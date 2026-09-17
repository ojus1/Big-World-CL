import asyncio
import json
from pathlib import Path
import tempfile
import threading
import unittest

from aiohttp import ClientSession, web

from worldlab.chat_relay import Relay


class ChatRelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='relay-test-')
        self.seen = []
        self.release = asyncio.Event()
        self.upstream_finished = asyncio.Event()
        app = web.Application()

        async def models(request):
            self.seen.append((request.method, request.path, dict(request.headers), b''))
            return web.json_response({'data': [{'id': 'test'}]})

        async def chat(request):
            body = await request.read()
            self.seen.append((request.method, request.path, dict(request.headers), body))
            if json.loads(body).get('stream'):
                response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
                await response.prepare(request)
                await response.write(b'data: {"value":"first"}\n\n')
                await self.release.wait()
                if json.loads(body).get('disconnect'):
                    for _ in range(10):
                        await response.write(b'data: ' + b'x' * 65536 + b'\n\n')
                await response.write(b'data: [DONE]\n\n')
                self.upstream_finished.set()
                return response
            return web.Response(body=body, content_type='application/json', status=201)

        app.router.add_get('/v1/models', models)
        app.router.add_post('/v1/chat/completions', chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        socket = str(Path(self.tmp.name) / 'meter.sock')
        await web.UnixSite(self.runner, socket).start()
        self.relay = Relay(('127.0.0.1', 0), socket, 5)
        self.thread = threading.Thread(target=self.relay.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.relay.server_port)
        self.client = ClientSession()

    async def asyncTearDown(self):
        self.release.set()
        await self.client.close()
        await asyncio.to_thread(self.relay.shutdown)
        self.relay.server_close()
        self.thread.join()
        await self.runner.cleanup()
        self.tmp.cleanup()

    async def test_native_bytes_and_headers(self):
        body = b'{"model":"test","messages":[{"role":"user","content":"caf\xc3\xa9"}]}'
        async with self.client.post(self.base + '/v1/chat/completions', data=body,
                headers={'Authorization': 'Bearer synthetic-not-a-secret', 'X-Upstream': 'http://other'}) as r:
            self.assertEqual(r.status, 201)
            self.assertEqual(await r.read(), body)
        headers = self.seen[0][2]
        self.assertNotIn('Authorization', headers)
        self.assertNotIn('X-Upstream', headers)
        self.assertEqual(headers['Host'], 'attempt')

    async def test_stream_does_not_wait_for_eof(self):
        async with self.client.post(self.base + '/v1/chat/completions', json={'stream': True}) as r:
            first = await asyncio.wait_for(r.content.readuntil(b'\n\n'), 2)
            self.assertEqual(first, b'data: {"value":"first"}\n\n')
            self.release.set()
            self.assertEqual(await r.read(), b'data: [DONE]\n\n')

    async def test_fixed_routes_and_methods(self):
        for path in ('/status', '/tokenize', '/v1/models?upstream=other', '/v1/chat/completions/extra'):
            async with self.client.get(self.base + path) as r:
                self.assertEqual(r.status, 404)
        async with self.client.post(self.base + '/v1/models', json={}) as r:
            self.assertEqual(r.status, 404)
        async with self.client.get(self.base + '/v1/models') as r:
            self.assertEqual((await r.json())['data'][0]['id'], 'test')
        self.assertEqual(len(self.seen), 1)

    async def test_client_exit_still_drains_upstream(self):
        r = await self.client.post(self.base + '/v1/chat/completions', json={'stream': True, 'disconnect': True})
        await r.content.readuntil(b'\n\n')
        r.close()
        self.release.set()
        await asyncio.wait_for(self.upstream_finished.wait(), 2)

    async def test_shutdown_waits_for_accepted_background_request(self):
        r = await self.client.post(self.base + '/v1/chat/completions', json={'stream': True})
        await r.content.readuntil(b'\n\n')
        cleanup = asyncio.create_task(self.runner.cleanup())
        await asyncio.sleep(.05)
        self.assertFalse(cleanup.done())
        self.release.set()
        self.assertEqual(await r.read(), b'data: [DONE]\n\n')
        await cleanup

    async def test_concurrent_attempt_requests_preserve_bodies(self):
        async def one(i):
            async with self.client.post(self.base + '/v1/chat/completions', json={'index': i}) as r:
                return (await r.json())['index']
        self.assertEqual(await asyncio.gather(*(one(i) for i in range(8))), list(range(8)))
        self.assertEqual(len(self.seen), 8)

    async def test_chunked_input_rejected_before_upstream(self):
        async def body():
            yield b'{}'
        async with self.client.post(self.base + '/v1/chat/completions', data=body()) as r:
            self.assertEqual(r.status, 400)
        self.assertEqual(self.seen, [])

    async def test_missing_socket_is_no_retry_gateway_failure(self):
        self.relay.socket_path += '.absent'
        async with self.client.get(self.base + '/v1/models') as r:
            self.assertEqual(r.status, 502)
        self.assertEqual(self.seen, [])


if __name__ == '__main__': unittest.main()
