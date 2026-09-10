"""Fabricated offline audit receipts; these never establish native evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.mirofish import save
from scripts import audit_scale_v2 as audit
from scripts import prepare_scale_v2 as prepare
from tests.test_scale_v2_contract import example_policy, importer


def native_fixture(*, unknown=False, failed=False):
    rows = [{'dispatch': 1, 'reserved_tokens': 100, 'charged_tokens': 5, 'output_cap': 4096,
        'accounting': 'reported', 'status': 'completed', 'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5}]
    if unknown:
        rows.append({'dispatch': 2, 'reserved_tokens': 100, 'charged_tokens': 100, 'output_cap': 4096,
            'accounting': 'reservation', 'status': 'dispatch_error', 'input_tokens': None,
            'output_tokens': None, 'total_tokens': None})
    return {'private_prompt': 'PRIVATE_CANARY', 'success': not failed, 'infrastructure_valid': not failed,
        'result': {'native': {'evaluation_budget': {'operations': rows, 'physical_model_calls': len(rows),
            'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5, 'reported_tokens': 5,
            'charged_tokens': 105 if unknown else 5, 'accounting_complete': not unknown}}},
        'usage': {'api_calls': len(rows), 'prompt_tokens': 3, 'completion_tokens': 2,
            'total_tokens': None if unknown else 5, 'charged_tokens': 105 if unknown else 5, 'complete': not unknown}}


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory()); self.root = Path(self.temp)

    def test_failed_behavior_keeps_known_usage(self):
        cost = audit.native_cost(native_fixture(failed=True))
        self.assertEqual((cost['known_physical_calls'], cost['known_tokens']), (1, 5))
        self.assertTrue(cost['accounting_complete'])

    def test_native_unknown_keeps_known_prefix_and_reservation(self):
        cost = audit.native_cost(native_fixture(unknown=True))
        self.assertEqual((cost['known_physical_calls'], cost['known_tokens']), (2, 5))
        self.assertEqual(cost['charged_or_reserved_tokens'], 105)
        self.assertFalse(cost['accounting_complete'])

    def test_native_overrun_retains_actual_observed_usage(self):
        record = native_fixture(); record['result']['native']['evaluation_budget']['operations'][0]['reserved_tokens'] = 4
        self.assertEqual(audit.native_cost(record)['known_tokens'], 5)

    def test_boolean_usage_or_inconsistent_totals_rejected(self):
        record = native_fixture(); record['usage']['api_calls'] = True
        with self.assertRaises(ValueError): audit.native_cost(record)
        record = native_fixture(); record['result']['native']['evaluation_budget']['operations'][0]['total_tokens'] = 8
        with self.assertRaises(ValueError): audit.native_cost(record)

    def test_pending_work_retains_conservative_action_reservation(self):
        save(self.root / 'INFLIGHT.json', {'kind': 'work', 'key': 'fixture', 'day': 0})
        cost = audit.employee_accounting(self.root)
        self.assertEqual(cost['total']['known_physical_calls'], 0)
        self.assertEqual(cost['total']['charged_or_reserved_model_calls'], 16)
        self.assertEqual(cost['total']['charged_or_reserved_tokens'], 250000)
        self.assertFalse(cost['total']['accounting_complete'])

    def test_returned_pending_work_is_not_double_counted(self):
        save(self.root / 'INFLIGHT.json', {'kind': 'work', 'key': 'fixture', 'day': 0})
        save(self.root / 'work/fixture/session.json', native_fixture())
        self.assertEqual(audit.employee_accounting(self.root)['total']['known_physical_calls'], 1)

    def test_orphan_native_directory_without_marker_cannot_mean_zero_cost(self):
        (self.root / 'work/fixture').mkdir(parents=True)
        result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['charged_or_reserved_model_calls'], 16)
        self.assertFalse(result['total']['accounting_complete'])

    def progress(self, *, missing=False, optimizer_unknown=False):
        directory = self.root / 'learning/d007-firm-0__renewal-regulated'
        relative = str((directory / 'trial-000/session.json').relative_to(self.root))
        if not missing: save(self.root / relative, native_fixture())
        transport = {'status': 'transport_failed' if optimizer_unknown else 'completed', 'model_calls': 1,
            'tokens': None if optimizer_unknown else 7, 'input_tokens': None if optimizer_unknown else 4,
            'output_tokens': None if optimizer_unknown else 3, 'accounting_complete': not optimizer_unknown,
            'optimizer_prompt': 'PRIVATE_CANARY', 'response': 'PRIVATE_CANARY'}
        progress = {'replay_artifacts': [{'attempt_index': 0, 'session_path': relative,
            'session_sha256': None if missing else audit.sha(self.root / relative),
            'limits': {'max_model_calls': 16, 'max_tokens': 250000}}],
            'optimizer_dispatches': [{'attempt_index': 0, 'limits': {'max_model_calls': 1, 'max_tokens': 32768},
                'receipt': {k: transport[k] for k in ('status', 'model_calls', 'tokens')}}],
            'optimizer_transport_audit': [transport]}
        save(directory / 'progress.json', progress)
        return directory, progress

    def test_learning_target_and_optimizer_separate_without_ledger_double_count(self):
        self.progress(); result = audit.employee_accounting(self.root)
        self.assertEqual(result['scopes']['learning_target']['known_tokens'], 5)
        self.assertEqual(result['scopes']['optimizer']['known_tokens'], 7)
        self.assertEqual(result['total']['known_physical_calls'], 2)
        self.assertEqual(result['total']['known_tokens'], 12)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_missing_replay_and_optimizer_timeout_keep_different_reservations(self):
        self.progress(missing=True, optimizer_unknown=True); result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['known_physical_calls'], 1)
        self.assertEqual(result['total']['charged_or_reserved_model_calls'], 17)
        self.assertEqual(result['total']['charged_or_reserved_tokens'], 282768)
        self.assertEqual(result['total']['unresolved_records'], 2)

    def test_late_progress_tamper_preserves_independent_target_cost(self):
        directory, progress = self.progress()
        progress['replay_artifacts'][0]['session_sha256'] = '0' * 64
        save(directory / 'progress.json', progress)
        result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['known_tokens'], 5)
        self.assertEqual(result['total']['charged_or_reserved_tokens'], 4000000)
        self.assertTrue(result['issues']); self.assertFalse(result['total']['accounting_complete'])

    def test_malformed_later_epoch_does_not_erase_earlier_usage(self):
        save(self.root / 'work/fixture/session.json', native_fixture())
        save(self.root / 'learning/d007-firm-0__renewal-regulated/progress.json', {'private': 'PRIVATE_CANARY'})
        result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['known_tokens'], 5)
        self.assertEqual(result['total']['charged_or_reserved_tokens'], 4000005)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_pending_learning_without_progress_is_unknown(self):
        save(self.root / 'INFLIGHT.json', {'kind': 'learning', 'key': 'd007-fixture', 'day': 7})
        result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['charged_or_reserved_tokens'], 4000000)
        self.assertFalse(result['total']['accounting_complete'])

    def test_pending_epoch_subtracts_already_counted_trial_from_reservation(self):
        save(self.root / 'INFLIGHT.json', {'kind': 'learning', 'key': 'd007-fixture', 'day': 7})
        save(self.root / 'learning/d007-fixture/trial-000/session.json', native_fixture())
        result = audit.employee_accounting(self.root)
        self.assertEqual(result['total']['known_tokens'], 5)
        self.assertEqual(result['total']['charged_or_reserved_tokens'], 4000000)
        self.assertEqual(result['total']['charged_or_reserved_model_calls'], 200)
        self.assertFalse(result['total']['accounting_complete'])
        self.assertTrue(result['issues'])

    def test_optimizer_cannot_report_tokens_without_a_physical_dispatch(self):
        with self.assertRaisesRegex(ValueError, 'tokens_without_dispatch'):
            audit.optimizer_cost({'limits': {'max_model_calls': 1, 'max_tokens': 32768}},
                {'accounting_complete': True, 'model_calls': 0, 'input_tokens': 3, 'output_tokens': 2, 'tokens': 5})


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory()); self.root = Path(self.temp)
        self.out = self.root / 'lifespan/artifacts/fixture'
        self.sources = {'fixture.py': 'a' * 64}
        self.deps = {key: {'revision': 'b' * 40} for key in ('hermes', 'mirofish', 'skillopt')}
        self.tools = {key: 'c' * 64 for key in audit.contract.REGISTRATION_TOOLS}
        self.enterContext(patch.object(prepare, 'ROOT', self.root))
        self.enterContext(patch.object(audit, 'source_hashes', return_value=self.sources))
        self.enterContext(patch.object(audit, 'dependency_provenance', return_value=self.deps))
        self.enterContext(patch.object(audit, 'tooling', return_value=self.tools))
        self.campaign = prepare.prepare(self.out, launch_policy=example_policy(), target_model='fixture',
            model_base_url='https://fixture.invalid', cohort_importer=importer, sources=self.sources,
            dependencies=self.deps, registration_tools=self.tools)
        self.reviewed = audit.sha(self.out / 'campaign.json')

    def inspect(self, **kw):
        return audit.audit_campaign_v2(self.out, campaign_sha256=self.reviewed, **kw)

    def completed(self, root, campaign, slot):
        return ({'status': 'completed', 'ok': True, 'completed': True, 'sessions': 1, 'updates': 0,
            'accepted_updates': 0, 'learner_physical_calls': 1, 'learner_measured_tokens': 5,
            'private': 'PRIVATE_CANARY'}, {'seed': slot['seed'], 'algorithm': slot['algorithm']})

    def fixtures(self):
        for slot in self.campaign['slots']:
            save(self.out / slot['relative_path'] / 'work/fixture/session.json', native_fixture())
        save(self.out / 'EXECUTION.json', {'fixture': True})
        self.enterContext(patch.object(audit, 'run_check', side_effect=self.completed))
        self.enterContext(patch.object(audit, 'actor_accounting', return_value={
            'logical_requests': 1, 'measured_physical_requests': 1, 'measured_tokens': 3,
            'unknown_requests': 0, 'reserved_output_tokens': 0, 'accounting_complete': True}))
        self.lifecycle = self.enterContext(patch.object(audit, 'lifecycle_audit', return_value={'ok': True}))
        self.comparison = self.enterContext(patch.object(audit, 'compare_reports_v2', return_value={
            'rejected_pairs': [], 'eligible_pairs': [{'seed': seed} for seed in audit.contract.SEEDS]}))

    def test_pristine_registration_keeps_all_slots_no_endpoint(self):
        result = self.inspect()
        self.assertTrue(result['ok'], result); self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(len(result['runs']), 6); self.assertEqual(len(result['missing_or_invalid_pairs']), 3)
        self.assertIsNone(result['comparison']); self.assertFalse(result['primary_endpoint_available'])
        self.assertFalse(result['accounting']['employee_and_optimizer']['all_world_costs_reconciled'])
        self.assertFalse(self.inspect(strict=True)['ok'])

    def test_missing_or_changed_reviewed_hash_keeps_six_unverified_slots(self):
        for digest in (None, '0' * 64, True):
            result = audit.audit_campaign_v2(self.out, campaign_sha256=digest)
            self.assertFalse(result['ok']); self.assertEqual(len(result['runs']), 6)
            self.assertIsNone(result['comparison'])

    def test_coherent_policy_rewrite_rejected_by_external_hash(self):
        value = deepcopy(self.campaign); value['launch_policy']['workers'] = 1
        save(self.out / 'campaign.json', value)
        self.assertFalse(self.inspect()['ok'])

    def test_six_complete_worlds_three_pairs_required_without_adoption_requirement(self):
        self.fixtures(); result = self.inspect(strict=True)
        self.assertTrue(result['ok'], result); self.assertTrue(result['primary_endpoint_available'])
        self.assertEqual((result['completed_runs'], result['complete_pairs']), (6, 3))
        self.assertEqual(result['accounting']['employee_and_optimizer']['known_tokens'], 30)
        self.assertEqual(result['accounting']['contracted_interviews']['measured_tokens'], 18)
        self.assertIsNone(result['accounting']['unmetered_environment']['tokens'])
        self.assertFalse(result['accounting']['all_in_accounting_complete'])
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_one_invalid_world_suppresses_every_pair_endpoint_keeps_costs(self):
        self.fixtures()
        def one_bad(root, campaign, slot):
            if slot['run_id'] == campaign['slots'][0]['run_id']: raise ValueError('fixture_raw_audit_failed')
            return self.completed(root, campaign, slot)
        with patch.object(audit, 'run_check', side_effect=one_bad): result = self.inspect()
        self.assertFalse(result['ok']); self.assertEqual(len(result['runs']), 6)
        self.assertEqual(result['complete_pairs'], 2); self.comparison.assert_not_called()
        self.assertIsNone(result['comparison']); self.assertEqual(result['accounting']['employee_and_optimizer']['known_tokens'], 30)

    def test_cleanup_failure_suppresses_endpoint_not_known_costs(self):
        self.fixtures(); self.lifecycle.side_effect = ValueError('unconfirmed_native_cleanup')
        result = self.inspect(strict=True)
        self.assertFalse(result['ok']); self.assertIsNone(result['comparison'])
        self.assertEqual(result['accounting']['employee_and_optimizer']['known_physical_calls'], 6)
        self.assertIsNone(result['model_quality_score'])

    def test_missing_supervisor_cannot_complete(self):
        self.fixtures(); (self.out / 'EXECUTION.json').unlink()
        result = self.inspect(strict=True)
        self.assertFalse(result['ok']); self.assertFalse(result['primary_endpoint_available'])

    def test_completed_cost_must_close_to_independent_world_audit(self):
        self.fixtures(); slot = self.campaign['slots'][0]
        save(self.out / slot['relative_path'] / 'work/fixture/session.json', native_fixture(unknown=True))
        result = self.inspect(strict=True)
        self.assertFalse(result['ok']); self.assertEqual(result['accounting']['employee_and_optimizer']['known_tokens'], 30)
        self.assertEqual(result['accounting']['employee_and_optimizer']['charged_or_reserved_tokens'], 130)
        self.comparison.assert_not_called()

    def test_pairing_rejection_suppresses_primary(self):
        self.fixtures(); self.comparison.return_value = {'rejected_pairs': [{'private': 'PRIVATE_CANARY'}], 'eligible_pairs': []}
        result = self.inspect(strict=True)
        self.assertFalse(result['ok']); self.assertIsNone(result['comparison'])
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_exception_text_cannot_leak_private_values(self):
        self.fixtures(); self.lifecycle.side_effect = ValueError('PRIVATE_CANARY /absolute/private/path')
        result = self.inspect()
        self.assertFalse(result['ok']); self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_untrusted_status_or_hash_fields_cannot_leak_private_text(self):
        self.fixtures()
        def bad(root, campaign, slot):
            value, report = self.completed(root, campaign, slot)
            value['status'] = 'PRIVATE_CANARY'
            return value, report
        with patch.object(audit, 'run_check', side_effect=bad): result = self.inspect()
        self.assertFalse(result['ok']); self.assertNotIn('PRIVATE_CANARY', json.dumps(result))


class ActorCostTests(unittest.TestCase):
    def setUp(self):
        from lifespan.ecosystem import Ecosystem
        from lifespan.actor_contract import descriptor, wire
        self.temp = self.enterContext(tempfile.TemporaryDirectory()); self.root = Path(self.temp)
        eco = Ecosystem(days=20, seed=211, enterprise_count=4, consumer_count=8)
        self.actor = eco.participants()[0]['id']; self.wire = wire
        self.contract = descriptor(audit.contract.ACTOR_CONTRACT, 'employee')
        save(self.root / 'checkpoint.json', {'ecosystem': eco.checkpoint()})
        save(self.root / 'manifest.json', {'config': {'actor_output_contract': audit.contract.ACTOR_CONTRACT}})
        save(self.root / 'actors/mirofish_state.json', {'simulation': {'simulation_id': 'fixture-native'}})
        record = {'prompt': 'PRIVATE_CANARY', 'response': 'PRIVATE_CANARY'}
        save(self.root / 'actors/mirofish_interviews/first.json', record)
        self.rows = [{'key': 'first', 'actor': self.actor, 'status': 'completed', 'output_contract': self.contract,
            'prompt_sha256': wire.text_hash(record['prompt']), 'response_sha256': wire.text_hash(record['response'])},
            {'key': 'pending', 'actor': self.actor, 'status': 'dispatched', 'output_contract': self.contract}]
        save(self.root / 'actors/evaluation_interview_ledger.json', {'requests': self.rows})

    def test_later_unknown_actor_does_not_erase_measured_receipt_prefix(self):
        expected = {'logical_requests': 2, 'measured_physical_requests': 1, 'measured_tokens': 17,
            'unknown_requests': 1, 'reserved_output_tokens': 4096}
        with patch('lifespan.actor_contract.verify_record', return_value={'physical_requests_dispatched': 1,
                'total_tokens': 17, 'output_sha256': self.rows[0]['response_sha256']}), \
             patch('lifespan.actor_contract.audit_interviews', return_value=expected):
            result = audit.actor_accounting(self.root, completed=False)
        self.assertFalse(result['accounting_complete']); self.assertEqual(result['measured_tokens'], 17)
        self.assertEqual(result['reserved_output_tokens'], 4096)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_global_actor_integrity_failure_retains_independently_verified_prefix(self):
        with patch('lifespan.actor_contract.verify_record', return_value={'physical_requests_dispatched': 1,
                'total_tokens': 17, 'output_sha256': self.rows[0]['response_sha256']}), \
             patch('lifespan.actor_contract.audit_interviews', side_effect=self.wire.ContractError('fixture_binding_failed')):
            result = audit.actor_accounting(self.root, completed=False)
        self.assertFalse(result['accounting_complete']); self.assertTrue(result['issues'])
        self.assertEqual(result['measured_physical_requests'], 1); self.assertEqual(result['measured_tokens'], 17)

    def test_duplicate_logical_requests_cannot_double_count(self):
        save(self.root / 'actors/evaluation_interview_ledger.json', {'requests': [self.rows[0], self.rows[0]]})
        with self.assertRaisesRegex(ValueError, 'ledger_inventory'):
            audit.actor_accounting(self.root, completed=False)


class LifecycleTests(unittest.TestCase):
    """Stub only separately tested process receipt validation; no native launch."""
    setUp = CampaignTests.setUp
    def lifecycle_fixture(self):
        from scripts import scale_v2_process as process
        limits = {'world_cleanup_seconds': 120, 'service_cleanup_seconds': 30,
                  'service_startup_seconds': 120, 'observation_interval_seconds': .25}
        self.enterContext(patch.dict('sys.modules', {'scripts.run_scale_v2': SimpleNamespace(LAUNCH_LIMITS=limits)}))
        execution = {'campaign_sha256': self.reviewed, 'installation': {'private': 'PRIVATE_CANARY'},
            'supervisor_identity': {'pid': 100, 'start_ticks': 10, 'uid': 1000, 'boot_id': 'fixture'}}
        self.enterContext(patch.object(audit, 'execution_check', return_value=execution))
        save(self.out / 'SERVICE_START.json', {'binding': execution['installation'], 'root_identity': {
            'pid': 110, 'ppid': 100, 'start_ticks': 11, 'uid': 1000, 'boot_id': 'fixture'}})
        save(self.out / 'SERVICE_CLEANUP.json', {'fixture': 'separately_stub_validated'})
        self.service = {'ok': True, 'hashes': {}, 'start': {'private': 'PRIVATE_CANARY'},
            'started_monotonic': 1, 'ended_monotonic': 101, 'cleanup_started_monotonic': 100,
            'cleanup_limit_seconds': 30, 'root_exitcode': 0, 'cleanup_confirmed': True, 'ready_monotonic': 2}
        self.worlds = {}; results = []
        for index, slot in enumerate(self.campaign['slots']):
            directory = self.out / slot['relative_path'] / 'lifecycle'
            save(directory / 'WORLD_START.json', {'root_identity': {
                'pid': 101 + index, 'ppid': 100, 'start_ticks': 11 + index, 'uid': 1000, 'boot_id': 'fixture'}})
            hashes = {'WORLD_START.json': str(index) * 64, 'WORLD_CLEANUP.json': str(index + 1) * 64}
            self.worlds[slot['run_id']] = {'ok': True, 'hashes': hashes,
                'started_monotonic': 10 + index, 'ended_monotonic': 30 + index,
                'cleanup_started_monotonic': 29 + index, 'cleanup_limit_seconds': 120,
                'root_exitcode': 0, 'cleanup_confirmed': True}
            results.append({'run_id': slot['run_id'], 'exit_code': 0, 'elapsed_seconds': 20,
                'termination_reason': 'exited', 'lifecycle': {
                    'start_sha256': hashes['WORLD_START.json'], 'cleanup_sha256': hashes['WORLD_CLEANUP.json']}})
        save(self.out / 'execution_results.json', {'schema_version': 2, 'campaign_sha256': self.reviewed, 'runs': results})
        self.enterContext(patch.object(process, 'validate_service_receipts', side_effect=lambda *a, **k: deepcopy(self.service)))
        self.enterContext(patch.object(process, 'validate_world_receipts', side_effect=lambda directory, run, *a, **k: deepcopy(self.worlds[run.name])))

    def test_lifecycle_six_slot_chain_and_private_start_projection(self):
        self.lifecycle_fixture(); result = audit.lifecycle_audit(self.out, self.campaign, True)
        self.assertTrue(result['ok']); self.assertEqual(result['peak_parallel_worlds'], 6)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_concurrency_reconstructed_from_full_cleanup_intervals(self):
        self.lifecycle_fixture(); self.campaign['launch_policy']['workers'] = 5
        with self.assertRaisesRegex(ValueError, 'concurrency_limit'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_distinct_worlds_cannot_share_one_native_simulation(self):
        self.lifecycle_fixture()
        for world in self.worlds.values(): world['simulation_id'] = 'shared-fixture'
        with self.assertRaisesRegex(ValueError, 'shared_native_simulation'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_world_must_follow_proven_service_readiness_and_startup_cap(self):
        self.lifecycle_fixture(); self.service['ready_monotonic'] = 11
        with self.assertRaisesRegex(ValueError, 'precedes_service_readiness'):
            audit.lifecycle_audit(self.out, self.campaign, True)
        self.service['ready_monotonic'] = 122
        with self.assertRaisesRegex(ValueError, 'startup_wall_limit'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_interruption_cannot_be_hidden_by_six_complete_reports(self):
        self.lifecycle_fixture(); save(self.out / 'SUPERVISOR_INTERRUPTED.json', {'fixture': True})
        with self.assertRaisesRegex(ValueError, 'supervisor_interrupted'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_completed_world_requires_normal_termination_reason(self):
        self.lifecycle_fixture(); path = self.out / 'execution_results.json'; value = audit.read(path)
        value['runs'][0]['termination_reason'] = 'observation_failed'; save(path, value)
        with self.assertRaisesRegex(ValueError, 'abnormal_termination'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_execution_wall_and_cleanup_allowance_checked_separately(self):
        self.lifecycle_fixture(); self.campaign['launch_policy']['per_world_wall_seconds'] = 18
        with self.assertRaisesRegex(ValueError, 'execution_wall'):
            audit.lifecycle_audit(self.out, self.campaign, True)
        self.campaign['launch_policy']['per_world_wall_seconds'] = 72000
        next(iter(self.worlds.values()))['cleanup_limit_seconds'] = 999
        with self.assertRaisesRegex(ValueError, 'cleanup_allowance'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_service_cannot_be_torn_down_before_world_cleanup(self):
        self.lifecycle_fixture(); self.service['cleanup_started_monotonic'] = 30
        with self.assertRaisesRegex(ValueError, 'service_closed_before'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_partial_campaign_terminal_world_overrun_is_invalid(self):
        self.lifecycle_fixture()
        # Five worlds have not launched; the sole terminal world remains bound
        # by its registered execution allowance, independently of completion.
        for slot in self.campaign['slots'][1:]:
            (self.out / slot['relative_path'] / 'lifecycle/WORLD_START.json').unlink()
        path = self.out / 'execution_results.json'; value = audit.read(path)
        value['runs'] = value['runs'][:1]; save(path, value)
        self.campaign['launch_policy']['per_world_wall_seconds'] = 19
        self.assertTrue(audit.lifecycle_audit(self.out, self.campaign, False)['ok'])
        self.campaign['launch_policy']['per_world_wall_seconds'] = 18
        with self.assertRaisesRegex(ValueError, 'world_execution_wall_limit'):
            audit.lifecycle_audit(self.out, self.campaign, False)

    def test_different_supervisor_parent_cannot_own_world(self):
        self.lifecycle_fixture(); path = self.out / self.campaign['slots'][0]['relative_path'] / 'lifecycle/WORLD_START.json'
        value = audit.read(path); value['root_identity']['ppid'] = 999; save(path, value)
        with self.assertRaisesRegex(ValueError, 'supervisor_process_binding'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_different_supervisor_cannot_own_service(self):
        self.lifecycle_fixture(); path = self.out / 'SERVICE_START.json'; original = audit.read(path)
        for key, value in (('ppid', 999), ('uid', 999), ('boot_id', 'foreign'), ('start_ticks', 9)):
            changed = deepcopy(original); changed['root_identity'][key] = value; save(path, changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'service_supervisor_process_binding'):
                audit.lifecycle_audit(self.out, self.campaign, True)

    def test_terminal_row_must_bind_raw_cleanup_and_exact_elapsed(self):
        self.lifecycle_fixture(); path = self.out / 'execution_results.json'
        value = audit.read(path); value['runs'][0]['elapsed_seconds'] = 19; save(path, value)
        with self.assertRaisesRegex(ValueError, 'supervisor_world_receipt'):
            audit.lifecycle_audit(self.out, self.campaign, True)

    def test_terminal_inventory_cannot_omit_or_duplicate_world(self):
        self.lifecycle_fixture(); path = self.out / 'execution_results.json'; original = audit.read(path)
        for rows in (original['runs'][:-1], [*original['runs'], original['runs'][0]]):
            save(path, {**original, 'runs': rows})
            with self.assertRaises(ValueError): audit.lifecycle_audit(self.out, self.campaign, True)

    def test_completed_campaign_requires_confirmed_service_and_world_cleanup(self):
        self.lifecycle_fixture(); self.service['cleanup_confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'cleanup_incomplete'):
            audit.lifecycle_audit(self.out, self.campaign, True)
        self.service['cleanup_confirmed'] = True; next(iter(self.worlds.values()))['cleanup_confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'world_exit_or_cleanup'):
            audit.lifecycle_audit(self.out, self.campaign, True)


class ExecutionBindingTests(unittest.TestCase):
    setUp = CampaignTests.setUp

    def execution_fixture(self):
        self.campaign['source_sha256'] = {'fixture.py': hashlib.sha256(b'fixture').hexdigest()}
        self.campaign['registration_tools_sha256'] = {'scripts/fixture_tool.py': hashlib.sha256(b'fixture').hexdigest()}
        prerequisites = {'schema_version': 1, 'verified': True, 'checks': [{'fixture': True}]}
        save(self.out / 'PREREQUISITES.json', prerequisites)
        value = {'schema_version': 2, 'kind': 'scale-v2-native-execution', 'campaign_sha256': self.reviewed,
            'workers': self.campaign['launch_policy']['workers'], 'repository_commit': 'a' * 40,
            'source_commit_verified': True, 'supervisor_pid': 100,
            'supervisor_identity': {'pid': 100, 'start_ticks': 5, 'uid': 1000, 'boot_id': 'fixture'},
            'prerequisites_sha256': audit.sha(self.out / 'PREREQUISITES.json'), 'prerequisite_paths': {},
            **{k: self.campaign[k] for k in ('source_sha256', 'registration_tools_sha256', 'dependencies')}}
        save(self.out / 'EXECUTION.json', value)
        self.enterContext(patch.object(audit.subprocess, 'check_output', return_value=b'fixture'))
        self.verify = self.enterContext(patch('scripts.scale_v2_prerequisites.verify_prerequisites',
            return_value=prerequisites, create=True))
        return value

    def test_exact_commit_and_prerequisite_bindings_are_required(self):
        value = self.execution_fixture()
        self.assertEqual(audit.execution_check(self.out, self.campaign), value)
        self.verify.assert_called_once_with(self.campaign, {})

    def test_false_commit_or_rewritten_tool_inventory_cannot_dispatch(self):
        value = self.execution_fixture()
        for field, replacement in (('source_commit_verified', False), ('repository_commit', None),
                ('registration_tools_sha256', {}), ('supervisor_pid', True)):
            save(self.out / 'EXECUTION.json', {**value, field: replacement})
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.execution_check(self.out, self.campaign)

    def test_prerequisite_hash_and_full_reaudit_must_both_match(self):
        value = self.execution_fixture()
        save(self.out / 'PREREQUISITES.json', {'schema_version': 1, 'verified': True, 'checks': []})
        with self.assertRaisesRegex(ValueError, 'prerequisite_hash'):
            audit.execution_check(self.out, self.campaign)
        value['prerequisites_sha256'] = audit.sha(self.out / 'PREREQUISITES.json')
        save(self.out / 'EXECUTION.json', value)
        with self.assertRaisesRegex(ValueError, 'prerequisite_audit'):
            audit.execution_check(self.out, self.campaign)


if __name__ == '__main__':
    unittest.main()
