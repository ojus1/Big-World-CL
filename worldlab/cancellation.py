"""One atomic study-wide stop request; already admitted waves retain their receipts."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
import time


class StudyCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Cancellation:
    root: Path
    context: dict = field(default_factory=dict)

    @property
    def path(self): return Path(self.root) / 'STOP_REQUESTED.json'

    def at(self, **context):
        return Cancellation(self.root, {**self.context, **context})

    def check(self):
        if self.path.exists():
            raise StudyCancelled('A study peer failed; no new work is admitted')

    def request(self, error_type):
        Path(self.root).mkdir(parents=True, exist_ok=True)
        record = {'version': 1, 'policy': 'stop_after_current_wave', 'observed_unix': time.time(),
                  'reporting_pid': os.getpid(), 'context': self.context, 'error_type': error_type,
                  'action': 'Stop new arms, decisions, work waves and learning waves; join and record admitted operations.'}
        # Publish a complete first-cause record atomically, including when several
        # processes discover failures simultaneously. Never read model workspace paths.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.root, prefix='.stop-request-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(record, stream, sort_keys=True); stream.write('\n'); stream.flush()
                os.fsync(stream.fileno())
            try: os.link(temporary, self.path)
            except FileExistsError: pass
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)

    def observe(self, future, allowed):
        """Notice a failed future promptly while collection stays in planned order."""
        try:
            result = future.result()
            if result.get('status') not in allowed:
                self.request('IncompleteOperation')
        except Exception as exc:
            self.request(type(exc).__name__)


def check(cancellation):
    if cancellation is not None: cancellation.check()
