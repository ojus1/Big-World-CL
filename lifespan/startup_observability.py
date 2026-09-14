"""Optional, local startup observations; never a usage or cleanup receipt."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

VERSION = 'startup-observation-v1'
STAGES = ('worker_entered', 'imports_before', 'imports_after', 'registry_before',
          'registry_after', 'sandbox_before', 'sandbox_after', 'agent_before',
          'agent_after', 'budget_transport_before', 'budget_transport_after',
          'probe_before', 'probe_after', 'ready_write_attempt', 'ready_write_returned',
          'popen_returned', 'ready_received', 'ready_observed_after_deadline', 'startup_exception',
          'run_request_write_attempt', 'run_request_write_returned')


def enabled(config):
    value = (config.get('hermes_startup_observability', False) if isinstance(config, dict)
             else getattr(config, 'hermes_startup_observability', False))
    if type(value) is not bool:
        raise ValueError('hermes_startup_observability must be boolean')
    return value


def executor_options(config):
    return {'hermes_startup_observability': True} if enabled(config) else {}


def provenance():
    root = Path(__file__).resolve().parent
    return {'version': VERSION, 'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ('startup_observability.py', 'computers.py', 'hermes_worker.py')},
        'scope': 'startup_and_parent_pipe_observations_not_provider_usage_or_cleanup',
        'journal_fsync': False}


def manifest_fields(config):
    return {'hermes_startup_observability': True, 'startup_observation_provenance': provenance()} if enabled(config) else {}


def error_class(exc):
    name = type(exc).__name__
    return name if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', name) else 'Exception'


def process_identity(pid):
    """Linux identity snapshot. Failure is evidence unavailable, not process gone."""
    try:
        root = Path('/proc') / str(pid)
        before = (root / 'stat').read_text()
        fields = before.rsplit(')', 1)[1].split()
        uid = next(line.split()[1:] for line in (root / 'status').read_text().splitlines() if line.startswith('Uid:'))
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        after = (root / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[19] != after[19]:
            raise RuntimeError('Process changed during identity observation')
        return {'pid': pid, 'start_ticks': int(fields[19]), 'uid': int(uid[0]),
                'boot_id': boot, 'available': True, 'error_type': None}
    except (OSError, ValueError, IndexError, StopIteration, RuntimeError) as exc:
        return {'pid': pid, 'start_ticks': None, 'uid': None, 'boot_id': None,
                'available': False, 'error_type': error_class(exc)}


class Observer:
    """Best-effort fixed-schema journal; errors cannot change native execution."""
    def __init__(self, root, role, *, expected_attempt=None):
        self.root = Path(root) / 'startup'
        self.role = role
        self.attempt = None
        self.errors = []
        self.sequence = 0
        self.writable = False
        self.last_stage = None
        self.identity = process_identity(os.getpid())
        try:
            if role == 'parent':
                self.attempt = uuid.uuid4().hex
                self.root.mkdir(mode=0o700)
                manifest = {'version': VERSION, 'attempt_id': self.attempt, **provenance()}
                with (self.root / 'manifest.json').open('x') as stream:
                    json.dump(manifest, stream, sort_keys=True); stream.write('\n'); stream.flush()
            elif role == 'worker':
                manifest = json.loads((self.root / 'manifest.json').read_bytes())
                if (manifest.get('version') != VERSION
                        or not re.fullmatch('[0-9a-f]{32}', manifest.get('attempt_id', ''))
                        or expected_attempt != manifest.get('attempt_id')):
                    raise ValueError('Invalid startup observation manifest')
                self.attempt = manifest['attempt_id']
            else:
                raise ValueError('Invalid observer role')
            self.writable = True
        except (OSError, ValueError, TypeError) as exc:
            self.errors.append(error_class(exc))
            self.attempt = None

    def event(self, stage, *, pid=None, exception=None):
        if stage not in STAGES:
            raise ValueError('Unknown startup observation stage')
        previous_stage = self.last_stage
        self.last_stage = stage
        record = {'version': VERSION, 'attempt_id': self.attempt, 'role': self.role,
            'sequence': self.sequence, 'stage': stage, 'previous_stage': previous_stage, 'monotonic_seconds': time.monotonic(),
            'utc': datetime.now(timezone.utc).isoformat(), 'observer_identity': self.identity,
            'worker_identity': process_identity(pid) if pid is not None else (self.identity if self.role == 'worker' else None),
            'error_type': error_class(exception) if exception is not None else None,
            'observation_errors': list(self.errors)}
        self.sequence += 1
        if not self.writable:
            return
        try:
            with (self.root / (self.role + '.jsonl')).open('a') as stream:
                stream.write(json.dumps(record, sort_keys=True) + '\n'); stream.flush()
        except (OSError, ValueError) as exc:
            self.errors.append(error_class(exc))

    def summary(self):
        return {'version': VERSION, 'attempt_id': self.attempt, 'last_stage': self.last_stage,
                'observation_errors': list(self.errors), 'usage_known': False, 'cleanup_known': False}
