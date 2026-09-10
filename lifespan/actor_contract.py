"""Future opt-in client verification; schemas are the tracked server-owned source.

No provider or native process is imported here. A receipt proves wire provenance,
not business authority. All ordinary decision validators still run afterwards.
"""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
_PATH = ROOT / 'local-overrides/backend/app/utils/actor_output_contract.py'
_NAME = '_bigworld_actor_output_contract'
if _NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_NAME, _PATH)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _module
    _spec.loader.exec_module(_module)
wire = sys.modules[_NAME]


def options(value):
    wire.require(type(value) is dict and set(value) == {'version', 'max_output_tokens', 'timeout_seconds'},
                 'invalid_actor_contract_options')
    result = wire.normalize_contract({**value, 'role': 'employee'})
    del result['role']
    return result


def descriptor(config, role):
    return wire.normalize_contract({**options(config), 'role': role})


def provenance(config, *, expected_provider=wire.USE_RUNTIME_PROVIDER):
    return {'options': options(config), 'support': wire.capabilities(expected_provider=expected_provider),
            'tracked_patch_sha256': hashlib.sha256((ROOT / 'patches/mirofish-local.patch').read_bytes()).hexdigest(),
            'validation_scope': 'wire_shape_and_receipt_only; existing_business_validators_remain_required',
            'accounting_scope': 'contracted_interviews_only; bootstrap_and_social_calls_are_not_metered'}


def verify_support(actual):
    wire.require(actual == wire.capabilities(), 'server_actor_contract_support_mismatch')


def verify_record(record, *, actor, agent_id, simulation_id, original_prompt, contract, request_key,
                  expected_provider=wire.USE_RUNTIME_PROVIDER):
    """Fail closed before exposing any native/cache response to a decision parser.

Shape-invalid text may be returned for the existing bounded repair step, but
unknown physical usage or a cap/deadline violation is an infrastructure failure.
"""
    try:
        wire.require(record['employee_id'] == actor and record['prompt'] == original_prompt
                     and record['output_contract'] == contract and record['contract_request_key'] == request_key, 'cached_actor_contract_mismatch')
        payload = record['native_result']
        wire.require(type(original_prompt) is str and type(payload.get('prompt')) is str, 'invalid_native_prompt')
        wire.require(payload['success'] is True and type(payload['agent_id']) is int
                     and payload['agent_id'] == agent_id, 'native_payload_actor_mismatch')
        result = payload['result']
        if 'reddit' in result:
            result = result['reddit']
        receipt = result['actor_output_receipt']
        provider = (wire.configured_provider_contract() if expected_provider is wire.USE_RUNTIME_PROVIDER
                    else wire.validate_provider_contract(expected_provider) if expected_provider is not None else None)
        if provider is not None:
            wire.require(wire.validate_provider_contract(receipt.get('provider_contract')) == provider,
                         'native_actor_provider_contract_mismatch')
        else:
            wire.require('provider_contract' not in receipt, 'native_actor_provider_configuration_downgrade')
        binding = receipt['binding']
        expected = {'version': wire.VERSION, 'actor': actor, 'agent_id': agent_id,
            'simulation_id': simulation_id, 'request_key': record['contract_request_key'], 'original_prompt_sha256': wire.text_hash(original_prompt),
            'native_prompt_sha256': wire.text_hash(payload['prompt']), 'contract': contract,
            'contract_sha256': wire.digest(contract), 'schema_sha256': wire.digest(wire.role_schema(contract['role'])),
            'support_sha256': wire.digest(wire.capabilities(expected_provider=provider))}
        wire.require(type(expected['request_key']) is str and re.fullmatch('[0-9a-f]{64}', expected['request_key']),
                     'invalid_logical_request_key')
        expected['request_id'] = wire.digest(expected)
        wire.require(binding == expected, 'native_receipt_binding_mismatch')
        wire.require(receipt['schema_version'] == 1 and receipt['status'] == 'completed'
                     and receipt['provider_status'] == 'completed'
                     and type(receipt['physical_requests_dispatched']) is int and receipt['physical_requests_dispatched'] == 1
                     and receipt['max_physical_requests'] == 1, 'native_receipt_not_completed')
        wire.require(type(result['agent_id']) is int and result['agent_id'] == agent_id
                     and result['native_prompt_sha256'] == expected['native_prompt_sha256']
                     and type(result['trace_rowid']) is int and result['trace_rowid'] > 0,
                     'native_trace_identity_mismatch')
        wire.require(record['response'] == result['response'] and type(result['response']) is str
                     and receipt['output_sha256'] == wire.text_hash(result['response'])
                     and receipt['native_result_sha256'] == wire.digest({k: v for k, v in result.items() if k != 'actor_output_receipt'}),
                     'native_receipt_output_mismatch')
        wire.require(all(type(receipt[k]) is str and re.fullmatch('[0-9a-f]{64}', receipt[k])
                     for k in ('provider_input_sha256', 'provider_request_sha256')), 'missing_provider_request_binding')
        counts = [receipt[k] for k in ('input_tokens', 'output_tokens', 'total_tokens')]
        wire.require(all(type(n) is int and n >= 0 for n in counts) and counts[0] + counts[1] == counts[2]
                     and receipt['accounting_complete'] is True and receipt['reserved_output_tokens'] == 0,
                     'native_usage_unknown_or_inconsistent')
        elapsed = receipt['elapsed_seconds']
        wire.require(type(elapsed) in (int, float) and 0 <= elapsed <= contract['timeout_seconds']
                     and counts[1] <= contract['max_output_tokens'] and receipt['deadline_valid'] is True
                     and receipt['output_budget_valid'] is True, 'native_contract_limit_failure')
        wire.require(type(receipt['output_schema_valid']) is bool
                     and receipt['output_schema_valid'] == wire.shape_valid(result['response'], contract['role']),
                     'native_schema_receipt_mismatch')
        return deepcopy(receipt)
    except (KeyError, TypeError, ValueError):
        raise wire.ContractError('malformed_native_actor_receipt') from None


def audit_interviews(root, manifest, participants, *, completed):
    """Check opt-in local evidence; no signatures or provider authentication.

Private prompt/cache records are read only. The return contains aggregate costs
and hash metadata. Noncompleted orphan requests retain unknown reservations.
"""
    import json
    root = Path(root)
    config = options(manifest['config']['actor_output_contract'])
    expected_provider = manifest.get('provider_contract')
    if expected_provider is not None:
        expected_provider = wire.validate_provider_contract(expected_provider)
    wire.require(manifest['config'].get('provider_profile') == (
        expected_provider['profile'] if expected_provider is not None else None), 'actor_provider_manifest_binding')
    for name in ('lifespan/actor_contract.py', 'lifespan/mirofish.py', 'lifespan/ecosystem_run.py',
                 'lifespan/evaluation/protocol.py', 'lifespan/evaluation/runner.py', 'scripts/audit_evaluation.py'):
        wire.require(manifest['source_sha256'][name] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                     'actor_contract_client_source_provenance')
    wire.require(manifest['actor_output_contract_provenance'] == provenance(config, expected_provider=expected_provider),
                 'actor_contract_source_provenance')
    actors = {p['id']: (index, wire.ROLE_TYPES[p.get('entity_type', 'Employee')]) for index, p in enumerate(participants)}
    actor_root = root / 'actors'
    state = json.loads((actor_root / 'mirofish_state.json').read_text())
    sim = state['simulation']['simulation_id']
    ledger = json.loads((actor_root / 'evaluation_interview_ledger.json').read_text())
    wire.require(ledger['limit'] == manifest['config'].get('max_actor_interviews'), 'actor_interview_budget_binding')
    rows = ledger['requests']
    wire.require(type(rows) is list and len({row['key'] for row in rows}) == len(rows), 'duplicate_actor_request')
    limit = ledger['limit']
    wire.require(limit is None or len(rows) <= limit, 'actor_interview_budget_overrun')
    keys, calls, tokens, unknown, reserved = set(), 0, 0, 0, 0
    for row in rows:
        key = row['key']
        wire.require(type(key) is str and re.fullmatch('[A-Za-z0-9_.-]{1,256}', key) and key not in ('.', '..'), 'unsafe_actor_cache_identity')
        keys.add(key)
        actor = row['actor']; agent, role = actors[actor]
        contract = descriptor(config, role)
        wire.require(row['output_contract'] == contract, 'actor_ledger_contract_binding')
        cache = actor_root / 'mirofish_interviews' / (key + '.json')
        if not cache.exists():
            wire.require(not completed and row['status'] == 'dispatched'
                         and row['accounting_complete'] is False
                         and row['reserved_output_tokens'] == contract['max_output_tokens'], 'unreconciled_actor_request')
            unknown += 1; reserved += row['reserved_output_tokens']
            continue
        record = json.loads(cache.read_text())
        receipt = verify_record(record, actor=actor, agent_id=agent, simulation_id=sim,
            original_prompt=record['prompt'], contract=contract, request_key=wire.text_hash(key),
            expected_provider=expected_provider)
        wire.require(row['status'] == 'completed' and row['prompt_sha256'] == wire.text_hash(record['prompt'])
                     and row['response_sha256'] == receipt['output_sha256'] and row['accounting_complete'] is True
                     and row['native_request_id'] == receipt['binding']['request_id']
                     and row['physical_model_calls'] == receipt['physical_requests_dispatched']
                     and row['tokens'] == receipt['total_tokens'] and row['input_tokens'] == receipt['input_tokens']
                     and row['output_tokens'] == receipt['output_tokens'] and row['reserved_output_tokens'] == 0,
                     'actor_ledger_receipt_disagreement')
        calls += receipt['physical_requests_dispatched']; tokens += receipt['total_tokens']
        if completed and not receipt['output_schema_valid']:
            repair = actor_root / 'mirofish_interviews' / (key + '-repair.json')
            repair_rows = [other for other in rows if other['key'] == key + '-repair']
            wire.require(not key.endswith('-repair') and repair.is_file() and len(repair_rows) == 1
                         and repair_rows[0]['actor'] == actor and repair_rows[0]['output_contract'] == contract,
                         'unresolved_actor_wire_shape_failure')
    cached = {p.stem for p in (actor_root / 'mirofish_interviews').glob('*.json')}
    wire.require(cached <= keys and (not completed or cached == keys), 'untracked_actor_cache')
    return {'logical_requests': len(rows), 'measured_physical_requests': calls, 'measured_tokens': tokens,
        'unknown_requests': unknown, 'reserved_output_tokens': reserved, 'currency_cost': None,
        'cost_status': 'unknown', 'scope': 'reconciled_client_cache_receipts_only; unreconciled_native_receipts_may_hold_known_costs; bootstrap_and_social_calls_excluded'}



def enabled_for_evidence(root, manifest):
    """Reject an option/provenance downgrade that leaves contracted artifacts."""
    import json
    root = Path(root) / 'actors'
    enabled = manifest['config'].get('actor_output_contract') is not None
    marked = manifest.get('actor_output_contract_provenance') is not None
    ledger = root / 'evaluation_interview_ledger.json'
    if ledger.exists():
        marked |= any(row.get('output_contract') is not None for row in json.loads(ledger.read_text())['requests'])
    for directory in ('mirofish_interviews', 'actor_returned_receipts'):
        marked |= any(json.loads(path.read_text()).get('output_contract') is not None for path in (root / directory).glob('*.json'))
    wire.require(enabled or not marked, 'actor_contract_configuration_downgrade')
    return enabled
