#!/usr/bin/env python3
"""Create an allowlisted publication draft for a completed scale-v1 campaign.

This independent postprocessor makes no model calls and publishes nothing. It
requires the strict native campaign audit and a byte-identical preregistration,
then writes SUMMARY.json and REPORT.md to a new directory. Fixture tests stub
the audit; their generated reports are never native benchmark evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.evaluation.metrics import _execution_costs, _learning_costs
from scripts import audit_scale_cli, scale_world_dynamics
from scripts.scale_summary import build_scale_summary

VERSION = 'scale-publication-v1'
audit_campaign = audit_scale_cli.audit_campaign_cli
RUN_FILES = ('manifest.json', 'checkpoint.json', 'REPORT.json', 'REPORT.v2.json', 'persona_cohort.json')
COMMITMENT_FIELDS = (
    'accepted_before_work_horizon', 'actionable_before_work_horizon',
    'fulfilled_before_work_horizon', 'unfulfilled_at_work_horizon',
    'fulfilled_at_observation', 'unfulfilled_at_observation',
    'pending_at_observation', 'abandoned_at_observation', 'settled_at_observation',
    'right_censored_unfulfilled', 'awaiting_availability_at_work_horizon',
    'arrived_during_outcome_window', 'scheduled_not_materialized_at_observation',
    'available_but_unfinished_at_work_horizon', 'materialized_at_observation',
    'availability_unknown', 'missing_task_evidence',
)
SOURCES = ('initial', 'benchmark', 'fixed_initial_and_benchmark', 'native_consumer', 'unknown')
EXPOSURE_FIELDS = ('sessions', 'valid_sessions', 'successes', 'unknown_outcomes', 'unique_obligations')
CAVEATS = [
    'Three preregistered development world pairs are descriptive. No causal efficacy, population generalization, or statistical significance claim is made.',
    'The primary endpoint is the equal-world mean paired difference in fixed initial/benchmark commitment fulfillment. All six planned worlds remain visible; native consumer orders are reported separately.',
    'Employees, tasks, retries, learning replays, and regime exposures within a world are dependent. No session-level confidence interval or effective sample-size claim is made.',
    'Paired arms share starting cohorts and exogenous schedules, but native actors can react differently. These reacting worlds are not an isolated causal test of a skill edit.',
    'World-state trajectories are a descriptive reporting supplement introduced during execution before learning began; they are not an additional preregistered endpoint.',
    'Work is limited to days 0–19, with settlement-only days 20–21. Pending and delayed commitments remain visible; results do not demonstrate indefinite lifelong learning.',
    'Optimizer training and gate replay outcomes are separate from prospective online work. Adoption counts describe the recorded gate decision, not proven out-of-sample benefit.',
    'Measured employee/optimizer calls and tokens exclude unmetered environment inference. Logical actor requests are not physical model calls. Currency and all-in costs remain unknown.',
    'This draft contains allowlisted aggregates only. Private prompts, cases, responses, skills, profiles, and logs must not be attached to a public release.',
]


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value, *, nonnegative=True):
    require(type(value) in (int, float) and math.isfinite(value)
            and (not nonnegative or value >= 0), 'invalid_numeric_evidence')
    return value


def count(value):
    require(type(value) is int and value >= 0, 'invalid_count_evidence')
    return value


def close(left, right):
    return type(left) in (int, float) and type(right) in (int, float) and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _load(path):
    raw = path.read_bytes()
    def invalid_constant(_):
        raise ValueError('nonfinite_json_input')
    return json.loads(raw, parse_constant=invalid_constant), sha(raw)


def _measure(raw):
    result = {key: count(raw[key]) for key in ('records', 'measured_records', 'missing_records')}
    require(type(raw['complete']) is bool, 'invalid_measure_completeness')
    result.update(complete=raw['complete'], recorded_total=number(raw['recorded_total']),
                  total=None if raw['total'] is None else number(raw['total']))
    require(result['records'] == result['measured_records'] + result['missing_records'], 'measure_count_closure')
    require((result['total'] is not None) == result['complete'], 'measure_total_completeness')
    if result['complete']:
        require(result['missing_records'] == 0 and close(result['total'], result['recorded_total']), 'measure_total_closure')
    return result


def _costs(report, state):
    # Recompute with the frozen metric implementation; export only known scalar
    # measures. Never copy provider receipts, operations, or diagnostic text.
    execution, learning = _execution_costs(state['sessions']), _learning_costs(state['updates'])
    result = {}
    fields = {
        'execution': ('tokens', 'charged_tokens', 'prompt_tokens', 'completion_tokens', 'model_calls', 'estimated_usd', 'wall_seconds'),
        'learning': ('tokens', 'charged_or_reserved_tokens', 'target_model_calls', 'optimizer_model_calls', 'replays', 'estimated_usd', 'wall_seconds'),
    }
    for name, expected in (('execution', execution), ('learning', learning)):
        raw = report['costs'][name]
        safe = {key: _measure(raw[key]) for key in fields[name]}
        for key, value in safe.items():
            require(value == _measure(expected[key]), 'checkpoint_report_cost_mismatch')
        require(raw['accounting_complete'] is expected['accounting_complete'] is True, 'incomplete_measured_costs')
        safe['accounting_complete'] = True
        safe['currency_status'] = 'estimate_available' if safe['estimated_usd']['complete'] else 'unknown'
        result['online' if name == 'execution' else name] = safe
    return result


def _commitments(raw):
    result = {key: count(raw[key]) for key in COMMITMENT_FIELDS}
    denominator, fulfilled = result['accepted_before_work_horizon'], result['fulfilled_before_work_horizon']
    require(fulfilled + result['unfulfilled_at_work_horizon'] == denominator
            and result['fulfilled_at_observation'] + result['unfulfilled_at_observation'] == denominator, 'commitment_closure')
    require(result['missing_task_evidence'] == 0, 'missing_commitment_evidence')
    require(all(value <= denominator for value in result.values()), 'commitment_subset_count')
    rate = fulfilled / denominator if denominator else None
    require(raw['fulfillment_rate'] is None if rate is None else close(raw['fulfillment_rate'], rate), 'commitment_rate_mismatch')
    result['fulfillment_rate'] = rate
    return result


def _optimizer(updates):
    rows = []
    for update in updates:
        status, gate = update['status'], update['gate_evidence']
        require(status in ('completed', 'budget_exhausted', 'failed') and type(update['accepted']) is bool, 'invalid_update_status')
        complete = all(type(gate.get(key)) is list for key in ('applied_edits', 'rejected_edits', 'unmatched_edits', 'gate_trials'))
        require(status != 'completed' or complete, 'completed_update_missing_gate_bookkeeping')
        if complete:
            require(all(type(edit) is dict for key in ('applied_edits', 'rejected_edits', 'unmatched_edits')
                        for edit in gate[key]), 'invalid_edit_record')
        values = {key: len(gate[key]) if complete else None for key in ('applied_edits', 'rejected_edits', 'unmatched_edits')}
        trials = gate.get('gate_trials', []) if complete else []
        require(all(row.get('target') in ('skill', 'memory', 'final') and type(row.get('accepted')) is bool for row in trials), 'invalid_gate_trial')
        require(type(update.get('optimizer_inputs')) is list, 'missing_reflection_input_count')
        rows.append({'employee': update['employee'], 'day': count(update['day']), 'status': status,
            'adopted': update['accepted'], 'gate_bookkeeping_complete': complete,
            'reflection_inputs_prepared': len(update['optimizer_inputs']),
            'optimizer_physical_calls': count(update['costs']['optimizer_model_calls']),
            'recorded_edit_proposals': sum(values.values()) if complete else None, **values,
            'scored_candidate_trials': sum(row['target'] != 'final' for row in trials) if complete else None,
            'final_gate_rechecks': sum(row['target'] == 'final' for row in trials) if complete else None})
    fields = ('reflection_inputs_prepared', 'optimizer_physical_calls', 'recorded_edit_proposals',
              'applied_edits', 'rejected_edits', 'unmatched_edits', 'scored_candidate_trials', 'final_gate_rechecks')
    return {'epochs': len(rows), 'accepted_epochs': sum(row['adopted'] for row in rows),
        'gate_recorded_epochs': sum(row['gate_bookkeeping_complete'] for row in rows),
        'gate_unreported_epochs': sum(not row['gate_bookkeeping_complete'] for row in rows),
        'epochs_with_recorded_edit_proposals': sum((row['recorded_edit_proposals'] or 0) > 0 for row in rows),
        'recorded_totals': {key: sum(row[key] or 0 for row in rows) for key in fields}, 'updates': rows,
        'interpretation': 'Edit totals count returned applied/rejected/unmatched records, not unique semantic ideas. Applied edits survived the final gate. '
            'Missing gate bookkeeping is unknown; recorded totals cover observed records only. Scored candidates exclude final rechecks. '
            'Prepared reflection inputs can precede a budget refusal; they are not physical call counts.'}


def _online(state, report):
    sessions = state['sessions']
    require(all(type(row.get('success')) is bool and row.get('infrastructure_valid') is True for row in sessions), 'invalid_online_outcome')
    scores = [number(row['semantic_score']) for row in sessions]
    require(all(score <= 1 for score in scores), 'semantic_score_range')
    identities = {(row['employee'], row['task_id']) for row in sessions}
    result = {'attempts': len(sessions), 'strict_successes': sum(row['success'] for row in sessions),
        'distinct_obligations_attempted': len(identities), 'retry_attempts': len(sessions) - len(identities),
        'strict_success_rate': sum(row['success'] for row in sessions) / len(sessions) if sessions else None,
        'mean_semantic_score': sum(scores) / len(scores) if scores else None,
        'budget_exhausted_attempts': sum(row.get('budget_exhausted') is True or row.get('usage', {}).get('budget_exhausted') is True for row in sessions)}
    for key, value in result.items():
        actual = report['prospective'][key]
        require(actual is None if value is None else close(actual, value), 'checkpoint_report_online_mismatch')
    return result


def _aggregate_costs(worlds):
    result = {}
    for scope in ('online', 'learning'):
        keys = worlds[0]['costs'][scope].keys()
        result[scope] = {}
        for key in keys:
            if key in ('accounting_complete', 'currency_status'):
                continue
            rows = [world['costs'][scope][key] for world in worlds]
            complete = all(row['complete'] for row in rows)
            result[scope][key] = {'total': sum(row['total'] for row in rows) if complete else None,
                'recorded_total': sum(row['recorded_total'] for row in rows),
                'complete': complete, 'measured_runs': sum(row['complete'] for row in rows), 'planned_runs': len(worlds)}
        result[scope]['accounting_complete'] = True
    execution, learning = result['online'], result['learning']
    currency = [scope['estimated_usd']['total'] for scope in (execution, learning)]
    result['employee_and_optimizer'] = {
        'measured_physical_calls': execution['model_calls']['total'] + learning['target_model_calls']['total'] + learning['optimizer_model_calls']['total'],
        'measured_tokens': execution['tokens']['total'] + learning['tokens']['total'],
        'charged_or_reserved_tokens': execution['charged_tokens']['total'] + learning['charged_or_reserved_tokens']['total'],
        'estimated_usd': sum(currency) if all(value is not None for value in currency) else None}
    return result


def _pairs(worlds):
    pairs = []
    for seed in sorted({row['seed'] for row in worlds}):
        arms = {row['algorithm']: row for row in worlds if row['seed'] == seed}
        require(set(arms) == {'no_learning', 'skillopt'}, 'incomplete_world_pair')
        base, learned = arms['no_learning'], arms['skillopt']
        pairs.append({'seed': seed, 'deltas': {
            'fixed_demand_fulfillment_rate': learned['primary_fixed_demand']['fulfillment_rate'] - base['primary_fixed_demand']['fulfillment_rate'],
            'all_commitment_fulfillment_rate': learned['all_commitments']['fulfillment_rate'] - base['all_commitments']['fulfillment_rate'],
            'realized_synthetic_utility': learned['business']['realized_utility'] - base['business']['realized_utility']}})
    return {'direction': 'skillopt minus no_learning', 'inference_unit': 'world pair', 'pairs': pairs,
        'equal_world_mean_deltas': {key: sum(row['deltas'][key] for row in pairs) / len(pairs) for key in pairs[0]['deltas']},
        'confidence_interval': None, 'interpretation': 'Three development pairs; descriptive differences only.'}


def _audit_provenance(audit, campaign_sha, hashes, identifiers):
    """Allowlist the additive alias correction; retain the frozen audit failure."""
    raw, original = audit['correction'], audit['frozen_audit']
    require(raw['scope'] == 'Known native CLI module alias only' and raw['campaign_sha256'] == campaign_sha
            and raw['observation_kind'] == 'during_execution_not_preregistered'
            and raw['observed_actor_driver'] == '__main__.NativeActors'
            and raw['resolved_actor_driver'] == 'lifespan.evaluation.runner.NativeActors'
            and raw['frozen_sources_changed'] is False and raw['raw_reports_rewritten'] is False
            and type(raw['matched_ast_guards']) is int and raw['matched_ast_guards'] == 1,
            'unsupported_audit_correction')
    require(raw['launch_receipts_sha256'] == hashes['CLI_LAUNCH_RECEIPTS.json']
            and raw['corrected_auditor_sha256'] == sha(Path(audit_scale_cli.__file__).read_bytes())
            and raw['frozen_auditor_sha256'] == sha((ROOT / 'scripts/audit_scale.py').read_bytes()), 'audit_correction_source_binding')
    require(isinstance(raw['published_commit'], str) and re.fullmatch('[0-9a-f]{40}', raw['published_commit']), 'invalid_correction_commit')
    errors = original['errors']
    require(original['status'] == 'invalid' and original['ok'] is False and len(errors) == 6
            and {row.get('run_id') for row in errors} == identifiers
            and all(row.get('code') == 'non_native_or_wrong_cohort_execution' for row in errors), 'unexplained_frozen_audit_failure')
    saved_hash = hashes.get('AUDIT.json')
    require(raw['original_saved_audit_sha256'] == saved_hash, 'saved_original_audit_binding')
    saved_status = raw['original_saved_audit_status']
    require(saved_status in (None, 'invalid', 'incomplete', 'valid_completed'), 'unknown_saved_audit_status')
    return {'strict': True, 'corrected_status': 'valid_completed', 'completed_runs': 6, 'complete_pairs': 3,
        'frozen_status': 'invalid', 'frozen_errors': [{'run_id': row['run_id'], 'code': 'non_native_or_wrong_cohort_execution'} for row in errors],
        'correction': {'scope': 'Known native CLI module alias only', 'campaign_sha256': campaign_sha,
            'launch_receipts_sha256': raw['launch_receipts_sha256'], 'frozen_auditor_sha256': raw['frozen_auditor_sha256'],
            'corrected_auditor_sha256': raw['corrected_auditor_sha256'], 'published_commit': raw['published_commit'],
            'observed_actor_driver': '__main__.NativeActors', 'resolved_actor_driver': 'lifespan.evaluation.runner.NativeActors',
            'observation_kind': 'during_execution_not_preregistered', 'matched_ast_guards': 1,
            'original_saved_audit_sha256': saved_hash, 'original_saved_audit_status': saved_status,
            'frozen_sources_changed': False, 'raw_reports_rewritten': False}}


def _markdown(summary):
    lines = ['# Scale-v1 completed development study — draft', '',
        f"Preregistered campaign SHA-256: `{summary['provenance']['campaign_raw_sha256']}`.", '',
        'All six planned worlds passed the strict native campaign audit with the separately recorded CLI module-alias correction. '
        'The frozen auditor rejected the recorded actor class name; the correction verifies the native launcher and changes that comparison only. '
        'Original audit failures and correction hashes remain in JSON; this correction was documented during execution, not preregistered. '
        'The primary endpoint counts fixed commitments placed before day 20, including delayed arrivals.', '',
        '| Seed | Arm | Fixed fulfilled / placed | All fulfilled / placed | Online successes / attempts | Epochs / adoptions | Recorded edits |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for row in summary['worlds']:
        fixed, all_work, online, opt = row['primary_fixed_demand'], row['all_commitments'], row['online'], row['optimizer']
        lines.append(f"| {row['seed']} | {row['algorithm']} | {fixed['fulfilled_before_work_horizon']} / {fixed['accepted_before_work_horizon']} | "
            f"{all_work['fulfilled_before_work_horizon']} / {all_work['accepted_before_work_horizon']} | {online['strict_successes']} / {online['attempts']} | "
            f"{opt['epochs']} / {opt['accepted_epochs']} | {opt['recorded_totals']['recorded_edit_proposals']} |")
    lines.extend(['', 'Paired differences are SkillOpt minus no-learning, with each world pair weighted equally.', '',
        '| Seed | Fixed-demand fulfillment difference | All-commitment fulfillment difference |', '| --- | --- | --- |'])
    for row in summary['comparison']['pairs']:
        lines.append(f"| {row['seed']} | {row['deltas']['fixed_demand_fulfillment_rate']:+.4f} | {row['deltas']['all_commitment_fulfillment_rate']:+.4f} |")
    mean = summary['comparison']['equal_world_mean_deltas']['fixed_demand_fulfillment_rate']
    lines.extend(['', f'Equal-world mean fixed-demand difference: **{mean:+.4f}**. No confidence interval or causal efficacy claim is made.', '',
        'The JSON draft retains every employee, scheduled eligibility boundary, regime, deployed-version exposure, and optimizer gate count. '
        'Rejected and unmatched edits are counted separately; absent gate bookkeeping remains unknown.', '',
        'World trajectories below are a descriptive supplement added during execution before learning began. '
        'Recorded decisions that leave strategy or route values unchanged are retained separately in JSON. '
        'These are not additional preregistered endpoints.', '',
        '| World | Firm strategy changes / decisions | Delivered route changes | Delivered policy value changes | Native consumer orders |',
        '| --- | --- | --- | --- | --- |'])
    for row in summary['worlds']:
        dynamics = row['world_dynamics']; firms = dynamics['enterprises']
        changes = sum(firm['strategy_change_events'] for firm in firms)
        decisions = sum(firm['recorded_decision_opportunities'] for firm in firms)
        routes = sum(firm['delivered_route_changes'] for firm in firms)
        lines.append(f"| {row['run_id']} | {changes} / {decisions} | {routes} | "
            f"{dynamics['government']['delivered_policy_value_changes']} | {dynamics['endogenous_order_count']} |")
    lines.extend(['',
        '| Measured scope | Physical calls | Tokens | Charged/reserved tokens |', '| --- | --- | --- | --- |'])
    costs = summary['costs']
    for label, scope, call_keys, token_key in (
            ('Online employee work', costs['online'], ('model_calls',), 'charged_tokens'),
            ('Learning replays and optimizer', costs['learning'], ('target_model_calls', 'optimizer_model_calls'), 'charged_or_reserved_tokens')):
        lines.append(f"| {label} | {sum(scope[key]['total'] for key in call_keys):,} | {scope['tokens']['total']:,} | {scope[token_key]['total']:,} |")
    measured = costs['employee_and_optimizer']
    lines.extend([f"| Campaign employee + optimizer | {measured['measured_physical_calls']:,} | {measured['measured_tokens']:,} | {measured['charged_or_reserved_tokens']:,} |", '',
        'These are employee/optimizer totals. Environment physical inference and currency costs are unknown. Summed session/epoch durations in JSON are service time, not elapsed campaign wall time.', '',
        'Limitations:', '', *['- ' + line for line in CAVEATS], ''])
    return '\n'.join(lines)


def report_scale(campaign_dir, out_dir, *, preregistration_path):
    """Write a new local draft only after completed, hash-bound native evidence.

    No bypass exists for incomplete studies. The preregistration must be the
    previously published manifest bytes, not a freshly rewritten equivalent.
    Caller-side publication/review remains separate from this offline helper.
    """
    root, out, prereg = Path(campaign_dir).resolve(), Path(out_dir).resolve(), Path(preregistration_path).resolve()
    require(not out.exists(), 'output_directory_already_exists')
    require(not out.is_relative_to(root) and not root.is_relative_to(out), 'output_must_be_separate_from_raw_campaign')
    campaign, campaign_sha = _load(root / 'campaign.json')
    _, prereg_sha = _load(prereg)
    require(campaign_sha == prereg_sha, 'published_preregistration_raw_hash_mismatch')
    slots = campaign['slots']
    expected = {(seed, arm) for seed in (211, 307, 401) for arm in ('no_learning', 'skillopt')}
    require(len(slots) == 6 and {(s['seed'], s['algorithm']) for s in slots} == expected, 'wrong_planned_worlds')
    for slot in slots:
        identifier = f"seed-{slot['seed']}-{slot['algorithm']}"
        require(slot['run_id'] == identifier and slot['relative_path'] == 'runs/' + identifier, 'unsafe_or_unplanned_run_identity')
    processor_sha = sha(Path(__file__).read_bytes())
    dynamics_sha = sha(Path(scale_world_dynamics.__file__).read_bytes())
    hashes = {'campaign.json': campaign_sha}
    for name in ('CLI_LAUNCH_RECEIPTS.json', 'EXECUTION.json', 'execution_results.json', 'AUDIT.json'):
        if name == 'AUDIT.json' and not (root / name).exists():
            continue
        hashes[name] = sha((root / name).read_bytes())
    audit = audit_campaign(root, strict=True)
    require(audit.get('ok') is True and audit.get('status') == 'valid_completed' and not audit.get('errors')
            and audit.get('completed_runs') == 6 and audit.get('complete_pairs') == 3
            and audit.get('accounting_verified') is True, 'strict_completed_campaign_audit_required')
    audited = {row['run_id']: row for row in audit['runs']}
    require(len(audited) == len(audit['runs']) == 6 and set(audited) == {s['run_id'] for s in slots}, 'audit_inventory_mismatch')
    audit_provenance = _audit_provenance(audit, campaign_sha, hashes, set(audited))
    records, worlds = [], []
    for slot in slots:
        identifier = slot['run_id']
        receipt = audited[identifier]
        require(receipt.get('completed') is True and receipt.get('status') == 'completed', 'incomplete_audited_run')
        path = root / slot['relative_path']
        loaded = {}
        for name in RUN_FILES:
            data, raw_sha = _load(path / name)
            require(receipt['evidence_sha256'].get(name) == raw_sha, 'raw_input_changed_since_audit')
            hashes[slot['relative_path'] + '/' + name] = raw_sha
            loaded[name] = data
        cp, v1, v2 = (loaded[name] for name in ('checkpoint.json', 'REPORT.json', 'REPORT.v2.json'))
        require(v1['status'] == v2['status'] == 'completed' and v2['metric_schema_version'] == 2
                and v2['correction_audit']['eligible_for_paired_inference'] is True
                and not v2['correction_audit']['issues'], 'ineligible_corrected_report')
        require(v2['source_hashes']['checkpoint_sha256'] == hashes[slot['relative_path'] + '/checkpoint.json']
                and v2['source_hashes']['v1_report_sha256'] == hashes[slot['relative_path'] + '/REPORT.json'], 'corrected_report_raw_binding')
        require(v1['algorithm'] == v2['algorithm'] == slot['algorithm'], 'report_algorithm_mismatch')
        breakdown = {key: _commitments(v2['source_breakdown'][key]) for key in SOURCES}
        all_work = _commitments(v2['commitments'])
        for key in COMMITMENT_FIELDS:
            require(breakdown['initial'][key] + breakdown['benchmark'][key] == breakdown['fixed_initial_and_benchmark'][key]
                    and sum(breakdown[source][key] for source in ('initial', 'benchmark', 'native_consumer', 'unknown')) == all_work[key], 'commitment_source_partition')
        require(breakdown['fixed_initial_and_benchmark']['accepted_before_work_horizon'] == 240, 'fixed_demand_denominator_changed')
        business = {'realized_utility': number(v1['business']['realized_utility'], nonnegative=False),
            'unit': 'synthetic_utility_not_currency', **{key: count(v1['business'][key]) for key in ('settled_entries', 'unsettled_entries', 'reward_censored_obligations')}}
        state = cp['runner']
        dynamics = scale_world_dynamics.summarize_world_dynamics(cp)
        require(dynamics['evidence_complete'] is True and not dynamics['evidence_issues'], 'world_dynamics_evidence_incomplete')
        native_orders = [order for consumer in dynamics['consumers'] for order in consumer['endogenous_orders']
            if order['day'] < slot['config']['days']]
        require(len(native_orders) == breakdown['native_consumer']['accepted_before_work_horizon'],
            'world_dynamics_native_commitment_count_mismatch')
        worlds.append({'run_id': identifier, 'seed': slot['seed'], 'algorithm': slot['algorithm'], 'status': 'completed',
            'primary_fixed_demand': breakdown['fixed_initial_and_benchmark'], 'all_commitments': all_work,
            'commitment_sources': breakdown, 'business': business, 'online': _online(state, v1),
            'optimizer': _optimizer(state['updates']), 'costs': _costs(v1, state), 'world_dynamics': dynamics})
        records.append({'run_id': identifier, 'checkpoint': cp, 'report': v1})
    exposure = build_scale_summary(campaign, records)
    require(exposure['complete'] is True and not exposure['evidence_issues'], 'incomplete_learning_exposure')
    costs = _aggregate_costs(worlds)
    measured = costs['employee_and_optimizer']
    require(close(measured['measured_physical_calls'], audit['accounting']['learner_physical_calls'])
            and close(measured['measured_tokens'], audit['accounting']['learner_measured_tokens']), 'audit_campaign_cost_mismatch')
    costs['environment'] = {'logical_interview_requests': count(audit['accounting']['environment']['logical_interview_requests']),
        'physical_model_calls': None, 'tokens': None, 'estimated_usd': None, 'accounting_complete': False}
    costs['all_in_estimated_usd'] = None
    costs['time_interpretation'] = 'Summed session/epoch durations are service time, not elapsed campaign wall time.'
    source_hashes = campaign['source_sha256']
    require(type(source_hashes) is dict and all(isinstance(name, str) and re.fullmatch(r'(lifespan|scripts)/[A-Za-z0-9_/]+\.py', name)
        and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for name, value in source_hashes.items()), 'unsafe_execution_source_metadata')
    summary = {'schema_version': 1, 'report_version': VERSION, 'kind': 'completed_development_study_publication_draft',
        'complete': True, 'planned_worlds': 6, 'completed_worlds': 6, 'world_pairs': 3,
        'work_days': 20, 'settlement_only_days': 2,
        'primary_endpoint': 'Equal-world mean paired difference in fixed initial/benchmark commitment fulfillment.',
        'provenance': {'hash_encoding': 'sha256_raw_file_bytes', 'campaign_raw_sha256': campaign_sha,
            'published_preregistration_raw_sha256': prereg_sha,
            'postprocessor': {'path': 'scripts/report_scale.py', 'sha256': processor_sha, 'version': VERSION,
                'supplemental_source_sha256': {'scripts/scale_world_dynamics.py': dynamics_sha}},
            'execution_source_sha256': source_hashes, 'raw_input_sha256': hashes,
            'audit': audit_provenance},
        'worlds': worlds, 'comparison': _pairs(worlds), 'learning_exposure': exposure,
        'costs': costs, 'limitations': CAVEATS}
    json_text = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n'
    markdown = _markdown(summary)
    # Recheck bytes after aggregation, including the independent postprocessor.
    require(sha(prereg.read_bytes()) == prereg_sha and sha(Path(__file__).read_bytes()) == processor_sha
            and sha(Path(scale_world_dynamics.__file__).read_bytes()) == dynamics_sha
            and sha(Path(audit_scale_cli.__file__).read_bytes()) == audit_provenance['correction']['corrected_auditor_sha256']
            and all(sha((ROOT / name).read_bytes()) == value for name, value in source_hashes.items())
            and all(sha((root / name).read_bytes()) == value for name, value in hashes.items()), 'raw_inputs_changed_during_reporting')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'SUMMARY.json').write_text(json_text, encoding='utf-8')
    (out / 'REPORT.md').write_text(markdown, encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--preregistration', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report_scale(args.campaign, args.out, preregistration_path=args.preregistration)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        # Native exceptions can contain private paths/text; expose no payload.
        print(json.dumps({'ok': False, 'error': type(exc).__name__}))
        return 1
    print(json.dumps({'ok': True, 'completed_worlds': result['completed_worlds'], 'world_pairs': result['world_pairs'],
                      'outputs': ['SUMMARY.json', 'REPORT.md']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
