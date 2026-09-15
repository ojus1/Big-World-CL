import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest

try:
    from aiohttp import ClientSession, ClientPayloadError, web
    from worldlab.chat_budget_gateway import create_app, METER, audit_meter, usage_from_response, wire_request
except ImportError:
    raise unittest.SkipTest('Install requirements-inference-gateway.txt')
from worldlab.contracts import Budget
from test_inference_gateway import serve

MODEL = 'fixture-model'


def reply(prompt=13, completion=2):
    return {'model': MODEL, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'é'},
            'finish_reason': 'stop'}], 'usage': {'prompt_tokens': prompt, 'completion_tokens': completion,
                                               'total_tokens': prompt + completion}}


class Tests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def setup_meter(self, responder=None, *, budget=None, tokenizer=None):
        seen = []
        async def complete(request):
            value = await request.json(); seen.append(value)
            if responder:
                return await responder(request, value)
            return web.json_response(reply())
        async def tokenize(request):
            if tokenizer: return await tokenizer(request)
            return web.json_response({'count': 13})
        app = web.Application(); app.router.add_post('/v1/chat/completions', complete)
        app.router.add_post('/tokenize', tokenize)
        with tempfile.TemporaryDirectory() as tmp:
            async with serve(app) as origin:
                budget = budget or Budget(model_calls=4, output_tokens=20, total_tokens=1000, seconds=30)
                root = Path(tmp) / 'meter'
                proxy = create_app(origin, origin, MODEL, budget, root)
                async with serve(proxy) as url, ClientSession() as client:
                    yield client, url, proxy[METER], seen, root, budget, origin

    async def call(self, client, url, **extra):
        return await client.post(url + '/v1/chat/completions', json={
            'model': MODEL, 'messages': [{'role': 'user', 'content': 'short response'}], **extra})

    def audit(self, root, budget, origin):
        return audit_meter(root, budget=budget, model=MODEL, upstream=origin, tokenizer=origin)

    async def test_actual_wire_cap_tokenizer_reservation_and_offline_audit(self):
        async with self.setup_meter() as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url, max_tokens=900, max_completion_tokens=800,
                                       reasoning_effort='high', response_format={'type': 'json_object'})
            self.assertEqual(response.status, 200); await response.read()
            self.assertEqual(seen[0]['max_tokens'], 20)
            self.assertNotIn('max_completion_tokens', seen[0])
            self.assertNotIn('reasoning_effort', seen[0])
            self.assertEqual(seen[0]['chat_template_kwargs'], {'enable_thinking': False})
            self.assertEqual(seen[0]['response_format'], {'type': 'json_object'})
            self.assertEqual(meter.rows[0]['reserved_tokens'], 33)
            self.assertEqual(meter.snapshot()['charged_tokens'], 15)
            self.assertTrue(self.audit(root, budget, origin)['ok'])
            request = root / 'call-0000/WIRE_REQUEST.json'
            request.write_bytes(request.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'request or reservation'): self.audit(root, budget, origin)

    async def test_two_concurrent_calls_cannot_exceed_one_call_budget(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def respond(request, value):
            entered.set(); await release.wait(); return web.json_response(reply())
        budget = Budget(model_calls=1, output_tokens=20, total_tokens=1000, seconds=30)
        async with self.setup_meter(respond, budget=budget) as (client, url, meter, seen, root, budget, origin):
            one = asyncio.create_task(self.call(client, url))
            await asyncio.wait_for(entered.wait(), 3)
            two = asyncio.create_task(self.call(client, url))
            await asyncio.sleep(.01); self.assertEqual(len(seen), 1)
            release.set()
            a, b = await asyncio.gather(one, two)
            self.assertEqual([a.status, b.status], [200, 402]); await a.read(); await b.read()
            self.assertEqual(len(seen), 1)
            self.assertTrue(meter.exhausted)
            self.assertEqual(self.audit(root, budget, origin)['physical_model_calls'], 1)

    async def test_token_budget_shrinks_wire_cap_then_blocks_before_generation(self):
        budget = Budget(model_calls=5, output_tokens=20, total_tokens=30, seconds=30)
        async with self.setup_meter(budget=budget) as (client, url, meter, seen, root, budget, origin):
            for _ in range(3):
                response = await self.call(client, url); await response.read()
            self.assertEqual([v['max_tokens'] for v in seen], [17, 2])
            self.assertEqual(response.status, 402)
            self.assertEqual(meter.snapshot()['charged_tokens'], 30)
            self.assertEqual(self.audit(root, budget, origin)['physical_model_calls'], 2)

    async def test_stream_bytes_and_usage_survive_arbitrary_chunk_boundaries(self):
        payload = ('data: ' + json.dumps(reply(), ensure_ascii=False) + '\r\n\r\ndata: [DONE]\r\n\r\n').encode()
        async def respond(request, value):
            self.assertEqual(value['stream_options'], {'include_usage': True})
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            for byte in payload: await response.write(bytes([byte]))
            await response.write_eof(); return response
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url, stream=True)
            self.assertEqual(await response.read(), payload)
            self.assertTrue(meter.rows[0]['upstream_eof'])
            self.assertTrue(self.audit(root, budget, origin)['accounting_complete'])

    async def test_missing_usage_preserves_reservation_and_latches_failure(self):
        async def respond(request, value):
            data = reply(); data.pop('usage'); return web.json_response(data)
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url)
            with self.assertRaises(ClientPayloadError): await response.read()
            self.assertEqual((await self.call(client, url)).status, 402)
            self.assertEqual(len(seen), 1)
            self.assertFalse(meter.snapshot()['accounting_complete'])
            self.assertEqual(meter.snapshot()['charged_tokens'], 33)
            self.assertFalse(self.audit(root, budget, origin)['accounting_complete'])

    async def test_provider_overrun_retains_actual_cost_and_stops(self):
        async def respond(request, value): return web.json_response(reply(completion=21))
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url)
            with self.assertRaises(ClientPayloadError): await response.read()
            self.assertTrue(meter.stopped)
            self.assertEqual(meter.snapshot()['charged_tokens'], 34)
            self.assertEqual(self.audit(root, budget, origin)['charged_tokens'], 34)

    async def test_http_failure_is_not_retried_or_reported_as_zero_cost(self):
        async def respond(request, value): return web.json_response({'error': 'fixture'}, status=503)
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url)
            self.assertEqual(response.status, 503)
            with self.assertRaises(ClientPayloadError): await response.read()
            self.assertEqual((await self.call(client, url)).status, 402)
            self.assertEqual(meter.snapshot()['physical_model_calls'], 1)
            self.assertEqual(meter.snapshot()['charged_tokens'], 33)
            self.assertTrue(self.audit(root, budget, origin)['ok'])

    async def test_interrupted_upstream_stream_retains_unknown_cost(self):
        async def respond(request, value):
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            await response.write(b'data: {"choices":[]}\n\n')
            request.transport.close()
            return response
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url, stream=True)
            with self.assertRaises(ClientPayloadError): await response.read()
            self.assertEqual((await self.call(client, url)).status, 402)
            self.assertFalse(meter.snapshot()['accounting_complete'])
            self.assertEqual(self.audit(root, budget, origin)['charged_tokens'], 33)

    async def test_client_cancellation_stops_attempt_and_prevents_later_dispatch(self):
        release = asyncio.Event()
        async def respond(request, value):
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            await response.write(b'data: {"choices":[]}\n\n')
            await release.wait()
            return response
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url, stream=True)
            await response.content.readuntil(b'\n\n')
            response.close()
            for _ in range(100):
                if meter.stopped: break
                await asyncio.sleep(.005)
            release.set()
            self.assertTrue(meter.stopped)
            self.assertEqual((await self.call(client, url)).status, 402)
            self.assertEqual(len(seen), 1)
            self.assertFalse(self.audit(root, budget, origin)['accounting_complete'])

    async def test_local_model_listing_is_free_and_headers_are_not_forwarded_or_saved(self):
        async def respond(request, value):
            self.assertNotIn('Authorization', request.headers)
            return web.json_response(reply())
        async with self.setup_meter(respond) as (client, url, meter, seen, root, budget, origin):
            response = await client.get(url + '/v1/models')
            self.assertEqual((await response.json())['data'][0]['id'], MODEL)
            self.assertEqual(meter.snapshot()['physical_model_calls'], 0)
            response = await client.post(url + '/v1/chat/completions',
                headers={'Authorization': 'Bearer fixture-header-secret'}, json={
                    'model': MODEL, 'messages': [{'role': 'user', 'content': 'hello'}]})
            await response.read()
            self.assertTrue(all(b'fixture-header-secret' not in p.read_bytes() for p in root.rglob('*') if p.is_file()))
            self.assertTrue(self.audit(root, budget, origin)['ok'])

    async def test_tokenizer_failure_prevents_model_dispatch(self):
        async def tokenize(request): return web.json_response({'count': True})
        async with self.setup_meter(tokenizer=tokenize) as (client, url, meter, seen, root, budget, origin):
            response = await self.call(client, url); await response.read()
            self.assertEqual(response.status, 502); self.assertFalse(seen)
            self.assertTrue(meter.stopped)
            self.assertEqual(self.audit(root, budget, origin)['physical_model_calls'], 0)

    async def test_unqualified_inputs_and_routes_never_reach_generation(self):
        async with self.setup_meter() as (client, url, meter, seen, root, budget, origin):
            for value in [{'model': 'other'}, {'n': True}, {'n': 2}, {'max_tokens': 0},
                          {'truncate_prompt_tokens': 1}, {'tool_choice': 'required'},
                          {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': 'private'}]}]}]:
                response = await self.call(client, url, **value); await response.read()
                self.assertEqual(response.status, 400)
            response = await client.post(url + '/v1/responses', json={}); await response.read()
            self.assertEqual(response.status, 404); self.assertFalse(seen)
            self.assertEqual(self.audit(root, budget, origin)['physical_model_calls'], 0)

    async def test_expired_attempt_blocks_without_tokenizer_or_generation(self):
        async with self.setup_meter() as (client, url, meter, seen, root, budget, origin):
            meter.started -= budget.seconds + 1
            response = await self.call(client, url); await response.read()
            self.assertEqual(response.status, 402); self.assertFalse(seen); self.assertFalse(meter.preflights)
            self.assertTrue(meter.exhausted)
            self.assertTrue(self.audit(root, budget, origin)['ok'])

    def test_incomplete_stream_and_conflicting_usage_are_rejected(self):
        data = ('data: ' + json.dumps(reply()) + '\n\n').encode()
        with self.assertRaisesRegex(ValueError, 'DONE'): usage_from_response(data, True)
        conflict = ('data: ' + json.dumps(reply(completion=3)) + '\n\ndata: [DONE]\n\n').encode()
        with self.assertRaisesRegex(ValueError, 'contradictory'): usage_from_response(data + conflict, True)
        bad = reply(); bad['usage']['total_tokens'] += 1
        with self.assertRaisesRegex(ValueError, 'Invalid provider usage'): usage_from_response(json.dumps(bad).encode(), False)


if __name__ == '__main__': unittest.main()
