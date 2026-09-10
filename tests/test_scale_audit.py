"""Offline integrity/tamper fixtures; these are not native performance evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.evaluation.protocol import SEED_SKILL, digest, scenario, ExperimentConfig
from lifespan.mirofish import save
from scripts import audit_scale as audit, run_scale


DEPS = {name: {'revision': 'offline-fixture-' + name} for name in ('hermes', 'mirofish', 'skillopt')}
CREDS = {'model': 'offline-fixture', 'base_url': 'https://fixture.example.invalid'}


def importer(cache, path, *, count, seed):
    cohort = {'personas': [{'persona_id': f'fixture-{seed}-{i}', 'private': 'DO_NOT_EXPORT'} for i in range(count)]}
    save(path, cohort)
    return cohort


class ScaleAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.out = Path(self.temp) / 'study'
        self.enterContext(patch.object(run_scale, 'dependency_provenance', return_value=DEPS))
        self.enterContext(patch.object(audit, 'dependency_provenance', return_value=DEPS))
        self.enterContext(patch.object(run_scale, 'credentials', side_effect=AssertionError('No native calls')))
        self.manifest = run_scale.prepare(self.out, creds=CREDS, cohort_importer=importer)

    def test_prepared_retains_all_six_planned_runs_and_unknown_cost(self):
        result = audit.audit_campaign(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual((result['completed_runs'], result['complete_pairs']), (0, 0))
        self.assertEqual(len(result['runs']), 6)
        self.assertEqual(len(result['missing_or_invalid_pairs']), 3)
        self.assertIsNone(result['accounting']['learner_physical_calls'])
        self.assertIsNone(result['accounting']['environment']['tokens'])
        self.assertFalse(audit.audit_campaign(self.out, strict=True)['ok'])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))

    def test_fixed_contract_and_source_tampering_rejected(self):
        mutations = [lambda m: m.update(days=21), lambda m: m['seeds'].reverse(),
            lambda m: m['population'].update(employees=13), lambda m: m['budgets'].update(actor_tokens=0),
            lambda m: m['design'].update(selection='Keep winners'),
            lambda m: m['slots'][0].update(relative_path='../outside'),
            lambda m: m['slots'][0]['config'].update(update_days=[3, 7, 11, 15]),
            lambda m: m['source_sha256'].pop('scripts/scale_summary.py'),
            lambda m: m['source_sha256'].update({'scripts/audit_scale.py': '0' * 64}),
            lambda m: m['dependencies']['hermes'].update(revision='changed')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = deepcopy(self.manifest); mutation(data)
                save(self.out / 'campaign.json', data)
                self.assertFalse(audit.audit_campaign(self.out)['ok'])
        save(self.out / 'campaign.json', self.manifest)

    def test_paired_cohort_cannot_be_replaced_by_self_consistent_other_cohort(self):
        slot = self.manifest['slots'][0]
        path = self.out / slot['relative_path'] / 'persona_cohort.json'
        save(path, {'personas': [{'persona_id': 'other-' + str(i)} for i in range(25)]})
        slot['persona_cohort_sha256'] = audit.sha(path)
        save(self.out / 'campaign.json', self.manifest)
        self.assertFalse(audit.audit_campaign(self.out)['ok'])

    def test_execution_marker_is_bound_to_published_campaign_and_worker_cap(self):
        save(self.out / 'EXECUTION.json', {'campaign_sha256': audit.sha(self.out / 'campaign.json'), 'workers': 6})
        self.assertTrue(audit.audit_campaign(self.out)['ok'])
        for bad in ({'campaign_sha256': '0' * 64, 'workers': 6},
                    {'campaign_sha256': audit.sha(self.out / 'campaign.json'), 'workers': 7}):
            save(self.out / 'EXECUTION.json', bad)
            self.assertFalse(audit.audit_campaign(self.out)['ok'])

    def initial_checkpoint(self):
        from lifespan.evaluation.runner import _new_state
        from lifespan.evaluation.hermes_transport import manifest_fields
        slot = self.manifest['slots'][0]
        cfg = ExperimentConfig(**slot['config']); spec = scenario(cfg)
        eco, state = _new_state(cfg, spec)
        run = self.out / slot['relative_path']
        save(run / 'manifest.json', {'config': cfg.public(), 'scenario': spec,
            **manifest_fields(cfg),
            **{key: self.manifest[key] for key in ('source_sha256', 'dependencies', 'target_model', 'model_base_url')}})
        cp = {'ecosystem': eco.checkpoint(), 'runner': state}
        save(run / 'checkpoint.json', cp)
        return slot, run, cp

    def test_native_bootstrap_before_v000_files_remains_initializing(self):
        slot, run, cp = self.initial_checkpoint()
        result = audit.audit_campaign(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['runs'][0]['status'], 'initializing')
        self.assertFalse(audit.audit_campaign(self.out, strict=True)['ok'])

    def test_completed_run_requires_independent_eligibility_log_audit(self):
        slot, run, cp = self.initial_checkpoint()
        cp['ecosystem']['day'] = 21
        save(run / 'checkpoint.json', cp)
        save(run / 'REPORT.json', {'status': 'completed'})
        with patch.object(audit, 'audit_run', return_value={'ok': True}), \
             patch.object(audit, 'actor_check', return_value={'logical_requests': 0}):
            result = audit.audit_campaign(self.out)
        self.assertFalse(result['ok'])
        self.assertEqual(result['runs'][0]['error'], 'completed_run_learning_eligibility_or_exposure_mismatch')

    def completed_fixture(self, root, manifest, slot):
        """Stub only the already separately tested native/v2 auditors."""
        return ({'run_id': slot['run_id'], 'seed': slot['seed'], 'algorithm': slot['algorithm'],
                 'ok': True, 'completed': True, 'status': 'completed', 'learner_physical_calls': 10,
                 'learner_measured_tokens': 100, 'actor_accounting': {'logical_requests': 2}}, slot)

    def comparison_fixture(self, reports):
        pairs = [seed for seed in audit.SEEDS if {r['algorithm'] for r in reports if r['seed'] == seed} == set(audit.ARMS)]
        return {'eligible_pairs': pairs, 'rejected_pairs': []}

    def supervisor_receipts(self):
        rows = []
        for slot in self.manifest['slots']:
            run = self.out / slot['relative_path']
            identifier = 'offline-env-' + slot['run_id']
            cleanup = {'status': 'closed', 'simulation_id': identifier}
            save(run / 'actors/mirofish_state.json', {'simulation': {'simulation_id': identifier}})
            save(run / 'SUPERVISOR_ACTOR_CLEANUP.json', cleanup)
            rows.append({'run_id': slot['run_id'], 'exit_code': 0, 'actor_cleanup': cleanup})
        save(self.out / 'execution_results.json', {'runs': rows})
        save(self.out / 'EXECUTION.json', {'campaign_sha256': audit.sha(self.out / 'campaign.json'), 'workers': 6})

    def test_complete_aggregation_and_saved_comparison_tamper(self):
        self.supervisor_receipts()
        with patch.object(audit, 'run_check', side_effect=self.completed_fixture), \
             patch.object(audit, 'compare_reports_v2', side_effect=self.comparison_fixture):
            result = audit.audit_campaign(self.out, strict=True)
            self.assertTrue(result['ok'], result)
            self.assertTrue(result['accounting_verified'])
            self.assertEqual(result['accounting']['learner_physical_calls'], 60)
            self.assertEqual(result['accounting']['learner_measured_tokens'], 600)
            self.assertFalse(result['accounting']['environment']['accounting_complete'])
            save(self.out / 'COMPARISON.json', result['comparison'])
            self.assertTrue(audit.audit_campaign(self.out, strict=True)['ok'])
            save(self.out / 'COMPARISON.json', {'eligible_pairs': [], 'rejected_pairs': []})
            self.assertFalse(audit.audit_campaign(self.out, strict=True)['ok'])

    def test_cleanup_failure_preserves_verified_cost_and_cannot_be_quality_failure(self):
        self.supervisor_receipts()
        receipts = audit.read(self.out / 'execution_results.json')
        receipts['runs'][0]['actor_cleanup']['status'] = 'close_unconfirmed'
        save(self.out / 'execution_results.json', receipts)
        with patch.object(audit, 'run_check', side_effect=self.completed_fixture), \
             patch.object(audit, 'compare_reports_v2', side_effect=self.comparison_fixture):
            result = audit.audit_campaign(self.out, strict=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'][0]['location'], 'supervisor_resource_cleanup')
        self.assertEqual(result['accounting']['learner_physical_calls'], 60)
        self.assertTrue(result['accounting_verified'])
        self.assertIsNone(result['model_quality_score'])

    def test_missing_supervisor_receipts_prevents_completed_campaign(self):
        with patch.object(audit, 'run_check', side_effect=self.completed_fixture), \
             patch.object(audit, 'compare_reports_v2', side_effect=self.comparison_fixture):
            result = audit.audit_campaign(self.out, strict=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'][0]['code'], 'completed_campaign_missing_supervisor_receipts')

    def test_invalid_world_remains_visible_and_never_becomes_failure_score(self):
        def partial(root, manifest, slot):
            if slot == manifest['slots'][0]:
                raise ValueError('fixture_native_receipt_invalid')
            return self.completed_fixture(root, manifest, slot)
        with patch.object(audit, 'run_check', side_effect=partial), \
             patch.object(audit, 'compare_reports_v2', side_effect=self.comparison_fixture):
            result = audit.audit_campaign(self.out)
        self.assertFalse(result['ok'])
        self.assertEqual((len(result['runs']), result['completed_runs'], result['complete_pairs']), (6, 5, 2))
        self.assertIsNone(result['model_quality_score'])
        self.assertIsNone(result['accounting']['learner_measured_tokens'])
        self.assertEqual(result['accounting']['verified_completed_run_tokens'], 500)
        self.assertEqual(result['missing_or_invalid_pairs'][0]['runs'], [self.manifest['slots'][0]['run_id']])


class ActorLedgerAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.run = Path(self.temp)
        self.cfg = audit.expected_config(211, 'no_learning')
        self.cp = {'ecosystem': {'firms': {'firm-0': {}}, 'worlds': {'firm-0': {'employees': {'incident-regulated': {}}}},
                               'consumers': {'consumer-0': {}}, 'agency': {'id': 'agency'}}, 'runner': {'sessions': []}}
        self.rows = []

    def add(self, key, actor, folder='actor_decisions', repair=False):
        final = key + '-repair' if repair else key
        native = {'employee_id': actor, 'prompt': 'Offline private fixture', 'response': '{"action":"hold"}'}
        save(self.run / 'actors/mirofish_interviews' / (final + '.json'), native)
        self.rows.append({'key': final, 'actor': actor, 'prompt_sha256': audit.text_sha(native['prompt']),
                          'response_sha256': audit.text_sha(native['response']), 'status': 'completed'})
        save(self.run / folder / (key + '.json'), {'view': {'actor_id': actor}, 'decision': {'action': 'hold'}})
        self.persist()

    def persist(self):
        save(self.run / 'actors/evaluation_interview_ledger.json', {'schema_version': 1, 'limit': 662,
             'accounting_unit': 'logical_mirofish_interview_request', 'physical_model_calls': None, 'tokens': None,
             'requests': self.rows})

    def test_incomplete_pending_logical_request_is_not_fabricated_physical_count(self):
        self.rows = [{'key': 'd000-agency', 'actor': 'agency', 'prompt_sha256': 'a' * 64, 'status': 'dispatched'}]
        self.persist()
        result = audit.actor_check(self.run, self.cfg, self.cp, False)
        self.assertEqual((result['logical_requests'], result['pending_requests']), (1, 1))
        self.assertIsNone(result['physical_model_calls'])
        with self.assertRaisesRegex(ValueError, 'uncertain_actor'):
            audit.actor_check(self.run, self.cfg, self.cp, True)

    def test_native_cache_and_enacted_decision_tamper_fail(self):
        self.add('d000-agency', 'agency')
        self.assertEqual(audit.actor_check(self.run, self.cfg, self.cp, False)['logical_requests'], 1)
        path = self.run / 'actor_decisions/d000-agency.json'
        original = audit.read(path)
        save(path, {'view': {'actor_id': 'agency'}, 'decision': {'action': 'tamper'}})
        with self.assertRaisesRegex(ValueError, 'differs_from_native'):
            audit.actor_check(self.run, self.cfg, self.cp, False)
        save(path, original)
        self.rows[0]['response_sha256'] = '0' * 64; self.persist()
        with self.assertRaisesRegex(ValueError, 'cache_binding'):
            audit.actor_check(self.run, self.cfg, self.cp, False)

    def test_orphan_repair_unmetered_cache_and_duplicate_requests_fail(self):
        self.add('d000-agency', 'agency', repair=True)
        with self.assertRaisesRegex(ValueError, 'orphan_actor_repair'):
            audit.actor_check(self.run, self.cfg, self.cp, False)
        self.add('d000-agency', 'agency')
        self.assertEqual(audit.actor_check(self.run, self.cfg, self.cp, False)['logical_requests'], 2)
        self.rows.append(deepcopy(self.rows[0])); self.persist()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            audit.actor_check(self.run, self.cfg, self.cp, False)

    def test_complete_schedule_is_independently_reconstructed(self):
        spec = scenario(ExperimentConfig(**self.cfg))
        days = set(range(0, 20, 4)) | {shock['day'] for shock in spec['shock_schedule']}
        for day in days:
            for actor in ('agency', 'firm-0', 'consumer-0'):
                self.add(f'd{day:03d}-{actor}', actor)
        self.assertEqual(audit.actor_check(self.run, self.cfg, self.cp, True)['logical_requests'], len(days) * 3)
        (self.run / 'actor_decisions/d000-agency.json').unlink()
        with self.assertRaisesRegex(ValueError, 'unreconciled_actor'):
            audit.actor_check(self.run, self.cfg, self.cp, True)


class LearningProgressAuditTests(unittest.TestCase):
    def setUp(self):
        # Reuse the actual pinned upstream consolidation fixture, adding only
        # synthetic physical receipts. No credentials or executor are native.
        from lifespan.tests.test_evaluation_learning_epochs import LearningEpochTests
        self.fixture = LearningEpochTests('test_epoch_caps_preserve_employee_budget_for_repeated_learning')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.run = self.fixture.out
        self.cfg = audit.expected_config(211, 'skillopt')
        self.fixture.config = SimpleNamespace(**self.cfg)
        employees = [f'firm-{firm}__{workflow}-regulated' for firm in range(4) for workflow in ('incident', 'renewal', 'access')]
        self.fixture.state['skills'] = {employee: SEED_SKILL for employee in employees}
        self.fixture.state['skill_versions'] = {employee: 0 for employee in employees}
        while self.fixture.eco.day < 7:
            self.fixture.eco.advance()
        self.fixture.native_calls, self.fixture.native_tokens = 1, 20
        self.fixture.perfect = False
        original = self.fixture.execute
        def execute(**kwargs):
            record = original(**kwargs)
            record['skill'] = {'content_sha256': audit.text_sha(kwargs['skill'])}
            record['result']['native']['evaluation_budget'] = {'physical_model_calls': 1, 'charged_tokens': 20,
                'operations': [{'output_cap': 4096}]}
            save(kwargs['root'] / 'session.json', record)
            return record
        self.update = self.fixture.run_epoch(executor=execute)
        self.progress_path = self.fixture.directory() / 'progress.json'

    def test_actual_upstream_replay_progress_matches_all_receipts(self):
        audit.learning_progress_check(self.run, self.cfg, self.update, [])
        self.assertEqual(len(self.update['replay_artifacts']), 12)
        self.assertEqual(len(audit.read(self.progress_path)['optimizer_dispatches']), 1)

    def test_raw_session_replacement_is_rejected(self):
        path = self.run / self.update['replay_artifacts'][0]['session_path']
        record = audit.read(path); record['success'] = not record['success']; save(path, record)
        with self.assertRaisesRegex(ValueError, 'raw_artifact_hash'):
            audit.learning_progress_check(self.run, self.cfg, self.update, [])

    def test_self_consistent_progress_quota_and_receipt_tampering_is_rejected(self):
        for key in ('quota', 'usage', 'attempt'):
            with self.subTest(key=key):
                update = deepcopy(self.update); progress = audit.read(self.progress_path)
                if key == 'quota':
                    update['epoch_allocation']['model_calls'] = 201
                elif key == 'usage':
                    update['replay_artifacts'][0]['usage']['api_calls'] = 0
                else:
                    update['replay_artifacts'][0]['attempt_index'] = 4
                progress['epoch_allocation'] = update['epoch_allocation']
                progress['replay_artifacts'] = update['replay_artifacts']
                save(self.progress_path, progress)
                with self.assertRaises(ValueError):
                    audit.learning_progress_check(self.run, self.cfg, update, [])
                progress['epoch_allocation'] = self.update['epoch_allocation']
                progress['replay_artifacts'] = self.update['replay_artifacts']
                save(self.progress_path, progress)

    def test_optimizer_dispatch_receipt_tamper_is_rejected(self):
        progress = audit.read(self.progress_path)
        progress['optimizer_dispatches'][0]['receipt']['tokens'] = 0
        save(self.progress_path, progress)
        with self.assertRaisesRegex(ValueError, 'optimizer_dispatch_binding'):
            audit.learning_progress_check(self.run, self.cfg, self.update, [])

    def test_eligibility_pool_and_original_deployed_version_are_bound(self):
        update = self.update
        log = {'employee': update['employee'], 'day': update['day'],
               'selected_ids': update['train_ids'] + update['validation_ids'], 'deployed_version_before': 0,
               'eligible': True, 'treatment_enabled': True}
        state = {'experiences': self.fixture.experiences, 'updates': [update], 'learning_eligibility': [log]}
        audit.eligibility_check(state, self.cfg)
        log['selected_ids'].reverse()
        with self.assertRaisesRegex(ValueError, 'selected_pool_mismatch'):
            audit.eligibility_check(state, self.cfg)
        log['selected_ids'].reverse(); log['deployed_version_before'] = 1
        with self.assertRaisesRegex(ValueError, 'deployed_version_mismatch'):
            audit.eligibility_check(state, self.cfg)


if __name__ == '__main__':
    unittest.main()
