"""Structured verdict shape; verbosity is prompt guidance, not a text quota."""
from copy import deepcopy

SCHEMA = {'type': 'object', 'properties': {
    'criterion_id': {'type': 'string'}, 'evidence': {'type': 'string'},
    'reasoning': {'type': 'string'}, 'passed': {'type': 'boolean'}},
    'required': ['criterion_id', 'evidence', 'reasoning', 'passed'],
    'additionalProperties': False}


def contract(criterion_id, evidence_paths):
    if not isinstance(criterion_id, str) or not criterion_id:
        raise ValueError('Criterion ID must be a nonempty string')
    paths = list(evidence_paths)
    if not paths or any(not isinstance(p, str) or not p for p in paths):
        raise ValueError('Nonempty evidence filenames required')
    schema = deepcopy(SCHEMA)
    schema['properties']['criterion_id']['enum'] = [criterion_id]
    schema['properties']['evidence']['enum'] = sorted(set(paths))
    return {'json': schema}


def validate_text(value):
    return isinstance(value, str)
