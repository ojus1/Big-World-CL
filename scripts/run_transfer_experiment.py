#!/usr/bin/env python3
"""One preregistered native learning epoch followed by frozen development probes.

Preparation writes all future probes before any learning call. Execution is a
single bounded invocation: uncertain or interrupted work is never retried by
this command. Raw artifacts are private; REPORT contains descriptive evidence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import SEED_SKILL, digest
from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from lifespan.evaluation.hermes_transport import executor_options, manifest_fields, mode
from lifespan.startup_observability import executor_options as startup_options, manifest_fields as startup_fields
from lifespan.evaluation.runtime import execute_case
from lifespan.mirofish import save
from scripts.audit_calibration import audit_calibration
from scripts.audit_evaluation import audit_run, session_check
from scripts.run_calibration import _accounted_usage
from scripts.transfer_analysis import select_employee, aggregate_probes
from scripts.transfer_probes import build_transfer_probes, public_probe_manifest

CONFIG = {'cutoff_day': 9, 'probe_seed': 20260910, 'repeats': 2,
          'max_model_calls': 256, 'max_charged_tokens': 4000000,
          'max_run_seconds': 1800, 'max_iterations': 16, 'max_output_tokens': 4096,
          'max_rollout_tokens': 250000, 'max_rollout_seconds': 420}
LEARNING_CONTRACT = {'epochs': 1, 'rollouts_k': 2, 'train_cases': 2, 'val_cases': 2,
                     'max_model_calls': 200, 'max_charged_tokens': 4000000, 'max_seconds': 1800}
CODE_FILES = ('scripts/run_transfer_experiment.py', 'scripts/transfer_learning.py',
              'scripts/transfer_probes.py', 'scripts/transfer_analysis.py',
              'scripts/audit_transfer.py', 'scripts/audit_calibration.py',
              'scripts/run_calibration.py', 'scripts/calibration_bank.py',
              'scripts/audit_evaluation.py')
RECEIPT_FIELDS = ('success', 'semantic_score', 'infrastructure_valid',
                  'budget_exhausted', 'usage', 'diagnostic', 'elapsed_seconds', 'skill_loaded')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def skill_hash(skill):
    return hashlib.sha256(skill.encode()).hexdigest()


def campaign_usage(learning_usage, state):
    """Keep epoch and probe accounting separate, then add their bounded charges."""
    return {'learning_usage': deepcopy(learning_usage),
            'probe_charged_or_reserved_tokens': state['charged_tokens'],
            'probe_charged_or_reserved_calls': state['model_calls'],
            'combined_charged_or_reserved_tokens': learning_usage['charged_or_reserved_tokens'] + state['charged_tokens'],
            'combined_charged_or_reserved_calls': learning_usage['charged_or_reserved_model_calls'] + state['model_calls'],
            'combined_budget_tokens': 8000000, 'combined_budget_calls': 456}


def plan_slots():
    slots = []
    for repeat in range(2):
        for probe in range(4):
            arms = ('seed', 'deployed') if (probe + repeat) % 2 == 0 else ('deployed', 'seed')
            for arm in arms:
                slots.append({'rollout_id': f'probe-{probe}-r{repeat}-{arm}',
                              'probe_index': probe, 'repeat_index': repeat, 'arm': arm})
    return slots


def _separate(*paths):
    for index, first in enumerate(paths):
        for second in paths[index + 1:]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError('Source, calibration and output directories must be separate')


def prepare(source, calibration, out):
    source, calibration, out = (Path(p).resolve() for p in (source, calibration, out))
    _separate(source, calibration, out)
    if out.exists():
        raise ValueError('Preparation requires a fresh output directory')
    if not audit_run(source, strict=True)['ok'] or not audit_calibration(calibration, strict=True)['ok']:
        raise ValueError('Source and complete calibration must pass strict native audits')
    if Path(read(calibration / 'manifest.json')['source_directory']).resolve() != source:
        raise ValueError('Calibration belongs to a different source run')
    checkpoint = read(source / 'checkpoint.json')
    selection = select_employee(checkpoint, read(calibration / 'bank.json'), read(calibration / 'state.json'),
                                cutoff_day=CONFIG['cutoff_day'])
    employee = selection['employee']
    if checkpoint['runner']['skills'][employee] != SEED_SKILL:
        raise ValueError('Source initial skill differs from the declared fixed baseline')
    probes = build_transfer_probes(checkpoint, employee, cutoff_day=CONFIG['cutoff_day'], seed=CONFIG['probe_seed'])
    public_probes = public_probe_manifest(probes)
    code = {**source_hashes(), **{name: sha(ROOT / name) for name in CODE_FILES}}
    original = read(source / 'manifest.json')
    if mode(read(calibration / 'manifest.json')) != mode(original['config']):
        raise ValueError('Calibration transport differs from source transport')
    out.mkdir(parents=True)
    for index, capsule in enumerate(probes):
        save(out / 'private/probes' / f'probe-{index}.json', capsule)
    save(out / 'private/experiences.json', selection['experiences'])
    manifest = {'schema_version': 1, 'kind': 'native_employee_learning_transfer_diagnostic',
                **manifest_fields(original['config']), **startup_fields(original['config']),
                'source_directory': str(source), 'calibration_directory': str(calibration),
                'source_checkpoint_sha256': sha(source / 'checkpoint.json'),
                'source_manifest_sha256': sha(source / 'manifest.json'),
                'calibration_sha256': {name: sha(calibration / name)
                                      for name in ('manifest.json', 'bank.json', 'state.json', 'REPORT.json')},
                'config': deepcopy(CONFIG), 'employee': employee, 'ranking': selection['ranking'],
                'experience_ids': [row['id'] for row in selection['experiences']],
                'experiences_sha256': sha(out / 'private/experiences.json'),
                'source_case_sha256': {row['id']: sha(source / 'private/cases' / (row['id'] + '.json'))
                                       for row in selection['experiences']},
                'probe_manifest': public_probes,
                'probe_files_sha256': {f'private/probes/probe-{i}.json': sha(out / 'private/probes' / f'probe-{i}.json')
                                       for i in range(4)},
                'slots': plan_slots(), 'source_sha256': code, 'dependencies': dependency_provenance(),
                'target_model': original['target_model'], 'model_base_url': original['model_base_url'],
                'seed_skill_sha256': skill_hash(SEED_SKILL),
                'selection_scope': 'Outcome-selected development employee; no population or final-test claim.',
                'learning_contract': deepcopy(LEARNING_CONTRACT),
                'information_contract': 'Future probes withheld from optimizer training and validation; frozen deployed skill.',
                'sampling': 'Fresh hosted model calls; provider randomness uncontrolled; all repeats retained.',
                'original_world_actor_compute_included': False}
    save(out / 'manifest.json', manifest)
    save(out / 'state.json', {'status': 'prepared', 'phase': 'prepared', 'next_slot': 0, 'results': [],
                             'charged_tokens': 0, 'model_calls': 0, 'elapsed_seconds': 0.0})
    return manifest


def validate_prepared(out):
    """Rebuild all frozen inputs without executing a model or exposing probes."""
    out = Path(out).resolve()
    manifest = read(out / 'manifest.json')
    source, calibration = (Path(manifest[name]).resolve() for name in ('source_directory', 'calibration_directory'))
    _separate(source, calibration, out)
    if (manifest['kind'] != 'native_employee_learning_transfer_diagnostic' or manifest['schema_version'] != 1
            or manifest['config'] != CONFIG or manifest['slots'] != plan_slots()
            or manifest['learning_contract'] != LEARNING_CONTRACT
            or set(manifest['calibration_sha256']) != {'manifest.json', 'bank.json', 'state.json', 'REPORT.json'}):
        raise ValueError('Transfer execution contract changed')
    expected_code = {**source_hashes(), **{name: sha(ROOT / name) for name in CODE_FILES}}
    if manifest['source_sha256'] != expected_code or manifest['dependencies'] != dependency_provenance():
        raise ValueError('Transfer execution code or native dependencies changed')
    if (sha(source / 'checkpoint.json') != manifest['source_checkpoint_sha256']
            or sha(source / 'manifest.json') != manifest['source_manifest_sha256']
            or any(sha(calibration / name) != value for name, value in manifest['calibration_sha256'].items())):
        raise ValueError('Transfer source or calibration evidence changed')
    if not audit_run(source, strict=True)['ok'] or not audit_calibration(calibration, strict=True)['ok']:
        raise ValueError('Transfer source audit failed')
    if Path(read(calibration / 'manifest.json')['source_directory']).resolve() != source:
        raise ValueError('Calibration source mismatch')
    original = read(source / 'manifest.json')
    if mode(manifest) != mode(original['config']) or mode(read(calibration / 'manifest.json')) != mode(original['config']):
        raise ValueError('Transfer transport differs from source or calibration')
    if any(manifest[key] != original[key] for key in ('target_model', 'model_base_url')):
        raise ValueError('Transfer model/provider differs from historical source')
    selection = select_employee(read(source / 'checkpoint.json'), read(calibration / 'bank.json'),
                                read(calibration / 'state.json'), cutoff_day=CONFIG['cutoff_day'])
    if (selection['employee'] != manifest['employee'] or selection['ranking'] != manifest['ranking']
            or selection['experiences'] != read(out / 'private/experiences.json')
            or sha(out / 'private/experiences.json') != manifest['experiences_sha256']
            or manifest['experience_ids'] != [row['id'] for row in selection['experiences']]
            or manifest['source_case_sha256'] != {row['id']: sha(source / 'private/cases' / (row['id'] + '.json'))
                                                 for row in selection['experiences']}):
        raise ValueError('Employee selection or optimizer experience changed')
    probes = build_transfer_probes(read(source / 'checkpoint.json'), manifest['employee'],
                                  cutoff_day=CONFIG['cutoff_day'], seed=CONFIG['probe_seed'])
    expected_paths = {f'private/probes/probe-{i}.json' for i in range(4)}
    if set(manifest['probe_files_sha256']) != expected_paths:
        raise ValueError('Frozen probe inventory changed')
    if any(read(out / f'private/probes/probe-{i}.json') != capsule for i, capsule in enumerate(probes)):
        raise ValueError('Frozen future probe capsule changed')
    if (public_probe_manifest(probes) != manifest['probe_manifest']
            or any(sha(out / name) != value for name, value in manifest['probe_files_sha256'].items())
            or manifest['seed_skill_sha256'] != skill_hash(SEED_SKILL)):
        raise ValueError('Frozen probe or seed skill hash changed')
    return manifest, probes, selection['experiences']


def execute(out, *, creds=None, executor=execute_case, learning_executor=None, learning_auditor=None):
    out = Path(out).resolve()
    state = read(out / 'state.json')
    if state != {'status': 'prepared', 'phase': 'prepared', 'next_slot': 0, 'results': [],
                 'charged_tokens': 0, 'model_calls': 0, 'elapsed_seconds': 0.0} or (out / 'INFLIGHT.json').exists():
        raise RuntimeError('This bounded campaign cannot resume or replay uncertain prior execution')
    if any((out / name).exists() for name in ('learning_epoch', 'probes', 'REPORT.json', 'FAILURE.json')):
        raise RuntimeError('Existing execution evidence requires reconciliation')
    manifest, probes, experiences = validate_prepared(out)
    creds = creds or credentials()
    if (creds['model'], creds['base_url']) != (manifest['target_model'], manifest['model_base_url']):
        raise ValueError('Transfer must use the preregistered model and provider')
    if learning_executor is None:
        from scripts.transfer_learning import run_learning_epoch
        learning_executor = run_learning_epoch
    if learning_auditor is None:
        from scripts.audit_transfer import audit_learning_epoch
        learning_auditor = audit_learning_epoch
    source = Path(manifest['source_directory'])
    state.update(status='running', phase='learning')
    save(out / 'state.json', state)
    save(out / 'INFLIGHT.json', {'phase': 'learning', 'reserved_tokens': 4000000, 'reserved_calls': 200})
    learning_usage = {'accounting_complete': False, 'model_calls': None, 'tokens': None,
                      'charged_or_reserved_model_calls': 200, 'charged_or_reserved_tokens': 4000000}
    try:
        learning = learning_executor(source, out / 'learning_epoch', manifest['employee'], experiences,
                                     cutoff_day=CONFIG['cutoff_day'], creds=creds, executor=executor)
        learning_audit = learning_auditor(out / 'learning_epoch', strict=learning['status'] == 'completed')
        if learning_audit['ok'] and (learning_audit.get('status') == 'valid_completed'
                                     or learning_audit.get('accounting_verified') is True):
            learning_usage = deepcopy(learning['usage'])
        if learning['status'] != 'completed' or not learning_audit['ok']:
            raise ValueError('Learning epoch did not produce independently valid accounting and skill evidence')
        learned = read(out / 'learning_epoch/checkpoint.json')['runner']
        deployed = learned['skills'][manifest['employee']]
        if sha(source / 'checkpoint.json') != manifest['source_checkpoint_sha256']:
            raise ValueError('Learning mutated the source parent')
        # Verify every future capsule still matches the bytes frozen before learning.
        for name, expected in manifest['probe_files_sha256'].items():
            if sha(out / name) != expected:
                raise ValueError('Learning changed a withheld probe')
        state.update(phase='probes', learning_report_sha256=sha(out / 'learning_epoch/REPORT.json'),
                     deployed_skill_sha256=skill_hash(deployed), same_skill=deployed == SEED_SKILL)
        save(out / 'state.json', state)
        (out / 'INFLIGHT.json').unlink()
    except Exception as exc:
        state.update(status='learning_failed')
        save(out / 'state.json', state)
        save(out / 'FAILURE.json', {'phase': 'learning', 'error_type': type(exc).__name__,
                                   'message': 'Keep all evidence and reservations; automatic retry forbidden.'})
        report = {'status': 'learning_failed', 'complete': False, 'probes_attempted': 0,
                  **campaign_usage(learning_usage, state),
                  'manifest_sha256': sha(out / 'manifest.json')}
        save(out / 'REPORT.json', report)
        return report

    started = time.monotonic()
    def checkpoint():
        state['elapsed_seconds'] = time.monotonic() - started
        save(out / 'state.json', state)

    def finish(status):
        state['status'] = status
        checkpoint()
        report = aggregate_probes(manifest['probe_manifest'], manifest['slots'], state['results'], same_skill=state['same_skill'])
        report.update(status=status, manifest_sha256=sha(out / 'manifest.json'),
                      learning_report_sha256=state['learning_report_sha256'],
                      deployed_skill_sha256=state['deployed_skill_sha256'],
                      actual_probe_elapsed_seconds=state['elapsed_seconds'],
                      **campaign_usage(learning_usage, state))
        save(out / 'REPORT.json', report)
        return report

    for index, slot in enumerate(manifest['slots']):
        if CONFIG['max_run_seconds'] - (time.monotonic() - started) < CONFIG['max_rollout_seconds']:
            return finish('exhausted_time_budget')
        if (state['charged_tokens'] + CONFIG['max_rollout_tokens'] > CONFIG['max_charged_tokens']
                or state['model_calls'] + CONFIG['max_iterations'] > CONFIG['max_model_calls']):
            return finish('exhausted_compute_budget')
        capsule = probes[slot['probe_index']]
        fork = Ecosystem.restore(capsule['ecosystem'])
        root = out / 'probes' / slot['rollout_id']
        skill = SEED_SKILL if slot['arm'] == 'seed' else deployed
        save(out / 'INFLIGHT.json', {'phase': 'probes', **slot,
                                    'reserved_tokens': CONFIG['max_rollout_tokens'], 'reserved_calls': CONFIG['max_iterations']})
        record = None
        try:
            record = executor(root=root, employee=capsule['employee'], world=fork.worlds[capsule['firm']],
                task_id=capsule['task_id'], case=capsule['case'], request=capsule['request'], skill=skill,
                credentials=creds, objectives=capsule['objectives'], business_files=capsule['business_files'],
                max_iterations=CONFIG['max_iterations'], max_tokens=CONFIG['max_output_tokens'],
                max_total_tokens=CONFIG['max_rollout_tokens'], timeout_seconds=CONFIG['max_rollout_seconds'],
                **executor_options(manifest), **startup_options(manifest))
            receipt = {**slot, 'status': 'completed' if record['infrastructure_valid'] else 'infrastructure_invalid',
                       **{key: deepcopy(record[key]) for key in RECEIPT_FIELDS},
                       'session_path': str((root / 'session.json').relative_to(out)), 'session_sha256': sha(root / 'session.json')}
            if record['infrastructure_valid']:
                session_check(record, root, capsule, transport_manifest=manifest)
                if record['skill']['content_sha256'] != skill_hash(skill):
                    raise ValueError('Probe did not load its assigned frozen skill')
            if digest(capsule) != manifest['probe_manifest']['probes'][slot['probe_index']]['capsule_sha256']:
                raise ValueError('Native execution mutated its frozen probe capsule')
        except Exception as exc:
            usage, charged, calls = _accounted_usage(record, CONFIG)
            state['charged_tokens'] += charged
            state['model_calls'] += calls
            state['results'].append({**slot, 'status': 'infrastructure_error', 'success': None,
                'semantic_score': None, 'infrastructure_valid': False, 'budget_exhausted': False,
                'skill_loaded': None, 'usage': usage, 'diagnostic': {}, 'elapsed_seconds': None,
                'error_type': type(exc).__name__})
            save(out / 'FAILURE.json', {'phase': 'probes', 'slot': slot, 'error_type': type(exc).__name__,
                                       'message': 'Keep native evidence and reservations; automatic retry forbidden.'})
            return finish('infrastructure_error')
        _, charged, calls = _accounted_usage(record, CONFIG)
        state['charged_tokens'] += charged
        state['model_calls'] += calls
        state['results'].append(receipt)
        state['next_slot'] = index + 1
        state['status'] = 'running' if record['infrastructure_valid'] else 'infrastructure_invalid'
        checkpoint()
        (out / 'INFLIGHT.json').unlink()
        print(f"Transfer {index+1}/16 {slot['rollout_id']} success={record['success']} calls={calls}", flush=True)
        if not record['infrastructure_valid']:
            return finish('infrastructure_invalid')
    return finish('completed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--execute', action='store_true')
    parser.add_argument('--source')
    parser.add_argument('--calibration')
    args = parser.parse_args()
    if args.prepare:
        if not args.source or not args.calibration:
            parser.error('--prepare requires --source and --calibration')
        result = prepare(args.source, args.calibration, args.out)
        print(json.dumps({'status': 'prepared', 'employee': result['employee'], 'out': str(Path(args.out).resolve())}))
    else:
        result = execute(args.out)
        print(json.dumps({'status': result['status'], 'out': str(Path(args.out).resolve())}))


if __name__ == '__main__':
    main()
