"""Shared concurrency limit across employee, solver, judge and learner processes.

JSON and SSE bytes pass through unchanged. No model retries or prompt logging.
Point every participating adapter at this endpoint, rather than the upstream.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector, TraceConfig, web
import aiohttp

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'content-length'}
GATEWAY = web.AppKey('gateway', object)


def headers(values):
    excluded = HOP_HEADERS | {name.strip().lower() for name in values.get('Connection', '').split(',')}
    return {key: value for key, value in values.items() if key.lower() not in excluded}


class Gateway:
    def __init__(self, upstream, concurrency, connection_policy='fresh', event_path=None):
        parsed = urlsplit(upstream)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username):
            raise ValueError('Upstream must be a loopback HTTP origin without credentials or a path')
        if type(concurrency) is not int or not 1 <= concurrency <= 64:
            raise ValueError('LLM concurrency must be an integer from 1 to 64')
        if connection_policy not in ('fresh', 'keepalive'):
            raise ValueError('Unknown upstream connection policy')
        self.upstream = upstream.rstrip('/')
        self.concurrency = concurrency
        self.connection_policy = connection_policy
        self.instance_id = uuid.uuid4().hex[:12]
        self.sequence = 0
        self.event_path = Path(event_path) if event_path is not None else None
        self.event_file = None
        self.semaphore = asyncio.Semaphore(concurrency)
        self.counts = dict(active=0, peak_active=0, queued=0, peak_queued=0,
                           started=0, completed=0, upstream_error_responses=0,
                           transport_errors=0, cancelled=0, connections_created=0, connections_reused=0)
        self.client = None

    def identity(self):
        return {'version': 'worldlab-inference-gateway-v2', 'instance_id': self.instance_id,
                'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'aiohttp_version': aiohttp.__version__, 'connection_policy': self.connection_policy,
                'llm_concurrency': self.concurrency, 'upstream': self.upstream, 'retries': 0}

    def event(self, kind, metadata):
        value = {'event': kind, 'utc': datetime.now(timezone.utc).isoformat(),
                 'instance_id': self.instance_id, **metadata}
        # No request/response bodies, query strings, credentials or exception text.
        destination = self.event_file if self.event_file is not None else sys.stderr
        print(json.dumps(value, sort_keys=True, allow_nan=False), file=destination, flush=True)

    @asynccontextmanager
    async def slot(self):
        self.counts['queued'] += 1
        self.counts['peak_queued'] = max(self.counts['peak_queued'], self.counts['queued'])
        try:
            await self.semaphore.acquire()
        finally:
            self.counts['queued'] -= 1
        self.counts['active'] += 1
        self.counts['started'] += 1
        self.counts['peak_active'] = max(self.counts['peak_active'], self.counts['active'])
        try:
            yield
        finally:
            self.counts['active'] -= 1
            self.semaphore.release()

    async def proxy(self, request):
        downstream = None
        self.sequence += 1
        request_id = f'wl-{self.instance_id}-{self.sequence}'
        route = request.match_info.get('path')
        metadata = {'request_id': request_id, 'method': request.method if request.method in ('GET', 'POST') else 'other',
                    'route': route if route in ('responses', 'chat/completions', 'models', 'props') else 'other',
                    'stage': 'waiting_slot', 'connection_created': False, 'connection_reused': False,
                    'headers_sent': False, 'sent_body_bytes': 0, 'response_bytes': 0,
                    'upstream_http_status': None}
        started = time.monotonic()
        try:
            async with self.slot():
                metadata['queue_seconds'] = time.monotonic() - started
                metadata['stage'] = 'reading_request'
                body = await request.read()
                metadata['stage'] = 'waiting_upstream_headers'
                outgoing = {k: v for k, v in headers(request.headers).items() if k.lower() != 'x-request-id'}
                outgoing['X-Request-ID'] = request_id
                async with self.client.request(request.method, self.upstream + request.rel_url.raw_path_qs,
                        data=body, headers=outgoing, allow_redirects=False, trace_request_ctx=metadata) as response:
                    metadata['upstream_http_status'] = response.status
                    if response.status >= 400:
                        self.counts['upstream_error_responses'] += 1
                        # Expected model-metadata misses stay in the counters.
                        if not (request.method == 'GET' and route == 'props' and response.status == 404):
                            self.event('upstream_http_error', {**metadata, 'seconds': time.monotonic() - started})
                    returned = {k: v for k, v in headers(response.headers).items() if k.lower() != 'x-request-id'}
                    returned['X-Request-ID'] = request_id
                    metadata['stage'] = 'starting_downstream_response'
                    downstream = web.StreamResponse(status=response.status, headers=returned)
                    await downstream.prepare(request)
                    metadata['stage'] = 'streaming_response'
                    async for chunk in response.content.iter_chunked(65536):
                        metadata['response_bytes'] += len(chunk)
                        await downstream.write(chunk)
                    await downstream.write_eof()
                    self.counts['completed'] += 1
                    return downstream
        except asyncio.CancelledError:
            self.counts['cancelled'] += 1
            self.event('client_cancelled', {**metadata, 'seconds': time.monotonic() - started})
            raise
        except (ClientError, ConnectionError, OSError, asyncio.TimeoutError) as exc:
            self.counts['transport_errors'] += 1
            details = {**metadata, 'error_type': type(exc).__name__, 'seconds': time.monotonic() - started}
            if type(getattr(exc, 'errno', None)) is int:
                details['errno'] = exc.errno
            self.event('transport_error', details)
            if downstream is not None and downstream.prepared:
                # A partial response must remain a transport failure, not a
                # successful shortened model output. Never replay the request.
                request.transport.close() if request.transport is not None else None
                return downstream
            return web.json_response({'error': {'type': 'upstream_transport_error', 'request_id': request_id}},
                                     status=502, headers={'X-Request-ID': request_id})

    async def status(self, request):
        return web.json_response({**self.identity(), **self.counts})


def create_app(upstream='http://127.0.0.1:8000', concurrency=64, *, connection_policy='fresh', event_path=None):
    gateway = Gateway(upstream, concurrency, connection_policy, event_path)
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app[GATEWAY] = gateway

    async def client_context(app):
        trace = TraceConfig()
        async def created(session, ctx, params):
            ctx.trace_request_ctx['connection_created'] = True
            gateway.counts['connections_created'] += 1
        async def reused(session, ctx, params):
            ctx.trace_request_ctx['connection_reused'] = True
            gateway.counts['connections_reused'] += 1
        async def sent_headers(session, ctx, params): ctx.trace_request_ctx['headers_sent'] = True
        async def sent_chunk(session, ctx, params): ctx.trace_request_ctx['sent_body_bytes'] += len(params.chunk)
        trace.on_connection_create_end.append(created)
        trace.on_connection_reuseconn.append(reused)
        trace.on_request_headers_sent.append(sent_headers)
        trace.on_request_chunk_sent.append(sent_chunk)
        if gateway.event_path is not None:
            gateway.event_file = gateway.event_path.open('x', encoding='utf-8')
        try:
            gateway.event('started', gateway.identity())
            async with ClientSession(connector=TCPConnector(limit=concurrency, force_close=connection_policy == 'fresh'),
                    timeout=ClientTimeout(total=None, sock_connect=30, sock_read=None), trace_configs=[trace],
                    auto_decompress=False, trust_env=False) as client:
                gateway.client = client
                yield
            gateway.event('stopped', gateway.counts)
        finally:
            if gateway.event_file is not None:
                gateway.event_file.close(); gateway.event_file = None

    app.cleanup_ctx.append(client_context)
    app.router.add_get('/status', gateway.status)
    app.router.add_route('*', '/v1/{path:.*}', gateway.proxy)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8000')
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--concurrency', type=int, default=64)
    parser.add_argument('--connection-policy', choices=('fresh', 'keepalive'), default='fresh')
    parser.add_argument('--events', type=Path, help='Fresh metadata-only JSONL event file; never overwrites')
    args = parser.parse_args()
    web.run_app(create_app(args.upstream, args.concurrency, connection_policy=args.connection_policy,
                           event_path=args.events), host='127.0.0.1', port=args.port,
                access_log=None, handler_cancellation=True)


if __name__ == '__main__':
    main()
