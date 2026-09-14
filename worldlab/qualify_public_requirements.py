"""Frozen source-grounded component controls; zero model calls or solver results."""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import csv
import io
import json
from pathlib import Path

from scripts.source_world_calibration import child, read, save, sha
from .bank import Bank
from .campaign import source_identity
from .public_requirements import evaluate, aggregate, table, REGISTRY, EDITORIAL_IDS, MRI_IDS


def csv_text(rows):
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


def controls(bank):
    cases = []
    def add(name, task, path, rows, failed):
        cases.append({'id': name, 'task_id': task, 'outputs': {path: csv_text(rows)}, 'expected_failed': failed})

    task = 'internal/euw_v1_fr_014'; path = 'output/planning_scenarios.csv'
    directory = child(bank.root, bank.by_id[task]['public_directory'])
    agenda = table((directory / 'input/agenda_editorial_v3.csv').read_text())
    rows = []
    for scenario in ('compression', 'dates_fixes', 'glissement'):
        for source in sorted(agenda, key=lambda r: (r['titre'], r['langue'])):
            start = date.fromisoformat(source['date_livraison_manuscrit']) + timedelta(days=0 if scenario == 'dates_fixes' else 14)
            end = date.fromisoformat(source['date_relecture'])
            days = (end - start).days + 1
            rows.append({'scenario': scenario, 'titre': source['titre'], 'langue': source['langue'],
                'date_livraison_manuscrit': start.isoformat(), 'date_relecture': end.isoformat(),
                'fenetre_jours_calendaires': str(days), 'fenetre_jours_ouvrables': '0',
                'sous_seuil_10j': 'oui', 'date_parution': source['date_parution'], 'statut': 'OK'})
    # Other fields deliberately do not purport to solve the complete task.
    add('editorial-component-positive', task, path, rows, [])
    wrong = deepcopy(rows)
    target = next(r for r in wrong if (r['scenario'], r['titre'], r['langue']) == ('compression', 'Les Rives du Silence', 'FR'))
    assert target['fenetre_jours_calendaires'] == '-6'
    target['fenetre_jours_calendaires'] = '0'
    add('negative-calendar-clamped', task, path, wrong, ['public_editorial_calendar_days'])
    wrong = deepcopy(rows); wrong[0]['date_livraison_manuscrit'] = '2025-01-26'; wrong[0]['fenetre_jours_calendaires'] = '28'
    add('negative-compression-thirteen-days', task, path, wrong, ['public_editorial_compression'])
    wrong = deepcopy(rows)
    target = next(r for r in wrong if r['scenario'] == 'glissement' and r['langue'] == 'FR')
    target['date_parution'] = '2025-02-24'
    add('negative-source-language-sliding', task, path, wrong, ['public_editorial_fr_publication'])
    add('negative-editorial-missing-row', task, path, rows[:-1], ['public_editorial_rows'])
    wrong = deepcopy(rows); wrong[0]['fenetre_jours_calendaires'] = 'NaN'
    add('negative-editorial-nonfinite', task, path, wrong, EDITORIAL_IDS)
    cases.append({'id': 'negative-editorial-missing-output', 'task_id': task, 'outputs': {}, 'expected_failed': EDITORIAL_IDS})

    task = 'internal/euw_v1_es_017_en_bridge'; path = 'output/tabla_puntuacion.csv'
    rows = []
    # Independent source review: A satisfies all technical minima, has no
    # contradiction, 5-year warranty and pending PACS. CSV TCO makes price 9.2.
    for criterion, weight, score, weighted in [('Technical', 30, '10.0', '3.00'),
        ('Price / TCO', 25, '9.2', '2.30'), ('Reliability', 20, '10.0', '2.00'),
        ('PACS Integration', 15, '6.0', '0.90'), ('Warranty / Support', 10, '10.0', '1.00')]:
        rows.append({'criterio': criterion, 'peso_pct': str(weight), 'punt_a': score,
            'punt_b': 'EXCLUDED', 'punt_c': 'EXCLUDED', 'ponderado_a': weighted,
            'ponderado_b': '0.00', 'ponderado_c': '0.00'})
    rows.append({'criterio': 'TOTAL', 'peso_pct': '100', 'punt_a': '', 'punt_b': 'EXCLUDED',
                 'punt_c': 'EXCLUDED', 'ponderado_a': '9.20', 'ponderado_b': '0.00', 'ponderado_c': '0.00'})
    add('mri-component-positive', task, path, rows, [])
    alternative = deepcopy(rows); alternative[0]['ponderado_b'] = '2.7'
    add('mri-nonzero-excluded-intermediate-allowed', task, path, alternative, [])
    wrong = deepcopy(rows); wrong[-1]['ponderado_a'] = '9.15'
    add('negative-mri-report-total', task, path, wrong, ['public_mri_weighted_scores'])
    wrong = deepcopy(rows); wrong[1]['punt_a'] = '9.0'
    add('negative-mri-report-price', task, path, wrong, ['public_mri_source_scores'])
    wrong = deepcopy(rows); wrong[0]['punt_b'] = 'EXCLUIDO'
    add('negative-mri-wrong-language-marker', task, path, wrong, ['public_mri_exclusions'])
    wrong = deepcopy(rows); wrong[-1]['ponderado_b'] = '9.8'
    add('negative-mri-excluded-total', task, path, wrong, ['public_mri_exclusions'])
    wrong = deepcopy(rows); wrong[1]['peso_pct'] = '30'
    add('negative-mri-duplicate-weight', task, path, wrong, MRI_IDS)
    wrong = deepcopy(rows); wrong[-1]['ponderado_a'] = 'NaN'
    add('negative-mri-nonfinite', task, path, wrong, MRI_IDS)
    cases.append({'id': 'negative-mri-missing-output', 'task_id': task, 'outputs': {}, 'expected_failed': MRI_IDS})
    return cases


def qualify(bank, out):
    out.mkdir(parents=True, exist_ok=False)
    cases = controls(bank)
    save(out / 'PLAN.json', {'bank_manifest_sha256': bank.verification['manifest_sha256'],
        'source_sha256': source_identity(), 'registry_sha256': sha(REGISTRY), 'cases': cases,
        'scope': 'Component-specific synthetic outputs, not complete-task positive gold, solver performance, or learning observations.'})
    rows = []
    for case in cases:
        result = evaluate(bank, case['task_id'], {k: {'text': v} for k, v in case['outputs'].items()})
        failed = [c['id'] for c in result['checks'] if not c['passed']]
        expected_count = 5 if 'editorial' in result['checker'] else 4
        # A malformed artifact must not reduce the scoring denominator.
        expected_weight = sum(c['weight'] for c in result['checks'])
        score, passed = aggregate([{'weight': 1}], [{'passed': True}], result)
        ok = set(failed) == set(case['expected_failed']) and expected_weight == expected_count
        ok = ok and (not failed or (score < 1 and not passed))
        rows.append({'id': case['id'], 'ok': ok, 'failed': failed, 'weight': expected_weight,
                     'all_semantic_criteria_pass_control_score': score})
        save(out / 'cases' / (case['id'] + '.json'), result)
    result = {'ok': all(r['ok'] for r in rows), 'rows': rows, 'cases': len(cases),
              'real_model_calls': 0, 'plan_sha256': sha(out / 'PLAN.json')}
    save(out / 'QUALIFICATION.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); result = qualify(Bank(a.bank), a.out.resolve())
    print(json.dumps(result, indent=2)); raise SystemExit(0 if result['ok'] else 1)
