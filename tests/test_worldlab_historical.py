from pathlib import Path
import tempfile
import unittest
from scripts.source_world_calibration import save, sha
from worldlab.qualify_learning import historical_request


class Tests(unittest.TestCase):
    def test_old_and_normalized_native_request_receipts_are_explicitly_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version, filename in [(1, 'REQUEST.json'), (2, 'PUBLIC_REQUEST.json')]:
                value = {'instruction': 'original brief', 'skill': 'seed'}
                save(root / filename, value)
                study = {'harness': {'name': 'native_hermes_task_package', 'version': version}}
                record = {'artifact_inventory': {filename: sha(root / filename)}}
                self.assertEqual(historical_request(study, root, record), value)
                save(root / filename, {**value, 'instruction': 'changed'})
                with self.assertRaises(ValueError): historical_request(study, root, record)

    def test_unknown_versions_do_not_silently_fall_back_to_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); save(root / 'REQUEST.json', {'instruction': 'legacy'})
            with self.assertRaises(ValueError):
                historical_request({'harness': {'name': 'native_hermes_task_package', 'version': 3}}, root, {})


if __name__ == '__main__': unittest.main()
