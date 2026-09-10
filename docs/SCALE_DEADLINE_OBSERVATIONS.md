# Learning deadline observations

This additive, read-only diagnostic was introduced during scale-v1 execution,
before any learning epoch had started. It does not change frozen execution,
the CLI-alias correction, the original audit, reported scores, or inclusion
rules. It makes no model calls and writes no campaign artifacts.

```bash
python3 scripts/scale_deadline_observations.py lifespan/artifacts/scale-v1
python3 -m unittest discover -s tests -p 'test_scale_deadline_observations.py' -v
```

The output retains each planned world, safe employee/day identifiers, operation
counts, pending learning records, and hashes of the exact input snapshots.
Requests, answers, skills, persona text, raw trace text and absolute paths are
not exported. `ok` means the diagnostic could read its inputs; it is not a
scientific validity or model-quality verdict. The original strict audit remains
authoritative and unchanged. Recorded provider costs are not independently
authenticated by this diagnostic.

## Why callback time and physical caps are separate

The frozen learning ledger measures the entire replay callback. This includes
private-case restoration, local setup, native execution, session serialization,
worker shutdown, trajectory filtering and progress persistence. In contrast,
the target session's `elapsed_seconds` is captured before its final session-file
write and `Computer.close()`. Worker shutdown alone can wait ten seconds before
termination and another five before killing an unresponsive process. The
difference between callback wall time and session latency is not a direct
measurement of cleanup alone.

Optimizer receipt latency includes context preparation and transport through
response receipt. Its enclosing callback wall time also includes response
processing and progress persistence. A callback timeout therefore does not, by
itself, prove that inference continued past a deadline. No physical inference
duration is inferred: that output stays null.

The diagnostic reports these dimensions separately:

- Reported physical call and token counts exceeding their respective operation
  limits. One dimension remains observable if the other is malformed.
- Callback wall time exceeding `limits.timeout_seconds`.
- Receipt latency exceeding that same limit in milliseconds.
- Timing overruns with both call/token dimensions known and within their caps.
  This means no recorded excess calls/tokens, not proof of cleanup-only delay.
- Operations explicitly marked `budget_exceeded` after dispatch.
- Dispatched target operations, scored replays, artifact records and the declared
  replay counter disagreeing.
- Fully known versus unknown cost records, malformed records and unknown timing.
  Known call/token subtotals retain individually known values even when another
  field is missing. They are partial subtotals, not complete campaign costs.

Uncheckpointed progress records remain separately visible. Their callback timing
ledger may not yet exist, so missing timing is unavailable rather than zero.

## The reproduced asymmetry

In the frozen `lifespan/evaluation/skillopt.py`, `_Ledger.invoke()` stores known
costs before checking callback duration, receipt latency and physical caps. A
post-dispatch overrun records `status="budget_exceeded"`, leaves complete known
costs intact and raises `BudgetExhausted`. The learner returns an unadopted
`budget_exhausted` update. `_learn()` checkpoints that update and continues when
its accounting is complete.

For a target callback, the scored replay is appended only after the ledger
returns successfully. Thus a post-dispatch overrun can leave one more dispatched
target than scored replay. The frozen raw and scale audits reject that missing
replay evidence. For an optimizer callback, all preceding target scores remain
present. The current frozen checks validate the operation's tokens/calls but do
not reject its timing-overrun status; this branch can pass those checks. Neither
branch adopts the candidate. This is a budget-stop/audit asymmetry, not evidence
of a model-quality failure or a reason to relax any cap.

The offline tests execute the actual pinned SkillOpt consolidation with T=2,
V=2, K=2 and synthetic callbacks. Setting a returned receipt latency to 2,000 ms
under a one-second limit, while retaining one call and a small known token
count, reproduces one target dispatch with zero scored replays, or eight target
dispatches with eight scored replays followed by the optimizer overrun. A
separate one-target-call budget exhausts before the second dispatch and retains
one fully scored, within-cap target. These are implementation fixtures, not
native model evidence.

`pre_dispatch_stop_consistent` is used only for a `budget_exhausted` update with
a fully known, completed, within-cap prefix and matching replay counters.
Post-dispatch overruns and unresolved/malformed evidence receive distinct
labels. Future evidence must retain the original operation records and original
audit result; any additional scientific exclusion rule requires an explicitly
versioned decision, not silent reinterpretation by this diagnostic.
