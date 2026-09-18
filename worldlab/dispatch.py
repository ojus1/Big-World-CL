"""Bounded work dispatch with an employee and day barrier.

All started attempts are joined and recorded, including peers of a failure.
Nothing is retried. Waves prevent an employee's next session overtaking its
previous one and avoid completion-speed-dependent dispatch order.
"""
from concurrent.futures import ThreadPoolExecutor
from .cancellation import check


def dispatch_day(slots, execute, record, journal, *, max_parallel=1, cancellation=None, continue_on_error=False):
    if type(max_parallel) is not int or not 1 <= max_parallel <= 64:
        raise ValueError('max_parallel_employees must be an integer from 1 to 64')
    pending = list(slots)
    with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix='worldlab') as pool:
        while pending:
            check(cancellation)
            wave, employees = [], set()
            for slot in pending:
                if slot['employee_id'] not in employees:
                    wave.append(slot); employees.add(slot['employee_id'])
                if len(wave) == max_parallel: break
            journal(wave)
            futures = [(slot, pool.submit(execute, slot)) for slot in wave]
            if cancellation is not None and not continue_on_error:
                for _, future in futures:
                    future.add_done_callback(lambda f: cancellation.observe(f, ('completed',)))
            errors = []
            # Result collection uses planned order, never score or runtime.
            for slot, future in futures:
                try:
                    result = future.result()
                    record(slot, result)
                    if result['status'] != 'completed' and not continue_on_error:
                        errors.append(RuntimeError('Unscored or invalid work attempt; preserved for reconciliation'))
                except Exception as exc:
                    if cancellation is not None and not continue_on_error: cancellation.request(type(exc).__name__)
                    errors.append(exc)
            if errors:
                # Leave the entire wave journal, including reservations, intact.
                # Completed peer receipts reconcile the known part of its cost.
                raise errors[0]
            journal([])
            dispatched = {s['id'] for s in wave}
            pending = [s for s in pending if s['id'] not in dispatched]
