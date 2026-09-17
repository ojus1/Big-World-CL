from pathlib import Path
import tempfile
import unittest

from scripts.source_world_calibration import save, read, sha
from worldlab.qualify_saved_judges import qualify
from worldlab.qualitative import FrozenRubricJudge
from test_worldlab_judge_recovery import Bank, Client, response
from worldlab.artifact_inventory import inventory, verify


class Tests(unittest.TestCase):
    def test_all_saved_contexts_include_missing_final_receipt_and_preserve_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);bank = Bank(root / 'bank')
            bank.rows = [{'id': 'fixture'}]
            study = root / 'study';save(study / 'STUDY.json', {'fixture': True})
            for index in range(2):
                original = study / f'worlds/seed-1/control/sessions/task-{index}'
                workspace = original / 'employee/workspace'
                (workspace / 'output').mkdir(parents=True)
                (workspace / 'source.md').write_text('Source fact.')
                (workspace / 'output/result.md').write_text('Result.')
                save(original / 'BASELINE.json', {'source.md': sha(workspace / 'source.md')})
                save(original / 'PUBLIC_REQUEST.json', {'workspace': str(workspace)})
                files = {str(p.relative_to(workspace)): {'text': p.read_text(), 'sha256': sha(p)}
                         for p in workspace.rglob('*') if p.is_file()}
                save(original / 'judging/EVIDENCE.json', {'instruction': 'Use the source.',
                     'files': files, 'frozen_clock': None})
                if index == 0:
                    save(original / 'ATTEMPT.json', {'task_id': 'fixture'})
                    save(original / 'judging/GRADE.json', {'grading_complete': False})
            before = {str(p): sha(p) for p in study.rglob('*') if p.is_file()}
            judge = FrozenRubricJudge(bank, 'fixture', Client.base_url,
                client_factory=lambda: Client([response(status='incomplete', text='{'), response(False, repair=True)]))
            report = qualify(bank, judge, study, root / 'new', concurrency=2)
            self.assertTrue(report['ok']);self.assertEqual(report['audited'], 2)
            self.assertEqual(report['recovery_attempts'], 2)
            self.assertEqual(report['calls'], 4);self.assertEqual(report['tokens'], 240)
            self.assertEqual(before, {str(p): sha(p) for p in study.rglob('*') if p.is_file()})
            slots = read(root / 'new/PLAN.json')['slots']
            self.assertEqual([s['original_grade_complete'] for s in slots], [False, None])

    def test_pregrade_failure_with_scratch_links_is_included_without_following_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bank = Bank(root / 'bank'); bank.rows = [{'id': 'fixture'}]
            study = root / 'study'; save(study / 'STUDY.json', {'fixture': True})
            original = study / 'worlds/seed-1/control/sessions/failed-before-grading'
            workspace = original / 'employee/workspace'
            (workspace / 'output').mkdir(parents=True)
            (workspace / 'scratch/venv').mkdir(parents=True)
            (workspace / 'source.md').write_text('Source fact.')
            (workspace / 'output/result.md').write_text('Result.')
            (root / 'external.md').write_text('Must not copy or grade through the link.')
            link = workspace / 'scratch/venv/python'; link.symlink_to(root / 'external.md')
            save(original / 'BASELINE.json', {'source.md': sha(workspace / 'source.md')})
            save(original / 'PUBLIC_REQUEST.json', {'workspace': str(workspace), 'instruction': 'Use the source.'})
            save(original / 'EXECUTION_RECEIPT.json', {'status': 'budget_exhausted', 'accounting_complete': True})
            save(study / 'worlds/seed-1/control/sessions/interrupted/PUBLIC_REQUEST.json', {'instruction': 'Use the source.'})
            before = inventory(study)
            judge = FrozenRubricJudge(bank, 'fixture', Client.base_url,
                                     client_factory=lambda: Client([response(False)]))
            out = root / 'qualification'; report = qualify(bank, judge, study, out, concurrency=2)
            self.assertTrue(report['ok']); self.assertEqual(report['audited'], 1)
            self.assertEqual(report['contexts_without_original_evidence'], 1)
            self.assertEqual(report['excluded_source_attempts'], 1)
            self.assertTrue((out / 'grade-0000/workspace/scratch/venv/python').is_symlink())
            self.assertEqual(set(read(out / 'grade-0000/EVIDENCE.json')['files']), {'source.md', 'output/result.md'})
            verify(study, *before)


if __name__ == '__main__': unittest.main()
