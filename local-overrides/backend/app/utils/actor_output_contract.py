"""Opt-in native interview output contracts; no business authority is granted.

This module is copied into MiroFish on fresh installation. Schemas and receipt
locations are server-owned. The ContextVar is installed inside the native
interview task, so a shared model backend never acquires mutable global schema
settings. Output-token reservations do NOT bound or estimate input tokens.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit

VERSION = 'actor-json-v1'
GENERATION_PROJECTION_ID = 'actor-string-maxlength-omission-v1'
ROLE_TYPES = {'Employee': 'employee', 'Enterprise': 'enterprise',
              'GovernmentAgency': 'government', 'Consumer': 'consumer'}
CURRENT = ContextVar('mirofish_actor_output_contract', default=None)
USE_RUNTIME_PROVIDER = object()


class ContractError(RuntimeError):
    """Safe failure code only: never include provider exception text."""


def require(condition, code):
    if not condition:
        raise ContractError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def _text(maximum=1800):
    return {'type': 'string', 'maxLength': maximum}


def _enum(values):
    return {'type': 'string', 'enum': list(values)}


def _array(item, maximum=100):
    return {'type': 'array', 'items': item, 'maxItems': maximum}


def role_schema(role):
    """Return a fresh server-owned schema. Caller schemas are never accepted."""
    require(role in ROLE_TYPES.values(), 'unsupported_actor_role')
    if role == 'employee':
        return _object({'delegate': {'type': 'boolean'}, 'request': _text(12000), 'working_notes': _text(),
            'share_document_ids': _array(_text(256)),
            'colleague_messages': _array(_object({'recipient': _text(256), 'text': _text(4000),
                                               'document_ids': _array(_text(256))}), 1),
            'process_proposal': {'anyOf': [{'type': 'null'}, _object({
                'action': _enum(['require_peer_review']), 'reason': _text()})]}})
    common = {'notes': _text(), 'reason': _text(4000), 'evidence_ids': _array(_text(256))}
    if role == 'enterprise':
        return _object({**common, 'objective': _enum(['growth', 'reliability', 'resilience', 'cost_control']),
            'price': {'type': 'number', 'minimum': 6, 'maximum': 20},
            'target_market': _enum(['domestic', 'cross_border']),
            'priority_workflow': _enum(['onboarding', 'renewal', 'incident']),
            'procedure': _enum(['keep', 'alternate_route', 'standard_route'])})
    if role == 'government':
        return _object({**common, 'policy': _enum(['keep', 'baseline', 'enhanced_review']),
                        'duration': {'type': 'integer', 'minimum': 2, 'maximum': 10}})
    return _object({**common, 'action': _enum(['wait', 'purchase', 'switch', 'complain']),
                    'firm': {'anyOf': [{'type': 'null'}, _text(256)]}})


def normalize_contract(raw):
    require(type(raw) is dict and set(raw) == {'version', 'role', 'max_output_tokens', 'timeout_seconds'}, 'invalid_contract_fields')
    require(raw['version'] == VERSION and raw['role'] in ROLE_TYPES.values(), 'unsupported_contract_version_or_role')
    for key, minimum, maximum in (('max_output_tokens', 256, 8192), ('timeout_seconds', 1, 120)):
        require(type(raw[key]) is int and minimum <= raw[key] <= maximum, 'invalid_contract_bound')
    return dict(raw)


def generation_schema(role, provider):
    """Provider-only projection; the authoritative acceptance schema is intact.

    Visit schema nodes, never arbitrary object keys: a property named
    ``maxLength`` is data describing a field, not this schema keyword.
    """
    schema = role_schema(role)
    if provider is None:
        return schema
    validate_provider_contract(provider)

    def project(node):
        if node.get('type') == 'string':
            node.pop('maxLength', None)
        for child in node.get('properties', {}).values():
            project(child)
        if isinstance(node.get('items'), dict):
            project(node['items'])
        for child in node.get('anyOf', []):
            project(child)

    project(schema)
    return schema


def generation_contract(role, provider):
    if provider is None:
        return None
    return {'projection_id': GENERATION_PROJECTION_ID,
            'acceptance_schema_sha256': digest(role_schema(role)),
            'generation_schema_sha256': digest(generation_schema(role, provider))}


def _valid(value, schema):
    if 'anyOf' in schema:
        return any(_valid(value, branch) for branch in schema['anyOf'])
    kind = schema['type']
    if kind == 'object':
        return (type(value) is dict and set(value) == set(schema['properties'])
                and all(_valid(value[key], item) for key, item in schema['properties'].items()))
    if kind == 'array':
        return type(value) is list and len(value) <= schema['maxItems'] and all(_valid(item, schema['items']) for item in value)
    if kind == 'null':
        return value is None
    if kind == 'boolean':
        return type(value) is bool
    if kind == 'string':
        return type(value) is str and len(value) <= schema.get('maxLength', 10**9) and ('enum' not in schema or value in schema['enum'])
    return (type(value) is int if kind == 'integer' else type(value) in (int, float)) and schema['minimum'] <= value <= schema['maximum'] and math.isfinite(value)


def shape_valid(text, role):
    def pairs(items):
        require(len(items) == len(dict(items)), 'duplicate_json_property')
        return dict(items)
    try:
        def invalid_constant(_):
            raise ContractError('nonfinite_json_constant')
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
        return _valid(value, role_schema(role))
    except (ValueError, TypeError, OverflowError, RecursionError, ContractError):
        return False


def registered_actor(simulation_dir, agent_id):
    """Read only the server's registered identity/type; never export personas."""
    require(type(agent_id) is int and agent_id >= 0, 'invalid_agent_id')
    root = Path(simulation_dir)
    config = json.loads((root / 'simulation_config.json').read_text())
    rows = [row for row in config['agent_configs'] if row['agent_id'] == agent_id]
    profiles = json.loads((root / 'reddit_profiles.json').read_text())
    require(len(rows) == 1 and agent_id < len(profiles), 'unregistered_actor')
    actor = profiles[agent_id]['username']
    require(type(actor) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,256}', actor), 'invalid_registered_actor_identity')
    role = ROLE_TYPES.get(rows[0]['entity_type'])
    require(role is not None, 'unsupported_registered_actor_type')
    return actor, role


def bind_request(simulation_dir, agent_id, original_prompt, native_prompt, contract, request_key):
    contract = normalize_contract(contract)
    require(type(request_key) is str and re.fullmatch('[0-9a-f]{64}', request_key), 'invalid_logical_request_key')
    actor, role = registered_actor(simulation_dir, agent_id)
    require(contract['role'] == role, 'contract_role_identity_mismatch')
    require(type(original_prompt) is str and type(native_prompt) is str and bool(native_prompt), 'invalid_contract_prompt')
    binding = {'version': VERSION, 'actor': actor, 'agent_id': agent_id, 'request_key': request_key,
        'simulation_id': Path(simulation_dir).name, 'original_prompt_sha256': text_hash(original_prompt),
        'native_prompt_sha256': text_hash(native_prompt), 'contract': contract,
        'contract_sha256': digest(contract), 'schema_sha256': digest(role_schema(role)),
        'support_sha256': digest(capabilities())}
    binding['request_id'] = digest(binding)
    return binding


def capabilities(*, expected_provider=USE_RUNTIME_PROVIDER):
    transport = json.loads(Path(__file__).with_name('actor_contract_transport.json').read_text())
    result = {'version': VERSION, 'transport_sha256': transport, 'platforms': ['reddit'], 'backends': ['responses'], 'max_physical_requests': 1,
        'role_schema_sha256': {role: digest(role_schema(role)) for role in ROLE_TYPES.values()},
        'contract_module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'bridge_module_sha256': hashlib.sha256(Path(__file__).with_name('camel_responses.py').read_bytes()).hexdigest()}
    provider = (configured_provider_contract() if expected_provider is USE_RUNTIME_PROVIDER
                else validate_provider_contract(expected_provider) if expected_provider is not None else None)
    if provider is not None:
        result['provider_contract'] = provider
        contracts = {role: generation_contract(role, provider) for role in ROLE_TYPES.values()}
        result['generation_schema_projection'] = {
            'projection_id': GENERATION_PROJECTION_ID,
            'acceptance_schema_sha256': {role: value['acceptance_schema_sha256'] for role, value in contracts.items()},
            'generation_schema_sha256': {role: value['generation_schema_sha256'] for role, value in contracts.items()}}
    return result


def provider_contract(model, base_url, profile='responses-no-thinking-v1'):
    """Server copy of the public provider descriptor; never contains a key."""
    require(profile == 'responses-no-thinking-v1', 'unsupported_actor_provider_profile')
    require(type(model) is str and 0 < len(model) <= 200 and model == model.strip()
            and not any(c in model for c in '\r\n'), 'invalid_actor_provider_model')
    require(type(base_url) is str and bool(base_url) and not any(c.isspace() for c in base_url), 'invalid_actor_provider_base_url')
    try:
        parsed = urlsplit(base_url)
        require(parsed.scheme in ('http', 'https') and bool(parsed.hostname)
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
                'invalid_actor_provider_base_url')
        parsed.port
    except ValueError:
        raise ContractError('invalid_actor_provider_base_url') from None
    return {'schema_version': 1, 'profile': 'responses-no-thinking-v1', 'model': model,
            'base_url': base_url.rstrip('/'), 'api_mode': 'responses', 'stream': False, 'store': False,
            'chat_template_kwargs': {'enable_thinking': False}}


def validate_provider_contract(value):
    require(type(value) is dict, 'invalid_actor_provider_contract')
    expected = provider_contract(value.get('model'), value.get('base_url'), value.get('profile'))
    require(set(value) == set(expected) and type(value.get('schema_version')) is int
            and type(value.get('stream')) is bool and type(value.get('store')) is bool
            and type(value.get('chat_template_kwargs')) is dict
            and type(value['chat_template_kwargs'].get('enable_thinking')) is bool
            and value == expected, 'invalid_actor_provider_contract')
    return deepcopy(expected)


def configured_provider_contract():
    """Delayed lookup: MiroFish loads Config/dotenv before constructing models.

    The absent selector preserves legacy capability/receipt structure. A named
    profile must have explicit nonsecret model/base configuration in both client
    and native worker; a missing or different profile cannot reuse its receipts.
    """
    selected = os.environ.get('BIGWORLD_PROVIDER_PROFILE')
    if selected is None:
        return None
    require(selected == 'responses-no-thinking-v1', 'unsupported_actor_provider_profile')
    return provider_contract(os.environ.get('LLM_MODEL_NAME'), os.environ.get('LLM_BASE_URL'))


def require_transport_support(backend_root):
    """Internal installation check; no client controls these relative paths."""
    expected = capabilities()['transport_sha256']
    paths = ('app/api/simulation.py', 'app/services/simulation_runner.py',
             'app/services/simulation_ipc.py', 'scripts/run_reddit_simulation.py')
    require(set(expected) == set(paths), 'invalid_transport_manifest')
    for relative in paths:
        path = Path(backend_root) / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected[relative],
                'native_transport_source_mismatch')


def simulation_path(root, simulation_id):
    require(type(simulation_id) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', simulation_id), 'invalid_simulation_identity')
    parent = Path(root).resolve()
    path = (parent / simulation_id).resolve()
    require(path.parent == parent, 'invalid_simulation_directory')
    return path


def require_worker_support(simulation_dir):
    status = json.loads((Path(simulation_dir) / 'env_status.json').read_text())
    require(status.get('status') in ('alive', 'waiting', 'running')
            and status.get('actor_output_contract') == capabilities(), 'native_worker_contract_support_mismatch')


def validate_binding(simulation_dir, agent_id, native_prompt, binding):
    require(type(binding) is dict and set(binding) == {'version', 'actor', 'agent_id', 'simulation_id',
        'original_prompt_sha256', 'native_prompt_sha256', 'request_key', 'contract', 'contract_sha256', 'schema_sha256', 'support_sha256', 'request_id'}, 'invalid_binding_fields')
    actor, role = registered_actor(simulation_dir, agent_id)
    contract = normalize_contract(binding['contract'])
    require(binding['version'] == VERSION and binding['actor'] == actor and type(binding['agent_id']) is int and binding['agent_id'] == agent_id
            and binding['simulation_id'] == Path(simulation_dir).name and contract['role'] == role,
            'native_actor_binding_mismatch')
    require(all(type(binding[key]) is str and re.fullmatch('[0-9a-f]{64}', binding[key]) for key in
        ('request_key', 'original_prompt_sha256', 'native_prompt_sha256', 'contract_sha256', 'schema_sha256', 'support_sha256', 'request_id')), 'invalid_binding_hash')
    require(binding['native_prompt_sha256'] == text_hash(native_prompt) and binding['contract_sha256'] == digest(contract)
            and binding['schema_sha256'] == digest(role_schema(role))
            and binding['support_sha256'] == digest(capabilities())
            and binding['request_id'] == digest({key: value for key, value in binding.items() if key != 'request_id'}), 'native_contract_binding_mismatch')
    return deepcopy(binding)


def trace_cursor(simulation_dir):
    """Server-owned DB only; record the boundary before the native action."""
    with sqlite3.connect(Path(simulation_dir) / 'reddit_simulation.db') as connection:
        return connection.execute('SELECT COALESCE(MAX(rowid), 0) FROM trace').fetchone()[0]


def contracted_trace_result(simulation_dir, agent_id, prompt, after_rowid):
    """Require exactly one new matching native trace; never reuse a stale row."""
    require(type(after_rowid) is int and after_rowid >= 0, 'invalid_trace_boundary')
    with sqlite3.connect(Path(simulation_dir) / 'reddit_simulation.db') as connection:
        rows = connection.execute(
            "SELECT rowid, user_id, info, created_at FROM trace WHERE rowid > ? AND user_id = ? AND action = ? ORDER BY rowid",
            (after_rowid, agent_id, 'interview')).fetchall()
    require(len(rows) == 1, 'native_interview_trace_not_unique')
    rowid, actor, raw, timestamp = rows[0]
    info = json.loads(raw)
    require(type(info) is dict and type(info.get('prompt')) is str and info['prompt'] == prompt
            and type(info.get('response')) is str and type(actor) is int and actor == agent_id,
            'native_interview_trace_prompt_mismatch')
    return {'agent_id': actor, 'response': info['response'], 'timestamp': timestamp,
            'trace_rowid': rowid, 'native_prompt_sha256': text_hash(info['prompt'])}


class InterviewScope:
    """Durable, single-dispatch receipt owned by one native interview task."""
    def __init__(self, simulation_dir, agent_id, prompt, binding):
        self.binding = validate_binding(simulation_dir, agent_id, prompt, binding)
        self.contract = self.binding['contract']
        self.started = time.monotonic()
        directory = Path(simulation_dir) / 'actor_contract_receipts'
        directory.mkdir(mode=0o700, exist_ok=True)
        self.path = directory / (self.binding['request_id'] + '.json')
        claims = Path(simulation_dir) / 'actor_contract_claims'
        claims.mkdir(mode=0o700, exist_ok=True)
        # Claim the logical key independently of actor/prompt/schema. Changing
        # request data must never manufacture a fresh dispatch for a spent key.
        claim = claims / (self.binding['request_key'] + '.json')
        try:
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ContractError('native_contract_request_already_exists') from None
        with os.fdopen(fd, 'w') as handle:
            json.dump({'request_key': self.binding['request_key'], 'request_id': self.binding['request_id']}, handle)
            handle.flush(); os.fsync(handle.fileno())
        self.receipt = {'schema_version': 1, 'binding': self.binding, 'status': 'received',
            'max_physical_requests': 1, 'physical_requests_dispatched': 0,
            'reserved_output_tokens': 0, 'input_tokens': None, 'output_tokens': None, 'total_tokens': None,
            'accounting_complete': False, 'estimated_cost_usd': None, 'cost_status': 'unknown',
            'provider_status': None, 'output_sha256': None, 'output_schema_valid': None,
            'provider_input_sha256': None, 'provider_request_sha256': None}
        # The deterministic identity is consumed once, including uncertainty.
        # Neither an HTTP retry nor an orphaned native task may replay it.
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ContractError('native_contract_request_already_exists') from None
        with os.fdopen(fd, 'w') as handle:
            json.dump(self.receipt, handle, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())

    def persist(self):
        self.receipt['elapsed_seconds'] = time.monotonic() - self.started
        temporary = self.path.with_suffix('.tmp')
        with open(temporary, 'w', encoding='utf-8') as handle:
            os.chmod(temporary, 0o600)
            json.dump(self.receipt, handle, sort_keys=True, allow_nan=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def before_dispatch(self, request, *, provider=None):
        require(self.receipt['physical_requests_dispatched'] == 0, 'actor_physical_request_limit')
        expected = configured_provider_contract()
        require(provider == expected, 'actor_provider_contract_mismatch')
        require(self.binding['support_sha256'] == digest(capabilities()), 'actor_provider_support_changed')
        if expected is not None:
            validate_provider_contract(provider)
            require(request.get('model') == expected['model'] and request.get('store') is False
                    and request.get('stream') is False
                    and request.get('extra_body') == {'chat_template_kwargs': {'enable_thinking': False}}
                    and request['extra_body']['chat_template_kwargs']['enable_thinking'] is False,
                    'actor_provider_request_policy_mismatch')
            role = self.contract['role']
            expected_format = {'format': {'type': 'json_schema', 'name': 'actor_' + role + '_v1',
                'strict': True, 'schema': generation_schema(role, expected)}}
            require(digest(request.get('text')) == digest(expected_format),
                    'actor_provider_generation_schema_mismatch')
        remaining = self.contract['timeout_seconds'] - (time.monotonic() - self.started)
        require(remaining > 0, 'actor_request_deadline')
        self.receipt.update(status='dispatched', physical_requests_dispatched=1,
            reserved_output_tokens=self.contract['max_output_tokens'], provider_input_sha256=digest(request['input']),
            provider_request_sha256=digest(request))
        if expected is not None:
            self.receipt['provider_contract'] = deepcopy(provider)
            self.receipt['generation_schema_contract'] = generation_contract(self.contract['role'], provider)
        self.persist()
        return remaining

    def provider_returned(self, response, text=None):
        usage = getattr(response, 'usage', None)
        values = {key: getattr(usage, key, None) for key in ('input_tokens', 'output_tokens', 'total_tokens')}
        observed = {key: value if type(value) is int and value >= 0 else None for key, value in values.items()}
        known = all(value is not None for value in observed.values())
        known = known and observed['input_tokens'] + observed['output_tokens'] == observed['total_tokens']
        raw_status = getattr(response, 'status', None)
        status = raw_status if raw_status in ('completed', 'incomplete', 'failed', 'cancelled', 'queued', 'in_progress') else 'unknown'
        self.receipt.update(status='provider_returned', provider_status=status,
            **observed, accounting_complete=known,
            accounting_issue=None if known else 'missing_invalid_or_inconsistent_usage')
        if type(text) is str:
            self.receipt.update(output_sha256=text_hash(text), output_schema_valid=shape_valid(text, self.contract['role']))
        if known:
            self.receipt['reserved_output_tokens'] = 0
        self.persist()

    def failed(self, exception):
        self.receipt['status'] = 'failed'
        self.receipt.setdefault('error_class', type(exception).__name__)
        self.receipt['boundary_error_class'] = type(exception).__name__
        self.persist()

    def finish(self, native_result):
        require(type(native_result.get('agent_id')) is int and native_result['agent_id'] == self.binding['agent_id']
                and native_result.get('native_prompt_sha256') == self.binding['native_prompt_sha256']
                and type(native_result.get('trace_rowid')) is int and native_result['trace_rowid'] > 0,
                'native_trace_binding_mismatch')
        require(self.receipt['physical_requests_dispatched'] == 1
                and self.receipt['provider_status'] == 'completed' and type(native_result.get('response')) is str
                and self.receipt['output_sha256'] == text_hash(native_result['response']), 'native_output_receipt_mismatch')
        # Completed is transport completion, not schema/business acceptance.
        # Unknown accounting or a deadline breach must block client acceptance.
        self.receipt.update(status='completed', native_result_sha256=digest(native_result),
            deadline_valid=time.monotonic() - self.started <= self.contract['timeout_seconds'],
            output_budget_valid=self.receipt['output_tokens'] is not None
                and self.receipt['output_tokens'] <= self.contract['max_output_tokens'])
        self.persist()
        return deepcopy(self.receipt)


@contextmanager
def interview_scope(simulation_dir, agent_id, prompt, binding):
    require(CURRENT.get() is None, 'nested_actor_contract_scope')
    scope = InterviewScope(simulation_dir, agent_id, prompt, binding)
    token = CURRENT.set(scope)
    try:
        yield scope
    except BaseException as exc:
        scope.failed(exc)
        raise
    finally:
        CURRENT.reset(token)
