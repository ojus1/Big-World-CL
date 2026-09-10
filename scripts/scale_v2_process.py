"""Owned service/world lifecycle for the separate scale-v2 checkout.

This module never chooses a campaign, model, cohort, budget or retry. Native
entry points accept only this checkout's fixed server and runner commands.
Receipts contain process/configuration metadata, never environment values.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time
import threading
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
SERVICE_URL = 'http://127.0.0.1:5002'


def require(condition, code):
    if not condition: raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def private_path(path):
    path = Path(path).absolute()
    require(path.resolve().is_relative_to(ROOT / 'lifespan/artifacts')
            and all(not p.is_symlink() for p in [path, *path.parents] if p != ROOT.parent), 'private_path_escape')
    return path


def save(path, value, *, exclusive=False):
    path = private_path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x') as stream: stream.write(raw)
    else:
        temporary = path.with_suffix('.tmp'); temporary.write_text(raw); temporary.replace(path)


@contextmanager
def cleanup_scope():
    """Repeated SIGTERM cannot abort bounded cleanup midway through its stages."""
    if threading.current_thread() is not threading.main_thread():
        # The launcher owns process-wide signal flags; worker cleanup must not
        # replace them, nor call signal.signal outside the main thread.
        yield
        return
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous: signal.signal(sig, lambda *_: None)
    try: yield
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)


def identity(pid):
    try:
        directory = Path('/proc') / str(pid)
        fields = (directory / 'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': int(pid), 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
                'start_ticks': int(fields[19]), 'uid': directory.stat().st_uid, 'state': fields[0],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except FileNotFoundError: return None
    except (OSError, ValueError, IndexError): return {'pid': pid, 'unreadable': True}


def same_identity(a, b):
    return (isinstance(a, dict) and isinstance(b, dict) and not a.get('unreadable') and not b.get('unreadable')
            and all(k in a and k in b and a[k] == b[k] for k in ('pid', 'start_ticks', 'uid', 'boot_id')))


def process_observation(old):
    now = identity(old['pid'])
    state = ('absent' if now is None else 'unknown' if now.get('unreadable') else 'identity_replaced'
             if not same_identity(old, now) else 'zombie' if now['state'] == 'Z' else 'same_alive')
    return {'identity': old, 'state': state, 'observed_current': now}


def discover_owned(known):
    current = {int(p.name): identity(int(p.name)) for p in Path('/proc').iterdir() if p.name.isdigit()}
    parents = {pid for pid, old in known.items() if same_identity(old, current.get(pid))}
    changed = True
    while changed:
        changed = False
        for pid, item in current.items():
            if item and not item.get('unreadable') and item['uid'] == os.getuid() and item['ppid'] in parents:
                require(pid not in known or same_identity(known[pid], item), 'owned_pid_reused_during_observation')
                if pid not in known:
                    known[pid] = item; parents.add(pid); changed = True


def _environment(env):
    values = dict(env)
    values.pop('PYTHONHOME', None)
    values.update(PYTHONPATH=str(ROOT / 'MiroFish/backend') + ':' + str(ROOT), PYTHONUNBUFFERED='1',
                  FLASK_HOST='127.0.0.1', FLASK_PORT='5002', FLASK_DEBUG='false', GRAPH_BACKEND='local',
                  LOCAL_GRAPH_DB=str(ROOT / 'MiroFish/backend/uploads/local_graph.sqlite3'))
    return values


def validate_installation(worktree=ROOT, python=None, service_url=SERVICE_URL, env=None, *, require_pristine=True):
    require(Path(worktree).resolve() == ROOT and service_url == SERVICE_URL, 'separate_v2_service_required')
    backend = ROOT / 'MiroFish/backend'; interpreter = backend / '.venv/bin/python'
    require(backend.resolve() == backend and interpreter.is_file(), 'fresh_native_checkout_required')
    require(python is None or Path(python).absolute() == interpreter, 'unexpected_service_interpreter')
    script = ("import json,os,app.config as c; from pathlib import Path; "
              "print(json.dumps({'config_module':str(Path(c.__file__).resolve()),"
              "'uploads':str(Path(c.Config.UPLOAD_FOLDER).resolve()),"
              "'graph_database':str(Path(c.Config.LOCAL_GRAPH_DB).resolve()),"
              "'graph_backend':c.Config.GRAPH_BACKEND,'debug':c.Config.DEBUG,"
              "'host':os.environ.get('FLASK_HOST'),'port':os.environ.get('FLASK_PORT')}))")
    try:
        data = json.loads(subprocess.check_output([str(interpreter), '-c', script], cwd=backend,
            env=_environment(os.environ if env is None else env), stderr=subprocess.DEVNULL, timeout=20))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ValueError('native_config_import_verification_failed') from None
    expected = {'config_module': str(backend / 'app/config.py'), 'uploads': str(backend / 'uploads'),
        'graph_database': str(backend / 'uploads/local_graph.sqlite3'), 'graph_backend': 'local',
        'debug': False, 'host': '127.0.0.1', 'port': '5002'}
    require(data == expected, 'native_mutable_state_or_module_isolation')
    uploads = backend / 'uploads'
    require(uploads.resolve() == uploads, 'native_uploads_symlink')
    if require_pristine: require(not uploads.exists() or not any(uploads.iterdir()), 'native_uploads_not_pristine')
    return {'schema_version': 1, 'worktree': str(ROOT), 'backend': str(backend), 'python': str(interpreter),
            'python_sha256': sha(interpreter), 'server_url': SERVICE_URL, 'configuration': data,
            'source_sha256': {name: sha(ROOT / name) for name in
                ('MiroFish/backend/run.py', 'MiroFish/backend/app/config.py', 'scripts/scale_v2_process.py')}}


@dataclass
class Handle:
    process: subprocess.Popen
    receipt_dir: Path
    kind: str
    cwd: Path
    started_monotonic: float
    root_identity: dict
    binding: dict
    known: dict = field(default_factory=dict)
    instances: dict = field(default_factory=dict)
    simulation: dict | None = None
    ended_monotonic: float | None = None
    ready_monotonic: float | None = None
    simulation_pending: dict | None = None
    lock: object = field(default_factory=threading.RLock, repr=False, compare=False)

    def poll(self): return self.process.poll()


def _spawn(command, cwd, env, receipt_dir, kind, binding):
    directory = private_path(receipt_dir); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    intent = directory / (kind + '_INTENT.json')
    started = time.monotonic()
    save(intent, {'schema_version': 1, 'kind': kind, 'started_monotonic': started, 'binding': binding,
                  'command': command, 'cwd': str(cwd), 'helper_sha256': sha(__file__)}, exclusive=True)
    with (directory / (kind.lower() + '.log')).open('a') as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    root = identity(process.pid) or {'pid': process.pid, 'unreadable': True}
    handle = Handle(process, directory, kind, cwd, started, root, binding,
                    {} if root.get('unreadable') else {root['pid']: root})
    try:
        save(directory / (kind + '_START.json'), {'schema_version': 1, 'kind': kind,
            'intent_sha256': sha(intent), 'helper_sha256': sha(__file__), 'started_monotonic': started,
            'root_identity': root, 'command': command, 'cwd': str(cwd), 'binding': binding}, exclusive=True)
    except BaseException:
        # Do not lose the newly spawned handle if its durable start write fails.
        # This does not invent a completed launch receipt or native cost proof.
        with cleanup_scope():
            _stop_known(handle, time.monotonic() + 5)
        raise
    return handle


def socket_owned(handle):
    require(same_identity(handle.root_identity, identity(handle.process.pid)), 'service_identity_changed')
    proc = Path('/proc') / str(handle.process.pid)
    require(proc.joinpath('cwd').resolve() == handle.cwd, 'service_cwd_changed')
    inodes = set()
    for fd in proc.joinpath('fd').iterdir():
        try:
            value = os.readlink(fd)
            if value.startswith('socket:['): inodes.add(value[8:-1])
        except FileNotFoundError: pass
    for line in proc.joinpath('net/tcp').read_text().splitlines()[1:]:
        row = line.split()
        if row[1] == '0100007F:138A' and row[3] == '0A' and row[9] in inodes:
            return {'address': '127.0.0.1', 'port': 5002, 'inode': row[9], 'owner_identity': handle.root_identity}
    raise ValueError('owned_loopback_service_socket_missing')


def verify_service(handle):
    with handle.lock:
        return _verify_service_locked(handle)


def _verify_service_locked(handle):
    require(handle.kind == 'SERVICE' and handle.ended_monotonic is None, 'service_not_active')
    observed = {'schema_version': 1, 'helper_sha256': sha(__file__), 'start_sha256': sha(handle.receipt_dir / 'SERVICE_START.json'),
                'observed_monotonic': time.monotonic(), 'socket': socket_owned(handle)}
    discover_owned(handle.known)
    observed['owned_processes'] = list(handle.known.values())
    save(handle.receipt_dir / 'SERVICE_OBSERVATION.json', observed)
    return observed


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError('service_redirect_forbidden')


def _request(service, path, body=None, timeout=5):
    verify_service(service)
    require(path in ('/health', '/api/simulation/close-env', '/api/simulation/env-status'), 'unexpected_service_operation')
    require(0 < timeout <= 20, 'bounded_service_timeout_required')
    data = json.dumps(body).encode() if body is not None else None
    request = Request(SERVICE_URL + path, data=data, headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout) as response:
        return json.loads(response.read())


def start_service(binding, receipt_dir, env=None, *, startup_seconds=120):
    require(type(startup_seconds) is int and 1 <= startup_seconds <= 120, 'service_startup_bound')
    values = os.environ if env is None else env
    require(binding == validate_installation(env=values), 'service_installation_binding_changed')
    with socket.socket() as probe: probe.bind(('127.0.0.1', 5002))
    handle = _spawn([binding['python'], 'run.py'], Path(binding['backend']), _environment(values),
                    receipt_dir, 'SERVICE', binding)
    deadline = handle.started_monotonic + startup_seconds
    try:
        while time.monotonic() < deadline and handle.poll() is None:
            try:
                if _request(handle, '/health', timeout=min(2, deadline-time.monotonic())).get('status') == 'ok':
                    observation = verify_service(handle)
                    ready = time.monotonic()
                    require(ready <= deadline, 'service_readiness_deadline')
                    save(handle.receipt_dir / 'SERVICE_READY.json', {'schema_version': 1,
                        'helper_sha256': sha(__file__), 'start_sha256': sha(handle.receipt_dir / 'SERVICE_START.json'),
                        'ready_monotonic': ready, 'health': {'status': 'ok'}, 'observation': observation,
                        'observation_sha256': sha(handle.receipt_dir / 'SERVICE_OBSERVATION.json')}, exclusive=True)
                    handle.ready_monotonic = ready
                    return handle
            except (OSError, ValueError): pass
            time.sleep(min(.1, max(0, deadline-time.monotonic())))
        raise ValueError('service_startup_failed')
    except BaseException:
        cleanup_service(handle, timeout_seconds=20)
        raise


def spawn_world(*, run_dir, receipt_dir, env=None, python=None):
    run = private_path(run_dir); config, config_sha = read(run / 'config.json')
    require(config.get('mirofish_service_url') == SERVICE_URL, 'world_requires_separate_service')
    require(not any((run / n).exists() for n in ('checkpoint.json', 'INFLIGHT.json', 'REPORT.json')), 'world_not_pristine')
    interpreter = Path(sys.executable) if python is None else Path(python)
    require(interpreter.resolve() == Path(sys.executable).resolve(), 'unexpected_world_interpreter')
    command = [str(interpreter), '-u', '-m', 'lifespan.evaluation.runner', '--out', str(run), '--config', str(run / 'config.json')]
    return _spawn(command, ROOT, _environment(os.environ if env is None else env), receipt_dir, 'WORLD',
        {'run_directory': str(run), 'config_sha256': config_sha, 'service_url': SERVICE_URL,
         'runner_sha256': sha(ROOT / 'lifespan/evaluation/runner.py'), 'python_sha256': sha(interpreter)})


def _computer_roots(run):
    # Pinned runner layouts: do not recursively scan growing filesystem object
    # stores on every 250 ms ownership observation.
    return [private_path(path) for pattern in ('work/*/computers/*', 'learning/*/trial-*/computers/*')
            for path in run.glob(pattern) if path.is_dir()]


def _native_instances(handle, run):
    for directory in _computer_roots(run):
        path = directory / 'instance.json'
        if not path.exists() or str(path) in handle.instances: continue
        value, file_sha = read(path)
        require(path.resolve().is_relative_to(run) and value.get('backend') == 'bubblewrap', 'native_instance_scope')
        socket_path = Path(value['rpc_socket']); alias = socket_path.parent.parent; control = path.parent / 'control'
        owned = (alias.parent == Path('/tmp') and not alias.is_symlink() and alias.name.startswith('lifespan-bwrap-')
                 and socket_path == alias / 'control/command.sock' and socket_path.parent.is_symlink()
                 and socket_path.parent.resolve() == control.resolve())
        worker, sandbox = handle.known.get(value['pid']), handle.known.get(value['sandbox_pid'])
        if not worker or not sandbox or not owned: continue
        handle.instances[str(path)] = {'instance_path': str(path), 'instance_sha256': file_sha,
            'worker_identity': worker, 'sandbox_identity': sandbox, 'rpc_socket': str(socket_path),
            'alias': str(alias), 'control_target': str(control), 'owned_alias_observed': True}


def _simulation(handle, run, service):
    path = run / 'actors/mirofish_state.json'
    if not path.exists(): return
    state, state_sha = read(path); sim_id = state.get('simulation', {}).get('simulation_id')
    if sim_id is None: return
    require(type(sim_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', sim_id), 'simulation_id_shape')
    directory = ROOT / 'MiroFish/backend/uploads/simulations' / sim_id
    require(directory.resolve() == directory, 'simulation_directory_escape')
    if handle.simulation is not None:
        require(handle.simulation['simulation_id'] == sim_id, 'world_simulation_changed'); return
    if handle.simulation_pending is not None:
        require(handle.simulation_pending['simulation_id'] == sim_id, 'world_simulation_changed')
    def pending(reason):
        handle.simulation_pending = {'simulation_id': sim_id, 'reason': reason}
    run_state = directory / 'run_state.json'
    if not run_state.exists(): pending('run_state_not_yet_present'); return
    try: native, run_sha = read(run_state)
    except json.JSONDecodeError: pending('native_run_state_write_in_progress_or_malformed'); return
    pid = native.get('process_pid')
    if pid is None and native.get('runner_status') in ('idle', 'starting'):
        pending('native_process_not_yet_started'); return
    require(type(pid) is int and pid > 0, 'simulation_pid_missing')
    with service.lock:
        discover_owned(service.known)
        observed = service.known.get(pid)
    if observed is None or not same_identity(observed, identity(pid)):
        pending('native_process_identity_unobserved'); return
    proc = Path('/proc') / str(pid)
    args = [item.decode() for item in proc.joinpath('cmdline').read_bytes().split(b'\0') if item]
    script = ROOT / 'MiroFish/backend/scripts/run_reddit_simulation.py'; cfg = directory / 'simulation_config.json'
    require(proc.joinpath('cwd').resolve() == directory and len(args) >= 4 and args[2] == '--config'
            and Path(args[1]).resolve() == script and Path(args[3]).resolve() == cfg
            and Path(args[0]).resolve() == Path(service.binding['python']).resolve()
            and (len(args) == 4 or len(args) == 6 and args[4] == '--max-rounds'
                 and args[5].isdigit() and int(args[5]) > 0)
            and observed['ppid'] == service.root_identity['pid']
            and observed['pgid'] == pid and observed['sid'] == pid, 'native_simulation_command_binding')
    handle.simulation = {'simulation_id': sim_id, 'state_path': str(path), 'state_sha256_at_binding': state_sha,
        'run_state_sha256_at_binding': run_sha, 'identity': observed, 'cwd': str(directory),
        'script': str(script), 'script_sha256': sha(script), 'config_path': str(cfg), 'config_sha256': sha(cfg),
        'service_identity': service.root_identity}
    handle.known[pid] = observed
    handle.simulation_pending = None


def observe_world(handle, run_dir, service):
    require(handle.kind == 'WORLD' and handle.ended_monotonic is None, 'world_not_active')
    run = private_path(run_dir)
    require(handle.binding['run_directory'] == str(run), 'world_output_changed')
    discover_owned(handle.known); _native_instances(handle, run); _simulation(handle, run, service)
    value = {'schema_version': 1, 'helper_sha256': sha(__file__), 'start_sha256': sha(handle.receipt_dir / 'WORLD_START.json'),
             'observed_monotonic': time.monotonic(), 'owned_processes': list(handle.known.values()),
             'native_instances': list(handle.instances.values()), 'simulation': handle.simulation,
             'simulation_pending': handle.simulation_pending}
    save(handle.receipt_dir / 'WORLD_OBSERVATION.json', value)
    return value


def _signal_owned(old, name):
    """Pin the kernel task before checking its recorded identity and signaling it."""
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'pidfd_support_required')
    try:
        descriptor = os.pidfd_open(old['pid'])
        try:
            if not same_identity(old, identity(old['pid'])): return False
            signal.pidfd_send_signal(descriptor, getattr(signal, 'SIG' + name))
            return True
        finally: os.close(descriptor)
    except ProcessLookupError: return False


def _stop_known(handle, deadline, *, exclude_roots=()):
    signals = []; sent = set(); started = time.monotonic()
    while time.monotonic() < deadline:
        discover_owned(handle.known)
        def excluded(item):
            seen = set()
            while item and item['pid'] not in seen:
                if item['pid'] in exclude_roots: return True
                seen.add(item['pid']); item = handle.known.get(item.get('ppid'))
            return False
        live = [item for item in handle.known.values() if not excluded(item) and process_observation(item)['state'] == 'same_alive']
        if not live: break
        name = 'TERM' if time.monotonic() - started < 3 else 'KILL'
        for old in live:
            key = (old['pid'], old['start_ticks'], name)
            if key in sent or not same_identity(old, identity(old['pid'])): continue
            try:
                if _signal_owned(old, name):
                    sent.add(key); signals.append({'identity': old, 'signal': name})
            except ProcessLookupError: pass
        handle.process.poll(); time.sleep(min(.1, max(0, deadline-time.monotonic())))
    handle.process.poll()
    return {'signals': signals, 'observations_after': [process_observation(item) for item in handle.known.values()]}


def _remove_sockets(instances):
    result = []
    for item in instances:
        alias = Path(item['alias']); control = Path(item['control_target']); socket_path = control / 'command.sock'
        require(item['owned_alias_observed'] is True and alias.parent == Path('/tmp') and not alias.is_symlink()
                and alias.name.startswith('lifespan-bwrap-') and private_path(control) == control,
                'socket_cleanup_scope')
        if (alias / 'control').is_symlink() and (alias / 'control').resolve() == control.resolve():
            (alias / 'control').unlink(); alias.rmdir()
        if socket_path.exists() and not socket_path.is_symlink() and stat.S_ISSOCK(socket_path.lstat().st_mode):
            socket_path.unlink()
        result.append({'instance_sha256': item['instance_sha256'], 'alias_absent': not alias.exists() and not alias.is_symlink(),
                       'underlying_socket_absent': not socket_path.exists() and not socket_path.is_symlink()})
    return result


def cleanup_world(handle, run_dir, service, *, timeout_seconds=120):
    require(handle.kind == 'WORLD' and handle.ended_monotonic is None, 'world_cleanup_already_ended_or_wrong_kind')
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 180, 'world_cleanup_bound')
    started = time.monotonic(); deadline = started + timeout_seconds; failures = []; http = {}; sockets = []
    observation = None; stopped = {'signals': [], 'observations_after': []}
    with cleanup_scope():
        try: observation = observe_world(handle, run_dir, service)
        except Exception as exc: failures.append({'stage': 'observe', 'error_type': type(exc).__name__})
        # Stop the world controller first, so it cannot dispatch more work while
        # the scoped environment is being closed. Every signal rechecks identity.
        try: stopped = _stop_known(handle, min(deadline, time.monotonic() + 10),
                                  exclude_roots=(() if handle.simulation is None else (handle.simulation['identity']['pid'],)))
        except Exception as exc: failures.append({'stage': 'processes', 'error_type': type(exc).__name__})
        if handle.simulation is not None:
            sid = handle.simulation['simulation_id']; http['simulation_id'] = sid
            try:
                if time.monotonic() < deadline:
                    _request(service, '/api/simulation/close-env', {'simulation_id': sid, 'timeout': 10},
                             timeout=min(15, deadline-time.monotonic()))
                if time.monotonic() < deadline:
                    reply = _request(service, '/api/simulation/env-status', {'simulation_id': sid},
                                     timeout=min(5, deadline-time.monotonic()))
                    alive = reply.get('data', {}).get('env_alive')
                    http['env_alive'] = alive if type(alive) is bool else None
            except Exception as exc: failures.append({'stage': 'environment_close', 'error_type': type(exc).__name__})
        try:
            final = _stop_known(handle, deadline)
            stopped = {'signals': stopped['signals'] + final['signals'], 'observations_after': final['observations_after']}
            gone = bool(stopped['observations_after']) and all(r['state'] in ('absent', 'identity_replaced', 'zombie') for r in stopped['observations_after'])
            if gone: sockets = _remove_sockets(handle.instances.values())
        except Exception as exc:
            gone = False; failures.append({'stage': 'final_cleanup', 'error_type': type(exc).__name__})
    run = private_path(run_dir)
    try:
        computers = _computer_roots(run)
        raw_instances = {str(path / 'instance.json') for path in computers if (path / 'instance.json').exists()}
        for computer in computers:
            if (computer / 'hermes/config.yaml').exists() and not (computer / 'instance.json').is_file():
                failures.append({'stage': 'native_startup', 'error_type': 'UnboundNativeInstance'})
        actor_state = run / 'actors/mirofish_state.json'
        has_simulation = actor_state.exists() and read(actor_state)[0].get('simulation') is not None
    except Exception as exc:
        raw_instances = {'unknown'}; has_simulation = True
        failures.append({'stage': 'final_inventory', 'error_type': type(exc).__name__})
    root_exitcode = handle.poll()
    source_hash = sha(__file__); start_hash = sha(handle.receipt_dir / 'WORLD_START.json')
    observation_hash = sha(handle.receipt_dir / 'WORLD_OBSERVATION.json') if observation else None
    ended = time.monotonic(); handle.ended_monotonic = ended
    confirmed = bool(not failures and gone and raw_instances == set(handle.instances)
        and (not has_simulation or handle.simulation is not None) and all(r['alias_absent'] and r['underlying_socket_absent'] for r in sockets)
        and ended <= deadline)
    value = {'schema_version': 1, 'helper_sha256': source_hash, 'status': 'confirmed' if confirmed else 'unconfirmed',
        'start_sha256': start_hash, 'observation_sha256': observation_hash,
        'started_monotonic': started, 'ended_monotonic': ended, 'limit_seconds': timeout_seconds,
        'root_exitcode': root_exitcode, 'failures': failures, 'environment_close': http,
        'clock_scope': 'through_final_inventory_and_poll; excludes_terminal_receipt_write',
        'processes': stopped, 'sockets': sockets}
    save(handle.receipt_dir / 'WORLD_CLEANUP.json', value, exclusive=True)
    return value


def cleanup_service(handle, *, timeout_seconds=30):
    require(handle.kind == 'SERVICE' and handle.ended_monotonic is None, 'service_cleanup_already_ended_or_wrong_kind')
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 120, 'service_cleanup_bound')
    started = time.monotonic(); deadline = started + timeout_seconds; failures = []
    stopped = {'signals': [], 'observations_after': []}
    with cleanup_scope():
        try: stopped = _stop_known(handle, deadline)
        except Exception as exc: failures.append({'stage': 'service_tree', 'error_type': type(exc).__name__})
    root_exitcode = handle.poll()
    source_hash = sha(__file__); start_hash = sha(handle.receipt_dir / 'SERVICE_START.json')
    observation_hash = sha(handle.receipt_dir / 'SERVICE_OBSERVATION.json') if (handle.receipt_dir / 'SERVICE_OBSERVATION.json').exists() else None
    ended = time.monotonic(); handle.ended_monotonic = ended
    confirmed = bool(stopped['observations_after']) and all(r['state'] in ('absent', 'identity_replaced', 'zombie')
        for r in stopped['observations_after']) and not failures and ended <= deadline
    value = {'schema_version': 1, 'helper_sha256': source_hash, 'status': 'confirmed' if confirmed else 'unconfirmed',
        'start_sha256': start_hash, 'observation_sha256': observation_hash, 'started_monotonic': started,
        'ended_monotonic': ended, 'limit_seconds': timeout_seconds, 'root_exitcode': root_exitcode,
        'clock_scope': 'through_final_inventory_and_poll; excludes_terminal_receipt_write', 'processes': stopped, 'failures': failures}
    save(handle.receipt_dir / 'SERVICE_CLEANUP.json', value, exclusive=True)
    return value


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _key(value):
    require(type(value) is dict and all(type(value.get(k)) is int and value[k] > 0 for k in ('pid', 'start_ticks'))
            and type(value.get('uid')) is int and value['uid'] >= 0
            and type(value.get('boot_id')) is str and bool(value['boot_id']), 'invalid_process_identity')
    return tuple(value[k] for k in ('pid', 'start_ticks', 'uid', 'boot_id'))


def _process_receipts(processes, root, extra_roots=()):
    rows = processes['observations_after']
    require(type(rows) is list and bool(rows), 'missing_final_process_inventory')
    keys = [_key(r['identity']) for r in rows]
    require(len(set(keys)) == len(keys) and len({key[0] for key in keys}) == len(keys)
            and _key(root) in keys, 'duplicate_or_missing_process_identity')
    by_pid = {r['identity']['pid']: r['identity'] for r in rows}
    roots = {_key(root), *(_key(r) for r in extra_roots)}
    for row in rows:
        old, current = row['identity'], row['observed_current']
        require(_key(old)[2:] == _key(root)[2:], 'process_owner_boot_mismatch')
        parent, seen = old, set()
        while _key(parent) not in roots:
            require(parent['pid'] not in seen and parent.get('ppid') in by_pid, 'unbound_process_ancestry')
            seen.add(parent['pid']); next_parent = by_pid[parent['ppid']]
            require(parent['start_ticks'] >= next_parent['start_ticks'], 'invalid_process_birth_order')
            parent = next_parent
        if row['state'] == 'absent': require(current is None, 'false_process_absence')
        elif row['state'] == 'zombie':
            require(_key(current) == _key(old) and current['state'] == 'Z', 'false_zombie_observation')
        elif row['state'] == 'identity_replaced':
            require(_key(current) != _key(old) and current['pid'] == old['pid'], 'false_replaced_identity')
        else: raise ValueError('owned_process_not_confirmed_gone')
    require(type(processes['signals']) is list, 'invalid_signal_inventory')
    for sent in processes['signals']:
        require(_key(sent['identity']) in keys and sent['signal'] in ('TERM', 'KILL'), 'unowned_process_signal')
    return set(keys)


def _receipt_chain(directory, kind, completed):
    directory = private_path(directory); hashes = {}
    def load(name):
        value, raw_hash = read(directory / name); hashes[name] = raw_hash
        require(type(value['schema_version']) is int and value['schema_version'] == 1 and value['helper_sha256'] == sha(__file__), 'lifecycle_source_binding')
        return value
    start = load(kind + '_START.json'); intent = load(kind + '_INTENT.json')
    require(start['intent_sha256'] == hashes[kind + '_INTENT.json'] and start['kind'] == intent['kind'] == kind
            and all(start[k] == intent[k] for k in ('command', 'cwd', 'binding', 'started_monotonic')),
            'lifecycle_launch_binding')
    root = start['root_identity']; _key(root)
    require(root['uid'] == os.getuid() and root['pgid'] == root['sid'] == root['pid'], 'isolated_process_session')
    require(_number(start['started_monotonic']), 'invalid_launch_clock')
    observation = load(kind + '_OBSERVATION.json') if (directory / (kind + '_OBSERVATION.json')).exists() else None
    if observation:
        require(observation['start_sha256'] == hashes[kind + '_START.json']
                and _number(observation['observed_monotonic'])
                and observation['observed_monotonic'] >= start['started_monotonic'], 'lifecycle_observation_binding')
    cleanup = load(kind + '_CLEANUP.json') if (directory / (kind + '_CLEANUP.json')).exists() else None
    if cleanup:
        require(cleanup['start_sha256'] == hashes[kind + '_START.json']
                and all(_number(cleanup[k]) for k in ('started_monotonic', 'ended_monotonic'))
                and type(cleanup['limit_seconds']) is int and 1 <= cleanup['limit_seconds'] <= (180 if kind == 'WORLD' else 120)
                and start['started_monotonic'] <= cleanup['started_monotonic'] <= cleanup['ended_monotonic']
                and cleanup['clock_scope'] == 'through_final_inventory_and_poll; excludes_terminal_receipt_write'
                and cleanup['status'] in ('confirmed', 'unconfirmed'), 'lifecycle_cleanup_binding')
        require(cleanup['observation_sha256'] == hashes.get(kind + '_OBSERVATION.json')
                and (observation is None or observation['observed_monotonic'] <= cleanup['ended_monotonic']),
                'cleanup_observation_hash')
        if cleanup['status'] == 'confirmed':
            require(cleanup['ended_monotonic'] - cleanup['started_monotonic'] <= cleanup['limit_seconds']
                    and not cleanup['failures'] and type(cleanup['root_exitcode']) is int, 'false_cleanup_confirmation')
    if completed:
        require(observation is not None and cleanup is not None and cleanup['status'] == 'confirmed', 'incomplete_lifecycle')
    return start, observation, cleanup, hashes


def _audit_result(callback):
    result = {'schema_version': 1, 'ok': False, 'errors': [], 'hashes': {}, 'cleanup_confirmed': False,
              'scope': 'local_source_bound_lifecycle_receipts; no_model_quality_or_cost_claim'}
    try:
        result.update(callback()); result['ok'] = True
    except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        code = str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else type(exc).__name__
        result['errors'].append({'code': code})
    return result


def validate_service_receipts(receipt_dir, *, completed=False):
    """Pure filesystem audit. Never inspect /proc, signal, import MiroFish or call HTTP."""
    def verify():
        start, observation, cleanup, hashes = _receipt_chain(receipt_dir, 'SERVICE', completed)
        binding = start['binding']; backend = ROOT / 'MiroFish/backend'
        require(start['cwd'] == str(backend) and start['command'] == [str(backend / '.venv/bin/python'), 'run.py']
                and binding['worktree'] == str(ROOT) and binding['backend'] == str(backend)
                and binding['server_url'] == SERVICE_URL and binding['python'] == str(backend / '.venv/bin/python'), 'service_launch_scope')
        expected_config = {'config_module': str(backend / 'app/config.py'), 'uploads': str(backend / 'uploads'),
            'graph_database': str(backend / 'uploads/local_graph.sqlite3'), 'graph_backend': 'local',
            'debug': False, 'host': '127.0.0.1', 'port': '5002'}
        require(binding['configuration'] == expected_config
                and binding['python_sha256'] == sha(backend / '.venv/bin/python'), 'service_configuration_binding')
        for name in ('MiroFish/backend/run.py', 'MiroFish/backend/app/config.py', 'scripts/scale_v2_process.py'):
            require(binding['source_sha256'][name] == sha(ROOT / name), 'service_source_changed')
        ready = None; ready_path = Path(receipt_dir) / 'SERVICE_READY.json'
        if ready_path.exists():
            ready, hashes['SERVICE_READY.json'] = read(ready_path)
            proof = ready['observation']
            proof_raw = (json.dumps(proof, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
            require(type(ready['schema_version']) is int and ready['schema_version'] == 1
                    and ready['helper_sha256'] == sha(__file__) and proof['helper_sha256'] == sha(__file__)
                    and ready['start_sha256'] == proof['start_sha256'] == hashes['SERVICE_START.json']
                    and ready['observation_sha256'] == hashlib.sha256(proof_raw).hexdigest()
                    and ready['health'] == {'status': 'ok'} and _number(ready['ready_monotonic'])
                    and _number(proof['observed_monotonic'])
                    and start['started_monotonic'] <= proof['observed_monotonic'] <= ready['ready_monotonic']
                    and ready['ready_monotonic'] - start['started_monotonic'] <= 120
                    and (cleanup is None or ready['ready_monotonic'] <= cleanup['started_monotonic']), 'service_readiness_binding')
        if completed: require(ready is not None, 'missing_service_readiness')
        observed_keys = set()
        for observed in [item for item in (observation, ready['observation'] if ready else None) if item]:
            keys = [_key(item) for item in observed['owned_processes']]
            require(len(keys) == len(set(keys)) and _key(start['root_identity']) in keys, 'service_observed_process_inventory')
            observed_keys.update(keys)
            socket_proof = observed['socket']
            require(socket_proof['address'] == '127.0.0.1' and type(socket_proof['port']) is int and socket_proof['port'] == 5002
                    and type(socket_proof['inode']) is str and socket_proof['inode'].isdigit()
                    and _key(socket_proof['owner_identity']) == _key(start['root_identity']), 'service_socket_owner_binding')
        if cleanup and cleanup['status'] == 'confirmed':
            final = _process_receipts(cleanup['processes'], start['root_identity'])
            require(observed_keys <= final, 'cleanup_dropped_observed_service_process')
        return {'hashes': hashes, 'start': start, 'ready_monotonic': ready['ready_monotonic'] if ready else None,
                'started_monotonic': start['started_monotonic'],
                'ended_monotonic': cleanup['ended_monotonic'] if cleanup else None,
                'cleanup_started_monotonic': cleanup['started_monotonic'] if cleanup else None,
                'cleanup_limit_seconds': cleanup['limit_seconds'] if cleanup else None,
                'root_exitcode': cleanup['root_exitcode'] if cleanup else None,
                'cleanup_confirmed': bool(cleanup and cleanup['status'] == 'confirmed')}
    return _audit_result(verify)


def validate_world_receipts(receipt_dir, run_dir, service_start, *, completed=False):
    """Validate one scoped world and native-process cleanup; never contact its service."""
    def verify():
        run = private_path(run_dir)
        start, observation, cleanup, hashes = _receipt_chain(receipt_dir, 'WORLD', completed)
        require(start['cwd'] == str(ROOT) and start['command'][1:] == ['-u', '-m', 'lifespan.evaluation.runner',
                    '--out', str(run), '--config', str(run / 'config.json')], 'canonical_world_command')
        binding = start['binding']
        require(binding['run_directory'] == str(run) and binding['service_url'] == SERVICE_URL
                and binding['config_sha256'] == sha(run / 'config.json')
                and binding['runner_sha256'] == sha(ROOT / 'lifespan/evaluation/runner.py')
                and Path(start['command'][0]).resolve() == Path(sys.executable).resolve()
                and binding['python_sha256'] == sha(start['command'][0]), 'world_configuration_binding')
        require(read(run / 'config.json')[0].get('mirofish_service_url') == SERVICE_URL, 'world_service_downgrade')
        extra = []; instances = []; known = set()
        if observation:
            require(type(observation['owned_processes']) is list and type(observation['native_instances']) is list,
                    'invalid_world_observation_inventory')
            known = {_key(item) for item in observation['owned_processes']}
            require(len(known) == len(observation['owned_processes']), 'duplicate_observed_process')
            require(_key(start['root_identity']) in known, 'world_root_not_observed')
            simulation = observation['simulation']; instances = observation['native_instances']
            if simulation:
                sid = simulation['simulation_id']; require(re.fullmatch('[A-Za-z0-9_-]{1,128}', sid), 'simulation_id_shape')
                directory = ROOT / 'MiroFish/backend/uploads/simulations' / sid
                require(simulation['cwd'] == str(directory) and directory.resolve() == directory
                        and simulation['config_path'] == str(directory / 'simulation_config.json')
                        and simulation['config_sha256'] == sha(directory / 'simulation_config.json')
                        and simulation['script'] == str(ROOT / 'MiroFish/backend/scripts/run_reddit_simulation.py')
                        and simulation['script_sha256'] == sha(simulation['script']), 'simulation_file_binding')
                pid = simulation['identity']['pid']; extra = [simulation['identity']]
                require(_key(extra[0]) in known and _key(simulation['service_identity']) == _key(service_start['root_identity'])
                        and _key(extra[0])[2:] == _key(service_start['root_identity'])[2:]
                        and extra[0]['start_ticks'] >= service_start['root_identity']['start_ticks']
                        and extra[0]['ppid'] == service_start['root_identity']['pid']
                        and extra[0]['pgid'] == extra[0]['sid'] == pid
                        and read(run / 'actors/mirofish_state.json')[0]['simulation']['simulation_id'] == sid
                        and read(directory / 'run_state.json')[0]['process_pid'] == pid, 'simulation_process_binding')
            for item in instances:
                path = private_path(item['instance_path']); value, raw_hash = read(path)
                require(path.is_relative_to(run) and raw_hash == item['instance_sha256']
                        and value['backend'] == 'bubblewrap'
                        and _key(item['worker_identity']) in known and _key(item['sandbox_identity']) in known
                        and value['pid'] == item['worker_identity']['pid'] and value['sandbox_pid'] == item['sandbox_identity']['pid'],
                        'native_instance_process_binding')
                alias = Path(item['alias']); control = path.parent / 'control'
                require(item['control_target'] == str(control) and item['owned_alias_observed'] is True
                        and alias.parent == Path('/tmp') and alias.name.startswith('lifespan-bwrap-')
                        and item['rpc_socket'] == value['rpc_socket'] == str(alias / 'control/command.sock'), 'native_socket_scope')
        if cleanup:
            require(cleanup['observation_sha256'] == hashes.get('WORLD_OBSERVATION.json'), 'cleanup_observation_hash')
        if cleanup and cleanup['status'] == 'confirmed':
            require(observation is not None, 'missing_world_cleanup_observation')
            close = cleanup['environment_close']
            require(type(close) is dict and (close == {} if not extra else
                    close.get('simulation_id') == observation['simulation']['simulation_id']
                    and (close.get('env_alive') is None or type(close['env_alive']) is bool)), 'environment_close_scope')
            final = _process_receipts(cleanup['processes'], start['root_identity'], extra)
            require(known <= final, 'cleanup_dropped_observed_process')
            computers = _computer_roots(run)
            raw_paths = {str(path / 'instance.json') for path in computers if (path / 'instance.json').exists()}
            require(raw_paths == {item['instance_path'] for item in instances}
                    and len(raw_paths) == len(instances), 'unbound_native_instance_inventory')
            for computer in computers:
                require(not (computer / 'hermes/config.yaml').exists() or (computer / 'instance.json').is_file(),
                        'unbound_native_startup')
            require({row['instance_sha256'] for row in cleanup['sockets']} == {item['instance_sha256'] for item in instances}
                    and len(cleanup['sockets']) == len(instances), 'socket_cleanup_inventory')
            for item, row in zip(sorted(instances, key=lambda x: x['instance_sha256']),
                                 sorted(cleanup['sockets'], key=lambda x: x['instance_sha256'])):
                alias = Path(item['alias']); socket_path = Path(item['control_target']) / 'command.sock'
                require(row['alias_absent'] is True and row['underlying_socket_absent'] is True
                        and not alias.exists() and not alias.is_symlink()
                        and not socket_path.exists() and not socket_path.is_symlink(), 'native_socket_survived_cleanup')
            state_path = run / 'actors/mirofish_state.json'
            require(not state_path.exists() or read(state_path)[0].get('simulation') is None or bool(extra), 'unbound_oasis_environment')
            if completed: require(cleanup['root_exitcode'] == 0, 'completed_world_exit_nonzero')
        return {'hashes': hashes, 'started_monotonic': start['started_monotonic'],
                'ended_monotonic': cleanup['ended_monotonic'] if cleanup else None,
                'cleanup_started_monotonic': cleanup['started_monotonic'] if cleanup else None,
                'cleanup_limit_seconds': cleanup['limit_seconds'] if cleanup else None,
                'root_exitcode': cleanup['root_exitcode'] if cleanup else None,
                'cleanup_confirmed': bool(cleanup and cleanup['status'] == 'confirmed'),
                'simulation_id': observation['simulation']['simulation_id'] if observation and observation['simulation'] else None}
    return _audit_result(verify)
