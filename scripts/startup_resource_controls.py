#!/usr/bin/env python3
"""Fixed, harmless own-user-unit cgroup-v2 probe; no native agent or model work.

Only ``run_probe(new_private_directory)`` starts anything. It runs the literal
readback payload below, never a caller-supplied command, unit name or environment.
Four CPU/memory/process controls are checked in kernel files. I/O controls are
not requested or qualified: an absent io.weight is unavailable; a present file
is only an observation. This probe neither reserves latency nor proves that a
future workload fits the limits. It does not alter existing workloads.

The child waits on its own stdin after publishing identity/readbacks. The parent
releases that pipe; RuntimeMaxSec is the independent service backstop. There is
no systemctl stop/kill operation. Only the directly spawned systemd-run client
can be killed after a timeout, after checking its still-matching process identity.
Private receipts retain hashes/counts rather than raw commands, stderr or env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import sys
import time
import uuid

VERSION = 'startup-resource-controls-v1'
PREFIX = 'bigworld-resource-probe-'
PROPERTIES = ('RuntimeMaxSec=15', 'MemoryMax=64M', 'MemorySwapMax=0',
              'TasksMax=32', 'CPUQuota=100%')
KERNEL_KEYS = ('memory.max', 'memory.swap.max', 'pids.max', 'cpu.max')
SHOW_KEYS = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID',
             'ControlGroup', 'InvocationID')
CGROUP_ROOT = Path('/sys/fs/cgroup')
OUTER_SECONDS = 22

# -I -S -B prevents environment/site customization and bytecode writes. No
# requests, model library, persona, workload file or environment variable is read.
PAYLOAD = r'''
import json, os, sys
from pathlib import Path
p = Path('/proc/self')
raw = (p/'stat').read_text(); fields = raw[raw.rfind(')')+2:].split()
rows = (p/'cgroup').read_text().splitlines()
assert len(rows) == 1 and rows[0].startswith('0::/')
group = rows[0][3:]; root = Path('/sys/fs/cgroup') / group.lstrip('/')
def read(name):
    try: return (root/name).read_text().strip()
    except FileNotFoundError: return None
print(json.dumps({'pid': os.getpid(), 'uid': os.getuid(),
    'start_ticks': int(fields[19]),
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'cgroup': group, 'kernel': {k: read(k) for k in
        ('memory.max','memory.swap.max','pids.max','cpu.max','io.weight')}}), flush=True)
sys.stdin.readline()
'''


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unit_name():
    return PREFIX + uuid.uuid4().hex + '.service'


def checked_name(name):
    require(type(name) is str and re.fullmatch(PREFIX + r'[0-9a-f]{32}\.service', name),
            'invalid_own_probe_unit')
    return name


def identity(pid):
    require(type(pid) is int and pid > 0, 'invalid_process_pid')
    proc = Path('/proc') / str(pid)
    try:
        raw = (proc / 'stat').read_text(); fields = raw[raw.rfind(')') + 2:].split()
        rows = (proc / 'cgroup').read_text().splitlines()
        require(len(rows) == 1 and rows[0].startswith('0::/'), 'process_not_cgroup_v2')
        return {'pid': pid, 'uid': proc.stat().st_uid, 'start_ticks': int(fields[19]),
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'state': fields[0], 'cgroup': rows[0][3:]}
    except FileNotFoundError:
        return None


def same_identity(first, second):
    keys = ('pid', 'uid', 'start_ticks', 'boot_id')
    return (type(first) is dict and type(second) is dict and
            all(type(first.get(k)) is type(second.get(k)) and first.get(k) == second.get(k)
                for k in keys))


def kernel_readback(group, uid, name):
    checked_name(name)
    require(type(group) is str, 'foreign_probe_cgroup')
    parts = PurePosixPath(group)
    require(type(group) is str and parts.is_absolute() and '..' not in parts.parts
            and group.startswith(f'/user.slice/user-{uid}.slice/user@{uid}.service/')
            and parts.name == name, 'foreign_probe_cgroup')
    base = CGROUP_ROOT / group.lstrip('/')
    require(base.resolve().is_relative_to(CGROUP_ROOT.resolve()), 'cgroup_path_escape')
    result = {}
    for key in (*KERNEL_KEYS, 'io.weight'):
        try:
            result[key] = (base / key).read_text().strip()
        except FileNotFoundError:
            result[key] = None
    return result


def show_unit(name, timeout=2):
    checked_name(name)
    result = subprocess.run(['systemctl', '--user', 'show', name,
        *['--property=' + key for key in SHOW_KEYS]], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    require(len(result.stdout) <= 16384, 'unit_observation_too_large')
    values = {}
    for line in result.stdout.decode('utf-8').splitlines():
        key, separator, value = line.partition('=')
        require(separator and key in SHOW_KEYS and key not in values, 'invalid_unit_observation')
        values[key] = value
    require(set(values) == set(SHOW_KEYS) and values['Id'] == name
            and (result.returncode == 0 or values['LoadState'] == 'not-found'),
            'own_unit_observation_failed')
    return values


def validate_observation(name, worker, unit, current, kernel, *, uid):
    """Pure binding and control validation, independently tested without systemd."""
    checked_name(name)
    require(type(worker) is dict and set(worker) ==
            {'pid', 'uid', 'start_ticks', 'boot_id', 'cgroup', 'kernel'}, 'invalid_probe_receipt')
    require(type(worker['pid']) is int and worker['pid'] > 0 and type(worker['uid']) is int
            and worker['uid'] == uid and type(worker['start_ticks']) is int and worker['start_ticks'] > 0
            and type(worker['boot_id']) is str and bool(worker['boot_id']), 'invalid_probe_identity')
    require(same_identity(worker, current) and current['state'] not in ('Z', 'X'), 'probe_process_identity_changed')
    require(unit['Id'] == name and unit['LoadState'] == 'loaded' and unit['ActiveState'] == 'active'
            and unit['SubState'] == 'running' and unit['MainPID'] == str(worker['pid'])
            and unit['ControlGroup'] == worker['cgroup']
            and re.fullmatch('[0-9a-f]{32}', unit['InvocationID']), 'probe_unit_identity_mismatch')
    group = worker['cgroup']
    require(type(group) is str and '..' not in PurePosixPath(group).parts
            and group.startswith(f'/user.slice/user-{uid}.slice/user@{uid}.service/')
            and PurePosixPath(group).name == name, 'foreign_probe_cgroup')
    require(current.get('cgroup') == group, 'probe_process_cgroup_mismatch')
    require(type(kernel) is dict and set(kernel) == {*KERNEL_KEYS, 'io.weight'}
            and worker['kernel'] == kernel, 'probe_kernel_readback_mismatch')
    require(kernel['memory.max'] == '67108864' and kernel['memory.swap.max'] == '0'
            and kernel['pids.max'] == '32', 'probe_kernel_limits_not_enforced')
    cpu = kernel['cpu.max']
    require(type(cpu) is str and re.fullmatch(r'[1-9][0-9]* [1-9][0-9]*', cpu), 'probe_cpu_quota_missing')
    quota, period = map(int, cpu.split())
    require(quota == period, 'probe_cpu_quota_not_one_cpu')
    io_value = kernel['io.weight']
    require(io_value is None or type(io_value) is str, 'invalid_io_observation')
    return {'verified': True, 'kernel': {key: kernel[key] for key in KERNEL_KEYS},
        'cpu_quota_cores': 1, 'io': {'requested': False, 'qualified': False,
            'status': 'unavailable' if io_value is None else 'observed_unrequested',
            'kernel_file_present': io_value is not None,
            'readback_sha256': sha(io_value.encode()) if io_value is not None else None}}


def cleanup_evidence(name, unit, owned, current, client_exit, observed_service=None):
    checked_name(name)
    require(unit['Id'] == name, 'cleanup_foreign_unit')
    dead = (unit['ActiveState'] == 'inactive' and unit['SubState'] == 'dead'
            and unit['MainPID'] == '0')
    collected = (unit['LoadState'] == 'not-found' and not unit['InvocationID']
                 and not unit['ControlGroup'])
    same_unit = (observed_service is not None and unit['LoadState'] == 'loaded'
                 and unit['InvocationID'] == observed_service['InvocationID']
                 and unit['ControlGroup'] in ('', observed_service['ControlGroup']))
    not_running = dead and (collected or same_unit)
    state = ('unbound' if owned is None else 'absent' if current is None else
             'identity_replaced' if not same_identity(owned, current) else
             'zombie' if current['state'] == 'Z' else 'live')
    return {'confirmed': not_running and state in ('absent', 'identity_replaced', 'zombie'),
        'unit_load_state': unit['LoadState'], 'unit_active_state': unit['ActiveState'],
        'unit_sub_state': unit['SubState'], 'original_process_state': state,
        'unit_identity_verified_or_collected': bool(collected or same_unit),
        'systemd_run_exit_code': client_exit, 'unit_stop_or_kill_issued': False}


def first_line(process, timeout):
    deadline = time.monotonic() + timeout; value = b''
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while b'\n' not in value:
            remaining = deadline - time.monotonic()
            require(remaining > 0 and selector.select(remaining), 'probe_readback_timeout')
            chunk = os.read(process.stdout.fileno(), 16385 - len(value))
            require(bool(chunk), 'probe_closed_before_readback')
            value += chunk
            require(len(value) <= 16384, 'probe_readback_too_large')
    require(value.endswith(b'\n') and value.count(b'\n') == 1, 'unexpected_probe_output')
    return value


def save(directory, name, value):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(canonical(value) + b'\n')


def run_probe(out_dir):
    """Start exactly one fixed harmless unit. No retry or existing-unit control."""
    directory = Path(out_dir).absolute()
    require(not directory.exists() and not directory.is_symlink(), 'probe_output_already_exists')
    require(directory.parent.is_dir() and directory.parent.resolve() == directory.parent,
            'probe_output_parent_must_be_real_directory')
    directory.mkdir(mode=0o700)
    name = checked_name(unit_name()); started = time.monotonic(); uid = os.getuid()
    command = ['systemd-run', '--user', '--quiet', '--collect', '--wait', '--pipe',
        '--service-type=exec', '--unit=' + name, *['--property=' + p for p in PROPERTIES],
        str(Path(sys.executable).resolve()), '-I', '-S', '-B', '-c', PAYLOAD]
    intent = {'schema_version': 1, 'kind': VERSION, 'unit': name, 'uid': uid,
        'started_monotonic': started, 'properties': list(PROPERTIES),
        'command_sha256': sha(canonical(command)), 'payload_sha256': sha(PAYLOAD.encode()),
        'helper_sha256': sha(Path(__file__).read_bytes()), 'native_or_model_calls': 0}
    save(directory, 'INTENT.json', intent)
    process = None; client_identity = None; owned = None; verified = None; errors = []; cleanup = None
    observed_service = None; client_forced = False; streams_complete = False
    output = b''; stderr = b''; client_exit = None
    try:
        existing = show_unit(name)
        require(existing['LoadState'] == 'not-found', 'probe_unit_name_already_exists')
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd='/', start_new_session=True)
        client_identity = identity(process.pid)
        require(client_identity is not None and client_identity['uid'] == uid, 'probe_client_identity_unavailable')
        save(directory, 'START.json', {'unit': name, 'systemd_run_identity': client_identity})
        output = first_line(process, min(8, max(0, OUTER_SECONDS - (time.monotonic() - started))))
        worker = json.loads(output)
        unit = show_unit(name)
        current = identity(worker['pid'])
        kernel = kernel_readback(worker['cgroup'], uid, name)
        verified = validate_observation(name, worker, unit, current, kernel, uid=uid)
        owned = {key: worker[key] for key in ('pid', 'uid', 'start_ticks', 'boot_id')}
        observed_service = unit
        save(directory, 'OBSERVATION.json', {'unit': name, 'worker': worker, 'service': unit,
            'independent_process': current, 'verified_controls': verified})
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as exc:
        errors.append({'stage': 'readback', 'error_type': type(exc).__name__,
            'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None})
    finally:
        if process is not None:
            try:
                remaining = max(.1, OUTER_SECONDS - (time.monotonic() - started))
                extra, stderr = process.communicate(input=b'\n', timeout=remaining)
                streams_complete = True
                client_exit = process.returncode
                require(not extra.strip(), 'unexpected_additional_probe_output')
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append({'stage': 'client_cleanup', 'error_type': type(exc).__name__})
                # This is our directly spawned client, never the service or any
                # pre-existing process. A changed identity is never signaled.
                try:
                    if process.poll() is None and same_identity(client_identity, identity(process.pid)):
                        process.kill(); client_forced = True
                        try: process.wait(timeout=2)
                        except subprocess.TimeoutExpired: pass
                except (OSError, ValueError, subprocess.SubprocessError) as cleanup_exc:
                    errors.append({'stage': 'client_identity_cleanup', 'error_type': type(cleanup_exc).__name__})
                client_exit = process.poll()
        try:
            unit = show_unit(name)
            cleanup = cleanup_evidence(name, unit, owned, identity(owned['pid']) if owned else None,
                                       client_exit, observed_service)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            errors.append({'stage': 'unit_cleanup_observation', 'error_type': type(exc).__name__})
            cleanup = {'confirmed': False, 'unit_stop_or_kill_issued': False}
        save(directory, 'CLEANUP.json', {'unit': name, 'cleanup': cleanup,
            'elapsed_seconds': time.monotonic() - started, 'stdout_bytes': len(output),
            'stdout_sha256': sha(output), 'stderr_bytes': len(stderr), 'stderr_sha256': sha(stderr),
            'streams_complete': streams_complete, 'own_client_forced_termination': client_forced})
    passed = bool(verified and verified['verified'] and cleanup['confirmed'] and client_exit == 0 and not errors)
    result = {'schema_version': 1, 'kind': VERSION, 'status': 'verified' if passed else 'failed',
        'ok': passed, 'unit': name, 'controls': verified, 'cleanup': cleanup, 'errors': errors,
        'native_or_model_calls': 0, 'existing_workload_controls_changed': False,
        'scope': 'Own fixed harmless user-unit probe only; no native startup or latency guarantee.',
        'receipt_sha256': {p.name: sha(p.read_bytes()) for p in sorted(directory.glob('*.json'))}}
    save(directory, 'REPORT.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_probe(args.out)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__})); return 1
    print(json.dumps({'ok': result['ok'], 'status': result['status'],
        'cleanup_confirmed': result['cleanup']['confirmed'], 'native_or_model_calls': 0}))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
