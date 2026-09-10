#!/usr/bin/env python3
"""Six fixed native Hermes transport capability slots; no world/learning claim.

Preparation is read-only with respect to dependencies and never loads a key.
Execution is one-shot. Native credentials cross only an in-memory fork boundary.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifespan.computers import HERMES
from lifespan.ecosystem import Ecosystem, WORKFLOWS
from lifespan.evaluation.hermes_transport import contract, verify_source
from lifespan.evaluation.protocol import SEED_SKILL
from lifespan.evaluation.runner import source_hashes
from lifespan.evaluation.runtime import execute_case
from lifespan.evaluation.tasks import make_case
from lifespan.mirofish import save
from lifespan.world import Task
from scripts.hermes_preflight_process import supervise, interruption_scope

VERSION = 'hermes-transport-capability-v1'
CONFIG = {'fixture_seed': 930117, 'fixture_day': 0, 'max_iterations': 16,
          'max_output_tokens': 4096, 'max_rollout_tokens': 250000,
          'max_rollout_seconds': 420, 'max_cleanup_seconds': 30,
          'max_run_seconds': 2700, 'max_model_calls': 96,
          'max_charged_tokens': 1500000, 'fixed_slots': 6}
ARTIFACT_PATH = '/workspace/deliverables/capability.json'
REQUEST = (
    'This is a fixed component capability task in a fictional workplace. '
    'Load the work-process skill with skill_view. Follow the supplied task files and published '
    'company procedure. Use native file tools to create ' + ARTIFACT_PATH + ' and read it back. '
    'Complete the workplace checks and submit this artifact through enterprise_action work.commit. '
    'After the submission attempt, even if rejected, use a native terminal or read_file tool to '
    'read the same artifact again. Then give a brief final response. Do not revise and resubmit '
    'after the first work.commit attempt; the task score is separate from this transport check.'
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def identity(fn):
    return fn.__module__ + '.' + fn.__qualname__


def execution_sources():
    result = source_hashes()
    for name in ('hermes_transport_preflight.py', 'hermes_preflight_process.py', 'audit_hermes_preflight.py'):
        result['scripts/' + name] = sha(ROOT / 'scripts' / name)
    return result


def committed_sources(commit, sources):
    """No clean-HEAD fiction: every declared execution byte must exist in commit."""
    if not isinstance(commit, str) or re.fullmatch('[0-9a-f]{40}', commit) is None:
        return False
    for name, expected in sources.items():
        try:
            raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + name],
                                          stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return False
        if hashlib.sha256(raw).hexdigest() != expected:
            return False
    return True


def dependencies():
    """Inspect only installed source/runtime metadata; never import a provider client."""
    native = verify_source(HERMES)
    python = native / 'venv/bin/python'
    package_versions = json.loads(subprocess.check_output([str(python), '-c',
        'import importlib.metadata,json; print(json.dumps({k:importlib.metadata.version(k) '
        'for k in ("openai","httpx")}))'], text=True, stderr=subprocess.DEVNULL, timeout=10))
    bwrap = shutil.which('bwrap')
    if not bwrap:
        raise RuntimeError('bubblewrap dependency is unavailable')
    return {'hermes': {'revision': contract('nonstreaming')['hermes_revision'],
                'native_source_sha256': contract('nonstreaming')['native_source_sha256'],
                'python_sha256': sha(python), 'packages': package_versions},
            'harness': {'python_version': platform.python_version(),
                'python_sha256': sha(sys.executable), 'pyyaml_version': importlib.metadata.version('PyYAML')},
            'bubblewrap': {'binary_sha256': sha(bwrap), 'version': subprocess.check_output(
                [bwrap, '--version'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()}}


def expected_capsules():
    result = {}
    for index, workflow in enumerate(WORKFLOWS):
        eco = Ecosystem(days=8, seed=CONFIG['fixture_seed'] + index)
        eco.day = 0
        for world in eco.worlds.values():
            world.day = 0
        world = eco.worlds['firm-0']
        tid = 'hermes-capability-' + workflow + '-v1'
        employee = 'firm-0__' + workflow + '-regulated'
        world.tasks[tid] = Task(tid, workflow, 'regulated', workflow + '-regulated', 'consumer-0', 0, 3, 10)
        case = make_case(workflow, CONFIG['fixture_seed'] + index, 0, tid, regime='base', split='online')
        result[workflow] = {'schema_version': 1, 'kind': VERSION, 'firm': 'firm-0',
            'employee': employee, 'task_id': tid, 'case': case, 'ecosystem': eco.checkpoint(),
            'request': REQUEST, 'objectives': deepcopy(eco.firms['firm-0']), 'business_files': {}}
    return result


def expected_slots(capsule_hashes):
    result = []
    for index, workflow in enumerate(WORKFLOWS):
        modes = ('nonstreaming', 'streaming') if index == 1 else ('streaming', 'nonstreaming')
        for mode in modes:
            result.append({'index': len(result), 'slot_id': f'{len(result):02d}-{workflow}-{mode}',
                'workflow': workflow, 'mode': mode, 'employee': 'firm-0__' + workflow + '-regulated',
                'task_id': 'hermes-capability-' + workflow + '-v1',
                'capsule_path': 'private/cases/' + workflow + '.json',
                'capsule_sha256': capsule_hashes[workflow]})
    return result


def validate_model(model, base_url):
    parsed = urlsplit(base_url)
    if (not isinstance(model, str) or not model.strip() or len(model) > 200
            or any(c in model for c in '\r\n') or parsed.scheme not in ('http', 'https')
            or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Expected a model name and credential-free HTTP service URL')


def prepare(out, *, target_model, model_base_url):
    validate_model(target_model, model_base_url)
    sources, deps = execution_sources(), dependencies()
    out = Path(out).resolve()
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(out, 0o700)
    (out/'private').mkdir(mode=0o700)
    capsule_hashes = {}
    for workflow, capsule in expected_capsules().items():
        path = out/'private/cases'/ (workflow + '.json')
        save(path, capsule); capsule_hashes[workflow] = sha(path)
    (out/'private/initial_skill.txt').write_text(SEED_SKILL)
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'schema_version': 1, 'kind': VERSION, 'config': deepcopy(CONFIG),
        'slots': expected_slots(capsule_hashes), 'source_sha256': sources, 'dependencies': deps,
        'repository_commit': commit, 'source_commit_verified': committed_sources(commit, sources),
        'target_model': target_model, 'model_base_url': model_base_url,
        'initial_skill_sha256': sha(out/'private/initial_skill.txt'),
        'transports': {m: contract(m) for m in ('streaming', 'nonstreaming')},
        'execution_driver': 'scripts.hermes_transport_preflight.execute',
        'native_executor': identity(execute_case),
        'scope': 'fixed_synthetic_component_tasks; no_native_actors_or_learning_or_study_cohort'}
    save(out/'manifest.json', manifest)
    save(out/'state.json', {'schema_version': 1, 'status': 'prepared', 'receipts': []})
    return manifest


def verify_prepared(out):
    manifest = read(out/'manifest.json')
    if (manifest['kind'] != VERSION or manifest['config'] != CONFIG
            or manifest['source_sha256'] != execution_sources() or manifest['dependencies'] != dependencies()
            or manifest['execution_driver'] != 'scripts.hermes_transport_preflight.execute'
            or manifest['native_executor'] != identity(execute_case)
            or manifest['transports'] != {m: contract(m) for m in ('streaming', 'nonstreaming')}):
        raise ValueError('Prepared capability provenance differs from current execution')
    validate_model(manifest['target_model'], manifest['model_base_url'])
    if (sha(out/'private/initial_skill.txt') != manifest['initial_skill_sha256']
            or (out/'private/initial_skill.txt').read_text() != SEED_SKILL):
        raise ValueError('Initial skill differs from fixed capability skill')
    hashes = {}
    for workflow, capsule in expected_capsules().items():
        path = out/'private/cases'/(workflow + '.json')
        if read(path) != capsule:
            raise ValueError('Case differs from fixed synthetic capability fixture')
        hashes[workflow] = sha(path)
    if manifest['slots'] != expected_slots(hashes):
        raise ValueError('Fixed slot ordering or paired capsule binding changed')
    return manifest


def cost_receipt(record):
    """Known receipt dimensions survive an invalid score or unsuccessful cleanup."""
    from scripts.audit_hermes_preflight import physical_usage
    try:
        result = physical_usage(record)
        return {**result, 'accounting_verified': True, 'reservation_reason': None}
    except (AttributeError, KeyError, TypeError, ValueError):
        # No complete trustworthy receipt: retain public numeric observations,
        # reserve the whole slot, and halt. Do not represent a reservation as usage.
        usage = record.get('usage', {}) if isinstance(record, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        observed = {key: value for key, value in usage.items()
                    if key in ('api_calls', 'charged_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens')
                    and type(value) is int and value >= 0}
        return {'api_calls': None, 'total_tokens': None, 'complete': False,
            'reported_tokens': None, 'charged_tokens': max(CONFIG['max_rollout_tokens'], observed.get('charged_tokens', 0)),
            'reserved_model_calls': max(CONFIG['max_iterations'], observed.get('api_calls', 0)),
            'accounting_verified': False, 'reservation_reason': 'missing_or_unreconciled_native_receipt',
            'observed_usage_unverified': observed, 'violations': []}


def aggregate(receipts):
    costs = [r['costs'] for r in receipts]
    complete = bool(costs) and all(c['accounting_verified'] and c['complete'] for c in costs)
    return {'accounting_verified': bool(costs) and all(c['accounting_verified'] for c in costs),
        'complete': complete, 'physical_model_calls': sum(c['api_calls'] for c in costs)
            if all(c['api_calls'] is not None for c in costs) else None,
        'charged_or_reserved_model_calls': sum(c['api_calls'] if c['api_calls'] is not None
            else c['reserved_model_calls'] for c in costs),
        'charged_or_reserved_tokens': sum(c['charged_tokens'] for c in costs),
        'reported_tokens_known_prefix': sum(c.get('reported_tokens') or 0 for c in costs),
        'total_tokens': sum(c['total_tokens'] for c in costs) if complete else None}


def execute(out, *, creds=None, executor=execute_case, expected_manifest_sha256=None):
    with interruption_scope() as interruption:
        return _execute(out, creds=creds, executor=executor, expected_manifest_sha256=expected_manifest_sha256,
                        interruption=interruption)


def _execute(out, *, creds, executor, expected_manifest_sha256, interruption):
    out = Path(out).resolve(); manifest = verify_prepared(out)
    if (out/'EXECUTION.json').exists() or (out/'INFLIGHT.json').exists() or read(out/'state.json')['status'] != 'prepared':
        raise ValueError('Capability execution is one-shot; no resume or uncertain retry')
    native = executor is execute_case
    if expected_manifest_sha256 is not None and expected_manifest_sha256 != sha(out/'manifest.json'):
        raise ValueError('Manifest differs from separately registered hash')
    if native and (expected_manifest_sha256 is None or manifest.get('source_commit_verified') is not True
            or not committed_sources(manifest['repository_commit'], manifest['source_sha256'])):
        raise ValueError('Native preflight requires committed sources and the registered manifest hash')
    if creds is None:
        creds = {'model': manifest['target_model'], 'base_url': manifest['model_base_url'],
                 'api_key': os.environ.get('BIGWORLD_PREFLIGHT_API_KEY')}
    if (creds.get('model') != manifest['target_model'] or creds.get('base_url') != manifest['model_base_url']
            or not isinstance(creds.get('api_key'), str) or not creds['api_key']):
        raise ValueError('Credentials must match prepared model/service metadata')
    # O_EXCL is the one-shot dispatch lock. No credential fields are persisted.
    execution = {'schema_version': 1, 'manifest_sha256': sha(out/'manifest.json'),
        'execution_driver': 'scripts.hermes_transport_preflight.execute',
        'executor_identity': identity(executor), 'fixture': not native,
        'registered_manifest_sha256': expected_manifest_sha256,
        'started_unix_seconds': time.time(), 'config': deepcopy(CONFIG)}
    with (out/'EXECUTION.json').open('x') as stream:
        json.dump(execution, stream, sort_keys=True, indent=2)
    started = time.monotonic(); receipts = []; status = 'running'
    for slot in manifest['slots']:
        if interruption['requested']:
            status = 'interrupted'; break
        used = aggregate(receipts)
        if (time.monotonic()-started + CONFIG['max_rollout_seconds'] + CONFIG['max_cleanup_seconds'] > CONFIG['max_run_seconds']
                or used['charged_or_reserved_model_calls'] + CONFIG['max_iterations'] > CONFIG['max_model_calls']
                or used['charged_or_reserved_tokens'] + CONFIG['max_rollout_tokens'] > CONFIG['max_charged_tokens']):
            status = 'halted_budget'; break
        trial = out/'private/trials'/slot['slot_id']
        capsule = read(out/slot['capsule_path']); eco = Ecosystem.restore(capsule['ecosystem'])
        save(out/'INFLIGHT.json', {'slot_id': slot['slot_id'], 'index': slot['index'],
            'reserved_model_calls': CONFIG['max_iterations'], 'reserved_tokens': CONFIG['max_rollout_tokens']})
        kwargs = {'root': trial/'native', 'employee': slot['employee'], 'world': eco.worlds[capsule['firm']],
            'task_id': slot['task_id'], 'case': capsule['case'], 'request': capsule['request'], 'skill': SEED_SKILL,
            'credentials': creds, 'objectives': capsule['objectives'], 'business_files': capsule['business_files'],
            'max_iterations': CONFIG['max_iterations'], 'max_tokens': CONFIG['max_output_tokens'],
            'max_total_tokens': CONFIG['max_rollout_tokens'], 'timeout_seconds': CONFIG['max_rollout_seconds'],
            'hermes_transport': slot['mode']}
        # Capsule loading/marker persistence is outside the child execution
        # clock. Recheck the full fixed allowance immediately before forking.
        if (interruption['requested'] or time.monotonic()-started + CONFIG['max_rollout_seconds']
                + CONFIG['max_cleanup_seconds'] > CONFIG['max_run_seconds']):
            (out/'INFLIGHT.json').unlink()
            status = 'interrupted' if interruption['requested'] else 'halted_budget'; break
        supervision = supervise(executor, kwargs, trial, timeout_seconds=CONFIG['max_rollout_seconds'],
                                 cleanup_seconds=CONFIG['max_cleanup_seconds'],
                                 stop_requested=lambda: interruption['requested'])
        record = None
        try:
            record = read(trial/'native/session.json')
        except (OSError, ValueError):
            pass
        costs = cost_receipt(record); evidence = None; evidence_error = None
        cleanup_valid = False; cleanup_error = None
        try:
            from scripts.audit_hermes_preflight import native_session, cleanup_check
            evidence = native_session(record, trial/'native', capsule, slot, manifest)
        except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
            evidence_error = type(exc).__name__
        try:
            cleanup_valid = cleanup_check(trial, slot, supervision['cleanup'])
        except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
            cleanup_error = type(exc).__name__
        valid = bool(supervision['status'] == 'returned' and supervision['root_exitcode'] == 0
                     and costs['accounting_verified'] and costs['complete'] and not costs['violations']
                     and evidence is not None and cleanup_valid
                     and supervision['execution_elapsed_seconds'] <= CONFIG['max_rollout_seconds']
                     and supervision['elapsed_seconds'] <= CONFIG['max_rollout_seconds'] + CONFIG['max_cleanup_seconds'])
        slot_status = 'interrupted' if supervision['status'] == 'interrupted' else 'completed' if valid else 'halted_infrastructure'
        receipt = {'schema_version': 1, 'slot_id': slot['slot_id'], 'index': slot['index'],
            'executor_identity': identity(executor), 'fixture': not native,
            'status': slot_status,
            'trial_path': str(trial.relative_to(out)), 'capsule_sha256': slot['capsule_sha256'],
            'session_sha256': sha(trial/'native/session.json') if record is not None else None,
            'supervision_sha256': sha(trial/'supervision.json'), 'cleanup_sha256': sha(trial/'cleanup.json'),
            'costs': costs, 'native_evidence': evidence, 'evidence_error_type': evidence_error,
            'cleanup_error_type': cleanup_error,
            'cleanup_confirmed': cleanup_valid, 'elapsed_seconds': time.monotonic()-started,
            'capability_pass': bool(valid and native and evidence['transport_roundtrip_capable'])}
        path = out/'private/receipts'/(slot['slot_id']+'.json'); save(path, receipt); receipts.append(receipt)
        state = {'schema_version': 1, 'status': 'running' if valid else slot_status,
            'receipts': [{'path': str((out/'private/receipts'/(r['slot_id']+'.json')).relative_to(out)),
                         'sha256': sha(out/'private/receipts'/(r['slot_id']+'.json'))} for r in receipts],
            'usage': aggregate(receipts), 'elapsed_seconds': time.monotonic()-started}
        save(out/'state.json', state); (out/'INFLIGHT.json').unlink()
        print(json.dumps({'slot': slot['slot_id'], 'status': receipt['status'],
                          'capability_pass': receipt['capability_pass'], 'usage_complete': costs['complete']}), flush=True)
        if not valid:
            status = slot_status; break
    if interruption['requested']:
        status = 'interrupted'
    if len(receipts) == CONFIG['fixed_slots'] and status == 'running':
        status = 'completed' if time.monotonic()-started <= CONFIG['max_run_seconds'] else 'halted_budget'
    report = {'schema_version': 1, 'kind': VERSION, 'status': status, 'fixture': not native,
        'manifest_sha256': sha(out/'manifest.json'), 'execution_sha256': sha(out/'EXECUTION.json'),
        'attempted_slots': len(receipts), 'fixed_slots': CONFIG['fixed_slots'], 'usage': aggregate(receipts),
        'elapsed_seconds': time.monotonic()-started,
        'capability_pass': bool(native and status == 'completed' and all(r['capability_pass'] for r in receipts)),
        'slots': [{'slot_id': s['slot_id'], 'mode': s['mode'], 'workflow': s['workflow'],
            'status': receipts[i]['status'] if i < len(receipts) else 'not_attempted',
            'capability_pass': receipts[i]['capability_pass'] if i < len(receipts) else None,
            'native_evidence': receipts[i]['native_evidence'] if i < len(receipts) else None}
            for i, s in enumerate(manifest['slots'])]}
    if not receipts:
        state = {'schema_version': 1, 'receipts': []}
    state.update(status=status, usage=aggregate(receipts), elapsed_seconds=report['elapsed_seconds'])
    save(out/'state.json', state); save(out/'REPORT.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--out', required=True)
    prep.add_argument('--model', required=True); prep.add_argument('--base-url', required=True)
    run = sub.add_parser('execute'); run.add_argument('--out', required=True)
    run.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.out, target_model=args.model, model_base_url=args.base_url) if args.command == 'prepare' else execute(
            args.out, expected_manifest_sha256=args.manifest_sha256)
        print(json.dumps({'status': result.get('status', 'prepared'), 'kind': VERSION}))
    except Exception as exc:
        # Provider bodies/keys may be embedded in arbitrary native exceptions.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    from scripts.hermes_transport_preflight import main as canonical_main
    raise SystemExit(canonical_main())
