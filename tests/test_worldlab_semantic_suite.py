from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import read, save
from worldlab import qualify_semantic_suite as suite


def cases():
    return [{'id': name, 'family': 'fixture', 'task_id': 'fixture/' + name,
             'expected': good, 'label_rationale': 'DO_NOT_SEND_THIS_LABEL',
             'payload': {'criterion': {'id': 'q', 'requirement': 'The artifact says good.'},
                         'ambiguities': [], 'evaluation_guidance': [],
                         'evidence': {'instruction': 'Write good.', 'files': {'output.txt': {'text': name}}}}}
            for name, good in [('good', True), ('bad', False)]]


class Client:
    base_url = 'http://127.0.0.1:8011/v1'
    max_retries = 0

    def __init__(self, callback):
        self.responses = SimpleNamespace(create=callback)

    def close(self):
        pass


def response(request, *, usage=True, status='completed', reverse=False):
    payload = json.loads(request['input'][1]['content'])
    value = payload['evidence']['files']['output.txt']['text'] == 'good'
    return SimpleNamespace(status=status, output_text=json.dumps({
        'criterion_id': 'q', 'evidence': 'output.txt', 'reasoning': 'The file content was checked.',
        'passed': not value if reverse else value}),
        usage=SimpleNamespace(input_tokens=50, output_tokens=10, total_tokens=60) if usage else None)


class Tests(unittest.TestCase):
    def prepare(self, *, repeats=1, concurrency=64):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / 'suite'
        with patch.object(suite, 'controls', return_value=cases()):
            suite.prepare(SimpleNamespace(verification={'manifest_sha256': 'fixture'}), out,
                          'fixture', Client.base_url, repeats=repeats, concurrency=concurrency)
        return out

    def test_parallel_dispatch_reaches_64_and_preserves_every_labeled_case(self):
        out = self.prepare(repeats=33)
        lock = threading.Lock(); barrier = threading.Barrier(64)
        counts = {'active': 0, 'peak': 0, 'calls': 0}
        def create(**request):
            with lock:
                counts['calls'] += 1; ordinal = counts['calls']
                counts['active'] += 1
                counts['peak'] = max(counts['peak'], counts['active'])
            try:
                self.assertNotIn('DO_NOT_SEND_THIS_LABEL', json.dumps(request))
                self.assertFalse(request['stream']); self.assertFalse(request['store'])
                self.assertEqual(request['max_output_tokens'], 4096)
                self.assertEqual(request['extra_body']['structured_outputs']['json']['properties']['evidence'],
                                 {'type': 'string'})
                if ordinal <= 64:
                    barrier.wait(timeout=10)
                return response(request)
            finally:
                with lock:
                    counts['active'] -= 1
        result = suite.run(out, client_factory=lambda: Client(create))
        self.assertTrue(result['ok'])
        self.assertEqual((result['completed'], result['matching_labels'], result['model_calls']), (66, 66, 66))
        self.assertEqual((counts['peak'], counts['active']), (64, 0))
        self.assertEqual(result['charged_tokens'], 66 * 60)
        self.assertFalse(result['general_accuracy_claim'])
        self.assertEqual(len(list((out / 'responses').glob('*/RESPONSE.json'))), 66)
        self.assertTrue(suite.audit(out)['ok'])
        with self.assertRaises(FileExistsError):
            suite.run(out, client_factory=lambda: Client(create))

    def test_wrong_labels_are_retained_without_retry_or_selected_subset(self):
        out = self.prepare(); calls = []
        def create(**request):
            calls.append(request)
            return response(request, reverse=True)
        result = suite.run(out, client_factory=lambda: Client(create))
        self.assertFalse(result['ok']); self.assertEqual(result['completed'], 2)
        self.assertEqual((result['valid'], result['matching_labels'], len(calls)), (2, 0, 2))
        self.assertEqual(result['unknown_accounting'], 0)
        bad = next((out / 'responses').iterdir())
        (bad / 'RESULT.json').unlink()
        with self.assertRaises(FileNotFoundError):
            suite.audit(out)

    def test_incomplete_and_unknown_usage_preserve_costs_without_retry(self):
        for mode in ('incomplete', 'unknown', 'timeout'):
            with self.subTest(mode=mode):
                out = self.prepare(); calls = []
                def create(**request):
                    calls.append(request)
                    if mode == 'timeout':
                        raise TimeoutError('fixture')
                    return response(request, usage=mode != 'unknown',
                                    status='incomplete' if mode == 'incomplete' else 'completed')
                result = suite.run(out, client_factory=lambda: Client(create))
                self.assertFalse(result['ok']); self.assertEqual(len(calls), 2)
                self.assertEqual(result['completed'], 2)
                if mode == 'incomplete':
                    self.assertEqual(result['charged_tokens'], 120)
                    self.assertEqual(result['unknown_accounting'], 0)
                else:
                    self.assertEqual(result['unknown_accounting'], 2)
                    self.assertGreater(result['charged_tokens'], 0)
                    self.assertEqual(result['reported_tokens'], 0)

    def test_case_drift_prevents_dispatch_and_response_or_prompt_tampering_fails_audit(self):
        out = self.prepare()
        case = out / 'cases/good.json'; before = case.read_bytes()
        value = read(case); value['expected'] = False; save(case, value)
        with self.assertRaisesRegex(ValueError, 'case changed'):
            suite.run(out)
        self.assertFalse((out / 'EXECUTION.json').exists())
        case.write_bytes(before)
        suite.run(out, client_factory=lambda: Client(lambda **request: response(request)))
        result = out / 'responses/r000-good/RESULT.json'; original = read(result)
        for field in ('actual', 'request_input_sha256', 'request_structured_outputs_sha256'):
            wrong = deepcopy(original)
            if field == 'actual':
                wrong[field] = False
            else:
                wrong['usage']['operations'][0][field] = 'changed'
            save(result, wrong)
            with self.assertRaises(ValueError):
                suite.audit(out)
            save(result, original)

    def test_setup_failure_records_no_dispatch_without_inventing_unknown_usage(self):
        out = self.prepare()
        def factory():
            raise ValueError('Invalid local fixture setup')
        result = suite.run(out, client_factory=factory)
        self.assertFalse(result['ok'])
        self.assertEqual((result['model_calls'], result['unknown_accounting'], result['undispatched']), (0, 0, 2))
        self.assertEqual(result['charged_tokens'], 0)

    def test_registered_source_rule_has_zero_calls_and_is_audited_separately(self):
        from worldlab.mechanical_criteria import CRITERION, SOURCE, OUTPUT
        case = {'id': 'registered-count', 'family': 'fixture', 'task_id': 'fixture/count',
                'expected': False, 'label_rationale': 'The output has no required references.',
                'payload': {'criterion': deepcopy(CRITERION), 'evidence': {'instruction': 'Use the sources.',
                            'files': {SOURCE: {'text': 'Fig. 4.7\nFig. 4.7\nFig. 4.7'},
                                      OUTPUT: {'text': 'No references.'}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'suite'
            with patch.object(suite, 'controls', return_value=[case]):
                prepared = suite.prepare(SimpleNamespace(verification={'manifest_sha256': 'fixture'}), out,
                                         'fixture', Client.base_url, repeats=1)
            self.assertEqual((prepared['planned_calls'], prepared['planned_evaluations']), (0, 1))
            def forbidden():
                raise AssertionError('Registered source rule must not construct an API client')
            result = suite.run(out, client_factory=forbidden)
            self.assertTrue(result['ok']); self.assertEqual(result['source_rule_evaluations'], 1)
            self.assertEqual((result['model_calls'], result['charged_tokens'], result['undispatched']), (0, 0, 0))
            self.assertTrue(suite.audit(out)['ok'])


if __name__ == '__main__':
    unittest.main()
