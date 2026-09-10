"""Offline orchestration fixtures, not model-quality or native execution evidence."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import SEED_SKILL
from lifespan.evaluation.tasks import make_case
from lifespan.mirofish import save
from scripts.calibration_bank import VERSION
from scripts import run_calibration as runner


class CalibrationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.out = self.root / 'source', self.root / 'out'
        self.config = json.loads((runner.ROOT / 'configs/calibration/replay_v1.json').read_bytes())
        eco = Ecosystem(12, 101); eco.advance()
        world = eco.worlds['firm-0']; task = next(iter(world.tasks.values()))
        self.employee = 'firm-0__' + task.owner
        case = make_case(task.workflow, 101, 0, task.id, 'base', 'online', exception_window=[4, 6])
        self.capsule = {'employee': self.employee, 'firm': 'firm-0', 'task_id': task.id,
                       'case': case, 'ecosystem': eco.checkpoint(), 'request': 'offline fixture',
                       'objectives': {}, 'business_files': {}}
        save(self.source / 'private/cases/first.json', self.capsule)
        save(self.source / 'manifest.json', {'target_model': 'offline-fixture', 'model_base_url': 'https://fixture.example.invalid', 'config': {}})
        save(self.source / 'checkpoint.json', {'runner': {'skills': {self.employee: SEED_SKILL}}})
        self.creds = {'model': 'offline-fixture', 'base_url': 'https://fixture.example.invalid', 'api_key': 'unused'}
        self.bank = {'bank_version': VERSION, 'repeats_per_selection': 2, 'expected_cell_count': 1,
                     'selected_cell_count': 1, 'expected_rollout_count': 2,
                     'missing_cells': [], 'dependence': {'underlying_obligation_count': 1, 'repeated_obligation_groups': []},
                     'selections': [{'selection_id': 'first', 'employee': self.employee, 'regime': 'base',
                         'source_task_id': task.id, 'source_case_path': 'private/cases/first.json',
                         'capsule_sha256': runner.file_hash(self.source / 'private/cases/first.json')}]}
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(runner, 'audit_run', return_value={'ok': True}))
        stack.enter_context(patch.object(runner, 'build_bank', side_effect=lambda *a, **k: deepcopy(self.bank)))
        stack.enter_context(patch.object(runner, 'source_hashes', return_value={'offline.py': 'fixture'}))
        stack.enter_context(patch.object(runner, 'dependency_provenance', return_value={'fixture': True}))
        stack.enter_context(patch.object(runner, 'credentials', side_effect=AssertionError('Fixture loaded real credentials')))
        self.auditor = stack.enter_context(patch.object(runner, 'session_check', side_effect=self.check_record))
        stack.enter_context(redirect_stdout(io.StringIO()))
        self.calls = []
        self.success = True
        self.valid = True

    def check_record(self, record, directory, capsule, *, transport_manifest=None):
        self.assertEqual(json.loads((directory / 'session.json').read_bytes()), record)
        self.assertEqual(record['task_id'], capsule['task_id'])

    def test_transport_is_inherited_by_every_calibration_replay(self):
        path = self.source/'manifest.json'
        manifest = json.loads(path.read_text()); manifest['config']['hermes_transport'] = 'nonstreaming'
        save(path, manifest)
        result = self.run_fixture()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(call['hermes_transport'] == 'nonstreaming' for call in self.calls))
        self.assertEqual(json.loads((self.out/'manifest.json').read_text())['hermes_transport'], 'nonstreaming')

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        self.assertEqual(kwargs['skill'], SEED_SKILL)
        self.assertEqual(kwargs['timeout_seconds'], self.config['max_rollout_seconds'])
        self.assertEqual(kwargs['max_total_tokens'], self.config['max_rollout_tokens'])
        task = kwargs['world'].tasks[kwargs['task_id']]
        self.assertEqual(task.status, 'pending')
        task.status = 'completed'  # A new fork must see pending again next time.
        record = {'fixture': 'not-native-model-evidence', 'task_id': kwargs['task_id'],
                  'success': self.success, 'semantic_score': float(self.success),
                  'infrastructure_valid': self.valid, 'budget_exhausted': not self.success,
                  'skill_loaded': True, 'skill': {'content_sha256': hashlib.sha256(SEED_SKILL.encode()).hexdigest()},
                  'usage': {'complete': True, 'api_calls': 3, 'total_tokens': 100, 'charged_tokens': 100},
                  'diagnostic': {'cost': .2}, 'elapsed_seconds': 0.0}
        save(kwargs['root'] / 'session.json', record)
        return record

    def run_fixture(self, **kwargs):
        return runner.run_calibration(self.source, self.out, self.config, executor=self.execute, creds=self.creds, **kwargs)

    def state(self):
        return json.loads((self.out / 'state.json').read_bytes())

    def test_resume_keeps_fresh_forks_and_counts_every_attempt(self):
        original = (self.source / 'private/cases/first.json').read_bytes()
        self.assertEqual(self.run_fixture(stop_after=1)['status'], 'paused_invocation_limit')
        self.success = False
        report = self.run_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(len(self.calls), 2)
        self.assertIsNot(self.calls[0]['world'], self.calls[1]['world'])
        self.assertEqual(report['counts']['strict_success'], 1)
        self.assertEqual(report['repeat_stability']['disagreeing_case_pairs'], 1)
        self.assertEqual((self.state()['charged_tokens'], self.state()['model_calls']), (200, 6))
        self.assertEqual((self.source / 'private/cases/first.json').read_bytes(), original)
        self.assertFalse((self.out / 'INFLIGHT.json').exists())
        with self.assertRaises(ValueError): self.run_fixture()

    def test_budget_stops_before_dispatch_and_keeps_missing_slot(self):
        self.config['max_model_calls'] = 16
        report = self.run_fixture()
        self.assertEqual(report['status'], 'exhausted_compute_budget')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report['counts']['missing'], 1)
        self.assertIsNone(report['costs']['tokens']['total'])

    def test_full_timeout_required_before_dispatch(self):
        self.config['max_run_seconds'] = self.config['max_rollout_seconds'] - 1
        report = self.run_fixture()
        self.assertEqual(report['status'], 'exhausted_time_budget')
        self.assertEqual(self.calls, [])
        self.assertEqual(report['counts']['missing'], 2)

    def test_unknown_failure_retains_reservation_and_inflight(self):
        with patch.object(self, 'execute', side_effect=TimeoutError('unknown native outcome')):
            report = self.run_fixture()
        self.assertEqual(report['status'], 'infrastructure_error')
        self.assertEqual(self.state()['charged_tokens'], self.config['max_rollout_tokens'])
        self.assertEqual(self.state()['model_calls'], self.config['max_iterations'])
        self.assertEqual(report['counts']['infrastructure_error'], 1)
        self.assertEqual(report['counts']['missing'], 1)
        self.assertTrue((self.out / 'INFLIGHT.json').exists())
        with self.assertRaises(RuntimeError): self.run_fixture()

    def test_post_execution_audit_failure_retains_measured_usage(self):
        self.auditor.side_effect = ValueError('invalid artifact evidence')
        report = self.run_fixture()
        self.assertEqual(report['status'], 'infrastructure_error')
        self.assertEqual((self.state()['charged_tokens'], self.state()['model_calls']), (100, 3))
        self.assertTrue(self.state()['results'][0]['usage']['complete'])

    def test_invalid_native_receipt_is_checkpointed_as_terminal(self):
        self.valid = False
        report = self.run_fixture()
        self.assertEqual(report['status'], 'infrastructure_invalid')
        self.assertEqual(self.state()['status'], 'infrastructure_invalid')
        self.assertFalse((self.out / 'INFLIGHT.json').exists())
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertEqual(len(self.calls), 1)

    def test_resume_rejects_budget_reset_and_altered_artifact(self):
        self.run_fixture(stop_after=1)
        state = self.state(); state['model_calls'] = 0; save(self.out / 'state.json', state)
        with self.assertRaises(ValueError): self.run_fixture()
        state['model_calls'] = 3; save(self.out / 'state.json', state)
        path = self.out / state['results'][0]['session_path']
        path.write_text('{}')
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertEqual(len(self.calls), 1)

    def test_resume_rejects_changed_provenance_and_capsule(self):
        self.run_fixture(stop_after=1)
        self.config['order_seed'] += 1
        with self.assertRaises(ValueError): self.run_fixture()
        self.config['order_seed'] -= 1
        (self.source / 'private/cases/first.json').write_text('{}')
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertEqual(len(self.calls), 1)

    def test_order_is_fixed_and_independent_of_attached_outcome(self):
        bank = deepcopy(self.bank)
        bank['selections'] = [dict(bank['selections'][0], selection_id='case-' + str(i)) for i in range(10)]
        before = runner.plan_slots(bank, self.config)
        for row in bank['selections']: row['original_outcome'] = {'success': False}
        self.assertEqual(before, runner.plan_slots(bank, self.config))
        self.assertEqual(len({row['rollout_id'] for row in before}), 20)


if __name__ == '__main__': unittest.main()
