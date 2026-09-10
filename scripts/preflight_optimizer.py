"""One bounded native SkillOpt reflector request, separate from learning outcomes.

Preparation and audit are offline. Execution captures the real production SDK
response and uses the pinned upstream reflection renderer/parser on a synthetic
TRAIN fixture. No target replay, candidate adoption or learning gain is claimed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import signal
import subprocess
import time

from lifespan.evaluation import optimizer, provider
from lifespan.evaluation.protocol import SEED_SKILL
from lifespan.evaluation.runner import ROOT, credentials, dependency_provenance, source_hashes
from lifespan.evaluation.skillopt import DEFAULT_SOURCE, _frozen_upstream_settings, _load_upstream
from lifespan.mirofish import save
from scripts.hermes_transport_preflight import committed_sources

KIND = 'native_optimizer_provider_capability_v1'
LIMITS = {'max_model_calls': 1, 'max_tokens': 32768, 'timeout_seconds': 120,
          'max_output_tokens': 1024, 'edit_budget': 4}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def same(first, second):
    return json.dumps(first, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(
        second, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sources():
    return {**source_hashes(), 'scripts/preflight_optimizer.py': sha(__file__),
            'scripts/hermes_transport_preflight.py': sha(ROOT / 'scripts/hermes_transport_preflight.py'),
            'scripts/hermes_preflight_process.py': sha(ROOT / 'scripts/hermes_preflight_process.py')}


def _fixture(raw='[{"op":"add","content":"Check signed adjustments before computing totals."}]'):
    """Exercise the actual upstream renderer/parser without invoking a model."""
    _, Backend, Task, prompts = _load_upstream(DEFAULT_SOURCE)
    Replay = importlib.import_module('skillopt_sleep.types').ReplayResult
    task = Task(id='optimizer-capability-train', project='synthetic-provider-fixture',
                intent='Reconcile a fictional account ledger with signed refunds.',
                context_excerpt='Input ledger rows contain signed adjustments.', split='train')
    replay = Replay(id=task.id, hard=0., soft=0., response='The refund row was omitted.',
                    fail_reason='Include every signed adjustment in the total.')
    captured = []

    class Capture(Backend):
        def _call(self, prompt, *, max_tokens=1024):
            captured.append({'prompt': prompt, 'max_output_tokens': max_tokens})
            return raw

    backend = Capture(model='offline-parser-fixture')
    with _frozen_upstream_settings(prompts):
        edits = backend.reflect([(task, replay)], [], SEED_SKILL, '',
            edit_budget=LIMITS['edit_budget'], evolve_skill=True, evolve_memory=False)
    payload = {**captured[0], 'phase': 'reflect', 'current_day': 1,
        'train_experiences': [{'task': {'id': task.id, 'split': 'train', 'available_day': 0,
            'feedback_available_day': 1, 'prompt': task.intent, 'context': task.context_excerpt,
            'source_session': 'synthetic-fixture-only'}, 'response': replay.response,
            'feedback': replay.fail_reason}]}
    return payload, [asdict(edit) for edit in edits]


def _policy_manifest(model, base_url, profile):
    return provider.provider_contract(model, base_url, profile)


def prepare(directory, *, model, base_url, provider_profile=provider.PROFILE):
    policy = _policy_manifest(model, base_url, provider_profile)
    payload, _ = _fixture()
    root = Path(directory).resolve(); root.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(root / 'payload.json', payload)
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    declared = sources()
    manifest = {'schema_version': 1, 'kind': KIND, 'provider_contract': policy,
        'target_model': model, 'model_base_url': policy['base_url'], 'limits': LIMITS,
        'source_sha256': declared, 'dependencies': dependency_provenance(),
        'repository_commit': commit, 'source_commit_verified': committed_sources(commit, declared),
        'payload_sha256': sha(root / 'payload.json'), 'native_driver': 'scripts.preflight_optimizer.execute',
        'scope': 'synthetic_train_reflection_transport_and_upstream_parsing_only'}
    save(root / 'manifest.json', manifest)
    return manifest


def verify_prepared(root, manifest_sha256):
    root = Path(root)
    if sha(root / 'manifest.json') != manifest_sha256:
        raise ValueError('optimizer_preflight_manifest_hash')
    m = read(root / 'manifest.json'); payload, _ = _fixture()
    provider.validate_contract(m.get('provider_contract'))
    if (m.get('kind') != KIND or not same(m.get('limits'), LIMITS)
            or m.get('source_sha256') != sources() or m.get('dependencies') != dependency_provenance()
            or m.get('source_commit_verified') is not True
            or not committed_sources(m.get('repository_commit'), m['source_sha256'])
            or not same(read(root / 'payload.json'), payload) or sha(root / 'payload.json') != m['payload_sha256']
            or m.get('native_driver') != 'scripts.preflight_optimizer.execute'
            or not same(m.get('provider_contract'), _policy_manifest(m['target_model'], m['model_base_url'], provider.PROFILE))):
        raise ValueError('optimizer_preflight_configuration_or_source_changed')
    return m


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and p.name not in ('REPORT.json', 'EVIDENCE.json')}


def _audit(root, manifest_sha256):
    root = Path(root); m = verify_prepared(root, manifest_sha256)
    execution = read(root / 'EXECUTION.json')
    if not same(execution, {'schema_version': 1, 'manifest_sha256': manifest_sha256,
                     'driver': m['native_driver'], 'native_sdk': True}):
        raise ValueError('optimizer_preflight_execution_binding')
    if any(p.is_symlink() for p in root.rglob('*')) or inventory(root) != read(root / 'EVIDENCE.json'):
        raise ValueError('optimizer_preflight_raw_inventory_changed')
    receipt = read(root / 'receipt.json'); request = read(root / 'request.json'); response = read(root / 'response.json')
    policy = m['provider_contract']; seen = []
    def replay_transport(value, *, timeout, api_mode):
        seen.append(deepcopy(value)); return deepcopy(response)
    expected = optimizer.make_reflector({'model': policy['model'], 'base_url': policy['base_url'],
        'provider_profile': policy['profile'], 'api_key': 'offline-auditor-no-secret'},
        transport=replay_transport)(read(root / 'payload.json'), LIMITS)
    stable_keys = set(expected) - {'latency_ms'}
    if (len(seen) != 1 or not same(seen[0], request) or set(receipt) != set(expected)
            or any(not same(receipt.get(k), expected[k]) for k in stable_keys)
            or receipt['status'] != 'completed' or receipt['accounting_complete'] is not True
            or receipt['model_calls'] != 1 or type(receipt['tokens']) is not int
            or not 0 <= receipt['tokens'] <= LIMITS['max_tokens']
            or type(receipt['latency_ms']) not in (int, float)
            or not 0 <= receipt['latency_ms'] <= LIMITS['timeout_seconds'] * 1000):
        raise ValueError('optimizer_preflight_response_policy_or_usage_failed')
    _, parsed = _fixture(receipt['response'])
    backend = importlib.import_module('skillopt_sleep.backend')
    # A valid empty edit array is permitted: adoption/quality is not this gate.
    array = backend._extract_json(receipt['response'], 'array')
    if (type(array) is not list or len(array) > LIMITS['edit_budget']
            or len(parsed) != len(array) or any(type(item) is not dict or type(item.get('content')) is not str
                or not item['content'].strip() or item.get('op', 'add') not in ('add', 'delete', 'replace') for item in array)
            or not same(parsed, read(root / 'parsed_edits.json'))):
        raise ValueError('optimizer_preflight_upstream_edit_parse_failed')
    timing = read(root / 'TIMING.json')
    if (set(timing) != {'started_monotonic', 'ended_monotonic', 'wall_seconds', 'scope'}
            or any(type(timing[k]) not in (int, float) or not math.isfinite(timing[k]) for k in
                   ('started_monotonic', 'ended_monotonic', 'wall_seconds'))
            or timing['scope'] != 'exclusive_dispatch_marker_through_client_close_and_parsed_output_persistence'
            or not 0 <= timing['wall_seconds'] <= LIMITS['timeout_seconds']
            or abs(timing['ended_monotonic'] - timing['started_monotonic'] - timing['wall_seconds']) > 1e-9
            or receipt['latency_ms'] > timing['wall_seconds'] * 1000):
        raise ValueError('optimizer_preflight_wall_evidence')
    return {'schema_version': 1, 'kind': KIND, 'ok': True, 'status': 'completed',
        'capability_pass': True, 'manifest_sha256': manifest_sha256,
        'provider_contract': policy, 'physical_model_calls': 1,
        'input_tokens': receipt['input_tokens'], 'output_tokens': receipt['output_tokens'],
        'tokens': receipt['tokens'], 'latency_ms': receipt['latency_ms'],
        'wall_seconds': timing['wall_seconds'],
        'parsed_edit_count': len(parsed), 'native_learning_or_adoption': False,
        'evidence_inventory_sha256': sha(root / 'EVIDENCE.json')}


def audit_preflight(directory, *, manifest_sha256, strict=True):
    result = _audit(directory, manifest_sha256)
    if not same(read(Path(directory) / 'REPORT.json'), result):
        raise ValueError('optimizer_preflight_report_changed')
    return result


def execute(directory, *, manifest_sha256):
    root = Path(directory).resolve(); m = verify_prepared(root, manifest_sha256)
    creds = credentials()
    if not same(provider.contract(creds), m['provider_contract']):
        raise ValueError('optimizer_preflight_actual_provider_changed')
    if signal.getitimer(signal.ITIMER_REAL) != (0., 0.):
        raise ValueError('optimizer_preflight_existing_alarm')
    started = time.monotonic()
    with (root / 'EXECUTION.json').open('x') as f:
        json.dump({'schema_version': 1, 'manifest_sha256': manifest_sha256,
                   'driver': m['native_driver'], 'native_sdk': True}, f)
    calls = 0
    def remaining_time():
        remaining = LIMITS['timeout_seconds'] - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError('optimizer_preflight_wall_limit')
        return remaining
    def capture(request, *, timeout, api_mode):
        nonlocal calls
        if calls:
            raise ValueError('optimizer_preflight_second_dispatch_forbidden')
        save(root / 'request.json', request)
        timeout = min(timeout, remaining_time())
        calls += 1
        result = send(request, timeout=timeout, api_mode=api_mode)
        save(root / 'response.json', result)
        return result
    def deadline(signum, frame):
        raise TimeoutError('optimizer_preflight_wall_limit')
    previous = signal.signal(signal.SIGALRM, deadline)
    receipt = {}; execution_error = None
    try:
        signal.setitimer(signal.ITIMER_REAL, remaining_time())
        send = optimizer._sdk_transport(creds)
        remaining_time()
        receipt = optimizer.make_reflector(creds, transport=capture)(read(root / 'payload.json'), LIMITS)
        save(root / 'receipt.json', receipt)
        _, edits = _fixture(receipt.get('response', ''))
        save(root / 'parsed_edits.json', edits)
    except Exception as exc:
        execution_error = type(exc).__name__
        save(root / 'FAILURE.json', {'error_type': execution_error})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    ended = time.monotonic()
    save(root / 'TIMING.json', {'started_monotonic': started, 'ended_monotonic': ended,
        'wall_seconds': ended - started,
        'scope': 'exclusive_dispatch_marker_through_client_close_and_parsed_output_persistence'})
    save(root / 'EVIDENCE.json', inventory(root))
    try:
        if execution_error:
            raise ValueError('optimizer_preflight_execution_failed')
        result = _audit(root, manifest_sha256)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        result = {'schema_version': 1, 'kind': KIND, 'ok': False, 'capability_pass': False,
            'status': 'failed', 'error_type': type(exc).__name__, 'manifest_sha256': manifest_sha256,
            'physical_requests_attempted': calls, 'usage_complete': calls == 0 or receipt.get('accounting_complete') is True,
            'known_tokens': 0 if calls == 0 else receipt.get('tokens'), 'reserved_tokens_if_unknown':
                LIMITS['max_tokens'] if receipt.get('tokens') is None and calls else 0}
    save(root / 'REPORT.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'execute', 'audit'))
    parser.add_argument('--out', required=True); parser.add_argument('--model'); parser.add_argument('--base-url')
    parser.add_argument('--manifest-sha256'); args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.out, model=args.model, base_url=args.base_url)
        result = {'status': 'prepared', 'manifest_sha256': sha(Path(args.out) / 'manifest.json')}
    elif args.command == 'execute':
        result = execute(args.out, manifest_sha256=args.manifest_sha256)
    else:
        result = audit_preflight(args.out, manifest_sha256=args.manifest_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
