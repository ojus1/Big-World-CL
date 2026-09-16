#!/usr/bin/env python3
"""Fresh, immutable qualification of QA fixes; never rewrite historical grades."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.source_world_calibration import read, save, sha
from worldlab.artifact_inventory import inventory, verify
from worldlab.bank import Bank
from worldlab.campaign import source_identity
from worldlab.qualitative import FrozenRubricJudge, workspace_evidence, request_verdict, parsed_response
from worldlab.judge_transport import StructuredJudgeBudget
from worldlab.verdict_schema import contract
from worldlab.supplier_notes import COLUMNS, OUTPUT, check

MODEL = 'Qwen/Qwen3.8-Flash-Next-FP8'
ENDPOINT = 'http://127.0.0.1:8011/v1'


def runtime():
    model = json.load(urllib.request.urlopen('http://127.0.0.1:8002/v1/models', timeout=15))
    gateway = json.load(urllib.request.urlopen('http://127.0.0.1:8011/status', timeout=15))
    if [r['id'] for r in model['data']] != [MODEL] or gateway['llm_concurrency'] != 64 or gateway['upstream'] != 'http://127.0.0.1:8002':
        raise ValueError('Model or concurrency differs from authorized serving setup')
    return {'at': datetime.now(timezone.utc).isoformat(), 'models': model, 'gateway': gateway}


def controls(bank, judge, out):
    task = 'internal/euw_v1_de_013_en_bridge'
    notes = [
        'Audit BF-2024-0317-01 is an open Major finding; the required re-inspection result is still missing, so K1 is not fulfilled.',
        'The 2024-02-10 certificate is four months before the 2024-06-14 contract amendment, within the handbook 12-month window.',
        'Insurance is EUR 5 million against the required EUR 10 million: 50 percent, meeting only the partial-fulfilment threshold.',
        'Contract amendment No. 7 is dated 2024-06-14 and bears both parties signatures, satisfying the signature/date requirement.',
        'Scope memo SCO-2024-0528 is dated 2024-05-28 and signed by T. Brandt, documenting the 316L scope change.',
    ]
    # The first four conditions require semantic inference, 16 draws each.
    # Mechanical controls are additional, and should use no model calls.
    conditions = [('grounded', True), ('irrelevant', False), ('empty_notes', False), ('wrong_language', False),
                  ('over_200', False), ('malformed_csv', False)]
    slots = []
    for name, expected in conditions:
        for repeat in range(16 if name in ('grounded', 'irrelevant', 'empty_notes', 'wrong_language') else 4):
            identifier = f'{name}-{repeat:02d}'; directory = out / identifier
            bank.stage(task, directory / 'workspace')
            workspace = directory / 'workspace'; (workspace / 'output').mkdir()
            values = list(notes)
            if name == 'irrelevant': values = ['The sky is blue and breakfast is delicious.'] * 5
            if name == 'empty_notes': values = [''] * 5
            if name == 'wrong_language': values = ['La note explique le résultat en français, sans justification tirée des preuves.'] * 5
            if name == 'over_200': values[0] = 'x' * 201
            stream = io.StringIO(newline=''); writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            for i, value in enumerate(values, 1):
                writer.writerow([f'K{i}', f'Criterion {i}', 'nicht_erfuellt' if i == 1 else
                                 'teilweise_erfuellt' if i == 3 else 'erfuellt', 'See note and supplied sources', value])
            (workspace / OUTPUT).write_bytes((stream.getvalue() if name != 'malformed_csv' else '"unterminated').encode())
            row = bank.by_id[task]
            criterion = next(c for c in read(bank.root / row['private_directory'] / 'rubric.json')['criteria'] if c['id'] == 'R7')
            payload = {'criterion': criterion, 'ambiguities': [], 'evaluation_guidance': [],
                       'evidence': {'instruction': bank.public(task)['instruction'], 'files': workspace_evidence(workspace)}}
            save(directory / 'REQUEST.json', payload)
            slots.append({'id': identifier, 'expected': expected, 'condition': name,
                          'request_sha256': sha(directory / 'REQUEST.json'), 'mechanical': check(payload)})
    save(out / 'PLAN.json', {'source_sha256': source_identity(), 'judge': judge.identity(), 'slots': slots,
         'max_parallel': 64, 'model_controls': 64, 'mechanical_controls': 8,
         'scope': 'Manually constructed R7 controls on development source evidence. Repetitions measure stability, not independent tasks.'})

    def run(slot):
        from openai import OpenAI
        directory = out / slot['id']; payload = read(directory / 'REQUEST.json')
        meter = StructuredJudgeBudget(structured_contracts=[contract('R7', payload['evidence']['files'])],
            max_model_calls=1, max_output_tokens=4096, max_total_tokens=400000, provider_contract=judge.provider)
        row = {'id': slot['id'], 'expected': slot['expected'], 'ok': False}
        with OpenAI(base_url=ENDPOINT, api_key=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'), max_retries=0, timeout=300) as client:
            meter.wrap_client(client)
            try:
                response = request_verdict(client, judge.provider, payload, 300)
                record = {'status': response.status, 'text': response.output_text,
                          'evaluation_method': getattr(response, 'evaluation_method', 'model')}
                save(directory / 'RESPONSE.json', record)
                verdict = parsed_response(record, payload['criterion'], payload['evidence']['files'])
                row.update(ok=verdict['passed'] is slot['expected'], verdict=verdict)
            except Exception as exc:
                row['error_type'] = type(exc).__name__
        row['usage'] = meter.report()
        row['ok'] = row['ok'] and row['usage']['accounting_complete']
        save(directory / 'RESULT.json', row)
        return row
    with ThreadPoolExecutor(max_workers=64) as pool:
        rows = list(pool.map(run, slots))
    report = {'ok': all(r['ok'] for r in rows), 'rows': rows, 'planned': len(rows),
              'matched': sum(r['ok'] for r in rows), 'calls': sum(r['usage']['physical_model_calls'] for r in rows),
              'tokens': sum(r['usage']['charged_tokens'] for r in rows), 'plan_sha256': sha(out / 'PLAN.json')}
    save(out / 'REPORT.json', report)
    return report


def regrade(bank, judge, old, out):
    paths = ['worlds/seed-401/no_learning/sessions/d000-communications-fr-003-000',
             'worlds/seed-401/no_learning/sessions/d002-research-en-001-000',
             'worlds/seed-401/no_learning/sessions/d006-communications-de-003-000',
             'worlds/seed-421/skillopt_sleep/learning/d010-communications-de-003/replay-005',
             'worlds/seed-421/skillopt_sleep/sessions/d002-communications-fr-001-000']
    slots = []
    by_instruction = {bank.public(r['id'])['instruction']: r['id'] for r in bank.rows}
    for i, relative in enumerate(paths):
        source = old / relative; directory = out / f'case-{i:02d}'
        request = read(source / 'PUBLIC_REQUEST.json'); workspace = Path(request['workspace'])
        original = read(source / 'EMPLOYEE_REQUEST.json')['original_instruction']
        if not workspace.is_relative_to(source): raise ValueError('Historical workspace escaped its attempt')
        files, links = inventory(workspace)
        shutil.copytree(workspace, directory / 'workspace', symlinks=True)
        verify(directory / 'workspace', files, links)
        baseline = read(source / 'BASELINE.json'); save(directory / 'BASELINE.json', baseline)
        slots.append({'id': directory.name, 'source': str(source), 'source_workspace': str(workspace),
            'task_id': by_instruction[original], 'files': files, 'symlinks': links,
            'source_execution_receipt_sha256': sha(source / 'EXECUTION_RECEIPT.json'),
            'source_baseline_sha256': sha(source / 'BASELINE.json')})
    save(out / 'PLAN.json', {'source_sha256': source_identity(), 'judge': judge.identity(), 'slots': slots,
         'scope': 'Copied frozen failed-run outputs, fresh grading contract. No solver rerun or historical score rewrite.'})
    def run(slot):
        directory = out / slot['id']; baseline = read(directory / 'BASELINE.json')
        grade = judge.grade(slot['task_id'], directory / 'workspace', baseline, directory / 'judging')
        judge.audit_grade(bank, slot['task_id'], directory / 'workspace', baseline, directory / 'judging', grade)
        verify(Path(slot['source_workspace']), slot['files'], slot['symlinks'])
        row = {'id': slot['id'], 'audited': True, 'quality_score': grade['quality_score'], 'success': grade['success'],
               'feedback': grade['feedback'], 'criteria': grade['criteria'], 'usage': grade['usage']}
        if slot['id'] == 'case-03':
            assert grade['evaluation_method'] == 'invalid_candidate_artifact' and grade['usage']['physical_model_calls'] == 0
        if slot['id'] == 'case-04':
            assert grade['quality_score'] == 0 and 'build_planning.py' in grade['feedback']
        save(directory / 'RESULT.json', row)
        return row
    with ThreadPoolExecutor(max_workers=64) as pool:
        rows = list(pool.map(run, slots))
    report = {'ok': all(r['audited'] for r in rows), 'rows': rows, 'plan_sha256': sha(out / 'PLAN.json'),
              'calls': sum(r['usage']['physical_model_calls'] for r in rows),
              'tokens': sum(r['usage']['charged_tokens'] for r in rows)}
    save(out / 'REPORT.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, required=True)
    parser.add_argument('--old-study', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']).strip():
        raise ValueError('Qualification requires clean frozen source')
    args.out.mkdir(parents=True, exist_ok=False)
    before = runtime(); save(args.out / 'RUNTIME-BEFORE.json', before)
    bank = Bank(args.bank); judge = FrozenRubricJudge(bank, MODEL, ENDPOINT)
    save(args.out / 'PROVENANCE.json', {'commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
         'source_sha256': source_identity(), 'operator_sha256': sha(Path(__file__)), 'judge': judge.identity()})
    results = {'controls': controls(bank, judge, args.out / 'controls'),
               'regrade': regrade(bank, judge, args.old_study, args.out / 'regrade')}
    after = runtime(); save(args.out / 'RUNTIME-AFTER.json', after)
    report = {'ok': all(r['ok'] for r in results.values()),
              'results': {k: {x: v for x, v in r.items() if x != 'rows'} for k, r in results.items()},
              'gateway_instance_unchanged': before['gateway']['instance_id'] == after['gateway']['instance_id']}
    report['ok'] &= report['gateway_instance_unchanged']
    save(args.out / 'REPORT.json', report)
    files, links = inventory(args.out, exclude=('FILES.json',))
    save(args.out / 'FILES.json', {'files': files, 'symlinks': links})
    print(json.dumps(report, indent=2))
    if not report['ok']: raise SystemExit(1)


if __name__ == '__main__': main()
