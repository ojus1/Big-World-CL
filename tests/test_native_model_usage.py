"""Offline provider receipts, including failures and independent simulations."""
import ast
import asyncio
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
from openai import OpenAI, AsyncOpenAI
import pytest

from tests.test_actor_output_contract import (PKG, bridge, wire, actor_dir, profile_model,
    profile_response, native_fixture, PROFILE_MODEL, PROFILE_BASE, EXAMPLE, patched_backend)

usage = importlib.import_module(PKG + '.model_usage')


@pytest.fixture(autouse=True)
def deny_real_http(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail('Usage fixture attempted real HTTP')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', denied)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', denied)


def instance(tmp_path, monkeypatch, responder):
    result = profile_model(responder, monkeypatch)
    directory = actor_dir(tmp_path)
    config = directory / 'simulation_config.json'
    value = json.loads(config.read_text()); value['native_model_usage'] = usage.VERSION
    config.write_text(json.dumps(value))
    result._model_usage = usage.ModelUsage(directory, wire.configured_provider_contract())
    return result, directory


def rows(directory):
    return [json.loads(path.read_text()) for path in sorted((directory / 'model_usage/calls').glob('*.json'))]


@pytest.mark.parametrize('asynchronous', [False, True])
def test_success_preserves_request_and_usage_without_sensitive_text(tmp_path, monkeypatch, asynchronous):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=profile_response('private-response-canary'))
    model, directory = instance(tmp_path, monkeypatch, respond)
    model._client = OpenAI(api_key='private-key-canary', base_url=PROFILE_BASE,
                          http_client=httpx.Client(transport=httpx.MockTransport(respond)), max_retries=3)
    messages = [{'role': 'user', 'content': 'private-prompt-canary'}]
    if asynchronous:
        result = asyncio.run(model.arun(messages))
    else:
        result = model.run(messages)
    assert result.choices[0].message.content == 'private-response-canary'
    summary = usage.summarize(directory / 'model_usage', simulation_id=directory.name)
    assert summary['provider_dispatch_attempts'] == 1 and summary['reported_tokens'] == 60
    assert summary['observed_accounting_complete'] is True
    row = rows(directory)[0]
    assert row['request_sha256'] == usage.digest(model._request(messages, None, None))
    assert len(requests) == 1 and row['status'] == 'completed'
    text = ''.join(path.read_text() for path in (directory / 'model_usage').rglob('*.json'))
    assert all(canary not in text for canary in ('private-key-canary', 'private-prompt-canary', 'private-response-canary'))


@pytest.mark.parametrize('failure', ['http', 'timeout', 'incomplete', 'malformed', 'missing_usage', 'bad_usage'])
def test_failure_preserves_known_usage_and_never_retries(tmp_path, monkeypatch, failure):
    requests = []
    def respond(request):
        requests.append(request)
        if failure == 'http':
            return httpx.Response(503, json={'error': {'message': 'private-error-canary'}})
        if failure == 'timeout':
            raise httpx.ReadTimeout('private-error-canary', request=request)
        body = profile_response('text', status='incomplete' if failure == 'incomplete' else 'completed')
        if failure == 'malformed': body['output'] = []
        if failure == 'missing_usage': body['usage'] = None
        if failure == 'bad_usage': body['usage']['total_tokens'] = 777
        return httpx.Response(200, json=body)
    model, directory = instance(tmp_path, monkeypatch, respond)
    async def run():
        if failure in ('missing_usage', 'bad_usage'):
            await model.arun([{'role': 'user', 'content': 'fixture'}])
        else:
            with pytest.raises(Exception):
                await model.arun([{'role': 'user', 'content': 'fixture'}])
    asyncio.run(run())
    assert len(requests) == 1
    row = rows(directory)[0]
    known = failure in ('incomplete', 'malformed')
    assert row['total_tokens'] == (60 if known else None)
    assert row['accounting_complete'] is known
    assert 'private-error-canary' not in json.dumps(row)
    summary = usage.summarize(directory / 'model_usage')
    assert summary['requests_with_unknown_usage'] == (0 if known else 1)


def test_parallel_simulations_and_contracted_interviews_do_not_double_count(tmp_path, monkeypatch):
    async def respond(request):
        await asyncio.sleep(0)
        return httpx.Response(200, json=profile_response(json.dumps(EXAMPLE)))
    (tmp_path / 'a').mkdir(); (tmp_path / 'b').mkdir()
    a, da = instance(tmp_path / 'a', monkeypatch, respond)
    b, db = instance(tmp_path / 'b', monkeypatch, respond)
    async def run():
        await asyncio.gather(a.arun([{'role': 'user', 'content': 'a'}]),
                             b.arun([{'role': 'user', 'content': 'b'}]),
                             a.arun([{'role': 'user', 'content': 'another a'}]),
                             native_fixture(da, a, request_key='b' * 64))
    asyncio.run(run())
    assert len(rows(da)) == 2 and len(rows(db)) == 1
    assert usage.summarize(da / 'model_usage')['reported_tokens'] == 120
    assert usage.summarize(db / 'model_usage')['reported_tokens'] == 60
    assert len(list((da / 'actor_contract_receipts').glob('*.json'))) == 1


def test_cancelled_and_interrupted_calls_retain_unknown_usage(tmp_path, monkeypatch):
    async def respond(request):
        raise asyncio.CancelledError()
    model, directory = instance(tmp_path, monkeypatch, respond)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(model.arun([{'role': 'user', 'content': 'fixture'}]))
    assert rows(directory)[0]['error_type'] == 'CancelledError'
    # A process interrupted before context cleanup leaves the initial receipt.
    usage.Call(model._model_usage, model._request([{'role': 'user', 'content': 'pending'}], None, None))
    summary = usage.summarize(directory / 'model_usage')
    assert summary['provider_dispatch_attempts'] == 2
    assert summary['requests_with_unknown_usage'] == 2 and summary['unfinished_requests'] == 1
    assert summary['observed_accounting_complete'] is False


def test_missing_reused_or_misbound_ledger_is_not_zero_cost(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError): usage.summarize(tmp_path / 'missing')
    model, directory = instance(tmp_path, monkeypatch, lambda _: pytest.fail('Unexpected dispatch'))
    with pytest.raises(FileExistsError): usage.ModelUsage(directory, wire.configured_provider_contract())
    with pytest.raises(ValueError, match='identity'):
        usage.summarize(directory / 'model_usage', simulation_id='another_simulation')
    with pytest.raises(ValueError, match='identity'):
        usage.summarize(directory / 'model_usage', config_sha256='0' * 64)
    manifest = directory / 'model_usage/MANIFEST.json'
    value = json.loads(manifest.read_text()); value['module_sha256'] = '0' * 64
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='identity'): usage.summarize(directory / 'model_usage')


def test_actual_patched_runner_passes_its_own_simulation_directory(patched_backend, monkeypatch, tmp_path):
    path = patched_backend / 'scripts/run_reddit_simulation.py'
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RedditSimulationRunner')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_create_model')
    namespace = {'os': os}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    calls = []
    monkeypatch.setitem(__import__('sys').modules, 'app.utils.camel_responses',
                        SimpleNamespace(create_simulation_model=lambda *a, **k: calls.append(k)))
    monkeypatch.setitem(__import__('sys').modules, 'app.utils.model_usage', usage)
    monkeypatch.setenv('LLM_API_KEY', 'fixture'); monkeypatch.setenv('LLM_MODEL_NAME', PROFILE_MODEL)
    runner = SimpleNamespace(config={'native_model_usage': usage.VERSION}, simulation_dir=str(tmp_path))
    namespace['_create_model'](runner)
    assert calls == [{'usage_simulation_dir': str(tmp_path)}]
    runner.config = {}; namespace['_create_model'](runner)
    assert calls[-1] == {'usage_simulation_dir': None}
    runner.config = {'native_model_usage': 'unknown'}
    with pytest.raises(ValueError): namespace['_create_model'](runner)


def test_native_employee_retains_separate_usage_and_auditable_copy(tmp_path, monkeypatch):
    from worldlab.employees import NativeEmployees, audit_social_usage
    model, directory = instance(tmp_path, monkeypatch,
        lambda _: httpx.Response(200, json=profile_response('social fixture')))
    asyncio.run(model.arun([{'role': 'user', 'content': 'fixture'}]))
    out = tmp_path / 'actors'; out.mkdir()
    (out / 'evaluation_interview_ledger.json').write_text(json.dumps({'requests': [
        {'physical_model_calls': 1, 'tokens': 17, 'accounting_complete': True}]}))
    (out / 'mirofish_state.json').write_text(json.dumps({'simulation': {'simulation_id': directory.name}}))
    events = []
    driver = object.__new__(NativeEmployees)
    driver.out = out
    driver.factory = SimpleNamespace(meter_social_calls=True, provider=wire.configured_provider_contract())
    driver.runtime = SimpleNamespace(sim_dir=directory, close=lambda: events.append('native_closed'),
                                     client=SimpleNamespace(close=lambda: events.append('client_closed')))
    result = driver.usage()
    assert result['model_calls'] == 1 and result['tokens'] == 17
    assert result['social_model_usage']['provider_dispatch_attempts'] == 1
    assert result['social_model_usage']['reported_tokens'] == 60
    driver.close()
    assert events == ['native_closed', 'client_closed']
    identity = {'meter_social_calls': True, 'provider': wire.configured_provider_contract()}
    assert audit_social_usage(out, identity, result) == result['social_model_usage']
    receipt = next((out / 'model_usage/calls').glob('*.json'))
    value = json.loads(receipt.read_text()); value['total_tokens'] += 1
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='accounting'): audit_social_usage(out, identity, result)


def test_unknown_social_usage_remains_unknown_in_employee_summary(tmp_path, monkeypatch):
    from worldlab.employees import NativeEmployees
    model, directory = instance(tmp_path, monkeypatch, lambda _: pytest.fail('Unexpected dispatch'))
    usage.Call(model._model_usage, model._request([{'role': 'user', 'content': 'pending'}], None, None))
    driver = object.__new__(NativeEmployees)
    driver.out = tmp_path / 'no_interview_receipts'
    driver.factory = SimpleNamespace(meter_social_calls=True, provider=wire.configured_provider_contract())
    driver.runtime = SimpleNamespace(sim_dir=directory)
    result = driver.usage()
    assert result['tokens'] == 0 and result['bootstrap_and_social_tokens'] is None
    assert result['whole_actor_accounting_complete'] is False
    assert result['social_model_usage']['requests_with_unknown_usage'] == 1
    assert result['social_model_usage']['observed_accounting_complete'] is False
