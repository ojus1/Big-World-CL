from copy import deepcopy
from types import SimpleNamespace
import unittest
from lifespan.evaluation.provider import provider_contract
from worldlab.judge_transport import StructuredJudgeBudget, digest
from worldlab.verdict_grammar import contract, validate_text, EVIDENCE_LIMIT, REASONING_LIMIT
import json


CONSTRAINT = {'json': {'type': 'object'}, 'disable_any_whitespace': True}


class Tests(unittest.TestCase):
    def test_legal_verdicts_fit_output_budget_even_when_every_character_needs_escaping(self):
        value = {'criterion_id': 'x' * 128, 'evidence': '\\' * EVIDENCE_LIMIT,
                 'reasoning': '"' * REASONING_LIMIT, 'passed': False}
        self.assertLess(len(json.dumps(value, separators=(',', ':')).encode()), 4096)
        self.assertTrue(validate_text(value['reasoning'], REASONING_LIMIT))
        for text in [' ', '\t', 'acc\u00e9nt', 'x' * (EVIDENCE_LIMIT + 1)]:
            self.assertFalse(validate_text(text, EVIDENCE_LIMIT))
        with self.assertRaises(ValueError): contract('unsafe"criterion')

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
