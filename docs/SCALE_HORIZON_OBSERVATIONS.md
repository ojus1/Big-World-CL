# Partial observations of scale-v1 durations

This additive diagnostic captures the six original scale-v1 slots and describes
the durations recorded so far. It preserves failed, completed, missing and
still-running worlds. It does not change any frozen execution file, installed
dependency, server, existing artifact, original audit or study inclusion rule.
It makes no model or native actor calls.

The implementation and its tests do not contain live results. Capture is a
separate explicit action after source review.

## Capture and verification

```bash
python3 scripts/scale_horizon_observations.py capture \
  lifespan/artifacts/scale-v1 \
  --out lifespan/artifacts/scale-v1-horizon-observation-001
python3 scripts/scale_horizon_observations.py verify \
  lifespan/artifacts/scale-v1-horizon-observation-001
```

The destination must be new, git-ignored, under `lifespan/artifacts/`, and outside
the campaign being observed. It is created with mode 0700. No capture is resumed,
overwritten, or retried to hide an uncertain read.

`private/raw/` contains exact bytes from the campaign/control files, six world
checkpoints and available terminal reports, visible raw work sessions, learning
updates/progress, replay sessions and their referenced case capsules. Private
task content and provider traces remain private. `private/source/` contains the
34 frozen execution source files, verified against the campaign before capture
and checked again at its end. The exact diagnostic source is copied separately.

`capture.json` records paths, byte counts and hashes of these originals, missing
files, read failures, and changes noticed during capture. `REPORT.json` is the
allowlisted public duration summary; it includes
`provenance.capture_sha256`. A reviewed REPORT hash therefore commits the raw
capture inventory without a circular hash dependency.

The Python interface is:

```python
capture(campaign_directory, new_observation_directory)
verify_snapshot(
    observation_directory,
    expected_capture_sha256=reviewed_capture_hash,
    expected_report_sha256=reviewed_report_hash,
)
```

`verify_snapshot` returns `ok`, `report_sha256`, `capture_sha256`,
`summary_reproduced`, `world_slots` and safe error codes. It reconstructs the
summary from captured originals, checks exact raw/source inventories and their
hashes, and compares the derived report with the saved report. It never reads
the mutable live campaign or queries a dependency/service. The running diagnostic must match the captured diagnostic source hash; a different historical processor is explicitly unsupported. `summarize(out)`
returns the reconstructed public report directly.

## What the rows mean

Online work, learning epochs and learning replays have separate tables and
separate duration groups:

- Online work groups retain arm, workflow and source-case regime.
- Epoch groups retain arm, employee workflow, learning day and proposal class.
  `proposal_observed` means the recorded upstream gate has applied, rejected or
  unmatched edit records. `no_proposal_observed` requires a completed update and
  three empty edit lists. Incomplete/missing evidence is `unknown_incomplete`.
  These labels are independent of acceptance; rejected proposals are not no-ops.
- Replay groups retain arm, workflow, original case regime, learning day and
  native upstream phase. Historical case regimes do not become the regime of
  the day on which they were replayed. Replay durations never enter the online
  work groups.

Every returned observation remains in its table, including infrastructure
failures and unknown usage. A checkpoint copy whose raw session is missing is
retained with a binding error instead of silently removing its duration.
Uncheckpointed raw returns and pending progress are separately marked. Missing
timing is unknown, never zero; nonfinite, negative, boolean and malformed timing
values cannot enter numeric duration summaries. Each group records the full
observation count, known/unknown duration count, min/max, sum, mean, median and
nearest-rank p90. These are descriptive values with no confidence intervals.

The raw work/checkpoint duplicate is reconciled after removing only the two
runner-added fields (`id`, `skill_version`). Raw updates are compared with their
checkpoint copies and progress. Epoch day/employee metadata must match its directory. Replay declarations require unique session paths and exact integer attempt indices and the owning epoch employee; pending declared returns remain explicitly missing and unknown, without fabricated time or measured usage. Replay session/capsule hashes and identities
are checked where declared. Missing or contradictory bindings remain visible
and make verification fail. This checks captured provenance, not every original
scientific criterion: no work is regraded and no accepted update is certified
as a learning improvement.

Recorded infrastructure validity, semantic success and accounting completeness
remain separate. A successful artifact with missing provider usage is not
silently recategorized as an infrastructure success. Charged/reserved tokens
and known reported-token prefixes retain their labels; they are not complete
measured consumption. Actor model usage, all-in monetary cost and physical
inference duration remain unknown.

## Timing scopes and use in a future budget decision

The native work/replay `elapsed_seconds` ends before final session persistence
and worker cleanup. An enclosing learning callback includes restoration,
execution, persistence and cleanup. `costs.wall_seconds` measures the learner
call; `progress.elapsed_seconds` additionally covers its surrounding runner
work up to that progress write. These overlapping clocks are reported
separately and must not be added together. Their difference is not a direct
measurement of cleanup alone.

World checkpoint runner elapsed time and supervisor terminal elapsed time are
also kept separate. A missing terminal duration cannot be reconstructed from
session durations. Actor activity, setup, waits, filesystem work and other
overhead prevent the sum of employee durations from being a complete world
wall-clock accounting.

The snapshot is sequential rather than simultaneous across worlds. Mutable
checkpoint/progress/control changes during the read window are reported
explicitly; the first captured bytes remain the evidence. Immutable record or
source mutation is a provenance error. Newly created files after a world's
inventory read are outside that inventory. There is no attempt to pause a
world or claim a single global observation instant.

Use this evidence to write a prospective wall-budget rationale alongside the
fixed schedule and call/token caps. For example, the current schedule allows
three potentially eligible dates across twelve employees; 36 possible
30-minute epoch allocations alone amount to 18 hours of allocations. That is
an arithmetic ceiling component, not a prediction that every epoch is eligible
or consumes its cap. Short, perfect-replay/no-proposal epochs do not estimate
the duration of proposal-generating epochs with additional gated replays.

The diagnostic deliberately emits no timing forecast or recommended new wall
limit. Sessions and epochs within a world share state and are not independent
samples; the six slots remain three paired development worlds. A chosen future
limit requires an explicit reviewed rationale, including unresolved actor and
operational overhead. These streaming scale-v1 observations do not establish
selected-nonstreaming reliability over a long horizon or justify replacing
failed slots.

Offline fixture tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -S -m unittest \
  tests.test_scale_horizon_observations -q
```

Tests create synthetic temporary campaigns only. They establish snapshot and
reconciliation behavior, not native execution quality or completion forecasts.
