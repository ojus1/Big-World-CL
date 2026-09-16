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
ROW_METHOD = 'registered_supplier_note_semantic_rows_v1'


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
        rows = [row for row in csv.reader(io.StringIO(text, newline=''), strict=True) if row]
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
        'condition. A passing length check alone is insufficient for a semantic pass. '
        'Assess every row K1 through K5 separately. For each row, verify ALL factual claims in '
        'the note against its source, including identifiers, severity, dates, amounts and signatures. '
        'A citation or plausible wording does not make a claim true. For example a note that '
        'misstates a source severity fails facts_supported even if it cites a real finding ID. '
        'Return criterion_id and rows; each row has evidence, reasoning, language_correct, '
        'facts_supported and justification_substantive. The host computes the conjunction.')
    return result


def semantic_schema(payload):
    measured = check(payload)
    if measured is None or not measured['passed']:
        return None
    props = {'evidence': {'type': 'string', 'enum': sorted(payload['evidence']['files'])},
             'reasoning': {'type': 'string'}, 'language_correct': {'type': 'boolean'},
             'facts_supported': {'type': 'boolean'}, 'justification_substantive': {'type': 'boolean'}}
    row = {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}
    rows = {f'K{i}': row for i in range(1, 6)}
    return {'json': {'type': 'object', 'properties': {
        'criterion_id': {'type': 'string', 'enum': ['R7']},
        'rows': {'type': 'object', 'properties': rows, 'required': list(rows), 'additionalProperties': False}},
        'required': ['criterion_id', 'rows'], 'additionalProperties': False}}


def parse_semantic(value, files):
    keys = ['evidence', 'reasoning', 'language_correct', 'facts_supported', 'justification_substantive']
    if (not isinstance(value, dict) or set(value) != {'criterion_id', 'rows'} or value['criterion_id'] != 'R7'
            or not isinstance(value['rows'], dict) or set(value['rows']) != {f'K{i}' for i in range(1, 6)}):
        raise ValueError('Missing or unexpected supplier row judgments')
    checks = []
    for identifier in [f'K{i}' for i in range(1, 6)]:
        row = value['rows'][identifier]
        if (not isinstance(row, dict) or set(row) != set(keys) or not isinstance(row['reasoning'], str)
                or row['evidence'] not in files or any(type(row[k]) is not bool for k in keys[2:])):
            raise ValueError('Invalid supplier semantic row judgment')
        checks.append({'kriterium_id': identifier, **row, 'passed': all(row[k] for k in keys[2:])})
    failures = [r for r in checks if not r['passed']]
    return {'criterion_id': 'R7', 'passed': not failures, 'evidence': OUTPUT,
            'reasoning': '; '.join(r['kriterium_id'] + ': ' + r['reasoning'] for r in (failures or checks)),
            'row_checks': checks}


def source_matrix_verdict(payload):
    """Complete executable restored R1-R5 predicates for pinned supplier inputs."""
    # Reuse exact instruction/source binding and the same strict CSV parser.
    bound = None
    for rule in json.loads(REGISTRY.read_text()):
        candidate = {**payload, 'criterion': rule['criterion']}
        if payload.get('criterion') in rule.get('matrix_criteria', []) and registration(candidate) is not None:
            bound = candidate
            break
    if bound is None:
        return None
    measured = check(bound)
    identifier = payload['criterion']['id']
    issues = []
    if measured['error'] is not None:
        issues.append('Invalid required CSV structure: ' + measured['error'])
    elif identifier != 'R1':
        rows = {r['kriterium_id']: r for r in csv.DictReader(io.StringIO(
            payload['evidence']['files'][OUTPUT]['text'].removeprefix('\ufeff'), newline=''), strict=True)}
        expected = {'R2': {'K1': 'nicht_erfuellt'}, 'R3': {'K2': 'erfuellt'},
                    'R4': {'K3': 'teilweise_erfuellt'}, 'R5': {'K4': 'erfuellt', 'K5': 'erfuellt'}}[identifier]
        for key, status in expected.items():
            if rows[key]['status'] != status:
                issues.append(key + ': status ' + repr(rows[key]['status']) + '; source requires ' + status)
    return {'criterion_id': identifier, 'passed': not issues, 'evidence': OUTPUT,
            'reasoning': '; '.join(issues) if issues else
                'The source-bound CSV predicate satisfies ' + identifier + ': ' + payload['criterion']['requirement'] +
                '. Counts apply to decoded CSV cells; human-readable criterion labels are not compared with untranslated private gold.'}


def matrix_status_check(bank, task_id, files):
    """The public handbook states exact statuses; all source bytes are pinned."""
    rule = next((r for r in json.loads(REGISTRY.read_text()) if r['task_id'] == task_id), None)
    if rule is None: return None
    payload = {'criterion': rule['criterion'], 'evidence': {'instruction': bank.public(task_id)['instruction'], 'files': files}}
    if registration(payload) is None: return None
    measured = check(payload)
    issues = []
    if measured['error'] is not None:
        issues.append(OUTPUT + ': ' + measured['error'])
    else:
        rows = list(csv.DictReader(io.StringIO(files[OUTPUT]['text'].removeprefix('\ufeff'), newline=''), strict=True))
        expected = {'K1': 'nicht_erfuellt', 'K2': 'erfuellt', 'K3': 'teilweise_erfuellt', 'K4': 'erfuellt', 'K5': 'erfuellt'}
        for row in rows:
            if row['status'] != expected[row['kriterium_id']]:
                issues.append(row['kriterium_id'] + ': status ' + repr(row['status']) + '; required ' + expected[row['kriterium_id']])
    return {'id': 'public_supplier_matrix_statuses', 'weight': 1, 'passed': not issues,
            'requirement': 'Apply the public K1-K5 status rules to the pinned evidence: open Major => K1 not fulfilled; '
                           'certificate within 12 months of contract => K2 fulfilled; 50% insurance => K3 partial; '
                           'signed dated amendment and scope memo => K4 and K5 fulfilled.',
            'evidence': issues, 'failure_count': len(issues)}
