"""Structured verdict shape; verbosity is prompt guidance, not a text quota."""
from copy import deepcopy

RECOVERY_RATIONALE = 'Format recovery verdict; no written rationale was requested.'


def recovery_contract(original):
    """Keep every decision field; replace open-ended rationale with a fixed label.

    The retry uses the same evidence and criterion. Finite choices are enforced
    in the inference request, without a character quota on model explanations.
    This also preserves all supplier-row and exam-section Boolean judgments.
    """
    result = deepcopy(original)
    def visit(schema):
        for name, prop in schema.get('properties', {}).items():
            if name == 'reasoning':
                prop['enum'] = [RECOVERY_RATIONALE]
            visit(prop)
        if schema.get('type') == 'string' and not schema.get('enum'):
            raise ValueError('Recovery schema contains an unconstrained string')
    visit(result['json'])
    return result


def validate_recovery(value):
    """Audit fixed labels independently of the provider's grammar enforcement."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'reasoning' and item != RECOVERY_RATIONALE:
                raise ValueError('Recovery rationale differs from the declared fixed label')
            validate_recovery(item)
    elif isinstance(value, list):
        for item in value:
            validate_recovery(item)

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
