"""One attempt's text/tool Chat Completions budget, ahead of the shared gateway.

The controller owns this process and its receipts. A harness must reach it only
through its isolated relay; this module alone does not isolate a harness. No
provider retries, auxiliary model aliases, prompt truncation or character caps.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from .contracts import Budget

METER = web.AppKey('attempt_meter', object)


def require(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def origin(value):
    p = urlsplit(value)
    require(p.scheme == 'http' and p.hostname in ('127.0.0.1', 'localhost', '::1')
            and p.path in ('', '/') and not (p.username or p.password or p.query or p.fragment),
            'Use a fixed loopback HTTP upstream origin')
    return value.rstrip('/')


def wire_request(value, model, output_limit):
    require(isinstance(value, dict) and value.get('model') == model, 'Unexpected model')
    require(type(value.get('stream', False)) is bool and value.get('n', 1) == 1
            and type(value.get('n', 1)) is int, 'One completion per request is supported')
    require(isinstance(value.get('messages'), list) and value['messages'], 'Expected chat messages')
    require(value.get('tool_choice') in (None, 'auto'), 'Only automatic tool selection is qualified')
    forbidden = ('prompt', 'prompt_embeds', 'input', 'chat_template', 'add_generation_prompt',
                 'continue_final_message', 'add_special_tokens', 'mm_processor_kwargs', 'media_io_kwargs',
                 'truncate_prompt_tokens', 'echo')
    require(not any(k in value for k in forbidden), 'Unqualified prompt rendering option')
    for message in value['messages']:
        require(isinstance(message, dict), 'Invalid chat message')
        content = message.get('content')
        require(content is None or isinstance(content, str) or (
            isinstance(content, list) and all(isinstance(p, dict) and p.get('type') == 'text'
                and isinstance(p.get('text'), str) and set(p) <= {'type', 'text'} for p in content)),
            'This profile supports text and tool messages only')
    proposed = [value[k] for k in ('max_tokens', 'max_completion_tokens') if k in value and value[k] is not None]
    require(all(type(v) is int and v > 0 for v in proposed), 'Invalid output-token cap')
    result = json.loads(encoded(value))
    result.pop('max_completion_tokens', None)
    result.pop('reasoning_effort', None)
    result['max_tokens'] = min([output_limit, *proposed])
    result['chat_template_kwargs'] = {'enable_thinking': False}
    result['stream'] = value.get('stream', False)
    if result['stream']:
        result['stream_options'] = {'include_usage': True}
    else:
        result.pop('stream_options', None)
    return result


def tokenizer_request(wire):
    return {k: wire[k] for k in ('model', 'messages', 'tools', 'chat_template_kwargs') if k in wire}


def usage_from_response(raw, streaming):
    """Require a terminal choice and complete usage, including through SSE EOF."""
    if streaming:
        events, pending = [], []
        for line in raw.decode('utf-8').splitlines() + ['']:
            if not line:
                if pending:
                    events.append('\n'.join(pending)); pending = []
            elif line.startswith('data:'):
                pending.append(line[5:].lstrip(' '))
        require(events and events[-1] == '[DONE]' and events.count('[DONE]') == 1,
                'Stream ended without exactly one terminal DONE event')
        values = [json.loads(v) for v in events[:-1]]
    else:
        values = [json.loads(raw)]
    usages, finishes = [], []
    for value in values:
        require(isinstance(value, dict) and 'error' not in value, 'Provider response contains an error')
        for choice in value.get('choices', []):
            require(choice.get('index') == 0, 'Unexpected completion index')
            if choice.get('finish_reason') is not None:
                finishes.append(choice['finish_reason'])
        if value.get('usage') is not None:
            usages.append(value['usage'])
    require(finishes and all(v in ('stop', 'length', 'tool_calls') for v in finishes),
            'Missing or unsupported terminal choice')
    require(usages and all(v == usages[0] for v in usages), 'Missing or contradictory usage')
    usage = usages[0]
    require(isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
            and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'],
            'Invalid provider usage')
    return {k: usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}


class AttemptGateway:
    def __init__(self, upstream, tokenizer, model, budget, out):
        self.upstream, self.tokenizer = origin(upstream), origin(tokenizer)
        require(isinstance(model, str) and model and isinstance(budget, Budget), 'Invalid attempt identity')
        self.model, self.budget, self.out = model, budget, Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.lock = asyncio.Lock()
        self.client = None
        self.rows, self.preflights = [], []
        self.stopped = self.exhausted = False
        self.stop_reason = None
        self.blocked_requests = 0
        self.flush()

    def remaining_seconds(self):
        return max(0., self.budget.seconds - (time.monotonic() - self.started))

    def snapshot(self):
        return {'version': 'attempt-chat-budget-v1', 'upstream': self.upstream, 'tokenizer': self.tokenizer,
                'implementation_sha256': sha(Path(__file__).read_bytes()),
                'model': self.model, 'budget': asdict(self.budget),
                'profile': 'text_tools_chat_no_thinking_single_choice_v1', 'retries': 0,
                'physical_model_calls': len(self.rows),
                'charged_tokens': sum(r['charged_tokens'] for r in self.rows),
                'reported_tokens': sum(r['usage']['total_tokens'] for r in self.rows if r.get('usage')),
                'accounting_complete': all(r['accounting'] == 'reported' for r in self.rows),
                'stopped': self.stopped, 'exhausted': self.exhausted, 'stop_reason': self.stop_reason,
                'blocked_requests': self.blocked_requests, 'operations': self.rows,
                'tokenizer_preflights': self.preflights}

    def flush(self):
        temporary = self.out / '.METER.json.tmp'
        temporary.write_bytes(encoded(self.snapshot()))
        temporary.replace(self.out / 'METER.json')

    def stop(self, reason, *, exhausted=False):
        self.stopped, self.exhausted, self.stop_reason = True, exhausted, self.stop_reason or reason
        self.flush()

    async def models(self, request):
        return web.json_response({'object': 'list', 'data': [{'id': self.model, 'object': 'model'}]})

    async def status(self, request):
        return web.json_response(self.snapshot())

    async def proxy(self, request):
        # Native auxiliary requests share the same attempt and cannot race its
        # reservations or retry after a terminal error. Different attempts run
        # concurrently through the global concurrency-64 upstream.
        async with self.lock:
            if self.stopped or len(self.rows) >= self.budget.model_calls or not self.remaining_seconds():
                self.blocked_requests += 1
                if not self.stopped:
                    self.stop('call_or_time_budget', exhausted=True)
                self.flush()
                return web.json_response({'error': {'type': 'attempt_stopped'}}, status=402)
            try:
                original = await request.read()
                wire = wire_request(json.loads(original), self.model, self.budget.output_tokens)
            except (ValueError, TypeError, UnicodeError):
                return web.json_response({'error': {'type': 'unqualified_request'}}, status=400)
            index = len(self.preflights)
            root = self.out / f'call-{index:04d}'; root.mkdir()
            (root / 'INPUT.json').write_bytes(original)
            tokenize = encoded(tokenizer_request(wire))
            (root / 'TOKENIZE_REQUEST.json').write_bytes(tokenize)
            preflight = {'path': root.name, 'status': 'tokenizing', 'input_sha256': sha(original),
                         'tokenize_request_sha256': sha(tokenize)}
            self.preflights.append(preflight); self.flush()
            row, downstream = None, None
            try:
                async with self.client.post(self.tokenizer + '/tokenize', data=tokenize,
                        headers={'Content-Type': 'application/json'}, allow_redirects=False,
                        timeout=ClientTimeout(total=max(.001, self.remaining_seconds()))) as response:
                    raw = await response.read(); (root / 'TOKENIZE_RESPONSE.json').write_bytes(raw)
                    preflight['response_sha256'], preflight['http_status'] = sha(raw), response.status
                    require(response.status == 200, 'Tokenizer HTTP error')
                    tokens = json.loads(raw).get('count')
                    require(type(tokens) is int and tokens >= 0, 'Invalid tokenizer count')
                remaining = self.budget.total_tokens - self.snapshot()['charged_tokens'] - tokens
                if remaining < 1 or not self.remaining_seconds():
                    preflight['status'] = 'budget_blocked'; self.blocked_requests += 1
                    self.stop('token_or_time_budget', exhausted=True)
                    return web.json_response({'error': {'type': 'attempt_budget_exhausted'}}, status=402)
                wire['max_tokens'] = min(wire['max_tokens'], remaining)
                body = encoded(wire); (root / 'WIRE_REQUEST.json').write_bytes(body)
                preflight['status'] = 'generation_dispatched'
                reserve = tokens + wire['max_tokens']
                row = {'path': root.name, 'dispatch': len(self.rows) + 1, 'status': 'dispatched',
                       'request_sha256': sha(body), 'tokenized_prompt_tokens': tokens,
                       'output_cap': wire['max_tokens'], 'reserved_tokens': reserve,
                       'charged_tokens': reserve, 'accounting': 'reservation', 'usage': None}
                self.rows.append(row); self.flush()
                started = time.monotonic()
                async with self.client.post(self.upstream + '/v1/chat/completions', data=body,
                        headers={'Content-Type': 'application/json'}, allow_redirects=False,
                        timeout=ClientTimeout(total=max(.001, self.remaining_seconds()))) as response:
                    row['http_status'] = response.status
                    downstream = web.StreamResponse(status=response.status,
                        headers={'Content-Type': response.headers.get('Content-Type', 'application/json')})
                    await downstream.prepare(request)
                    with (root / 'RESPONSE.bin').open('xb') as stream:
                        async for chunk in response.content.iter_chunked(65536):
                            stream.write(chunk)
                            await downstream.write(chunk)
                    raw = (root / 'RESPONSE.bin').read_bytes()
                    row['response_sha256'] = sha(raw)
                    row['upstream_eof'] = True
                    require(response.status == 200, 'Generation HTTP error')
                    usage = usage_from_response(raw, wire['stream'])
                    row.update(usage=usage, accounting='reported', charged_tokens=usage['total_tokens'])
                    require(usage['prompt_tokens'] <= tokens and usage['completion_tokens'] <= wire['max_tokens']
                            and usage['total_tokens'] <= reserve, 'Provider exceeded its reservation')
                    row['status'] = 'completed'
                    row['seconds'] = time.monotonic() - started
                    self.flush()
                    await downstream.write_eof()
                    return downstream
            except BaseException as exc:
                if row is not None:
                    row['status'] = 'failed'
                    row['error_type'] = type(exc).__name__
                    if (root / 'RESPONSE.bin').exists():
                        row['response_sha256'] = sha((root / 'RESPONSE.bin').read_bytes())
                else:
                    preflight['status'] = 'failed'; preflight['error_type'] = type(exc).__name__
                self.stop('generation_or_accounting_failure' if row is not None else 'tokenizer_failure')
                if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise
                if downstream is not None and downstream.prepared:
                    if request.transport is not None:
                        request.transport.close()
                    return downstream
                return web.json_response({'error': {'type': self.stop_reason}}, status=502)


def create_app(upstream, tokenizer, model, budget, out):
    meter = AttemptGateway(upstream, tokenizer, model, budget, out)
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app[METER] = meter

    async def client_context(app):
        async with ClientSession(auto_decompress=False, trust_env=False,
                headers={'Accept-Encoding': 'identity'}) as client:
            meter.client = client
            yield
        meter.flush()

    app.cleanup_ctx.append(client_context)
    app.router.add_get('/v1/models', meter.models)
    app.router.add_get('/status', meter.status)
    app.router.add_post('/v1/chat/completions', meter.proxy)
    return app


def audit_meter(out, *, budget, model, upstream, tokenizer):
    """Recompute a terminal meter's bounds and usage from its retained wire bytes.

    A passing audit can describe a failed attempt or incomplete accounting. It
    establishes receipt consistency, not a successful harness/task execution.
    """
    out = Path(out)
    meter = json.loads((out / 'METER.json').read_bytes())
    require(meter['version'] == 'attempt-chat-budget-v1' and meter['implementation_sha256'] == sha(Path(__file__).read_bytes())
            and meter['budget'] == asdict(budget) and meter['model'] == model and meter['retries'] == 0
            and meter['upstream'] == origin(upstream) and meter['tokenizer'] == origin(tokenizer),
            'Meter source, budget or provider identity changed')
    rows = meter['operations']; preflights = meter['tokenizer_preflights']
    require(len(rows) == meter['physical_model_calls'] <= budget.model_calls
            and len({r['path'] for r in rows}) == len(rows), 'Invalid physical dispatch count')
    by_path = {r['path']: r for r in rows}
    charged = 0
    generated_paths = []
    for index, preflight in enumerate(preflights):
        require(preflight['path'] == f'call-{index:04d}' and preflight['status'] != 'tokenizing',
                'Invalid or unfinished tokenizer preflight')
        root = out / preflight['path']
        original = (root / 'INPUT.json').read_bytes()
        require(sha(original) == preflight['input_sha256'], 'Native request changed')
        wire = wire_request(json.loads(original), model, budget.output_tokens)
        tokenize = (root / 'TOKENIZE_REQUEST.json').read_bytes()
        require(sha(tokenize) == preflight['tokenize_request_sha256'] and
                tokenize == encoded(tokenizer_request(wire)), 'Tokenizer request changed')
        if 'response_sha256' in preflight:
            raw = (root / 'TOKENIZE_RESPONSE.json').read_bytes()
            require(sha(raw) == preflight['response_sha256'], 'Tokenizer response changed')
        row = by_path.get(preflight['path'])
        if row is None:
            require(preflight['status'] in ('budget_blocked', 'failed'), 'Generation receipt missing')
            continue
        generated_paths.append(preflight['path'])
        require(preflight['status'] == 'generation_dispatched' and preflight['http_status'] == 200,
                'Generation preceded tokenizer qualification')
        tokens = json.loads(raw)['count']
        require(type(tokens) is int and tokens >= 0 and tokens == row['tokenized_prompt_tokens'],
                'Prompt token reservation changed')
        available = budget.total_tokens - charged - tokens
        require(available > 0, 'Dispatch occurred after token exhaustion')
        wire['max_tokens'] = min(wire['max_tokens'], available)
        body = (root / 'WIRE_REQUEST.json').read_bytes()
        reserve = tokens + wire['max_tokens']
        require(body == encoded(wire) and sha(body) == row['request_sha256']
                and row['output_cap'] == wire['max_tokens'] and row['reserved_tokens'] == reserve,
                'Actual inference request or reservation changed')
        require(row['status'] in ('completed', 'failed'), 'Unfinished model dispatch')
        if 'response_sha256' in row:
            reply = (root / 'RESPONSE.bin').read_bytes()
            require(sha(reply) == row['response_sha256'], 'Provider response changed')
        if row['accounting'] == 'reported':
            require(row.get('upstream_eof') is True and row['http_status'] == 200, 'Usage lacks complete provider response')
            usage = usage_from_response(reply, wire['stream'])
            require(usage == row['usage'] and row['charged_tokens'] == usage['total_tokens'], 'Usage or charge changed')
            if row['status'] == 'completed':
                require(usage['prompt_tokens'] <= tokens and usage['completion_tokens'] <= wire['max_tokens']
                        and usage['total_tokens'] <= reserve, 'Successful dispatch exceeded budget')
        else:
            require(row['accounting'] == 'reservation' and row['status'] == 'failed'
                    and row['charged_tokens'] == reserve and row['usage'] is None, 'Unknown usage lost its reservation')
            if row.get('upstream_eof') is True and row.get('http_status') == 200:
                try:
                    usage_from_response(reply, wire['stream'])
                except (ValueError, UnicodeError):
                    pass
                else:
                    raise ValueError('Complete available provider usage was not credited')
        charged += row['charged_tokens']
    require(generated_paths == [r['path'] for r in rows]
            and [r['dispatch'] for r in rows] == list(range(1, len(rows) + 1)), 'Dispatch order changed')
    failed = any(r['status'] == 'failed' for r in rows)
    require(not failed or meter['stopped'] is True, 'Failure did not stop this attempt')
    require(all(r['status'] == 'completed' for r in rows[:-1]), 'A failed generation was automatically retried')
    require(meter['charged_tokens'] == charged
            and meter['reported_tokens'] == sum(r['usage']['total_tokens'] for r in rows if r.get('usage'))
            and meter['accounting_complete'] == all(r['accounting'] == 'reported' for r in rows),
            'Meter total or accounting completeness changed')
    return {'ok': True, 'physical_model_calls': len(rows), 'charged_tokens': charged,
            'accounting_complete': meter['accounting_complete'], 'stopped': meter['stopped'],
            'scope': 'Retained tokenizer/request/response bytes and budget arithmetic; not harness isolation, skill loading or task success'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8011')
    parser.add_argument('--tokenizer', default='http://127.0.0.1:8002')
    parser.add_argument('--model', required=True)
    parser.add_argument('--budget', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--socket', type=Path, required=True)
    args = parser.parse_args()
    app = create_app(args.upstream, args.tokenizer, args.model,
                     Budget(**json.loads(args.budget.read_text())), args.out)
    web.run_app(app, path=str(args.socket), access_log=None, handler_cancellation=True)


if __name__ == '__main__':
    main()
