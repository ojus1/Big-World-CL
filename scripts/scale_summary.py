"""Pure allowlisted learning/exposure summaries for a planned world campaign.

Inputs contain private checkpoints. Outputs contain counts, status, synthetic
identities and hashes only. This is descriptive evidence reconciliation, not a
replacement for native audits or commitment-level world-pair comparison.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math

from lifespan.ecosystem import WORKFLOWS
from lifespan.evaluation.protocol import ExperimentConfig, regime_at, scenario, select_experiences


VERSION = 'scale-learning-exposure-summary-v1'
REGIMES = ('base', 'changed', 'exception', 'reversal')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _integer(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _exposure(rows, known=True):
    if not known:
        return {'sessions': None, 'valid_sessions': None, 'successes': None, 'unknown_outcomes': None,
                'unique_obligations': None, 'mean_semantic_score': None}
    valid = [row for row in rows if row.get('infrastructure_valid') is True and type(row.get('success')) is bool]
    scores = [row['semantic_score'] for row in valid if _number(row.get('semantic_score'))]
    return {'sessions': len(rows), 'valid_sessions': len(valid), 'successes': sum(row['success'] for row in valid),
            'unknown_outcomes': len(rows) - len(valid), 'unique_obligations': len({row['task_id'] for row in rows}),
            'mean_semantic_score': sum(scores) / len(scores) if len(scores) == len(valid) and scores else None}


def build_scale_summary(campaign, records):
    """Summarize every planned run, employee and scheduled learning boundary.

    ``records`` contains mappings with ``run_id`` and optional parsed
    ``checkpoint``/``report``. Omitted runs remain in the result. Eligibility
    counts are independently reconstructed from both observation and feedback
    release times, and compared to ``runner.learning_eligibility`` when present.
    Future/unobserved boundaries are unknown, never invented zero-count updates.
    """
    slots = campaign['slots']
    planned = {slot['run_id']: slot for slot in slots}
    if not planned or len(planned) != len(slots):
        raise ValueError('Campaign run identities must be nonempty and unique')
    indexed = {}
    for record in records:
        identifier = record.get('run_id')
        if identifier not in planned or identifier in indexed:
            raise ValueError('Unknown or duplicate campaign raw record')
        indexed[identifier] = record
    runs, issues = [], []
    for slot in slots:
        run_id, config = slot['run_id'], ExperimentConfig(**slot['config'])
        if slot['algorithm'] != config.algorithm or slot['seed'] != config.seed:
            raise ValueError('Campaign slot and configuration disagree')
        spec = scenario(config)
        employees = [f'firm-{firm}__{workflow}-regulated' for firm in range(config.enterprise_count) for workflow in WORKFLOWS]
        configured_days = getattr(config, 'update_days', None)
        boundaries = list(configured_days) if configured_days is not None else list(
            range(config.update_every - 1, config.days - 1, config.update_every))
        raw = indexed.get(run_id, {})
        checkpoint, report = raw.get('checkpoint'), raw.get('report')
        known = checkpoint is not None
        state = checkpoint['runner'] if known else {}
        current_day = checkpoint['ecosystem']['day'] if known else None
        sessions, updates, experiences = (state.get(key, []) for key in ('sessions', 'updates', 'experiences'))
        logs = state.get('learning_eligibility', [])
        if known and not (type(current_day) is int and current_day >= -1):
            raise ValueError('Checkpoint observation day is invalid')
        status = report.get('status') if report else 'running' if known else 'not_started'
        allowed_status = {'completed', 'running', 'not_started', 'failed', 'paused_invocation_limit',
                          'exhausted_time_budget', 'exhausted_work_budget', 'exhausted_work_sessions', 'exhausted_compute_budget'}
        if status not in allowed_status:
            status = 'unknown_status'
        if report and not known:
            issues.append({'run_id': run_id, 'kind': 'report_without_checkpoint'})
        by_log = {}
        for log in logs:
            key = (log.get('employee'), log.get('day'))
            if key[0] not in employees or type(key[1]) is not int or key[1] not in boundaries or key in by_log:
                raise ValueError('Unknown or duplicate employee eligibility boundary')
            if not known or key[1] > current_day:
                raise ValueError('Eligibility log predates its checkpoint observation')
            by_log[key] = log
        for record in experiences:
            if (record.get('employee') not in employees or record.get('split') not in ('train', 'val')
                    or not isinstance(record.get('source_session'), str) or not record['source_session']
                    or not _integer(record.get('available_day'))
                    or not _integer(record.get('feedback_available_day', record.get('available_day')))):
                raise ValueError('Experience scope, underlying identity or release metadata is invalid')
        split_ownership = {}
        for record in experiences:
            key = (record['employee'], record['source_session'])
            if key in split_ownership and split_ownership[key] != record['split']:
                raise ValueError('One underlying obligation crosses training and validation')
            split_ownership[key] = record['split']
        for session in sessions:
            if (session.get('employee') not in employees or not _integer(session.get('day'))
                    or session['day'] >= config.days or session['day'] > current_day
                    or session.get('regime') != regime_at(spec, session['day'])
                    or not _integer(session.get('skill_version')) or not isinstance(session.get('task_id'), str)):
                raise ValueError('Session is outside the planned employee, time, regime or version scope')
        update_keys = set()
        for update in updates:
            key = (update.get('employee'), update.get('day'))
            if (key in update_keys or key[0] not in employees or type(key[1]) is not int or key[1] not in boundaries
                    or key[1] > current_day or type(update.get('accepted')) is not bool
                    or not _integer(update.get('parent_version')) or not _integer(update.get('deployed_version'))
                    or update.get('available_from_day') != key[1] + 1):
                raise ValueError('Update identity, timing or deployed version metadata is invalid')
            update_keys.add(key)
        employee_rows = []
        for employee in employees:
            own_sessions = [row for row in sessions if row['employee'] == employee]
            own_updates = [row for row in updates if row['employee'] == employee]
            accepted = [row for row in own_updates if row['accepted']]
            boundary_rows = []
            for day in boundaries:
                log = by_log.get((employee, day))
                observed = log is not None
                passed = known and (day < current_day or (day == current_day and state.get('phase') == 'advance') or status == 'completed')
                observed_status = 'observed' if observed else 'missing_log' if passed else 'not_reached'
                if observed_status == 'missing_log':
                    issues.append({'run_id': run_id, 'employee': employee, 'day': day, 'kind': 'missing_eligibility_log'})
                counts = Counter(row['split'] for row in select_experiences(experiences, employee, day, len(experiences), len(experiences))) if observed or passed else None
                eligible = counts['train'] >= config.train_cases and counts['val'] >= config.val_cases if counts is not None else None
                enabled = config.algorithm == 'skillopt' and (config.focal_employee is None or employee == config.focal_employee)
                boundary_updates = [row for row in own_updates if row['day'] == day]
                consistent = True
                if observed:
                    expected = {'available_unique_train': counts['train'], 'available_unique_val': counts['val'],
                                'eligible': eligible, 'treatment_enabled': enabled}
                    consistent = all(type(log.get(key)) is type(value) and log[key] == value for key, value in expected.items())
                    if not consistent:
                        issues.append({'run_id': run_id, 'employee': employee, 'day': day, 'kind': 'eligibility_count_or_treatment_mismatch'})
                boundary_rows.append({'day': day, 'observation_status': observed_status,
                    'available_unique_train': counts['train'] if counts is not None else None,
                    'available_unique_val': counts['val'] if counts is not None else None,
                    'eligible': eligible, 'treatment_enabled': enabled, 'logged_counts_match': consistent if observed else None,
                    'actual_updates': len(boundary_updates) if known and (observed or passed) else None,
                    'accepted_updates': sum(row['accepted'] for row in boundary_updates) if known and (observed or passed) else None,
                    'eligible_without_recorded_update': bool(eligible and enabled and not boundary_updates) if observed or passed else None})
            versions = sorted({0, *[row['deployed_version'] for row in own_updates], *[row['skill_version'] for row in own_sessions]})
            version_rows = []
            for version in versions:
                deployment = next((row for row in accepted if row['deployed_version'] == version), None)
                available = 0 if version == 0 else deployment['available_from_day'] if deployment else None
                exposure = [row for row in own_sessions if row['skill_version'] == version]
                premature = [row for row in exposure if available is None or row['day'] < available]
                if premature:
                    issues.append({'run_id': run_id, 'employee': employee, 'version': version, 'kind': 'unadopted_or_premature_version_exposure', 'sessions': len(premature)})
                version_rows.append({'version': version, 'available_from_day': available,
                    'first_observed_day': min((row['day'] for row in exposure), default=None),
                    **_exposure(exposure, known), 'premature_or_unadopted_sessions': len(premature) if known else None})
            public_updates = []
            for update in own_updates:
                costs = update.get('costs', {})
                public_updates.append({'day': update['day'], 'accepted': update['accepted'],
                    'available_from_day': update['available_from_day'], 'parent_version': update['parent_version'],
                    'deployed_version': update['deployed_version'],
                    'status': update.get('status') if update.get('status') in ('completed', 'failed', 'budget_exhausted') else 'unknown',
                    'costs': {key: costs.get(key) if _integer(costs.get(key)) else None for key in ('tokens', 'target_model_calls', 'optimizer_model_calls', 'replays')},
                    'accounting_complete': costs.get('accounting_complete') is True})
            employee_rows.append({'employee': employee, **_exposure(own_sessions, known),
                'actual_updates': len(own_updates) if known else None,
                'accepted_updates': len(accepted) if known else None,
                'learning_boundaries': boundary_rows, 'updates': public_updates,
                'versions': version_rows, 'regimes': [{'regime': regime, **_exposure([row for row in own_sessions if row['regime'] == regime], known)} for regime in REGIMES]})
        runs.append({'run_id': run_id, 'seed': slot['seed'], 'algorithm': slot['algorithm'], 'status': status,
                     'checkpoint_present': known, 'observed_day': current_day,
                     'checkpoint_sha256': _hash(checkpoint) if known else None, 'report_sha256': _hash(report) if report else None,
                     'planned_employees': len(employees), 'scheduled_boundaries': boundaries, 'employees': employee_rows})
    all_boundaries = [boundary for run in runs for employee in run['employees'] for boundary in employee['learning_boundaries']]
    all_employees = [employee for run in runs for employee in run['employees']]
    return {'schema_version': 1, 'summary_version': VERSION, 'hash_encoding': 'canonical_json',
            'hash_format': 'JSON with sorted keys, compact separators, ensure_ascii=true, encoded as UTF-8; not raw file bytes.',
            'campaign_sha256': _hash(campaign),
            'planned_runs': len(runs), 'completed_runs': sum(run['status'] == 'completed' and run['checkpoint_present'] for run in runs),
            'missing_checkpoints': sum(not run['checkpoint_present'] for run in runs),
            'planned_employee_world_instances': len(all_employees), 'planned_learning_boundaries': len(all_boundaries),
            'observed_learning_boundaries': sum(row['observation_status'] == 'observed' for row in all_boundaries),
            'observed_ineligible_boundaries': sum(row['observation_status'] == 'observed' and row['eligible'] is False for row in all_boundaries),
            'recorded_updates': sum(employee['actual_updates'] or 0 for employee in all_employees),
            'accepted_updates': sum(employee['accepted_updates'] or 0 for employee in all_employees),
            'runs': runs, 'evidence_issues': issues,
            'complete': all(run['status'] == 'completed' and run['checkpoint_present'] for run in runs) and not issues,
            'interpretation': 'All planned employees and boundaries are retained. Unreached observations and missing checkpoints are unknown, not zero eligibility. '
                'Recorded update totals are partial when runs are incomplete. Exposure is prospective only when its logged version was previously adopted. '
                'Employee/session counts are dependent descriptive exposures, not independent world replications; native and commitment audits remain separate.'}
