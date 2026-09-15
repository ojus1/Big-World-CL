"""Compare upstream connection policies and stress fresh connections at 64.

Synthetic structured-output transport controls only, not workplace throughput.
No model retries. Every planned request, including failures, is retained.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

from .inference_gateway import create_app, GATEWAY
from .chat_budget_gateway import usage_from_response


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serving():
    raw = json.loads(subprocess.check_output(['docker', 'inspect', 'bigworld-qwen38flashnext-throughput-v2']))[0]
    if raw['State']['Status'] != 'running':
        raise ValueError('Configured native model container is not running')
    return {'id': raw['Id'], 'image_id': raw['Image'], 'image_reference': raw['Config']['Image'],
            'started_at': raw['State']['StartedAt'], 'command_sha256': hashlib.sha256(encoded(raw['Config']['Cmd'])).hexdigest()}


SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean', 'enum': [True]}},
          'required': ['ok'], 'additionalProperties': False}
CONTEXT = ('This is a synthetic transport control. The requested JSON object is independent of these repeated context notes.\n' * 36)


def request(model, index):
    mode = ('responses_json', 'chat_json', 'chat_sse')[index % 3]
    messages = [{'role': 'system', 'content': CONTEXT},
                {'role': 'user', 'content': f'Control {index}. Return exactly a JSON object with ok set to true.'}]
    if mode == 'responses_json':
        body = {'model': model, 'input': messages, 'stream': False, 'store': False,
                'max_output_tokens': 128, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False},
                'text': {'format': {'type': 'json_schema', 'name': 'transport_control', 'strict': True, 'schema': SCHEMA}}}
        return mode, '/v1/responses', body
    body = {'model': model, 'messages': messages, 'stream': mode == 'chat_sse',
            'max_tokens': 128, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'transport_control', 'strict': True, 'schema': SCHEMA}}}
    if body['stream']:
        body['stream_options'] = {'include_usage': True}
    return mode, '/v1/chat/completions', body


def inspect_response(raw, mode):
    if mode == 'responses_json':
        value = json.loads(raw)
        terminal = value['status'] == 'completed'
        usage = value['usage']
        tokens = [usage[k] for k in ('input_tokens', 'output_tokens', 'total_tokens')]
        text = ''.join(p['text'] for item in value['output'] if item['type'] == 'message'
                       for p in item['content'] if p['type'] == 'output_text')
    else:
        terminal = True
        usage = usage_from_response(raw, mode == 'chat_sse')
        tokens = [usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
        if mode == 'chat_json':
            text = json.loads(raw)['choices'][0]['message']['content']
        else:
            text = ''.join(choice.get('delta', {}).get('content') or ''
                for line in raw.decode().splitlines() if line.startswith('data: ') and line != 'data: [DONE]'
                for choice in json.loads(line[6:]).get('choices', []))
    if not (all(type(n) is int and n >= 0 for n in tokens) and tokens[0] + tokens[1] == tokens[2]):
        raise ValueError('Invalid native token usage')
    try:
        matches = json.loads(text) == {'ok': True}
    except (ValueError, TypeError):
        matches = False
    return tokens[2], terminal and tokens[1] <= 128 and matches


async def qualify(out, upstream, model):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    phases = [('warmup', 'fresh', 64), ('keepalive-a', 'keepalive', 128), ('fresh-a', 'fresh', 128),
              ('fresh-b', 'fresh', 128), ('keepalive-b', 'keepalive', 128), ('fresh-stress', 'fresh', 512)]
    plan = {'kind': 'gateway_connections_native_v1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'phases': phases, 'model': model, 'upstream': upstream, 'concurrency': 64,
            'request_timeout_seconds': 120, 'retries': 0, 'serving': serving(),
            'source_sha256': {name: sha(Path(__file__).with_name(name)) for name in
                              ('qualify_gateway.py', 'inference_gateway.py', 'chat_budget_gateway.py')},
            'request_examples': [request(model, i) for i in range(3)], 'planned_requests': sum(n for _, _, n in phases),
            'scope': 'Synthetic transport controls with repeated context and tiny structured completions. '
                     'Not workplace throughput or proof of the earlier HTTP 502 cause. All requests retained; no retries.'}
    (out / 'PLAN.json').write_bytes(encoded(plan))
    records, offset = [], 0
    for name, policy, count in phases:
        root = out / name; root.mkdir()
        app = create_app(upstream, 64, connection_policy=policy, event_path=root / 'EVENTS.jsonl')
        runner = web.AppRunner(app, handler_cancellation=True)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
        base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        (root / 'START.json').write_bytes(encoded(app[GATEWAY].identity()))
        started = time.monotonic()
        try:
            async with ClientSession(connector=TCPConnector(limit=64), timeout=ClientTimeout(total=120), trust_env=False) as client:
                async def one(index):
                    dest = root / f'request-{index:04d}'; dest.mkdir()
                    mode, path, body = request(model, index)
                    (dest / 'REQUEST.json').write_bytes(encoded({'path': path, 'mode': mode, 'body': body}))
                    result = {'index': index, 'mode': mode, 'ok': False, 'reported_tokens': None}
                    clock = time.monotonic()
                    try:
                        async with client.post(base + path, json=body) as response:
                            result['status'] = response.status
                            result['request_id'] = response.headers.get('X-Request-ID')
                            raw = await response.read(); (dest / 'RESPONSE.bin').write_bytes(raw)
                            if response.status != 200: raise ValueError('Native gateway HTTP error')
                            result['reported_tokens'], result['ok'] = inspect_response(raw, mode)
                            if not result['ok']:
                                result['error_type'] = 'ControlMismatchWithKnownUsage'
                    except Exception as exc:
                        result['error_type'] = type(exc).__name__
                    result['seconds'] = time.monotonic() - clock
                    (dest / 'RESULT.json').write_bytes(encoded(result))
                    return result
                rows = await asyncio.gather(*(one(i) for i in range(offset, offset + count)))
            seconds = time.monotonic() - started
            gateway = {**app[GATEWAY].identity(), **app[GATEWAY].counts}
        finally:
            await runner.cleanup()
        record = {'phase': name, 'policy': policy, 'requests': count, 'seconds': seconds,
                  'requests_per_second': count / seconds, 'successful_controls': sum(r['ok'] for r in rows),
                  'reported_tokens': sum(r['reported_tokens'] or 0 for r in rows),
                  'requests_with_unknown_usage': sum(r['reported_tokens'] is None for r in rows), 'gateway': gateway}
        (root / 'REPORT.json').write_bytes(encoded(record)); records.append(record)
        print(json.dumps(record), flush=True)
        offset += count
    if serving() != plan['serving']:
        raise ValueError('Model serving container changed during qualification')
    ok = all(r['successful_controls'] == r['requests'] and not r['requests_with_unknown_usage']
             and r['gateway']['active'] == 0 and r['gateway']['queued'] == 0
             and not r['gateway']['transport_errors'] and r['gateway']['peak_active'] <= 64
             and r['gateway']['started'] == r['requests'] and r['gateway']['completed'] == r['requests']
             and (r['policy'] != 'fresh' or (r['gateway']['connections_created'] == r['requests']
                                           and r['gateway']['connections_reused'] == 0)) for r in records)
    report = {'ok': ok, 'plan_sha256': sha(out / 'PLAN.json'), 'phases': records,
              'planned_requests': plan['planned_requests'], 'reported_tokens': sum(r['reported_tokens'] for r in records),
              'requests_with_unknown_usage': sum(r['requests_with_unknown_usage'] for r in records), 'scope': plan['scope']}
    (out / 'REPORT.json').write_bytes(encoded(report))
    files = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    (out / 'EXPORT.json').write_bytes(encoded({'files': files}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--upstream', default='http://127.0.0.1:8002')
    parser.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    args = parser.parse_args()
    report = asyncio.run(qualify(args.out, args.upstream, args.model))
    print(json.dumps({k: v for k, v in report.items() if k != 'phases'}, indent=2))


if __name__ == '__main__': main()
