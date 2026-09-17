"""Freeze native task actions at their deadline, then settle accepted inference.

Settlement cannot admit another model call or resume the task sandbox. Its
separate bounded allowance is reported as elapsed time, never as free work.
"""
import json
import math
from pathlib import Path
import threading
import time


def save(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.pending')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    temporary.replace(path)


def clock_contract(seconds, admitted=None):
    admitted = time.monotonic() if admitted is None else admitted
    return {'version': 1, 'clock': 'same_host_monotonic', 'admitted_monotonic': admitted,
            'active_seconds': seconds, 'deadline_monotonic': admitted + seconds,
            'tool_cleanup_seconds': 10, 'settlement_seconds': min(600, seconds) + 15}


def validate_clock(clock, seconds):
    admitted = clock.get('admitted_monotonic')
    if (type(admitted) not in (int, float) or not math.isfinite(admitted) or admitted <= 0
            or clock != clock_contract(seconds, admitted)):
        raise ValueError('Native task clock differs from the declared deadline policy')


class TaskDeadline:
    def __init__(self, root, clock, meter, sandbox):
        self.root, self.clock, self.meter, self.sandbox = Path(root), clock, meter, sandbox
        self.error = None
        self.expired = False
        self.lock = threading.Lock()
        self.timer = threading.Timer(max(0., clock['deadline_monotonic'] - time.monotonic()), self.expire)
        self.timer.daemon = True

    def start(self):
        self.timer.start()

    def expire(self):
        with self.lock:
            if self.expired:
                return
            self.expired = True
            self._expire()

    def _expire(self):
        save(self.root / 'DEADLINE_INTENT.json', {'clock': self.clock, 'observed_monotonic': time.monotonic(),
            'sandbox_pid': self.sandbox.sandbox.process.pid,
            'action': 'close model admissions and terminate task sandbox; settle accepted inference'})
        try:
            self.meter.expire()
            self.sandbox.cleanup()
            save(self.root / 'DEADLINE_ACTION.json', {'completed_monotonic': time.monotonic(),
                'sandbox_pid': self.sandbox.sandbox.process.pid,
                'sandbox_returncode': self.sandbox.sandbox.process.poll(), 'error_type': None})
        except Exception as exc:
            self.error = type(exc).__name__
            save(self.root / 'DEADLINE_ACTION.json', {'completed_monotonic': time.monotonic(),
                'sandbox_pid': self.sandbox.sandbox.process.pid,
                'sandbox_returncode': self.sandbox.sandbox.process.poll(), 'error_type': self.error})

    def finish(self):
        self.timer.cancel()
        self.timer.join()
        # Dispatch can notice the deadline before the timer receives CPU time.
        # Finalization must not cancel the only pending sandbox stop in that race.
        if time.monotonic() >= self.clock['deadline_monotonic']:
            self.expire()
        if self.error:
            raise RuntimeError('Native task deadline cleanup failed: ' + self.error)


def checkpoint_costs(path, provider, clock, budget):
    """A checkpoint preserves admissions and bounds, never a task completion."""
    meter = json.loads(Path(path).read_bytes())
    rows = meter['operations']
    if (meter['provider_contract'] != provider or meter['deadline_monotonic'] != clock['deadline_monotonic']
            or meter['physical_model_calls'] != len(rows) or len(rows) > budget.model_calls
            or meter['charged_tokens'] != sum(r['charged_tokens'] for r in rows)
            or meter['reported_tokens'] != sum(r['total_tokens'] or 0 for r in rows)):
        raise ValueError('Durable dispatch checkpoint differs from this attempt')
    for index, row in enumerate(rows, 1):
        if (row['dispatch'] != index or type(row['charged_tokens']) is not int or row['charged_tokens'] < 0
                or not 0 < row['output_cap'] <= budget.output_tokens
                or not clock['admitted_monotonic'] <= row['admitted_monotonic'] < clock['deadline_monotonic']):
            raise ValueError('Invalid durable dispatch reservation')
        if row['accounting'] == 'reported':
            if row['charged_tokens'] != row['total_tokens'] or row['input_tokens'] + row['output_tokens'] != row['total_tokens']:
                raise ValueError('Invalid reported usage in durable checkpoint')
        elif row['accounting'] == 'reservation':
            if row['charged_tokens'] != row['reserved_tokens'] or row['total_tokens'] is not None:
                raise ValueError('Unknown usage lost its durable reservation')
        else:
            raise ValueError('Unrecognized durable accounting basis')
    return {'physical_model_calls': len(rows), 'charged_tokens': meter['charged_tokens'],
            'reported_tokens': meter['reported_tokens'], 'accounting_complete': False,
            'checkpoint_accounting_complete': meter['accounting_complete'],
            'reservation_reason': 'Final native execution missing; retained durable dispatch reservations'}


def audit_deadline(root, clock, native):
    root = Path(root)
    saved = json.loads((root / 'METER_CHECKPOINT.json').read_bytes())
    if saved != native['evaluation_budget'] or saved.get('deadline_monotonic') != clock['deadline_monotonic']:
        raise ValueError('Durable native meter differs from final accounting or deadline')
    if any(not clock['admitted_monotonic'] <= row['admitted_monotonic'] < clock['deadline_monotonic']
           for row in saved['operations']):
        raise ValueError('Model request was admitted outside the task work window')
    reached = root / 'DEADLINE_INTENT.json'
    if reached.exists():
        intent = json.loads(reached.read_bytes())
        action = json.loads((root / 'DEADLINE_ACTION.json').read_bytes())
        ready = json.loads((root / 'READY.json').read_bytes())
        times = [intent['observed_monotonic'], action['completed_monotonic']]
        if (intent['clock'] != clock or intent['observed_monotonic'] < clock['deadline_monotonic']
                or any(type(t) not in (int, float) or not math.isfinite(t) for t in times)
                or action['completed_monotonic'] < intent['observed_monotonic']
                or action['completed_monotonic'] > clock['deadline_monotonic'] + clock['tool_cleanup_seconds']
                or intent['sandbox_pid'] != ready['sandbox_pid']
                or action['sandbox_pid'] != intent['sandbox_pid'] or action['sandbox_returncode'] is None
                or action['error_type'] is not None or not saved['exhausted']
                or saved['exhaustion_reason'] != 'task_deadline'):
            raise ValueError('Task deadline did not freeze native execution')
    elif saved.get('exhaustion_reason') == 'task_deadline':
        raise ValueError('Native deadline exhaustion lacks its task cleanup receipt')
