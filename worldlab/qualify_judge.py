"""Prospective repeated exact-count controls after a recorded judge contradiction.

This qualifies one frozen criterion and response ordering, not general judgment
accuracy. No solver or learner runs and no original attempt is overwritten.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from scripts.source_world_calibration import read, save, sha
from lifespan.evaluation.budget import ResponsesBudget
from lifespan.evaluation.provider import provider_contract
from .campaign import source_identity
from .qualitative import request_verdict, validate_verdict, VERDICT_SCHEMA, RULES

PATTERN = r'(?i)fig(?:ure|\.)?\s*5\.4'
OUTPUT = 'output/texte_restructure_v3.md'


def qualify(request_path, out, model, base_url):
    payload = read(request_path)
    if payload['criterion']['id'] != 'fig54_exact_count':
        raise ValueError('These controls cover only the diagnosed frozen count criterion')
    text = payload['evidence']['files'][OUTPUT]['text']
    if len(re.findall(PATTERN, text)) != 3:
        raise ValueError('Original positive control must contain exactly three references')
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    cases = [('original-three', text, True),
             ('case-variation-three', re.sub(PATTERN, 'FIGURE 5.4', text), True),
             ('extra-four', text + '\nFig. 5.4\n', False),
             ('missing-two', re.sub(PATTERN, 'Fig. 5.5', text, count=1), False)]
    plan = []
    for repeat in range(3):
        for name, candidate, expected in cases:
            item = deepcopy(payload)
            item['evidence']['files'][OUTPUT] = {'text': candidate, 'sha256': hashlib.sha256(candidate.encode()).hexdigest()}
            plan.append({'id': f'{name}-r{repeat}', 'payload': item, 'expected': expected,
                         'independent_regex_count': len(re.findall(PATTERN, candidate))})
    provider = provider_contract(model, base_url)
    save(out / 'PLAN.json', {'source_request_sha256': sha(request_path), 'source_sha256': source_identity(),
                            'provider': provider, 'schema': VERDICT_SCHEMA, 'rules': RULES, 'slots': plan,
                            'scope': 'Twelve fixed calls on four constructed count controls; not general judge calibration.'})
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'), max_retries=0, timeout=120)
    meter = ResponsesBudget(max_model_calls=12, max_output_tokens=4096, max_total_tokens=400000,
                            provider_contract=provider)
    meter.wrap_client(client)
    rows = []
    try:
        for slot in plan:
            save(out / 'INFLIGHT.json', {'id': slot['id']})
            response = request_verdict(client, provider, slot['payload'], 120)
            raw = {'text': response.output_text, 'status': response.status}
            save(out / (slot['id'] + '-RESPONSE.json'), raw)
            if response.status != 'completed': raise ValueError('Incomplete criterion response')
            verdict = validate_verdict(json.loads(response.output_text), payload['criterion'])
            rows.append({'id': slot['id'], 'expected': slot['expected'], 'verdict': verdict,
                         'correct': verdict['passed'] == slot['expected']})
            save(out / 'PROGRESS.json', {'rows': rows, 'usage': meter.report()})
            (out / 'INFLIGHT.json').unlink()
    finally:
        client.close()
        save(out / 'USAGE.json', meter.report())
    result = {'completed': len(rows), 'correct': sum(r['correct'] for r in rows),
              'all_controls_pass': len(rows) == 12 and all(r['correct'] for r in rows),
              'rows': rows, 'usage': meter.report(), 'plan_sha256': sha(out / 'PLAN.json'),
              'scope': 'Exact-count and decision-ordering diagnostic only. Original study judgments are preserved.'}
    save(out / 'QUALIFICATION.json', result)
    return {k: result[k] for k in ('completed', 'correct', 'all_controls_pass', 'plan_sha256')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-request', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    print(json.dumps(qualify(a.source_request, a.out, a.model, a.base_url), indent=2))
