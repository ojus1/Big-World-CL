"""Run original mechanical checks on a frozen snapshot of existing attempts.

No model or learner runs. Source artifacts and historical grades stay unchanged.
Agreement is a diagnostic: neither evaluator is assumed to be ground truth.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from scripts.source_world_calibration import read, save, sha, child
from .attempts import task_instruction
from .bank import Bank
from .campaign import source_identity
from .grading import EuroBenchMechanical


def verified_attempt(bank, path):
    path = Path(path).resolve()
    root = path.parent
    record = read(path)
    inventory = record['artifact_inventory']
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'ATTEMPT.json'}
    if actual != set(inventory) or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Attempt inventory differs from its completion receipt')
    for name, digest in inventory.items():
        if sha(child(root, name)) != digest:
            raise ValueError('Attempt artifact changed: ' + name)
    row = bank.by_id[record['task_id']]
    request_name = 'PUBLIC_REQUEST.json' if 'PUBLIC_REQUEST.json' in inventory else 'REQUEST.json'
    request = read(root / request_name)
    message = None
    if 'EMPLOYEE_REQUEST.json' in inventory:
        delegation = read(root / 'EMPLOYEE_REQUEST.json')
        if delegation['original_instruction'] != bank.public(record['task_id'])['instruction']:
            raise ValueError('Delegated original instruction changed')
        message = delegation['message']
    if request['instruction'] != task_instruction(bank.public(record['task_id'])['instruction'], message):
        raise ValueError('Attempt did not receive the original public task')
    if request['employee_id'] != record['employee_id']:
        raise ValueError('Employee identity differs between request and attempt')
    workspace = child(root, record['employee_id'] + '/workspace')
    prefix = row['public_directory'] + '/'
    expected = {name[len(prefix):]: value['sha256'] for name, value in bank.inventory.items()
                if name.startswith(prefix) and name[len(prefix):] != 'task.json'}
    expected['.employee_identity'] = hashlib.sha256((record['employee_id'] + '\n').encode()).hexdigest()
    if read(root / 'BASELINE.json') != expected:
        raise ValueError('Attempt baseline differs from original source bytes')
    return record, workspace, expected


def snapshot(bank, roots):
    paths = sorted({p.resolve() for root in roots for p in Path(root).rglob('ATTEMPT.json')})
    if not paths:
        raise ValueError('No completed attempt receipts found')
    rows = []
    for path in paths:
        record, _, _ = verified_attempt(bank, path)
        grade = record.get('grade') or {}
        rows.append({'id': f'attempt-{len(rows):04d}', 'path': str(path), 'sha256': sha(path),
                     'task_id': record['task_id'], 'status': record['status'],
                     'qualitative_success': grade.get('success') if grade.get('grading_complete') else None,
                     'lineage_group': bank.by_id[record['task_id']]['calibration_group']})
    return rows


def inspect_slot(bank, grader, slot):
    path = Path(slot['path'])
    if sha(path) != slot['sha256']:
        raise ValueError('Source attempt changed after diagnostic preparation')
    record, workspace, baseline = verified_attempt(bank, path)
    if record['task_id'] != slot['task_id']:
        raise ValueError('Task binding changed')
    definition = bank.private_definition(slot['task_id'])
    unsupported = grader.unsupported(definition)
    if unsupported:
        return {**slot, 'status': 'unsupported', 'reasons': unsupported, 'mechanical': None}
    result = grader.grade(definition, workspace, baseline)
    # The supported original checks must be read-only, including on failure.
    verified_attempt(bank, path)
    return {**slot, 'mechanical': result}


def summarize(rows):
    pairs = [(row['qualitative_success'], row['mechanical']['mechanical_success']) for row in rows
             if row['qualitative_success'] is not None and row['mechanical'] and row['mechanical']['grading_complete']]
    return {'attempts': len(rows), 'mechanically_observable': sum(bool(r['mechanical'] and r['mechanical']['grading_complete']) for r in rows),
            'comparable_attempts': len(pairs),
            'agreement_table': {f'qualitative_{q}_mechanical_{m}': pairs.count((q, m)) for q in (False, True) for m in (False, True)},
            'distinct_lineage_groups': len({r['lineage_group'] for r in rows}),
            'failed_check_counts': dict(Counter(c['id'] for r in rows if r['mechanical'] for c in r['mechanical']['checks'] if not c['pass'])),
            'model_calls': 0, 'historical_grades_changed': False,
            'scope': 'Read-only agreement diagnostic. Repeats and translated families are dependent. Mechanical failures need source review; this is not judge-accuracy or learning-effect evidence.'}


def diagnose(bank, grader, roots, out):
    out = Path(out).resolve()
    roots = [Path(root).resolve() for root in roots]
    if out.exists() or any(out == root or root in out.parents for root in roots):
        raise ValueError('Use a fresh diagnostic destination outside every source artifact root')
    slots = snapshot(bank, roots)
    out.mkdir(parents=True)
    save(out / 'PLAN.json', {'bank_manifest_sha256': bank.verification['manifest_sha256'],
                           'grader': grader.identity(), 'source_sha256': source_identity(), 'slots': slots,
                           'selection': 'Every available ATTEMPT.json in the specified roots at preparation time, independent of scores.'})
    rows = []
    for slot in slots:
        rows.append(inspect_slot(bank, grader, slot))
        save(out / 'RESULTS.json', rows)
    report = {**summarize(rows), 'plan_sha256': sha(out / 'PLAN.json')}
    save(out / 'REPORT.json', report)
    return report


def audit(bank, grader, out):
    out = Path(out)
    plan, rows = read(out / 'PLAN.json'), read(out / 'RESULTS.json')
    if plan['bank_manifest_sha256'] != bank.verification['manifest_sha256'] or plan['grader'] != grader.identity():
        raise ValueError('Bank or mechanical evaluator changed')
    if plan['source_sha256'] != source_identity():
        raise ValueError('Use the frozen diagnostic source checkout')
    replayed = [inspect_slot(bank, grader, slot) for slot in plan['slots']]
    if replayed != rows or read(out / 'REPORT.json') != {**summarize(replayed), 'plan_sha256': sha(out / 'PLAN.json')}:
        raise ValueError('Diagnostic differs from original regrading')
    return {'ok': True, 'attempts_regraded': len(rows), 'model_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['run', 'audit'])
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--eurobench-root', type=Path, required=True)
    p.add_argument('--roots', type=Path, nargs='+')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    bank, grader = Bank(a.bank), EuroBenchMechanical(a.eurobench_root)
    result = diagnose(bank, grader, a.roots or [], a.out) if a.command == 'run' else audit(bank, grader, a.out)
    print(json.dumps(result, indent=2))
