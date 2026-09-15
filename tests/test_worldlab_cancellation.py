from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
import tempfile
import unittest
from scripts.source_world_calibration import read, save
from worldlab.cancellation import Cancellation, StudyCancelled
from worldlab.experience_update import dispatch_updates
from worldlab.worlds import prepare_study, execute_study
from worldlab.reacting import run_world
from test_worldlab_judge_adapter import Bank, Harness, Judge, ReplayLearner
from test_worldlab_worlds import SPEC
from test_worldlab_reacting import Factory, Driver


class FailedLearner:
    def update(self, skill, experiences, replay, *, artifact_root, **kwargs):
        result = {'status': 'failed', 'accepted': False, 'skill': skill}
        save(artifact_root / 'UPDATE.json', result)
        return result


class FailedHarness(Harness):
    def run(self, request, artifact_root):
        save(artifact_root / 'ENTERED.json', {'entered': True})
        raise RuntimeError('Serial fixture failure')


class Tests(unittest.TestCase):
    def test_serial_study_records_first_failure_and_starts_no_second_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            bank, harness, judge, learner = Bank(), FailedHarness(), Judge(), ReplayLearner()
            prepare_study(bank, SPEC, [211, 223], harness, judge, learner, root)
            with self.assertRaisesRegex(RuntimeError, 'Serial fixture failure'):
                execute_study(bank, harness, judge, learner, root)
            self.assertTrue(read(root / 'STATUS.json')['stop_requested'])
            self.assertEqual(read(root / 'STOP_REQUESTED.json')['context']['world_seed'], 211)
            self.assertEqual(len(list(root.rglob('ENTERED.json'))), 1)
            self.assertFalse((root / 'worlds/seed-223').exists())
            self.assertFalse((root / 'REPORT.json').exists())

    def test_first_cause_is_atomic_and_ordinary_outcomes_do_not_stop_the_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Cancellation(Path(tmp))
            for status in ('completed', 'budget_exhausted'):
                future = Future(); future.set_result({'status': status, 'accepted': False, 'quality_score': 0.})
                stop.observe(future, ('completed', 'budget_exhausted'))
                stop.check()
            with ThreadPoolExecutor(max_workers=16) as pool:
                list(pool.map(lambda n: stop.at(world_seed=n).request('FixtureFailure'), range(32)))
            record = read(stop.path)
            self.assertIn(record['context']['world_seed'], range(32))
            self.assertEqual(record['error_type'], 'FixtureFailure')
            first = stop.path.read_bytes(); stop.request('LaterFailure')
            self.assertEqual(stop.path.read_bytes(), first)
            self.assertFalse(list(Path(tmp).glob('.stop-request-*')))
            with self.assertRaises(StudyCancelled): stop.check()

    def test_failed_epoch_does_not_start_queued_employee_epochs(self):
        selected = [{'id': 'observed', 'split': 'train', 'day': 0, 'feedback_day': 1,
                     'lineage_group': 'family', 'task_id': 'train-0', 'grade': {'feedback': 'Observed'},
                     'work_budget': {'model_calls': 32, 'output_tokens': 8192, 'total_tokens': 500000, 'seconds': 900}}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); stop = Cancellation(root)
            recorded, waves = [], []
            with self.assertRaisesRegex(RuntimeError, 'Learning failed'):
                dispatch_updates(Bank(), Harness(), Judge(), FailedLearner(),
                    [(name, selected) for name in ('a','b','c')], day=2,
                    skills={name:'seed' for name in ('a','b','c')}, out=root,
                    record=lambda employee,result:recorded.append(employee), journal=waves.append,
                    max_parallel=1, cancellation=stop)
            self.assertEqual(recorded, ['a'])
            self.assertEqual(waves, [['a']])
            self.assertEqual(len(list(root.rglob('UPDATE.json'))), 1)
            self.assertTrue(stop.path.is_file())

    def test_reacting_employee_state_is_preserved_and_driver_closes_on_peer_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'; stop = Cancellation(root)
            class StoppingDriver(Driver):
                def decide(self, view, key, validate):
                    decision = super().decide(view, key, validate)
                    stop.request('PeerFixtureFailure')
                    return decision
            class StoppingFactory(Factory):
                def open(self, world, context, out):
                    driver = StoppingDriver(); self.drivers.append(driver); return driver
            bank, harness, judge, learner = Bank(), Harness(), Judge(), ReplayLearner()
            factory = StoppingFactory()
            prepare_study(bank, SPEC, [211], harness, judge, learner, root, factory)
            world = read(root / 'STUDY.json')['worlds'][0]
            arm = root / 'worlds/seed-211/fixture'
            with self.assertRaises(StudyCancelled):
                run_world(bank, world, harness, judge, learner, arm, factory, cancellation=stop)
            self.assertTrue(factory.drivers[0].closed)
            self.assertEqual(len(read(arm / 'STATE.json')['decisions']), 1)
            self.assertFalse(list(arm.rglob('ATTEMPT.json')))

    def test_unknown_failure_policy_is_rejected_before_native_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'failure policy'):
                prepare_study(Bank(), {**SPEC,'failure_policy':'retry_for_success'}, [211],
                              Harness(), Judge(), ReplayLearner(), Path(tmp)/'study')


if __name__ == '__main__': unittest.main()
