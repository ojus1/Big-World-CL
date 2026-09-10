#!/usr/bin/env python3
"""Read-only six-world v2 audit. Local receipts are consistency evidence.

No surviving-pair endpoint is emitted. Cost reconciliation is independent of
behavioral acceptance and cleanup; unreturned work retains reservations. Actor
numbers cover contracted client-cache interviews only, never bootstrap/social
inference, billing, or authenticated provider totals. Private text is not output.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifespan.evaluation.runner import dependency_provenance, source_hashes
from scripts import scale_v2_contract as contract
from scripts.audit_scale import run_check
from scripts.evaluation_report_v2 import compare_reports_v2
from scripts.prepare_scale_v2 import tooling

VERSION = 'scale-v2-six-world-integrity-audit'
ERRORS = (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError, RecursionError, RuntimeError, ImportError)
require, child, read, sha = contract.require, contract.child, contract.read, contract.sha
FIELDS = ('records', 'known_physical_calls', 'known_input_tokens', 'known_output_tokens',
          'known_tokens', 'charged_or_reserved_model_calls', 'charged_or_reserved_tokens', 'unresolved_records')


def integer(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and value >= 0 and (type(value) is int or math.isfinite(value))


def code(exc):
    value = str(exc)
    return value if type(exc) is ValueError and re.fullmatch('[a-z][a-z0-9_]{0,95}', value) else type(exc).__name__


def totals(rows):
    return {**{k: sum(row[k] for row in rows) for k in FIELDS},
            'accounting_complete': all(row['accounting_complete'] for row in rows)}


def reservation(calls=16, tokens=250000):
    require(integer(calls) and integer(tokens), 'invalid_cost_reservation')
    return {**dict.fromkeys(FIELDS, 0), 'records': 1, 'unresolved_records': 1,
            'charged_or_reserved_model_calls': calls, 'charged_or_reserved_tokens': tokens,
            'accounting_complete': False}


def native_cost(record):
    """Physical usage only: rejected behavior or cleanup cannot erase a receipt."""
    meter = record['result']['native']['evaluation_budget']
    rows = meter['operations']
    require(type(rows) is list, 'native_physical_operations')
    result = {**dict.fromkeys(FIELDS, 0), 'records': 1, 'accounting_complete': True}
    for index, row in enumerate(rows, 1):
        require(type(row['dispatch']) is int and row['dispatch'] == index, 'native_dispatch_sequence')
        require(all(integer(row[k]) for k in ('reserved_tokens', 'charged_tokens', 'output_cap')),
                'native_physical_reservation')
        require(row['accounting'] in ('reported', 'reservation'), 'native_accounting_kind')
        result['known_physical_calls'] += 1
        result['charged_or_reserved_model_calls'] += 1
        result['charged_or_reserved_tokens'] += row['charged_tokens']
        if row['accounting'] == 'reported':
            require(all(integer(row[k]) for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    and row['input_tokens'] + row['output_tokens'] == row['total_tokens'] == row['charged_tokens'],
                    'native_usage_equation')
            for dest, source in (('known_input_tokens', 'input_tokens'), ('known_output_tokens', 'output_tokens'),
                                 ('known_tokens', 'total_tokens')):
                result[dest] += row[source]
        else:
            require(all(row[k] is None for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    and row['charged_tokens'] == row['reserved_tokens'], 'native_unknown_reservation')
            result['accounting_complete'] = False
    complete = result['accounting_complete']
    expected = {'physical_model_calls': len(rows), 'input_tokens': result['known_input_tokens'],
        'output_tokens': result['known_output_tokens'], 'total_tokens': result['known_tokens'],
        'reported_tokens': result['known_tokens'], 'charged_tokens': result['charged_or_reserved_tokens'],
        'accounting_complete': complete}
    require(all(type(meter.get(k)) is type(v) and meter[k] == v for k, v in expected.items()), 'native_meter_summary')
    usage = {'api_calls': len(rows), 'prompt_tokens': expected['input_tokens'],
        'completion_tokens': expected['output_tokens'], 'charged_tokens': expected['charged_tokens'],
        'total_tokens': expected['total_tokens'] if complete else None, 'complete': complete}
    require(all(type(record['usage'].get(k)) is type(v) and record['usage'][k] == v for k, v in usage.items()),
            'native_session_usage_summary')
    result['unresolved_records'] = int(not complete)
    return result


def optimizer_cost(dispatch, receipt):
    limits = dispatch['limits']
    fallback = reservation(limits['max_model_calls'], limits['max_tokens'])
    if receipt is None:
        return fallback
    require(integer(receipt['model_calls']) and receipt['model_calls'] <= 1, 'optimizer_physical_calls')
    fallback['known_physical_calls'] = receipt['model_calls']
    fallback['charged_or_reserved_model_calls'] = receipt['model_calls']
    if receipt['accounting_complete'] is not True:
        return fallback
    require(all(integer(receipt[k]) for k in ('input_tokens', 'output_tokens', 'tokens'))
            and receipt['input_tokens'] + receipt['output_tokens'] == receipt['tokens'], 'optimizer_usage_equation')
    require(receipt['model_calls'] > 0 or receipt['tokens'] == 0, 'optimizer_tokens_without_dispatch')
    return {**dict.fromkeys(FIELDS, 0), 'records': 1, 'accounting_complete': True,
        'known_physical_calls': receipt['model_calls'], 'known_input_tokens': receipt['input_tokens'],
        'known_output_tokens': receipt['output_tokens'], 'known_tokens': receipt['tokens'],
        'charged_or_reserved_model_calls': receipt['model_calls'], 'charged_or_reserved_tokens': receipt['tokens']}


def employee_accounting(run):
    """Reconcile durable physical meters; count each replay once, not its ledger twice.

In-progress progress.json is a snapshot, not a complete ledger. A work marker
without a session gets a conservative action reservation even if actor planning
has not reached the target. Optimizer transport receipts, not proposals, count.
"""
    run = Path(run)
    scopes = {'online': [], 'learning_target': [], 'optimizer': [], 'learning_unknown': []}
    issues, hashes, seen, by_source, referenced_learning = [], {}, set(), {}, set()
    def session(relative, scope, missing_limits=None):
        require(relative not in seen, 'duplicate_native_cost_source')
        seen.add(relative); path = child(run, relative)
        if not path.exists():
            limits = missing_limits or {'max_model_calls': 16, 'max_tokens': 250000}
            value = reservation(limits['max_model_calls'], limits['max_tokens'])
            scopes[scope].append(value); by_source[relative] = value
            return
        hashes[relative] = sha(path)
        try:
            value = native_cost(read(path))
        except ERRORS as exc:
            issues.append({'scope': scope, 'code': code(exc), 'source_sha256': hashes[relative]})
            value = reservation()
        scopes[scope].append(value)
        by_source[relative] = value
    for path in sorted((run / 'work').glob('*/session.json')):
        session(str(path.relative_to(run)), 'online')
    for directory in sorted((run / 'work').glob('*')):
        relative = str((directory / 'session.json').relative_to(run))
        if directory.is_dir() and relative not in seen:
            session(relative, 'online')
    for path in sorted((run / 'learning').glob('*/trial-*/session.json')):
        session(str(path.relative_to(run)), 'learning_target')
    for path in sorted((run / 'learning').glob('*/progress.json')):
        hashes[str(path.relative_to(run))] = sha(path)
        before = totals([row for rows in scopes.values() for row in rows])
        try:
            progress = read(path); replay_paths = set()
            for index, row in enumerate(progress['replay_artifacts']):
                relative = str((path.parent / f'trial-{index:03d}/session.json').relative_to(run))
                require(row['attempt_index'] == index and row['session_path'] == relative, 'replay_cost_identity')
                replay_paths.add(relative)
                referenced_learning.add(relative)
                actual = child(run, relative)
                if actual.exists() and row.get('session_sha256') is not None:
                    require(sha(actual) == row['session_sha256'], 'replay_cost_session_hash')
                if relative not in seen:
                    session(relative, 'learning_target', row['limits'])
            for actual in path.parent.glob('trial-*/session.json'):
                require(str(actual.relative_to(run)) in replay_paths, 'untracked_replay_cost_source')
            dispatches, receipts = progress['optimizer_dispatches'], progress['optimizer_transport_audit']
            require(type(dispatches) is list and type(receipts) is list and len(receipts) <= len(dispatches),
                    'optimizer_cost_inventory')
            for index, dispatch in enumerate(dispatches):
                require(dispatch['attempt_index'] == index, 'optimizer_cost_identity')
                receipt = receipts[index] if index < len(receipts) else None
                if receipt is not None and dispatch.get('receipt') is not None:
                    require(all(dispatch['receipt'][k] == receipt[k] for k in ('status', 'model_calls', 'tokens')),
                            'optimizer_dispatch_receipt_binding')
                scopes['optimizer'].append(optimizer_cost(dispatch, receipt))
        except ERRORS as exc:
            issues.append({'scope': 'learning', 'code': code(exc), 'source_sha256': hashes[str(path.relative_to(run))]})
            after = totals([row for rows in scopes.values() for row in rows])
            prefix = str(path.parent.relative_to(run)) + '/'
            existing = totals([value for name, value in by_source.items() if name.startswith(prefix)
                               and child(run, name).exists()])
            scopes['learning_unknown'].append(reservation(
                max(0, 200 - existing['charged_or_reserved_model_calls'] -
                    (after['charged_or_reserved_model_calls'] - before['charged_or_reserved_model_calls'])),
                max(0, 4000000 - existing['charged_or_reserved_tokens'] -
                    (after['charged_or_reserved_tokens'] - before['charged_or_reserved_tokens']))))
    for actual in (run / 'learning').glob('*/trial-*/session.json'):
        relative = str(actual.relative_to(run))
        if relative not in referenced_learning:
            issues.append({'scope': 'learning_target', 'code': 'session_without_progress', 'source_sha256': sha(actual)})
    for directory in (run / 'learning').glob('*/trial-*'):
        relative = str((directory / 'session.json').relative_to(run))
        if directory.is_dir() and relative not in seen:
            session(relative, 'learning_target')
    marker = run / 'INFLIGHT.json'
    pending = None
    if marker.exists():
        hashes['INFLIGHT.json'] = sha(marker); pending = read(marker)
        require(pending['kind'] in ('work', 'actor', 'learning'), 'unknown_inflight_kind')
        if pending['kind'] == 'work':
            relative = 'work/' + pending['key'] + '/session.json'
            if relative not in seen:
                session(relative, 'online')
        elif pending['kind'] == 'learning' and not child(run, 'learning/' + pending['key'] + '/progress.json').exists():
            prefix = 'learning/' + pending['key'] + '/'
            existing = totals([value for name, value in by_source.items() if name.startswith(prefix)])
            scopes['learning_unknown'].append(reservation(max(0, 200 - existing['charged_or_reserved_model_calls']),
                max(0, 4000000 - existing['charged_or_reserved_tokens'])))
    return {'scopes': {key: totals(rows) for key, rows in scopes.items()},
        'total': totals([row for rows in scopes.values() for row in rows]), 'issues': issues,
        'raw_source_sha256': hashes, 'inflight_kind': pending['kind'] if pending else None,
        'scope': 'durable_local_physical_receipts_and_unreturned_dispatch_reservations; no_behavior_or_cleanup_acceptance_claim'}


def actor_accounting(run, *, completed):
    from lifespan.actor_contract import audit_interviews, descriptor, verify_record, wire
    from lifespan.ecosystem import Ecosystem
    run = Path(run); ledger = run / 'actors/evaluation_interview_ledger.json'
    if not ledger.exists():
        require(not completed, 'completed_missing_actor_ledger')
        return {'logical_requests': 0, 'measured_physical_requests': 0, 'measured_tokens': 0,
            'unknown_requests': 0, 'reserved_output_tokens': 0, 'accounting_complete': False,
            'scope': 'no_durable_contracted_interview_ledger; bootstrap_social_cost_unknown'}
    cp, manifest = read(run / 'checkpoint.json'), read(run / 'manifest.json')
    participants = Ecosystem.restore(cp['ecosystem']).participants()
    roles = {p['id']: (index, wire.ROLE_TYPES[p['entity_type']]) for index, p in enumerate(participants)}
    config = manifest['config']['actor_output_contract']
    rows = read(ledger)['requests']
    require(type(rows) is list and len({r['key'] for r in rows}) == len(rows), 'actor_cost_ledger_inventory')
    simulation = read(run / 'actors/mirofish_state.json')['simulation']['simulation_id']
    result = {'logical_requests': len(rows), 'measured_physical_requests': 0, 'measured_tokens': 0,
        'unknown_requests': 0, 'reserved_output_tokens': 0, 'issues': [], 'ledger_sha256': sha(ledger),
        'scope': 'reconciled_client_cache_receipts_only; native_server_orphans_and_bootstrap_social_cost_excluded'}
    for row in rows:
        try:
            agent, role = roles[row['actor']]; expected = descriptor(config, role)
            require(type(row['key']) is str and re.fullmatch('[A-Za-z0-9_.-]{1,256}', row['key'])
                    and row['key'] not in ('.', '..'), 'actor_cost_cache_key')
            cache = child(run, 'actors/mirofish_interviews/' + row['key'] + '.json')
            if not cache.exists():
                require(row['status'] == 'dispatched', 'actor_cost_missing_completed_cache')
                result['unknown_requests'] += 1
                result['reserved_output_tokens'] += expected['max_output_tokens']
                continue
            record = read(cache)
            receipt = verify_record(record, actor=row['actor'], agent_id=agent, simulation_id=simulation,
                original_prompt=record['prompt'], contract=expected, request_key=wire.text_hash(row['key']))
            require(row['output_contract'] == expected and row['prompt_sha256'] == wire.text_hash(record['prompt'])
                and row['response_sha256'] == receipt['output_sha256'] and row['status'] == 'completed',
                'actor_cost_cache_ledger_binding')
            result['measured_physical_requests'] += receipt['physical_requests_dispatched']
            result['measured_tokens'] += receipt['total_tokens']
        except ERRORS as exc:
            result['issues'].append({'code': code(exc)})
            result['unknown_requests'] += 1
            result['reserved_output_tokens'] += config['max_output_tokens']
    try:
        whole = audit_interviews(run, manifest, participants, completed=completed)
        require(all(whole[key] == result[key] for key in ('logical_requests', 'measured_physical_requests',
            'measured_tokens', 'unknown_requests', 'reserved_output_tokens')), 'actor_cost_whole_ledger_closure')
    except ERRORS as exc:
        result['issues'].append({'code': code(exc)})
    result['accounting_complete'] = not result['issues'] and result['unknown_requests'] == 0
    return result


def registration(directory, campaign_sha256):
    return contract.validate(directory, campaign_sha256=campaign_sha256,
        source_sha256=source_hashes(), dependencies=dependency_provenance(),
        registration_tools_sha256=tooling(), require_pristine=False)


def execution_check(root, campaign):
    """Bind dispatch intent to reviewed registration, committed tools and gates."""
    execution = read(root / 'EXECUTION.json')
    require(execution['schema_version'] == 2 and execution['kind'] == 'scale-v2-native-execution'
        and execution['campaign_sha256'] == sha(root / 'campaign.json')
        and type(execution['workers']) is int and execution['workers'] == campaign['launch_policy']['workers'],
        'execution_registration_binding')
    for key in ('source_sha256', 'registration_tools_sha256', 'dependencies'):
        require(contract.same(execution[key], campaign[key]), 'execution_source_or_dependency_binding')
    commit = execution['repository_commit']
    require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit)
        and execution['source_commit_verified'] is True, 'execution_committed_source_claim')
    for name, expected in {**campaign['source_sha256'], **campaign['registration_tools_sha256']}.items():
        child(ROOT, name)
        try:
            raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + name],
                                          stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            raise ValueError('execution_commit_source_unavailable') from None
        require(hashlib.sha256(raw).hexdigest() == expected, 'execution_commit_source_mismatch')
    identity = execution['supervisor_identity']
    require(type(execution['supervisor_pid']) is int and execution['supervisor_pid'] > 0
        and identity['pid'] == execution['supervisor_pid'] and type(identity['start_ticks']) is int
        and identity['start_ticks'] > 0 and integer(identity['uid'])
        and type(identity['boot_id']) is str and bool(identity['boot_id']), 'supervisor_identity_binding')
    require(sha(root / 'PREREQUISITES.json') == execution['prerequisites_sha256'], 'execution_prerequisite_hash')
    from scripts.scale_v2_prerequisites import verify_prerequisites
    actual = verify_prerequisites(campaign, execution['prerequisite_paths'])
    saved = read(root / 'PREREQUISITES.json')
    require(contract.same(saved, actual) and saved['verified'] is True, 'execution_prerequisite_audit')
    return execution


def lifecycle_audit(root, campaign, completed):
    """The process helper owns exact local identity/receipt semantics."""
    from scripts import scale_v2_process as process
    execution = execution_check(root, campaign)
    from scripts.run_scale_v2 import LAUNCH_LIMITS
    service = process.validate_service_receipts(root, completed=completed)
    require(service['ok'], 'service_lifecycle_invalid')
    start = read(root / 'SERVICE_START.json')
    require(contract.same(execution['installation'], start['binding']), 'execution_service_installation_binding')
    parent, service_identity = execution['supervisor_identity'], start['root_identity']
    require(service_identity['ppid'] == parent['pid'] and service_identity['uid'] == parent['uid']
        and service_identity['boot_id'] == parent['boot_id']
        and service_identity['start_ticks'] >= parent['start_ticks'], 'service_supervisor_process_binding')
    ready = service.get('ready_monotonic')
    if ready is not None:
        require(number(ready) and 0 <= ready - service['started_monotonic'] <= LAUNCH_LIMITS['service_startup_seconds'],
                'service_startup_wall_limit')
    service_cleanup = read(root / 'SERVICE_CLEANUP.json') if (root / 'SERVICE_CLEANUP.json').exists() else None
    if service_cleanup:
        require(type(service['cleanup_limit_seconds']) is int and 0 < service['cleanup_limit_seconds'] <=
                LAUNCH_LIMITS['service_cleanup_seconds'], 'service_cleanup_allowance')
        if completed:
            require(service['cleanup_limit_seconds'] == LAUNCH_LIMITS['service_cleanup_seconds'], 'service_cleanup_allowance')
    worlds = []
    for slot in campaign['slots']:
        run = child(root, slot['relative_path']); directory = run / 'lifecycle'
        if not (directory / 'WORLD_START.json').exists():
            require(not completed, 'missing_world_launch_receipt')
            continue
        world = process.validate_world_receipts(directory, run, start, completed=completed)
        require(world['ok'], 'world_lifecycle_invalid')
        raw_start = read(directory / 'WORLD_START.json'); identity = raw_start['root_identity']
        require(identity['ppid'] == parent['pid'] and identity['uid'] == parent['uid']
            and identity['boot_id'] == parent['boot_id'] and identity['start_ticks'] >= parent['start_ticks'],
            'world_supervisor_process_binding')
        require(ready is not None and world['started_monotonic'] >= ready, 'world_precedes_service_readiness')
        if world['ended_monotonic'] is not None:
            require(world['cleanup_limit_seconds'] == LAUNCH_LIMITS['world_cleanup_seconds'], 'world_cleanup_allowance')
            if service_cleanup:
                require(world['ended_monotonic'] <= service['cleanup_started_monotonic'], 'service_closed_before_world_cleanup')
            require(world['cleanup_started_monotonic'] - world['started_monotonic'] <=
                    campaign['launch_policy']['per_world_wall_seconds'], 'world_execution_wall_limit')
        worlds.append({'run_id': slot['run_id'], **world})
    intervals = []
    simulations = [row['simulation_id'] for row in worlds if row.get('simulation_id') is not None]
    require(len(simulations) == len(set(simulations)), 'shared_native_simulation_between_worlds')
    for world in worlds:
        begin, end = world['started_monotonic'], world.get('ended_monotonic')
        require(number(begin) and (end is None or number(end) and end >= begin), 'world_lifecycle_clock')
        intervals.append((begin, 1))
        if end is not None: intervals.append((end, -1))
        if completed:
            require(world['root_exitcode'] == 0 and type(world['root_exitcode']) is int
                    and world['cleanup_confirmed'] is True, 'completed_world_exit_or_cleanup')
    active = peak = 0
    for _, change in sorted(intervals):
        active += change; peak = max(peak, active)
    require(peak <= campaign['launch_policy']['workers'], 'world_concurrency_limit')
    require(not completed or len(worlds) == 6 and service['cleanup_confirmed'] is True,
            'completed_campaign_cleanup_incomplete')
    final = root / 'execution_results.json'
    if final.exists():
        result = read(final)
        require(result['schema_version'] == 2 and result['campaign_sha256'] == execution['campaign_sha256']
            and type(result['runs']) is list, 'supervisor_result_binding')
        by_id = {row['run_id']: row for row in worlds}; recorded = set()
        for row in result['runs']:
            identifier = row['run_id']
            require(identifier in by_id and identifier not in recorded, 'supervisor_result_inventory')
            recorded.add(identifier); world = by_id[identifier]
            require(world['ended_monotonic'] is not None and type(row['exit_code']) is int
                and row['exit_code'] == world['root_exitcode']
                and number(row['elapsed_seconds']) and row['elapsed_seconds'] ==
                    world['ended_monotonic'] - world['started_monotonic']
                and row['lifecycle'] == {'start_sha256': world['hashes']['WORLD_START.json'],
                                        'cleanup_sha256': world['hashes']['WORLD_CLEANUP.json']},
                'supervisor_world_receipt_binding')
            require(row['termination_reason'] in ('exited', 'supervisor_interrupted', 'wall_limit', 'observation_failed'),
                    'unknown_world_termination_reason')
            if completed:
                require(row['termination_reason'] == 'exited', 'completed_world_abnormal_termination')
                slot = next(slot for slot in campaign['slots'] if slot['run_id'] == identifier)
                require(not (child(root, slot['relative_path']) / 'lifecycle/SUPERVISION_FAILURE.json').exists(),
                        'completed_world_supervision_failure')
        require(not completed or recorded == set(by_id) and len(recorded) == 6, 'completed_supervisor_inventory')
    else:
        require(not completed, 'completed_missing_supervisor_result')
    require(not completed or not (root / 'SUPERVISOR_INTERRUPTED.json').exists(), 'completed_supervisor_interrupted')
    safe = ('ok', 'errors', 'hashes', 'started_monotonic', 'ended_monotonic', 'root_exitcode',
            'cleanup_confirmed', 'simulation_id', 'cleanup_started_monotonic', 'cleanup_limit_seconds', 'ready_monotonic')
    return {'ok': True, 'service': {k: service[k] for k in safe if k in service},
        'worlds': [{k: row[k] for k in ('run_id', *safe) if k in row} for row in worlds], 'peak_parallel_worlds': peak}


def audit_campaign_v2(directory, *, campaign_sha256, strict=False):
    root = Path(directory).resolve()
    slots = [{'run_id': f'seed-{seed}-{arm}', 'seed': seed, 'algorithm': arm,
              'status': 'not_verified', 'ok': False, 'completed': False, 'model_quality_score': None}
             for seed, arm in contract.schedule()]
    output = {'schema_version': 1, 'kind': VERSION, 'status': 'invalid', 'ok': False,
        'errors': [], 'runs': slots, 'planned_runs': 6, 'planned_pairs': 3,
        'completed_runs': 0, 'complete_pairs': 0, 'primary_endpoint_available': False,
        'comparison': None, 'model_quality_score': None, 'postprocessor_sha256': sha(__file__),
        'cost_scope': 'employee_and_optimizer_physical_receipts; contracted_interviews_separate; all_in_cost_unknown'}
    try:
        campaign = registration(root, campaign_sha256)
        output['campaign_sha256'] = campaign_sha256
        reports, costs, actors = [], [], []
        for index, slot in enumerate(campaign['slots']):
            item = slots[index]; run = child(root, slot['relative_path'])
            item['launch_state'] = ('cleanup_recorded' if (run / 'lifecycle/WORLD_CLEANUP.json').exists()
                else 'start_recorded' if (run / 'lifecycle/WORLD_START.json').exists()
                else 'intent_without_start_receipt' if (run / 'lifecycle/WORLD_INTENT.json').exists() else 'not_launched')
            try:
                raw, report = run_check(root, campaign, slot)
                require(raw['status'] in ('not_started', 'initializing', 'running', 'completed', 'failed',
                    'exhausted_time_budget', 'paused_invocation_limit', 'exhausted_work_budget')
                    and type(raw['ok']) is bool and type(raw['completed']) is bool
                    and raw['completed'] == (raw['status'] == 'completed'), 'raw_audit_status_shape')
                item.update({k: raw[k] for k in ('status', 'ok', 'completed')})
                for key in ('sessions', 'updates', 'accepted_updates', 'learning_target_replays'):
                    if key in raw:
                        require(integer(raw[key]), 'raw_audit_count_shape')
                        item[key] = raw[key]
                if 'evidence_sha256' in raw:
                    item['evidence_sha256'] = {key: raw['evidence_sha256'][key] for key in
                        ('manifest.json', 'checkpoint.json', 'REPORT.json', 'REPORT.v2.json', 'persona_cohort.json')}
                    require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                        for value in item['evidence_sha256'].values()), 'raw_audit_hash_shape')
                item['raw_audit_pass'] = True
                if report is not None: reports.append(report)
            except ERRORS as exc:
                raw = None
                item.update(status='invalid', ok=False, completed=False, error=code(exc))
                output['errors'].append({'run_id': slot['run_id'], 'scope': 'world', 'code': code(exc)})
            try:
                cost = employee_accounting(run); costs.append(cost['total'])
                item['employee_costs'] = {k: v for k, v in cost.items() if k != 'raw_source_sha256'}
                item['employee_costs']['raw_source_hashes'] = sorted(cost['raw_source_sha256'].values())
                require(not cost['issues'], 'employee_cost_evidence_invalid')
                if item['completed']:
                    require(cost['total']['accounting_complete'] and
                        cost['total']['known_physical_calls'] == raw['learner_physical_calls'] and
                        cost['total']['known_tokens'] == raw['learner_measured_tokens'], 'completed_cost_closure')
            except ERRORS as exc:
                item['employee_costs_complete'] = False
                output['errors'].append({'run_id': slot['run_id'], 'scope': 'employee_costs', 'code': code(exc)})
            try:
                actor = actor_accounting(run, completed=item['completed']); actors.append(actor)
                item['contracted_interview_costs'] = actor
                require(not actor.get('issues'), 'actor_cost_evidence_invalid')
            except ERRORS as exc:
                if 'contracted_interview_costs' not in item:
                    item['contracted_interview_costs'] = {'accounting_complete': False, 'measured_tokens': None,
                        'measured_physical_requests': None, 'unknown_scope': 'unreconciled_actor_evidence'}
                output['errors'].append({'run_id': slot['run_id'], 'scope': 'actor_costs', 'code': code(exc)})
        complete = [row for row in slots if row['completed']]
        pairs = [seed for seed in contract.SEEDS if sum(row['seed'] == seed for row in complete) == 2]
        output.update(completed_runs=len(complete), complete_pairs=len(pairs),
            missing_or_invalid_pairs=[{'seed': seed, 'runs': [row['run_id'] for row in slots
                if row['seed'] == seed and not row['completed']]} for seed in contract.SEEDS if seed not in pairs])
        all_complete = len(complete) == 6 and len(pairs) == 3 and not output['errors']
        cost = totals(costs)
        cost['all_world_costs_reconciled'] = all_complete and len(costs) == 6 and cost['accounting_complete']
        actor_totals = {key: sum(row[key] for row in actors) for key in ('logical_requests',
            'measured_physical_requests', 'measured_tokens', 'unknown_requests', 'reserved_output_tokens')}
        actor_totals['all_world_costs_reconciled'] = all_complete and len(actors) == 6 and all(row['accounting_complete'] for row in actors)
        output['accounting'] = {'employee_and_optimizer': cost, 'contracted_interviews': actor_totals,
            'unmetered_environment': {'physical_model_calls': None, 'tokens': None, 'accounting_complete': False},
            'currency_cost': None, 'all_in_accounting_complete': False}
        require(cost['charged_or_reserved_model_calls'] <= campaign['budgets']['employee_target_and_optimizer_physical_calls']
            and cost['charged_or_reserved_tokens'] <= campaign['budgets']['employee_target_and_optimizer_charged_tokens']
            and actor_totals['logical_requests'] <= campaign['budgets']['logical_actor_interviews']
            and actor_totals['measured_physical_requests'] <= campaign['budgets']['contracted_interview_physical_requests'],
            'campaign_cost_budget_exceeded')
        if (root / 'EXECUTION.json').exists():
            try: output['lifecycle'] = lifecycle_audit(root, campaign, all_complete)
            except ERRORS as exc:
                output['errors'].append({'scope': 'lifecycle', 'code': code(exc)})
        else:
            require(not complete and all(row['status'] == 'not_started' for row in slots), 'world_evidence_without_execution')
        all_complete &= not output['errors']
        if all_complete:
            comparison = compare_reports_v2(reports)
            require(not comparison['rejected_pairs'] and len(comparison['eligible_pairs']) == 3,
                    'all_three_world_pairs_required')
            output.update(comparison=comparison, primary_endpoint_available=True)
        output['status'] = 'invalid' if output['errors'] else 'valid_completed' if all_complete else 'incomplete'
        output['ok'] = not output['errors'] and (not strict or all_complete)
    except ERRORS as exc:
        output.update(status='invalid', ok=False, primary_endpoint_available=False, comparison=None)
        output['errors'].append({'scope': 'campaign', 'code': code(exc)})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory'); parser.add_argument('--campaign-sha256', required=True)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    result = audit_campaign_v2(args.directory, campaign_sha256=args.campaign_sha256, strict=args.strict)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
