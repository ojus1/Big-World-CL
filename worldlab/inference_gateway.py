"""Shared concurrency limit across employee, solver, judge and learner processes.

JSON and SSE bytes pass through unchanged. No model retries or prompt logging.
Point every participating adapter at this endpoint, rather than the upstream.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector, web

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'content-length'}
GATEWAY = web.AppKey('gateway', object)


def headers(values):
    excluded = HOP_HEADERS | {name.strip().lower() for name in values.get('Connection', '').split(',')}
    return {key: value for key, value in values.items() if key.lower() not in excluded}


class Gateway:
    def __init__(self, upstream, concurrency):
        parsed = urlsplit(upstream)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username):
            raise ValueError('Upstream must be a loopback HTTP origin without credentials or a path')
        if type(concurrency) is not int or not 1 <= concurrency <= 64:
            raise ValueError('LLM concurrency must be an integer from 1 to 64')
        self.upstream = upstream.rstrip('/')
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.counts = dict(active=0, peak_active=0, queued=0, peak_queued=0,
                           started=0, completed=0, upstream_error_responses=0,
                           transport_errors=0, cancelled=0)
        self.client = None

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
        try:
            async with self.slot():
                body = await request.read()
                async with self.client.request(request.method, self.upstream + request.rel_url.raw_path_qs,
                        data=body, headers=headers(request.headers), allow_redirects=False) as response:
                    if response.status >= 400:
                        self.counts['upstream_error_responses'] += 1
                    downstream = web.StreamResponse(status=response.status, headers=headers(response.headers))
                    await downstream.prepare(request)
                    async for chunk in response.content.iter_chunked(65536):
                        await downstream.write(chunk)
                    await downstream.write_eof()
                    self.counts['completed'] += 1
                    return downstream
        except asyncio.CancelledError:
            self.counts['cancelled'] += 1
            raise
        except (ClientError, ConnectionError, OSError, asyncio.TimeoutError):
            self.counts['transport_errors'] += 1
            if downstream is not None and downstream.prepared:
                # A partial response must remain a transport failure, not a
                # successful shortened model output. Never replay the request.
                request.transport.close() if request.transport is not None else None
                return downstream
            return web.json_response({'error': {'type': 'upstream_transport_error'}}, status=502)

    async def status(self, request):
        return web.json_response({'llm_concurrency': self.concurrency, 'upstream': self.upstream,
                                  'retries': 0, **self.counts})


def create_app(upstream='http://127.0.0.1:8000', concurrency=64):
    gateway = Gateway(upstream, concurrency)
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app[GATEWAY] = gateway

    async def client_context(app):
        async with ClientSession(connector=TCPConnector(limit=concurrency),
                timeout=ClientTimeout(total=None, sock_connect=30, sock_read=None),
                auto_decompress=False, trust_env=False) as client:
            gateway.client = client
            yield

    app.cleanup_ctx.append(client_context)
    app.router.add_get('/status', gateway.status)
    app.router.add_route('*', '/v1/{path:.*}', gateway.proxy)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8000')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--concurrency', type=int, default=64)
    args = parser.parse_args()
    web.run_app(create_app(args.upstream, args.concurrency), host='127.0.0.1', port=args.port,
                access_log=None, handler_cancellation=True)


if __name__ == '__main__':
    main()
