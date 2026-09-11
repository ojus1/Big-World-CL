"""Thinking-disabled Responses policy fixtures: no HTTP or native agent launch."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation import hermes_transport as transport
from lifespan.evaluation.budget import ResponsesBudget, NativeBudgetExceeded, install_native_budget
from lifespan.evaluation.provider import PROFILE, provider_contract
from lifespan.evaluation.runtime import native_usage
from lifespan.tests.test_hermes_transport import Client, response
from scripts.audit_evaluation import (provider_check, transport_check, optimizer_provider_check,
    update_provider_check, provider_manifest_check)

ROOT = Path(__file__).resolve().parents[2]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.policy = provider_contract('Qwen/Qwen3.8-27B-FP8', 'http://example.invalid/v1')
        self.relay = NS(execute=lambda request, callback, **kwargs: callback(request))
        self.enterContext(patch.dict(sys.modules, {'agent': NS(relay_llm=self.relay)}))
        self.guard = self.enterContext(patch.object(transport, '_verify_agent'))

    def agent(self, outcomes=None, **limits):
        client = Client(outcomes if outcomes is not None else [response()])
        client.base_url = self.policy['base_url'] + '/'
        meter = ResponsesBudget(max_model_calls=limits.pop('max_model_calls', 4), max_output_tokens=64,
            max_total_tokens=limits.pop('max_total_tokens', 100000), provider_contract=self.policy, **limits)
        meter.wrap_client(client)
        agent = NS(api_mode='codex_responses', model=self.policy['model'], base_url=self.policy['base_url'],
            reasoning_config={'enabled': False}, client=client, _big_world_budget=meter,
            _interrupt_requested=False, _run_codex_stream=lambda *args: None,
            _get_transport=lambda: NS(preflight_kwargs=lambda payload, **kw: dict(payload, store=False)),
            _is_copilot_url=lambda: False, _is_codex_backend=lambda: False)
        transport.install(agent, 'nonstreaming', hermes_root='/unused', provider_contract=self.policy)
        return agent, client, meter

    def request(self):
        return {'model': self.policy['model'], 'input': [{'role': 'user', 'content': 'Fixture only.'}],
            'tools': [{'type': 'function', 'name': 'terminal', 'parameters': {'type': 'object'}}],
            'instructions': 'Fixture instructions.', 'store': False, 'max_output_tokens': 64}

    def direct_request(self):
        return {**self.request(), 'stream': False,
                'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}

    def record(self):
        agent, client, meter = self.agent(); agent._run_codex_stream(self.request(), client=client)
        native = {'provider_contract': self.policy, 'evaluation_transport': transport.contract('nonstreaming'),
                  'evaluation_budget': meter.report()}
        return {'provider_contract': self.policy, 'hermes_transport': transport.contract('nonstreaming'),
                'result': {'native': native}, 'usage': native_usage(native), 'infrastructure_valid': True}

    def manifest(self):
        sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'lifespan/evaluation/provider.py', 'lifespan/evaluation/budget.py', 'lifespan/evaluation/hermes_transport.py',
            'lifespan/hermes_worker.py', 'lifespan/evaluation/runtime.py', 'lifespan/evaluation/runner.py',
            'lifespan/evaluation/optimizer.py')}
        return {'provider_contract': self.policy, 'target_model': self.policy['model'],
            'model_base_url': self.policy['base_url'], 'config': {'algorithm': 'skillopt', 'provider_profile': PROFILE,
            'hermes_transport': 'nonstreaming'}, 'source_sha256': sources,
            **transport.manifest_fields({'hermes_transport': 'nonstreaming'})}

    def test_profile_injects_only_policy_preserving_native_request_and_receipt(self):
        answer = response(); agent, client, meter = self.agent([answer])
        request = self.request(); before = deepcopy(request)
        self.assertIs(agent._run_codex_stream(request, client=client), answer)
        self.assertEqual(request, before); self.assertEqual(client.calls, [self.direct_request()])
        report = meter.report(); row = report['operations'][0]
        self.assertEqual(report['provider_contract'], self.policy)
        self.assertEqual(row['provider_contract'], self.policy)
        self.assertEqual(row['request_api_mode'], 'responses'); self.assertEqual(row['request_model'], self.policy['model'])
        self.assertEqual(row['request_base_url'], self.policy['base_url'])
        self.assertIs(row['request_store'], False); self.assertEqual(row['request_chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(row['reserved_tokens'], len(json.dumps(client.calls[0], ensure_ascii=False, default=str).encode()) + 64 + 2048)
        self.assertEqual(report['charged_tokens'], 15); self.assertEqual(client.max_retries, 0)

    def test_policy_readbacks_check_actual_client_and_request_before_physical_dispatch(self):
        for change in ('url', 'model', 'api_mode', 'stream', 'store', 'thinking', 'numeric_false', 'hidden_model', 'reasoning', 'retries'):
            with self.subTest(change=change):
                _, client, meter = self.agent(); request = self.direct_request()
                if change == 'url': client.base_url = 'http://wrong.invalid/v1'
                elif change == 'model': request['model'] = 'wrong-model'
                elif change == 'api_mode': request.pop('extra_body')
                elif change in ('stream', 'store'): request[change] = True
                elif change == 'thinking': request['extra_body']['chat_template_kwargs']['enable_thinking'] = True
                elif change == 'numeric_false': request['extra_body']['chat_template_kwargs']['enable_thinking'] = 0
                elif change == 'hidden_model': request['extra_body']['model'] = 'wrong-model'
                elif change == 'reasoning': request['reasoning'] = {'effort': 'low'}
                elif change == 'retries': client.max_retries = 1
                with self.assertRaises(ValueError): client.responses.create(**request)
                self.assertEqual(client.calls, []); self.assertEqual(meter.report()['physical_model_calls'], 0)

    def test_adapter_refuses_template_override_and_preserves_legacy_no_profile(self):
        for extra in ({'chat_template_kwargs': {'enable_thinking': True}}, {'model': 'wrong-model'},
                      {'chat_template_kwargs': {'enable_thinking': False, 'private': 'secret'}}):
            agent, client, meter = self.agent()
            with self.assertRaises(ValueError): agent._run_codex_stream({**self.request(), 'extra_body': extra}, client=client)
            self.assertEqual(meter.report()['physical_model_calls'], 0)
        legacy = ResponsesBudget(max_model_calls=1, max_output_tokens=64); client = Client([response()])
        legacy.wrap_client(client).responses.create(input='legacy')
        self.assertNotIn('provider_contract', legacy.report())
        self.assertNotIn('provider_contract', legacy.report()['operations'][0])
        self.assertNotIn('extra_body', client.calls[0])

    def test_failed_cancelled_incomplete_and_missing_receipts_keep_actual_or_reserved_cost(self):
        for status in ('completed', 'incomplete', 'failed', 'cancelled'):
            agent, client, meter = self.agent([response(status)])
            result = agent._run_codex_stream(self.request(), client=client)
            self.assertEqual(result.status, status); self.assertEqual(meter.report()['charged_tokens'], 15)
            self.assertEqual(meter.report()['operations'][0]['provider_response_status'], status)
        for output in (response(usage=False), ConnectionError('PRIVATE_PROVIDER_BODY')):
            agent, client, meter = self.agent([output])
            if isinstance(output, Exception):
                with self.assertRaises(ConnectionError): agent._run_codex_stream(self.request(), client=client)
            else: agent._run_codex_stream(self.request(), client=client)
            row = meter.report()['operations'][0]
            self.assertFalse(meter.report()['accounting_complete']); self.assertIsNone(row['total_tokens'])
            self.assertEqual(row['charged_tokens'], row['reserved_tokens']); self.assertEqual(row['provider_contract'], self.policy)
            self.assertNotIn('PRIVATE_PROVIDER_BODY', json.dumps(meter.report()))

    def test_caps_and_report_copy_are_not_weakened_by_profile(self):
        agent, client, meter = self.agent(max_model_calls=1)
        agent._run_codex_stream({**self.request(), 'max_output_tokens': 999}, client=client)
        self.assertEqual(client.calls[0]['max_output_tokens'], 64)
        with self.assertRaises(NativeBudgetExceeded): agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(len(client.calls), 1)
        report = meter.report(); report['provider_contract']['model'] = 'changed'; report['operations'][0]['provider_contract']['model'] = 'changed'
        self.assertEqual(meter.report()['provider_contract'], self.policy)
        self.assertEqual(meter.report()['operations'][0]['provider_contract'], self.policy)
        agent, client, meter = self.agent(max_total_tokens=1)
        with self.assertRaises(NativeBudgetExceeded): agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(client.calls, [])

    def test_native_budget_factories_and_install_require_matching_policy(self):
        primary = Client([response()]); request = Client([response()])
        primary.base_url = request.base_url = self.policy['base_url']
        agent = NS(api_mode='codex_responses', client=primary,
            _ensure_primary_openai_client=lambda **kw: primary, _create_request_openai_client=lambda **kw: request,
            interrupt=lambda *a, **kw: None)
        meter = install_native_budget(agent, max_model_calls=2, max_output_tokens=64, provider_contract=self.policy)
        agent._ensure_primary_openai_client(reason='fixture').responses.create(**self.direct_request())
        agent._create_request_openai_client(reason='fixture').responses.create(**self.direct_request())
        self.assertEqual(meter.report()['physical_model_calls'], 2)
        self.assertTrue(all(r['provider_contract'] == self.policy for r in meter.report()['operations']))
        for change in ('omitted', 'reasoning', 'mode'):
            agent, _, _ = self.agent(); del agent._big_world_transport
            if change == 'reasoning': agent.reasoning_config = {'enabled': True, 'effort': 'low'}
            with self.assertRaises(ValueError):
                transport.install(agent, 'streaming' if change == 'mode' else 'nonstreaming', hermes_root='/unused',
                                  provider_contract=None if change == 'omitted' else self.policy)

    def test_executor_options_propagate_explicit_profile_only(self):
        self.assertEqual(transport.executor_options({'hermes_transport': 'nonstreaming', 'provider_profile': PROFILE}),
                         {'hermes_transport': 'nonstreaming', 'provider_profile': PROFILE})
        self.assertEqual(transport.executor_options({}), {})
        with self.assertRaises(ValueError): transport.executor_options({'provider_profile': PROFILE})

    def test_independent_audit_binds_profile_and_actual_readbacks_at_every_layer(self):
        record, manifest = self.record(), self.manifest(); transport_check(record, manifest)
        for key in ('request_api_mode', 'request_model', 'request_base_url', 'request_store', 'request_chat_template_kwargs', 'provider_contract'):
            altered = deepcopy(record); altered['result']['native']['evaluation_budget']['operations'][0][key] = None
            with self.assertRaises(ValueError): provider_check(altered, manifest)
        for layer in ('record', 'native', 'meter', 'manifest', 'config', 'source'):
            altered, declared = deepcopy(record), deepcopy(manifest)
            if layer == 'record': altered.pop('provider_contract')
            elif layer == 'native': altered['result']['native'].pop('provider_contract')
            elif layer == 'meter': altered['result']['native']['evaluation_budget'].pop('provider_contract')
            elif layer == 'manifest': declared.pop('provider_contract')
            elif layer == 'config': declared['config'].pop('provider_profile')
            else: declared['source_sha256']['lifespan/evaluation/provider.py'] = '0' * 64
            with self.assertRaises(ValueError): provider_check(altered, declared)

    def test_profile_marker_downgrade_never_uses_legacy_contract(self):
        original = self.record()
        for retained in ('native', 'meter', 'row'):
            record = deepcopy(original); record.pop('provider_contract')
            if retained != 'native': record['result']['native'].pop('provider_contract')
            if retained != 'meter': record['result']['native']['evaluation_budget'].pop('provider_contract')
            if retained != 'row': record['result']['native']['evaluation_budget']['operations'] = []
            with self.assertRaises(ValueError): provider_check(record, {'config': {}})

    def optimizer_receipt(self, max_tokens=10000):
        from lifespan.evaluation.optimizer import make_reflector
        reflect = make_reflector({'api_key': 'PRIVATE_FIXTURE', 'model': self.policy['model'],
            'base_url': self.policy['base_url'], 'provider_profile': PROFILE}, transport=lambda *a, **kw: {
                'status': 'completed', 'usage': {'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3},
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'fixture'}]}]})
        return reflect({'prompt': 'offline fixture', 'max_output_tokens': 32, 'current_day': 7, 'train_experiences': []},
            {'max_model_calls': 1, 'max_tokens': max_tokens, 'timeout_seconds': 10})

    def test_optimizer_actual_mock_transport_request_and_zero_call_binding(self):
        receipt = self.optimizer_receipt(); self.assertEqual(receipt['model_calls'], 1)
        optimizer_provider_check(receipt, self.policy)
        for field in ('provider_request_sha256', 'optimizer_prompt', 'max_output_tokens', 'request_model',
                      'request_base_url', 'request_stream', 'request_store', 'request_chat_template_kwargs', 'provider_contract'):
            changed = deepcopy(receipt); changed[field] = None
            with self.subTest(field=field), self.assertRaises(ValueError): optimizer_provider_check(changed, self.policy)
        empty = self.optimizer_receipt(max_tokens=1)
        self.assertEqual(empty['model_calls'], 0); optimizer_provider_check(empty, self.policy)
        self.assertEqual(empty['status'], 'budget_exhausted')
        for field in ('request_stream', 'request_model', 'provider_request_sha256'):
            changed = {**empty, field: 'forged'}
            with self.assertRaises(ValueError): optimizer_provider_check(changed, self.policy)
        with self.assertRaises(ValueError): optimizer_provider_check(receipt, None)
        optimizer_provider_check({'model_calls': 0}, None)

    def test_update_progress_and_report_provider_binding(self):
        update = {'provider_contract': self.policy, 'employee': 'fixture', 'day': 7,
                  'optimizer_transport_audit': [self.optimizer_receipt()]}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); progress = {'provider_contract': self.policy, 'employee': 'fixture', 'day': 7}
            path = directory / 'progress.json'; path.write_text(json.dumps(progress))
            update_provider_check(directory, update, self.manifest())
            for field in ('provider_contract', 'employee', 'day'):
                path.write_text(json.dumps({**progress, field: None}))
                with self.assertRaises(ValueError): update_provider_check(directory, update, self.manifest())
            path.unlink()
            with self.assertRaises(FileNotFoundError): update_provider_check(directory, update, self.manifest())
            with self.assertRaises(ValueError): update_provider_check(directory, update, {'config': {}})
        manifest = self.manifest(); report = {'config': manifest['config'], 'provenance': {'provider_contract': self.policy}}
        provider_manifest_check(manifest, report)
        report['provenance'] = {}
        with self.assertRaises(ValueError): provider_manifest_check(manifest, report)

    def test_nested_provider_descriptors_preserve_boolean_types(self):
        for layer in ('native', 'meter'):
            record = self.record(); native = record['result']['native']
            data = native if layer == 'native' else native['evaluation_budget']
            data['provider_contract'] = deepcopy(self.policy)
            data['provider_contract']['chat_template_kwargs']['enable_thinking'] = 0
            with self.subTest(layer=layer), self.assertRaises(ValueError): provider_check(record, self.manifest())
        altered = deepcopy(self.policy); altered['store'] = 0
        with self.assertRaises(ValueError): provider_manifest_check(self.manifest(),
            {'config': self.manifest()['config'], 'provenance': {'provider_contract': altered}})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); (path / 'progress.json').write_text(json.dumps({
                'provider_contract': altered, 'employee': 'fixture', 'day': 7}))
            with self.assertRaises(ValueError): update_provider_check(path, {'provider_contract': self.policy,
                'employee': 'fixture', 'day': 7, 'optimizer_transport_audit': []}, self.manifest())

    def test_update_check_threads_manifest_into_real_raw_replay_validation(self):
        from tests import test_evaluation_audit as fixtures
        from scripts.audit_evaluation import update_check
        fixture = fixtures.ArtifactAuditTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        update, directory = fixture.add_update()
        update['provider_contract'] = self.policy
        update['optimizer_transport_audit'] = [self.optimizer_receipt()]
        fixtures.save(directory / 'update.json', update)
        fixtures.save(directory / 'progress.json', {'provider_contract': self.policy,
            'employee': update['employee'], 'day': update['day']})
        for trial in directory.glob('trial-*'):
            path = trial / 'session.json'; record = json.loads(path.read_bytes())
            record['provider_contract'] = self.policy; record['hermes_transport'] = transport.contract('nonstreaming')
            native = record['result']['native']; native['provider_contract'] = self.policy
            native['evaluation_transport'] = record['hermes_transport']
            native['evaluation_budget']['provider_contract'] = self.policy
            for row in native['evaluation_budget']['operations']:
                row.update(provider_contract=self.policy, request_api_mode='responses', request_model=self.policy['model'],
                    request_base_url=self.policy['base_url'], request_stream=False, request_store=False,
                    request_chat_template_kwargs={'enable_thinking': False})
            fixtures.save(path, record)
        args = (fixture.root, update, {e['id']: e for e in fixture.state['experiences']},
                {r['id']: r for r in fixture.state['sessions']}, 1)
        update_check(*args, transport_manifest=self.manifest())
        fixtures.save(fixture.root / 'manifest.json', self.manifest())
        update_check(*args)  # The legacy caller still binds its on-disk manifest.
        wrong_manifest = self.manifest(); wrong_manifest['provider_contract'] = deepcopy(self.policy)
        wrong_manifest['provider_contract']['model'] = wrong_manifest['target_model'] = 'wrong-model'
        fixtures.save(fixture.root / 'manifest.json', wrong_manifest)
        with self.assertRaisesRegex(ValueError, 'provider_update_manifest_mismatch'): update_check(*args)
        path = directory / 'trial-001/session.json'; record = json.loads(path.read_bytes())
        record['result']['native']['evaluation_budget']['operations'][0]['request_base_url'] = 'https://wrong.invalid'
        fixtures.save(path, record)
        with self.assertRaisesRegex(ValueError, 'provider_physical_request_binding'):
            update_check(*args, transport_manifest=self.manifest())

    def test_worker_validates_profile_before_constructor_and_forwards_disabled_reasoning(self):
        from lifespan import hermes_worker
        seen = {}; sandbox = NS(sandbox=NS(process=NS(pid=1), rpc_socket='fixture-socket'), cleanup=lambda: None)
        terminal = NS(terminal_tool=lambda **kw: json.dumps({'exit_code': 0, 'output': '/workspace\nfixture\n'}),
            register_task_env_overrides=lambda *a: None, _active_environments={'default': sandbox})
        class Agent:
            def __init__(self, **kwargs): seen['agent'] = kwargs; self.tools = []
        def budget(*args, **kwargs): seen['budget'] = kwargs; return NS()
        def install(*args, **kwargs): seen['transport'] = kwargs; return {'fixture': True}
        modules = {'tools': NS(skills_tool=NS()), 'tools.registry': NS(registry=NS(register=lambda **kw: None)),
            'toolsets': NS(create_custom_toolset=lambda *a, **kw: None), 'run_agent': NS(AIAgent=Agent, IterationBudget=object),
            'hermes_state': NS(SessionDB=lambda: None), 'tools.terminal_tool': terminal,
            'lifespan.bubblewrap': NS(install_hermes_backend=lambda root: sandbox),
            'lifespan.evaluation.budget': NS(install_native_budget=budget),
            'lifespan.evaluation.hermes_transport': NS(install=install)}
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'hermes'; profile.mkdir()
            env = {'HERMES_HOME': str(profile), 'LIFESPAN_EMPLOYEE': 'fixture', 'LIFESPAN_MODEL': self.policy['model'],
                'LIFESPAN_API_KEY': 'PRIVATE_FIXTURE', 'LIFESPAN_BASE_URL': self.policy['base_url'],
                'LIFESPAN_SANDBOX': 'bubblewrap'}
            for mismatch in (False, True):
                seen.clear(); policy = deepcopy(self.policy)
                if mismatch: policy['model'] = 'different-model'
                env['LIFESPAN_EXECUTION_CONFIG'] = json.dumps({'mode': 'evaluation', 'hermes_transport': 'nonstreaming', 'provider_contract': policy})
                with patch.dict(sys.modules, modules), patch.dict(os.environ, env), patch('sys.stdout', io.StringIO()) as output, \
                     patch('sys.stderr', io.StringIO()), patch('sys.stdin', io.StringIO('{"kind":"close"}\n')):
                    if mismatch:
                        with self.assertRaises(ValueError): hermes_worker._main()
                        self.assertNotIn('agent', seen)
                    else:
                        hermes_worker._main()
                        self.assertEqual(seen['agent']['api_mode'], 'codex_responses')
                        self.assertEqual(seen['agent']['reasoning_config'], {'enabled': False})
                        self.assertEqual(seen['budget']['provider_contract'], self.policy)
                        self.assertEqual(seen['transport']['provider_contract'], self.policy)
                        self.assertEqual(json.loads(output.getvalue().splitlines()[0])['provider_contract'], self.policy)


if __name__ == '__main__':
    unittest.main()
