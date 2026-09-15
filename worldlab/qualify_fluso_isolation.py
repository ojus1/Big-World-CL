"""Native Fluso control through a network-none relay and private meter.

This is a prospective integration qualification, not a task-bank evaluation or
the finished WorldLab Harness adapter. All auxiliary model requests are metered.
"""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from aiohttp import web

from .chat_budget_gateway import METER, audit_meter, create_app, encoded, sha
from .contracts import Budget

IMAGE = 'sha256:3eea3855506e6c5694143609a73f7f4a0469d60d136e250c0ecf3c91ac75749d'
DATA = '/run/fluso-data'
WORKSPACE = DATA + '/tenants/dev/users/dev-user/workspace'
ENDPOINT = 'http://127.0.0.1:8080/v1'
SKILL = ('---\nname: work-process\ndescription: Employee work process. Read before every task.\n'
         'compatibility: fluso-native\n---\n\n'
         'Read the provided input files and verify the arithmetic. When writing a JSON result, '
         'include a process_marker field with the exact value WORK_PROCESS_CONTROL_V1.\n')
PROMPT = ('Read the work-process skill before doing this task. In your current project, read numbers.csv '
          'and write files/result.json containing the total of its value column under the key sum. '
          'Keep the final reply short.')


def catalog(model, output_tokens):
    return {'providers': {'pcci': {'baseUrl': ENDPOINT, 'api': 'openai-completions', 'models': [{
        'id': model, 'name': model, 'reasoning': False, 'input': ['text'], 'contextWindow': 131072,
        'maxTokens': output_tokens, 'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
        'compat': {'supportsDeveloperRole': False, 'supportsStore': False, 'supportsStrictMode': False,
                   'supportsReasoningEffort': False, 'supportsUsageInStreaming': True,
                   'maxTokensField': 'max_tokens'}}]}}}


def environment(model, seconds):
    env = {'HOME': '/tmp/home', 'TMPDIR': '/tmp', 'NO_COLOR': '1',
           'FLUSO_DEV_HARNESS_DATA_DIR': DATA, 'FLUSO_MODELS_JSON_PATH': '/run/models.json',
           'FLUSO_PROVIDER': 'pcci', 'FLUSO_MODEL': model, 'FLUSO_THINKING_LEVEL': 'off',
           'FLUSO_PCCI_BASE_URL': ENDPOINT, 'FLUSO_MAX_CONCURRENT_PROMPTS': '1',
           'FLUSO_MAX_SESSIONS_PER_USER': '2', 'FLUSO_SESSION_IDLE_TIMEOUT_MS': str((seconds + 60) * 1000),
           'FLUSO_CHAT_AGENT_TIMEOUT_MS': str(seconds * 1000),
           'FLUSO_PROVIDER_REQUEST_TIMEOUT_MS': str(seconds * 1000),
           'OPENAI_API_KEY': 'dummy', 'OPENROUTER_API_KEY': 'dummy', 'PREM_API_KEY': 'dummy'}
    for key in ('STEP_STATUS', 'THREAD_TITLE', 'WORKING_MEMORY', 'OM', 'PT'):
        env['FLUSO_' + key + '_MODEL'] = model
    return env


async def command(argv, *, check=True, timeout=45):
    process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            process.kill(); await process.wait()
        raise
    if check and process.returncode:
        raise RuntimeError(f'Command failed ({process.returncode}): {argv[:3]}: {err.decode(errors="replace")}')
    return {'argv': argv, 'returncode': process.returncode, 'stdout': out.decode(), 'stderr': err.decode()}


def common(network, name):
    return ['--name', name, '--network', network, '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--user', f'{os.getuid()}:{os.getgid()}',
            '--pids-limit', '256', '--memory', '4g', '--cpus', '2',
            '--tmpfs', '/tmp:rw,nosuid,size=512m',
            *([] if network.startswith('container:') else ['--dns', '127.0.0.1'])]


async def qualify(out, model, upstream, tokenizer):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    identity = uuid.uuid4().hex
    relay_name, solver_name = ('wl-' + identity[:16] + suffix for suffix in ('-relay', '-solver'))
    budget = Budget(model_calls=32, output_tokens=4096, total_tokens=600000, seconds=600)
    env = environment(model, budget.seconds)
    plan = {'kind': 'fluso_isolated_native_control_v1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'image': IMAGE, 'model': model, 'upstream': upstream, 'tokenizer': tokenizer,
            'budget': asdict(budget), 'environment': env, 'catalog': catalog(model, budget.output_tokens),
            'prompt': PROMPT, 'skill': SKILL, 'expected_result': {'sum': 42, 'process_marker': 'WORK_PROCESS_CONTROL_V1'},
            'network': 'solver shares network-none relay namespace', 'relay': relay_name, 'solver': solver_name,
            'source_sha256': {name: sha(Path(__file__).with_name(name).read_bytes()) for name in
                ('qualify_fluso_isolation.py', 'chat_relay.py', 'chat_budget_gateway.py', 'contracts.py')},
            'scope': 'Synthetic native Fluso control, private socket relay, isolated network and meter receipts. '
                     'Not a benchmark outcome, full Harness adapter, independent grader or learning-effect claim.'}
    (out / 'PLAN.json').write_bytes(encoded(plan))
    (out / 'models.json').write_bytes(encoded(plan['catalog']))
    user_workspace = out / 'data' / WORKSPACE.removeprefix(DATA + '/')
    workspace = user_workspace / 'projects/Home'
    workspace.mkdir(parents=True)
    skill = user_workspace / 'skills/work-process/SKILL.md'
    skill.parent.mkdir(parents=True); skill.write_text(SKILL)
    (workspace / 'numbers.csv').write_text('value\n10\n13\n19\n')
    (out / 'private-sentinel').write_text('This controller file must not enter the solver mount.')
    app = create_app(upstream, tokenizer, model, budget, out / 'meter')
    runner = web.AppRunner(app, handler_cancellation=True, shutdown_timeout=budget.seconds)
    runner_cleaned = False
    created, process = [], None
    started = time.monotonic()
    report = None
    try:
        info = json.loads((await command(['docker', 'image', 'inspect', IMAGE]))['stdout'])[0]
        if info['Id'] != IMAGE:
            raise ValueError('Native image changed')
        # Avoid copying unrelated image environment into evidence; the immutable ID binds it.
        (out / 'IMAGE.json').write_bytes(encoded({'Id': info['Id'], 'RepoDigests': info.get('RepoDigests'),
                                                 'Created': info['Created']}))
        await runner.setup()
        with tempfile.TemporaryDirectory(prefix='worldlab-fluso-') as temporary:
            socket = str(Path(temporary) / 'meter.sock')
            await web.UnixSite(runner, socket).start()
            relay_cmd = ['docker', 'create', *common('none', relay_name),
                '--mount', f'type=bind,src={socket},dst=/run/meter.sock,readonly',
                '--mount', f'type=bind,src={Path(__file__).with_name("chat_relay.py")},dst=/run/relay.py,readonly',
                '--entrypoint', 'python3', IMAGE, '/run/relay.py', '--socket', '/run/meter.sock',
                '--timeout', str(budget.seconds)]
            (out / 'RELAY_COMMAND.json').write_bytes(encoded(relay_cmd))
            created.append((await command(relay_cmd))['stdout'].strip())
            await command(['docker', 'start', created[-1]])
            relay_info = json.loads((await command(['docker', 'inspect', created[-1]]))['stdout'])[0]
            (out / 'RELAY_INSPECT.json').write_bytes(encoded(relay_info))
            if relay_info['HostConfig']['NetworkMode'] != 'none':
                raise ValueError('Relay must have no external network')
            shared_network = 'container:' + created[-1]
            mounts = ['--mount', f'type=bind,src={out / "data"},dst={DATA}',
                '--mount', f'type=bind,src={out / "models.json"},dst=/run/models.json,readonly',
                '--mount', f'type=bind,src={skill.parent},dst={WORKSPACE}/skills/work-process,readonly']
            probe = f'''import json, pathlib, socket, urllib.request, urllib.error, time
base="http://127.0.0.1:8080"
for attempt in range(30):
 try:
  models=json.load(urllib.request.urlopen(base+"/v1/models",timeout=2)); break
 except OSError: time.sleep(.1)
else: raise AssertionError("Relay never became ready")
assert models["data"][0]["id"]=={model!r}
for path in ("/status", "/tokenize", "/v1/models?upstream=other"):
 try: urllib.request.urlopen(base+path,timeout=2)
 except urllib.error.HTTPError as e: assert e.code==404
 else: raise AssertionError("Private relay route exposed")
blocked=[]
for host,port in [("127.0.0.1",8002),("127.0.0.1",8011),("1.1.1.1",443)]:
 try: c=socket.create_connection((host,port),timeout=1); c.close()
 except OSError: blocked.append([host,port])
 else: raise AssertionError("Direct inference or internet route exposed")
for path in ({str(out / 'private-sentinel')!r}, "/run/meter.sock", "/run/relay.py"):
 assert not pathlib.Path(path).exists(),path
try: socket.getaddrinfo("example.com",443)
except socket.gaierror: pass
else: raise AssertionError("External DNS resolution enabled")
print(json.dumps({{"ok":True,"model":models["data"][0]["id"],"blocked_tcp":blocked,"external_dns_blocked":True,"private_paths_absent":True}}))
'''
            probe += '\nassert sorted(p.name for p in pathlib.Path("/sys/class/net").iterdir()) == ["lo"]\n'
            (out / 'PROBE.py').write_text(probe)
            probe_cmd = ['docker', 'create', *common(shared_network, solver_name + '-probe'), *mounts,
                         '--entrypoint', 'python3', IMAGE, '-c', probe]
            created.append((await command(probe_cmd))['stdout'].strip())
            (out / 'PROBE_INSPECT.json').write_bytes(encoded(json.loads((await command(['docker', 'inspect', created[-1]]))['stdout'])[0]))
            probe_result = await command(['docker', 'start', '-a', created[-1]])
            (out / 'ISOLATION_PROBE.json').write_bytes(encoded(probe_result))
            solver_cmd = ['docker', 'create', *common(shared_network, solver_name), *mounts,
                '--workdir', '/opt/fluso/agents/dev-harness']
            for key, value in env.items():
                solver_cmd += ['--env', key + '=' + value]
            solver_cmd += ['--entrypoint', '/usr/local/bin/bun', IMAGE, 'harness.ts', 'send', '--thread', 'worldlab-control', PROMPT]
            (out / 'SOLVER_COMMAND.json').write_bytes(encoded(solver_cmd))
            created.append((await command(solver_cmd))['stdout'].strip())
            (out / 'SOLVER_INSPECT.json').write_bytes(encoded(json.loads((await command(['docker', 'inspect', created[-1]]))['stdout'])[0]))
            with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
                process = await asyncio.create_subprocess_exec('docker', 'start', '-a', created[-1], stdout=stdout, stderr=stderr)
                while process.returncode is None:
                    if app[METER].stopped or not app[METER].remaining_seconds():
                        (out / 'STOP_INTENT.json').write_bytes(encoded({'reason': app[METER].stop_reason or 'time_budget',
                            'container': created[-1], 'meter': app[METER].snapshot()}))
                        (out / 'STOP_BEFORE.json').write_bytes(encoded(await command(['docker', 'inspect', created[-1]])))
                        await command(['docker', 'stop', '--time', '2', created[-1]])
                        break
                    await asyncio.sleep(.25)
                await process.wait()
            terminal = json.loads((await command(['docker', 'inspect', created[-1]]))['stdout'])[0]
            (out / 'TERMINAL_INSPECT.json').write_bytes(encoded(terminal))
            # Native Fluso exits while background memory requests can still be
            # in flight. Stop admitting connections and drain accepted handlers
            # through their existing deadlines before inspecting final usage.
            # Keep the relay alive until this completes; killing it loses usage.
            await runner.cleanup()
            runner_cleaned = True
            meter = app[METER].snapshot()
            result_path = workspace / 'files/result.json'
            result = json.loads(result_path.read_text()) if result_path.is_file() else None
            traces = sorted((out / 'data').glob('tenants/dev/users/dev-user/sessions/*/.fluso-agent-core/session/*.jsonl'))
            audit = audit_meter(out / 'meter', budget=budget, model=model, upstream=upstream, tokenizer=tokenizer)
            native_log = (out / 'stdout.log').read_text()
            ok = (process.returncode == 0 and terminal['State']['ExitCode'] == 0 and
                  meter['accounting_complete'] and not meter['stopped'] and bool(traces) and
                  result == plan['expected_result'] and '[REQ]' in native_log and 'completed' in native_log
                  and 'FAILED:' not in native_log)
            report = {'ok': ok, 'plan_sha256': sha((out / 'PLAN.json').read_bytes()), 'seconds': time.monotonic() - started,
                      'meter_audit': audit, 'result': result, 'trace_files': [str(p.relative_to(out)) for p in traces],
                      'exit_code': process.returncode, 'scope': plan['scope'],
                      'native_skill_read_audit': 'pending inspection of native tool trajectory and request bytes'}
    except BaseException as exc:
        (out / 'FAILURE.json').write_bytes(encoded({'error_type': type(exc).__name__, 'error': str(exc),
                                                  'seconds': time.monotonic() - started, 'meter': app[METER].snapshot()}))
        raise
    finally:
        cleanup = []
        for container in reversed(created):
            cleanup.append(await command(['docker', 'rm', '-f', container], check=False))
        if process is not None and process.returncode is None:
            await process.wait()
        (out / 'CLEANUP.json').write_bytes(encoded(cleanup))
        if not runner_cleaned:
            await runner.cleanup()
    (out / 'REPORT.json').write_bytes(encoded(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    parser.add_argument('--upstream', default='http://127.0.0.1:8011')
    parser.add_argument('--tokenizer', default='http://127.0.0.1:8002')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(qualify(args.out, args.model, args.upstream, args.tokenizer)), indent=2))


if __name__ == '__main__': main()
