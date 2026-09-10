"""Native startup-only child for a future, separately registered qualification.

This module does not launch a service or a campaign. Its caller must own the
resource unit, independently verify its identities, and enforce the outer
deadline and cleanup. The native body refuses the host network namespace and
never sends a work request. No real credential is accepted by this interface.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import time

VERSION = 'hermes-startup-probe-v1'
ROOT = Path(__file__).resolve().parents[1]
UNIT_PREFIX = 'bigworld-startup-qualification-'
KERNEL_LIMITS = {'memory.max': '4294967296', 'memory.swap.max': '0',
                 'pids.max': '128', 'cpu.max': '200000 100000'}
EXECUTION = {'mode': 'evaluation', 'max_iterations': 16, 'max_tokens': 4096,
             'max_total_tokens': 250000, 'hermes_transport': 'nonstreaming',
             'hermes_startup_observability': True}
CREDENTIALS = {'model': 'gpt-5.6-luna', 'base_url': 'http://127.0.0.1:9/v1',
               'api_key': 'startup-probe-no-provider-credential'}
STARTUP_SECONDS = 150
CLEANUP_SECONDS = 30


def require(value, code):
    if not value:
        raise ValueError(code)


def observe_boundary():
    """Read current namespace/cgroup metadata; do not connect a socket."""
    interfaces = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
        for _, name in socket.if_nameindex():
            flags = fcntl.ioctl(handle.fileno(), 0x8913, struct.pack('256s', name.encode()))
            interfaces.append({'name': name, 'up': bool(struct.unpack_from('H', flags, 16)[0] & 1)})
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    require(len(rows) == 1 and rows[0].startswith('0::/'), 'unified_cgroup_required')
    group = rows[0][3:]
    base = Path('/sys/fs/cgroup') / group.lstrip('/')
    return {'uid': os.getuid(), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'net_namespace': os.readlink('/proc/self/ns/net'),
            'user_namespace': os.readlink('/proc/self/ns/user'),
            'interfaces': sorted(interfaces, key=lambda item: item['name']),
            'cgroup': group, 'invocation_id': os.environ.get('INVOCATION_ID'),
            'kernel': {name: (base / name).read_text().strip() for name in KERNEL_LIMITS}}


def verify_boundary(expected, current):
    """Pure guard. A parent must independently establish these expected values."""
    require(type(expected) is dict and set(expected) ==
            {'uid', 'boot_id', 'host_net_namespace', 'host_user_namespace', 'unit', 'invocation_id'},
            'invalid_expected_boundary')
    require(type(expected['uid']) is int and expected['uid'] > 0, 'unprivileged_uid_required')
    require(re.fullmatch(UNIT_PREFIX + r'[0-9a-f]{32}\.service', expected['unit']) is not None,
            'invalid_qualification_unit')
    require(re.fullmatch('[0-9a-f]{32}', expected['invocation_id']) is not None,
            'invalid_invocation_identity')
    for key in ('host_net_namespace', 'host_user_namespace'):
        kind = 'net' if key == 'host_net_namespace' else 'user'
        require(re.fullmatch(kind + r':\[[0-9]+\]', expected[key]) is not None,
                'invalid_host_namespace')
        require(type(current[kind + '_namespace']) is str
                and re.fullmatch(kind + r':\[[0-9]+\]', current[kind + '_namespace']) is not None,
                'invalid_current_namespace')
    require(current['uid'] == expected['uid'] and current['boot_id'] == expected['boot_id'],
            'uid_or_boot_changed')
    require(current['net_namespace'] != expected['host_net_namespace']
            and current['user_namespace'] != expected['host_user_namespace'],
            'separate_user_and_network_namespaces_required')
    require(current['interfaces'] == [{'name': 'lo', 'up': False}], 'network_interface_not_isolated')
    expected_group = '/user.slice/user-{0}.slice/user@{0}.service/'.format(expected['uid'])
    group = current['cgroup']
    require(type(group) is str and group.startswith(expected_group)
            and '..' not in Path(group).parts and Path(group).name == expected['unit']
            and current['invocation_id'] == expected['invocation_id'], 'qualification_unit_mismatch')
    require(current['kernel'] == KERNEL_LIMITS, 'qualification_kernel_limits_mismatch')
    return {'verified': True, 'provider_network': 'separate_namespace_disabled_loopback_only',
            'kernel': dict(KERNEL_LIMITS), 'io_isolation_qualified': False}


def save(directory, name, value):
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def native_startup(out, expected, *, computer_factory=None, boundary_reader=observe_boundary,
                   startup_deadline=None, before_close=None):
    """One fresh start and close, never work; no retry or provider parameters.

    Tests may supply a fake factory. The real path is for the future registered
    unit supervisor only, not a stand-alone benchmark execution command.
    Returned close is not independently certified descendant/alias cleanup.
    An optional supervisor callback may hold READY long enough to capture live
    identities; its wait and phase writes consume the same cleanup allowance.
    """
    entered = time.monotonic()
    deadline = entered + STARTUP_SECONDS if startup_deadline is None else startup_deadline
    require(type(deadline) in (int, float) and math.isfinite(deadline)
            and entered < deadline <= entered + STARTUP_SECONDS, 'invalid_startup_deadline')
    before = boundary_reader()
    boundary = verify_boundary(expected, before)
    directory = Path(out).absolute()
    require(directory.parent.resolve() == directory.parent and directory.parent.is_dir()
            and not directory.exists() and not directory.is_symlink(), 'fresh_real_output_required')
    directory.mkdir(mode=0o700)
    save(directory, 'BOUNDARY_BEFORE.json', {'expected': expected, 'observed': before, 'verification': boundary})
    from lifespan.evaluation.hermes_transport import contract
    from lifespan.evaluation.protocol import SEED_SKILL
    from lifespan.evaluation.runtime import install_skill
    from lifespan.startup_observability import error_class
    if computer_factory is None:
        from lifespan.computers import Computer
        computer_factory = Computer
    computer = computer_factory(directory / 'computers', 'startup-qualification',
                                backend='bubblewrap', execution=dict(EXECUTION))
    skill = install_skill(computer.profile, SEED_SKILL)
    save(directory, 'STARTUP_INTENT.json', {'kind': VERSION, 'execution': EXECUTION,
         'startup_seconds': STARTUP_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS,
         'entered_monotonic': entered, 'startup_deadline': deadline,
         'skill': skill, 'work_requests_sent': 0,
         'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    ready = None
    error = None
    close_error = None
    outcome_error = None
    pre_close_error = None
    close_elapsed = None
    started = entered
    try:
        require(not any((computer.profile / name).exists() or (computer.profile / name).is_symlink()
                        for name in ('.env', '.op.env')), 'profile_environment_file_present')
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'startup_deadline_exhausted_before_launch')
        ready = computer.start(dict(CREDENTIALS), timeout=min(STARTUP_SECONDS, remaining))
        require(ready.get('kind') == 'ready' and ready.get('backend') == 'bubblewrap',
                'invalid_native_ready')
        require(ready.get('evaluation_transport') == contract('nonstreaming'),
                'native_transport_mismatch')
        require(not set(ready.get('tool_names', [])) & {'memory', 'skill_manage'},
                'native_learning_tools_exposed')
        require(time.monotonic() <= deadline, 'late_startup_return')
    except Exception as exc:
        error = error_class(exc)
    finally:
        close_started = time.monotonic()
        if close_started > deadline and error is None:
            error = 'TimeoutError'
        close_deadline = min(close_started + CLEANUP_SECONDS, deadline + CLEANUP_SECONDS)
        try:
            save(directory, 'STARTUP_FINISHED.json', {
                'entered_monotonic': entered, 'startup_deadline': deadline,
                'finished_monotonic': close_started,
                'startup_elapsed_seconds': close_started - entered,
                'ready_observed': ready is not None and error is None, 'error_type': error})
            # Writing these receipts consumes cleanup time. A stalled write or
            # Computer.close still needs the independent unit deadline.
            save(directory, 'CLOSE_STARTED.json', {
                'started_monotonic': close_started, 'cleanup_deadline': close_deadline})
        except OSError as exc:
            outcome_error = error_class(exc)
        if before_close is not None:
            try:
                before_close(directory, ready, close_deadline)
            except Exception as exc:
                pre_close_error = error_class(exc)
        try:
            computer.close()
        except Exception as exc:
            close_error = error_class(exc)
        close_finished = time.monotonic()
        close_elapsed = close_finished - close_started
    after = boundary_reader()
    after_valid = verify_boundary(expected, after)
    save(directory, 'BOUNDARY_AFTER.json', {'observed': after, 'verification': after_valid})
    result = {'schema_version': 1, 'kind': VERSION,
              'ready_observed': ready is not None and error is None,
              'error_type': error, 'close_error_type': close_error,
              'outcome_receipt_error_type': outcome_error,
              'pre_close_error_type': pre_close_error,
              'entered_monotonic': entered, 'startup_deadline': deadline,
              'startup_finished_monotonic': close_started,
              'startup_elapsed_seconds': close_started - entered,
              'cleanup_deadline': close_deadline, 'close_finished_monotonic': close_finished,
              'elapsed_seconds': time.monotonic() - started,
              'close_elapsed_seconds': close_elapsed,
              'close_returned_within_allowance': close_error is None and close_finished <= close_deadline,
              'work_requests_sent': 0, 'provider_credentials_supplied': False,
              'boundary_verified_before_and_after': True,
              'independent_cleanup_confirmed': False,
              'complete_qualification': False,
              'scope': 'Native startup-only child; requires independent registered supervisor audit.'}
    save(directory, 'CHILD_RESULT.json', result)
    return result
