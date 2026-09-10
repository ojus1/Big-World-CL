#!/usr/bin/env python3
"""Read-only native transport component audit; never a learning-effect score.

Local, source-bound receipts are consistency evidence, not signed provider proof.
Unknown costs, missing slots and cleanup uncertainty remain explicit.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_evaluation import child, reports_equal, require, session_check
from lifespan.evaluation.hermes_transport import contract
from lifespan.evaluation.protocol import SEED_SKILL


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), sha(raw)


def integer(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def physical_usage(record):
    """Reconcile known/reserved dimensions even when capability validation fails."""
    require(type(record) is dict and type(record.get('result')) is dict
            and type(record['result'].get('native')) is dict and type(record.get('usage')) is dict,
            'native_usage_shape')
    meter = record['result']['native']['evaluation_budget']
    require(type(meter) is dict, 'physical_meter_shape')
    rows = meter['operations']
    require(type(rows) is list, 'physical_operation_shape')
    totals = {key: 0 for key in ('input_tokens', 'output_tokens', 'total_tokens', 'charged_tokens')}
    complete, violations = True, []
    for index, row in enumerate(rows, 1):
        require(type(row) is dict, 'physical_operation_shape')
        require(type(row['dispatch']) is int and row['dispatch'] == index, 'physical_dispatch_sequence')
        require(all(integer(row[k]) for k in ('reserved_tokens', 'charged_tokens', 'output_cap')),
                'physical_reservation_shape')
        require(row['accounting'] in ('reported', 'reservation'), 'physical_accounting_kind')
        if row['accounting'] == 'reported':
            require(all(integer(row[k]) for k in ('input_tokens', 'output_tokens', 'total_tokens')),
                    'physical_usage_shape')
            require(row['input_tokens'] + row['output_tokens'] == row['total_tokens'] == row['charged_tokens'],
                    'physical_usage_equation')
            if (row['total_tokens'] > row['reserved_tokens'] or row['output_tokens'] > row['output_cap']
                    or row['status'] == 'provider_budget_overrun'):
                violations.append('provider_budget_overrun')
        else:
            complete = False
            require(all(row[k] is None for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    and row['charged_tokens'] == row['reserved_tokens'], 'unknown_usage_reservation')
        if row['output_cap'] > 4096 or row['reserved_tokens'] > 250000:
            violations.append('physical_operation_cap')
        for key in totals:
            totals[key] += row[key] or 0
    require(type(meter['physical_model_calls']) is int and meter['physical_model_calls'] == len(rows),
            'physical_call_count')
    require(all(type(meter[k]) is int and meter[k] == value for k, value in totals.items()),
            'physical_total_equation')
    require(type(meter['reported_tokens']) is int and meter['reported_tokens'] == totals['total_tokens']
            and meter['accounting_complete'] is complete, 'physical_accounting_summary')
    expected = {'api_calls': len(rows), 'charged_tokens': totals['charged_tokens'],
                'prompt_tokens': totals['input_tokens'], 'completion_tokens': totals['output_tokens'],
                'total_tokens': totals['total_tokens'] if complete else None, 'complete': complete}
    require(all(type(record['usage'].get(k)) is type(v) and record['usage'][k] == v
                for k, v in expected.items()), 'session_usage_equation')
    if len(rows) > 16 or totals['charged_tokens'] > 250000:
        violations.append('physical_slot_cap')
    return {**expected, 'reported_tokens': totals['total_tokens'],
            'unknown_operations': sum(r['accounting'] == 'reservation' for r in rows),
            'violations': sorted(set(violations))}


def native_session(record, directory, capsule, slot, manifest):
    """Regrade immutable submissions and check the actual native tool sequence."""
    require(type(record) is dict and type(record.get('result')) is dict
            and type(record['result'].get('native')) is dict, 'native_session_shape')
    mode = slot['mode']
    declared = {'config': {'hermes_transport': mode}, 'hermes_transport': mode,
                'hermes_transport_provenance': manifest['transports'][mode],
                'source_sha256': manifest['source_sha256']}
    if manifest.get('provider_contract') is not None:
        declared.update(provider_contract=manifest['provider_contract'], target_model=manifest['target_model'],
                        model_base_url=manifest['model_base_url'])
        declared['config']['provider_profile'] = manifest['config']['provider_profile']
    session_check(record, directory, capsule, transport_manifest=declared)
    require(record['skill']['content_sha256'] == manifest['initial_skill_sha256'] == sha(SEED_SKILL.encode()),
            'seed_skill_binding')
    require(record['employee'] == slot['employee'] and record['task_id'] == slot['task_id'], 'slot_session_identity')
    require(record['hermes_transport'] == contract(mode), 'slot_transport_binding')
    require(all(type(record.get(key)) is bool for key in ('success', 'skill_loaded', 'infrastructure_valid'))
            and number(record['semantic_score']) and record['semantic_score'] <= 1, 'native_outcome_shape')
    require(number(record['elapsed_seconds']) and record['elapsed_seconds'] <= 420, 'native_runtime_deadline')
    native = record['result']['native']
    messages = native.get('messages')
    require(type(messages) is list and all(type(m) is dict for m in messages), 'native_message_shape')
    calls = [(index, call) for index, message in enumerate(messages) for call in message.get('tool_calls') or []]
    require(all(type(c) is dict and type(c.get('function')) is dict for _, c in calls), 'native_tool_call_shape')
    require(type(record['tool_calls']) is int and record['tool_calls'] == len(calls), 'native_tool_count')
    require(not any(c.get('function', {}).get('name') in ('memory', 'skill_manage') for _, c in calls),
            'private_learning_tool_used')
    submitted = record.get('last_submitted_artifact_sha256')
    commit_results = []
    for index, call in calls:
        function = call.get('function', {})
        if function.get('name') != 'enterprise_action':
            continue
        try:
            args = json.loads(function.get('arguments', '{}'))
        except (TypeError, ValueError):
            continue
        if args.get('operation') != 'work.commit':
            continue
        for after in range(index + 1, len(messages)):
            message = messages[after]
            if message.get('role') != 'tool' or message.get('tool_call_id') != call.get('id'):
                continue
            try:
                result = json.loads(message.get('content', '{}'))
            except (TypeError, ValueError):
                continue
            if (submitted is not None and type(result) is dict and result.get('artifact_sha256') == submitted
                    and 'observation' in result and any(
                        rpc.get('action', {}).get('tool') == 'work.commit' and rpc.get('response') == result
                        for rpc in record['result'].get('workplace_rpc', []))):
                commit_results.append(after)
    continuation = any(message.get('role') == 'assistant' and
                       (message.get('content') or message.get('tool_calls'))
                       for index in commit_results for message in messages[index + 1:])
    readbacks = []
    artifact_path = '/workspace/deliverables/capability.json'
    submitted_value = json.loads((directory / 'filesystem_objects' / submitted).read_bytes()) if submitted else None
    for index, call in calls:
        if not any(previous < index for previous in commit_results):
            continue
        function = call.get('function', {})
        try:
            args = json.loads(function.get('arguments', '{}'))
            name = function.get('name')
            command = shlex.split(args.get('command', '')) if name == 'terminal' else []
            is_read = name == 'read_file' and args.get('path') == artifact_path
            is_cat = name == 'terminal' and command in (['cat', artifact_path], ['cat', '--', artifact_path])
            is_hash = name == 'terminal' and command in (['sha256sum', artifact_path], ['sha256sum', '--', artifact_path])
            if not (is_read or is_cat or is_hash):
                continue
            for after in range(index + 1, len(messages)):
                message = messages[after]
                if message.get('role') != 'tool' or message.get('tool_call_id') != call.get('id'):
                    continue
                result = json.loads(message.get('content', '{}'))
                if type(result) is not dict or result.get('error'):
                    continue
                text = result.get('content' if is_read else 'output', '')
                if type(text) is not str or (not is_read and result.get('exit_code') != 0):
                    continue
                if is_read:
                    text = '\n'.join(re.sub(r'^\s*\d+\|', '', line) for line in text.splitlines())
                # Python object equality equates JSON true/false with 1/0.
                # Canonical encoding preserves scalar types while permitting
                # harmless whitespace and object-key ordering differences.
                matches = (text.strip().split()[0] == submitted if is_hash and text.strip()
                           else json.dumps(json.loads(text), sort_keys=True, separators=(',', ':'), allow_nan=False)
                           == json.dumps(submitted_value, sort_keys=True, separators=(',', ':'), allow_nan=False)
                           if not is_hash else False)
                if matches:
                    readbacks.append(after)
        except (ValueError, TypeError, AttributeError):
            continue
    final_response = any(message.get('role') == 'assistant' and type(message.get('content')) is str
                         and bool(message['content'].strip()) and not message.get('tool_calls')
                         for index in readbacks for message in messages[index + 1:])
    auxiliary = native['evaluation_budget'].get('disabled_auxiliary_calls', [])
    require(type(auxiliary) is list, 'auxiliary_evidence_shape')
    tool_capable = bool(record['skill_loaded'] and submitted and commit_results and readbacks and final_response
                        and not auxiliary and not native.get('failed', False)
                        and not record.get('budget_exhausted', False)
                        and native['evaluation_budget']['physical_model_calls'] >= 2)
    # The explicit profile prospectively uses the exact reviewed warning parser.
    # Raw submission bytes, trusted grade, commit RPC, costs and source bindings
    # have already been checked above; arbitrary suffixes remain ineligible.
    warning_evidence = None
    if manifest.get('provider_contract') is not None and submitted:
        require(manifest.get('readback_contract') == 'hermes-native-readback-audit-v2', 'profile_readback_contract')
        from scripts.audit_hermes_readback_v2 import readback_evidence
        warning_evidence = readback_evidence(record, directory)
        readbacks = [row['result_index'] for row in warning_evidence['readbacks']]
        final_response = bool(readbacks)
        tool_capable = warning_evidence['transport_roundtrip_capable']
    return {'skill_loaded': record['skill_loaded'], 'artifact_submitted': submitted is not None,
            'trusted_submission_tool_roundtrip': bool(commit_results),
            'subsequent_assistant_turn': bool(continuation),
            'post_submission_native_file_readback': bool(readbacks), 'final_response_after_readback': bool(final_response),
            'synthetic_summary_excluded': not auxiliary, 'transport_roundtrip_capable': tool_capable,
            'semantic_success': record['success'], 'semantic_score': record['semantic_score'],
            'business_committed': record['committed_artifact_sha256'] is not None,
            'physical_request_to_message_binding': 'not_recorded; trajectory_inference_from_pinned_native_harness'}


def stable_identity(value):
    require(type(value) is dict and all(type(value.get(k)) is int and value[k] > 0
            for k in ('pid', 'start_ticks')) and integer(value.get('uid'))
            and type(value.get('boot_id')) is str and bool(value['boot_id']), 'process_identity_shape')
    return tuple(value[k] for k in ('pid', 'start_ticks', 'uid', 'boot_id'))


def cleanup_check(trial, slot, cleanup, provider_contract=None):
    """Reconcile persisted ownership and final observations without signaling PIDs."""
    require(cleanup.get('schema_version') == 1 and cleanup.get('limit_seconds') == 30,
            'cleanup_contract')
    require(number(cleanup.get('elapsed_seconds')), 'cleanup_clock')
    require(cleanup.get('status') in ('confirmed', 'unconfirmed'), 'cleanup_status')
    if cleanup['status'] != 'confirmed':
        return False
    require(cleanup['elapsed_seconds'] <= 30, 'cleanup_deadline')
    processes = cleanup['owned_processes']
    require(type(processes) is list and bool(processes), 'missing_owned_processes')
    keys = [stable_identity(item) for item in processes]
    require(len(set(keys)) == len(keys) and len({key[0] for key in keys}) == len(keys), 'duplicate_owned_process')
    root = stable_identity(cleanup['root_identity'])
    require(root in keys and all(key[2:] == root[2:] for key in keys), 'process_owner_boot_binding')
    by_pid = {p['pid']: p for p in processes}
    for process in processes:
        ancestry, seen = process, set()
        while ancestry['pid'] != root[0]:
            require(ancestry['pid'] not in seen and ancestry.get('ppid') in by_pid, 'unbound_process_ancestry')
            seen.add(ancestry['pid']); parent = by_pid[ancestry['ppid']]
            require(ancestry['start_ticks'] >= parent['start_ticks'], 'process_birth_order')
            ancestry = parent
    observed = cleanup['observations_after']
    require(type(observed) is list and len(observed) == len(keys)
            and {stable_identity(row['identity']) for row in observed} == set(keys), 'cleanup_observation_inventory')
    for row in observed:
        current = row['observed_current']
        if row['state'] == 'absent':
            require(current is None, 'false_process_absence')
        elif row['state'] == 'zombie':
            require(stable_identity(current) == stable_identity(row['identity']) and current.get('state') == 'Z',
                    'false_zombie_observation')
        elif row['state'] == 'identity_replaced':
            require(stable_identity(current) != stable_identity(row['identity']), 'false_replaced_identity')
        else:
            raise ValueError('owned_process_not_confirmed_gone')
    require(type(cleanup['forced']) is bool and type(cleanup['signals']) is list, 'cleanup_signal_shape')
    for row in cleanup['signals']:
        require(row.get('pid') in by_pid and row.get('start_ticks') == by_pid[row['pid']]['start_ticks']
                and row.get('signal') in ('TERM', 'KILL'), 'unowned_cleanup_signal')
    require(cleanup['forced'] or not cleanup['signals'], 'cleanup_forced_flag')
    worker, _ = read(trial / 'worker-identity.json')
    require(stable_identity(worker) == root and worker['sid'] == worker['pid'], 'isolated_executor_process')
    instance = cleanup['instance']
    path = trial / 'native/computers' / slot['employee'] / 'instance.json'
    value, file_sha = read(path)
    require(Path(instance['instance_path']).resolve() == path.resolve()
            and instance['instance_sha256'] == file_sha, 'native_instance_hash')
    require(value['kind'] == 'ready' and value['employee'] == slot['employee'] and value['backend'] == 'bubblewrap'
            and value['evaluation_transport'] == contract(slot['mode'])
            and value['computer_id'] == 'lifespan-' + sha(str(path.parent / 'hermes').encode())[:16],
            'native_instance_identity_or_transport')
    if provider_contract is not None:
        from lifespan.evaluation.provider import validate_contract
        validate_contract(value.get('provider_contract'))
    require(value.get('provider_contract') == provider_contract, 'native_instance_provider_contract')
    if provider_contract is None:
        require('provider_contract' not in value, 'native_instance_provider_marker_downgrade')
    probe = json.loads(value['probe'])
    require(probe.get('exit_code') == 0 and slot['employee'] in probe.get('output', '').splitlines(),
            'native_sandbox_probe')
    require('skill_view' in value['tool_names'] and 'enterprise_action' in value['tool_names']
            and not {'memory', 'skill_manage'} & set(value['tool_names']), 'native_tool_exposure')
    for key, pid_key in (('worker_identity', 'pid'), ('sandbox_identity', 'sandbox_pid')):
        identity = stable_identity(instance[key])
        require(identity in keys and identity[0] == value[pid_key] == instance['worker_pid' if key == 'worker_identity' else 'sandbox_pid'],
                'native_process_instance_binding')
    socket = Path(instance['rpc_socket']); alias = Path(instance['alias'])
    control = trial / 'native/computers' / slot['employee'] / 'control'
    require(value['rpc_socket'] == str(socket) and socket == alias / 'control/command.sock'
            and alias.parent == Path('/tmp') and alias.name.startswith('lifespan-bwrap-')
            and Path(instance['control_target']).resolve() == control.resolve()
            and instance['owned_alias_observed'] is True, 'native_socket_ownership')
    require(cleanup['socket_and_alias_absent'] is True and not socket.exists() and not alias.exists()
            and not alias.is_symlink(),
            'native_rpc_alias_not_removed')
    underlying = control / 'command.sock'
    require(cleanup['underlying_control_socket_absent'] is True
            and not underlying.exists() and not underlying.is_symlink(), 'underlying_control_socket_not_removed')
    return True


def committed_sources(commit, sources):
    require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit), 'repository_commit_shape')
    for name, expected in sources.items():
        child(ROOT, name)
        try:
            raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + name],
                                          stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            raise ValueError('uncommitted_execution_source') from None
        require(sha(raw) == expected, 'committed_execution_source_mismatch')


def plan_check(root):
    from scripts import hermes_transport_preflight as launcher
    manifest, manifest_sha = read(root / 'manifest.json')
    require(manifest['schema_version'] == 1, 'preflight_kind')
    profile = launcher.manifest_profile(manifest)
    config = launcher.profile_config(profile)
    require(reports_equal(manifest['config'], config), 'fixed_capability_config')
    require(manifest['execution_driver'] == 'scripts.hermes_transport_preflight.execute'
            and manifest['native_executor'] == 'lifespan.evaluation.runtime.execute_case', 'native_driver_contract')
    require(manifest['source_sha256'] == launcher.execution_sources(profile), 'execution_source_mismatch')
    require(manifest['dependencies'] == launcher.dependencies(profile), 'native_dependency_mismatch')
    require(manifest.get('source_commit_verified') is True, 'uncommitted_execution_source')
    committed_sources(manifest['repository_commit'], manifest['source_sha256'])
    launcher.validate_model(manifest['target_model'], manifest['model_base_url'])
    require(manifest['transports'] == {m: contract(m) for m in launcher.profile_modes(profile)}, 'transport_contracts')
    require((root / 'private/initial_skill.txt').read_bytes() == SEED_SKILL.encode()
            and manifest['initial_skill_sha256'] == sha(SEED_SKILL.encode()), 'initial_skill_bytes')
    hashes, capsules = {}, {}
    for workflow, expected in launcher.expected_capsules(profile).items():
        value, file_sha = read(root / 'private/cases' / (workflow + '.json'))
        require(reports_equal(value, expected), 'fixed_synthetic_capsule')
        hashes[workflow], capsules[workflow] = file_sha, value
    require(reports_equal(manifest['slots'], launcher.expected_slots(hashes, profile)) and len(manifest['slots']) == config['fixed_slots'],
            'fixed_six_slot_paired_plan')
    return manifest, manifest_sha, capsules


def costs_check(record):
    try:
        return {**physical_usage(record), 'accounting_verified': True, 'reservation_reason': None}
    except (KeyError, TypeError, ValueError):
        usage = record.get('usage', {}) if type(record) is dict else {}
        if type(usage) is not dict: usage = {}
        observed = {k: v for k, v in usage.items() if k in
                    ('api_calls', 'charged_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens') and integer(v)}
        return {'api_calls': None, 'total_tokens': None, 'complete': False,
                'reported_tokens': None, 'charged_tokens': max(250000, observed.get('charged_tokens', 0)),
                'reserved_model_calls': max(16, observed.get('api_calls', 0)), 'accounting_verified': False,
                'reservation_reason': 'missing_or_unreconciled_native_receipt',
                'observed_usage_unverified': observed, 'violations': []}


def aggregate_costs(receipts):
    costs = [r['costs'] for r in receipts]
    complete = bool(costs) and all(c['accounting_verified'] and c['complete'] for c in costs)
    return {'accounting_verified': bool(costs) and all(c['accounting_verified'] for c in costs), 'complete': complete,
            'physical_model_calls': sum(c['api_calls'] for c in costs) if all(c['api_calls'] is not None for c in costs) else None,
            'charged_or_reserved_model_calls': sum(c['api_calls'] if c['api_calls'] is not None else c['reserved_model_calls'] for c in costs),
            'charged_or_reserved_tokens': sum(c['charged_tokens'] for c in costs),
            'reported_tokens_known_prefix': sum(c.get('reported_tokens') or 0 for c in costs),
            'total_tokens': sum(c['total_tokens'] for c in costs) if complete else None}


def audit_preflight(directory, strict=False, expected_manifest_sha256=None):
    root = Path(directory).resolve()
    output = {'schema_version': 1, 'status': 'invalid', 'ok': False, 'errors': [], 'slots': [],
              'accounting_verified': False, 'capability_pass': False, 'model_quality_score': None,
              'scope': 'six_fixed_transport_component_slots; no_learning_effect_or_world_study_claim'}
    def error(code):
        output['errors'].append({'code': code})
    try:
        manifest, manifest_sha, capsules = plan_check(root)
        config = manifest['config']; count = config['fixed_slots']
        output['manifest_sha256'] = manifest_sha
        if manifest.get('provider_contract') is not None:
            output['scope'] = 'three_fixed_profile_transport_component_slots; no_learning_effect_or_world_study_claim'
            output['provider_contract'] = deepcopy(manifest['provider_contract'])
        require(expected_manifest_sha256 is None or expected_manifest_sha256 == manifest_sha, 'published_manifest_hash')
        state, state_sha = read(root / 'state.json'); slots = manifest['slots']
        output['slots'] = [{'slot_id': s['slot_id'], 'mode': s['mode'], 'workflow': s['workflow'], 'status': 'not_attempted'} for s in slots]
        require(state['schema_version'] == 1 and type(state['receipts']) is list and len(state['receipts']) <= count,
                'state_receipt_shape')
        execution_path = root / 'EXECUTION.json'; marker_path = root / 'INFLIGHT.json'
        report_path = root / 'REPORT.json'
        if not execution_path.exists():
            require(state == {'schema_version': 1, 'status': 'prepared', 'receipts': []}
                    and not marker_path.exists() and not report_path.exists()
                    and not any((root / 'private/receipts').glob('*'))
                    and not any((root / 'private/trials').glob('*')), 'prepared_state_contains_execution')
            output.update(status='valid_prepared', ok=not strict)
            if strict: error('preflight_not_completed')
            return output
        execution, execution_sha = read(execution_path)
        require(execution['schema_version'] == 1 and execution['manifest_sha256'] == manifest_sha
                and execution['registered_manifest_sha256'] == manifest_sha
                and reports_equal(execution['config'], manifest['config'])
                and execution['execution_driver'] == manifest['execution_driver']
                and number(execution['started_unix_seconds']), 'execution_manifest_binding')
        require(execution['fixture'] is False and execution['executor_identity'] == manifest['native_executor'],
                'fixture_is_not_native_evidence')
        receipts, paths, previous_elapsed, reconciled_costs = [], set(), 0, []
        for index, pointer in enumerate(state['receipts']):
            slot = slots[index]; expected_path = 'private/receipts/' + slot['slot_id'] + '.json'
            require(pointer['path'] == expected_path, 'receipt_slot_order')
            receipt, file_sha = read(child(root, expected_path)); paths.add(expected_path)
            require(pointer['sha256'] == file_sha, 'receipt_file_hash')
            require(receipt['schema_version'] == 1 and type(receipt['index']) is int and receipt['index'] == index
                    and receipt['slot_id'] == slot['slot_id'] and receipt['capsule_sha256'] == slot['capsule_sha256'], 'receipt_slot_binding')
            require(receipt['fixture'] is False and receipt['executor_identity'] == manifest['native_executor'], 'fixture_receipt')
            require(receipt['trial_path'] == 'private/trials/' + slot['slot_id'], 'trial_path_binding')
            trial = child(root, receipt['trial_path']); native_root = trial / 'native'
            record = None; session_sha = None
            if (native_root / 'session.json').exists(): record, session_sha = read(native_root / 'session.json')
            require(session_sha == receipt['session_sha256'], 'native_session_hash')
            costs = costs_check(record)
            reconciled_costs.append({'costs': costs})
            output['usage'] = aggregate_costs(reconciled_costs)
            output['accounting_verified'] = output['usage']['accounting_verified']
            output['accounting_scope'] = 'independently_reconciled_receipt_prefix; excludes_any_unread_or_unbound_later_slots'
            output['slots'][index]['costs'] = deepcopy(costs)
            require(reports_equal(receipt['costs'], costs), 'receipt_costs_mismatch')
            supervision, supervision_sha = read(trial / 'supervision.json')
            cleanup, cleanup_sha = read(trial / 'cleanup.json')
            require(supervision_sha == receipt['supervision_sha256'] and cleanup_sha == receipt['cleanup_sha256']
                    and reports_equal(supervision['cleanup'], cleanup), 'supervision_cleanup_hash')
            require(supervision['timeout_seconds'] == 420 and supervision['cleanup_seconds'] == 30
                    and all(number(supervision[k]) for k in ('elapsed_seconds', 'execution_elapsed_seconds'))
                    and supervision['elapsed_seconds'] >= supervision['execution_elapsed_seconds'] + cleanup['elapsed_seconds'],
                    'supervision_timing_contract')
            evidence = None; evidence_error = cleanup_error = None; cleaned = False
            try: evidence = native_session(record, native_root, capsules[slot['workflow']], slot, manifest)
            except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc: evidence_error = type(exc).__name__
            try: cleaned = cleanup_check(trial, slot, cleanup, provider_contract=manifest.get('provider_contract'))
            except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc: cleanup_error = type(exc).__name__
            require(reports_equal(receipt['native_evidence'], evidence) and receipt['evidence_error_type'] == evidence_error
                    and receipt['cleanup_error_type'] == cleanup_error and receipt['cleanup_confirmed'] is cleaned,
                    'receipt_native_or_cleanup_evidence')
            if supervision['status'] == 'returned' or (type(supervision.get('outcome')) is dict
                                                       and supervision['outcome'].get('status') == 'returned'):
                outcome, _ = read(trial / 'worker-outcome.json')
                require(outcome == supervision['outcome'] and outcome['status'] == 'returned'
                        and outcome['session_sha256'] == session_sha, 'worker_outcome_session_binding')
            valid = bool(supervision['status'] == 'returned' and type(supervision['root_exitcode']) is int
                         and supervision['root_exitcode'] == 0 and costs['accounting_verified'] and costs['complete']
                         and not costs['violations'] and evidence is not None and cleaned
                         and supervision['execution_elapsed_seconds'] <= 420 and supervision['elapsed_seconds'] <= 450)
            expected_status = 'interrupted' if supervision['status'] == 'interrupted' else 'completed' if valid else 'halted_infrastructure'
            require(receipt['status'] == expected_status
                    and receipt['capability_pass'] is bool(valid and evidence['transport_roundtrip_capable']), 'receipt_validity_claim')
            require(number(receipt['elapsed_seconds']) and previous_elapsed + supervision['elapsed_seconds'] <= receipt['elapsed_seconds'],
                    'receipt_chronology')
            previous_elapsed = receipt['elapsed_seconds']; receipts.append(receipt)
            output['slots'][index].update(status=receipt['status'], capability_pass=receipt['capability_pass'],
                                         costs=deepcopy(costs), native_evidence=evidence, cleanup_confirmed=cleaned)
            require(valid or index == len(state['receipts']) - 1, 'execution_continued_after_invalid_slot')
        require({str(p.relative_to(root)) for p in (root / 'private/receipts').glob('*.json')} == paths,
                'untracked_receipt_inventory')
        usage = aggregate_costs(receipts)
        if 'usage' in state: require(reports_equal(state['usage'], usage), 'state_cost_aggregate')
        elif receipts: raise ValueError('missing_state_costs')
        require(state['status'] in ('prepared', 'running', 'completed', 'halted_budget', 'halted_infrastructure', 'interrupted'), 'state_status')
        require(not receipts or state['status'] != 'prepared', 'prepared_state_has_receipts')
        inflight = 0
        if marker_path.exists():
            marker, _ = read(marker_path)
            require(len(receipts) < count and marker == {'slot_id': slots[len(receipts)]['slot_id'], 'index': len(receipts),
                    'reserved_model_calls': 16, 'reserved_tokens': 250000} and not report_path.exists()
                    and state['status'] in ('prepared', 'running'), 'inflight_identity')
            inflight = 1; output['slots'][len(receipts)]['status'] = 'inflight_usage_unknown'
        trial_ids = {p.name for p in (root / 'private/trials').iterdir()} if (root / 'private/trials').exists() else set()
        allowed_ids = {s['slot_id'] for s in slots[:len(receipts) + inflight]}
        require(trial_ids <= allowed_ids and {s['slot_id'] for s in slots[:len(receipts)]} <= trial_ids,
                'untracked_trial_inventory')
        output.update(usage=usage, accounting_verified=usage['accounting_verified'] and not inflight,
                      attempted_slots=len(receipts), inflight_reserved_calls=16*inflight, inflight_reserved_tokens=250000*inflight)
        require(usage['charged_or_reserved_model_calls'] + 16*inflight <= config['max_model_calls']
                and usage['charged_or_reserved_tokens'] + 250000*inflight <= config['max_charged_tokens'], 'campaign_physical_budget')
        if report_path.exists():
            report, report_sha = read(report_path)
            require(state['status'] == report['status'] and report['status'] in ('completed', 'halted_budget', 'halted_infrastructure', 'interrupted'),
                    'terminal_report_status')
            if state['status'] == 'halted_infrastructure':
                require(bool(receipts) and receipts[-1]['status'] == 'halted_infrastructure', 'false_infrastructure_halt')
            if state['status'] == 'halted_budget':
                require(all(r['status'] == 'completed' for r in receipts)
                        and ((len(receipts) == count and report['elapsed_seconds'] > config['max_run_seconds'])
                             or (len(receipts) < count and (report['elapsed_seconds'] + 450 > config['max_run_seconds']
                             or usage['charged_or_reserved_model_calls'] + 16 > config['max_model_calls']
                             or usage['charged_or_reserved_tokens'] + 250000 > config['max_charged_tokens']))), 'false_budget_halt')
            require(number(report['elapsed_seconds']) and report['elapsed_seconds'] >= previous_elapsed
                    and state['elapsed_seconds'] == report['elapsed_seconds'], 'terminal_clock')
            rebuilt = {'schema_version': 1, 'kind': manifest['kind'], 'status': state['status'], 'fixture': False,
                'manifest_sha256': manifest_sha, 'execution_sha256': execution_sha,
                'attempted_slots': len(receipts), 'fixed_slots': count, 'usage': usage,
                'elapsed_seconds': report['elapsed_seconds'],
                'capability_pass': bool(state['status'] == 'completed' and len(receipts) == count and all(r['capability_pass'] for r in receipts)),
                'slots': [{'slot_id': s['slot_id'], 'mode': s['mode'], 'workflow': s['workflow'],
                    'status': receipts[i]['status'] if i < len(receipts) else 'not_attempted',
                    'capability_pass': receipts[i]['capability_pass'] if i < len(receipts) else None,
                    'native_evidence': receipts[i]['native_evidence'] if i < len(receipts) else None} for i, s in enumerate(slots)]}
            require(reports_equal(report, rebuilt), 'persisted_report_mismatch')
            output['report_sha256'] = report_sha
        completed = report_path.exists() and state['status'] == 'completed'
        if completed:
            require(len(receipts) == count and all(r['status'] == 'completed' for r in receipts) and not inflight,
                    'completed_six_slot_contract')
            require(state['elapsed_seconds'] <= config['max_run_seconds'], 'campaign_wall_budget')
        elif state['status'] == 'completed': raise ValueError('completed_state_missing_report')
        output.update(status='valid_completed' if completed else 'incomplete',
                      capability_pass=bool(completed and all(r['capability_pass'] for r in receipts)),
                      ok=completed or not strict, state_sha256=state_sha)
        if strict and not completed: error('preflight_not_completed')
    except (OSError, AttributeError, KeyError, ValueError, TypeError, IndexError) as exc:
        error(str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else type(exc).__name__)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory'); parser.add_argument('--strict', action='store_true')
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    result = audit_preflight(args.directory, args.strict, args.manifest_sha256)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
