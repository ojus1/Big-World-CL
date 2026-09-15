import copy
import json
from pathlib import Path
import tempfile
import unittest

from worldlab.fluso_evidence import audit_skill_and_responses, response_message


class FlusoEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trace = self.root / 'native.jsonl'
        self.skill = 'Read the original inputs.\n'
        self.skill_path = '/workspace/skills/work-process/SKILL.md'
        call = {'type': 'toolCall', 'id': 'tool1', 'name': 'read', 'arguments': {'path': self.skill_path}}
        base = {'role': 'assistant', 'api': 'openai-completions', 'provider': 'pcci', 'model': 'test',
                'usage': {'input': 2, 'output': 3, 'totalTokens': 5}}
        self.messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'Do the task.'}]},
            {**copy.deepcopy(base), 'content': [call], 'responseId': 'r1', 'stopReason': 'toolUse'},
            {'role': 'toolResult', 'toolCallId': 'tool1', 'toolName': 'read', 'isError': False,
             'content': [{'type': 'text', 'text': self.skill}]},
            {**copy.deepcopy(base), 'content': [{'type': 'text', 'text': 'Done.'}], 'responseId': 'r2', 'stopReason': 'stop'}]
        operations = []
        for i, (rid, message, finish) in enumerate([
            ('r1', {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'tool1', 'type': 'function',
                     'function': {'name': 'read', 'arguments': json.dumps(call['arguments'])}}]}, 'tool_calls'),
            ('r2', {'role': 'assistant', 'content': 'Done.'}, 'stop'),
            ('aux', {'role': 'assistant', 'content': 'Title'}, 'stop')]):
            path = self.root / f'call-{i:04d}'; path.mkdir()
            wire = {'model': 'test', 'stream': False, 'messages': []}
            if rid == 'r2':
                wire['messages'] = [{'role': 'tool', 'tool_call_id': 'tool1', 'content': self.skill}]
            (path / 'WIRE_REQUEST.json').write_text(json.dumps(wire))
            (path / 'RESPONSE.bin').write_text(json.dumps({'id': rid, 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}]}))
            operations.append({'status': 'completed', 'path': path.name, 'dispatch': i + 1,
                               'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5}})
        (self.root / 'METER.json').write_text(json.dumps({'operations': operations, 'physical_model_calls': 3}))

    def audit(self):
        self.trace.write_text('\n'.join(json.dumps({'type': 'message', 'message': m}) for m in self.messages) + '\n')
        return audit_skill_and_responses(self.trace, self.root, model='test', skill_path=self.skill_path, skill_text=self.skill)

    def test_primary_and_auxiliary_calls_are_separate(self):
        result = self.audit()
        self.assertEqual((result['primary_model_calls'], result['other_metered_calls']), (2, 1))
        self.assertTrue(result['skill_loaded'])
        self.assertEqual(result['skill_consumption'][0]['consuming_response_id'], 'r2')
        self.assertEqual([m['role'] for m in result['trajectory']], ['user', 'assistant', 'tool', 'assistant'])

    def test_native_response_tampering_rejected(self):
        self.messages[-1]['content'][0]['text'] = 'Changed.'
        with self.assertRaisesRegex(ValueError, 'provider bytes'):
            self.audit()

    def test_failed_or_partial_skill_read_rejected(self):
        self.messages[2]['content'][0]['text'] = 'Read the'
        with self.assertRaisesRegex(ValueError, 'installed bytes'):
            self.audit()

    def test_skill_must_enter_later_inference_request(self):
        path = self.root / 'call-0001/WIRE_REQUEST.json'
        wire = json.loads(path.read_text()); wire['messages'] = []
        path.write_text(json.dumps(wire))
        with self.assertRaisesRegex(ValueError, 'consumed skill'):
            self.audit()

    def test_unmetered_response_rejected(self):
        self.messages[-1]['responseId'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'Unmetered'):
            self.audit()

    def test_primary_cost_mismatch_rejected(self):
        self.messages[-1]['usage']['totalTokens'] = 999
        with self.assertRaisesRegex(ValueError, 'usage differs'):
            self.audit()

    def test_duplicate_tool_result_rejected(self):
        self.messages.insert(3, copy.deepcopy(self.messages[2]))
        with self.assertRaisesRegex(ValueError, 'repeated native tool result'):
            self.audit()

    def test_sse_tool_arguments_and_unicode_are_reconstructed(self):
        values = [{'id': 'r', 'choices': [{'index': 0, 'delta': {'content': 'caf\u00e9', 'tool_calls': [
                    {'index': 0, 'id': 't', 'function': {'name': 'read', 'arguments': '{"path":'}}]}}]},
                  {'id': 'r', 'choices': [{'index': 0, 'delta': {'tool_calls': [
                    {'index': 0, 'function': {'arguments': '"file"}'}}]}, 'finish_reason': 'tool_calls'}]}]
        raw = ''.join('data: ' + json.dumps(v) + '\n\n' for v in values).encode() + b'data: [DONE]\n\n'
        rid, result, finish = response_message(raw, True)
        self.assertEqual((rid, finish), ('r', 'tool_calls'))
        self.assertEqual(result, {'text': 'caf\u00e9', 'tools': [{'id': 't', 'name': 'read', 'arguments': {'path': 'file'}}]})


if __name__ == '__main__': unittest.main()
