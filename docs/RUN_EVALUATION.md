# Running deployment-time skill-learning evaluations

This runner compares native **no-learning Hermes** with **SkillOpt-Sleep + BigWorld
trajectory-context adapter** in a persistent synthetic enterprise world. It adds
controlled trials and executable work-quality rubrics to the historical integration
PoC. The commands below create new experiments. The first completed
[native pilot and its limitations](EVALUATION_RESULTS.md) are documented separately;
it demonstrated no learning advantage.

The world uses actual MiroFish/OASIS institutional, consumer and employee actors,
pinned Persona 8B records, native Hermes agents, and bubblewrap employee
computers. The default population has two enterprises, six employees, three
consumers and one government agency, requiring 12 distinct persona records.
Population size is configurable; the [scale-v1 study](SCALE_STUDY_PLAN.md) uses
25 participants per world. Competition and government decisions remain reactive. A declared
exogenous daily workload supplies recurring employee tasks alongside consumer
orders, so each method can be evaluated across change, scoped exception and
reversal rather than unrelated one-off episodes.

## Baselines and state contract

Both methods start with the same `work-process` skill. Each work attempt and
candidate replay creates a **fresh private Hermes profile and conversation** with
authorized task files. The accepted document is written to the profile's native
`skills/work-process/SKILL.md`; Hermes can discover and read it through native
`skills_list` and `skill_view`. Target agents cannot call `memory` or `skill_manage`.

- **No learning:** the seed skill stays fixed throughout the world. The employee
  can still receive new requests and current public evidence. No optimizer runs.
- **SkillOpt:** after eligible experience becomes available, the pinned upstream
  consolidation reflects on training replays, proposes bounded skill edits,
  validates the candidate on separate cases, and performs a fresh final validation
  before adoption. Every target replay runs in a new isolated computer restored
  from its historical pre-task world state. The optimizer is a separate model
  callback; it never replaces target execution with answer-only text generation.

Skill discovery is **prompted, not deterministically injected**. Not loading a
skill and exhausting a declared execution budget remain measured behavioral
outcomes in the denominator. Neither condition removes a difficult trial as an
infrastructure failure. Load rates are reported separately; a loaded document is
evidence of availability/use, not proof that its instructions caused success.

The supplied configs use `state_mode="skill_transfer"`: reusable skill is the
explicit persistent agent treatment, while organizations, obligations, policies,
employee actors and business outcomes retain their world history. The optional
`full_deployment` mode additionally carries accepted business artifacts into new
employee workspaces. It does **not** currently retain arbitrary private notes,
conversation histories, OS processes or every filesystem mutation. Do not call
that option a complete persistent-agent-memory comparison.

See [SkillOpt baseline implementation and callback contract](SKILLOPT_BASELINE.md)
for the exact pin, default prompt augmentation, budgets, failure handling and the
exact-upstream-prompt ablation.

## Setup and offline verification

Follow [the pinned runtime setup](SETUP.md) for Linux namespaces, MiroFish,
the native Hermes virtual environment, Persona data import and private model
configuration. Set `HERMES_AGENT_ROOT` in the launching shell if using a
nondefault installation. The runner uses the model and endpoint configured in
the existing MiroFish `.env`; no key belongs in the JSON experiment configs.

From the repository root:

```bash
python3 scripts/install_skillopt.py
python3 -m unittest discover -s lifespan/tests -v
python3 scripts/stack.py start
```

The SkillOpt installer fetches its reviewed revision into ignored `.cache/SkillOpt`.
Install it before **either** arm, including no learning, so dependency provenance
matches. The tests include offline fixtures; they neither run the model comparison
nor establish model gains. Live commands below make billable inference requests.

## Integration pilot

The pilot is one eight-day world per method, with all six employees working.
Only `firm-0__onboarding-regulated` receives SkillOpt updates; the other five
employees retain the seed skill in both arms. The pilot uses one training and one
validation case per update, attempts an update every two simulated days when
enough distinct eligible obligations exist, and caps online work at 48 sessions.

The pilot configs are identical except for `algorithm`:

- [pilot_no_learning.json](../configs/evaluation/pilot_no_learning.json)
- [pilot_skillopt.json](../configs/evaluation/pilot_skillopt.json)

Run the first two **additional sessions** of each arm as a bounded integration
check. Use separate output directories:

```bash
MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/pilot_no_learning.json \
  --out lifespan/artifacts/evaluation/pilot-no-learning \
  --stop-after-sessions 2

MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/pilot_skillopt.json \
  --out lifespan/artifacts/evaluation/pilot-skillopt \
  --stop-after-sessions 2
```

Then resume each arm to its configured horizon by repeating its command without
the invocation cap:

```bash
MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/pilot_no_learning.json \
  --out lifespan/artifacts/evaluation/pilot-no-learning

MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/pilot_skillopt.json \
  --out lifespan/artifacts/evaluation/pilot-skillopt
```

Two early sessions generally do not reach an eligible skill update. The complete
pilot is an integration exercise, **not strong aggregate evidence** about which
algorithm learns better. An update can legitimately be skipped or rejected; no
config guarantees a skill will improve.

## Larger development comparison

The development configs use 24 days, six employees eligible for learning, two
training and two validation cases per update, an update cadence of four days and
at most 144 online work attempts:

```bash
MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/dev_no_learning.json \
  --out lifespan/artifacts/evaluation/dev-no-learning

MiroFish/backend/.venv/bin/python -u -m lifespan.evaluation.runner \
  --config configs/evaluation/dev_skillopt.json \
  --out lifespan/artifacts/evaluation/dev-skillopt
```

[dev_no_learning.json](../configs/evaluation/dev_no_learning.json) and
[dev_skillopt.json](../configs/evaluation/dev_skillopt.json) differ only in the
algorithm. They provide a larger development workload, still only one independent
world pair at seed 101. Freeze the code, model configuration, rubric and protocol
before running a prespecified set of additional seeds. Keep each seed's configs
identical across methods except for `algorithm`, and give every arm a fresh output
directory. Hosted model randomness is not determined by the scenario seed.

`split="test"` selects a separate seed namespace and held-out input mechanisms.
Within a deployment test world, an algorithm may still learn from its own **past
observed** work once feedback is released; it never sees future evaluation work.
Use this mode only after fixing development choices. It is a sequential deployment
evaluation, not a static test set that becomes freely available to the optimizer.

## Population and learning-calendar configuration

Experiment JSON accepts `enterprise_count` and `consumer_count`, defaulting to
two and three. Each enterprise has three regulated-workflow employees, one each
for onboarding, renewal and incident response. Evaluation configs require at
least two enterprises and at least one consumer per enterprise. Raising the
enterprise count therefore also requires enough consumers. Each participant,
including an enterprise or government decision profile, receives a distinct
imported synthetic persona. Four enterprises and eight consumers produce twelve
employees and 25 total participants.

An optional `update_days` JSON list overrides the periodic `update_every`
calendar. Its values are zero-based simulated days, strictly increasing and
distinct, and must leave at least one subsequent action day. Omit it or use
`null` to retain the periodic calendar used by the earlier configs. For example,
these fields select the scale-v1 population and calendar within a full config:

```json
{
  "enterprise_count": 4,
  "consumer_count": 8,
  "days": 20,
  "max_work_sessions": 240,
  "update_every": 4,
  "update_days": [3, 7, 11, 17]
}
```

An update date is an opportunity, not a guaranteed epoch or adoption. Each
employee needs the configured number of distinct TRAIN and VAL obligations with
released feedback. Retries cannot supply additional distinct tasks. With one
attempt per employee per day and one-day feedback delay, day 3 cannot supply
the four observations required by T=2/V=2. Day 17 can use reversal feedback from
days 15–16, and any adopted skill becomes available for work on days 18–19.
The checkpoint records eligibility even when no update runs.

Scale work-session and learning budgets together with the population. The existing
24-day configs retain their original six-employee budgets; changing population
alone does not increase those limits. Optional `max_learning_calls_per_epoch`,
`max_learning_tokens_per_epoch` and `max_learning_seconds_per_epoch` bound each
epoch within the fleet and equal per-employee lifetime allocations. The
preregistered campaign below generates the complete matching configs for both arms.

## Preregistered scale-v1 campaign

The [study plan](SCALE_STUDY_PLAN.md) and
[published preregistration](scale-preregistration-v1.json) define six native runs:
seeds 211, 307 and 401, each with no-learning Hermes and SkillOpt. The campaign was
prepared and launched with execution code frozen at commit `b72fdda`. Its exact
`campaign.json` **raw-file SHA256** is:

```text
6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa
```

Each run has twenty action days (0–19), then settlement days 20–21 with no new
orders, employee attempts, actor interviews or learning. Previously accepted
delayed tasks can still arrive. There are 240 fixed initial/exogenous commitments per
world and at most 240 online attempts; native consumer commitments are additional.
Failures and delayed arrivals remain in commitment accounting. The campaign
therefore permits at most 1,440 online attempts and 108 eligible learning epochs.
These are ceilings, not promised completed work or learning progress.

| Limit | Scale-v1 value |
|---|---:|
| World active execution time | 36,000 seconds, with bounded cleanup afterward |
| Native work attempt | 16 physical calls, 4,096 output tokens/request, 250,000 total-token cap, up to 420 seconds |
| Learning epoch | 200 target-plus-optimizer calls, 4M tokens, 1,800 seconds |
| Employee lifetime learning allocation | 600 calls and 12M tokens |
| Logical actor interviews | 662 per world, including response-repair requests |
| Concurrent worlds | At most six; actions within each world stay sequential |

Graph generation, the initial social round and OASIS internal inference do not
have complete physical-call/token accounting. Actor tokens and all-in currency
cost remain unknown. See the study plan for separate campaign compute ceilings.

The commands below document the frozen preparation and launch. **Do not rerun
them against the already launched `scale-v1` directory.** Preparation requires a
new directory; execution is one-shot and rejects existing native output. To start
a separate campaign, use a fresh directory, review and publish its own generated
manifest, and provide that manifest's hash instead of reusing the value above.
Preparation imports the pinned cohorts and makes no model calls:

```bash
MiroFish/backend/.venv/bin/python scripts/run_scale.py prepare \
  --out lifespan/artifacts/scale-v1

MiroFish/backend/.venv/bin/python -u scripts/run_scale.py execute \
  --out lifespan/artifacts/scale-v1 --workers 6 \
  --campaign-sha256 6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa
```

The supervisor verifies the published hash, execution sources, dependencies,
configs, dispatch order and cohort identities before starting native work. The
paired arms share identical cohort bytes; the three seeds use 75 distinct persona
records. `EXECUTION.json` records exclusive dispatch intent. Uncertain work is
never automatically retried or resumed. Preserve any `INFLIGHT.json`, failure or
supervisor-interruption records for reconciliation; do not delete them or reset
an actor database to force a restart. A failed/incomplete arm remains in the
planned comparison while other runs continue under their original limits.

Use the read-only status command for the running campaign:

```bash
python3 scripts/run_scale.py status --out lifespan/artifacts/scale-v1
```

The supervisor also writes `STATUS.json` roughly every 30 seconds. Status includes
all six slots, checkpoint age, simulated day/phase, work and update counts,
learning replays, metered learning compute, logical actor requests and any
in-flight learning progress. A quiet terminal or an unchanged checkpoint alone
does not establish a stalled model call; inspect the in-flight progress and
declared limits. Private per-run `execution.log`, checkpoints, actor ledgers and
learning `progress.json` files provide detailed evidence and should not be
published wholesale. The supervisor records process exits, closes each run's
native actor environment and writes its final campaign audit.

Audit completed evidence with:

```bash
python3 scripts/audit_scale.py lifespan/artifacts/scale-v1 --strict
```

`--strict` requires all six completed, valid runs and three valid world pairs.
An interrupted or still-running campaign cannot pass strict completion. The
non-strict audit retains incomplete slots explicitly, but it does not establish
complete cost accounting or authorize resuming uncertain work. Completed worlds
retain both `REPORT.json` and corrected `REPORT.v2.json`; the primary comparison
uses fixed initial/exogenous commitment fulfillment, not an attempt-only rate.
Employee exposure summaries retain all scheduled boundaries and mark missing
eligibility evidence. Their hashes are labeled `canonical_json` and are distinct
from the raw-file hash required for execution.

This campaign is three development world pairs, not 1,440 independent samples.
Accepted edits, gate scores and subsequent version exposure are reported
separately from any world-level performance difference. Keep the earlier pilot
and single-pair examples above as separate protocols. Strict auditing of frozen
historical runs requires their recorded implementation revision; new population
or calendar fields do not retroactively change those experiments.

## Budgets and lifecycle

| Limit | Development config | Integration pilot |
|---|---:|---:|
| Work horizon | 24 days | 8 days |
| Maximum online sessions | 144 | 48 |
| Native physical model calls per work attempt | 16 | 16 |
| Maximum output tokens per native request | 4,096 | 4,096 |
| Total work-attempt token reservation cap | 250,000 | 250,000 |
| Fleet learning calls, including replay and optimizer | 2,880 | 320 |
| Fleet learning tokens | 36,000,000 | 4,000,000 |
| Eligible employees | 6 | 1 |
| Learning quota per eligible employee | 480 calls / 6,000,000 tokens | 320 calls / 4,000,000 tokens |
| Total active runtime budget | 14,400 seconds | 14,400 seconds |
| Feedback delay | 1 simulated day | 1 simulated day |

Fleet learning budgets are divided into equal employee quotas; early employees
cannot consume the entire fleet allocation. No learning carries the same declared
configuration and uses zero optimizer/replay budget. Work inference and learning
inference are separately recorded, so the comparison exposes the extra cost of
learning rather than hiding it inside task performance.

Native Responses transport attempts are metered before dispatch, including
Hermes stream retries. Output caps and conservative input reservations prevent the
next request from starting when it cannot fit; unknown usage retains a reservation
and invalidates complete accounting. Optional model-based end summaries and context
compaction are disabled in this controlled execution path. Per-operation timeouts
are bounded by the remaining experiment deadline. See
[the budget limitations](SKILLOPT_BASELINE.md#budgets-failures-and-audit): conservative
token reservations are not a provider-side billing guarantee.

`--stop-after-sessions` is an **invocation limit**, not a change to the experiment
config. It checkpoints only completed operations and deliberately leaves the
native MiroFish actor process/database alive. Resume requires the same source,
dependencies, provider, config and output directory, and that native process must
still be alive. Do not restart or reset its database to make a resume appear valid.
A dead or closed native environment is rejected; an unresolved `INFLIGHT.json`
requires reconciliation instead of blind replay. Completed worlds cannot be
overwritten. Exhausting the configured total time/work budget is different from
a clean invocation pause and can leave an incomplete comparison.

The horizon includes a separate two-day settlement drain. It lets commitments
already created during the work horizon settle without providing new work or
learning opportunities. Every method uses the same observation window.

## Executable rubrics and feedback

The agent must produce a real JSON deliverable, pass substantive checks in the
trusted process, satisfy current business authorization/check/approval rules, and
successfully commit. Correct prose or a nonempty file is insufficient.

| Work family | Substantive checks |
|---|---|
| Onboarding | Posted-event reconciliation, duplicate handling, signed amounts, complete account coverage, correct activation decision and totals |
| Renewal | Contract/usage reconciliation, applicable scoped discounts, integer monetary calculation and complete contract totals |
| Incident | Correct endpoints and schemas, bounded timeout/retry repair, diagnosis and replay of supplied probes |

Published specifications and data change across base, changed, scoped-exception
and reversal regimes. Held-out cases add mechanisms such as reversal postings or
cold-start probes. Expected answers and evaluator policy state stay outside all
employee files and optimizer prompts. Feedback reports failed check categories
and aggregate success, without supplying hidden expected outputs.

Historical replays retain their historical rules. Current work follows currently
effective rules; a later policy reversal must not retroactively rewrite a prior
validation case. Training and validation pools use distinct underlying obligations,
with retries grouped into their original pool and feedback released on schedule.
Future work and other employees' private cases never enter an employee's update.

## Reports and paired comparison

Each output directory contains:

- `manifest.json`: model, source hashes, configuration, scenario and dependency
  provenance.
- `REPORT.json`: original version-1 execution report, preserved for audit;
  its obligation denominator counts task availability, not commitment placement.
  It includes completion/audit status; conditional work and attempt success;
  semantic score; employee/regime breakdowns; skill loading; compute exhaustion;
  descriptive adaptation/censoring; realized business utility and delayed rewards;
  separate execution and learning costs.
- `REPORT.v2.json`: canonical commitment fulfillment, all accepted obligations,
  pending/scheduled work, source breakdown and the hashes of the original report
  and checkpoint. New completed runs generate this automatically.
- `work/`: native work sessions, graded file artifacts and private audit evidence.
- `learning/`: isolated replay trials, upstream gate evidence, accepted/rejected
  updates and actual sanitized optimizer prompts.
- `skills/`: immutable accepted skill versions, including the initial version.
- `checkpoint.json`, `timeline.json`, `actors/` and `private/cases/`: persistent
  world state, native actors and trusted replay capsules.

Do not publish raw run directories as learner datasets. They contain privileged
rubrics, private world state and runtime metadata; use an audited public export.

To compare completed pilot reports without additional inference:

First audit each private run directory. `--strict` rejects unfinished runs,
unreconciled artifacts, incorrect hashes, temporal leakage, accounting mismatch,
and completed reports without matching task/settlement evidence:

```bash
python3 scripts/audit_evaluation.py lifespan/artifacts/evaluation/pilot-no-learning --strict
python3 scripts/audit_evaluation.py lifespan/artifacts/evaluation/pilot-skillopt --strict
```

The audit independently regrades committed outputs and checks raw content-addressed
bytes, skill versions, physical transport receipts and report regeneration. It
does not authenticate a provider's billing system or infer that learning caused
an observed improvement. Legacy unsuccessful sessions may lack the exact rejected
artifact bytes; the audit labels that limitation instead of claiming to regrade
their partial scores.

```bash
# Historical runs need this explicit correction; new completed runs already have it.
python3 scripts/evaluation_report_v2.py \
  lifespan/artifacts/evaluation/pilot-no-learning \
  lifespan/artifacts/evaluation/pilot-skillopt

python3 scripts/compare_evaluations.py \
  lifespan/artifacts/evaluation/pilot-no-learning/REPORT.v2.json \
  lifespan/artifacts/evaluation/pilot-skillopt/REPORT.v2.json \
  --out lifespan/artifacts/evaluation/pilot-paired-report.json
```

The correction preserves v1 byte-for-byte and counts accepted orders even if
their availability lies after work stops. Fixed initial/exogenous demand is
separate from native consumer orders. Comparison verifies the local source files,
regenerates the correction and requires matching postprocessor hashes. Intentional
historical v1 comparison requires `--legacy-actionable`; it is not the canonical
business fulfillment headline. See [the correction semantics](EVALUATION_RUBRICS.md).

If automatic postprocessing fails, the command fails with a separate
`REPORTING_FAILURE.json` diagnostic while preserving completed `REPORT.json` and
checkpoint bytes. Reconcile the reporting problem and invoke the standalone
postprocessor; do not rerun already completed model work. The diagnostic describes
that failed reporting attempt, and the regenerated report has its own verified
source hashes.

Pairing requires matching treatment-independent model, code, dependency and persona
provenance, shared config, scenario and settlement window. Changed source between
arms, duplicate runs, missing methods and failed/incomplete audits are reported
explicitly rather than silently pooled. The methods each simulate their own
reactive downstream world; one method's consumer decisions are not replayed as
fixed inputs to the other.

The inference unit is an **independent world pair**, not an employee or session.
The paired report returns SkillOpt-minus-no-learning differences and bootstraps
whole-world differences when multiple eligible seeds exist. A single pair receives
no confidence interval; small-sample intervals remain unstable. Replay gate scores
are not prospective work performance, and an accepted edit is not evidence of
generalization until later work demonstrates it.

MiroFish actor token and monetary usage is currently **unknown**, and optimizer
monetary costs are not supplied by the callback. Reports do not claim all-in spend
or dollar-normalized business utility. The business score is synthetic. This
benchmark does not establish economic realism, persona causal validity, a complete
lifelong memory comparison, online weight updates or RL training.
