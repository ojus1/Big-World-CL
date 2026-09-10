#!/usr/bin/env python3
"""Read-only observations of learning deadline/cost receipts; not a quality audit."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE = re.compile(r'firm-[0-9]+__(onboarding|renewal|incident)-regulated\Z')
RUN = re.compile(r'seed-[0-9]+-(no_learning|skillopt)\Z')
STATUSES = {'completed', 'budget_exhausted', 'failed', 'running', 'failed_or_interrupted'}
COUNTS = ('operations', 'target_operations', 'optimizer_operations', 'known_cost_records',
    'unknown_cost_records', 'malformed_records', 'reported_physical_call_cap_overruns',
    'reported_physical_token_cap_overruns', 'callback_wall_overruns', 'receipt_latency_overruns',
    'time_overruns_without_recorded_call_or_token_overrun', 'unknown_callback_wall_records',
    'unknown_receipt_latency_records', 'post_dispatch_budget_exceeded_operations',
    'recorded_known_physical_calls', 'recorded_known_tokens')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def read_hashed(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def count(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def summarize_update(update):
    """Inspect primitive ledger facts without grading or interpreting trace text."""
    if not isinstance(update, dict):
        raise ValueError('malformed_update')
    employee, day = update.get('employee'), update.get('day')
    if not isinstance(employee, str) or not EMPLOYEE.fullmatch(employee) or not count(day):
        raise ValueError('invalid_update_identity')
    status = update.get('status') if isinstance(update.get('status'), str) and update['status'] in STATUSES else 'unknown'
    costs = update.get('costs') if isinstance(update.get('costs'), dict) else {}
    ops = costs.get('operations'); stats = {key: 0 for key in COUNTS}
    malformed_container = not isinstance(ops, list)
    if malformed_container:
        ops = []; stats['malformed_records'] += 1
    all_completed = True
    for row in ops:
        stats['operations'] += 1
        if not isinstance(row, dict):
            stats['malformed_records'] += 1; stats['unknown_cost_records'] += 1
            stats['unknown_callback_wall_records'] += 1; stats['unknown_receipt_latency_records'] += 1
            all_completed = False
            continue
        kind = row.get('kind'); valid_kind = kind in ('target', 'optimizer')
        if valid_kind:
            stats[kind + '_operations'] += 1
        limits = row.get('limits') if isinstance(row.get('limits'), dict) else {}
        call_known = row.get('accounting') == 'reported' and count(row.get('model_calls'))
        token_known = row.get('accounting') == 'reported' and count(row.get('tokens'))
        known = call_known and token_known
        stats['known_cost_records' if known else 'unknown_cost_records'] += 1
        stats['recorded_known_physical_calls'] += row['model_calls'] if call_known else 0
        stats['recorded_known_tokens'] += row['tokens'] if token_known else 0
        call_cap_known = call_known and count(limits.get('max_model_calls')) and limits['max_model_calls'] > 0
        token_cap_known = token_known and count(limits.get('max_tokens')) and limits['max_tokens'] > 0
        cap_known = call_cap_known and token_cap_known
        call_over = call_cap_known and row['model_calls'] > limits['max_model_calls']
        token_over = token_cap_known and row['tokens'] > limits['max_tokens']
        stats['reported_physical_call_cap_overruns'] += int(call_over)
        stats['reported_physical_token_cap_overruns'] += int(token_over)
        timed = number(limits.get('timeout_seconds')) and limits['timeout_seconds'] > 0
        wall_known = timed and number(row.get('wall_seconds'))
        latency_known = timed and number(row.get('latency_ms'))
        wall_over = wall_known and row['wall_seconds'] > limits['timeout_seconds']
        latency_over = latency_known and row['latency_ms'] > limits['timeout_seconds'] * 1000
        stats['callback_wall_overruns'] += int(wall_over); stats['receipt_latency_overruns'] += int(latency_over)
        stats['unknown_callback_wall_records'] += int(not wall_known)
        stats['unknown_receipt_latency_records'] += int(not latency_known)
        stats['time_overruns_without_recorded_call_or_token_overrun'] += int(bool((wall_over or latency_over) and cap_known and not call_over and not token_over))
        stats['post_dispatch_budget_exceeded_operations'] += int(row.get('status') == 'budget_exceeded')
        valid_accounting = row.get('accounting') in ('reported', 'reservation')
        valid_values = all(count(row.get(key)) for key in ('model_calls', 'tokens'))
        invalid_timing = any(key in row and not number(row[key]) for key in ('wall_seconds', 'latency_ms'))
        if not valid_kind or not valid_accounting or not valid_values or not all(count(limits.get(key)) and limits[key] > 0 for key in ('max_model_calls', 'max_tokens')) or not timed or invalid_timing:
            stats['malformed_records'] += 1
        all_completed &= row.get('status') == 'completed' and known and wall_known and latency_known
    scored = len(update['replay_evidence']) if isinstance(update.get('replay_evidence'), list) else None
    artifacts = len(update['replay_artifacts']) if isinstance(update.get('replay_artifacts'), list) else None
    dispatched = None if malformed_container else stats['target_operations']
    difference = dispatched - scored if dispatched is not None and scored is not None else None
    ledger_replays = costs.get('replays') if count(costs.get('replays')) else None
    any_over = any(stats[key] for key in ('reported_physical_call_cap_overruns', 'reported_physical_token_cap_overruns',
        'callback_wall_overruns', 'receipt_latency_overruns', 'post_dispatch_budget_exceeded_operations'))
    stop = 'not_budget_exhausted'
    if status == 'budget_exhausted':
        stop = 'post_dispatch_budget_exceeded' if stats['post_dispatch_budget_exceeded_operations'] else (
            'pre_dispatch_stop_consistent' if all_completed and not any_over and not stats['malformed_records']
            and costs.get('accounting_complete') is True and ledger_replays == dispatched == scored == artifacts else 'unresolved')
    return {'employee': employee, 'day': day, 'update_status': status, **stats,
        'scored_replays': scored, 'replay_artifacts': artifacts, 'ledger_replay_count': ledger_replays,
        'dispatched_minus_scored': difference,
        'replay_count_disagreement': None if ledger_replays is None or dispatched is None or scored is None or artifacts is None
            else not (ledger_replays == dispatched == scored == artifacts),
        'stop_classification': stop, 'reported_accounting_complete': costs.get('accounting_complete') is True,
        'physical_inference_seconds': None}


def observe_campaign(directory):
    root = Path(directory).resolve()
    result = {'schema_version': 1, 'kind': 'learning_deadline_observations', 'errors': [], 'worlds': [],
        'quality_score': None, 'changes_original_audit': False, 'physical_inference_seconds': None,
        'interpretation': 'Recorded costs are not independently authenticated here. Callback wall includes local work and target cleanup; a timing overrun alone does not establish excess physical calls/tokens or inference after a deadline. Missing/pending records remain unknown. No work is rescored and original audit rules are unchanged.'}
    try:
        manifest, manifest_hash = read_hashed(root / 'campaign.json')
        if not isinstance(manifest, dict) or not isinstance(manifest.get('source_sha256'), dict):
            raise ValueError('invalid_manifest')
        result['provenance'] = {'campaign_sha256': manifest_hash, 'diagnostic_sha256': sha(__file__),
                                'execution_source_files': len(manifest['source_sha256'])}
        checks = []
        for name, expected in manifest['source_sha256'].items():
            if not isinstance(name, str) or not re.fullmatch(r'(lifespan|scripts)/[A-Za-z0-9_/]+\.py', name):
                raise ValueError('invalid_source_identity')
            checks.append(sha(ROOT / name) == expected)
        result['provenance']['execution_source_bytes_match'] = all(checks)
        for slot in manifest['slots']:
            identifier = slot['run_id']
            if not isinstance(identifier, str) or not RUN.fullmatch(identifier) or slot['relative_path'] != 'runs/' + identifier:
                raise ValueError('invalid_run_identity')
            run = root / slot['relative_path']; cp_path = run / 'checkpoint.json'
            row = {'run_id': identifier, 'checkpoint_present': cp_path.exists(), 'updates': [], 'pending_learning_progress': []}
            result['worlds'].append(row)
            if not cp_path.exists():
                continue
            cp, checkpoint_hash = read_hashed(cp_path); state = cp['runner']; row['checkpoint_sha256'] = checkpoint_hash
            row['observed_day'] = cp['ecosystem']['day'] if count(cp['ecosystem']['day']) else None
            keys = set()
            for update in state['updates']:
                summary = summarize_update(update); row['updates'].append(summary)
                keys.add(f"d{summary['day']:03d}-{summary['employee']}")
            for path in sorted((run / 'learning').glob('*/progress.json')):
                if path.parent.name in keys:
                    continue
                data, progress_hash = read_hashed(path)
                if not isinstance(data, dict):
                    raise ValueError('invalid_pending_record')
                employee, day = data.get('employee'), data.get('day')
                if not isinstance(employee, str) or not EMPLOYEE.fullmatch(employee) or not count(day):
                    raise ValueError('invalid_pending_identity')
                attempts = data.get('replay_artifacts'); dispatches = data.get('optimizer_dispatches')
                row['pending_learning_progress'].append({'employee': employee, 'day': day,
                    'status': data.get('status') if isinstance(data.get('status'), str) and data['status'] in STATUSES else 'unknown',
                    'target_dispatches': len(attempts) if isinstance(attempts, list) else None,
                    'optimizer_dispatches': len(dispatches) if isinstance(dispatches, list) else None,
                    'known_usage_target_records': sum(isinstance(a, dict) and a.get('usage_known') is True for a in attempts) if isinstance(attempts, list) else None,
                    'operation_timing_audit': 'unavailable_until_ledger_is_recorded', 'progress_sha256': progress_hash})
        updates = [u for world in result['worlds'] for u in world['updates']]
        result['totals'] = {key: sum(row[key] for row in updates) for key in COUNTS}
        result['totals'].update(checkpointed_updates=len(updates),
            pending_learning_progress_records=sum(len(w['pending_learning_progress']) for w in result['worlds']),
            stops=dict(Counter(row['stop_classification'] for row in updates)))
    except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
        result['errors'].append({'code': type(exc).__name__})
    result['ok'] = not result['errors']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('campaign', type=Path)
    result = observe_campaign(parser.parse_args().campaign)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
