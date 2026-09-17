from pathlib import Path
from contextlib import redirect_stderr
import io
import tempfile
import unittest
from scripts.source_world_calibration import save, sha
from worldlab.qualify_learning import historical_request, parse_args


class Tests(unittest.TestCase):
    def test_target_harness_choice_is_explicit_and_source_is_independent(self):
        base = ['--bank', '/bank', '--source-study', '/historical-hermes', '--out', '/fresh',
                '--skillopt-root', '/skillopt', '--employee', 'employee', '--day', '6']
        for flag in ('--hermes-root', '--harness-config'):
            args = parse_args(base + [flag, '/target'])
            self.assertEqual(args.source_study, Path('/historical-hermes'))
            self.assertEqual(getattr(args, flag[2:].replace('-', '_')), Path('/target'))
        for extra in ([], ['--hermes-root', '/hermes', '--harness-config', '/fluso.json']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                parse_args(base + extra)
            self.assertEqual(caught.exception.code, 2)

    def test_old_and_normalized_native_request_receipts_are_explicitly_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version, filename in [(1, 'REQUEST.json'), (2, 'PUBLIC_REQUEST.json'), (3, 'PUBLIC_REQUEST.json'), (4, 'PUBLIC_REQUEST.json'), (5, 'PUBLIC_REQUEST.json'), (6, 'PUBLIC_REQUEST.json')]:
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
                historical_request({'harness': {'name': 'native_hermes_task_package', 'version': 99}}, root, {})

    def test_nonstreaming_stale_and_request_windows_fit_whole_attempt_budget(self):
        from worldlab.hermes_worker import native_timeouts
        for whole, expected in [(1200, 600), (900, 600), (180, 180)]:
            self.assertEqual(native_timeouts({'seconds': whole}),
                             {'request_timeout_seconds': expected, 'stale_timeout_seconds': expected})


if __name__ == '__main__': unittest.main()
