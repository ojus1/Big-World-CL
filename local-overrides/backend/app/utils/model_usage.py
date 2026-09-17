"""Opt-in, simulation-bound receipts for otherwise unmetered Responses calls.

Contracted interviews retain their separate ledger. This records dispatch
attempts and provider-reported usage, not a billing estimate. Missing usage and
interrupted requests remain unknown. Prompts, outputs, keys and exception text
are never stored here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

VERSION = 'native-social-usage-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def count(value):
    return type(value) is int and value >= 0


def usage_directory(config, simulation_dir):
    if 'native_model_usage' not in config:
        return None
    if config['native_model_usage'] != VERSION:
        raise ValueError('Unknown native model usage version')
    return simulation_dir


class ModelUsage:
    def __init__(self, simulation_dir, provider):
        from .actor_output_contract import validate_provider_contract
        self.provider = validate_provider_contract(provider)
        self.simulation_dir = Path(simulation_dir).resolve()
        config = self.simulation_dir / 'simulation_config.json'
        config_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        self.root = self.simulation_dir / 'model_usage'
        # A new worker never silently appends to evidence from an earlier run.
        self.root.mkdir(mode=0o700)
        (self.root / 'calls').mkdir(mode=0o700)
        self.manifest = {'schema_version': 1, 'version': VERSION,
            'simulation_id': self.simulation_dir.name,
            'simulation_config_sha256': config_hash,
            'provider_contract': self.provider,
            'module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'bridge_sha256': hashlib.sha256(Path(__file__).with_name('camel_responses.py').read_bytes()).hexdigest(),
            'scope': 'uncontracted_responses_only; interviews use their existing ledger',
            'sdk_max_retries': 0}
        save(self.root / 'MANIFEST.json', self.manifest)

    @contextmanager
    def call(self, request, provider):
        if provider != self.provider:
            raise ValueError('Social-usage provider identity changed')
        receipt = Call(self, request)
        try:
            yield receipt
        except BaseException as exc:
            receipt.finish('failed', type(exc).__name__)
            raise
        else:
            receipt.finish('completed', None)


class Call:
    def __init__(self, recorder, request):
        self.started = time.monotonic()
        self.path = recorder.root / 'calls' / (uuid.uuid4().hex + '.json')
        self.value = {'schema_version': 1, 'call_id': self.path.stem,
            'manifest_sha256': digest(recorder.manifest),
            'started_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'dispatched', 'provider_dispatch_attempts': 1,
            'request_sha256': digest(request), 'input_sha256': digest(request['input']),
            'max_output_tokens': request['max_output_tokens'],
            'provider_status': None, 'returned_model': None,
            'input_tokens': None, 'output_tokens': None, 'total_tokens': None,
            'accounting_complete': False, 'latency_ms': None, 'error_type': None}
        save(self.path, self.value)  # Persist unknown consumption before dispatch.

    def returned(self, response):
        usage = getattr(response, 'usage', None)
        values = [getattr(usage, key, None) for key in ('input_tokens', 'output_tokens', 'total_tokens')]
        valid = all(count(value) for value in values) and values[0] + values[1] == values[2]
        self.value.update(provider_status=getattr(response, 'status', None),
                          returned_model=getattr(response, 'model', None),
                          accounting_complete=valid)
        if valid:
            self.value.update(zip(('input_tokens', 'output_tokens', 'total_tokens'), values))
        # Output conversion can fail after the provider has consumed tokens.
        save(self.path, self.value)

    def finish(self, status, error_type):
        self.value.update(status=status, error_type=error_type,
                          latency_ms=round((time.monotonic() - self.started) * 1000))
        save(self.path, self.value)


def summarize(root, *, provider=None, simulation_id=None, config_sha256=None):
    """Read an existing ledger; absence is never interpreted as zero usage."""
    root = Path(root)
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    if (manifest['schema_version'] != 1 or manifest['version'] != VERSION or manifest['sdk_max_retries'] != 0 or
            manifest['module_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or
            manifest['bridge_sha256'] != hashlib.sha256(Path(__file__).with_name('camel_responses.py').read_bytes()).hexdigest() or
            (provider is not None and manifest['provider_contract'] != provider) or
            (simulation_id is not None and manifest['simulation_id'] != simulation_id) or
            (config_sha256 is not None and manifest['simulation_config_sha256'] != config_sha256)):
        raise ValueError('Social-usage manifest identity mismatch')
    rows = []
    for path in sorted((root / 'calls').glob('*.json')):
        row = json.loads(path.read_text())
        if (row['schema_version'] != 1 or row['call_id'] != path.stem or row['manifest_sha256'] != digest(manifest) or
                type(row['provider_dispatch_attempts']) is not int or row['provider_dispatch_attempts'] != 1 or
                row['status'] not in ('dispatched', 'completed', 'failed')):
            raise ValueError('Social-usage receipt identity mismatch')
        values = [row[key] for key in ('input_tokens', 'output_tokens', 'total_tokens')]
        valid = all(count(value) for value in values) and values[0] + values[1] == values[2]
        if type(row['accounting_complete']) is not bool or row['accounting_complete'] != valid:
            raise ValueError('Social-usage receipt accounting mismatch')
        rows.append(row)
    return {'version': VERSION, 'manifest_sha256': digest(manifest),
        'provider_dispatch_attempts': len(rows),
        'reported_tokens': sum(row['total_tokens'] for row in rows if row['accounting_complete']),
        'requests_with_unknown_usage': sum(not row['accounting_complete'] for row in rows),
        'unfinished_requests': sum(row['status'] == 'dispatched' for row in rows),
        'failed_requests': sum(row['status'] == 'failed' for row in rows),
        'observed_accounting_complete': all(row['accounting_complete'] and row['status'] != 'dispatched' for row in rows),
        'scope': 'observed_uncontracted_responses; excludes interviews and other bootstrap providers'}
