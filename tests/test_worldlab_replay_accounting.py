"""Keep unknown provider usage unknown across the replay callback boundary."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from dataclasses import asdict
import hashlib
import unittest

from lifespan.evaluation.skillopt import _Ledger, LearningBudget, ReplayFailure, BudgetExhausted
from worldlab.experience_update import update_employee, audit_replay_admissions
from scripts.audit_learning_v2 import reconcile


class Tests(unittest.TestCase):
    def test_skill_validation_failure_settles_actual_usage_and_delivers_no_score(self):
        from test_worldlab_adapters import Bank, Harness, Judge
        from scripts.source_world_calibration import read
        class Invalid(Harness):
            def run(self, request, artifact_root):
                return {**super().run(request, artifact_root), 'skill_loaded': False}
        class Learner:
            def update(inner, skill, experiences, replay, **kwargs):
                ledger = _Ledger(LearningBudget(replay_seconds=1200))
                with self.assertRaises(ReplayFailure):
                    ledger.invoke('target', replay, {'task': {'id': 'observed'}, 'skill': skill,
                        'attempt_index': 0, 'sample_id': 0, 'phase': 'train'})
                return ledger.report()
        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': {'feedback': 'Observed feedback'},
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        with tempfile.TemporaryDirectory() as tmp:
            judge = Judge(); judge.max_tokens = 400000
            costs = update_employee(Bank(), Invalid(), judge, Learner(), selected, employee='employee',
                day=2, skill='seed', update_root=Path(tmp))
            self.assertEqual(judge.calls, 0)
            self.assertEqual(costs['tokens'], 20)
            self.assertEqual(costs['target_model_calls'], 1)
            self.assertTrue(costs['accounting_complete'])
            self.assertEqual(costs['operations'][0]['status'], 'execution_invalid')
            self.assertIsNone(read(Path(tmp) / 'replay-000/ATTEMPT.json')['grade'])

    def test_rejected_submission_reaches_learner_as_metered_zero_not_callback_failure(self):
        from worldlab.artifact_contract import rejected_grade
        grade = rejected_grade({'passed': False, 'input_changes': [], 'unauthorized_files': [],
            'evidence_violations': [{'path': 'output/', 'reason': 'No deliverable submitted'}]}, 'rubric', 'evidence')
        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': grade,
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        class Learner:
            def update(inner, skill, experiences, replay, **kwargs):
                self.assertEqual(experiences[0]['feedback'], grade['feedback'])
                ledger = _Ledger(LearningBudget(replay_seconds=1200))
                result = ledger.invoke('target', replay, {'task': {'id': 'observed'}, 'skill': skill,
                    'attempt_index': 0, 'sample_id': 0, 'phase': 'train'})
                return result, ledger.report()
        def executor(*args, **kwargs):
            return {'status': 'completed', 'grade': grade, 'trajectory': [], 'tokens': 12345,
                    'model_calls': 9, 'tool_calls': 14, 'seconds': 5, 'accounting_complete': True}
        with tempfile.TemporaryDirectory() as tmp:
            result, costs = update_employee(SimpleNamespace(public=lambda _: {'instruction': 'Original task'}),
                None, SimpleNamespace(max_tokens=400000), Learner(), selected, employee='employee',
                day=2, skill='seed', update_root=Path(tmp), executor=executor)
        self.assertEqual(result['hard'], 0.)
        self.assertEqual(result['soft'], 0.)
        self.assertEqual(result['feedback'], grade['feedback'])
        self.assertTrue(costs['accounting_complete'])
        self.assertEqual(costs['tokens'], 12345)
        self.assertEqual(costs['operations'][0]['status'], 'completed')

    def test_insufficient_replay_time_stops_without_native_calls_or_a_score(self):
        selected = [{'id': 'observed', 'split': 'val', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': {'feedback': 'Observed feedback'},
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        for seconds in (1, 271.2613402288407, 285.2769024595618, 300.99, 301, 900, 1199.99):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as tmp:
                budget = LearningBudget(max_seconds=3600, replay_seconds=seconds)
                class Learner:
                    def update(inner, skill, experiences, replay, **kwargs):
                        ledger = _Ledger(budget)
                        with self.assertRaises(BudgetExhausted):
                            ledger.invoke('target', replay, {'task': {'id': 'observed'}, 'skill': skill,
                                'attempt_index': 0, 'sample_id': 0, 'phase': 'baseline_val'})
                        return ledger.report()
                def forbidden(*args, **kwargs): raise AssertionError('Must not stage or start a native attempt')
                costs = update_employee(SimpleNamespace(public=lambda _: {'instruction': 'Original task'}),
                    None, SimpleNamespace(max_tokens=400000), Learner(), selected, employee='employee',
                    day=2, skill='seed', update_root=Path(tmp), executor=forbidden)
                self.assertEqual(costs['tokens'], 0)
                self.assertEqual(costs['target_model_calls'], 0)
                self.assertTrue(costs['accounting_complete'])
                digest = hashlib.sha256(b'seed').hexdigest()
                update = {'learning_evidence_version': 2, 'status': 'budget_exhausted', 'accepted': False,
                    'skill': 'seed', 'skill_before_sha256': digest, 'skill_after_sha256': digest,
                    'configuration': {'budget': asdict(budget)}, 'costs': costs,
                    'gate_evidence': {'accepted': False, 'gate_action': 'reject_incomplete'},
                    'train_ids': [], 'validation_ids': ['observed'], 'replay_evidence': [], 'optimizer_inputs': [],
                    'unscored_replay_evidence': [{'id': 'observed', 'phase': 'baseline_val', 'sample_id': 0,
                        'attempt_index': 0, 'skill_sha256': digest, 'score_consumed': False,
                        'reason': 'not_delivered_to_upstream'}]}
                reconcile(update)
                audit_replay_admissions(Path(tmp), update, selected)
                costs['operations'][0]['admission']['minimum'] = 999
                with self.assertRaises(ValueError): audit_replay_admissions(Path(tmp), update, selected)

    def test_declared_judging_allocation_is_reserved_inside_the_replay_call_budget(self):
        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': {'feedback': 'Observed feedback'},
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        with tempfile.TemporaryDirectory() as tmp:
            for available, expected, dynamic in [(40, 9, False), (12, 6, False), (40, 11, True), (12, 6, True)]:
                captured = {}
                class Learner:
                    def update(self, skill, experiences, replay, **kwargs):
                        return replay({'task': {'id': 'observed'}, 'skill': skill, 'attempt_index': 0},
                            {'max_tokens': 1000000, 'max_model_calls': available, 'timeout_seconds': 1200})
                def executor(*args, **kwargs):
                    captured.update(kwargs)
                    return {'status': 'completed', 'grade': {'success': False, 'quality_score': 0.,
                            'grading_complete': True, 'feedback': 'Observed failure'}, 'trajectory': [],
                        'tokens': 10, 'model_calls': 1, 'tool_calls': 0, 'seconds': 1, 'accounting_complete': True}
                judge=SimpleNamespace(max_tokens=400000,max_model_calls=13 if dynamic else 9)
                if dynamic:
                    def allocation(task_id):
                        self.assertEqual(task_id,'source-task');return 11
                    judge.max_model_calls_for=allocation
                update_employee(SimpleNamespace(public=lambda _: {'instruction': 'Original task'}),
                    None, judge, Learner(), selected,
                    employee='employee', day=2, skill='seed', update_root=Path(tmp), executor=executor)
                self.assertEqual(captured['judge_calls'], expected)
                self.assertLessEqual(captured['judge_calls'] + captured['budget'].model_calls, available)

    def test_reserved_attempt_tokens_cannot_be_reported_as_measured_learning_usage(self):
        class Learner:
            def update(self, skill, experiences, replay, **kwargs):
                ledger = _Ledger(LearningBudget(replay_seconds=1200))
                try:
                    ledger.invoke('target', replay, {'task': {'id': 'observed'},
                                  'skill': skill, 'attempt_index': 0})
                except ReplayFailure:
                    return ledger.report()
                raise AssertionError('A failed native attempt must stop consolidation')

        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': {'feedback': 'Observed feedback'},
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        with tempfile.TemporaryDirectory() as tmp:
            for complete in (True, False):
                def executor(*args, **kwargs):
                    return {'status': 'infrastructure_error', 'grade': None, 'trajectory': [],
                        'tokens': 12345, 'model_calls': 9, 'tool_calls': 14, 'seconds': 5,
                        'accounting_complete': complete}
                report = update_employee(SimpleNamespace(public=lambda _: {'instruction': 'Original task'}),
                    None, SimpleNamespace(max_tokens=400000), Learner(), selected, employee='employee',
                    day=2, skill='seed', update_root=Path(tmp), executor=executor)
                row = report['operations'][0]
                self.assertEqual(report['accounting_complete'], complete)
                self.assertEqual(report['target_model_calls'], 9)
                self.assertEqual(report['tokens'], 12345 if complete else row['limits']['max_tokens'])
                self.assertEqual(row['reported_usage']['tokens'], 12345 if complete else None)


if __name__ == '__main__': unittest.main()
