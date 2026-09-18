"""Chronological, calibrated work worlds with persistent employee skill state.

This first world protocol uses fixed source packages and isolated task attempts.
Employee queues, feedback, obligations, skills and costs persist across days.
It is a development skill-transfer world, not yet a reacting MiroFish economy.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import re
import time
from scripts.source_world_calibration import read, save, sha
from .attempts import execute_task
from .calibration import fit
from .campaign import SEED_SKILL, source_identity
from .contracts import Budget
from .dispatch import dispatch_day
from .resilience import POLICIES, enabled, attempt_seconds, report_failures
from .cancellation import check as check_cancellation
from .workforce import expand_workforce
from .validation_context import ISOLATED, policy, compile_cases, validate_world, select_experiences, employee_world

PARTITIONS = {'train': 'calibration_train', 'val': 'calibration_validation', 'probe': 'calibration_holdout'}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compile_world(bank, specification, seed, harness, judge):
    """Freeze all schedules before outcomes; role defaults work without examples."""
    if specification.get('study_scope') != 'development':
        raise ValueError('The calibration bank cannot authorize a final confirmatory study')
    if specification.get('failure_policy', 'record_and_continue') not in POLICIES:
        raise ValueError('Unsupported study failure policy')
    employees = specification['employees']
    isolated = policy(specification) == ISOLATED
    calibrated = fit(bank, specification)
    fit_by_id = {r['employee_id']: r for r in calibrated['workforce']}
    days = specification['days']
    probe_start = specification['probe_start_day']
    updates = specification.get('update_days', [])
    if type(days) is not int or not 2 <= probe_start < days or any(d >= probe_start - 1 or d < 1 for d in updates):
        raise ValueError('Learning must finish before the fixed probe phase')
    delay = specification.get('feedback_delay', 1)
    if type(delay) is not int or delay < 1:
        raise ValueError('Feedback must be delayed by at least one day')
    work_budget = Budget(**specification.get('work_budget', {}))
    for field in ('max_parallel_employees', 'max_parallel_worlds', 'max_parallel_updates'):
        parallel = specification.get(field, 1)
        if type(parallel) is not int or not 1 <= parallel <= 64:
            raise ValueError(field + ' must be an integer from 1 to 64')
    workforce = []
    schedule = []
    issues = []
    validation_cases = {}
    for employee in employees:
        eid = employee['id']
        capacity = employee.get('sessions_per_day', 1)
        count = employee.get('arrivals_per_day', capacity)
        if any(type(value) is not int or not 1 <= value <= 64 for value in (capacity, count)):
            raise ValueError('Daily work capacity and arrivals must be integers from 1 to 64')
        selector = employee.get('task_selector', {})
        candidates = [r for r in bank.rows if r['language'] == employee['language'] and
                      all(r[field] in selector[key] for key, field in
                          [('sources', 'source'), ('workflows', 'workflow')]
                          if key in selector)]
        pool = defaultdict(list)
        for row in candidates:
            reasons = harness.unsupported(bank.public(row['id'])) + judge.unsupported(bank.public(row['id']))
            if reasons:
                issues.append({'employee_id': eid, 'task_id': row['id'], 'reasons': reasons})
                continue
            pool[row['partition']].append(row)
        if any(not pool[partition] for partition in PARTITIONS.values()):
            raise ValueError('Employee lacks a supported train/validation/probe pool: ' + eid)
        # Role controls which work is suitable. Calibration weights influence
        # TRAIN frequency only; future val/probe briefs never enter the fit.
        mixture = fit_by_id[eid]['task_mixture'] or {}
        available_train = {r['id'] for r in pool[PARTITIONS['train']]}
        application = {'supported_training_weight': sum(weight for task, weight in mixture.items()
                                                       if task in available_train),
                       'unavailable_matched_tasks': sorted(set(mixture) - available_train),
                       'status': 'applied' if set(mixture) & available_train else 'retained_default'}
        rng = random.Random(stable_hash([seed, eid]))
        if isolated:
            validation_cases[eid] = compile_cases(pool[PARTITIONS['val']], eid, seed,
                                                   asdict(work_budget), specification.get('val_cases', 2))
        used = defaultdict(Counter)
        employee_slots = []
        for day in range(days):
            split = 'probe' if day >= probe_start else 'val' if not isolated and day % 4 in (1, 3) else 'train'
            for ordinal in range(count):
                available = pool[PARTITIONS[split]]
                # Guarantee a minimally distinct early learning slice, then
                # respect the calibrated frequency weights. Probe coverage uses
                # every eligible family before a repeat.
                required = (specification.get('train_cases', 2) if split == 'train'
                            else specification.get('val_cases', 2))
                if split == 'probe' or len(used[split]) < required:
                    least = min(used[split][r['calibration_group']] for r in available)
                    eligible = [r for r in available if used[split][r['calibration_group']] == least]
                else:
                    eligible = available
                weights = [1 + 4 * mixture.get(r['id'], 0) if split == 'train' else 1 for r in eligible]
                row = rng.choices(eligible, weights=weights, k=1)[0]
                used[split][row['calibration_group']] += 1
                slot = {'id': f'd{day:03d}-{eid}-{ordinal:03d}', 'day': day,
                        'employee_id': eid, 'task_id': row['id'], 'split': split,
                        'lineage_group': row['calibration_group'], 'feedback_day': day + delay,
                        'due_day': day + employee.get('deadline_days', 1),
                        'work_budget': asdict(work_budget)}
                employee_slots.append(slot)
        schedule.extend(employee_slots)
        workforce.append({**deepcopy(employee), 'calibration': fit_by_id[eid],
                          'calibration_application': application,
                          'distinct_groups_by_split': {key: len(value) for key, value in used.items()}})
    schedule.sort(key=lambda s: (s['day'], s['employee_id'], s['id']))
    # Fix execution order independently from future scores, separately each day.
    for day in range(days):
        day_slots = [s for s in schedule if s['day'] == day]
        random.Random(seed * 1009 + day).shuffle(day_slots)
        for order, slot in enumerate(day_slots): slot['day_order'] = order
    schedule.sort(key=lambda s: (s['day'], s['day_order']))
    world = {'schema_version': 1, 'seed': seed, 'specification': specification,
            'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'workforce': workforce, 'schedule': schedule, 'capability_exclusions': issues,
            'scope': 'Development fixed-package skill-transfer world. Sessions and reused task families are dependent; this is not final-test or reacting-economy evidence.'}
    if isolated:
        world['validation_cases'] = validation_cases
    validate_world(bank, world)
    return world


def eligible_experiences(sessions, employee, day, train_cases, val_cases):
    """Latest released observation per lineage, fixed temporal selection, no scores."""
    grouped = {'train': {}, 'val': {}}
    for session in sessions:
        if (session['employee_id'] != employee or session['feedback_day'] > day or
                session['split'] not in grouped or session['status'] != 'completed'):
            continue
        grouped[session['split']][session['lineage_group']] = session
    if len(grouped['train']) < train_cases or len(grouped['val']) < val_cases:
        return []
    chosen = [r for split, count in [('train', train_cases), ('val', val_cases)]
              for r in list(grouped[split].values())[-count:]]
    chosen.sort(key=lambda s: (s['day'], s['id']))
    return chosen


def prepare_study(bank, spec, seeds, harness, judge, learner, out, employee_factory=None):
    spec = expand_workforce(spec)
    spec = {**spec, 'failure_policy': spec.get('failure_policy', 'record_and_continue')}
    replay_seconds = learner.identity().get('budget', {}).get('replay_seconds')
    if (spec.get('update_days') and replay_seconds is not None
            and replay_seconds < attempt_seconds(harness, Budget(**spec.get('work_budget', {})))):
        raise ValueError('Replay timeout cannot fit work, settlement and 300 seconds of judging')
    if callable(getattr(learner, 'validate_plan', None)):
        learner.validate_plan(spec, judge)
    if not callable(getattr(learner, 'audit_update', None)):
        raise ValueError('Learner must provide an offline audit_update method before preparation')
    if not callable(getattr(judge, 'audit_grade', None)):
        raise ValueError('Judge must provide an offline audit_grade method before preparation')
    if type(judge.max_tokens) is not int or judge.max_tokens <= 0:
        raise ValueError('Judge must declare a positive integer max_tokens ceiling')
    if judge.identity().get('bank_manifest_sha256', bank.verification['manifest_sha256']) != bank.verification['manifest_sha256']:
        raise ValueError('Judge bank differs from the prepared task bank')
    name = learner.identity().get('name')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name) or name == 'no_learning':
        raise ValueError('The experimental learner needs a safe arm name distinct from no_learning')
    out = Path(out).resolve()
    if out.exists() or len(seeds) != len(set(seeds)) or not seeds:
        raise ValueError('Fresh output and unique world seeds required')
    worlds = [compile_world(bank, spec, seed, harness, judge) for seed in seeds]
    if max(spec.get('max_parallel_worlds', 1), spec.get('max_parallel_updates', 1)) > 1:
        import pickle
        try:
            pickle.loads(pickle.dumps((bank, harness, judge, learner, employee_factory)))
        except Exception as exc:
            raise ValueError('Parallel execution requires process-serializable adapters: ' + type(exc).__name__) from None
    if employee_factory is None and any(e.get('arrivals_per_day', e.get('sessions_per_day', 1)) !=
            e.get('sessions_per_day', 1) for e in spec['employees']):
        raise ValueError('Independent arrivals and capacity require a workplace employee driver')
    if employee_factory is not None:
        from .workplace import Workplace
        for world in worlds:
            Workplace(world)  # Validate consequence parameters before any native calls.
            world['employee_context'] = employee_factory.prepare(employee_world(world))
            world['scope'] = ('Development workplace with native employee decisions, persistent queues, delayed feedback, '
                              'rework and colleague messages. Roles and task arrivals are assigned; no final-test inference.')
    work_limits = [work_opportunity_limit(w) if employee_factory is not None else len(w['schedule']) for w in worlds]
    # A repeated obligation consumes another capacity slot. Reserve every slot,
    # even if deferral or an empty queue ultimately makes it unused.
    work_reservation = (2 * sum(limit * (Budget(**spec.get('work_budget', {})).total_tokens + judge.max_tokens)
                               for limit in work_limits))
    learning_reservation = sum(len(w['workforce']) * len(spec.get('update_days', [])) for w in worlds) * learner.identity().get('budget', {}).get('max_tokens', 0)
    harness_model = harness.identity().get('provider', {}).get('model')
    judge_model = judge.identity().get('provider', {}).get('model')
    manifest = {'schema_version': 1, 'worlds': worlds, 'harness': harness.identity(),
                'judge': judge.identity(), 'learner': learner.identity(), 'source_sha256': source_identity(),
                'seed_skill': SEED_SKILL,
                'token_reservation_ceiling': {'work_including_judges': work_reservation,
                                              'learning_including_replay_judges': learning_reservation,
                                              'total': work_reservation + learning_reservation},
                'analysis': {'unit': 'world_pair', 'primary': 'post_learning_probe_quality_mean',
                             'scope': 'development', 'all_planned_probes_in_denominator': True,
                             'same_model_judge': harness_model == judge_model
                                if harness_model is not None and judge_model is not None else None}}
    if employee_factory is not None:
        manifest['employee_driver'] = employee_factory.identity()
        manifest['analysis']['primary'] = 'probe_accepted_on_time_fraction'
        manifest['actor_reservations'] = {'max_logical_interviews': 4 * sum(work_limits),
                                          'input_and_bootstrap_token_ceiling': None,
                                          'scope': 'Work and learning ceiling excludes native employee generation'}
    if policy(spec) == ISOLATED:
        manifest['analysis']['validation_context'] = ISOLATED
    save(out / 'STUDY.json', manifest)
    save(out / 'PREPARED.json', {'study_sha256': sha(out / 'STUDY.json'), 'prepared_unix': time.time()})
    return {'study_sha256': sha(out / 'STUDY.json'), 'world_pairs': len(worlds),
            'token_reservation_ceiling': manifest['token_reservation_ceiling'],
            'planned_work_sessions': 2 * sum(work_limits),
            'planned_obligations': 2 * sum(len(w['schedule']) for w in worlds)}


def work_opportunity_limit(world):
    """Maximum decisions/delegations per arm, including rework and deferrals."""
    return world['specification']['days'] * sum(e.get('sessions_per_day', 1) for e in world['workforce'])


def run_world(bank, world, harness, judge, learner, out, *, cancellation=None):
    check_cancellation(cancellation)
    validate_world(bank, world)
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    spec = world['specification']
    resilient = enabled(spec)
    skills = {e['id']: SEED_SKILL for e in world['workforce']}
    sessions, updates, events = [], [], []
    state = {'day': 0, 'skills': skills, 'sessions': sessions, 'updates': updates, 'events': events}
    judge_tokens = judge.max_tokens
    for day in range(spec['days']):
        check_cancellation(cancellation)
        state['day'] = day

        def work(slot):
            return execute_task(bank, harness, judge, task_id=slot['task_id'], employee_id=slot['employee_id'],
                                  skill=skills[slot['employee_id']], budget=Budget(**slot['work_budget']),
                                  out=out / 'sessions' / slot['id'], judge_tokens=judge_tokens, continue_on_error=resilient)

        def record_work(slot, result):
            record = {**slot, 'status': result['status'], 'tokens': result['tokens'],
                      'model_calls': result['model_calls'], 'grade': result['grade'],
                      'accounting_complete': result.get('accounting_complete', result['status'] == 'completed'),
                      'attempt_sha256': sha(out / 'sessions' / slot['id'] / 'ATTEMPT.json'),
                      'skill_content_sha256': hashlib.sha256(skills[slot['employee_id']].encode()).hexdigest()}
            sessions.append(record)
            sessions.sort(key=lambda s: (s['day'], s['day_order']))
            events.append({'day': day, 'kind': 'work_completed' if result['status'] == 'completed' else 'work_incomplete',
                           'employee_id': slot['employee_id'], 'obligation_id': slot['id'],
                           'feedback_release_day': slot['feedback_day']})
            save(out / 'STATE.json', state)
            print(json.dumps({'world': world['seed'], 'arm': learner.identity()['name'], 'day': day,
                              'session': slot['id'], 'status': result['status'],
                              'quality': result['grade']['quality_score'] if result.get('grade') else None}), flush=True)

        def journal_work(wave):
            if wave:
                reservations = [{'id': slot['id'], 'max_reserved_tokens': slot['work_budget']['total_tokens'] + judge_tokens}
                                for slot in wave]
                save(out / 'INFLIGHT.json', {'kind': 'work_wave', 'day': day, 'attempts': reservations,
                                            'max_reserved_tokens': sum(r['max_reserved_tokens'] for r in reservations)})
            else:
                (out / 'INFLIGHT.json').unlink()

        dispatch_day([s for s in world['schedule'] if s['day'] == day], work, record_work, journal_work,
                     max_parallel=spec.get('max_parallel_employees', 1),
                     cancellation=cancellation.at(stage='work_wave', day=day) if cancellation else None,
                     continue_on_error=resilient)
        if day not in spec.get('update_days', []): continue
        check_cancellation(cancellation)
        if spec.get('max_parallel_updates', 1) > 1:
            from .experience_update import dispatch_updates
            selections = []
            for employee in sorted(skills):
                selected = select_experiences(world, sessions, employee, day)
                if selected:
                    selections.append((employee, selected))
                else:
                    events.append({'day': day, 'employee_id': employee, 'kind': 'insufficient_released_learning_cases'})

            def record_update(employee, update):
                updates.append({'day': day, 'employee_id': employee, 'result': update})
                if update.get('accepted'):
                    skills[employee] = update['skill']
                    events.append({'day': day + 1, 'employee_id': employee, 'kind': 'skill_deployed',
                                   'content_sha256': hashlib.sha256(update['skill'].encode()).hexdigest()})
                save(out / 'STATE.json', state)

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
                selected = select_experiences(world, sessions, employee, day)
                if not selected:
                    events.append({'day': day, 'employee_id': employee, 'kind': 'insufficient_released_learning_cases'})
                    continue
                update_root = out / 'learning' / f'd{day:03d}-{employee}'
                save(out / 'INFLIGHT.json', {'kind': 'learning', 'day': day, 'employee_id': employee,
                                            'budget': learner.identity().get('budget')})
                from .experience_update import update_employee
                update = update_employee(bank, harness, judge, learner, selected, employee=employee, day=day,
                                         skill=skills[employee], update_root=update_root, executor=execute_task, continue_on_error=resilient)
                updates.append({'day': day, 'employee_id': employee, 'result': update})
                if update['status'] not in ('completed', 'budget_exhausted') and not resilient:
                    save(out / 'STATE.json', state)
                    raise RuntimeError('Learning attempt failed; no automatic replay')
                if update.get('accepted'):
                    skills[employee] = update['skill']
                    events.append({'day': day + 1, 'employee_id': employee, 'kind': 'skill_deployed',
                                   'content_sha256': hashlib.sha256(update['skill'].encode()).hexdigest()})
                save(out / 'STATE.json', state)
                (out / 'INFLIGHT.json').unlink()
    probes = [s for s in sessions if s['split'] == 'probe']
    report = {'status': 'completed', 'world_seed': world['seed'], 'arm': learner.identity()['name'],
              'work_sessions': len(sessions), 'probe_sessions': len(probes),
              'probe_quality_mean': sum(s['grade']['quality_score'] if s['status'] == 'completed' else 0. for s in probes) / len(probes),
              'probe_successes': sum(bool(s['grade']['success']) if s['status'] == 'completed' else False for s in probes),
              'learning_epochs': len(updates), 'adoptions': sum(u['result']['accepted'] for u in updates),
              'work_and_judging_tokens': sum(s['tokens'] for s in sessions),
              'learning_and_replay_judging_tokens': sum(u['result']['costs']['tokens'] for u in updates),
              'world_schedule_sha256': stable_hash(world), 'scope': world['scope']}
    report['failures'] = report_failures(sessions, updates)
    save(out / 'REPORT.json', report)
    return report


def execute_study(bank, harness, judge, learner, out, employee_factory=None):
    from .contracts import NoLearning
    out = Path(out).resolve()
    study = read(out / 'STUDY.json')
    if (sha(out / 'STUDY.json') != read(out / 'PREPARED.json')['study_sha256'] or
            study['source_sha256'] != source_identity() or study['harness'] != harness.identity() or
            study['judge'] != judge.identity() or study['learner'] != learner.identity() or
            any(w['bank_manifest_sha256'] != bank.verification['manifest_sha256'] for w in study['worlds'])):
        raise ValueError('Study preparation differs from current execution dependencies')
    if study.get('employee_driver') != (employee_factory.identity() if employee_factory is not None else None):
        raise ValueError('Employee driver differs from frozen preparation')
    with (out / 'EXECUTION.json').open('x') as f: json.dump({'started_unix': time.time()}, f)
    workers = study['worlds'][0]['specification'].get('max_parallel_worlds', 1)
    if workers > 1:
        from .parallel import execute_pairs
        reports = execute_pairs(bank, study, harness, judge, learner, out, employee_factory, workers)
    else:
        from .cancellation import Cancellation, StudyCancelled
        failure_policy = study['worlds'][0]['specification'].get('failure_policy', 'stop_after_current_wave')
        resilient = enabled(study['worlds'][0]['specification'])
        cancellation = Cancellation(out) if failure_policy != 'drain_all_pairs' else None
        reports = []
        failures = []
        for index, world in enumerate(study['worlds']):
            arms = [NoLearning(), learner]
            if index % 2: arms.reverse()
            for arm in arms:
                root = out / 'worlds' / f'seed-{world["seed"]}' / arm.identity()['name']
                stop = cancellation.at(world_seed=world['seed'], arm=arm.identity()['name']) if cancellation else None
                try:
                    check_cancellation(stop)
                    if employee_factory is None:
                        report = run_world(bank, world, harness, judge, arm, root, cancellation=stop)
                    else:
                        from .reacting import run_world as run_reacting
                        report = run_reacting(bank, world, harness, judge, arm, root, employee_factory, cancellation=stop)
                    reports.append(report)
                except BaseException as exc:
                    if stop is not None and not isinstance(exc, StudyCancelled) and not resilient: stop.request(type(exc).__name__)
                    failures.append({'failed_world': world['seed'], 'failed_arm': arm.identity()['name'],
                                     'error_type': type(exc).__name__})
                    save(out / 'STATUS.json', {'status': 'incomplete', 'completed_arms': len(reports),
                                               'planned_arms': 2 * len(study['worlds']), 'error_type': type(exc).__name__,
                                               'failure_policy': failure_policy,
                                               'stop_requested': cancellation is not None and cancellation.path.exists(),
                                               'failed_world': world['seed'], 'failed_arm': arm.identity()['name'],
                                               'reports': reports, 'failures': failures})
                    if resilient and not isinstance(exc, StudyCancelled): continue
                    raise
                save(out / 'STATUS.json', {'completed_arms': len(reports), 'planned_arms': 2 * len(study['worlds']), 'reports': reports})
    pairs = []
    missing = []
    for world in study['worlds']:
        rows = {r['arm']: r for r in reports if r['world_seed'] == world['seed']}
        if set(rows) != {'no_learning', learner.identity()['name']}:
            missing.append(world['seed'])
            continue
        pairs.append({'seed': world['seed'], 'probe_quality_delta':
                      rows[learner.identity()['name']]['probe_quality_mean'] - rows['no_learning']['probe_quality_mean']})
        if employee_factory is not None:
            pairs[-1]['probe_on_time_delta'] = (rows[learner.identity()['name']]['probe_accepted_on_time_fraction'] -
                                                rows['no_learning']['probe_accepted_on_time_fraction'])
    result = {'status': 'incomplete' if missing else 'completed', 'world_pairs': pairs,
              'missing_world_pairs': missing, 'analysis': study['analysis'],
              'mean_probe_quality_delta': sum(p['probe_quality_delta'] for p in pairs) / len(pairs) if pairs else None,
              'retained_failures': [dict(world_seed=r['world_seed'], arm=r['arm'], **r['failures'])
                                    for r in reports if r.get('failures')],
              'confirmatory_significance_claim': False}
    save(out / 'REPORT.json', result)
    return result
