#!/usr/bin/env python3
"""Offline consistency audit; receipts are evidence, never an independent model score.

Run ``python scripts/audit_evaluation.py RUN --strict`` for a completed release.
Unfinished runs may be inspected without --strict; integrity errors always fail.
This does not authenticate provider receipts, re-run models, or reconstruct the
last rejected artifact when no immutable rejected-artifact snapshot was retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.metrics import build_report
from lifespan.evaluation.tasks import grade_case


def require(condition, code):
    if not condition:
        raise ValueError(code)


def reports_equal(left, right):
    """Allow only finite float roundoff (relative/absolute 1e-12).

    Python processes can sum equivalent groups in different orders. Structure,
    JSON value types, integer counts, booleans, strings and null remain exact.
    """
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(reports_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(reports_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def child(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'unsafe_artifact_path')
    return path


def observed_skill_load(messages, file_sha):
    """Verify native call/result evidence without importing the mutable executor."""
    requests = set()
    for message in messages:
        for call in message.get('tool_calls') or []:
            function = call.get('function', {})
            try:
                args = json.loads(function.get('arguments', '{}'))
            except (ValueError, TypeError):
                continue
            if function.get('name') == 'skill_view' and isinstance(args, dict) and 'work-process' in args.values():
                requests.add(call.get('id'))
    for message in messages:
        if message.get('role') != 'tool' or message.get('tool_call_id') not in requests:
            continue
        try:
            result = json.loads(message.get('content', '{}'))
        except (ValueError, TypeError):
            continue
        if (isinstance(result, dict) and result.get('success') is True and result.get('name') == 'work-process'
                and not result.get('error') and isinstance(result.get('content'), str) and sha(result['content'].encode()) == file_sha):
            return True
    return False


def meter_check(record):
    native = record['result']['native']
    meter = native['evaluation_budget']
    rows = meter['operations']
    require(meter['physical_model_calls'] == len(rows), 'physical_call_count')
    for index, row in enumerate(rows, 1):
        require(row['dispatch'] == index, 'physical_dispatch_sequence')
        require(all(type(row[k]) is int and row[k] >= 0 for k in
                    ('reserved_tokens', 'charged_tokens', 'output_cap')), 'invalid_physical_reservation')
        require(row['accounting'] in ('reported', 'reservation'), 'unknown_physical_accounting')
        if row['accounting'] == 'reported':
            require(all(type(row[k]) is int and row[k] >= 0 for k in
                        ('input_tokens', 'output_tokens', 'total_tokens')), 'invalid_physical_usage')
            require(row['input_tokens'] + row['output_tokens'] == row['total_tokens'] == row['charged_tokens'], 'physical_token_equation')
            require(row['total_tokens'] <= row['reserved_tokens'] and row['output_tokens'] <= row['output_cap']
                    and row['status'] != 'provider_budget_overrun', 'provider_budget_overrun')
        else:
            require(all(row[k] is None for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    and row['charged_tokens'] == row['reserved_tokens'], 'reservation_misreported_as_usage')
    for key in ('input_tokens', 'output_tokens', 'total_tokens', 'charged_tokens'):
        require(meter[key] == sum(row[key] or 0 for row in rows), 'physical_total_' + key)
    complete = all(row['accounting'] == 'reported' for row in rows)
    require(meter['reported_tokens'] == meter['total_tokens'] and meter['accounting_complete'] == complete, 'physical_accounting_summary')
    expected = {'api_calls': len(rows), 'charged_tokens': meter['charged_tokens'],
                'prompt_tokens': meter['input_tokens'], 'completion_tokens': meter['output_tokens'],
                'total_tokens': meter['total_tokens'] if complete else None, 'complete': complete}
    require(all(record['usage'].get(k) == expected[k] for k in
                ('api_calls', 'charged_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'complete')), 'session_usage_mismatch')
    require(complete and record['infrastructure_valid'] is True, 'trial_infrastructure_or_accounting_invalid')


def session_check(record, directory, capsule, version=None):
    disk = read(directory / 'session.json')
    require({k: v for k, v in record.items() if k not in ('id', 'skill_version')} == disk, 'checkpoint_session_mismatch')
    case = capsule['case']
    require(record['employee'] == capsule['employee'] and record['task_id'] == capsule['task_id'] == case['id']
            and record['case_id'] == case['id'] and record['day'] == case['day'] == capsule['ecosystem']['day'], 'private_case_identity')
    native_file = child(directory, 'computers/' + record['employee'] + '/hermes/skills/work-process/SKILL.md').read_bytes()
    require(sha(native_file) == record['skill']['native_file_sha256'], 'deployed_native_skill_hash')
    content = native_file.split(b'---\n\n', 1)[1]
    require(sha(content) == record['skill']['content_sha256'], 'deployed_skill_content_hash')
    if version is not None:
        require(sha(version['skill'].encode()) == version['hash'] == sha(content)
                and version['version'] == record['skill_version'], 'deployed_skill_version')
        require(version['adopted_after_day'] < record['day'], 'future_skill_deployment')
    loaded = observed_skill_load(record['result']['native'].get('messages', []), sha(native_file))
    require(record['skill_loaded'] == loaded, 'native_skill_load_provenance')
    for name, text in case['public_files'].items():
        require(record['filesystem_before'][name]['sha256'] == sha(text.encode()), 'case_public_input_hash')
    if record['success']:
        object_path = child(directory / 'filesystem_objects', record['committed_artifact_sha256'])
        require(object_path.is_file(), 'missing_immutable_committed_bytes')
        raw = object_path.read_bytes()
        require(sha(raw) == record['committed_artifact_sha256'] and json.loads(raw) == record['artifact'], 'committed_artifact_hash_or_content')
        grade = grade_case(case, record['artifact'])
        require(grade['success'] is True and grade['score'] == record['semantic_score']
                and grade['checks'] == record['checks'] and grade['feedback'] == record['feedback'], 'independent_committed_artifact_grade')
    else:
        require(record['artifact'] is None and record['committed_artifact_sha256'] is None, 'failed_session_claims_commit')
    if 'last_submitted_artifact_sha256' in record:
        submitted = record['last_submitted_artifact_sha256']
        grade = {'score': 0., 'checks': {}, 'feedback': 'No artifact reached substantive submission.'}
        if submitted is not None:
            path = child(directory / 'filesystem_objects', submitted)
            require(path.is_file(), 'missing_immutable_submitted_bytes')
            raw = path.read_bytes()
            require(sha(raw) == submitted, 'submitted_artifact_hash')
            grade = grade_case(case, json.loads(raw))
        require(all(grade[key] == record[field] for key, field in
                    (('score', 'semantic_score'), ('checks', 'checks'), ('feedback', 'feedback'))), 'independent_last_submission_grade')
    meter_check(record)


def update_check(root, update, experiences, sessions, feedback_delay):
    directory = child(root, f"learning/d{update['day']:03d}-{update['employee']}")
    require(read(directory / 'update.json') == update, 'checkpoint_update_mismatch')
    day, employee = update['day'], update['employee']
    require(update['current_day'] == day and update['available_from_day'] == day + 1, 'update_visibility_day')
    train, val = update['train_ids'], update['validation_ids']
    require(len(set(train + val)) == len(train + val), 'duplicate_or_overlapping_experience')
    sources = {'train': set(), 'val': set()}
    for split, ids in (('train', train), ('val', val)):
        for identifier in ids:
            item, source = experiences[identifier], sessions[identifier]
            require(item['employee'] == source['employee'] == employee and item['split'] == split, 'cross_employee_or_split_experience')
            earliest = source['day'] + feedback_delay
            require(earliest <= item['available_day'] <= day and earliest <= item['feedback_available_day'] <= day, 'future_update_experience')
            require(item['source_session'] == source['task_id'], 'experience_source_identity')
            sources[split].add(item['source_session'])
    require(not (sources['train'] & sources['val']), 'source_task_split_leakage')
    require(len(sources['train']) == len(train) and len(sources['val']) == len(val), 'repeated_source_task_in_update')
    for payload in update['optimizer_inputs']:
        require(payload['current_day'] == day and all(item['task']['id'] in train and item['task']['split'] == 'train'
                and item['task']['available_day'] <= day and item['task']['feedback_available_day'] <= day
                and all(value == experiences[item['task']['id']][key] for key, value in item['task'].items())
                for item in payload['train_experiences']), 'optimizer_nontraining_or_future_context')
    costs, targets, optimizers = update['costs'], [], []
    for row in costs['operations']:
        require(row['kind'] in ('target', 'optimizer'), 'unknown_learning_operation')
        (targets if row['kind'] == 'target' else optimizers).append(row)
        require(row['accounting'] == 'reported', 'learning_accounting_incomplete')
        require(all(type(row[k]) is int and row[k] >= 0 for k in ('tokens', 'model_calls', 'tool_calls')), 'invalid_learning_usage')
        require(row['tokens'] <= row['limits']['max_tokens'] and row['model_calls'] <= row['limits']['max_model_calls'], 'learning_budget_overrun')
    require(costs['tokens'] == sum(row['tokens'] for row in costs['operations'])
            and costs['target_model_calls'] == sum(row['model_calls'] for row in targets)
            and costs['optimizer_model_calls'] == sum(row['model_calls'] for row in optimizers)
            and costs['replays'] == len(targets) and costs['accounting_complete'] is True, 'learning_receipt_totals')
    evidence = update['replay_evidence']
    require(len(evidence) == len(targets), 'missing_replay_evidence')
    require({p.parent.name for p in directory.glob('trial-*/session.json')} ==
            {f'trial-{index:03d}' for index in range(len(targets))}, 'unreconciled_replay_sessions')
    for index, (row, receipt) in enumerate(zip(targets, evidence)):
        require(row['task_id'] in train + val and receipt['id'] == row['task_id'], 'replay_source_identity')
        trial = directory / f'trial-{index:03d}'
        record = read(trial / 'session.json')
        session_check(record, trial, read(child(root, 'private/cases/' + row['task_id'] + '.json')))
        require(record['skill']['content_sha256'] == receipt['skill_sha256'] and float(record['success']) == receipt['hard']
                and (record['semantic_score'] if record['success'] else min(.99, record['semantic_score'])) == receipt['soft']
                and record['usage']['total_tokens'] == row['tokens'] and record['usage']['api_calls'] == row['model_calls'], 'replay_physical_evidence_mismatch')
    audits = update['optimizer_transport_audit']
    require(len(audits) == len(optimizers), 'missing_optimizer_transport_evidence')
    for row, receipt in zip(optimizers, audits):
        require(receipt['accounting_complete'] is True and receipt['tokens'] == row['tokens']
                and receipt['model_calls'] == row['model_calls'] and receipt['input_tokens'] + receipt['output_tokens'] == receipt['tokens'], 'optimizer_transport_usage')
        if receipt['model_calls']:
            require(sha(receipt['optimizer_prompt'].encode()) == receipt['optimizer_prompt_sha256'], 'optimizer_prompt_hash')
    require(update['status'] != 'failed', 'learning_trial_failed')


def audit_run(root, strict=False):
    root, errors, notes = Path(root).resolve(), [], []
    result = {'schema_version': 1, 'run': str(root), 'status': 'invalid', 'errors': errors, 'notes': notes,
              'scope': 'Artifact consistency and trusted regrading; no new model-quality or learning-effect claim.',
              'sessions_checked': 0, 'updates_checked': 0, 'model_quality_score': None}
    def inspect(label, callback):
        try:
            callback()
        except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
            errors.append({'location': label, 'code': str(exc) if type(exc) is ValueError else type(exc).__name__})
    try:
        manifest, cp = read(root / 'manifest.json'), read(root / 'checkpoint.json')
        for name in ('lifespan/evaluation/tasks.py', 'lifespan/evaluation/metrics.py', 'lifespan/ecosystem.py', 'lifespan/world.py'):
            require(sha((ROOT / name).read_bytes()) == manifest['source_sha256'][name], 'audit_source_revision_mismatch')
        state = cp['runner']
        status = read(root / 'REPORT.json')['status'] if (root / 'REPORT.json').exists() else 'running'
        result['run_status'] = status
        sessions = {record['id']: record for record in state['sessions']}
        experiences = {record['id']: record for record in state['experiences']}
        require(len(sessions) == len(state['sessions']) and len(experiences) == len(state['experiences']), 'duplicate_record_identity')
        for identifier, record in sessions.items():
            inspect('work/' + identifier, lambda r=record, i=identifier: session_check(r, child(root, 'work/' + i),
                read(child(root, 'private/cases/' + i + '.json')),
                read(child(root, f"skills/{r['employee']}/v{r['skill_version']:03d}.json"))))
            result['sessions_checked'] += 1
        for update in state['updates']:
            inspect(f"learning/day-{update['day']}/{update['employee']}", lambda u=update: update_check(
                root, u, experiences, sessions, manifest['config']['feedback_delay']))
            result['updates_checked'] += 1
        for employee, skill in state['skills'].items():
            version = read(child(root, f'skills/{employee}/v000.json'))
            require(version['version'] == 0 and sha(version['skill'].encode()) == version['hash'], 'initial_skill_version')
            for update in (u for u in state['updates'] if u['employee'] == employee):
                require(update['parent_version'] == version['version'] and update['skill_before_sha256'] == version['hash'], 'update_parent_chain')
                if update['accepted']:
                    version = read(child(root, f"skills/{employee}/v{version['version'] + 1:03d}.json"))
                    require(version['adopted_after_day'] == update['day'], 'accepted_skill_day')
                require(update['deployed_version'] == version['version'] and update['skill'] == version['skill']
                        and sha(version['skill'].encode()) == version['hash'] == update['skill_after_sha256'], 'accepted_skill_chain')
            require(state['skill_versions'][employee] == version['version'] and skill == version['skill'], 'checkpoint_final_skill')
        require(state['learning_calls'] == sum(u['costs']['target_model_calls'] + u['costs']['optimizer_model_calls'] for u in state['updates'])
                and state['learning_tokens'] == sum(u['costs']['tokens'] for u in state['updates']), 'checkpoint_learning_totals')
        if manifest['config']['algorithm'] == 'no_learning':
            require(not state['updates'] and all(r['skill_version'] == 0 for r in sessions.values()), 'no_learning_treatment_mutated')
        report_path = root / 'REPORT.json'
        if report_path.exists():
            report = read(report_path)
            provenance = dict(report['provenance'])
            for key in ('target_model', 'model_base_url', 'dependencies', 'source_sha256'):
                require(provenance[key] == manifest[key], 'report_provenance_' + key)
            cohort = root / 'persona_cohort.json'
            require(provenance['persona_cohort_sha256'] == (sha(cohort.read_bytes()) if cohort.exists() else 'offline-fixture-no-personas'), 'persona_cohort_provenance')
            rebuilt = build_report(manifest['config'], manifest['scenario'], state['sessions'], state['updates'],
                                   Ecosystem.restore(cp['ecosystem']).snapshot(), status=status, provenance=provenance)
            result['report_audit'] = rebuilt['audit']
            if status == 'completed':
                require(reports_equal(report, rebuilt), 'persisted_report_mismatch')
                require(rebuilt['audit']['eligible_for_paired_inference'], 'completed_report_ineligible')
        pending = sorted(str(p.relative_to(root)) for pattern in ('**/INFLIGHT.json', '**/FAILURE.json') for p in root.glob(pattern))
        result['pending_or_failed_artifacts'] = pending
        orphans = sorted(p.parent.name for p in (root / 'work').glob('*/session.json') if p.parent.name not in sessions)
        result['uncheckpointed_sessions'] = orphans
        update_keys = {f"d{u['day']:03d}-{u['employee']}" for u in state['updates']}
        untracked_learning = sorted(p.name for p in (root / 'learning').glob('*') if p.is_dir() and p.name not in update_keys)
        result['uncheckpointed_learning'] = untracked_learning
        if status == 'completed':
            require(not pending and not orphans and not untracked_learning, 'completed_run_has_unreconciled_artifacts')
        else:
            notes.append('Run is incomplete; current in-flight artifacts and report/checkpoint skew may be expected.')
        failed_scores = sum(not r['success'] and 'last_submitted_artifact_sha256' not in r for r in sessions.values())
        if failed_scores:
            notes.append(f'{failed_scores} unsuccessful sessions have no immutable committed output; their partial scores cannot be independently reconstructed by this audit.')
        result['status'] = 'invalid' if errors else 'valid_completed' if status == 'completed' else 'incomplete'
    except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
        errors.append({'location': 'run', 'code': str(exc) if type(exc) is ValueError else type(exc).__name__})
    result['ok'] = not errors and (not strict or result['status'] == 'valid_completed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--strict', action='store_true', help='Require completed, reconciled, inference-eligible evidence.')
    args = parser.parse_args()
    result = audit_run(args.run, args.strict)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
