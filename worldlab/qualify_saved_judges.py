"""Grade saved contexts and pre-grading failures from a stopped development study.

Copies preserve original outputs, including incomplete and failed judgments.
Only the new judge runs. This qualifies completion, metering and audit behavior;
it does not establish judgment accuracy, successful work or a learning effect.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import time

from scripts.source_world_calibration import read, save, sha
from .bank import Bank
from .campaign import source_identity
from .qualitative import FrozenRubricJudge, workspace_evidence
from .artifact_inventory import inventory, verify as verify_inventory


def qualify(bank, judge, study, out, *, concurrency=64, timeout_seconds=1200):
    if not 1 <= concurrency <= 64 or timeout_seconds <= 0:
        raise ValueError('Invalid qualification concurrency or deadline')
    study, out = Path(study).resolve(), Path(out).resolve()
    if out == study or out.is_relative_to(study):
        raise ValueError('Qualification output must be outside the original study')
    out.mkdir(parents=True, exist_ok=False)
    instructions = {}
    for task in bank.rows:
        instructions.setdefault(bank.public(task['id'])['instruction'], []).append(task['id'])
    slots, excluded = [], []
    originals = {p.parent.parent for p in study.glob('worlds/*/*/sessions/*/judging/EVIDENCE.json')}
    for path in study.glob('worlds/*/*/sessions/*/PUBLIC_REQUEST.json'):
        original = path.parent
        if original in originals:
            continue
        receipt_path = original / 'EXECUTION_RECEIPT.json'
        receipt = read(receipt_path) if receipt_path.exists() else {}
        if receipt.get('status') in ('completed', 'budget_exhausted'):
            originals.add(original)
        else:
            excluded.append({'original_attempt': str(original), 'execution_status': receipt.get('status'),
                             'reason': 'No saved judge evidence or gradeable solver receipt; not assigned a score.'})
    for original in sorted(originals):
        evidence_path = original / 'judging/EVIDENCE.json'
        request = read(original / 'PUBLIC_REQUEST.json')
        workspace = Path(request['workspace']).resolve()
        if not workspace.is_relative_to(original):
            raise ValueError('Original workspace escaped its attempt')
        evidence = read(evidence_path) if evidence_path.exists() else None
        if evidence is None:
            instruction = (read(original / 'EMPLOYEE_REQUEST.json')['original_instruction']
                           if (original / 'EMPLOYEE_REQUEST.json').exists() else request['instruction'])
            evidence = {'instruction': instruction, 'files': workspace_evidence(workspace)}
        ids = instructions[evidence['instruction']]
        task_id = read(original / 'ATTEMPT.json')['task_id'] if (original / 'ATTEMPT.json').exists() else None
        if task_id is None and len(ids) == 1:
            task_id = ids[0]
        if task_id not in ids:
            raise ValueError('Cannot bind saved evidence to its original task')
        if not evidence_path.exists():
            evidence['frozen_clock'] = bank.public(task_id).get('frozen_clock')
        files, links = inventory(workspace)
        slot = {'id': f'grade-{len(slots):04d}', 'task_id': task_id,
                'original_attempt': str(original),
                'original_evidence_available': evidence_path.exists(),
                'original_evidence_sha256': sha(evidence_path) if evidence_path.exists() else None,
                'public_request_sha256': sha(original / 'PUBLIC_REQUEST.json'),
                'baseline_sha256': sha(original / 'BASELINE.json'),
                'workspace_files': files, 'workspace_symlinks': links,
                'original_grade_complete': read(original / 'judging/GRADE.json')['grading_complete']
                    if (original / 'judging/GRADE.json').exists() else None}
        dest = out / slot['id']
        dest.mkdir()
        shutil.copytree(workspace, dest / 'workspace', symlinks=True)
        for name in ('BASELINE.json', 'PUBLIC_REQUEST.json', 'EMPLOYEE_REQUEST.json', 'EXECUTION_RECEIPT.json'):
            if (original / name).exists():
                shutil.copyfile(original / name, dest / name)
        if evidence_path.exists():
            shutil.copyfile(evidence_path, dest / 'EVIDENCE.json')
        else:
            # No original verdict is invented: freeze only the new projection
            # of a completed solver's retained output, before the first call.
            save(dest / 'EVIDENCE.json', evidence)
        slot['evidence_sha256'] = sha(dest / 'EVIDENCE.json')
        verify_inventory(workspace, files, links)
        verify_inventory(dest / 'workspace', files, links)
        if ((slot['original_evidence_available'] and slot['evidence_sha256'] != slot['original_evidence_sha256'])
                or sha(dest / 'BASELINE.json') != slot['baseline_sha256']
                or sha(dest / 'PUBLIC_REQUEST.json') != slot['public_request_sha256']):
            raise ValueError('Saved context changed while copying')
        slots.append(slot)
    if not slots:
        raise ValueError('No saved evidence snapshots')
    plan = {'source_sha256': source_identity(), 'study': str(study),
            'study_sha256': sha(study / 'STUDY.json'), 'judge': judge.identity(),
            'concurrency': concurrency, 'max_calls_per_grade': 8,
            'max_tokens_per_grade': 400_000, 'timeout_seconds_per_grade': timeout_seconds,
            'max_reserved_tokens': len(slots) * 400_000, 'slots': slots,
            'excluded_source_attempts': excluded, 'scope': __doc__}
    save(out / 'PLAN.json', plan)
    rows = []

    def run(slot):
        dest = out / slot['id']
        started = time.monotonic()
        row = {'id': slot['id'], 'task_id': slot['task_id'], 'audited': False}
        try:
            grade = judge.grade(slot['task_id'], dest / 'workspace', read(dest / 'BASELINE.json'),
                                dest / 'judging', call_limit=8, token_limit=400_000,
                                timeout_seconds=timeout_seconds)
            row.update(grading_complete=grade['grading_complete'], usage=grade['usage'],
                       recoveries=grade['format_recoveries'], error_type=grade['error_type'])
            if read(dest / 'judging/EVIDENCE.json') != read(dest / 'EVIDENCE.json'):
                raise ValueError('Qualification changed original evidence')
            judge.audit_grade(bank, slot['task_id'], dest / 'workspace', read(dest / 'BASELINE.json'),
                              dest / 'judging', grade)
            row['audited'] = True
        except Exception as exc:
            row['audit_error_type'] = type(exc).__name__
        row['seconds'] = time.monotonic() - started
        save(dest / 'RESULT.json', row)
        return row

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run, slot) for slot in slots]
        for future in as_completed(futures):
            rows.append(future.result())
            save(out / 'PROGRESS.json', {'finished': len(rows), 'planned': len(slots), 'rows': rows})
            print(json.dumps({'finished': len(rows), 'planned': len(slots),
                              'audited': sum(r['audited'] for r in rows)}), flush=True)
    result = {'ok': all(r['audited'] for r in rows), 'planned': len(slots),
              'audited': sum(r['audited'] for r in rows),
              'calls': sum(r.get('usage', {}).get('physical_model_calls', 0) for r in rows),
              'tokens': sum(r.get('usage', {}).get('charged_tokens', 0) for r in rows),
              'recovery_attempts': sum(len(r.get('recoveries', [])) for r in rows),
              'unknown_accounting': sum(not r.get('usage', {}).get('accounting_complete', False) for r in rows),
              'contexts_without_original_evidence': sum(not s['original_evidence_available'] for s in slots),
              'excluded_source_attempts': len(excluded),
              'plan_sha256': sha(out / 'PLAN.json'), 'scope': __doc__}
    save(out / 'QUALIFICATION.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--study', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--concurrency', type=int, default=64)
    p.add_argument('--timeout-seconds', type=int, default=1200)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8011/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    report = qualify(bank, FrozenRubricJudge(bank, a.model, a.base_url), a.study, a.out,
                     concurrency=a.concurrency, timeout_seconds=a.timeout_seconds)
    print(json.dumps(report, indent=2))
    if not report['ok']:
        raise SystemExit(1)
