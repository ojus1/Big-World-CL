"""Replay every saved criterion request from selected stopped development studies.

Only the judge runs. Original work, judgments, failures and costs are preserved.
This checks completion and response contracts, not general judgment accuracy.
"""
import argparse
import json
import os
from pathlib import Path
import time
from scripts.source_world_calibration import read, save, sha
from lifespan.evaluation.provider import provider_contract
from .campaign import source_identity
from .judge_transport import StructuredJudgeBudget, digest
from .qualitative import request_verdict, validate_verdict, RULES
from .verdict_schema import contract


def qualify(studies, out, model, base_url):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    slots, parents, constraints = [], [], {}
    reservation = 0
    for study in studies:
        study = Path(study).resolve()
        parents.append({'path': str(study), 'study_sha256': sha(study / 'STUDY.json')})
        for source in sorted((study / 'worlds').glob('*/*/sessions/*/judging/REQUEST-*.json')):
            payload = read(source)
            structure = contract(payload['criterion']['id'])
            constraints[digest(structure)] = structure
            key = f'criterion-{len(slots):04d}'
            save(out / 'requests' / (key + '.json'), payload)
            slots.append({'id': key, 'source_request': str(source), 'source_sha256': sha(source),
                          'copied_sha256': sha(out / 'requests' / (key + '.json')),
                          'criterion_id': payload['criterion']['id']})
            reservation += 2 * len(json.dumps(payload, ensure_ascii=False).encode()) + 16384
    if not slots:
        raise ValueError('No saved criterion requests found')
    provider = provider_contract(model, base_url)
    plan = {'source_sha256': source_identity(), 'parents': parents, 'slots': slots,
            'provider': provider, 'rules': RULES, 'structured_contracts': list(constraints.values()),
            'max_reserved_tokens': reservation,
            'scope': 'All available requests from the named stopped studies; dependent development contexts. Completion qualification only.'}
    save(out / 'PLAN.json', plan)
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'), max_retries=0, timeout=120)
    meter = StructuredJudgeBudget(structured_contracts=list(constraints.values()), max_model_calls=len(slots),
                                  max_output_tokens=4096, max_total_tokens=reservation, provider_contract=provider)
    meter.wrap_client(client)
    rows, error = [], None
    started = time.monotonic()
    try:
        for slot in slots:
            save(out / 'INFLIGHT.json', {'id': slot['id']})
            payload = read(out / 'requests' / (slot['id'] + '.json'))
            response = request_verdict(client, provider, payload, 120)
            save(out / 'responses' / (slot['id'] + '.json'), {'text': response.output_text, 'status': response.status})
            if response.status != 'completed': raise ValueError('Incomplete judge response')
            verdict = validate_verdict(json.loads(response.output_text), payload['criterion'])
            rows.append({'id': slot['id'], 'valid': True, 'passed': verdict['passed'],
                         'evidence_chars': len(verdict['evidence']), 'reasoning_chars': len(verdict['reasoning'])})
            save(out / 'PROGRESS.json', {'rows': rows, 'planned': len(slots), 'usage': meter.report()})
            (out / 'INFLIGHT.json').unlink()
            if len(rows) % 10 == 0:
                print(json.dumps({'completed': len(rows), 'planned': len(slots), 'seconds': time.monotonic() - started}), flush=True)
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        client.close()
        report = {'ok': len(rows) == len(slots) and error is None, 'completed': len(rows), 'planned': len(slots),
                  'error_type': error, 'usage': meter.report(), 'plan_sha256': sha(out / 'PLAN.json'), 'scope': plan['scope']}
        save(out / 'QUALIFICATION.json', report)
    return {k: report[k] for k in ('ok', 'completed', 'planned', 'error_type', 'plan_sha256')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--studies', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    print(json.dumps(qualify(a.studies, a.out, a.model, a.base_url), indent=2))
