#!/usr/bin/env python3
"""Measure native completion throughput and streamed OpenAI chat concurrency."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import threading
import time
from urllib.request import Request, urlopen

p = argparse.ArgumentParser()
p.add_argument('--concurrency', default='1,8,16,32,64')
p.add_argument('--tokens', type=int, default=256)
p.add_argument('--output', default='results/benchmark.json')
p.add_argument('--chat', action='store_true')
p.add_argument('--prompt-file', type=Path, help='Use a complete realistic prompt instead of synthetic repeated text.')
a = p.parse_args()


def run(i):
    text = f'Request {i}: ' + ('A simulated community has students, teachers, journalists and administrators discussing a proposed policy. ' * 32)
    if a.prompt_file:
        text = a.prompt_file.read_text() + f'\nRequest identifier: {i}.'
    payload = {'prompt': text, 'n_predict': a.tokens, 'temperature': 0, 'ignore_eos': True, 'cache_prompt': False, 'stream': True}
    endpoint = '/completion'
    if a.chat:
        endpoint = '/v1/chat/completions'
        payload = {'model': 'minicpm5-2b', 'messages': [{'role': 'user', 'content': text + ('' if a.prompt_file else '\nWrite a detailed fictional discussion.')}],
                   'max_tokens': a.tokens, 'temperature': 0.7, 'stream': True, 'stream_options': {'include_usage': True}, 'cache_prompt': False}
    start = time.perf_counter()
    first, count, output, prompt_tokens = None, 0, '', 0
    last_events = []
    try:
        req = Request('http://127.0.0.1:8080' + endpoint, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=300) as response:
            for line in response:
                if not line.startswith(b'data: ') or line.strip() == b'data: [DONE]':
                    continue
                event = json.loads(line[6:])
                last_events = (last_events + [event])[-3:]
                if 'error' in event:
                    raise RuntimeError(event['error'])
                if a.chat:
                    delta = ((event.get('choices') or [{}])[0].get('delta') or {}).get('content') or ''
                    if event.get('usage'):
                        count = event['usage']['completion_tokens']
                        prompt_tokens = event['usage']['prompt_tokens']
                else:
                    delta = event.get('content', '')
                    if event.get('stop'):
                        count = event['tokens_predicted']
                        prompt_tokens = event['tokens_evaluated']
                output += delta
                if delta and first is None:
                    first = time.perf_counter() - start
        if not output or not count:
            raise RuntimeError('Empty output or missing token usage')
        return dict(id=i, tokens=count, prompt_tokens=prompt_tokens, ttft_s=first, latency_s=time.perf_counter() - start,
                    output=output if a.prompt_file else None, error=None)
    except Exception as e:
        return dict(id=i, error=str(e), latency_s=time.perf_counter() - start,
                    tokens=count, prompt_tokens=prompt_tokens, output=output, last_events=last_events)


results = []
versions = json.loads((Path(__file__).resolve().parents[1] / 'results/versions.json').read_text())
for concurrency in map(int, a.concurrency.split(',')):
    stopped = threading.Event()
    observed = {'peak_busy_slots': 0, 'peak_gpu_busy_percent': 0, 'peak_gpu_vram_bytes': 0}
    def observe():
        while not stopped.is_set():
            try:
                with urlopen('http://127.0.0.1:8080/slots', timeout=5) as response:
                    slots = json.load(response)
                observed['peak_busy_slots'] = max(observed['peak_busy_slots'], sum(s['is_processing'] for s in slots))
                for path in Path('/sys/class/drm').glob('card[0-9]*/device/gpu_busy_percent'):
                    observed['peak_gpu_busy_percent'] = max(observed['peak_gpu_busy_percent'], int(path.read_text()))
                    memory = path.parent / 'mem_info_vram_used'
                    observed['peak_gpu_vram_bytes'] = max(observed['peak_gpu_vram_bytes'], int(memory.read_text()))
            except Exception:
                pass
            stopped.wait(0.5)
    observer = threading.Thread(target=observe, daemon=True)
    observer.start()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(run, range(concurrency * 2)))
    wall = time.perf_counter() - start
    stopped.set()
    observer.join(timeout=6)
    good = [r for r in rows if not r['error']]
    latency = sorted(r['latency_s'] for r in good)
    result = dict(concurrency=concurrency, requests=len(rows), errors=len(rows)-len(good), wall_s=wall,
                  output_tokens=sum(r['tokens'] for r in good),
                  output_tokens_per_second=sum(r['tokens'] for r in good)/wall,
                  median_ttft_s=statistics.median(r['ttft_s'] for r in good) if good else None,
                  p95_latency_s=latency[min(len(latency)-1, int(len(latency)*.95))] if good else None,
                  mode='chat' if a.chat else 'native-fixed-output', observations=observed, rows=rows, versions=versions,
                  prompt_file=str(a.prompt_file) if a.prompt_file else None)
    results.append(result)
    Path(a.output).write_text(json.dumps(results, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}), flush=True)
if any(r['errors'] for r in results):
    raise SystemExit(1)
