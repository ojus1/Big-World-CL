"""Report frozen workload coverage and hypothetical learning supply, without outcomes.

Counts describe the prepared design, not independent samples or completed work.
Scheduled supply assumes every arriving task completes immediately and feedback
arrives on its scheduled day. Actual eligibility can only be established from
the execution's released, completed experiences.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.source_world_calibration import read, sha
from worldlab.bank import Bank
from worldlab.validation_context import ISOLATED, policy, validate_world
from worldlab.worlds import PARTITIONS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def coverage(slots):
    families = Counter(s['lineage_group'] for s in slots)
    return {'scheduled_slots': len(slots),
            'distinct_tasks': len({s['task_id'] for s in slots}),
            'distinct_lineages': len(families),
            'largest_lineage_obligations': max(families.values(), default=0),
            'largest_lineage_fraction': max(families.values()) / len(slots) if slots else None}


def describe(study, bank):
    worlds = study['worlds']
    seeds = [w['seed'] for w in worlds]
    require(seeds and all(type(s) is int for s in seeds) and len(seeds) == len(set(seeds)),
            'World seeds must be distinct integers')
    rows, all_slots = [], defaultdict(list)
    for world in worlds:
        require(world['bank_manifest_sha256'] == bank.verification['manifest_sha256'], 'Study bank changed')
        spec = world['specification']
        workforce = world['workforce']
        employees = {e['id']: e for e in workforce}
        require(employees and len(employees) == len(workforce), 'Duplicate or empty workforce')
        require(set(employees) == {e['id'] for e in spec['employees']}, 'Workforce differs from specification')
        schedule = world['schedule']
        require(len({s['id'] for s in schedule}) == len(schedule), 'Duplicate scheduled obligation')
        require(type(spec['days']) is int and type(spec['probe_start_day']) is int
                and 0 < spec['probe_start_day'] < spec['days'], 'Invalid study horizon')
        updates = spec.get('update_days', [])
        require(all(type(d) is int and 0 < d < spec['probe_start_day'] for d in updates)
                and len(updates) == len(set(updates)), 'Invalid learning days')
        validate_world(bank, world)
        for slot in schedule:
            require(slot['employee_id'] in employees and slot['split'] in PARTITIONS, 'Unknown employee or split')
            source = bank.by_id.get(slot['task_id'])
            require(source is not None and source['calibration_group'] == slot['lineage_group']
                    and source['partition'] == PARTITIONS[slot['split']], 'Source task lineage or partition changed')
            require(type(slot['day']) is int and 0 <= slot['day'] < spec['days']
                    and type(slot['feedback_day']) is int and slot['feedback_day'] > slot['day'],
                    'Invalid work or feedback day')
            require((slot['day'] >= spec['probe_start_day']) == (slot['split'] == 'probe'),
                    'Probe work lies outside its declared phase')
            all_slots[slot['split']].append(slot)
        for employee in workforce:
            slots = [s for s in schedule if s['employee_id'] == employee['id']]
            groups = {split: {s['lineage_group'] for s in slots if s['split'] == split} for split in PARTITIONS}
            isolated = policy(spec) == ISOLATED
            gates = world['validation_cases'][employee['id']] if isolated else [s for s in slots if s['split'] == 'val']
            if isolated:
                all_slots['isolated_gate'].extend(gates)
            gate_groups = {s['lineage_group'] for s in gates}
            require(not (groups['train'] & groups['probe'] or gate_groups & (groups['train'] | groups['probe'])),
                    'Training, gate and probe lineages overlap')
            supply = []
            for day in updates:
                training = {s['lineage_group'] for s in slots if s['split'] == 'train' and s['feedback_day'] <= day}
                validation = {s['lineage_group'] for s in gates if s['feedback_day'] <= day}
                supply.append({'day': day, 'scheduled_training_lineages': len(training),
                               'scheduled_gate_lineages': len(validation),
                               'hypothetical_supply_sufficient': len(training) >= spec.get('train_cases', 2)
                                   and len(validation) >= spec.get('val_cases', 2)})
            rows.append({'seed': world['seed'], 'employee_id': employee['id'],
                'role': employee['role'], 'language': employee['language'],
                'calibration_status': employee['calibration']['calibration_status'],
                'coverage': {split: coverage([s for s in slots if s['split'] == split]) for split in PARTITIONS},
                'validation_context': policy(spec), 'distinct_gate_lineages': len(gate_groups),
                'scheduled_learning_supply': supply})
    return {'world_pairs': len(worlds), 'employee_world_instances': len(rows),
        'planned_arriving_obligations_per_arm_across_worlds': sum(len(all_slots[k]) for k in PARTITIONS),
        'planned_isolated_gate_descriptors_across_worlds': len(all_slots['isolated_gate']),
        'calibration_status_counts_across_world_instances': dict(Counter(r['calibration_status'] for r in rows)),
        'language_counts_across_world_instances': dict(Counter(r['language'] for r in rows)),
        'coverage_per_arm_across_prepared_worlds': {k: coverage(v) for k, v in sorted(all_slots.items())},
        'scheduled_learner_updates': sum(len(r['scheduled_learning_supply']) for r in rows),
        'updates_with_sufficient_hypothetical_supply': sum(s['hypothetical_supply_sufficient'] for r in rows for s in r['scheduled_learning_supply']),
        'employee_world_instances_with_one_probe_lineage': sum(r['coverage']['probe']['distinct_lineages'] == 1 for r in rows),
        'employee_world_instances_without_probes': sum(r['coverage']['probe']['scheduled_slots'] == 0 for r in rows),
        'rows': rows,
        'interpretation': {'counting': 'Each prepared world is counted once, before duplicating it into matched arms. Isolated gate counts are task descriptors, not arriving obligations or model calls.',
            'independence': 'Repeated tasks, translations, employees, gate cases and simulated days are not extra independent world pairs.',
            'supply': __doc__,
            'coverage': 'A single probe lineage limits transfer coverage. Metadata separation does not prove semantic independence, grading accuracy or absence of historical exposure.'},
        'execution_inspected': False, 'actual_update_eligibility_established': False,
        'confirmatory_readiness_established': False, 'model_calls': 0}


def snapshot(study_root, bank):
    root = Path(study_root).resolve()
    require(not (root / 'STUDY.json').is_symlink(), 'Study manifest cannot be a symlink')
    before = sha(root / 'STUDY.json')
    require(before == read(root / 'PREPARED.json')['study_sha256'], 'Prepared study bytes changed')
    report = describe(read(root / 'STUDY.json'), bank)
    require(sha(root / 'STUDY.json') == before, 'Study changed during observation')
    return {'observed_at': datetime.now(timezone.utc).isoformat(), 'study_root': str(root),
            'study_sha256': before, 'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'reporter_sha256': sha(__file__), **report}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study', type=Path, required=True)
    p.add_argument('--bank', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(snapshot(args.study, Bank(args.bank)), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
