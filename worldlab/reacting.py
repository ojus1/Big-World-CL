"""Run native employee decisions against a persistent, causally replayable workplace."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
from scripts.source_world_calibration import save, sha
from .attempts import execute_task
from .campaign import SEED_SKILL
from .contracts import Budget
from .dispatch import dispatch_day
from .cancellation import check as check_cancellation
from .experience_update import update_employee
from .workplace import Workplace
from .worlds import stable_hash
from .validation_context import select_experiences, employee_world, validate_world
from .resilience import enabled, incident, report_failures


def run_world(bank, world, harness, judge, learner, out, employee_factory, *, cancellation=None):
    check_cancellation(cancellation)
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    validate_world(bank, world)
    place = Workplace(world)
    spec = world['specification']
    resilient = enabled(spec)
    skills = {e['id']: SEED_SKILL for e in world['workforce']}
    state = {'skills': skills, 'sessions': [], 'updates': [], 'decisions': [],
             'decision_failures': [], 'workplace': place.state}
    driver = None

    def checkpoint():
        if driver is not None: state['actor_usage'] = driver.usage()
        save(out / 'STATE.json', state)

    try:
        save(out / 'INFLIGHT.json', {'kind': 'employee_bootstrap'})
        driver = employee_factory.open(employee_world(world), world['employee_context'], out / 'actors')
        (out / 'INFLIGHT.json').unlink()
        for day in range(spec['days']):
            check_cancellation(cancellation)
            place.advance(day); checkpoint()
            for ordinal in range(max(e.get('sessions_per_day', 1) for e in world['workforce'])):
                employees = sorted(skills)
                random.Random(stable_hash([world['seed'], day, ordinal])).shuffle(employees)
                work = []
                for employee in employees:
                    check_cancellation(cancellation)
                    pending = place.available(employee)
                    if not pending: continue
                    oid = pending[0]
                    key = f'd{day:03d}-{employee}-{ordinal:03d}'
                    view = place.view(employee, oid, bank)
                    save(out / 'INFLIGHT.json', {'kind': 'employee_decision', 'id': key})
                    # Business validation may reject an actor answer before a
                    # bounded native repair, but must not mutate the workplace.
                    def validate(decision):
                        deepcopy(place).decide(employee, oid, decision)
                    try:
                        decision = driver.decide(view, key, validate)
                    except Exception as exc:
                        if not resilient: raise
                        failure_root = out / 'decision_failures' / key
                        failure = incident(failure_root, 'employee_decision', exc,
                                           key=key, view=view, usage=driver.usage())
                        state['decision_failures'].append({'id': key, 'day': day, 'employee_id': employee,
                            'obligation_id': oid, 'view': view, 'failure': failure,
                            'incident_sha256': sha(failure_root / 'INCIDENT.json')})
                        place.decision_failed(employee, oid, key)
                        checkpoint(); (out / 'INFLIGHT.json').unlink()
                        continue
                    delegated = place.decide(employee, oid, decision)
                    state['decisions'].append({'id': key, 'day': day, 'employee_id': employee,
                        'obligation_id': oid, 'view': view, 'decision': decision,
                        'session_id': key if delegated else None})
                    if delegated:
                        slot = {**place.arrivals[oid], 'id': key, 'obligation_id': oid, 'day': day,
                                'day_order': ordinal * len(employees) + employees.index(employee),
                                'feedback_day': day + place.delay, 'employee_message': decision['request']}
                        work.append(slot)
                    checkpoint(); (out / 'INFLIGHT.json').unlink()

                def perform(slot):
                    return execute_task(bank, harness, judge, task_id=slot['task_id'],
                        employee_id=slot['employee_id'], skill=skills[slot['employee_id']],
                        employee_message=slot['employee_message'], budget=Budget(**slot['work_budget']),
                        out=out / 'sessions' / slot['id'], judge_tokens=judge.max_tokens, continue_on_error=resilient)

                def record(slot, result):
                    state['sessions'].append({**slot, 'status': result['status'], 'grade': result['grade'],
                        'tokens': result['tokens'], 'model_calls': result['model_calls'],
                        'accounting_complete': result.get('accounting_complete', result['status'] == 'completed'),
                        'attempt_sha256': sha(out / 'sessions' / slot['id'] / 'ATTEMPT.json'),
                        'skill_content_sha256': hashlib.sha256(skills[slot['employee_id']].encode()).hexdigest()})
                    state['sessions'].sort(key=lambda s: (s['day'], s['day_order']))
                    if result['status'] == 'completed' and result['grade']['grading_complete']:
                        place.complete(slot['obligation_id'], slot['id'], {k: result['grade'][k]
                                       for k in ('success', 'quality_score', 'feedback')})
                    elif resilient:
                        place.fail(slot['obligation_id'], slot['id'], result['status'])
                    checkpoint()
                    print(json.dumps({'seed': world['seed'], 'arm': learner.identity()['name'],
                                      'day': day, 'session': slot['id'], 'status': result['status']}), flush=True)

                def journal(wave):
                    if wave:
                        # Delegation queues work. Only a wave admitted by the
                        # dispatcher consumes an attempt and work utility.
                        for slot in wave:
                            place.start(slot['obligation_id'], slot['id'])
                        checkpoint()
                        save(out / 'INFLIGHT.json', {'kind': 'work_wave', 'ids': [s['id'] for s in wave],
                            'max_reserved_tokens': sum(s['work_budget']['total_tokens'] + judge.max_tokens for s in wave)})
                    else:
                        (out / 'INFLIGHT.json').unlink()

                dispatch_day(work, perform, record, journal, max_parallel=spec.get('max_parallel_employees', 1),
                             cancellation=cancellation.at(stage='work_wave', day=day) if cancellation else None,
                             continue_on_error=resilient)
            if day not in spec.get('update_days', []): continue
            check_cancellation(cancellation)
            if spec.get('max_parallel_updates', 1) > 1:
                from .experience_update import dispatch_updates
                selections = [(employee, select_experiences(world, state['sessions'], employee, day))
                              for employee in sorted(skills)]
                selections = [(employee, selected) for employee, selected in selections if selected]

                def record_update(employee, update):
                    state['updates'].append({'day': day, 'employee_id': employee, 'result': update})
                    if update.get('accepted'):
                        skills[employee] = update['skill']
                    checkpoint()

                def journal_updates(employees):
                    if employees:
                        save(out / 'INFLIGHT.json', {'kind': 'learning_wave', 'day': day,
                            'employee_ids': employees, 'budget_per_employee': learner.identity().get('budget')})
                    else:
                        (out / 'INFLIGHT.json').unlink()

                dispatch_updates(bank, harness, judge, learner, selections, day=day, skills=skills, out=out,
                    record=record_update, journal=journal_updates, max_parallel=spec['max_parallel_updates'],
                    cancellation=cancellation.at(stage='learning_wave', day=day) if cancellation else None,
                    continue_on_error=resilient)
            else:
                for employee in sorted(skills):
                    check_cancellation(cancellation)
                    selected = select_experiences(world, state['sessions'], employee, day)
                    if not selected: continue
                    save(out / 'INFLIGHT.json', {'kind': 'learning', 'day': day, 'employee_id': employee,
                                                'budget': learner.identity().get('budget')})
                    update = update_employee(bank, harness, judge, learner, selected, employee=employee, day=day,
                        skill=skills[employee], update_root=out / 'learning' / f'd{day:03d}-{employee}',
                        continue_on_error=resilient)
                    state['updates'].append({'day': day, 'employee_id': employee, 'result': update})
                    checkpoint()
                    if update['status'] not in ('completed', 'budget_exhausted') and not resilient:
                        raise RuntimeError('Learning failed; evidence preserved without automatic replay')
                    if update.get('accepted'): skills[employee] = update['skill']
                    checkpoint(); (out / 'INFLIGHT.json').unlink()
        # Close the observation window without extra work opportunities. Delayed
        # reviews and payments settle; outstanding obligations remain failures.
        drain = max(place.delay + place.settlement_delay,
                    max(s['due_day'] - s['day'] for s in world['schedule']) + place.grace) + 1
        for day in range(spec['days'], spec['days'] + drain): place.advance(day)
        checkpoint()
        summary = place.summary()
        report = {'status': 'completed', 'world_seed': world['seed'], 'arm': learner.identity()['name'],
            'work_sessions': len(state['sessions']), 'probe_sessions': summary['probe_obligations'],
            'probe_quality_mean': summary['probe_quality_mean'],
            'probe_accepted_on_time_fraction': summary['probe_accepted_on_time_fraction'],
            'learning_epochs': len(state['updates']), 'adoptions': sum(u['result']['accepted'] for u in state['updates']),
            'work_and_judging_tokens': sum(s['tokens'] for s in state['sessions']),
            'learning_and_replay_judging_tokens': sum(u['result']['costs']['tokens'] for u in state['updates']),
            'actor_usage': driver.usage(), 'workplace': summary,
            'world_schedule_sha256': stable_hash(world), 'scope': world['scope']}
        report['failures'] = report_failures(state['sessions'], state['updates'], state['decision_failures'])
        save(out / 'REPORT.json', report)
        return report
    finally:
        checkpoint()
        if driver is not None: driver.close()
