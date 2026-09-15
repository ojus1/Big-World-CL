from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts.report_worldlab_readiness import capture, describe
from scripts.source_world_calibration import read, save, sha
from worldlab.campaign import source_identity
from worldlab.validation_context import ISOLATED
from worldlab.worlds import compile_world
from test_worldlab_worlds import Bank, Harness, Judge, SPEC


class Tests(unittest.TestCase):
    def fixture(self, delay=1):
        bank = Bank()
        spec = {**deepcopy(SPEC), 'validation_context': ISOLATED, 'feedback_delay': delay}
        world = compile_world(bank, spec, 211, Harness(), Judge())
        train = [s for s in world['schedule'] if s['split'] == 'train'][:2]
        assert len({s['lineage_group'] for s in train}) == 2
        sessions = [{**s, 'status': 'completed', 'grade': {'grading_complete': True, 'quality_score': 0}}
                    for s in train]
        return bank, world, {'workplace': {'day': 2}, 'sessions': sessions, 'updates': []}

    def test_delayed_release_and_future_readiness_use_only_completed_work(self):
        bank, world, state = self.fixture(delay=5)
        row = describe(world, state, bank)[0]
        self.assertFalse(row['observed_now']['eligible'])
        self.assertEqual(row['observed_now']['released_training_lineages'], 0)
        self.assertTrue(row['at_next_update_from_existing_work']['eligible'])
        self.assertEqual(row['next_unrecorded_update_day'], 6)
        self.assertEqual(len(row['at_next_update_from_existing_work']['selected_training_ids']), 2)
        self.assertEqual(len(row['at_next_update_from_existing_work']['selected_validation_ids']), 2)
        state['sessions'].pop()
        self.assertFalse(describe(world, state, bank)[0]['at_next_update_from_existing_work']['eligible'])

    def test_repeated_lineage_does_not_create_eligibility_and_scores_do_not_select(self):
        bank, world, state = self.fixture()
        self.assertTrue(describe(world, state, bank)[0]['observed_now']['eligible'])
        before = describe(world, state, bank)
        for s in state['sessions']: s['grade']['quality_score'] = 1
        self.assertEqual(describe(world, state, bank), before)
        first, second = state['sessions']
        second.update(task_id=first['task_id'], lineage_group=first['lineage_group'])
        row = describe(world, state, bank)[0]
        self.assertFalse(row['observed_now']['eligible'])
        self.assertEqual(row['observed_now']['released_training_lineages'], 1)

    def test_incomplete_work_is_not_training_and_completed_update_is_not_pending(self):
        bank, world, state = self.fixture()
        state['sessions'][1]['status'] = 'grading_incomplete'
        self.assertFalse(describe(world, state, bank)[0]['observed_now']['eligible'])
        state['workplace']['day'] = 6
        state['updates'] = [{'employee_id': 'writer', 'day': 6, 'result': {'accepted': False}}]
        row = describe(world, state, bank)[0]
        self.assertIsNone(row['next_unrecorded_update_day'])
        self.assertEqual(row['recorded_updates'], 1)
        self.assertEqual(row['recorded_adoptions'], 0)

    def test_corrupt_partition_chronology_and_grade_are_rejected(self):
        for change in ('partition', 'future', 'feedback', 'grade', 'duplicate', 'order'):
            with self.subTest(change=change):
                bank, world, state = self.fixture()
                session = state['sessions'][0]
                if change == 'partition': session['split'] = 'probe'
                if change == 'future': session['day'] = 9
                if change == 'feedback': session['feedback_day'] = 0
                if change == 'grade': session['grade']['grading_complete'] = False
                if change == 'duplicate': state['sessions'].append(deepcopy(session))
                if change == 'order': state['sessions'].reverse()
                with self.assertRaises(ValueError): describe(world, state, bank)

    def test_capture_binds_source_state_and_receipts_without_modifying_study(self):
        bank, world, state = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'study', Path(tmp) / 'readiness'
            study = {'source_sha256': source_identity(), 'worlds': [world], 'learner': {'name': 'learner'}}
            save(root / 'STUDY.json', study)
            save(root / 'PREPARED.json', {'study_sha256': sha(root / 'STUDY.json')})
            arm = root / 'worlds/seed-211/learner'
            for s in state['sessions']:
                receipt = arm / 'sessions' / s['id'] / 'ATTEMPT.json'
                save(receipt, {k: s[k] for k in ('task_id', 'employee_id', 'status', 'grade')})
                s['attempt_sha256'] = sha(receipt)
            save(arm / 'STATE.json', state)
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = capture(root, bank, out)
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual(result['observed_learner_employee_instances'], 1)
            self.assertEqual(result['learner_employees_eligible_now'], 1)
            self.assertEqual(len(result['missing_states']), 1)
            self.assertEqual(sha(out / 'PLAN.json'), result['plan_sha256'])
            self.assertEqual((out / 'snapshots/worlds/seed-211/learner/STATE.json').read_bytes(),
                             (arm / 'STATE.json').read_bytes())
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            with self.assertRaises(FileExistsError): capture(root, bank, out)
            with self.assertRaisesRegex(ValueError, 'outside'): capture(root, bank, root / 'report')
            save(receipt, {})
            with self.assertRaisesRegex(ValueError, 'receipt changed'): capture(root, bank, Path(tmp) / 'tampered')
            study['source_sha256']['worldlab/worlds.py'] = 'wrong'
            save(root / 'STUDY.json', study)
            save(root / 'PREPARED.json', {'study_sha256': sha(root / 'STUDY.json')})
            with self.assertRaisesRegex(ValueError, 'frozen study execution sources'):
                capture(root, bank, Path(tmp) / 'wrong-source')


if __name__ == '__main__': unittest.main()
