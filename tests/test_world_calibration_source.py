"""Source-bank isolation, lineage grouping, and byte-integrity regressions."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.source_world_calibration import assign_groups, child, save, sha, verify


class CalibrationSourceTests(unittest.TestCase):
    def test_transitive_family_and_template_links_stay_together(self):
        rows = [{'lineage_keys': ['family:de', 'template:x']},
                {'lineage_keys': ['family:en', 'template:x']},
                {'lineage_keys': ['family:en', 'template:y']},
                {'lineage_keys': ['family:fr', 'template:y']}]
        assign_groups(rows)
        self.assertEqual(len({r['calibration_group'] for r in rows}), 1)
        self.assertEqual(len({r['partition'] for r in rows}), 1)
        reversed_rows = list(reversed([{'lineage_keys': r['lineage_keys']} for r in rows]))
        assign_groups(reversed_rows)
        self.assertEqual({r['calibration_group'] for r in rows}, {r['calibration_group'] for r in reversed_rows})

    def test_parent_and_symlink_paths_cannot_leave_bank(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'bank'; root.mkdir()
            (root / 'escape').symlink_to(root.parent, target_is_directory=True)
            for value in ('../private.json', '/tmp/private.json', 'escape/private.json'):
                with self.assertRaises(ValueError):
                    child(root, value)

    def test_tampering_and_private_fields_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / 'public/fixture/task.json'
            save(task, {'id': 'fixture', 'instruction': 'Create a file.'})
            rows = [{'id': 'fixture', 'source': 'fixture', 'lineage_keys': ['family:a'],
                     'partition': 'calibration_train', 'public_directory': 'public/fixture'}]
            (root / 'TASKS.jsonl').write_text(json.dumps(rows[0]) + '\n')
            def seal():
                save(root / 'FILES.json', {str(p.relative_to(root)): {'sha256': sha(p), 'bytes': p.stat().st_size}
                     for p in (task, root / 'TASKS.jsonl')})
                save(root / 'MANIFEST.json', {'files_sha256': sha(root / 'FILES.json'),
                     'catalog_sha256': sha(root / 'TASKS.jsonl'), 'source_counts': {'fixture': 1},
                     'source_partition_counts': {'fixture/calibration_train': 1}})
            seal()
            self.assertTrue(verify(root)['ok'])
            save(task, {'id': 'fixture', 'instruction': 'Modified task.'})
            with self.assertRaisesRegex(ValueError, 'Bank file changed'):
                verify(root)
            save(task, {'id': 'fixture', 'checks': [{'expected': 'private answer'}]})
            seal()
            with self.assertRaisesRegex(ValueError, 'Private evaluator fields'):
                verify(root)
