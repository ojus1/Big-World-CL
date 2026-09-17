#!/usr/bin/env python3
"""Bounded native replays of an outcome-blind historical development bank.

This is repeated execution calibration, not a new reacting world or held-out
learning result. Unknown in-flight usage stops the run rather than disappearing.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import SEED_SKILL, digest
from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from lifespan.evaluation.hermes_transport import executor_options, manifest_fields
from lifespan.startup_observability import executor_options as startup_options, manifest_fields as startup_fields
from lifespan.evaluation.runtime import execute_case
from lifespan.mirofish import save
from scripts.audit_evaluation import audit_run, session_check
from scripts.calibration_bank import build_bank, aggregate_repeats


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_config(config):
    names = ('repeats', 'max_rollouts', 'max_model_calls', 'max_charged_tokens',
             'max_run_seconds', 'max_iterations', 'max_output_tokens',
             'max_rollout_tokens', 'max_rollout_seconds', 'order_seed')
    if set(config) != set(names):
        raise ValueError('Calibration config keys must exactly match the versioned contract')
    if any(type(config[name]) is not int or config[name] < (0 if name == 'order_seed' else 1) for name in names):
        raise ValueError('Calibration limits must be positive integers; order_seed may be zero')
    if config['repeats'] != 2:
        raise ValueError('This calibration contract requires exactly two repetitions')


def plan_slots(bank, config):
    slots = []
    for repeat in range(config['repeats']):
        selected = list(bank['selections'])
        random.Random(config['order_seed'] + repeat).shuffle(selected)
        for selection in selected:
            identifier = selection['selection_id']
            if not identifier or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.' for char in identifier):
                raise ValueError('Unsafe selection identity')
            slots.append({'selection_id': identifier, 'repeat_index': repeat,
                          'rollout_id': identifier + '-r' + str(repeat)})
    if len(slots) > config['max_rollouts']:
        raise ValueError('Declared rollout cap cannot accommodate the selected bank')
    return slots


def _capsule(source, selection):
    path = (source / selection['source_case_path']).resolve()
    if not path.is_relative_to((source / 'private/cases').resolve()):
        raise ValueError('Calibration case path leaves the private capsule directory')
    if file_hash(path) != selection['capsule_sha256']:
        raise ValueError('Historical capsule changed after selection')
    return json.loads(path.read_bytes())


def _manifest(source, bank, config, creds, slots):
    hashes = source_hashes()
    for name in ('scripts/run_calibration.py', 'scripts/calibration_bank.py', 'scripts/audit_evaluation.py'):
        hashes[name] = file_hash(ROOT / name)
    original = json.loads((source / 'manifest.json').read_bytes())
    source_state = json.loads((source / 'checkpoint.json').read_bytes())['runner']
    if any(source_state['skills'][row['employee']] != SEED_SKILL for row in bank['selections']):
        raise ValueError('Calibration seed skill differs from the source employee skill')
    if (creds['model'], creds['base_url']) != (original['target_model'], original['model_base_url']):
        raise ValueError('Calibration must use the declared source model and provider')
    return {'schema_version': 1, 'kind': 'native_historical_replay_calibration',
            **manifest_fields(original['config']), **startup_fields(original['config']),
            'source_directory': str(source), 'bank_sha256': digest(bank),
            'config': deepcopy(config), 'slots': slots, 'source_sha256': hashes,
            'target_model': creds['model'], 'model_base_url': creds['base_url'],
            'dependencies': dependency_provenance(), 'skill_sha256': hashlib.sha256(SEED_SKILL.encode()).hexdigest(),
            'information_contract': 'Original authorized request/files and historical rules; fresh private state; fixed initial skill.',
            'sampling': 'Fixed order permutation; hosted model randomness is not controlled.',
            'original_world_actor_compute_included': False}


def _accounted_usage(record, config):
    usage = (record or {}).get('usage') or {}
    known = usage.get('complete') is True and all(type(usage.get(key)) is int and usage[key] >= 0
        for key in ('api_calls', 'total_tokens', 'charged_tokens'))
    return (deepcopy(usage), usage['charged_tokens'], usage['api_calls']) if known else (
        {'complete': False, 'total_tokens': None, 'api_calls': None,
         'charged_tokens': config['max_rollout_tokens']}, config['max_rollout_tokens'], config['max_iterations'])


def run_calibration(source, out, config, *, stop_after=None, executor=execute_case, creds=None):
    validate_config(config)
    if stop_after is not None and (type(stop_after) is not int or stop_after < 1):
        raise ValueError('stop_after must be a positive invocation cap')
    source, out = Path(source).resolve(), Path(out).resolve()
    if source.is_relative_to(out) or out.is_relative_to(source):
        raise ValueError('Source and calibration output directories must be separate')
    source_audit = audit_run(source, strict=True)
    if not source_audit['ok']:
        raise ValueError('Historical source failed strict native artifact audit')
    bank = build_bank(source, repeats=config['repeats'])
    slots = plan_slots(bank, config)
    selections = {row['selection_id']: row for row in bank['selections']}
    creds = creds or credentials()
    manifest = _manifest(source, bank, config, creds, slots)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'INFLIGHT.json').exists():
        raise RuntimeError('Ambiguous calibration attempt needs reconciliation; automatic replay forbidden')
    if (out / 'manifest.json').exists():
        if json.loads((out / 'manifest.json').read_bytes()) != manifest:
            raise ValueError('Calibration source, bank, config or execution provenance changed')
        state = json.loads((out / 'state.json').read_bytes())
        if state['status'] not in ('running', 'paused_invocation_limit'):
            raise ValueError('Calibration is terminal; choose a new output directory')
        if (type(state['next_slot']) is not int or not 0 <= state['next_slot'] <= len(slots)
                or any(type(state[key]) is not int or state[key] < 0 for key in ('charged_tokens', 'model_calls'))
                or type(state['elapsed_seconds']) not in (int, float)
                or not math.isfinite(state['elapsed_seconds']) or state['elapsed_seconds'] < 0
                or json.loads((out / 'bank.json').read_bytes()) != bank
                or state['next_slot'] != len(state['results'])
                or any(any(result.get(key) != slot[key] for key in ('selection_id', 'repeat_index', 'rollout_id'))
                       for result, slot in zip(state['results'], slots))):
            raise ValueError('Calibration bank or checkpoint prefix changed')
        for result in state['results']:
            if result['status'] != 'completed' or result['infrastructure_valid'] is not True:
                raise ValueError('Invalid prior receipt requires a terminal calibration halt')
            path = (out / result['session_path']).resolve()
            if not path.is_relative_to((out / 'replays').resolve()) or file_hash(path) != result['session_sha256']:
                raise ValueError('Prior calibration evidence changed')
            record = json.loads(path.read_bytes())
            session_check(record, path.parent, _capsule(source, selections[result['selection_id']]), transport_manifest=manifest)
            if (record['skill']['content_sha256'] != manifest['skill_sha256']
                    or any(result[key] != record[key] for key in ('success', 'semantic_score', 'infrastructure_valid',
                        'budget_exhausted', 'usage', 'diagnostic', 'elapsed_seconds', 'skill_loaded'))):
                raise ValueError('Prior calibration receipt differs from verified native session')
        expected_tokens = sum(_accounted_usage(result, config)[1] for result in state['results'])
        expected_calls = sum(_accounted_usage(result, config)[2] for result in state['results'])
        if (state['charged_tokens'], state['model_calls']) != (expected_tokens, expected_calls):
            raise ValueError('Calibration budget checkpoint does not reconcile')
        if state['elapsed_seconds'] + 1e-9 < sum(row['elapsed_seconds'] for row in state['results']):
            raise ValueError('Calibration time checkpoint is shorter than recorded native execution')
        completed_ids = {row['rollout_id'] for row in state['results']}
        if any(path.is_dir() and path.name not in completed_ids for path in (out / 'replays').glob('*')):
            raise ValueError('Uncheckpointed replay directory needs reconciliation')
    else:
        if any(out.iterdir()):
            raise ValueError('Output directory contains unrecognized existing artifacts')
        save(out / 'manifest.json', manifest)
        save(out / 'bank.json', bank)
        state = {'status': 'running', 'next_slot': 0, 'results': [], 'charged_tokens': 0,
                 'model_calls': 0, 'elapsed_seconds': 0.0}
    initial = state['next_slot']
    started = time.monotonic()
    elapsed_before = state['elapsed_seconds']

    def checkpoint():
        state['elapsed_seconds'] = elapsed_before + time.monotonic() - started
        save(out / 'state.json', state)

    def finish(status):
        state['status'] = status
        checkpoint()
        report = aggregate_repeats(bank, state['results'])
        report.update(status=status, config=deepcopy(config), manifest_sha256=file_hash(out / 'manifest.json'),
                      actual_execution_elapsed_seconds=state['elapsed_seconds'],
                      charged_or_reserved_tokens=state['charged_tokens'], charged_or_reserved_calls=state['model_calls'])
        save(out / 'REPORT.json', report)
        return report

    checkpoint()
    for index in range(state['next_slot'], len(slots)):
        if stop_after is not None and index - initial >= stop_after:
            return finish('paused_invocation_limit')
        remaining = config['max_run_seconds'] - elapsed_before - (time.monotonic() - started)
        if remaining < config['max_rollout_seconds']:
            return finish('exhausted_time_budget')
        if (state['charged_tokens'] + config['max_rollout_tokens'] > config['max_charged_tokens']
                or state['model_calls'] + config['max_iterations'] > config['max_model_calls']):
            return finish('exhausted_compute_budget')
        slot = slots[index]
        selection = selections[slot['selection_id']]
        capsule = _capsule(source, selection)
        fork = Ecosystem.restore(capsule['ecosystem'])
        root = out / 'replays' / slot['rollout_id']
        if root.exists():
            raise RuntimeError('Uncheckpointed rollout directory exists; reconcile before resuming')
        save(out / 'INFLIGHT.json', {**slot, 'reserved_tokens': config['max_rollout_tokens'],
                                    'reserved_calls': config['max_iterations']})
        record = None
        try:
            record = executor(root=root, employee=capsule['employee'],
                world=fork.worlds[capsule['firm']], task_id=capsule['task_id'], case=capsule['case'],
                request=capsule['request'], skill=SEED_SKILL, credentials=creds,
                objectives=capsule['objectives'], business_files=capsule['business_files'],
                max_iterations=config['max_iterations'], max_tokens=config['max_output_tokens'],
                max_total_tokens=config['max_rollout_tokens'], timeout_seconds=config['max_rollout_seconds'],
                **executor_options(manifest), **startup_options(manifest))
            receipt = {**slot, 'status': 'completed' if record['infrastructure_valid'] else 'infrastructure_invalid',
                **{key: deepcopy(record[key]) for key in ('success', 'semantic_score', 'infrastructure_valid',
                    'budget_exhausted', 'usage', 'diagnostic', 'elapsed_seconds', 'skill_loaded')},
                'session_path': str((root / 'session.json').relative_to(out)),
                'session_sha256': file_hash(root / 'session.json')}
            if record['infrastructure_valid']:
                session_check(record, root, capsule, transport_manifest=manifest)
                if record['skill']['content_sha256'] != manifest['skill_sha256']:
                    raise ValueError('Calibration target skill changed')
            # Source bytes must stay unchanged after a mutable native replay.
            _capsule(source, selection)
        except Exception as exc:
            usage, charged, model_calls = _accounted_usage(record, config)
            state['charged_tokens'] += charged
            state['model_calls'] += model_calls
            state['results'].append({**slot, 'status': 'infrastructure_error',
                'success': None, 'semantic_score': None, 'infrastructure_valid': False,
                'budget_exhausted': False, 'skill_loaded': None, 'usage': usage,
                'diagnostic': {}, 'elapsed_seconds': None, 'error_type': type(exc).__name__})
            # Keep INFLIGHT: billing/completion may be unknown even in a private
            # fork. Never rerun this slot silently or label reserved cost measured.
            save(out / 'FAILURE.json', {'type': type(exc).__name__, 'slot': slot,
                                        'message': 'Inspect private rollout artifacts; no automatic retry.'})
            return finish('infrastructure_error')
        usage = record['usage']
        _, charged, model_calls = _accounted_usage(record, config)
        state['charged_tokens'] += charged
        state['model_calls'] += model_calls
        state['results'].append(receipt)
        state['next_slot'] = index + 1
        state['status'] = 'running' if record['infrastructure_valid'] else 'infrastructure_invalid'
        checkpoint()
        (out / 'INFLIGHT.json').unlink()
        print(f"Calibration {index + 1}/{len(slots)} {slot['rollout_id']} success={record['success']} calls={usage['api_calls']}", flush=True)
        if not record['infrastructure_valid']:
            return finish('infrastructure_invalid')
    return finish('completed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--config', default=ROOT / 'configs/calibration/replay_v1.json', type=Path)
    parser.add_argument('--stop-after-rollouts', type=int)
    args = parser.parse_args()
    result = run_calibration(args.source, args.out, json.loads(args.config.read_text()), stop_after=args.stop_after_rollouts)
    print(json.dumps({'status': result['status'], 'out': str(args.out)}))
    return 0 if result['status'] in ('completed', 'paused_invocation_limit') else 1


if __name__ == '__main__':
    raise SystemExit(main())
