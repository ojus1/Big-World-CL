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
from .qualitative import validate_verdict
from .contracts import Budget, validate_execution
from .verdict_grammar import contract as verdict_contract
from .judge_transport import digest as transport_digest
from .worlds import eligible_experiences, stable_hash
from .attempts import task_instruction
from .mechanical_criteria import evaluate as mechanical_verdict


def require(condition, message):
    if not condition: raise ValueError(message)


def audit_attempt(bank, root, task_id, expected_skill=None, harness=None, employee_message=None):
    record = read(root / 'ATTEMPT.json')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'ATTEMPT.json'}
    require(actual == set(record['artifact_inventory']), 'Attempt artifact inventory changed')
    for name, digest in record['artifact_inventory'].items():
        p = child(root, name)
        require(not p.is_symlink() and sha(p) == digest, 'Attempt file changed: ' + name)
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
    rubric = read(child(bank.root, bank.by_id[task_id]['private_directory']) / 'rubric.json')
    grade = record['grade']
    require(grade == read(root / 'judging/GRADE.json') and grade['grading_complete'], 'Judgment incomplete')
    verdicts = []
    model_criteria = []
    evidence = read(root / 'judging/EVIDENCE.json')
    expected_files = {str(p.relative_to(workspace)): {'text': p.read_text(), 'sha256': sha(p)}
                      for p in workspace.rglob('*') if p.is_file() and
                      str(p.relative_to(workspace)) != '.employee_identity' and
                      not str(p.relative_to(workspace)).startswith('scratch/')}
    require(evidence['files'] == expected_files and evidence['instruction'] == original,
            'Judge evidence differs from original input and actual deliverables')
    changed = [name for name, digest in expected_baseline.items()
               if not child(workspace, name).is_file() or sha(child(workspace, name)) != digest]
    unauthorized = [name for name in expected_files if name not in expected_baseline and not name.startswith('output/')]
    require(sorted(changed) == sorted(grade['input_changes']) and sorted(unauthorized) == sorted(grade['unauthorized_files']),
            'Preservation result differs from workspace')
    for i, criterion in enumerate(rubric['criteria']):
        payload = read(root / 'judging' / f'REQUEST-{i:02d}.json')
        response = read(root / 'judging' / f'RESPONSE-{i:02d}.json')
        require(payload['criterion'] == criterion and payload['evidence'] == read(root / 'judging/EVIDENCE.json'),
                'Frozen criterion/evidence mismatch')
        require(response['status'] == 'completed', 'Judge response incomplete')
        mechanical = mechanical_verdict(payload)
        require(response['evaluation_method'] == ('registered_literal_count' if mechanical is not None else 'model'),
                'Criterion execution method changed')
        if mechanical is None:
            model_criteria.append(criterion)
        else:
            require(json.loads(response['text']) == mechanical, 'Literal count differs from source/output bytes')
        verdicts.append(validate_verdict(json.loads(response['text']), criterion))
    require(verdicts == grade['criteria'], 'Criterion verdicts changed')
    score = sum(c['weight'] * v['passed'] for c, v in zip(rubric['criteria'], verdicts)) / sum(c['weight'] for c in rubric['criteria'])
    valid_files = not grade['input_changes'] and not grade['unauthorized_files']
    require(grade['quality_score'] == (score if valid_files else 0.) and
            grade['success'] == (all(v['passed'] for v in verdicts) and valid_files), 'Quality aggregation mismatch')
    jm = grade['usage']
    require(jm['accounting_complete'] and jm['physical_model_calls'] == len(model_criteria) and
            jm['charged_tokens'] == sum(r['charged_tokens'] for r in jm['operations']), 'Judge cost mismatch')
    contracts = [transport_digest(verdict_contract(c['id'])) for c in rubric['criteria']]
    require(jm['registered_structured_output_sha256'] == contracts and
            [r['request_structured_outputs_sha256'] for r in jm['operations']] ==
            [transport_digest(verdict_contract(c['id'])) for c in model_criteria],
            'Physical judge constraints differ from the declared bounded grammar')
    require(record['tokens'] == execution['charged_tokens'] + jm['charged_tokens'] and
            record['model_calls'] == execution['physical_model_calls'] + jm['physical_model_calls'], 'Combined cost mismatch')
    return record


def audit_updates(bank, world, root, state, name, harness, counts):
    updates = state['updates']
    for item in updates:
        update = item['result']
        if name == 'no_learning':
            require(not update['accepted'] and update['costs']['tokens'] == 0, 'Control learned')
            continue
        update_root = root / 'learning' / f'd{item["day"]:03d}-{item["employee_id"]}'
        require(read(update_root / 'UPDATE.json') == update, 'Update evidence changed')
        selected = eligible_experiences(state['sessions'], item['employee_id'], item['day'],
                world['specification'].get('train_cases', 2), world['specification'].get('val_cases', 2))
        by_id = {s['id']: s for s in selected}
        require(update['train_ids'] == [s['id'] for s in selected if s['split'] == 'train'] and
                update['validation_ids'] == [s['id'] for s in selected if s['split'] == 'val'], 'Learning leaked future or wrong cases')
        for replay in update['replay_evidence']:
            r = audit_attempt(bank, update_root / f'replay-{replay["attempt_index"]:03d}', by_id[replay['id']]['task_id'], harness=harness,
                                      employee_message=by_id[replay['id']].get('employee_message'))
            require(replay['hard'] == float(r['grade']['success']) and replay['soft'] == r['grade']['quality_score'], 'Replay score mismatch')
            req = read(update_root / f'replay-{replay["attempt_index"]:03d}' / 'PUBLIC_REQUEST.json')
            require(hashlib.sha256(req['skill'].encode()).hexdigest() == replay['skill_sha256'], 'Replay skill mismatch')
            operations = [o for o in update['costs']['operations'] if o['kind'] == 'target']
            operation = operations[replay['attempt_index']]
            require(operation['tokens'] == r['tokens'] and operation['model_calls'] == r['model_calls'],
                    'Learning ledger differs from work plus judge usage')
            counts['learning_replays'] += 1
        for payload in update['optimizer_inputs']:
            require(all(e['task']['id'] in update['train_ids'] and e['task']['split'] == 'train'
                        for e in payload['train_experiences']), 'Optimizer saw non-training evidence')
        from scripts.audit_transfer import gate_check
        gate_check(update)
        counts['adoptions'] += int(update['accepted'])


def audit(bank, out, harness=None):
    study = read(out / 'STUDY.json')
    if harness is None and study['harness']['name'] == 'native_hermes_task_package':
        from .hermes import Hermes
        harness = Hermes  # Static offline auditor; no native environment needed.
    require(harness is not None, 'Supply an offline auditor for the registered harness')
    require(sha(out / 'STUDY.json') == read(out / 'PREPARED.json')['study_sha256'], 'Study bytes changed')
    require(source_identity() == study['source_sha256'], 'Use the frozen source checkout for this study')
    if study.get('employee_driver') is not None:
        from .audit_reacting import audit_workplaces
        return audit_workplaces(bank, out, study, harness)
    counts = {'online_attempts': 0, 'learning_replays': 0, 'adoptions': 0, 'world_pairs': 0}
    for world in study['worlds']:
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
                record = audit_attempt(bank, root / 'sessions' / slot['id'], slot['task_id'], skill, harness)
                require(record['grade'] == session['grade'] and record['tokens'] == session['tokens'], 'Session receipt mismatch')
                require(sha(root / 'sessions' / slot['id'] / 'ATTEMPT.json') == session['attempt_sha256'], 'Session hash mismatch')
                counts['online_attempts'] += 1
            audit_updates(bank, world, root, state, name, harness, counts)
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
    a = p.parse_args()
    print(json.dumps(audit(Bank(a.bank), a.out.resolve()), indent=2))
