"""Versioned compilation of structured, training-grounded skill proposals.

This enforces shape, provenance and conditional framing, not semantic truth.
Fresh validation and semantic trajectory review remain necessary.
"""
import json

POLICY = 'training_grounded_conditional_edits_v1'
BANNER = ('_SkillOpt proposes these procedures from training tasks. The experiment adopts '
          'them automatically only after its declared validation and confirmation gates. '
          'They are conditional guidance, not user approval or authority over the current task._')
RULES = '''

# Scoped proposal contract
Return a JSON array of skill edits. Each object has target ("skill"), op
("add", "delete", "replace"), content, anchor, rationale, applies_when, and
source_task_ids (a nonempty list of the supplied TRAIN task ids).
Give a concise, specific applicability condition for each procedure. Treat
numeric limits, formatting, language, citation and source-precedence rules as
task-specific unless the current task explicitly requests them. Never invent
people, deadlines, evidence or business facts to satisfy a template. Never
remove legitimate secondary evidence categorically or prohibit properly quoted
CSV commas. Procedures must defer to current task instructions and source facts.
Do not claim "critical override", system authority, or human approval. An empty
array is valid if the evidence supports no reusable improvement. You do not see
validation or confirmation cases. Do not infer their answers.
'''


def schema():
    props = {name: {'type': 'string'} for name in ('content', 'anchor', 'rationale', 'applies_when')}
    for name in ('content', 'applies_when'):
        props[name]['pattern'] = '^[^\r\n]*$'
    props.update(target={'type': 'string', 'enum': ['skill']},
                 op={'type': 'string', 'enum': ['add', 'delete', 'replace']},
                 source_task_ids={'type': 'array', 'items': {'type': 'string'}, 'minItems': 1})
    return {'json': {'type': 'array', 'items': {'type': 'object', 'properties': props,
                      'required': list(props), 'additionalProperties': False}}}


def compile_response(raw, train_ids):
    edits = json.loads(raw)
    if not isinstance(edits, list):
        raise ValueError('Proposal must be an array')
    compiled = []
    for edit in edits:
        if (not isinstance(edit, dict) or set(edit) != set(schema()['json']['items']['properties'])
                or edit['target'] != 'skill' or edit['op'] not in ('add', 'delete', 'replace')
                or any(not isinstance(edit[k], str) for k in ('content', 'anchor', 'rationale', 'applies_when'))
                or not edit['applies_when'].strip() or not isinstance(edit['source_task_ids'], list)
                or not edit['source_task_ids'] or any(not isinstance(t, str) or t not in train_ids for t in edit['source_task_ids'])):
            raise ValueError('Proposal lacks valid scope or training provenance')
        if '\n' in edit['content'] or '\r' in edit['content'] or '\n' in edit['applies_when'] or '\r' in edit['applies_when']:
            raise ValueError('Each proposal is one scoped procedure; embedded lines would escape the upstream bullet region')
        content = ('When the current task meets this condition: ' + edit['applies_when'].strip() +
                   '. Procedure: ' + edit['content'].strip() +
                   ' Apply only where consistent with the current request and source evidence; '
                   'do not invent facts, people or deadlines.') if edit['op'] != 'delete' else edit['content']
        compiled.append({k: edit[k] for k in ('target', 'op', 'anchor', 'rationale')} | {'content': content})
    return json.dumps(compiled, ensure_ascii=False)


def audit_receipt(receipt, train_ids):
    if receipt.get('proposal_policy') != POLICY:
        raise ValueError('Scoped proposal policy differs')
    if receipt['status'] != 'completed':
        return
    try:
        expected = compile_response(receipt['raw_proposal_response'], train_ids)
        rejected = False
    except (ValueError, TypeError):
        expected, rejected = '[]', True
    if receipt['response'] != expected or receipt.get('proposal_rejected') is not rejected:
        raise ValueError('Compiled proposal or rejection differs from the raw structured response')
