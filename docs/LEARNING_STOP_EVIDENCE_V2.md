# Learning stop evidence, version 2

This contract applies to future runs that declare `learning_evidence_version: 2`
in their manifest and updates. It changes accounting and incomplete-update
reconciliation, not pinned SkillOpt reflection, edit application or gates.
It does not reinterpret scale-v1 or authorize replaying an interrupted run.

Every incurred target/optimizer operation remains in the cost ledger. A target
score enters `replay_evidence` only after the callback passes receipt and budget
checks and its score reaches upstream. When a returned target exceeds its timing
allowance, the update records that physical attempt separately in
`unscored_replay_evidence`: task, phase, sample, attempt index, executed skill hash
and `score_consumed: false`. This record contains no hard/soft score or response.
The native session, submitted bytes, source capsule, limits and receipts remain
bound by raw-file hashes in `replay_artifacts`. Independent grading of those bytes
checks artifact integrity; it does not retroactively supply a score to SkillOpt.

## Explicit stop stages

| `costs.stop_evidence.stage` | Meaning | Deployment |
|---|---|---|
| `pre_dispatch` | The next operation cannot fit the remaining call, token, replay or epoch-time budget | Retain incumbent |
| `post_dispatch` | A returned operation exceeds one or more declared call, token or timing limits | Retain incumbent |
| `post_consolidation` | The epoch clock expires during local consolidation, before the adoption decision | Retain incumbent |
| No stop | Upstream consolidation finishes and the adoption decision is within the epoch deadline | Apply the unchanged upstream decision |

Each incomplete optimization returns `accepted: false`, the original skill/hash
and `reject_incomplete`. Even an earlier tentative candidate-gate pass cannot
survive a final replay stop. Target attempt indices count targets; the terminal
operation index counts both targets and optimizer calls.

A fully known, unadopted **timing-only** terminal operation can be reconciled in
either the target or optimizer branch. It must be the last operation following a
completed prefix. A terminal target must have a completed native callback and
exactly one unscored identity. A terminal optimizer may report `completed` or the
provider adapter's explicit `budget_exhausted` timing status; failed or incomplete
transport statuses do not become valid stops. Optimizer status, latency, usage and
output cap are checked against its transport receipt.

Physical call/token violations remain invalid, including mixed timing/physical
violations. The runner persists their costs and stops the run; the auditor rejects
them. Unknown usage also remains invalid. Each independently returned nonnegative
integer is retained in `reported_usage`; unknown dimensions retain their full
reservation. Thus a missing token receipt cannot erase a known call count, nor can
a missing tool count erase known model costs. Missing/malformed timing with exact
costs is still a failed receipt and cannot permit adoption.

## Timing scopes and independent checks

Callback wall time includes case restoration, local setup, native execution,
serialization, cleanup, trajectory filtering and progress persistence. Target
`elapsed_seconds` ends before session-file writing and worker cleanup; the native
record explicitly names that scope. Neither value measures physical inference
time. Optimizer receipt latency similarly lies within its enclosing callback.

The V2 auditor reconstructs the remaining call/token allowance at each dispatch,
checks receipt latency lies inside callback wall time, checks successive callback
clock ranges and total epoch time, and checks the adoption-decision clock.
One microsecond of tolerance covers clock arithmetic roundoff, not deadline grace.
The original strict operation/deadline comparisons have no added grace period.
No model dispatch deadline is extended. The decision clock is measured immediately
before recording the upstream adoption decision; subsequent bookkeeping and file
deployment are not reported as model execution or as extra training opportunity.

Raw update auditing, scale progress auditing and the historical-transfer wrapper
share the V2 operation reconciliation contract. They retain their separate source,
native receipt, rubric, phase, split, skill-chain and budget checks. A missing or
extra native session, unscored identity, scored replay or capsule binding fails.
An unscored terminal operation never enters reflection context or gate means.

## Historical behavior and verification

Missing-version/V1 records use the original audit behavior. In particular, V1
rejects a terminal target without scored replay evidence, while its optimizer
timing-status branch retains the historical behavior. New manifests bind the
declared evidence version and V2 producer-source hashes, so removing both manifest
and update markers cannot select legacy rules. Historical source hashes must be
audited in their matching checkout.

The historical `audit_scale_cli.py` campaign, receipt and source constants remain
unchanged. It deliberately refuses the future auditor revision. Its two tests of
the exact historical AST skip explicitly when those supported bytes are absent;
generic launch/tamper tests and the future-revision-refusal test still run.

Offline tests exercise actual pinned consolidation, including final validation
after a tentative candidate pass, and use fabricated filesystem/provider receipts
to test independent audit binding. They cover both timing branches, pre-dispatch
and post-consolidation stops, clock tampering, physical overruns, missing costs,
extra/missing scores, source/session tampering, and legacy behavior. These fixtures
are implementation evidence, not native learning results.

```bash
python3 -m unittest lifespan.tests.test_learning_stop_v2 tests.test_learning_audit_v2 -v
```
