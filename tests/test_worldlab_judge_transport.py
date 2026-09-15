from copy import deepcopy
from types import SimpleNamespace
import unittest
from lifespan.evaluation.provider import provider_contract
from worldlab.judge_transport import StructuredJudgeBudget, digest
from worldlab.verdict_schema import contract, validate_text
from worldlab.qualitative import validate_verdict
import json


CONSTRAINT = {'json': {'type': 'object'}, 'disable_any_whitespace': True}


class Tests(unittest.TestCase):
    def test_verdict_unicode_and_verbosity_are_not_rejected(self):
        value = {'criterion_id': 'c', 'evidence': 'acc\u00e9nt ' * 400,
                 'reasoning': '"' * 2000, 'passed': False}
        self.assertEqual(validate_verdict(value, {'id': 'c'}), value)
        expected = contract('c')['json']
        self.assertEqual(expected['properties']['criterion_id']['enum'], ['c'])
        self.assertEqual(expected['properties']['evidence'], {'type': 'string'})
        self.assertFalse(expected['additionalProperties'])
        for invalid in [dict(value, criterion_id='other'), dict(value, extra='unexpected'),
                        dict(value, passed=1), dict(value, evidence=None)]:
            with self.assertRaises(ValueError): validate_verdict(invalid, {'id': 'c'})
        for invalid in [None, 3, True, []]:
            self.assertFalse(validate_text(invalid))

    def test_declared_constraint_is_sent_unchanged_and_bound_to_usage(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status='completed', usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12))
        client = SimpleNamespace(base_url='http://127.0.0.1:8000/v1', max_retries=0, responses=SimpleNamespace(create=create))
        meter = StructuredJudgeBudget(structured_contracts=[CONSTRAINT], max_model_calls=3, max_output_tokens=64,
            provider_contract=provider_contract('fixture', str(client.base_url)))
        meter.wrap_client(client)
        request = {'model': 'fixture', 'input': 'judge', 'max_output_tokens': 64, 'stream': False, 'store': False,
                   'extra_body': {'chat_template_kwargs': {'enable_thinking': False}, 'structured_outputs': deepcopy(CONSTRAINT)}}
        client.responses.create(**request)
        self.assertEqual(calls[0]['extra_body'], request['extra_body'])
        self.assertEqual(meter.report()['operations'][0]['request_structured_outputs_sha256'], digest(CONSTRAINT))
        for change in ['schema', 'thinking', 'endpoint', 'extra', 'text']:
            bad = deepcopy(request)
            if change == 'schema': bad['extra_body']['structured_outputs']['disable_any_whitespace'] = False
            if change == 'thinking': bad['extra_body']['chat_template_kwargs']['enable_thinking'] = True
            if change == 'endpoint': bad['model'] = 'different-model'
            if change == 'extra': bad['extra_body']['unregistered'] = True
            if change == 'text': bad['text'] = {'format': {'type': 'text'}}
            with self.assertRaises(ValueError): client.responses.create(**bad)
        self.assertEqual(len(calls), 1)
        self.assertEqual(meter.report()['physical_model_calls'], 1)


if __name__ == '__main__': unittest.main()
