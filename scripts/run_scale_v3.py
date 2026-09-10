"""Own one caller-launched resource scope around the whole v3 campaign.

The inner supervisor keeps its normal direct children. This module adds a
private pre-dispatch gate and independently observes the containing scope.
Scope success alone never substitutes for the native controller return code.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from scripts import hermes_startup_qualification as base

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'bigworld-scale-v3-'
require, canonical, sha, load = base.require, base.canonical, base.sha, base.load
same = base.same
SHOW_KEYS = ('Id', 'LoadState', 'ActiveState', 'SubState', 'ControlGroup',
             'InvocationID', 'RuntimeMaxUSec', 'TimeoutStopUSec', 'KillMode', 'Delegate')
BOOTSTRAP = r'''
import json,os,sys
from pathlib import Path
root,directory,campaign_hash=sys.argv[1:]
intent=json.loads((Path(directory)/'scope/INTENT.json').read_bytes())
assert intent['campaign_sha256']==campaign_hash
os.environ.clear();os.environ.update(intent['controller_environment'])
sys.path[:]=[root,*intent['controller_import_paths'],*sys.path]
from scripts.run_scale_v3 import _worker
_worker(Path(directory),campaign_hash)
'''


def limits():
    from scripts.scale_v3_contract import SCOPE_LIMITS
    return {**SCOPE_LIMITS, 'runtime_seconds': SCOPE_LIMITS['runtime_max_seconds'],
        'stop_seconds': SCOPE_LIMITS['timeout_stop_seconds'],
        'kernel_limits': {'memory.max': str(SCOPE_LIMITS['memory_max_bytes']),
            'memory.swap.max': str(SCOPE_LIMITS['memory_swap_max_bytes']),
            'pids.max': str(SCOPE_LIMITS['tasks_max']),
            'cpu.max': f"{SCOPE_LIMITS['cpu_max_usec']} {SCOPE_LIMITS['cpu_quota_period_usec']}"}}


def identity(pid):
    value = base.identity(pid)
    if value is not None:
        value['security_context'] = (Path('/proc') / str(pid) / 'attr/current').read_text().strip()
    return value


def private_root(directory):
    path = Path(directory).absolute()
    require(path.resolve() == path and path.is_relative_to(ROOT / 'lifespan/artifacts'),
            'scope_private_directory_required')
    return path


def save(path, value, *, replace=False):
    path = Path(path)
    require(path.resolve().is_relative_to(ROOT / 'lifespan/artifacts') and not path.is_symlink(),
            'scope_receipt_path_escape')
    if not replace:
        base.save(path, value)
    else:
        temporary = path.with_suffix('.tmp')
        base.save(temporary, value)
        temporary.replace(path)


def checked_unit(name):
    require(type(name) is str and re.fullmatch(PREFIX + r'[0-9a-f]{32}\.scope', name),
            'foreign_campaign_scope')
    return name


def show(unit, timeout=2):
    checked_unit(unit)
    proc = subprocess.run([base.binary('systemctl'), '--user', 'show', unit,
        *['--property=' + key for key in SHOW_KEYS]], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
    require(len(proc.stdout) < 32768, 'scope_observation_too_large')
    rows = [line.split('=', 1) for line in proc.stdout.decode().splitlines()]
    require(all(len(row) == 2 for row in rows), 'scope_observation_invalid')
    result = dict(rows)
    require(len(rows) == len(result) and set(result) == set(SHOW_KEYS)
            and result['Id'] == unit and (proc.returncode == 0 or result['LoadState'] == 'not-found'),
            'scope_observation_invalid')
    return result


def group_path(unit, group, uid):
    checked_unit(unit)
    require(type(group) is str and group.startswith(f'/user.slice/user-{uid}.slice/user@{uid}.service/')
            and '..' not in Path(group).parts and Path(group).name == unit, 'scope_cgroup_mismatch')
    root = Path('/sys/fs/cgroup')
    path = root / group.lstrip('/')
    require(path.resolve().is_relative_to(root), 'scope_cgroup_escape')
    return path


def group_members(unit, binding):
    root = group_path(unit, binding['cgroup'], binding['controller_identity']['uid'])
    if not root.exists():
        return []
    paths = [root / 'cgroup.procs', *root.glob('**/cgroup.procs')]
    require(len(paths) <= 512, 'scope_subgroup_limit')
    members = set()
    for path in paths:
        require(not path.is_symlink() and path.resolve().is_relative_to(root), 'scope_cgroup_escape')
        try:
            members.update(int(value) for value in path.read_text().split())
        except FileNotFoundError:
            continue
    require(len(members) <= 512 and all(pid > 0 for pid in members), 'scope_process_limit')
    return sorted(members)


def kernel(unit, group, uid):
    root = group_path(unit, group, uid)
    return {key: (root / key).read_text().strip() for key in limits()['kernel_limits']}


def resource_observation(unit, binding):
    root = group_path(unit, binding['cgroup'], binding['controller_identity']['uid'])
    files = ('memory.events', 'memory.peak', 'pids.events', 'cpu.stat', 'io.stat')
    return {name: (root / name).read_text().strip() if (root / name).exists() else None
            for name in files}


def properties():
    cap = limits()
    return ['MemoryMax=12G', 'MemorySwapMax=0', 'TasksMax=512', 'CPUQuota=400%',
            'CPUQuotaPeriodSec=100ms', f"RuntimeMaxSec={cap['runtime_seconds']}",
            f"TimeoutStopSec={cap['stop_seconds']}", 'KillMode=control-group', 'Delegate=no']


def native_argv(directory, campaign_hash, python):
    return [python, '-I', '-S', '-u', '-c', BOOTSTRAP, str(ROOT), str(directory), campaign_hash]


def launch_argv(directory, intent):
    return [base.binary('systemd-run'), '--user', '--scope', '--quiet', '--unit=' + intent['unit'],
            *['--property=' + value for value in properties()],
            *native_argv(directory, intent['campaign_sha256'], intent['python'])]


def seconds(value):
    """Parse systemd's duration display without accepting absent/infinite limits."""
    require(type(value) is str and value, 'scope_duration_invalid')
    parts = re.findall(r'([0-9]+(?:\.[0-9]+)?)(h|min|s|ms|us|d)', value)
    require(parts and ''.join(a + b for a, b in parts) == value.replace(' ', ''), 'scope_duration_invalid')
    factors = {'us': .000001, 'ms': .001, 's': 1, 'min': 60, 'h': 3600, 'd': 86400}
    return sum(float(number) * factors[unit] for number, unit in parts)


def validate_binding(directory, intent, launch, hello, observed, current, values):
    outer = intent['outer_identity']
    require(same(launch, hello) and same(hello, current), 'scope_exec_identity_changed')
    require(current['ppid'] == outer['pid'] and current['uid'] == outer['uid']
            and current['boot_id'] == outer['boot_id'] and current['start_ticks'] >= outer['start_ticks']
            and current['security_context'] == outer['security_context']
            and current['user_namespace'] == outer['user_namespace']
            and current['net_namespace'] == outer['net_namespace']
            and current['cwd'] == str(ROOT) and current['state'] not in ('Z', 'X')
            and current['argv_sha256'] == sha(canonical(native_argv(directory, intent['campaign_sha256'], intent['python']))),
            'scope_controller_context_changed')
    require(observed['Id'] == intent['unit'] and observed['LoadState'] == 'loaded'
            and observed['ActiveState'] == 'active' and observed['SubState'] == 'running'
            and observed['ControlGroup'] == current['cgroup']
            and re.fullmatch('[0-9a-f]{32}', observed['InvocationID']), 'scope_live_identity_invalid')
    group_path(intent['unit'], current['cgroup'], current['uid'])
    require(seconds(observed['RuntimeMaxUSec']) == limits()['runtime_seconds']
            and seconds(observed['TimeoutStopUSec']) == limits()['stop_seconds']
            and observed['KillMode'] == 'control-group' and observed['Delegate'] == 'no'
            and values == limits()['kernel_limits'], 'scope_controls_not_effective')
    return {'controller_identity': current, 'invocation_id': observed['InvocationID'],
            'cgroup': current['cgroup'], 'kernel_limits': values, 'unit': intent['unit']}


def verify_sources(campaign):
    sources = {**campaign['source_sha256'], **campaign['registration_tools_sha256']}
    for name, expected in sources.items():
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts
                and sha((ROOT / path).read_bytes()) == expected, 'scope_execution_source_changed')
    require('scripts/run_scale_v3.py' in sources, 'scope_supervisor_not_registered')
    return sources


def validate_worker_gate(directory, *, campaign_sha256, scope_gate):
    """Must run before the inner supervisor can read credentials or dispatch."""
    directory = private_root(directory)
    campaign, actual = load(directory / 'campaign.json')
    require(actual == campaign_sha256, 'scope_campaign_hash_changed')
    intent, _ = load(directory / 'scope/INTENT.json')
    gate, _ = load(directory / 'scope/GATE.json')
    hello, _ = load(directory / 'scope/HELLO.json')
    launch, _ = load(directory / 'scope/LAUNCH.json')
    require(scope_gate == gate and intent['campaign_sha256'] == campaign_sha256
            and gate['campaign_sha256'] == campaign_sha256, 'scope_gate_hash_mismatch')
    current = identity(os.getpid())
    unit = show(intent['unit'])
    rebuilt = validate_binding(directory, intent, launch['identity'], hello['identity'], unit, current,
        kernel(intent['unit'], current['cgroup'], current['uid']))
    require(same(rebuilt['controller_identity'], gate['binding']['controller_identity'])
            and rebuilt['invocation_id'] == gate['binding']['invocation_id'], 'scope_gate_identity_changed')
    require(time.monotonic() < gate['execution_deadline'] and verify_sources(campaign) == intent['source_sha256'],
            'scope_gate_expired_or_source_changed')
    return {**gate, 'controller_identity': current,
            'scope_gate_sha256': load(directory / 'scope/GATE.json')[1]}


def verify_prerequisites(campaign, paths):
    from scripts.scale_v3_prerequisites import verify_prerequisites as verify
    return verify(campaign, paths)


def wait_file(path, deadline):
    while not path.exists():
        require(time.monotonic() < deadline, 'scope_gate_deadline')
        time.sleep(.1)
    require(time.monotonic() < deadline, 'scope_gate_deadline')
    return load(path)[0]


def _worker(directory, campaign_hash):
    intent, _ = load(directory / 'scope/INTENT.json')
    save(directory / 'scope/HELLO.json', {'identity': identity(os.getpid()),
        'campaign_sha256': campaign_hash, 'observed_monotonic': time.monotonic()})
    gate = wait_file(directory / 'scope/GATE.json', intent['startup_deadline'])
    validate_worker_gate(directory, campaign_sha256=campaign_hash, scope_gate=gate)
    try:
        from scripts.run_scale_v3_inner import execute as inner_execute
        outcome = inner_execute(directory, campaign_sha256=campaign_hash,
            prerequisite_paths=intent['prerequisite_paths'], scope_gate=gate)
        completed = outcome.get('inner_completed') is True
        result = {'returned_normally': True, 'inner_completed': completed,
                  'exit_code': 0 if completed else 1, 'error_type': None}
    except BaseException as exc:
        result = {'returned_normally': False, 'inner_completed': False,
                  'exit_code': 1, 'error_type': type(exc).__name__}
    result.update(campaign_sha256=campaign_hash, controller_identity=identity(os.getpid()),
                  finished_monotonic=time.monotonic())
    save(directory / 'scope/INNER_RESULT.json', result)
    release = wait_file(directory / 'scope/RELEASE.json',
                        min(result['finished_monotonic'], intent['execution_deadline']) + limits()['cleanup_seconds'])
    require(release['campaign_sha256'] == campaign_hash
            and same(release['controller_identity'], identity(os.getpid())), 'scope_release_mismatch')
    save(directory / 'scope/CONTROLLER_EXIT.json', {'campaign_sha256': campaign_hash,
        'identity': identity(os.getpid()), 'release_sha256': load(directory / 'scope/RELEASE.json')[1],
        'exit_code': result['exit_code'], 'observed_monotonic': time.monotonic()})
    raise SystemExit(result['exit_code'])


def _signal_controller(binding, sig):
    from scripts.scale_v2_process import _signal_owned
    name = signal.Signals(sig).name.removeprefix('SIG')
    return _signal_owned(binding['controller_identity'], name)


def cleanup_binding(intent, launched):
    """A direct child's scope can be owned for cleanup before its HELLO.

    This narrower check grants no resource, startup or completed-scope pass.
    """
    require(launched is not None, 'scope_cleanup_launch_missing')
    current = identity(launched['pid'])
    require(same(current, launched) and current['ppid'] == intent['outer_identity']['pid']
            and current['uid'] == intent['outer_identity']['uid']
            and current['boot_id'] == intent['outer_identity']['boot_id'], 'scope_cleanup_child_unbound')
    unit = show(intent['unit'])
    require(unit['LoadState'] == 'loaded' and unit['ControlGroup'] == current['cgroup']
            and re.fullmatch('[0-9a-f]{32}', unit['InvocationID']), 'scope_cleanup_unit_unbound')
    group_path(intent['unit'], current['cgroup'], current['uid'])
    return {'controller_identity': current, 'cgroup': current['cgroup'],
            'invocation_id': unit['InvocationID'], 'unit': intent['unit'], 'cleanup_only': True}


def checked_inner_result(scope, intent, observed):
    result, _ = load(scope / 'INNER_RESULT.json')
    value = result['finished_monotonic']
    require(base.finite(value) and intent['started_monotonic'] <= value <= observed,
            'scope_inner_result_clock_invalid')
    return result


def _stop_scope(intent, binding, deadline):
    unit = show(intent['unit'])
    if unit['LoadState'] == 'not-found':
        return False
    require(binding is not None and unit['InvocationID'] == binding['invocation_id']
            and unit['ControlGroup'] in ('', binding['cgroup']), 'scope_stop_unbound')
    require(time.monotonic() < deadline, 'scope_stop_deadline')
    subprocess.run([base.binary('systemctl'), '--user', 'stop', intent['unit']],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=min(7, max(.01, deadline - time.monotonic())), check=True)
    return True


def execute(out, *, campaign_sha256, prerequisite_paths):
    directory = private_root(out)
    campaign, actual = load(directory / 'campaign.json')
    require(actual == campaign_sha256, 'scope_campaign_hash_changed')
    sources = verify_sources(campaign)
    base.committed(sources, subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    # The historical capability audit is separate from the exact installed
    # binaries/packages that passed the fresh startup qualification.
    prereqs = verify_prerequisites(campaign, prerequisite_paths)
    from scripts import hermes_startup_scope_qualification_v3 as qualification
    qualification_dir = Path(prerequisite_paths['startup']['directory'])
    qualification_hash = load(qualification_dir / 'manifest.json')[1]
    qualified = qualification.validate_manifest(qualification_dir, qualification_hash, current=True)
    cap = limits()
    scope = directory / 'scope'
    require(not scope.exists() and not (directory / 'EXECUTION.json').exists(), 'scope_execution_is_one_shot')
    scope.mkdir(mode=0o700)
    started = time.monotonic()
    intent = {'schema_version': 1, 'campaign_sha256': campaign_sha256, 'source_sha256': sources,
        'unit': PREFIX + uuid.uuid4().hex + '.scope', 'outer_identity': identity(os.getpid()),
        'python': base.interpreter(), 'controller_environment': base.controller_environment(),
        'controller_import_paths': base.controller_import_paths(), 'limits': cap,
        'qualification_manifest_sha256': qualification_hash,
        'qualified_dependencies_sha256': sha(canonical(qualified['dependencies'])),
        'qualified_boot_id': qualified['boot_id'], 'prerequisite_checks_sha256': sha(canonical(prereqs)),
        'prerequisite_paths': prerequisite_paths, 'started_monotonic': started,
        'startup_deadline': started + cap['controller_startup_seconds'],
        'execution_deadline': started + cap['execution_seconds']}
    intent['command_sha256'] = sha(canonical(launch_argv(directory, intent)))
    save(scope / 'INTENT.json', intent)
    stop = threading.Event()
    process = binding = result = launched = None
    released = False
    errors = []
    cleanup_start = cleanup_deadline = None
    with base.interrupt_scope(stop), (scope / 'controller.log').open('x') as log:
        os.chmod(scope / 'controller.log', 0o600)
        try:
            require(show(intent['unit'])['LoadState'] == 'not-found', 'scope_name_already_exists')
            process = subprocess.Popen(launch_argv(directory, intent), cwd=ROOT,
                env=intent['controller_environment'], stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
            launched = identity(process.pid)
            require(launched is not None, 'scope_launch_identity_missing')
            save(scope / 'LAUNCH.json', {'identity': launched, 'observed_monotonic': time.monotonic()})
            while not (scope / 'HELLO.json').exists():
                require(process.poll() is None and not stop.is_set()
                        and time.monotonic() < intent['startup_deadline'], 'scope_controller_start_failed')
                time.sleep(.1)
            hello, _ = load(scope / 'HELLO.json')
            unit, current = show(intent['unit']), identity(process.pid)
            binding = validate_binding(directory, intent, launched, hello['identity'], unit, current,
                kernel(intent['unit'], current['cgroup'], current['uid']))
            gate = {'campaign_sha256': campaign_sha256, 'binding': binding, 'unit_observation': unit,
                    'execution_started_monotonic': intent['started_monotonic'],
                    'execution_deadline': intent['execution_deadline'], 'observed_monotonic': time.monotonic()}
            require(gate['observed_monotonic'] < intent['startup_deadline'], 'scope_controller_gate_late')
            save(scope / 'GATE.json', gate)
            while process.poll() is None:
                if (scope / 'INNER_RESULT.json').exists():
                    result = checked_inner_result(scope, intent, time.monotonic())
                    break
                if stop.is_set() or time.monotonic() >= intent['execution_deadline']:
                    _signal_controller(binding, signal.SIGINT)
                    break
                unit = show(intent['unit'])
                require(unit['InvocationID'] == binding['invocation_id'], 'scope_invocation_changed')
                members = group_members(intent['unit'], binding)
                require(process.pid in members, 'scope_controller_missing')
                current_kernel = kernel(intent['unit'], binding['cgroup'], current['uid'])
                require(current_kernel == cap['kernel_limits'], 'scope_controls_changed')
                save(scope / 'OBSERVATION.json', {'observed_monotonic': time.monotonic(),
                    'member_count': len(members), 'controller_present': True,
                    'invocation_id': unit['InvocationID'],
                    'kernel': current_kernel, 'resources': resource_observation(intent['unit'], binding)}, replace=True)
                stop.wait(.5)
            cleanup_start = min(time.monotonic(), intent['execution_deadline'])
            if result is not None:
                cleanup_start = min(result['finished_monotonic'], intent['execution_deadline'])
            cleanup_deadline = cleanup_start + cap['cleanup_seconds']
            while process.poll() is None and time.monotonic() < cleanup_deadline - 10:
                if result is None and (scope / 'INNER_RESULT.json').exists():
                    result = checked_inner_result(scope, intent, time.monotonic())
                if result is not None and group_members(intent['unit'], binding) == [process.pid]:
                    live = show(intent['unit'])
                    current = identity(process.pid)
                    require(same(current, binding['controller_identity']) and
                            live['InvocationID'] == binding['invocation_id'], 'scope_drain_identity_changed')
                    final_kernel = kernel(intent['unit'], binding['cgroup'], current['uid'])
                    require(final_kernel == cap['kernel_limits'], 'scope_controls_changed')
                    final_dependencies = sha(canonical(qualification.dependencies()))
                    require(final_dependencies == intent['qualified_dependencies_sha256'],
                            'scope_qualified_dependencies_changed')
                    save(scope / 'DRAINED.json', {'controller_identity': current, 'unit_observation': live,
                        'members': [process.pid], 'kernel': final_kernel,
                        'qualified_dependencies_sha256': final_dependencies,
                        'resources': resource_observation(intent['unit'], binding),
                        'observed_monotonic': time.monotonic()})
                    save(scope / 'RELEASE.json', {'campaign_sha256': campaign_sha256,
                        'controller_identity': current, 'observed_monotonic': time.monotonic()})
                    released = True
                    break
                time.sleep(.1)
        except Exception as exc:
            errors.append({'error_type': type(exc).__name__,
                'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None})
        finally:
            cleanup_start = cleanup_start or min(time.monotonic(), intent['execution_deadline'])
            cleanup_deadline = cleanup_deadline or cleanup_start + cap['cleanup_seconds']
            forced = False
            owned = binding
            if owned is None and launched is not None:
                try:
                    owned = cleanup_binding(intent, launched)
                    save(scope / 'CLEANUP_BINDING.json', owned)
                except Exception:
                    # A failed resource/HELLO gate must not leave a known child
                    # running for the multi-day campaign RuntimeMax backstop.
                    from scripts.scale_v2_process import _signal_owned
                    try:
                        _signal_owned(launched, 'TERM')
                    except Exception as exc:
                        errors.append({'error_type': type(exc).__name__, 'code': 'scope_child_stop_unconfirmed'})
            if not released:
                try:
                    forced = _stop_scope(intent, owned, cleanup_deadline)
                except Exception as exc:
                    errors.append({'error_type': type(exc).__name__, 'code': 'scope_stop_unconfirmed'})
            wait_code = None
            if process is not None:
                try:
                    wait_code = process.wait(timeout=max(.01, min(10, cleanup_deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    errors.append({'error_type': 'TimeoutExpired', 'code': 'scope_wait_unconfirmed'})
                    try:
                        forced = _stop_scope(intent, owned, cleanup_deadline) or forced
                    except Exception as exc:
                        errors.append({'error_type': type(exc).__name__, 'code': 'scope_timeout_stop_unconfirmed'})
                    if launched is not None:
                        from scripts.scale_v2_process import _signal_owned
                        try:
                            _signal_owned(launched, 'KILL')
                        except Exception as exc:
                            errors.append({'error_type': type(exc).__name__, 'code': 'scope_timeout_kill_unconfirmed'})
                    try:
                        wait_code = process.wait(timeout=max(.01, min(5, cleanup_deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        pass
            final_unit = remaining = controller_state = None
            try:
                final_unit = show(intent['unit'])
                remaining = group_members(intent['unit'], binding) if binding else None
                now = identity(process.pid) if process else None
                controller_state = ('absent' if now is None else 'replaced' if binding and not
                    same(now, binding['controller_identity']) else 'zombie' if now['state'] == 'Z' else 'alive')
            except Exception as exc:
                errors.append({'error_type': type(exc).__name__, 'code': 'scope_terminal_unconfirmed'})
            save(scope / 'TERMINAL.json', {'campaign_sha256': campaign_sha256,
                'started_monotonic': cleanup_start, 'cleanup_deadline': cleanup_deadline,
                'ended_monotonic': time.monotonic(), 'native_wait_exit_code': wait_code,
                'released': released, 'forced_stop': forced, 'errors': errors,
                'unit_final': final_unit, 'members_remaining': remaining, 'controller_state': controller_state})
    from scripts.audit_scale_v3 import audit_campaign_v3
    audit = audit_campaign_v3(directory, campaign_sha256=campaign_sha256, strict=True)
    save(directory / 'AUDIT.json', audit)
    return audit


def audit_scope(directory, *, campaign_sha256, strict=True):
    """Read-only reconstruction; a prepared/running/failed scope cannot pass."""
    result = {'ok': False, 'status': 'incomplete', 'scope_passed': False,
              'scope_complete': False, 'inner_completed': False,
              'campaign_sha256': campaign_sha256, 'errors': []}
    try:
        directory = private_root(directory)
        campaign, actual = load(directory / 'campaign.json')
        require(actual == campaign_sha256, 'scope_campaign_hash_changed')
        scope = directory / 'scope'
        required = ('INTENT.json', 'LAUNCH.json', 'HELLO.json', 'GATE.json', 'INNER_RESULT.json',
                    'DRAINED.json', 'RELEASE.json', 'CONTROLLER_EXIT.json', 'TERMINAL.json')
        if not all((scope / name).is_file() for name in required):
            return result
        data = {name: load(scope / name)[0] for name in required}
        intent, launch, hello, gate = [data[name] for name in required[:4]]
        inner, drained, release, exited, terminal = [data[name] for name in required[4:]]
        require(intent['source_sha256'] == verify_sources(campaign) and intent['limits'] == limits()
                and intent['campaign_sha256'] == campaign_sha256
                and intent['command_sha256'] == sha(canonical(launch_argv(directory, intent))),
                'scope_registered_execution_changed')
        qualified, qualification_hash = load(Path(intent['prerequisite_paths']['startup']['directory']) / 'manifest.json')
        require(qualification_hash == intent['qualification_manifest_sha256']
                and intent['qualified_dependencies_sha256'] == sha(canonical(qualified['dependencies']))
                and intent['qualified_boot_id'] == qualified['boot_id'] == intent['outer_identity']['boot_id']
                and qualified['caller_security_context'] == intent['outer_identity']['security_context'],
                'scope_qualified_execution_context_changed')
        rebuilt = validate_binding(directory, intent, launch['identity'], hello['identity'],
            gate['unit_observation'], gate['binding']['controller_identity'], gate['binding']['kernel_limits'])
        require(rebuilt == gate['binding'], 'scope_binding_receipt_changed')
        ident = rebuilt['controller_identity']
        require(all(row['campaign_sha256'] == campaign_sha256 for row in
                    (hello, gate, inner, release, exited, terminal)), 'scope_receipt_campaign_mismatch')
        require(all(same(row[key], ident) for row, key in ((inner, 'controller_identity'),
            (drained, 'controller_identity'), (release, 'controller_identity'), (exited, 'identity'))),
            'scope_receipt_controller_mismatch')
        require(intent['startup_deadline'] == intent['started_monotonic'] + limits()['controller_startup_seconds']
            and intent['execution_deadline'] == intent['started_monotonic'] + limits()['execution_seconds']
            and gate['execution_deadline'] == intent['execution_deadline']
            and gate['execution_started_monotonic'] == intent['started_monotonic'], 'scope_deadline_changed')
        clocks = [intent['started_monotonic'], gate['observed_monotonic'], inner['finished_monotonic'], drained['observed_monotonic'],
                  release['observed_monotonic'], exited['observed_monotonic'], terminal['ended_monotonic']]
        require(all(base.finite(value) for value in clocks) and clocks == sorted(clocks)
                and all(base.finite(row['observed_monotonic']) and intent['started_monotonic'] <= row['observed_monotonic']
                        <= gate['observed_monotonic'] for row in (launch, hello))
                and gate['observed_monotonic'] <= intent['startup_deadline']
                and inner['finished_monotonic'] <= intent['execution_deadline']
                and terminal['started_monotonic'] == inner['finished_monotonic']
                and terminal['cleanup_deadline'] == inner['finished_monotonic'] + limits()['cleanup_seconds']
                and terminal['ended_monotonic'] <= terminal['cleanup_deadline'], 'scope_measured_deadline_failed')
        require(drained['members'] == [ident['pid']] and drained['unit_observation']['Id'] == intent['unit']
                and drained['unit_observation']['InvocationID'] == rebuilt['invocation_id']
                and drained['unit_observation']['ControlGroup'] == rebuilt['cgroup']
                and drained['kernel'] == limits()['kernel_limits']
                and drained['qualified_dependencies_sha256'] == intent['qualified_dependencies_sha256'],
                'scope_drain_not_verified')
        if (scope / 'OBSERVATION.json').exists():
            observation, _ = load(scope / 'OBSERVATION.json')
            require(observation['kernel'] == limits()['kernel_limits']
                    and observation['invocation_id'] == rebuilt['invocation_id']
                    and observation['controller_present'] is True
                    and type(observation['member_count']) is int and 1 <= observation['member_count'] <= 512
                    and gate['observed_monotonic'] <= observation['observed_monotonic']
                    <= drained['observed_monotonic'], 'scope_retained_observation_invalid')
            required += ('OBSERVATION.json',)
        require(exited['release_sha256'] == load(scope / 'RELEASE.json')[1]
                and terminal['released'] is True and terminal['forced_stop'] is False and not terminal['errors']
                and terminal['members_remaining'] == [] and terminal['controller_state'] in ('absent', 'replaced', 'zombie'),
                'scope_cleanup_not_verified')
        final = terminal['unit_final']
        require(final['Id'] == intent['unit'] and (final['LoadState'] == 'not-found'
                and not final['InvocationID'] and not final['ControlGroup']
                and final['ActiveState'] == 'inactive' and final['SubState'] == 'dead'
                or final['LoadState'] == 'loaded'
                and final['ActiveState'] == 'inactive' and final['InvocationID'] == rebuilt['invocation_id']),
                'scope_not_terminal')
        require(inner['returned_normally'] is True and inner['inner_completed'] is True
                and inner['error_type'] is None and type(inner['exit_code']) is int and inner['exit_code'] == 0
                and type(terminal['native_wait_exit_code']) is int and terminal['native_wait_exit_code'] == 0
                and type(exited['exit_code']) is int and exited['exit_code'] == 0, 'scope_inner_not_successful')
        result.update(ok=True, status='completed', scope_passed=True, scope_complete=True, inner_completed=True,
            inner_supervisor_identity=ident, native_wait_exit_code=terminal['native_wait_exit_code'],
            inner_result_exit_code=inner['exit_code'],
            raw_evidence_sha256={name: load(scope / name)[1] for name in required})
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result.update(status='invalid', errors=[{'error_type': type(exc).__name__,
            'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None}])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--campaign-sha256', required=True)
    parser.add_argument('--prerequisite-paths', type=Path)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    if args.audit:
        result = audit_scope(args.out, campaign_sha256=args.campaign_sha256)
    else:
        require(args.prerequisite_paths is not None, 'scope_prerequisite_paths_required')
        result = execute(args.out, campaign_sha256=args.campaign_sha256,
                         prerequisite_paths=load(args.prerequisite_paths)[0])
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
