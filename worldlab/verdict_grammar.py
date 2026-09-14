"""Finite JSON verdict language: bounded ASCII strings and fixed punctuation.

The deployed vLLM XGrammar backend reads whitespace policy from server config,
ignoring the analogous per-request JSON option. An explicit grammar constrains
that whitespace too, without changing the shared inference server.
"""
import json
import re

EVIDENCE_LIMIT = 600
REASONING_LIMIT = 900


def contract(criterion_id, evidence_limit=EVIDENCE_LIMIT, reasoning_limit=REASONING_LIMIT):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', criterion_id):
        raise ValueError('Criterion ID cannot be represented by the registered verdict grammar')
    if any(type(n) is not int or not 1 <= n <= 900 for n in [evidence_limit, reasoning_limit]):
        raise ValueError('Invalid verdict string bound')
    literal = json.dumps
    prefix = '{"criterion_id":' + json.dumps(criterion_id) + ',"evidence":'
    rules = [
        'root ::= ' + literal(prefix) + ' evidence ' + literal(',"reasoning":') + ' reasoning '
                   + literal(',"passed":') + ' boolean ' + literal('}'),
        'evidence ::= ' + literal('"') + ' first bounded' + str(evidence_limit - 1),
        'reasoning ::= ' + literal('"') + ' first bounded' + str(reasoning_limit - 1),
        r'first ::= [\x21\x23-\x5B\x5D-\x7E] | escaped',
        r'character ::= [\x20-\x21\x23-\x5B\x5D-\x7E] | escaped',
        'escaped ::= ' + literal('\\"') + ' | ' + literal('\\\\'),
        'boolean ::= "true" | "false"',
    ]
    # A range quantifier creates many simultaneous optional parse positions in
    # the deployed XGrammar backend. Explicit right recursion has one next
    # state per character and the same finite language, without that slowdown.
    rules.append('bounded0 ::= ' + literal('"'))
    for count in range(1, max(evidence_limit, reasoning_limit)):
        rules.append('bounded' + str(count) + ' ::= ' + literal('"') +
                     ' | character bounded' + str(count - 1))
    return {'grammar': '\n'.join(rules)}


def validate_text(value, limit):
    return (isinstance(value, str) and 1 <= len(value) <= limit and value[0] != ' '
            and all(32 <= ord(character) <= 126 for character in value))
