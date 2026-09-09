# Development calibration and stronger SkillOpt baseline

This is the next research stage after the completed native integration pilot.
The goal is to identify repeatable, skill-addressable failures, measure native
replay variability, and test actual learning on independent later work. A null
result is valid. Calibration outcomes must not be presented as independent world
replication or as held-out test performance.

## Run and audit

The first-stage source is a completed private run with valid native artifacts;
the public aggregate summary alone cannot reconstruct employee computers. Use a
fresh output directory. Model credentials come from the existing private runtime
configuration and never belong in these configs or output manifests.

```bash
MiroFish/backend/.venv/bin/python -u scripts/run_calibration.py \
  --source lifespan/artifacts/evaluation-pilot-v1/no_learning \
  --out lifespan/artifacts/calibration-v1 \
  --config configs/calibration/replay_v1.json

python3 scripts/audit_calibration.py lifespan/artifacts/calibration-v1 --strict
```

`--stop-after-rollouts N` pauses after N additional completed slots; repeat the
same command without it to continue. Resume requires the exact config, source
capsules, bank, execution code and prior native records. An unresolved in-flight
attempt or infrastructure failure blocks automatic continuation. The independent
auditor verifies raw artifacts, rejected submissions, skill hashes, the fixed
slot order, budgets and regenerated reports. Raw state/capsules remain private;
publish only reviewed aggregate results and allowlisted bank metadata.

## Preregistered first stage

Before new model execution, freeze the following selection and budget contract:

- Source: the completed no-learning development world from `evaluation-pilot-v1`,
  seed 101, with its original checkpoint, manifest and private case hashes.
- Select the earliest session by `(day, session_id)` in each of the six employee
  by four regime cells. Selection never reads success or score. Original outcomes
  are attached only after selection. Leave missing cells missing.
- This yields 22 populated cells and 44 planned native Hermes replays. Two cells
  are absent, and 22 cells represent only 20 underlying obligations. Different
  historical versions of the same obligation are dependent exposures.
- Repeat each selected capsule twice, restoring the same pre-task world,
  public files, original employee request and competent initial `work-process`
  skill into a fresh bubblewrap computer and native Hermes profile each time.
  Every repetition makes new model/tool calls; no output cache is reused.
- Preserve the pilot's per-rollout 16 physical calls, 4,096 output tokens and
  250,000 conservative total-token reservation cap. The campaign caps are 48
  rollouts, 768 physical calls, 12 million charged/reserved tokens and one hour
  of active execution. These are ceilings, not expected usage or currency cost.
- Execute two rounds, each using a fixed seeded permutation of the selected cells
  (order seed 104729). Selection remains chronological; execution order is fixed
  independently of outcomes. Require the full 420-second allowance remaining
  before starting a slot; do not shorten a final slot because the campaign ends.
  Finish all planned slots unless a declared resource limit or infrastructure
  failure prevents it. Never stop, retry, replace or reorder a slot because its
  score is disappointing. Unknown usage reserves the full dispatch allowance;
  an ambiguous in-flight attempt requires explicit reconciliation.
- Measure within-case success disagreement, failure categories, skill use,
  budget exhaustion, measured/reserved compute and missing slots. Keep original
  online outcomes separate from fresh replay outcomes. Do not bootstrap these
  dependent exposures as independent worlds or treat two repeats as a precise
  estimate of a task's success probability.

The source cases were generated in a native MiroFish/Persona world. Calibration
restores those historical cases; it does not run new institutional decisions or
pretend to be a new reacting-world comparison. Actor-generation cost from the
original world remains outside replay-only measurements.

## Implementation and review ownership

The coordinator implements and executes the bounded native calibration runner,
records immutable provenance, integrates configs and publishes verified progress.
The task agent owns outcome-blind bank selection and descriptive aggregation.
The SkillOpt agent implements the pinned upstream repeated-training option and
its regression tests. The independent reviewer audits information boundaries,
dependence, model accounting, selection and the interpretation of live evidence.

## Learning and fresh-work stage

Use development calibration to choose a disclosed employee/workflow for further
study, then freeze a second-stage contract before launching its model calls.
Training, adoption validation and fresh probes must use disjoint underlying
obligations; multiple versions or retries of an obligation stay in one pool.
Calibration-selected cases are development resources, never fresh-test evidence.

The employee selection rule is fixed before calibration: among employees with at
least two train and two validation underlying obligations in the full authorized
source experience pool, choose the employee with the most unsuccessful **valid
calibration** repeats; break ties by employee ID. Proceed only after all planned
calibration slots have valid evidence. Select the latest two eligible distinct
obligations in each existing split at cutoff day 9 using the published experience
selector. This is explicit development selection, not an unbiased quality estimate.
In particular, the source firm-1 incident employee has only three obligations and
cannot satisfy a 2+2 split; retries must not manufacture a fourth task.

The first stronger upstream variant enables `rollouts_k=2`. In the pinned
SkillOpt-Sleep code this adds contrastive **training** replays after the initial
training replay. It does not repeat or average baseline validation, candidate
validation or final validation. Every additional training replay is charged.
The original strict-improvement and per-task non-regression gates remain intact.
Do not claim that this setting removes noisy-gate adoption.

If an edit is adopted, compare it with the original skill in new native profiles
on predeclared fresh task instances, including changed requirements and reversal.
Retain both arms' failures and costs. Independently repeated probes assess whether
the gate's chosen skill generalizes; they are not additional free gate queries.
If no edit is adopted, report that fact without substituting hand-written edits
or disabling the gate to manufacture a learning result.

Freeze four synthetic development probes before that one learning epoch: two
changed-requirement tasks at cutoff+1/+2 and two reversal tasks at cutoff+3/+4,
using seed 20260910 and new obligation IDs. Each arm receives two fresh executions
per probe with counterbalanced order, for 16 total probe attempts. The generator
uses the development `validation` task mechanism, not the final test namespace.
These are fixed-environment transfer probes with no new MiroFish institutional
decisions; they cannot establish world-level causal effects. Even if no edit is
adopted, execute the same predeclared schedule and label it an identical-skill A/A
diagnostic. Never select the better of repeated outputs or retune against probes.

Provision the one K=2, T=2, V=2 skill-only epoch for at most 12 native target
rollouts plus up to four optimizer calls: 200 physical calls and four million
charged/reserved tokens, with 30 minutes active time. Probe execution is capped at
16 rollouts, 256 physical calls, four million charged/reserved tokens and 30
minutes, with the original full per-rollout bounds. Report exhaustion and missing
slots rather than silently extending a campaign after seeing its outcomes.

Full-workforce, replicated reacting worlds follow development calibration. Freeze
model, task mechanisms, budgets and analysis choices before using the separate
test namespace. Competitive learning claims require this later evidence; this
stage supplies calibration and implementation evidence rather than a ranking.
