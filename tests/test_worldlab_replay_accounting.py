"""Keep unknown provider usage unknown across the replay callback boundary."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from lifespan.evaluation.skillopt import _Ledger, LearningBudget, ReplayFailure
from worldlab.experience_update import update_employee


class Tests(unittest.TestCase):
    def test_declared_judging_allocation_is_reserved_inside_the_replay_call_budget(self):
        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
            'lineage_group': 'family', 'task_id': 'source-task', 'grade': {'feedback': 'Observed feedback'},
            'work_budget': {'seconds': 900, 'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000}}]
        with tempfile.TemporaryDirectory() as tmp:
            for available, expected in [(40, 9), (12, 6)]:
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
                update_employee(SimpleNamespace(public=lambda _: {'instruction': 'Original task'}),
                    None, SimpleNamespace(max_tokens=400000, max_model_calls=9), Learner(), selected,
                    employee='employee', day=2, skill='seed', update_root=Path(tmp), executor=executor)
                self.assertEqual(captured['judge_calls'], expected)
                self.assertLessEqual(captured['judge_calls'] + captured['budget'].model_calls, available)

    def test_reserved_attempt_tokens_cannot_be_reported_as_measured_learning_usage(self):
        class Learner:
            def update(self, skill, experiences, replay, **kwargs):
                ledger = _Ledger(LearningBudget())
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
