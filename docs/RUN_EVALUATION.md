# Running deployment-time skill-learning evaluations

This runner compares native **no-learning Hermes** with **SkillOpt-Sleep + BigWorld
trajectory-context adapter** in a persistent synthetic enterprise world. It adds
controlled trials and executable work-quality rubrics to the historical integration
PoC. The commands below create new experiments; this document reports no live
baseline results or demonstrated learning advantage.

The world uses actual MiroFish/OASIS institutional, consumer and employee actors,
12 pinned Persona 8B records, native Hermes agents, and bubblewrap employee
computers. Competition and government decisions remain reactive. A declared
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

## Budgets and lifecycle

| Limit | Development config | Integration pilot |
|---|---:|---:|
| Work horizon | 24 days | 8 days |
| Maximum online sessions | 144 | 48 |
| Native physical model calls per work attempt | 16 | 16 |
| Maximum output tokens per native request | 4,096 | 4,096 |
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
- `REPORT.json`: completion/audit status; obligation and attempt success;
  semantic score; employee/regime breakdowns; skill loading; compute exhaustion;
  descriptive adaptation/censoring; realized business utility and delayed rewards;
  separate execution and learning costs.
- `work/`: native work sessions, graded file artifacts and private audit evidence.
- `learning/`: isolated replay trials, upstream gate evidence, accepted/rejected
  updates and actual sanitized optimizer prompts.
- `skills/`: immutable accepted skill versions, including the initial version.
- `checkpoint.json`, `timeline.json`, `actors/` and `private/cases/`: persistent
  world state, native actors and trusted replay capsules.

Do not publish raw run directories as learner datasets. They contain privileged
rubrics, private world state and runtime metadata; use an audited public export.

To compare completed pilot reports without additional inference:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from lifespan.evaluation.metrics import paired_report

root = Path('lifespan/artifacts/evaluation')
reports = [json.loads((root / name / 'REPORT.json').read_text())
           for name in ('pilot-no-learning', 'pilot-skillopt')]
result = paired_report(reports)
(root / 'pilot-paired-report.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
```

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
