"""Offline failure/cancellation fixtures, not native qualification evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from lifespan.evaluation.budget import ResponsesBudget, NativeProviderStopped, install_native_budget
from lifespan.evaluation.provider import provider_contract
from lifespan.evaluation import provider_failure as evidence
from lifespan.tests.test_evaluation_budget import Client, usage_response

POLICY = provider_contract('offline-fixture', 'http://example.invalid/v1')
COMPUTER = 'lifespan-' + '0' * 16


def request():
    return dict(model=POLICY['model'], input='PRIVATE_FIXTURE_INPUT', stream=False, store=False,
                extra_body={'chat_template_kwargs': {'enable_thinking': False}})


def answer(usage=None, status='completed'):
    result = usage_response() if usage is None else NS(usage=usage)
    result.status = status
    return result


def meter(client, **kwargs):
    client.base_url = POLICY['base_url']
    budget = ResponsesBudget(max_model_calls=20, max_output_tokens=64,
        max_total_tokens=100000, provider_contract=POLICY, **kwargs)
    budget.wrap_client(client)
    return budget


class StopTests(unittest.TestCase):
    def test_error_notifies_before_cancel_then_blocks_both_factories_and_old_clients(self):
        primary = Client([answer(), ConnectionError('PRIVATE_PROVIDER_BODY'), answer()])
        replacement = Client([answer()]); primary.base_url = replacement.base_url = POLICY['base_url']
        seen = []
        agent = NS(api_mode='codex_responses', client=primary,
            _ensure_primary_openai_client=lambda **kw: replacement,
            _create_request_openai_client=lambda **kw: replacement,
            interrupt=lambda message, **kw: seen.append(('cancel', message, kw)))
        budget = install_native_budget(agent, max_model_calls=20, max_output_tokens=64,
            provider_contract=POLICY, on_failure=lambda report: seen.append(('notify', report)))
        primary.responses.create(**request())
        with self.assertRaises(NativeProviderStopped): primary.responses.create(**request())
        self.assertEqual([item[0] for item in seen], ['notify', 'cancel'])
        self.assertEqual(seen[1][2], {'hard_cancel': True})
        # Even clearing Hermes' own cancellation or attempting a fresh client
        # does not clear this independent physical transport latch.
        agent._interrupt_requested = False
        for action in (lambda: primary.responses.create(**request()),
                       agent._ensure_primary_openai_client, agent._create_request_openai_client):
            with self.assertRaises(NativeProviderStopped): action()
        budget.wrap_client(replacement)
        with self.assertRaises(NativeProviderStopped): replacement.responses.create(**request())
        report = budget.report()
        self.assertTrue(report['stopped']); self.assertFalse(report['exhausted'])
        self.assertEqual(report['physical_model_calls'], 2); self.assertEqual(replacement.calls, [])
        self.assertEqual(report['reported_tokens'], 15)
        self.assertEqual(report['charged_tokens'], 15 + report['operations'][1]['reserved_tokens'])
        self.assertFalse(report['accounting_complete'])
        self.assertEqual(report['terminal_failure']['error_type'], 'ConnectionError')
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_invalid_usage_preserves_each_known_dimension_and_reservation(self):
        for values in ({'input_tokens': 9, 'output_tokens': 7, 'total_tokens': 2},
                       {'input_tokens': None, 'output_tokens': 9000, 'total_tokens': None},
                       {'input_tokens': True, 'output_tokens': 5, 'total_tokens': 6}, {}):
            with self.subTest(values=values):
                client = Client([answer(NS(**values)), answer()]); budget = meter(client)
                with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
                row = budget.report()['operations'][0]
                self.assertEqual(row['observed_usage'], {key: values.get(key) if type(values.get(key)) is int
                    else None for key in ('input_tokens', 'output_tokens', 'total_tokens')})
                self.assertEqual(row['charged_tokens'], row['reserved_tokens'])
                self.assertIsNone(row['total_tokens']); self.assertFalse(budget.report()['accounting_complete'])
                with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
                self.assertEqual(len(client.calls), 1)

    def test_terminal_status_preserves_valid_costs_but_incomplete_can_continue(self):
        for status in ('failed', 'cancelled', None, 'queued', 'in_progress', 'private-unknown'):
            client = Client([answer(status=status)]); budget = meter(client)
            with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
            report = budget.report()
            self.assertEqual(report['charged_tokens'], 15); self.assertTrue(report['accounting_complete'])
            self.assertFalse(report['exhausted']); self.assertTrue(report['stopped'])
            self.assertNotIn('private-unknown', json.dumps(report))
        client = Client([answer(status='incomplete'), answer()]); budget = meter(client)
        client.responses.create(**request()); client.responses.create(**request())
        self.assertEqual(budget.report()['physical_model_calls'], 2); self.assertFalse(budget.stopped)

    def test_overrun_and_callback_failures_cannot_mask_original_evidence_or_allow_retry(self):
        calls = []
        def bad_notify(report): calls.append('notify'); raise OSError('PRIVATE_WRITE')
        def bad_cancel(reason): calls.append('cancel'); raise RuntimeError('PRIVATE_CANCEL')
        client = Client([answer(NS(input_tokens=10, output_tokens=100, total_tokens=110))])
        budget = meter(client, on_failure=bad_notify, on_block=bad_cancel)
        with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
        report = budget.report(); self.assertEqual(calls, ['notify', 'cancel'])
        self.assertEqual(report['charged_tokens'], 110)
        self.assertEqual(report['terminal_failure']['notification_error_type'], 'OSError')
        self.assertEqual(report['terminal_failure']['cancellation_error_type'], 'RuntimeError')
        self.assertNotIn('PRIVATE', json.dumps(report))
        with self.assertRaises(NativeProviderStopped): client.responses.create(**request())

    def test_waiting_concurrent_client_never_dispatches_after_first_failure(self):
        entered, release = threading.Event(), threading.Event()
        first, second = Client([]), Client([answer()])
        def fail(**kwargs): entered.set(); self.assertTrue(release.wait(5)); raise ConnectionError('private')
        first.responses.create = fail
        budget = meter(first); second.base_url = POLICY['base_url']; budget.wrap_client(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            failed = pool.submit(first.responses.create, **request())
            self.assertTrue(entered.wait(5))
            waiting = pool.submit(second.responses.create, **request()); release.set()
            for future in (failed, waiting):
                with self.assertRaises(NativeProviderStopped): future.result(timeout=5)
        self.assertEqual(second.calls, []); self.assertEqual(budget.report()['physical_model_calls'], 1)

    def test_actual_sdk_timeout_and_http_errors_dispatch_once_classify_safely(self):
        try:
            import httpx
            import openai
        except ImportError:
            self.skipTest('Optional real SDK boundary needs openai/httpx; no network is used')
        for mode, classification in (('timeout', 'timeout'), ('connect', 'connection_error'),
                                      (503, 'server_unavailable'), (400, 'other_terminal_failure')):
            with self.subTest(mode=mode):
                seen = []
                def handler(req):
                    seen.append(True)
                    if mode == 'timeout': raise httpx.ReadTimeout('PRIVATE_TIMEOUT', request=req)
                    if mode == 'connect': raise httpx.ConnectError('PRIVATE_CONNECT', request=req)
                    return httpx.Response(mode, json={'error': {'message': 'PRIVATE_BODY', 'type': 'fixture'}}, request=req)
                with openai.OpenAI(api_key='DUMMY_OFFLINE', base_url=POLICY['base_url'],
                    http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
                    budget = meter(client)
                    for _ in range(2):
                        with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
                    self.assertEqual(len(seen), 1)
                    report = budget.report()
                    self.assertEqual(report['terminal_failure']['availability_classification'], classification)
                    self.assertFalse(report['accounting_complete']); self.assertGreater(report['charged_tokens'], 0)
                    self.assertNotIn('PRIVATE', json.dumps(report))


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory()); self.root = Path(self.temp)
        (self.root / 'workspace').mkdir()

    def failure(self, **kwargs):
        client = Client([ConnectionError('PRIVATE_BODY')]); budget = meter(client,
            on_failure=evidence.notifier(self.root, COMPUTER), **kwargs)
        with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
        return budget

    def test_atomic_full_meter_exists_before_cancel_and_does_not_enter_guest_workspace(self):
        seen = []
        budget = self.failure(on_block=lambda reason: seen.append(evidence.read_failure(
            self.root, worker_pid=os.getpid(), computer_id=COMPUTER)))
        payload = evidence.read_failure(self.root)
        self.assertEqual(seen, [payload]); self.assertEqual(payload['evaluation_budget'], budget.report())
        path = self.root / evidence.FILENAME
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list((self.root / 'workspace').iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [evidence.FILENAME, 'workspace'])
        self.assertNotIn('PRIVATE', path.read_text()); self.assertNotIn('DUMMY_OFFLINE', path.read_text())
        self.assertEqual(payload['availability_classification'], 'connection_error')
        before = path.read_bytes()
        with self.assertRaises(ValueError): evidence.notifier(self.root, COMPUTER)
        self.assertEqual(path.read_bytes(), before)

    def test_no_partial_file_visible_at_publish_boundary(self):
        original = os.link; observed = []
        def checked(*args, **kwargs):
            observed.append(evidence.read_failure(self.root))
            # The temporary full JSON is already fsynced and validates before
            # the final name exists; readers cannot see a partial final body.
            temp = self.root / args[0]
            evidence.validate(json.loads(temp.read_bytes()))
            return original(*args, **kwargs)
        with patch.object(evidence.os, 'link', side_effect=checked): self.failure()
        self.assertEqual(observed, [None]); self.assertIsNotNone(evidence.read_failure(self.root))

    def test_symlink_and_changed_root_do_not_overwrite_any_evidence(self):
        target = self.root / 'target'; target.write_text('private sentinel')
        (self.root / evidence.FILENAME).symlink_to(target)
        with self.assertRaises(ValueError): evidence.notifier(self.root, COMPUTER)
        with self.assertRaises(OSError): evidence.read_failure(self.root)
        self.assertEqual(target.read_text(), 'private sentinel')
        (self.root / evidence.FILENAME).unlink()
        notify = evidence.notifier(self.root, COMPUTER)
        original = self.root / 'original'; child = self.root / 'bound'; child.mkdir()
        notify = evidence.notifier(child, COMPUTER); child.rename(original); child.mkdir()
        client = Client([ConnectionError('private')]); budget = meter(client, on_failure=notify)
        with self.assertRaises(NativeProviderStopped): client.responses.create(**request())
        self.assertEqual(budget.report()['terminal_failure']['notification_error_type'], 'ValueError')
        self.assertFalse((child / evidence.FILENAME).exists()); self.assertFalse((original / evidence.FILENAME).exists())

    def test_reader_refuses_fifo_without_writer_and_symlinked_parent(self):
        path = self.root / evidence.FILENAME; os.mkfifo(path)
        with self.assertRaises(ValueError): evidence.read_failure(self.root)
        path.unlink()
        alias = self.root / 'alias'; real = self.root / 'real'; real.mkdir(); alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError): evidence.read_failure(alias)
        with self.assertRaises(ValueError): evidence.notifier(alias, COMPUTER)

    def test_reader_refuses_identity_hash_types_private_fields_and_coherent_cost_tampering(self):
        self.failure(); original = evidence.read_failure(self.root)
        for change in ('pid', 'hash', 'boolean', 'extra', 'cost', 'classification', 'private_row'):
            item = deepcopy(original)
            if change == 'pid': item['worker_pid'] += 1
            elif change == 'hash': item['evaluation_budget_sha256'] = '0' * 64
            elif change == 'boolean': item['schema_version'] = True
            elif change == 'extra': item['prompt'] = 'PRIVATE'
            elif change == 'cost': item['evaluation_budget']['charged_tokens'] = 0
            elif change == 'classification': item['availability_classification'] = 'other_terminal_failure'
            else: item['evaluation_budget']['operations'][0]['response_body'] = 'PRIVATE'
            if change in ('cost', 'private_row'):
                item['evaluation_budget_sha256'] = evidence._digest(item['evaluation_budget'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                evidence.validate(item, worker_pid=os.getpid(), computer_id=COMPUTER)


class WorkerTests(unittest.TestCase):
    def test_native_return_and_exception_both_preserve_failed_meter_and_close_rpc(self):
        from lifespan import hermes_worker
        for mode in ('return', 'unwind', 'local_after_receipt'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                profile = Path(folder) / 'hermes'; profile.mkdir()
                client = Client([answer() if mode == 'local_after_receipt' else ConnectionError('PRIVATE_BODY')])
                client.base_url = POLICY['base_url']
                state = {'closed': False}
                class Agent:
                    def __init__(self, **kwargs):
                        self.tools = []; self.client = client; self.api_mode = 'codex_responses'; self.max_iterations = 2
                        self._ensure_primary_openai_client = self._create_request_openai_client = lambda **kw: client
                    def interrupt(self, reason, **kwargs):
                        state['notification_at_cancel'] = evidence.read_failure(Path(folder))
                        state['hard_cancel'] = kwargs['hard_cancel']
                    def run_conversation(self, *args, **kwargs):
                        try: self.client.responses.create(**request())
                        except NativeProviderStopped:
                            if mode == 'unwind': raise
                        if mode == 'local_after_receipt': raise ValueError('PRIVATE_LOCAL_ERROR')
                        return {'failed': False, 'messages': []}
                sandbox = NS(sandbox=NS(process=NS(pid=1), rpc_socket='fixture'),
                    cleanup=lambda: state.update(closed=True))
                terminal = NS(terminal_tool=lambda **kw: json.dumps({'exit_code': 0, 'output': '/workspace\nfixture\n'}),
                    register_task_env_overrides=lambda *a: None, _active_environments={'default': sandbox})
                modules = {'tools': NS(skills_tool=NS()), 'tools.registry': NS(registry=NS(register=lambda **kw: None)),
                    'toolsets': NS(create_custom_toolset=lambda *a, **kw: None),
                    'run_agent': NS(AIAgent=Agent, IterationBudget=lambda count: object()),
                    'hermes_state': NS(SessionDB=lambda: None), 'tools.terminal_tool': terminal,
                    'lifespan.bubblewrap': NS(install_hermes_backend=lambda root: sandbox),
                    'lifespan.evaluation.hermes_transport': NS(install=lambda *a, **kw: {'fixture': True})}
                execution = {'mode': 'evaluation', 'hermes_transport': 'nonstreaming', 'provider_contract': POLICY}
                env = {'HERMES_HOME': str(profile), 'LIFESPAN_EMPLOYEE': 'fixture', 'LIFESPAN_MODEL': POLICY['model'],
                    'LIFESPAN_API_KEY': 'PRIVATE_CREDENTIAL', 'LIFESPAN_BASE_URL': POLICY['base_url'],
                    'LIFESPAN_SANDBOX': 'bubblewrap', 'LIFESPAN_EXECUTION_CONFIG': json.dumps(execution)}
                with patch.dict(sys.modules, modules), patch.dict(os.environ, env), \
                    patch('sys.stdout', io.StringIO()) as output, patch('sys.stderr', io.StringIO()), \
                    patch('sys.stdin', io.StringIO('{"kind":"run","prompt":"PRIVATE_REQUEST"}\n{"kind":"close"}\n')):
                    hermes_worker._main()
                records = [json.loads(line) for line in output.getvalue().splitlines()]
                result = records[1]['result']
                self.assertEqual([row['kind'] for row in records], ['ready', 'result', 'closed'])
                self.assertTrue(result['failed']); self.assertTrue(state['closed'])
                self.assertEqual(result['evaluation_budget']['physical_model_calls'], 1)
                if mode == 'local_after_receipt':
                    self.assertEqual(result['error_type'], 'ValueError')
                    self.assertTrue(result['evaluation_budget']['accounting_complete'])
                    self.assertEqual(result['evaluation_budget']['reported_tokens'], 15)
                    self.assertFalse(result['evaluation_budget']['stopped'])
                    self.assertIsNone(evidence.read_failure(Path(folder)))
                    self.assertNotIn('hard_cancel', state)
                    self.assert_runtime_rejects_with_known_costs(result, Path(folder) / 'runtime')
                else:
                    self.assertTrue(result['interrupted']); self.assertTrue(state['hard_cancel'])
                    self.assertIsNotNone(state['notification_at_cancel'])
                    self.assertFalse(result['evaluation_budget']['accounting_complete'])
                    self.assertEqual(result['evaluation_budget'], evidence.read_failure(Path(folder))['evaluation_budget'])
                self.assertNotIn('PRIVATE', json.dumps(records[1]))

    def assert_runtime_rejects_with_known_costs(self, native, root):
        from lifespan.ecosystem import Ecosystem
        from lifespan.evaluation import runtime
        from lifespan.evaluation.hermes_transport import contract
        from lifespan.evaluation.tasks import make_case
        from lifespan.world import Task
        world = Ecosystem(16, 101).worlds['firm-0']
        task = Task('failure-fixture', 'onboarding', 'regulated', 'onboarding-regulated', 'consumer-0', 0, 3, 10)
        world.tasks[task.id] = task
        native = deepcopy(native); native['evaluation_transport'] = contract('nonstreaming')
        with patch.object(runtime.Computer, 'start', return_value={'tool_names': [],
            'evaluation_transport': native['evaluation_transport'], 'provider_contract': POLICY}), \
             patch.object(runtime.Computer, 'run', return_value={'native': native}), \
             patch.object(runtime.Computer, 'close'):
            record = runtime.execute_case(root=root, employee='firm-0__onboarding-regulated', world=world,
                task_id=task.id, case=make_case('onboarding', 101, 0, task.id), request='Offline fixture.',
                skill='Fixture skill.', credentials={'model': POLICY['model'], 'base_url': POLICY['base_url'],
                    'provider_profile': POLICY['profile']}, objectives={},
                hermes_transport='nonstreaming', provider_profile=POLICY['profile'])
        self.assertFalse(record['infrastructure_valid']); self.assertFalse(record['budget_exhausted'])
        self.assertTrue(record['usage']['complete']); self.assertEqual(record['usage']['total_tokens'], 15)
        self.assertEqual(json.loads((root / 'session.json').read_bytes()), record)


if __name__ == '__main__':
    unittest.main()
