"""Read-only task-world audit. Recompute scores from saved judge responses.

This verifies execution and calculations, not whether model judgments are true.
"""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.source_world_calibration import read, sha, child
from .bank import Bank
from .campaign import source_identity, SEED_SKILL
from .contracts import Budget, validate_execution, validate_grade
from .worlds import stable_hash
from .validation_context import select_experiences, validate_world
from .attempts import task_instruction
from .artifact_inventory import verify as verify_inventory


def require(condition, message):
    if not condition: raise ValueError(message)


def audit_attempt(bank, root, task_id, expected_skill=None, harness=None, employee_message=None, judge=None):
    require(not (root / 'ATTEMPT.json').is_symlink(), 'Attempt receipt cannot be a symlink')
    record = read(root / 'ATTEMPT.json')
    verify_inventory(root, record['artifact_inventory'], record.get('artifact_symlinks', {}),
                     exclude=('ATTEMPT.json',))
    request = read(root / 'PUBLIC_REQUEST.json')
    original = bank.public(task_id)['instruction']
    require(request['instruction'] == task_instruction(original, employee_message), 'Public task instruction mismatch')
    if employee_message is not None:
        require(read(root / 'EMPLOYEE_REQUEST.json') == {'message': employee_message, 'original_instruction': original},
                'Employee delegation changed')
    if expected_skill is not None: require(request['skill'] == expected_skill, 'Wrong deployed skill')
    execution = read(root / 'EXECUTION_RECEIPT.json')
    require(execution == record['execution'], 'Execution receipt changed')
    validate_execution(execution, Budget(**request['budget']), request['skill'])
    if harness is None:
        raise ValueError('Supply the harness offline auditor')
    harness.audit_execution(root, request, execution)
    workspace = root / request['employee_id'] / 'workspace'
    prefix = bank.by_id[task_id]['public_directory'] + '/'
    expected_baseline = {name[len(prefix):]: item['sha256'] for name, item in bank.inventory.items()
                         if name.startswith(prefix) and name[len(prefix):] != 'task.json'}
    expected_baseline['.employee_identity'] = hashlib.sha256((request['employee_id'] + '\n').encode()).hexdigest()
    require(read(root / 'BASELINE.json') == expected_baseline, 'Original input baseline changed')
    require(record['trajectory'] == execution['trajectory'] and record['skill_sha256'] == execution['skill_sha256'],
            'Normalized trajectory or skill changed')
    if judge is None:
        from .qualitative import FrozenRubricJudge
        judge = FrozenRubricJudge
    grade = record['grade']
    validate_grade(grade)
    require(grade['grading_complete'], 'Judgment incomplete')
    judge.audit_grade(bank, task_id, workspace, expected_baseline, root / 'judging', grade)
    jm = grade['usage']
    require(record['tokens'] == execution['charged_tokens'] + jm['charged_tokens'] and
            record['model_calls'] == execution['physical_model_calls'] + jm['physical_model_calls'], 'Combined cost mismatch')
    return record


def audit_updates(bank, world, root, state, name, harness, counts, learner=None, learner_identity=None, judge=None):
    updates = state['updates']
    from .contracts import NoLearning
    skills = {e['id']: SEED_SKILL for e in world['workforce']}
    seen = set()
    previous_day = -1
    for item in updates:
        employee, day = item['employee_id'], item['day']
        require(employee in skills and type(day) is int and day in world['specification'].get('update_days', []) and
                day >= previous_day and (day, employee) not in seen, 'Invalid or duplicate learning chronology')
        previous_day = day; seen.add((day, employee))
        before = skills[employee]
        update = item['result']
        require(update['status'] in ('completed', 'budget_exhausted') and type(update['accepted']) is bool and
                isinstance(update['skill'], str) and
                (not update['accepted'] or update['status'] == 'completed') and
                (update['accepted'] or update['skill'] == before), 'Invalid skill adoption result')
        if name == 'no_learning':
            NoLearning.audit_update(None, update, skill_before=before, expected_identity=NoLearning().identity())
            continue
        update_root = root / 'learning' / f'd{item["day"]:03d}-{item["employee_id"]}'
        require(read(update_root / 'UPDATE.json') == update, 'Update evidence changed')
        selected = select_experiences(world, state['sessions'], item['employee_id'], item['day'])
        by_id = {s['id']: s for s in selected}
        require(update['train_ids'] == [s['id'] for s in selected if s['split'] == 'train'] and
                update['validation_ids'] == [s['id'] for s in selected if s['split'] == 'val'], 'Learning leaked future or wrong cases')
        from .experience_update import audit_replay_admissions
        audit_replay_admissions(update_root, update, selected)
        for replay in update['replay_evidence']:
            r = audit_attempt(bank, update_root / f'replay-{replay["attempt_index"]:03d}', by_id[replay['id']]['task_id'], harness=harness,
                                      employee_message=by_id[replay['id']].get('employee_message'), judge=judge)
            require(replay['hard'] == float(r['grade']['success']) and replay['soft'] == r['grade']['quality_score'], 'Replay score mismatch')
            req = read(update_root / f'replay-{replay["attempt_index"]:03d}' / 'PUBLIC_REQUEST.json')
            require(hashlib.sha256(req['skill'].encode()).hexdigest() == replay['skill_sha256'], 'Replay skill mismatch')
            operations = [o for o in update['costs']['operations'] if o['kind'] == 'target']
            operation = operations[replay['attempt_index']]
            require(operation['tokens'] == r['tokens'] and operation['model_calls'] == r['model_calls'],
                    'Learning ledger differs from work plus judge usage')
            counts['learning_replays'] += 1
        require(learner is not None and learner_identity is not None,
                'Supply the registered learner offline auditor')
        learner.audit_update(update_root, update, skill_before=before, expected_identity=learner_identity)
        counts['adoptions'] += int(update['accepted'])
        if update['accepted']: skills[employee] = update['skill']


def resolve_auditors(study, harness=None, learner=None):
    """Never silently audit a configured implementation as the built-in adapter."""
    resolved = []
    for kind, supplied in (('harness', harness), ('learner', learner)):
        identity = study[kind]
        if supplied is not None:
            require(supplied.identity() == identity, kind + ' auditor differs from frozen identity')
            require(callable(getattr(supplied, 'audit_execution' if kind == 'harness' else 'audit_update', None)),
                    kind + ' does not implement its offline audit method')
            resolved.append(supplied)
            continue
        require('operator_factory' not in identity, 'Supply the frozen ' + kind + ' factory configuration for audit')
        if kind == 'harness' and identity['name'] == 'native_hermes_task_package':
            from .hermes import Hermes
            resolved.append(Hermes)
        elif kind == 'learner' and identity['name'] == 'skillopt_sleep':
            from .learning import SkillOpt
            resolved.append(SkillOpt)
        else:
            raise ValueError('Supply an offline auditor for the registered ' + kind)
    return tuple(resolved)


def resolve_judge(study, judge=None):
    identity = study['judge']
    if judge is not None:
        require(judge.identity() == identity, 'Judge auditor differs from frozen identity')
        require(callable(getattr(judge, 'audit_grade', None)), 'Judge needs its offline audit_grade method')
        return judge
    require('operator_factory' not in identity, 'Supply the frozen judge factory configuration for audit')
    require(identity['name'] == 'frozen_internal_r3_text_judge', 'Supply an offline auditor for the registered judge')
    from .qualitative import FrozenRubricJudge
    return FrozenRubricJudge


def audit(bank, out, harness=None, learner=None, judge=None):
    study = read(out / 'STUDY.json')
    require(sha(out / 'STUDY.json') == read(out / 'PREPARED.json')['study_sha256'], 'Study bytes changed')
    require(source_identity() == study['source_sha256'], 'Use the frozen source checkout for this study')
    harness, learner = resolve_auditors(study, harness, learner)
    judge = resolve_judge(study, judge)
    if study.get('employee_driver') is not None:
        from .audit_reacting import audit_workplaces
        return audit_workplaces(bank, out, study, harness, learner, judge)
    counts = {'online_attempts': 0, 'learning_replays': 0, 'adoptions': 0, 'world_pairs': 0}
    for world in study['worlds']:
        validate_world(bank, world)
        require(world['bank_manifest_sha256'] == bank.verification['manifest_sha256'], 'Bank changed')
        for name in ['no_learning', study['learner']['name']]:
            root = out / 'worlds' / f'seed-{world["seed"]}' / name
            report, state = read(root / 'REPORT.json'), read(root / 'STATE.json')
            require(report['status'] == 'completed' and not (root / 'INFLIGHT.json').exists(), 'World incomplete')
            require([s['id'] for s in state['sessions']] == [s['id'] for s in world['schedule']], 'World schedule changed')
            updates = state['updates']
            for slot, session in zip(world['schedule'], state['sessions']):
                require(all(session[k] == v for k, v in slot.items()), 'Session identity changed')
                past = [u for u in updates if u['employee_id'] == slot['employee_id'] and
                        u['day'] < slot['day'] and u['result']['accepted']]
                skill = past[-1]['result']['skill'] if past else SEED_SKILL
                record = audit_attempt(bank, root / 'sessions' / slot['id'], slot['task_id'], skill, harness, judge=judge)
                require(record['grade'] == session['grade'] and record['tokens'] == session['tokens'], 'Session receipt mismatch')
                require(sha(root / 'sessions' / slot['id'] / 'ATTEMPT.json') == session['attempt_sha256'], 'Session hash mismatch')
                counts['online_attempts'] += 1
            audit_updates(bank, world, root, state, name, harness, counts, learner, study['learner'], judge)
            probes = [s for s in state['sessions'] if s['split'] == 'probe']
            require(report['probe_quality_mean'] == sum(s['grade']['quality_score'] for s in probes) / len(probes), 'Probe report mismatch')
            require(report['world_schedule_sha256'] == stable_hash(world), 'World schedule hash mismatch')
            require(report['work_and_judging_tokens'] == sum(s['tokens'] for s in state['sessions']) and
                    report['learning_and_replay_judging_tokens'] == sum(u['result']['costs']['tokens'] for u in updates), 'World cost mismatch')
        counts['world_pairs'] += 1
    return {'ok': True, **counts, 'scope': 'Execution, split, skill-gate and accounting audit. Model-judgment correctness and confirmatory statistical validity are not certified.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--harness-config', type=Path)
    p.add_argument('--learner-config', type=Path)
    p.add_argument('--judge-config', type=Path)
    a = p.parse_args()
    harness = learner = judge = None
    if a.harness_config:
        from .adapters import load_adapter
        harness = load_adapter(a.harness_config, 'harness')
    if a.learner_config:
        from .adapters import load_adapter
        learner = load_adapter(a.learner_config, 'learner')
    if a.judge_config:
        from .adapters import load_adapter
        judge = load_adapter(a.judge_config, 'judge')
    print(json.dumps(audit(Bank(a.bank), a.out.resolve(), harness=harness, learner=learner, judge=judge), indent=2))
