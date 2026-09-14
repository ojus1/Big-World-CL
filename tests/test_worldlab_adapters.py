import copy
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.source_world_calibration import read, save, sha
from worldlab.attempts import execute_task
from worldlab.contracts import Budget
from worldlab.dispatch import dispatch_day


class Bank:
    def public(self, task_id):
        return {'id': task_id, 'instruction': 'Write a sourced briefing.', 'language': 'en'}

    def stage(self, task_id, workspace):
        workspace.mkdir(parents=True)
        (workspace / 'input.md').write_text('Source evidence')
        return {'input.md': sha(workspace / 'input.md')}


class Harness:
    """Deliberately has none of the Hermes filenames or directories."""
    def unsupported(self, task): return []

    def run(self, request, artifact_root):
        (artifact_root / 'deployment.txt').write_text(request.skill)
        save(artifact_root / 'custom-log.json', {'input': request.instruction})
        return {'status': 'completed', 'physical_model_calls': 1, 'charged_tokens': 20,
                'accounting_complete': True, 'skill_loaded': True,
                'skill_content_sha256': hashlib.sha256(request.skill.encode()).hexdigest(),
                'skill_sha256': sha(artifact_root / 'deployment.txt'),
                'trajectory': [{'role': 'assistant', 'content': 'Done'}]}


class Judge:
    calls = 0
    def unsupported(self, task): return []

    def grade(self, *args, **kwargs):
        self.calls += 1
        return {'grading_complete': True, 'quality_score': 1., 'success': True,
                'usage': {'physical_model_calls': 2, 'charged_tokens': 40, 'accounting_complete': True}}


class Tests(unittest.TestCase):
    def test_alternate_harness_needs_no_hermes_paths_and_keeps_public_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'case'
            result = execute_task(Bank(), Harness(), Judge(), task_id='task', employee_id='writer',
                                  skill='Read evidence', budget=Budget(), out=root)
            self.assertEqual(result['tokens'], 60)
            self.assertEqual(result['model_calls'], 3)
            self.assertEqual(result['trajectory'], [{'role': 'assistant', 'content': 'Done'}])
            self.assertEqual(result['skill_sha256'], sha(root / 'deployment.txt'))
            self.assertFalse((root / 'NATIVE.json').exists())
            self.assertEqual(read(root / 'PUBLIC_REQUEST.json')['instruction'], 'Write a sourced briefing.')
            self.assertIn('EXECUTION_RECEIPT.json', result['artifact_inventory'])

    def test_invalid_accounting_or_wrong_skill_never_becomes_graded_feedback(self):
        for change in [{'charged_tokens': 500001}, {'accounting_complete': False},
                       {'skill_content_sha256': 'wrong'}, {'skill_loaded': False}, {'trajectory': None}]:
            class Invalid(Harness):
                def run(self, request, artifact_root):
                    return {**super().run(request, artifact_root), **change}
            with tempfile.TemporaryDirectory() as tmp:
                judge = Judge()
                with self.assertRaises(ValueError):
                    execute_task(Bank(), Invalid(), judge, task_id='task', employee_id='writer',
                                 skill='Read evidence', budget=Budget(), out=Path(tmp) / 'case')
                self.assertEqual(judge.calls, 0)
                self.assertTrue((Path(tmp) / 'case/EXECUTION_RECEIPT.json').exists())

    def test_parallel_employees_keep_order_and_bounded_concurrency(self):
        slots = [{'id': name, 'employee_id': name[0]} for name in ['a0', 'a1', 'b0', 'c0']]
        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        active, finished, recorded, journals = set(), set(), [], []
        peak = [0]
        def execute(slot):
            with lock:
                self.assertNotIn(slot['employee_id'], active)
                if slot['id'] == 'a1': self.assertIn('a0', finished)
                active.add(slot['employee_id']); peak[0] = max(peak[0], len(active))
            barrier.wait()
            with lock:
                active.remove(slot['employee_id']); finished.add(slot['id'])
            return {'status': 'completed'}
        dispatch_day(slots, execute, lambda slot, result: recorded.append(slot['id']),
                     lambda wave: journals.append(copy.deepcopy(wave)), max_parallel=2)
        self.assertEqual(peak[0], 2)
        self.assertEqual(recorded, ['a0', 'b0', 'a1', 'c0'])
        self.assertEqual(journals[-1], [])

    def test_failed_wave_records_started_peers_and_never_dispatches_more(self):
        slots = [{'id': name, 'employee_id': name[0]} for name in ['a0', 'b0', 'c0']]
        started, recorded, journals = [], [], []
        def execute(slot):
            started.append(slot['id'])
            if slot['id'] == 'a0': raise RuntimeError('provider transport failed')
            return {'status': 'completed'}
        with self.assertRaisesRegex(RuntimeError, 'transport failed'):
            dispatch_day(slots, execute, lambda slot, result: recorded.append(slot['id']),
                         lambda wave: journals.append(copy.deepcopy(wave)), max_parallel=2)
        self.assertEqual(set(started), {'a0', 'b0'})
        self.assertEqual(recorded, ['b0'])
        self.assertEqual([s['id'] for s in journals[-1]], ['a0', 'b0'])


if __name__ == '__main__': unittest.main()
