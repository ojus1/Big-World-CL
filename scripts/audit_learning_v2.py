"""Independent V2 learning-operation reconciliation; never supplies a score.

V1 evidence is deliberately outside this contract. A V2 timing-only terminal
operation may be fully accounted without having delivered a score to upstream.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path


def require(condition, code):
    if not condition:
        raise ValueError(code)


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def version(update):
    value = update.get('learning_evidence_version', 1)
    require(type(value) is int and value in (1, 2), 'unsupported_learning_evidence_version')
    return value


def manifest_version(manifest, root):
    """Bind version to the producer source as well as the mutable marker."""
    declared = version(manifest)
    sources = manifest.get('source_sha256', {})
    for name in ('lifespan/evaluation/skillopt.py', 'scripts/audit_learning_v2.py'):
        if sources.get(name) == hashlib.sha256((Path(root) / name).read_bytes()).hexdigest():
            require(declared == 2, 'learning_evidence_source_version')
    return declared


def reconcile(update):
    """Validate V2 costs/stops and return every target's scored or unscored identity."""
    require(version(update) == 2, 'expected_learning_evidence_v2')
    costs, cfg = update['costs'], update['configuration']['budget']
    rows, scores, unscored = costs['operations'], update['replay_evidence'], update['unscored_replay_evidence']
    require(isinstance(rows, list) and isinstance(scores, list) and isinstance(unscored, list),
            'v2_operation_container')
    targets, optimizer_rows = [], []
    spent = {'target': 0, 'optimizer': 0, 'tokens': 0}
    last_callback_end = 0.
    tolerance = 1e-6  # Subtraction/serialization roundoff, not deadline grace.
    for index, row in enumerate(rows):
        require(row['kind'] in ('target', 'optimizer') and row['accounting'] == 'reported',
                'v2_incomplete_operation_accounting')
        require(all(type(row[k]) is int and row[k] >= 0 for k in ('tokens', 'model_calls', 'tool_calls')),
                'v2_invalid_usage')
        require(row['reported_usage'] == {k: row[k] for k in ('tokens', 'model_calls', 'tool_calls')},
                'v2_reported_usage_binding')
        limits = row['limits']
        require(all(type(limits[k]) is int and limits[k] > 0 for k in ('max_tokens', 'max_model_calls'))
                and number(limits['timeout_seconds']) and limits['timeout_seconds'] > 0
                and number(row['wall_seconds']) and number(row['latency_ms']), 'v2_invalid_limits_or_timing')
        require(row['latency_ms'] <= row['wall_seconds'] * 1000 + tolerance * 1000,
                'v2_receipt_latency_outside_callback')
        kind = row['kind']; prefix = 'replay' if kind == 'target' else 'optimizer'
        remaining_calls = cfg['max_' + kind + '_model_calls'] - spent[kind]
        remaining_tokens = cfg['max_tokens'] - spent['tokens']
        require(limits['remaining_model_calls'] == remaining_calls
                and limits['remaining_tokens'] == remaining_tokens
                and limits['max_model_calls'] == min(remaining_calls, cfg[prefix + '_model_calls'])
                and limits['max_tokens'] == min(remaining_tokens, cfg[prefix + '_tokens'])
                and number(limits['remaining_seconds']) and 0 < limits['remaining_seconds'] <= cfg['max_seconds']
                and limits['timeout_seconds'] == min(limits['remaining_seconds'], cfg[prefix + '_seconds']),
                'v2_operation_reservation')
        dispatch_elapsed = cfg['max_seconds'] - limits['remaining_seconds']
        require(dispatch_elapsed + tolerance >= last_callback_end, 'v2_nonmonotonic_callback_clock')
        last_callback_end = dispatch_elapsed + row['wall_seconds']
        spent[kind] += row['model_calls']; spent['tokens'] += row['tokens']
        violations = [key for key, exceeded in (
            ('model_calls', row['model_calls'] > limits['max_model_calls']),
            ('tokens', row['tokens'] > limits['max_tokens']),
            ('callback_wall_seconds', row['wall_seconds'] > limits['timeout_seconds']),
            ('receipt_latency_ms', row['latency_ms'] > limits['timeout_seconds'] * 1000)) if exceeded]
        require(row['budget_violations'] == violations, 'v2_budget_violation_evidence')
        require(not set(violations) & {'model_calls', 'tokens'}, 'v2_physical_budget_overrun')
        require(not violations or index == len(rows) - 1, 'v2_operation_after_budget_stop')
        if row['kind'] == 'target':
            require(row['attempt_index'] == len(targets) and type(row['attempt_index']) is int
                    and type(row['sample_id']) is int and row['sample_id'] >= 0
                    and row['task_id'] in update['train_ids'] + update['validation_ids'],
                    'v2_target_identity')
            targets.append(row)
        else:
            optimizer_rows.append(row)
    require(costs['accounting_complete'] is True and costs['replays'] == len(targets)
            and costs['tokens'] == sum(r['tokens'] for r in rows)
            and costs['target_model_calls'] == sum(r['model_calls'] for r in targets)
            and costs['optimizer_model_calls'] == sum(r['model_calls'] for r in optimizer_rows),
            'v2_receipt_totals')
    require(number(costs['wall_seconds']) and costs['wall_seconds'] + tolerance >= last_callback_end,
            'v2_total_wall_clock')
    require(costs['tokens'] <= cfg['max_tokens'] and costs['target_model_calls'] <= cfg['max_target_model_calls']
            and costs['optimizer_model_calls'] <= cfg['max_optimizer_model_calls']
            and len(targets) <= cfg['max_replays'], 'v2_total_physical_budget_overrun')
    stop = costs['stop_evidence']
    terminal = None
    if stop is None:
        require(update['status'] == 'completed' and number(costs['decision_elapsed_seconds'])
                and costs['decision_elapsed_seconds'] <= cfg['max_seconds'], 'v2_missing_stop_evidence')
        require(last_callback_end <= costs['decision_elapsed_seconds'] + tolerance
                and costs['decision_elapsed_seconds'] <= costs['wall_seconds'] + tolerance,
                'v2_decision_clock')
    else:
        require(update['status'] == 'budget_exhausted' and update['accepted'] is False
                and update['skill_after_sha256'] == update['skill_before_sha256']
                and hashlib.sha256(update['skill'].encode()).hexdigest() == update['skill_before_sha256']
                and update['gate_evidence'] == {'accepted': False, 'gate_action': 'reject_incomplete'},
                'v2_incomplete_optimization_adoption')
        if stop['stage'] == 'post_consolidation':
            require(stop == {'stage': 'post_consolidation', 'reason': 'wall_seconds',
                        'elapsed_seconds': costs['decision_elapsed_seconds']}
                    and number(costs['decision_elapsed_seconds'])
                    and costs['decision_elapsed_seconds'] > cfg['max_seconds'],
                    'v2_post_consolidation_deadline')
            require(last_callback_end <= costs['decision_elapsed_seconds'] + tolerance
                    and costs['decision_elapsed_seconds'] <= costs['wall_seconds'] + tolerance,
                    'v2_decision_clock')
        elif stop['stage'] == 'post_dispatch':
            require(stop['kind'] in ('target', 'optimizer'), 'v2_stop_kind')
            require(rows and type(stop['operation_index']) is int and stop['operation_index'] == len(rows) - 1,
                    'v2_terminal_operation_index')
            terminal = rows[-1]
            require(terminal['kind'] == stop['kind'] and terminal['status'] == 'budget_exceeded'
                    and stop['violations'] == terminal['budget_violations'] and bool(stop['violations'])
                    and terminal['callback_status'] in (('completed',) if stop['kind'] == 'target'
                        else ('completed', 'budget_exhausted')), 'v2_terminal_stop_evidence')
        elif stop['stage'] == 'pre_dispatch':
            require(stop['kind'] in ('target', 'optimizer'), 'v2_stop_kind')
            remaining_calls = cfg['max_' + stop['kind'] + '_model_calls'] - costs[stop['kind'] + '_model_calls']
            require(stop['remaining_model_calls'] == remaining_calls
                    and stop['remaining_tokens'] == cfg['max_tokens'] - costs['tokens']
                    and type(stop['remaining_seconds']) in (int, float)
                    and math.isfinite(stop['remaining_seconds']), 'v2_predispatch_remaining_budget')
            elapsed = cfg['max_seconds'] - stop['remaining_seconds']
            require(last_callback_end <= elapsed + tolerance and elapsed <= costs['wall_seconds'] + tolerance,
                    'v2_predispatch_clock')
            reason = ('replays' if stop['kind'] == 'target' and len(targets) >= cfg['max_replays'] else
                      'model_calls' if remaining_calls < 1 else 'tokens' if stop['remaining_tokens'] < 1 else
                      'wall_seconds' if stop['remaining_seconds'] <= 0 else None)
            require(reason is not None and stop['reason'] == reason, 'v2_predispatch_stop_reason')
            if reason == 'wall_seconds':
                require(number(costs['wall_seconds']) and costs['wall_seconds'] >= cfg['max_seconds'],
                        'v2_predispatch_deadline_not_reached')
        else:
            require(False, 'v2_unknown_stop_stage')
    require(all(row is terminal or row['status'] == row['callback_status'] == 'completed'
                and not row['budget_violations'] for row in rows), 'v2_nonterminal_operation_failure')
    expected_unscored = []
    if terminal is not None and terminal['kind'] == 'target':
        expected_unscored = [{
            'id': terminal['task_id'], 'phase': terminal['phase'], 'sample_id': terminal['sample_id'],
            'attempt_index': terminal['attempt_index'], 'skill_sha256': terminal['skill_sha256'],
            'score_consumed': False, 'reason': 'not_delivered_to_upstream'}]
    require(unscored == expected_unscored and len(scores) + len(unscored) == len(targets),
            'v2_scored_unscored_inventory')
    extra_input = int(stop is not None and stop['stage'] == 'pre_dispatch' and stop['kind'] == 'optimizer')
    require(len(update['optimizer_inputs']) == len(optimizer_rows) + extra_input,
            'v2_optimizer_input_dispatch_inventory')
    identities = scores + unscored
    for index, (row, identity) in enumerate(zip(targets, identities)):
        require(identity['id'] == row['task_id'] and identity['phase'] == row['phase']
                and identity['sample_id'] == row['sample_id'] and identity['attempt_index'] == index
                and identity['skill_sha256'] == row['skill_sha256'], 'v2_replay_operation_binding')
    return identities
