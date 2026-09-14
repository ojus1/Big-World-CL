"""Live service evidence, incomplete receipts and non-additive replay costs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/report_worldlab_progress.py'
spec = importlib.util.spec_from_file_location('report_worldlab_progress', SOURCE)
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class Tests(unittest.TestCase):
    def test_unknown_receipts_are_visible_in_totals(self):
        rows = [{'status': 'completed', 'model_calls': 4, 'tokens': 30,
                 'accounting_complete': True, 'grade': {'grading_complete': True}},
                {'status': 'infrastructure_ambiguous', 'model_calls': None, 'tokens': 100,
                 'accounting_complete': False, 'grade': None}]
        result = progress.attempt_totals(rows)
        self.assertEqual(result['known_physical_model_calls'], 4)
        self.assertEqual(result['attempts_with_unknown_call_count'], 1)
        self.assertEqual(result['charged_or_reserved_tokens'], 130)
        self.assertEqual(result['attempts_with_incomplete_accounting'], 1)
        self.assertEqual(result['fully_graded'], 1)

    def test_service_timeout_is_unavailable_and_never_terminal(self):
        with patch.object(progress.subprocess, 'run', side_effect=subprocess.TimeoutExpired('systemctl', 10)) as call:
            result = progress.service_state('example.service')
            self.assertEqual(result['observation'], 'unavailable')
            self.assertIn('show', call.call_args.args[0])
        for active, pid, expected in [('active', 123, 'main_process_present'), ('failed', 0, 'terminal')]:
            output = f'LoadState=loaded\nActiveState={active}\nMainPID={pid}\n'
            with patch.object(progress.subprocess, 'run', return_value=SimpleNamespace(stdout=output)), \
                 patch.object(progress.os, 'kill'):
                self.assertEqual(progress.service_state('example')['observation'], expected)

    def test_markers_do_not_prove_liveness_and_replay_costs_stay_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / 'STUDY.json', {'worlds': [{'seed': 17, 'schedule': [{'split': 'probe'}]}],
                                      'learner': {'name': 'learner'}})
            digest = hashlib.sha256((root / 'STUDY.json').read_bytes()).hexdigest()
            save(root / 'PREPARED.json', {'study_sha256': digest})
            arm = root / 'worlds/seed-17/learner'
            save(arm / 'INFLIGHT.json', {'kind': 'learning'})
            save(arm / 'learning/update/UPDATE.json', {'accepted': False, 'costs': {'tokens': 15, 'accounting_complete': True}})
            save(arm / 'learning/update/replay-000/ATTEMPT.json', {
                'status': 'completed', 'tokens': 10, 'model_calls': 2, 'accounting_complete': True})
            save(arm / 'sessions/pending/PUBLIC_REQUEST.json', {'id': 'pending'})
            (arm / 'STATE.json').write_text('{')  # A writer may be midway through a checkpoint.
            value = progress.snapshot(root)
            self.assertIsNone(value['service'])
            self.assertEqual(value['completed_arm_reports'], 0)
            self.assertEqual(len(value['read_errors']), 1)
            row = value['arms'][1]
            self.assertEqual(row['learning']['charged_or_reserved_tokens_including_replays'], 15)
            self.assertEqual(row['replay_finalized_attempts']['charged_or_reserved_tokens'], 10)
            self.assertEqual(row['attempts_without_final_receipt'], ['sessions/pending'])
            self.assertNotIn('total_tokens', value)
            self.assertIsNone(row['bootstrap_and_social_tokens'])
            self.assertEqual((arm / 'STATE.json').read_text(), '{')
            self.assertTrue((arm / 'INFLIGHT.json').exists())


if __name__ == '__main__':
    unittest.main()
