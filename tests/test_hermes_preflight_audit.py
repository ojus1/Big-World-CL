"""Fabricated local receipts exercise auditing only; never native capability proof."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from tests import test_evaluation_audit as fixtures
from scripts.audit_hermes_preflight import physical_usage, native_session, cleanup_check, sha, audit_preflight, costs_check, aggregate_costs
from lifespan.evaluation.hermes_transport import contract
from lifespan.evaluation.protocol import SEED_SKILL
from lifespan.evaluation.runner import source_hashes
from lifespan.evaluation.runtime import install_skill
from lifespan.evaluation.tasks import grade_case

save = fixtures.save


class PreflightEvidenceTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ArtifactAuditTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.directory = fixture.root / 'work/session-train'
        self.record = json.loads((self.directory / 'session.json').read_bytes())
        self.capsule = json.loads((fixture.root / 'private/cases/session-train.json').read_bytes())
        self.record['skill'] = install_skill(self.directory / f'computers/{fixture.employee}/hermes', SEED_SKILL)
        native = self.record['result']['native']
        skill_file = self.directory / f'computers/{fixture.employee}/hermes/skills/work-process/SKILL.md'
        native['messages'][1]['content'] = json.dumps({'success': True, 'name': 'work-process', 'content': skill_file.read_text()})
        native['messages'] += [
            {'role': 'assistant', 'tool_calls': [{'id': 'commit', 'function': {'name': 'enterprise_action',
                'arguments': '{"operation":"work.commit","arguments":{}}'}}]},
            {'role': 'tool', 'tool_call_id': 'commit', 'content': json.dumps({
                'artifact_sha256': self.record['committed_artifact_sha256'], 'observation': {}})},
            {'role': 'assistant', 'tool_calls': [{'id': 'readback', 'function': {'name': 'read_file',
                'arguments': '{"path":"/workspace/deliverables/capability.json"}'}}]},
            {'role': 'tool', 'tool_call_id': 'readback', 'content': json.dumps({'content': json.dumps(self.record['artifact'])})},
            {'role': 'assistant', 'content': 'Offline fabricated post-tool response.'}]
        self.record['tool_calls'] = 3
        response = json.loads(native['messages'][3]['content'])
        self.record['result']['workplace_rpc'] = [{'action': {'tool': 'work.commit', 'args': {}}, 'response': response}]
        self.record['last_submitted_artifact_sha256'] = self.record['committed_artifact_sha256']
        self.record['hermes_transport'] = native['evaluation_transport'] = contract('streaming')
        native['evaluation_budget']['operations'][0]['request_stream'] = True
        self.slot = {'mode': 'streaming', 'employee': fixture.employee, 'task_id': self.record['task_id']}
        self.manifest = {'initial_skill_sha256': sha(SEED_SKILL.encode()), 'transports': {'streaming': contract('streaming')},
                         'source_sha256': source_hashes()}
        self.flush()

    def flush(self):
        save(self.directory / 'session.json', self.record)

    def inspect(self):
        # Four fabricated physical receipts represent the four assistant turns.
        meter = self.record['result']['native']['evaluation_budget']
        if meter['physical_model_calls'] == 1:
            meter['operations'] = [{**deepcopy(meter['operations'][0]), 'dispatch': i} for i in (1, 2, 3, 4)]
            meter.update(physical_model_calls=4, input_tokens=12, output_tokens=8,
                         total_tokens=20, reported_tokens=20, charged_tokens=20)
            self.record['usage'].update(api_calls=4, prompt_tokens=12, completion_tokens=8, total_tokens=20, charged_tokens=20)
        self.flush()
        return native_session(self.record, self.directory, self.capsule, self.slot, self.manifest)

    def test_accounting_is_independent_of_behavior_and_cleanup(self):
        self.record['success'] = False
        result = physical_usage(self.record)
        self.assertEqual(result['api_calls'], 1)
        self.assertEqual(result['total_tokens'], 5)
        self.assertTrue(result['complete'])

    def test_unknown_receipt_keeps_known_prefix_and_reservation(self):
        meter = self.record['result']['native']['evaluation_budget']
        row = deepcopy(meter['operations'][0])
        row.update(dispatch=2, accounting='reservation', charged_tokens=100,
                   reserved_tokens=100, input_tokens=None, output_tokens=None, total_tokens=None)
        meter['operations'].append(row)
        meter.update(physical_model_calls=2, charged_tokens=105, accounting_complete=False)
        self.record['usage'].update(api_calls=2, charged_tokens=105, total_tokens=None, complete=False)
        result = physical_usage(self.record)
        self.assertIsNone(result['total_tokens'])
        self.assertEqual(result['reported_tokens'], 5)
        self.assertEqual(result['charged_tokens'], 105)
        self.assertEqual(result['unknown_operations'], 1)

    def test_physical_overrun_retains_actual_usage_and_flags_it(self):
        row = self.record['result']['native']['evaluation_budget']['operations'][0]
        row['reserved_tokens'] = 4
        result = physical_usage(self.record)
        self.assertEqual(result['total_tokens'], 5)
        self.assertIn('provider_budget_overrun', result['violations'])

    def test_malformed_counter_is_not_accounted_as_known(self):
        self.record['usage']['api_calls'] = True
        with self.assertRaisesRegex(ValueError, 'session_usage_equation'):
            physical_usage(self.record)

    def test_substantive_commit_and_native_tool_sequence(self):
        result = self.inspect()
        self.assertTrue(result['transport_roundtrip_capable'])
        self.assertTrue(result['semantic_success'])
        self.assertTrue(result['business_committed'])

    def test_local_cap_summary_is_not_followup_inference(self):
        self.record['result']['native']['evaluation_budget']['disabled_auxiliary_calls'] = ['iteration_summary']
        result = self.inspect()
        self.assertFalse(result['transport_roundtrip_capable'])
        self.assertFalse(result['synthetic_summary_excluded'])

    def test_rejected_submission_can_demonstrate_transport_roundtrip(self):
        artifact = deepcopy(self.record['artifact']); artifact['content'] = '{}'
        raw = json.dumps(artifact).encode(); submitted = sha(raw)
        (self.directory / 'filesystem_objects' / submitted).write_bytes(raw)
        grade = grade_case(self.capsule['case'], artifact)
        self.assertFalse(grade['success'])
        self.record.update(success=False, semantic_score=grade['score'], checks=grade['checks'], feedback=grade['feedback'],
                           artifact=None, committed_artifact_sha256=None, last_submitted_artifact_sha256=submitted)
        result = self.record['result']['workplace_rpc'][0]['response']
        result['artifact_sha256'] = submitted
        self.record['result']['native']['messages'][3]['content'] = json.dumps(result)
        self.record['result']['native']['messages'][5]['content'] = json.dumps({'content': json.dumps(artifact)})
        observed = self.inspect()
        self.assertTrue(observed['transport_roundtrip_capable'])
        self.assertFalse(observed['semantic_success'])
        self.assertFalse(observed['business_committed'])

    def test_missing_or_unmatched_post_tool_response_cannot_pass(self):
        messages = self.record['result']['native']['messages']
        messages.pop()
        self.assertFalse(self.inspect()['transport_roundtrip_capable'])
        messages.append({'role': 'assistant', 'content': 'Offline fixture.'})
        messages[-2]['tool_call_id'] = 'wrong-call'
        self.assertFalse(self.inspect()['transport_roundtrip_capable'])

    def test_readback_preserves_json_scalar_types(self):
        artifact = deepcopy(self.record['artifact'])
        message = self.record['result']['native']['messages'][5]
        message['content'] = json.dumps({'content': json.dumps(artifact, sort_keys=True, indent=3)})
        self.assertTrue(self.inspect()['post_submission_native_file_readback'])
        artifact['redact'] = int(artifact['redact'])
        message['content'] = json.dumps({'content': json.dumps(artifact)})
        result = self.inspect()
        self.assertFalse(result['post_submission_native_file_readback'])
        self.assertFalse(result['transport_roundtrip_capable'])

    def test_submitted_object_tamper_is_regraded(self):
        path = self.directory / 'filesystem_objects' / self.record['last_submitted_artifact_sha256']
        path.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'committed_artifact_hash_or_content'):
            self.inspect()

    def test_mode_mismatch_or_fake_tool_count_fails(self):
        self.record['tool_calls'] += 1
        with self.assertRaisesRegex(ValueError, 'native_tool_count'):
            self.inspect()
        self.record['tool_calls'] -= 1
        self.record['result']['native']['evaluation_budget']['operations'][0]['request_stream'] = False
        with self.assertRaisesRegex(ValueError, 'hermes_transport_physical_mode_mismatch'):
            self.inspect()

    def cleanup_fixture(self):
        trial = self.directory.parent / 'cleanup-only-fixture'
        native = trial / 'native/computers' / self.slot['employee']
        alias = Path('/tmp') / ('lifespan-bwrap-fixture-' + self.directory.parents[1].name)
        socket = alias / 'control/command.sock'
        processes = [{'pid': 13000+i, 'ppid': 12999+i, 'pgid': 13000, 'sid': 13000,
                      'start_ticks': 100+i, 'uid': 1000, 'boot_id': 'offline-fixture-boot', 'state': 'S'} for i in range(3)]
        save(trial / 'worker-identity.json', processes[0])
        instance = {'kind': 'ready', 'employee': self.slot['employee'], 'backend': 'bubblewrap',
            'evaluation_transport': contract(self.slot['mode']), 'pid': 13001, 'sandbox_pid': 13002,
            'computer_id': 'lifespan-' + sha(str(native / 'hermes').encode())[:16],
            'probe': json.dumps({'exit_code': 0, 'output': '/workspace\n'+self.slot['employee']}),
            'tool_names': ['skill_view', 'enterprise_action', 'terminal'], 'rpc_socket': str(socket)}
        save(native / 'instance.json', instance)
        cleanup = {'schema_version': 1, 'limit_seconds': 30, 'elapsed_seconds': .1, 'status': 'confirmed',
            'owned_processes': processes, 'root_identity': processes[0],
            'observations_after': [{'identity': p, 'state': 'absent', 'observed_current': None} for p in processes],
            'forced': False, 'signals': [], 'socket_and_alias_absent': True, 'underlying_control_socket_absent': True,
            'instance': {'instance_path': str(native / 'instance.json'),
                'instance_sha256': sha((native / 'instance.json').read_bytes()),
                'worker_pid': 13001, 'sandbox_pid': 13002, 'worker_identity': processes[1], 'sandbox_identity': processes[2],
                'rpc_socket': str(socket), 'alias': str(alias), 'control_target': str(native / 'control'),
                'owned_alias_observed': True}}
        return trial, cleanup

    def test_complete_cleanup_identity_proof(self):
        trial, cleanup = self.cleanup_fixture()
        self.assertTrue(cleanup_check(trial, self.slot, cleanup))

    def test_detached_native_process_or_missing_observation_fails(self):
        trial, cleanup = self.cleanup_fixture()
        cleanup['observations_after'][-1]['state'] = 'same_alive'
        with self.assertRaisesRegex(ValueError, 'owned_process_not_confirmed_gone'):
            cleanup_check(trial, self.slot, cleanup)
        cleanup['observations_after'].pop()
        with self.assertRaisesRegex(ValueError, 'cleanup_observation_inventory'):
            cleanup_check(trial, self.slot, cleanup)

    def test_unrelated_process_cannot_be_claimed_or_signaled(self):
        trial, cleanup = self.cleanup_fixture()
        cleanup['owned_processes'][-1]['ppid'] = 1
        with self.assertRaisesRegex(ValueError, 'unbound_process_ancestry'):
            cleanup_check(trial, self.slot, cleanup)
        trial, cleanup = self.cleanup_fixture()
        cleanup['forced'] = True
        cleanup['signals'] = [{'pid': 99999, 'start_ticks': 500, 'signal': 'KILL'}]
        with self.assertRaisesRegex(ValueError, 'unowned_cleanup_signal'):
            cleanup_check(trial, self.slot, cleanup)

    def test_cleanup_cap_and_instance_byte_tamper_fail(self):
        trial, cleanup = self.cleanup_fixture()
        cleanup['elapsed_seconds'] = 30.01
        with self.assertRaisesRegex(ValueError, 'cleanup_deadline'):
            cleanup_check(trial, self.slot, cleanup)
        cleanup['elapsed_seconds'] = .1
        Path(cleanup['instance']['instance_path']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'native_instance_hash'):
            cleanup_check(trial, self.slot, cleanup)

    def test_removing_alias_does_not_prove_underlying_socket_removed(self):
        trial, cleanup = self.cleanup_fixture()
        control = Path(cleanup['instance']['control_target']); control.mkdir()
        (control / 'command.sock').symlink_to(control / 'absent-target')
        with self.assertRaisesRegex(ValueError, 'underlying_control_socket_not_removed'):
            cleanup_check(trial, self.slot, cleanup)


class PreflightCampaignTests(unittest.TestCase):
    """Mock component checks only to isolate outer inventory/report invariants."""
    def setUp(self):
        from scripts import hermes_transport_preflight as launcher
        self.launcher = launcher
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'run'
        for target, kwargs in [
            ('scripts.hermes_transport_preflight.dependencies', {'return_value': {'offline_fixture': True}}),
            ('scripts.hermes_transport_preflight.committed_sources', {'return_value': True}),
            ('scripts.audit_hermes_preflight.committed_sources', {'return_value': None})]:
            scope = patch(target, **kwargs); scope.start(); self.addCleanup(scope.stop)
        self.manifest = launcher.prepare(self.root, target_model='offline-fixture', model_base_url='https://example.invalid')
        self.evidence = {'transport_roundtrip_capable': True, 'semantic_success': False,
                         'semantic_score': .2, 'business_committed': False}
        self.native = patch('scripts.audit_hermes_preflight.native_session', return_value=self.evidence).start()
        self.addCleanup(patch.stopall)
        patch('scripts.audit_hermes_preflight.cleanup_check', return_value=True).start()
        self.receipts = []

    def begin(self, fixture=False):
        h = sha((self.root / 'manifest.json').read_bytes())
        save(self.root / 'EXECUTION.json', {'schema_version': 1, 'manifest_sha256': h,
            'registered_manifest_sha256': h, 'config': self.manifest['config'], 'started_unix_seconds': 100.0,
            'execution_driver': self.manifest['execution_driver'], 'executor_identity': self.manifest['native_executor'],
            'fixture': fixture})

    def add_receipt(self):
        index = len(self.receipts); slot = self.manifest['slots'][index]
        trial = self.root / 'private/trials' / slot['slot_id']
        row = {'dispatch': 1, 'reserved_tokens': 100, 'charged_tokens': 5, 'output_cap': 32,
               'accounting': 'reported', 'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5, 'status': 'completed'}
        record = {'result': {'native': {'evaluation_budget': {'physical_model_calls': 1,
            'operations': [row], 'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5,
            'reported_tokens': 5, 'charged_tokens': 5, 'accounting_complete': True}}},
            'usage': {'api_calls': 1, 'charged_tokens': 5, 'total_tokens': 5,
                      'prompt_tokens': 3, 'completion_tokens': 2, 'complete': True}}
        save(trial / 'native/session.json', record); h = sha((trial / 'native/session.json').read_bytes())
        outcome = {'status': 'returned', 'session_sha256': h}
        cleanup = {'status': 'confirmed', 'elapsed_seconds': .1}
        supervision = {'status': 'returned', 'root_exitcode': 0, 'outcome': outcome, 'cleanup': cleanup,
            'timeout_seconds': 420, 'cleanup_seconds': 30, 'elapsed_seconds': 1.2, 'execution_elapsed_seconds': 1.0}
        save(trial / 'worker-outcome.json', outcome); save(trial / 'cleanup.json', cleanup)
        save(trial / 'supervision.json', supervision)
        receipt = {'schema_version': 1, 'slot_id': slot['slot_id'], 'index': index,
            'capsule_sha256': slot['capsule_sha256'], 'fixture': False,
            'executor_identity': self.manifest['native_executor'], 'trial_path': str(trial.relative_to(self.root)),
            'session_sha256': h, 'supervision_sha256': sha((trial / 'supervision.json').read_bytes()),
            'cleanup_sha256': sha((trial / 'cleanup.json').read_bytes()), 'costs': costs_check(record),
            'native_evidence': self.evidence, 'evidence_error_type': None, 'cleanup_error_type': None,
            'cleanup_confirmed': True, 'status': 'completed', 'capability_pass': True, 'elapsed_seconds': 2.0*(index+1)}
        self.receipts.append(receipt)

    def flush(self, status='completed', report=True):
        pointers = []
        for row in self.receipts:
            path = 'private/receipts/' + row['slot_id'] + '.json'; save(self.root / path, row)
            pointers.append({'path': path, 'sha256': sha((self.root / path).read_bytes())})
        elapsed = 2.0 * len(self.receipts) + .5
        usage = aggregate_costs(self.receipts)
        save(self.root / 'state.json', {'schema_version': 1, 'status': status, 'receipts': pointers,
             'usage': usage, 'elapsed_seconds': elapsed})
        if report:
            save(self.root / 'REPORT.json', {'schema_version': 1, 'kind': self.manifest['kind'],
                'status': status, 'fixture': False, 'manifest_sha256': sha((self.root / 'manifest.json').read_bytes()),
                'execution_sha256': sha((self.root / 'EXECUTION.json').read_bytes()), 'fixed_slots': 6,
                'attempted_slots': len(self.receipts), 'usage': usage, 'elapsed_seconds': elapsed,
                'capability_pass': status == 'completed' and all(r['capability_pass'] for r in self.receipts),
                'slots': [{'slot_id': s['slot_id'], 'mode': s['mode'], 'workflow': s['workflow'],
                    'status': self.receipts[i]['status'] if i < len(self.receipts) else 'not_attempted',
                    'capability_pass': self.receipts[i]['capability_pass'] if i < len(self.receipts) else None,
                    'native_evidence': self.receipts[i]['native_evidence'] if i < len(self.receipts) else None}
                    for i, s in enumerate(self.manifest['slots'])]})

    def test_prepared_is_not_completed_native_evidence(self):
        self.assertEqual(audit_preflight(self.root)['status'], 'valid_prepared')
        result = audit_preflight(self.root, strict=True)
        self.assertFalse(result['ok']); self.assertFalse(result['capability_pass'])

    def test_all_six_slots_and_semantic_failures_remain_visible(self):
        self.begin()
        for _ in range(6): self.add_receipt()
        self.flush(); result = audit_preflight(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['slots']), 6)
        self.assertTrue(result['capability_pass'])
        self.assertTrue(all(not row['native_evidence']['semantic_success'] for row in result['slots']))
        self.assertEqual(result['usage']['total_tokens'], 30)
        self.assertIsNone(result['model_quality_score'])

    def test_report_tamper_retains_independently_known_costs(self):
        self.begin()
        for _ in range(6): self.add_receipt()
        self.flush()
        path = self.root / 'REPORT.json'; report = json.loads(path.read_bytes()); report['usage']['total_tokens'] = 1; save(path, report)
        result = audit_preflight(self.root, strict=True)
        self.assertFalse(result['ok']); self.assertEqual(result['usage']['total_tokens'], 30)
        self.assertIn({'code': 'persisted_report_mismatch'}, result['errors'])

    def test_fixture_driver_and_registered_hash_downgrade_rejected(self):
        self.begin(fixture=True)
        self.assertIn({'code': 'fixture_is_not_native_evidence'}, audit_preflight(self.root)['errors'])
        self.begin(); path = self.root / 'EXECUTION.json'; value = json.loads(path.read_bytes())
        value['registered_manifest_sha256'] = '0' * 64; save(path, value)
        self.assertIn({'code': 'execution_manifest_binding'}, audit_preflight(self.root)['errors'])

    def test_inflight_reservation_and_missing_slots_are_not_zero_outcomes(self):
        self.begin(); self.add_receipt(); self.flush(status='running', report=False)
        slot = self.manifest['slots'][1]
        save(self.root / 'INFLIGHT.json', {'slot_id': slot['slot_id'], 'index': 1, 'reserved_model_calls': 16, 'reserved_tokens': 250000})
        result = audit_preflight(self.root)
        self.assertTrue(result['ok'], result); self.assertFalse(result['accounting_verified'])
        self.assertEqual(result['inflight_reserved_tokens'], 250000)
        self.assertEqual([r['status'] for r in result['slots']], ['completed', 'inflight_usage_unknown'] + ['not_attempted']*4)
        self.assertFalse(audit_preflight(self.root, strict=True)['ok'])

    def test_paired_case_and_receipt_order_tamper_rejected(self):
        self.begin(); self.add_receipt(); self.flush(status='running', report=False)
        path = self.root / 'state.json'; state = json.loads(path.read_bytes())
        state['receipts'][0]['path'] = 'private/receipts/wrong.json'; save(path, state)
        self.assertIn({'code': 'receipt_slot_order'}, audit_preflight(self.root)['errors'])
        capsule = self.root / self.manifest['slots'][0]['capsule_path']
        value = json.loads(capsule.read_bytes()); value['request'] += ' altered'; save(capsule, value)
        self.assertIn({'code': 'fixed_synthetic_capsule'}, audit_preflight(self.root)['errors'])

    def test_known_costs_survive_infrastructure_halt(self):
        self.begin(); self.add_receipt(); receipt = self.receipts[0]
        receipt.update(status='halted_infrastructure', native_evidence=None, evidence_error_type='ValueError', capability_pass=False)
        self.native.side_effect = ValueError('fixture failure')
        self.flush(status='halted_infrastructure')
        result = audit_preflight(self.root)
        self.assertTrue(result['ok'], result); self.assertFalse(result['capability_pass'])
        self.assertEqual(result['usage']['total_tokens'], 5)
        self.assertTrue(result['accounting_verified'])

    def test_predispatch_interruption_keeps_all_slots_missing(self):
        self.begin(); self.flush(status='interrupted')
        result = audit_preflight(self.root)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['usage']['charged_or_reserved_model_calls'], 0)
        self.assertTrue(all(row['status'] == 'not_attempted' for row in result['slots']))
        self.assertFalse(audit_preflight(self.root, strict=True)['ok'])

    def test_interrupted_slot_preserves_returned_usage_but_never_passes(self):
        self.begin(); self.add_receipt(); receipt = self.receipts[0]
        path = self.root / receipt['trial_path'] / 'supervision.json'
        supervision = json.loads(path.read_bytes()); supervision['status'] = 'interrupted'; save(path, supervision)
        receipt.update(status='interrupted', capability_pass=False, supervision_sha256=sha(path.read_bytes()))
        self.flush(status='interrupted')
        result = audit_preflight(self.root)
        self.assertTrue(result['ok'], result); self.assertFalse(result['capability_pass'])
        self.assertEqual(result['usage']['total_tokens'], 5)
        self.assertFalse(audit_preflight(self.root, strict=True)['ok'])
        self.add_receipt(); self.flush(status='interrupted')
        result = audit_preflight(self.root)
        self.assertIn({'code': 'execution_continued_after_invalid_slot'}, result['errors'])


if __name__ == '__main__':
    unittest.main()
