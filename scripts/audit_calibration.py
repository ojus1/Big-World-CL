#!/usr/bin/env python3
"""Offline audit of calibration evidence; --strict requires all planned slots.

An incomplete campaign can have consistent reservations and missing slots. That
does not make those slots model failures or establish a learning-effect estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_evaluation import audit_run, child, read, reports_equal, require, session_check
from scripts.calibration_bank import aggregate_repeats, build_bank
from lifespan.evaluation.protocol import SEED_SKILL


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _audit(root, output):
    manifest, bank, state = (read(root / name) for name in ('manifest.json', 'bank.json', 'state.json'))
    config = manifest['config']
    require(manifest['kind'] == 'native_historical_replay_calibration', 'wrong_campaign_kind')
    require(config['repeats'] == bank['repeats_per_selection'] == 2, 'repeat_contract')
    require(all(type(v) is int and v >= (0 if k == 'order_seed' else 1) for k, v in config.items()), 'invalid_campaign_config')
    source = Path(manifest['source_directory']).resolve()
    require(not source.is_relative_to(root) and not root.is_relative_to(source), 'source_output_overlap')
    # All recorded implementation files must match; use the historical checkout
    # if a future executor/grader/selector change makes this check fail.
    for name, expected in manifest['source_sha256'].items():
        require(sha(child(ROOT, name)) == expected, 'campaign_source_revision_mismatch')
    required = {'lifespan/evaluation/tasks.py', 'lifespan/evaluation/runtime.py', 'lifespan/evaluation/budget.py',
                'lifespan/computers.py', 'lifespan/ecosystem.py', 'lifespan/world.py', 'lifespan/evaluation/protocol.py',
                'scripts/run_calibration.py', 'scripts/calibration_bank.py', 'scripts/audit_evaluation.py'}
    require(required <= set(manifest['source_sha256']), 'missing_campaign_source_provenance')
    require(audit_run(source, strict=True)['ok'], 'historical_source_audit_failed')
    rebuilt_bank = build_bank(source, repeats=config['repeats'])
    require(bank == rebuilt_bank and digest(bank) == manifest['bank_sha256'], 'calibration_bank_mismatch')
    original = read(source / 'manifest.json')
    require(all(manifest[k] == original[k] for k in ('target_model', 'model_base_url')), 'source_provider_mismatch')
    original_skills = read(source / 'checkpoint.json')['runner']['skills']
    require(hashlib.sha256(SEED_SKILL.encode()).hexdigest() == manifest['skill_sha256'], 'calibration_initial_skill_mismatch')
    require(all(hashlib.sha256(original_skills[row['employee']].encode()).hexdigest() == manifest['skill_sha256']
                for row in bank['selections']), 'source_seed_skill_mismatch')
    slots = []
    for repeat in range(config['repeats']):
        selections = list(bank['selections'])
        random.Random(config['order_seed'] + repeat).shuffle(selections)
        slots.extend({'selection_id': row['selection_id'], 'repeat_index': repeat,
                      'rollout_id': row['selection_id'] + '-r' + str(repeat)} for row in selections)
    require(slots == manifest['slots'] and len(slots) <= config['max_rollouts'], 'planned_slot_order_mismatch')
    results, cursor = state['results'], state['next_slot']
    require(type(cursor) is int and 0 <= cursor <= len(slots) and len(results) <= len(slots), 'invalid_slot_cursor')
    require(type(state['elapsed_seconds']) in (int, float) and math.isfinite(state['elapsed_seconds'])
            and state['elapsed_seconds'] >= 0, 'invalid_elapsed_time')
    status = state['status']
    require(status in ('running', 'paused_invocation_limit', 'completed', 'exhausted_time_budget',
                      'exhausted_compute_budget', 'infrastructure_error', 'infrastructure_invalid'), 'unknown_campaign_status')
    output.update(run_status=status, expected_slots=len(slots), checked_slots=0,
                  trial_errors=[], pending_artifacts=[], uncheckpointed_replay_directories=[])
    selections = {row['selection_id']: row for row in bank['selections']}
    total_tokens = total_calls = 0
    for index, result in enumerate(results):
        slot = slots[index]
        require(all(type(result.get(k)) is type(v) and result[k] == v for k, v in slot.items()), 'receipt_not_planned_prefix')
        require(result['status'] in ('completed', 'infrastructure_error', 'infrastructure_invalid'), 'invalid_receipt_status')
        if result['status'] != 'completed':
            output['trial_errors'].append(slot['rollout_id'])
            require(index == len(results) - 1 and status in ('infrastructure_error', 'infrastructure_invalid'), 'continued_after_infrastructure_failure')
        usage = result.get('usage') or {}
        known = usage.get('complete') is True and all(type(usage.get(k)) is int and usage[k] >= 0
                    for k in ('api_calls', 'total_tokens', 'charged_tokens'))
        total_tokens += usage['charged_tokens'] if known else config['max_rollout_tokens']
        total_calls += usage['api_calls'] if known else config['max_iterations']
        selection = selections[slot['selection_id']]
        case_path = child(source / 'private/cases', Path(selection['source_case_path']).name)
        require(selection['capsule_hash_encoding'] == 'raw_file_bytes' and sha(case_path) == selection['capsule_sha256'], 'source_capsule_hash_mismatch')
        capsule = read(case_path)
        directory = child(root, 'replays/' + slot['rollout_id'])
        path = directory / 'session.json'
        if result['status'] == 'completed':
            require(result.get('session_path') == str(path.relative_to(root)) and sha(path) == result['session_sha256'], 'native_session_hash_or_path_mismatch')
            record = read(path)
            session_check(record, directory, capsule)
            require(record['skill']['content_sha256'] == manifest['skill_sha256'], 'calibration_skill_hash')
            fields = ('success', 'semantic_score', 'infrastructure_valid', 'budget_exhausted', 'usage',
                      'diagnostic', 'elapsed_seconds', 'skill_loaded')
            require(all(result[k] == record[k] for k in fields), 'receipt_native_session_mismatch')
            meter = record['result']['native']['evaluation_budget']
            require(meter['physical_model_calls'] <= config['max_iterations'] and meter['charged_tokens'] <= config['max_rollout_tokens']
                    and all(row['output_cap'] <= config['max_output_tokens'] for row in meter['operations']), 'per_rollout_physical_budget')
            output['checked_slots'] += 1
        elif path.exists() and known:
            # Failed audit/transport remains a trial error, but known charges
            # cannot be fabricated or replaced by an arbitrary reservation.
            require(read(path)['usage'] == usage, 'failed_receipt_known_usage_mismatch')
        elif known:
            require(False, 'known_usage_without_native_receipt')
    expected_cursor = len(results) - int(bool(results) and results[-1]['status'] == 'infrastructure_error')
    require(cursor == expected_cursor, 'checkpoint_cursor_mismatch')
    require(type(state['charged_tokens']) is int and type(state['model_calls']) is int
            and (state['charged_tokens'], state['model_calls']) == (total_tokens, total_calls), 'campaign_cost_totals')
    measured_elapsed = sum(row['elapsed_seconds'] for row in results if type(row.get('elapsed_seconds')) in (int, float))
    require(math.isfinite(measured_elapsed) and measured_elapsed <= state['elapsed_seconds'] + 1e-9, 'checkpoint_elapsed_below_recorded_rollouts')
    require(total_tokens <= config['max_charged_tokens'] and total_calls <= config['max_model_calls'], 'campaign_budget_exceeded')
    inflight = root / 'INFLIGHT.json'
    if inflight.exists():
        marker = read(inflight)
        candidates = slots[max(0, cursor - 1):min(len(slots), cursor + 1)]
        require(any(all(marker.get(k) == v for k, v in slot.items()) for slot in candidates)
                and marker.get('reserved_tokens') == config['max_rollout_tokens']
                and marker.get('reserved_calls') == config['max_iterations'], 'inflight_reservation_identity')
    recorded_ids = {row['rollout_id'] for row in results}
    output['uncheckpointed_replay_directories'] = sorted(p.name for p in (root / 'replays').glob('*')
                                                       if p.is_dir() and p.name not in recorded_ids)
    pending_id = read(inflight)['rollout_id'] if inflight.exists() else None
    require(all(name == pending_id for name in output['uncheckpointed_replay_directories']), 'unaccounted_replay_directory')
    output['pending_artifacts'] = sorted(str(p.relative_to(root)) for pattern in ('**/INFLIGHT.json', '**/FAILURE.json') for p in root.glob(pattern))
    rebuilt = aggregate_repeats(bank, results)
    rebuilt.update(status=status, config=config, manifest_sha256=sha(root / 'manifest.json'),
                   actual_execution_elapsed_seconds=state['elapsed_seconds'], charged_or_reserved_tokens=total_tokens,
                   charged_or_reserved_calls=total_calls)
    if (root / 'REPORT.json').exists() and status != 'running':
        require(reports_equal(read(root / 'REPORT.json'), rebuilt), 'calibration_report_mismatch')
    if status == 'completed':
        require((root / 'REPORT.json').exists() and cursor == len(slots) and not output['trial_errors']
                and not output['pending_artifacts'] and not output['uncheckpointed_replay_directories'], 'completed_campaign_unreconciled')
    output.update(status='valid_completed' if status == 'completed' else 'incomplete',
                  charged_or_reserved_tokens=total_tokens, charged_or_reserved_calls=total_calls,
                  all_native_receipts_valid=rebuilt['all_native_receipts_valid'])


def audit_calibration(directory, strict=False):
    root = Path(directory).resolve()
    output = {'schema_version': 1, 'status': 'invalid', 'errors': [], 'model_quality_score': None,
              'scope': 'Calibration artifact integrity; incomplete slots are not model failures and this is not learning-effect evidence.'}
    try:
        _audit(root, output)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        output['errors'].append(str(exc) if type(exc) is ValueError else type(exc).__name__)
    output['ok'] = not output['errors'] and (not strict or output['status'] == 'valid_completed')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    result = audit_calibration(args.directory, strict=args.strict)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
