"""Outcome-blind mapping of representative employee prompts to source tasks.

Text similarity is a transparent retrieval aid, not a simulator-fidelity score.
Only calibration-training briefs are searched. Validation and holdout briefs
cannot influence the task mixture fitted here.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import math
import random
import re
from dataclasses import asdict
from .contracts import Budget

STOP = set('a an the to of and or in for on with from this that is are be as by it its my our please'.split())


def attach_examples(workforce, examples):
    """Combine simulator-generated employees with examples for any subset.

    The user supplies {employee_id: [representative task objects]}. They do not
    need to enumerate unobserved employees or repeat role/language metadata.
    """
    specification = deepcopy(workforce)
    indexed = {e['id']: e for e in specification['employees']}
    if not isinstance(examples, dict) or set(examples) - set(indexed):
        raise ValueError('Examples must refer to known employees in the simulated workforce')
    for employee_id, tasks in examples.items():
        if not isinstance(tasks, list):
            raise ValueError('Employee examples must be a list')
        indexed[employee_id]['representative_tasks'] = deepcopy(tasks)
    return specification


def tokens(text):
    return [t for t in re.findall(r'[^\W_]+', text.lower()) if len(t) > 1 and t not in STOP]


def fit(bank, specification):
    if specification.get('schema_version') != 1:
        raise ValueError('Unknown calibration schema')
    employees = specification.get('employees', [])
    if not employees or len({e['id'] for e in employees}) != len(employees):
        raise ValueError('Employee identities must be nonempty and unique')
    catalog = [r for r in bank.rows if r['partition'] == 'calibration_train']
    documents = {r['id']: Counter(tokens(r['title'] + ' ' + r['workflow'] + ' ' +
                  bank.public(r['id'])['instruction'])) for r in catalog}
    df = Counter(word for doc in documents.values() for word in doc)
    n = len(documents)
    idf = {word: math.log(1 + (n + 1) / (count + 1)) for word, count in df.items()}

    def similarity(query, task_id):
        doc = documents[task_id]
        def weight(count, word):
            return (1 + math.log(count)) * idf.get(word, math.log(n + 2))
        numerator = sum(weight(c, w) * weight(doc[w], w) for w, c in query.items() if w in doc)
        denom = math.sqrt(sum(weight(c, w)**2 for w, c in query.items()) *
                          sum(weight(c, w)**2 for w, c in doc.items()))
        return numerator / denom if denom else 0.0

    matches = []
    for employee in employees:
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', employee['id']):
            raise ValueError('Invalid employee ID')
        anchors = employee.get('representative_tasks', [])
        if not isinstance(anchors, list) or not employee.get('role') or not employee.get('language'):
            raise ValueError('Each employee needs role and language; representative_tasks is an optional list')
        seen = set()
        for i, anchor in enumerate(anchors):
            if not isinstance(anchor.get('prompt'), str) or not anchor['prompt'].strip():
                raise ValueError('A representative task needs a nonempty prompt')
            weight = anchor.get('weight', 1)
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
                raise ValueError('Task weights must be finite and positive')
            selector = anchor.get('selector', {})
            if set(selector) - {'task_ids', 'sources', 'workflows'}:
                raise ValueError('Unknown task selector')
            count = anchor.get('matches', 1)
            if type(count) is not int or count < 1:
                raise ValueError('matches must be positive')
            if 'task_ids' in selector:
                if not selector['task_ids'] or len(set(selector['task_ids'])) != len(selector['task_ids']):
                    raise ValueError('Explicit task IDs must be nonempty and unique')
                for ident in selector['task_ids']:
                    if ident not in bank.by_id or bank.by_id[ident]['partition'] != 'calibration_train':
                        raise ValueError('Representative anchors may select only calibration-training tasks')
            candidates = [r for r in catalog if r['language'] == employee['language'] and
                          all(r[field] in selector[key] for key, field in
                              [('task_ids', 'id'), ('sources', 'source'), ('workflows', 'workflow')]
                              if key in selector)]
            query = Counter(tokens(anchor['prompt']))
            ranked = sorted(((similarity(query, r['id']), r) for r in candidates), key=lambda x: (-x[0], x[1]['id']))
            chosen = []
            for score, row in ranked:
                if row['calibration_group'] in seen:
                    continue
                if score == 0 and 'task_ids' not in selector:
                    continue
                chosen.append({'task_id': row['id'], 'lineage_group': row['calibration_group'],
                               'similarity': score, 'source': row['source'], 'workflow': row['workflow']})
                seen.add(row['calibration_group'])
                if len(chosen) == count:
                    break
            matches.append({'employee_id': employee['id'], 'role': employee['role'],
                            'language': employee['language'], 'anchor_index': i,
                            'prompt': anchor['prompt'], 'weight': weight,
                            'selection': 'explicit' if 'task_ids' in selector else 'tfidf_cosine',
                            'requested_matches': count, 'matches': chosen,
                            'unfilled_matches': count - len(chosen)})
    total = sum(a['weight'] for a in matches)
    covered = sum(a['weight'] * (len(a['matches']) / a['requested_matches']) for a in matches)
    workforce = assign_workforce(employees, matches)
    return {'schema_version': 1, 'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'anchors': matches, 'weighted_retrieval_coverage': covered / total if total else None,
            'workforce': workforce,
            'employee_coverage': dict(Counter(e['calibration_status'] for e in workforce)),
            'scope': 'Development task retrieval from an optional subset of employees. Weights are supplied, not measured prevalence. Role transfer is an assumption; unanchored employees retain simulator defaults. Similarity is not semantic equivalence or simulator fidelity.'}


def assign_workforce(employees, anchors):
    """Partial calibration never makes missing employees disappear from a world.

    Direct examples take precedence. Transfer requires matching language and
    calibration_role (or exact role label); broad cross-role fallback is absent.
    A None task_mixture tells the caller to retain its existing simulator default.
    """
    by_employee = {}
    for anchor in anchors:
        by_employee.setdefault(anchor['employee_id'], []).append(anchor)

    def role_key(employee):
        return (employee.get('calibration_role', employee['role']).strip().casefold(), employee['language'])

    workforce = []
    for employee in employees:
        direct = by_employee.get(employee['id'], [])
        donors = [e['id'] for e in employees if e['id'] != employee['id'] and
                  role_key(e) == role_key(employee) and e.get('representative_tasks')]
        supplied = bool(employee.get('representative_tasks'))
        selected = direct if supplied else [a for ident in donors for a in by_employee.get(ident, [])]
        mixture = Counter()
        for anchor in selected:
            for match in anchor['matches']:
                mixture[match['task_id']] += anchor['weight'] / anchor['requested_matches']
        status = ('direct_examples' if supplied else 'role_transfer') if mixture else 'uncalibrated_default'
        mass = sum(mixture.values())
        workforce.append({'employee_id': employee['id'], 'role': employee['role'],
                          'language': employee['language'], 'calibration_status': status,
                          'examples_supplied': supplied,
                          'evidence_employee_ids': [employee['id']] if supplied else donors,
                          'task_mixture': {k: v / mass for k, v in sorted(mixture.items())} if mass else None,
                          'assumption': 'Same role and language share a task mixture; no examples observed for this employee.'
                                        if status == 'role_transfer' else None,
                          'default_action': 'retain_simulator_default' if not mass else None})
    return workforce


def slots(bank, fit_result, config):
    repeats = config.get('repeats', 2)
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be positive')
    budget = Budget(**config.get('budget', {}))
    result = []
    # Round-major order separates same-case repetitions; order is fixed before outcomes.
    for repeat in range(repeats):
        round_slots = []
        for anchor in fit_result['anchors']:
            for match in anchor['matches']:
                public = bank.public(match['task_id'])
                b = asdict(budget)
                b['seconds'] = min(b['seconds'], public.get('budgets', {}).get('time_seconds', b['seconds']))
                ident = hashlib.sha256((anchor['employee_id'] + '\n' + match['task_id']).encode()).hexdigest()[:16]
                round_slots.append({'id': f'{ident}-r{repeat}', 'repeat': repeat,
                                    'employee_id': anchor['employee_id'], 'role': anchor['role'],
                                    'task_id': match['task_id'], 'lineage_group': match['lineage_group'],
                                    'budget': b})
        random.Random(config.get('seed', 1729) + repeat).shuffle(round_slots)
        result.extend(round_slots)
    return result
