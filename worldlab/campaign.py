"""Immutable calibration plans and single-execution native receipts."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from scripts.source_world_calibration import read, save, sha
from .bank import Bank
from .calibration import fit, slots
from .contracts import Budget, TaskRequest

ROOT = Path(__file__).resolve().parents[1]
SEED_SKILL = ('# Work process\n\nRead the current request and relevant source files. Extract the required '
              'deliverables, facts and constraints. Complete the work using the available tools. '
              'Check the resulting artifacts against the request and preserve original inputs. '
              'Current evidence overrides remembered guidance.\n')


def source_identity():
    paths = [p for folder in ('worldlab', 'lifespan') for p in (ROOT / folder).rglob('*.py')
             if 'tests' not in p.parts and 'artifacts' not in p.relative_to(ROOT).parts]
    paths += [ROOT / 'scripts' / name for name in ('source_world_calibration.py', 'audit_transfer.py',
                                                   'audit_learning_v2.py', 'audit_evaluation.py')
              if (ROOT / 'scripts' / name).exists()]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def prepare(bank, specification, harness, grader, out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Use a fresh campaign destination')
    fitted = fit(bank, specification)
    schedule = slots(bank, fitted, specification)
    for slot in schedule:
        public = bank.public(slot['task_id'])
        reasons = harness.unsupported(public)
        if public['source'] == 'internal_eurobench':
            kinds = grader.unsupported(bank.private_definition(slot['task_id']))
            if kinds:
                reasons.append('Grader qualification pending: ' + ','.join(kinds))
        slot['unsupported'] = reasons
    ceiling = specification.get('max_campaign_tokens', 4_000_000)
    maximum = sum(s['budget']['total_tokens'] for s in schedule if not s['unsupported'])
    if type(ceiling) is not int or ceiling < maximum:
        raise ValueError('Campaign ceiling must cover every planned eligible attempt reservation')
    plan = {'schema_version': 1, 'kind': 'fixed_skill_source_calibration',
            'bank_manifest_sha256': bank.verification['manifest_sha256'],
            'specification': specification, 'fit': fitted, 'slots': schedule,
            'harness': harness.identity(), 'grader': grader.identity(),
            'source_sha256': source_identity(), 'skill': SEED_SKILL,
            'max_campaign_tokens': ceiling, 'planned_reservation_tokens': maximum,
            'scope': 'Development replay calibration. Repetitions and translated families are dependent. No learning effect or final-world inference.'}
    save(out / 'PLAN.json', plan)
    digest = sha(out / 'PLAN.json')
    save(out / 'PREPARED.json', {'plan_sha256': digest, 'prepared_unix': time.time()})
    return {'plan_sha256': digest, 'planned_slots': len(schedule),
            'unsupported_slots': sum(bool(s['unsupported']) for s in schedule),
            'weighted_retrieval_coverage': fitted['weighted_retrieval_coverage']}


def summarize(plan, receipts):
    known = {s['id']: s for s in plan['slots']}
    if len({r['id'] for r in receipts}) != len(receipts) or any(r['id'] not in known for r in receipts):
        raise ValueError('Unknown or duplicate receipt')
    completed = [r for r in receipts if r['status'] in ('completed', 'budget_exhausted')]
    graded = [r for r in completed if r.get('grade', {}).get('grading_complete')]
    paired = {}
    for receipt in graded:
        slot = known[receipt['id']]
        paired.setdefault((slot['employee_id'], slot['task_id']), []).append(receipt['grade']['mechanical_success'])
    pairs = [v for v in paired.values() if len(v) == 2]
    return {'planned_slots': len(known), 'recorded_slots': len(receipts),
            'missing_slots': sorted(set(known) - {r['id'] for r in receipts}),
            'status_counts': dict(Counter(r['status'] for r in receipts)),
            'completed_native_attempts': len(completed), 'mechanically_graded_attempts': len(graded),
            'mechanical_successes': sum(r['grade']['mechanical_success'] for r in graded),
            'repeated_case_pairs': len(pairs), 'disagreeing_pairs': sum(v[0] != v[1] for v in pairs),
            'distinct_lineage_groups': len({s['lineage_group'] for s in plan['slots']}),
            'charged_or_reserved_tokens': sum(r.get('charged_tokens', 0) for r in receipts),
            'known_physical_model_calls': sum(r.get('physical_model_calls') or 0 for r in receipts),
            'unknown_call_count_attempts': sum(r.get('physical_model_calls') is None and
                                              r['status'] != 'unsupported' for r in receipts),
            'accounting_complete': all(r.get('accounting_complete') for r in receipts if r['status'] != 'unsupported'),
            'scope': plan['scope'], 'quality_judging': 'not_executed', 'learning_claim_eligible': False}


def execute(bank, harness, grader, out):
    out = Path(out).resolve()
    plan = read(out / 'PLAN.json')
    if sha(out / 'PLAN.json') != read(out / 'PREPARED.json')['plan_sha256']:
        raise ValueError('Prepared plan bytes changed')
    for current, expected in ((bank.verification['manifest_sha256'], plan['bank_manifest_sha256']),
                              (harness.identity(), plan['harness']), (grader.identity(), plan['grader']),
                              (source_identity(), plan['source_sha256'])):
        if current != expected:
            raise ValueError('Execution dependencies changed since preparation')
    # Never replay an interrupted/ambiguous attempt under the same frozen plan.
    with (out / 'EXECUTION.json').open('x') as f:
        json.dump({'started_unix': time.time(), 'plan_sha256': sha(out / 'PLAN.json')}, f)
    receipts = []
    for slot in plan['slots']:
        if slot['unsupported']:
            receipt = {'id': slot['id'], 'status': 'unsupported', 'reasons': slot['unsupported']}
        else:
            root = out / 'attempts' / slot['id']
            workspace = root / slot['employee_id'] / 'workspace'
            public = bank.public(slot['task_id'])
            baseline = bank.stage(slot['task_id'], workspace)
            identity = workspace / '.employee_identity'
            identity.write_text(slot['employee_id'] + '\n')
            baseline['.employee_identity'] = sha(identity)
            save(root / 'BASELINE.json', baseline)
            request = TaskRequest(slot['id'], slot['employee_id'], public['instruction'],
                                  public['language'], workspace, plan['skill'], Budget(**slot['budget']))
            save(out / 'INFLIGHT.json', {'id': slot['id'], 'started_unix': time.time(),
                                       'token_reservation': request.budget.total_tokens})
            receipt = {}
            try:
                receipt = {'id': slot['id'], **harness.run(request, root)}
                if receipt['status'] in ('completed', 'budget_exhausted'):
                    receipt['grade'] = grader.grade(bank.private_definition(slot['task_id']), workspace, baseline)
                # Full output inventory is evaluator evidence; no sibling workspace reaches another attempt.
                receipt['files'] = {str(p.relative_to(root)): {'sha256': sha(p), 'bytes': p.stat().st_size}
                                    for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}
            except Exception as exc:
                # Preserve any completed native receipt separately. Never turn a grader error into a solver failure.
                receipt = {**receipt, 'id': slot['id'], 'status': 'infrastructure_error',
                           'error_type': type(exc).__name__,
                           'charged_tokens': receipt.get('charged_tokens', request.budget.total_tokens),
                           'accounting_complete': False}
            save(root / 'RECEIPT.json', receipt)
            if not receipt['status'].startswith('infrastructure'):
                (out / 'INFLIGHT.json').unlink()
        receipts.append(receipt)
        save(out / 'RECEIPTS.json', receipts)
        save(out / 'STATUS.json', {'updated_unix': time.time(), **summarize(plan, receipts)})
        if receipt['status'].startswith('infrastructure'):
            break
    report = summarize(plan, receipts)
    report['status'] = 'complete' if not report['missing_slots'] and not any(
        k.startswith('infrastructure') for k in report['status_counts']) else 'incomplete'
    save(out / 'REPORT.json', report)
    return report


def audit(bank, grader, out):
    """Rehash raw evidence and rerun original mechanics; never execute candidates."""
    out = Path(out).resolve()
    plan = read(out / 'PLAN.json')
    if sha(out / 'PLAN.json') != read(out / 'PREPARED.json')['plan_sha256']:
        raise ValueError('Plan changed')
    if plan['source_sha256'] != source_identity() or plan['grader'] != grader.identity():
        raise ValueError('Frozen execution/grading source changed')
    if plan['bank_manifest_sha256'] != bank.verification['manifest_sha256']:
        raise ValueError('Task bank changed')
    receipts = read(out / 'RECEIPTS.json')
    planned = {s['id']: s for s in plan['slots']}
    for receipt in receipts:
        slot = planned[receipt['id']]
        if receipt['status'] == 'unsupported':
            if not slot['unsupported'] or receipt['reasons'] != slot['unsupported']:
                raise ValueError('Unsupported scope changed')
            continue
        root = out / 'attempts' / receipt['id']
        if read(root / 'RECEIPT.json') != receipt:
            raise ValueError('Receipt mismatch')
        if receipt.get('files'):
            actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'RECEIPT.json'}
            if actual != set(receipt['files']) or any(p.is_symlink() for p in root.rglob('*')):
                raise ValueError('Raw attempt inventory changed')
        for name, expected in receipt.get('files', {}).items():
            from scripts.source_world_calibration import child
            path = child(root, name)
            if path.is_symlink() or sha(path) != expected['sha256'] or path.stat().st_size != expected['bytes']:
                raise ValueError('Raw attempt artifact changed: ' + name)
        if receipt['status'] not in ('completed', 'budget_exhausted'):
            continue
        request = read(root / 'REQUEST.json')
        if (request['instruction'] != bank.public(slot['task_id'])['instruction'] or
                request['skill'] != plan['skill'] or request['budget'] != slot['budget'] or
                request['provider'] != plan['harness']['provider']):
            raise ValueError('Solver request differs from the frozen public contract')
        native = read(root / 'NATIVE.json')
        meter = native['evaluation_budget']
        if (sum(op['charged_tokens'] for op in meter['operations']) != receipt['charged_tokens'] or
                len(meter['operations']) != receipt['physical_model_calls'] or
                meter['physical_model_calls'] > slot['budget']['model_calls'] or
                meter['charged_tokens'] > slot['budget']['total_tokens'] or
                meter['provider_contract'] != plan['harness']['provider'] or meter.get('stopped')):
            raise ValueError('Native accounting/provider contract mismatch')
        workspace = root / slot['employee_id'] / 'workspace'
        regraded = grader.grade(bank.private_definition(slot['task_id']), workspace, read(root / 'BASELINE.json'))
        if regraded != receipt['grade']:
            raise ValueError('Original mechanical regrading changed')
    regenerated = summarize(plan, receipts)
    regenerated['status'] = 'complete' if not regenerated['missing_slots'] and not any(
        k.startswith('infrastructure') for k in regenerated['status_counts']) else 'incomplete'
    if regenerated != read(out / 'REPORT.json'):
        raise ValueError('Report differs from receipts')
    return {'ok': True, 'status': regenerated['status'], 'verified_receipts': len(receipts),
            'plan_sha256': sha(out / 'PLAN.json'), 'learning_claim_eligible': False}
