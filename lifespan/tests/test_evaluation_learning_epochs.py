"""Actual upstream consolidation with offline callbacks; not native quality evidence."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import ExperimentConfig, SEED_SKILL, digest
from lifespan.evaluation.runner import _learn
from lifespan.evaluation.skillopt import DEFAULT_SOURCE
from lifespan.evaluation.tasks import make_case
from lifespan.mirofish import save
from lifespan.world import Task


@unittest.skipUnless((DEFAULT_SOURCE / 'skillopt_sleep/consolidate.py').is_file(),
                     'Pinned upstream missing: python3 scripts/install_skillopt.py')
class LearningEpochTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.out = Path(self.temp)
        self.employee = 'firm-0__incident-regulated'
        self.other = 'firm-1__incident-regulated'
        values = ExperimentConfig(algorithm='skillopt', days=24,
            max_learning_calls=1200, max_learning_tokens=24000000,
            skillopt_rollouts_k=2, focal_employee=None).public()
        values.update(max_learning_calls_per_epoch=200, max_learning_tokens_per_epoch=4000000,
                      max_learning_seconds_per_epoch=1800)
        self.config = SimpleNamespace(**values)
        self.eco = Ecosystem(24, 101)
        self.eco.advance()
        self.experiences = []
        for split in ('train', 'val'):
            for index in range(2):
                task_id = split + '-fixture-' + str(index)
                self.eco.worlds['firm-0'].tasks[task_id] = Task(task_id, 'incident', 'regulated',
                    'incident-regulated', 'fixture-customer', 0, 3, 1.0)
                case = make_case('incident', 101, 0, task_id, 'base', 'online')
                case['private']['fixture_marker'] = 'PRIVILEGED_FIXTURE_NEVER_IN_PROGRESS'
                capsule = {'ecosystem': self.eco.checkpoint(), 'case': case,
                    'request': case['request'], 'employee': self.employee, 'firm': 'firm-0',
                    'task_id': task_id, 'objectives': {}, 'business_files': None}
                save(self.out / 'private/cases' / (task_id + '.json'), capsule)
                self.experiences.append({'id': task_id, 'employee': self.employee, 'split': split,
                    'source_session': task_id, 'available_day': 1, 'feedback_available_day': 1,
                    'prompt': case['request'], 'context': json.dumps(case['public_files']),
                    'feedback': 'Public fixture feedback.'})
        while self.eco.day < 3:
            self.eco.advance()
        self.state = {'skills': {self.employee: SEED_SKILL, self.other: SEED_SKILL},
            'skill_versions': {self.employee: 0, self.other: 0}, 'updates': [],
            'learning_calls': 0, 'learning_tokens': 0, 'update_index': 0}
        self.calls, self.reflections, self.begins, self.finishes = [], [], [], []
        self.perfect = True
        self.creds = {'model': 'offline-fixture', 'base_url': 'https://fixture.example.invalid',
                      'api_key': 'PRIVATE_FIXTURE_NO_LIVE_TOKEN'}
        self.native_calls, self.native_tokens = 16, 250000
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch('lifespan.evaluation.optimizer.make_reflector', side_effect=self.make_reflector))
        stack.enter_context(redirect_stdout(io.StringIO()))

    def directory(self):
        return self.out / 'learning' / ('d%03d-%s' % (self.eco.day, self.employee))

    def read_progress(self):
        return json.loads((self.directory() / 'progress.json').read_bytes())

    def make_reflector(self, creds, **options):
        self.assertEqual(creds, self.creds)
        self.assertTrue(options['augment_training_context'])
        def reflect(payload, limits):
            progress = self.read_progress()
            self.assertEqual(progress['optimizer_dispatches'][-1]['dispatch_status'], 'dispatched')
            self.reflections.append(deepcopy(payload))
            receipt = {'status': 'completed', 'model_calls': 1, 'tokens': 3,
                'tool_calls': 0, 'latency_ms': 0.0,
                'response': json.dumps([{'op': 'add', 'content': 'Use the accurate offline fixture procedure.',
                                         'rationale': 'Contract fixture, not learning evidence.'}])}
            reflect.audit_records.append({'accounting_complete': True, 'model_calls': 1,
                'tokens': 3, 'input_tokens': 1, 'output_tokens': 2,
                'optimizer_prompt': payload['prompt'],
                'optimizer_prompt_sha256': hashlib.sha256(payload['prompt'].encode()).hexdigest()})
            return receipt
        reflect.audit_records = []
        return reflect

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        progress = self.read_progress()
        self.assertEqual(progress['replay_artifacts'][-1]['dispatch_status'], 'dispatched')
        self.assertEqual(progress['target_progress']['unknown_usage_replays'], 1)
        self.assertEqual(progress['target_progress']['returned_replays'], len(progress['replay_artifacts']) - 1)
        task = kwargs['world'].tasks[kwargs['task_id']]
        self.assertEqual(task.status, 'pending')
        task.status = 'completed'
        success = self.perfect or 'accurate offline fixture procedure' in kwargs['skill']
        calls = min(self.native_calls, kwargs['max_iterations'])
        tokens = min(self.native_tokens, kwargs['max_total_tokens'])
        record = {'fixture': 'offline-callback-not-native-quality-evidence',
            'employee': kwargs['employee'], 'task_id': kwargs['task_id'],
            'infrastructure_valid': True, 'success': success, 'semantic_score': float(success),
            'feedback': 'Fixture passed.' if success else 'Fixture procedure missing.',
            'usage': {'complete': True, 'api_calls': calls, 'total_tokens': tokens, 'charged_tokens': tokens},
            'elapsed_seconds': 0.0, 'tool_calls': 1, 'skill_loaded': True,
            'result': {'native': {'messages': [{'role': 'tool', 'content': 'Observed public fixture output.'}]}}}
        save(kwargs['root'] / 'session.json', record)
        return record

    def run_epoch(self, **kwargs):
        return _learn(self.out, self.config, self.eco, self.state, self.employee,
            self.experiences, self.creds, kwargs.pop('executor', self.execute),
            lambda *args: self.begins.append(args), lambda: self.finishes.append(True), **kwargs)

    def test_epoch_caps_preserve_employee_budget_for_repeated_learning(self):
        updates = []
        for day in (3, 7, 11):
            while self.eco.day < day:
                self.eco.advance()
            updates.append(self.run_epoch())
        self.assertEqual(len(updates), 3)
        self.assertEqual([u['employee_epoch_index'] for u in updates], [1, 2, 3])
        self.assertEqual([u['epoch_allocation']['model_calls'] for u in updates], [200] * 3)
        self.assertEqual([u['epoch_allocation']['employee_remaining_model_calls'] for u in updates], [600, 440, 280])
        self.assertEqual([u['epoch_allocation']['tokens'] for u in updates], [4000000] * 3)
        self.assertEqual(self.state['learning_calls'], 480)
        self.assertEqual(self.state['learning_tokens'], 7500000)
        self.assertEqual(len(self.calls), 30)
        self.assertEqual(len({id(row['world']) for row in self.calls}), 30)
        self.assertEqual(len(self.finishes), 3)
        self.assertEqual(self.state['skills'][self.other], SEED_SKILL)

    def test_cap_is_inside_existing_fleet_and_equal_employee_quotas(self):
        self.state['updates'] = [{'employee': self.other,
            'costs': {'target_model_calls': 599, 'optimizer_model_calls': 1, 'tokens': 12000000}}]
        self.state['learning_calls'], self.state['learning_tokens'] = 600, 12000000
        result = self.run_epoch()
        allocation = result['epoch_allocation']
        self.assertEqual((allocation['fleet_remaining_model_calls'], allocation['employee_remaining_model_calls']), (600, 600))
        self.assertEqual(result['employee_epoch_index'], 1)
        budget = result['configuration']['budget']
        self.assertEqual(budget['max_target_model_calls'] + budget['max_optimizer_model_calls'], 200)
        self.assertEqual(self.state['learning_calls'], 760)

    def test_optional_missing_caps_keep_legacy_allocation(self):
        for name in ('max_learning_calls_per_epoch', 'max_learning_tokens_per_epoch', 'max_learning_seconds_per_epoch'):
            delattr(self.config, name)
        result = self.run_epoch()
        self.assertEqual(result['epoch_allocation']['model_calls'], 600)
        self.assertEqual(result['configuration']['budget']['max_target_model_calls'], 596)
        self.assertEqual(result['epoch_allocation']['tokens'], 12000000)
        self.assertEqual(result['epoch_allocation']['seconds'], 1800)

    def test_remaining_run_time_bounds_epoch_and_native_dispatches(self):
        self.config.max_learning_seconds_per_epoch = 120
        result = self.run_epoch(remaining_seconds=lambda: 45)
        self.assertEqual(result['configuration']['budget']['max_seconds'], 45)
        self.assertTrue(all(call['timeout_seconds'] <= 45 for call in self.calls))

    def test_replay_progress_binds_every_actual_upstream_phase_and_session(self):
        parent = digest(self.eco.checkpoint())
        result = self.run_epoch(next_update_index=2)
        rows = result['replay_artifacts']
        self.assertEqual(len(rows), 10)
        self.assertEqual([row['attempt_index'] for row in rows], list(range(10)))
        self.assertEqual([row['sample_id'] for row in rows if row['phase'] == 'train'], [0, 0, 0, 1, 0, 1])
        for row, replay in zip(rows, result['replay_evidence']):
            self.assertEqual((row['experience_id'], row['phase'], row['sample_id'], row['skill_sha256']),
                             (replay['id'], replay['phase'], replay['sample_id'], replay['skill_sha256']))
            self.assertEqual(row['session_sha256'], hashlib.sha256((self.out / row['session_path']).read_bytes()).hexdigest())
            self.assertEqual(row['capsule_sha256'], hashlib.sha256((self.out / row['capsule_path']).read_bytes()).hexdigest())
        progress = self.read_progress()
        self.assertEqual(progress['replay_artifacts'], rows)
        self.assertEqual(progress['status'], 'completed')
        self.assertEqual(progress['costs'], result['costs'])
        self.assertEqual(progress['target_progress'], {'dispatched_replays': 10, 'returned_replays': 10,
            'unknown_usage_replays': 0, 'charged_or_reserved_model_calls': 160, 'charged_or_reserved_tokens': 2500000})
        self.assertNotIn('PRIVILEGED_FIXTURE_NEVER_IN_PROGRESS', json.dumps(progress))
        self.assertNotIn(self.creds['api_key'], json.dumps(progress))
        self.assertEqual(digest(self.eco.checkpoint()), parent)
        self.assertEqual(self.state['update_index'], 2)

    def test_accepted_skill_is_incumbent_on_the_next_employee_epoch(self):
        self.perfect = False
        first = self.run_epoch()
        self.assertTrue(first['accepted'])
        self.assertEqual(first['costs']['target_model_calls'], 192)
        self.assertEqual(first['costs']['optimizer_model_calls'], 1)
        progress = self.read_progress()
        self.assertEqual(progress['optimizer_transport_audit'], first['optimizer_transport_audit'])
        self.assertEqual(progress['optimizer_dispatches'][0]['receipt']['tokens'], 3)
        self.assertEqual(progress['optimizer_dispatches'][0]['dispatch_status'], 'returned')
        while self.eco.day < 7:
            self.eco.advance()
        second = self.run_epoch()
        self.assertEqual(second['parent_version'], 1)
        self.assertFalse(second['accepted'])
        self.assertEqual(second['skill'], first['skill'])
        self.assertEqual(second['employee_epoch_index'], 2)
        self.assertEqual(second['skill_before_sha256'], first['skill_after_sha256'])
        self.assertTrue(all(row['skill_sha256'] == first['skill_after_sha256'] for row in second['replay_artifacts']))
        self.assertEqual(len(self.reflections), 1)

    def test_failed_replay_keeps_physical_identity_and_conservative_reservation(self):
        def fail(**kwargs):
            self.assertEqual(self.read_progress()['target_progress']['unknown_usage_replays'], 1)
            raise RuntimeError(self.creds['api_key'])
        with self.assertRaises(RuntimeError):
            self.run_epoch(executor=fail)
        result = self.state['updates'][0]
        self.assertFalse(result['accepted'])
        self.assertFalse(result['costs']['accounting_complete'])
        row = self.read_progress()['replay_artifacts'][0]
        self.assertEqual(row['attempt_index'], 0)
        self.assertEqual(row['phase'], 'baseline_val')
        self.assertEqual(row['dispatch_status'], 'failed_or_interrupted')
        self.assertEqual(row['error_class'], 'RuntimeError')
        self.assertIsNone(row['session_sha256'])
        self.assertEqual(self.read_progress()['target_progress']['charged_or_reserved_model_calls'], 16)
        self.assertEqual(self.read_progress()['target_progress']['charged_or_reserved_tokens'], 250000)
        self.assertNotIn(self.creds['api_key'], json.dumps(self.read_progress()))
        self.assertEqual(self.finishes, [])

    def test_invalid_caps_and_too_small_budget_never_dispatch(self):
        for value in (0, -1, True, 1.5):
            self.config.max_learning_calls_per_epoch = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_epoch()
        self.config.max_learning_calls_per_epoch = 1
        self.config.max_iterations = 1
        self.assertIsNone(self.run_epoch())
        self.assertEqual(self.begins, [])
        self.assertEqual(self.calls, [])
        self.assertFalse((self.out / 'learning').exists())

    def test_known_wall_stop_retains_unscored_native_identity_and_finishes_without_adoption(self):
        clock = [0.]
        def late(**kwargs):
            record = self.execute(**kwargs)
            clock[0] += 421.
            return record
        with patch('lifespan.evaluation.skillopt.time', SimpleNamespace(monotonic=lambda: clock[0])):
            result = self.run_epoch(executor=late)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertFalse(result['accepted'])
        self.assertTrue(result['costs']['accounting_complete'])
        self.assertEqual(result['costs']['target_model_calls'], 16)
        self.assertEqual(result['replay_evidence'], [])
        self.assertEqual(len(result['unscored_replay_evidence']), 1)
        self.assertEqual(result['unscored_replay_evidence'][0]['attempt_index'], 0)
        self.assertEqual(self.state['skills'][self.employee], SEED_SKILL)
        self.assertEqual(self.finishes, [True])
        self.assertEqual(self.read_progress()['replay_artifacts'], result['replay_artifacts'])

    def test_physical_overrun_keeps_actual_cost_and_blocks_epoch_finish(self):
        def overrun(**kwargs):
            record = self.execute(**kwargs)
            record['usage']['api_calls'] = kwargs['max_iterations'] + 1
            save(kwargs['root'] / 'session.json', record)
            return record
        with self.assertRaises(RuntimeError):
            self.run_epoch(executor=overrun)
        result = self.state['updates'][0]
        self.assertFalse(result['accepted'])
        self.assertTrue(result['costs']['accounting_complete'])
        self.assertEqual(result['costs']['target_model_calls'], 17)
        self.assertIn('model_calls', result['costs']['stop_evidence']['violations'])
        self.assertEqual(self.state['skills'][self.employee], SEED_SKILL)
        self.assertEqual(self.finishes, [])

    def test_failed_callback_with_known_timing_overrun_blocks_finish(self):
        clock = [0.]
        def late_failure(**kwargs):
            record = self.execute(**kwargs)
            record['infrastructure_valid'] = False
            save(kwargs['root'] / 'session.json', record)
            clock[0] += 421.
            return record
        with patch('lifespan.evaluation.skillopt.time', SimpleNamespace(monotonic=lambda: clock[0])):
            with self.assertRaises(RuntimeError):
                self.run_epoch(executor=late_failure)
        result = self.state['updates'][0]
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['costs']['accounting_complete'])
        self.assertEqual(result['costs']['target_model_calls'], 16)
        self.assertEqual(self.finishes, [])


if __name__ == '__main__':
    unittest.main()
