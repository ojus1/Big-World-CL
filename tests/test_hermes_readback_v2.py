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


class CompoundReadbackTests(unittest.TestCase):
    """Synthetic byte-bound trajectories, never native quality evidence."""
    def setUp(self):
        self.fixture = ReadbackTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.raw = b'{"field":true,"count":2,"text":"synthetic fixture"}\n'
        self.configure(self.raw)

    def configure(self, raw):
        f = self.fixture; self.raw = raw
        f.submitted = hashlib.sha256(raw).hexdigest()
        (f.root / 'filesystem_objects' / f.submitted).write_bytes(raw)
        f.record['last_submitted_artifact_sha256'] = f.submitted
        f.commit['artifact_sha256'] = f.submitted
        f.messages[:] = []
        f.add('commit', 'enterprise_action', {'operation': 'work.commit'}, json.dumps(f.commit))
        # Construct expected native output independently of the helper under test.
        self.output = (raw.decode('utf-8') + f.submitted + '  ' + audit.ARTIFACT_PATH + '\n').strip()
        f.add('readback', 'terminal', {'command': audit.COMPOUND_COMMAND},
              json.dumps({'output': self.output, 'exit_code': 0, 'error': None}))
        f.messages.append({'role': 'assistant', 'content': 'Checked the submitted fixture.'})

    def payload(self, **changes):
        value = {'output': self.output, 'exit_code': 0, 'error': None}
        value.update(changes); self.fixture.messages[3]['content'] = json.dumps(value)

    def test_exact_compound_preserves_bytes_hash_and_native_boundary_whitespace(self):
        raws = (self.raw, self.raw.rstrip(b'\n'), b' \n' + self.raw + b'\n\t',
                '{"text":"caf\u00e9 \u03bb","field":true}\n'.encode())
        for raw in raws:
            with self.subTest(artifact_sha256=hashlib.sha256(raw).hexdigest()):
                self.configure(raw); before = deepcopy(self.fixture.record)
                evidence = self.fixture.evidence()
                self.assertTrue(evidence['transport_roundtrip_capable'])
                self.assertEqual(len(evidence['readbacks']), 1)
                row = evidence['readbacks'][0]
                self.assertEqual((row['call_index'], row['result_index'], row['final_response_index']), (2, 3, 4))
                self.assertEqual(row['artifact_sha256'], self.fixture.submitted)
                self.assertIsNone(row['native_warning_count'])
                self.assertEqual(self.fixture.record, before)

    def test_only_exact_literal_command_and_arguments_are_supported(self):
        path = audit.ARTIFACT_PATH
        commands = (
            f'cat {path} "&&" sha256sum {path}', f'cat {path} \'&&\' sha256sum {path}',
            f'cat {path}; sha256sum {path}', f'cat {path} || sha256sum {path}',
            f'cat {path} | sha256sum {path}', f'cat {path} && sha256sum {path} > /tmp/out',
            f'cat {path} && sha256sum {path}; true', f'cat {path} && sha256sum {path} # comment',
            f'cat {path} &&\nsha256sum {path}', f'cat {path}  && sha256sum {path}',
            f'cat "{path}" && sha256sum {path}', f'cat -- {path} && sha256sum -- {path}',
            f'X=1 cat {path} && sha256sum {path}', f'cat $(echo {path}) && sha256sum {path}',
            f'cat `{path}` && sha256sum {path}', f'cat $FILE && sha256sum $FILE',
            f'cat {path}/../capability.json && sha256sum {path}',
            f'cat {path} && sha256sum /workspace/other.json', audit.COMPOUND_COMMAND + "'",
            None, False, [],
        )
        for command in commands:
            with self.subTest(command_index=commands.index(command)):
                self.fixture.messages[2]['tool_calls'][0]['function']['arguments'] = json.dumps({'command': command})
                self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])
        self.fixture.messages[2]['tool_calls'][0]['function']['arguments'] = json.dumps(
            {'command': audit.COMPOUND_COMMAND, 'workdir': '/workspace'})
        self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])

    def test_entire_raw_body_hash_filename_and_envelope_must_match(self):
        wrong_raw = self.raw.replace(b'true', b'1')
        variants = (
            self.output.replace(self.fixture.submitted, '0' * 64),
            self.output.replace(audit.ARTIFACT_PATH, '/workspace/other.json'),
            self.output.replace('"field":true', '"field": true'),  # same parsed JSON
            self.output.replace('"field":true', '"field":1'),
            wrong_raw.decode() + hashlib.sha256(wrong_raw).hexdigest() + '  ' + audit.ARTIFACT_PATH,
            self.output.replace('  ' + audit.ARTIFACT_PATH, ' ' + audit.ARTIFACT_PATH),
            self.output[:-1], self.raw.decode(), 'prefix\n' + self.output,
            self.output + '\n', self.output + ' ', self.output + '\nextra',
            self.output + '\n' + self.fixture.submitted + '  ' + audit.ARTIFACT_PATH,
            self.output.replace('synthetic fixture', '[OUTPUT TRUNCATED]'),
        )
        for index, body in enumerate(variants):
            with self.subTest(output_variant=index):
                self.payload(output=body)
                self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])
        for changes in ({'exit_code': False}, {'exit_code': 0.0}, {'exit_code': '0'},
                        {'exit_code': 1}, {'error': 'fixture-error'}, {'error': False},
                        {'error': 0}, {'truncated': False}, {'stderr': ''}, {'output': None}):
            with self.subTest(envelope_variant=repr(changes)):
                self.payload(**changes)
                self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])
        self.payload(); del_value = json.loads(self.fixture.messages[3]['content']); del_value.pop('error')
        self.fixture.messages[3]['content'] = json.dumps(del_value)
        self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])

    def test_terminal_warning_and_arbitrary_json_suffix_cannot_be_removed(self):
        for suffix in (audit.warning(2), '\n{}', ' extra'):
            self.payload(); self.fixture.messages[3]['content'] += suffix
            self.assertFalse(self.fixture.evidence()['transport_roundtrip_capable'])

    def test_commit_order_result_identity_and_final_response_remain_required(self):
        f = self.fixture
        original = deepcopy(f.messages)
        mutations = (
            lambda: f.messages.__setitem__(slice(None), f.messages[2:4] + f.messages[:2] + f.messages[4:]),
            lambda: f.messages[1].__setitem__('content', json.dumps({**f.commit, 'observation': {'changed': True}})),
            lambda: f.messages.pop(),
            lambda: f.messages[-1].__setitem__('tool_calls', [{'id': 'later', 'function': {'name': 'noop', 'arguments': '{}'}}]),
        )
        for index, mutate in enumerate(mutations):
            f.messages[:] = deepcopy(original); mutate()
            with self.subTest(mutation=index): self.assertFalse(f.evidence()['transport_roundtrip_capable'])
        for field, value in (('tool_call_id', 'unknown'), ('name', 'read_file')):
            f.messages[:] = deepcopy(original); f.messages[3][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): f.evidence()

    def test_unchanged_skill_budget_and_native_failure_gates_apply_to_compound(self):
        f = self.fixture; original = deepcopy(f.record)
        for key in ('skill', 'budget', 'failed', 'auxiliary', 'physical_calls'):
            f.record = deepcopy(original); native = f.record['result']['native']
            if key == 'skill': f.record['skill_loaded'] = False
            elif key == 'budget': f.record['budget_exhausted'] = True
            elif key == 'failed': native['failed'] = True
            elif key == 'auxiliary': native['evaluation_budget']['disabled_auxiliary_calls'] = ['iteration_summary']
            else: native['evaluation_budget']['physical_model_calls'] = 1
            with self.subTest(key=key): self.assertFalse(f.evidence()['transport_roundtrip_capable'])

    def test_simple_cat_and_hash_remain_supported_but_bool_exit_is_rejected(self):
        f = self.fixture
        for command, body in ((f'cat {audit.ARTIFACT_PATH}', self.raw.decode()),
                              (f'sha256sum {audit.ARTIFACT_PATH}', f.submitted + '  ' + audit.ARTIFACT_PATH)):
            f.messages[2]['tool_calls'][0]['function']['arguments'] = json.dumps({'command': command})
            self.payload(output=body)
            self.assertTrue(f.evidence()['transport_roundtrip_capable'])
            self.payload(output=body, exit_code=False)
            self.assertFalse(f.evidence()['transport_roundtrip_capable'])


class PinnedNativeFormatterTests(unittest.TestCase):
    def test_actual_pinned_terminal_normalizes_expected_compound_output(self):
        root = Path(os.environ.get('BIGWORLD_TEST_HERMES_SOURCE', audit.HERMES))
        path = root / 'tools/terminal_tool.py'
        if not path.is_file():
            if 'BIGWORLD_TEST_HERMES_SOURCE' in os.environ:
                self.fail('Explicit pinned Hermes source fixture is missing')
            self.skipTest('Pinned Hermes source not installed; use BIGWORLD_TEST_HERMES_SOURCE')
        self.assertEqual(audit.sha(path), audit.NATIVE_SOURCES['tools/terminal_tool.py'])
        tree = ast.parse(path.read_text())
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Assign) and
                 len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and
                 node.targets[0].id == 'output' and isinstance(node.value, ast.IfExp) and
                 isinstance(node.value.body, ast.Call) and isinstance(node.value.body.func, ast.Name) and
                 node.value.body.func.id == 'redact_terminal_output']
        self.assertEqual(len(nodes), 1)
        # Execute only this pinned pure expression with a no-op redactor. No
        # terminal, SDK, provider, native imports or native constructor executes.
        for raw in (b'{"a":true}', b'{"a":true}\n', b' \n{"a":true}\n\t',
                    '{"text":"caf\u00e9"}\n'.encode()):
            submitted = hashlib.sha256(raw).hexdigest()
            output = raw.decode() + submitted + '  ' + audit.ARTIFACT_PATH + '\n'
            seen = []
            def redactor(value, command):
                seen.append((value, command)); return value
            namespace = {'output': output, 'command': audit.COMPOUND_COMMAND, 'redact_terminal_output': redactor}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
            self.assertEqual(seen, [(output.strip(), audit.COMPOUND_COMMAND)])
            self.assertEqual(namespace['output'], audit.compound_output(raw, submitted))

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
