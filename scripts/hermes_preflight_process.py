"""Owned-process supervision for the additive Hermes capability preflight.

No provider calls live here. The child invokes the supplied executor exactly
once; the native path supplies the unchanged runtime.execute_case callable.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
import stat
import time

from lifespan.mirofish import save

POLL_SECONDS = .1
TERM_GRACE_SECONDS = 5


@contextmanager
def interruption_scope():
    """SIGTERM requests cleanup; repeated signals cannot interrupt cleanup."""
    state = {'requested': False}
    previous = signal.getsignal(signal.SIGTERM)
    def request(signum, frame):
        state['requested'] = True
    signal.signal(signal.SIGTERM, request)
    try:
        yield state
    finally:
        signal.signal(signal.SIGTERM, previous)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def identity(pid):
    """Only process metadata; never read argv, environment or provider bodies."""
    try:
        root = Path('/proc') / str(pid)
        fields = (root/'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': int(pid), 'ppid': int(fields[1]), 'pgid': int(fields[2]),
                'sid': int(fields[3]), 'start_ticks': int(fields[19]),
                'uid': root.stat().st_uid, 'boot_id': boot_id(), 'state': fields[0]}
    except FileNotFoundError:
        return None
    except (OSError, ValueError, IndexError):
        return {'pid': int(pid), 'unreadable': True}


def same_identity(first, second):
    return (isinstance(first, dict) and isinstance(second, dict)
            and not first.get('unreadable') and not second.get('unreadable')
            and all(first.get(key) == second.get(key) for key in ('pid', 'uid', 'start_ticks', 'boot_id')))


def discover_owned(known):
    current = {int(p.name): identity(int(p.name)) for p in Path('/proc').iterdir() if p.name.isdigit()}
    parents = {pid for pid, old in known.items() if same_identity(old, current.get(pid))}
    changed = True
    while changed:
        changed = False
        for pid, item in current.items():
            if (item and not item.get('unreadable') and item['uid'] == os.getuid()
                    and pid not in known and item['ppid'] in parents):
                known[pid] = item; parents.add(pid); changed = True
    return current


def observation(old):
    current = identity(old['pid'])
    if current is None:
        state = 'absent'
    elif current.get('unreadable'):
        state = 'unknown'
    elif not same_identity(old, current):
        state = 'identity_replaced'
    elif current['state'] == 'Z':
        state = 'zombie'
    else:
        state = 'same_alive'
    return {'identity': deepcopy(old), 'state': state, 'observed_current': current}


def _instance(trial, employee, known):
    path = Path(trial) / 'native/computers' / employee / 'instance.json'
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes(); data = json.loads(raw)
        socket = Path(data['rpc_socket'])
        alias = socket.parent.parent
        control = Path(trial) / 'native/computers' / employee / 'control'
        owned_alias = (alias.parent == Path('/tmp') and alias.name.startswith('lifespan-bwrap-')
            and socket.name == 'command.sock' and socket.parent.name == 'control'
            and socket.parent.is_symlink() and socket.parent.resolve() == control.resolve())
        return {'instance_path': str(path), 'instance_sha256': hashlib.sha256(raw).hexdigest(),
            'worker_pid': data['pid'], 'sandbox_pid': data['sandbox_pid'],
            'worker_identity': deepcopy(known.get(data['pid'])),
            'sandbox_identity': deepcopy(known.get(data['sandbox_pid'])),
            'rpc_socket': str(socket), 'alias': str(alias), 'control_target': str(control),
            'owned_alias_observed': owned_alias, 'socket_existed': socket.exists()}
    except (OSError, ValueError, TypeError, KeyError):
        return {'malformed': True}


def _child(executor, kwargs, trial, connection):
    try:
        os.setsid()
        # Do not inherit the parent's cooperative stop handler in an executor
        # that must itself remain terminable by the owned-process supervisor.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        with (Path(trial)/'worker.log').open('a') as log:
            os.dup2(log.fileno(), 1); os.dup2(log.fileno(), 2)
            save(Path(trial)/'worker-identity.json', identity(os.getpid()))
            record = executor(**kwargs)
            path = Path(kwargs['root'])/'session.json'
            if not path.is_file():
                raise RuntimeError('Executor returned without a durable session')
            if json.loads(path.read_bytes()) != record:
                raise RuntimeError('Executor return differs from durable native session')
            outcome = {'status': 'returned', 'session_sha256': sha(path)}
    except BaseException as exc:
        outcome = {'status': 'exception', 'error_type': type(exc).__name__}
    try:
        save(Path(trial)/'worker-outcome.json', outcome)
        connection.send(outcome)
    finally:
        connection.close()


def supervise(executor, kwargs, trial, *, timeout_seconds=420, cleanup_seconds=30, stop_requested=lambda: False):
    with interruption_scope() as interruption:
        return _supervise(executor, kwargs, trial, timeout_seconds=timeout_seconds,
                          cleanup_seconds=cleanup_seconds, interruption=interruption, stop_requested=stop_requested)


def _supervise(executor, kwargs, trial, *, timeout_seconds, cleanup_seconds, interruption, stop_requested):
    """One fork, one execution, bounded termination of verified descendants.

PID identity checks prevent signaling reused or unrelated processes. Missing
native identity/socket evidence remains unconfirmed, even after a clean exit.
"""
    trial = Path(trial); trial.mkdir(parents=True, mode=0o700)
    context = multiprocessing.get_context('fork')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(executor, kwargs, trial, child))
    started = time.monotonic(); process.start(); child.close()
    root = identity(process.pid)
    known = {process.pid: root} if root and not root.get('unreadable') else {}
    outcome = None; instance = None; timed_out = interrupted = False
    try:
        while process.is_alive():
            current_root = identity(process.pid)
            if same_identity(root, current_root) and current_root.get('sid') == process.pid:
                root = current_root; known[process.pid] = root
            discover_owned(known)
            current_instance = _instance(trial, kwargs['employee'], known)
            if current_instance and (instance is None or current_instance.get('owned_alias_observed')):
                instance = current_instance
            if parent.poll():
                try: outcome = parent.recv()
                except EOFError: pass
            if interruption['requested'] or stop_requested():
                interrupted = True; break
            if time.monotonic() - started >= timeout_seconds:
                timed_out = True; break
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        cleanup_started = time.monotonic(); deadline = cleanup_started + cleanup_seconds
        execution_elapsed = cleanup_started - started
        signals = []; signaled = set(); forced = False
        while True:
            discover_owned(known)
            live = [old for old in known.values() if observation(old)['state'] == 'same_alive']
            if not live or time.monotonic() >= deadline:
                break
            forced = True
            name = 'TERM' if time.monotonic() - cleanup_started < TERM_GRACE_SECONDS else 'KILL'
            for old in live:
                key = (old['pid'], old['start_ticks'], name)
                if key not in signaled and same_identity(old, identity(old['pid'])):
                    try:
                        os.kill(old['pid'], getattr(signal, 'SIG' + name))
                        signals.append({'pid': old['pid'], 'start_ticks': old['start_ticks'], 'signal': name})
                        signaled.add(key)
                    except ProcessLookupError:
                        pass
            process.join(timeout=min(POLL_SECONDS, max(0, deadline-time.monotonic())))
        process.join(timeout=0)
        if outcome is None and parent.poll():
            try: outcome = parent.recv()
            except EOFError: pass
        parent.close()
        if instance is None:
            instance = _instance(trial, kwargs['employee'], known)
        after = [observation(old) for old in known.values()]
        gone = bool(known) and all(item['state'] in ('absent', 'identity_replaced', 'zombie') for item in after)
        alias_removed = False; socket_absent = False; underlying_absent = False; underlying_removed = False
        if instance and not instance.get('malformed'):
            socket = Path(instance['rpc_socket']); alias = Path(instance['alias'])
            underlying = Path(instance['control_target'])/'command.sock'
            if gone and instance['owned_alias_observed'] and underlying.exists():
                # Only the exact trial-owned socket inode; never unlink a
                # substituted file or symlink and never touch a live sandbox.
                try:
                    if not underlying.is_symlink() and stat.S_ISSOCK(underlying.lstat().st_mode):
                        underlying.unlink(); underlying_removed = True
                except OSError:
                    pass
            if gone and instance['owned_alias_observed'] and socket.parent.is_symlink():
                # The underlying socket is in this trial, never another native
                # sandbox. Keep filesystem artifacts; remove only our alias.
                if socket.parent.resolve() == Path(instance['control_target']).resolve():
                    try:
                        socket.parent.unlink(); alias.rmdir(); alias_removed = True
                    except OSError:
                        pass
            socket_absent = not socket.exists() and not alias.exists()
            underlying_absent = not underlying.exists() and not underlying.is_symlink()
        cleanup_elapsed = time.monotonic() - cleanup_started
        confirmed = (gone and instance and not instance.get('malformed')
            and instance.get('worker_identity') and instance.get('sandbox_identity')
            and instance.get('owned_alias_observed') and socket_absent and underlying_absent
            and cleanup_elapsed <= cleanup_seconds)
        cleanup = {'schema_version': 1, 'status': 'confirmed' if confirmed else 'unconfirmed',
            'limit_seconds': cleanup_seconds, 'elapsed_seconds': cleanup_elapsed,
            'forced': forced, 'root_identity': root, 'owned_processes': list(known.values()),
            'observations_after': after, 'signals': signals, 'instance': instance,
            'alias_removed_by_supervisor': alias_removed, 'socket_and_alias_absent': socket_absent,
            'underlying_control_socket_absent': underlying_absent,
            'underlying_socket_removed_by_supervisor': underlying_removed}
        save(trial/'cleanup.json', cleanup)
    interrupted = interrupted or interruption['requested'] or stop_requested()
    result = {'status': 'interrupted' if interrupted else 'timeout' if timed_out else
              'returned' if outcome and outcome.get('status') == 'returned' else 'exception',
        'outcome': outcome, 'root_exitcode': process.exitcode,
        'timeout_seconds': timeout_seconds, 'cleanup_seconds': cleanup_seconds,
        'execution_elapsed_seconds': execution_elapsed,
        'elapsed_seconds': time.monotonic() - started, 'cleanup': cleanup}
    save(trial/'supervision.json', result)
    return result
