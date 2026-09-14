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
import time
from scripts.source_world_calibration import read, save, sha
from .attempts import execute_task
from .calibration import fit
from .campaign import SEED_SKILL, source_identity
from .contracts import Budget
from .dispatch import dispatch_day
from .workforce import expand_workforce

PARTITIONS = {'train': 'calibration_train', 'val': 'calibration_validation', 'probe': 'calibration_holdout'}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compile_world(bank, specification, seed, harness, judge):
    """Freeze all schedules before outcomes; role defaults work without examples."""
    if specification.get('study_scope') != 'development':
        raise ValueError('The calibration bank cannot authorize a final confirmatory study')
    employees = specification['employees']
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
    parallel = specification.get('max_parallel_employees', 1)
    if type(parallel) is not int or not 1 <= parallel <= 64:
        raise ValueError('max_parallel_employees must be an integer from 1 to 64')
    workforce = []
    schedule = []
    issues = []
    for employee in employees:
        eid = employee['id']
        count = employee.get('sessions_per_day', 1)
        if type(count) is not int or count < 1:
            raise ValueError('Invalid daily work volume')
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
        rng = random.Random(stable_hash([seed, eid]))
        used = defaultdict(Counter)
        employee_slots = []
        for day in range(days):
            split = 'probe' if day >= probe_start else 'val' if day % 4 in (1, 3) else 'train'
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
                          'distinct_groups_by_split': {key: len(value) for key, value in used.items()}})
    schedule.sort(key=lambda s: (s['day'], s['employee_id'], s['id']))
    # Fix execution order independently from future scores, separately each day.
    for day in range(days):
        day_slots = [s for s in schedule if s['day'] == day]
        random.Random(seed * 1009 + day).shuffle(day_slots)
        for order, slot in enumerate(day_slots): slot['day_order'] = order
    schedule.sort(key=lambda s: (s['day'], s['day_order']))
    return {'schema_version': 1, 'seed': seed, 'specification': specification,
            'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'workforce': workforce, 'schedule': schedule, 'capability_exclusions': issues,
            'scope': 'Development fixed-package skill-transfer world. Sessions and reused task families are dependent; this is not final-test or reacting-economy evidence.'}


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


def prepare_study(bank, spec, seeds, harness, judge, learner, out):
    spec = expand_workforce(spec)
    out = Path(out).resolve()
    if out.exists() or len(seeds) != len(set(seeds)) or not seeds:
        raise ValueError('Fresh output and unique world seeds required')
    worlds = [compile_world(bank, spec, seed, harness, judge) for seed in seeds]
    work_reservation = 2 * sum(s['work_budget']['total_tokens'] + judge.max_tokens for w in worlds for s in w['schedule'])
    learning_reservation = sum(len(w['workforce']) * len(spec.get('update_days', [])) for w in worlds) * learner.identity().get('budget', {}).get('max_tokens', 0)
    manifest = {'schema_version': 1, 'worlds': worlds, 'harness': harness.identity(),
                'judge': judge.identity(), 'learner': learner.identity(), 'source_sha256': source_identity(),
                'seed_skill': SEED_SKILL,
                'token_reservation_ceiling': {'work_including_judges': work_reservation,
                                              'learning_including_replay_judges': learning_reservation,
                                              'total': work_reservation + learning_reservation},
                'analysis': {'unit': 'world_pair', 'primary': 'post_learning_probe_quality_mean',
                             'scope': 'development', 'all_planned_probes_in_denominator': True,
                             'same_model_judge': harness.identity().get('provider', {}).get('model') == judge.identity()['provider']['model']}}
    save(out / 'STUDY.json', manifest)
    save(out / 'PREPARED.json', {'study_sha256': sha(out / 'STUDY.json'), 'prepared_unix': time.time()})
    return {'study_sha256': sha(out / 'STUDY.json'), 'world_pairs': len(worlds),
            'token_reservation_ceiling': manifest['token_reservation_ceiling'],
            'planned_work_sessions': 2 * sum(len(w['schedule']) for w in worlds)}


def run_world(bank, world, harness, judge, learner, out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    spec = world['specification']
    skills = {e['id']: SEED_SKILL for e in world['workforce']}
    sessions, updates, events = [], [], []
    state = {'day': 0, 'skills': skills, 'sessions': sessions, 'updates': updates, 'events': events}
    judge_tokens = judge.max_tokens
    for day in range(spec['days']):
        state['day'] = day

        def work(slot):
            return execute_task(bank, harness, judge, task_id=slot['task_id'], employee_id=slot['employee_id'],
                                  skill=skills[slot['employee_id']], budget=Budget(**slot['work_budget']),
                                  out=out / 'sessions' / slot['id'], judge_tokens=judge_tokens)

        def record_work(slot, result):
            record = {**slot, 'status': result['status'], 'tokens': result['tokens'],
                      'model_calls': result['model_calls'], 'grade': result['grade'],
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
                     max_parallel=spec.get('max_parallel_employees', 1))
        if day not in spec.get('update_days', []): continue
        for employee in sorted(skills):
            selected = eligible_experiences(sessions, employee, day,
                                            spec.get('train_cases', 2), spec.get('val_cases', 2))
            if not selected:
                events.append({'day': day, 'employee_id': employee, 'kind': 'insufficient_released_learning_cases'})
                continue
            update_root = out / 'learning' / f'd{day:03d}-{employee}'
            save(out / 'INFLIGHT.json', {'kind': 'learning', 'day': day, 'employee_id': employee,
                                        'budget': learner.identity().get('budget')})
            by_id = {s['id']: s for s in selected}
            experiences = [{'id': s['id'], 'split': s['split'], 'available_day': s['day'],
                            'feedback_available_day': s['feedback_day'],
                            'source_session': s['lineage_group'], 'prompt': bank.public(s['task_id'])['instruction'],
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
                                       total_timeout_seconds=limits['timeout_seconds'])
                grade = attempt['grade']
                return {'status': attempt['status'], 'hard': float(grade['success']) if grade else 0.0,
                        'soft': grade['quality_score'] if grade and grade['grading_complete'] else 0.0,
                        'response': json.dumps({'messages': attempt['trajectory']}, ensure_ascii=False),
                        'feedback': grade['feedback'] if grade else '',
                        'tokens': attempt['tokens'], 'model_calls': attempt['model_calls'],
                        'tool_calls': attempt['tool_calls'], 'latency_ms': attempt['seconds'] * 1000}

            update = learner.update(skills[employee], experiences, replay, current_day=day, artifact_root=update_root)
            updates.append({'day': day, 'employee_id': employee, 'result': update})
            if update['status'] not in ('completed', 'budget_exhausted'):
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
              'probe_quality_mean': sum(s['grade']['quality_score'] for s in probes) / len(probes),
              'probe_successes': sum(s['grade']['success'] for s in probes),
              'learning_epochs': len(updates), 'adoptions': sum(u['result']['accepted'] for u in updates),
              'work_and_judging_tokens': sum(s['tokens'] for s in sessions),
              'learning_and_replay_judging_tokens': sum(u['result']['costs']['tokens'] for u in updates),
              'world_schedule_sha256': stable_hash(world), 'scope': world['scope']}
    save(out / 'REPORT.json', report)
    return report


def execute_study(bank, harness, judge, learner, out):
    from .contracts import NoLearning
    out = Path(out).resolve()
    study = read(out / 'STUDY.json')
    if (sha(out / 'STUDY.json') != read(out / 'PREPARED.json')['study_sha256'] or
            study['source_sha256'] != source_identity() or study['harness'] != harness.identity() or
            study['judge'] != judge.identity() or study['learner'] != learner.identity() or
            any(w['bank_manifest_sha256'] != bank.verification['manifest_sha256'] for w in study['worlds'])):
        raise ValueError('Study preparation differs from current execution dependencies')
    with (out / 'EXECUTION.json').open('x') as f: json.dump({'started_unix': time.time()}, f)
    reports = []
    for index, world in enumerate(study['worlds']):
        arms = [NoLearning(), learner]
        if index % 2: arms.reverse()
        for arm in arms:
            root = out / 'worlds' / f'seed-{world["seed"]}' / arm.identity()['name']
            try:
                reports.append(run_world(bank, world, harness, judge, arm, root))
            except BaseException as exc:
                save(out / 'STATUS.json', {'status': 'incomplete', 'completed_arms': len(reports),
                                           'planned_arms': 2 * len(study['worlds']), 'error_type': type(exc).__name__,
                                           'failed_world': world['seed'], 'failed_arm': arm.identity()['name'],
                                           'reports': reports})
                raise
            save(out / 'STATUS.json', {'completed_arms': len(reports), 'planned_arms': 2 * len(study['worlds']), 'reports': reports})
    pairs = []
    for world in study['worlds']:
        rows = {r['arm']: r for r in reports if r['world_seed'] == world['seed']}
        pairs.append({'seed': world['seed'], 'probe_quality_delta':
                      rows[learner.identity()['name']]['probe_quality_mean'] - rows['no_learning']['probe_quality_mean']})
    result = {'status': 'completed', 'world_pairs': pairs, 'analysis': study['analysis'],
              'mean_probe_quality_delta': sum(p['probe_quality_delta'] for p in pairs) / len(pairs),
              'confirmatory_significance_claim': False}
    save(out / 'REPORT.json', result)
    return result
