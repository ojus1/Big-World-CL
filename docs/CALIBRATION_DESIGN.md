# Fixed-skill native replay calibration

The next experiment checks whether the native Hermes harness can reliably solve
the existing work cases with one fixed, competent seed skill. It measures repeat
variation and failure modes before spending more runs on learning comparisons.
It does not train or select a new skill, estimate a learning effect, or turn the
pilot's dependent employee sessions into independent benchmark examples.

## Frozen historical source and outcome-blind selection

The source is the completed `evaluation-pilot-v1/no_learning` run. Its eight-day
work horizon, historical scenario, personas, source versions, task capsules, and
native receipts remain immutable. The source must be `no_learning`, `dev`, and
`skill_transfer`, with a completed execution audit and matching manifest/report
provenance. Final test-split cases are excluded from calibration.

`scripts/calibration_bank.py` selects the first released source session by
`(day, session_id)` within each employee/regime cell. It reads identity, scope, and
time to make that selection. It does not filter or reorder by success, score,
budget exhaustion, or whether the original agent loaded its skill. Original
outcomes are attached only after the selection is complete. A missing or invalid
selected capsule fails validation; it is never replaced with a later success.

The desired matrix is six employees across base, changed, exception, and reversal
regimes: 24 cells. The actual frozen source covers **22 cells**, yielding **44
replay slots** with two repeats per cell. The missing cells are firm-0 onboarding
and renewal during the exception regime; they remain visibly uncovered.

There are only **20 underlying obligations** in those 22 selected cells. The
firm-0 incident obligation `firm-0-order-0011` spans changed and exception
sessions, while firm-1 incident `firm-1-order-0008` spans exception and reversal.
Different historical capsules are meaningful changing-context exposures, but
they do not make the underlying tasks independent. The bank reports these groups
explicitly. Four selected source sessions failed originally; this fact is a
post-selection description, not a reason to include or replace any case.

The selection rule is outcome-blind within the chosen source. The calibration
study itself follows inspection of the pilot and is a development experiment;
it is not an untouched final evaluation set.

## Manifest and interface

The module makes no model or network calls. It provides:

```python
bank = build_bank(source_run, repeats=2)
slots = expected_slots(bank)
summary = aggregate_repeats(bank, receipts)
```

For fabricated offline tests, `select_bank(checkpoint, source_manifest,
capsules_by_session, source_report, repeats=2)` is pure. The file-backed builder
uses raw SHA256 hashes for the source checkpoint, source manifest, source report,
selector implementation, and selected capsule files. A canonical case hash also
binds every selected task, including its evaluator-only truth. Pure-function test
fixtures label canonical JSON hashes separately from raw file hashes.

Each selection records its stable `selection_id` (the original session ID),
employee, regime, historical day, underlying task ID, relative source capsule
path, and hashes. It does **not** include the request, workspace file contents,
whole world state, or expected answer. The public summary can expose selection
identifiers and post-selection source outcomes without exposing private task
truth.

`expected_slots` returns one record per preregistered repeat:

```json
{
  "selection_id": "the-original-source-session-id",
  "repeat_index": 0,
  "rollout_id": "the-original-source-session-id-r0"
}
```

Repeat indices are zero-based. Duplicate selection IDs, duplicate employee/regime
cells, or inconsistent declared coverage/rollout counts are rejected.

## Native execution contract

The calibration runner owns actual model calls and must preregister the exact
seed skill/hash, executor and model versions, provider/settings, tool limits,
maximum output tokens, per-rollout token reservation, timeout, execution order,
and global budget. Both repeats of every selected capsule receive the identical
skill and work budgets. Each repeat starts in an independent fresh native profile
and filesystem reconstructed from the same historical capsule. Successful work
is checked with the frozen substantive grader and business submission rules.

The phase is capped at 48 possible rollout slots, 768 physical model calls,
12 million reserved tokens, and one hour. The actual 22-cell bank schedules 44
slots, not fabricated replacements for the two uncovered cells. There is no
performance-based early stopping. Infrastructure problems, exhausted global
budgets, or missing receipts must be recorded as incomplete accounting/coverage.
They must not disappear from the planned denominator.

The runner stores raw native sessions under
`replays/<selection_id>-r<repeat_index>/session.json`, with a separate receipt
containing its hash. The receipt passed to aggregation includes:

- Selection ID, repeat index, rollout ID, and a relative artifact reference.
- `status`: `completed`, `infrastructure_invalid`, or `infrastructure_error`.
- Strict success, substantive score, infrastructure validity, skill loading,
  budget exhaustion, usage receipts, elapsed time, and simulated operation cost.

A valid native behavioral failure still has status `completed`. Budget exhaustion
alone is not an infrastructure failure. An exception without a valid native
receipt uses `infrastructure_error`. Absolute or parent-traversing artifact
references, unknown slots, duplicate receipts, and inconsistent success/status
records are rejected before aggregation.

## Descriptive aggregation and missing evidence

Every expected repeat slot appears in the summary. Missing receipts,
infrastructure-invalid receipts, and infrastructure errors have separate counts.
Completed native receipts distinguish:

- Strict success: substantive work and trusted submission both succeeded.
- Substantive incomplete: the substantive score is below one.
- Protocol incomplete: substantive score is one but trusted submission failed.

Budget exhaustion and skill loading are separate, overlapping behavior measures.
The labels describe observable outcomes; they do not establish a causal diagnosis
of why the agent failed.

Within-case disagreement is computed only when both repeats have valid completed
native receipts. The report gives disagreeing pairs, evaluable pairs, and
unevaluable pairs. It also reports the absolute substantive-score difference.
Missing repeats remain explicit, and incomplete cases do not silently vanish.

Success among completed receipts and confirmed successes divided by all planned
slots are both shown. With missing execution, the latter is a lower bound on
confirmed successes, not a claim that the missing agents behaviorally failed.
Measured usage, charged reservations, unknown costs, and missing slots remain
distinct. Missing provider prices do not become zero-dollar estimates.

There is **no confidence interval across these dependent cells** and no claim of
an independent 44-example sample. The useful outputs are concrete repeatability
counts, source coverage gaps, cost/accounting completeness, and failure categories
that can inform a subsequent preregistered evaluation design.

## Offline verification

```bash
python3 -m unittest discover -s tests -p test_calibration_bank.py -q
```

The fixtures verify that changing original outcomes does not change selection;
scope, split, temporal and provenance boundaries; missing-cell coverage and
repeated-obligation groups; exact source hashing; deterministic slot allocation;
partial/missing result accounting; duplicate/unknown receipt rejection; and
substantive, protocol, budget, infrastructure, and currency distinctions. These
tests make no model calls and are not native calibration evidence.
