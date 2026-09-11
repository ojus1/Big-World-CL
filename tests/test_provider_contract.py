"""Offline request-policy, configuration and optimizer regressions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from lifespan.evaluation import provider
from lifespan.evaluation.optimizer import make_reflector
from lifespan.evaluation.protocol import ExperimentConfig
from lifespan.evaluation.runtime import execute_case
from lifespan.tests.test_evaluation_optimizer import Transport, payload, limits


CREDS = {'model': 'Qwen/Qwen3.8-27B-FP8', 'base_url': 'https://example.invalid/v1',
         'api_key': 'offline-fixture-secret', 'provider_profile': provider.PROFILE}


class ProviderTests(unittest.TestCase):
    def test_legacy_has_no_profile_or_added_public_configuration(self):
        self.assertIsNone(provider.contract({'model': 'legacy', 'base_url': 'https://example.invalid'}))
        self.assertNotIn('provider_profile', ExperimentConfig().public())
        self.assertEqual(provider.manifest_fields(ExperimentConfig(), {'model': 'legacy'}), {})

    def test_contract_has_no_credential_and_canonicalizes_sdk_slash(self):
        value = provider.contract(CREDS)
        self.assertNotIn(CREDS['api_key'], json.dumps(value))
        self.assertEqual(provider.contract({**CREDS, 'base_url': CREDS['base_url'] + '/'}), value)
        self.assertEqual(provider.validate_contract(value), value)
        for key, wrong in (('schema_version', True), ('stream', 0), ('store', 0),
                           ('api_mode', 'chat_completions'), ('base_url', CREDS['base_url'] + '/')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                provider.validate_contract({**value, key: wrong})
        for template in ({'enable_thinking': 0}, {'enable_thinking': True}, {'enable_thinking': False, 'other': 1}):
            with self.subTest(template=template), self.assertRaises(ValueError):
                provider.validate_contract({**value, 'chat_template_kwargs': template})
        with self.assertRaises(ValueError):
            provider.validate_contract({**value, 'api_key': 'not-allowed'})

    def test_runtime_descriptor_match_rejects_numeric_booleans(self):
        expected = provider.contract(CREDS)
        self.assertTrue(provider.matches(deepcopy(expected), expected))
        for key, value in (('schema_version', True), ('stream', 0), ('store', 0),
                           ('chat_template_kwargs', {'enable_thinking': 0})):
            with self.subTest(key=key):
                self.assertFalse(provider.matches({**expected, key: value}, expected))
        self.assertFalse(provider.matches(None, expected))
        self.assertFalse(provider.matches(expected, None))
        self.assertTrue(provider.matches(None, None))

    def test_url_credentials_parameters_and_invalid_ports_are_rejected(self):
        for url in ('https://user:fake@example.invalid/v1', 'https://example.invalid/v1?key=x',
                    'https://example.invalid/v1#x', 'https://example.invalid:invalid/v1',
                    'https://example.invalid:99999/v1', 'file:///tmp/data', 'https://example.invalid/v1\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                provider.contract({**CREDS, 'base_url': url})

    def test_explicit_profile_requires_matching_config_and_transport(self):
        config = ExperimentConfig(hermes_transport='nonstreaming', provider_profile=provider.PROFILE)
        self.assertEqual(provider.require_config(config, CREDS), provider.contract(CREDS))
        self.assertEqual(config.public()['provider_profile'], provider.PROFILE)
        for options in ({'provider_profile': provider.PROFILE},
                        {'provider_profile': 'unknown', 'hermes_transport': 'nonstreaming'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ExperimentConfig(**options)
        with self.assertRaises(ValueError):
            provider.require_config(ExperimentConfig(hermes_transport='nonstreaming'), CREDS)
        with self.assertRaises(ValueError):
            provider.contract({**CREDS, 'api_mode': 'chat_completions'})

    def test_runtime_mismatch_stops_before_artifact_or_worker_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'attempt'
            with self.assertRaises(ValueError):
                execute_case(root=root, employee='fixture', world=None, task_id='fixture', case={},
                             request='fixture', skill='fixture', credentials=CREDS, objectives={},
                             hermes_transport='nonstreaming')
            self.assertFalse(root.exists())

    def test_optimizer_binds_exact_request_policy_and_usage(self):
        transport = Transport()
        result = make_reflector({**CREDS, 'reasoning_effort': 'high'}, transport=transport)(payload(), limits())
        request = transport.calls[0]['request']
        self.assertIs(request['stream'], False)
        self.assertIs(request['store'], False)
        self.assertNotIn('reasoning', request)
        self.assertEqual(request['extra_body'], {'chat_template_kwargs': {'enable_thinking': False}})
        self.assertEqual(result['provider_contract'], provider.contract(CREDS))
        self.assertEqual(result['request_model'], CREDS['model'])
        self.assertEqual(result['request_base_url'], CREDS['base_url'])
        self.assertEqual(result['request_api_mode'], 'responses')
        self.assertEqual(result['tokens'], 180)
        self.assertEqual(result['provider_request_sha256'], hashlib.sha256(json.dumps(
            request, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest())
        self.assertNotIn(CREDS['api_key'], json.dumps(result))

    def test_missing_optimizer_usage_stays_unknown_with_policy_retained(self):
        transport = Transport(); transport.result.pop('usage')
        result = make_reflector(CREDS, transport=transport)(payload(), limits())
        self.assertEqual(result['status'], 'invalid_usage')
        self.assertIsNone(result['tokens'])
        self.assertFalse(result['accounting_complete'])
        self.assertEqual(result['model_calls'], 1)
        self.assertEqual(result['provider_contract'], provider.contract(CREDS))

    def test_sdk_refuses_numeric_thinking_flag_before_dispatch(self):
        from lifespan.evaluation.optimizer import _sdk_transport, OptimizerInputError
        client = MagicMock(); client.base_url = CREDS['base_url'] + '/'
        client.__enter__.return_value = client
        sdk = types.ModuleType('openai'); sdk.OpenAI = MagicMock(return_value=client)
        request = {'model': CREDS['model'], 'stream': False, 'store': False,
                   'extra_body': {'chat_template_kwargs': {'enable_thinking': 0}}}
        with patch.dict(sys.modules, {'openai': sdk}):
            with self.assertRaises(OptimizerInputError):
                _sdk_transport(CREDS)(request, timeout=1, api_mode='responses')
        client.responses.create.assert_not_called()
        client.chat.completions.create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
