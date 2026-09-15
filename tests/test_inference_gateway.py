import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import tempfile
import unittest

try:
    import aiohttp
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
    async def test_connection_policy_uses_distinct_or_reused_actual_sockets(self):
        for policy, expected in [('fresh', 3), ('keepalive', 1)]:
            connections = set()
            async def upstream(request):
                await request.read(); connections.add(request.transport)
                return web.json_response({'ok': True})
            app = web.Application(); app.router.add_post('/v1/responses', upstream)
            async with serve(app) as origin, serve(create_app(origin, connection_policy=policy)) as url:
                async with ClientSession() as client:
                    for _ in range(3):
                        async with client.post(url + '/v1/responses', data=b'{}') as response:
                            self.assertEqual(response.status, 200)
                            await response.read()
            self.assertEqual(len(connections), expected)

    async def test_refused_connection_has_correlated_metadata_without_private_payload(self):
        with socket.socket() as bound, tempfile.TemporaryDirectory() as temp:
            bound.bind(('127.0.0.1', 0))  # Reserved port with no listener.
            events = Path(temp) / 'events.jsonl'
            proxy = create_app('http://127.0.0.1:' + str(bound.getsockname()[1]), event_path=events)
            async with serve(proxy) as url, ClientSession() as client:
                async with client.post(url + '/v1/responses?private=PRIVATE_QUERY', data=b'PRIVATE_BODY',
                        headers={'Authorization': 'Bearer PRIVATE_CREDENTIAL', 'X-Request-ID': 'PRIVATE_ID'}) as r:
                    self.assertEqual(r.status, 502)
                    request_id = r.headers['X-Request-ID']
                    self.assertEqual((await r.json())['error']['request_id'], request_id)
                self.assertEqual(proxy[GATEWAY].counts['active'], 0)
            rows = [json.loads(line) for line in events.read_text().splitlines()]
            failure = next(r for r in rows if r['event'] == 'transport_error')
            self.assertEqual(failure['request_id'], request_id)
            self.assertEqual(failure['route'], 'responses')
            self.assertEqual(failure['error_type'], 'ClientConnectorError')
            self.assertFalse(failure['connection_created'])
            self.assertFalse(failure['headers_sent'])
            self.assertEqual(failure['sent_body_bytes'], 0)
            self.assertNotIn('PRIVATE', events.read_text())

    async def test_peer_closes_reused_socket_and_fresh_connections_avoid_that_fixture_failure(self):
        requests = []
        async def peer(reader, writer):
            try:
                for index in range(2):
                    head = await reader.readuntil(b'\r\n\r\n')
                    length = next(int(line.split(b':', 1)[1]) for line in head.split(b'\r\n')
                                  if line.lower().startswith(b'content-length:'))
                    requests.append(await reader.readexactly(length))
                    if index == 1:
                        return  # Controlled connection-reuse fault, with no response.
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}')
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close(); await writer.wait_closed()
        server = await asyncio.start_server(peer, '127.0.0.1', 0)
        origin = 'http://127.0.0.1:' + str(server.sockets[0].getsockname()[1])
        async with server:
            for policy, expected in [('keepalive', [200, 502]), ('fresh', [200, 200])]:
                with tempfile.TemporaryDirectory() as temp:
                    events = Path(temp) / 'events.jsonl'
                    proxy = create_app(origin, connection_policy=policy, event_path=events)
                    before = len(requests)
                    async with serve(proxy) as url, ClientSession() as client:
                        statuses = []
                        for _ in range(2):
                            async with client.post(url + '/v1/responses', data=b'{}') as r:
                                statuses.append(r.status); await r.read()
                    self.assertEqual(statuses, expected)
                    self.assertEqual(len(requests) - before, 2, 'Generation was retried')
                    failures = [json.loads(line) for line in events.read_text().splitlines()
                                if json.loads(line)['event'] == 'transport_error']
                    if policy == 'keepalive':
                        self.assertEqual(len(failures), 1)
                        self.assertTrue(failures[0]['connection_reused'])
                        self.assertTrue(failures[0]['headers_sent'])
                        self.assertEqual(failures[0]['sent_body_bytes'], 2)
                    else:
                        self.assertEqual(failures, [])

    async def test_truncated_response_remains_error_after_headers_and_releases_slot(self):
        async def peer(reader, writer):
            await reader.readuntil(b'\r\n\r\n')
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort')
            await writer.drain(); writer.close(); await writer.wait_closed()
        server = await asyncio.start_server(peer, '127.0.0.1', 0)
        async with server:
            origin = 'http://127.0.0.1:' + str(server.sockets[0].getsockname()[1])
            with tempfile.TemporaryDirectory() as temp:
                events = Path(temp) / 'events.jsonl'
                proxy = create_app(origin, event_path=events)
                async with serve(proxy) as url, ClientSession() as client:
                    with self.assertRaises(aiohttp.ClientPayloadError):
                        async with client.post(url + '/v1/responses', data=b'{}') as r:
                            await r.read()
                    self.assertEqual(proxy[GATEWAY].counts['active'], 0)
                failure = next(json.loads(line) for line in events.read_text().splitlines()
                               if json.loads(line)['event'] == 'transport_error')
                self.assertEqual(failure['upstream_http_status'], 200)
                self.assertEqual(failure['stage'], 'streaming_response')

    async def test_event_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            events = Path(temp) / 'events.jsonl'; events.write_text('original evidence')
            with self.assertRaises(FileExistsError):
                async with serve(create_app(event_path=events)):
                    self.fail('Existing event file accepted')
            self.assertEqual(events.read_text(), 'original evidence')

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
