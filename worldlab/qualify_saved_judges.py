"""Grade every saved evidence snapshot from a stopped development study.

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
from .qualitative import FrozenRubricJudge


def qualify(bank, judge, study, out, *, concurrency=64, timeout_seconds=1200):
    if not 1 <= concurrency <= 64 or timeout_seconds <= 0:
        raise ValueError('Invalid qualification concurrency or deadline')
    study, out = Path(study).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    instructions = {}
    for task in bank.rows:
        instructions.setdefault(bank.public(task['id'])['instruction'], []).append(task['id'])
    slots = []
    for evidence_path in sorted(study.glob('worlds/*/*/sessions/*/judging/EVIDENCE.json')):
        original = evidence_path.parent.parent
        evidence = read(evidence_path)
        ids = instructions[evidence['instruction']]
        task_id = read(original / 'ATTEMPT.json')['task_id'] if (original / 'ATTEMPT.json').exists() else None
        if task_id is None and len(ids) == 1:
            task_id = ids[0]
        if task_id not in ids:
            raise ValueError('Cannot bind saved evidence to its original task')
        request = read(original / 'PUBLIC_REQUEST.json')
        workspace = Path(request['workspace']).resolve()
        if not workspace.is_relative_to(original):
            raise ValueError('Original workspace escaped its attempt')
        source_files = list(workspace.rglob('*'))
        if any(p.is_symlink() for p in source_files):
            raise ValueError('Symlink in saved workspace')
        inventory = {str(p.relative_to(workspace)): sha(p) for p in source_files if p.is_file()}
        slot = {'id': f'grade-{len(slots):04d}', 'task_id': task_id,
                'original_attempt': str(original), 'evidence_sha256': sha(evidence_path),
                'baseline_sha256': sha(original / 'BASELINE.json'), 'workspace_files': inventory,
                'original_grade_complete': read(original / 'judging/GRADE.json')['grading_complete']
                    if (original / 'judging/GRADE.json').exists() else None}
        dest = out / slot['id']
        dest.mkdir()
        shutil.copytree(workspace, dest / 'workspace')
        for name in ('BASELINE.json', 'judging/EVIDENCE.json'):
            shutil.copyfile(original / name, dest / Path(name).name)
        for name, digest in inventory.items():
            if sha(workspace / name) != digest or sha(dest / 'workspace' / name) != digest:
                raise ValueError('Saved workspace changed while copying')
        if sha(dest / 'EVIDENCE.json') != slot['evidence_sha256'] or sha(dest / 'BASELINE.json') != slot['baseline_sha256']:
            raise ValueError('Saved context changed while copying')
        slots.append(slot)
    if not slots:
        raise ValueError('No saved evidence snapshots')
    plan = {'source_sha256': source_identity(), 'study': str(study),
            'study_sha256': sha(study / 'STUDY.json'), 'judge': judge.identity(),
            'concurrency': concurrency, 'max_calls_per_grade': 8,
            'max_tokens_per_grade': 400_000, 'timeout_seconds_per_grade': timeout_seconds,
            'max_reserved_tokens': len(slots) * 400_000, 'slots': slots, 'scope': __doc__}
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
