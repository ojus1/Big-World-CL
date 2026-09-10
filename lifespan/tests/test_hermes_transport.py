"""Offline transport fixtures; these do not establish native/model quality."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from lifespan.evaluation import hermes_transport as transport
from lifespan.evaluation.budget import ResponsesBudget, NativeBudgetExceeded
from lifespan.evaluation.protocol import ExperimentConfig
from lifespan.evaluation.runtime import native_usage
from scripts.audit_evaluation import transport_check, transport_manifest_check

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, outputs):
        self.outputs, self.calls, self.max_retries = iter(outputs), [], 2
        self.responses = NS(create=self.create)

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        value = next(self.outputs)
        if isinstance(value, BaseException):
            raise value
        return value() if callable(value) else value


def response(status='completed', usage=True):
    return NS(status=status, output=[NS(type='message', content='fixture')],
              usage=NS(input_tokens=10, output_tokens=5, total_tokens=15) if usage else None)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.preflight = []
        def validate(payload, **kwargs):
            self.preflight.append((deepcopy(payload), kwargs))
            return dict(payload, store=False)
        self.native = NS(preflight_kwargs=validate)
        self.relay = NS(execute=lambda request, callback, **kwargs: callback(request))
        self.scope = patch.dict(sys.modules, {'agent': NS(relay_llm=self.relay)})
        self.scope.start(); self.addCleanup(self.scope.stop)
        guard = patch.object(transport, '_verify_agent')
        self.guard = guard.start(); self.addCleanup(guard.stop)

    def agent(self, outputs, calls=4):
        client = Client(outputs)
        meter = ResponsesBudget(max_model_calls=calls, max_output_tokens=64, max_total_tokens=100000)
        meter.wrap_client(client)
        agent = NS(api_mode='codex_responses', client=client, _big_world_budget=meter,
            _interrupt_requested=False, _run_codex_stream=lambda *args: 'original fixture',
            _get_transport=lambda: self.native, _is_copilot_url=lambda: False, _is_codex_backend=lambda: False)
        return agent, client, meter

    def request(self):
        return {'model': 'offline-fixture', 'instructions': 'Fixture only.',
            'input': [{'type': 'function_call_output', 'call_id': 'call_1', 'output': 'ok'}],
            'tools': [{'type': 'function', 'name': 'terminal', 'parameters': {'type': 'object'}}],
            'store': False, 'include': ['reasoning.encrypted_content'], 'reasoning': {'effort': 'low'},
            'max_output_tokens': 64, 'timeout': 3.0}

    def install(self, agent):
        return transport.install(agent, 'nonstreaming', hermes_root=Path('/unused-fixture'))

    def manifest(self, value='nonstreaming'):
        import hashlib
        return {'config': ExperimentConfig(hermes_transport=value).public(),
                **transport.manifest_fields({'hermes_transport': value}),
                'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                    ('lifespan/evaluation/hermes_transport.py', 'lifespan/hermes_worker.py',
                     'lifespan/evaluation/runtime.py', 'lifespan/evaluation/runner.py')}}

    def test_streaming_default_does_not_patch_or_access_native_dependency(self):
        agent, _, _ = self.agent([])
        original = agent._run_codex_stream
        result = transport.install(agent, 'streaming', hermes_root='/absent')
        self.assertIs(agent._run_codex_stream, original)
        self.guard.assert_not_called()
        self.assertEqual(result['mode'], 'streaming')
        self.assertNotIn('hermes_transport', ExperimentConfig().public())
        self.assertEqual(transport.executor_options(ExperimentConfig()), {})

    def test_config_and_manifest_explicitly_bind_nondefault_mode(self):
        config = ExperimentConfig(hermes_transport='nonstreaming')
        self.assertEqual(config.public()['hermes_transport'], 'nonstreaming')
        self.assertEqual(transport.executor_options(config), {'hermes_transport': 'nonstreaming'})
        fields = transport.manifest_fields(config)
        self.assertEqual(transport_manifest_check(self.manifest()), fields['hermes_transport_provenance'])
        for value in (None, False, 'auto', []):
            with self.assertRaises(ValueError):
                ExperimentConfig(hermes_transport=value)

    def test_final_body_preserves_native_payload_and_response_object(self):
        answer = response(); agent, client, meter = self.agent([answer])
        other, _, _ = self.agent([]); untouched = other._run_codex_stream
        descriptor = self.install(agent)
        request = self.request(); before = deepcopy(request)
        result = agent._run_codex_stream(request, client=client)
        self.assertIs(result, answer)
        self.assertEqual(request, before)
        self.assertEqual(client.calls, [dict(request, stream=False)])
        self.assertEqual(self.preflight[0][0], request)
        self.assertIs(other._run_codex_stream, untouched)
        self.assertEqual(descriptor['hermes_revision'], transport.PIN)
        self.assertEqual(meter.report()['physical_model_calls'], 1)
        self.assertEqual(meter.report()['charged_tokens'], 15)
        self.assertIs(meter.report()['operations'][0]['request_stream'], False)
        self.assertEqual(client.max_retries, 0)

    def test_noncompleted_response_is_returned_unchanged_for_native_parser(self):
        for status in ('failed', 'cancelled', 'incomplete', 'completed'):
            answer = response(status); agent, client, meter = self.agent([answer]); self.install(agent)
            self.assertIs(agent._run_codex_stream(self.request(), client=client), answer)
            self.assertEqual(answer.status, status)
            self.assertEqual(meter.report()['operations'][0]['provider_response_status'], status)
            self.assertEqual(meter.report()['operations'][0]['status'], 'completed')

    def test_missing_or_unsupported_provider_status_is_unknown_without_losing_usage(self):
        for status in (None, 'private provider body', {}, 'absent'):
            answer = response(status)
            if status == 'absent': del answer.status
            agent, client, meter = self.agent([answer]); self.install(agent)
            self.assertIs(agent._run_codex_stream(self.request(), client=client), answer)
            row = meter.report()['operations'][0]
            self.assertIsNone(row['provider_response_status'])
            self.assertEqual(row['charged_tokens'], 15)
            self.assertEqual(row['status'], 'completed')
            self.assertTrue(meter.report()['accounting_complete'])
            self.assertNotIn('private provider body', str(meter.report()))

    def test_no_sdk_retry_or_fallback_and_unknown_usage_remains_invalid(self):
        for first in (ConnectionError('private provider body'), response(usage=False)):
            agent, client, meter = self.agent([first, response()]); descriptor = self.install(agent)
            if isinstance(first, BaseException):
                with self.assertRaises(ConnectionError):
                    agent._run_codex_stream(self.request(), client=client)
            else:
                agent._run_codex_stream(self.request(), client=client)
            self.assertEqual(len(client.calls), 1)
            # This explicit fixture retry models a later native harness attempt.
            agent._run_codex_stream(self.request(), client=client)
            native = {'evaluation_budget': meter.report(), 'evaluation_transport': descriptor}
            usage = native_usage(native)
            self.assertEqual(usage['api_calls'], 2)
            self.assertIsNone(usage['total_tokens']); self.assertFalse(usage['complete'])
            row = meter.report()['operations'][0]
            self.assertEqual(row['charged_tokens'], row['reserved_tokens'])
            self.assertEqual(meter.report()['charged_tokens'], row['reserved_tokens'] + 15)
            self.assertNotIn('private provider body', str(meter.report()))

    def test_cancellation_before_dispatch_and_after_receipt_preserves_costs(self):
        agent, client, meter = self.agent([]); self.install(agent); agent._interrupt_requested = True
        with self.assertRaises(InterruptedError): agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(meter.report()['physical_model_calls'], 0)
        agent._interrupt_requested = False
        def cancel_after_response():
            agent._interrupt_requested = True
            return response()
        client.outputs = iter([cancel_after_response])
        with self.assertRaises(InterruptedError): agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(meter.report()['physical_model_calls'], 1)
        self.assertEqual(meter.report()['charged_tokens'], 15)
        self.assertTrue(meter.report()['accounting_complete'])

    def test_cancelled_dispatch_without_receipt_preserves_unknown_reservation(self):
        agent, client, meter = self.agent([]); self.install(agent)
        def interrupted():
            agent._interrupt_requested = True
            raise InterruptedError('fixture cancellation')
        client.outputs = iter([interrupted])
        with self.assertRaises(InterruptedError): agent._run_codex_stream(self.request(), client=client)
        report = meter.report(); row = report['operations'][0]
        self.assertEqual(row['charged_tokens'], row['reserved_tokens'])
        self.assertFalse(report['accounting_complete']); self.assertIsNone(row['total_tokens'])

    def test_physical_cap_blocks_next_dispatch_and_clamps_output(self):
        agent, client, meter = self.agent([response()], calls=1); self.install(agent)
        request = self.request(); request['max_output_tokens'] = 1000
        agent._run_codex_stream(request, client=client)
        self.assertEqual(client.calls[0]['max_output_tokens'], 64)
        with self.assertRaises(NativeBudgetExceeded): agent._run_codex_stream(request, client=client)
        self.assertEqual(len(client.calls), 1)

    def test_storage_meter_and_retry_overrides_fail_before_dispatch(self):
        for field in ('store', 'stream', 'max_output_tokens'):
            agent, client, _ = self.agent([]); self.install(agent)
            request = self.request(); request['extra_body'] = {field: True}
            with self.assertRaises(ValueError): agent._run_codex_stream(request, client=client)
            self.assertEqual(client.calls, [])
        for bad in ('unmetered', 'retry'):
            agent, client, _ = self.agent([]); self.install(agent)
            if bad == 'unmetered': client._big_world_budget = object()
            else: client.max_retries = 1
            with self.assertRaises(RuntimeError): agent._run_codex_stream(self.request(), client=client)
            self.assertEqual(client.calls, [])

    def test_guard_failure_does_not_modify_instance(self):
        agent, _, _ = self.agent([]); original = agent._run_codex_stream
        self.guard.side_effect = RuntimeError('fixture revision mismatch')
        with self.assertRaises(RuntimeError): self.install(agent)
        self.assertIs(agent._run_codex_stream, original)

    def test_source_guard_rejects_wrong_revision_and_modified_bytes(self):
        import hashlib
        expected = {'run_agent.py': hashlib.sha256(b'fixture source').hexdigest()}
        with patch.object(transport, 'NATIVE_FILES', expected), patch.object(Path, 'read_bytes', return_value=b'fixture source'):
            for revision, dirty in ((transport.PIN, b'changed'), ('wrong-revision', b'')):
                with patch.object(subprocess, 'check_output', side_effect=[revision, dirty]):
                    with self.assertRaisesRegex(RuntimeError, 'clean pinned Hermes revision'):
                        transport.verify_source('/fixture')
            with patch.object(subprocess, 'check_output', side_effect=[transport.PIN, b'']), patch.object(Path, 'read_bytes', return_value=b'changed'):
                with self.assertRaisesRegex(RuntimeError, 'clean pinned Hermes revision'):
                    transport.verify_source('/fixture')

    def test_relay_cannot_synthesize_or_repeat_physical_response(self):
        agent, client, meter = self.agent([response()]); self.install(agent)
        self.relay.execute = lambda *a, **k: response()
        with self.assertRaisesRegex(RuntimeError, 'bypassed'):
            agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(meter.report()['physical_model_calls'], 0)
        def twice(request, callback, **kwargs):
            callback(request)
            return callback(request)
        self.relay.execute = twice
        with self.assertRaisesRegex(RuntimeError, 'one physical dispatch'):
            agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(meter.report()['physical_model_calls'], 1)

    def test_relay_cannot_replace_a_metered_response_or_erase_its_cost(self):
        agent, client, meter = self.agent([response()]); self.install(agent)
        def replacement(request, callback, **kwargs):
            callback(request)
            return response()
        self.relay.execute = replacement
        with self.assertRaisesRegex(RuntimeError, 'replaced the physical response'):
            agent._run_codex_stream(self.request(), client=client)
        self.assertEqual(meter.report()['physical_model_calls'], 1)
        self.assertEqual(meter.report()['charged_tokens'], 15)
        self.assertTrue(meter.report()['accounting_complete'])

    def test_raw_audit_rejects_top_level_and_per_physical_mode_mismatch(self):
        descriptor = transport.contract('nonstreaming')
        manifest = self.manifest()
        record = {'hermes_transport': descriptor, 'result': {'native': {
            'evaluation_transport': descriptor, 'evaluation_budget': {'operations': [{'request_stream': False}]}}}}
        transport_check(record, manifest)
        for path in ('physical', 'native', 'session', 'manifest', 'config'):
            item, declared = deepcopy(record), deepcopy(manifest)
            if path == 'physical': item['result']['native']['evaluation_budget']['operations'][0]['request_stream'] = True
            elif path == 'native': item['result']['native']['evaluation_transport'] = transport.contract('streaming')
            elif path == 'session': item['hermes_transport'] = transport.contract('streaming')
            elif path == 'manifest': declared.pop('hermes_transport_provenance')
            else: declared['config'].pop('hermes_transport')
            with self.assertRaises(ValueError): transport_check(item, declared)

    def test_raw_audit_binds_all_new_execution_source_hashes(self):
        manifest = self.manifest()
        for name in manifest['source_sha256']:
            altered = deepcopy(manifest); altered['source_sha256'][name] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hermes_transport_execution_source_binding'):
                transport_manifest_check(altered)
        stripped = deepcopy(manifest); stripped.pop('source_sha256')
        with self.assertRaisesRegex(ValueError, 'hermes_transport_execution_source_binding'):
            transport_manifest_check(stripped)

    def test_raw_audit_rejects_stripped_session_or_legacy_nondefault_binding(self):
        descriptor = transport.contract('nonstreaming')
        record = {'hermes_transport': descriptor, 'result': {'native': {
            'evaluation_transport': descriptor, 'evaluation_budget': {'operations': [{'request_stream': False}]}}}}
        transport_check(record)  # Standalone modern receipt remains inspectable.
        with self.assertRaisesRegex(ValueError, 'legacy_manifest_mode_mismatch'):
            transport_check(record, {'config': {}})
        for marker in ('native', 'physical'):
            stripped = deepcopy(record); stripped.pop('hermes_transport')
            if marker == 'native': stripped['result']['native']['evaluation_budget']['operations'] = []
            else: stripped['result']['native'].pop('evaluation_transport')
            with self.assertRaisesRegex(ValueError, 'missing_session_contract'):
                transport_check(stripped, {'config': {}})

    def test_paired_reports_reject_differing_transport_configuration_or_provenance(self):
        from lifespan.evaluation.metrics import paired_report
        from lifespan.tests.test_evaluation_metrics import report
        for mismatch in ('config', 'provenance'):
            first, second = report(), report(algorithm='skillopt')
            if mismatch == 'config': second['config']['hermes_transport'] = 'nonstreaming'
            else:
                first['provenance'].update(transport.manifest_fields({'hermes_transport': 'streaming'}))
                second['provenance'].update(transport.manifest_fields({'hermes_transport': 'nonstreaming'}))
            result = paired_report([first, second])
            self.assertEqual(result['eligible_pairs'], [])
            self.assertEqual(len(result['rejected_pairs']), 1)

    def test_future_worker_hash_requires_transport_marker_even_if_other_markers_removed(self):
        import hashlib
        manifest = {'config': {'algorithm': 'no_learning'}, 'source_sha256': {
            'lifespan/hermes_worker.py': hashlib.sha256((ROOT/'lifespan/hermes_worker.py').read_bytes()).hexdigest()}}
        with self.assertRaisesRegex(ValueError, 'hermes_transport_manifest_contract'):
            transport_manifest_check(manifest)
        self.assertIsNone(transport_manifest_check({'config': {'algorithm': 'no_learning'}}))

    def test_current_runtime_or_runner_cannot_downgrade_by_stripping_all_transport_markers(self):
        for retained in ('lifespan/evaluation/runtime.py', 'lifespan/evaluation/runner.py'):
            manifest = self.manifest()
            manifest.pop('hermes_transport'); manifest.pop('hermes_transport_provenance')
            manifest['config'].pop('hermes_transport')
            manifest['source_sha256'] = {retained: manifest['source_sha256'][retained]}
            with self.assertRaisesRegex(ValueError, 'hermes_transport_manifest_contract'):
                transport_check({'result': {'native': {'evaluation_budget': {'operations': []}}}}, manifest)
        self.assertIsNone(transport_manifest_check({'config': {}, 'source_sha256': {
            'lifespan/evaluation/runtime.py': 'explicit-historical-fixture-revision'}}))

    def test_runtime_persists_returned_costs_when_transport_evidence_is_invalid(self):
        import json
        from lifespan.ecosystem import Ecosystem
        from lifespan.evaluation import runtime
        from lifespan.evaluation.tasks import make_case
        from lifespan.world import Task
        descriptor = transport.contract('nonstreaming')
        for mismatch in ('none', 'native', 'physical'):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as folder:
                eco = Ecosystem(16, 101)
                world = eco.worlds['firm-0']
                task = Task('transport-fixture', 'onboarding', 'regulated', 'onboarding-regulated',
                            'consumer-0', 0, 3, 10)
                world.tasks[task.id] = task
                case = make_case('onboarding', 101, 0, task.id)
                agent, client, meter = self.agent([response()]); self.install(agent)
                agent._run_codex_stream(self.request(), client=client)
                native = {'messages': [], 'failed': False, 'evaluation_transport': descriptor,
                          'evaluation_budget': meter.report()}
                if mismatch == 'native': native['evaluation_transport'] = transport.contract('streaming')
                if mismatch == 'physical': native['evaluation_budget']['operations'][0]['request_stream'] = True
                root = Path(folder) / 'trial'
                with patch.object(runtime.Computer, 'start', return_value={
                        'tool_names': [], 'evaluation_transport': descriptor}), \
                     patch.object(runtime.Computer, 'run', return_value={'native': native}), \
                     patch.object(runtime.Computer, 'close'):
                    record = runtime.execute_case(root=root, employee='firm-0__onboarding-regulated',
                        world=world, task_id=task.id, case=case, request='Offline fixture.',
                        skill='Read current published task files.', credentials={}, objectives={},
                        hermes_transport='nonstreaming')
                self.assertEqual(record['infrastructure_valid'], mismatch == 'none')
                self.assertEqual(record['usage']['total_tokens'], 15)
                self.assertTrue(record['usage']['complete'])
                self.assertEqual(json.loads((root/'session.json').read_text()), record)
                self.assertFalse((root/'INFLIGHT.json').exists())
                self.assertFalse((root/'FAILURE.json').exists())


class NativeParityTests(unittest.TestCase):
    def test_actual_pinned_native_conversion_preflight_parser_and_hook(self):
        native = Path(os.environ.get('HERMES_AGENT_ROOT', Path.home()/'.hermes/hermes-agent')).resolve()
        python = native/'venv/bin/python'
        if not python.is_file():
            self.skipTest('Optional actual Hermes parity fixture: pinned Hermes virtualenv unavailable')
        try: transport.verify_source(native)
        except RuntimeError:
            self.skipTest('Optional actual Hermes parity fixture: clean pinned source unavailable')
        with tempfile.TemporaryDirectory() as folder:
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': folder,
                   'HERMES_HOME': str(Path(folder)/'profile'), 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTHONPATH': str(ROOT)+os.pathsep+str(native), 'BIGWORLD_NATIVE_ROOT': str(native)}
            result = subprocess.run([str(python), str(ROOT/'lifespan/tests/hermes_transport_native_fixture.py')],
                cwd=folder, env=env, capture_output=True, text=True, timeout=90)
        if result.returncode == 77:
            self.skipTest('Optional actual Hermes parity fixture: native runtime import dependency unavailable')
        self.assertEqual(result.returncode, 0, result.stdout[-2000:]+result.stderr[-2000:])
        self.assertIn('NATIVE_PARITY_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
