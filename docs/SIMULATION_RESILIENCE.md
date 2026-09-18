# Continuing simulations after operational errors

Newly prepared studies default to `failure_policy: record_and_continue`.
An execution, grade or employee-decision error is retained as an operational
failure while later days, employees and independent arms continue. Existing
frozen studies keep their original policy. `stop_after_current_wave` remains
available explicitly, and a manual stop request is honored under continuation.

A failed work attempt has no fabricated score or semantic feedback. Its actual
usage is retained where available, and unknown dimensions keep their declared
reservation. The workplace releases the slot and permits another attempt only
through its ordinary capacity, delay, deadline and maximum-attempt rules.
An employee-decision failure consumes that opportunity and defers work, without
inserting a synthetic employee answer. A failed learning epoch keeps the
previous skill, records its costs and permits the next scheduled epoch.

Work, native inference settlement and grading have distinct time allowances.
Hermes stops new task actions at the active work deadline and can wait a bounded
period for an already admitted model call. That wait no longer consumes the
300-second grading allowance. For 1,800 seconds of active work, a full replay
now needs 2,725 seconds: work, up to 615 seconds settlement, 10 seconds worker
termination and 300 seconds grading. Preparation rejects smaller replay budgets;
full-epoch reservations must also cover the corrected replay duration.

Failures remain in ATTEMPT/UPDATE receipts, incident records and causal workplace
commands. Reports separately count ungraded work, failed decisions, failed
learning updates, budget exhaustion and unknown usage. Operational completion
does not assert complete grading or measured accounting. All planned probes
remain in denominators; ungraded attempts do not become learner scores.

Audits check failure provenance, unchanged skills, original task bindings,
retained native receipts, known costs and unknown reservations. They distinguish
a recorded failure from successful native execution. Corrupt evidence is still
reported as an audit failure. If an arm cannot maintain its state or start its
employee environment, its incomplete record is retained and other arms proceed;
missing pairs are explicitly reported rather than counted as completed.

No automatic model retry was added. Existing bounded format repair remains
unchanged. Concurrency is still capped at 64 and no inference-server settings
are changed by this policy.
