"""Offline phase/orchestration checks; injected fixtures are not native evidence."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import SEED_SKILL
from lifespan.mirofish import save
from scripts import run_transfer_experiment as runner
from scripts.transfer_probes import build_transfer_probes, public_probe_manifest


class TransferRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp)
        self.source, self.out = self.root / 'source', self.root / 'out'
        eco = Ecosystem(12, 101)
        while eco.day < 9:
            eco.advance()
        self.employee = 'firm-0__onboarding-regulated'
        cp = {'ecosystem': eco.checkpoint(), 'runner': {}}
        save(self.source / 'checkpoint.json', cp)
        self.probes = build_transfer_probes(cp, self.employee)
        for index, capsule in enumerate(self.probes):
            save(self.out / 'private/probes' / f'probe-{index}.json', capsule)
        self.manifest = {'source_directory': str(self.source), 'employee': self.employee,
            'source_checkpoint_sha256': runner.sha(self.source / 'checkpoint.json'),
            'probe_files_sha256': {f'private/probes/probe-{i}.json': runner.sha(self.out / 'private/probes' / f'probe-{i}.json')
                                   for i in range(4)},
            'target_model': 'offline', 'model_base_url': 'https://fixture.example.invalid',
            'slots': runner.plan_slots(), 'probe_manifest': public_probe_manifest(self.probes)}
        save(self.out / 'manifest.json', self.manifest)
        save(self.out / 'state.json', {'status': 'prepared', 'phase': 'prepared', 'next_slot': 0,
             'results': [], 'charged_tokens': 0, 'model_calls': 0, 'elapsed_seconds': 0.0})
        self.creds = {'model': 'offline', 'base_url': 'https://fixture.example.invalid', 'api_key': 'unused'}
        self.original_validate = runner.validate_prepared
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(runner, 'validate_prepared', return_value=(self.manifest, self.probes, [])))
        self.auditor = stack.enter_context(patch.object(runner, 'session_check', side_effect=self.check_record))
        stack.enter_context(patch.object(runner, 'credentials', side_effect=AssertionError('Real credentials used by fixture')))
        stack.enter_context(redirect_stdout(io.StringIO()))
        self.calls, self.learning_calls = [], []
        self.deployed = SEED_SKILL
        self.learning_status = 'completed'
        self.valid = True

    def check_record(self, record, directory, capsule, *, transport_manifest=None):
        self.assertEqual(json.loads((directory / 'session.json').read_bytes()), record)
        self.assertEqual(record['task_id'], capsule['task_id'])

    def learn(self, source, out, employee, experiences, **kwargs):
        self.learning_calls.append(kwargs)
        # All four future tasks already exist, before learning is called.
        self.assertEqual(len(list(self.out.glob('private/probes/*.json'))), 4)
        save(out / 'checkpoint.json', {'runner': {'skills': {employee: self.deployed}}})
        report = {'status': self.learning_status, 'fixture': 'not-native-evidence',
                  'usage': {'accounting_complete': True, 'model_calls': 30, 'tokens': 1000,
                            'charged_or_reserved_model_calls': 30, 'charged_or_reserved_tokens': 1000}}
        save(out / 'REPORT.json', report)
        return report

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        task = kwargs['world'].tasks[kwargs['task_id']]
        self.assertEqual(task.status, 'pending')
        task.status = 'completed'
        self.assertEqual(kwargs['timeout_seconds'], 420)
        self.assertEqual(kwargs['max_iterations'], 16)
        success = len(self.calls) % 3 != 0
        record = {'fixture': 'not-native-model-evidence', 'task_id': kwargs['task_id'],
            'success': success, 'semantic_score': 1.0 if success else .5,
            'infrastructure_valid': self.valid, 'budget_exhausted': not success, 'skill_loaded': True,
            'skill': {'content_sha256': runner.skill_hash(kwargs['skill'])},
            'usage': {'complete': True, 'api_calls': 3, 'total_tokens': 100, 'charged_tokens': 100},
            'diagnostic': {}, 'elapsed_seconds': 0.0}
        save(kwargs['root'] / 'session.json', record)
        return record

    def run_fixture(self):
        return runner.execute(self.out, creds=self.creds, executor=self.execute, learning_executor=self.learn,
                              learning_auditor=lambda *a, **k: {'ok': True, 'status': 'valid_completed'})

    def state(self):
        return json.loads((self.out / 'state.json').read_bytes())

    def test_all_probe_arms_use_the_declared_transport(self):
        from lifespan.evaluation.hermes_transport import manifest_fields
        self.manifest.update(manifest_fields({'hermes_transport': 'nonstreaming'}))
        save(self.out/'manifest.json', self.manifest)
        result = self.run_fixture()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(self.calls), 16)
        self.assertTrue(all(call['hermes_transport'] == 'nonstreaming' for call in self.calls))

    def test_no_adoption_runs_all_identical_skill_probes_with_failures(self):
        report = self.run_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(len(self.calls), 16)
        self.assertEqual(len(self.learning_calls), 1)
        self.assertTrue(self.state()['same_skill'])
        self.assertEqual({call['skill'] for call in self.calls}, {SEED_SKILL})
        self.assertEqual(sum(not row['success'] for row in self.state()['results']), 5)
        self.assertEqual((self.state()['charged_tokens'], self.state()['model_calls']), (1600, 48))
        self.assertEqual((report['combined_charged_or_reserved_tokens'], report['combined_charged_or_reserved_calls']), (2600, 78))
        self.assertEqual(len({id(call['world']) for call in self.calls}), 16)
        self.assertFalse((self.out / 'INFLIGHT.json').exists())
        with self.assertRaises(RuntimeError): self.run_fixture()

    def test_adopted_skill_is_frozen_and_order_counterbalanced(self):
        self.deployed += '\nOffline fixture edit.\n'
        self.run_fixture()
        self.assertFalse(self.state()['same_skill'])
        for call, slot in zip(self.calls, self.manifest['slots']):
            self.assertEqual(call['skill'], SEED_SKILL if slot['arm'] == 'seed' else self.deployed)
        for probe in range(4):
            firsts = [next(row['arm'] for row in self.manifest['slots']
                          if row['probe_index'] == probe and row['repeat_index'] == repeat) for repeat in range(2)]
            self.assertEqual(set(firsts), {'seed', 'deployed'})

    def test_learning_failure_never_dispatches_future_probe(self):
        self.learning_status = 'failed'
        self.assertEqual(self.run_fixture()['status'], 'learning_failed')
        self.assertEqual(self.calls, [])
        self.assertTrue((self.out / 'INFLIGHT.json').exists())
        self.assertEqual(self.state()['phase'], 'learning')
        with self.assertRaises(RuntimeError): self.run_fixture()

    def test_learning_cannot_mutate_withheld_probe(self):
        learn = self.learn
        def altered(*args, **kwargs):
            result = learn(*args, **kwargs)
            save(self.out / 'private/probes/probe-0.json', {})
            return result
        with patch.object(self, 'learn', side_effect=altered):
            self.assertEqual(self.run_fixture()['status'], 'learning_failed')
        self.assertEqual(self.calls, [])

    def test_unknown_probe_retains_full_reservation_and_blocks_retry(self):
        with patch.object(self, 'execute', side_effect=TimeoutError('unknown fixture')):
            report = self.run_fixture()
        self.assertEqual(report['status'], 'infrastructure_error')
        self.assertEqual((self.state()['charged_tokens'], self.state()['model_calls']), (250000, 16))
        self.assertIsNone(self.state()['results'][0]['success'])
        self.assertTrue((self.out / 'INFLIGHT.json').exists())
        with self.assertRaises(RuntimeError): self.run_fixture()

    def test_post_native_audit_failure_preserves_known_physical_usage(self):
        self.auditor.side_effect = ValueError('fixture mismatch')
        self.assertEqual(self.run_fixture()['status'], 'infrastructure_error')
        self.assertEqual((self.state()['charged_tokens'], self.state()['model_calls']), (100, 3))
        self.assertTrue(self.state()['results'][0]['usage']['complete'])

    def test_invalid_native_receipt_is_terminal_not_a_behavioral_failure(self):
        self.valid = False
        self.assertEqual(self.run_fixture()['status'], 'infrastructure_invalid')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.state()['status'], 'infrastructure_invalid')
        self.assertFalse((self.out / 'INFLIGHT.json').exists())

    def test_full_timeout_required_before_each_probe(self):
        with patch.dict(runner.CONFIG, max_run_seconds=419):
            self.assertEqual(self.run_fixture()['status'], 'exhausted_time_budget')
        self.assertEqual(self.calls, [])

    def test_output_with_uncheckpointed_evidence_is_not_reused(self):
        (self.out / 'probes').mkdir()
        with self.assertRaises(RuntimeError): self.run_fixture()
        self.assertEqual(self.learning_calls, [])

    def test_prepare_freezes_inputs_and_rejects_altered_probe_or_code(self):
        # Isolate preparation/provenance logic from native evidence audits. The
        # independent auditor has separate tests for those trusted boundaries.
        fresh, calibration = self.root / 'fresh', self.root / 'calibration'
        cp = json.loads((self.source / 'checkpoint.json').read_bytes())
        cp['runner']['skills'] = {self.employee: SEED_SKILL}
        save(self.source / 'checkpoint.json', cp)
        save(self.source / 'manifest.json', {'config': {}, **{key: self.manifest[key] for key in ('target_model', 'model_base_url')}})
        for name in ('bank.json', 'state.json', 'REPORT.json'):
            save(calibration / name, {})
        save(calibration / 'manifest.json', {'source_directory': str(self.source)})
        selected = {'employee': self.employee, 'experiences': [], 'ranking': []}
        # The setUp patch only applies to execute; use the actual function here.
        original_validate = self.original_validate
        with patch.object(runner, 'audit_run', return_value={'ok': True}), \
             patch.object(runner, 'audit_calibration', return_value={'ok': True}), \
             patch.object(runner, 'select_employee', return_value=selected), \
             patch.object(runner, 'dependency_provenance', return_value={'fixture': True}):
            manifest = runner.prepare(self.source, calibration, fresh)
            self.assertEqual(len(manifest['probe_files_sha256']), 4)
            self.assertEqual(original_validate(fresh)[0], manifest)
            with self.assertRaises(ValueError): runner.prepare(self.source, calibration, fresh)
            capsule_path = fresh / 'private/probes/probe-0.json'
            original = capsule_path.read_bytes()
            save(capsule_path, {})
            with self.assertRaises(ValueError): original_validate(fresh)
            capsule_path.write_bytes(original)
            manifest['source_sha256']['scripts/run_transfer_experiment.py'] = 'altered'
            save(fresh / 'manifest.json', manifest)
            with self.assertRaises(ValueError): original_validate(fresh)


if __name__ == '__main__':
    unittest.main()
