"""Offline wrapper fixtures with actual upstream consolidation; no native quality evidence."""
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
from lifespan.evaluation.protocol import SEED_SKILL, experience_split
from lifespan.evaluation.skillopt import DEFAULT_SOURCE
from lifespan.evaluation.tasks import make_case
from lifespan.mirofish import save
from lifespan.world import Task
from scripts import transfer_learning as learner


class TransferLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.out = self.root / 'source', self.root / 'learning'
        self.employee = 'firm-0__incident-regulated'
        self.creds = {'model': 'fixture-no-model', 'base_url': 'https://fixture.example.invalid',
                      'api_key': 'SECRET_FIXTURE_NEVER_PERSIST'}
        eco = Ecosystem(10, 101)
        self.experiences, records = [], []
        seen = set()
        for index, split in enumerate(('train', 'train', 'val', 'val')):
            eco.advance()
            suffix = 0
            while True:
                task_id = 'fixture-task-' + str(suffix)
                suffix += 1
                if task_id not in seen and experience_split(task_id) == split:
                    break
            seen.add(task_id)
            task = Task(id=task_id, workflow='incident', segment='regulated',
                        owner='incident-regulated', customer='fixture-customer',
                        created=index, due=index + 3, value=1.0)
            eco.worlds['firm-0'].tasks[task_id] = task
            case = make_case('incident', 101, index, task_id, 'base', 'online')
            capsule = {'ecosystem': eco.checkpoint(), 'employee': self.employee,
                       'firm': 'firm-0', 'task_id': task_id, 'case': case,
                       'request': case['request'], 'business_files': None, 'objectives': {}}
            identifier = 'd%03d-%s-%s' % (index, self.employee, task_id)
            item = {'id': identifier, 'employee': self.employee, 'source_session': task_id,
                    'split': split, 'available_day': index + 1, 'feedback_available_day': index + 1,
                    'prompt': case['request'], 'context': json.dumps(case['public_files']),
                    'feedback': 'Public historical feedback.'}
            self.experiences.append(item)
            record = {'employee': self.employee, 'day': index, 'task_id': task_id,
                      'case_id': task_id, 'feedback': item['feedback'], 'fixture': True}
            save(self.source / 'private/cases' / (identifier + '.json'), capsule)
            save(self.source / 'work' / identifier / 'session.json', record)
            records.append(dict(record, id=identifier, skill_version=0))
        while eco.day < 9:
            eco.advance()
        self.cp = {'ecosystem': eco.checkpoint(), 'runner': {
            'skills': {self.employee: SEED_SKILL}, 'skill_versions': {self.employee: 0},
            'experiences': deepcopy(self.experiences), 'sessions': records}}
        save(self.source / 'checkpoint.json', self.cp)
        save(self.source / 'skills' / self.employee / 'v000.json', {'skill': SEED_SKILL,
             'hash': hashlib.sha256(SEED_SKILL.encode()).hexdigest(), 'version': 0, 'adopted_after_day': -1})
        save(self.source / 'manifest.json', {'target_model': self.creds['model'],
             'model_base_url': self.creds['base_url'],
             'config': {'split': 'dev', 'algorithm': 'no_learning', 'state_mode': 'skill_transfer',
                        'seed': 101, 'days': 8, 'feedback_delay': 1}})
        save(self.source / 'private/cases/held-out-probe.json', {'probe': {'day': 10},
             'private': 'FUTURE_PROBE_NEVER_COPY'})
        self.calls, self.reflections = [], []
        self.perfect, self.adopt, self.break_final = True, True, False
        self.native_calls, self.native_tokens = 3, 100
        stack = self.enterContext(ExitStack())
        self.audit = stack.enter_context(patch.object(learner, 'audit_run', return_value={'ok': True}))
        stack.enter_context(patch.object(learner, 'session_check', side_effect=self.check_record))
        stack.enter_context(patch.object(learner, 'source_hashes', return_value={'fixture.py': 'test'}))
        stack.enter_context(patch.object(learner, 'dependency_provenance', return_value={'fixture': True}))
        stack.enter_context(patch.object(learner, 'credentials', side_effect=AssertionError('No real credentials in tests')))
        stack.enter_context(patch('lifespan.evaluation.optimizer.make_reflector', side_effect=self.make_reflector))
        stack.enter_context(redirect_stdout(io.StringIO()))

    def check_record(self, record, directory, capsule):
        self.assertEqual({k: v for k, v in record.items() if k not in ('id', 'skill_version')},
                         json.loads((directory / 'session.json').read_bytes()))
        self.assertEqual(record['task_id'], capsule['task_id'])
        self.assertEqual(record['employee'], capsule['employee'])

    def make_reflector(self, creds, **options):
        self.assertEqual(creds, self.creds)
        self.assertTrue(options['augment_training_context'])
        def reflect(payload, limits):
            self.reflections.append(deepcopy(payload))
            output = json.dumps([{'op': 'add', 'content': 'Use calibrated fixture repair.',
                                  'rationale': 'Deterministic contract fixture.'}])
            reflect.audit_records.append({'accounting_complete': True, 'model_calls': 1,
                'tokens': 3, 'input_tokens': 2, 'output_tokens': 1,
                'optimizer_prompt': payload['prompt'],
                'optimizer_prompt_sha256': hashlib.sha256(payload['prompt'].encode()).hexdigest()})
            return {'status': 'completed', 'tokens': 3, 'model_calls': 1,
                    'tool_calls': 0, 'latency_ms': 0.0, 'response': output}
        reflect.audit_records = []
        return reflect

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        task = kwargs['world'].tasks[kwargs['task_id']]
        self.assertEqual(task.status, 'pending')
        task.status = 'completed'  # Every subsequent rollout must restore pending.
        score = self.perfect or (self.adopt and 'calibrated fixture repair' in kwargs['skill'])
        if self.break_final and len(self.calls) > 10:
            score = False
        self.assertLessEqual(kwargs['max_iterations'], 16)
        self.assertLessEqual(kwargs['max_total_tokens'], 250000)
        self.assertLessEqual(kwargs['timeout_seconds'], 420)
        record = {'fixture': 'not-native-quality-evidence', 'employee': kwargs['employee'],
            'task_id': kwargs['task_id'], 'day': kwargs['case']['day'],
            'infrastructure_valid': True, 'success': bool(score), 'semantic_score': float(score),
            'feedback': 'Passed fixture.' if score else 'Repair missing.',
            'usage': {'complete': True, 'api_calls': self.native_calls,
                      'total_tokens': self.native_tokens, 'charged_tokens': self.native_tokens},
            'tool_calls': 1, 'elapsed_seconds': 0.0,
            'skill': {'content_sha256': hashlib.sha256(kwargs['skill'].encode()).hexdigest()},
            'result': {'native': {'messages': [{'role': 'tool', 'content': 'Public observed fixture result.'}]}}}
        save(kwargs['root'] / 'session.json', record)
        return record

    def run_fixture(self, **kwargs):
        if not (DEFAULT_SOURCE / 'skillopt_sleep/consolidate.py').is_file():
            self.skipTest('Pinned upstream missing: python3 scripts/install_skillopt.py')
        return learner.run_learning_epoch(self.source, self.out, self.employee,
            self.experiences, creds=self.creds, executor=kwargs.pop('executor', self.execute), **kwargs)

    def load(self, name):
        return json.loads((self.out / name).read_bytes())

    def test_no_adoption_is_valid_and_every_k_rollout_is_fresh(self):
        parent = (self.source / 'checkpoint.json').read_bytes()
        report = self.run_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertFalse(report['accepted'])
        self.assertEqual(report['skill_version'], 0)
        self.assertEqual(report['execution_mode'], 'injected_executor_fixture')
        self.assertEqual(len(self.calls), 10)  # baseline V + initial T + K*T + final V
        self.assertEqual(len({id(call['world']) for call in self.calls}), 10)
        self.assertEqual(self.reflections, [])
        self.assertEqual(report['usage']['model_calls'], 30)
        self.assertEqual(report['usage']['tokens'], 1000)
        self.assertTrue(report['usage']['accounting_complete'])
        self.assertEqual((self.source / 'checkpoint.json').read_bytes(), parent)
        self.assertEqual(self.load('checkpoint.json')['ecosystem'], self.cp['ecosystem'])
        self.assertEqual(len(self.load('state.json')['updates']), 1)
        self.assertEqual(self.load('state.json'), self.load('checkpoint.json')['runner'])
        self.assertFalse((self.out / 'INFLIGHT.json').exists())
        self.assertFalse(report['future_probes_evaluated'])
        self.assertTrue(report['parent_unchanged'])
        copied = sorted(p.name for p in (self.out / 'private/cases').iterdir())
        self.assertEqual(copied, sorted(e['id'] + '.json' for e in self.experiences))
        for name in copied:
            self.assertEqual((self.source / 'private/cases' / name).read_bytes(),
                             (self.out / 'private/cases' / name).read_bytes())
        evidence = self.load('evidence.json')
        self.assertEqual([e['attempt_index'] for e in evidence['target_sessions']], list(range(10)))
        self.assertEqual(len([e for e in evidence['target_sessions'] if e['phase'] == 'train']), 6)
        self.assertTrue(all(e['session_sha256'] == learner.file_hash(self.out / e['session_path'])
                            for e in evidence['target_sessions']))
        with self.assertRaises(ValueError):
            self.run_fixture()

    def test_accepted_candidate_has_final_replays_receipts_and_no_probe_deployment(self):
        self.perfect = False
        report = self.run_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertTrue(report['accepted'])
        self.assertEqual(report['skill_version'], 1)
        self.assertFalse(report['deployed_to_future_probes'])
        self.assertEqual(len(self.calls), 12)
        self.assertEqual(report['usage']['model_calls'], 37)
        self.assertEqual(report['usage']['tokens'], 1203)
        self.assertEqual(len(self.reflections), 1)
        val_ids = {e['id'] for e in self.experiences if e['split'] == 'val'}
        self.assertFalse(any(i in json.dumps(self.reflections) for i in val_ids))
        self.assertNotIn('FUTURE_PROBE_NEVER_COPY', json.dumps(self.reflections))
        update = self.load(report['update_path'])
        self.assertEqual((update['parent_version'], update['deployed_version']), (0, 1))
        self.assertEqual(update['configuration']['rollouts_k'], 2)
        self.assertEqual(update['available_from_day'], 10)
        self.assertEqual(len(self.load('evidence.json')['optimizer_receipts']), 1)
        self.assertEqual(self.load('skills/' + self.employee + '/v001.json')['skill'], update['skill'])
        for path in self.out.rglob('*.json'):
            self.assertNotIn(self.creds['api_key'], path.read_text())

    def test_final_gate_rejects_regression_without_changing_seed(self):
        self.perfect = False
        self.break_final = True
        report = self.run_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertFalse(report['accepted'])
        self.assertEqual(report['skill_version'], 0)
        self.assertEqual(len(self.calls), 12)
        self.assertEqual(self.load('state.json')['skills'][self.employee], SEED_SKILL)

    def test_full_native_reservations_fit_the_200_call_and_4m_token_contract(self):
        self.perfect = False
        self.native_calls, self.native_tokens = 16, 250000
        report = self.run_fixture()
        self.assertEqual(report['usage']['model_calls'], 193)
        self.assertEqual(report['usage']['tokens'], 3000003)
        self.assertTrue(report['accepted'])
        self.assertEqual(self.load('manifest.json')['limits'], learner.LIMITS)

    def test_failed_unknown_receipt_retains_reservation_and_inflight(self):
        def failing(**kwargs):
            raise RuntimeError(self.creds['api_key'])
        report = self.run_fixture(executor=failing)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['accepted'])
        self.assertFalse(report['usage']['accounting_complete'])
        self.assertIsNone(report['usage']['tokens'])
        self.assertIsNone(report['usage']['model_calls'])
        self.assertEqual(report['usage']['charged_or_reserved_tokens'], 250000)
        self.assertEqual(report['usage']['charged_or_reserved_model_calls'], 16)
        self.assertTrue((self.out / 'INFLIGHT.json').exists())
        self.assertTrue((self.out / 'FAILURE.json').exists())
        target = self.load('evidence.json')['target_sessions'][0]
        self.assertEqual(target['dispatch_status'], 'interrupted_or_failed')
        self.assertIsNone(target['session_sha256'])
        self.assertEqual(target['cost']['accounting'], 'reservation')
        for path in self.out.rglob('*.json'):
            self.assertNotIn(self.creds['api_key'], path.read_text())
        with self.assertRaises(ValueError):
            self.run_fixture()

    def test_parent_mutation_stops_further_dispatch(self):
        def mutating(**kwargs):
            result = self.execute(**kwargs)
            (self.source / 'checkpoint.json').write_text('{}')
            return result
        report = self.run_fixture(executor=mutating)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['parent_unchanged'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((self.out / 'INFLIGHT.json').exists())

    def test_copied_capsule_mutation_cannot_influence_later_replays(self):
        def mutating(**kwargs):
            result = self.execute(**kwargs)
            selected = next(e for e in self.experiences if e['source_session'] == kwargs['task_id'])
            path = self.out / 'private/cases' / (selected['id'] + '.json')
            capsule = json.loads(path.read_bytes())
            capsule['case']['private']['fixture_poison'] = True
            save(path, capsule)
            return result
        report = self.run_fixture(executor=mutating)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['accepted'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(report['parent_unchanged'])
        self.assertTrue((self.out / 'INFLIGHT.json').exists())

    def test_all_preflight_rejections_dispatch_nothing(self):
        variants = []
        for key, value in [('feedback_available_day', 10), ('available_day', 10),
                           ('employee', 'firm-1__incident-regulated'), ('split', 'test'),
                           ('feedback', 'Altered feedback'), ('prompt', 'future instructions'),
                           ('context', '{}')]:
            altered = deepcopy(self.experiences)
            altered[0][key] = value
            variants.append(altered)
        variants += [self.experiences[:3], self.experiences[:3] + [self.experiences[0]]]
        for selected in variants:
            with self.subTest(selected=selected[0].get('split')), self.assertRaises(ValueError):
                learner.run_learning_epoch(self.source, self.out, self.employee, selected,
                    creds=self.creds, executor=self.execute)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.calls, [])

    def test_cutoff_provider_source_audit_and_namespace_are_required(self):
        with self.assertRaises(ValueError):
            self.run_fixture(cutoff_day=8)
        self.audit.return_value = {'ok': False}
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.audit.return_value = {'ok': True}
        self.creds['model'] = 'other-provider-model'
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.creds['model'] = 'fixture-no-model'
        path = self.source / 'private/cases' / (self.experiences[0]['id'] + '.json')
        capsule = json.loads(path.read_bytes()); capsule['probe'] = {'day': 10}; save(path, capsule)
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.assertFalse(self.out.exists())

    def test_source_descriptor_itself_cannot_override_capsule_feedback_or_time(self):
        for key, value in [('feedback', 'Source descriptor poisoned'), ('context', '{}'),
                           ('feedback_available_day', 10)]:
            original = deepcopy(self.experiences)
            self.experiences[0][key] = value
            self.cp['runner']['experiences'] = deepcopy(self.experiences)
            save(self.source / 'checkpoint.json', self.cp)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_fixture()
            self.experiences = original
        self.assertEqual(self.calls, [])

    def test_source_and_learning_output_cannot_overlap(self):
        for out in [self.source, self.source / 'learning', self.root]:
            with self.assertRaises(ValueError):
                learner.run_learning_epoch(self.source, out, self.employee, self.experiences,
                    creds=self.creds, executor=self.execute)


if __name__ == '__main__':
    unittest.main()
