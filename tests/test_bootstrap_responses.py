"""Offline bootstrap Responses fixtures; these do not qualify a native provider.

Apply the real tracked patch to pinned native source in a temporary directory,
then use the real OpenAI SDK with only MockTransport. Installed sources are read
through git objects, never imported or changed. All real HTTP is forbidden.
"""
from copy import deepcopy
import importlib.util
import ast
import logging
from typing import Any, Dict, List, Optional, Callable
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import httpx
from openai import OpenAI
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'Qwen/Qwen3.8-27B-FP8'
BASE = 'https://bootstrap-fixture.invalid/v1'
PROFILE = 'responses-no-thinking-v1'
MESSAGES = [{'role': 'system', 'content': 'Return JSON.'}, {'role': 'user', 'content': 'Fixture only.'}]


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Offline fixture attempted a real HTTP request')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setenv('BIGWORLD_PROVIDER_PROFILE', PROFILE)
    monkeypatch.setenv('LLM_MODEL_NAME', MODEL)
    monkeypatch.setenv('LLM_BASE_URL', BASE)


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    source = Path(os.environ.get('BIGWORLD_TEST_MIROFISH_SOURCE', ROOT / '.cache/mirofish-contract'))
    if os.environ.get('BIGWORLD_TEST_MIROFISH_SOURCE') and not (source / '.git').exists():
        pytest.fail('Explicit pinned MiroFish source is missing')
    if not source.exists():
        source = ROOT / 'MiroFish'
    if not (source / '.git').exists():
        pytest.skip('Pinned source required for actual native patch fixture')
    temporary = tmp_path_factory.mktemp('bootstrap-patched-source')
    paths = ['backend/app/utils/' + name for name in ('openai_chat_compat.py', 'llm_client.py')]
    paths += ['backend/app/services/' + name for name in ('oasis_profile_generator.py', 'simulation_config_generator.py')]
    for relative in paths:
        target = temporary / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', '-C', str(source), 'show',
            '39d849138ef254f6c737ab4c4705e5545dbe31d4:' + relative]))
    subprocess.run(['git', 'apply', *['--include=' + path for path in paths],
        str(ROOT / 'patches/mirofish-local.patch')], cwd=temporary, check=True, capture_output=True)
    package = '_bootstrap_native_fixture'
    registered = []
    for suffix, path in [('', temporary/'backend/app'), ('.utils', temporary/'backend/app/utils')]:
        module = ModuleType(package + suffix); module.__path__ = [str(path)]
        sys.modules[module.__name__] = module; registered.append(module.__name__)
    config = ModuleType(package + '.config')
    config.Config = SimpleNamespace(GRAPH_BACKEND='cloud', LLM_REASONING_EFFORT='low',
        LLM_API_KEY='offline-key', LLM_MODEL_NAME=MODEL, LLM_BASE_URL=BASE)
    sys.modules[config.__name__] = config; registered.append(config.__name__)
    def load(name, path):
        spec = importlib.util.spec_from_file_location(package + '.utils.' + name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module; registered.append(spec.name)
        spec.loader.exec_module(module)
        return module
    wire = load('actor_output_contract', ROOT/'local-overrides/backend/app/utils/actor_output_contract.py')
    compat = load('openai_chat_compat', temporary/paths[0])
    llm = load('llm_client', temporary/paths[1])
    methods = {}
    context = {'json': json, 'Dict': Dict, 'Any': Any, 'List': List, 'Optional': Optional, 'Callable': Callable,
        'logger': logging.getLogger('offline-bootstrap-fixture'),
        'EntityNode': object, 'OasisAgentProfile': lambda **kw: pytest.fail('Synthetic profile fallback executed'),
        'create_chat_completion': compat.create_chat_completion,
        'extract_chat_completion_text': compat.extract_chat_completion_text,
        'is_local_llama_client': compat.is_local_llama_client,
        'ProfiledResponseError': compat.ProfiledResponseError,
        'get_locale': lambda: 'en', 'set_locale': lambda value: None,
        'get_language_instruction': lambda: 'Fixture language instruction.'}
    for relative in paths[2:]:
        tree = ast.parse((temporary / relative).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {
                    '_generate_profile_with_llm', '_call_llm_with_retry', 'generate_profiles_from_entities'}:
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(temporary/relative), 'exec'), context)
                methods[node.name] = context[node.name]
    yield SimpleNamespace(compat=compat, llm=llm, wire=wire, config=config.Config, methods=methods)
    for name in registered:
        sys.modules.pop(name, None)


def body(text='{"ok": true}', *, usage=None, status='completed'):
    return {'id': 'resp_fixture', 'object': 'response', 'created_at': 1, 'model': MODEL,
        'status': status, 'incomplete_details': None,
        'output': [{'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
        'usage': usage if usage is not None else {'input_tokens': 12, 'output_tokens': 7, 'total_tokens': 19}}


def client(handler, base=BASE):
    return OpenAI(api_key='offline-key', base_url=base, max_retries=3,
                  http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def call(native, sdk, **kw):
    return native.compat.create_chat_completion(sdk, model=MODEL, messages=deepcopy(MESSAGES), **kw)


def test_basic_preserves_escaping_minimal_usage_and_sdk_settings(native):
    requests = []
    text = json.dumps({'braces': '{ }', 'quote': '"', 'slash': '\\', 'newline': '\n', 'unicode': 'Ω'})
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=body(text))
    with client(respond) as sdk:
        original_timeout, original_retries = sdk.timeout, sdk.max_retries
        result = call(native, sdk, temperature=0.25)
        assert sdk.timeout == original_timeout and sdk.max_retries == original_retries == 3
    assert len(requests) == 1 and requests[0].url.path == '/v1/responses'
    sent = json.loads(requests[0].content)
    assert sent == {'model': MODEL, 'input': MESSAGES, 'stream': False, 'store': False,
        'max_output_tokens': 8192, 'temperature': 0.25, 'chat_template_kwargs': {'enable_thinking': False}}
    assert all(value == 120 for value in requests[0].extensions['timeout'].values())
    assert result.choices[0].finish_reason == 'stop'
    assert native.compat.extract_chat_completion_text(result) == text
    assert result.usage.prompt_tokens == 12 and result.usage.completion_tokens == 7 and result.usage.total_tokens == 19
    assert result.usage.prompt_tokens_details.cached_tokens is None
    assert result.usage.completion_tokens_details.reasoning_tokens is None
    assert result.provider_contract == native.wire.configured_provider_contract()
    assert native.llm.LLMClient._parse_json_response(result) == json.loads(text)


@pytest.mark.parametrize('response_format', [None, {'type': 'text'}, {'type': 'json_object'},
    {'type': 'json_schema', 'json_schema': {'name': 'ontology', 'strict': True, 'description': 'Fixture',
        'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}}}])
def test_request_formats_and_explicit_cap_are_faithful(native, response_format):
    requests = []
    with client(lambda request: requests.append(json.loads(request.content)) or httpx.Response(200, json=body())) as sdk:
        original = deepcopy(response_format)
        call(native, sdk, max_tokens=128, response_format=response_format)
        assert original == response_format
    assert requests[0]['max_output_tokens'] == 128
    expected = None if response_format is None else (
        dict(response_format['json_schema'], type='json_schema') if response_format['type'] == 'json_schema' else response_format)
    assert requests[0].get('text') == (None if expected is None else {'format': expected})


@pytest.mark.parametrize('cap', [True, 0, -1, 8193, '4096', 3.5])
def test_invalid_caps_reject_before_dispatch(native, cap):
    with client(lambda _: pytest.fail('Unexpected dispatch')) as sdk:
        with pytest.raises(native.compat.ProfiledResponseError, match='configuration_failed'):
            call(native, sdk, max_tokens=cap)


@pytest.mark.parametrize('mismatch', ['endpoint', 'model', 'profile', 'clone_endpoint'])
def test_actual_provider_binding_refuses_before_dispatch(native, monkeypatch, mismatch):
    with client(lambda _: pytest.fail('Unexpected dispatch')) as sdk:
        if mismatch == 'endpoint': sdk.base_url = 'https://different.invalid/v1'
        if mismatch == 'model': monkeypatch.setenv('LLM_MODEL_NAME', 'different-model')
        if mismatch == 'profile': monkeypatch.setenv('BIGWORLD_PROVIDER_PROFILE', 'unsupported-profile')
        if mismatch == 'clone_endpoint':
            original = sdk.with_options
            def changed(**kw):
                clone = original(**kw); clone.base_url = 'https://different.invalid/v1'; return clone
            monkeypatch.setattr(sdk, 'with_options', changed)
        with pytest.raises(native.compat.ProfiledResponseError) as caught:
            call(native, sdk)
        assert caught.value.dispatch_attempts == 0
        assert caught.value.accounting_complete is True and caught.value.reserved_output_tokens == 0
        assert caught.value.known_usage == {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}


@pytest.mark.parametrize('usage', [
    {'input_tokens': 12, 'output_tokens': None, 'total_tokens': None},
    {'input_tokens': 12, 'output_tokens': 7, 'total_tokens': 99},
    {'input_tokens': None, 'output_tokens': 9000, 'total_tokens': None},
    {'input_tokens': True, 'output_tokens': 7, 'total_tokens': 8}])
def test_incomplete_usage_preserves_independent_dimensions(native, usage):
    with client(lambda _: httpx.Response(200, json=body(usage=usage))) as sdk:
        with pytest.raises(native.compat.ProfiledResponseError) as caught:
            call(native, sdk)
    expected = {key: value if type(value) is int and value >= 0 else None for key, value in usage.items()}
    assert caught.value.known_usage == expected
    assert caught.value.accounting_complete is False and caught.value.reserved_output_tokens == 8192
    if usage.get('output_tokens') == 9000:
        assert str(caught.value) == 'bootstrap_responses_output_limit_exceeded'


@pytest.mark.parametrize('invalid', ['incomplete', 'wrong_model', 'malformed_output', 'refusal', 'tool', 'empty'])
def test_returned_invalid_output_keeps_known_cost_without_retry(native, invalid):
    payload = body()
    if invalid == 'incomplete': payload['status'] = 'incomplete'
    if invalid == 'wrong_model': payload['model'] = 'different-model'
    if invalid == 'malformed_output': payload['output'] = None
    if invalid == 'empty': payload['output'] = []
    if invalid == 'refusal': payload['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'Fixture'}]
    if invalid == 'tool': payload['output'] = [{'type': 'function_call', 'call_id': 'fixture', 'name': 'x', 'arguments': '{}'}]
    requests = []
    with client(lambda request: requests.append(request) or httpx.Response(200, json=payload)) as sdk:
        with pytest.raises(native.compat.ProfiledResponseError) as caught:
            call(native, sdk)
    assert len(requests) == 1
    assert caught.value.known_usage == {'input_tokens': 12, 'output_tokens': 7, 'total_tokens': 19}
    assert caught.value.accounting_complete is True and caught.value.reserved_output_tokens == 0


@pytest.mark.parametrize('failure', ['timeout', 'server', 'format_rejection'])
def test_sdk_failure_is_one_request_without_json_mode_fallback(native, failure):
    requests = []
    def respond(request):
        requests.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('fixture private body', request=request)
        status = 400 if failure == 'format_rejection' else 500
        return httpx.Response(status, json={'error': {'message': 'response_format unsupported private body',
            'param': 'response_format', 'code': 'unsupported_parameter'}})
    with client(respond) as sdk:
        instance = object.__new__(native.llm.LLMClient)
        instance.client, instance.model, instance.base_url = sdk, MODEL, BASE
        with pytest.raises(native.compat.ProfiledResponseError) as caught:
            instance.chat_json(MESSAGES, max_tokens=None, max_attempts=2)
    assert len(requests) == 1 and requests[0].url.path == '/v1/responses'
    assert 'private body' not in str(caught.value)
    assert caught.value.error_class in {'APITimeoutError', 'InternalServerError', 'BadRequestError'}
    assert caught.value.known_usage == dict.fromkeys(('input_tokens', 'output_tokens', 'total_tokens'))
    assert caught.value.reserved_output_tokens == 8192


def test_explicit_content_retry_stays_bounded_and_capped(native):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=body('not json' if len(requests) == 1 else '{"ok": true}'))
    with client(respond) as sdk:
        instance = object.__new__(native.llm.LLMClient)
        instance.client, instance.model, instance.base_url = sdk, MODEL, BASE
        assert instance.chat_json(MESSAGES, max_tokens=None, max_attempts=2) == {'ok': True}
    assert len(requests) == 2
    assert all(request['max_output_tokens'] == 8192 and request['text']['format'] == {'type': 'json_object'} for request in requests)


@pytest.mark.parametrize('model', ['legacy-model', 'gpt-5'])
def test_absent_profile_retains_legacy_path_and_request_shape(native, monkeypatch, model):
    monkeypatch.delenv('BIGWORLD_PROVIDER_PROFILE')
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'id': 'chat_fixture', 'object': 'chat.completion', 'created': 1, 'model': model,
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'legacy'}}]})
    with client(respond) as sdk:
        result = native.compat.create_chat_completion(sdk, model=model, messages=MESSAGES,
            temperature=0.2, max_tokens=42, response_format={'type': 'json_object'})
    expected = {'model': model, 'messages': MESSAGES, 'response_format': {'type': 'json_object'}}
    expected.update({'reasoning_effort': 'low', 'max_completion_tokens': 42} if model == 'gpt-5' else {'temperature': 0.2, 'max_tokens': 42})
    assert requests[0].url.path == '/v1/chat/completions'
    assert json.loads(requests[0].content) == expected
    assert native.compat.extract_chat_completion_text(result) == 'legacy'


def generator(native, sdk):
    return SimpleNamespace(client=sdk, model_name=MODEL,
        _is_individual_entity=lambda _: True,
        _build_individual_persona_prompt=lambda *args: 'Fixture persona prompt.',
        _build_group_persona_prompt=lambda *args: 'Fixture institution prompt.',
        _get_system_prompt=lambda *args: 'Fixture system prompt.',
        _try_fix_json=lambda *args: {}, _try_fix_config_json=lambda *args: None,
        _generate_profile_rule_based=lambda *args: pytest.fail('Rule-based profile fallback executed'))


def generate(native, instance, family):
    if family == 'config':
        return native.methods['_call_llm_with_retry'](instance, 'Fixture prompt.', 'Fixture system.')
    return native.methods['_generate_profile_with_llm'](instance, 'Fixture', 'Employee', 'Fixture summary', {}, '')


@pytest.mark.parametrize('family', ['profile', 'config'])
@pytest.mark.parametrize('failure', ['timeout', 'format_rejection', 'usage', 'endpoint', 'model', 'profile'])
def test_actual_generator_provider_failures_propagate_once_without_fallback(native, monkeypatch, family, failure):
    import time
    monkeypatch.setattr(time, 'sleep', lambda *args: pytest.fail('Unexpected retry/backoff'))
    requests = []
    def respond(request):
        requests.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('offline', request=request)
        if failure == 'format_rejection':
            return httpx.Response(400, json={'error': {'param': 'response_format', 'message': 'unsupported', 'code': 'unsupported_parameter'}})
        return httpx.Response(200, json=body(usage={'input_tokens': 12, 'output_tokens': None, 'total_tokens': None}))
    with client(respond) as sdk:
        instance = generator(native, sdk)
        if failure == 'endpoint': sdk.base_url = 'https://different.invalid/v1'
        if failure == 'model': instance.model_name = 'wrong-model'
        if failure == 'profile': monkeypatch.setenv('BIGWORLD_PROVIDER_PROFILE', 'wrong-profile')
        with pytest.raises(native.compat.ProfiledResponseError) as caught:
            generate(native, instance, family)
    dispatched = failure not in {'endpoint', 'model', 'profile'}
    assert len(requests) == caught.value.dispatch_attempts == int(dispatched)
    if not dispatched:
        assert caught.value.known_usage == {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
        assert caught.value.reserved_output_tokens == 0


def test_actual_profile_batch_never_synthesizes_profile_after_provider_failure(native, monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        raise httpx.ReadTimeout('offline', request=request)
    with client(respond) as sdk:
        instance = generator(native, sdk)
        instance.generate_profile_from_entity = lambda **kw: generate(native, instance, 'profile')
        instance._print_generated_profile = lambda *args: pytest.fail('Printed synthetic profile')
        instance._generate_username = lambda *args: pytest.fail('Synthetic username fallback')
        entity = SimpleNamespace(name='Fixture', summary='Fixture', uuid='fixture', get_entity_type=lambda: 'Employee')
        with pytest.raises(native.compat.ProfiledResponseError):
            native.methods['generate_profiles_from_entities'](instance, [entity], parallel_count=1)
    assert len(requests) == 1


@pytest.mark.parametrize('family', ['profile', 'config'])
def test_actual_generators_keep_explicit_content_regeneration(native, family):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        text = 'not json' if len(requests) == 1 else '{"bio":"Fixture bio", "persona":"Fixture persona"}'
        return httpx.Response(200, json=body(text))
    with client(respond) as sdk:
        result = generate(native, generator(native, sdk), family)
    assert result == {'bio': 'Fixture bio', 'persona': 'Fixture persona'}
    assert len(requests) == 2 and all(request['max_output_tokens'] == 8192 for request in requests)


@pytest.mark.parametrize('family', ['profile', 'config'])
def test_actual_generators_legacy_error_behavior_unchanged(native, monkeypatch, family):
    import time
    monkeypatch.delenv('BIGWORLD_PROVIDER_PROFILE')
    monkeypatch.setattr(time, 'sleep', lambda *args: None)
    attempts = []
    def legacy_error(*args, **kwargs):
        attempts.append(1)
        raise RuntimeError('legacy fixture failure')
    monkeypatch.setitem(native.methods['_generate_profile_with_llm'].__globals__, 'create_chat_completion', legacy_error)
    with client(lambda _: pytest.fail('Unexpected SDK dispatch')) as sdk:
        instance = generator(native, sdk)
        instance._generate_profile_rule_based = lambda *args: {'legacy': 'fallback'}
        if family == 'config':
            with pytest.raises(RuntimeError, match='legacy fixture failure'):
                generate(native, instance, family)
        else:
            assert generate(native, instance, family) == {'legacy': 'fallback'}
    assert len(attempts) == 3


def test_multiple_output_text_segments_preserve_json_string_bytes(native):
    payload = body()
    text = '{"content": "left{right}quote\\\"end"}'
    split = text.index('right')
    payload['output'][0]['content'] = [
        {'type': 'output_text', 'text': part, 'annotations': []} for part in (text[:split], text[split:])]
    with client(lambda _: httpx.Response(200, json=payload)) as sdk:
        result = call(native, sdk, response_format={'type': 'json_object'})
    assert native.compat.extract_chat_completion_text(result) == text
    assert native.llm.LLMClient._parse_json_response(result) == json.loads(text)
