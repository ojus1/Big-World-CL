"""Fresh, bounded parallel adapter checks; these are not learning observations."""
import argparse
import json
from pathlib import Path
import time
from scripts.source_world_calibration import save, sha
from .attempts import execute_task
from .audit_worlds import audit_attempt
from .bank import Bank
from .campaign import SEED_SKILL, source_identity
from .contracts import Budget
from .dispatch import dispatch_day
from .hermes import Hermes
from .qualitative import FrozenRubricJudge


def qualify(bank, harness, judge, task_id, out, parallel=2):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    budget = Budget()
    slots = [{'id': f'control-{i:02d}', 'employee_id': f'qualification-{i:02d}'} for i in range(parallel)]
    manifest = {'schema_version': 1, 'source_sha256': source_identity(), 'task_id': task_id,
                'harness': harness.identity(), 'judge': judge.identity(),
                'bank_manifest_sha256': bank.verification['manifest_sha256'],
                'max_reserved_tokens': parallel * (budget.total_tokens + judge.max_tokens),
                'slots': slots, 'started_unix': time.time(),
                'scope': 'Concurrent adapter, isolation and receipt qualification. Repeated development controls, not learning or independent outcomes.'}
    save(out / 'PLAN.json', manifest)
    rows = []
    def execute(slot):
        return execute_task(bank, harness, judge, task_id=task_id, employee_id=slot['employee_id'],
                            skill=SEED_SKILL, budget=budget, out=out / slot['id'])
    def record(slot, result):
        row = {'id': slot['id'], 'status': result['status'], 'tokens': result['tokens'],
               'calls': result['model_calls'], 'audited': False}
        rows.append(row)
        save(out / 'PROGRESS.json', rows)
        audit_attempt(bank, out / slot['id'], task_id, SEED_SKILL, harness)
        row['audited'] = True
        save(out / 'PROGRESS.json', rows)
    def journal(wave):
        if wave: save(out / 'INFLIGHT.json', wave)
        else: (out / 'INFLIGHT.json').unlink()
    try:
        dispatch_day(slots, execute, record, journal, max_parallel=parallel)
    except Exception as exc:
        save(out / 'QUALIFICATION.json', {'ok': False, 'error_type': type(exc).__name__, 'rows': rows})
        raise
    result = {'ok': True, 'plan_sha256': sha(out / 'PLAN.json'), 'rows': rows,
              'calls': sum(r['calls'] for r in rows), 'tokens': sum(r['tokens'] for r in rows),
              'scope': manifest['scope']}
    save(out / 'QUALIFICATION.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--hermes-root', type=Path, required=True)
    p.add_argument('--task-id', required=True)
    p.add_argument('--parallel', type=int, default=2)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    b = Bank(a.bank)
    print(json.dumps(qualify(b, Hermes(a.hermes_root, a.model, a.base_url),
        FrozenRubricJudge(b, a.model, a.base_url), a.task_id, a.out, a.parallel), indent=2))
