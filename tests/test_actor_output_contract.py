"""Offline contract fixtures. Mock HTTP is not native integration evidence.

The tested override is explicitly loaded from this checkout. Native method
fixtures are compiled from the tracked patch applied to pinned upstream source;
no installed server modules or active actor artifacts are changed.
"""
import ast
import asyncio
from copy import deepcopy
from datetime import datetime
from enum import Enum
import importlib.util
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from threading import Event, Thread, RLock
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.actor_contract import wire, descriptor, options, verify_record, verify_support
from lifespan.mirofish import MiroFishRuntime

PKG = '_actor_override_fixture'
pkg = ModuleType(PKG)
pkg.__path__ = [str(ROOT / 'local-overrides/backend/app/utils')]
sys.modules[PKG] = pkg
sys.modules[PKG + '.actor_output_contract'] = wire
spec = importlib.util.spec_from_file_location(PKG + '.camel_responses', Path(pkg.__path__[0]) / 'camel_responses.py')
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

CONFIG = {'version': wire.VERSION, 'max_output_tokens': 512, 'timeout_seconds': 120}
TOOLS = [{'type': 'function', 'function': {'name': 'create_post', 'parameters': {'type': 'object', 'properties': {}}}}]
EXAMPLE = {'delegate': True, 'request': 'Read the files.', 'working_notes': '',
           'share_document_ids': [], 'colleague_messages': [], 'process_proposal': None}


def actor_dir(tmp_path):
    directory = tmp_path / 'sim_fixture'
    directory.mkdir()
    (directory / 'simulation_config.json').write_text(json.dumps({'agent_configs': [
        {'agent_id': 0, 'entity_type': 'Employee'}, {'agent_id': 1, 'entity_type': 'GovernmentAgency'}]}))
    (directory / 'reddit_profiles.json').write_text(json.dumps([{'username': 'firm-0__renewal'}, {'username': 'agency'}]))
    with sqlite3.connect(directory / 'reddit_simulation.db') as db:
        db.execute('CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT, created_at TEXT)')
    return directory


def model(responder):
    instance = object.__new__(bridge.OpenAIResponsesModel)
    instance.model_type = 'gpt-5.6-luna'
    instance.model_config_dict = {'reasoning_effort': 'low'}
    instance._items_by_call, instance._items_lock = {}, RLock()
    instance._log_enabled = False
    instance._async_client = AsyncOpenAI(api_key='offline-test-key',
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(responder)))
    return instance


def response(text, *, status='completed', usage=None):
    return {'id': 'resp_fixture', 'object': 'response', 'created_at': 1, 'status': status,
        'model': 'gpt-5.6-luna', 'output': [{'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
        'status': 'completed', 'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
        'incomplete_details': {'reason': 'max_output_tokens'} if status == 'incomplete' else None,
        'usage': usage or {'input_tokens': 10, 'output_tokens': 50, 'total_tokens': 60,
            'input_tokens_details': {'cached_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 2}}}


def write_trace(directory, agent_id, prompt, text):
    with sqlite3.connect(directory / 'reddit_simulation.db') as db:
        db.execute('INSERT INTO trace VALUES (?, ?, ?, ?)',
            (agent_id, 'interview', json.dumps({'prompt': prompt, 'response': text}), 'same-timestamp'))


async def native_fixture(directory, instance, *, agent_id=0, role='employee', prompt='fixture', original='fixture', request_key=None):
    request_key = request_key or wire.text_hash('fixture-agent-' + str(agent_id))
    contract = descriptor(CONFIG, role)
    binding = wire.bind_request(directory, agent_id, original, prompt, contract, request_key)
    with wire.interview_scope(directory, agent_id, prompt, binding) as scope:
        before = wire.trace_cursor(directory)
        # Same asyncio task handoff as OASIS env.step -> gather -> interview -> CAMEL.
        async def interview():
            completion = await instance.arun([{'role': 'user', 'content': prompt}], tools=TOOLS)
            text = completion.choices[0].message.content
            write_trace(directory, agent_id, prompt, text)
        await asyncio.gather(interview())
        result = wire.contracted_trace_result(directory, agent_id, prompt, before)
        result['actor_output_receipt'] = scope.finish(result)
        return {'employee_id': binding['actor'], 'prompt': original, 'response': result['response'],
                'output_contract': contract, 'contract_request_key': request_key, 'native_result': {'success': True, 'agent_id': agent_id,
                'prompt': prompt, 'result': result}}


def verify(record):
    return verify_record(record, actor=record['employee_id'], agent_id=record['native_result']['agent_id'],
        simulation_id='sim_fixture', original_prompt=record['prompt'], contract=record['output_contract'], request_key=record['contract_request_key'])


def test_server_owned_schemas_and_role_identity(tmp_path):
    directory = actor_dir(tmp_path)
    with pytest.raises(wire.ContractError, match='role_identity'):
        wire.bind_request(directory, 0, 'x', 'x', descriptor(CONFIG, 'government'), 'a' * 64)
    for field in ('schema', 'receipt_path', 'request_id'):
        with pytest.raises(wire.ContractError, match='invalid_contract_fields'):
            wire.normalize_contract({**descriptor(CONFIG, 'employee'), field: '../../unsafe'})
    with pytest.raises(wire.ContractError):
        wire.simulation_path(tmp_path, '../outside')
    for role in wire.ROLE_TYPES.values():
        schema = wire.role_schema(role)
        assert schema['required'] == list(schema['properties']) and schema['additionalProperties'] is False
        assert 'anyOf' not in schema
    assert wire.shape_valid(json.dumps(EXAMPLE), 'employee')
    assert not wire.shape_valid(json.dumps({**EXAMPLE, 'extra': 1}), 'employee')
    assert not wire.shape_valid(json.dumps(EXAMPLE)[:-1], 'employee')
    assert not wire.shape_valid('{"delegate":true,"delegate":false}', 'employee')
    gov = {'notes': '', 'reason': '', 'evidence_ids': [], 'policy': 'keep', 'duration': 3}
    for value in (True, 11, float('nan'), float('inf')):
        assert not wire.shape_valid(json.dumps({**gov, 'duration': value}), 'government')


@pytest.mark.parametrize('value', [True, 255, 8193, None, '512'])
def test_output_cap_validated(value):
    with pytest.raises(wire.ContractError):
        options({**CONFIG, 'max_output_tokens': value})


def test_concurrent_scopes_and_ordinary_tools_preserve_settings(tmp_path):
    directory = actor_dir(tmp_path)
    requests = []
    employee = json.dumps({**EXAMPLE, 'working_notes': 'Braces { } quote " slash \\ newline\n unicode Ω'})
    government = json.dumps({'notes': '', 'reason': '', 'evidence_ids': [], 'policy': 'keep', 'duration': 3})
    async def respond(request):
        data = json.loads(request.content); requests.append(data)
        await asyncio.sleep(0)
        role = data.get('text', {}).get('format', {}).get('name')
        return httpx.Response(200, json=response(government if role == 'actor_government_v1' else employee))
    instance = model(respond)
    original = deepcopy(instance.model_config_dict)
    async def run():
        a, b, legacy = await asyncio.gather(
            native_fixture(directory, instance, prompt='employee'),
            native_fixture(directory, instance, agent_id=1, role='government', prompt='government'),
            instance.arun([{'role': 'user', 'content': 'ordinary'}], tools=TOOLS))
        assert a['response'] == employee and b['response'] == government
        assert verify(a)['output_schema_valid'] is True and verify(b)['output_schema_valid'] is True
        assert wire.CURRENT.get() is None
    asyncio.run(run())
    assert instance.model_config_dict == original
    assert len(requests) == 3
    for request in requests:
        if 'text' in request:
            assert 'tools' not in request and request['max_output_tokens'] == 512
            assert request['text']['format']['strict'] is True
        else:
            assert request['tools'][0]['name'] == 'create_post' and request['max_output_tokens'] == 8192


@pytest.mark.parametrize('mode', ['incomplete', 'timeout', 'overrun_partial_usage', 'inconsistent_usage'])
def test_failures_preserve_independent_costs_and_never_retry(tmp_path, mode):
    directory = actor_dir(tmp_path)
    calls = []
    async def respond(request):
        calls.append(request)
        if mode == 'timeout':
            raise httpx.ReadTimeout('private provider detail must not be echoed')
        usage = {'input_tokens': 10, 'output_tokens': 50, 'total_tokens': 999,
                 'input_tokens_details': {'cached_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 0}}
        if mode == 'overrun_partial_usage':
            usage.update(input_tokens=None, output_tokens=9000, total_tokens=None)
        return httpx.Response(200, json=response(json.dumps(EXAMPLE),
            status='incomplete' if mode == 'incomplete' else 'completed',
            usage=usage if mode in ('inconsistent_usage', 'overrun_partial_usage') else None))
    with pytest.raises((wire.ContractError, ValueError)):
        record = asyncio.run(native_fixture(directory, model(respond)))
        verify(record)
    receipt = json.loads(next((directory / 'actor_contract_receipts').glob('*.json')).read_text())
    assert len(calls) == receipt['physical_requests_dispatched'] == 1
    assert 'private provider detail' not in json.dumps(receipt)
    if mode == 'timeout':
        assert receipt['error_class'] == 'APITimeoutError'
        assert receipt['reserved_output_tokens'] == 512 and receipt['total_tokens'] is None
    elif mode == 'overrun_partial_usage':
        assert receipt['output_tokens'] == 9000 and receipt['input_tokens'] is None
        assert receipt['reserved_output_tokens'] == 512
    elif mode == 'inconsistent_usage':
        assert receipt['input_tokens'] == 10 and receipt['output_tokens'] == 50 and receipt['total_tokens'] == 999
        assert receipt['accounting_complete'] is False
    with pytest.raises(wire.ContractError, match='already_exists'):
        asyncio.run(native_fixture(directory, model(respond)))
    assert len(calls) == 1


def test_invalid_output_is_not_salvaged_and_repair_remains_capped(tmp_path):
    from lifespan.ecosystem_run import native_decision
    directory = actor_dir(tmp_path)
    malformed = json.dumps(EXAMPLE)[:-1]
    record = asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=response(malformed)))))
    assert record['response'] == malformed and verify(record)['output_schema_valid'] is False
    calls = []
    class Fixture:
        def interview(self, actor, prompt, key):
            calls.append(key)
            return malformed
    with pytest.raises(ValueError):
        native_decision(Fixture(), 'employee', 'request', 'case', lambda _: None)
    assert calls == ['case', 'case-repair']


def test_wire_shape_never_bypasses_business_validation():
    from lifespan.ecosystem_run import native_decision
    calls = []
    class Fixture:
        def interview(self, actor, prompt, key):
            calls.append(key)
            return json.dumps(EXAMPLE)
        def validate_output_contract(self, raw, actor):
            assert wire.shape_valid(raw, 'employee')
    def business(_):
        raise ValueError('Fixture authority rejected')
    with pytest.raises(ValueError, match='authority rejected'):
        native_decision(Fixture(), 'employee', 'request', 'case', business)
    assert len(calls) == 2


def test_trace_boundary_blocks_stale_or_ambiguous_output(tmp_path):
    directory = actor_dir(tmp_path)
    write_trace(directory, 0, 'previous', '{}')
    cursor = wire.trace_cursor(directory)
    with pytest.raises(wire.ContractError, match='not_unique'):
        wire.contracted_trace_result(directory, 0, 'current', cursor)
    write_trace(directory, 0, 'wrong', '{}')
    with pytest.raises(wire.ContractError, match='prompt_mismatch'):
        wire.contracted_trace_result(directory, 0, 'current', cursor)
    write_trace(directory, 0, 'current', '{}')
    with pytest.raises(wire.ContractError, match='not_unique'):
        wire.contracted_trace_result(directory, 0, 'current', cursor)


@pytest.mark.parametrize('target', ['contract', 'actor', 'original_prompt', 'schema', 'support', 'output', 'trace', 'usage', 'deadline', 'uncontracted'])
def test_client_rejects_cache_receipt_tampering(tmp_path, target):
    record = asyncio.run(native_fixture(actor_dir(tmp_path), model(lambda _: httpx.Response(200, json=response(json.dumps(EXAMPLE))))))
    r = record['native_result']['result']['actor_output_receipt']
    if target == 'contract': record['output_contract']['max_output_tokens'] = 1024
    elif target == 'actor': r['binding']['actor'] = 'agency'
    elif target == 'original_prompt': r['binding']['original_prompt_sha256'] = '0' * 64
    elif target == 'schema': r['binding']['schema_sha256'] = '0' * 64
    elif target == 'support': r['binding']['support_sha256'] = '0' * 64
    elif target == 'output': record['response'] += '}'
    elif target == 'trace': record['native_result']['result']['trace_rowid'] = 0
    elif target == 'usage': r['accounting_complete'] = False
    elif target == 'deadline': r['deadline_valid'] = False
    else: del record['output_contract']
    with pytest.raises((wire.ContractError, KeyError)):
        verify(record)


def test_old_server_and_worker_fail_before_dispatch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(MiroFishRuntime, 'call', lambda self, path: calls.append(path) or {})
    with pytest.raises(wire.ContractError, match='support_mismatch'):
        MiroFishRuntime(tmp_path / 'client', actor_output_contract=CONFIG)
    assert calls == ['/api/simulation/actor-contract-support']
    directory = actor_dir(tmp_path)
    (directory / 'env_status.json').write_text('{"status":"alive"}')
    with pytest.raises(wire.ContractError, match='worker_contract_support'):
        wire.require_worker_support(directory)
    (directory / 'env_status.json').write_text(json.dumps({'status': 'alive', 'actor_output_contract': wire.capabilities()}))
    wire.require_worker_support(directory)
    verify_support(wire.capabilities())


def test_http_timeout_does_not_cancel_native_receipt_or_allow_client_retry(tmp_path, monkeypatch):
    directory = actor_dir(tmp_path)
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def respond(_):
            started.set(); await release.wait()
            return httpx.Response(200, json=response(json.dumps(EXAMPLE)))
        task = asyncio.create_task(native_fixture(directory, model(respond)))
        await started.wait()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), .01)
        pending = json.loads(next((directory / 'actor_contract_receipts').glob('*.json')).read_text())
        assert pending['status'] == 'dispatched' and pending['reserved_output_tokens'] == 512
        release.set()
        record = await task
        assert verify(record)['accounting_complete'] is True
    asyncio.run(run())
    runtime = MiroFishRuntime(tmp_path / 'client')
    runtime.actor_output_contract = CONFIG
    runtime.actor_roles = {'firm-0__renewal': 'employee'}
    runtime.employee_ids = {'firm-0__renewal': 0}
    runtime.state = {'simulation': {'simulation_id': 'sim_fixture'}}
    def fail(*args, **kwargs): raise TimeoutError('fixture HTTP deadline')
    monkeypatch.setattr(runtime, 'call', fail)
    with pytest.raises(TimeoutError): runtime.interview('firm-0__renewal', 'fixture', 'request')
    with pytest.raises(RuntimeError, match='refusing automatic replay'):
        runtime.interview('firm-0__renewal', 'fixture', 'request')
    ledger = json.loads((runtime.out / 'evaluation_interview_ledger.json').read_text())
    assert ledger['requests'][0]['reserved_output_tokens'] == 512
    assert ledger['requests'][0]['physical_model_calls'] is None


@pytest.fixture(scope='session')
def patched_backend(tmp_path_factory):
    """Apply only the four transport hunks from the actual tracked patch."""
    source = Path(os.environ.get('BIGWORLD_TEST_MIROFISH_SOURCE', ROOT / '.cache/mirofish-contract'))
    if os.environ.get('BIGWORLD_TEST_MIROFISH_SOURCE') and not (source / '.git').exists():
        pytest.fail('Explicit pinned MiroFish test source is missing')
    if not source.exists():
        source = ROOT / 'MiroFish'
    if not (source / '.git').exists():
        pytest.skip('Pinned upstream checkout required for offline native-transport fixtures')
    base = tmp_path_factory.mktemp('patched-native-source')
    paths = ['backend/' + key for key in wire.capabilities()['transport_sha256']]
    for relative in paths:
        target = base / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', '-C', str(source), 'show',
            '39d849138ef254f6c737ab4c4705e5545dbe31d4:' + relative]))
    subprocess.run(['git', 'apply', *['--include=' + name for name in paths],
                    str(ROOT / 'patches/mirofish-local.patch')], cwd=base, check=True, capture_output=True)
    wire.require_transport_support(base / 'backend')
    for path in (base / 'backend').rglob('*.py'):
        compile(path.read_text(), str(path), 'exec')
    return base / 'backend'


def test_logical_keys_distinguish_repeat_prompts_and_consume_duplicates(tmp_path):
    directory = actor_dir(tmp_path)
    calls = []
    def respond(_):
        calls.append(1)
        return httpx.Response(200, json=response(json.dumps(EXAMPLE)))
    instance = model(respond)
    a = asyncio.run(native_fixture(directory, instance, request_key='a' * 64))
    b = asyncio.run(native_fixture(directory, instance, request_key='b' * 64))
    assert verify(a)['binding']['request_id'] != verify(b)['binding']['request_id']
    with pytest.raises(wire.ContractError, match='already_exists'):
        asyncio.run(native_fixture(directory, instance, request_key='a' * 64))
    assert len(calls) == 2


def test_full_patched_api_ipc_database_client_path(patched_backend, tmp_path, monkeypatch):
    """Actual patched transport methods, fake OASIS actors and mock provider."""
    from flask import Flask, Blueprint, jsonify, request
    import traceback
    directory = actor_dir(tmp_path)
    text = json.dumps({**EXAMPLE, 'working_notes': 'Delimited { } \\ " newline\n Ω'}, ensure_ascii=False)
    requests = []
    def respond(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200, json=response(text))
    instance = model(respond)
    agent = type('FixtureNativeAgent', (), {})()
    agent.model_backend = SimpleNamespace(models=[instance])
    env_steps = []
    class FakeEnv:
        async def step(self, actions):
            env_steps.append(1)
            async def interview(action):
                prompt = action.action_args['prompt']
                completion = await instance.arun([{'role': 'user', 'content': prompt}], tools=TOOLS)
                write_trace(directory, 0, prompt, completion.choices[0].message.content)
            await asyncio.gather(*(interview(action) for action in actions.values()))
    class ActionType(Enum): INTERVIEW = 'interview'
    class CommandType: INTERVIEW = 'interview'; BATCH_INTERVIEW = 'batch_interview'; CLOSE_ENV = 'close_env'
    # Explicit temporary aliases are required by the native handler's imports.
    for name in ('app', 'app.utils', 'app.services', 'app.api'):
        module = ModuleType(name); module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, 'app.utils.actor_output_contract', wire)
    monkeypatch.setitem(sys.modules, 'app.utils.camel_responses', bridge)
    logger = ModuleType('app.utils.logger'); logger.get_logger = lambda _: logging.getLogger('offline-contract')
    monkeypatch.setitem(sys.modules, 'app.utils.logger', logger)
    path = patched_backend / 'scripts/run_reddit_simulation.py'
    tree = ast.parse(path.read_text())
    ns = dict(__file__=str(path), os=os, json=json, sqlite3=sqlite3, datetime=datetime,
        Dict=Dict, Any=Any, List=List, Optional=Optional, ActionType=ActionType,
        CommandType=CommandType, ManualAction=lambda **kw: SimpleNamespace(**kw),
        IPC_COMMANDS_DIR='ipc_commands', IPC_RESPONSES_DIR='ipc_responses', ENV_STATUS_FILE='env_status.json')
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'IPCHandler'], type_ignores=[]), str(path), 'exec'), ns)
    handler = ns['IPCHandler'](str(directory), FakeEnv(), SimpleNamespace(get_agent=lambda _: agent))
    handler.update_status('alive')
    # Import the real file-based IPC module, with only its logger stubbed.
    path = patched_backend / 'app/services/simulation_ipc.py'
    spec = importlib.util.spec_from_file_location('app.services.simulation_ipc', path)
    ipc = importlib.util.module_from_spec(spec); monkeypatch.setitem(sys.modules, spec.name, ipc); spec.loader.exec_module(ipc)
    path = patched_backend / 'app/services/simulation_runner.py'
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SimulationRunner')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'interview_agent']
    ns = dict(os=os, Dict=Dict, Any=Any, SimulationIPCClient=ipc.SimulationIPCClient, logger=logging.getLogger('offline'))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), ns)
    runner = ns['SimulationRunner']; runner.RUN_STATE_DIR = str(tmp_path)
    runner.check_env_alive = lambda _: True
    path = patched_backend / 'app/api/simulation.py'
    tree = ast.parse(path.read_text())
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
        ('optimize_interview_prompt', 'actor_contract_support', 'interview_agent')]
    # Preserve the actual pinned optimization prefix as part of this wire test.
    selected = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INTERVIEW_PROMPT_PREFIX' for t in n.targets)] + selected
    bp = Blueprint('contract_fixture', __name__)
    ns = dict(__file__=str(path), __package__='app.api', os=os, simulation_bp=bp, request=request,
        jsonify=jsonify, SimulationRunner=runner, traceback=traceback, logger=logging.getLogger('offline'), t=lambda value, **_: value)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), ns)
    app = Flask(__name__); app.register_blueprint(bp, url_prefix='/api/simulation')
    stopped = Event()
    async def pump():
        while not stopped.is_set():
            await handler.process_commands()
            await asyncio.sleep(.005)
    thread = Thread(target=lambda: asyncio.run(pump()), daemon=True); thread.start()
    try:
        client = app.test_client()
        verify_support(client.get('/api/simulation/actor-contract-support').json['data'])
        original = 'Fixture request { } " \\ Ω\nsecond line'
        payload = client.post('/api/simulation/interview', json={'simulation_id': directory.name, 'agent_id': 0,
            'prompt': original, 'platform': 'reddit', 'timeout': 5, 'output_contract': descriptor(CONFIG, 'employee'),
            'contract_request_key': 'c' * 64}).json
        assert payload['success'] is True
        record = {'employee_id': 'firm-0__renewal', 'prompt': original, 'response': text,
            'contract_request_key': 'c' * 64, 'output_contract': descriptor(CONFIG, 'employee'), 'native_result': payload['data']}
        receipt = verify(record)
        assert receipt['output_schema_valid'] is True
        assert receipt['provider_input_sha256'] == wire.digest(requests[0]['input'])
        assert receipt['binding']['original_prompt_sha256'] != receipt['binding']['native_prompt_sha256']
        # Both native payload forms are verified; neither silently loses a receipt.
        nested = deepcopy(record); nested['native_result']['result'] = {'reddit': nested['native_result']['result']}
        assert verify(nested) == receipt
        runtime = MiroFishRuntime(tmp_path / 'client')
        runtime.actor_output_contract = CONFIG; runtime.actor_roles = {'firm-0__renewal': 'employee'}
        runtime.employee_ids = {'firm-0__renewal': 0}; runtime.state = {'simulation': {'simulation_id': directory.name}}
        key = 'next-request'; next_key = wire.text_hash(key)
        returned = client.post('/api/simulation/interview', json={'simulation_id': directory.name, 'agent_id': 0,
            'prompt': original, 'platform': 'reddit', 'timeout': 5, 'output_contract': descriptor(CONFIG, 'employee'),
            'contract_request_key': next_key}).json['data']
        returned['result'] = {'reddit': returned['result']}
        monkeypatch.setattr(runtime, 'call', lambda *a, **kw: returned)
        assert runtime.interview('firm-0__renewal', original, key) == text
        monkeypatch.setattr(runtime, 'call', lambda *a, **kw: pytest.fail('Cache made a new request'))
        assert runtime.interview('firm-0__renewal', original, key) == text
        assert len(requests) == 2
        # Same logical request cannot cause another physical call.
        duplicate = client.post('/api/simulation/interview', json={'simulation_id': directory.name, 'agent_id': 0,
            'prompt': original, 'platform': 'reddit', 'timeout': 5, 'output_contract': descriptor(CONFIG, 'employee'),
            'contract_request_key': 'c' * 64}).json
        assert duplicate['success'] is False and len(requests) == 2
        agent.model_backend = SimpleNamespace(models=[object()])
        unsupported = client.post('/api/simulation/interview', json={'simulation_id': directory.name, 'agent_id': 0,
            'prompt': original, 'platform': 'reddit', 'timeout': 5, 'output_contract': descriptor(CONFIG, 'employee'),
            'contract_request_key': 'e' * 64}).json
        assert unsupported['success'] is False and len(requests) == len(env_steps) == 2
    finally:
        stopped.set(); thread.join(timeout=3)
        assert not thread.is_alive()


def test_partial_transport_install_rejected(patched_backend, tmp_path):
    import shutil
    copy = tmp_path / 'backend'; shutil.copytree(patched_backend, copy)
    path = copy / 'app/services/simulation_ipc.py'
    path.write_text(path.read_text().replace("args['output_contract'] = output_contract", 'pass'))
    with pytest.raises(wire.ContractError, match='source_mismatch'):
        wire.require_transport_support(copy)


def test_config_is_opt_in_and_provenance_is_explicit():
    from lifespan.evaluation.protocol import ExperimentConfig, scenario
    from lifespan.actor_contract import provenance
    config = ExperimentConfig()
    assert config.actor_output_contract is None and 'actor_output_contract' not in scenario(config)
    configured = ExperimentConfig(actor_output_contract=CONFIG)
    assert scenario(configured)['actor_output_contract'] == CONFIG
    meta = provenance(CONFIG)
    assert meta['support']['transport_sha256'] and len(meta['tracked_patch_sha256']) == 64
    assert 'bootstrap_and_social_calls_are_not_metered' in meta['accounting_scope']


@pytest.mark.parametrize('change', ['prompt', 'contract', 'actor'])
def test_spent_native_logical_key_cannot_change_binding(tmp_path, change):
    directory = actor_dir(tmp_path)
    record = asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=response(json.dumps(EXAMPLE)))),
                                         request_key='d' * 64))
    contract = descriptor(CONFIG, 'employee'); prompt = 'fixture'; agent = 0
    if change == 'prompt': prompt = 'different prompt'
    elif change == 'contract': contract['max_output_tokens'] = 256
    else: contract = descriptor(CONFIG, 'government'); agent = 1
    binding = wire.bind_request(directory, agent, prompt, prompt, contract, 'd' * 64)
    assert binding['request_id'] != verify(record)['binding']['request_id']
    with pytest.raises(wire.ContractError, match='already_exists'):
        wire.InterviewScope(directory, agent, prompt, binding)


def test_actor_window_must_fit_remaining_run_budget(tmp_path, monkeypatch):
    import time
    runtime = MiroFishRuntime(tmp_path)
    runtime.actor_output_contract = CONFIG; runtime.actor_roles = {'employee': 'employee'}
    runtime.employee_ids = {'employee': 0}; runtime.state = {'simulation': {'simulation_id': 'fixture'}}
    runtime.evaluation_deadline = time.monotonic() + 30
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: pytest.fail('Dispatched beyond remaining budget'))
    with pytest.raises(TimeoutError, match='does not fit'):
        runtime.interview('employee', 'fixture', 'request')
    assert not (tmp_path / 'evaluation_interview_ledger.json').exists()


def test_audit_checks_opt_in_receipts_and_source_binding(tmp_path, monkeypatch):
    from lifespan.actor_contract import audit_interviews, provenance
    directory = actor_dir(tmp_path)
    key = 'audit-fixture'
    record = asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=response(json.dumps(EXAMPLE)))),
        request_key=wire.text_hash(key)))
    runtime = MiroFishRuntime(tmp_path / 'run/actors')
    runtime.actor_output_contract = CONFIG; runtime.actor_roles = {'firm-0__renewal': 'employee'}
    runtime.employee_ids = {'firm-0__renewal': 0}; runtime.state = {'simulation': {'simulation_id': directory.name}}
    runtime.state_path.write_text(json.dumps(runtime.state))
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: record['native_result'])
    runtime.interview('firm-0__renewal', 'fixture', key)
    manifest = {'config': {'actor_output_contract': CONFIG}, 'actor_output_contract_provenance': provenance(CONFIG),
        'source_sha256': __import__('lifespan.evaluation.runner', fromlist=['source_hashes']).source_hashes()}
    participants = [{'id': 'firm-0__renewal', 'entity_type': 'Employee'}]
    result = audit_interviews(tmp_path / 'run', manifest, participants, completed=True)
    assert result['measured_physical_requests'] == 1 and result['measured_tokens'] == 60
    manifest['actor_output_contract_provenance']['tracked_patch_sha256'] = '0' * 64
    with pytest.raises(wire.ContractError, match='source_provenance'):
        audit_interviews(tmp_path / 'run', manifest, participants, completed=True)


@pytest.mark.parametrize('malformed,expected_error', [(None, 'TypeError'), ([{'type': 'message', 'content': None}], 'KeyError')])
def test_malformed_received_output_retains_known_usage(tmp_path, malformed, expected_error):
    directory = actor_dir(tmp_path)
    body = response(json.dumps(EXAMPLE)); body['output'] = malformed
    with pytest.raises(wire.ContractError, match='provider_failure'):
        asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=body))))
    receipt = json.loads(next((directory / 'actor_contract_receipts').glob('*.json')).read_text())
    assert receipt['physical_requests_dispatched'] == 1 and receipt['status'] == 'failed'
    assert receipt['input_tokens'] == 10 and receipt['output_tokens'] == 50 and receipt['total_tokens'] == 60
    assert receipt['accounting_complete'] is True and receipt['reserved_output_tokens'] == 0
    assert receipt['output_sha256'] is None
    assert receipt['error_class'] == expected_error


@pytest.mark.parametrize('config', [None, CONFIG])
def test_native_actor_constructor_forwards_opt_in_without_default_regression(tmp_path, monkeypatch, config):
    from lifespan.evaluation import runner
    from lifespan.ecosystem import Ecosystem
    calls = []
    class FixtureRuntime:
        def __init__(self, out, *, actor_output_contract=None):
            self.state = {}; calls.append(actor_output_contract)
        def bootstrap(self, blueprint, cohort):
            calls.append(len(blueprint['employees']))
    monkeypatch.setattr(runner, 'MiroFishRuntime', FixtureRuntime)
    (tmp_path / 'persona_cohort.json').write_text('{"personas":[]}')
    eco = Ecosystem(days=12, seed=1)
    spec = {'seed': 1, 'actor_output_contract': config}
    actors = runner.NativeActors(tmp_path, eco, spec)
    assert calls == [config, len(eco.participants())]
    assert actors.runtime.evaluation_max_interviews is None


@pytest.mark.parametrize('location', ['ledger', 'cache', 'returned', 'provenance'])
def test_disabled_option_cannot_hide_contracted_artifacts(tmp_path, location):
    from lifespan.actor_contract import enabled_for_evidence
    manifest = {'config': {}}
    assert enabled_for_evidence(tmp_path, manifest) is False
    if location == 'provenance':
        manifest['actor_output_contract_provenance'] = {'fixture': True}
    else:
        path = tmp_path / 'actors' / {
            'ledger': 'evaluation_interview_ledger.json', 'cache': 'mirofish_interviews/fixture.json',
            'returned': 'actor_returned_receipts/fixture.json'}[location]
        path.parent.mkdir(parents=True)
        legacy = {'requests': [{'key': 'fixture', 'status': 'completed'}]} if location == 'ledger' else {'prompt': 'fixture', 'response': 'fixture'}
        path.write_text(json.dumps(legacy))
        assert enabled_for_evidence(tmp_path, manifest) is False
        marked = {'requests': [{'output_contract': descriptor(CONFIG, 'employee')}]} if location == 'ledger' else {'output_contract': descriptor(CONFIG, 'employee')}
        path.write_text(json.dumps(marked))
    with pytest.raises(wire.ContractError, match='configuration_downgrade'):
        enabled_for_evidence(tmp_path, manifest)


def test_huge_numeric_shape_value_fails_closed():
    value = {'notes': '', 'reason': '', 'evidence_ids': [], 'policy': 'keep', 'duration': 10 ** 400}
    assert not wire.shape_valid(json.dumps(value), 'government')


def test_completed_wire_repair_must_belong_to_original_actor(tmp_path, monkeypatch):
    from lifespan.actor_contract import audit_interviews, provenance
    directory = actor_dir(tmp_path)
    malformed = json.dumps(EXAMPLE)[:-1]
    first = asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=response(malformed))),
        request_key=wire.text_hash('case')))
    government = json.dumps({'notes': '', 'reason': '', 'evidence_ids': [], 'policy': 'keep', 'duration': 3})
    second = asyncio.run(native_fixture(directory, model(lambda _: httpx.Response(200, json=response(government))),
        agent_id=1, role='government', request_key=wire.text_hash('case-repair')))
    runtime = MiroFishRuntime(tmp_path / 'run/actors')
    runtime.actor_output_contract = CONFIG
    runtime.actor_roles = {'firm-0__renewal': 'employee', 'agency': 'government'}
    runtime.employee_ids = {'firm-0__renewal': 0, 'agency': 1}
    runtime.state = {'simulation': {'simulation_id': directory.name}}
    runtime.state_path.write_text(json.dumps(runtime.state))
    records = iter((first, second))
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: next(records)['native_result'])
    runtime.interview('firm-0__renewal', 'fixture', 'case')
    runtime.interview('agency', 'fixture', 'case-repair')
    manifest = {'config': {'actor_output_contract': CONFIG}, 'actor_output_contract_provenance': provenance(CONFIG),
        'source_sha256': __import__('lifespan.evaluation.runner', fromlist=['source_hashes']).source_hashes()}
    roster = [{'id': 'firm-0__renewal', 'entity_type': 'Employee'}, {'id': 'agency', 'entity_type': 'GovernmentAgency'}]
    with pytest.raises(wire.ContractError, match='unresolved_actor_wire_shape'):
        audit_interviews(tmp_path / 'run', manifest, roster, completed=True)


def test_excessive_json_nesting_is_classified_and_keeps_single_repair_cap():
    from lifespan.ecosystem_run import native_decision
    nested = '[' * 2000 + ']' * 2000
    assert wire.shape_valid(nested, 'employee') is False
    calls = []
    class FixtureRuntime:
        def interview(self, actor, prompt, key):
            calls.append(key); return nested
        def validate_output_contract(self, raw, actor):
            if not wire.shape_valid(raw, 'employee'):
                raise ValueError('Fixture wire shape invalid')
    with pytest.raises(ValueError, match='wire shape invalid'):
        native_decision(FixtureRuntime(), 'employee', 'fixture', 'case', lambda _: pytest.fail('Malformed business input'))
    assert calls == ['case', 'case-repair']
