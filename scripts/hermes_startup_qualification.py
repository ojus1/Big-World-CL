#!/usr/bin/env python3
"""Registered startup qualification, isolated from every historical campaign.

prepare() is read-only with respect to processes. execute() is the sole native
launch entry point and requires its exact prepublished manifest hash. Nine fixed
starts run as three singles then three pairs, with a barrier between batches.
No work request, actor, real credential, retry or replacement is permitted.
The separate --worker entry point requires a source-bound parent gate and an
independently verified owned systemd unit/network boundary before native import.
"""
from __future__ import annotations

import argparse
import ast
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

from scripts import hermes_startup_probe as child
from scripts import startup_resource_controls as resource

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'hermes-startup-qualification-v1'
BATCHES = (1, 1, 1, 2, 2, 2)
CONFIG = {'startup_seconds': 150, 'cleanup_seconds': 30, 'poll_seconds': .1,
          'max_parallel': 2, 'planned_slots': 9, 'batch_sizes': list(BATCHES),
          'failure_policy': 'halt_later_batches_on_any_failed_start_or_uncertain_boundary_or_cleanup',
          'work_requests': 0, 'provider_network': 'new_user_and_net_namespaces_loopback_down',
          'kernel_limits': dict(child.KERNEL_LIMITS), 'io_isolation_qualified': False}
UNSET_ENV = ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT', 'LD_DEBUG', 'LD_DEBUG_OUTPUT',
             'LD_PROFILE', 'LD_PROFILE_OUTPUT', 'LD_ORIGIN_PATH', 'GCONV_PATH', 'LOCPATH',
             'GLIBC_TUNABLES', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONUSERBASE', 'PYTHONSTARTUP')
PROPERTIES = ('UnsetEnvironment=' + ' '.join(UNSET_ENV), 'MemoryMax=4G', 'MemorySwapMax=0', 'TasksMax=128', 'CPUQuota=200%',
              'CPUQuotaPeriodSec=100ms', 'RuntimeMaxSec=180', 'TimeoutStopSec=5',
              'KillMode=control-group', 'Restart=no', 'Delegate=no', 'RemainAfterExit=yes')
SHOW_KEYS = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup',
             'InvocationID', 'ExecMainCode', 'ExecMainStatus', 'Result', 'KillMode',
             'TimeoutStopUSec', 'RuntimeMaxUSec', 'Restart', 'Delegate', 'RemainAfterExit', 'UnsetEnvironment')
CGROUP_ROOT = Path('/sys/fs/cgroup')
IDENTITY_KEYS = ('pid', 'start_ticks', 'uid', 'boot_id')
ENV_KEYS = ('PATH', 'HOME', 'LANG', 'USER', 'LOGNAME', 'XDG_RUNTIME_DIR', 'HERMES_AGENT_ROOT')
BOOTSTRAP = r'''
import hashlib,json,os,sys
from pathlib import Path
root,directory,slot=sys.argv[1:]
raw=(Path(directory)/'manifest.json').read_bytes()
execution=json.loads((Path(directory)/'EXECUTION.json').read_bytes())
assert hashlib.sha256(raw).hexdigest()==execution['registered_manifest_sha256']
manifest=json.loads(raw)
assert manifest['working_directory']==root and manifest['root']==directory
allowed=manifest['controller_environment']
assert set(allowed)=={'PATH','HOME','LANG','USER','LOGNAME','XDG_RUNTIME_DIR','HERMES_AGENT_ROOT'}
assert all(type(v) is str for v in allowed.values())
invocation=os.environ.get('INVOCATION_ID')
os.environ.clear(); os.environ.update(allowed)
if invocation is not None: os.environ['INVOCATION_ID']=invocation
sys.path[:]=[root,*manifest['controller_import_paths'],*sys.path]
from scripts.hermes_startup_qualification import _worker
_worker(Path(directory),slot)
'''


def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing_or_symlink_evidence')
    raw = path.read_bytes()
    return json.loads(raw), sha(raw)


def save(path, value):
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(canonical(value) + b'\n')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def boot():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def checked_unit(name):
    require(type(name) is str and re.fullmatch(child.UNIT_PREFIX + r'[0-9a-f]{32}\.service', name),
            'invalid_owned_unit_name')
    return name


def identity(pid):
    require(type(pid) is int and pid > 0, 'invalid_pid')
    base = Path('/proc') / str(pid)
    try:
        before = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        rows = (base / 'cgroup').read_text().splitlines()
        require(len(rows) == 1 and rows[0].startswith('0::/'), 'cgroup_v2_required')
        argv = (base / 'cmdline').read_bytes().split(b'\0')
        if argv[-1:] == [b'']:
            argv.pop()
        cwd = os.readlink(base / 'cwd')
        result = {'pid': pid, 'start_ticks': int(before[19]), 'uid': base.stat().st_uid,
                  'boot_id': boot(), 'ppid': int(before[1]), 'state': before[0],
                  'cgroup': rows[0][3:], 'cwd': cwd,
                  'argv_sha256': sha(canonical([x.decode() for x in argv])),
                  'net_namespace': os.readlink(base / 'ns/net'),
                  'user_namespace': os.readlink(base / 'ns/user')}
        after = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        require(before[19] == after[19], 'identity_changed_during_read')
        return result
    except FileNotFoundError:
        return None


def same(first, second):
    return (type(first) is dict and type(second) is dict and all(
        key in first and type(first[key]) is type(second.get(key)) and first[key] == second[key]
        for key in IDENTITY_KEYS))


def interpreter():
    # Preserve the invocation path: resolving a venv symlink loses its venv.
    return str(Path(sys.executable).absolute())


def controller_environment():
    from lifespan.computers import HERMES
    user = pwd.getpwuid(os.getuid())
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(Path(user.pw_dir).resolve()),
            'LANG': 'C.UTF-8', 'USER': user.pw_name, 'LOGNAME': user.pw_name,
            'XDG_RUNTIME_DIR': '/run/user/' + str(os.getuid()), 'HERMES_AGENT_ROOT': str(HERMES)}


def controller_import_paths():
    import site
    return sorted({str(Path(p).resolve()) for p in site.getsitepackages() if Path(p).is_dir()})


def native_argv(directory, slot):
    return [interpreter(), '-I', '-S', '-u', '-c', BOOTSTRAP,
            str(ROOT), str(directory), slot['slot_id']]


def binary(name):
    value = shutil.which(name)
    require(value is not None, 'missing_control_binary')
    return str(Path(value).resolve())


def launch_argv(directory, slot):
    return [binary('systemd-run'), '--user', '--quiet', '--wait', '--pipe', '--service-type=exec',
            '--unit=' + checked_unit(slot['unit']), *['--property=' + p for p in PROPERTIES],
            '--property=WorkingDirectory=' + str(ROOT), binary('unshare'), '--user',
            '--map-current-user', '--net', *native_argv(directory, slot)]


def show(name, timeout=2):
    checked_unit(name)
    result = subprocess.run([binary('systemctl'), '--user', 'show', name,
        *['--property=' + key for key in SHOW_KEYS]], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=max(.01, timeout), check=False)
    require(len(result.stdout) <= 32768, 'unit_observation_too_large')
    values = {}
    for line in result.stdout.decode().splitlines():
        key, sep, value = line.partition('=')
        require(sep and key in SHOW_KEYS and key not in values, 'invalid_unit_observation')
        values[key] = value
    require(set(values) == set(SHOW_KEYS) and values['Id'] == name and
            (result.returncode == 0 or values['LoadState'] == 'not-found'), 'unit_observation_failed')
    return values


def group_path(name, group, uid):
    checked_unit(name)
    require(type(group) is str and group.startswith(f'/user.slice/user-{uid}.slice/user@{uid}.service/')
            and '..' not in Path(group).parts and Path(group).name == name, 'foreign_unit_cgroup')
    base = CGROUP_ROOT / group.lstrip('/')
    require(base.resolve().is_relative_to(CGROUP_ROOT.resolve()), 'cgroup_path_escape')
    return base


def kernel(name, group, uid):
    base = group_path(name, group, uid)
    return {key: (base / key).read_text().strip() for key in child.KERNEL_LIMITS}


def members(name, group, uid):
    """Only the positively bound unit subtree, including detached descendants."""
    base = group_path(name, group, uid)
    if not base.exists():
        return []
    ids = set()
    files = [base / 'cgroup.procs'] + list(base.glob('**/cgroup.procs'))
    require(len(files) <= 512, 'cgroup_inventory_too_large')
    for path in files:
        require(not path.is_symlink() and path.resolve().is_relative_to(base.resolve()), 'cgroup_inventory_escape')
        try:
            ids.update(int(value) for value in path.read_text().split())
        except FileNotFoundError:
            continue
    require(len(ids) <= 512 and all(value > 0 for value in ids), 'invalid_cgroup_members')
    return sorted(ids)


def validate_unit(slot, observed, proc, expected, *, directory, kernel_values):
    """Pure native-main binding: never substitute the systemd-run client PID."""
    require(type(proc) is dict and same(proc, expected['main_identity']), 'native_main_identity_mismatch')
    require(proc['uid'] == expected['uid'] and proc['boot_id'] == expected['boot_id']
            and proc['cwd'] == str(ROOT) and proc['argv_sha256'] == sha(canonical(native_argv(directory, slot)))
            and proc['state'] not in ('Z', 'X'), 'native_main_configuration_mismatch')
    require(observed['Id'] == slot['unit'] and observed['LoadState'] == 'loaded'
            and observed['ActiveState'] == 'active' and observed['SubState'] == 'running'
            and observed['MainPID'] == str(proc['pid'])
            and re.fullmatch('[0-9a-f]{32}', observed['InvocationID'])
            and observed['ControlGroup'] == proc['cgroup'], 'unit_main_binding_mismatch')
    group_path(slot['unit'], proc['cgroup'], proc['uid'])
    require(proc['net_namespace'] != expected['host_net_namespace']
            and proc['user_namespace'] != expected['host_user_namespace'], 'namespace_not_separate')
    require(observed['KillMode'] == 'control-group' and observed['Restart'] == 'no'
            and observed['Delegate'] == 'no' and observed['RemainAfterExit'] == 'yes' and observed['TimeoutStopUSec'] == '5s'
            and observed['RuntimeMaxUSec'] == '3min', 'unit_lifecycle_properties_mismatch')
    require(set(observed['UnsetEnvironment'].split()) == set(UNSET_ENV), 'loader_environment_not_removed')
    require(kernel_values == child.KERNEL_LIMITS, 'unit_kernel_limits_mismatch')
    return {'verified': True, 'invocation_id': observed['InvocationID'],
            'cgroup': proc['cgroup'], 'main_identity': proc, 'kernel': kernel_values}


def sources():
    files = []
    for base, directories, names in os.walk(ROOT / 'lifespan', topdown=True, followlinks=False):
        directories[:] = sorted(name for name in directories
            if name not in ('tests', 'artifacts', '__pycache__', '.git') and not (Path(base) / name).is_symlink())
        for name in names:
            if name.endswith('.py'):
                path = Path(base) / name
                require(not path.is_symlink(), 'symlink_execution_source')
                files.append(path)
    files += [ROOT / 'scripts' / name for name in ('hermes_startup_qualification.py',
              'hermes_startup_probe.py', 'startup_resource_controls.py')]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(files)}


def dependencies():
    # Inspect metadata and pinned source only; no native agent/provider import.
    import importlib.metadata
    import platform
    from lifespan.computers import HERMES
    from lifespan.evaluation.hermes_transport import contract, verify_source
    native = verify_source(HERMES)
    require(not (native / '.env').exists() and not (native / '.env').is_symlink()
            and not Path('/etc/hermes').exists() and not Path('/etc/hermes').is_symlink(),
            'native_global_configuration_present')
    python = native / 'venv/bin/python'
    versions = json.loads(subprocess.check_output([str(python), '-I', '-c',
        'import importlib.metadata,json; print(json.dumps({k:importlib.metadata.version(k) '
        'for k in ("openai","httpx")}))'], text=True, stderr=subprocess.DEVNULL, timeout=10))
    bwrap = binary('bwrap')
    result = {'hermes': {'revision': contract('nonstreaming')['hermes_revision'],
        'native_source_sha256': contract('nonstreaming')['native_source_sha256'],
        'python_sha256': sha(python.read_bytes()), 'packages': versions},
        'harness': {'python_version': platform.python_version(), 'python_sha256': sha(Path(sys.executable).read_bytes()),
                    'pyyaml_version': importlib.metadata.version('PyYAML')},
        'bubblewrap': {'binary_sha256': sha(Path(bwrap).read_bytes()), 'version': subprocess.check_output(
            [bwrap, '--version'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()}, 'control_binaries': {}, 'global_configuration_absence': {'installed_repo_dotenv': True, 'managed_etc_hermes': True}}
    for name in ('systemd-run', 'systemctl', 'unshare'):
        location = binary(name)
        result['control_binaries'][name] = {'path': location, 'sha256': sha(Path(location).read_bytes())}
    return result


def committed(source_map, revision):
    require(type(revision) is str and re.fullmatch('[0-9a-f]{40}', revision), 'invalid_source_commit')
    for name, expected in source_map.items():
        raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', revision + ':' + name],
                                      stderr=subprocess.DEVNULL, timeout=10)
        require(sha(raw) == expected, 'uncommitted_execution_source')


def verify_resource(directory, *, expected_boot=None, expected_uid=None):
    report, _ = load(directory / 'REPORT.json')
    require(report.get('ok') is True and report.get('status') == 'verified', 'resource_probe_not_verified')
    for name, expected in report['receipt_sha256'].items():
        require(name in ('INTENT.json', 'START.json', 'OBSERVATION.json', 'CLEANUP.json'), 'unexpected_resource_receipt')
        require(load(directory / name)[1] == expected, 'resource_receipt_hash_mismatch')
    require(set(report['receipt_sha256']) == {'INTENT.json', 'START.json', 'OBSERVATION.json', 'CLEANUP.json'},
            'missing_resource_receipt')
    intent, _ = load(directory / 'INTENT.json')
    observation, _ = load(directory / 'OBSERVATION.json')
    cleanup, _ = load(directory / 'CLEANUP.json')
    require(intent['helper_sha256'] == sha(Path(resource.__file__).read_bytes())
            and intent['payload_sha256'] == sha(resource.PAYLOAD.encode())
            and intent['properties'] == list(resource.PROPERTIES), 'resource_source_mismatch')
    worker = observation['worker']
    require(worker['boot_id'] == (expected_boot or boot()) and worker['uid'] == (os.getuid() if expected_uid is None else expected_uid), 'resource_probe_wrong_boot_or_user')
    resource.validate_observation(intent['unit'], worker, observation['service'],
        observation['independent_process'], worker['kernel'], uid=worker['uid'])
    require(cleanup['cleanup']['confirmed'] is True and cleanup['streams_complete'] is True
            and cleanup['own_client_forced_termination'] is False
            and cleanup['cleanup']['systemd_run_exit_code'] == 0, 'resource_cleanup_unconfirmed')
    return {name: load(directory / name)[1] for name in (*report['receipt_sha256'], 'REPORT.json')}


def prepare(out, *, resource_probe):
    directory = Path(out).absolute()
    require(directory.parent.is_dir() and directory.parent.resolve() == directory.parent
            and not directory.exists() and not directory.is_symlink(), 'fresh_real_output_required')
    proof = Path(resource_probe).resolve()
    proof_hashes = verify_resource(proof)
    source_map = sources()
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
    committed(source_map, revision)
    deps = dependencies()
    slots = []
    for batch, size in enumerate(BATCHES):
        for repeat in range(size):
            index = len(slots)
            slots.append({'index': index, 'slot_id': f'start-{index:02d}', 'batch': batch,
                          'unit': child.UNIT_PREFIX + uuid.uuid4().hex + '.service'})
    manifest = {'schema_version': 1, 'kind': VERSION, 'config': CONFIG, 'slots': slots,
        'source_sha256': source_map, 'repository_commit': revision, 'dependencies': deps,
        'boot_id': boot(), 'uid': os.getuid(), 'root': str(directory), 'working_directory': str(ROOT),
        'python': interpreter(), 'resource_receipt_sha256': proof_hashes,
        'controller_environment': controller_environment(), 'controller_import_paths': controller_import_paths(),
        'child_execution': child.EXECUTION, 'created_at': datetime.now(timezone.utc).isoformat(),
        'limits_are_containment_not_latency_reservation': True}
    directory.mkdir(mode=0o700)
    (directory / 'resource').mkdir(mode=0o700)
    for name, expected in proof_hashes.items():
        raw = (proof / name).read_bytes()
        require(sha(raw) == expected, 'resource_changed_during_prepare')
        descriptor = os.open(directory / 'resource' / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
    (directory / 'slots').mkdir(mode=0o700)
    save(directory / 'manifest.json', manifest)
    return {'manifest_sha256': load(directory / 'manifest.json')[1], 'slots': 9, 'prepared': True}


def validate_manifest(directory, expected_hash, *, current=True):
    manifest, actual = load(directory / 'manifest.json')
    require(actual == expected_hash and re.fullmatch('[0-9a-f]{64}', expected_hash or ''), 'registered_manifest_mismatch')
    require(manifest['kind'] == VERSION and canonical(manifest['config']) == canonical(CONFIG)
            and canonical(manifest['child_execution']) == canonical(child.EXECUTION), 'qualification_contract_mismatch')
    require(manifest['root'] == str(directory) and manifest['working_directory'] == str(ROOT)
            and manifest['python'] == interpreter(), 'execution_location_mismatch')
    require(type(manifest['controller_environment']) is dict and set(manifest['controller_environment']) == set(ENV_KEYS)
            and all(type(v) is str for v in manifest['controller_environment'].values())
            and type(manifest['controller_import_paths']) is list
            and all(type(p) is str and Path(p).is_absolute() and Path(p).is_dir() for p in manifest['controller_import_paths']),
            'controller_bootstrap_contract_mismatch')
    slots = manifest['slots']
    require(type(slots) is list and len(slots) == 9, 'nine_fixed_slots_required')
    batches = [batch for batch, size in enumerate(BATCHES) for _ in range(size)]
    for index, slot in enumerate(slots):
        require(set(slot) == {'index', 'slot_id', 'batch', 'unit'} and type(slot['index']) is int
                and slot['index'] == index and slot['slot_id'] == f'start-{index:02d}'
                and type(slot['batch']) is int and slot['batch'] == batches[index], 'slot_schedule_mismatch')
        checked_unit(slot['unit'])
    require(len({x['unit'] for x in slots}) == 9, 'unit_reuse_forbidden')
    require(manifest['source_sha256'] == sources(), 'execution_source_changed')
    committed(manifest['source_sha256'], manifest['repository_commit'])
    require(manifest['resource_receipt_sha256'] == verify_resource(directory / 'resource',
        expected_boot=manifest['boot_id'], expected_uid=manifest['uid']), 'resource_proof_changed')
    if current:
        require(manifest['boot_id'] == boot() and manifest['uid'] == os.getuid(), 'boot_or_user_changed')
        require(manifest['dependencies'] == dependencies(), 'dependency_changed')
        require(manifest['controller_environment'] == controller_environment()
                and manifest['controller_import_paths'] == controller_import_paths(), 'controller_bootstrap_changed')
        require(manifest['resource_receipt_sha256'] == verify_resource(directory / 'resource'), 'resource_proof_changed')
    return manifest


def _worker(directory, slot_id):
    manifest, manifest_hash = load(directory / 'manifest.json')
    execution, _ = load(directory / 'EXECUTION.json')
    require(execution['registered_manifest_sha256'] == manifest_hash, 'worker_manifest_not_registered')
    manifest = validate_manifest(directory, manifest_hash, current=False)
    require(manifest['boot_id'] == boot() and manifest['uid'] == os.getuid(), 'worker_boot_changed')
    slot = next(item for item in manifest['slots'] if item['slot_id'] == slot_id)
    trial = directory / 'slots' / slot_id
    intent, _ = load(trial / 'INTENT.json')
    deadline = intent['startup_deadline_monotonic']
    require(finite(deadline) and time.monotonic() < deadline, 'worker_start_deadline_exhausted')
    save(trial / 'HELLO.json', {'slot_id': slot_id, 'manifest_sha256': manifest_hash,
                               'identity': identity(os.getpid()), 'observed_monotonic': time.monotonic()})
    while not (trial / 'GATE.json').exists():
        require(time.monotonic() < deadline, 'worker_gate_deadline_exhausted')
        time.sleep(.05)
    gate, _ = load(trial / 'GATE.json')
    require(gate['manifest_sha256'] == manifest_hash and gate['slot_id'] == slot_id
            and gate['startup_deadline_monotonic'] == deadline
            and same(gate['unit_binding']['main_identity'], identity(os.getpid())), 'worker_gate_identity_mismatch')
    require(manifest['source_sha256'] == sources() and manifest['dependencies'] == dependencies(),
            'post_gate_source_or_dependency_changed')
    require({key: os.environ.get(key) for key in ENV_KEYS} == manifest['controller_environment']
            and set(os.environ) <= set(ENV_KEYS) | {'INVOCATION_ID'}, 'controller_environment_not_scrubbed')
    expected = gate['expected_boundary']
    require(expected['unit'] == slot['unit'] and expected['boot_id'] == manifest['boot_id']
            and expected['uid'] == manifest['uid'], 'worker_boundary_manifest_mismatch')
    # The child verifies kernel/namespace/interface constraints before heavy imports.
    def release_close(native, ready, cleanup_deadline):
        if ready is None:
            return
        while not (trial / 'CLOSE_GATE.json').exists():
            require(time.monotonic() < cleanup_deadline, 'close_gate_deadline_exhausted')
            time.sleep(min(.05, max(0, cleanup_deadline - time.monotonic())))
        receipt, _ = load(trial / 'CLOSE_GATE.json')
        require(receipt['slot_id'] == slot_id and receipt['manifest_sha256'] == manifest_hash
                and receipt['cleanup_deadline_monotonic'] == cleanup_deadline, 'close_gate_binding_mismatch')
        for item in receipt['native_identities'].values():
            require(same(item, identity(item['pid'])), 'close_gate_native_identity_changed')
        require(time.monotonic() < cleanup_deadline, 'late_close_gate')
    child.native_startup(trial / 'native', expected, startup_deadline=deadline, before_close=release_close)


def expected_native_commands(trial, manifest):
    computer = trial / 'native/computers/startup-qualification'
    worker = [str(Path(manifest['controller_environment']['HERMES_AGENT_ROOT']) / 'venv/bin/python'),
              '-u', '-m', 'lifespan.hermes_worker']
    # Read the source-bound literal command recipe without constructing a sandbox.
    tree = ast.parse((ROOT / 'lifespan/bubblewrap.py').read_bytes())
    recipes = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                       and target.value.id == 'self' and target.attr == 'command' for target in node.targets)]
    require(len(recipes) == 1, 'sandbox_command_recipe_changed')
    recipe = recipes[0]
    allowed = (ast.List, ast.Load, ast.Constant, ast.Call, ast.Name, ast.Attribute, ast.BinOp, ast.Div)
    require(all(isinstance(node, allowed) for node in ast.walk(recipe)), 'unsupported_sandbox_command_recipe')
    require(all(isinstance(node.func, ast.Name) and node.func.id == 'str' and len(node.args) == 1 and not node.keywords
                for node in ast.walk(recipe) if isinstance(node, ast.Call)), 'unsupported_sandbox_command_call')
    environment = {'self': SimpleNamespace(root=computer, home=computer/'os_home', control=computer/'control'),
        'passwd':computer/'control/passwd', 'group':computer/'control/group',
        'server':ROOT/'lifespan/bwrap_server.py'}
    command = eval(compile(ast.Expression(recipe), '<source-bound sandbox command>', 'eval'),
                   {'__builtins__': {'str': str}}, environment)
    require(type(command) is list and all(type(value) is str for value in command) and command[0] == 'bwrap',
            'invalid_sandbox_command_recipe')
    return {'worker':worker, 'sandbox':command}


def _capture_native(trial, binding, manifest):
    instance, digest = load(trial / 'native/computers/startup-qualification/instance.json')
    require(instance['kind'] == 'ready' and instance['backend'] == 'bubblewrap'
            and instance['employee'] == 'startup-qualification', 'native_instance_mismatch')
    identities = {}
    commands = expected_native_commands(trial, manifest)
    for key, pid in [('worker', instance['pid']), ('sandbox', instance['sandbox_pid'])]:
        proc = identity(pid)
        require(proc is not None and proc['uid'] == manifest['uid'] and proc['boot_id'] == manifest['boot_id']
                and proc['cgroup'] == binding['cgroup'] and proc['state'] not in ('Z', 'X')
                and proc['start_ticks'] >= binding['main_identity']['start_ticks'], 'native_descendant_not_bound')
        require(proc['argv_sha256'] == sha(canonical(commands[key]))
                and proc['cwd'] == str(trial / 'native/computers/startup-qualification/workspace'),
                'native_descendant_command_changed')
        identities[key] = proc
    require(identities['worker']['net_namespace'] == binding['main_identity']['net_namespace']
            and identities['worker']['user_namespace'] == binding['main_identity']['user_namespace'], 'native_worker_namespace_changed')
    require(identities['worker']['ppid'] == binding['main_identity']['pid']
            and identities['sandbox']['ppid'] == identities['worker']['pid'], 'native_parent_binding_mismatch')
    return {'instance_sha256': digest, 'identities': identities}


def _socket_inventory(trial):
    require(trial.is_dir() and trial.resolve() == trial, 'trial_path_not_canonical')
    control = trial / 'native/computers/startup-qualification/control'
    require(control.resolve() == control and control.is_relative_to(trial), 'control_parent_symlink')
    aliases = []
    alias_identities = {}
    for alias in Path('/tmp').glob('lifespan-bwrap-*'):
        link = alias / 'control'
        if (not alias.is_symlink() and alias.is_dir() and alias.stat().st_uid == os.getuid()
                and link.is_symlink() and link.resolve() == control):
            require(set(x.name for x in alias.iterdir()) == {'control'}, 'owned_alias_unexpected_contents')
            data = alias.stat()
            alias_identities[str(alias)] = {'device':data.st_dev, 'inode':data.st_ino, 'uid':data.st_uid}
            aliases.append(str(alias))
    return {'control': str(control), 'aliases': sorted(aliases), 'alias_identities':alias_identities,
            'underlying_socket_present': (control / 'command.sock').exists()}


def _clean_sockets(trial):
    observed = _socket_inventory(trial)
    for item in observed['aliases']:
        alias = Path(item)
        # Recheck exact owned target immediately before mutation.
        data = alias.lstat()
        require(stat.S_ISDIR(data.st_mode) and not alias.is_symlink()
                and {'device':data.st_dev,'inode':data.st_ino,'uid':data.st_uid} == observed['alias_identities'][item],
                'owned_alias_identity_changed')
        require((alias / 'control').is_symlink() and (alias / 'control').resolve() == Path(observed['control']),
                'owned_alias_changed')
        (alias / 'control').unlink()
        alias.rmdir()
    socket = Path(observed['control']) / 'command.sock'
    if socket.exists():
        require(not socket.is_symlink() and stat.S_ISSOCK(socket.stat().st_mode), 'owned_control_not_socket')
        socket.unlink()
    final = _socket_inventory(trial)
    return {'confirmed': not final['aliases'] and not final['underlying_socket_present'],
            'removed_aliases': len(observed['aliases']), 'removed_underlying_socket': observed['underlying_socket_present']}


def _stop_owned(slot, binding, *, deadline):
    """Control only a still-identical registered unit invocation; never PID-kill."""
    observed = show(slot['unit'], timeout=min(2, max(.01, deadline - time.monotonic())))
    if observed['LoadState'] == 'not-found':
        return {'requested': False, 'already_absent': True}
    require(binding is not None and observed['InvocationID'] == binding['invocation_id']
            and observed['ControlGroup'] in ('', binding['cgroup']), 'refuse_unbound_unit_stop')
    require(time.monotonic() < deadline, 'no_cleanup_time_for_unit_stop')
    result = subprocess.run([binary('systemctl'), '--user', 'stop', slot['unit']], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=min(7, max(.01, deadline - time.monotonic())), check=False)
    return {'requested': True, 'returncode': result.returncode}


def _cleanup(slot, binding, known, process, trial, started, deadline):
    errors = []
    stop = None
    terminal_before_stop = None
    try:
        prior = show(slot['unit'], timeout=min(2, max(.01, deadline - time.monotonic())))
        if (binding and prior['LoadState'] == 'loaded' and prior['InvocationID'] == binding['invocation_id']
                and prior['ControlGroup'] == binding['cgroup'] and prior['MainPID'] == '0'
                and prior['ActiveState'] == 'active' and prior['SubState'] == 'exited'):
            terminal_before_stop = prior
            save(trial / 'UNIT_TERMINAL.json', {'unit': prior, 'observed_monotonic': time.monotonic()})
        stop = _stop_owned(slot, binding, deadline=deadline)
    except Exception as exc:
        errors.append(type(exc).__name__)
    final_unit = None
    remaining = None
    while time.monotonic() < deadline:
        try:
            final_unit = show(slot['unit'], timeout=min(2, max(.01, deadline - time.monotonic())))
            remaining = members(slot['unit'], binding['cgroup'], os.getuid()) if binding else None
            if remaining == [] and final_unit['MainPID'] == '0' and final_unit['ActiveState'] in ('inactive', 'failed'):
                break
        except Exception as exc:
            errors.append(type(exc).__name__)
            break
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    observed = []
    for item in known.values():
        try:
            now = identity(item['pid'])
            state = 'absent' if now is None else 'replaced' if not same(item, now) else 'zombie' if now['state'] == 'Z' else 'alive'
        except Exception:
            state = 'unknown'
        observed.append({'identity': item, 'state': state})
    identities_clear = bool(binding) and all(x['state'] in ('absent', 'replaced', 'zombie') for x in observed)
    sockets = {'confirmed': False}
    terminal = bool(final_unit and final_unit['MainPID'] == '0'
        and final_unit['ActiveState'] in ('inactive', 'failed')
        and (final_unit['LoadState'] == 'not-found' and not final_unit['InvocationID']
             and not final_unit['ControlGroup'] or binding and final_unit['InvocationID'] == binding['invocation_id']))
    if identities_clear and remaining == [] and terminal and not errors:
        try:
            sockets = _clean_sockets(trial)
        except Exception as exc:
            errors.append(type(exc).__name__)
    client_exit = None
    if process is not None:
        try:
            client_exit = process.wait(timeout=max(.01, min(2, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            errors.append('ClientExitUnknown')
    ended = time.monotonic()
    return {'started_monotonic': started, 'ended_monotonic': ended, 'deadline_monotonic': deadline,
        'limit_seconds': CONFIG['cleanup_seconds'], 'unit_stop': stop, 'unit_final': final_unit,
        'terminal_before_stop': terminal_before_stop,
        'members_remaining': remaining, 'observed_processes': observed, 'socket_cleanup': sockets,
        'control_client_exit_code': client_exit, 'errors': errors,
        'confirmed': bool(terminal and identities_clear and sockets['confirmed'] and not remaining
                          and client_exit is not None and ended <= deadline and not errors)}


def _run_slot(directory, manifest, slot, stop_event):
    trial = directory / 'slots' / slot['slot_id']
    trial.mkdir(mode=0o700)
    started = time.monotonic()
    deadline = started + CONFIG['startup_seconds']
    intent = {'slot_id': slot['slot_id'], 'unit': slot['unit'], 'started_monotonic': started,
        'startup_deadline_monotonic': deadline, 'manifest_sha256': load(directory / 'manifest.json')[1],
        'command_sha256': sha(canonical(launch_argv(directory, slot)))}
    save(trial / 'INTENT.json', intent)
    process = None; binding = None; known = {}; errors = []; outcome = None; startup_end = None
    status = 'infrastructure_failed'; gate = None; client_id = None
    log = (trial / 'controller.log').open('xb')
    try:
        require(show(slot['unit'])['LoadState'] == 'not-found', 'unit_name_already_exists')
        require(not stop_event.is_set() and time.monotonic() < deadline, 'dispatch_deadline_or_interrupt')
        process = subprocess.Popen(launch_argv(directory, slot), cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
        client_id = identity(process.pid)
        require(client_id is not None, 'control_client_identity_unavailable')
        save(trial / 'CLIENT.json', {'identity': client_id, 'observed_monotonic': time.monotonic()})
        while time.monotonic() < deadline and not stop_event.is_set():
            if (trial / 'HELLO.json').exists():
                hello, _ = load(trial / 'HELLO.json')
                require(hello['slot_id'] == slot['slot_id'] and hello['manifest_sha256'] == intent['manifest_sha256'],
                        'worker_hello_mismatch')
                unit = show(slot['unit'])
                proc = identity(int(unit['MainPID']))
                expected = {'main_identity': hello['identity'], 'uid': manifest['uid'], 'boot_id': manifest['boot_id'],
                            'host_net_namespace': os.readlink('/proc/self/ns/net'),
                            'host_user_namespace': os.readlink('/proc/self/ns/user')}
                binding = validate_unit(slot, unit, proc, expected, directory=directory,
                                        kernel_values=kernel(slot['unit'], unit['ControlGroup'], manifest['uid']))
                known[proc['pid']] = proc
                gate = {'slot_id': slot['slot_id'], 'manifest_sha256': intent['manifest_sha256'],
                    'startup_deadline_monotonic': deadline, 'unit_binding': binding, 'unit_observation': unit,
                    'expected_boundary': {'uid': manifest['uid'], 'boot_id': manifest['boot_id'],
                        'host_net_namespace': expected['host_net_namespace'],
                        'host_user_namespace': expected['host_user_namespace'],
                        'unit': slot['unit'], 'invocation_id': unit['InvocationID']}}
                require(time.monotonic() < deadline, 'gate_dispatch_deadline_exhausted')
                save(trial / 'GATE.json', gate)
                break
            if process.poll() is not None:
                raise RuntimeError('ControllerExitedBeforeHello')
            time.sleep(CONFIG['poll_seconds'])
        require(binding is not None, 'native_unit_not_bound')
        while not stop_event.is_set():
            for pid in members(slot['unit'], binding['cgroup'], manifest['uid']):
                proc = identity(pid)
                if proc is not None:
                    require(proc['uid'] == manifest['uid'] and proc['boot_id'] == manifest['boot_id'], 'foreign_member_identity')
                    known[pid] = proc
            phase = trial / 'native/STARTUP_FINISHED.json'
            if phase.exists():
                outcome, _ = load(phase)
                candidate_end = outcome['finished_monotonic']
                require(finite(candidate_end) and started <= candidate_end <= deadline, 'startup_deadline_exceeded')
                startup_end = candidate_end
                status = 'ready' if outcome['ready_observed'] is True else 'startup_failed'
                if status == 'ready':
                    native = _capture_native(trial, binding, manifest)
                    known.update({item['pid']: item for item in native['identities'].values()})
                    save(trial / 'NATIVE_IDENTITIES.json', native)
                    save(trial / 'CLOSE_GATE.json', {'slot_id': slot['slot_id'],
                        'manifest_sha256': intent['manifest_sha256'],
                        'cleanup_deadline_monotonic': startup_end + CONFIG['cleanup_seconds'],
                        'native_identities': native['identities']})
                break
            if time.monotonic() >= deadline:
                status = 'startup_timed_out'; break
            if process.poll() is not None:
                status = 'infrastructure_failed'; break
            time.sleep(CONFIG['poll_seconds'])
        if stop_event.is_set():
            status = 'interrupted'
    except Exception as exc:
        errors.append({'error_type': type(exc).__name__,
                       'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None})
    cleanup_started = startup_end if startup_end is not None else min(time.monotonic(), deadline)
    cleanup_deadline = cleanup_started + CONFIG['cleanup_seconds']
    # Let native close finish naturally while observing cgroup descendants.
    if process is not None and startup_end is not None:
        while process.poll() is None and time.monotonic() < cleanup_deadline - 7 and not stop_event.is_set():
            try:
                if (trial / 'native/CHILD_RESULT.json').exists():
                    unit = show(slot['unit'])
                    if unit['InvocationID'] == binding['invocation_id'] and unit['MainPID'] == '0':
                        break
                for pid in members(slot['unit'], binding['cgroup'], manifest['uid']):
                    proc = identity(pid)
                    if proc is not None:
                        known[pid] = proc
            except Exception as exc:
                errors.append({'error_type': type(exc).__name__, 'code': None}); break
            time.sleep(CONFIG['poll_seconds'])
    cleanup = _cleanup(slot, binding, known, process, trial, cleanup_started, cleanup_deadline)
    save(trial / 'CLEANUP.json', cleanup)
    log.close()
    native_result = None
    try:
        if (trial / 'native/CHILD_RESULT.json').exists():
            native_result, _ = load(trial / 'native/CHILD_RESULT.json')
    except Exception as exc:
        errors.append({'error_type': type(exc).__name__, 'code': None})
    boundary_ok = bool(gate and native_result and native_result.get('boundary_verified_before_and_after') is True
                       and native_result.get('work_requests_sent') == 0
                       and native_result.get('provider_credentials_supplied') is False
                       and native_result.get('outcome_receipt_error_type') is None
                       and native_result.get('pre_close_error_type') is None
                       and native_result.get('close_returned_within_allowance') is True)
    continued = bool(status == 'ready' and cleanup['confirmed'] and boundary_ok and not errors)
    receipt = {'slot': slot, 'status': status, 'intent_sha256': load(trial / 'INTENT.json')[1],
        'client_identity': client_id, 'unit_binding': binding, 'startup_outcome': outcome,
        'cleanup': cleanup, 'boundary_verified': boundary_ok, 'errors': errors,
        'qualification_passed': bool(continued and status == 'ready' and native_result['ready_observed']),
        'safe_to_continue': continued, 'native_inference_requests': 0 if boundary_ok else None,
        'work_requests_sent': 0, 'usage_scope': 'no_inference_boundary_not_a_model_usage_meter',
        'evidence_sha256': {str(p.relative_to(trial)): sha(p.read_bytes()) for p in sorted(trial.rglob('*'))
                           if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.jsonl')}}
    if receipt['qualification_passed']:
        try:
            execution, _ = load(directory / 'EXECUTION.json')
            _completed_evidence(trial, directory, manifest, execution, slot, intent, receipt)
        except Exception as exc:
            receipt.update(status='infrastructure_failed', qualification_passed=False, safe_to_continue=False)
            receipt['errors'].append({'error_type':type(exc).__name__,
                'code':str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+',str(exc)) else None})
    save(trial / 'RECEIPT.json', receipt)
    return receipt


@contextmanager
def interrupt_scope(event):
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def stop(signum, frame):
        event.set()
    for sig in previous:
        signal.signal(sig, stop)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def execute(out, *, manifest_sha256):
    directory = Path(out).absolute()
    manifest = validate_manifest(directory, manifest_sha256)
    require(not (directory / 'EXECUTION.json').exists() and not any((directory / 'slots').iterdir()),
            'qualification_is_one_shot')
    save(directory / 'EXECUTION.json', {'schema_version': 1, 'registered_manifest_sha256': manifest_sha256,
        'supervisor': identity(os.getpid()), 'started_monotonic': time.monotonic(), 'boot_id': boot(),
        'dependencies': manifest['dependencies'], 'source_sha256': manifest['source_sha256']})
    results = []
    stop = threading.Event()
    with interrupt_scope(stop), ThreadPoolExecutor(max_workers=2) as pool:
        for batch in range(len(BATCHES)):
            planned = [x for x in manifest['slots'] if x['batch'] == batch]
            if stop.is_set():
                results.extend({'slot': x, 'status': 'skipped_after_stop', 'qualification_passed': False,
                                'safe_to_continue': False, 'native_inference_requests': None} for x in planned)
                continue
            futures = [pool.submit(_run_slot, directory, manifest, slot, stop) for slot in planned]
            rows = []
            for slot, future in zip(planned, futures):
                try:
                    rows.append(future.result())
                except Exception as exc:
                    rows.append({'slot': slot, 'status': 'unresolved', 'error_type': type(exc).__name__,
                                 'qualification_passed': False, 'safe_to_continue': False,
                                 'native_inference_requests': None})
                    stop.set()
            results.extend(rows)
            if any(not row['safe_to_continue'] for row in rows):
                stop.set()
    report = {'schema_version': 1, 'kind': VERSION, 'manifest_sha256': manifest_sha256,
        'status': 'completed' if len(results) == 9 and all(x['safe_to_continue'] for x in results) else 'incomplete',
        'qualification_passed': len(results) == 9 and all(x['qualification_passed'] for x in results),
        'planned_slots': 9, 'results': results,
        'scope': 'Startup component only; cache and IO latency uncontrolled; no learning or long-horizon claim.'}
    save(directory / 'REPORT.json', report)
    return audit_qualification(directory, manifest_sha256=manifest_sha256, strict=True)


def _completed_evidence(trial, directory, manifest, execution, slot, intent, receipt):
    """Reconstruct a claimed pass from native, boundary and lifecycle artifacts."""
    require(receipt['status'] == 'ready' and receipt['safe_to_continue'] is True
            and receipt['qualification_passed'] is True and receipt['boundary_verified'] is True
            and not receipt['errors'], 'completed_receipt_contradiction')
    require(execution['dependencies'] == manifest['dependencies']
            and execution['source_sha256'] == manifest['source_sha256'], 'execution_provenance_mismatch')
    expected_inventory = {str(p.relative_to(trial)): sha(p.read_bytes()) for p in sorted(trial.rglob('*'))
        if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.jsonl') and p.name != 'RECEIPT.json'}
    require(receipt['evidence_sha256'] == expected_inventory, 'evidence_inventory_mismatch')
    gate, _ = load(trial / 'GATE.json')
    hello, _ = load(trial / 'HELLO.json')
    client, _ = load(trial / 'CLIENT.json')
    binding = receipt['unit_binding']
    supervisor = execution['supervisor']
    require(gate['slot_id'] == slot['slot_id'] and gate['manifest_sha256'] == intent['manifest_sha256']
            and gate['startup_deadline_monotonic'] == intent['startup_deadline_monotonic']
            and hello['slot_id'] == slot['slot_id'] and hello['manifest_sha256'] == intent['manifest_sha256'], 'gate_launch_mismatch')
    require(client['identity'] == receipt['client_identity'] and client['identity']['ppid'] == supervisor['pid']
            and client['identity']['uid'] == manifest['uid'] and client['identity']['boot_id'] == manifest['boot_id']
            and client['identity']['start_ticks'] >= supervisor['start_ticks']
            and client['identity']['argv_sha256'] == intent['command_sha256'], 'control_client_parent_mismatch')
    expected = {'main_identity': hello['identity'], 'uid': manifest['uid'], 'boot_id': manifest['boot_id'],
        'host_net_namespace': supervisor['net_namespace'], 'host_user_namespace': supervisor['user_namespace']}
    rebuilt = validate_unit(slot, gate['unit_observation'], binding['main_identity'], expected,
                            directory=directory, kernel_values=binding['kernel'])
    require(rebuilt == binding and gate['unit_binding'] == binding, 'unit_binding_changed')
    require(gate['expected_boundary'] == {'uid': manifest['uid'], 'boot_id': manifest['boot_id'],
        'host_net_namespace': supervisor['net_namespace'], 'host_user_namespace': supervisor['user_namespace'],
        'unit': slot['unit'], 'invocation_id': binding['invocation_id']}, 'host_boundary_changed')
    close_gate, _ = load(trial / 'CLOSE_GATE.json')
    native_ids, _ = load(trial / 'NATIVE_IDENTITIES.json')
    computer = trial / 'native/computers/startup-qualification'
    instance, instance_hash = load(computer / 'instance.json')
    require(native_ids['instance_sha256'] == instance_hash and close_gate['native_identities'] == native_ids['identities']
            and close_gate['slot_id'] == slot['slot_id'] and close_gate['manifest_sha256'] == intent['manifest_sha256'],
            'native_identity_receipt_mismatch')
    ids = native_ids['identities']
    require(set(ids) == {'worker', 'sandbox'} and ids['worker']['net_namespace'] == binding['main_identity']['net_namespace']
            and ids['worker']['user_namespace'] == binding['main_identity']['user_namespace']
            and ids['worker']['pid'] == instance['pid']
            and ids['sandbox']['pid'] == instance['sandbox_pid']
            and ids['worker']['ppid'] == binding['main_identity']['pid']
            and ids['sandbox']['ppid'] == ids['worker']['pid'], 'native_identity_parent_mismatch')
    commands = expected_native_commands(trial, manifest)
    for key, proc in ids.items():
        require(proc['argv_sha256'] == sha(canonical(commands[key]))
                and proc['cwd'] == str(computer / 'workspace'), 'native_descendant_command_changed')
        require(proc['cgroup'] == binding['cgroup'] and proc['uid'] == manifest['uid']
                and proc['boot_id'] == manifest['boot_id'] and proc['state'] not in ('Z', 'X')
                and proc['start_ticks'] >= binding['main_identity']['start_ticks'], 'native_identity_scope_mismatch')
        require(any(same(proc, row['identity']) for row in receipt['cleanup']['observed_processes']),
                'native_identity_missing_in_cleanup')
    from lifespan.evaluation.hermes_transport import contract
    require(instance['kind'] == 'ready' and instance['backend'] == 'bubblewrap'
            and instance['employee'] == 'startup-qualification'
            and instance['evaluation_transport'] == contract('nonstreaming')
            and {'terminal', 'skill_view', 'enterprise_action'} <= set(instance['tool_names'])
            and not {'memory', 'skill_manage'} & set(instance['tool_names']), 'native_ready_contract_mismatch')
    terminal_probe = json.loads(instance['probe'])
    require(type(terminal_probe['exit_code']) is int and terminal_probe['exit_code'] == 0
            and 'startup-qualification' in terminal_probe['output'].splitlines(), 'native_sandbox_probe_invalid')
    journal_manifest, _ = load(computer / 'startup/manifest.json')
    from lifespan.startup_observability import provenance, VERSION as observation_version
    require(journal_manifest == {'version': observation_version, 'attempt_id': journal_manifest['attempt_id'], **provenance()}
            and re.fullmatch('[0-9a-f]{32}', journal_manifest['attempt_id']), 'startup_journal_manifest_mismatch')
    stages = {'parent': ['popen_returned', 'ready_received'], 'worker': ['worker_entered',
        'imports_before', 'imports_after', 'registry_before', 'registry_after', 'sandbox_before', 'sandbox_after',
        'agent_before', 'agent_after', 'budget_transport_before', 'budget_transport_after', 'probe_before',
        'probe_after', 'ready_write_attempt', 'ready_write_returned']}
    phase, _ = load(trial / 'native/STARTUP_FINISHED.json')
    journal_result, _ = load(trial / 'native/CHILD_RESULT.json')
    for role, expected_stages in stages.items():
        records = [json.loads(line) for line in (computer / 'startup' / (role + '.jsonl')).read_bytes().splitlines()]
        require([row['stage'] for row in records] == expected_stages, 'startup_stage_or_work_request_mismatch')
        require(all(finite(row['monotonic_seconds']) for row in records)
                and all(a['monotonic_seconds'] <= b['monotonic_seconds'] for a,b in zip(records,records[1:])),
                'startup_stage_order_changed')
        for index, row in enumerate(records):
            end = journal_result['close_finished_monotonic'] if row['stage'] == 'ready_write_returned' else phase['finished_monotonic']
            require(type(row['sequence']) is int and row['sequence'] == index and row['role'] == role
                    and row['attempt_id'] == journal_manifest['attempt_id'] and row['version'] == observation_version
                    and row['error_type'] is None and row['observation_errors'] == []
                    and same(row['observer_identity'], ids['worker'] if role == 'worker' else binding['main_identity'])
                    and same(row['worker_identity'], ids['worker'])
                    and finite(row['monotonic_seconds']) and intent['started_monotonic'] <= row['monotonic_seconds']
                    <= end, 'startup_journal_binding_mismatch')
    result, _ = load(trial / 'native/CHILD_RESULT.json')
    close, _ = load(trial / 'native/CLOSE_STARTED.json')
    start_intent, _ = load(trial / 'native/STARTUP_INTENT.json')
    require(start_intent['kind'] == child.VERSION and start_intent['execution'] == child.EXECUTION
            and start_intent['helper_sha256'] == manifest['source_sha256']['scripts/hermes_startup_probe.py']
            and start_intent['work_requests_sent'] == 0, 'native_startup_intent_mismatch')
    require(phase['ready_observed'] is True and phase['error_type'] is None and result['ready_observed'] is True
            and all(result[key] is None for key in ('error_type', 'close_error_type', 'outcome_receipt_error_type', 'pre_close_error_type'))
            and result['close_returned_within_allowance'] is True, 'native_child_error')
    require(result['startup_finished_monotonic'] == phase['finished_monotonic']
            and result['entered_monotonic'] == phase['entered_monotonic']
            and result['startup_deadline'] == phase['startup_deadline'] == intent['startup_deadline_monotonic']
            and intent['started_monotonic'] <= phase['entered_monotonic'] <= phase['finished_monotonic']
            and phase['startup_elapsed_seconds'] == phase['finished_monotonic'] - phase['entered_monotonic'],
            'native_timing_mismatch')
    require(close['started_monotonic'] == phase['finished_monotonic']
            and close['cleanup_deadline'] == close['started_monotonic'] + CONFIG['cleanup_seconds']
            == result['cleanup_deadline'] == close_gate['cleanup_deadline_monotonic']
            and close['started_monotonic'] <= result['close_finished_monotonic'] <= close['cleanup_deadline'],
            'native_close_timing_mismatch')
    raw_cleanup, _ = load(trial / 'CLEANUP.json')
    require(raw_cleanup == receipt['cleanup'], 'cleanup_receipt_mismatch')
    retained, _ = load(trial / 'UNIT_TERMINAL.json')
    terminal = retained['unit']
    require(terminal == raw_cleanup['terminal_before_stop'] and terminal['Id'] == slot['unit']
            and terminal['LoadState'] == 'loaded' and terminal['InvocationID'] == binding['invocation_id']
            and terminal['ControlGroup'] == binding['cgroup'] and terminal['MainPID'] == '0'
            and terminal['ActiveState'] == 'active' and terminal['SubState'] == 'exited'
            and terminal['ExecMainCode'] == '1' and terminal['ExecMainStatus'] == '0'
            and terminal['Result'] == 'success' and terminal['RemainAfterExit'] == 'yes'
            and finite(retained['observed_monotonic'])
            and raw_cleanup['started_monotonic'] <= retained['observed_monotonic'] <= raw_cleanup['ended_monotonic'],
            'native_unit_terminal_not_successful')
    final = raw_cleanup['unit_final']
    require(final['Id'] == slot['unit'] and final['MainPID'] == '0' and final['ActiveState'] == 'inactive'
            and final['SubState'] == 'dead' and (final['LoadState'] == 'not-found' and not final['InvocationID']
            and not final['ControlGroup'] or final['LoadState'] == 'loaded' and final['InvocationID'] == binding['invocation_id']),
            'final_owned_unit_not_terminated')
    require(raw_cleanup['unit_stop']['requested'] is True and raw_cleanup['unit_stop']['returncode'] == 0,
            'owned_unit_stop_not_confirmed')


def audit_qualification(out, *, manifest_sha256, strict=False):
    """Read-only independent closure for this new ownership model, not v2 audit."""
    directory = Path(out).absolute()
    errors = []; rows = []
    try:
        manifest = validate_manifest(directory, manifest_sha256, current=False)
        if not (directory / 'EXECUTION.json').exists():
            return {'ok': not strict, 'status': 'prepared', 'planned_slots': 9, 'qualification_passed': False, 'errors': []}
        execution, _ = load(directory / 'EXECUTION.json')
        require(execution['registered_manifest_sha256'] == manifest_sha256
                and execution['boot_id'] == manifest['boot_id'], 'execution_binding_mismatch')
        for slot in manifest['slots']:
            trial = directory / 'slots' / slot['slot_id']
            if not (trial / 'RECEIPT.json').exists():
                rows.append({'slot_id': slot['slot_id'], 'status': 'missing', 'qualification_passed': False})
                continue
            receipt, receipt_hash = load(trial / 'RECEIPT.json')
            require(receipt['slot'] == slot, 'receipt_slot_mismatch')
            for name, expected in receipt['evidence_sha256'].items():
                path = Path(name)
                require(not path.is_absolute() and '..' not in path.parts and name != 'RECEIPT.json', 'receipt_path_escape')
                require((trial / path).is_file() and not (trial / path).is_symlink()
                        and sha((trial / path).read_bytes()) == expected, 'raw_evidence_changed')
            intent, intent_hash = load(trial / 'INTENT.json')
            require(intent_hash == receipt['intent_sha256'] and intent['slot_id'] == slot['slot_id']
                    and intent['unit'] == slot['unit'] and intent['manifest_sha256'] == manifest_sha256
                    and intent['command_sha256'] == sha(canonical(launch_argv(directory, slot))), 'launch_intent_mismatch')
            require(finite(intent['started_monotonic']) and intent['startup_deadline_monotonic']
                    == intent['started_monotonic'] + CONFIG['startup_seconds'], 'startup_allowance_changed')
            passed = receipt.get('qualification_passed') is True
            if passed or receipt.get('safe_to_continue') is True:
                _completed_evidence(trial, directory, manifest, execution, slot, intent, receipt)
                gate, _ = load(trial / 'GATE.json')
                before, _ = load(trial / 'native/BOUNDARY_BEFORE.json')
                after, _ = load(trial / 'native/BOUNDARY_AFTER.json')
                result, _ = load(trial / 'native/CHILD_RESULT.json')
                phase, _ = load(trial / 'native/STARTUP_FINISHED.json')
                child.verify_boundary(gate['expected_boundary'], before['observed'])
                child.verify_boundary(gate['expected_boundary'], after['observed'])
                require(before['expected'] == gate['expected_boundary']
                        and gate['unit_binding'] == receipt['unit_binding'], 'boundary_binding_mismatch')
                require(result['work_requests_sent'] == 0 and result['provider_credentials_supplied'] is False
                        and receipt['native_inference_requests'] == 0
                        and result['boundary_verified_before_and_after'] is True, 'inference_boundary_not_verified')
                require(phase == receipt['startup_outcome'] and finite(phase['finished_monotonic'])
                        and intent['started_monotonic'] <= phase['finished_monotonic']
                        <= intent['startup_deadline_monotonic'], 'startup_phase_mismatch')
                cleanup = receipt['cleanup']
                require(cleanup['started_monotonic'] == phase['finished_monotonic']
                        and cleanup['deadline_monotonic'] == cleanup['started_monotonic'] + CONFIG['cleanup_seconds']
                        and cleanup['limit_seconds'] == CONFIG['cleanup_seconds']
                        and cleanup['started_monotonic'] <= cleanup['ended_monotonic'] <= cleanup['deadline_monotonic'],
                        'cleanup_allowance_changed')
                require(cleanup['confirmed'] is True and not cleanup['members_remaining'] and not cleanup['errors']
                        and cleanup['socket_cleanup']['confirmed'] is True
                        and cleanup['control_client_exit_code'] is not None
                        and all(x['state'] in ('absent', 'replaced', 'zombie') for x in cleanup['observed_processes']),
                        'cleanup_unconfirmed')
                require(any(same(x['identity'], receipt['unit_binding']['main_identity'])
                            for x in cleanup['observed_processes']), 'native_main_missing_from_cleanup')
                require(passed == (phase['ready_observed'] is True and result['ready_observed'] is True), 'startup_pass_forged')
            rows.append({'slot_id': slot['slot_id'], 'status': receipt['status'],
                         'qualification_passed': passed, 'receipt_sha256': receipt_hash,
                         'safe_to_continue': receipt.get('safe_to_continue') is True,
                         'started_monotonic': intent['started_monotonic'],
                         'ended_monotonic': receipt['cleanup']['ended_monotonic']})
        complete = len(rows) == 9 and all(x.get('safe_to_continue') for x in rows)
        for batch in range(1, len(BATCHES)):
            previous = [r for r, s in zip(rows, manifest['slots']) if s['batch'] == batch - 1 and 'ended_monotonic' in r]
            current_rows = [r for r, s in zip(rows, manifest['slots']) if s['batch'] == batch and 'started_monotonic' in r]
            if previous and current_rows:
                require(min(x['started_monotonic'] for x in current_rows) >= max(x['ended_monotonic'] for x in previous),
                        'batch_barrier_broken')
        if (directory / 'REPORT.json').exists():
            report, _ = load(directory / 'REPORT.json')
            require(report['manifest_sha256'] == manifest_sha256 and report['planned_slots'] == 9
                    and [x['slot'] for x in report['results']] == manifest['slots'], 'report_plan_mismatch')
            for expected_slot, reported in zip(manifest['slots'], report['results']):
                raw_path = directory / 'slots' / expected_slot['slot_id'] / 'RECEIPT.json'
                if raw_path.exists():
                    require(reported == load(raw_path)[0], 'report_receipt_mismatch')
                else:
                    require(reported['status'] in ('skipped_after_stop', 'unresolved')
                            and reported['qualification_passed'] is False
                            and reported['safe_to_continue'] is False, 'report_missing_slot_misrepresented')
            require((report['status'] == 'completed') == complete
                    and report['qualification_passed'] == (complete and all(x['qualification_passed'] for x in rows)),
                    'report_outcome_mismatch')
        elif complete:
            complete = False
        return {'ok': complete or not strict, 'status': 'completed' if complete else 'incomplete',
                'planned_slots': 9, 'slots': rows, 'qualification_passed': complete and all(x['qualification_passed'] for x in rows),
                'errors': errors, 'postprocessor_sha256': sha(Path(__file__).read_bytes())}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
        return {'ok': False, 'status': 'invalid', 'planned_slots': 9, 'slots': rows,
                'qualification_passed': False, 'errors': [{'error_type': type(exc).__name__,
                    'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--execute', action='store_true')
    action.add_argument('--audit', action='store_true')
    action.add_argument('--worker', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resource-probe', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--slot')
    args = parser.parse_args()
    try:
        if args.worker:
            _worker(args.out.absolute(), args.slot)
            return 0
        if args.prepare:
            result = prepare(args.out, resource_probe=args.resource_probe)
        elif args.execute:
            result = execute(args.out, manifest_sha256=args.manifest_sha256)
        else:
            result = audit_qualification(args.out, manifest_sha256=args.manifest_sha256, strict=True)
    except Exception as exc:
        result = {'ok': False, 'error_type': type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('ok', result.get('prepared', False)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
