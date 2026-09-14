"""Prospective gate tasks that never become live employee work or feedback."""
from copy import deepcopy
from dataclasses import asdict
import random
from .contracts import Budget

ISOLATED = 'isolated_public_tasks_v1'
HISTORY = 'workplace_history'
CASE_KEYS = {'id', 'employee_id', 'task_id', 'split', 'lineage_group', 'day',
             'feedback_day', 'work_budget', 'context_source'}


def policy(spec):
    value = spec.get('validation_context', HISTORY)
    if value not in (HISTORY, ISOLATED):
        raise ValueError('Unknown validation_context')
    return value


def compile_cases(rows, employee, seed, budget, count):
    """Select distinct validation families before outcomes with an independent RNG."""
    from .worlds import stable_hash
    if type(count) is not int or count < 1:
        raise ValueError('Isolated validation needs a positive val_cases count')
    groups = {}
    for row in sorted(rows, key=lambda r: r['id']):
        groups.setdefault(row['calibration_group'], []).append(row)
    if len(groups) < count:
        raise ValueError('Employee lacks enough distinct isolated validation families: ' + employee)
    rng = random.Random(stable_hash([seed, employee, ISOLATED]))
    families = rng.sample(sorted(groups), count)
    return [{'id': f'gate-{employee}-{i:03d}', 'employee_id': employee,
             'task_id': rng.choice(groups[family])['id'],
             'split': 'val', 'lineage_group': family, 'day': 0, 'feedback_day': 0,
             'work_budget': deepcopy(budget), 'context_source': ISOLATED}
            for i, family in enumerate(families)]


def validate_world(bank, world):
    """Check bank lineage and reject outcome/context fields in gate descriptors."""
    if policy(world['specification']) != ISOLATED:
        if 'validation_cases' in world:
            raise ValueError('Validation catalog requires isolated validation_context')
        return
    spec = world['specification']
    if any(type(spec.get(k, 2)) is not int or spec.get(k, 2) < 1 for k in ('train_cases', 'val_cases')):
        raise ValueError('Isolated learning needs positive train_cases and val_cases')
    catalog = world.get('validation_cases')
    if not isinstance(catalog, dict) or set(catalog) != {e['id'] for e in world['workforce']}:
        raise ValueError('Isolated validation catalog differs from workforce')
    # A split label on a slot cannot override the original bank partition.
    partition_by_family = {}
    for row in bank.rows:
        previous = partition_by_family.setdefault(row['calibration_group'], row['partition'])
        if previous != row['partition']:
            raise ValueError('Bank family crosses partitions')
    live_groups = set()
    for slot in world['schedule']:
        expected = {'train': 'calibration_train', 'probe': 'calibration_holdout'}.get(slot['split'])
        row = bank.by_id[slot['task_id']]
        if expected is None or row['partition'] != expected or row['calibration_group'] != slot['lineage_group']:
            raise ValueError('Live workplace includes validation or mislabeled source work')
        live_groups.add(slot['lineage_group'])
    expected_budget = asdict(Budget(**spec.get('work_budget', {})))
    for employee in world['workforce']:
        rows = catalog[employee['id']]
        if not isinstance(rows, list) or len(rows) != spec.get('val_cases', 2):
            raise ValueError('Isolated validation case count changed')
        families = set()
        for i, case in enumerate(rows):
            if set(case) != CASE_KEYS:
                raise ValueError('Isolated gate descriptor includes unexpected context or outcome')
            row = bank.by_id[case['task_id']]
            selector = employee.get('task_selector', {})
            if (case['id'] != f'gate-{employee["id"]}-{i:03d}' or case['employee_id'] != employee['id'] or
                    case['split'] != 'val' or case['context_source'] != ISOLATED or
                    type(case['day']) is not int or type(case['feedback_day']) is not int or
                    case['day'] != 0 or case['feedback_day'] != 0 or case['work_budget'] != expected_budget or
                    row['partition'] != 'calibration_validation' or row['language'] != employee['language'] or
                    row['calibration_group'] != case['lineage_group'] or
                    case['lineage_group'] in live_groups | families or
                    any(row[field] not in selector[key] for key, field in
                        [('sources', 'source'), ('workflows', 'workflow')] if key in selector)):
                raise ValueError('Isolated gate differs from public validation partition or employee role')
            families.add(case['lineage_group'])


def select_experiences(world, sessions, employee, day):
    from .worlds import eligible_experiences
    spec = world['specification']
    if policy(spec) == HISTORY:
        return eligible_experiences(sessions, employee, day, spec.get('train_cases', 2), spec.get('val_cases', 2))
    if any(s['split'] == 'val' for s in sessions):
        raise ValueError('Isolated validation cannot use workplace validation history')
    train = eligible_experiences([s for s in sessions if s['split'] == 'train'], employee, day,
                                 spec.get('train_cases', 2), 0)
    if not train:
        return []
    cases = deepcopy(world['validation_cases'][employee])
    return sorted(train + cases, key=lambda s: (s['day'], s['id']))


def employee_world(world):
    """Employee adapters do not receive the evaluator's gate task catalog."""
    if policy(world['specification']) != ISOLATED:
        return world
    return deepcopy({key: value for key, value in world.items()
                     if key not in ('validation_cases', 'capability_exclusions')})


def observed_feedback(case):
    if case.get('context_source') == ISOLATED:
        if set(case) != CASE_KEYS or case['split'] != 'val':
            raise ValueError('Prepared gate tasks cannot carry employee context or observed grades')
        # Day zero denotes public task availability, not a fabricated observation.
        return ''
    return case['grade']['feedback']
