"""Offline artifact tamper fixtures, never native model-quality evidence.

Native session regrading is tested independently in test_evaluation_audit. Here
those boundaries are mocked explicitly; real files and upstream consolidation
exercise the additional epoch/transfer provenance and report reconciliation.
"""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lifespan.mirofish import save
from scripts import audit_transfer as audit
from lifespan.evaluation.hermes_transport import manifest_fields

TRANSPORT_SOURCES = {'lifespan/evaluation/hermes_transport.py', 'lifespan/hermes_worker.py',
                     'lifespan/evaluation/runtime.py', 'lifespan/evaluation/runner.py'}


def fixture_class(filename, name):
    spec = importlib.util.spec_from_file_location('_audit_' + name, audit.ROOT / 'tests' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return getattr(module, name)


class LearningAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_class('test_transfer_learning.py', 'TransferLearningTests')()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        source_manifest = json.loads((self.fixture.source / 'manifest.json').read_bytes())
        source_manifest['config'].update(algorithm='no_learning', state_mode='skill_transfer')
        save(self.fixture.source / 'manifest.json', source_manifest)
        self.fixture.run_fixture()
        self.out = self.fixture.out
        self.manifest, self.state, self.evidence, self.report = [self.load(name) for name in
                    ('manifest.json', 'state.json', 'evidence.json', 'REPORT.json')]
        self.manifest['execution_mode'] = self.report['execution_mode'] = 'native'
        # Deliberately fabricated local driver evidence for audit control flow.
        self.manifest['source_sha256'] = {name: audit.sha(audit.ROOT / name)
                                         for name in audit.CORE | TRANSPORT_SOURCES | {'scripts/transfer_learning.py'}}
        for row in self.evidence['target_sessions']:
            path = self.out / row['session_path']; record = self.load(row['session_path'])
            record['result']['native']['evaluation_budget'] = {'physical_model_calls': 3,
                'charged_tokens': 100, 'operations': [{'output_cap': 4096}] * 3}
            record['last_submitted_artifact_sha256'] = None
            save(path, record); row['session_sha256'] = audit.sha(path)
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(audit, 'audit_run', return_value={'ok': True}))
        self.manifest['dependencies'] = {name: {'revision': 'fabricated-fixture'} for name in ('hermes', 'mirofish', 'skillopt')}
        self.stack.enter_context(patch.object(audit, 'dependency_provenance', return_value=self.manifest['dependencies']))
        self.raw_audit = self.stack.enter_context(patch.object(audit, 'session_check'))
        self.update_audit = self.stack.enter_context(patch.object(audit, 'update_check'))
        self.flush()

    def load(self, name):
        return json.loads((self.out / name).read_bytes())

    def flush(self):
        save(self.out / 'manifest.json', self.manifest)
        save(self.out / 'evidence.json', self.evidence)
        save(self.out / 'state.json', self.state)
        cp = self.load('checkpoint.json'); cp['runner'] = deepcopy(self.state); save(self.out / 'checkpoint.json', cp)
        self.report['manifest_sha256'] = audit.sha(self.out / 'manifest.json')
        self.report['evidence_sha256'] = audit.sha(self.out / 'evidence.json')
        save(self.out / 'REPORT.json', self.report)

    def invalid(self, code):
        result = audit.audit_learning_epoch(self.out)
        self.assertFalse(result['ok'], result)
        self.assertIn(code, result['errors'], result)

    def test_complete_no_adoption_reconciles_all_attempts(self):
        result = audit.audit_learning_epoch(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['target_sessions_checked'], 10)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['model_calls'], 30)
        self.assertIsNone(result['model_quality_score'])
        self.assertEqual(self.raw_audit.call_count, 4)
        self.update_audit.assert_called_once()

    def test_future_source_cannot_select_v1_by_removing_both_version_markers(self):
        self.manifest.pop('learning_evidence_version')
        self.state['updates'][0].pop('learning_evidence_version')
        self.flush()
        self.invalid('learning_evidence_source_version')

    def test_raw_session_byte_tampering(self):
        with (self.out / self.evidence['target_sessions'][0]['session_path']).open('a') as stream:
            stream.write('\n')
        self.invalid('learning_native_session_hash')

    def test_attempt_and_phase_tampering(self):
        self.evidence['target_sessions'][1]['attempt_index'] = 0
        self.flush(); self.invalid('learning_attempt_binding')
        self.evidence['target_sessions'][1]['attempt_index'] = 1
        self.evidence['target_sessions'][1]['phase'] = 'train'
        self.flush(); self.invalid('learning_attempt_binding')

    def test_source_feedback_and_future_probe_tampering(self):
        self.state['experiences'][0]['feedback_available_day'] = 10
        self.flush(); self.invalid('altered_historical_experience')

    def test_deployed_skill_and_report_usage_tampering(self):
        self.report['usage']['tokens'] += 1
        self.flush(); self.invalid('learning_report_usage_mismatch')
        self.report['usage']['tokens'] -= 1
        self.state['skills'][self.fixture.employee] += '\nUnsupported change.'
        self.flush(); self.invalid('learning_deployed_skill_chain')

    def test_source_hash_and_extra_capsule_rejected(self):
        self.manifest['source_sha256']['lifespan/evaluation/tasks.py'] = '0' * 64
        self.flush(); self.invalid('execution_source_revision_mismatch')
        self.manifest['source_sha256']['lifespan/evaluation/tasks.py'] = audit.sha(audit.ROOT / 'lifespan/evaluation/tasks.py')
        save(self.out / 'private/cases/future-probe.json', {'probe': {'day': 10}})
        self.flush(); self.invalid('unexpected_learning_capsules')

    def test_inflight_and_injected_evidence_cannot_pass_strict(self):
        save(self.out / 'INFLIGHT.json', {'phase': 'learning'})
        self.invalid('completed_learning_has_pending_artifacts')
        (self.out / 'INFLIGHT.json').unlink()
        self.manifest['execution_mode'] = 'injected_executor_fixture'
        self.flush(); self.invalid('completed_learning_requires_native_update')

    def test_physical_budget_cannot_be_hidden_by_aggregate(self):
        row = self.evidence['target_sessions'][0]
        path = self.out / row['session_path']; record = self.load(row['session_path'])
        record['result']['native']['evaluation_budget']['operations'][0]['output_cap'] = 4097
        save(path, record); row['session_sha256'] = audit.sha(path)
        self.flush(); self.invalid('target_physical_budget_exceeded')

    def test_incomplete_learning_does_not_certify_low_cost_claims(self):
        self.state['status'] = self.report['status'] = 'failed'
        self.report['usage']['model_calls'] = 0
        self.report['usage']['charged_or_reserved_model_calls'] = 0
        save(self.out / 'INFLIGHT.json', {'phase': 'learning'})
        self.flush()
        result = audit.audit_learning_epoch(self.out, strict=False)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(result['accounting_verified'])
        self.assertFalse(audit.audit_learning_epoch(self.out, strict=True)['ok'])

    def test_dependency_revision_tamper_rejected(self):
        self.manifest['dependencies'] = deepcopy(self.manifest['dependencies'])
        self.manifest['dependencies']['hermes']['revision'] = 'altered'
        self.flush(); self.invalid('native_dependency_revision_mismatch')


class TransferAuditTests(unittest.TestCase):
    def setUp(self):
        from scripts import run_transfer_experiment as runner
        self.runner = runner
        self.fixture = fixture_class('test_transfer_runner.py', 'TransferRunnerTests')()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_fixture()
        self.out, self.source = self.fixture.out, self.fixture.source
        self.calibration = self.fixture.root / 'calibration'
        for name in ('bank.json', 'state.json', 'REPORT.json'):
            save(self.calibration / name, {'fixture': 'not-native-evidence'})
        save(self.calibration / 'manifest.json', {'source_directory': str(self.source)})
        save(self.source / 'manifest.json', {'target_model': 'offline', 'model_base_url': 'https://fixture.example.invalid', 'config': {}})
        self.manifest = deepcopy(self.fixture.manifest)
        deps = {name: {'revision': 'fabricated-fixture'} for name in ('hermes', 'mirofish', 'skillopt')}
        save(self.out / 'private/experiences.json', [])
        self.manifest.update(kind='native_employee_learning_transfer_diagnostic',
            **manifest_fields({'hermes_transport': 'streaming'}),
            config=deepcopy(runner.CONFIG), calibration_directory=str(self.calibration),
            source_manifest_sha256=audit.sha(self.source / 'manifest.json'),
            calibration_sha256={name: audit.sha(self.calibration / name) for name in ('manifest.json', 'bank.json', 'state.json', 'REPORT.json')},
            source_sha256={name: audit.sha(audit.ROOT / name) for name in audit.CORE | TRANSPORT_SOURCES | set(runner.CODE_FILES)},
            dependencies=deps, ranking=[], experience_ids=[], source_case_sha256={},
            experiences_sha256=audit.sha(self.out / 'private/experiences.json'), seed_skill_sha256=audit.skill_hash(audit.SEED_SKILL),
            learning_contract={'epochs': 1, 'rollouts_k': 2, 'train_cases': 2, 'val_cases': 2,
                               'max_model_calls': 200, 'max_charged_tokens': 4000000, 'max_seconds': 1800})
        self.state = self.fixture.state()
        save(self.out / 'learning_epoch/manifest.json', {'source_directory': str(self.source), 'employee': self.fixture.employee})
        save(self.out / 'learning_epoch/state.json', {'skills': {self.fixture.employee: audit.SEED_SKILL}, 'experiences': []})
        for row in self.state['results']:
            path = self.out / row['session_path']; record = json.loads(path.read_bytes())
            record['last_submitted_artifact_sha256'] = None
            record['result'] = {'native': {'evaluation_budget': {'physical_model_calls': 3, 'charged_tokens': 100,
                                                              'operations': [{'output_cap': 4096}] * 3}}}
            save(path, record); row['session_sha256'] = audit.sha(path)
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(audit, 'audit_run', return_value={'ok': True}))
        stack.enter_context(patch('scripts.audit_calibration.audit_calibration', return_value={'ok': True}))
        stack.enter_context(patch.object(audit, 'dependency_provenance', return_value=deps))
        self.learning_audit = stack.enter_context(patch.object(audit, 'audit_learning_epoch', return_value={
            'ok': True, 'status': 'valid_completed', 'accounting_verified': True}))
        stack.enter_context(patch('scripts.transfer_analysis.select_employee', return_value={
            'employee': self.fixture.employee, 'ranking': [], 'experiences': []}))
        self.raw_audit = stack.enter_context(patch.object(audit, 'session_check'))
        self.flush()

    def flush(self):
        from scripts.transfer_analysis import aggregate_probes
        save(self.out / 'manifest.json', self.manifest); save(self.out / 'state.json', self.state)
        learning = json.loads((self.out / 'learning_epoch/REPORT.json').read_bytes())
        report = aggregate_probes(self.manifest['probe_manifest'], self.manifest['slots'], self.state['results'], same_skill=self.state['same_skill'])
        report.update(status=self.state['status'], manifest_sha256=audit.sha(self.out / 'manifest.json'),
            learning_report_sha256=self.state['learning_report_sha256'], deployed_skill_sha256=self.state['deployed_skill_sha256'],
            actual_probe_elapsed_seconds=self.state['elapsed_seconds'], **self.runner.campaign_usage(learning['usage'], self.state))
        save(self.out / 'REPORT.json', report)

    def invalid(self, code):
        result = audit.audit_transfer(self.out, strict=True)
        self.assertFalse(result['ok'], result); self.assertIn(code, result['errors'], result)

    def test_complete_all_attempts_and_combined_cost(self):
        result = audit.audit_transfer(self.out, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['accounting_verified'])
        self.assertEqual(result['checked_slots'], 16)
        self.assertEqual(result['probe_model_calls'], 48)
        self.assertEqual(self.raw_audit.call_count, 16)
        self.assertIsNone(result['model_quality_score'])

    def test_probe_byte_and_schedule_tampering(self):
        path = self.out / 'private/probes/probe-0.json'
        path.write_text(path.read_text() + '\n')
        self.invalid('transfer_frozen_probe_changed')
        self.manifest['probe_files_sha256']['private/probes/probe-0.json'] = audit.sha(path)
        self.manifest['slots'].reverse()
        save(self.out / 'manifest.json', self.manifest)
        self.invalid('transfer_slot_or_seed_contract')

    def test_wrong_arm_skill_and_raw_session_hash(self):
        row = self.state['results'][0]; path = self.out / row['session_path']; record = json.loads(path.read_bytes())
        record['skill']['content_sha256'] = '0' * 64
        save(path, record)
        self.invalid('transfer_native_session_hash')
        row['session_sha256'] = audit.sha(path); self.flush()
        self.invalid('transfer_wrong_arm_skill')

    def test_score_report_and_cost_tampering(self):
        path = self.out / 'REPORT.json'; report = json.loads(path.read_bytes())
        report['combined_charged_or_reserved_calls'] = 0
        save(path, report); self.invalid('transfer_report_mismatch')
        self.state['model_calls'] = 0; self.flush(); self.invalid('transfer_probe_cost_totals')

    def test_missing_attempt_is_explicit_not_model_failure(self):
        import shutil
        last = self.state['results'].pop()
        shutil.rmtree((self.out / last['session_path']).parent)
        self.state.update(status='exhausted_time_budget', next_slot=15, charged_tokens=1500, model_calls=45)
        self.flush()
        result = audit.audit_transfer(self.out)
        self.assertTrue(result['ok'], result); self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(result['accounting_verified'])
        self.assertFalse(audit.audit_transfer(self.out, strict=True)['ok'])

    def test_completed_cannot_claim_learning_phase(self):
        self.state['phase'] = 'learning'; self.flush()
        self.invalid('transfer_phase_status_mismatch')

    def test_untracked_probe_and_unverified_learning_rejected(self):
        (self.out / 'probes/extra-attempt').mkdir()
        self.invalid('unaccounted_transfer_directory')
        (self.out / 'probes/extra-attempt').rmdir()
        self.learning_audit.return_value = {'ok': False}
        self.invalid('transfer_learning_audit_failed')

    def test_failed_learning_requires_full_unverified_reservation(self):
        import shutil
        shutil.rmtree(self.out / 'probes')
        self.state.update(phase='learning', status='learning_failed', results=[], next_slot=0,
                          charged_tokens=0, model_calls=0, elapsed_seconds=0.0)
        self.learning_audit.return_value = {'ok': True, 'status': 'incomplete', 'accounting_verified': False}
        save(self.out / 'state.json', self.state)
        save(self.out / 'INFLIGHT.json', {'phase': 'learning', 'reserved_tokens': 4000000, 'reserved_calls': 200})
        save(self.out / 'FAILURE.json', {'phase': 'learning', 'error_type': 'FabricatedOfflineFailure'})
        usage = {'accounting_complete': False, 'model_calls': None, 'tokens': None,
                 'charged_or_reserved_model_calls': 200, 'charged_or_reserved_tokens': 4000000}
        report = {'status': 'learning_failed', 'complete': False, 'probes_attempted': 0,
                  'manifest_sha256': audit.sha(self.out / 'manifest.json'), **self.runner.campaign_usage(usage, self.state)}
        save(self.out / 'REPORT.json', report)
        result = audit.audit_transfer(self.out)
        self.assertTrue(result['ok'], result); self.assertEqual(result['status'], 'incomplete')
        report['combined_charged_or_reserved_calls'] = 0; save(self.out / 'REPORT.json', report)
        self.invalid('failed_learning_reservation_report_mismatch')


class GateReconstructionTests(unittest.TestCase):
    """Actual pinned upstream gates, deterministic offline scored callbacks."""
    def setUp(self):
        self.fixture = fixture_class('test_transfer_learning.py', 'TransferLearningTests')()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)

    def update(self, **options):
        report = self.fixture.run_fixture(**options)
        return self.fixture.load(report['update_path'])

    def test_accepted_candidate_passes_both_independent_gates(self):
        self.fixture.perfect = False
        update = self.update()
        self.assertTrue(update['accepted'])
        audit.gate_check(update)
        update['configuration']['gate_metric'] = 'soft'
        with self.assertRaisesRegex(ValueError, 'upstream_gate_metric_contract'):
            audit.gate_check(update)

    def test_final_fresh_regression_rolls_back_trial_acceptance(self):
        self.fixture.perfect = False; self.fixture.break_final = True
        update = self.update()
        self.assertTrue(update['gate_evidence']['gate_trials'][0]['accepted'])
        self.assertFalse(update['accepted'])
        audit.gate_check(update)
        update['accepted'] = update['gate_evidence']['accepted'] = True
        update['gate_evidence']['gate_action'] = 'accept_new_best'
        with self.assertRaisesRegex(ValueError, 'upstream_gate_decision_mismatch'):
            audit.gate_check(update)

    def test_no_edit_final_noise_improvement_cannot_be_adoption(self):
        def changing_scores(**kwargs):
            self.fixture.perfect = len(self.fixture.calls) >= 2
            self.fixture.adopt = False
            return self.fixture.execute(**kwargs)
        update = self.update(executor=changing_scores)
        self.assertFalse(update['accepted'])
        self.assertGreater(update['gate_evidence']['candidate_score'], update['gate_evidence']['baseline_score'])
        audit.gate_check(update)
        update['accepted'] = True
        with self.assertRaisesRegex(ValueError, 'upstream_gate_decision_mismatch'):
            audit.gate_check(update)

    def test_per_task_regression_blocks_mean_improvement(self):
        self.fixture.perfect = False
        def unequal_scores(**kwargs):
            record = self.fixture.execute(**kwargs)
            index = len(self.fixture.calls) - 1
            # Baseline: one partial success and one failure. Candidate improves
            # average but sacrifices the first case, so the strict gate rejects.
            if index in (0, 8):
                record['success'] = False
                record['semantic_score'] = .9 if index == 0 else .5
            save(kwargs['root'] / 'session.json', record)
            return record
        update = self.update(executor=unequal_scores)
        trial = update['gate_evidence']['gate_trials'][0]
        self.assertGreater(trial['candidate_score'], trial['baseline_score'])
        self.assertTrue(trial['blocked_by_regression'])
        self.assertFalse(update['accepted'])
        audit.gate_check(update)
        trial['blocked_by_regression'] = False
        with self.assertRaisesRegex(ValueError, 'upstream_gate_score_evidence_mismatch'):
            audit.gate_check(update)

    def test_v1_budget_exhausted_prefix_abstains_without_full_gate(self):
        update = self.update()
        update.pop('learning_evidence_version')  # Historical gate-only contract.
        update.update(status='budget_exhausted', replay_evidence=update['replay_evidence'][:3],
                      gate_evidence={'accepted': False, 'gate_action': 'reject_incomplete'})
        audit.gate_check(update)
        update['accepted'] = True
        with self.assertRaisesRegex(ValueError, 'budget_exhausted_gate_claim'):
            audit.gate_check(update)


if __name__ == '__main__':
    unittest.main()
