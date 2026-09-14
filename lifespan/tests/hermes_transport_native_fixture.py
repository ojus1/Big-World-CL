"""Subprocess-only native parser fixture; temporary HOME and no network allowed.

The parent test selects the existing pinned runtime. No AIAgent constructor,
provider credentials, native work session or model inference is used.
"""
from copy import deepcopy
from dataclasses import asdict
import os
from pathlib import Path
import socket
from types import SimpleNamespace as NS


def no_network(*args, **kwargs):
    raise AssertionError('Native parity fixtures forbid network access')


socket.socket.connect = no_network
socket.create_connection = no_network

try:
    import run_agent
    from agent.codex_runtime import _consume_codex_event_stream
    from agent.transports.codex import ResponsesApiTransport
except ImportError:
    raise SystemExit(77)

from lifespan.evaluation.budget import ResponsesBudget, NativeProviderStopped, install_native_budget
from lifespan.evaluation.hermes_transport import install
from lifespan.tests.test_hermes_transport import Client


def result(status, output):
    return NS(status=status, output=output, model='offline-fixture', id='fixture-response',
        usage=NS(input_tokens=10, output_tokens=5, total_tokens=15),
        error=NS(message='fixture rejection'), incomplete_details=NS(reason='max_output_tokens'))


text = NS(type='message', role='assistant', status='completed',
          content=[NS(type='output_text', text='Fixture final text.')])
tools = [NS(type='reasoning', id='reasoning-fixture', status='completed',
            encrypted_content='opaque-fixture-reasoning', summary=[]),
         NS(type='function_call', id='fc_1', call_id='call_1', name='terminal', arguments='{"command":"pwd"}', status='completed'),
         NS(type='function_call', id='fc_2', call_id='call_2', name='terminal', arguments='{"command":"ls"}', status='completed')]
partial = NS(type='message', role='assistant', status='in_progress',
             content=[NS(type='output_text', text='Fixture partial text.')])
refusal = NS(type='message', role='assistant', status='completed', content=[NS(type='refusal', refusal='Fixture refusal.')])
partial_tool = NS(type='function_call', id='partial_fc', call_id='partial_call',
                  name='terminal', arguments='{"command":', status='in_progress')
cases = [('completed', [text]), ('completed', tools), ('incomplete', [partial]),
         ('completed', [refusal]), ('failed', [text]), ('cancelled', [text]),
         ('incomplete', [partial_tool])]
native_root = Path(os.environ['BIGWORLD_NATIVE_ROOT'])

for status, output in cases:
    answer = result(status, deepcopy(output))
    native_transport = ResponsesApiTransport()
    agent = object.__new__(run_agent.AIAgent)
    agent.api_mode, agent.provider = 'codex_responses', 'custom'
    agent.base_url, agent.session_id = 'https://example.invalid/v1', 'offline-fixture'
    agent._base_url_hostname, agent._base_url_lower = 'example.invalid', agent.base_url
    agent._interrupt_requested = False
    agent._transport_cache = {'codex_responses': native_transport}
    agent.client = Client([answer])
    meter = ResponsesBudget(max_model_calls=4, max_output_tokens=64, max_total_tokens=100000)
    meter.wrap_client(agent.client)
    agent._big_world_budget = meter
    original_method = run_agent.AIAgent._run_codex_stream
    descriptor = install(agent, 'nonstreaming', hermes_root=native_root)
    assert run_agent.AIAgent._run_codex_stream is original_method
    payload = native_transport.build_kwargs('offline-fixture', [{'role': 'user', 'content': 'Fixture request.'}],
        tools=[{'type': 'function', 'function': {'name': 'terminal', 'description': 'Fixture only.',
                'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}}}}}],
        instructions='Fixture instructions.', reasoning_config={'enabled': True, 'effort': 'low'},
        max_tokens=64, base_url=agent.base_url, session_id=agent.session_id)
    payload = native_transport.preflight_kwargs(payload, allow_stream=False,
        is_github_responses=False, sanitize_harmony_tokens=False)
    before = deepcopy(payload)
    returned = agent._run_codex_stream(payload, client=agent.client)
    assert returned is answer and returned.status == status and payload == before
    assert agent.client.calls == [dict(before, stream=False)]
    assert meter.report()['accounting_complete'] is True and meter.report()['charged_tokens'] == 15
    assert meter.report()['operations'][0]['request_stream'] is False
    assert meter.report()['operations'][0]['provider_response_status'] == status
    assert descriptor['mode'] == 'nonstreaming'

    # The same native normalizer receives the final body and the native stream
    # assembler's output. Do not substitute a homegrown chat/tool conversion.
    stream_status = status if status in ('completed', 'incomplete', 'failed') else 'failed'
    events = [NS(type='response.output_item.done', item=item) for item in deepcopy(output)]
    events.append(NS(type='response.'+stream_status, response=answer))
    assembled = _consume_codex_event_stream(events, model='offline-fixture')
    if status in ('failed', 'cancelled'):
        for candidate in (returned, assembled):
            try: native_transport.normalize_response(candidate)
            except RuntimeError: pass
            else: raise AssertionError('Native failed/cancelled status was promoted')
        continue
    normalized = native_transport.normalize_response(returned)
    assert asdict(normalized) == asdict(native_transport.normalize_response(assembled))
    if output == [partial_tool]:
        assert not normalized.tool_calls and normalized.finish_reason == 'incomplete'
    if output is tools or len(output) > 1:
        assert [call.call_id for call in normalized.tool_calls] == ['call_1', 'call_2']
        history = [{'role': 'user', 'content': 'Fixture request.'}, {
            'role': 'assistant', 'content': normalized.content,
            'tool_calls': [{'id': call.id, 'type': 'function', 'function': {
                'name': call.name, 'arguments': call.arguments}} for call in normalized.tool_calls],
            **normalized.provider_data},
            *[{'role': 'tool', 'tool_call_id': call.id, 'content': 'fixture tool output'} for call in normalized.tool_calls]]
        replay = native_transport.convert_messages(history, base_url=agent.base_url)
        assert [item['call_id'] for item in replay if item.get('type') == 'function_call_output'] == ['call_1', 'call_2']
        assert any(item.get('encrypted_content') == 'opaque-fixture-reasoning' for item in replay)

from lifespan.evaluation.provider import provider_contract

# The explicit new profile changes request policy only. Exercise the same
# pinned converters, request preflight and response normalizer without a
# constructor, socket, or provider call.
policy = provider_contract('offline-fixture', 'http://example.invalid/v1')
for status, output in cases:
    answer = result(status, deepcopy(output))
    native_transport = ResponsesApiTransport()
    agent = object.__new__(run_agent.AIAgent)
    agent.api_mode, agent.provider = 'codex_responses', 'custom'
    agent.model, agent.reasoning_config = policy['model'], {'enabled': False}
    agent.base_url, agent.session_id = policy['base_url'], 'offline-profile-fixture'
    agent._base_url_hostname, agent._base_url_lower = 'example.invalid', agent.base_url
    agent._interrupt_requested = False
    agent._transport_cache = {'codex_responses': native_transport}
    agent.client = Client([answer]); agent.client.base_url = policy['base_url'] + '/'
    meter = ResponsesBudget(max_model_calls=4, max_output_tokens=64, max_total_tokens=100000, provider_contract=policy)
    meter.wrap_client(agent.client); agent._big_world_budget = meter
    install(agent, 'nonstreaming', hermes_root=native_root, provider_contract=policy)
    payload = native_transport.build_kwargs(policy['model'], [{'role': 'user', 'content': 'Profile fixture.'}],
        tools=[{'type': 'function', 'function': {'name': 'terminal', 'parameters': {'type': 'object'}}}],
        instructions='Fixture only.', reasoning_config=agent.reasoning_config,
        max_tokens=64, base_url=agent.base_url, session_id=agent.session_id)
    payload = native_transport.preflight_kwargs(payload, allow_stream=False,
        is_github_responses=False, sanitize_harmony_tokens=False)
    before = deepcopy(payload)
    if status in ('failed', 'cancelled'):
        try: agent._run_codex_stream(payload, client=agent.client)
        except NativeProviderStopped: pass
        else: raise AssertionError('Profile must stop before native provider-failure retry')
        returned = answer
        assert meter.stopped
    else:
        returned = agent._run_codex_stream(payload, client=agent.client)
        assert returned is answer
    assert payload == before and 'reasoning' not in payload
    assert agent.client.calls == [{**before, 'stream': False,
        'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}]
    row = meter.report()['operations'][0]
    assert row['provider_contract'] == policy and row['request_base_url'] == policy['base_url']
    assert row['request_model'] == policy['model'] and row['request_api_mode'] == 'responses'
    assert row['provider_response_status'] == status and row['total_tokens'] == 15
    if status in ('failed', 'cancelled'):
        try: native_transport.normalize_response(returned)
        except RuntimeError: pass
        else: raise AssertionError('Profile must retain native terminal failure handling')
    else:
        normalized = native_transport.normalize_response(returned)
        if len(output) > 1:
            assert [call.call_id for call in normalized.tool_calls] == ['call_1', 'call_2']
            followup = native_transport.convert_messages([
                {'role': 'tool', 'tool_call_id': call.id, 'content': 'fixture tool result'}
                for call in normalized.tool_calls], base_url=agent.base_url)
            assert [item['call_id'] for item in followup] == ['call_1', 'call_2']
        if output == [partial_tool]:
            assert not normalized.tool_calls and normalized.finish_reason == 'incomplete'

# Exercise the actual pinned AIAgent.interrupt hard-cancel boundary, without
# its constructor, a conversation, native tools, or a provider request.
import threading
agent = object.__new__(run_agent.AIAgent)
agent.api_mode, agent.provider = 'codex_responses', 'custom'
agent.client = Client([ConnectionError('private offline failure')]); agent.client.base_url = policy['base_url']
agent._ensure_primary_openai_client = agent._create_request_openai_client = lambda **kw: agent.client
agent._hard_interrupt_requested = threading.Event()
agent._execution_thread_id = None
agent._active_children_lock = threading.RLock(); agent._active_children = []
agent.quiet_mode = True
events = []
meter = install_native_budget(agent, max_model_calls=5, max_output_tokens=64,
    provider_contract=policy, on_failure=lambda report: events.append(report))
payload = dict(model=policy['model'], input='Offline cancellation fixture', stream=False, store=False,
    extra_body={'chat_template_kwargs': {'enable_thinking': False}})
try: agent.client.responses.create(**payload)
except NativeProviderStopped: pass
else: raise AssertionError('Provider failure must stop immediately')
assert agent._hard_interrupt_requested.is_set() and agent._interrupt_requested is True
assert agent._pending_redirect is None and agent._interrupt_thread_signal_pending is True
assert len(events) == 1 and events[0]['terminal_failure']['error_type'] == 'ConnectionError'
agent._interrupt_requested = False; agent._hard_interrupt_requested.clear()
for factory in (agent._ensure_primary_openai_client, agent._create_request_openai_client):
    try: factory(reason='fake retry after clearing native interrupt')
    except NativeProviderStopped: pass
    else: raise AssertionError('Meter latch must survive clearing native interrupt')
assert meter.report()['physical_model_calls'] == 1 and len(agent.client.calls) == 1

# Execute the exact pinned conversation-loop InterruptedError handler inside
# a minimal retry loop. Full native constructor/conversation side effects are
# intentionally excluded; the handler's persist/break behavior is real code.
import ast
import time
from agent import conversation_loop
tree = ast.parse((native_root / 'agent/conversation_loop.py').read_text())
handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name) and node.type.id == 'InterruptedError']
assert len(handlers) == 1
fixture = ast.parse('''
def exercise():
    retry_count = 0
    interrupted = False
    final_response = None
    thinking_spinner = None
    while retry_count < 3:
        try:
            agent.client.responses.create(**payload)
        except InterruptedError:
            pass
        except Exception:
            retry_count += 1
    return interrupted, retry_count, final_response
''')
native_try = next(node for node in ast.walk(fixture) if isinstance(node, ast.Try))
native_try.handlers[0] = deepcopy(handlers[0])
persisted = []
agent.client = Client([ConnectionError('private first-dispatch error')]); agent.client.base_url = policy['base_url']
meter = ResponsesBudget(max_model_calls=5, max_output_tokens=64, provider_contract=policy,
    on_block=lambda reason: agent.interrupt(reason, hard_cancel=True))
meter.wrap_client(agent.client)
agent.thinking_callback = None; agent.log_prefix = 'offline'
agent._has_pending_redirect = lambda: False
agent._vprint = lambda *args, **kwargs: None
agent._strip_think_blocks = lambda value: value
agent._persist_session = lambda messages, history: persisted.append((messages, history))
scope = dict(agent=agent, payload=payload, thinking_spinner=None, api_start_time=time.time(),
    time=time, messages=[], conversation_history=[],
    INTERRUPT_WAITING_FOR_MODEL_PREFIX=conversation_loop.INTERRUPT_WAITING_FOR_MODEL_PREFIX)
exec(compile(ast.fix_missing_locations(fixture), '<pinned-interruption-handler-fixture>', 'exec'), scope)
interrupted, retries, final = scope['exercise']()
assert interrupted is True and retries == 0 and len(persisted) == 1
assert final.startswith(conversation_loop.INTERRUPT_WAITING_FOR_MODEL_PREFIX)
assert meter.report()['physical_model_calls'] == 1 and agent._hard_interrupt_requested.is_set()

print('NATIVE_PARITY_OK: seven legacy and seven profiled pinned cases, native hard cancel and retry handler; no model calls')
