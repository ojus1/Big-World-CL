"""Capture observed learning supply without dispatching work or altering a study.

The verified controller selects from captured completed sessions. Future-day
readiness uses only already completed work and assumes its scheduled feedback
is released; it does not assume future tasks succeed. Eligibility is not an
update, proposal, adoption, scoring audit or evidence of a learning effect.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from scripts.source_world_calibration import read, save, sha
from worldlab.bank import Bank
from worldlab.campaign import source_identity
from worldlab.validation_context import ISOLATED, policy, select_experiences, validate_world
from worldlab.worlds import PARTITIONS


def require(value, message):
    if not value:
        raise ValueError(message)


def selection(world, sessions, employee, day):
    observed = [s for s in sessions if s['employee_id'] == employee and s['status'] == 'completed']
    released = [s for s in observed if s['feedback_day'] <= day]
    selected = select_experiences(world, sessions, employee, day)
    return {'eligible': bool(selected), 'completed_sessions': len(observed),
            'released_sessions': len(released),
            'released_training_lineages': len({s['lineage_group'] for s in released if s['split'] == 'train'}),
            'released_workplace_validation_lineages': len({s['lineage_group'] for s in released if s['split'] == 'val'}),
            'selected_training_ids': [s['id'] for s in selected if s['split'] == 'train'],
            'selected_validation_ids': [s['id'] for s in selected if s['split'] == 'val']}


def describe(world, state, bank):
    validate_world(bank, world)
    spec = world['specification']
    employees = {e['id']: e for e in world['workforce']}
    require(len(employees) == len(world['workforce']), 'Duplicate employee')
    day = state.get('workplace', {}).get('day', state.get('day'))
    require(type(day) is int and day >= -1, 'Missing or invalid recorded day')
    sessions = state['sessions']
    require(len({s['id'] for s in sessions}) == len(sessions), 'Duplicate published session')
    require(sessions == sorted(sessions, key=lambda s: (s['day'], s['day_order'])),
            'Published sessions are not in controller order')
    for session in sessions:
        source = bank.by_id[session['task_id']]
        require(session['employee_id'] in employees and session['split'] in PARTITIONS and
                source['calibration_group'] == session['lineage_group'] and
                source['partition'] == PARTITIONS[session['split']], 'Session employee, lineage or partition changed')
        require(type(session['day']) is int and 0 <= session['day'] <= day and
                session['feedback_day'] == session['day'] + spec.get('feedback_delay', 1),
                'Session work or feedback chronology changed')
        if session['status'] == 'completed':
            require(session['grade']['grading_complete'] is True, 'Completed session has no complete grade')
    rows = []
    for employee in world['workforce']:
        eid = employee['id']
        updates = [u for u in state['updates'] if u['employee_id'] == eid]
        recorded_days = {u['day'] for u in updates}
        future = [d for d in spec.get('update_days', []) if d >= day and d not in recorded_days]
        next_day = min(future) if future else None
        rows.append({'employee_id': eid, 'role': employee['role'], 'language': employee['language'],
            'calibration_status': employee['calibration']['calibration_status'],
            'recorded_day': day, 'required_training_lineages': spec.get('train_cases', 2),
            'required_validation_lineages': spec.get('val_cases', 2),
            'isolated_gate_descriptors': len(world['validation_cases'][eid]) if policy(spec) == ISOLATED else 0,
            'observed_now': selection(world, sessions, eid, day),
            'next_unrecorded_update_day': next_day,
            'at_next_update_from_existing_work': selection(world, sessions, eid, next_day) if next_day is not None else None,
            'recorded_updates': len(updates),
            'recorded_adoptions': sum(u['result'].get('accepted') is True for u in updates)})
    return rows


def capture(study_root, bank, out):
    root, out = Path(study_root).resolve(), Path(out).resolve()
    require(out != root and not out.is_relative_to(root), 'Keep the report outside the running study')
    study = read(root / 'STUDY.json')
    study_sha = sha(root / 'STUDY.json')
    require(study_sha == read(root / 'PREPARED.json')['study_sha256'], 'Prepared study changed')
    actual_sources = source_identity()
    require(study.get('source_sha256') and all(actual_sources.get(k) == v for k, v in study['source_sha256'].items()),
            'Use the frozen study execution sources for this observation')
    learner = study['learner']['name']
    require(isinstance(learner, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', learner)
            and learner != 'no_learning', 'Invalid learner arm')
    seeds = [w['seed'] for w in study['worlds']]
    require(seeds and all(type(s) is int for s in seeds) and len(seeds) == len(set(seeds)), 'Invalid world seeds')
    out.mkdir(parents=True, exist_ok=False)
    snapshots, missing, rows = {}, [], []
    for world in study['worlds']:
        require(world['bank_manifest_sha256'] == bank.verification['manifest_sha256'], 'Prepared bank changed')
        for arm in ('no_learning', learner):
            rel = f'worlds/seed-{world["seed"]}/{arm}'
            original = root / rel
            path = original / 'STATE.json'
            if not path.exists():
                missing.append({'seed': world['seed'], 'arm': arm, 'reason': 'No published state observed'})
                continue
            raw = path.read_bytes()
            state = json.loads(raw)
            target = out / 'snapshots' / rel / 'STATE.json'
            target.parent.mkdir(parents=True); target.write_bytes(raw)
            receipts = {}
            for session in state['sessions']:
                sid = session['id']
                require(isinstance(sid, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', sid), 'Unsafe session ID')
                receipt = original / 'sessions' / sid / 'ATTEMPT.json'
                require(not receipt.is_symlink() and sha(receipt) == session['attempt_sha256'],
                        'Published attempt receipt changed')
                attempt = read(receipt)
                require(all(attempt[k] == session[k] for k in ('task_id', 'employee_id', 'status', 'grade')),
                        'Published state differs from the attempt receipt')
                receipts[sid] = session['attempt_sha256']
            snapshots[rel] = {'state_sha256': sha(target), 'published_attempt_sha256': receipts}
            rows.extend({'seed': world['seed'], 'arm': arm, 'is_learner_arm': arm == learner, **r}
                        for r in describe(world, state, bank))
    require(sha(root / 'STUDY.json') == study_sha, 'Study changed during observation')
    plan = {'captured_at': datetime.now(timezone.utc).isoformat(), 'study_sha256': study_sha,
            'source_sha256': study['source_sha256'], 'reporter_sha256': sha(Path(__file__)),
            'bank_manifest_sha256': bank.verification['manifest_sha256'], 'snapshots': snapshots,
            'missing_states': missing, 'scope': __doc__}
    save(out / 'PLAN.json', plan)
    active = [r for r in rows if r['is_learner_arm']]
    report = {'plan_sha256': sha(out / 'PLAN.json'), 'model_calls': 0, 'rows': rows,
              'observed_learner_employee_instances': len(active),
              'learner_employees_eligible_now': sum(r['observed_now']['eligible'] for r in active),
              'learner_employees_sufficient_at_next_update_from_existing_work': sum(
                  (r['at_next_update_from_existing_work'] or {}).get('eligible', False) for r in active),
              'recorded_learner_updates': sum(r['recorded_updates'] for r in active),
              'recorded_learner_adoptions': sum(r['recorded_adoptions'] for r in active),
              'missing_states': missing, 'calibration_status_counts_in_observed_learner_arms':
                  dict(Counter(r['calibration_status'] for r in active)),
              'whole_study_audit': False, 'scope': __doc__}
    save(out / 'REPORT.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--bank', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.study, Bank(args.bank), args.out)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))
