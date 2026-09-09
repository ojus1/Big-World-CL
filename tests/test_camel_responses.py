import asyncio
import json
from pathlib import Path
import sys

import httpx
from openai import OpenAI, AsyncOpenAI
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.utils.camel_responses import OpenAIResponsesModel


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
