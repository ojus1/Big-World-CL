"""One learning operation shared by fixed schedules and reacting workplaces."""
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from scripts.source_world_calibration import save, read
from .attempts import execute_task, task_instruction
from .contracts import Budget, judge_call_allocation
from .validation_context import observed_feedback
from .cancellation import check
from .learning_feedback import learning_feedback


def replay_admission(limits, work_budget, harness=None):
    """Admit a full work window plus grading, rather than starting a shortened replay."""
    from .resilience import attempt_seconds
    seconds = attempt_seconds(harness, Budget(**work_budget))
    for dimension, minimum in [('timeout_seconds', seconds), ('max_model_calls', 2), ('max_tokens', 2)]:
        if limits[dimension] < minimum:
            return {'admitted': False, 'dimension': dimension, 'available': limits[dimension],
                    'minimum': minimum, 'policy': 'reserve_work_settlement_and_300_second_judging_v2'}
    return None


def audit_replay_admissions(update_root, update, selected, harness=None):
    by_id = {s['id']: s for s in selected}
    for row in update['costs']['operations']:
        if row.get('callback_status') != 'not_admitted': continue
        root = update_root / f'replay-{row["attempt_index"]:03d}'
        budget = by_id[row['task_id']]['work_budget']
        expected = replay_admission(row['limits'], budget, harness)
        if (row['kind'] != 'target' or expected is None or row.get('admission') != expected
                or read(root / 'REPLAY_ADMISSION.json') != {'limits': row['limits'], 'work_budget': budget, 'admission': expected}
                or {p.name for p in root.iterdir()} != {'REPLAY_ADMISSION.json'}):
            raise ValueError('Replay admission stop differs from the allocated budget')


def dispatch_updates(bank, harness, judge, learner, selections, *, day, skills, out,
                     record, journal, max_parallel, cancellation=None, continue_on_error=False):
    """Parallel employee epochs with independent upstream settings and ledgers.

    SkillOpt mutates process-global prompt/worker settings, so epochs use spawned
    processes rather than sharing that state between threads. Each employee's
    replay/gate sequence remains unchanged; results are recorded in planned order.
    """
    if not selections:
        return
    width = min(max_parallel, len(selections))
    with ProcessPoolExecutor(max_workers=width,
                             mp_context=multiprocessing.get_context('spawn')) as pool:
        for offset in range(0, len(selections), width):
            check(cancellation)
            wave = selections[offset:offset + width]
            journal([employee for employee, _ in wave])
            errors = []
            futures = [(employee, pool.submit(update_employee, bank, harness, judge, learner, selected,
                        employee=employee, day=day, skill=skills[employee],
                        update_root=out / 'learning' / f'd{day:03d}-{employee}', continue_on_error=continue_on_error))
                       for employee, selected in wave]
            if cancellation is not None and not continue_on_error:
                for _, future in futures:
                    future.add_done_callback(lambda f: cancellation.observe(f, ('completed', 'budget_exhausted')))
            for employee, future in futures:
                try:
                    try:
                        update = future.result()
                    except Exception as exc:
                        if not continue_on_error: raise
                        from .resilience import failed_update
                        selected = dict(wave)[employee]
                        update = failed_update(out / 'learning' / f'd{day:03d}-{employee}', learner,
                                               skills[employee], selected, exc)
                    record(employee, update)
                    if update['status'] not in ('completed', 'budget_exhausted') and not continue_on_error:
                        errors.append(RuntimeError('Learning failed; evidence preserved without automatic replay'))
                except Exception as exc:
                    if cancellation is not None and not continue_on_error: cancellation.request(type(exc).__name__)
                    errors.append(exc)
            if errors: raise errors[0]
            journal([])


def update_employee(bank, harness, judge, learner, selected, *, employee, day, skill, update_root, executor=None,
                    continue_on_error=False):
    execute_task = executor or globals()['execute_task']
    judge_tokens = judge.max_tokens
    by_id = {s['id']: s for s in selected}
    experiences = [{'id': s['id'], 'split': s['split'], 'available_day': s['day'],
                    'feedback_available_day': s['feedback_day'],
                    'source_session': s['lineage_group'], 'prompt': task_instruction(bank.public(s['task_id'])['instruction'], s.get('employee_message')),
                    'context': '', 'feedback': observed_feedback(s)} for s in selected]

    def replay(payload, limits):
        slot = by_id[payload['task']['id']]
        replay_root = update_root / f'replay-{payload["attempt_index"]:03d}'
        admission = replay_admission(limits, slot['work_budget'], harness)
        if admission is not None:
            save(replay_root / 'REPLAY_ADMISSION.json', {'limits': limits, 'work_budget': slot['work_budget'], 'admission': admission})
            return {'status': 'not_admitted', 'admission': admission,
                    'tokens': 0, 'model_calls': 0, 'tool_calls': 0, 'latency_ms': 0.}
        # Target ledger includes BOTH work and its judge. Reserve judging
        # before giving the remaining allowance to native work.
        jt = min(judge_tokens, limits['max_tokens'] // 2)
        jc = min(judge_call_allocation(judge, slot['task_id']), limits['max_model_calls'] // 2)
        wb = Budget(model_calls=min(slot['work_budget']['model_calls'], limits['max_model_calls'] - jc),
                    output_tokens=min(slot['work_budget']['output_tokens'], limits['max_tokens'] - jt),
                    total_tokens=min(slot['work_budget']['total_tokens'], limits['max_tokens'] - jt),
                    seconds=slot['work_budget']['seconds'])
        attempt = execute_task(bank, harness, judge, task_id=slot['task_id'], employee_id=employee,
                               skill=payload['skill'], budget=wb, out=replay_root, judge_tokens=jt, judge_calls=jc,
                               employee_message=slot.get('employee_message'),
                               total_timeout_seconds=limits['timeout_seconds'], continue_on_error=continue_on_error)
        grade = attempt['grade']
        return {'status': attempt['status'], 'hard': float(grade['success']) if grade else 0.0,
                'soft': grade['quality_score'] if grade and grade['grading_complete'] else 0.0,
                'response': json.dumps({'messages': attempt['trajectory']}, ensure_ascii=False),
                'feedback': learning_feedback(grade) if grade else '',
                # The attempt's tokens include conservative reservations after
                # an unknown provider receipt. The learner expects measured
                # usage or None; retain its reservation when usage is unknown.
                'tokens': attempt['tokens'] if attempt.get('accounting_complete') is True else None,
                'model_calls': attempt['model_calls'],
                'tool_calls': attempt['tool_calls'], 'latency_ms': attempt['seconds'] * 1000}

    try:
        update = learner.update(skill, experiences, replay, current_day=day, artifact_root=update_root)
        if continue_on_error and update['status'] != 'completed' and (update.get('accepted') or update.get('skill') != skill):
            raise ValueError('Incomplete learning cannot deploy a changed skill')
    except Exception as exc:
        if not continue_on_error: raise
        from .resilience import failed_update
        update = failed_update(update_root, learner, skill, selected, exc)
    return update
