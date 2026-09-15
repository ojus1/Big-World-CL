"""Regression for a completed but overlong employee response and its one repair."""
import json
import unittest

from lifespan.actor_contract import wire, wire_shape_error
from lifespan.ecosystem_run import native_decision
from lifespan.mirofish import MiroFishRuntime


def employee(**overrides):
    return {'delegate': True, 'request': 'Reconcile the supplier invoices.',
            'working_notes': '', 'share_document_ids': [], 'colleague_messages': [],
            'process_proposal': None, **overrides}


class Tests(unittest.TestCase):
    def test_scale_failure_length_gets_actionable_bounded_repair(self):
        calls, validated = [], []
        original = employee(working_notes='é' * 1900)

        class Runtime:
            actor_output_contract = {'version': 'actor-json-v1'}
            actor_roles = {'employee': 'employee'}
            validate_output_contract = MiroFishRuntime.validate_output_contract

            def interview(self, actor, prompt, key):
                calls.append((prompt, key))
                if len(calls) == 1:
                    return json.dumps(original)
                if 'working_notes: 1900 characters; maximum 1800' not in prompt:
                    return json.dumps(original)
                return json.dumps(employee(working_notes='Carry the unresolved discrepancy forward.'))

        result = native_decision(Runtime(), 'employee', 'Public task brief', 'case', validated.append)
        self.assertEqual([key for _, key in calls], ['case', 'case-repair'])
        self.assertEqual(validated, [result])
        self.assertEqual(result['request'], original['request'])
        self.assertFalse(wire.shape_valid(json.dumps(original), 'employee'))
        self.assertTrue(wire.shape_valid(json.dumps(result), 'employee'))
        self.assertEqual(len(original['working_notes']), 1900)

    def test_diagnostic_does_not_salvage_an_invalid_second_response(self):
        calls = []

        class Runtime:
            actor_output_contract = {'version': 'actor-json-v1'}
            actor_roles = {'employee': 'employee'}
            validate_output_contract = MiroFishRuntime.validate_output_contract

            def interview(self, actor, prompt, key):
                calls.append(key)
                return json.dumps(employee(working_notes='x' * 1900))

        with self.assertRaisesRegex(ValueError, 'working_notes: 1900 characters; maximum 1800'):
            native_decision(Runtime(), 'employee', 'brief', 'case', lambda _: self.fail('Invalid output accepted'))
        self.assertEqual(calls, ['case', 'case-repair'])

    def test_nested_limits_use_schema_paths_without_response_values(self):
        raw = json.dumps(employee(request='r' * 12001, share_document_ids=['d' * 257],
            colleague_messages=[{'recipient': 'n' * 257, 'text': 't' * 4001, 'document_ids': ['i' * 257]}],
            process_proposal={'action': 'require_peer_review', 'reason': 'p' * 1801},
            private_unexpected_key='Do not echo this value'))
        message = wire_shape_error(raw, 'employee')
        for path, length, maximum in [('request', 12001, 12000), ('share_document_ids[0]', 257, 256),
                ('colleague_messages[0].recipient', 257, 256), ('colleague_messages[0].text', 4001, 4000),
                ('colleague_messages[0].document_ids[0]', 257, 256), ('process_proposal.reason', 1801, 1800)]:
            self.assertIn(f'{path}: {length} characters; maximum {maximum}', message)
        self.assertNotIn('private_unexpected_key', message)
        self.assertNotIn('Do not echo', message)
        self.assertNotIn('rrrr', message)

    def test_exact_unicode_boundary_and_malformed_json_keep_original_validation(self):
        at_limit = employee(working_notes='é' * 1800)
        self.assertTrue(wire.shape_valid(json.dumps(at_limit), 'employee'))
        self.assertNotIn('Shorten', wire_shape_error(json.dumps(at_limit), 'employee'))
        for raw in ('not JSON', '{"delegate": true', json.dumps(employee(delegate='true'))):
            self.assertFalse(wire.shape_valid(raw, 'employee'))
            self.assertNotIn('Shorten', wire_shape_error(raw, 'employee'))

    def test_diagnostic_is_bounded(self):
        message = wire_shape_error(json.dumps(employee(share_document_ids=['x' * 257] * 100)), 'employee')
        self.assertEqual(message.count('characters; maximum'), 8)
        self.assertLess(len(message), 1000)


if __name__ == '__main__':
    unittest.main()
