"""Real-clock, loopback-only native timeout fixtures; no model inference.

Each case constructs the pinned native agent with an isolated profile and SDK,
then calls its unmodified interruptible request helper through our final-body
transport. HTTP responses and usage are synthetic and cannot be learning data.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts.source_world_calibration import read, save, sha
from .hermes_worker import native_timeouts, native_watchdog_environment

CASES = {
    'legacy_first_byte': {'delay_seconds': 130, 'budget_seconds': 180, 'override': False},
    'final_body_success': {'delay_seconds': 130, 'budget_seconds': 180, 'override': True},
    'bounded_request': {'delay_seconds': 6, 'budget_seconds': 2, 'override': True},
}


def child_case(name, root, hermes_root):
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import yaml

    case = CASES[name]
    # Never contact inference or public services, even from native import hooks.
    connect = socket.socket.connect
    def loopback_only(sock, address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            raise RuntimeError('Timeout fixture forbids non-loopback connections')
        return connect(sock, address)
    socket.socket.connect = loopback_only
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append({'path': self.path, 'payload': payload})
            save(root / 'WIRE.json', requests)
            if self.path != '/v1/responses':
                # Native construction probes local endpoints for model metadata.
                # Record these reads and reject unsupported routes immediately;
                # only the Responses request is the delayed fixture treatment.
                self.send_error(404)
                return
            time.sleep(case['delay_seconds'])
            response = {'id': 'fixture-response', 'object': 'response', 'created_at': 1,
                'status': 'completed', 'error': None, 'incomplete_details': None,
                'model': 'worldlab-timeout-fixture', 'output': [
                    {'id': 'fixture-message', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                     'content': [{'type': 'output_text', 'text': 'Synthetic timeout fixture.', 'annotations': []}]}],
                'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
                          'input_tokens_details': {'cached_tokens': 0},
                          'output_tokens_details': {'reasoning_tokens': 0}}}
            body = json.dumps(response).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f'http://127.0.0.1:{server.server_port}/v1'
    profile = Path(os.environ['HERMES_HOME']); profile.mkdir()
    settings = native_timeouts({'seconds': case['budget_seconds']})
    (profile / 'config.yaml').write_text(yaml.safe_dump({
        'model': {'default': 'worldlab-timeout-fixture', 'provider': 'custom',
                  'base_url': base_url, 'api_mode': 'codex_responses'},
        'providers': {'custom': settings},
        'memory': {'memory_enabled': False, 'user_profile_enabled': False},
        'checkpoints': {'enabled': False}}))
    if case['override']: os.environ.update(native_watchdog_environment())
    from run_agent import AIAgent
    from lifespan.evaluation.budget import install_native_budget
    from lifespan.evaluation.hermes_transport import install, verify_source
    from lifespan.evaluation.provider import provider_contract
    verify_source(hermes_root)
    provider = provider_contract('worldlab-timeout-fixture', base_url)
    agent = AIAgent(model=provider['model'], provider='custom', api_key='EMPTY', base_url=base_url,
        api_mode='codex_responses', enabled_toolsets=[], max_iterations=1, max_tokens=64,
        reasoning_config={'enabled': False}, quiet_mode=True, session_id=name,
        skip_memory=True, skip_context_files=True, skip_background_review=True,
        checkpoints_enabled=False)
    stale, implicit = agent._resolved_api_call_stale_timeout_base()
    assert not implicit and settings == {'request_timeout_seconds': agent._resolved_api_call_timeout(),
                                        'stale_timeout_seconds': stale}
    meter = install_native_budget(agent, max_model_calls=1, max_output_tokens=64,
                                  max_total_tokens=100000, provider_contract=provider)
    transport = install(agent, 'nonstreaming', hermes_root=hermes_root, provider_contract=provider)
    payload = agent._get_transport().build_kwargs(provider['model'],
        [{'role': 'user', 'content': 'Return the synthetic fixture response.'}], tools=[],
        instructions='Transport fixture only.', reasoning_config={'enabled': False},
        max_tokens=64, base_url=base_url, session_id=name)
    start = time.monotonic(); error = None; response = None
    try:
        response = agent._interruptible_api_call(payload)
    except Exception as exc:
        error = type(exc).__name__
    elapsed = time.monotonic() - start
    evidence = {'case': case, 'seconds': elapsed, 'error_type': error,
                'native_timeouts': settings, 'transport': transport,
                'watchdog_environment': {k: os.environ.get(k) for k in native_watchdog_environment()},
                'native_last_event_ts': getattr(agent, '_codex_stream_last_event_ts', None),
                'response_status': getattr(response, 'status', None), 'usage': meter.report(),
                'scope': __doc__}
    save(root / 'RESULT.json', evidence)
    inference_requests = [r for r in requests if r['path'] == '/v1/responses']
    assert len(inference_requests) == 1 and inference_requests[0]['payload']['stream'] is False
    assert all(r['path'] in ('/v1/responses', '/api/show') for r in requests)
    assert evidence['native_last_event_ts'] is None
    if name == 'final_body_success':
        assert response is not None and response.status == 'completed' and error is None
        assert 129 <= elapsed < 175 and meter.report()['accounting_complete']
    elif name == 'legacy_first_byte':
        assert response is None and error is not None and 115 <= elapsed < 129
    else:
        assert response is None and error is not None and 1.5 <= elapsed < 6
    assert meter.report()['physical_model_calls'] == 1
    save(root / 'PASS.json', {'ok': True, 'result_sha256': sha(root / 'RESULT.json'),
                              'wire_sha256': sha(root / 'WIRE.json')})
    server.shutdown()


def qualify(out, hermes_root):
    from .campaign import source_identity
    from lifespan.evaluation.hermes_transport import verify_source, PIN
    verify_source(hermes_root)
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'PLAN.json', {'cases': CASES, 'native_revision': PIN, 'source': source_identity(),
        'scope': __doc__, 'real_model_calls': 0, 'wall_clock_limit_seconds_per_case': 230})
    processes = []
    for name in CASES:
        root = out / name; root.mkdir(); (root / 'home').mkdir()
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'USER', 'LOGNAME') if k in os.environ}
        env.update(HOME=str(root / 'home'), HERMES_HOME=str(root / 'hermes'),
                   HERMES_AGENT_ROOT=str(hermes_root), PYTHONUNBUFFERED='1',
                   PYTHONPATH=f'{Path(__file__).resolve().parents[1]}:{hermes_root}')
        log = (root / 'worker.log').open('w')
        process = subprocess.Popen([str(hermes_root / 'venv/bin/python'), '-m', __spec__.name,
            '--out', str(out), '--hermes-root', str(hermes_root), '--case', name],
            cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
        log.close()
        processes.append((name, process, time.monotonic()))
    results = []
    for name, process, started in processes:
        try:
            process.wait(timeout=max(1, 230 - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGKILL); process.wait()
        root = out / name
        results.append({'id': name, 'returncode': process.returncode,
                        'ok': process.returncode == 0 and (root / 'PASS.json').is_file()})
    report = {'ok': all(r['ok'] for r in results), 'results': results,
              'plan_sha256': sha(out / 'PLAN.json'), 'real_model_calls': 0, 'scope': __doc__}
    save(out / 'QUALIFICATION.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--hermes-root', required=True, type=Path)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    if args.case:
        child_case(args.case, args.out.resolve() / args.case, args.hermes_root.resolve())
    else:
        report = qualify(args.out.resolve(), args.hermes_root.resolve())
        print(json.dumps(report, indent=2))
        sys.exit(0 if report['ok'] else 1)
