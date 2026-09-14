"""Exercise native consolidation on temporally selected development experiences.

Historical online work stays immutable. Fresh target replays and their frozen
judge determine consolidation scores. This is a component check, not a new
paired world or evidence of a final learning effect.
"""
import argparse
import json
from pathlib import Path
from scripts.source_world_calibration import read, save, sha
from .bank import Bank
from .campaign import source_identity, SEED_SKILL
from .experience_update import update_employee
from .hermes import Hermes
from .learning import SkillOpt
from .qualitative import FrozenRubricJudge
from .worlds import eligible_experiences


def historical_request(study, attempt_root, record):
    adapter = study['harness']
    if adapter['name'] != 'native_hermes_task_package' or adapter['version'] not in (1, 2):
        raise ValueError('Historical request importer does not recognize this adapter version')
    filename = 'REQUEST.json' if adapter['version'] == 1 else 'PUBLIC_REQUEST.json'
    path = attempt_root / filename
    if record['artifact_inventory'].get(filename) != sha(path):
        raise ValueError('Historical request bytes differ from the native attempt inventory')
    return read(path)


def qualify(bank, harness, judge, learner, source_study, employee, day, out):
    study = read(source_study / 'STUDY.json')
    if len(study['worlds']) != 1:
        raise ValueError('Specify a single-world development source')
    world = study['worlds'][0]
    if (world['specification']['study_scope'] != 'development' or day >= world['specification']['probe_start_day'] or
            world['bank_manifest_sha256'] != bank.verification['manifest_sha256']):
        raise ValueError('Only matching development-bank experiences before probes are eligible')
    root = source_study / 'worlds' / f'seed-{world["seed"]}' / 'no_learning'
    state = read(root / 'STATE.json')
    selected = eligible_experiences(state['sessions'], employee, day, 2, 2)
    if len(selected) != 4: raise ValueError('Need two released train and two released validation lineages')
    for row in selected:
        source = root / 'sessions' / row['id'] / 'ATTEMPT.json'
        if sha(source) != row['attempt_sha256'] or read(source)['grade'] != row['grade']:
            raise ValueError('Historical experience differs from its native attempt')
        request = historical_request(study, source.parent, read(source))
        if request['skill'] != SEED_SKILL or request['instruction'] != bank.public(row['task_id'])['instruction']:
            raise ValueError('Historical control must use the original brief and seed skill')
        expected = {'train': 'calibration_train', 'val': 'calibration_validation'}[row['split']]
        if bank.by_id[row['task_id']]['partition'] != expected:
            raise ValueError('Source experience split differs from the bank')
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    save(out / 'PLAN.json', {'source_sha256': source_identity(), 'source_study_sha256': sha(source_study / 'STUDY.json'),
        'source_state_sha256': sha(root / 'STATE.json'), 'source_path': str(source_study.resolve()),
        'employee': employee, 'current_day': day, 'selected': selected, 'initial_skill': SEED_SKILL,
        'harness': harness.identity(), 'judge': judge.identity(), 'learner': learner.identity(),
        'selection': 'Latest released observation per lineage at the fixed day, with two train and two validation cases; scores do not select cases.',
        'scope': 'Historical development context only. Fresh replay judgments determine consolidation. No paired-world inference.'})
    save(out / 'INFLIGHT.json', {'kind': 'native_skillopt_update', 'budget': learner.identity()['budget']})
    result = update_employee(bank, harness, judge, learner, selected, employee=employee, day=day,
                             skill=SEED_SKILL, update_root=out / 'learning')
    audit = None
    if result['status'] == 'completed':
        from .audit_worlds import audit_attempt
        from scripts.audit_transfer import gate_check
        by_id = {s['id']: s for s in selected}
        targets = [o for o in result['costs']['operations'] if o['kind'] == 'target']
        for replay in result['replay_evidence']:
            record = audit_attempt(bank, out / 'learning' / f'replay-{replay["attempt_index"]:03d}',
                                   by_id[replay['id']]['task_id'], harness=harness)
            operation = targets[replay['attempt_index']]
            if (replay['hard'] != float(record['grade']['success']) or replay['soft'] != record['grade']['quality_score'] or
                    operation['tokens'] != record['tokens'] or operation['model_calls'] != record['model_calls']):
                raise ValueError('Native replay score or cost differs from consolidation evidence')
        gate_check(result)
        audit = {'ok': True, 'replays_checked': len(result['replay_evidence']),
                 'scope': 'Native task artifacts, replay scores/costs and adoption gate; not semantic judge truth.'}
        save(out / 'AUDIT.json', audit)
    summary = {'completed': result['status'] == 'completed', 'status': result['status'],
               'accepted': result['accepted'], 'replays': len(result.get('replay_evidence', [])),
               'costs': result['costs'], 'audit': audit, 'plan_sha256': sha(out / 'PLAN.json'),
               'scope': 'Native consolidation component qualification only; no final significance claim.'}
    save(out / 'QUALIFICATION.json', summary)
    if result['status'] in ('completed', 'budget_exhausted'): (out / 'INFLIGHT.json').unlink()
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('bank', 'source-study', 'out', 'hermes-root', 'skillopt-root'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--employee', required=True)
    p.add_argument('--day', type=int, required=True)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    result = qualify(bank, Hermes(a.hermes_root, a.model, a.base_url), FrozenRubricJudge(bank, a.model, a.base_url),
                     SkillOpt(a.skillopt_root, a.model, a.base_url), a.source_study, a.employee, a.day, a.out)
    print(json.dumps({k: v for k, v in result.items() if k != 'costs'}, indent=2))
