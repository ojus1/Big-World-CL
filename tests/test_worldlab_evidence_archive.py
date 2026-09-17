import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile
import stat
import warnings
from unittest.mock import patch

from scripts.source_world_calibration import sha
from worldlab.qualitative import FrozenRubricJudge, workspace_evidence
from test_worldlab_judge_recovery import Bank, Client, response


class Tests(unittest.TestCase):
    def test_zip_duplicate_is_complete_and_changed_linked_or_new_evidence_is_rejected(self):
        root, workspace = self.workspace()
        path = workspace / 'output/bundle.zip'
        data = (workspace / 'output/result.md').read_bytes()
        def create(entries):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, content, mode in entries:
                        info = zipfile.ZipInfo(name); info.create_system = 3
                        info.external_attr = mode << 16
                        archive.writestr(info, content)
        create([('result.md', data, stat.S_IFREG | 0o644)])
        files = workspace_evidence(workspace)
        self.assertEqual(json.loads(files['output/bundle.zip']['text'])['members'][0]['sha256'], sha(workspace / 'output/result.md'))
        bank = Bank(root / 'bank')
        judge = FrozenRubricJudge(bank, 'fixture', Client.base_url, client_factory=lambda: Client([response(False)]))
        baseline = {'source.md': sha(workspace / 'source.md')}
        grade = judge.grade('fixture', workspace, baseline, root / 'judging')
        judge.audit_grade(bank, 'fixture', workspace, baseline, root / 'judging', grade)
        variants = [[('result.md', data.replace(b'Result', b'Faulte'), stat.S_IFREG)],
                    [('new.md', data, stat.S_IFREG)], [('result.md', data, stat.S_IFLNK)],
                    [('../source.md', data, stat.S_IFREG)], [('/outside.md', data, stat.S_IFREG)],
                    [('result.md', data, stat.S_IFREG)] * 2]
        for entries in variants:
            create(entries)
            with self.assertRaises(ValueError): workspace_evidence(workspace)
        create([('result.md', b'x', stat.S_IFREG)])
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('Must check size before decompressing')):
            with self.assertRaisesRegex(ValueError, 'size differs'): workspace_evidence(workspace)

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

    def test_empty_extensionless_file_is_visible_and_grade_remains_auditable(self):
        root, workspace = self.workspace()
        empty = workspace / 'f'
        empty.write_bytes(b'')
        files = workspace_evidence(workspace)
        self.assertEqual(files['f'], {'text': '', 'sha256': sha(empty)})
        bank = Bank(root / 'bank')
        judge = FrozenRubricJudge(bank, 'fixture', Client.base_url,
                                 client_factory=lambda: Client([response(False)]))
        baseline = {'source.md': sha(workspace / 'source.md')}
        grade = judge.grade('fixture', workspace, baseline, root / 'judge')
        self.assertTrue(grade['grading_complete'])
        self.assertFalse(grade['success'])
        judge.audit_grade(bank, 'fixture', workspace, baseline, root / 'judge', grade)
        # Empty files are evidence, not excluded metadata: changing one invalidates
        # the original grade instead of silently keeping its result.
        empty.write_bytes(b'\x00\xff')
        with self.assertRaises(ValueError):
            judge.audit_grade(bank, 'fixture', workspace, baseline, root / 'judge', grade)

    def test_empty_file_names_do_not_qualify_nonempty_binary_payloads(self):
        _, workspace = self.workspace()
        for name in ['f', 'output/empty.pdf', 'output/empty.tar.gz']:
            with self.subTest(name=name):
                path = workspace / name
                path.write_bytes(b'')
                self.assertEqual(workspace_evidence(workspace)[name]['text'], '')
                path.write_bytes(b'\x00\xff')
                with self.assertRaises(ValueError): workspace_evidence(workspace)
                path.unlink()


if __name__ == '__main__': unittest.main()
