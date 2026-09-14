"""One learning operation shared by fixed schedules and reacting workplaces."""
import json
from .attempts import execute_task, task_instruction
from .contracts import Budget


def update_employee(bank, harness, judge, learner, selected, *, employee, day, skill, update_root, executor=None):
    execute_task = executor or globals()['execute_task']
    judge_tokens = judge.max_tokens
    by_id = {s['id']: s for s in selected}
    experiences = [{'id': s['id'], 'split': s['split'], 'available_day': s['day'],
                    'feedback_available_day': s['feedback_day'],
                    'source_session': s['lineage_group'], 'prompt': task_instruction(bank.public(s['task_id'])['instruction'], s.get('employee_message')),
                    'context': '', 'feedback': s['grade']['feedback']} for s in selected]

    def replay(payload, limits):
        slot = by_id[payload['task']['id']]
        replay_root = update_root / f'replay-{payload["attempt_index"]:03d}'
        # Target ledger includes BOTH work and its judge. Reserve judging
        # before giving the remaining allowance to native work.
        jt = min(judge_tokens, limits['max_tokens'] // 2)
        jc = min(8, limits['max_model_calls'] // 2)
        wb = Budget(model_calls=min(slot['work_budget']['model_calls'], limits['max_model_calls'] - jc),
                    output_tokens=min(slot['work_budget']['output_tokens'], limits['max_tokens'] - jt),
                    total_tokens=min(slot['work_budget']['total_tokens'], limits['max_tokens'] - jt),
                    seconds=max(1, min(slot['work_budget']['seconds'], int(limits['timeout_seconds']) - 300)))
        attempt = execute_task(bank, harness, judge, task_id=slot['task_id'], employee_id=employee,
                               skill=payload['skill'], budget=wb, out=replay_root, judge_tokens=jt, judge_calls=jc,
                               employee_message=slot.get('employee_message'),
                               total_timeout_seconds=limits['timeout_seconds'])
        grade = attempt['grade']
        return {'status': attempt['status'], 'hard': float(grade['success']) if grade else 0.0,
                'soft': grade['quality_score'] if grade and grade['grading_complete'] else 0.0,
                'response': json.dumps({'messages': attempt['trajectory']}, ensure_ascii=False),
                'feedback': grade['feedback'] if grade else '',
                # The attempt's tokens include conservative reservations after
                # an unknown provider receipt. The learner expects measured
                # usage or None; retain its reservation when usage is unknown.
                'tokens': attempt['tokens'] if attempt.get('accounting_complete') is True else None,
                'model_calls': attempt['model_calls'],
                'tool_calls': attempt['tool_calls'], 'latency_ms': attempt['seconds'] * 1000}

    update = learner.update(skill, experiences, replay, current_day=day, artifact_root=update_root)
    return update
