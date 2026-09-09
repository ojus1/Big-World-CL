#!/usr/bin/env python3
"""Manage MiroFish services; local GPU inference is disabled by default."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'run'
RUN.mkdir(exist_ok=True)
(ROOT / 'logs').mkdir(exist_ok=True)
SERVICES = {
    'llama': ([str(ROOT / 'scripts/llama-server.sh')], ROOT, 'http://127.0.0.1:8080/health'),
    'backend': ([str(ROOT / 'MiroFish/backend/.venv/bin/python'), 'run.py'], ROOT / 'MiroFish/backend', 'http://127.0.0.1:5001/health'),
    'frontend': (['node', str(ROOT / 'MiroFish/frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '3000', '--strictPort'], ROOT / 'MiroFish/frontend', 'http://127.0.0.1:3000'),
}


def owned_pid(name):
    path = RUN / (name + '.json')
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    try:
        stat = Path(f'/proc/{data["pid"]}/stat').read_text().split()
        if stat[2] == 'Z':
            return None
        start = stat[21]
        if start == data['start_time']:
            return data['pid']
    except FileNotFoundError:
        pass
    return None


def healthy(url):
    try:
        with urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


action = sys.argv[1] if len(sys.argv) > 1 else 'status'
if action not in {'start', 'status', 'stop'}:
    raise SystemExit('Usage: stack.py start|status|stop [llama|backend|frontend]')
names = sys.argv[2:] or (['backend', 'frontend'] if action == 'start' else list(SERVICES))
if action == 'start' and 'llama' in names:
    raise SystemExit('GPU inference is disabled: MiroFish uses OpenAI Luna. The historical llama-server.sh remains available for deliberate manual use.')
if action == 'stop':
    names = list(reversed(names))
for name in names:
    cmd, cwd, url = SERVICES[name]
    pid = owned_pid(name)
    if action == 'start' and not pid:
        if healthy(url):
            raise SystemExit(f'{url} already occupied by a service not started here')
        env = os.environ.copy()
        env.update(PYTHONUNBUFFERED='1', TOKENIZERS_PARALLELISM='false', HF_HUB_DISABLE_TELEMETRY='1',
                   HF_HUB_CACHE=str(ROOT / 'models/embedding-cache'),
                   TIKTOKEN_CACHE_DIR=str(ROOT / 'models/tiktoken'),
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        with (ROOT / 'logs' / (name + '.log')).open('ab', buffering=0) as log:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        pid = proc.pid
        start = Path(f'/proc/{pid}/stat').read_text().split()[21]
        (RUN / (name + '.json')).write_text(json.dumps({'pid': pid, 'start_time': start}))
        for _ in range(120):
            if healthy(url):
                break
            if proc.poll() is not None:
                raise SystemExit(f'{name} exited: inspect logs/{name}.log')
            time.sleep(1)
        else:
            raise SystemExit(f'{name} has not become healthy: inspect logs/{name}.log')
    elif action == 'stop' and pid:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(120):
            if not owned_pid(name):
                break
            time.sleep(1)
        else:
            raise SystemExit(f'{name} is still stopping; inspect its log before restarting')
    if action == 'start' and not healthy(url):
        raise SystemExit(f'{name} has a recorded live process but is unhealthy; inspect its log')
    print(f'{name}: pid={owned_pid(name)}, healthy={healthy(url)}, url={url}', flush=True)
