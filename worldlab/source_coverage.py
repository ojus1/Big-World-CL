"""Restore source rubric obligations omitted by qualitative-only extraction.

Original executable check code is not automatically trusted: source QA found
false substring/column failures and unsound schedule predicates. Restored
obligations use the structured criterion judge except where a separately
registered, source-bound executable predicate exists. This is explicit in the
contract and does not claim that all arithmetic is machine verified.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from scripts.source_world_calibration import read, child, sha

POLICY = 'original_mechanical_obligations_plus_frozen_r3_v1'
REGISTRY = Path(__file__).with_name('source_coverage_registry.json')


def rubric(bank, task_id):
    row = bank.by_id[task_id]
    result = deepcopy(read(child(bank.root, row['private_directory']) / 'rubric.json'))
    definition = bank.private_definition(task_id)
    review = read(REGISTRY)['tasks'].get(task_id)
    if review is not None and (review['definition_sha256'] != row.get('definition_sha256') or
            review['instruction_sha256'] != hashlib.sha256(bank.public(task_id)['instruction'].encode()).hexdigest()):
        raise ValueError('Source-obligation correction requires requalification after source change')
    original_count = len(result['criteria'])
    present = {c['id'] for c in result['criteria']}
    restored = []
    for c in definition.get('rubric', []):
        if c.get('verification') != 'mechanical' or c['id'] in present:
            continue
        value = {key: deepcopy(c[key]) for key in ('id', 'requirement', 'weight')}
        value.update(acceptable_alternatives=deepcopy(c.get('acceptable_alternatives', [])),
                     evidence_anchors=[], failure_examples=[])
        correction = review.get('corrections', {}).get(c['id']) if review else None
        if correction is not None:
            if c['requirement'] != correction['original_requirement']:
                raise ValueError('Corrected source requirement differs from reviewed original')
            value['requirement'] = correction['requirement']
        restored.append(value); present.add(c['id'])
    result['criteria'].extend(restored)
    if restored:
        result.setdefault('evaluation_guidance', []).append(
            'These restored source obligations were formerly assigned to an executable checker. '
            'Assess their public meaning, not the private checker implementation or unbound gold strings. '
            'The actual public instruction and supplied source evidence control translated prose, '
            'section names and recommendation wording; preserve explicit machine field names and enums. '
            'Check every required row or item and report the first decisive violation concisely. '
            'Do not infer correct arithmetic from an agent claim that it ran a validator.')
    result['source_coverage'] = {'policy': POLICY, 'restored_ids': [c['id'] for c in restored],
        'original_r3_criterion_count': original_count,
        'correction_registry_sha256': sha(REGISTRY),
        'corrected_ids': list(review['corrections']) if review else [],
        'source_definition_sha256': row.get('definition_sha256'),
        'criteria_sha256': hashlib.sha256(json.dumps(result['criteria'], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'method': 'structured model judgments except separately registered executable predicates; original checker SQL/gold is not executed',
        'public_contract_completeness_certified': False}
    return result


def count_verdict(payload):
    evidence = payload.get('evidence', {})
    digest = hashlib.sha256(evidence.get('instruction', '').encode()).hexdigest()
    for review in read(REGISTRY)['tasks'].values():
        if review['instruction_sha256'] != digest:
            continue
        for identifier, rule in review.get('counts', {}).items():
            if payload.get('criterion') != rule['criterion']:
                continue
            for name, expected in review['input_text_sha256'].items():
                text = evidence.get('files', {}).get(name, {}).get('text')
                if not isinstance(text, str) or hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != expected:
                    break
            else:
                text = evidence['files'].get(rule['path'], {}).get('text', '')
                if rule['exclude_title']:
                    text = '\n'.join(text.strip().splitlines()[1:])
                count = sum(any(c.isalnum() for c in word) for word in text.split())
                return {'criterion_id': identifier, 'passed': rule['minimum'] <= count <= rule['maximum'],
                        'evidence': rule['path'], 'reasoning':
                        f"The source-bound full-report count is {count} words; the required range is {rule['minimum']}–{rule['maximum']}. Whitespace-delimited tokens containing a Unicode letter/digit count once; standalone punctuation is excluded."}
    return None
