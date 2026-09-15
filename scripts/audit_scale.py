#!/usr/bin/env python3
"""Offline audit of the preregistered six-run reacting-world development study.

All planned slots remain visible. Three world pairs are descriptive; employees,
tasks and retries are not independent world replicates. Actor request counts
are logical requests, never fabricated physical model-call/token measurements.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.evaluation.protocol import ExperimentConfig, digest, scenario, select_experiences
from lifespan.evaluation.runner import dependency_provenance
from lifespan.mirofish import parse_object
from scripts.audit_evaluation import audit_run, child, read, reports_equal, require
from scripts.audit_transfer import gate_check
from scripts.evaluation_report_v2 import compare_reports_v2, load_verified_report_v2
from scripts.scale_summary import build_scale_summary

SEEDS = [211, 307, 401]
ARMS = ['no_learning', 'skillopt']
POPULATION = {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1}
REQUIRED_SOURCES = {'lifespan/evaluation/runner.py', 'lifespan/evaluation/protocol.py',
    'lifespan/evaluation/runtime.py', 'lifespan/evaluation/budget.py', 'lifespan/evaluation/tasks.py',
    'lifespan/evaluation/metrics.py', 'lifespan/evaluation/skillopt.py', 'lifespan/evaluation/optimizer.py',
    'lifespan/computers.py', 'lifespan/ecosystem.py', 'lifespan/ecosystem_run.py', 'lifespan/mirofish.py',
    'lifespan/world.py', 'scripts/audit_scale.py', 'scripts/run_scale.py', 'scripts/audit_transfer.py',
    'scripts/audit_evaluation.py', 'scripts/evaluation_report_v2.py', 'scripts/scale_summary.py'}
BUDGETS = {'max_parallel_worlds': 6, 'per_world_wall_seconds': 36000, 'max_online_sessions': 1440,
    'max_learning_epochs': 108, 'max_learning_target_replays': 1296,
    'employee_target_and_optimizer_physical_calls': 44640,
    'employee_target_and_optimizer_charged_tokens': 792000000, 'logical_actor_interviews': 3972,
    'actor_physical_model_calls': None, 'actor_tokens': None, 'currency_cost': None}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def expected_config(seed, algorithm):
    return ExperimentConfig(algorithm=algorithm, seed=seed, days=20,
        enterprise_count=4, consumer_count=8, split='dev', state_mode='skill_transfer',
        decision_every=4, update_every=4, update_days=[3, 7, 11, 17], feedback_delay=1, max_iterations=16,
        max_output_tokens=4096, max_work_sessions=240, max_run_seconds=36000,
        max_learning_calls=7200, max_learning_tokens=144000000,
        max_learning_calls_per_epoch=200, max_learning_tokens_per_epoch=4000000,
        max_learning_seconds_per_epoch=1800, max_actor_interviews=662,
        train_cases=2, val_cases=2, edit_budget=4, skillopt_rollouts_k=2,
        focal_employee=None, schema_version=2).public()


def campaign_check(root):
    manifest = read(root / 'campaign.json')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1
            and manifest['kind'] == 'multi_seed_reacting_world_comparison', 'wrong_campaign_schema')
    require(reports_equal(manifest['seeds'], SEEDS) and manifest['algorithms'] == ARMS
            and reports_equal(manifest['population'], POPULATION) and type(manifest['days']) is int
            and manifest['days'] == 20 and reports_equal(manifest['budgets'], BUDGETS), 'campaign_preregistered_design_mismatch')
    require(manifest['design']['primary'] == 'Equal-world mean difference in fixed initial/benchmark commitment fulfillment.'
            and manifest['design']['inference_unit'] == 'world pair; three development pairs are descriptive'
            and manifest['design']['selection'] == 'All employees; no outcome-conditioned selection, replacement, extension or stopping.',
            'campaign_estimand_or_selection_changed')
    sources = manifest['source_sha256']
    require(REQUIRED_SOURCES <= sources.keys(), 'missing_campaign_source_provenance')
    require(all(sha(child(ROOT, name)) == value for name, value in sources.items()), 'campaign_source_revision_mismatch')
    require(manifest['dependencies'] == dependency_provenance()
            and all(manifest['dependencies'].get(name, {}).get('revision') for name in ('hermes', 'mirofish', 'skillopt')),
            'campaign_dependency_revision_mismatch')
    expected = [(seed, arm) for index, seed in enumerate(SEEDS)
                for arm in (ARMS if index % 2 == 0 else ARMS[::-1])]
    slots = manifest['slots']
    require(len(slots) == 6 and [(s['seed'], s['algorithm']) for s in slots] == expected, 'campaign_slot_schedule')
    cohorts, all_personas = {}, set()
    for seed in SEEDS:
        path = root / 'cohorts' / f'{seed}.json'
        data = read(path); ids = [row['persona_id'] for row in data['personas']]
        require(len(ids) == len(set(ids)) == 25 and not all_personas.intersection(ids), 'campaign_persona_cohort_identity')
        all_personas.update(ids); cohorts[seed] = sha(path)
    for slot in slots:
        run_id = f"seed-{slot['seed']}-{slot['algorithm']}"
        require(slot['run_id'] == run_id and slot['relative_path'] == 'runs/' + run_id, 'campaign_run_path_or_identity')
        run = child(root, slot['relative_path'])
        cfg = expected_config(slot['seed'], slot['algorithm'])
        require(reports_equal(slot['config'], cfg) and read(run / 'config.json') == cfg
                and slot['config_sha256'] == digest(cfg), 'campaign_run_configuration')
        require(slot['persona_cohort_sha256'] == cohorts[slot['seed']] == sha(run / 'persona_cohort.json'), 'campaign_cohort_binding')
    require({p.name for p in (root / 'runs').iterdir() if p.is_dir()} == {s['run_id'] for s in slots}, 'unregistered_campaign_run')
    marker = root / 'EXECUTION.json'
    if marker.exists():
        execution = read(marker)
        require(execution['campaign_sha256'] == sha(root / 'campaign.json')
                and type(execution['workers']) is int and 1 <= execution['workers'] <= 6, 'campaign_execution_binding')
    return manifest


def actor_check(run, cfg, cp, complete):
    """Link each logical dispatch to cached native output and enacted decision."""
    eco, state = cp['ecosystem'], cp['runner']
    employees = {firm + '__' + name for firm, world in eco['worlds'].items() for name in world['employees']}
    institutions = {'agency', *eco['firms'], *eco['consumers']}
    ledger_path = run / 'actors/evaluation_interview_ledger.json'
    cache = run / 'actors/mirofish_interviews'
    if not ledger_path.exists():
        require(not complete and not list(cache.glob('*.json')), 'missing_actor_dispatch_ledger')
        return {'logical_requests': 0, 'pending_requests': 0, 'physical_model_calls': None, 'tokens': None}
    ledger = read(ledger_path); rows = ledger['requests']
    require(ledger['schema_version'] == 1 and ledger['limit'] == cfg['max_actor_interviews']
            and ledger['accounting_unit'] == 'logical_mirofish_interview_request'
            and ledger['physical_model_calls'] is None and ledger['tokens'] is None, 'actor_ledger_unit_or_limit')
    require(len(rows) <= 662 and len({r['key'] for r in rows}) == len(rows), 'actor_dispatch_count_or_duplicate')
    for row in rows:
        require(row['actor'] in employees | institutions and row['status'] in ('dispatched', 'completed'), 'actor_dispatch_identity')
        path = child(cache, row['key'] + '.json')
        if row['status'] == 'completed':
            native = read(path)
            require(native['employee_id'] == row['actor'] and text_sha(native['prompt']) == row['prompt_sha256']
                    and text_sha(native['response']) == row['response_sha256'], 'actor_native_cache_binding')
        else:
            require(not complete, 'completed_run_has_uncertain_actor_request')
    require({p.stem for p in cache.glob('*.json')} <= {r['key'] for r in rows}, 'unmetered_actor_cache')
    row_map = {r['key']: r for r in rows}
    decision_keys = set()
    for folder, institutional in (('actor_decisions', True), ('employee_decisions', False)):
        for path in (run / folder).glob('*.json'):
            key = path.stem; decision_keys.add(key); data = read(path)
            final = key + '-repair' if key + '-repair' in row_map else key
            require(final in row_map and row_map[final]['status'] == 'completed', 'decision_missing_completed_actor_request')
            require(parse_object(read(child(cache, final + '.json'))['response']) == data['decision'], 'enacted_actor_decision_differs_from_native')
            require(row_map[final]['actor'] in (institutions if institutional else employees), 'decision_wrong_actor_role')
            if institutional:
                require(data['view']['actor_id'] == row_map[final]['actor'], 'institutional_view_identity')
    for row in rows:
        base = row['key'].removesuffix('-repair')
        require(row['key'] == base or base in row_map and row_map[base]['actor'] == row['actor'], 'orphan_actor_repair')
        if complete:
            require(base in decision_keys, 'unreconciled_actor_request')
    if complete:
        spec = scenario(ExperimentConfig(**cfg))
        days = {d for d in range(cfg['days']) if d % cfg['decision_every'] == 0} | {s['day'] for s in spec['shock_schedule']}
        expected = {f'd{day:03d}-{actor}' for day in days for actor in institutions}
        require({p.stem for p in (run / 'actor_decisions').glob('*.json')} == expected, 'institutional_decision_schedule')
        require({p.stem for p in (run / 'employee_decisions').glob('*.json')} == {r['id'] for r in state['sessions']}, 'employee_decision_session_inventory')
        for record in state['sessions']:
            require(row_map[record['id']]['actor'] == record['employee'], 'employee_request_session_binding')
    return {'logical_requests': len(rows), 'pending_requests': sum(r['status'] != 'completed' for r in rows),
            'physical_model_calls': None, 'tokens': None}


def learning_progress_check(run, cfg, update, previous):
    from scripts.audit_learning_v2 import reconcile, version
    directory = run / f"learning/d{update['day']:03d}-{update['employee']}"
    progress = read(directory / 'progress.json')
    require(all(progress[k] == update[k] for k in ('employee', 'day', 'employee_epoch_index',
        'status', 'epoch_allocation', 'replay_artifacts', 'optimizer_transport_audit', 'accepted', 'deployed_version', 'costs'))
        and progress['parent_skill_sha256'] == update['skill_before_sha256'], 'epoch_progress_update_binding')
    own = [u for u in previous if u['employee'] == update['employee']]
    require(update['employee_epoch_index'] == len(own) + 1, 'employee_epoch_sequence')
    alloc = update['epoch_allocation']
    calls = lambda rows: sum(u['costs']['target_model_calls'] + u['costs']['optimizer_model_calls'] for u in rows)
    tokens = lambda rows: sum(u['costs']['tokens'] for u in rows)
    expected = {'fleet_remaining_model_calls': 7200 - calls(previous), 'fleet_remaining_tokens': 144000000 - tokens(previous),
                'employee_remaining_model_calls': 600 - calls(own), 'employee_remaining_tokens': 12000000 - tokens(own)}
    require(all(alloc[k] == v for k, v in expected.items()) and alloc['eligible_employee_count'] == 12
            and alloc['model_calls'] == min(200, expected['fleet_remaining_model_calls'], expected['employee_remaining_model_calls'])
            and alloc['tokens'] == min(4000000, expected['fleet_remaining_tokens'], expected['employee_remaining_tokens'])
            and 0 < alloc['seconds'] <= 1800, 'epoch_allocation_mismatch')
    require(alloc['configured_caps'] == {k: cfg[k] for k in ('max_learning_calls_per_epoch', 'max_learning_tokens_per_epoch', 'max_learning_seconds_per_epoch')},
            'epoch_configured_caps_mismatch')
    targets = [op for op in update['costs']['operations'] if op['kind'] == 'target']
    evidence = update['replay_artifacts']
    identities = reconcile(update) if version(update) == 2 else update['replay_evidence']
    require(len(evidence) == len(targets) == len(identities), 'epoch_replay_artifact_inventory')
    for index, (row, op, replay) in enumerate(zip(evidence, targets, identities)):
        case_name = 'private/cases/' + replay['id'] + '.json'
        relative = str((directory / f'trial-{index:03d}/session.json').relative_to(run))
        require(row['capsule_path'] == case_name and row['capsule_sha256'] == sha(child(run, case_name))
                and row['session_path'] == relative and row['session_sha256'] == sha(child(run, relative)), 'epoch_raw_artifact_hash')
        record = read(child(run, relative))
        require(row['dispatch_status'] == 'returned' and row['usage_known'] is True
                and row['attempt_index'] == replay['attempt_index'] == op['attempt_index'] == index
                and row['sample_id'] == replay['sample_id'] == op['sample_id']
                and row['phase'] == replay['phase'] == op['phase']
                and row['experience_id'] == replay['id'] == op['task_id']
                and row['source_task_id'] == record['task_id'] and row['employee'] == record['employee']
                and row['skill_sha256'] == record['skill']['content_sha256'] == replay['skill_sha256']
                and row['limits'] == op['limits'], 'epoch_replay_provenance')
        require(all(row['usage'][k] == record['usage'].get(k) for k in row['usage'])
                and all(row[k] == record[k] for k in ('success', 'semantic_score', 'infrastructure_valid', 'skill_loaded')),
                'epoch_replay_receipt_mismatch')
        meter = record['result']['native']['evaluation_budget']
        require(meter['physical_model_calls'] <= 16 and meter['charged_tokens'] <= 250000
                and all(op['output_cap'] <= 4096 for op in meter['operations']), 'replay_physical_budget_exceeded')
    require(progress['target_progress'] == {'dispatched_replays': len(evidence), 'returned_replays': len(evidence),
        'unknown_usage_replays': 0, 'charged_or_reserved_model_calls': sum(op['model_calls'] for op in targets),
        'charged_or_reserved_tokens': sum(op['tokens'] for op in targets)}, 'epoch_progress_cost_totals')
    optimizers = [op for op in update['costs']['operations'] if op['kind'] == 'optimizer']
    require(len(progress['optimizer_dispatches']) == len(optimizers)
            and len(update['optimizer_inputs']) in ((len(optimizers), len(optimizers) + 1)
                if update['status'] == 'budget_exhausted' else (len(optimizers),)), 'epoch_optimizer_dispatch_inventory')
    for index, (row, op, payload) in enumerate(zip(progress['optimizer_dispatches'], optimizers, update['optimizer_inputs'])):
        require(row['attempt_index'] == index and row['dispatch_status'] == 'returned' and row['limits'] == op['limits']
                and row['prompt_sha256'] == text_sha(payload['prompt'])
                and row['receipt']['tokens'] == op['tokens'] and row['receipt']['model_calls'] == op['model_calls'], 'epoch_optimizer_dispatch_binding')


def eligibility_check(state, cfg):
    """Bind the recorded selector output to the actual optimizer input pool."""
    logs = {(row['employee'], row['day']): row for row in state.get('learning_eligibility', [])}
    for (employee, day), row in logs.items():
        selected = select_experiences(state['experiences'], employee, day, cfg['train_cases'], cfg['val_cases'])
        require(row['selected_ids'] == [experience['id'] for experience in selected], 'eligibility_selected_pool_mismatch')
        version = sum(update['accepted'] for update in state['updates']
                      if update['employee'] == employee and update['day'] < day)
        require(type(row['deployed_version_before']) is int and row['deployed_version_before'] == version,
                'eligibility_deployed_version_mismatch')
    for update in state['updates']:
        log = logs.get((update['employee'], update['day']))
        require(log is not None and log['eligible'] is True and log['treatment_enabled'] is True
                and log['selected_ids'] == update['train_ids'] + update['validation_ids'], 'update_selected_pool_mismatch')


def run_check(root, campaign, slot):
    run, cfg = child(root, slot['relative_path']), slot['config']
    result = {'run_id': slot['run_id'], 'seed': slot['seed'], 'algorithm': slot['algorithm'],
              'status': 'not_started', 'ok': True, 'completed': False, 'model_quality_score': None}
    if not (run / 'manifest.json').exists():
        require(not any((run / name).exists() for name in ('checkpoint.json', 'REPORT.json', 'REPORT.v2.json')), 'run_evidence_without_manifest')
        return result, None
    manifest = read(run / 'manifest.json')
    require(reports_equal(manifest['config'], cfg) and manifest['scenario'] == scenario(ExperimentConfig(**cfg)), 'run_manifest_configuration')
    require(all(manifest[k] == campaign[k] for k in ('source_sha256', 'dependencies', 'target_model', 'model_base_url')), 'run_campaign_provenance')
    if not (run / 'checkpoint.json').exists():
        result['status'] = 'initializing'
        return result, None
    cp = read(run / 'checkpoint.json'); eco, state = cp['ecosystem'], cp['runner']
    roster = {firm + '__' + name for firm, world in eco['worlds'].items() for name in world['employees']}
    require(len(eco['firms']) == len(eco['worlds']) == 4 and len(roster) == 12 and len(eco['consumers']) == 8
            and eco['agency']['id'] == 'agency' and set(state['skills']) == set(state['skill_versions']) == roster, 'run_population_mismatch')
    report = read(run / 'REPORT.json') if (run / 'REPORT.json').exists() else None
    status = report['status'] if report else 'running'
    complete = status == 'completed'
    # The native bootstrap starts after the day -1 checkpoint and before the
    # v000 files exist. This is observable startup, not scored employee work.
    if eco['day'] == -1 and report is None and not state['sessions'] and not state['updates']:
        require(not state['experiences'] and not state['learning_calls'] and not state['learning_tokens']
                and all(version == 0 for version in state['skill_versions'].values())
                and not list((run / 'work').glob('*/session.json'))
                and not list((run / 'learning').glob('*/update.json')), 'initializing_run_has_work_evidence')
        result.update(status='initializing', actor_accounting=actor_check(run, cfg, cp, False))
        return result, None
    native = audit_run(run, strict=complete)
    require(native['ok'], 'run_raw_artifact_audit_failed')
    actor = actor_check(run, cfg, cp, complete)
    result.update(status=status, completed=complete, native_audit=native, actor_accounting=actor,
                  sessions=len(state['sessions']), updates=len(state['updates']),
                  accepted_updates=sum(u['accepted'] for u in state['updates']))
    exposure = build_scale_summary({**campaign, 'slots': [slot]},
        [{'run_id': slot['run_id'], 'checkpoint': cp, 'report': report}])
    result['learning_exposure_audit'] = {'complete': exposure['complete'],
        'issues': exposure['evidence_issues'],
        'observed_learning_boundaries': exposure['observed_learning_boundaries']}
    if not complete:
        result['pending_artifacts'] = sorted(str(p.relative_to(run)) for pattern in ('**/INFLIGHT.json', '**/FAILURE.json') for p in run.glob(pattern))
        return result, None
    require(not (run / 'REPORTING_FAILURE.json').exists(), 'unresolved_versioned_reporting_failure')
    require(exposure['complete'], 'completed_run_learning_eligibility_or_exposure_mismatch')
    eligibility_check(state, cfg)
    provenance = report['provenance']
    require(provenance['actor_driver'] == 'lifespan.evaluation.runner.NativeActors'
            and provenance['executor'] == 'lifespan.evaluation.runtime.execute_case'
            and provenance['persona_cohort_sha256'] == slot['persona_cohort_sha256'], 'non_native_or_wrong_cohort_execution')
    require(len(state['sessions']) <= 240, 'online_session_budget_exceeded')
    for record in state['sessions']:
        require('last_submitted_artifact_sha256' in record, 'missing_online_submitted_byte_evidence')
        meter = record['result']['native']['evaluation_budget']
        require(meter['physical_model_calls'] <= 16 and meter['charged_tokens'] <= 250000
                and all(op['output_cap'] <= 4096 for op in meter['operations']), 'online_physical_budget_exceeded')
    employee_updates = Counter()
    for update_index, update in enumerate(state['updates']):
        employee_updates[update['employee']] += 1
        require(update['day'] in (7, 11, 17) and len(update['train_ids']) == len(update['validation_ids']) == 2,
                'unplanned_learning_day_or_pool')
        uc = update['configuration']
        require(uc['rollouts_k'] == 2 and uc['edit_budget'] == 4 and uc['gate_metric'] == 'mixed'
                and uc['gate_no_regression'] is True and uc['gate_mode'] == 'on' and uc['evolve_memory'] is False,
                'learning_method_changed')
        gate_check(update)
        learning_progress_check(run, cfg, update, state['updates'][:update_index])
        calls = update['costs']['target_model_calls'] + update['costs']['optimizer_model_calls']
        require(calls <= 200 and update['costs']['tokens'] <= 4000000 and update['costs']['replays'] <= 12,
                'learning_epoch_budget_exceeded')
        directory = run / f"learning/d{update['day']:03d}-{update['employee']}"
        for path in directory.glob('trial-*/session.json'):
            record = read(path)
            require('last_submitted_artifact_sha256' in record, 'missing_learning_submitted_byte_evidence')
    require(all(n <= 3 for n in employee_updates.values()) and len(state['updates']) <= 36, 'too_many_learning_epochs')
    require(state['learning_calls'] <= 7200 and state['learning_tokens'] <= 144000000, 'fleet_learning_budget_exceeded')
    for employee in roster:
        own = [u['costs'] for u in state['updates'] if u['employee'] == employee]
        require(sum(u['target_model_calls'] + u['optimizer_model_calls'] for u in own) <= 600
                and sum(u['tokens'] for u in own) <= 12000000, 'employee_lifetime_learning_quota')
    corrected = load_verified_report_v2(run / 'REPORT.v2.json')
    require(corrected['correction_audit']['eligible_for_paired_inference'] is True, 'run_versioned_report_ineligible')
    require(corrected['source_breakdown']['fixed_initial_and_benchmark']['accepted_before_work_horizon'] == 240, 'fixed_demand_denominator_changed')
    calls = sum(r['usage']['api_calls'] for r in state['sessions']) + state['learning_calls']
    tokens = sum(r['usage']['total_tokens'] for r in state['sessions']) + state['learning_tokens']
    result.update(learner_physical_calls=calls, learner_measured_tokens=tokens,
        evidence_sha256={name: sha(run / name) for name in ('manifest.json', 'checkpoint.json', 'REPORT.json', 'REPORT.v2.json', 'persona_cohort.json')},
        learning_target_replays=sum(u['costs']['replays'] for u in state['updates']))
    return result, corrected


def supervisor_check(root, campaign, runs, complete):
    """Cleanup errors affect campaign integrity, never employee quality scores."""
    path = root / 'execution_results.json'
    if not path.exists():
        require(not complete, 'completed_campaign_missing_supervisor_receipts')
        return {'complete': False, 'verified_closed_runs': 0}
    rows = read(path)['runs']; slots = {s['run_id']: s for s in campaign['slots']}
    require(len({row['run_id'] for row in rows}) == len(rows)
            and all(row['run_id'] in slots for row in rows), 'supervisor_receipt_inventory')
    completed = {row['run_id'] for row in runs if row['completed']}
    closed = 0
    for row in rows:
        if row['run_id'] not in completed:
            continue
        run = child(root, slots[row['run_id']]['relative_path'])
        cleanup = row['actor_cleanup']
        require(type(row['exit_code']) is int and row['exit_code'] == 0, 'completed_world_supervisor_exit_failure')
        require(cleanup['status'] == 'closed' and cleanup['simulation_id'] ==
                read(run / 'actors/mirofish_state.json')['simulation']['simulation_id']
                and cleanup == read(run / 'SUPERVISOR_ACTOR_CLEANUP.json'), 'world_actor_cleanup_unconfirmed_or_unbound')
        closed += 1
    if complete:
        require((root / 'EXECUTION.json').exists() and len(rows) == closed == 6, 'completed_campaign_missing_supervisor_receipts')
    return {'complete': complete and closed == 6, 'verified_closed_runs': closed}


def audit_campaign(directory, strict=False):
    root = Path(directory).resolve()
    output = {'schema_version': 1, 'kind': 'multi_seed_campaign_integrity_audit', 'status': 'invalid',
              'errors': [], 'notes': [], 'runs': [], 'planned_runs': 6, 'planned_pairs': 3,
              'model_quality_score': None, 'accounting_verified': False}
    try:
        campaign = campaign_check(root); reports = []
        for slot in campaign['slots']:
            try:
                run, report = run_check(root, campaign, slot)
                output['runs'].append(run)
                if report is not None:
                    reports.append(report)
            except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
                code = str(exc) if type(exc) is ValueError else type(exc).__name__
                output['runs'].append({'run_id': slot['run_id'], 'seed': slot['seed'], 'algorithm': slot['algorithm'],
                                       'status': 'invalid', 'ok': False, 'completed': False, 'error': code})
                output['errors'].append({'run_id': slot['run_id'], 'code': code})
        completed = [r for r in output['runs'] if r['completed']]
        complete_seeds = [s for s in SEEDS if {r['algorithm'] for r in completed if r['seed'] == s} == set(ARMS)]
        comparison = compare_reports_v2(reports)
        require(not comparison['rejected_pairs'] and len(comparison['eligible_pairs']) == len(complete_seeds), 'incompatible_completed_world_pair')
        missing = [{'seed': s, 'runs': [r['run_id'] for r in output['runs'] if r['seed'] == s and not r['completed']]} for s in SEEDS if s not in complete_seeds]
        output.update(completed_runs=len(completed), complete_pairs=len(complete_seeds), missing_or_invalid_pairs=missing, comparison=comparison)
        if (root / 'COMPARISON.json').exists():
            require(reports_equal(read(root / 'COMPARISON.json'), comparison), 'saved_campaign_comparison_mismatch')
        measured_calls = sum(r['learner_physical_calls'] for r in completed)
        measured_tokens = sum(r['learner_measured_tokens'] for r in completed)
        logical = sum(r.get('actor_accounting', {}).get('logical_requests', 0) for r in output['runs'])
        require(measured_calls <= BUDGETS['employee_target_and_optimizer_physical_calls']
                and measured_tokens <= BUDGETS['employee_target_and_optimizer_charged_tokens']
                and logical <= BUDGETS['logical_actor_interviews'], 'campaign_budget_exceeded')
        all_complete = len(completed) == 6 and len(complete_seeds) == 3 and not output['errors']
        output['accounting'] = {'complete': all_complete, 'learner_physical_calls': measured_calls if all_complete else None,
            'learner_measured_tokens': measured_tokens if all_complete else None,
            'verified_completed_run_calls': measured_calls, 'verified_completed_run_tokens': measured_tokens,
            'environment': {'logical_interview_requests': logical, 'physical_model_calls': None, 'tokens': None,
                            'accounting_complete': False, 'note': 'Graph, social and OASIS physical inference remains unmetered.'}}
        output['accounting_verified'] = all_complete
        try:
            output['supervisor_audit'] = supervisor_check(root, campaign, output['runs'], all_complete)
        except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
            output['errors'].append({'location': 'supervisor_resource_cleanup',
                'code': str(exc) if type(exc) is ValueError else type(exc).__name__})
            output['notes'].append('Execution costs above remain verified independently of this supervisor/cleanup error; it is not an employee behavioral failure.')
        output['status'] = 'invalid' if output['errors'] else 'valid_completed' if all_complete else 'incomplete'
        output['notes'].append('Three preregistered development world pairs are descriptive; all planned slots remain visible. No session-level independence or all-in cost claim.')
        if not all_complete:
            output['notes'].append('Missing, interrupted and invalid worlds are not behavioral failures; totals exclude unverified/in-flight charges and therefore are not complete campaign costs.')
    except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
        output['errors'].append({'location': 'campaign', 'code': str(exc) if type(exc) is ValueError else type(exc).__name__})
    output['ok'] = not output['errors'] and (not strict or output['status'] == 'valid_completed')
    return output


audit_scale = audit_campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path); parser.add_argument('--strict', action='store_true')
    args = parser.parse_args(); result = audit_campaign(args.run, args.strict)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
