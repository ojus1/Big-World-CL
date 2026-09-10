"""Readback-envelope compatibility, with adversarial synthetic trajectories."""
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from scripts import audit_hermes_readback_v2 as audit


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        raw = b'{"field":true,"count":2,"text":"synthetic fixture"}'
        self.submitted = hashlib.sha256(raw).hexdigest()
        (self.root / 'filesystem_objects').mkdir()
        (self.root / 'filesystem_objects' / self.submitted).write_bytes(raw)
        self.payload = {'content': '1|' + raw.decode(), 'file_size': len(raw), 'truncated': False}
        self.body = json.dumps(self.payload)
        self.messages = []
        self.add('first', 'read_file', {'path': audit.ARTIFACT_PATH}, self.body)
        self.commit = {'artifact_sha256': self.submitted, 'observation': {}, 'terminated': False}
        self.add('commit', 'enterprise_action', {'operation': 'work.commit'}, json.dumps(self.commit))
        self.add('second', 'read_file', {'path': audit.ARTIFACT_PATH}, self.body + audit.warning(2))
        self.messages.append({'role': 'assistant', 'content': 'Checked the submitted fixture.'})
        self.record = {'last_submitted_artifact_sha256': self.submitted, 'skill_loaded': True,
            'budget_exhausted': False, 'result': {'native': {'messages': self.messages,
                'evaluation_budget': {'physical_model_calls': 4, 'disabled_auxiliary_calls': []}},
                'workplace_rpc': [{'action': {'tool': 'work.commit'}, 'response': self.commit}]}}

    def add(self, call_id, name, args, content):
        self.messages += [{'role': 'assistant', 'tool_calls': [{'id': call_id, 'function': {
            'name': name, 'arguments': json.dumps(args)}}]},
            {'role': 'tool', 'tool_call_id': call_id, 'name': name, 'content': content}]

    def evidence(self):
        return audit.readback_evidence(self.record, self.root)

    def test_exact_warning_preserves_native_readback_and_final_response(self):
        before = deepcopy(self.record); result = self.evidence()
        self.assertTrue(result['transport_roundtrip_capable'])
        self.assertEqual(result['readbacks'][0]['native_warning_count'], 2)
        self.assertEqual(result['readbacks'][0]['observed_same_result_count'], 2)
        self.assertEqual(self.record, before)

    def test_plain_json_readback_stays_supported(self):
        self.messages[5]['content'] = self.body
        self.assertTrue(self.evidence()['transport_roundtrip_capable'])

    def test_arbitrary_suffixes_are_not_ignored(self):
        for suffix in (' extra', '\n{}', '\n\n[Tool loop hard stop: blocked]',
                       audit.warning(2) + ' extra', audit.warning(2).replace('read_file', 'terminal'),
                       audit.warning(2).replace('count=2', 'count=3')):
            self.messages[5]['content'] = self.body + suffix
            with self.subTest(suffix_hash=hashlib.sha256(suffix.encode()).hexdigest()):
                self.assertFalse(self.evidence()['transport_roundtrip_capable'])

    def test_warning_count_must_match_observed_history(self):
        self.messages[5]['content'] = self.body + audit.warning(3)
        with self.assertRaisesRegex(ValueError, 'repeat_count_unproven'): self.evidence()

    def test_warning_cannot_attest_a_first_read_or_changed_result(self):
        self.messages[1]['content'] = self.body.replace('synthetic fixture', 'earlier bytes')
        with self.assertRaisesRegex(ValueError, 'repeat_count_unproven'): self.evidence()

    def test_warning_requires_identical_call_arguments(self):
        self.messages[0]['tool_calls'][0]['function']['arguments'] = json.dumps({'path': '/workspace/elsewhere.json'})
        with self.assertRaisesRegex(ValueError, 'repeat_count_unproven'): self.evidence()

    def test_boolean_numeric_substitution_cannot_match_artifact(self):
        value = json.loads(self.body); value['content'] = value['content'].replace('true', '1')
        self.messages[1]['content'] = json.dumps(value)
        self.messages[5]['content'] = json.dumps(value) + audit.warning(2)
        self.assertFalse(self.evidence()['transport_roundtrip_capable'])

    def test_final_response_is_required_after_readback(self):
        self.messages.pop()
        self.assertFalse(self.evidence()['transport_roundtrip_capable'])

    def test_untrusted_or_mismatched_commit_cannot_establish_readback(self):
        self.messages[3]['content'] = json.dumps({**self.commit, 'artifact_sha256': '0' * 64})
        self.assertFalse(self.evidence()['transport_roundtrip_capable'])

    def test_duplicate_call_or_result_identity_rejected(self):
        self.messages[4]['tool_calls'][0]['id'] = 'first'
        with self.assertRaisesRegex(ValueError, 'duplicate_tool_call_id'): self.evidence()

    def test_changed_immutable_object_fails_before_readback(self):
        (self.root / 'filesystem_objects' / self.submitted).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'submitted_object_hash'): self.evidence()

    def test_budget_auxiliary_or_native_failure_cannot_pass(self):
        native = self.record['result']['native']
        for key in ('budget_exhausted', 'failed', 'auxiliary'):
            self.record['budget_exhausted'] = key == 'budget_exhausted'
            native['failed'] = key == 'failed'
            native['evaluation_budget']['disabled_auxiliary_calls'] = ['fixture'] if key == 'auxiliary' else []
            with self.subTest(key=key): self.assertFalse(self.evidence()['transport_roundtrip_capable'])


class PinnedNativeFormatterTests(unittest.TestCase):
    def test_actual_pinned_formatter_emits_exact_supported_suffix(self):
        root = Path(os.environ.get('BIGWORLD_TEST_HERMES_SOURCE', audit.HERMES))
        path = root / 'agent/tool_guardrails.py'
        if not path.is_file():
            if 'BIGWORLD_TEST_HERMES_SOURCE' in os.environ:
                self.fail('Explicit pinned Hermes source fixture is missing')
            self.skipTest('Pinned Hermes source not installed; use BIGWORLD_TEST_HERMES_SOURCE')
        self.assertEqual(audit.sha(path), audit.NATIVE_SOURCES['agent/tool_guardrails.py'])
        # Compile only the real pure formatting function, not native imports or
        # any provider/runtime code. This is source parity, not native inference.
        tree = ast.parse(path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'append_toolguard_guidance')
        namespace = {'ToolGuardrailDecision': SimpleNamespace}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
        for count in (2, 3, 10):
            message = (f'read_file returned the same result {count} times. '
                       'Use the result already provided or change the query instead of repeating it unchanged.')
            decision = SimpleNamespace(action='warn', message=message, code='idempotent_no_progress_warning', count=count)
            result = namespace['append_toolguard_guidance']('{}', decision)
            self.assertEqual(result, '{}' + audit.warning(count))
            self.assertEqual(audit.decode_observation(result, name='read_file'), ({}, count))


if __name__ == '__main__':
    unittest.main()
