"""Alternate binary-evidence scoring must work without the internal r3 format."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import read, save, sha
from worldlab.adapters import load_adapter
from worldlab.attempts import execute_task
from worldlab.audit_worlds import audit, audit_attempt, resolve_judge
from worldlab.contracts import Budget, NoLearning, validate_grade
from worldlab.worlds import prepare_study, execute_study
from test_worldlab_worlds import Bank as ScheduleBank, SPEC
from test_worldlab_adapters import Harness as ExecutionHarness


class Bank(ScheduleBank):
    """No private rubric paths; deliberately non-UTF8 public evidence."""
    def __init__(self):
        super().__init__()
        self.inventory = {}
        for row in self.rows:
            row['public_directory'] = 'public/' + row['id']
            self.inventory[row['public_directory'] + '/input.bin'] = {
                'sha256': hashlib.sha256(b'\xff\x00source').hexdigest()}

    def stage(self, task_id, workspace):
        workspace.mkdir(parents=True)
        (workspace / 'input.bin').write_bytes(b'\xff\x00source')
        return {'input.bin': sha(workspace / 'input.bin')}


class Harness(ExecutionHarness):
    def identity(self): return {'name': 'binary_fixture_harness'}

    def run(self, request, artifact_root):
        result = super().run(request, artifact_root)
        (request.workspace / 'output').mkdir()
        (request.workspace / 'output/result.bin').write_bytes(b'\xfe\x01result')
        return result

    @staticmethod
    def audit_execution(root, request, receipt):
        if (root / 'deployment.txt').read_text() != request['skill']:
            raise ValueError('Wrong fixture skill')


class Judge:
    max_tokens = 1000
    def identity(self): return {'name': 'binary_fixture_judge', 'rule': 'exact output bytes'}
    def unsupported(self, public): return []

    @staticmethod
    def result(workspace):
        passed = (workspace / 'output/result.bin').read_bytes() == b'\xfe\x01result'
        return {'grading_complete': True, 'quality_score': float(passed), 'success': passed,
                'feedback': 'Exact byte fixture ' + ('satisfied' if passed else 'failed'),
                'usage': {'physical_model_calls': 0, 'charged_tokens': 0, 'accounting_complete': True}}

    def grade(self, task_id, workspace, baseline, out, **kwargs):
        result = self.result(workspace)
        save(out / 'NATIVE_BINARY_VERDICT.json', {'task': task_id, 'verdict': result})
        return result

    @staticmethod
    def audit_grade(bank, task_id, workspace, baseline, root, receipt):
        if (receipt != Judge.result(workspace) or
                read(root / 'NATIVE_BINARY_VERDICT.json') != {'task': task_id, 'verdict': receipt} or
                any(sha(workspace / name) != digest for name, digest in baseline.items())):
            raise ValueError('Binary verdict differs from original evidence')


class Learner(NoLearning):
    def identity(self): return {'name': 'fixture_unchanged_policy'}


class ReplayLearner:
    def identity(self): return {'name': 'fixture_replay_policy', 'budget': {'max_tokens': 20000}}

    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        task = experiences[0]
        result = replay({'task': task, 'attempt_index': 0, 'skill': skill},
                        {'max_tokens': 20000, 'max_model_calls': 40, 'timeout_seconds': 1200})
        update = {'status': 'completed', 'accepted': False, 'skill': skill,
                  'train_ids': [e['id'] for e in experiences if e['split'] == 'train'],
                  'validation_ids': [e['id'] for e in experiences if e['split'] == 'val'],
                  'replay_evidence': [{'id': task['id'], 'attempt_index': 0, 'hard': result['hard'],
                                      'soft': result['soft'], 'skill_sha256': hashlib.sha256(skill.encode()).hexdigest()}],
                  'costs': {'tokens': result['tokens'], 'target_model_calls': result['model_calls'],
                            'optimizer_model_calls': 0, 'accounting_complete': True,
                            'operations': [{'kind': 'target', 'tokens': result['tokens'], 'model_calls': result['model_calls']}]}}
        save(artifact_root / 'UPDATE.json', update)
        return update

    def audit_update(self, root, update, *, skill_before, expected_identity):
        if (expected_identity != self.identity() or update['skill'] != skill_before or update['accepted'] or
                len(update['replay_evidence']) != 1):
            raise ValueError('Wrong fixture replay policy')


class UnauditableJudge:
    max_tokens = 1000
    def identity(self): return {'name': 'missing_audit'}
    def unsupported(self, public): return []
    def grade(self, *args, **kwargs): raise AssertionError('Never dispatch')


class Tests(unittest.TestCase):
    def test_online_attempt_uses_declared_judge_calls_and_respects_explicit_override(self):
        class DeclaredJudge(Judge):
            max_model_calls = 9
        for override, expected in [(None, 9), (3, 3)]:
            with self.subTest(override=override), tempfile.TemporaryDirectory() as tmp:
                judge = DeclaredJudge()
                with patch.object(judge, 'grade', wraps=judge.grade) as grade:
                    execute_task(Bank(), Harness(), judge, task_id='a', employee_id='employee',
                                 skill='seed', budget=Budget(), out=Path(tmp) / 'attempt', judge_calls=override)
                    self.assertEqual(grade.call_args.kwargs['call_limit'], expected)

    def test_complete_world_pair_with_alternate_binary_evidence_and_offline_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root / 'judge.json'
            save(config, {'factory': 'test_worldlab_judge_adapter:Judge', 'kwargs': {}})
            judge = load_adapter(config, 'judge')
            bank, harness, learner = Bank(), Harness(), ReplayLearner()
            spec = deepcopy(SPEC)
            study = root / 'study'
            prepare_study(bank, spec, [211], harness, judge, learner, study)
            execute_study(bank, harness, judge, learner, study)
            with patch('worldlab.qualitative.FrozenRubricJudge.audit_grade', side_effect=AssertionError('Wrong judge')):
                result = audit(bank, study, harness, learner, judge)
            self.assertEqual(result['online_attempts'], 20)
            self.assertEqual(result['world_pairs'], 1)
            self.assertEqual(result['learning_replays'], 1)
            self.assertIsNone(read(study / 'STUDY.json')['analysis']['same_model_judge'])
            self.assertFalse(list(study.rglob('GRADE.json')))
            self.assertEqual(len(list(study.rglob('NATIVE_BINARY_VERDICT.json'))), 21)

    def test_tampered_grade_rejected_by_policy_even_with_rehashed_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'attempt'; bank, harness, judge = Bank(), Harness(), Judge()
            record = execute_task(bank, harness, judge, task_id='train-0', employee_id='writer',
                                  skill='seed', budget=Budget(), out=root)
            self.assertEqual(audit_attempt(bank, root, 'train-0', 'seed', harness, judge=judge), record)
            record['grade'].update(success=False, quality_score=0.)
            native = root / 'judging/NATIVE_BINARY_VERDICT.json'
            save(native, {'task': 'train-0', 'verdict': record['grade']})
            record['artifact_inventory'][str(native.relative_to(root))] = sha(native)
            save(root / 'ATTEMPT.json', record)
            with self.assertRaisesRegex(ValueError, 'Binary verdict differs'):
                audit_attempt(bank, root, 'train-0', harness=harness, judge=judge)

    def test_factory_cannot_silently_use_builtin_or_a_different_bank(self):
        judge = Judge()
        self.assertIs(resolve_judge({'judge': judge.identity()}, judge), judge)
        with self.assertRaisesRegex(ValueError, 'differs from frozen identity'):
            resolve_judge({'judge': {**judge.identity(), 'rule': 'another rule'}}, judge)
        with self.assertRaisesRegex(ValueError, 'frozen judge factory'):
            resolve_judge({'judge': {'name': 'frozen_internal_r3_text_judge', 'operator_factory': {}}})
        class WrongBank(Judge):
            def identity(self): return {**super().identity(), 'bank_manifest_sha256': 'another bank'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'Judge bank differs'):
                prepare_study(Bank(), SPEC, [211], Harness(), WrongBank(), Learner(), root / 'study')
            self.assertFalse((root / 'study').exists())

    def test_missing_auditor_or_changed_factory_rejected_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root / 'judge.json'
            save(config, {'factory': 'test_worldlab_judge_adapter:UnauditableJudge', 'kwargs': {}})
            with self.assertRaisesRegex(ValueError, 'judge contract'): load_adapter(config, 'judge')
            with self.assertRaisesRegex(ValueError, 'audit_grade'):
                prepare_study(Bank(), SPEC, [211], Harness(), UnauditableJudge(), Learner(), root / 'missing')
            save(config, {'factory': 'test_worldlab_judge_adapter:Judge', 'kwargs': {}})
            judge = load_adapter(config, 'judge')
            prepare_study(Bank(), SPEC, [211], Harness(), judge, Learner(), root / 'study')
            config.write_text(config.read_text() + '\n')
            with self.assertRaises(ValueError):
                execute_study(Bank(), Harness(), load_adapter(config, 'judge'), Learner(), root / 'study')
            self.assertFalse((root / 'study/EXECUTION.json').exists())

    def test_malformed_scores_or_usage_never_become_learning_feedback(self):
        valid = {'grading_complete': True, 'quality_score': .5, 'success': False, 'feedback': 'review',
                 'usage': {'physical_model_calls': 2, 'charged_tokens': 40, 'accounting_complete': True}}
        for change in [{'quality_score': float('nan')}, {'quality_score': True}, {'quality_score': 1.1},
                       {'success': 1}, {'feedback': None}, {'grading_complete': 'yes'},
                       {'usage': {**valid['usage'], 'physical_model_calls': True}},
                       {'usage': {**valid['usage'], 'charged_tokens': 101}},
                       {'usage': {**valid['usage'], 'accounting_complete': False}}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_grade({**valid, **change}, token_limit=100, call_limit=3)

    def test_invalid_grade_does_not_finalize_an_attempt(self):
        class Invalid(Judge):
            def grade(self, *args, **kwargs):
                return {**super().grade(*args, **kwargs), 'quality_score': float('nan')}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'attempt'
            with self.assertRaisesRegex(ValueError, 'invalid score'):
                execute_task(Bank(), Harness(), Invalid(), task_id='train-0', employee_id='writer',
                             skill='seed', budget=Budget(), out=root)
            self.assertTrue((root / 'EXECUTION_RECEIPT.json').exists())
            self.assertFalse((root / 'ATTEMPT.json').exists())

    def test_unknown_harness_model_does_not_claim_independent_judging(self):
        class ModelJudge(Judge):
            def identity(self): return {**super().identity(), 'provider': {'model': 'fixture'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            prepare_study(Bank(), SPEC, [211], Harness(), ModelJudge(), Learner(), root)
            self.assertIsNone(read(root / 'STUDY.json')['analysis']['same_model_judge'])


if __name__ == '__main__': unittest.main()
