"""Inner six-world supervisor, callable only through the reviewed outer scope gate.

No independent CLI or native launch fallback. The outer controller stays this
actual process, retaining v2 service/world direct parentage. It owns final scope
release/audit; this module reports only inner execution and cleanup receipts.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import math
import os
import re
from pathlib import Path
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from scripts import scale_v3_contract as contract
from scripts import scale_v2_process as process
from scripts.prepare_scale_v3 import tooling

LAUNCH_LIMITS = contract.LAUNCH_LIMITS


def utc():
    return datetime.now(timezone.utc).isoformat()


def validate_worker_gate(directory, *, campaign_sha256, scope_gate):
    # Lazy import avoids an import cycle, never an optional production gate.
    from scripts.run_scale_v3 import validate_worker_gate as validate
    return validate(directory, campaign_sha256=campaign_sha256, scope_gate=scope_gate)


def verify_prerequisites(campaign, paths):
    from scripts.run_scale_v3 import verify_prerequisites as verify
    return verify(campaign, paths)


def committed_sources(sources, tools):
    """Bind executed files to a Git revision, allowing unrelated documentation."""
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        contract.require(re.fullmatch('[0-9a-f]{40}', revision), 'execution_commit_identity')
        for name, expected in {**sources, **tools}.items():
            contract.require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                             'execution_source_path')
            raw = subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT,
                                          stderr=subprocess.DEVNULL, timeout=10)
            contract.require(hashlib.sha256(raw).hexdigest() == expected == contract.sha(ROOT / name),
                             'execution_source_not_committed')
    except (OSError, subprocess.SubprocessError):
        raise ValueError('execution_source_commit_unavailable') from None
    return revision


def runtime_binding(campaign):
    sources, tools, deps = source_hashes(), tooling(), dependency_provenance()
    contract.require(contract.same(sources, campaign['source_sha256']) and
                     contract.same(tools, campaign['registration_tools_sha256']) and
                     contract.same(deps, campaign['dependencies']), 'execution_provenance_changed')
    return sources, tools, deps


@contextmanager
def interrupt_control(event):
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda *_: event.set())
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def monitor_world(handle, run, service, *, stop, wall_seconds):
    """Own one handle through cleanup; no world-level retry or budget renewal."""
    reason = 'exited'; failure = None
    interval = LAUNCH_LIMITS['observation_interval_seconds']
    try:
        while True:
            process.observe_world(handle, run, service)
            if handle.poll() is not None:
                break
            if stop.is_set():
                reason = 'supervisor_interrupted'; break
            # Leave one observation interval before the registered hard ceiling.
            # OS scheduling delays can still invalidate the receipt; they never
            # grant extra accepted execution time in the independent audit.
            remaining = handle.started_monotonic + wall_seconds - interval - time.monotonic()
            if remaining <= 0:
                reason = 'wall_limit'; break
            stop.wait(min(interval, remaining))
    except Exception as exc:
        reason = 'observation_failed'; failure = type(exc).__name__
    finally:
        if reason != 'exited' or handle.poll() != 0:
            stop.set()
        cleanup = process.cleanup_world(handle, run, service,
            timeout_seconds=LAUNCH_LIMITS['world_cleanup_seconds'])
    if cleanup.get('status') != 'confirmed':
        stop.set()
    result = {'run_id': run.name, 'exit_code': handle.poll(),
        'elapsed_seconds': cleanup['ended_monotonic'] - handle.started_monotonic,
        'termination_reason': reason, 'lifecycle': {
            'start_sha256': contract.sha(handle.receipt_dir / 'WORLD_START.json'),
            'cleanup_sha256': contract.sha(handle.receipt_dir / 'WORLD_CLEANUP.json')},
        'cleanup_confirmed': cleanup.get('status') == 'confirmed'}
    if failure is not None:
        process.save(handle.receipt_dir / 'SUPERVISION_FAILURE.json',
                     {'schema_version': 1, 'error_type': failure}, exclusive=True)
    return result


def result_envelope(campaign_sha256, rows, slots):
    by_id = {row['run_id']: row for row in rows}
    return {'schema_version': 3, 'campaign_sha256': campaign_sha256,
            'runs': [by_id[s['run_id']] for s in slots if s['run_id'] in by_id]}



def normal_world(row):
    return (type(row.get('exit_code')) is int and row['exit_code'] == 0 and
            row.get('termination_reason') == 'exited' and row.get('cleanup_confirmed') is True)


def status_envelope(slots, rows, started, active, *, stopped, terminal=False):
    completed = {row['run_id'] for row in rows}
    return {'schema_version': 3, 'as_of': utc(), 'planned_worlds': 6,
        'started_worlds': len(started), 'terminal_worlds': len(rows),
        'active_worlds': list(active), 'interruption_requested': stopped,
        'slots': [{'run_id': slot['run_id'], 'wave': index // 2,
                   'status': ('terminal' if slot['run_id'] in completed else
                              'active' if slot['run_id'] in active else
                              'started_without_terminal' if slot['run_id'] in started else
                              'unlaunched' if terminal else 'pending')}
                  for index, slot in enumerate(slots)]}


def execute(directory, *, campaign_sha256, prerequisite_paths, scope_gate):
    # This must precede credential access, source imports in the outer worker,
    # installation inspection and every service/world dispatch.
    gate = validate_worker_gate(directory, campaign_sha256=campaign_sha256, scope_gate=scope_gate)
    entered = time.monotonic()
    start, deadline = gate['execution_started_monotonic'], gate['execution_deadline']
    contract.require(all(type(x) in (int, float) and math.isfinite(x) for x in (start, deadline)) and
        0 <= start <= entered < deadline and
        deadline == start + contract.SCOPE_LIMITS['execution_seconds'], 'scope_execution_clock')
    directory = process.private_path(directory).resolve()
    gate_path = contract.child(directory, 'scope/GATE.json')
    contract.require(contract.sha(gate_path) == gate['scope_gate_sha256'], 'scope_gate_raw_binding')
    creds = credentials()
    sources, tools, deps = source_hashes(), tooling(), dependency_provenance()
    campaign = contract.validate(directory, source_sha256=sources, dependencies=deps,
        registration_tools_sha256=tools, campaign_sha256=campaign_sha256,
        target_model=creds['model'], model_base_url=creds['base_url'], require_pristine=True)
    revision = committed_sources(sources, tools)
    prerequisites = verify_prerequisites(campaign, prerequisite_paths)
    contract.require(prerequisites.get('verified') is True, 'native_prerequisites_not_verified')
    binding = process.validate_installation(worktree=ROOT,
        service_url=campaign['launch_policy']['mirofish_service_url'])
    supervisor = process.identity(os.getpid())
    contract.require(supervisor is not None and not supervisor.get('unreadable'), 'supervisor_identity_unavailable')
    process.save(directory / 'PREREQUISITES.json', prerequisites, exclusive=True)
    process.save(directory / 'EXECUTION.json', {'schema_version': 3, 'kind': 'scale-v3-native-execution',
        'campaign_sha256': campaign_sha256, 'workers': 2, 'started_at': utc(),
        'started_monotonic': start, 'execution_deadline': deadline,
        'scope_gate_sha256': gate['scope_gate_sha256'],
        'supervisor_pid': os.getpid(), 'supervisor_identity': supervisor,
        'source_sha256': sources, 'registration_tools_sha256': tools, 'dependencies': deps,
        'repository_commit': revision, 'source_commit_verified': True,
        'prerequisites_sha256': contract.sha(directory / 'PREREQUISITES.json'),
        'installation': binding, 'prerequisite_paths': prerequisite_paths}, exclusive=True)
    stop = threading.Event(); active = {}; rows = []; started = []; service = None
    failure = None; cleanup = None; slots = campaign['slots']
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='world-supervisor')
    reserve = LAUNCH_LIMITS['world_cleanup_seconds'] + LAUNCH_LIMITS['service_cleanup_seconds']
    work_deadline = deadline - reserve

    def persist(terminal=False):
        process.save(directory / 'execution_results.json', result_envelope(campaign_sha256, rows, slots))
        process.save(directory / 'STATUS.json', status_envelope(slots, rows, started, list(active.values()),
                     stopped=stop.is_set(), terminal=terminal))

    def settle(future):
        nonlocal failure
        run_id = active.pop(future)
        try:
            row = future.result()
            contract.require(row['run_id'] == run_id, 'world_result_identity')
            rows.append(row)
            if not normal_world(row):
                failure = failure or 'WorldExecutionFailed'; stop.set()
        except BaseException as exc:
            failure = failure or type(exc).__name__; stop.set()

    with interrupt_control(stop):
        try:
            contract.require(time.monotonic() + LAUNCH_LIMITS['service_startup_seconds'] < work_deadline,
                             'campaign_startup_window_exhausted')
            runtime_binding(campaign)
            service = process.start_service(binding, directory,
                startup_seconds=LAUNCH_LIMITS['service_startup_seconds'])
            for wave in range(3):
                if stop.is_set(): break
                contract.require(not active and len(rows) == 2 * wave and all(normal_world(row) for row in rows),
                                 'prior_pair_not_complete')
                # A full next wave must fit. Refusal is an explicit missing slot,
                # never a shortened native allocation or renewed wall clock.
                required = campaign['launch_policy']['per_world_wall_seconds'] + reserve
                contract.require(time.monotonic() + required <= deadline, 'campaign_wave_window_exhausted')
                for slot in slots[2 * wave:2 * wave + 2]:
                    if stop.is_set(): break
                    process.verify_service(service)
                    runtime_binding(campaign)
                    contract.require(time.monotonic() + required <= deadline, 'campaign_wave_window_exhausted')
                    run = directory / slot['relative_path']
                    handle = process.spawn_world(run_dir=run, receipt_dir=run / 'lifecycle')
                    started.append(slot['run_id'])
                    try:
                        future = pool.submit(monitor_world, handle, run, service, stop=stop,
                            wall_seconds=campaign['launch_policy']['per_world_wall_seconds'])
                    except BaseException:
                        process.cleanup_world(handle, run, service,
                            timeout_seconds=LAUNCH_LIMITS['world_cleanup_seconds'])
                        raise
                    active[future] = slot['run_id']
                    persist()
                while active:
                    if time.monotonic() >= work_deadline:
                        failure = failure or 'CampaignWallLimit'; stop.set()
                    if not stop.is_set(): process.verify_service(service)
                    for future in list(active):
                        if future.done(): settle(future)
                    persist()
                    if active: time.sleep(LAUNCH_LIMITS['observation_interval_seconds'])
                # This barrier includes cleanup, not merely native root exit.
                if stop.is_set(): break
        except BaseException as exc:
            failure = failure or type(exc).__name__; stop.set()
        finally:
            # SIGTERM/SIGINT are still nonthrowing while all per-world monitors
            # perform their existing bounded cleanup, before shared service stop.
            for future in list(active): settle(future)
            try:
                pool.shutdown(wait=True, cancel_futures=False)
            except BaseException as exc:
                failure = failure or type(exc).__name__
            if service is not None:
                try:
                    cleanup = process.cleanup_service(service,
                        timeout_seconds=LAUNCH_LIMITS['service_cleanup_seconds'])
                    if cleanup.get('status') != 'confirmed': failure = failure or 'ServiceCleanupUnconfirmed'
                except BaseException as exc:
                    failure = failure or type(exc).__name__
            finished = time.monotonic()
            if finished > deadline: failure = failure or 'CampaignWallLimit'
            completed = (failure is None and not stop.is_set() and len(rows) == 6 and
                         all(normal_world(row) for row in rows) and cleanup is not None and
                         cleanup.get('status') == 'confirmed')
            if not completed:
                stop.set()
                process.save(directory / 'SUPERVISOR_INTERRUPTED.json', {'schema_version': 3,
                    'finished_at': utc(), 'error_type': failure, 'started_worlds': len(started),
                    'terminal_worlds': len(rows)}, exclusive=True)
            persist(terminal=True)
            results_hash = contract.sha(directory / 'execution_results.json')
            # Include final status/result persistence and hashing in the inner
            # clock; the outer observer independently times the actual return.
            finished = time.monotonic()
            if finished > deadline and completed:
                completed = False; failure = 'CampaignWallLimit'; stop.set()
                process.save(directory / 'SUPERVISOR_INTERRUPTED.json', {'schema_version': 3,
                    'finished_at': utc(), 'error_type': failure, 'started_worlds': len(started),
                    'terminal_worlds': len(rows)}, exclusive=True)
                persist(terminal=True)
                results_hash = contract.sha(directory / 'execution_results.json')
                finished = time.monotonic()
    # This is not an audit decision. The outer scope lifecycle and independent
    # full-six audit remain mandatory even when this inner return is normal.
    return {'schema_version': 3, 'inner_completed': completed, 'error_type': failure,
            'started_monotonic': start, 'execution_deadline': deadline, 'finished_monotonic': finished,
            'planned_worlds': 6, 'started_worlds': len(started), 'terminal_worlds': len(rows),
            'normal_worlds': sum(normal_world(row) for row in rows),
            'service_cleanup_confirmed': cleanup is not None and cleanup.get('status') == 'confirmed',
            'execution_results_sha256': results_hash}
