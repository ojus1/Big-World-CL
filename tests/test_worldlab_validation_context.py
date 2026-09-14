"""Information-flow and full saved-replay checks for prospective gate isolation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.source_world_calibration import read, save, sha
from worldlab.worlds import compile_world, prepare_study, execute_study
from worldlab.validation_context import ISOLATED, select_experiences, validate_world, observed_feedback
from worldlab.audit_worlds import audit, audit_updates, audit_attempt
from worldlab.audit_reacting import replay_commands
from test_worldlab_worlds import SPEC
from test_worldlab_judge_adapter import Bank as BaseBank, Harness, Judge as BaseJudge, ReplayLearner

CANARY = 'VALIDATION_ONLY_PRIVATE_FEEDBACK_763a98'


class Bank(BaseBank):
    def public(self, task_id):
        value = super().public(task_id)
        if self.by_id[task_id]['partition'] == 'calibration_validation':
            value['instruction'] += ' GATE_ONLY_PUBLIC_INSTRUCTION_c56d0f'
        return value


class Judge(BaseJudge):
    def grade(self, task_id, workspace, baseline, out, **kwargs):
        result = self.result(workspace)
        if task_id.startswith('validation-'):
            result['feedback'] = CANARY
        save(out / 'NATIVE_BINARY_VERDICT.json', {'task': task_id, 'verdict': result})
        return result

    @staticmethod
    def audit_grade(bank, task_id, workspace, baseline, root, receipt):
        result = BaseJudge.result(workspace)
        if task_id.startswith('validation-'):
            result['feedback'] = CANARY
        if receipt != result or read(root / 'NATIVE_BINARY_VERDICT.json') != {'task': task_id, 'verdict': result}:
            raise ValueError('Canary judge receipt changed')


class EchoDriver:
    """Deliberately propagates every available feedback channel into requests."""
    def decide(self, view, key, validate):
        text = '\n'.join([view['own_previous_working_notes']] +
                         [f['feedback'] for f in view['recent_observed_outcomes']] +
                         [m['text'] for m in view['received_colleague_messages']])
        messages = ([{'recipient': view['colleagues'][0], 'text': text[-1600:] or 'No feedback yet',
                      'document_ids': []}] if view['colleagues'] else [])
        decision = {'delegate': True, 'request': view['substantive_work'] + '\n' + text,
                    'working_notes': text[-1800:], 'colleague_messages': messages,
                    'share_document_ids': [], 'process_proposal': None}
        validate(decision)
        return decision

    def usage(self): return {'model_calls': 0, 'tokens': 0}
    def close(self): pass


class Factory:
    def __init__(self): self.inputs = []
    def identity(self): return {'name': 'feedback_echo_fixture'}
    def prepare(self, world):
        self.inputs.append(deepcopy(world))
        return {'fixture': 'no model calls'}
    def open(self, world, context, out):
        self.inputs.append(deepcopy(world))
        return EchoDriver()


class Tests(unittest.TestCase):
    def spec(self): return {**deepcopy(SPEC), 'validation_context': ISOLATED}

    def test_gate_catalog_is_prospective_distinct_and_never_live_work(self):
        world = compile_world(Bank(), self.spec(), 211, Harness(), Judge())
        self.assertEqual(world, compile_world(Bank(), self.spec(), 211, Harness(), Judge()))
        self.assertEqual(len(world['schedule']), 10)
        self.assertEqual({s['split'] for s in world['schedule']}, {'train', 'probe'})
        gates = world['validation_cases']['writer']
        self.assertEqual(len({s['lineage_group'] for s in gates}), 2)
        self.assertTrue(all('grade' not in s and 'status' not in s and 'employee_message' not in s for s in gates))
        sessions = [{**s, 'status': 'completed', 'grade': {'feedback': 'ordinary'}} for s in world['schedule']]
        self.assertEqual(select_experiences(world, sessions, 'writer', 0), [])
        chosen = select_experiences(world, sessions, 'writer', 6)
        self.assertEqual(len(chosen), 4)
        self.assertEqual([s for s in chosen if s['split'] == 'val'], gates)
        self.assertTrue(all(s['feedback_day'] <= 6 for s in chosen))

    def test_invalid_policy_missing_families_and_wrong_partition_are_rejected(self):
        for change in [{'validation_context': 'typo'}, {'val_cases': 4}, {'train_cases': 0}, {'val_cases': True}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_world(Bank(), {**self.spec(), **change}, 211, Harness(), Judge())
        world = compile_world(Bank(), self.spec(), 211, Harness(), Judge())
        mutations = [lambda w: w['validation_cases']['writer'][0].update(employee_message=CANARY),
                     lambda w: w['validation_cases']['writer'][0].update(grade={'feedback': CANARY}),
                     lambda w: w['validation_cases']['writer'][0].update(task_id='train-0'),
                     lambda w: w['schedule'][0].update(task_id='validation-0', lineage_group='validation-0'),
                     lambda w: w['validation_cases']['writer'].pop(),
                     lambda w: w['validation_cases']['writer'][0].update(day=True)]
        for mutation in mutations:
            corrupt = deepcopy(world); mutation(corrupt)
            with self.assertRaises(ValueError): validate_world(Bank(), corrupt)
        corrupt = deepcopy(world['validation_cases']['writer'][0]); corrupt['grade'] = {'feedback': CANARY}
        with self.assertRaises(ValueError): observed_feedback(corrupt)
        with self.assertRaises(ValueError): select_experiences(world, [{'split': 'val'}], 'writer', 6)

    def test_complete_fixed_study_audits_gate_replay_without_fabricated_online_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'; bank, harness, judge, learner = Bank(), Harness(), Judge(), ReplayLearner()
            prepare_study(bank, self.spec(), [211], harness, judge, learner, out)
            execute_study(bank, harness, judge, learner, out)
            result = audit(bank, out, harness, learner, judge)
            self.assertEqual(result['online_attempts'], 20)
            self.assertEqual(result['learning_replays'], 1)
            root = out / 'worlds/seed-211/fixture_replay_policy'
            request = read(root / 'learning/d006-writer/replay-000/PUBLIC_REQUEST.json')
            self.assertIn('GATE_ONLY_PUBLIC_INSTRUCTION', request['instruction'])
            self.assertNotIn('Employee request', request['instruction'])
            self.assertFalse(any(p.name.startswith('gate-') for p in (root / 'sessions').iterdir()))
            # Even rewriting the manifest receipt cannot authorize injected context.
            study = read(out / 'STUDY.json')
            study['worlds'][0]['validation_cases']['writer'][0]['employee_message'] = CANARY
            save(out / 'STUDY.json', study)
            prepared = read(out / 'PREPARED.json'); prepared['study_sha256'] = sha(out / 'STUDY.json')
            save(out / 'PREPARED.json', prepared)
            with self.assertRaisesRegex(ValueError, 'unexpected context'): audit(bank, out, harness, learner, judge)

    def test_validation_cannot_flow_through_employee_notes_or_colleague_messages(self):
        spec = self.spec()
        spec['employees'].append({'id': 'colleague', 'role': 'Editor', 'language': 'en'})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'; bank, harness, judge, learner = Bank(), Harness(), Judge(), ReplayLearner()
            factory = Factory()
            prepare_study(bank, spec, [211], harness, judge, learner, out, factory)
            execute_study(bank, harness, judge, learner, out, factory)
            self.assertTrue(all('validation_cases' not in w for w in factory.inputs))
            world = read(out / 'STUDY.json')['worlds'][0]
            for arm in ['no_learning', learner.identity()['name']]:
                root = out / 'worlds/seed-211' / arm
                state = read(root / 'STATE.json')
                replay_commands(bank, world, state)
                self.assertEqual(len(state['sessions']), 20)
                self.assertTrue(any(d['view']['received_colleague_messages'] for d in state['decisions']))
                for text in [json.dumps(state['decisions']), json.dumps(state['workplace'])]:
                    self.assertNotIn(CANARY, text)
                    self.assertNotIn('GATE_ONLY_PUBLIC_INSTRUCTION', text)
                for session in state['sessions']:
                    audit_attempt(bank, root / 'sessions' / session['id'], session['task_id'],
                                  harness=harness, judge=judge, employee_message=session['employee_message'])
                counts = {'learning_replays': 0, 'adoptions': 0}
                audit_updates(bank, world, root, state, arm, harness, counts, learner, learner.identity(), judge)
                self.assertEqual(counts['learning_replays'], 0 if arm == 'no_learning' else 2)
                if arm != 'no_learning':
                    for path in root.glob('learning/*/replay-*/ATTEMPT.json'):
                        self.assertEqual(read(path)['grade']['feedback'], CANARY)

    def test_native_skillopt_reflection_excludes_isolated_validation_canaries(self):
        from lifespan.evaluation.skillopt import SkillOptLearner, LearningBudget, DEFAULT_SOURCE
        if not DEFAULT_SOURCE.is_dir(): self.skipTest('Pinned native SkillOpt checkout required')
        bank = Bank(); world = compile_world(bank, self.spec(), 211, Harness(), Judge())
        sessions = [{**s, 'status': 'completed', 'grade': {'feedback': 'Ordinary train feedback'},
                     'employee_message': 'Ordinary request'} for s in world['schedule']]
        selected = select_experiences(world, sessions, 'writer', 6)
        from worldlab.attempts import task_instruction
        experiences = [{'id': s['id'], 'split': s['split'], 'available_day': s['day'],
                        'feedback_available_day': s['feedback_day'], 'source_session': s['lineage_group'],
                        'prompt': task_instruction(bank.public(s['task_id'])['instruction'], s.get('employee_message')),
                        'context': '', 'feedback': observed_feedback(s)} for s in selected]
        reflections = []
        def replay(payload, limits):
            val = payload['task']['split'] == 'val'
            return {'status': 'completed', 'hard': float(val), 'soft': float(val),
                    'response': CANARY if val else 'Training attempt failed',
                    'feedback': CANARY if val else 'Fix the training failure',
                    'tokens': 10, 'model_calls': 1, 'tool_calls': 0, 'latency_ms': 0}
        def reflect(payload, limits):
            reflections.append(payload)
            self.assertNotIn(CANARY, json.dumps(payload))
            self.assertNotIn('GATE_ONLY_PUBLIC_INSTRUCTION', json.dumps(payload))
            return {'status': 'completed', 'response': '[]', 'tokens': 10,
                    'model_calls': 1, 'tool_calls': 0, 'latency_ms': 0}
        result = SkillOptLearner(source=DEFAULT_SOURCE, edit_budget=1, rollouts_k=2).update(
            '# Work process\nRead evidence.', experiences, replay, reflect, current_day=6,
            budget=LearningBudget(max_tokens=100000, replay_tokens=1000, max_seconds=300, replay_seconds=5))
        self.assertEqual(result['status'], 'completed')
        self.assertGreater(len(reflections), 0)
        self.assertTrue(all(e['feedback'] == '' for e in experiences if e['split'] == 'val'))


if __name__ == '__main__': unittest.main()
