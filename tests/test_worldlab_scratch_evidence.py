from pathlib import Path
import tempfile
import unittest

from scripts.source_world_calibration import read, sha
from worldlab.artifact_inventory import inventory, verify
from worldlab.qualitative import FrozenRubricJudge, workspace_evidence
from test_worldlab_judge_recovery import Bank, Client, response


class Tests(unittest.TestCase):
    def workspace(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); workspace = root / 'workspace'
        (workspace / 'output').mkdir(parents=True)
        (workspace / 'source.md').write_text('Source fact.')
        (workspace / 'output/result.md').write_text('Result.')
        (root / 'outside.md').write_text('Outside data must not be graded or copied through a link.')
        return root, workspace

    def test_ignored_venv_links_binary_and_recursive_tree_are_never_graded(self):
        root, workspace = self.workspace()
        venv = workspace / 'scratch/venv'; (venv / 'bin').mkdir(parents=True)
        (venv / 'bin/python').symlink_to('/usr/bin/python3')
        (venv / 'lib64').symlink_to('lib')
        (venv / 'loop').symlink_to(venv, target_is_directory=True)
        (venv / 'outside.md').symlink_to(root / 'outside.md')
        (venv / 'vendor.so').write_bytes(b'\x00\xff\x00')
        evidence = workspace_evidence(workspace)
        self.assertEqual(set(evidence), {'source.md', 'output/result.md'})
        bank = Bank(root / 'bank')
        judge = FrozenRubricJudge(bank, 'fixture', Client.base_url,
                                 client_factory=lambda: Client([response(False)]))
        out = root / 'judging'; baseline = {'source.md': sha(workspace / 'source.md')}
        grade = judge.grade('fixture', workspace, baseline, out)
        self.assertTrue(grade['grading_complete'])
        self.assertEqual(grade['usage']['physical_model_calls'], 1)
        self.assertEqual(read(out / 'EVIDENCE.json')['files'], evidence)
        judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)
        (workspace / 'output/leak.md').symlink_to(root / 'outside.md')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)

    def test_root_scratch_link_is_excluded_but_input_or_output_links_are_rejected(self):
        root, workspace = self.workspace()
        (workspace / 'scratch').symlink_to(root, target_is_directory=True)
        self.assertEqual(set(workspace_evidence(workspace)), {'source.md', 'output/result.md'})
        for name in ('input', 'output/link.md', 'other/dangling.md'):
            path = workspace / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(root / 'absent.md')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                workspace_evidence(workspace)
            path.unlink()

    def test_regular_binary_outside_scratch_remains_unqualified(self):
        _, workspace = self.workspace()
        (workspace / 'output/result.png').write_bytes(b'\x89PNG')
        with self.assertRaisesRegex(ValueError, 'Unqualified binary'):
            workspace_evidence(workspace)

    def test_artifact_inventory_preserves_link_targets_without_following_them(self):
        root, workspace = self.workspace()
        (workspace / 'scratch').mkdir()
        link = workspace / 'scratch/outside.md'; link.symlink_to(root / 'outside.md')
        (workspace / 'scratch/recursive').symlink_to(workspace, target_is_directory=True)
        (workspace / 'scratch/missing').symlink_to('missing-target')
        files, links = inventory(workspace)
        self.assertEqual(set(files), {'source.md', 'output/result.md'})
        self.assertEqual(set(links), {'scratch/outside.md', 'scratch/recursive', 'scratch/missing'})
        self.assertEqual(links['scratch/outside.md'], str(root / 'outside.md'))
        verify(workspace, files, links)
        (root / 'outside.md').write_text('An external target changed; its bytes were never captured.')
        verify(workspace, files, links)
        link.unlink(); link.symlink_to('different-target')
        with self.assertRaisesRegex(ValueError, 'symlink targets changed'):
            verify(workspace, files, links)
        with self.assertRaises(ValueError):
            verify(workspace, files)


if __name__ == '__main__':
    unittest.main()
