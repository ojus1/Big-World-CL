"""Contract and failure tests use a local fake provider, never native model calls."""
import asyncio
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from aiohttp import ClientSession, ClientPayloadError, web
    from worldlab.fluso import Fluso
except ImportError:
    raise unittest.SkipTest('Install requirements-inference-gateway.txt')

from worldlab import chat_relay
from worldlab.chat_budget_gateway import create_app, encoded, sha
from worldlab.contracts import Budget, TaskRequest, validate_execution
from worldlab.fluso_runtime import (DATA, WORKSPACE, TASK_DIRECTORY, SKILL_PATH, THREAD,
    audit_container, catalog, environment, skill_file, task_prompt)
from test_inference_gateway import serve


def container(image, name, network, mounts, *, entrypoint, cmd, env=()):
    return {'Id': name + '-id', 'Name': '/' + name, 'Image': image,
        'HostConfig': {'NetworkMode': network, 'CapDrop': ['ALL'], 'CapAdd': [], 'Privileged': False,
            'ReadonlyRootfs': True, 'SecurityOpt': ['no-new-privileges'], 'IpcMode': 'private', 'PidMode': '',
            'Tmpfs': {'/tmp': 'rw,nosuid,size=512m'}, 'PidsLimit': 256, 'Memory': 4 * 1024**3, 'NanoCpus': 2 * 10**9},
        'Config': {'User': '1000:1000', 'Entrypoint': entrypoint, 'Cmd': cmd,
            'WorkingDir': '/opt/fluso/agents/dev-harness', 'Env': list(env)},
        'Mounts': [{'Type': 'bind', 'Destination': d, 'Source': s, 'RW': rw} for d, (s, rw) in mounts.items()],
        'State': {'Running': False, 'ExitCode': 0}}


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.mounts = {'/task': ('/public/task', True)}
        self.info = container('pinned-image', 'solver', 'container:relay', self.mounts, entrypoint=[], cmd=[])

    def audit(self, info):
        audit_container(info, image='pinned-image', network='container:relay', mounts=self.mounts, user='1000:1000')

    def test_declared_isolated_configuration(self):
        self.audit(self.info)

    def test_network_privilege_resources_and_mount_tampering(self):
        alterations = [lambda d: d['HostConfig'].update(NetworkMode='host'),
            lambda d: d['HostConfig'].update(Privileged=True), lambda d: d['HostConfig'].update(ReadonlyRootfs=False),
            lambda d: d['HostConfig'].update(CapAdd=['SYS_ADMIN']), lambda d: d['HostConfig'].update(Memory=0),
            lambda d: d['HostConfig'].update(IpcMode='host'), lambda d: d['HostConfig'].update(VolumesFrom=['other']),
            lambda d: d['Config'].update(User='0:0'), lambda d: d.update(Image='other-image'),
            lambda d: d['Mounts'].append({'Type': 'bind', 'Source': '/private', 'Destination': '/private', 'RW': False}),
            lambda d: d['Mounts'][0].update(Source='/private')]
        for index, alter in enumerate(alterations):
            with self.subTest(index=index):
                value = copy.deepcopy(self.info); alter(value)
                with self.assertRaises(ValueError): self.audit(value)

    def test_fixed_origins_and_text_capability_boundaries(self):
        for url in ['https://example.com', 'http://127.0.0.1:8011/v1', 'http://key@localhost']:
            with self.assertRaises(ValueError): Fluso(upstream=url)
        harness = Fluso()
        task = {'source': 'internal_eurobench', 'input_formats': ['.csv'], 'budgets': {}}
        self.assertEqual(harness.unsupported(task), [])
        for changes in [{'source': 'jobbench'}, {'requires_app_state': True},
                        {'input_formats': ['.pdf']}, {'budgets': {'user_turns': 1}}]:
            self.assertTrue(harness.unsupported({**task, **changes}))
        self.assertIn(TASK_DIRECTORY, task_prompt('Write output.txt'))


class HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'attempt'; self.root.mkdir()
        self.workspace = self.root / 'employee/workspace'; self.workspace.mkdir(parents=True)
        self.budget = Budget(model_calls=5, output_tokens=128, total_tokens=2000, seconds=30)
        self.request = TaskRequest('attempt', 'employee', 'Write output.txt.', 'en', self.workspace, 'Check original sources.\n', self.budget)
        self.counter = 0
        self.fail_on_call = None
        async def tokenize(request): return web.json_response({'count': 100})
        async def complete(request):
            self.counter += 1
            if self.counter == self.fail_on_call:
                return web.json_response({'error': 'controlled failure'}, status=502)
            message = {'role': 'assistant', 'content': 'Done.'}
            finish = 'stop'
            if self.counter == 1:
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'read1', 'type': 'function',
                    'function': {'name': 'read', 'arguments': json.dumps({'path': SKILL_PATH})}}]}
                finish = 'tool_calls'
            return web.json_response({'id': f'response-{self.counter}', 'model': 'fixture-model',
                'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 4, 'total_tokens': 104}})
        app = web.Application(); app.router.add_post('/tokenize', tokenize); app.router.add_post('/v1/chat/completions', complete)
        self.server = serve(app)
        self.origin = await self.server.__aenter__()
        self.addAsyncCleanup(self.server.__aexit__, None, None, None)
        self.harness = Fluso(model='fixture-model', upstream=self.origin, tokenizer=self.origin)

    async def fixture_execute(self, request, root, identity):
        root.mkdir()
        write = lambda name, value: (root / name).write_bytes(encoded(value))
        user = 'Native project context.\n' + task_prompt(request.instruction)
        native_request = {**asdict(request), 'workspace': str(request.workspace)}
        plan = {'request': native_request, 'identity': identity, 'prompt': task_prompt(request.instruction),
            'catalog': catalog(self.harness.model, request.budget.output_tokens),
            'environment': environment(self.harness.model, request.budget.seconds),
            'relay': 'fixture-relay', 'solver': 'fixture-solver', 'user': '1000:1000', 'socket': '/private/socket'}
        write('PLAN.json', plan); write('models.json', plan['catalog'])
        (root / 'skill').mkdir(); (root / 'skill/SKILL.md').write_text(skill_file(request.skill))
        relay = container(identity['image'], plan['relay'], 'none', {
            '/run/meter.sock': (plan['socket'], False), '/run/relay.py': (str(Path(chat_relay.__file__).resolve()), False)},
            entrypoint=['python3'], cmd=['/run/relay.py', '--socket', '/run/meter.sock', '--timeout', str(request.budget.seconds)])
        solver = container(identity['image'], plan['solver'], 'container:' + relay['Id'], {
            DATA: (str(root / 'data'), True), '/run/models.json': (str(root / 'models.json'), False),
            WORKSPACE + '/skills/work-process': (str(root / 'skill'), False), TASK_DIRECTORY: (str(request.workspace), True)},
            entrypoint=['/usr/local/bin/bun'], cmd=['harness.ts', 'send', '--thread', THREAD, plan['prompt']],
            env=[k + '=' + v for k, v in plan['environment'].items()])
        write('RELAY_INSPECT.json', relay); write('SOLVER_INSPECT.json', solver); write('TERMINAL_INSPECT.json', solver)
        messages = [{'role': 'user', 'content': [{'type': 'text', 'text': user}]}]
        wire_messages = [{'role': 'user', 'content': user}]
        proxy = create_app(self.origin, self.origin, self.harness.model, request.budget, root / 'meter')
        async with serve(proxy) as url, ClientSession() as client:
            for ordinal in range(3):
                async with client.post(url + '/v1/chat/completions', json={'model': self.harness.model,
                        'messages': wire_messages if ordinal < 2 else [{'role': 'user', 'content': 'Auxiliary title'}],
                        'stream': False, 'max_tokens': 128}) as response:
                    if response.status != 200:
                        try: await response.read()
                        except ClientPayloadError: pass
                        break
                    value = await response.json()
                if ordinal == 2: continue
                choice = value['choices'][0]; part = choice['message']
                content = ([{'type': 'toolCall', 'id': 'read1', 'name': 'read', 'arguments': {'path': SKILL_PATH}}]
                           if ordinal == 0 else [{'type': 'text', 'text': part['content']}])
                messages.append({'role': 'assistant', 'api': 'openai-completions', 'provider': 'pcci', 'model': self.harness.model,
                    'responseId': value['id'], 'content': content, 'stopReason': 'toolUse' if ordinal == 0 else 'stop',
                    'usage': {'input': 100, 'output': 4, 'totalTokens': 104}})
                wire_messages.append(part)
                if ordinal == 0:
                    text = skill_file(request.skill)
                    messages.append({'role': 'toolResult', 'toolCallId': 'read1', 'toolName': 'read',
                                     'isError': False, 'content': [{'type': 'text', 'text': text}]})
                    wire_messages.append({'role': 'tool', 'tool_call_id': 'read1', 'content': text})
        trace = root / 'data/tenants/dev/users/dev-user/sessions/fixture/.fluso-agent-core/session/native.jsonl'
        trace.parent.mkdir(parents=True)
        trace.write_text(''.join(json.dumps({'type': 'message', 'message': m}) + '\n' for m in messages))
        write('CLEANUP.json', [{'argv': ['docker', 'rm', '-f', plan[k]], 'returncode': 0} for k in ('solver', 'relay')])
        result = {'seconds': 1.0, 'exit_code': 0, 'error_type': None, 'cleanup_error': None,
            'trace_files': [str(trace.relative_to(root))], 'meter_sha256': sha((root / 'meter/METER.json').read_bytes()),
            'plan_sha256': sha((root / 'PLAN.json').read_bytes())}
        write('RESULT.json', result)
        return result

    async def run_fixture(self):
        with patch('worldlab.fluso.execute', self.fixture_execute):
            return await asyncio.to_thread(self.harness.run, self.request, self.root)

    def audit(self, receipt):
        self.harness.audit_execution(self.root, {**asdict(self.request), 'workspace': str(self.workspace)}, receipt)

    async def test_completed_receipt_covers_primary_and_auxiliary_calls(self):
        receipt = await self.run_fixture()
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual((receipt['physical_model_calls'], receipt['primary_model_calls'], receipt['other_metered_calls']), (3, 2, 1))
        self.assertEqual(receipt['charged_tokens'], 312)
        validate_execution(receipt, self.budget, self.request.skill)
        self.audit(receipt)

    async def test_changed_receipt_cost_or_trajectory_is_rejected(self):
        receipt = await self.run_fixture()
        for changes in [{'charged_tokens': 1}, {'trajectory': []}, {'other_metered_calls': 0}, {'status': 'budget_exhausted'}]:
            with self.assertRaises(ValueError): self.audit({**receipt, **changes})

    async def test_extra_host_mount_or_provider_override_is_rejected(self):
        receipt = await self.run_fixture()
        path = self.root / 'fluso/SOLVER_INSPECT.json'
        original = json.loads(path.read_bytes())
        value = copy.deepcopy(original); value['Mounts'].append({'Type': 'bind', 'Source': '/private', 'Destination': '/secret', 'RW': False})
        path.write_bytes(encoded(value))
        with self.assertRaisesRegex(ValueError, 'mounted unexpected'): self.audit(receipt)
        value = copy.deepcopy(original); value['Config']['Env'].append('FLUSO_MODEL=unmetered-model')
        path.write_bytes(encoded(value))
        with self.assertRaisesRegex(ValueError, 'environment differs'): self.audit(receipt)

    async def test_cleanup_failure_cannot_be_a_passing_audit(self):
        receipt = await self.run_fixture()
        path = self.root / 'fluso/CLEANUP.json'
        value = json.loads(path.read_bytes()); value[0]['returncode'] = 1; path.write_bytes(encoded(value))
        with self.assertRaisesRegex(ValueError, 'containers were not removed'): self.audit(receipt)

    async def test_provider_failure_retains_reservation_and_stops_dispatch(self):
        self.fail_on_call = 2
        receipt = await self.run_fixture()
        self.assertEqual(receipt['status'], 'infrastructure_error')
        self.assertFalse(receipt['accounting_complete'])
        self.assertEqual(receipt['physical_model_calls'], 2)
        self.assertEqual(receipt['charged_tokens'], 104 + 228)
        self.assertEqual(self.counter, 2)
        with self.assertRaises(ValueError): self.audit(receipt)

    async def test_exhaustion_without_completed_native_proof_is_preserved(self):
        budget = Budget(model_calls=1, output_tokens=128, total_tokens=2000, seconds=30)
        self.request = TaskRequest('attempt', 'employee', self.request.instruction, 'en', self.workspace, self.request.skill, budget)
        receipt = await self.run_fixture()
        self.assertEqual(receipt['status'], 'budget_exhausted_unverified')
        self.assertTrue(receipt['accounting_complete'])
        self.assertEqual((receipt['physical_model_calls'], receipt['charged_tokens']), (1, 104))
        self.assertEqual(self.counter, 1)

    async def test_attempt_directory_cannot_be_reused(self):
        await self.run_fixture()
        with self.assertRaises(FileExistsError): await self.run_fixture()


if __name__ == '__main__': unittest.main()
