import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from worldlab.worlds import compile_world, eligible_experiences, prepare_study, execute_study, stable_hash
from worldlab.qualitative import validate_verdict
from worldlab.contracts import NoLearning
from scripts.source_world_calibration import save


class Bank:
    verification = {'manifest_sha256': 'bank'}
    def __init__(self):
        self.rows = [{'id': f'{split}-{i}', 'partition': 'calibration_' + split,
                      'calibration_group': f'{split}-{i}', 'source': 'internal_eurobench',
                      'workflow': 'draft_edit', 'title': 'Revise report', 'language': 'en'}
                     for split in ['train', 'validation', 'holdout'] for i in range(3)]
        self.by_id = {r['id']: r for r in self.rows}
    def public(self, ident):
        return {'id': ident, 'source': 'internal_eurobench', 'instruction': 'Revise report ' + ident,
                'language': 'en', 'input_formats': ['.md']}


class Harness:
    def identity(self): return {'name': 'fake-harness', 'provider': {'model': 'fixture'}}
    def unsupported(self, public): return []


class Judge:
    max_tokens = 1000
    def identity(self): return {'name': 'fake-judge', 'provider': {'model': 'fixture'}}
    def unsupported(self, public): return []


class Learning(NoLearning):
    def identity(self): return {'name': 'fixture-learning'}
    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        self.seen = experiences
        result = super().update(skill, experiences, replay, current_day=current_day, artifact_root=artifact_root)
        return {**result, 'skill': skill + '\nNew skill', 'accepted': True}


SPEC = {'schema_version': 1, 'study_scope': 'development', 'days': 10, 'probe_start_day': 8,
        'update_days': [6], 'feedback_delay': 1, 'train_cases': 2, 'val_cases': 2,
        'employees': [{'id': 'writer', 'role': 'Editor', 'language': 'en'}]}


class Tests(unittest.TestCase):
    def test_world_retains_uncalibrated_employee_and_freezes_split_schedule(self):
        bank = Bank()
        world = compile_world(bank, SPEC, 211, Harness(), Judge())
        self.assertEqual(world['workforce'][0]['calibration']['calibration_status'], 'uncalibrated_default')
        self.assertEqual(len(world['schedule']), 10)
        self.assertEqual(world, compile_world(bank, SPEC, 211, Harness(), Judge()))
        groups = {split: {s['lineage_group'] for s in world['schedule'] if s['split'] == split}
                  for split in ['train', 'val', 'probe']}
        self.assertFalse(groups['train'] & groups['val'])
        self.assertFalse(groups['train'] & groups['probe'])
        self.assertTrue(all(s['day'] >= 8 for s in world['schedule'] if s['split'] == 'probe'))
        self.assertEqual(len(groups['train']), 3)

    def test_selection_is_score_blind_delayed_and_lineage_distinct(self):
        world = compile_world(Bank(), SPEC, 211, Harness(), Judge())
        sessions = [{**s, 'status': 'completed', 'grade': {'quality_score': 0}} for s in world['schedule']]
        chosen = eligible_experiences(sessions, 'writer', 6, 2, 2)
        self.assertEqual(len(chosen), 4)
        self.assertTrue(all(s['feedback_day'] <= 6 and s['split'] != 'probe' for s in chosen))
        other = copy.deepcopy(sessions)
        for s in other: s['grade']['quality_score'] = 1
        self.assertEqual([s['id'] for s in chosen], [s['id'] for s in eligible_experiences(other, 'writer', 6, 2, 2)])
        self.assertEqual(eligible_experiences(sessions, 'writer', 1, 2, 2), [])

    def test_final_claim_and_late_update_rejected(self):
        for change in [{'study_scope': 'final'}, {'update_days': [8]}]:
            with self.assertRaises(ValueError): compile_world(Bank(), {**SPEC, **change}, 211, Harness(), Judge())

    def test_world_applies_learning_only_to_later_work_and_control_keeps_seed(self):
        observed = []
        def attempt(bank, harness, judge, **kw):
            observed.append((str(kw['out']), kw['skill']))
            result = {'status': 'completed', 'tokens': 10, 'model_calls': 1,
                      'grade': {'grading_complete': True, 'quality_score': .5, 'success': False, 'feedback': 'feedback'}}
            save(Path(kw['out']) / 'ATTEMPT.json', result)
            return result
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'; learner = Learning()
            prepare_study(Bank(), SPEC, [211], Harness(), Judge(), learner, out)
            with patch('worldlab.worlds.execute_task', side_effect=attempt):
                report = execute_study(Bank(), Harness(), Judge(), learner, out)
            self.assertEqual(report['mean_probe_quality_delta'], 0)
            self.assertEqual(len(observed), 20)
            for path, skill in observed:
                changed = 'New skill' in skill
                if 'no_learning' in path: self.assertFalse(changed)
                elif '/d007-' in path or '/d008-' in path or '/d009-' in path: self.assertTrue(changed)
                else: self.assertFalse(changed)
            self.assertTrue(all(x['split'] in ['train', 'val'] for x in learner.seen))
            with self.assertRaises(FileExistsError): execute_study(Bank(), Harness(), Judge(), learner, out)

    def test_incomplete_attempt_preserves_failure_and_does_not_execute_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'
            prepare_study(Bank(), SPEC, [211], Harness(), Judge(), Learning(), out)
            with patch('worldlab.worlds.execute_task', side_effect=RuntimeError('provider failed')) as run:
                with self.assertRaises(RuntimeError): execute_study(Bank(), Harness(), Judge(), Learning(), out)
            self.assertEqual(run.call_count, 1)
            status = json.loads((out / 'STATUS.json').read_text())
            self.assertEqual(status['status'], 'incomplete')
            self.assertTrue(list(out.rglob('INFLIGHT.json')))

    def test_grader_refuses_boolean_strings_and_missing_evidence(self):
        for result in [{'criterion_id': 'c', 'passed': 'true', 'reasoning': 'yes', 'evidence': 'a'},
                       {'criterion_id': 'c', 'passed': True, 'reasoning': 'yes', 'evidence': ''}]:
            with self.assertRaises(ValueError): validate_verdict(result, {'id': 'c'})
        self.assertTrue(validate_verdict({'criterion_id': 'c', 'passed': True,
                         'reasoning': 'supported', 'evidence': 'output/a.md'}, {'id': 'c'})['passed'])


if __name__ == '__main__': unittest.main()
