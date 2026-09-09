#!/usr/bin/env python3
"""Independent offline transfer evidence audit; never a model-quality score.

Strict mode requires completed native evidence. Source revision mismatches must
be audited in the recorded checkout, not bypassed. No models or providers run.
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
from lifespan.evaluation.protocol import SEED_SKILL, digest, experience_split
from lifespan.evaluation.runner import dependency_provenance
from scripts.audit_evaluation import audit_run, child, read, reports_equal, require, session_check, update_check

CORE = {'lifespan/evaluation/tasks.py', 'lifespan/evaluation/runtime.py',
        'lifespan/evaluation/budget.py', 'lifespan/evaluation/protocol.py',
        'lifespan/evaluation/runner.py', 'lifespan/evaluation/skillopt.py',
        'lifespan/evaluation/optimizer.py', 'lifespan/computers.py',
        'lifespan/ecosystem.py', 'lifespan/world.py'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def skill_hash(skill):
    return hashlib.sha256(skill.encode()).hexdigest()


def sources_check(manifest, extra):
    sources = manifest['source_sha256']
    require(CORE | set(extra) <= sources.keys(), 'missing_execution_source_provenance')
    for name, expected in sources.items():
        require(sha(child(ROOT, name)) == expected, 'execution_source_revision_mismatch')
    require(manifest['dependencies'] == dependency_provenance()
            and all(manifest['dependencies'].get(name, {}).get('revision') for name in ('hermes', 'mirofish', 'skillopt')),
            'native_dependency_revision_mismatch')


def bounded(record):
    meter = record['result']['native']['evaluation_budget']
    require(meter['physical_model_calls'] <= 16 and meter['charged_tokens'] <= 250000
            and all(row['output_cap'] <= 4096 for row in meter['operations']), 'target_physical_budget_exceeded')


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def gate_check(update):
    """Recompute pinned K2 skill-only gates from independently graded replays."""
    cfg = update['configuration']
    require(cfg['gate_metric'] == 'mixed' and type(cfg['gate_mixed_weight']) is float
            and cfg['gate_mixed_weight'] == .5, 'upstream_gate_metric_contract')
    rows, train, val = update['replay_evidence'], update['train_ids'], update['validation_ids']
    require(all(type(r['sample_id']) is int and r['hard'] in (0., 1.)
                and all(number(r[k]) and r[k] <= 1 for k in ('hard', 'soft')) for r in rows), 'invalid_gate_replay_score_or_sample')
    base_plan = [('baseline_val', i, 0) for i in val] + [('train', i, 0) for i in train]
    base_plan += [('train', i, sample) for i in train for sample in range(2)]
    candidate_plan = base_plan + [('gate_trial:skill', i, 0) for i in val] + [('final_val', i, 0) for i in val]
    no_candidate_plan = base_plan + [('final_val', i, 0) for i in val]
    observed = [(r['phase'], r['id'], r['sample_id']) for r in rows]
    require(observed == candidate_plan[:len(rows)] or observed == no_candidate_plan[:len(rows)], 'upstream_replay_phase_schedule')
    seed = update['skill_before_sha256']
    require(all(r['skill_sha256'] == seed for r in rows if r['phase'] in ('baseline_val', 'train')), 'gate_baseline_skill_mismatch')
    gate = update['gate_evidence']
    if update['status'] == 'budget_exhausted':
        require(update['accepted'] is False and update['skill_after_sha256'] == seed
                and gate == {'accepted': False, 'gate_action': 'reject_incomplete'}, 'budget_exhausted_gate_claim')
        return
    require(update['status'] == 'completed' and observed in (candidate_plan, no_candidate_plan), 'incomplete_upstream_gate_schedule')
    by_phase = {phase: [r for r in rows if r['phase'] == phase] for phase in ('baseline_val', 'gate_trial:skill', 'final_val')}
    base, trial, final = (by_phase[p] for p in ('baseline_val', 'gate_trial:skill', 'final_val'))
    def mean(items, key):
        return sum(r[key] for r in items) / len(items)
    def mixed(items):
        return .5 * mean(items, 'hard') + .5 * mean(items, 'soft')
    def comparisons(candidate):
        deltas = []
        for before, after in zip(base, candidate):
            a, b = .5 * before['hard'] + .5 * before['soft'], .5 * after['hard'] + .5 * after['soft']
            deltas.append({'task_id': before['id'], 'tags': [], 'baseline_score': a, 'candidate_score': b,
                           'status': 'improved' if b > a else 'regressed' if b < a else 'unchanged', 'scores_are_finite': True})
        blocked = any(d['status'] == 'regressed' for d in deltas)
        return mixed(candidate) > mixed(base) and not blocked, blocked, deltas
    trials, trial_passed, proposed = [], False, seed
    if trial:
        require(len({r['skill_sha256'] for r in trial}) == 1, 'mixed_candidate_skills_in_gate')
        proposed = trial[0]['skill_sha256']
        trial_passed, blocked, deltas = comparisons(trial)
        trials.append({'target': 'skill', 'baseline_score': mixed(base), 'candidate_score': mixed(trial),
                       'accepted': trial_passed, 'blocked_by_regression': blocked, 'task_deltas': deltas})
    require(all(r['skill_sha256'] == (proposed if trial_passed else seed) for r in final), 'fresh_final_gate_wrong_skill')
    final_passed, blocked, deltas = comparisons(final)
    accepted = bool(trial_passed and final_passed)
    trials.append({'target': 'final', 'baseline_score': mixed(base), 'candidate_score': mixed(final),
                   'accepted': accepted, 'blocked_by_regression': blocked, 'task_deltas': deltas})
    require(type(update['accepted']) is bool and update['accepted'] == accepted
            and gate['accepted'] is accepted and gate['gate_action'] == ('accept_new_best' if accepted else 'reject')
            and gate['holdout_leaked'] is False, 'upstream_gate_decision_mismatch')
    require(reports_equal(gate['gate_trials'], trials) and reports_equal(gate['baseline_score'], mixed(base))
            and reports_equal(gate['candidate_score'], mixed(final))
            and reports_equal(gate['holdout_baseline'], mean(base, 'hard'))
            and reports_equal(gate['holdout_candidate'], mean(final, 'hard')), 'upstream_gate_score_evidence_mismatch')
    require(bool(gate['applied_edits']) == accepted and gate['new_memory'] == ''
            and gate['new_skill'] == update['skill']
            and update['skill_after_sha256'] == (proposed if accepted else seed), 'upstream_gate_document_mismatch')


def _learning(root, output):
    manifest, cp, state, evidence = (read(root / name) for name in
                                   ('manifest.json', 'checkpoint.json', 'state.json', 'evidence.json'))
    require(manifest['kind'] == 'one_historical_learning_epoch'
            and manifest['version'] == 'historical-transfer-learning-epoch-v1', 'wrong_learning_kind')
    sources_check(manifest, ('scripts/transfer_learning.py',))
    require(state == cp['runner'], 'learning_checkpoint_state_mismatch')
    source = Path(manifest['source_directory']).resolve()
    require(not source.is_relative_to(root) and not root.is_relative_to(source), 'source_output_overlap')
    require(audit_run(source, strict=True)['ok'], 'historical_source_audit_failed')
    original, parent = read(source / 'manifest.json'), read(source / 'checkpoint.json')
    require(original['config']['algorithm'] == 'no_learning' and original['config']['split'] == 'dev'
            and original['config']['state_mode'] == 'skill_transfer', 'wrong_historical_treatment')
    require(sha(source / 'checkpoint.json') == manifest['source_checkpoint_sha256'], 'historical_checkpoint_hash')
    employee, day = manifest['employee'], manifest['cutoff_day']
    require(day == 9 and parent['ecosystem']['day'] == day
            and all(w['day'] == day for w in parent['ecosystem']['worlds'].values()), 'learning_cutoff_mismatch')
    require(cp['ecosystem'] == parent['ecosystem'] and digest(cp['ecosystem']) == manifest['parent_ecosystem_sha256'], 'learning_changed_parent_world')
    require(all(manifest[k] == original[k] for k in ('target_model', 'model_base_url')), 'historical_model_mismatch')
    limits = manifest['limits']
    expected = {'max_model_calls': 200, 'max_target_model_calls': 196, 'max_optimizer_model_calls': 4,
                'max_tokens': 4000000, 'max_seconds': 1800, 'max_iterations': 16, 'max_output_tokens': 4096,
                'train_cases': 2, 'val_cases': 2, 'rollouts_k': 2, 'edit_budget': 4, 'max_replays': 12}
    require(all(type(limits.get(k)) is int and limits[k] == v for k, v in expected.items()), 'learning_budget_contract')
    cfg = manifest['config']
    required_cfg = {'algorithm': 'skillopt', 'split': 'dev', 'state_mode': 'skill_transfer',
                    'focal_employee': employee, 'max_iterations': 16, 'max_output_tokens': 4096,
                    'max_learning_calls': 200, 'max_learning_tokens': 4000000, 'max_run_seconds': 1800,
                    'train_cases': 2, 'val_cases': 2, 'edit_budget': 4, 'skillopt_rollouts_k': 2}
    require(all(type(cfg.get(k)) is type(v) and cfg[k] == v for k, v in required_cfg.items()), 'learning_configuration_mismatch')
    require(all(cfg[k] == original['config'][k] for k in ('seed', 'days', 'feedback_delay')), 'historical_configuration_mismatch')
    parent_exps = {row['id']: row for row in parent['runner']['experiences']}
    parent_sessions = {row['id']: row for row in parent['runner']['sessions']}
    experiences = {row['id']: row for row in state['experiences']}
    selected = manifest['selected_experiences']
    require(len(experiences) == len(state['experiences']) == len(selected) == 4
            and [r['id'] for r in selected] == [r['id'] for r in state['experiences']], 'selected_experience_inventory')
    bindings = {'checkpoint.json': sha(source / 'checkpoint.json'), 'manifest.json': sha(source / 'manifest.json'),
                'skills/' + employee + '/v000.json': sha(child(source, 'skills/' + employee + '/v000.json'))}
    task_ids, capsules = set(), {}
    for row in selected:
        item, identifier = experiences[row['id']], row['id']
        record = parent_sessions[identifier]
        require(item == parent_exps[identifier] and digest(item) == row['experience_sha256'], 'altered_historical_experience')
        case_path, session_path = 'private/cases/' + identifier + '.json', 'work/' + identifier + '/session.json'
        capsule = read(child(source, case_path)); capsules[identifier] = capsule
        require(row['capsule_path'] == case_path and row['source_session_path'] == session_path
                and sha(child(source, case_path)) == row['capsule_sha256'] == sha(child(root, case_path))
                and sha(child(source, session_path)) == row['source_session_sha256'], 'historical_raw_evidence_binding')
        bindings[case_path], bindings[session_path] = row['capsule_sha256'], row['source_session_sha256']
        task = item['source_session']; earliest = record['day'] + cfg['feedback_delay']
        require(task not in task_ids and task == record['task_id'] == capsule['task_id'] == row['source_task_id'], 'duplicate_or_wrong_source_task')
        task_ids.add(task)
        require(item['employee'] == record['employee'] == capsule['employee'] == row['employee'] == employee
                and item['split'] == row['split'] == experience_split(task), 'cross_employee_or_split_experience')
        require('probe' not in capsule and capsule['case']['split'] == 'online'
                and record['day'] == row['source_day'] == capsule['case']['day'], 'future_probe_in_learning')
        for key in ('available_day', 'feedback_available_day'):
            require(type(item[key]) is int and earliest <= item[key] <= day and item[key] == row[key], 'future_historical_feedback')
        require(item['prompt'] == capsule['case']['request'] and json.loads(item['context']) == capsule['case']['public_files']
                and item['feedback'] == record['feedback'], 'altered_public_learning_context')
        session_check(record, child(source, session_path).parent, capsule)
    require(sorted(row['split'] for row in selected) == ['train', 'train', 'val', 'val'], 'learning_split_cardinality')
    require(manifest['source_files_sha256'] == bindings, 'historical_file_inventory')
    require({p.name for p in (root / 'private/cases').glob('*')} == {i + '.json' for i in experiences}, 'unexpected_learning_capsules')
    initial = read(child(root, 'skills/' + employee + '/v000.json'))
    require(initial == {'skill': SEED_SKILL, 'hash': skill_hash(SEED_SKILL), 'adopted_after_day': -1, 'version': 0}
            and manifest['initial_skill_sha256'] == initial['hash']
            and parent['runner']['skills'][employee] == SEED_SKILL and parent['runner']['skill_versions'][employee] == 0, 'learning_initial_skill')
    require(state['sessions'] == [] and number(state['elapsed_seconds']), 'unexpected_learning_online_sessions')
    updates = state['updates']
    require(len(updates) <= 1, 'multiple_learning_epochs')
    complete = state['status'] == 'completed'
    output.update(run_status=state['status'], target_sessions_checked=0, optimizer_operations_checked=0)
    require(state['status'] in ('initialized', 'running', 'completed', 'failed'), 'unknown_learning_status')
    if complete:
        require(manifest['execution_mode'] == 'native' and len(updates) == 1, 'completed_learning_requires_native_update')
        update = updates[0]
        require(update['employee'] == employee and update['day'] == day, 'wrong_learning_employee_or_day')
        require(set(update['train_ids'] + update['validation_ids']) == set(experiences), 'learning_selected_pool_mismatch')
        update_check(root, update, experiences, parent_sessions, cfg['feedback_delay'])
        uc = update['configuration']
        require(uc['rollouts_k'] == 2 and uc['edit_budget'] == 4 and uc['gate_mode'] == 'on'
                and uc['gate_no_regression'] is True and uc['evolve_memory'] is False, 'upstream_gate_contract')
        gate_check(update)
        targets = [op for op in update['costs']['operations'] if op['kind'] == 'target']
        rows = evidence['target_sessions']
        require(len(rows) == len(targets) == len(update['replay_evidence']) <= 12, 'target_evidence_inventory')
        for index, (row, op, replay) in enumerate(zip(rows, targets, update['replay_evidence'])):
            relative = f'learning/d{day:03d}-{employee}/trial-{index:03d}/session.json'
            path = child(root, relative); record = read(path)
            require(row['session_path'] == relative and row['session_sha256'] == sha(path), 'learning_native_session_hash')
            require(type(row['attempt_index']) is int and row['attempt_index'] == replay['attempt_index'] == op['attempt_index'] == index
                    and row['experience_id'] == replay['id'] == op['task_id']
                    and row['source_task_id'] == experiences[row['experience_id']]['source_session']
                    and row['phase'] == replay['phase'] == op['phase']
                    and row['sample_id'] == replay['sample_id'] == op['sample_id']
                    and row['cost'] == op and row['skill_sha256'] == replay['skill_sha256'] == record['skill']['content_sha256'], 'learning_attempt_binding')
            bounded(record)
            require('last_submitted_artifact_sha256' in record, 'missing_learning_last_submission_evidence')
            output['target_sessions_checked'] += 1
        require(evidence['optimizer_receipts'] == update['optimizer_transport_audit'], 'optimizer_evidence_mismatch')
        output['optimizer_operations_checked'] = len(evidence['optimizer_receipts'])
        calls = update['costs']['target_model_calls'] + update['costs']['optimizer_model_calls']
        tokens = update['costs']['tokens']
        require(type(state['learning_calls']) is int and type(state['learning_tokens']) is int
                and (state['learning_calls'], state['learning_tokens']) == (calls, tokens)
                and calls <= 200 and tokens <= 4000000 and update['costs']['optimizer_model_calls'] <= 4, 'learning_cost_totals')
        version = int(update['accepted'])
        final = read(child(root, f'skills/{employee}/v{version:03d}.json'))
        require(type(update['accepted']) is bool and update['parent_version'] == 0 and update['deployed_version'] == version
                and update['skill_before_sha256'] == initial['hash'] and update['skill_after_sha256'] == final['hash']
                and final['hash'] == skill_hash(final['skill']) and update['skill'] == final['skill']
                and final['version'] == version and (not version or final['adopted_after_day'] == day)
                and state['skills'] == {employee: final['skill']} and state['skill_versions'] == {employee: version}, 'learning_deployed_skill_chain')
        require({p.name for p in (root / 'skills' / employee).glob('*')} == {f'v{i:03d}.json' for i in range(version + 1)}, 'unexpected_skill_versions')
        output.update(accepted=update['accepted'], skill_sha256=final['hash'], model_calls=calls, charged_tokens=tokens)
    report_path = root / 'REPORT.json'
    if report_path.exists():
        report = read(report_path)
        require(report['status'] == state['status'] and report['manifest_sha256'] == sha(root / 'manifest.json')
                and report['evidence_path'] == 'evidence.json' and report['evidence_sha256'] == sha(root / 'evidence.json'), 'learning_report_binding')
        require(report['parent_unchanged'] is True and report['future_probes_evaluated'] is False
                and report['deployed_to_future_probes'] is False and manifest['future_probes_evaluated'] is False, 'learning_information_contract')
        if complete:
            require(report['employee'] == employee and report['cutoff_day'] == day and report['error_class'] is None
                    and report['execution_mode'] == 'native' and report['accepted'] == update['accepted']
                    and report['learning_status'] == update['status'] and report['skill_version'] == version
                    and report['skill_sha256'] == final['hash'], 'learning_report_outcome_mismatch')
            require(report['update_path'] == f'learning/d{day:03d}-{employee}/update.json'
                    and report['update_sha256'] == sha(child(root, report['update_path'])), 'learning_report_update_hash')
            usage = report['usage']
            require(usage['accounting_complete'] is True and usage['model_calls'] == calls and usage['tokens'] == tokens
                    and usage['target_model_calls'] == update['costs']['target_model_calls']
                    and usage['optimizer_model_calls'] == update['costs']['optimizer_model_calls']
                    and usage['charged_or_reserved_model_calls'] == calls and usage['charged_or_reserved_tokens'] == tokens
                    and usage['reserved_max_model_calls'] == 200 and usage['reserved_max_tokens'] == 4000000
                    and usage['elapsed_seconds'] == state['elapsed_seconds'], 'learning_report_usage_mismatch')
    elif complete:
        require(False, 'missing_completed_learning_report')
    pending = sorted(str(p.relative_to(root)) for pat in ('**/INFLIGHT.json', '**/FAILURE.json') for p in root.glob(pat))
    output['pending_artifacts'] = pending
    if complete:
        require(not pending, 'completed_learning_has_pending_artifacts')
    else:
        output['notes'].append('Learning is incomplete; no skill may be deployed and missing receipts are not model failures.')
    output['accounting_verified'] = complete
    output['status'] = 'valid_completed' if complete else 'incomplete'


def _audit(directory, strict, callback):
    root = Path(directory).resolve()
    result = {'schema_version': 1, 'run': str(root), 'status': 'invalid', 'errors': [], 'notes': [], 'accounting_verified': False,
              'model_quality_score': None, 'scope': 'Offline evidence consistency; no new calls or learning-effect claim.'}
    try:
        callback(root, result)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        result['errors'].append(str(exc) if type(exc) is ValueError else type(exc).__name__)
    result['ok'] = not result['errors'] and (not strict or result['status'] == 'valid_completed')
    return result


def audit_learning_epoch(directory, strict=True):
    return _audit(directory, strict, _learning)


def _transfer(root, output):
    # Pure selectors/aggregators are replayed only after their source is checked;
    # execution orchestration helpers are deliberately not called by this audit.
    from scripts.audit_calibration import audit_calibration
    from scripts.transfer_analysis import aggregate_probes, select_employee
    from scripts.transfer_probes import build_transfer_probes, public_probe_manifest
    manifest, state = read(root / 'manifest.json'), read(root / 'state.json')
    require(manifest['kind'] == 'native_employee_learning_transfer_diagnostic', 'wrong_transfer_kind')
    sources_check(manifest, ('scripts/run_transfer_experiment.py', 'scripts/transfer_learning.py',
        'scripts/transfer_analysis.py', 'scripts/transfer_probes.py', 'scripts/audit_transfer.py',
        'scripts/audit_calibration.py', 'scripts/audit_evaluation.py', 'scripts/calibration_bank.py', 'scripts/run_calibration.py'))
    config = {'cutoff_day': 9, 'probe_seed': 20260910, 'repeats': 2, 'max_model_calls': 256,
              'max_charged_tokens': 4000000, 'max_run_seconds': 1800, 'max_iterations': 16,
              'max_output_tokens': 4096, 'max_rollout_tokens': 250000, 'max_rollout_seconds': 420}
    require(reports_equal(manifest['config'], config), 'transfer_budget_contract')
    require(manifest['learning_contract'] == {'epochs': 1, 'rollouts_k': 2, 'train_cases': 2, 'val_cases': 2,
                'max_model_calls': 200, 'max_charged_tokens': 4000000, 'max_seconds': 1800}, 'transfer_learning_contract')
    source, calibration = (Path(manifest[k]).resolve() for k in ('source_directory', 'calibration_directory'))
    for a, b in ((source, calibration), (source, root), (calibration, root)):
        require(not a.is_relative_to(b) and not b.is_relative_to(a), 'source_output_overlap')
    require(sha(source / 'checkpoint.json') == manifest['source_checkpoint_sha256']
            and sha(source / 'manifest.json') == manifest['source_manifest_sha256'], 'transfer_historical_source_hash')
    require(set(manifest['calibration_sha256']) == {'manifest.json', 'bank.json', 'state.json', 'REPORT.json'}
            and all(sha(child(calibration, k)) == v for k, v in manifest['calibration_sha256'].items()), 'transfer_calibration_hash')
    require(audit_run(source, strict=True)['ok'] and audit_calibration(calibration, strict=True)['ok'], 'transfer_parent_audit_failed')
    require(Path(read(calibration / 'manifest.json')['source_directory']).resolve() == source, 'transfer_calibration_source_mismatch')
    parent, original = read(source / 'checkpoint.json'), read(source / 'manifest.json')
    require(all(manifest[k] == original[k] for k in ('target_model', 'model_base_url')), 'transfer_model_mismatch')
    selection = select_employee(parent, read(calibration / 'bank.json'), read(calibration / 'state.json'), cutoff_day=9)
    experiences = read(root / 'private/experiences.json')
    require(selection['employee'] == manifest['employee'] and selection['ranking'] == manifest['ranking']
            and selection['experiences'] == experiences and sha(root / 'private/experiences.json') == manifest['experiences_sha256']
            and [e['id'] for e in experiences] == manifest['experience_ids']
            and {e['id']: sha(child(source, 'private/cases/' + e['id'] + '.json')) for e in experiences} == manifest['source_case_sha256'], 'transfer_selection_changed')
    probes = build_transfer_probes(parent, manifest['employee'], cutoff_day=9, seed=20260910)
    require(public_probe_manifest(probes) == manifest['probe_manifest'], 'transfer_probe_manifest_changed')
    require(set(manifest['probe_files_sha256']) == {f'private/probes/probe-{i}.json' for i in range(4)}, 'transfer_probe_inventory')
    for index, capsule in enumerate(probes):
        path = root / f'private/probes/probe-{index}.json'
        require(read(path) == capsule and sha(path) == manifest['probe_files_sha256'][str(path.relative_to(root))], 'transfer_frozen_probe_changed')
    slots = []
    for repeat in range(2):
        for probe in range(4):
            for arm in (('seed', 'deployed') if (probe + repeat) % 2 == 0 else ('deployed', 'seed')):
                slots.append({'rollout_id': f'probe-{probe}-r{repeat}-{arm}', 'probe_index': probe, 'repeat_index': repeat, 'arm': arm})
    require(slots == manifest['slots'] and manifest['seed_skill_sha256'] == skill_hash(SEED_SKILL), 'transfer_slot_or_seed_contract')
    status = state['status']; output.update(run_status=status, checked_slots=0, expected_slots=16)
    require(status in ('prepared', 'running', 'learning_failed', 'completed', 'exhausted_time_budget',
                       'exhausted_compute_budget', 'infrastructure_error', 'infrastructure_invalid'), 'unknown_transfer_status')
    require(number(state['elapsed_seconds']) and type(state['next_slot']) is int, 'invalid_transfer_clock_or_cursor')
    if state['phase'] in ('prepared', 'learning'):
        require((state['phase'] == 'prepared' and status == 'prepared') or
                (state['phase'] == 'learning' and status in ('running', 'learning_failed')), 'transfer_phase_status_mismatch')
        require(not state['results'] and state['next_slot'] == state['charged_tokens'] == state['model_calls'] == 0,
                'probes_executed_before_learning_gate')
        require(not list((root / 'probes').glob('*')), 'untracked_early_probes')
        if status == 'prepared':
            require(not any((root / name).exists() for name in ('learning_epoch', 'INFLIGHT.json', 'FAILURE.json', 'REPORT.json')),
                    'prepared_transfer_has_execution_artifacts')
        if status == 'learning_failed':
            require((root / 'INFLIGHT.json').exists() and (root / 'FAILURE.json').exists(), 'failed_learning_missing_markers')
            report = read(root / 'REPORT.json')
            learning_audit = audit_learning_epoch(root / 'learning_epoch', strict=False)
            output['learning_audit'] = learning_audit
            usage = {'accounting_complete': False, 'model_calls': None, 'tokens': None,
                     'charged_or_reserved_model_calls': 200, 'charged_or_reserved_tokens': 4000000}
            if learning_audit['ok'] and learning_audit['accounting_verified']:
                usage = read(root / 'learning_epoch/REPORT.json')['usage']
            expected = {'status': 'learning_failed', 'complete': False, 'probes_attempted': 0,
                        'manifest_sha256': sha(root / 'manifest.json'), 'learning_usage': usage,
                        'probe_charged_or_reserved_tokens': 0, 'probe_charged_or_reserved_calls': 0,
                        'combined_charged_or_reserved_tokens': usage['charged_or_reserved_tokens'],
                        'combined_charged_or_reserved_calls': usage['charged_or_reserved_model_calls'],
                        'combined_budget_tokens': 8000000, 'combined_budget_calls': 456}
            require(reports_equal(report, expected), 'failed_learning_reservation_report_mismatch')
        output['notes'].append('Learning has not passed the independent deployment gate; all future probes remain missing.')
        output['status'] = 'incomplete'
        return
    require(state['phase'] == 'probes', 'unknown_transfer_phase')
    require(status not in ('prepared', 'learning_failed'), 'transfer_phase_status_mismatch')
    learning = audit_learning_epoch(root / 'learning_epoch', strict=True)
    output['learning_audit'] = learning
    require(learning['ok'], 'transfer_learning_audit_failed')
    epoch_manifest = read(root / 'learning_epoch/manifest.json')
    epoch_state = read(root / 'learning_epoch/state.json')
    epoch_report = read(root / 'learning_epoch/REPORT.json')
    require(Path(epoch_manifest['source_directory']).resolve() == source and epoch_manifest['employee'] == manifest['employee']
            and epoch_state['experiences'] == experiences, 'transfer_wrong_learning_epoch')
    deployed = epoch_state['skills'][manifest['employee']]
    require(state['learning_report_sha256'] == sha(root / 'learning_epoch/REPORT.json')
            and state['deployed_skill_sha256'] == skill_hash(deployed)
            and type(state['same_skill']) is bool and state['same_skill'] == (deployed == SEED_SKILL), 'transfer_skill_assignment')
    results = state['results']; tokens = calls = 0
    require(len(results) <= len(slots), 'too_many_transfer_attempts')
    for index, receipt in enumerate(results):
        slot = slots[index]
        require(all(type(receipt.get(k)) is type(v) and receipt[k] == v for k, v in slot.items()), 'transfer_receipts_not_planned_prefix')
        usage = receipt.get('usage') or {}
        known = usage.get('complete') is True and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('api_calls', 'total_tokens', 'charged_tokens'))
        calls += usage['api_calls'] if known else 16
        tokens += usage['charged_tokens'] if known else 250000
        directory = child(root, 'probes/' + slot['rollout_id']); path = directory / 'session.json'
        if receipt['status'] == 'completed':
            require(receipt['session_path'] == str(path.relative_to(root)) and receipt['session_sha256'] == sha(path), 'transfer_native_session_hash')
            record = read(path); capsule = probes[slot['probe_index']]
            session_check(record, directory, capsule); bounded(record)
            fields = ('success', 'semantic_score', 'infrastructure_valid', 'budget_exhausted', 'usage', 'diagnostic', 'elapsed_seconds', 'skill_loaded')
            require(all(reports_equal(receipt[k], record[k]) for k in fields), 'transfer_receipt_native_mismatch')
            assigned = SEED_SKILL if slot['arm'] == 'seed' else deployed
            require(record['skill']['content_sha256'] == skill_hash(assigned), 'transfer_wrong_arm_skill')
            require('last_submitted_artifact_sha256' in record, 'missing_transfer_last_submission_evidence')
            output['checked_slots'] += 1
        else:
            require(index == len(results) - 1 and status == receipt['status']
                    and status in ('infrastructure_error', 'infrastructure_invalid'), 'continued_after_transfer_trial_error')
            if known:
                require(path.exists() and read(path)['usage'] == usage, 'transfer_failure_usage_without_receipt')
    require(state['next_slot'] == len(results) - int(bool(results) and results[-1]['status'] == 'infrastructure_error'), 'transfer_checkpoint_cursor')
    require(type(state['charged_tokens']) is int and type(state['model_calls']) is int
            and (state['charged_tokens'], state['model_calls']) == (tokens, calls)
            and tokens <= 4000000 and calls <= 256, 'transfer_probe_cost_totals')
    require(sum(r['elapsed_seconds'] for r in results if number(r.get('elapsed_seconds'))) <= state['elapsed_seconds'] + 1e-9,
            'transfer_clock_below_recorded_rollouts')
    recorded = {r['rollout_id'] for r in results}
    inflight = read(root / 'INFLIGHT.json') if (root / 'INFLIGHT.json').exists() else None
    if inflight:
        require(inflight['phase'] == 'probes' and inflight['reserved_tokens'] == 250000 and inflight['reserved_calls'] == 16
                and any(all(inflight.get(k) == v for k, v in slot.items()) for slot in slots[max(0, state['next_slot']-1):state['next_slot']+1]), 'transfer_inflight_identity')
    require(all(p.name in recorded or inflight and p.name == inflight['rollout_id'] for p in (root / 'probes').glob('*') if p.is_dir()), 'unaccounted_transfer_directory')
    pending = sorted(str(p.relative_to(root)) for pat in ('**/INFLIGHT.json', '**/FAILURE.json') for p in root.glob(pat))
    output.update(pending_artifacts=pending, probe_model_calls=calls, probe_charged_tokens=tokens)
    report_path = root / 'REPORT.json'
    if report_path.exists():
        rebuilt = aggregate_probes(manifest['probe_manifest'], slots, results, same_skill=state['same_skill'])
        learning_usage = epoch_report['usage']
        campaign = {'learning_usage': learning_usage, 'probe_charged_or_reserved_tokens': tokens,
                    'probe_charged_or_reserved_calls': calls,
                    'combined_charged_or_reserved_tokens': learning_usage['charged_or_reserved_tokens'] + tokens,
                    'combined_charged_or_reserved_calls': learning_usage['charged_or_reserved_model_calls'] + calls,
                    'combined_budget_calls': 456, 'combined_budget_tokens': 8000000}
        rebuilt.update(status=status, manifest_sha256=sha(root / 'manifest.json'),
                       learning_report_sha256=state['learning_report_sha256'], deployed_skill_sha256=state['deployed_skill_sha256'],
                       actual_probe_elapsed_seconds=state['elapsed_seconds'], **campaign)
        require(reports_equal(read(report_path), rebuilt), 'transfer_report_mismatch')
    elif status == 'completed':
        require(False, 'missing_completed_transfer_report')
    if status == 'completed':
        require(len(results) == output['checked_slots'] == 16 and not pending, 'completed_transfer_has_missing_or_failed_slots')
    else:
        output['notes'].append('Incomplete probe schedule; missing or infrastructure-invalid attempts are not model failures.')
    output['status'] = 'valid_completed' if status == 'completed' else 'incomplete'


def audit_transfer(directory, strict=False):
    return _audit(directory, strict, _transfer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--learning-only', action='store_true')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    result = (audit_learning_epoch if args.learning_only else audit_transfer)(args.run, strict=args.strict)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
