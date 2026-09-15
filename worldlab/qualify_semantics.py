"""Source-grounded semantic controls for the production rubric judge.

Constructed positive/negative outputs are never solver results or learning data.
Labels follow the corrected public/r3 contract, including optional A6 coverage.
This is one-family qualification, not general professional-quality calibration.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from scripts.source_world_calibration import child, read, save, sha
from .bank import Bank
from .campaign import source_identity
from .judge_transport import StructuredJudgeBudget
from .qualitative import FrozenRubricJudge, request_verdict, validate_verdict, RULES
from .verdict_schema import contract

TASK = 'internal/euw_fr_003_en_bridge'
PROSE = '''## Fiscal
Income-tax reduction through deductible donations requires donations >= 100 CHF/year.
Cultural-activity VAT exemption requires revenue strictly below 100 000 CHF.

## Administrative
Access to cantonal grants requires recognized association status. Collective
representation before authorities requires at least 5 members.

## Network
Introduction to partner galleries requires active membership of at least 12 months.

These benefits and their conditions come from fiche_avantages.csv, which takes
precedence over conflicting meeting notes. They are not unconditional guarantees.
'''


def controls(bank):
    row = bank.by_id[TASK]
    definition = bank.private_definition(TASK)
    rubric = read(child(bank.root, row['private_directory']) / 'rubric.json')
    criteria = {c['id']: c for c in rubric['criteria']}
    if set(criteria) != {'Q01', 'Q02', 'Q03', 'Q04'} or 'if included' not in criteria['Q02']['requirement']:
        raise ValueError('Semantic controls require the source-corrected optional-benefit contract')
    expected = next(c['expected'] for c in definition['checks'] if c['id'] == 'annexe_faits_json')
    facts = [deepcopy(x) for x in expected if x['id'] in ['A1', 'A2', 'A3', 'A4', 'A5']]
    if [f['id'] for f in facts] != ['A1', 'A2', 'A3', 'A4', 'A5'] or facts[0]['condition'] != 'Donations >= 100 CHF/year':
        raise ValueError('Frozen source fact assumptions changed')
    files = {}
    directory = child(bank.root, row['public_directory'])
    for source in sorted(directory.rglob('*')):
        if not source.is_file() or source.name == 'task.json': continue
        files[str(source.relative_to(directory))] = source.read_text()
    candidates = []

    def add(name, criterion, passed, rationale, prose=PROSE, appendix=None):
        texts = {**files, 'output/synthese_avantages.md': prose,
                 'output/annexe_faits.json': json.dumps(facts if appendix is None else appendix, ensure_ascii=False, indent=2)}
        evidence = {'instruction': bank.public(TASK)['instruction'],
                    'frozen_clock': bank.public(TASK).get('frozen_clock'),
                    'files': {k: {'text': v, 'sha256': hashlib.sha256(v.encode()).hexdigest()} for k, v in texts.items()}}
        candidates.append({'id': name, 'expected': passed, 'label_rationale': rationale,
                           'payload': {'criterion': criteria[criterion], 'ambiguities': rubric.get('ambiguities', []),
                                       'evaluation_guidance': rubric.get('evaluation_guidance', []), 'evidence': evidence}})

    for criterion in sorted(criteria):
        add('valid-five-benefits-' + criterion.lower(), criterion, True,
            'A1-A5 and their source conditions are preserved. The corrected r3 contract makes the notes-only workshop optional.')
    paraphrased = deepcopy(facts); paraphrased[0]['condition'] = 'Annual donations of at least CHF 100'
    add('valid-semantic-paraphrase', 'Q03', True,
        'The public task does not bind ordinary condition wording; at least 100 is equivalent to >=100.', appendix=paraphrased)
    wrong = deepcopy(facts); wrong[0]['condition'] = 'Donations < 100 CHF/year'
    add('reversed-donation-boundary', 'Q03', False,
        'CSV and Q03 require donations at least 100 CHF/year, not below 100.',
        PROSE.replace('>= 100', '< 100'), wrong)
    wrong = deepcopy(facts); wrong[1]['condition'] = 'Revenue <= 100 000 CHF'
    add('inclusive-vat-boundary', 'Q03', False,
        'CSV and Q03 require revenue strictly below 100000; equality is not eligible.',
        PROSE.replace('strictly below', 'at most'), wrong)
    wrong = deepcopy(facts); wrong[3]['condition'] = 'Active membership >= 6 months'
    add('shortened-membership', 'Q03', False,
        'CSV and Q03 require at least 12 months, not 6.', PROSE.replace('12 months', '6 months'), wrong)
    wrong = deepcopy(facts); wrong.append({'id': 'A7', 'categorie': 'fiscal',
        'avantage': 'Guaranteed annual grant of 10000 CHF', 'condition': 'Not specified', 'source_fichier': 'fiche_avantages.csv'})
    add('invented-guarantee', 'Q02', False,
        'No input supplies a guaranteed 10000 CHF annual grant; Q02 prohibits invented benefits and guarantees.',
        PROSE + '\nEvery member also receives a guaranteed annual grant of 10000 CHF.\n', wrong)
    add('reversed-appendix-order', 'Q04', False,
        'The public task and Q04 require ascending id order.', appendix=list(reversed(facts)))
    add('missing-network-heading', 'Q01', False,
        'The exact required ## Network heading is absent.', PROSE.replace('## Network', 'Gallery contacts'))
    return candidates


def qualify(bank, out, model, base_url, repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('Positive repeat count required')
    cases = controls(bank)
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    judge = FrozenRubricJudge(bank, model, base_url)
    provider = judge.provider
    structures = [contract(c['payload']['criterion']['id']) for c in cases[:4]]
    slots = [{'id': f'r{r}-{c["id"]}', 'case_id': c['id'], 'expected': c['expected']}
             for r in range(repeats) for c in cases]
    for c in cases: save(out / 'cases' / (c['id'] + '.json'), c)
    reserve = sum(2 * len(json.dumps(c['payload'], ensure_ascii=False).encode()) + 16384 for c in cases) * repeats
    save(out / 'PLAN.json', {'bank_manifest_sha256': bank.verification['manifest_sha256'],
        'definition_sha256': bank.by_id[TASK]['definition_sha256'], 'rubric_sha256': bank.by_id[TASK]['rubric_sha256'],
        'source_sha256': source_identity(), 'judge': judge.identity(), 'rules': RULES, 'slots': slots,
        'case_sha256': {c['id']: sha(out / 'cases' / (c['id'] + '.json')) for c in cases},
        'max_reserved_tokens': reserve, 'scope': __doc__,
        'pass_rule': 'Every predeclared label must match. Repeats are dependent; no general accuracy inference.'})
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'), max_retries=0, timeout=120)
    meter = StructuredJudgeBudget(structured_contracts=structures, max_model_calls=len(slots), max_output_tokens=4096,
                                  max_total_tokens=reserve, provider_contract=provider)
    meter.wrap_client(client)
    by_id = {c['id']: c for c in cases}; results = []; error = None
    try:
        for slot in slots:
            save(out / 'INFLIGHT.json', slot)
            payload = by_id[slot['case_id']]['payload']
            response = request_verdict(client, provider, payload, 120)
            save(out / 'responses' / (slot['id'] + '.json'), {'text': response.output_text, 'status': response.status})
            if response.status != 'completed': raise ValueError('Incomplete semantic control response')
            verdict = validate_verdict(json.loads(response.output_text), payload['criterion'])
            results.append({**slot, 'actual': verdict['passed'], 'correct': verdict['passed'] == slot['expected']})
            save(out / 'PROGRESS.json', {'rows': results, 'usage': meter.report()})
            (out / 'INFLIGHT.json').unlink()
            print(json.dumps(results[-1]), flush=True)
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        client.close()
        result = {'ok': len(results) == len(slots) and all(r['correct'] for r in results) and error is None,
                  'completed': len(results), 'planned': len(slots), 'correct': sum(r['correct'] for r in results),
                  'errors_by_case': dict(Counter(r['case_id'] for r in results if not r['correct'])),
                  'error_type': error, 'usage': meter.report(), 'plan_sha256': sha(out / 'PLAN.json'), 'scope': __doc__}
        save(out / 'QUALIFICATION.json', result)
    return {k:v for k,v in result.items() if k != 'usage'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8011/v1')
    a = p.parse_args()
    print(json.dumps(qualify(Bank(a.bank), a.out, a.model, a.base_url), indent=2))
