"""Real spawned processes, complete saved-work audits, and failed-pair retention."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import time
import unittest

from scripts.source_world_calibration import read, save
from test_worldlab_judge_adapter import Bank, Harness, Judge, ReplayLearner
from test_worldlab_worlds import SPEC
from worldlab.adapters import load_adapter
from worldlab.audit_worlds import audit
from worldlab.worlds import prepare_study, execute_study


def wait_for(paths, count):
    deadline = time.monotonic() + 10
    while len(list(paths())) < count:
        if time.monotonic() >= deadline:
            raise RuntimeError('Independent fixture processes never overlapped')
        time.sleep(.01)


class ParallelHarness(Harness):
    def __init__(self, fail_seed=None): self.fail_seed = fail_seed
    def identity(self): return {'name': 'parallel_fixture_harness', 'fail_seed': self.fail_seed}

    def run(self, request, artifact_root):
        if artifact_root.parent.name == 'sessions':
            world = artifact_root.parents[2]
            study = artifact_root.parents[4]
            save(study / (world.name + '-worker.json'), {'pid': os.getpid()})
            wait_for(lambda: study.glob('seed-*-worker.json'), 2)
            if world.name == 'seed-' + str(self.fail_seed):
                raise RuntimeError('Planned fixture failure')
        return super().run(request, artifact_root)


class ParallelLearner(ReplayLearner):
    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        save(artifact_root / 'READY.json', {'pid': os.getpid()})
        wait_for(lambda: artifact_root.parent.glob('*/READY.json'), 2)
        result = super().update(skill, experiences, replay, current_day=current_day, artifact_root=artifact_root)
        result['worker_pid'] = os.getpid()
        save(artifact_root / 'UPDATE.json', result)
        return result


class StopHarness(ParallelHarness):
    def run(self, request, artifact_root):
        world, study = artifact_root.parents[2], artifact_root.parents[4]
        save(study / (world.name + '-worker.json'), {'pid': os.getpid()})
        save(artifact_root / 'ENTERED.json', {'pid': os.getpid()})
        if world.name == 'seed-211':
            wait_for(lambda: study.glob('worlds/seed-223/*/sessions/*/ENTERED.json'), 2)
            raise RuntimeError('Planned fixture failure')
        wait_for(lambda: study.glob('STOP_REQUESTED.json'), 1)
        return Harness.run(self, request, artifact_root)


class Tests(unittest.TestCase):
    def spec(self):
        spec = deepcopy(SPEC)
        spec.update(max_parallel_worlds=64, max_parallel_employees=64,
                    max_parallel_updates=64, validation_context='isolated_public_tasks_v1')
        spec['employees'].append({'id': 'colleague', 'role': 'Editor', 'language': 'en'})
        return spec

    def test_two_parallel_pairs_and_employee_epochs_pass_full_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'study'
            config = root / 'judge.json'
            save(config, {'factory': 'test_worldlab_judge_adapter:Judge', 'kwargs': {}})
            judge = load_adapter(config, 'judge')
            bank, harness, learner = Bank(), ParallelHarness(), ParallelLearner()
            prepare_study(bank, self.spec(), [211, 223], harness, judge, learner, out)
            report = execute_study(bank, harness, judge, learner, out)
            self.assertEqual(report['status'], 'completed')
            checked = audit(bank, out, harness, learner, judge)
            self.assertEqual(checked['world_pairs'], 2)
            self.assertEqual(checked['online_attempts'], 80)
            self.assertEqual(checked['learning_replays'], 4)
            self.assertEqual(len({read(p)['pid'] for p in out.glob('seed-*-worker.json')}), 2)
            for world in (out / 'worlds').iterdir():
                updates = list((world / learner.identity()['name'] / 'learning').glob('*/UPDATE.json'))
                self.assertEqual(len(updates), 2)
                self.assertEqual(len({read(p)['worker_pid'] for p in updates}), 2)

    def test_failed_pair_is_retained_and_successful_peer_is_joined(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'
            bank, harness, learner, judge = Bank(), ParallelHarness(fail_seed=211), ParallelLearner(), Judge()
            spec = self.spec(); spec['failure_policy'] = 'drain_all_pairs'
            prepare_study(bank, spec, [211, 223], harness, judge, learner, out)
            with self.assertRaisesRegex(RuntimeError, 'failed pairs'):
                execute_study(bank, harness, judge, learner, out)
            status = read(out / 'STATUS.json')
            self.assertEqual(status['status'], 'incomplete')
            self.assertEqual(status['completed_arms'], 2)
            self.assertEqual(status['planned_arms'], 4)
            self.assertEqual([f['failed_world'] for f in status['failures']], [211])
            self.assertFalse((out / 'REPORT.json').exists())
            with self.assertRaises(FileExistsError):
                execute_study(bank, harness, judge, learner, out)

    def test_first_failed_pair_stops_new_waves_and_preserves_inflight_peer_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'
            bank, harness, learner, judge = Bank(), StopHarness(), ParallelLearner(), Judge()
            prepare_study(bank, self.spec(), [211, 223], harness, judge, learner, out)
            with self.assertRaisesRegex(RuntimeError, 'failed pairs'):
                execute_study(bank, harness, judge, learner, out)
            status = read(out / 'STATUS.json'); stop = read(out / 'STOP_REQUESTED.json')
            self.assertTrue(status['stop_requested'])
            self.assertEqual(status['failure_policy'], 'stop_after_current_wave')
            self.assertEqual(stop['context']['world_seed'], 211)
            self.assertEqual(stop['context']['stage'], 'work_wave')
            self.assertEqual(stop['error_type'], 'RuntimeError')
            self.assertEqual({r['status'] for r in status['failures']}, {'incomplete', 'cancelled'})
            peer = out / 'worlds/seed-223' / learner.identity()['name']
            state = read(peer / 'STATE.json')
            self.assertEqual(len(state['sessions']), 2)
            self.assertTrue(all(r['status'] == 'completed' for r in state['sessions']))
            self.assertEqual(len(list(out.rglob('ATTEMPT.json'))), 2)
            self.assertFalse((out / 'REPORT.json').exists())
            self.assertFalse((out / 'worlds/seed-223/no_learning').exists())
            status = read(out / 'STATUS.json')
            self.assertEqual(status['status'], 'incomplete')
            self.assertEqual(status['completed_arms'], 0)
            self.assertEqual(status['planned_arms'], 4)
            self.assertFalse((out / 'REPORT.json').exists())
            with self.assertRaises(FileExistsError):
                execute_study(bank, harness, judge, learner, out)


if __name__ == '__main__':
    unittest.main()
