"""CAMEL's chat interface backed by the stateless OpenAI Responses API.

Luna requires Responses for function tools with reasoning enabled. CAMEL's
installed version only implements Chat Completions, so translate its messages
and results while retaining encrypted reasoning across each tool round trip.
"""
import json
from threading import RLock

from camel.models import OpenAIModel
from openai.types.chat import ChatCompletion


class OpenAIResponsesModel(OpenAIModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A backend is shared by concurrent agents. Unique call IDs associate
        # response items with the right history; there is no global last response.
        self._items_by_call = {}
        self._items_lock = RLock()

    def preprocess_messages(self, messages):
        # CAMEL's chat preprocessor groups adjacent tool messages and can drop
        # later sequential calls. Responses already accepts their actual order.
        return [dict(message) for message in messages]

    def _input(self, messages):
        items, emitted = [], set()
        for message in messages:
            role = message['role']
            calls = message.get('tool_calls') or []
            if role == 'tool':
                content = message.get('content', '')
                items.append({'type': 'function_call_output',
                              'call_id': message['tool_call_id'],
                              'output': content if isinstance(content, str) else json.dumps(content)})
            elif role == 'assistant' and calls:
                with self._items_lock:
                    saved = self._items_by_call.get(calls[0]['id'])
                if saved:
                    for item in saved:
                        identity = item.get('id') or item.get('call_id')
                        if identity not in emitted:
                            items.append(item)
                            emitted.add(identity)
                else:
                    if message.get('content'):
                        items.append({'role': role, 'content': message['content']})
                    for call in calls:
                        if call['id'] not in emitted:
                            items.append({'type': 'function_call', 'call_id': call['id'],
                                          'name': call['function']['name'],
                                          'arguments': call['function']['arguments']})
                            emitted.add(call['id'])
            else:
                items.append({'role': role, 'content': message.get('content') or ''})
        return items

    def _request(self, messages, response_format, tools):
        config = self.model_config_dict
        if response_format or config.get('response_format') or config.get('stream'):
            raise ValueError('MiroFish Responses bridge supports non-streaming text and function tools only')
        request = {
            'model': str(self.model_type), 'input': self._input(messages),
            'store': False, 'include': ['reasoning.encrypted_content'],
            'reasoning': {'effort': config.get('reasoning_effort', 'low')},
            'max_output_tokens': config.get('max_completion_tokens') or config.get('max_tokens') or 8192,
        }
        tools = tools if tools is not None else config.get('tools')
        if tools:
            if any(tool['type'] != 'function' for tool in tools):
                raise ValueError('MiroFish simulation tools must be functions')
            request['tools'] = [dict(type='function', **dict(tool['function'],
                                strict=tool['function'].get('strict', False))) for tool in tools]
            request['parallel_tool_calls'] = config.get('parallel_tool_calls', False)
            choice = config.get('tool_choice', 'auto')
            if isinstance(choice, dict):
                choice = {'type': 'function', 'name': choice['function']['name']}
            request['tool_choice'] = choice
        return request

    def _completion(self, response):
        if response.status != 'completed':
            # Never execute a partial function call or label truncation a success.
            reason = getattr(response.incomplete_details, 'reason', None)
            raise RuntimeError(f'Responses generation did not complete: {response.status}, {reason}')
        output = [item.model_dump(exclude_none=True) for item in response.output]
        calls, texts, refusals = [], [], []
        for item in output:
            if item['type'] == 'function_call':
                calls.append({'id': item['call_id'], 'type': 'function',
                              'function': {'name': item['name'], 'arguments': item['arguments']}})
            elif item['type'] == 'message':
                for part in item['content']:
                    if part['type'] == 'output_text':
                        texts.append(part['text'])
                    elif part['type'] == 'refusal':
                        refusals.append(part['refusal'])
        if not calls and not texts and not refusals:
            raise RuntimeError('Responses generation returned no text or function call')
        if calls:
            with self._items_lock:
                for call in calls:
                    self._items_by_call[call['id']] = output
        usage = response.usage
        return ChatCompletion(
            id=response.id, object='chat.completion', created=int(response.created_at),
            model=response.model,
            choices=[{'index': 0, 'finish_reason': 'tool_calls' if calls else 'stop',
                      'message': {'role': 'assistant', 'content': '\n'.join(texts + refusals) or None,
                                  'tool_calls': calls or None, 'refusal': '\n'.join(refusals) or None}}],
            usage={'prompt_tokens': usage.input_tokens, 'completion_tokens': usage.output_tokens,
                   'total_tokens': usage.total_tokens,
                   'prompt_tokens_details': {'cached_tokens': usage.input_tokens_details.cached_tokens},
                   'completion_tokens_details': {'reasoning_tokens': usage.output_tokens_details.reasoning_tokens}}
            if usage else None,
        )

    def _run(self, messages, response_format=None, tools=None):
        return self._completion(self._client.responses.create(**self._request(messages, response_format, tools)))

    async def _arun(self, messages, response_format=None, tools=None):
        response = await self._async_client.responses.create(**self._request(messages, response_format, tools))
        return self._completion(response)


def create_simulation_model(model, api_key, url):
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from .openai_chat_compat import is_gpt5_family, reasoning_config
    config = reasoning_config(model) if is_gpt5_family(model) else None
    if model.startswith('gpt-5.6-luna'):
        return OpenAIResponsesModel(model_type=model, api_key=api_key, url=url,
                                    model_config_dict=config)
    return ModelFactory.create(model_platform=ModelPlatformType.OPENAI, model_type=model,
                               api_key=api_key, url=url, model_config_dict=config)
