"""Registered memo body count, kept separate from prose semantics.

This repairs historical diagnostics; the scheduling family remains excluded for
independently demonstrated source infeasibility. It does not requalify the task.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

REGISTRY = Path(__file__).with_name('memo_count_registry.json')
OUTPUT = 'output/memorando.md'


def registration(payload):
    evidence = payload.get('evidence', {})
    instruction = evidence.get('instruction', '')
    for row in json.loads(REGISTRY.read_text()):
        if (hashlib.sha256(instruction.encode()).hexdigest() != row['instruction_sha256'] or
                payload.get('criterion') not in row['criteria']):
            continue
        for name, digest in row['source_sha256'].items():
            text = evidence.get('files', {}).get(name, {}).get('text')
            if not isinstance(text, str) or hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != digest:
                break
        else:
            return row
    return None


def body_count(text):
    lines = text.removeprefix('\ufeff').strip().splitlines()
    # The public contract requires title + body. The first nonblank line is
    # the title; support the two common Markdown title syntaxes.
    body = lines[1:]
    if body and re.fullmatch(r'[=-]+', body[0].strip()):
        body = body[1:]
    tokens = '\n'.join(body).split()
    return sum(any(c.isalnum() for c in token) for token in tokens)


def measure(payload):
    if registration(payload) is None:
        return None
    text = payload['evidence']['files'].get(OUTPUT, {}).get('text', '')
    count = body_count(text)
    return {'file': OUTPUT, 'body_words': count, 'minimum': 145, 'maximum': 155,
            'passed': 145 <= count <= 155,
            'convention': 'Exclude the first nonblank title line and optional Setext underline; count whitespace-delimited body tokens containing a Unicode letter or digit. Hyphenated and apostrophe-containing tokens count once; standalone punctuation does not count.'}


def verdict(payload):
    measured = measure(payload)
    if measured is None or payload['criterion']['id'] != 'memo_word_count':
        return None
    return {'criterion_id': 'memo_word_count', 'passed': measured['passed'], 'evidence': OUTPUT,
            'reasoning': 'Registered body word-count check: ' + json.dumps(measured, ensure_ascii=False)}


def semantic_payload(payload):
    measured = measure(payload)
    if measured is None or payload['criterion']['id'] != 'memo_format_quality':
        return payload
    result = deepcopy(payload)
    result['separately_evaluated_word_count'] = measured
    result['evaluation_scope'] = (
        'Judge this format/content criterion only: title, continuous body, professional register, '
        'source-grounded capacities and attribution, normative decision and practical consequence. '
        'The separate memo_word_count criterion is mechanically evaluated with the recorded count. '
        'Do not estimate or recount words, or propagate its pass/fail into this different criterion. '
        'A correct word count does not establish correct prose or facts.')
    return result
