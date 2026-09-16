"""Exact, source-bound CSV subcondition of the composite supplier R7 rubric.

The frozen rubric is unchanged. Its character condition is executable; language
and evidential substance still require judgment. No model text quota is added.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path

REGISTRY = Path(__file__).with_name('supplier_note_registry.json')
OUTPUT = 'output/entscheidungs_matrix.csv'
COLUMNS = ['kriterium_id', 'kriterium', 'status', 'beleg', 'anmerkung']


def registration(payload):
    evidence = payload.get('evidence', {})
    instruction = evidence.get('instruction')
    if not isinstance(instruction, str):
        return None
    digest = hashlib.sha256(instruction.encode()).hexdigest()
    for rule in json.loads(REGISTRY.read_text()):
        if rule['instruction_sha256'] != digest or rule['criterion'] != payload.get('criterion'):
            continue
        for name, expected in rule['source_sha256'].items():
            text = evidence.get('files', {}).get(name, {}).get('text')
            if not isinstance(text, str) or hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != expected:
                break
        else:
            return rule
    return None


def check(payload):
    if registration(payload) is None:
        return None
    text = payload['evidence']['files'].get(OUTPUT, {}).get('text')
    result = {'policy': 'supplier_r7_csv_unicode_characters_v1', 'file': OUTPUT,
              'limit': 200, 'units': 'Unicode code points in parsed cells; no trimming',
              'counts': [], 'passed': False}
    if not isinstance(text, str):
        return {**result, 'error': 'missing_matrix'}
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except csv.Error:
        return {**result, 'error': 'malformed_csv'}
    # Map by header so a valid reordered column set is not misread. A BOM is a
    # file encoding marker, not part of the first column's name.
    if rows and rows[0]:
        rows[0][0] = rows[0][0].removeprefix('\ufeff')
    if (not rows or len(rows[0]) != len(COLUMNS) or set(rows[0]) != set(COLUMNS)
            or any(len(row) != len(COLUMNS) for row in rows[1:])):
        return {**result, 'error': 'invalid_matrix_shape'}
    records = [dict(zip(rows[0], row)) for row in rows[1:]]
    if len(records) != 5 or {r['kriterium_id'] for r in records} != {f'K{i}' for i in range(1, 6)}:
        return {**result, 'error': 'missing_or_duplicate_criterion_rows'}
    counts = [{'kriterium_id': row['kriterium_id'], 'characters': len(row['anmerkung'])} for row in records]
    return {**result, 'counts': counts, 'passed': all(r['characters'] <= 200 for r in counts), 'error': None}


def veto(payload):
    measured = check(payload)
    if measured is None or measured['passed']:
        return None
    return {'criterion_id': payload['criterion']['id'], 'passed': False, 'evidence': OUTPUT,
            'reasoning': 'The required anmerkung cells cannot satisfy the registered CSV/length condition: ' +
                         json.dumps(measured, ensure_ascii=False, sort_keys=True) +
                         '. Language and evidential substance are not automatically approved.'}


def semantic_payload(payload):
    rule = registration(payload)
    measured = check(payload) if rule else None
    if measured is None or not measured['passed']:
        return payload
    result = deepcopy(payload)
    result['criterion']['requirement'] = rule['semantic_requirement']
    result['prevalidated_subconditions'] = measured
    result['evaluation_scope'] = (
        'The original composite criterion is a conjunction. The trusted CSV parser has already '
        'verified the character bound and recorded exact counts. Judge ONLY whether each anmerkung '
        'uses the required language and provides substantive justification tied to source evidence. '
        'Do not recount characters or fail this semantic judgment for the already verified length '
        'condition. A passing length check alone is insufficient for a semantic pass.')
    return result
