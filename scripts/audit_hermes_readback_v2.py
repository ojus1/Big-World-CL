#!/usr/bin/env python3
"""Readback audit for pinned Hermes warning and exact compound cat/hash output.

Never rewrites a native session, receipt, report or the original preflight
verdict. The original auditor must pass first at its matching source revision.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.computers import HERMES
from lifespan.evaluation.hermes_transport import PIN, verify_source
from scripts.audit_hermes_preflight import audit_preflight

NATIVE_SOURCES = {
    'agent/tool_guardrails.py': 'd4ebeded7abcb36dd0d10d235313fb7bfd05309a30850a0c3a008844f1d62d40',
    'agent/tool_executor.py': '34da0c06add4db54342c70b686e747b01e114607668e769bd7ed6b087897e002',
    'tools/terminal_tool.py': '59a0f637caec97c0a87aed5c667267c537d8747dcab91b408850e34c9eeba64a'}
ARTIFACT_PATH = '/workspace/deliverables/capability.json'
COMPOUND_COMMAND = f'cat {ARTIFACT_PATH} && sha256sum {ARTIFACT_PATH}'
VERSION = 'hermes-native-readback-audit-v2'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def warning(count):
    # Exact append_toolguard_guidance + after_call warning at PIN, not a
    # permissive 'first JSON object' extraction or arbitrary suffix stripping.
    return (f'\n\n[Tool loop warning: idempotent_no_progress_warning; count={count}; '
            f'read_file returned the same result {count} times. '
            'Use the result already provided or change the query instead of '
            'repeating it unchanged.]')


def compound_output(raw, submitted):
    # Pinned terminal_tool.py strips the combined output before returning it.
    # Normalize the expected output only; observed prefixes/suffixes must not be
    # discarded. The checksum binds the original bytes, including whitespace.
    # Any redaction, truncation or other output transformation cannot match.
    return (raw.decode('utf-8') + submitted + '  ' + ARTIFACT_PATH + '\n').strip()


def decode_observation(content, *, name):
    require(type(content) is str, 'tool_observation_not_text')
    stripped = content.lstrip()
    value, end = json.JSONDecoder().raw_decode(stripped)
    require(type(value) is dict, 'tool_observation_not_object')
    suffix = stripped[end:]
    if not suffix.strip():
        return value, None
    match = re.search(r'count=([1-9][0-9]*);', suffix)
    count = int(match.group(1)) if match else 0
    require(name == 'read_file' and count >= 2 and suffix == warning(count),
            'unrecognized_tool_observation_suffix')
    return value, count


def readback_evidence(record, directory):
    """Reconstruct matching native tool results after the trusted commit call.

    Callers must run the original raw/session/grade/source/cleanup audit first.
    This supports the exact native warning envelope and one literal compound
    cat/hash command; it does not interpret arbitrary shell commands.
    """
    native = record['result']['native']; messages = native['messages']
    submitted = record['last_submitted_artifact_sha256']
    require(type(submitted) is str and re.fullmatch('[0-9a-f]{64}', submitted), 'missing_submitted_hash')
    artifact = Path(directory) / 'filesystem_objects' / submitted
    raw = artifact.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == submitted, 'submitted_object_hash')
    expected = canonical(json.loads(raw))
    calls = {}
    for index, message in enumerate(messages):
        if message.get('role') != 'assistant':
            continue
        for call in message.get('tool_calls') or []:
            require(type(call.get('id')) is str and call['id'] not in calls, 'duplicate_tool_call_id')
            function = call['function']; args = json.loads(function['arguments'])
            require(type(args) is dict, 'tool_arguments_not_object')
            calls[call['id']] = (index, function['name'], args)
    commits = []; repeats = {}; results = []; seen_results = set()
    for index, message in enumerate(messages):
        if message.get('role') != 'tool':
            continue
        call_id = message.get('tool_call_id')
        require(call_id in calls and call_id not in seen_results, 'unbound_or_duplicate_tool_result')
        seen_results.add(call_id); call_index, name, args = calls[call_id]
        require(call_index < index and message.get('name') == name, 'tool_result_order_or_name')
        if name == 'enterprise_action' and args.get('operation') == 'work.commit':
            payload = json.loads(message['content'])
            if (payload.get('artifact_sha256') == submitted and 'observation' in payload and any(
                    rpc.get('action', {}).get('tool') == 'work.commit' and
                    canonical(rpc.get('response')) == canonical(payload)
                    for rpc in record['result'].get('workplace_rpc', []))):
                commits.append(index)
            continue
        if name not in ('read_file', 'terminal'):
            continue
        signature = canonical([name, args])
        try:
            payload, count = decode_observation(message.get('content'), name=name)
        except (ValueError, TypeError):
            # A malformed/unknown envelope cannot establish readback, and it
            # breaks this call signature's observed repeat history.
            repeats.pop(signature, None)
            continue
        key = canonical(payload)
        previous_key, previous_count = repeats.get(signature, (None, 0))
        observed_count = previous_count + 1 if key == previous_key else 1
        if payload.get('error'):
            repeats.pop(signature, None); continue
        repeats[signature] = (key, observed_count)
        if count is not None:
            require(count == observed_count, 'native_warning_repeat_count_unproven')
        if not any(commit < call_index for commit in commits):
            continue
        try:
            command = (shlex.split(args['command']) if name == 'terminal' and
                       type(args.get('command')) is str else [])
        except ValueError:
            continue
        is_read = name == 'read_file' and args.get('path') == ARTIFACT_PATH
        is_cat = name == 'terminal' and command in (['cat', ARTIFACT_PATH], ['cat', '--', ARTIFACT_PATH])
        is_hash = name == 'terminal' and command in (['sha256sum', ARTIFACT_PATH], ['sha256sum', '--', ARTIFACT_PATH])
        # shlex alone would conflate a quoted '&&' argument with a shell
        # operator. Only this literal command and its single argument field are
        # supported; no quoting, substitutions, extra commands or options.
        is_compound = name == 'terminal' and args == {'command': COMPOUND_COMMAND}
        if not (is_read or is_cat or is_hash or is_compound):
            continue
        body = payload.get('content' if is_read else 'output')
        if type(body) is not str or (not is_read and
                (type(payload.get('exit_code')) is not int or payload['exit_code'] != 0)):
            continue
        if is_compound and (set(payload) != {'output', 'exit_code', 'error'} or
                not (payload['error'] is None or type(payload['error']) is str and payload['error'] == '')):
            continue
        if is_read:
            body = '\n'.join(re.sub(r'^\s*\d+\|', '', line) for line in body.splitlines())
        try:
            if is_compound:
                matches = body == compound_output(raw, submitted)
            else:
                matches = (bool(body.strip()) and body.strip().split()[0] == submitted
                           if is_hash else canonical(json.loads(body)) == expected)
        except (ValueError, TypeError):
            matches = False
        if not matches:
            continue
        final = [i for i, item in enumerate(messages[index + 1:], index + 1)
                 if item.get('role') == 'assistant' and type(item.get('content')) is str and
                 item['content'].strip() and not item.get('tool_calls')]
        if final:
            results.append({'tool': name, 'call_index': call_index, 'result_index': index,
                'final_response_index': final[0], 'artifact_sha256': submitted,
                'tool_payload_sha256': hashlib.sha256(key.encode()).hexdigest(),
                'native_warning_count': count, 'observed_same_result_count': observed_count,
                'warning_sha256': hashlib.sha256(warning(count).encode()).hexdigest() if count is not None else None})
    eligible = bool(record['skill_loaded'] and commits and results and
        not native['evaluation_budget'].get('disabled_auxiliary_calls', []) and
        not native.get('failed', False) and not record.get('budget_exhausted', False) and
        native['evaluation_budget']['physical_model_calls'] >= 2)
    return {'transport_roundtrip_capable': eligible, 'readbacks': results,
            'physical_request_to_message_binding': 'not_recorded; trajectory_inference_from_pinned_native_harness'}


def audit(directory, *, manifest_sha256):
    root = Path(directory).resolve()
    output = {'schema_version': 2, 'kind': VERSION, 'ok': False, 'capability_pass': False,
              'errors': [], 'scope': 'posthoc_native_tool_envelope_correction; no_original_artifact_rewrite',
              'slots': [], 'model_quality_score': None}
    try:
        native_root = verify_source(HERMES)
        require(all(sha(native_root / name) == value for name, value in NATIVE_SOURCES.items()), 'native_warning_source_changed')
        original = audit_preflight(root, strict=True, expected_manifest_sha256=manifest_sha256)
        output['original_audit'] = original
        require(original['ok'] and original['status'] == 'valid_completed', 'original_preflight_integrity_failed')
        manifest = read(root / 'manifest.json'); report = read(root / 'REPORT.json')
        state = read(root / 'state.json')
        for slot, pointer in zip(manifest['slots'], state['receipts']):
            receipt = read(root / pointer['path']); native_dir = root / receipt['trial_path'] / 'native'
            record = read(native_dir / 'session.json')
            evidence = readback_evidence(record, native_dir)
            output['slots'].append({'slot_id': slot['slot_id'], 'workflow': slot['workflow'], 'mode': slot['mode'],
                'session_sha256': sha(native_dir / 'session.json'), 'receipt_sha256': sha(root / pointer['path']),
                'original_capability_pass': receipt['capability_pass'], 'corrected_evidence': evidence,
                'semantic_success': record['success'], 'semantic_score': record['semantic_score'],
                'business_committed': receipt['native_evidence']['business_committed']})
        require(len(output['slots']) == 6, 'six_slot_inventory')
        output.update(ok=True, capability_pass=all(row['corrected_evidence']['transport_roundtrip_capable'] for row in output['slots']),
            original_report_capability_pass=report['capability_pass'], usage=deepcopy(report['usage']),
            elapsed_seconds=report['elapsed_seconds'], manifest_sha256=manifest_sha256,
            original_report_sha256=sha(root / 'REPORT.json'), original_state_sha256=sha(root / 'state.json'),
            correction_source_sha256=sha(__file__), hermes_revision=PIN, native_warning_source_sha256=NATIVE_SOURCES)
    except (KeyError, ValueError, TypeError, IndexError, OSError) as exc:
        output['errors'].append(str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else type(exc).__name__)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path); parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args(); result = audit(args.directory, manifest_sha256=args.manifest_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result['ok'] and result['capability_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
