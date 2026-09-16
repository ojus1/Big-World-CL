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
from scripts.source_world_calibration import read, child

POLICY = 'original_mechanical_obligations_plus_frozen_r3_v1'


def rubric(bank, task_id):
    row = bank.by_id[task_id]
    result = deepcopy(read(child(bank.root, row['private_directory']) / 'rubric.json'))
    definition = bank.private_definition(task_id)
    original_count = len(result['criteria'])
    present = {c['id'] for c in result['criteria']}
    restored = []
    for c in definition.get('rubric', []):
        if c.get('verification') != 'mechanical' or c['id'] in present:
            continue
        value = {key: deepcopy(c[key]) for key in ('id', 'requirement', 'weight')}
        value.update(acceptable_alternatives=deepcopy(c.get('acceptable_alternatives', [])),
                     evidence_anchors=[], failure_examples=[])
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
        'source_definition_sha256': row.get('definition_sha256'),
        'criteria_sha256': hashlib.sha256(json.dumps(result['criteria'], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'method': 'structured model judgments except separately registered executable predicates; original checker SQL/gold is not executed',
        'public_contract_completeness_certified': False}
    return result
