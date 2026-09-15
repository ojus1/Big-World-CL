"""Structured verdict shape; verbosity is prompt guidance, not a text quota."""
from copy import deepcopy

SCHEMA = {'type': 'object', 'properties': {
    'criterion_id': {'type': 'string'}, 'evidence': {'type': 'string'},
    'reasoning': {'type': 'string'}, 'passed': {'type': 'boolean'}},
    'required': ['criterion_id', 'evidence', 'reasoning', 'passed'],
    'additionalProperties': False}


def contract(criterion_id):
    if not isinstance(criterion_id, str) or not criterion_id:
        raise ValueError('Criterion ID must be a nonempty string')
    schema = deepcopy(SCHEMA)
    schema['properties']['criterion_id']['enum'] = [criterion_id]
    return {'json': schema}


def validate_text(value):
    return isinstance(value, str)
