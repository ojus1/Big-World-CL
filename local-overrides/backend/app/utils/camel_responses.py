"""CAMEL's chat interface backed by the stateless OpenAI Responses API.

Luna requires Responses for function tools with reasoning enabled. CAMEL's
installed version only implements Chat Completions, so translate its messages
and results while retaining encrypted reasoning across each tool round trip.
"""
import json
import asyncio
from threading import RLock

from camel.models import OpenAIModel
from openai.types.chat import ChatCompletion
from .actor_output_contract import (CURRENT, ContractError, role_schema, require,
                                    configured_provider_contract, provider_contract)


class OpenAIResponsesModel(OpenAIModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._provider_contract_at_creation = configured_provider_contract()
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
        if configured_provider_contract() is not None:
            # Explicit profile, including ordinary bootstrap/social tool calls.
            # Do not request reasoning payloads for a no-thinking provider.
            request.pop('reasoning')
            request.pop('include')
            request.update(stream=False, extra_body={'chat_template_kwargs': {'enable_thinking': False}})
        scope = CURRENT.get()
        if scope is not None:
            # Contract applies only to this native interview task. Do not mutate
            # the shared model's config or affect concurrent social/tool calls.
            request['max_output_tokens'] = scope.contract['max_output_tokens']
            request['text'] = {'format': {'type': 'json_schema', 'name': 'actor_' + scope.contract['role'] + '_v1',
                'strict': True, 'schema': role_schema(scope.contract['role'])}}
            return request
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
        scope = CURRENT.get()
        if scope is not None:
            scope.provider_returned(response, '\n'.join(texts + refusals))
            if calls or refusals:
                raise ContractError('contracted_interview_returned_tools_or_refusal')
            if scope.receipt['output_tokens'] is not None and scope.receipt['output_tokens'] > scope.contract['max_output_tokens']:
                raise ContractError('actor_output_token_limit_exceeded')
        provider = configured_provider_contract()
        if provider is not None:
            require(getattr(response, 'model', None) == provider['model'], 'actor_returned_model_mismatch')
        if response.status != 'completed':
            # Account for partial output before failing; never execute it.
            reason = getattr(response.incomplete_details, 'reason', None)
            raise RuntimeError(f'Responses generation did not complete: {response.status}, {reason}')
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
                   'prompt_tokens_details': {'cached_tokens': getattr(usage.input_tokens_details, 'cached_tokens', None)}
                       if getattr(usage, 'input_tokens_details', None) is not None else None,
                   'completion_tokens_details': {'reasoning_tokens': getattr(usage.output_tokens_details, 'reasoning_tokens', None)}
                       if getattr(usage, 'output_tokens_details', None) is not None else None}
            if usage else None,
        )

    def _provider(self, *, asynchronous):
        expected = configured_provider_contract()
        require(getattr(self, '_provider_contract_at_creation', expected) == expected,
                'actor_provider_configuration_changed')
        if expected is not None:
            client = self._async_client if asynchronous else self._client
            actual = provider_contract(str(self.model_type), str(client.base_url))
            require(actual == expected, 'actor_provider_contract_mismatch')
        return expected

    def _run(self, messages, response_format=None, tools=None):
        if CURRENT.get() is not None:
            raise ContractError('contracted_interviews_require_async_native_execution')
        self._provider(asynchronous=False)
        return self._completion(self._client.responses.create(**self._request(messages, response_format, tools)))

    async def _arun(self, messages, response_format=None, tools=None):
        provider = self._provider(asynchronous=True)
        request = self._request(messages, response_format, tools)
        scope = CURRENT.get()
        if scope is None:
            response = await self._async_client.responses.create(**request)
            return self._completion(response)
        remaining = scope.before_dispatch(request, provider=provider)
        try:
            # SDK and CAMEL retry layers must not hide extra physical attempts.
            client = self._async_client.with_options(max_retries=0, timeout=remaining)
            response = await asyncio.wait_for(client.responses.create(**request), timeout=remaining)
            # Preserve independently observed usage before output normalization:
            # a malformed body must not erase known physical consumption.
            scope.provider_returned(response)
            return self._completion(response)
        except Exception as exc:
            scope.failed(exc)
            raise ContractError('contracted_actor_provider_failure') from None


def create_simulation_model(model, api_key, url):
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    provider = configured_provider_contract()
    if provider is not None:
        require(provider_contract(model, url) == provider, 'actor_provider_contract_mismatch')
        return OpenAIResponsesModel(model_type=model, api_key=api_key, url=url, model_config_dict={})
    from .openai_chat_compat import is_gpt5_family, reasoning_config
    config = reasoning_config(model) if is_gpt5_family(model) else None
    if model.startswith('gpt-5.6-luna'):
        return OpenAIResponsesModel(model_type=model, api_key=api_key, url=url,
                                    model_config_dict=config)
    return ModelFactory.create(model_platform=ModelPlatformType.OPENAI, model_type=model,
                               api_key=api_key, url=url, model_config_dict=config)
