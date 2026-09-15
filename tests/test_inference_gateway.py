import asyncio
from contextlib import asynccontextmanager
import unittest

try:
    from aiohttp import ClientSession, TCPConnector, web
    from worldlab.inference_gateway import create_app, GATEWAY
except ImportError:
    raise unittest.SkipTest('Install requirements-inference-gateway.txt in the gateway runtime')


@asynccontextmanager
async def serve(app):
    runner = web.AppRunner(app, handler_cancellation=True)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    try:
        yield 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    finally:
        await runner.cleanup()


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_eighty_independent_requests_reach_but_never_exceed_sixty_four(self):
        reached, release = asyncio.Event(), asyncio.Event()
        observed = {'active': 0, 'peak': 0, 'requests': 0}

        async def upstream(request):
            body = await request.read()
            observed['active'] += 1
            observed['requests'] += 1
            observed['peak'] = max(observed['peak'], observed['active'])
            if observed['active'] == 64:
                reached.set()
            try:
                await release.wait()
                return web.Response(body=body, content_type='application/json')
            finally:
                observed['active'] -= 1

        app = web.Application(); app.router.add_post('/v1/responses', upstream)
        async with serve(app) as origin:
            proxy = create_app(origin, 64)
            async with serve(proxy) as url, ClientSession(connector=TCPConnector(limit=0)) as client:
                async def call(index):
                    raw = ('{"input":"fixture ' + str(index) + '","text":{"format":{"type":"json_schema"}}}').encode()
                    async with client.post(url + '/v1/responses', data=raw) as response:
                        self.assertEqual(await response.read(), raw)
                jobs = [asyncio.create_task(call(i)) for i in range(80)]
                try:
                    await asyncio.wait_for(reached.wait(), 5)
                    self.assertEqual(observed['active'], 64)
                    self.assertEqual(proxy[GATEWAY].counts['active'], 64)
                finally:
                    release.set()
                await asyncio.wait_for(asyncio.gather(*jobs), 5)
                self.assertEqual(observed['requests'], 80)
                self.assertEqual(observed['peak'], 64)
                self.assertEqual(proxy[GATEWAY].counts['peak_active'], 64)
                self.assertEqual(proxy[GATEWAY].counts['active'], 0)
                self.assertEqual(proxy[GATEWAY].counts['queued'], 0)

    async def test_stream_holds_slot_until_eof_and_bytes_and_errors_are_preserved(self):
        release = asyncio.Event()
        seen = []
        async def upstream(request):
            body = await request.read(); seen.append(body)
            if body == b'fail':
                return web.Response(status=429, body=b'{"error":"fixture"}', headers={'Retry-After': '7'})
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            await response.write(b'data: {"delta":"a"}\n\n')
            await release.wait()
            await response.write(b'data: [DONE]\n\n')
            await response.write_eof()
            return response
        app = web.Application(); app.router.add_post('/v1/chat/completions', upstream)
        async with serve(app) as origin:
            proxy = create_app(origin, 1)
            async with serve(proxy) as url, ClientSession() as client:
                first = await client.post(url + '/v1/chat/completions', data=b'stream')
                self.assertEqual(await first.content.readuntil(b'\n\n'), b'data: {"delta":"a"}\n\n')
                second = asyncio.create_task(client.post(url + '/v1/chat/completions', data=b'fail'))
                await asyncio.sleep(.03)
                self.assertEqual(seen, [b'stream'])
                self.assertEqual(proxy[GATEWAY].counts['active'], 1)
                release.set()
                self.assertEqual(await first.read(), b'data: [DONE]\n\n')
                response = await asyncio.wait_for(second, 3)
                self.assertEqual(response.status, 429)
                self.assertEqual(response.headers['Retry-After'], '7')
                self.assertEqual(await response.read(), b'{"error":"fixture"}')
                self.assertEqual(seen, [b'stream', b'fail'])

    async def test_cancelled_waiter_does_not_leak_slot(self):
        gateway = create_app()[GATEWAY]
        gateway.semaphore = asyncio.Semaphore(1)
        async with gateway.slot():
            async def waiting():
                async with gateway.slot():
                    self.fail('Cancelled waiter was admitted')
            task = asyncio.create_task(waiting())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(gateway.counts['queued'], 0)
        async with gateway.slot():
            self.assertEqual(gateway.counts['active'], 1)
        self.assertEqual(gateway.counts['active'], 0)


if __name__ == '__main__':
    unittest.main()
