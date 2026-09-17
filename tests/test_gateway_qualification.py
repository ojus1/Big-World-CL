import json
import unittest

from worldlab.qualify_gateway import inspect_response


class Tests(unittest.TestCase):
    def response(self, content='{"ok":true}', out=7, total=17, status='completed'):
        return json.dumps({'status': status, 'usage': {'input_tokens': 10, 'output_tokens': out, 'total_tokens': total},
                           'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': content}]}]}).encode()

    def test_responses_known_usage_survives_invalid_control(self):
        self.assertEqual(inspect_response(self.response(), 'responses_json'), (17, True))
        for content in ('not json', '{"ok":false}', '{}'):
            self.assertEqual(inspect_response(self.response(content), 'responses_json'), (17, False))

    def test_overrun_and_incomplete_keep_measured_usage(self):
        self.assertEqual(inspect_response(self.response(out=129, total=139), 'responses_json'), (139, False))
        self.assertEqual(inspect_response(self.response(status='incomplete'), 'responses_json'), (17, False))

    def test_invalid_accounting_is_not_measured(self):
        with self.assertRaisesRegex(ValueError, 'Invalid native token usage'):
            inspect_response(self.response(total=16), 'responses_json')

    def test_chat_and_sse_are_checked(self):
        usage = {'prompt_tokens': 10, 'completion_tokens': 7, 'total_tokens': 17}
        value = {'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}], 'usage': usage}
        self.assertEqual(inspect_response(json.dumps(value).encode(), 'chat_json'), (17, True))
        value['choices'][0]['delta'] = value['choices'][0].pop('message')
        raw = ('data: ' + json.dumps(value) + '\n\ndata: [DONE]\n\n').encode()
        self.assertEqual(inspect_response(raw, 'chat_sse'), (17, True))


if __name__ == '__main__': unittest.main()
