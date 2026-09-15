"""One fresh native JobBench task and a predeclared missing-output judge control.

Run as a module from a clean, frozen checkout. No study results or deployed
skills are updated. A completed task may score zero; infrastructure qualification
does not require favorable model outcomes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.request

from scripts.source_world_calibration import read, save, sha
from worldlab.attempts import execute_task
from worldlab.audit_worlds import audit_attempt
from worldlab.bank import Bank
from worldlab.campaign import SEED_SKILL, source_identity
from worldlab.contracts import Budget, validate_grade
from worldlab.jobbench import SourceRubricJudge
from worldlab.jobbench_capabilities import ReviewedOfflineHermes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', required=True, type=Path)
    p.add_argument('--hermes-root', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--model', required=True); p.add_argument('--base-url', required=True)
    p.add_argument('--gateway-status-url', default='http://127.0.0.1:8011/status')
    p.add_argument('--task-id', default='jobbench/web_administrators/task1')
    args = p.parse_args()
    out = args.out.resolve()
    if out.exists(): raise ValueError('Use a fresh qualification destination')
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('Qualification requires a clean frozen checkout')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    bank = Bank(args.bank)
    if bank.by_id[args.task_id]['partition'] != 'calibration_train':
        raise ValueError('This development qualification only uses training tasks')
    harness = ReviewedOfflineHermes(args.hermes_root, args.model, args.base_url)
    judge = SourceRubricJudge(bank, args.model, args.base_url)
    reasons = harness.unsupported(bank.public(args.task_id)) + judge.unsupported(bank.public(args.task_id))
    if reasons: raise ValueError('; '.join(reasons))
    gateway = json.load(urllib.request.urlopen(args.gateway_status_url, timeout=15))
    if gateway['llm_concurrency'] != 64 or gateway['retries'] != 0:
        raise ValueError('Qualification requires the shared 64-slot, zero-retry inference gateway')
    budget = Budget(model_calls=32, output_tokens=8192, total_tokens=500_000, seconds=900)
    plan = {'at': datetime.now(timezone.utc).isoformat(), 'commit': commit,
            'source_sha256': source_identity(), 'operator_sha256': sha(Path(__file__)),
            'task_id': args.task_id, 'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'harness': harness.identity(), 'judge': judge.identity(), 'budget': asdict(budget),
            'judge_tokens_per_case': judge.max_tokens, 'judge_calls_per_case': judge.max_model_calls,
            'task_and_grading_timeout_seconds': 1200, 'negative_control_timeout_seconds': 300,
            'parallel_cases': 2, 'gateway_before': gateway, 'skill': SEED_SKILL,
            'reservation_tokens': budget.total_tokens + 2 * judge.max_tokens,
            'controls': {'native': 'Require completed metered execution and offline audit; score unconstrained.',
                         'missing_outputs': 'Original public inputs only; every original rubric must fail.'},
            'scope': 'Adapter qualification on one training task. No learning, final outcomes, statistical effect or official score equivalence.'}
    save(out / 'PLAN.json', plan)
    save(out / 'PREPARED.json', {'plan_sha256': sha(out / 'PLAN.json')})

    def native():
        root = out / 'native'
        result = execute_task(bank, harness, judge, task_id=args.task_id, employee_id='web-administrator',
            skill=SEED_SKILL, budget=budget, out=root, total_timeout_seconds=1200)
        if result['status'] != 'completed': raise ValueError('Native JobBench task was not completely graded')
        audit_attempt(bank, root, args.task_id, SEED_SKILL, harness, judge=judge)
        report = {'ok': True, 'status': result['status'], 'quality_score': result['grade']['quality_score'],
                  'physical_model_calls': result['model_calls'], 'charged_tokens': result['tokens'],
                  'accounting_complete': result['accounting_complete'], 'seconds': result['seconds'],
                  'attempt_sha256': sha(root / 'ATTEMPT.json')}
        # Keep review receipts outside the already sealed attempt inventory.
        save(out / 'NATIVE_AUDIT.json', report)
        return report

    def missing_outputs():
        root = out / 'missing-outputs'; workspace = root / 'workspace'
        baseline = bank.stage(args.task_id, workspace)
        save(root / 'BASELINE.json', baseline)
        grade = judge.grade(args.task_id, workspace, baseline, root / 'judging', token_limit=judge.max_tokens,
                            call_limit=judge.max_model_calls, timeout_seconds=300)
        validate_grade(grade, token_limit=judge.max_tokens, call_limit=judge.max_model_calls)
        judge.audit_grade(bank, args.task_id, workspace, baseline, root / 'judging', grade)
        ok = (grade['quality_score'] == 0 and grade['success'] is False
              and all(not c['passed'] for v in grade['criteria'] for c in v['criteria_results']))
        report = {'ok': ok, 'quality_score': grade['quality_score'],
                  'physical_model_calls': grade['usage']['physical_model_calls'],
                  'charged_tokens': grade['usage']['charged_tokens'],
                  'accounting_complete': grade['usage']['accounting_complete'],
                  'grade_sha256': sha(root / 'judging/GRADE.json')}
        save(root / 'QUALIFICATION_AUDIT.json', report)
        if not ok: raise ValueError('Missing-output control did not fail every original subcriterion')
        return report

    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {'native': pool.submit(native), 'missing_outputs': pool.submit(missing_outputs)}
        for name, future in futures.items():
            try: results[name] = future.result()
            except Exception as exc: results[name] = {'ok': False, 'error_type': type(exc).__name__}
            save(out / 'PROGRESS.json', results)
    report = {'ok': all(r['ok'] for r in results.values()), 'cases': results,
              'plan_sha256': sha(out / 'PLAN.json'), 'finished_at': datetime.now(timezone.utc).isoformat(),
              'scope': plan['scope']}
    save(out / 'REPORT.json', report)
    print(json.dumps(report, indent=2))
    if not report['ok']: raise SystemExit(1)


if __name__ == '__main__': main()
