"""Bounded incident containment without inventing outcomes or measured usage."""
import hashlib
import math
import time
from pathlib import Path
from scripts.source_world_calibration import save, read, sha

CONTINUE = 'record_and_continue'
POLICIES = ('stop_after_current_wave', 'drain_all_pairs', CONTINUE)
JUDGE_SECONDS = 300


def enabled(spec):
    return spec.get('failure_policy') == CONTINUE


def work_wall_seconds(harness, budget):
    method = getattr(harness, 'wall_seconds', None)
    value = method(budget) if callable(method) else budget.seconds
    if type(value) not in (int, float) or not math.isfinite(value) or value < budget.seconds:
        raise ValueError('Harness wall allowance cannot shorten active work')
    return value


def attempt_seconds(harness, budget):
    return work_wall_seconds(harness, budget) + JUDGE_SECONDS


def incident(root, stage, exc, **context):
    """No exception text or locals: provider errors can contain credentials."""
    value = {'version': 1, 'stage': stage, 'error_type': type(exc).__name__,
             'at_unix': time.time(), 'context': context,
             'outcome': 'ungraded; retain evidence and continue independent work'}
    save(Path(root) / 'INCIDENT.json', value)
    return value


def report_failures(sessions, updates, decision_failures=()):
    bad = [s for s in sessions if s['status'] != 'completed']
    failed_updates = [u for u in updates if u['result']['status'] not in ('completed', 'budget_exhausted')]
    return {'ungraded_work_attempts': len(bad), 'failed_learning_updates': len(failed_updates),
            'ungraded_probe_attempts': sum(s.get('split') == 'probe' for s in bad),
            'learning_budget_exhaustions': sum(u['result']['status'] == 'budget_exhausted' for u in updates),
            'work_attempts_with_unknown_usage': sum(s.get('accounting_complete', s['status'] == 'completed') is not True
                                                     for s in sessions),
            'failed_employee_decisions': len(decision_failures),
            'accounting_complete': all(s.get('accounting_complete', s['status'] == 'completed') for s in sessions)
                and all(u['result']['costs'].get('accounting_complete') is True for u in updates)
                and not decision_failures,
            'cost_scope': 'Token charges include reservations for unknown usage; not all are measured tokens.',
            'outcome_scope': 'Operational completion includes retained ungraded failures; no missing score is fabricated.'}


def failed_update(root, learner, skill, selected, exc):
    """A thrown epoch cannot adopt a partial candidate or erase its evidence."""
    root = Path(root)
    identity = learner.identity()
    budget = identity.get('budget', {})
    failure = incident(root, 'learning', exc, learner=identity,
                       skill_before_sha256=hashlib.sha256(skill.encode()).hexdigest())
    # A lost epoch may have dispatched anywhere inside its allocation. Reserve
    # the full allocation rather than guessing usage from partial artifacts.
    value = {'status': 'failed', 'accepted': False, 'skill': skill,
             'failure': failure, 'train_ids': [s['id'] for s in selected if s['split'] == 'train'],
             'validation_ids': [s['id'] for s in selected if s['split'] == 'val'],
             'replay_evidence': [], 'optimizer_inputs': [], 'unscored_replay_evidence': [],
             'costs': {'tokens': budget.get('max_tokens', 0),
                       'target_model_calls': budget.get('max_target_model_calls'),
                       'optimizer_model_calls': budget.get('max_optimizer_model_calls'),
                       'accounting_complete': False, 'operations': [],
                       'accounting': 'whole_epoch_reservation', 'measured_tokens': None}}
    # Preserve an adapter-written partial UPDATE before writing the controller receipt.
    prior = root / 'UPDATE.json'
    if prior.exists():
        prior.rename(root / 'ADAPTER_UPDATE.json')
        value['adapter_update_sha256'] = sha(root / 'ADAPTER_UPDATE.json')
    from .artifact_inventory import inventory
    value['artifact_inventory'], value['artifact_symlinks'] = inventory(root)
    save(root / 'UPDATE.json', value)
    return value


def audit_usage(usage):
    """Reconcile retained physical receipts and reservations, without imputing usage."""
    rows = usage.get('operations')
    if rows is None:
        return  # Alternate adapters may own a different receipt format.
    if usage['physical_model_calls'] != len(rows) or usage['charged_tokens'] != sum(r['charged_tokens'] for r in rows):
        raise ValueError('Failure usage differs from physical operations')
    for row in rows:
        if row['accounting'] == 'reported':
            if (row['charged_tokens'] != row['total_tokens'] or
                    row['input_tokens'] + row['output_tokens'] != row['total_tokens']):
                raise ValueError('Reported failure cost changed')
        elif row['accounting'] == 'reservation':
            if row['charged_tokens'] != row['reserved_tokens'] or row['total_tokens'] is not None:
                raise ValueError('Unknown failure cost lost its reservation')
        else:
            raise ValueError('Unknown failure accounting basis')
    if usage['accounting_complete'] != all(r['accounting'] == 'reported' for r in rows):
        raise ValueError('Unknown failure usage presented as measured')


def audit_failed_attempt(root, record, request, harness):
    """Audit failure provenance and costs; this never certifies task correctness."""
    from .contracts import Budget, validate_execution, validate_grade
    root = Path(root)
    execution, grade = record['execution'], record['grade']
    if record['status'] == 'completed':
        raise ValueError('Failure audit cannot replace successful execution audit')
    if record['status'] == 'execution_invalid':
        try:
            validate_execution(execution, Budget(**request['budget']), request['skill'])
        except ValueError as exc:
            if record['validation_error'] != str(exc):
                raise ValueError('Execution rejection reason changed')
        else:
            raise ValueError('Unjustified invalid execution receipt')
        calls, tokens = execution.get('physical_model_calls'), execution.get('charged_tokens')
        calls = calls if type(calls) is int and calls >= 0 else None
        known_tokens = type(tokens) is int and tokens >= 0 and execution.get('accounting_complete') is True
        expected = (tokens if known_tokens else request['budget']['total_tokens'], calls,
                    calls is not None and known_tokens)
        if grade is not None or (record['tokens'], record['model_calls'], record['accounting_complete']) != expected:
            raise ValueError('Invalid execution lost known usage or unknown reservations')
        return
    elif execution['status'] in ('completed', 'budget_exhausted'):
        validate_execution(execution, Budget(**request['budget']), request['skill'])
        harness.audit_execution(root, request, execution)
    elif execution.get('failure'):
        if read(root / 'INCIDENT.json') != execution['failure']:
            raise ValueError('Execution incident changed')
        if execution['charged_tokens'] != request['budget']['total_tokens'] or execution['accounting_complete']:
            raise ValueError('Thrown execution lost its unknown reservation')
    else:
        # Native interrupted receipts are evidence of failure only. A final or
        # checkpoint meter can preserve cost without proving successful work.
        native = root / 'NATIVE.json'
        checkpoint = root / 'METER_CHECKPOINT.json'
        meter = read(native)['evaluation_budget'] if native.exists() else read(checkpoint) if checkpoint.exists() else None
        if meter is not None:
            audit_usage(meter)
            if any(execution[k] != meter[k] for k in ('charged_tokens', 'physical_model_calls')):
                raise ValueError('Interrupted execution costs changed')
        elif execution.get('accounting_complete') or execution.get('physical_model_calls') is not None:
            raise ValueError('Interrupted execution lacks cost evidence')
    calls, tokens = execution.get('physical_model_calls'), execution['charged_tokens']
    complete = execution.get('accounting_complete') is True
    if grade is not None:
        validate_grade(grade)
        if grade['grading_complete'] or grade.get('quality_score') is not None or grade.get('success') is not False:
            raise ValueError('Failure fabricated a scored outcome')
        if read(root / 'JUDGE_RECEIPT.json') != grade:
            raise ValueError('Incomplete grade receipt changed')
        usage = grade['usage']; audit_usage(usage)
        checkpoint = root / 'judging/METER_CHECKPOINT.json'
        if checkpoint.exists() and read(checkpoint) != usage:
            raise ValueError('Incomplete judge meter changed')
        tokens += usage['charged_tokens']
        calls = calls + usage['physical_model_calls'] if calls is not None else None
        complete = complete and usage['accounting_complete']
    elif record['status'] == 'grading_error':
        if read(root / 'INCIDENT.json') != record['failure']:
            raise ValueError('Grading incident changed')
        tokens += record['judge_token_reservation']; calls = None; complete = False
    if (record['tokens'], record['model_calls'], record['accounting_complete']) != (tokens, calls, complete):
        raise ValueError('Ungraded attempt costs changed')
