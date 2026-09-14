"""One task execution shared by online work and isolated learner replays."""
from dataclasses import asdict
import time
from pathlib import Path
from scripts.source_world_calibration import save, sha
from .contracts import TaskRequest, validate_execution


def execute_task(bank, harness, judge, *, task_id, employee_id, skill, budget, out,
                 judge_tokens=400_000, judge_calls=8, total_timeout_seconds=None):
    started = time.monotonic()
    deadline = started + (total_timeout_seconds if total_timeout_seconds is not None else budget.seconds + 300)
    out = Path(out).resolve()
    public = bank.public(task_id)
    reasons = harness.unsupported(public) + judge.unsupported(public)
    if reasons: raise ValueError('Unsupported task: ' + '; '.join(reasons))
    workspace = out / employee_id / 'workspace'
    baseline = bank.stage(task_id, workspace)
    ident = workspace / '.employee_identity'
    ident.write_text(employee_id + '\n'); baseline['.employee_identity'] = sha(ident)
    save(out / 'BASELINE.json', baseline)
    request = TaskRequest(out.name, employee_id, public['instruction'], public['language'], workspace, skill, budget)
    save(out / 'PUBLIC_REQUEST.json', {**asdict(request), 'workspace': str(workspace)})
    execution = harness.run(request, out)
    save(out / 'EXECUTION_RECEIPT.json', execution)
    validate_execution(execution, budget, skill)
    result = {'task_id': task_id, 'employee_id': employee_id, 'execution': execution,
              'status': execution['status'], 'grade': None,
              'model_calls': execution.get('physical_model_calls'),
              'tokens': execution.get('charged_tokens', budget.total_tokens),
              'accounting_complete': execution.get('accounting_complete', False)}
    if execution['status'] in ('completed', 'budget_exhausted'):
        grade = judge.grade(task_id, workspace, baseline, out / 'judging',
                            token_limit=judge_tokens, call_limit=judge_calls,
                            timeout_seconds=max(0, deadline - time.monotonic()))
        result.update(grade=grade, status='completed' if grade['grading_complete'] else 'grading_incomplete',
                      model_calls=(execution['physical_model_calls'] + grade['usage']['physical_model_calls']),
                      tokens=execution['charged_tokens'] + grade['usage']['charged_tokens'],
                      accounting_complete=execution['accounting_complete'] and grade['usage']['accounting_complete'])
    messages = execution.get('trajectory', [])
    result['trajectory'] = messages
    result['tool_calls'] = sum(len(m.get('tool_calls') or []) for m in messages)
    result['seconds'] = time.monotonic() - started
    result['skill_sha256'] = execution.get('skill_sha256')
    result['artifact_inventory'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                                    if p.is_file() and not p.is_symlink()}
    save(out / 'ATTEMPT.json', result)
    return result
