#!/usr/bin/env python3
"""Execute one separately reviewed six-world registration without retries.

Each world has its own observation/deadline/cleanup thread. All model work runs
in canonical native subprocesses. Only the main thread owns the shared service
and signals; every spawned world is cleaned before that service is stopped.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from scripts import scale_v2_contract as contract
from scripts import scale_v2_process as process
from scripts.prepare_scale_v2 import tooling
from scripts.scale_v2_prerequisites import verify_prerequisites

LAUNCH_LIMITS = contract.LAUNCH_LIMITS


def utc():
    return datetime.now(timezone.utc).isoformat()


def committed_sources(sources, tools):
    """Bind executed files to a Git revision, allowing unrelated documentation."""
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            stderr=subprocess.DEVNULL, timeout=10).decode().strip()
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
        cleanup = process.cleanup_world(handle, run, service,
            timeout_seconds=LAUNCH_LIMITS['world_cleanup_seconds'])
    result = {'run_id': run.name, 'exit_code': handle.poll(),
        'elapsed_seconds': cleanup['ended_monotonic'] - handle.started_monotonic,
        'termination_reason': reason, 'lifecycle': {
            'start_sha256': contract.sha(handle.receipt_dir / 'WORLD_START.json'),
            'cleanup_sha256': contract.sha(handle.receipt_dir / 'WORLD_CLEANUP.json')}}
    if failure is not None:
        process.save(handle.receipt_dir / 'SUPERVISION_FAILURE.json',
                     {'schema_version': 1, 'error_type': failure}, exclusive=True)
    return result


def result_envelope(campaign_sha256, rows, slots):
    by_id = {row['run_id']: row for row in rows}
    return {'schema_version': 2, 'campaign_sha256': campaign_sha256,
            'runs': [by_id[s['run_id']] for s in slots if s['run_id'] in by_id]}


def execute(directory, *, campaign_sha256, prerequisite_paths):
    directory = process.private_path(directory).resolve()
    creds = credentials()
    sources, tools, deps = source_hashes(), tooling(), dependency_provenance()
    campaign = contract.validate(directory, source_sha256=sources, dependencies=deps,
        registration_tools_sha256=tools, campaign_sha256=campaign_sha256,
        target_model=creds['model'], model_base_url=creds['base_url'], require_pristine=True)
    revision = committed_sources(sources, tools)
    prerequisites = verify_prerequisites(campaign, prerequisite_paths)
    binding = process.validate_installation(worktree=ROOT,
        service_url=campaign['launch_policy']['mirofish_service_url'])
    supervisor = process.identity(os.getpid())
    contract.require(supervisor is not None and not supervisor.get('unreadable'), 'supervisor_identity_unavailable')
    process.save(directory / 'PREREQUISITES.json', prerequisites, exclusive=True)
    process.save(directory / 'EXECUTION.json', {'schema_version': 2, 'kind': 'scale-v2-native-execution',
        'campaign_sha256': campaign_sha256, 'workers': campaign['launch_policy']['workers'],
        'started_at': utc(), 'supervisor_pid': os.getpid(), 'supervisor_identity': supervisor,
        'source_sha256': sources, 'registration_tools_sha256': tools, 'dependencies': deps,
        'repository_commit': revision, 'source_commit_verified': True,
        'prerequisites_sha256': contract.sha(directory / 'PREREQUISITES.json'),
        'installation': binding, 'prerequisite_paths': prerequisite_paths}, exclusive=True)
    # No second execution can cross this durable intent, even if no model work
    # follows. A failed native setup needs a new registration/output directory.
    stop = threading.Event(); active = {}; rows = []; service = None; failure = None
    next_slot = 0; slots = campaign['slots']; workers = campaign['launch_policy']['workers']
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='world-supervisor')
    with interrupt_control(stop):
        try:
            runtime_binding(campaign)
            service = process.start_service(binding, directory,
                startup_seconds=LAUNCH_LIMITS['service_startup_seconds'])
            while active or (next_slot < len(slots) and not stop.is_set()):
                process.verify_service(service)
                while len(active) < workers and next_slot < len(slots) and not stop.is_set():
                    runtime_binding(campaign)
                    slot = slots[next_slot]; run = directory / slot['relative_path']
                    handle = process.spawn_world(run_dir=run, receipt_dir=run / 'lifecycle')
                    try:
                        future = pool.submit(monitor_world, handle, run, service, stop=stop,
                            wall_seconds=campaign['launch_policy']['per_world_wall_seconds'])
                    except BaseException:
                        process.cleanup_world(handle, run, service,
                            timeout_seconds=LAUNCH_LIMITS['world_cleanup_seconds'])
                        raise
                    active[future] = slot['run_id']; next_slot += 1
                for future in list(active):
                    if future.done():
                        rows.append(future.result()); del active[future]
                        process.save(directory / 'execution_results.json', result_envelope(campaign_sha256, rows, slots))
                process.save(directory / 'STATUS.json', {'schema_version': 2, 'as_of': utc(),
                    'planned_worlds': 6, 'started_worlds': next_slot, 'terminal_worlds': len(rows),
                    'active_worlds': list(active.values()), 'interruption_requested': stop.is_set()})
                # Waiting on an already-set stop event would busy-spin during
                # bounded cleanup. This sleep never blocks a world monitor.
                time.sleep(LAUNCH_LIMITS['observation_interval_seconds'])
        except BaseException as exc:
            failure = type(exc).__name__; stop.set()
        finally:
            stop.set()
            # Monitor threads handle their own failures and cleanup concurrently.
            # Repeated signals only set the event and cannot abort this phase.
            for future in list(active):
                try:
                    rows.append(future.result())
                except BaseException as exc:
                    failure = failure or type(exc).__name__
            pool.shutdown(wait=True, cancel_futures=False)
            if service is not None:
                try:
                    process.cleanup_service(service, timeout_seconds=LAUNCH_LIMITS['service_cleanup_seconds'])
                except BaseException as exc:
                    failure = failure or type(exc).__name__
            process.save(directory / 'execution_results.json', result_envelope(campaign_sha256, rows, slots))
            if failure is not None or len(rows) != 6:
                process.save(directory / 'SUPERVISOR_INTERRUPTED.json', {'schema_version': 2,
                    'finished_at': utc(), 'error_type': failure, 'started_worlds': next_slot,
                    'terminal_worlds': len(rows)}, exclusive=True)
    from scripts.audit_scale_v2 import audit_campaign_v2
    audit = audit_campaign_v2(directory, campaign_sha256=campaign_sha256, strict=True)
    process.save(directory / 'AUDIT.json', audit)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--campaign-sha256', required=True)
    parser.add_argument('--prerequisite-paths', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.out, campaign_sha256=args.campaign_sha256,
                         prerequisite_paths=contract.read(args.prerequisite_paths))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result.get('ok') is True else 1
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
