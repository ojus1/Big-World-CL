import asyncio
import json
from pathlib import Path
import sys

import httpx
from openai import OpenAI, AsyncOpenAI
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Exercise this checkout's tracked override, never an installed native server.
from tests.test_actor_output_contract import bridge
OpenAIResponsesModel = bridge.OpenAIResponsesModel


@pytest.fixture(autouse=True)
def deny_real_http(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Offline bridge fixture attempted real HTTP')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


TOOLS = [{'type': 'function', 'function': {'name': 'create_post', 'parameters': {
    'type': 'object', 'properties': {'content': {'type': 'string'}}, 'required': ['content']}}}]


def response(output, status='completed'):
    return {'id': 'resp_test', 'object': 'response', 'created_at': 1, 'status': status,
            'model': 'gpt-5.6-luna', 'output': output,
            'incomplete_details': {'reason': 'max_output_tokens'} if status == 'incomplete' else None,
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
                      'input_tokens_details': {'cached_tokens': 0},
                      'output_tokens_details': {'reasoning_tokens': 2}}}


def output_for(call_id):
    return [{'id': 'reason_' + call_id, 'type': 'reasoning', 'summary': [], 'encrypted_content': 'opaque_' + call_id},
            {'id': 'fc_' + call_id, 'type': 'function_call', 'call_id': call_id,
             'name': 'create_post', 'arguments': '{"content":"Test"}', 'status': 'completed'}]


def model():
    return OpenAIResponsesModel(model_type='gpt-5.6-luna', api_key='test-key',
                                model_config_dict={'reasoning_effort': 'low'})


def tool_result(completion):
    return [completion.choices[0].message.model_dump(exclude_none=True),
            {'role': 'tool', 'tool_call_id': completion.choices[0].message.tool_calls[0].id,
             'content': '{"success":true}'}]


def test_sync_tool_roundtrip_preserves_encrypted_reasoning_and_usage():
    requests = []
    def respond(request):
        data = json.loads(request.content)
        requests.append(data)
        assert request.url.path == '/v1/responses'
        if len(requests) == 1:
            return httpx.Response(200, json=response(output_for('call_a')))
        return httpx.Response(200, json=response([{'id': 'msg_final', 'type': 'message',
            'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': 'Posted.', 'annotations': []}]}]))
    instance = model()
    instance._client = OpenAI(api_key='test-key', http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    messages = [{'role': 'user', 'content': 'Post Test.'}]
    first = instance.run(messages, tools=TOOLS)
    final = instance.run(messages + tool_result(first), tools=TOOLS)
    assert final.choices[0].message.content == 'Posted.'
    assert final.usage.completion_tokens_details.reasoning_tokens == 2
    assert requests[0]['reasoning'] == {'effort': 'low'}
    assert requests[0]['store'] is False
    assert requests[0]['tools'][0]['name'] == 'create_post'
    assert requests[1]['input'][1:3] == output_for('call_a')
    assert requests[1]['input'][3]['call_id'] == 'call_a'


def test_concurrent_agents_do_not_mix_tool_histories():
    async def scenario():
        async def respond(request):
            data = json.loads(request.content)
            name = data['input'][0]['content']
            await asyncio.sleep(0)
            if len(data['input']) > 1:
                reasoning = [i for i in data['input'] if i.get('type') == 'reasoning']
                assert reasoning == [output_for(name)[0]]
            return httpx.Response(200, json=response(output_for(name)))
        instance = model()
        instance._async_client = AsyncOpenAI(api_key='test-key', http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        async def agent(name):
            messages = [{'role': 'user', 'content': name}]
            first = await instance.arun(messages, tools=TOOLS)
            await instance.arun(messages + tool_result(first), tools=TOOLS)
        await asyncio.gather(agent('alice'), agent('bob'))
    asyncio.run(scenario())


def test_incomplete_tool_call_is_never_executed():
    instance = model()
    instance._client = OpenAI(api_key='test-key', http_client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response(output_for('partial'), 'incomplete')))))
    with pytest.raises(RuntimeError, match='did not complete'):
        instance.run([{'role': 'user', 'content': 'Post.'}], tools=TOOLS)


def test_split_parallel_calls_replay_response_items_once():
    instance = model()
    output = output_for('one') + output_for('two')[1:]
    instance._items_by_call = {'one': output, 'two': output}
    history = []
    for name in ('one', 'two'):
        history += [{'role': 'assistant', 'tool_calls': [{'id': name, 'type': 'function',
                     'function': {'name': 'create_post', 'arguments': '{"content":"Test"}'}}]},
                    {'role': 'tool', 'tool_call_id': name, 'content': 'ok'}]
    items = instance._input(history)
    assert len([i for i in items if i['type'] == 'reasoning']) == 1
    assert len([i for i in items if i['type'] == 'function_call']) == 2
    assert len([i for i in items if i['type'] == 'function_call_output']) == 2


def test_sequential_tool_rounds_are_not_dropped_by_camel_preprocessing():
    requests = []
    def respond(request):
        data = json.loads(request.content)
        requests.append(data)
        index = len(requests)
        outputs = [item['call_id'] for item in data['input'] if item.get('type') == 'function_call_output']
        assert outputs == [f'call_{i}' for i in range(1, index)]
        return httpx.Response(200, json=response(output_for(f'call_{index}')))
    instance = model()
    instance._client = OpenAI(api_key='test-key', http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    messages = [{'role': 'user', 'content': 'Research this proposal.'}]
    for _ in range(3):
        completion = instance.run(messages, tools=TOOLS)
        messages += tool_result(completion)
    assert len(requests) == 3


# Profile normalization tests are synthetic compatibility fixtures, not native
# capability evidence. They never load captured personas or native transcripts.
def _profiled(monkeypatch, responder=None):
    from tests.test_actor_output_contract import profile_model
    return profile_model(responder or (lambda _: pytest.fail('Unexpected HTTP dispatch')), monkeypatch)


def test_profile_combines_leading_system_text_without_deduplication_or_mutation(monkeypatch):
    from copy import deepcopy
    instance = _profiled(monkeypatch)
    repeated = 'Preserve braces { } quote " slash \\ and unicode Ω\n'
    messages = [{'role': 'system', 'content': repeated}, {'role': 'system', 'content': repeated},
                {'role': 'system', 'content': '\nFinal prefix instruction.  '},
                {'role': 'user', 'content': 'Fixture task.'},
                {'role': 'system', 'content': 'Later instruction stays here.'},
                {'role': 'developer', 'content': 'Developer instruction stays here.'},
                {'role': 'assistant', 'content': ''}]
    original = deepcopy(messages)
    result = instance._input(messages)
    assert result == [{'role': 'system', 'content': repeated + '\n\n' + repeated + '\n\n\nFinal prefix instruction.  '}] + messages[3:]
    assert messages == original


@pytest.mark.parametrize('messages', [[], [{'role': 'user', 'content': 'Fixture'}],
    [{'role': 'system', 'content': ''}, {'role': 'user', 'content': 'Fixture'}],
    [{'role': 'system', 'content': 'One'}, {'role': 'developer', 'content': 'Boundary'},
     {'role': 'system', 'content': 'Two'}, {'role': 'system', 'content': 'Three'}],
    [{'role': 'user', 'content': 'Before'}, {'role': 'system', 'content': 'Late one'},
     {'role': 'system', 'content': 'Late two'}]])
def test_profile_zero_single_and_late_system_messages_are_unchanged(monkeypatch, messages):
    instance = _profiled(monkeypatch)
    assert instance._input(messages) == messages


@pytest.mark.parametrize('unsupported', [
    {'role': 'system', 'content': [{'type': 'input_text', 'text': 'Structured'}]},
    {'role': 'system', 'content': {'text': 'Structured'}},
    {'role': 'system', 'content': None}, {'role': 'system'},
    {'role': 'system', 'content': 'Named', 'name': 'fixture'},
    {'role': 'system', 'content': 'Extra', 'tool_calls': []},
])
def test_profile_unsupported_system_prefix_fails_before_dispatch(monkeypatch, unsupported):
    from copy import deepcopy
    instance = _profiled(monkeypatch)
    messages = [{'role': 'system', 'content': 'Plain'}, unsupported, {'role': 'user', 'content': 'Fixture'}]
    before = deepcopy(messages)
    with pytest.raises(bridge.ContractError, match='leading_system_messages_require_plain_text'):
        asyncio.run(instance.arun(messages))
    assert messages == before


def test_legacy_multiple_system_messages_and_structured_content_remain_unchanged(monkeypatch):
    monkeypatch.delenv('BIGWORLD_PROVIDER_PROFILE', raising=False)
    instance = model()
    messages = [{'role': 'system', 'content': 'Repeat'}, {'role': 'system', 'content': 'Repeat'},
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'Structured'}]},
                {'role': 'user', 'content': 'Fixture'}]
    assert instance._input(messages) == messages


def test_profile_leading_merge_preserves_cached_response_items_and_tool_results(monkeypatch):
    from copy import deepcopy
    instance = _profiled(monkeypatch)
    # The existing cache may contain reasoning and response-item metadata. This
    # change must leave all cached items and their order untouched.
    cached = output_for('fixture')
    instance._items_by_call = {'fixture': deepcopy(cached)}
    messages = [{'role': 'system', 'content': 'First'}, {'role': 'system', 'content': 'Second'},
        {'role': 'user', 'content': 'Before tools'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'fixture', 'type': 'function',
            'function': {'name': 'create_post', 'arguments': '{"content":"Test"}'}}]},
        {'role': 'tool', 'tool_call_id': 'fixture', 'content': '{"success":true}'},
        {'role': 'assistant', 'content': ''}, {'role': 'user', 'content': 'Interview'}]
    original = deepcopy(messages)
    assert instance._input(messages) == [
        {'role': 'system', 'content': 'First\n\nSecond'}, {'role': 'user', 'content': 'Before tools'},
        *cached, {'type': 'function_call_output', 'call_id': 'fixture', 'output': '{"success":true}'},
        {'role': 'assistant', 'content': ''}, {'role': 'user', 'content': 'Interview'}]
    assert messages == original and instance._items_by_call == {'fixture': cached}


def test_contracted_profile_request_merges_prefix_and_binds_normalized_input(monkeypatch, tmp_path):
    from tests.test_actor_output_contract import (actor_dir, profile_response, EXAMPLE,
        CONFIG, descriptor, wire, write_trace)
    requests = []
    text = json.dumps(EXAMPLE)
    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if payload['input'][0]['role'] == payload['input'][1].get('role') == 'system':
            return httpx.Response(400, json={'error': {'message': 'System message must be at the beginning.'}})
        return httpx.Response(200, json=profile_response(text))
    instance = _profiled(monkeypatch, respond)
    directory = actor_dir(tmp_path)
    prompt = 'Return the employee fixture.'
    messages = [{'role': 'system', 'content': 'Same instruction'}, {'role': 'system', 'content': 'Same instruction'},
        {'role': 'user', 'content': 'Prior task'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call_fixture', 'type': 'function',
            'function': {'name': 'create_post', 'arguments': '{"content":"Prior result"}'}}]},
        {'role': 'tool', 'tool_call_id': 'call_fixture', 'content': '{"success":true}'},
        {'role': 'assistant', 'content': ''}, {'role': 'user', 'content': prompt}]
    contract = descriptor(CONFIG, 'employee')
    binding = wire.bind_request(directory, 0, prompt, prompt, contract, 'b' * 64)
    async def interview():
        with wire.interview_scope(directory, 0, prompt, binding) as scope:
            cursor = wire.trace_cursor(directory)
            completion = await instance.arun(messages, tools=TOOLS)
            write_trace(directory, 0, prompt, completion.choices[0].message.content)
            result = wire.contracted_trace_result(directory, 0, prompt, cursor)
            return scope.finish(result)
    receipt = asyncio.run(interview())
    assert len(requests) == 1
    sent = requests[0]
    assert sent['input'][0] == {'role': 'system', 'content': 'Same instruction\n\nSame instruction'}
    assert sent['input'][-2:] == messages[-2:]
    assert sent['input'][2]['type'] == 'function_call' and sent['input'][3]['type'] == 'function_call_output'
    assert sent['text']['format'] == {'type': 'json_schema', 'name': 'actor_employee_v1', 'strict': True,
                                     'schema': wire.role_schema('employee')}
    assert sent['max_output_tokens'] == CONFIG['max_output_tokens']
    assert sent['stream'] is sent['store'] is False
    assert sent['chat_template_kwargs'] == {'enable_thinking': False} and 'tools' not in sent
    assert receipt['provider_input_sha256'] == wire.digest(sent['input'])
    assert receipt['output_schema_valid'] is receipt['accounting_complete'] is True
    assert receipt['physical_requests_dispatched'] == 1
