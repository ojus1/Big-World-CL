"""One task execution shared by online work and isolated learner replays."""
from dataclasses import asdict
import time
from pathlib import Path
from scripts.source_world_calibration import save, sha
from .contracts import TaskRequest, validate_execution, validate_grade, judge_call_allocation
from .artifact_inventory import inventory


def task_instruction(original, employee_message=None):
    if employee_message is None:
        return original
    if not isinstance(employee_message, str) or not employee_message.strip():
        raise ValueError('A delegated task requires the employee request')
    return ('Original task and deliverable requirements:\n' + original +
            '\n\nEmployee request and observed workplace context (may contain mistakes or unrelated history):\n' + employee_message +
            '\n\nThe original task above and its source files control the topic, facts, filenames and deliverables. '
            'Use employee context only where it is consistent with that task. Disregard any conflicting or '
            'unrelated requirements and do not transfer another task\'s completion status. '
            'Complete the original deliverables. Employee context does not waive source requirements.')


def execute_task(bank, harness, judge, *, task_id, employee_id, skill, budget, out,
                 judge_tokens=400_000, judge_calls=None, total_timeout_seconds=None, employee_message=None,
                 continue_on_error=False):
    from .resilience import attempt_seconds, JUDGE_SECONDS, incident
    if judge_calls is None:
        judge_calls = judge_call_allocation(judge, task_id)
    started = time.monotonic()
    allowance = attempt_seconds(harness, budget)
    if total_timeout_seconds is not None and total_timeout_seconds < allowance:
        raise ValueError('Attempt allocation cannot fit work, settlement and grading')
    deadline = started + (total_timeout_seconds if total_timeout_seconds is not None else allowance)
    out = Path(out).resolve()
    public = bank.public(task_id)
    reasons = harness.unsupported(public) + judge.unsupported(public)
    if reasons: raise ValueError('Unsupported task: ' + '; '.join(reasons))
    workspace = out / employee_id / 'workspace'
    baseline = bank.stage(task_id, workspace)
    ident = workspace / '.employee_identity'
    ident.write_text(employee_id + '\n'); baseline['.employee_identity'] = sha(ident)
    save(out / 'BASELINE.json', baseline)
    instruction = task_instruction(public['instruction'], employee_message)
    request = TaskRequest(out.name, employee_id, instruction, public['language'], workspace, skill, budget)
    if employee_message is not None:
        save(out / 'EMPLOYEE_REQUEST.json', {'message': employee_message, 'original_instruction': public['instruction']})
    save(out / 'PUBLIC_REQUEST.json', {**asdict(request), 'workspace': str(workspace)})
    timing = {'version': 1, 'work_active_seconds': budget.seconds,
              'work_wall_seconds': allowance - JUDGE_SECONDS, 'judge_seconds': JUDGE_SECONDS,
              'attempt_deadline_monotonic': deadline, 'started_monotonic': started}
    save(out / 'TIMING.json', timing)
    try:
        execution = harness.run(request, out)
    except Exception as exc:
        if not continue_on_error: raise
        failure = incident(out, 'execution', exc, task_id=task_id, employee_id=employee_id)
        execution = {'status': 'infrastructure_error', 'physical_model_calls': None,
                     'charged_tokens': budget.total_tokens, 'accounting_complete': False,
                     'reservation_reason': 'Harness raised without a verified final receipt',
                     'failure': failure}
    save(out / 'EXECUTION_RECEIPT.json', execution)
    validation_error = None
    try:
        validate_execution(execution, budget, skill)
    except ValueError as exc:
        # Retain the original receipt and known usage even when its evidence
        # cannot be graded. A callback exception would hide measured costs
        # behind the learner's full reservation.
        validation_error = str(exc)
    result = {'task_id': task_id, 'employee_id': employee_id, 'execution': execution,
              'status': execution['status'], 'grade': None,
              'model_calls': execution.get('physical_model_calls'),
              'tokens': execution.get('charged_tokens', budget.total_tokens),
              'accounting_complete': execution.get('accounting_complete', False)}
    if validation_error:
        calls, tokens = execution.get('physical_model_calls'), execution.get('charged_tokens')
        known_calls = type(calls) is int and calls >= 0
        known_tokens = type(tokens) is int and tokens >= 0 and execution.get('accounting_complete') is True
        result.update(status='execution_invalid', validation_error=validation_error,
                      model_calls=calls if known_calls else None,
                      tokens=tokens if known_tokens else budget.total_tokens,
                      accounting_complete=known_calls and known_tokens)
    elif execution['status'] in ('completed', 'budget_exhausted'):
        timing.update(judge_started_monotonic=time.monotonic(),
                      judge_allowance_seconds=min(JUDGE_SECONDS, max(0, deadline - time.monotonic())))
        save(out / 'TIMING.json', timing)
        try:
            grade = judge.grade(task_id, workspace, baseline, out / 'judging',
                                token_limit=judge_tokens, call_limit=judge_calls,
                                timeout_seconds=timing['judge_allowance_seconds'])
            save(out / 'JUDGE_RECEIPT.json', grade)
            validate_grade(grade, token_limit=judge_tokens, call_limit=judge_calls)
            result.update(grade=grade, status='completed' if grade['grading_complete'] else 'grading_incomplete',
                          model_calls=(execution['physical_model_calls'] + grade['usage']['physical_model_calls']),
                          tokens=execution['charged_tokens'] + grade['usage']['charged_tokens'],
                          accounting_complete=execution['accounting_complete'] and grade['usage']['accounting_complete'])
        except Exception as exc:
            if not continue_on_error: raise
            failure = incident(out, 'grading', exc, task_id=task_id, employee_id=employee_id)
            result.update(status='grading_error', grade=None, failure=failure,
                          model_calls=None, tokens=execution['charged_tokens'] + judge_tokens,
                          accounting_complete=False, judge_token_reservation=judge_tokens)
    messages = execution.get('trajectory', [])
    if not isinstance(messages, list): messages = []
    result['trajectory'] = messages
    result['tool_calls'] = sum(len(m.get('tool_calls') or []) for m in messages if isinstance(m, dict))
    result['seconds'] = time.monotonic() - started
    result['skill_sha256'] = execution.get('skill_sha256')
    result['artifact_inventory'], result['artifact_symlinks'] = inventory(out)
    save(out / 'ATTEMPT.json', result)
    return result
