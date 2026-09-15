import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import sha
from worldlab.qualitative import FrozenRubricJudge, workspace_evidence
from test_worldlab_judge_recovery import Bank, Client, response


class Tests(unittest.TestCase):
    def workspace(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); workspace = root / 'workspace'
        (workspace / 'output').mkdir(parents=True)
        (workspace / 'source.md').write_text('Source fact.')
        (workspace / 'output/result.md').write_text('Result with café.')
        return root, workspace

    def archive(self, workspace, entries):
        path = workspace / 'output/bundle.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for name, content, kind in entries:
                info = tarfile.TarInfo(name); info.type = kind
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = 'result.md'; tar.addfile(info)
                else:
                    info.size = len(content); tar.addfile(info, io.BytesIO(content))
        return path

    def test_archive_is_a_verified_view_of_existing_bytes_and_remains_auditable(self):
        root, workspace = self.workspace()
        data = (workspace / 'output/result.md').read_bytes()
        archive = self.archive(workspace, [('result.md', data, tarfile.REGTYPE)])
        files = workspace_evidence(workspace)
        projection = files['output/bundle.tar.gz']
        self.assertEqual(projection['sha256'], sha(archive))
        descriptor = json.loads(projection['text'])
        self.assertEqual(descriptor['representation'], 'verified_duplicate_text_archive')
        self.assertEqual(descriptor['members'][0]['visible_path'], 'output/result.md')
        self.assertEqual(descriptor['members'][0]['sha256'], sha(workspace / 'output/result.md'))
        bank = Bank(root / 'bank')
        judge = FrozenRubricJudge(bank, 'fixture', Client.base_url,
                                 client_factory=lambda: Client([response(False)]))
        baseline = {'source.md': sha(workspace / 'source.md')}
        grade = judge.grade('fixture', workspace, baseline, root / 'judge')
        self.assertTrue(grade['grading_complete'])
        judge.audit_grade(bank, 'fixture', workspace, baseline, root / 'judge', grade)
        self.archive(workspace, [('result.md', b'Wrong contents!!', tarfile.REGTYPE)])
        with self.assertRaises(ValueError):
            judge.audit_grade(bank, 'fixture', workspace, baseline, root / 'judge', grade)

    def test_new_changed_duplicate_or_linked_members_are_not_silently_ignored(self):
        _, workspace = self.workspace(); data = (workspace / 'output/result.md').read_bytes()
        variants = [[('new.md', data, tarfile.REGTYPE)],
                    [('result.md', data.replace(b'Result', b'Faulte'), tarfile.REGTYPE)],
                    [('result.md', data, tarfile.SYMTYPE)],
                    [('result.md', data, tarfile.LNKTYPE)],
                    [('result.md', data, tarfile.REGTYPE), ('result.md', data, tarfile.REGTYPE)],
                    [('../source.md', b'Source fact.', tarfile.REGTYPE)],
                    [('/outside.md', data, tarfile.REGTYPE)]]
        for entries in variants:
            with self.subTest(entries=entries):
                self.archive(workspace, entries)
                with self.assertRaises(ValueError): workspace_evidence(workspace)
        self.assertFalse((workspace.parent / 'outside.md').exists())

    def test_declared_size_mismatch_is_rejected_before_reading_member_contents(self):
        _, workspace = self.workspace()
        header = tarfile.TarInfo('result.md'); header.size = 10**9
        (workspace / 'output/bundle.tar.gz').write_bytes(gzip.compress(header.tobuf()))
        with patch.object(tarfile.TarFile, 'extractfile', side_effect=AssertionError('Must not read payload')):
            with self.assertRaisesRegex(ValueError, 'size differs'): workspace_evidence(workspace)

    def test_truncated_archive_and_archive_only_evidence_are_rejected(self):
        _, workspace = self.workspace()
        path = self.archive(workspace, [('result.md', (workspace / 'output/result.md').read_bytes(), tarfile.REGTYPE)])
        (workspace / 'output/result.md').unlink()
        with self.assertRaisesRegex(ValueError, 'not already visible'): workspace_evidence(workspace)
        path.write_bytes(b'not gzip')
        with self.assertRaises(ValueError): workspace_evidence(workspace)


if __name__ == '__main__': unittest.main()
