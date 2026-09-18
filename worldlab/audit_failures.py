"""Audit contained failures as failures, including unknown-cost reservations."""
import hashlib
from scripts.source_world_calibration import read, sha
from .resilience import audit_usage


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit_failed_learning(bank, root, update, selected, skill, harness, judge, identity, counts):
    from .audit_worlds import audit_attempt, audit_replay_response, audit_learning_context
    require(update['status'] == 'failed' and update['accepted'] is False and update['skill'] == skill,
            'Failed epoch changed its deployed skill')
    costs = update['costs']
    if update.get('failure'):
        from .artifact_inventory import verify
        verify(root, update['artifact_inventory'], update['artifact_symlinks'], exclude=('UPDATE.json',))
        failure = read(root / 'INCIDENT.json')
        require(failure == update['failure'] and failure['context']['learner'] == identity and
                failure['context']['skill_before_sha256'] == hashlib.sha256(skill.encode()).hexdigest(),
                'Lost epoch incident changed')
        budget = identity.get('budget', {})
        require(costs['accounting_complete'] is False and costs['accounting'] == 'whole_epoch_reservation'
                and costs['tokens'] == budget.get('max_tokens', 0)
                and costs['target_model_calls'] == budget.get('max_target_model_calls')
                and costs['optimizer_model_calls'] == budget.get('max_optimizer_model_calls'),
                'Lost epoch reservation changed')
        if update.get('adapter_update_sha256'):
            require(sha(root / 'ADAPTER_UPDATE.json') == update['adapter_update_sha256'], 'Partial update changed')
        return
    require(update['configuration']['budget'] == identity['budget'], 'Failed epoch budget changed')
    require(update['skill_before_sha256'] == update['skill_after_sha256'] == hashlib.sha256(skill.encode()).hexdigest(),
            'Failed epoch skill binding changed')
    require(update['gate_evidence'] == {'accepted': False, 'gate_action': 'reject_incomplete'},
            'Incomplete epoch claimed a gate result')
    by_id = {s['id']: s for s in selected}
    rows = costs['operations']
    targets = [r for r in rows if r['kind'] == 'target']
    scored = update['replay_evidence']; unscored = update['unscored_replay_evidence']
    require(len(targets) == len(scored) + len(unscored), 'Missing failed replay inventory')
    require(costs['tokens'] == sum(r['tokens'] for r in rows) and
            all(costs[k + '_model_calls'] == sum(r['model_calls'] for r in rows if r['kind'] == k)
                for k in ('target', 'optimizer')), 'Failed epoch costs differ from ledger')
    require(costs['accounting_complete'] == all(r['accounting'] == 'reported' for r in rows),
            'Failed epoch fabricated measured accounting')
    spent = {'tokens': 0, 'target': 0, 'optimizer': 0}
    budget = identity['budget']
    for index, row in enumerate(rows):
        kind = row['kind']; limits = row['limits']
        require(kind in ('target', 'optimizer'), 'Unknown failed epoch operation')
        prefix = 'replay' if kind == 'target' else 'optimizer'
        require(limits['remaining_tokens'] == budget['max_tokens'] - spent['tokens'] and
                limits['remaining_model_calls'] == budget['max_' + kind + '_model_calls'] - spent[kind] and
                limits['max_tokens'] == min(limits['remaining_tokens'], budget[prefix + '_tokens']) and
                limits['max_model_calls'] == min(limits['remaining_model_calls'], budget[prefix + '_model_calls']),
                'Failed epoch reservation differs from prospective budget')
        for dimension in ('tokens', 'model_calls'):
            reported = row.get('reported_usage', {}).get(dimension)
            expected = limits['max_' + dimension] if reported is None else reported
            require(type(expected) is int and 0 <= expected <= limits['max_' + dimension]
                    and row[dimension] == expected, 'Failed epoch lost known cost or unknown reservation')
        require(index == len(rows) - 1 or row.get('callback_status') == row['status'] == 'completed',
                'Epoch continued after a failed callback')
        spent['tokens'] += row['tokens']; spent[kind] += row['model_calls']
    for index, (row, evidence) in enumerate(zip(targets, scored + unscored)):
        require(row['attempt_index'] == evidence['attempt_index'] == index and
                row['task_id'] == evidence['id'] and row['skill_sha256'] == evidence['skill_sha256'],
                'Failed replay identity changed')
        slot = by_id[row['task_id']]
        attempt = audit_attempt(bank, root / f'replay-{index:03d}', slot['task_id'], harness=harness,
            judge=judge, employee_message=slot.get('employee_message'), allow_incomplete=True)
        if index < len(scored):
            require(attempt['status'] == 'completed' and evidence['hard'] == float(attempt['grade']['success'])
                    and evidence['soft'] == attempt['grade']['quality_score'], 'Failed epoch consumed an unscored replay')
            audit_replay_response(evidence['response'], attempt['trajectory'])
        else:
            require(evidence['score_consumed'] is False, 'Unscored replay claimed a score')
        reported = row.get('reported_usage', {})
        require(reported.get('tokens') == (attempt['tokens'] if attempt['accounting_complete'] else None)
                and reported.get('model_calls') == attempt['model_calls'], 'Failed replay costs differ from execution')
        counts['learning_replays'] += 1
    optimizers = [r for r in rows if r['kind'] == 'optimizer']
    receipts = update.get('optimizer_transport_audit', [])
    require(len(optimizers) == len(receipts), 'Failed optimizer transport receipt missing')
    for row, receipt in zip(optimizers, receipts):
        require(receipt.get('provider_contract') == identity['provider'] and
                receipt.get('context_adapter') == identity.get('optimizer_context_adapter'),
                'Failed optimizer provider or context changed')
        reported = row.get('reported_usage', {})
        require(all(reported.get(k) == receipt.get(k) for k in ('tokens', 'model_calls', 'tool_calls')),
                'Failed optimizer cost differs from native receipt')
        if receipt.get('accounting_complete'):
            require(receipt['tokens'] == receipt['input_tokens'] + receipt['output_tokens'],
                    'Failed optimizer known usage changed')
        else:
            require(receipt.get('tokens') is None, 'Unknown optimizer tokens invented')
    audit_learning_context(bank, selected, update)


def audit_actor_failures(root, state, identity):
    """Bind system deferrals to saved incidents and retain native interview ledger rows."""
    failures = state.get('decision_failures', [])
    failed_keys = set()
    for failure in failures:
        path = root / 'decision_failures' / failure['id'] / 'INCIDENT.json'
        require(sha(path) == failure['incident_sha256'] and read(path) == failure['failure'], 'Actor incident changed')
        require(failure['failure']['stage'] == 'employee_decision' and
                failure['failure']['context']['view'] == failure['view'], 'Actor failure view changed')
        failed_keys.update((failure['id'], failure['id'] + '-repair'))
    return failed_keys
