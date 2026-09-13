"""Immutable host-only signal for a profiled Hermes physical transport stop.

The full safe meter is durable before native hard cancellation. Costs are the
physical prefix at first failure; reservations and independent invalid usage
dimensions are not complete measured usage. No prompt, output, HTTP body,
credential, guest-controlled path or free-form error is accepted here.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

from .budget import availability_classification
from .provider import validate_contract

FILENAME = 'PROVIDER_FAILURE.json'
KIND = 'profiled_hermes_provider_failure'
SCOPE = 'physical_transport_prefix_at_first_failure; reservations_are_not_measured_usage'
ENCODING = 'json_sort_keys_compact_ensure_ascii_true_utf8'
METER_KEYS = {'physical_model_calls', 'charged_tokens', 'reported_tokens', 'input_tokens',
    'output_tokens', 'total_tokens', 'accounting_complete', 'exhausted', 'stopped', 'blocked_calls',
    'terminal_failure', 'operations', 'disabled_auxiliary_calls', 'provider_contract'}
ROW_KEYS = {'dispatch', 'reserved_tokens', 'charged_tokens', 'accounting', 'status',
    'input_tokens', 'output_tokens', 'total_tokens', 'cache_read_tokens', 'reasoning_tokens',
    'output_cap', 'request_stream', 'provider_response_status', 'error_type', 'wall_seconds',
    'observed_usage', 'http_status', 'provider_contract', 'request_api_mode', 'request_model',
    'request_base_url', 'request_store', 'request_chat_template_kwargs'}
REASONS = {'dispatch_error', 'missing_or_invalid_usage', 'provider_budget_overrun',
           'provider_response_not_completed'}


def _require(condition):
    if not condition:
        raise ValueError('Invalid profiled provider failure receipt')


def _integer(value):
    return type(value) is int and value >= 0


def _class(value):
    return value is None or (type(value) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', value))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate(payload, *, worker_pid=None, computer_id=None):
    """Pure, strict metadata reader for parent watchdogs; never signals."""
    _require(type(payload) is dict and set(payload) == {'schema_version', 'kind', 'worker_pid',
        'computer_id', 'availability_classification', 'cost_scope', 'evaluation_budget',
        'evaluation_budget_sha256', 'hash_encoding'})
    _require(type(payload['schema_version']) is int and payload['schema_version'] == 1
             and payload['kind'] == KIND and payload['cost_scope'] == SCOPE and payload['hash_encoding'] == ENCODING)
    _require(_integer(payload['worker_pid']) and payload['worker_pid'] > 0)
    _require(type(payload['computer_id']) is str and re.fullmatch(r'lifespan-[0-9a-f]{16}', payload['computer_id']))
    _require(worker_pid is None or (type(worker_pid) is int and payload['worker_pid'] == worker_pid))
    _require(computer_id is None or payload['computer_id'] == computer_id)
    meter = payload['evaluation_budget']
    _require(type(meter) is dict and set(meter) == METER_KEYS)
    _require(payload['evaluation_budget_sha256'] == _digest(meter))
    policy = validate_contract(meter['provider_contract'])
    for key in ('stopped', 'exhausted', 'accounting_complete'):
        _require(type(meter[key]) is bool)
    _require(meter['stopped'] is True)
    for key in ('physical_model_calls', 'charged_tokens', 'reported_tokens', 'input_tokens',
                'output_tokens', 'total_tokens', 'blocked_calls'):
        _require(_integer(meter[key]))
    _require(type(meter['disabled_auxiliary_calls']) is list and all(value in
        ('iteration_summary', 'context_compression') for value in meter['disabled_auxiliary_calls']))
    rows = meter['operations']
    _require(type(rows) is list and len(rows) == meter['physical_model_calls'] and len(rows) > 0)
    for index, row in enumerate(rows, 1):
        _require(type(row) is dict and not set(row) - ROW_KEYS and type(row.get('dispatch')) is int and row['dispatch'] == index)
        _require(row.get('accounting') in ('reported', 'reservation') and row.get('status') in
            ('completed', 'dispatch_error', 'missing_or_invalid_usage', 'provider_budget_overrun'))
        for key in ('input_tokens', 'output_tokens', 'total_tokens', 'cache_read_tokens', 'reasoning_tokens'):
            _require(key in row and (row[key] is None or _integer(row[key])))
        for key in ('reserved_tokens', 'charged_tokens', 'output_cap'):
            _require(_integer(row.get(key)))
        _require(row.get('request_stream') is False and row.get('request_store') is False)
        _require(_digest(row.get('provider_contract')) == _digest(policy)
            and row.get('request_model') == policy['model'] and row.get('request_base_url') == policy['base_url']
            and row.get('request_api_mode') == 'responses'
            and _digest(row.get('request_chat_template_kwargs')) == _digest(policy['chat_template_kwargs']))
        _require(row.get('provider_response_status') in (None, 'completed', 'incomplete', 'failed', 'cancelled', 'queued', 'in_progress'))
        _require(_class(row.get('error_type')) and (row.get('http_status') is None or
            (type(row['http_status']) is int and 100 <= row['http_status'] <= 599)))
        _require(type(row.get('wall_seconds')) in (int, float) and math.isfinite(row['wall_seconds']) and row['wall_seconds'] >= 0)
        if 'observed_usage' in row:
            value = row['observed_usage']
            _require(type(value) is dict and set(value) == {'input_tokens', 'output_tokens', 'total_tokens'}
                     and all(item is None or _integer(item) for item in value.values()))
        if row['accounting'] == 'reported':
            _require(all(_integer(row[key]) for key in ('input_tokens', 'output_tokens', 'total_tokens'))
                and row['input_tokens'] + row['output_tokens'] == row['total_tokens'] == row['charged_tokens'])
        else:
            _require(all(row[key] is None for key in ('input_tokens', 'output_tokens', 'total_tokens'))
                     and row['charged_tokens'] == row['reserved_tokens'])
    for key in ('input_tokens', 'output_tokens', 'total_tokens', 'charged_tokens'):
        _require(meter[key] == sum(row[key] or 0 for row in rows))
    _require(meter['reported_tokens'] == meter['total_tokens'] and
             meter['accounting_complete'] == all(row['accounting'] == 'reported' for row in rows))
    failure = meter['terminal_failure']
    _require(type(failure) is dict and set(failure) == {'reason', 'dispatch', 'operation_status',
        'error_type', 'accounting', 'provider_response_status', 'http_status', 'availability_classification', 'observed_monotonic'})
    _require(failure['reason'] in REASONS and type(failure['dispatch']) is int and failure['dispatch'] == len(rows))
    _require(type(failure['observed_monotonic']) in (int, float) and math.isfinite(failure['observed_monotonic'])
             and failure['observed_monotonic'] >= 0)
    last = rows[-1]
    for field, name in (('operation_status', 'status'), ('error_type', 'error_type'), ('accounting', 'accounting'),
                         ('provider_response_status', 'provider_response_status'), ('http_status', 'http_status')):
        _require(failure[field] == last.get(name))
    expected = availability_classification(failure['error_type'], failure['http_status'])
    _require(payload['availability_classification'] == failure['availability_classification'] == expected)
    return deepcopy(payload)


def read_failure(root, *, worker_pid=None, computer_id=None):
    """Read the fixed host file without following a symlink; absent is pending."""
    root = Path(root)
    _require(root.is_absolute() and root.resolve() == root)
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        # O_NONBLOCK prevents a malformed FIFO from hanging the supervisor
        # before fstat can reject it. The directory fd pins the host root.
        try:
            fd = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
    finally:
        os.close(directory)
    with os.fdopen(fd, 'rb') as source:
        _require(stat.S_ISREG(os.fstat(source.fileno()).st_mode))
        data = source.read(4_000_001)
    _require(len(data) <= 4_000_000)
    return validate(json.loads(data, parse_constant=lambda value: _require(False)),
                    worker_pid=worker_pid, computer_id=computer_id)


def notifier(root, computer_id):
    """Bind the fixed host root before work; publish+fsync before cancellation."""
    root = Path(root)
    _require(root.is_absolute() and root.resolve() == root and not root.is_symlink() and root.is_dir())
    identity = root.stat()
    _require(not (root / FILENAME).exists() and not (root / FILENAME).is_symlink())

    def notify(report):
        payload = {'schema_version': 1, 'kind': KIND, 'worker_pid': os.getpid(), 'computer_id': computer_id,
            'availability_classification': report['terminal_failure']['availability_classification'],
            'cost_scope': SCOPE, 'evaluation_budget': report, 'evaluation_budget_sha256': _digest(report),
            'hash_encoding': ENCODING}
        validate(payload)
        data = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temp = '.' + FILENAME + '.' + uuid.uuid4().hex + '.tmp'
        made = False
        try:
            current = os.fstat(directory)
            _require((current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino))
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            made = True
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.link(temp, FILENAME, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.fsync(directory)
        finally:
            if made:
                os.unlink(temp, dir_fd=directory)
            os.close(directory)
    return notify
