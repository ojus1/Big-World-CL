"""Two native requests through the attempt meter's intended Unix socket path.

Component qualification only. No workplace state or benchmark task is used.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time

from aiohttp import ClientSession, UnixConnector, web

from .chat_budget_gateway import METER, audit_meter, create_app, encoded, sha
from .contracts import Budget


async def qualify(upstream, tokenizer, model, out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    budget = Budget(model_calls=2, output_tokens=128, total_tokens=12000, seconds=120)
    schema = {'type': 'json_schema', 'json_schema': {'name': 'transport_control', 'strict': True,
        'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                   'required': ['ok'], 'additionalProperties': False}}}
    cases = [
        {'model': model, 'messages': [{'role': 'user', 'content': 'Return JSON with ok set to true.'}],
         'max_tokens': 500, 'stream': False, 'response_format': schema, 'temperature': 0},
        {'model': model, 'messages': [{'role': 'user', 'content': 'Call record_value exactly once with value 7.'}],
         'max_tokens': 500, 'stream': True, 'temperature': 0,
         'tools': [{'type': 'function', 'function': {'name': 'record_value', 'description': 'Record a number.',
                    'parameters': {'type': 'object', 'properties': {'value': {'type': 'integer', 'enum': [7]}},
                                   'required': ['value'], 'additionalProperties': False}}}]}]
    plan = {'kind': 'native_attempt_chat_meter_component_qualification',
            'started_at': datetime.now(timezone.utc).isoformat(), 'upstream': upstream, 'tokenizer': tokenizer,
            'model': model, 'budget': asdict(budget), 'cases': cases,
            'source_sha256': {name: sha(Path(__file__).with_name(name).read_bytes())
                              for name in ('qualify_chat_budget.py', 'chat_budget_gateway.py', 'contracts.py')},
            'scope': 'JSON schema and streamed tool-call transport through a Unix socket, tokenizer reservation and offline usage audit. No Fluso execution, harness isolation, native skill read or learning claim.'}
    (out / 'PLAN.json').write_bytes(encoded(plan))
    app = create_app(upstream, tokenizer, model, budget, out / 'meter')
    runner = web.AppRunner(app, handler_cancellation=True)
    started = time.monotonic()
    try:
        await runner.setup()
        with tempfile.TemporaryDirectory(prefix='worldlab-meter-') as tmp:
            socket = str(Path(tmp) / 'model.sock')
            site = web.UnixSite(runner, socket); await site.start()
            async with ClientSession(connector=UnixConnector(path=socket)) as client:
                for i, case in enumerate(cases):
                    async with client.post('http://attempt/v1/chat/completions', json=case) as response:
                        raw = await response.read()
                        (out / f'client-{i}.bin').write_bytes(raw)
                        if response.status != 200: raise ValueError('Native qualification HTTP error')
            meter = app[METER].snapshot()
            if meter['physical_model_calls'] != 2 or meter['stopped'] or not meter['accounting_complete']:
                raise ValueError('Native meter did not complete both declared calls')
            first = json.loads((out / 'client-0.bin').read_bytes())
            if json.loads(first['choices'][0]['message']['content']) != {'ok': True}:
                raise ValueError('Structured JSON control did not match')
            calls = {}
            for line in (out / 'client-1.bin').read_text().splitlines():
                if not line.startswith('data: ') or line == 'data: [DONE]': continue
                value = json.loads(line[6:])
                for choice in value.get('choices', []):
                    for part in choice.get('delta', {}).get('tool_calls', []):
                        call = calls.setdefault(part['index'], {'name': '', 'arguments': ''})
                        for key in call: call[key] += part.get('function', {}).get(key, '')
            if len(calls) != 1 or calls[0]['name'] != 'record_value' or json.loads(calls[0]['arguments']) != {'value': 7}:
                raise ValueError('Streamed native tool-call control did not match')
        result = audit_meter(out / 'meter', budget=budget, model=model, upstream=upstream, tokenizer=tokenizer)
        report = {'ok': True, 'plan_sha256': sha((out / 'PLAN.json').read_bytes()),
                  'seconds': time.monotonic() - started, 'audit': result,
                  'controls': ['structured_json_true', 'streamed_record_value_7'], 'scope': plan['scope']}
    except BaseException as exc:
        (out / 'FAILURE.json').write_bytes(encoded({'error_type': type(exc).__name__,
            'seconds': time.monotonic() - started, 'meter': app[METER].snapshot()}))
        raise
    finally:
        await runner.cleanup()
    (out / 'REPORT.json').write_bytes(encoded(report))
    return report


def main():
    import asyncio
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8011')
    parser.add_argument('--tokenizer', default='http://127.0.0.1:8002')
    parser.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(qualify(args.upstream, args.tokenizer, args.model, args.out)), indent=2))


if __name__ == '__main__': main()
