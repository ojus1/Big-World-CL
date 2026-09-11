"""Real pinned SkillOpt parsing with mocked provider I/O; no network calls."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation import provider
from scripts import preflight_optimizer as p


CREDS = {'model': 'Qwen/Qwen3.8-27B-FP8', 'base_url': 'https://example.invalid/v1',
         'provider_profile': provider.PROFILE, 'api_key': 'offline-fixture-value'}


def response(text='[]'):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': text}]}],
        'usage': {'input_tokens': 130, 'output_tokens': 50, 'total_tokens': 180}}


class OptimizerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())) / 'run'
        self.stack.enter_context(patch.object(p, 'sources', return_value={'fixture.py': 'a' * 64}))
        self.stack.enter_context(patch.object(p, 'dependency_provenance', return_value={'fixture': 'b' * 40}))
        self.stack.enter_context(patch.object(p, 'committed_sources', return_value=True))
        self.stack.enter_context(patch.object(p, 'credentials', return_value=deepcopy(CREDS)))
        self.calls = []; self.result = response(); self.error = None
        def send(request, *, timeout, api_mode):
            self.calls.append(deepcopy(request))
            self.assertEqual(api_mode, 'responses')
            self.assertGreater(timeout, 0); self.assertLessEqual(timeout, p.LIMITS['timeout_seconds'])
            if self.error:
                raise self.error
            return deepcopy(self.result)
        self.stack.enter_context(patch.object(p.optimizer, '_sdk_transport', return_value=send))
        p.prepare(self.root, model=CREDS['model'], base_url=CREDS['base_url'])
        self.manifest_sha = p.sha(self.root / 'manifest.json')

    def execute(self):
        return p.execute(self.root, manifest_sha256=self.manifest_sha)

    def audit(self):
        return p.audit_preflight(self.root, manifest_sha256=self.manifest_sha)

    def refresh_inventory(self):
        p.save(self.root / 'EVIDENCE.json', p.inventory(self.root))

    def test_empty_array_is_valid_without_learning_claim(self):
        report = self.execute()
        self.assertTrue(report['ok']); self.assertEqual(report, self.audit())
        self.assertEqual(report['tokens'], 180)
        self.assertEqual(report['physical_model_calls'], 1)
        self.assertEqual(report['parsed_edit_count'], 0)
        self.assertIs(report['native_learning_or_adoption'], False)
        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0]['stream'], False)
        self.assertEqual(self.calls[0]['extra_body'], {'chat_template_kwargs': {'enable_thinking': False}})
        self.assertNotIn(CREDS['api_key'], (self.root / 'request.json').read_text())

    def test_valid_edit_uses_actual_upstream_parser(self):
        self.result = response('[{"op":"add","content":"Sum signed refunds."}]')
        report = self.execute(); self.assertTrue(report['ok'])
        self.assertEqual(report['parsed_edit_count'], 1)
        self.assertEqual(p.read(self.root / 'parsed_edits.json')[0],
            {'target': 'skill', 'op': 'add', 'content': 'Sum signed refunds.', 'anchor': '', 'rationale': ''})
        self.assertEqual(report, self.audit())

    def test_invalid_nonempty_array_cannot_become_valid_empty_array(self):
        for text in ('[{"op":"unknown","content":"x"}]', '[{"op":"add","content":""}]',
                     '[{"op":"add","content":12}]', '["wrong"]', '{}'):
            with self.subTest(text=text):
                self.result = response(text)
                # Each synthetic execution has its own prepared one-shot directory.
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / 'case'
                    p.prepare(root, model=CREDS['model'], base_url=CREDS['base_url'])
                    report = p.execute(root, manifest_sha256=p.sha(root / 'manifest.json'))
                    self.assertFalse(report['ok'])
                    self.assertEqual(report['physical_requests_attempted'], 1)

    def test_exclusive_marker_prevents_second_physical_request(self):
        self.assertTrue(self.execute()['ok'])
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.calls), 1)

    def test_actual_provider_change_fails_before_dispatch_marker(self):
        with patch.object(p, 'credentials', return_value={**CREDS, 'base_url': 'https://other.invalid/v1'}):
            with self.assertRaisesRegex(ValueError, 'actual_provider_changed'):
                self.execute()
        self.assertFalse((self.root / 'EXECUTION.json').exists())
        self.assertEqual(self.calls, [])

    def test_typed_limit_change_fails_even_with_new_manifest_hash(self):
        manifest = p.read(self.root / 'manifest.json')
        manifest['limits']['max_model_calls'] = True
        p.save(self.root / 'manifest.json', manifest)
        self.manifest_sha = p.sha(self.root / 'manifest.json')
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_source_change_fails_before_dispatch(self):
        with patch.object(p, 'sources', return_value={'fixture.py': 'c' * 64}):
            with self.assertRaises(ValueError):
                self.execute()
        self.assertEqual(self.calls, [])

    def test_request_numeric_boolean_tamper_fails_after_inventory_refresh(self):
        self.assertTrue(self.execute()['ok'])
        request = p.read(self.root / 'request.json'); request['stream'] = 0
        p.save(self.root / 'request.json', request); self.refresh_inventory()
        with self.assertRaisesRegex(ValueError, 'response_policy_or_usage_failed'):
            self.audit()

    def test_receipt_numeric_boolean_tamper_fails_after_inventory_refresh(self):
        self.assertTrue(self.execute()['ok'])
        receipt = p.read(self.root / 'receipt.json'); receipt['model_calls'] = True
        p.save(self.root / 'receipt.json', receipt); self.refresh_inventory()
        with self.assertRaisesRegex(ValueError, 'response_policy_or_usage_failed'):
            self.audit()

    def test_changed_raw_usage_fails_reconstruction(self):
        self.assertTrue(self.execute()['ok'])
        raw = p.read(self.root / 'response.json'); raw['usage']['input_tokens'] += 1
        p.save(self.root / 'response.json', raw); self.refresh_inventory()
        with self.assertRaises(ValueError):
            self.audit()

    def test_wall_evidence_cannot_hide_overrun(self):
        self.assertTrue(self.execute()['ok'])
        timing = p.read(self.root / 'TIMING.json')
        timing.update(wall_seconds=121, ended_monotonic=timing['started_monotonic'] + 121)
        p.save(self.root / 'TIMING.json', timing); self.refresh_inventory()
        with self.assertRaisesRegex(ValueError, 'wall_evidence'):
            self.audit()

    def test_report_typed_boolean_tamper_fails(self):
        self.assertTrue(self.execute()['ok'])
        report = p.read(self.root / 'REPORT.json'); report['ok'] = 1
        p.save(self.root / 'REPORT.json', report)
        with self.assertRaisesRegex(ValueError, 'report_changed'):
            self.audit()

    def test_unknown_usage_keeps_full_reservation(self):
        self.result.pop('usage')
        report = self.execute()
        self.assertFalse(report['ok']); self.assertFalse(report['usage_complete'])
        self.assertIsNone(report['known_tokens'])
        self.assertEqual(report['reserved_tokens_if_unknown'], p.LIMITS['max_tokens'])
        self.assertEqual(report['physical_requests_attempted'], 1)

    def test_transport_error_keeps_full_reservation(self):
        self.error = TimeoutError('offline simulated unreachable endpoint')
        report = self.execute()
        self.assertFalse(report['ok']); self.assertFalse(report['usage_complete'])
        self.assertIsNone(report['known_tokens'])
        self.assertEqual(report['reserved_tokens_if_unknown'], p.LIMITS['max_tokens'])
        self.assertEqual(report['physical_requests_attempted'], 1)

    def test_setup_overrun_cannot_dispatch_after_deadline(self):
        now = [0.]
        def late_factory(creds):
            now[0] = 121.
            return lambda *a, **kw: self.fail('Expired preflight dispatched a request')
        with patch.object(p.time, 'monotonic', side_effect=lambda: now[0]), \
                patch.object(p.optimizer, '_sdk_transport', side_effect=late_factory):
            report = self.execute()
        self.assertFalse(report['ok']); self.assertEqual(report['physical_requests_attempted'], 0)
        self.assertEqual(report['known_tokens'], 0); self.assertTrue(report['usage_complete'])
        self.assertEqual(report['reserved_tokens_if_unknown'], 0)

    def test_request_persistence_overrun_cannot_dispatch_after_deadline(self):
        now = [0.]; original_save = p.save
        def slow_save(path, value):
            original_save(path, value)
            if Path(path).name == 'request.json':
                now[0] = 121.
        with patch.object(p.time, 'monotonic', side_effect=lambda: now[0]), \
                patch.object(p, 'save', side_effect=slow_save):
            report = self.execute()
        self.assertFalse(report['ok']); self.assertEqual(report['physical_requests_attempted'], 0)
        self.assertEqual(report['known_tokens'], 0); self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
