#!/usr/bin/env python3
"""Bounded four-role native wire preflight, separate from study worlds.

Prepare is offline when the pinned Persona shard is cached. Execute starts only
this checkout's isolated server on port 5002. Private artifacts contain prompts;
stdout and SUMMARY.json contain counts, hashes and safe error classes only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from importlib.metadata import version
import math
import os
from pathlib import Path
import signal
import re
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.actor_contract import audit_interviews, provenance, wire
from lifespan.evaluation.provider import contract as credential_contract, validate_contract
from lifespan.ecosystem_run import native_decision
from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from lifespan.mirofish import MiroFishRuntime, save
from lifespan.personas import import_cohort

URL = 'http://127.0.0.1:5002'
CONTRACT = {'version': 'actor-json-v1', 'max_output_tokens': 4096, 'timeout_seconds': 120}
LIMITS = {'wall_seconds': 900, 'logical_interviews': 8, 'max_repairs_per_actor': 1,
          'output_tokens_per_interview': 4096, 'cleanup_seconds': 120}
MARKER = 'wire witness: "quoted" {braces} \\ path; café\nsecond line'
ROLES = ('employee', 'enterprise', 'government', 'consumer')
TYPES = dict(zip(ROLES, ('Employee', 'Enterprise', 'GovernmentAgency', 'Consumer')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def same(left, right):
    """JSON value types matter: booleans are not integer evidence counts."""
    try:
        return wire.digest(left) == wire.digest(right)
    except (ValueError, TypeError):
        return False


def sources():
    result = source_hashes()
    result['scripts/preflight_actor_contract.py'] = sha(__file__)
    result.update({name: sha(ROOT / name) for name in tracked_overlays()})
    result['patches/mirofish-local.patch'] = sha(ROOT / 'patches/mirofish-local.patch')
    return result


def committed_sources(values, revision=None):
    revision = revision or subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('preflight_invalid_source_commit')
    for name, expected in values.items():
        raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', revision + ':' + name],
                                      stderr=subprocess.DEVNULL, timeout=10)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('preflight_source_not_committed')
    return revision


def dependencies():
    return {'repositories': dependency_provenance(), 'python': {'executable': sys.executable, 'version': sys.version},
            'packages': {name: version(name) for name in ('openai', 'camel-ai', 'httpx', 'pydantic')}}


def tracked_overlays():
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--',
        'local-overrides/backend'], text=True).splitlines()
    expected = {'local-overrides/backend/app/utils/' + name for name in (
        'actor_output_contract.py', 'actor_contract_transport.json', 'camel_responses.py', 'local_graph.py')}
    if set(names) != expected:
        raise ValueError('preflight_tracked_overlay_inventory_changed')
    return sorted(names)


def installation(*, current=True):
    backend = ROOT / 'MiroFish/backend'
    if backend.resolve() != backend or not (backend / 'app/config.py').is_file():
        raise ValueError('preflight_mutable_state_or_module_isolation_failed')
    if current:
        from lifespan.mirofish import imports
        imports()
        import app.config as config
        if (Path(config.__file__).resolve() != backend / 'app/config.py'
                or Path(config.Config.UPLOAD_FOLDER).resolve() != backend / 'uploads'
                or Path(config.Config.LOCAL_GRAPH_DB).resolve() != backend / 'uploads/local_graph.sqlite3'
                or config.Config.GRAPH_BACKEND != 'local'):
            raise ValueError('preflight_mutable_state_or_module_isolation_failed')
    overlays = {}
    for name in tracked_overlays():
        original = ROOT / name
        installed = backend / Path(name).relative_to('local-overrides/backend')
        if (original.is_symlink() or not installed.is_file() or installed.is_symlink()
                or installed.resolve() != installed or sha(original) != sha(installed)):
            raise ValueError('preflight_installed_overlay_missing_or_changed')
        overlays[name] = sha(original)
    return {'backend': str(backend), 'config_module': str(backend / 'app/config.py'),
            'uploads': str(backend / 'uploads'), 'graph_database': str(backend / 'uploads/local_graph.sqlite3'),
            'overlay_sha256': overlays}


def provider(creds):
    result = credential_contract(creds)
    if result is None or result != wire.configured_provider_contract():
        raise ValueError('preflight_explicit_provider_contract_required')
    return result


def config(provider):
    return {'actor_output_contract': CONTRACT, 'max_actor_interviews': 8, 'provider_profile': provider['profile']}


def participants():
    return [{'id': 'preflight-' + role, 'name': 'Synthetic ' + role,
             'entity_type': TYPES[role], 'workflow': 'onboarding', 'segment': 'regulated',
             'role_description': 'Participates only in a transport capability fixture.'}
            for role in ROLES]


def expected(role):
    common = {'notes': MARKER, 'reason': 'Transport capability fixture only.', 'evidence_ids': []}
    return {
        'employee': {'delegate': True, 'request': 'Inspect the supplied fixture.',
                     'working_notes': MARKER, 'share_document_ids': [],
                     'colleague_messages': [], 'process_proposal': None},
        'enterprise': {**common, 'objective': 'reliability', 'price': 10,
                       'target_market': 'domestic', 'priority_workflow': 'onboarding', 'procedure': 'keep'},
        'government': {**common, 'policy': 'keep', 'duration': 4},
        'consumer': {**common, 'action': 'wait', 'firm': None},
    }[role]


def prepare(out):
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT):
        raise ValueError('preflight_output_must_be_in_isolated_checkout')
    out.mkdir(parents=True, exist_ok=False)
    cohort = import_cohort(ROOT / 'lifespan/data/persona8b', out / 'persona_cohort.json', count=4, seed=907)
    creds = credentials()
    bound_provider = provider(creds)
    source_map = sources()
    revision = committed_sources(source_map)
    manifest = {'schema_version': 1, 'kind': 'native_actor_wire_capability_preflight',
        'created_at': datetime.now(timezone.utc).isoformat(), 'limits': LIMITS, 'server_url': URL,
        'roles': list(ROLES), 'participants': participants(),
        'config': config(bound_provider), 'provider_contract': bound_provider,
        'actor_output_contract_provenance': provenance(CONTRACT, expected_provider=bound_provider), 'source_sha256': source_map,
        'repository_commit': revision, 'source_commit_verified': True,
        'dependencies': dependencies(), 'cohort_sha256': sha(out / 'persona_cohort.json'),
        'installation': installation(),
        'cohort_revision': cohort['revision'], 'target_model': creds['model'],
        'model_base_url': creds['base_url'],
        'fixture_sha256': wire.digest({role: expected(role) for role in ROLES}),
        'claims_excluded': ['business decision validity', 'learning quality', 'long-horizon reliability'],
        'accounting_scope': 'Contracted interviews only; graph/bootstrap/social physical usage and currency unknown.'}
    save(out / 'manifest.json', manifest)
    return {'status': 'prepared', 'manifest_sha256': sha(out / 'manifest.json'), 'limits': LIMITS}


def verify(out, manifest_hash, *, current=True):
    if not out.resolve().is_relative_to(ROOT):
        raise ValueError('preflight_output_must_be_in_isolated_checkout')
    if sha(out / 'manifest.json') != manifest_hash:
        raise ValueError('preflight_manifest_hash_mismatch')
    m = read(out / 'manifest.json')
    bound_provider = validate_contract(m['provider_contract'])
    checks = [same(m['source_sha256'], sources()), same(m['dependencies'], dependencies()),
        m.get('source_commit_verified') is True,
        committed_sources(m['source_sha256'], m.get('repository_commit')) == m.get('repository_commit'),
        m['cohort_sha256'] == sha(out / 'persona_cohort.json'), same(m['limits'], LIMITS),
        same(m['roles'], list(ROLES)), same(m['participants'], participants()), m['server_url'] == URL,
        type(m['schema_version']) is int and m['schema_version'] == 1 and m['kind'] == 'native_actor_wire_capability_preflight',
        same(m['config'], config(bound_provider)),
        same(m['actor_output_contract_provenance'], provenance(CONTRACT, expected_provider=bound_provider)),
        m['fixture_sha256'] == wire.digest({role: expected(role) for role in ROLES}),
        same(m['installation'], installation(current=current)),
        wire.provider_contract(m['target_model'], m['model_base_url']) == bound_provider]
    if current:
        c = credentials()
        checks.append(provider(c) == bound_provider)
    if not all(checks):
        raise ValueError('preflight_source_or_configuration_changed')
    wire.require_transport_support(ROOT / 'MiroFish/backend')
    return m


def verify_worker_parent(out, manifest_hash):
    execution = read(out / 'EXECUTION.json')
    server = read(out / 'SERVER.json')
    proc = Path('/proc') / str(server['pid'])
    if (execution['manifest_sha256'] != manifest_hash or execution['supervisor_pid'] != os.getppid()
            or proc.joinpath('stat').read_text().split()[21] != server['start_ticks']
            or proc.joinpath('cwd').resolve() != ROOT / 'MiroFish/backend'):
        raise ValueError('preflight_worker_requires_its_live_supervisor_and_server')
    sockets = set()
    for descriptor in proc.joinpath('fd').iterdir():
        try:
            sockets.add(descriptor.readlink().name)
        except FileNotFoundError:
            pass  # A completed health-check connection can close concurrently.
    rows = [line.split() for line in proc.joinpath('net/tcp').read_text().splitlines()[1:]]
    if not any(row[1] == '0100007F:138A' and row[3] == '0A'
               and 'socket:[' + row[9] + ']' in sockets for row in rows):
        raise ValueError('preflight_server_does_not_own_loopback_port')
    started, deadline = execution['started_monotonic'], execution['deadline_monotonic']
    if (type(started) not in (int, float) or not math.isfinite(started)
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or deadline != started + LIMITS['wall_seconds'] or time.monotonic() >= deadline):
        raise ValueError('preflight_supervisor_deadline_invalid_or_exhausted')
    return deadline


def worker(out, manifest_hash):
    m = verify(out, manifest_hash)
    deadline = verify_worker_parent(out, manifest_hash)
    runtime = None
    try:
        runtime = MiroFishRuntime(out / 'actors', URL, actor_output_contract=CONTRACT)
        runtime.evaluation_deadline = deadline
        runtime.evaluation_max_interviews = LIMITS['logical_interviews']
        runtime.bootstrap({'name': 'Four-role wire capability preflight', 'employees': participants(),
            'rules': [], 'project_name': 'Big World CL transport preflight',
            'ecosystem_description': 'Four fictional entities testing JSON transport; no study work is performed.'},
            read(out / 'persona_cohort.json'))
        results = []
        for role in ROLES:
            value = expected(role)
            prompt = ('This is a transport capability fixture. Return exactly the following JSON object, '
                      'preserving all string characters. Do not call tools or add prose.\n' + json.dumps(value, ensure_ascii=False))
            def check(actual):
                if not same(actual, value):
                    raise ValueError('Fixture fields or escaped witness differ')
            native_decision(runtime, 'preflight-' + role, prompt, 'wire-' + role, check)
            results.append({'role': role, 'exact_fixture_match': True})
            save(out / 'ROLE_RESULTS.json', results)
        audit = audit_interviews(out, m, participants(), completed=True)
        save(out / 'WIRE_RESULT.json', {'status': 'completed', 'roles': results, 'actor_interviews': audit})
    except BaseException as exc:
        save(out / 'WORKER_FAILURE.json', {'error_class': type(exc).__name__})
        raise
    finally:
        if runtime is not None:
            runtime.client.close()


def request(path, body=None, timeout=5):
    req = Request(URL + path, data=None if body is None else json.dumps(body).encode(),
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def terminate(process):
    if process is None:
        return {'status': 'not_started'}
    if process.poll() is not None:
        return {'status': 'exited', 'exit_code': process.returncode}
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # Process may exit between poll and killpg.
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    return {'status': 'exited', 'exit_code': process.returncode}


def evidence_inventory(out):
    """Private relative inventory, including raw native claims/receipts and DBs."""
    inventories = {}
    for label, root in (('preflight', out), ('native_uploads', ROOT / 'MiroFish/backend/uploads')):
        entries = {}
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise ValueError('preflight_evidence_symlink')
            if path.is_file() and not (label == 'preflight' and path.name in ('SUMMARY.json', 'EVIDENCE.json')):
                before = path.stat()
                value = sha(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('preflight_evidence_changed_during_inventory')
                entries[str(path.relative_to(root))] = value
        inventories[label] = entries
    return {'schema_version': 1, 'kind': 'private_native_preflight_evidence_inventory', 'files': inventories}


def observe_native(out, *, proc_root=Path('/proc')):
    path = out / 'actors/mirofish_state.json'
    if not path.exists() or 'simulation' not in read(path):
        return {'status': 'not_started'}
    simulation = read(path)['simulation']['simulation_id']
    directory = ROOT / 'MiroFish/backend/uploads/simulations' / simulation
    if not directory.resolve().is_relative_to(ROOT / 'MiroFish/backend/uploads/simulations'):
        raise ValueError('preflight_native_directory_invalid')
    state = directory / 'run_state.json'
    if not state.exists():
        return {'status': 'unknown_native_identity'}
    pid = read(state).get('process_pid')
    if type(pid) is not int or pid <= 0:
        return {'status': 'unknown_native_identity'}
    proc = proc_root / str(pid)
    if not proc.exists():
        return {'status': 'exited', 'pid': pid}
    stat = proc.joinpath('stat').read_text().split()
    if stat[2] == 'Z':
        return {'status': 'exited', 'pid': pid}
    argv = [item.decode() for item in proc.joinpath('cmdline').read_bytes().split(b'\0') if item]
    if (proc.joinpath('cwd').resolve() != directory
            or len(argv) < 4 or argv[2] != '--config'
            or Path(argv[1]).resolve() != ROOT / 'MiroFish/backend/scripts/run_reddit_simulation.py'
            or Path(argv[3]).resolve() != directory / 'simulation_config.json'
            or os.getpgid(pid) != pid):
        return {'status': 'unknown_native_identity'}
    return {'status': 'observed_live', 'pid': pid, 'start_ticks': stat[21],
            'simulation_id': simulation, 'cwd': str(directory)}


def native_gone(observation):
    proc = Path('/proc') / str(observation['pid'])
    try:
        stat = proc.joinpath('stat').read_text().split()
    except FileNotFoundError:
        return True
    return stat[2] == 'Z' or stat[21] != observation['start_ticks']


def finish_native(observation):
    if observation['status'] in ('exited', 'not_started'):
        return observation
    if observation['status'] != 'observed_live':
        return {'status': 'cleanup_unconfirmed', 'reason': 'unknown_native_identity'}
    forced = []
    # File-based env-status may say stopped before OASIS awaits env.close().
    # Give it time to exit, then stop only the process group observed above.
    for wait, signum in ((5, None), (5, signal.SIGTERM), (5, signal.SIGKILL)):
        if native_gone(observation):
            return {'status': 'exited', 'forced_signals': forced}
        if signum is not None:
            try:
                group = os.getpgid(observation['pid'])
            except ProcessLookupError:
                return {'status': 'exited', 'forced_signals': forced}
            if group != observation['pid']:
                return {'status': 'cleanup_unconfirmed', 'reason': 'native_process_group_changed'}
            try:
                os.killpg(observation['pid'], signum)
                forced.append(signum.name)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if native_gone(observation):
                return {'status': 'exited', 'forced_signals': forced}
            time.sleep(0.1)
    return {'status': 'cleanup_unconfirmed', 'forced_signals': forced}


def cleanup_actor(out):
    path = out / 'actors/mirofish_state.json'
    if not path.exists() or 'simulation' not in read(path):
        return {'status': 'no_recorded_environment'}
    simulation_id = read(path)['simulation']['simulation_id']
    # This ID belongs to this preflight's fresh server and manifest directory.
    result = {'status': 'close_unconfirmed', 'simulation_id': simulation_id}
    try:
        request('/api/simulation/close-env', {'simulation_id': simulation_id, 'timeout': 15}, timeout=25)
        reply = request('/api/simulation/env-status', {'simulation_id': simulation_id}, timeout=10)
        if reply.get('success') is True and reply.get('data', {}).get('env_alive') is False:
            result['status'] = 'closed'
    except Exception as exc:
        result['error_class'] = type(exc).__name__
    if result['status'] != 'closed':
        # The server owns only this fresh preflight. Stop its recorded simulation
        # process group if a pending interview prevents graceful close.
        result['forced_stop_requested'] = True
        try:
            try:
                request('/api/simulation/stop', {'simulation_id': simulation_id}, timeout=20)
            except Exception as exc:
                result['stop_error_class'] = type(exc).__name__
            reply = request('/api/simulation/env-status', {'simulation_id': simulation_id}, timeout=5)
            if reply.get('success') is True and reply.get('data', {}).get('env_alive') is False:
                result['status'] = 'closed'
        except Exception as exc:
            result['verification_error_class'] = type(exc).__name__
    return result


def execute(out, manifest_hash):
    m = verify(out, manifest_hash)
    # Binding is deliberately limited to an unused loopback port and fresh
    # checkout. Never attach this test to the existing campaign's port 5001.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 5002))
    backend = ROOT / 'MiroFish/backend'
    if (backend / 'uploads').exists() and any((backend / 'uploads').iterdir()):
        raise ValueError('preflight_requires_fresh_backend_uploads')
    started = time.monotonic()
    with (out / 'EXECUTION.json').open('x') as handle:
        json.dump({'manifest_sha256': manifest_hash, 'started_at': datetime.now(timezone.utc).isoformat(),
                   'supervisor_pid': os.getpid(), 'started_monotonic': started,
                   'deadline_monotonic': started + LIMITS['wall_seconds']}, handle)
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', FLASK_HOST='127.0.0.1',
        FLASK_PORT='5002', FLASK_DEBUG='False', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false',
        HF_HUB_CACHE=str(ROOT / 'models/embedding-cache'), TIKTOKEN_CACHE_DIR=str(ROOT / 'models/tiktoken'),
        LOCAL_GRAPH_DB=str(backend / 'uploads/local_graph.sqlite3'))
    server = child = None
    result = {'status': 'failed', 'manifest_sha256': manifest_hash,
              'provider_contract': m['provider_contract'],
              'claims_excluded': m['claims_excluded'], 'accounting_scope': m['accounting_scope']}
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    old = signal.signal(signal.SIGTERM, interrupted)
    try:
        with (out / 'backend.log').open('xb') as log:
            server = subprocess.Popen([sys.executable, 'run.py'], cwd=backend, env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        save(out / 'SERVER.json', {'pid': server.pid,
            'start_ticks': Path(f'/proc/{server.pid}/stat').read_text().split()[21], 'url': URL})
        ready = False
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError('isolated_server_exited')
            try:
                request('/health', timeout=1)
                ready = True
                break
            except Exception:
                time.sleep(1)
        if not ready:
            raise TimeoutError('isolated_server_start_deadline')
        with (out / 'worker.log').open('xb') as log:
            child = subprocess.Popen([sys.executable, __file__, 'worker', '--out', str(out),
                '--manifest-sha256', manifest_hash], cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        save(out / 'WORKER.json', {'pid': child.pid,
            'start_ticks': Path(f'/proc/{child.pid}/stat').read_text().split()[21]})
        result['worker_exit_code'] = child.wait(timeout=max(1, LIMITS['wall_seconds'] - (time.monotonic() - started)))
        if result['worker_exit_code'] == 0:
            result.update(read(out / 'WIRE_RESULT.json'))
    except BaseException as exc:
        result['error_class'] = type(exc).__name__
    finally:
        cleanup_started = time.monotonic()
        result['execution_elapsed_seconds'] = cleanup_started - started
        result['execution_started_monotonic'] = started
        result['cleanup_started_monotonic'] = cleanup_started
        try:
            try:
                result['worker_cleanup'] = terminate(child)
            except BaseException as exc:
                result['worker_cleanup'] = {'status': 'cleanup_unconfirmed', 'error_class': type(exc).__name__}
            try:
                native = observe_native(out)
                save(out / 'NATIVE_PROCESS.json', native)
            except BaseException as exc:
                native = {'status': 'unknown_native_identity', 'error_class': type(exc).__name__}
            for key, function in (('actor_cleanup', lambda: cleanup_actor(out)), ('server_cleanup', lambda: terminate(server)),
                    ('native_process_cleanup', lambda: finish_native(native))):
                try:
                    result[key] = function()
                except BaseException as exc:
                    result[key] = {'status': 'cleanup_unconfirmed', 'error_class': type(exc).__name__}
            result['elapsed_seconds'] = time.monotonic() - started
            result['cleanup_elapsed_seconds'] = time.monotonic() - cleanup_started
            if (result['execution_elapsed_seconds'] > LIMITS['wall_seconds']
                    or result['cleanup_elapsed_seconds'] > LIMITS['cleanup_seconds']):
                result['status'] = 'deadline_exceeded'
            if (result['actor_cleanup']['status'] not in ('closed', 'no_recorded_environment')
                    or any(result[k]['status'] not in ('exited', 'not_started') for k in ('worker_cleanup', 'server_cleanup'))):
                result['status'] = 'cleanup_unconfirmed'
            if result['native_process_cleanup']['status'] not in ('exited', 'not_started'):
                result['status'] = 'cleanup_unconfirmed'
            try:
                inventory = evidence_inventory(out)
                save(out / 'EVIDENCE.json', inventory)
                result['evidence_inventory_sha256'] = sha(out / 'EVIDENCE.json')
                result['evidence_files'] = {k: len(v) for k, v in inventory['files'].items()}
            except BaseException as exc:
                result['status'] = 'evidence_inventory_failed'
                result['evidence_error_class'] = type(exc).__name__
            end = time.monotonic()
            result.update(finished_monotonic=end, elapsed_seconds=end - started,
                          cleanup_elapsed_seconds=end - cleanup_started)
            if (result['execution_elapsed_seconds'] > LIMITS['wall_seconds']
                    or result['cleanup_elapsed_seconds'] > LIMITS['cleanup_seconds']):
                result['status'] = 'deadline_exceeded'
            save(out / 'SUMMARY.json', result)
        finally:
            signal.signal(signal.SIGTERM, old)
    return result


def audit(out, *, manifest_sha256, strict=False):
    """Read-only completed-proof reconstruction; no credentials, /proc or HTTP.

    Provider usage is local receipt evidence, not remote authentication. The
    fixed fixtures qualify wire transport only, never business or learning.
    Recorded process cleanup is checked; current host liveness is not inferred.
    """
    out = Path(out).resolve()
    result = {'ok': False, 'verified': False, 'status': 'incomplete', 'errors': [],
              'manifest_sha256': manifest_sha256, 'actor_interviews': None}
    try:
        m = verify(out, manifest_sha256, current=False)
        result['provider_contract'] = m['provider_contract']
        result['roles'] = list(ROLES)
        result['accounting_scope'] = 'Reconciled contracted client receipts only; native orphan receipts and bootstrap/social all-in costs remain outside this meter.'
        if (out / 'actors/evaluation_interview_ledger.json').is_file() and (out / 'actors/mirofish_state.json').is_file():
            try:
                result['actor_interviews'] = audit_interviews(out, m, participants(), completed=False)
            except (OSError, ValueError, KeyError, TypeError, wire.ContractError) as exc:
                result['accounting_error_class'] = type(exc).__name__
        if not (out / 'SUMMARY.json').is_file() or not (out / 'EVIDENCE.json').is_file():
            if strict: raise ValueError('preflight_completed_evidence_required')
            return result
        summary = read(out / 'SUMMARY.json')
        result['summary_sha256'] = sha(out / 'SUMMARY.json')
        result['evidence_inventory_sha256'] = sha(out / 'EVIDENCE.json')
        if (summary.get('status') != 'completed' or summary.get('manifest_sha256') != manifest_sha256
                or validate_contract(summary.get('provider_contract')) != m['provider_contract']
                or summary.get('worker_exit_code') != 0 or type(summary.get('worker_exit_code')) is not int
                or summary.get('evidence_inventory_sha256') != result['evidence_inventory_sha256']):
            raise ValueError('preflight_summary_not_completed_or_bound')
        original_inventory = read(out / 'EVIDENCE.json')
        if (not same(original_inventory, evidence_inventory(out))
                or not same(summary.get('evidence_files'), {key: len(value) for key, value in original_inventory['files'].items()})):
            raise ValueError('preflight_raw_inventory_changed')
        execution = read(out / 'EXECUTION.json')
        start = execution.get('started_monotonic')
        if (execution.get('manifest_sha256') != manifest_sha256
                or type(start) not in (int, float) or not math.isfinite(start) or start < 0
                or not same(execution.get('deadline_monotonic'), start + LIMITS['wall_seconds'])
                or not same(summary.get('execution_started_monotonic'), start)):
            raise ValueError('preflight_execution_binding_mismatch')
        server, worker, native_process = (read(out / name) for name in ('SERVER.json', 'WORKER.json', 'NATIVE_PROCESS.json'))
        if (server.get('url') != URL or any(type(item.get('pid')) is not int or item['pid'] <= 0
                or type(item.get('start_ticks')) is not str or not item['start_ticks'].isdigit() for item in (server, worker))
                or server['pid'] == worker['pid'] or type(execution.get('supervisor_pid')) is not int
                or execution['supervisor_pid'] <= 0 or execution['supervisor_pid'] in (server['pid'], worker['pid'])
                or native_process.get('status') not in ('observed_live', 'exited')
                or type(native_process.get('pid')) is not int or native_process['pid'] <= 0):
            raise ValueError('preflight_process_identity_evidence_missing')
        for field, limit in (('execution_elapsed_seconds', LIMITS['wall_seconds']),
                             ('cleanup_elapsed_seconds', LIMITS['cleanup_seconds'])):
            value = summary.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= limit:
                raise ValueError('preflight_deadline_or_timing_unknown')
        total = summary.get('elapsed_seconds')
        cleanup_start, end = summary.get('cleanup_started_monotonic'), summary.get('finished_monotonic')
        if (type(total) not in (int, float) or not math.isfinite(total)
                or type(cleanup_start) not in (int, float) or not math.isfinite(cleanup_start)
                or type(end) not in (int, float) or not math.isfinite(end)
                or not start <= cleanup_start <= end
                or abs(cleanup_start - start - summary['execution_elapsed_seconds']) > .01
                or abs(end - cleanup_start - summary['cleanup_elapsed_seconds']) > .01
                or abs(total - summary['execution_elapsed_seconds'] - summary['cleanup_elapsed_seconds']) > .01):
            raise ValueError('preflight_total_timing_disagreement')
        if (summary.get('actor_cleanup', {}).get('status') != 'closed'
                or any(summary.get(name, {}).get('status') != 'exited' for name in
                       ('worker_cleanup', 'server_cleanup', 'native_process_cleanup'))):
            raise ValueError('preflight_cleanup_unconfirmed')
        if not same(summary['worker_cleanup'].get('exit_code'), summary['worker_exit_code']):
            raise ValueError('preflight_worker_cleanup_exit_disagreement')
        roles = [{'role': role, 'exact_fixture_match': True} for role in ROLES]
        wire_result = read(out / 'WIRE_RESULT.json')
        if (wire_result.get('status') != 'completed' or wire.digest(wire_result.get('roles')) != wire.digest(roles)
                or wire.digest(read(out / 'ROLE_RESULTS.json')) != wire.digest(roles)
                or wire.digest(summary.get('roles')) != wire.digest(roles)):
            raise ValueError('preflight_fixed_role_results_incomplete')
        measured = audit_interviews(out, m, participants(), completed=True)
        if not same(measured, summary.get('actor_interviews')) or not same(measured, wire_result.get('actor_interviews')):
            raise ValueError('preflight_summary_usage_disagreement')
        state = read(out / 'actors/mirofish_state.json')
        native = wire.simulation_path(ROOT / 'MiroFish/backend/uploads/simulations', state['simulation']['simulation_id'])
        if summary['actor_cleanup'].get('simulation_id') != native.name:
            raise ValueError('preflight_cleanup_simulation_mismatch')
        if native_process['status'] == 'observed_live' and (
                native_process.get('simulation_id') != native.name or native_process.get('cwd') != str(native)
                or type(native_process.get('start_ticks')) is not str or not native_process['start_ticks'].isdigit()):
            raise ValueError('preflight_native_process_binding_mismatch')
        ledger = read(out / 'actors/evaluation_interview_ledger.json')['requests']
        keys = {row['key'] for row in ledger}
        originals = {'wire-' + role for role in ROLES}
        if not originals <= keys or not keys <= originals | {key + '-repair' for key in originals}:
            raise ValueError('preflight_unplanned_interview')
        expected_claims, expected_receipts, rowids = set(), set(), set()
        for row in ledger:
            record = read(out / 'actors/mirofish_interviews' / (row['key'] + '.json'))
            value = record['native_result']['result']
            if 'reddit' in value: value = value['reddit']
            receipt = value['actor_output_receipt']; binding = receipt['binding']
            request_key, request_id = binding['request_key'], binding['request_id']
            expected_claims.add(request_key + '.json'); expected_receipts.add(request_id + '.json')
            if (not same(read(native / 'actor_contract_receipts' / (request_id + '.json')), receipt)
                    or not same(read(native / 'actor_contract_claims' / (request_key + '.json')),
                        {'request_key': request_key, 'request_id': request_id})):
                raise ValueError('preflight_native_receipt_or_claim_mismatch')
            with sqlite3.connect((native / 'reddit_simulation.db').as_uri() + '?mode=ro', uri=True) as database:
                trace = database.execute('SELECT user_id, action, info, created_at FROM trace WHERE rowid=?',
                                         (value['trace_rowid'],)).fetchall()
            if len(trace) != 1:
                raise ValueError('preflight_native_trace_missing')
            actor, action, raw, timestamp = trace[0]; info = json.loads(raw)
            if (actor != binding['agent_id'] or action != 'interview' or timestamp != value['timestamp']
                    or info['response'] != record['response']
                    or wire.text_hash(info['prompt']) != binding['native_prompt_sha256']):
                raise ValueError('preflight_native_trace_mismatch')
            rowids.add(value['trace_rowid'])
        if (len(rowids) != len(ledger)
                or {p.name for p in (native / 'actor_contract_claims').iterdir()} != expected_claims
                or {p.name for p in (native / 'actor_contract_receipts').iterdir()} != expected_receipts):
            raise ValueError('preflight_unreconciled_native_requests')
        with sqlite3.connect((native / 'reddit_simulation.db').as_uri() + '?mode=ro', uri=True) as database:
            native_interviews = database.execute("SELECT COUNT(*) FROM trace WHERE action='interview'").fetchone()[0]
        if native_interviews != len(ledger):
            raise ValueError('preflight_unreconciled_native_interview_trace')
        for role in ROLES:
            key = 'wire-' + role
            if key + '-repair' in keys: key += '-repair'
            record = read(out / 'actors/mirofish_interviews' / (key + '.json'))
            if not wire.shape_valid(record['response'], role) or not same(json.loads(record['response']), expected(role)):
                raise ValueError('preflight_exact_fixture_mismatch')
        if (not same(original_inventory, evidence_inventory(out)) or result['summary_sha256'] != sha(out / 'SUMMARY.json')
                or result['evidence_inventory_sha256'] != sha(out / 'EVIDENCE.json')
                or not same(m['source_sha256'], sources()) or not same(m['dependencies'], dependencies())
                or not same(m['installation'], installation(current=False))):
            raise ValueError('preflight_evidence_changed_during_audit')
        result.update(ok=True, verified=True, status='completed', actor_interviews=measured)
    except (OSError, ValueError, KeyError, TypeError, wire.ContractError, sqlite3.Error, subprocess.SubprocessError) as exc:
        code = str(exc)
        result.update(status='invalid', errors=[code if code.replace('_', '').isalnum() and len(code) < 120 else type(exc).__name__])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'execute', 'worker', 'audit'))
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    out = args.out.resolve()
    if args.mode == 'prepare':
        result = prepare(out)
    else:
        if not args.manifest_sha256:
            parser.error('--manifest-sha256 required')
        result = (worker(out, args.manifest_sha256) if args.mode == 'worker' else
                  audit(out, manifest_sha256=args.manifest_sha256, strict=True) if args.mode == 'audit' else execute(out, args.manifest_sha256))
    if result is not None:
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] in ('prepared', 'completed') else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
