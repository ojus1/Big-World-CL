"""Source-bound arithmetic/structure checks supplementing frozen r3 judgments.

This registry closes reviewed omissions; it is not a certificate that every
public requirement of every task has an executable predicate. It never imports
the benchmark's potentially overstrict gold strings as new public obligations.
"""
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import io
from pathlib import Path

from scripts.source_world_calibration import child, read, sha

REGISTRY = Path(__file__).with_name('public_requirements_registry.json')
EDITORIAL_IDS = ['public_editorial_rows', 'public_editorial_calendar_days', 'public_editorial_fixed_dates',
                 'public_editorial_compression', 'public_editorial_fr_publication']
MRI_IDS = ['public_mri_rows', 'public_mri_source_scores', 'public_mri_weighted_scores', 'public_mri_exclusions']


def table(text, columns=None):
    reader = csv.DictReader(io.StringIO(text))
    if columns is not None and reader.fieldnames != columns:
        raise ValueError('CSV header differs from the public column order')
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('CSV row has missing or extra fields')
    return rows


def number(value):
    result = Decimal(value)
    if not result.is_finite(): raise ValueError('Nonfinite number')
    return result


def verdict(name, issues, requirement):
    return {'id': name, 'weight': 1, 'passed': not issues, 'requirement': requirement,
            'evidence': issues[:20], 'failure_count': len(issues)}


def editorial(inputs, outputs):
    path = 'output/planning_scenarios.csv'
    requirement = 'Public CSV shape, original fixed dates, +14-day compression and inclusive calendar subtraction.'
    columns = 'scenario titre langue date_livraison_manuscrit date_relecture fenetre_jours_calendaires fenetre_jours_ouvrables sous_seuil_10j date_parution statut'.split()
    try:
        rows = table(outputs.get(path, ''), columns)
        agenda = {(r['titre'], r['langue']): r for r in table(inputs['input/agenda_editorial_v3.csv'])}
        expected = {(scenario, *key) for scenario in ('dates_fixes', 'compression', 'glissement') for key in agenda}
        keys = [(r['scenario'], r['titre'], r['langue']) for r in rows]
        issues = [] if len(keys) == len(expected) and set(keys) == expected and keys == sorted(keys) else [
            'Need exactly the 36 distinct scenario/title/language rows, in the declared order.']
        shape = verdict('public_editorial_rows', issues, '36 distinct rows, exact columns and scenario/title/language ordering.')
        calendar, fixed, compression, source_language = [], [], [], []
        for row in rows:
            key = (row['scenario'], row['titre'], row['langue'])
            original = agenda.get((row['titre'], row['langue']))
            if original is None: continue
            start, end = date.fromisoformat(row['date_livraison_manuscrit']), date.fromisoformat(row['date_relecture'])
            if number(row['fenetre_jours_calendaires']) != (end - start).days + 1:
                calendar.append(f'{key}: calendar days must equal inclusive date subtraction, including negative intervals.')
            if row['scenario'] == 'dates_fixes' and any(row[k] != original[k] for k in
                    ('date_livraison_manuscrit', 'date_relecture', 'date_parution')):
                fixed.append(f'{key}: fixed dates differ from the signed agenda.')
            if row['scenario'] == 'compression' and (
                    start != date.fromisoformat(original['date_livraison_manuscrit']) + timedelta(days=14) or
                    any(row[k] != original[k] for k in ('date_relecture', 'date_parution'))):
                compression.append(f'{key}: compression changes delivery by exactly 14 days, preserving review/publication.')
            if row['scenario'] == 'glissement' and row['langue'] == 'FR' and row['date_parution'] != original['date_parution']:
                source_language.append(f'{key}: source-language publication cannot slide.')
        return [shape,
            verdict('public_editorial_calendar_days', calendar, 'Calendar days = review date minus delivery date plus one, without zero-clamping.'),
            verdict('public_editorial_fixed_dates', fixed, 'The signed agenda determines all dates_fixes dates.'),
            verdict('public_editorial_compression', compression, 'Compression adds 14 days to delivery only.'),
            verdict('public_editorial_fr_publication', source_language, 'Publication sliding never applies to FR.')]
    except (KeyError, ValueError, InvalidOperation, csv.Error) as exc:
        return [verdict(name, [type(exc).__name__ + ': invalid or missing required CSV/date/number.'], requirement)
                for name in EDITORIAL_IDS]


def procurement(inputs, outputs, excluded_marker='EXCLUDED'):
    columns = 'criterio peso_pct punt_a punt_b punt_c ponderado_a ponderado_b ponderado_c'.split()
    try:
        rows = table(outputs.get('output/tabla_puntuacion.csv', ''), columns)
        total = [r for r in rows if r['criterio'].strip() == 'TOTAL']
        partial = [r for r in rows if r['criterio'].strip() != 'TOTAL']
        weights = [number(r['peso_pct']) for r in partial]
        shape = [] if len(rows) == 6 and len(total) == 1 and rows[-1] is total[0] and sorted(weights) == [10, 15, 20, 25, 30] else [
            'Need five distinct policy weights and one final TOTAL row with the public columns.']
        if shape: return [verdict(name, shape, 'Five criteria at weights 30/25/20/15/10 plus final TOTAL.') for name in MRI_IDS]
        by_weight = {number(r['peso_pct']): r for r in partial}
        # These fixed source facts are reviewed against the pinned technical CSV,
        # supplier proposal and PACS report; the TCO arithmetic is recomputed.
        costs = table(inputs['input/informe_coste_propiedad.csv'])
        tco = {provider: sum(number(r[f'prov_{provider}_{kind}']) for r in costs
                            for kind in ('manten', 'consum', 'energia')) for provider in 'abc'}
        price_a = (10 * min(tco.values()) / tco['a']).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        expected = {Decimal(30): Decimal(10), Decimal(25): price_a, Decimal(20): Decimal(10),
                    Decimal(15): Decimal(6), Decimal(10): Decimal(10)}
        scores, weighted, exclusions = [], [], []
        for weight, row in by_weight.items():
            if number(row['punt_a']) != expected[weight]:
                scores.append(f'Weight {weight}: supplier A partial score differs from the public source rules.')
            if number(row['ponderado_a']) != (expected[weight] * weight / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):
                weighted.append(f'Weight {weight}: supplier A weighted score differs from rounded policy arithmetic.')
            if any(row[f'punt_{provider}'] != excluded_marker for provider in 'bc'):
                exclusions.append(f'Weight {weight}: B and C require the public {excluded_marker} marker.')
            # Only excluded TOTALs must be numeric zero. Intermediate weighted
            # cells may be blank, marked excluded, zero or informational scores.
        expected_total = sum((v * w / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for w, v in expected.items())
        if number(total[0]['ponderado_a']) != expected_total:
            weighted.append('Supplier A TOTAL differs from source-derived rounded partials.')
        if any(number(total[0][f'ponderado_{provider}']) != 0 for provider in 'bc'):
            exclusions.append('Excluded suppliers must have zero weighted TOTAL.')
        return [verdict('public_mri_rows', [], 'Five policy criteria and final TOTAL.'),
            verdict('public_mri_source_scores', scores, 'A scores: technical/reliability/warranty 10, pending PACS 6; price from seven-year CSV sums.'),
            verdict('public_mri_weighted_scores', weighted, 'Rounded partial × weight / 100; total is sum of rounded weighted scores.'),
            verdict('public_mri_exclusions', exclusions, f'B noise and C warranty/PACS exclude them; {excluded_marker} markers and zero TOTALs are required.')]
    except (KeyError, ValueError, InvalidOperation, csv.Error) as exc:
        return [verdict(name, [type(exc).__name__ + ': invalid or missing required CSV/number.'],
                        'Public scoring CSV and finite policy arithmetic.') for name in MRI_IDS]


CHECKERS = {'editorial_calendar_v1': editorial, 'mri_scoring_v1': procurement}


def evaluate(bank, task_id, files):
    from .supplier_notes import matrix_status_check
    registry = read(REGISTRY)
    registration = registry['tasks'].get(task_id)
    report = {'registry_sha256': sha(REGISTRY), 'source_sha256': sha(Path(__file__)),
              'registered': registration is not None, 'checks': [],
              'scope': 'Reviewed supplemental public requirements only; other obligations still need coverage review.'}
    supplier = matrix_status_check(bank, task_id, files)
    if supplier is not None:
        report.update(registered=True, checker='supplier_public_status_rules_v1', checks=[supplier])
    if registration is None: return report
    row = bank.by_id[task_id]
    public = child(bank.root, row['public_directory'])
    if sha(public / 'task.json') != registration['public_descriptor_sha256']:
        raise ValueError('Registered public task contract changed')
    inputs = {}
    for name, expected in registration['input_sha256'].items():
        source = child(public, name)
        if sha(source) != expected: raise ValueError('Registered public source input changed')
        inputs[name] = source.read_text()
    report.update(checker=registration['checker'], source_inputs=registration['input_sha256'],
                  checks=CHECKERS[registration['checker']](inputs, {k: v['text'] for k, v in files.items()}))
    return report


def aggregate(criteria, verdicts, supplement):
    checks = supplement['checks']
    weight = sum(c['weight'] for c in criteria) + sum(c['weight'] for c in checks)
    points = sum(c['weight'] * v['passed'] for c, v in zip(criteria, verdicts)) + sum(c['weight'] * c['passed'] for c in checks)
    return points / weight, all(v['passed'] for v in verdicts) and all(c['passed'] for c in checks)
