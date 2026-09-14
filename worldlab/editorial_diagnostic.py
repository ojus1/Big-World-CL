"""Read-only working-day arithmetic audit of the pinned editorial training task.

This does not replace historical grades or certify the complete scheduling task.
Candidate dates are checked for arithmetic consistency; choosing the dates,
translator assignments and narrative risk judgments requires separate coverage.
"""
import argparse
from collections import Counter
import csv
from datetime import date
import json
from pathlib import Path

from scripts.source_world_calibration import read, save, sha
from .bank import Bank
from .campaign import source_identity
from .mechanical_diagnostic import snapshot, verified_attempt
from .public_requirements import evaluate as public_checks, table, number, verdict, REGISTRY

TASK = 'internal/euw_v1_fr_014'
OUTPUT = 'output/planning_scenarios.csv'
HOLIDAYS = tuple(date.fromisoformat(s) for s in ('2025-01-01', '2025-04-18', '2025-05-01', '2025-05-08', '2025-07-14'))
BOUNDARIES = [
    ('saturday-is-working', '2025-01-11', '2025-01-11', 1),
    ('sunday-excluded', '2025-01-12', '2025-01-12', 0),
    ('whole-week', '2025-01-06', '2025-01-12', 6),
    ('holiday-start-and-sunday-end', '2025-04-18', '2025-04-20', 1),
    ('listed-holiday-only', '2025-05-01', '2025-05-01', 0),
    ('strictly-below-threshold', '2025-01-06', '2025-01-15', 9),
    ('exact-threshold', '2025-01-06', '2025-01-16', 10),
    ('negative-window-remains-negative', '2025-01-20', '2025-01-13', -6),
]


def working_days(start, end):
    """Task-stipulated inclusive calendar subtraction, not a Mon-Fri calendar."""
    span = (end - start).days + 1
    first_sunday = (6 - start.weekday()) % 7
    sundays = 0 if span <= first_sunday else 1 + (span - first_sunday - 1) // 7
    holidays = sum(start <= holiday <= end for holiday in HOLIDAYS)
    return span - sundays - holidays


def boundary_controls():
    rows = [{'id': name, 'start': start, 'end': end, 'expected': expected,
             'actual': working_days(date.fromisoformat(start), date.fromisoformat(end))}
            for name, start, end, expected in BOUNDARIES]
    return {'ok': all(r['expected'] == r['actual'] for r in rows), 'cases': rows,
            'model_calls': 0, 'scope': 'Hand-checked arithmetic boundaries only; not complete-task positive answers.'}


def arithmetic_checks(text):
    days, threshold, comparisons = [], [], []
    try:
        rows = table(text)
        if not rows: raise ValueError('No planning rows')
        for row in rows:
            key = (row['scenario'], row['titre'], row['langue'])
            start, end = date.fromisoformat(row['date_livraison_manuscrit']), date.fromisoformat(row['date_relecture'])
            expected = working_days(start, end)
            reported = number(row['fenetre_jours_ouvrables'])
            flag = 'oui' if expected < 10 else 'non'
            if reported != expected:
                days.append(f'{key}: reported {reported}, expected {expected}; exclude Sundays and the five stipulated holidays only.')
            if row['sous_seuil_10j'] != flag:
                threshold.append(f'{key}: expected {flag} for {expected} working days and strict <10 threshold.')
            comparisons.append({'key': list(key), 'expected_working_days': expected,
                                'reported_working_days': str(reported), 'expected_under_threshold': flag,
                                'reported_under_threshold': row['sous_seuil_10j']})
    except (KeyError, ValueError, ArithmeticError, csv.Error) as exc:
        # Malformed rows remain failures rather than shrinking the checked set.
        message = type(exc).__name__ + ': missing or invalid required planning field.'
        days.append(message); threshold.append(message)
    return {'checks': [verdict('editorial_working_days', days, 'Inclusive calendar days minus Sundays and the five source-listed 2025 holidays.'),
                       verdict('editorial_under_threshold', threshold, 'sous_seuil_10j is oui exactly when the recomputed working-day window is <10.')],
            'row_comparisons': comparisons}


def inspect_slot(bank, slot):
    path = Path(slot['path'])
    if sha(path) != slot['sha256']:
        raise ValueError('Attempt changed after diagnostic preparation')
    record, workspace, _ = verified_attempt(bank, path)
    if record['task_id'] != TASK or slot['task_id'] != TASK:
        raise ValueError('Only the pinned editorial task is supported')
    output = workspace / OUTPUT
    texts = {OUTPUT: {'text': output.read_text()}} if output.is_file() else {}
    # Existing registration binds the exact public instruction and all six
    # inputs before the additional task-specific calendar is applied.
    existing = public_checks(bank, TASK, texts)
    if not existing['registered'] or existing['checker'] != 'editorial_calendar_v1':
        raise ValueError('Missing source-bound editorial registration')
    result = arithmetic_checks(texts.get(OUTPUT, {}).get('text', ''))
    verified_attempt(bank, path)
    return {**slot, **result, 'existing_public_checks': existing['checks'],
            'source_inputs': existing['source_inputs'], 'whole_task_validity': None}


def summarize(rows):
    failures = [r for r in rows if any(not c['passed'] for c in r['checks'])]
    return {'attempts': len(rows), 'arithmetic_failures': len(failures),
            'historically_successful_with_arithmetic_failure': sum(r['qualitative_success'] is True for r in failures),
            'failed_check_counts': dict(Counter(c['id'] for r in failures for c in r['checks'] if not c['passed'])),
            'row_comparisons': sum(len(r['row_comparisons']) for r in rows),
            'model_calls': 0, 'historical_grades_changed': False, 'distinct_task_families': 1,
            'scope': __doc__ + ' Repeated development attempts are dependent; no general accuracy or learning-effect estimate.'}


def diagnose(bank, root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or root == out or root in out.parents:
        raise ValueError('Use a fresh diagnostic directory outside the source arm')
    if read(root / 'REPORT.json')['status'] != 'completed' or (root / 'INFLIGHT.json').exists():
        raise ValueError('Source arm must be complete')
    if bank.by_id[TASK]['partition'] != 'calibration_train':
        raise ValueError('Only the original calibration-training task is authorized')
    slots = [slot for slot in snapshot(bank, [root / 'sessions']) if slot['task_id'] == TASK]
    if not slots: raise ValueError('No completed editorial attempts in the source arm')
    controls = boundary_controls()
    if not controls['ok']: raise ValueError('Calendar boundary controls failed')
    out.mkdir(parents=True)
    save(out / 'CONTROLS.json', controls)
    save(out / 'PLAN.json', {'source_sha256': source_identity(), 'bank_manifest_sha256': bank.verification['manifest_sha256'],
        'registry_sha256': sha(REGISTRY), 'source_arm': str(root), 'source_report_sha256': sha(root / 'REPORT.json'),
        'slots': slots, 'controls_sha256': sha(out / 'CONTROLS.json'),
        'selection': 'All completed attempts for the single pinned training task in the named completed arm, irrespective of historical outcome.',
        'scope': __doc__})
    rows = [inspect_slot(bank, slot) for slot in slots]
    save(out / 'RESULTS.json', rows)
    report = {**summarize(rows), 'plan_sha256': sha(out / 'PLAN.json')}
    save(out / 'REPORT.json', report)
    return report


def audit(bank, out):
    out = Path(out)
    plan = read(out / 'PLAN.json')
    if (plan['source_sha256'] != source_identity() or plan['bank_manifest_sha256'] != bank.verification['manifest_sha256'] or
            plan['registry_sha256'] != sha(REGISTRY) or plan['controls_sha256'] != sha(out / 'CONTROLS.json') or
            read(out / 'CONTROLS.json') != boundary_controls() or
            sha(Path(plan['source_arm']) / 'REPORT.json') != plan['source_report_sha256']):
        raise ValueError('Diagnostic source, controls, bank or completed arm changed')
    selected = [slot for slot in snapshot(bank, [Path(plan['source_arm']) / 'sessions']) if slot['task_id'] == TASK]
    if selected != plan['slots']:
        raise ValueError('Diagnostic no longer covers every selected source attempt')
    rows = [inspect_slot(bank, slot) for slot in plan['slots']]
    if rows != read(out / 'RESULTS.json') or read(out / 'REPORT.json') != {**summarize(rows), 'plan_sha256': sha(out / 'PLAN.json')}:
        raise ValueError('Diagnostic does not reproduce from original source artifacts')
    return {'ok': True, 'attempts': len(rows), 'model_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('run', 'audit'))
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    b = Bank(a.bank)
    if a.command == 'run' and a.root is None: p.error('run requires --root')
    result = diagnose(b, a.root, a.out) if a.command == 'run' else audit(b, a.out)
    print(json.dumps(result, indent=2))
