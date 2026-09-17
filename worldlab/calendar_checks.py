"""Source-bound calendar arithmetic; policy and arithmetic are separate checks."""
import csv
from datetime import date, timedelta
import hashlib
import io
from pathlib import Path
import re
from scripts.source_world_calibration import read

REGISTRY = Path(__file__).with_name('calendar_registry.json')
OUTPUT = 'output/planning_scenarios.csv'
SOURCE = 'input/agenda_editorial_v3.csv'
COLUMNS = ['scenario', 'titre', 'langue', 'date_livraison_manuscrit', 'date_relecture',
           'fenetre_jours_calendaires', 'fenetre_jours_ouvrables', 'sous_seuil_10j', 'date_parution', 'statut']
SCENARIOS = {'dates_fixes', 'compression', 'glissement'}
STATUSES = {'OK', 'ALERTE_INDISPONIBILITE', 'GLISSEMENT_OBLIGATOIRE', 'EXCEPTION_EVENEMENT'}
HOLIDAYS = {date(2025, m, d) for m, d in [(1, 1), (4, 18), (5, 1), (5, 8), (7, 14)]}
DATE_FIELDS = ['date_livraison_manuscrit', 'date_relecture', 'date_parution']


def calendar_day(text):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        raise ValueError('Dates must use YYYY-MM-DD')
    return date.fromisoformat(text)


def window(start, end):
    days = (end - start).days + 1
    interval = [start + timedelta(days=i) for i in range(max(0, days))]
    # A negative interval is prescribed by the public subtraction formula.
    # It has no Sundays/holidays within [start,end], and is not silently clamped.
    working = days - sum(d.weekday() == 6 for d in interval) - sum(d in HOLIDAYS for d in interval)
    return days, working


def rows(text):
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    if reader.fieldnames != COLUMNS:
        raise ValueError('CSV columns differ from the ten public columns')
    result = list(reader)
    if len(result) != 36 or any(None in r or any(v is None or not v.strip() for v in r.values()) for r in result):
        raise ValueError('CSV must have 36 complete rows with exactly ten cells each')
    return result


def verdict(payload):
    c = payload.get('criterion', {}); identifier = c.get('id')
    registry = read(REGISTRY)
    if identifier not in registry['criterion_ids']:
        return None
    evidence = payload.get('evidence', {}); files = evidence.get('files', {})
    digest = hashlib.sha256(evidence.get('instruction', '').encode()).hexdigest()
    for rule in registry['tasks'].values():
        if rule['instruction_sha256'] != digest or c not in rule['criteria']:
            continue
        for path, expected in rule['input_text_sha256'].items():
            text = files.get(path, {}).get('text')
            if not isinstance(text, str) or hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != expected:
                break
        else:
            break
    else:
        return None
    # Do not accept a matching instruction with changed source files.
    if any(not isinstance(files.get(p, {}).get('text'), str) or
           hashlib.sha256(files[p]['text'].replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != h
           for p, h in rule['input_text_sha256'].items()):
        return None
    reason = 'Every submitted row satisfies this source-bound calendar criterion.'
    passed = True
    try:
        data = rows(files.get(OUTPUT, {}).get('text', ''))
        agenda = {(r['titre'], r['langue']): r for r in csv.DictReader(io.StringIO(files[SOURCE]['text']))}
        keys = [(r['scenario'], r['titre'], r['langue']) for r in data]
        expected = {(s, t, l) for s in SCENARIOS for t, l in agenda}
        if len(set(keys)) != 36 or set(keys) != expected:
            raise ValueError('CSV has duplicate, missing or unknown scenario/title/language keys')
        if identifier == 'csv_sort_order' and keys != sorted(keys):
            raise ValueError('CSV keys are not alphabetically sorted')
        for r in data:
            key = (r['titre'], r['langue']); original = agenda[key]
            if r['statut'] not in STATUSES or r['sous_seuil_10j'] not in {'oui', 'non'}:
                raise ValueError('CSV contains an invalid status or threshold enum')
            dates = {f: calendar_day(r[f]) for f in DATE_FIELDS}
            if identifier == 'window_arithmetic':
                actual = tuple(int(r[f]) for f in ['fenetre_jours_calendaires', 'fenetre_jours_ouvrables'])
                want = window(dates[DATE_FIELDS[0]], dates[DATE_FIELDS[1]])
                if actual != want:
                    raise ValueError(f'{r["scenario"]}/{key}: calendar/working days {actual}, expected {want} from submitted dates')
            if identifier == 'sous_seuil_flag':
                want = 'oui' if int(r['fenetre_jours_ouvrables']) < 10 else 'non'
                if r['sous_seuil_10j'] != want:
                    raise ValueError(f'{r["scenario"]}/{key}: threshold flag must be {want}')
            applicable = {'dates_fixes_fidelity': 'dates_fixes', 'compression_shift': 'compression', 'glissement_logic': 'glissement'}
            if identifier not in applicable or r['scenario'] != applicable[identifier]:
                continue
            want = {f: calendar_day(original[f]) for f in DATE_FIELDS}
            delayed = want[DATE_FIELDS[0]] + timedelta(days=14)
            if identifier == 'compression_shift':
                want[DATE_FIELDS[0]] = delayed
            elif identifier == 'glissement_logic':
                trigger = r['langue'] != 'FR' and window(delayed, want[DATE_FIELDS[1]])[1] < 10
                if trigger:
                    want[DATE_FIELDS[0]] = delayed
                    if key != ('Atlas des Migrations', 'DE'):
                        want[DATE_FIELDS[2]] += timedelta(days=14)
                        want[DATE_FIELDS[1]] = want[DATE_FIELDS[2]] - timedelta(days=7)
                # Explicit public instruction: unaffected rows retain dates_fixes.
            if dates != want:
                raise ValueError(f'{r["scenario"]}/{key}: dates must be ' + ', '.join(f'{f}={want[f]}' for f in DATE_FIELDS))
    except (ValueError, KeyError, TypeError, csv.Error) as exc:
        passed = False; reason = str(exc)
    return {'criterion_id': identifier, 'passed': passed, 'evidence': OUTPUT, 'reasoning': reason}
