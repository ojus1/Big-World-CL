"""Freeze then run source-grounded judge controls, with up to 64 concurrent calls.

Every planned response is retained, including wrong labels and unknown usage.
These are dependent development controls, not a general accuracy estimate or
employee performance. Registered source-rule evaluations are frozen separately
from model calls. No response is retried and no study outcome is rewritten.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

from scripts.source_world_calibration import child, read, save, sha
from lifespan.evaluation.provider import provider_contract, validate_contract
from .bank import Bank
from .campaign import source_identity
from .judge_transport import StructuredJudgeBudget, digest, JUDGE_SAMPLING
from .qualitative import parsed_response, request_verdict, verdict_input, mechanical_verdict, mechanical_method
from .semantic_cases import controls
from .verdict_schema import contract


def now():
    return datetime.now(timezone.utc).isoformat()


def execution_method(case):
    return mechanical_method(case['payload']) if mechanical_verdict(case['payload']) is not None else 'model'


def prepare(bank, out, model, base_url, *, repeats=2, concurrency=64):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('Positive repeat count required')
    if type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ValueError('Concurrency must be an integer from 1 through 64')
    cases = controls(bank)
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Nonempty unique semantic controls required')
    for case in cases:
        if not re.fullmatch('[a-z0-9-]+', case['id']) or type(case['expected']) is not bool:
            raise ValueError('Invalid semantic case ID or label')
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    for case in cases:
        save(out / 'cases' / (case['id'] + '.json'), case)
    slots = [{'id': f'r{r:03d}-{c["id"]}', 'case_id': c['id'], 'evaluation_method': execution_method(c),
              'max_reserved_tokens': 2 * len(json.dumps(verdict_input(c['payload']), ensure_ascii=False).encode()) + 16384}
             for r in range(repeats) for c in cases]
    plan = {'prepared_at': now(), 'scope': __doc__,
            'source_sha256': source_identity(),
            'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'provider': provider_contract(model, base_url),
            'concurrency': concurrency, 'request_timeout_seconds': 300,
            'max_output_tokens': 4096, 'sampling': dict(JUDGE_SAMPLING), 'slots': slots,
            'cases': {c['id']: sha(out / 'cases' / (c['id'] + '.json')) for c in cases},
            'pass_rule': 'Every planned case must return a valid verdict matching its predeclared label with known usage. '
                         'One request per model slot; predeclared source-rule slots make no model call. No retries or outcome selection.'}
    save(out / 'PLAN.json', plan)
    save(out / 'PREPARED.json', {'plan_sha256': sha(out / 'PLAN.json')})
    return {'cases': len(cases), 'planned_evaluations': len(slots),
            'planned_calls': sum(s['evaluation_method'] == 'model' for s in slots), 'concurrency': concurrency,
            'plan_sha256': sha(out / 'PLAN.json')}


def load_plan(out):
    out = Path(out).resolve()
    plan = read(out / 'PLAN.json')
    if sha(out / 'PLAN.json') != read(out / 'PREPARED.json')['plan_sha256']:
        raise ValueError('Prepared semantic plan changed')
    if source_identity() != plan['source_sha256']:
        raise ValueError('Use the frozen source checkout for this qualification')
    validate_contract(plan['provider'])
    cases = {}
    for case_id, expected in plan['cases'].items():
        path = child(out, 'cases/' + case_id + '.json')
        if sha(path) != expected:
            raise ValueError('Prepared semantic case changed')
        case = read(path)
        if case['id'] != case_id:
            raise ValueError('Semantic case identity changed')
        cases[case_id] = case
    if plan['sampling'] != JUDGE_SAMPLING:
        raise ValueError('Prepared semantic sampling changed')
    if any(slot['evaluation_method'] != execution_method(cases[slot['case_id']]) for slot in plan['slots']):
        raise ValueError('Prepared semantic execution method changed')
    return out, plan, cases


def run(out, *, client_factory=None):
    out, plan, cases = load_plan(out)
    # Creation is exclusive: a crashed or failed run remains preserved and
    # cannot be retried by calling this entry point again.
    with (out / 'EXECUTION.json').open('x') as handle:
        json.dump({'started_at': now(), 'plan_sha256': sha(out / 'PLAN.json')}, handle)
    provider = plan['provider']

    def execute(slot):
        case = cases[slot['case_id']]
        root = out / 'responses' / slot['id']
        root.mkdir(parents=True, exist_ok=False)
        payload = case['payload']
        save(root / 'REQUEST.json', payload)
        save(root / 'INFLIGHT.json', {'started_at': now()})
        meter = StructuredJudgeBudget(structured_contracts=[contract(payload['criterion']['id'], payload['evidence']['files'])],
            max_model_calls=1, max_output_tokens=plan['max_output_tokens'],
            max_total_tokens=slot['max_reserved_tokens'], provider_contract=provider)
        client = None; started = time.monotonic(); error = None; verdict = None
        try:
            if slot['evaluation_method'] != 'model':
                client = None
            elif client_factory is None:
                from openai import OpenAI
                client = OpenAI(base_url=provider['base_url'], api_key=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'),
                                max_retries=0, timeout=plan['request_timeout_seconds'])
            else:
                client = client_factory()
            if client is not None:
                meter.wrap_client(client)
            response = request_verdict(client, provider, payload, plan['request_timeout_seconds'])
            record = {'text': response.output_text, 'status': response.status,
                      'evaluation_method': getattr(response, 'evaluation_method', 'model')}
            # Keep the complete SDK response when available, as well as the
            # normalized fields consumed by the original verdict parser.
            if callable(getattr(response, 'model_dump', None)):
                record['raw'] = response.model_dump(mode='json')
            save(root / 'RESPONSE.json', record)
            verdict = parsed_response(record, payload['criterion'], payload['evidence']['files'])
        except Exception as exc:
            error = type(exc).__name__
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as exc:
                    error = error or type(exc).__name__
        usage = meter.report()
        row = {'id': slot['id'], 'case_id': slot['case_id'], 'expected': case['expected'],
               'evaluation_method': slot['evaluation_method'],
               'valid': verdict is not None, 'actual': verdict['passed'] if verdict else None,
               'correct': verdict is not None and verdict['passed'] == case['expected'],
               'error_type': error, 'seconds': time.monotonic() - started, 'usage': usage}
        save(root / 'RESULT.json', row)
        (root / 'INFLIGHT.json').unlink()
        return row

    started = time.monotonic(); results = []
    with ThreadPoolExecutor(max_workers=plan['concurrency']) as pool:
        futures = [pool.submit(execute, slot) for slot in plan['slots']]
        for future in as_completed(futures):
            results.append(future.result())
            save(out / 'PROGRESS.json', {'completed': len(results), 'planned': len(plan['slots']),
                 'matching_labels': sum(r['correct'] for r in results), 'observed_at': now()})
    report = audit(out)
    report.update(completed_at=now(), wall_seconds=time.monotonic() - started)
    save(out / 'QUALIFICATION.json', report)
    return report


def audit(out):
    """Recompute label agreement and accounting from the retained requests/results."""
    out, plan, cases = load_plan(out)
    expected_ids = {slot['id'] for slot in plan['slots']}
    if {p.name for p in (out / 'responses').iterdir() if p.is_dir()} != expected_ids:
        raise ValueError('Missing or unplanned semantic response slot')
    rows = []
    for slot in plan['slots']:
        root = out / 'responses' / slot['id']; case = cases[slot['case_id']]
        if (root / 'INFLIGHT.json').exists():
            raise ValueError('Unfinished semantic request')
        if read(root / 'REQUEST.json') != case['payload']:
            raise ValueError('Semantic request differs from the prepared evidence')
        row = read(root / 'RESULT.json'); usage = row['usage']; ops = usage['operations']
        if (row['id'] != slot['id'] or row['case_id'] != case['id'] or row['expected'] != case['expected']
                or row['evaluation_method'] != slot['evaluation_method']
                or any(type(row[k]) is not bool for k in ('expected', 'valid', 'correct'))
                or usage['provider_contract'] != plan['provider']
                or usage['physical_model_calls'] != len(ops) or len(ops) > 1
                or usage['charged_tokens'] != sum(r['charged_tokens'] for r in ops)
                or usage['reported_tokens'] != sum(r['total_tokens'] or 0 for r in ops)
                or usage['accounting_complete'] != all(r['accounting'] == 'reported' for r in ops)):
            raise ValueError('Semantic result identity or cost differs from declared execution')
        verdict = None; response = None
        if (root / 'RESPONSE.json').exists():
            response = read(root / 'RESPONSE.json')
            if response['evaluation_method'] != slot['evaluation_method']:
                raise ValueError('Semantic response execution method changed')
            try:
                verdict = parsed_response(response, case['payload']['criterion'], case['payload']['evidence']['files'])
            except (ValueError, TypeError):
                pass
        valid = verdict is not None
        if (row['valid'] != valid or row['actual'] != (verdict['passed'] if valid else None)
                or row['correct'] != (valid and verdict['passed'] == case['expected'])):
            raise ValueError('Recorded verdict differs from the retained response')
        structure = digest(contract(case['payload']['criterion']['id'], case['payload']['evidence']['files']))
        if usage['registered_structured_output_sha256'] != [structure]:
            raise ValueError('Semantic schema differs from the prepared criterion')
        for op in ops:
            if (op['request_structured_outputs_sha256'] != structure
                    or op['request_sampling'] != plan['sampling']
                    or op['request_input_sha256'] != digest(verdict_input(case['payload']))
                    or op['output_cap'] != plan['max_output_tokens']):
                raise ValueError('Physical semantic request differs from the prepared contract')
            if op['accounting'] == 'reported' and (
                    any(type(op[k]) is not int or op[k] < 0 for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    or op['input_tokens'] + op['output_tokens'] != op['total_tokens']
                    or op['charged_tokens'] != op['total_tokens']):
                raise ValueError('Reported semantic token accounting is inconsistent')
        if slot['evaluation_method'] == 'model':
            complete = (len(ops) == 1 and usage['accounting_complete'] and not usage['stopped']
                        and ops[0]['accounting'] == 'reported' and ops[0]['status'] == 'completed'
                        and response is not None and ops[0]['provider_response_status'] == response['status'])
        else:
            expected_verdict = mechanical_verdict(case['payload'])
            if response is not None and json.loads(response['text']) != expected_verdict:
                raise ValueError('Source-rule verdict differs from the prepared evidence')
            complete = (not ops and usage['accounting_complete'] and not usage['stopped']
                        and response is not None and response['status'] == 'completed')
        rows.append({'id': slot['id'], 'case_id': case['id'], 'family': case['family'],
                     'evaluation_method': slot['evaluation_method'],
                     'correct': row['correct'], 'valid': valid,
                     'accounting_complete': usage['accounting_complete'], 'request_completed': bool(complete),
                     'error_type': row['error_type'], 'seconds': row['seconds'],
                     'result_sha256': sha(root / 'RESULT.json'), 'model_calls': len(ops),
                     'charged_tokens': usage['charged_tokens'], 'reported_tokens': usage['reported_tokens']})
    report = {'ok': all(r['correct'] and r['request_completed'] and r['error_type'] is None for r in rows),
            'planned': len(plan['slots']), 'completed': len(rows),
            'planned_model_calls': sum(s['evaluation_method'] == 'model' for s in plan['slots']),
            'valid': sum(r['valid'] for r in rows), 'matching_labels': sum(r['correct'] for r in rows),
            'unknown_accounting': sum(not r['accounting_complete'] for r in rows),
            'undispatched': sum(r['evaluation_method'] == 'model' and r['model_calls'] == 0 for r in rows),
            'source_rule_evaluations': sum(r['evaluation_method'] != 'model' for r in rows),
            'model_calls': sum(r['model_calls'] for r in rows),
            'charged_tokens': sum(r['charged_tokens'] for r in rows),
            'reported_tokens': sum(r['reported_tokens'] for r in rows),
            'rows': rows, 'plan_sha256': sha(out / 'PLAN.json'), 'scope': __doc__,
            'general_accuracy_claim': False, 'learning_effect_claim': False}
    if (out / 'QUALIFICATION.json').exists():
        saved = read(out / 'QUALIFICATION.json')
        if any(saved.get(k) != v for k, v in report.items()):
            raise ValueError('Qualification summary differs from retained evidence')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--bank', type=Path, required=True)
    prep.add_argument('--model', required=True)
    prep.add_argument('--base-url', required=True)
    prep.add_argument('--repeats', type=int, default=2)
    prep.add_argument('--concurrency', type=int, default=64)
    for cmd in (prep, commands.add_parser('run'), commands.add_parser('audit')):
        cmd.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        report = prepare(Bank(args.bank), args.out, args.model, args.base_url,
                         repeats=args.repeats, concurrency=args.concurrency)
    elif args.command == 'run':
        report = run(args.out)
    else:
        report = audit(args.out)
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
    return 0 if report.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
