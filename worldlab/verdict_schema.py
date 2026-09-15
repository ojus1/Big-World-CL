"""Structured verdict shape; verbosity is prompt guidance, not a text quota."""
from copy import deepcopy
import json

SCHEMA = {'type': 'object', 'properties': {
    'criterion_id': {'type': 'string'}, 'evidence': {'type': 'string'},
    'reasoning': {'type': 'string'}, 'passed': {'type': 'boolean'}},
    'required': ['criterion_id', 'evidence', 'reasoning', 'passed'],
    'additionalProperties': False}


def schema(criterion_id):
    if not isinstance(criterion_id, str) or not criterion_id:
        raise ValueError('Criterion ID must be a nonempty string')
    schema = deepcopy(SCHEMA)
    schema['properties']['criterion_id']['enum'] = [criterion_id]
    return {'json': schema}


def contract(criterion_id):
    """Compact JSON syntax without inter-field whitespace or text-length limits.

    The deployed XGrammar version ignores per-request JSON whitespace controls.
    This six-rule grammar enforces the same value types with Unicode strings.
    It avoids the hundreds of bounding rules in the historical ASCII grammar.
    """
    schema(criterion_id)  # Validate identity before embedding it as a literal.
    literal = lambda value: json.dumps(value, ensure_ascii=False)
    prefix = '{"criterion_id":' + json.dumps(criterion_id, ensure_ascii=False) + ',"passed":'
    rules = [
        'root ::= ' + literal(prefix) + ' boolean ' + literal(',"evidence":') +
            ' string ' + literal(',"reasoning":') + ' string ' + literal('}'),
        r'string ::= "\"" character* "\""',
        r'character ::= [^"\\\x00-\x1f] | "\\" escape',
        r'escape ::= ["\\/bfnrt] | "u" hex hex hex hex',
        'hex ::= [0-9a-fA-F]',
        'boolean ::= "true" | "false"',
    ]
    return {'grammar': '\n'.join(rules)}


def validate_text(value):
    return isinstance(value, str)
