#!/usr/bin/env python3
"""Read-only six-world v3 audit with a mandatory owned-scope proof. Local receipts are consistency evidence.

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
from scripts import scale_v3_contract as contract
from scripts.audit_scale import run_check
from scripts.evaluation_report_v2 import compare_reports_v2
from scripts.prepare_scale_v3 import tooling

VERSION = 'scale-v3-six-world-integrity-audit'
# Reuse the physical accounting implementation unchanged. These helpers do not
# inspect launch policy or reinterpret behavioral/cleanup failures as zero cost.
from scripts.audit_scale_v2 import (ERRORS, require, child, read, sha, integer,
    number, code, totals, reservation, native_cost, optimizer_cost,
    employee_accounting, actor_accounting)


def registration(directory, campaign_sha256):
    return contract.validate(directory, campaign_sha256=campaign_sha256,
        source_sha256=source_hashes(), dependencies=dependency_provenance(),
        registration_tools_sha256=tooling(), require_pristine=False)


def execution_check(root, campaign):
    """Bind dispatch intent to reviewed registration, committed tools and gates."""
    execution = read(root / 'EXECUTION.json')
    require(execution['schema_version'] == 3 and execution['kind'] == 'scale-v3-native-execution'
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
    try:
        from scripts.run_scale_v3 import verify_prerequisites
    except (ImportError, AttributeError):
        raise ValueError('v3_prerequisite_verifier_pending') from None
    actual = verify_prerequisites(campaign, execution['prerequisite_paths'])
    saved = read(root / 'PREREQUISITES.json')
    require(contract.same(saved, actual) and saved['verified'] is True, 'execution_prerequisite_audit')
    require(sha(child(root, 'scope/GATE.json')) == execution['scope_gate_sha256'],
            'execution_outer_scope_gate_hash')
    gate = read(child(root, 'scope/GATE.json'))
    require(number(execution['started_monotonic']) and number(execution['execution_deadline'])
        and execution['execution_deadline'] == execution['started_monotonic'] + contract.SCOPE_LIMITS['execution_seconds']
        and execution['started_monotonic'] == gate['execution_started_monotonic']
        and execution['execution_deadline'] == gate['execution_deadline'], 'inner_execution_clock_shape')
    return execution


def outer_scope_audit(root, campaign, completed):
    """No scope-result shortcut: require the separately audited native wait.

    The outer implementation is deliberately an obligatory dependency. Until
    its read-only audit exists, this hook fails closed rather than accepting an
    unverified manifest or a systemd Result=success value.
    """
    try:
        from scripts.run_scale_v3 import audit_scope
    except (ImportError, AttributeError):
        raise ValueError('outer_scope_auditor_pending') from None
    result = audit_scope(root, campaign_sha256=sha(root / 'campaign.json'), strict=completed)
    require(type(result) is dict and result.get('campaign_sha256') == sha(root / 'campaign.json'),
            'outer_scope_campaign_binding')
    require(type(result.get('ok')) is bool, 'outer_scope_integrity_invalid')
    require(result.get('errors') == [] and type(result.get('errors')) is list,
            'outer_scope_errors_present')
    flags = ('scope_passed', 'scope_complete', 'inner_completed')
    require(all(type(result.get(k)) is bool for k in flags), 'outer_scope_status_shape')
    require(all(result.get(k) is None or type(result[k]) is int for k in
        ('native_wait_exit_code', 'inner_result_exit_code')), 'outer_scope_exit_code_shape')
    if not result['ok']:
        require(result.get('status') == 'incomplete' and not result['scope_passed']
            and not result['scope_complete'], 'outer_scope_integrity_invalid')
        # This is a missing-proof observation, never an alternative acceptance
        # route. The campaign endpoint below additionally requires scope_passed.
        return {'ok': False, 'status': 'incomplete', **{k: result[k] for k in flags},
            'inner_supervisor_identity_bound': False, 'native_wait_exit_code': result.get('native_wait_exit_code'),
            'inner_result_exit_code': result.get('inner_result_exit_code')}
    if completed:
        require(all(result[k] for k in flags), 'completed_outer_scope_unconfirmed')
        require(type(result.get('native_wait_exit_code')) is int and result['native_wait_exit_code'] == 0
            and type(result.get('inner_result_exit_code')) is int and result['inner_result_exit_code'] == 0,
            'completed_outer_native_return_or_wait')
    bound = False
    if (root / 'EXECUTION.json').exists():
        execution = read(root / 'EXECUTION.json')
        expected = execution['supervisor_identity']; actual = result.get('inner_supervisor_identity')
        require(type(actual) is dict and all(type(actual.get(k)) is type(expected.get(k))
            and actual[k] == expected[k] for k in ('pid', 'start_ticks', 'uid', 'boot_id')),
            'outer_scope_inner_supervisor_binding')
        bound = True
    hashes = result.get('raw_evidence_sha256')
    require(type(hashes) is dict and bool(hashes) and all(type(v) is str and
            re.fullmatch('[0-9a-f]{64}', v) for v in hashes.values()), 'outer_scope_evidence_hashes')
    # Never forward identities, cgroup/unit paths, exception text or native logs.
    return {'ok': True, **{k: result[k] for k in flags},
        'inner_supervisor_identity_bound': bound,
        'native_wait_exit_code': result.get('native_wait_exit_code'),
        'inner_result_exit_code': result.get('inner_result_exit_code'),
        'raw_evidence_hashes': sorted(hashes.values())}


def pair_barriers(campaign, worlds, terminal_rows):
    """Fixed seed pairs only; prior normal completion precedes next dispatch."""
    by_id = {row['run_id']: row for row in worlds}
    require(len(by_id) == len(worlds), 'duplicate_world_lifecycle_identity')
    final = {row['run_id']: row for row in terminal_rows}
    require(len(final) == len(terminal_rows), 'duplicate_supervisor_terminal_identity')
    groups = [[slot['run_id'] for slot in campaign['slots'] if slot['seed'] == seed]
              for seed in contract.SEEDS]
    require(len(groups) == 3 and all(len(group) == 2 for group in groups), 'fixed_pair_inventory')
    checked = 0
    for index, group in enumerate(groups):
        current = [by_id[name] for name in group if name in by_id]
        if not current:
            continue
        for earlier in groups[:index]:
            for name in earlier:
                require(name in by_id and name in final, 'pair_started_before_prior_pair_terminal')
                prior = by_id[name]; receipt = final[name]
                require(prior['ended_monotonic'] is not None and prior['cleanup_confirmed'] is True
                    and type(prior['root_exitcode']) is int and prior['root_exitcode'] == 0
                    and type(receipt['exit_code']) is int and receipt['exit_code'] == 0
                    and receipt['termination_reason'] == 'exited', 'pair_advanced_after_prior_failure')
                require(all(row['started_monotonic'] >= prior['ended_monotonic'] for row in current),
                        'fixed_pair_cleanup_barrier_broken')
        checked += int(index > 0)
    return {'planned_pair_batches': 3, 'observed_following_pair_barriers': checked,
            'prior_pair_requires_normal_exit_and_confirmed_cleanup': True}


def lifecycle_audit(root, campaign, completed):
    """The process helper owns exact local identity/receipt semantics."""
    from scripts import scale_v2_process as process
    execution = execution_check(root, campaign)
    from scripts.scale_v3_contract import LAUNCH_LIMITS
    service = process.validate_service_receipts(root, completed=completed)
    require(service['ok'], 'service_lifecycle_invalid')
    require(number(service['started_monotonic']) and execution['started_monotonic'] <=
            service['started_monotonic'] <= execution['execution_deadline'],
            'service_precedes_inner_execution_clock')
    if service['ended_monotonic'] is not None:
        require(number(service['ended_monotonic']) and service['ended_monotonic'] <= execution['execution_deadline'],
                'inner_execution_deadline_exceeded')
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
        require(number(world['started_monotonic']) and execution['started_monotonic'] <=
            world['started_monotonic'] <= execution['execution_deadline'], 'world_outside_inner_execution_clock')
        raw_start = read(directory / 'WORLD_START.json'); identity = raw_start['root_identity']
        require(identity['ppid'] == parent['pid'] and identity['uid'] == parent['uid']
            and identity['boot_id'] == parent['boot_id'] and identity['start_ticks'] >= parent['start_ticks'],
            'world_supervisor_process_binding')
        require(ready is not None and world['started_monotonic'] >= ready, 'world_precedes_service_readiness')
        if world['ended_monotonic'] is not None:
            require(number(world['ended_monotonic']) and world['ended_monotonic'] <= execution['execution_deadline'],
                    'world_cleanup_after_inner_deadline')
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
    terminal_rows = []
    if final.exists():
        result = read(final)
        require(result['schema_version'] == 3 and result['campaign_sha256'] == execution['campaign_sha256']
            and type(result['runs']) is list, 'supervisor_result_binding')
        terminal_rows = result['runs']
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
    barriers = pair_barriers(campaign, worlds, terminal_rows)
    safe = ('ok', 'errors', 'hashes', 'started_monotonic', 'ended_monotonic', 'root_exitcode',
            'cleanup_confirmed', 'simulation_id', 'cleanup_started_monotonic', 'cleanup_limit_seconds', 'ready_monotonic')
    return {'ok': True, 'service': {k: service[k] for k in safe if k in service},
        'worlds': [{k: row[k] for k in ('run_id', *safe) if k in row} for row in worlds],
        'peak_parallel_worlds': peak, 'pair_barriers': barriers}


def audit_campaign_v3(directory, *, campaign_sha256, strict=False):
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
                require(raw['ok'] is True, 'world_raw_audit_not_ok')
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
        if (root / 'EXECUTION.json').exists() or (root / 'scope').exists():
            try: output['outer_scope'] = outer_scope_audit(root, campaign, all_complete)
            except ERRORS as exc:
                output['errors'].append({'scope': 'outer_scope', 'code': code(exc)})
        if (root / 'EXECUTION.json').exists():
            try: output['lifecycle'] = lifecycle_audit(root, campaign, all_complete)
            except ERRORS as exc:
                output['errors'].append({'scope': 'lifecycle', 'code': code(exc)})
        else:
            require(not complete and all(row['status'] == 'not_started' for row in slots), 'world_evidence_without_execution')
        all_complete &= not output['errors'] and output.get('outer_scope', {}).get('scope_passed') is True
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
    result = audit_campaign_v3(args.directory, campaign_sha256=args.campaign_sha256, strict=args.strict)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
