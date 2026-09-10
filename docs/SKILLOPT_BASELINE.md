# SkillOpt-Sleep baseline

Big World CL integrates **the upstream SkillOpt-Sleep consolidation algorithm** at
Microsoft SkillOpt commit `79124b37e9a6371e13b753f8bcd7adb1e493ade1`. It runs the
upstream reflection prompt/parser, bounded edit application, candidate validation
and fresh final validation. It does not replace those operations with a locally
invented optimizer. The native target remains the employee's Hermes execution
harness; an independently configured optimizer model supplies reflection.

This is a baseline implementation and integration contract. Offline tests and the
first native pilot establish execution and accounting behavior, **not learning
gains**. The live evidence and remaining calibration work are described below.

## Native pilot evidence and remaining calibration

The first completed eight-day pilot exercised both native no-learning and SkillOpt
arms. Only the focal onboarding employee was eligible for updates. Inspection of
its recorded update traces shows:

| Evidence | Native execution and outcome |
|---|---|
| Two prospective pilot consolidation cycles | Six isolated target replays, 54 target model calls, 527,103 tokens; every training and validation replay scored 1.0 |
| Optimizer use in those cycles | **Zero reflection calls and zero accepted edits**; the deployed skill remained the seed document |
| Separate optimizer-provider smoke | One real optimizer call, 4,652 tokens and four returned edits; `deployed=false`, with no candidate replay or adoption claim |
| Separate retrospective incident diagnostic | Four perfect target replays, 39 target model calls and 437,336 tokens; zero reflection calls and zero accepted edits |

These are separate evidence sets. The provider smoke and retrospective incident
diagnostic are not prospective outcomes of the pilot and must not be added to its
learning totals. Source artifact identifiers are
`evaluation-pilot-v1/skillopt/learning/*/update.json`,
`evaluation-optimizer-smoke-v1/result.json`, and
`evaluation-incident-learning-diagnostic-v1/learning/*/update.json` under the local
ignored `lifespan/artifacts/` directory. The pilot contains two successful no-op
consolidation executions, not two trained skill versions.

In the pilot's single-shot path, upstream `CliBackend.reflect` returns no edits
without failed **training replays**.
Previously unsuccessful online work is not sufficient: when an isolated replay
succeeds, that replay enters the successful set. Moreover, a validation score of
1.0 leaves no room for the strict improvement gate. This explains the zero
reflection calls without implying a broken optimizer connection. The separate
provider smoke verifies that a real model can propose edits from public evidence;
it does not establish that those edits pass validation or improve future work.

Since the native pilot never changed a skill, differences between its online arms
cannot be evidence of successful skill refinement. Native target and actor
randomness, reactive world divergence and learning overhead still differ between
the runs. One world pair supplies no reliable aggregate estimate, and the perfect
retrospective replays do not show that earlier online failures were impossible or
that the task distribution has zero difficulty.

The next development calibration should be explicit and bounded:

1. **Measure reproducible failure opportunities on development data.** Use
   multiple distinct train and validation obligations across employees, task
   families and change regimes. Diagnose whether mistakes concern substantive
   reasoning, business protocol, skill discovery or compute exhaustion. A single
   observed failure followed by a perfect replay is insufficient. Do not weaken
   the frozen baseline or hide authorized specifications merely to force updates.
2. **Characterize replay noise before tuning the gate.** Repeat incumbent
   rollouts from identical capsules, then preregister rollout counts, matching and
   candidate/final acceptance criteria. Count every rollout. The adapter now
   exposes upstream's repeated **training** rollouts through `rollouts_k`, described
   below. This does not average validation or establish its uncertainty: repeated
   incumbent/candidate gate evaluation remains separate follow-up work.
3. **Expand the declared experience pool and workforce.** The supplied
   [24-day development configs](RUN_EVALUATION.md#larger-development-comparison)
   use two training and two validation cases and all six employees, with equal
   employee learning quotas. Calibrate on these development worlds before freezing
   a separate multi-seed test campaign. Selecting difficult development tasks is
   allowed; selecting or reusing future test outcomes to manufacture gains is not.
4. **Budget for the full update, including rejection.** Use measured native
   rollout costs to provision incumbent validation, training replays, reflection,
   candidate trials and fresh final validation. Keep per-attempt bounds comparable
   across methods, expose additional learning spend, and include failures and
   missing receipts. Larger nominal budgets alone do not remedy an accuracy ceiling.
5. **Require prospective evidence after an accepted revision.** Demonstrate
   skill creation, native reuse in a fresh profile, revision after change and
   correct behavior after reversal on later work. Report rejected/no-op updates,
   stale-procedure errors, retained competence, assistance and compute costs,
   followed by uncertainty across independent world pairs. If correctness remains
   saturated but inefficiency is substantial, preregister a separate cost-aware
   gate variant: the present hard/soft quality gate cannot accept efficiency-only
   gains at a perfect score.

This implementation faithfully calls the pinned **SkillOpt-Sleep consolidation**
with documented native-Hermes and public-trajectory adapters. It does not reproduce
the main paper's complete reflective-training pipeline, benchmark suite,
hyperparameters or reported results. A strong native baseline requires this
calibration and prospective evidence; the current integration should not be
presented as having already demonstrated lifelong learning improvements.

The subsequent [larger development study](SCALE_STUDY_PLAN.md) preregisters three
world pairs, twelve employees per world and repeated employee epochs. Its frozen
schedule, budgets and prospective comparison are distinct from the historical
pilot evidence above. This document specifies that study's integration contract;
it does not report its ongoing results.

## Installation and provenance

From the repository root:

```bash
python3 scripts/install_skillopt.py
python3 -m unittest lifespan.tests.test_skillopt_baseline -v
```

The installer creates an ignored `.cache/SkillOpt` checkout at the exact revision.
This Sleep path imports only standard-library dependencies. It does not install
the full research package, alter a Python environment or read personal agent
sessions. Each update verifies the checkout's revision and cleanliness and refuses
a conflicting imported SkillOpt version. Missing dependencies fail explicitly;
there is no fallback to `MockBackend`.

Source: [pinned consolidation](https://github.com/microsoft/SkillOpt/blob/79124b37e9a6371e13b753f8bcd7adb1e493ade1/skillopt_sleep/consolidate.py),
[pinned reflection backend](https://github.com/microsoft/SkillOpt/blob/79124b37e9a6371e13b753f8bcd7adb1e493ade1/skillopt_sleep/backend.py),
[upstream Sleep documentation](https://github.com/microsoft/SkillOpt/blob/79124b37e9a6371e13b753f8bcd7adb1e493ade1/docs/sleep/README.md).
The upstream software is MIT licensed; it remains a separate dependency.

## Algorithm variant and deliberate choices

The name in results is `skillopt_sleep`. It refers to Sleep's consolidation
implementation, not a claim to reproduce the main SkillOpt paper's full trainer,
all benchmark settings or its published scores.

| Setting | This baseline |
|---|---|
| Update unit | One employee, one skill document, one consolidation epoch |
| Reflection | Pinned upstream `CliBackend.reflect`, real optimizer callback |
| Target | Fresh native Hermes execution through a supplied replay callback |
| Judge | Trusted executable environment rubric; never an optimizer's self-score |
| Edits | Upstream `add`, `replace`, `delete`, at most four by default |
| Memory evolution | Off; skill-only comparison |
| Gate | On; strict improvement over incumbent |
| Gate metric | `0.5 * hard + 0.5 * soft` by default; configurable |
| Regression guard | Per-validation-task no regression by default; configurable |
| Rollouts | One per task per phase by default; optional native `rollouts_k > 1` adds repeated training attempts for contrastive reflection |
| Candidate verification | Separate candidate trial and **fresh** final validation |
| Retry | Upstream reflection JSON retry, charged against optimizer budget |
| Deployment | Caller atomically installs an accepted native `SKILL.md` |

Upstream defaults are configurable and include modes this comparison does not
enable. In particular, greedy gate-off adoption, memory evolution, mining personal
transcripts, hallucinated validation tasks and cached final target responses are
not part of this baseline. Scheduled simulation experience supplies the recurring
tasks and splits, rather than the upstream personal-session harvest/mining stages.

Default prompt rendering is frozen to the pinned upstream text during an update.
Personal prompt overrides are neither read nor written. Calls are serialized to
avoid overlapping temporary upstream settings. Run separate worker processes when
comparing multiple optimizer configurations concurrently.

The upstream reflection prompt summarizes up to eight training failures and
truncates individual wanted/result/feedback snippets to 160 characters. The
stronger default provider adapter preserves that upstream prompt and appends a
bounded public training context: task inputs, observed feedback and visible
user/assistant/tool trajectory when supplied. Its explicit name is **SkillOpt-Sleep
+ BigWorld trajectory-context adapter**, recorded as
`skillopt_sleep_bigworld_trajectory_context_v1`. This remedies the short snippets
without replacing the upstream edit application or gate. The exact upstream prompt
is also available as a separately recorded ablation.

```python
from lifespan.evaluation.optimizer import make_reflector

reflect = make_reflector(credentials, augment_training_context=True)
# Exact upstream prompt ablation:
exact_reflect = make_reflector(credentials, augment_training_context=False)
```

`credentials` uses the existing `{model, base_url, api_key}` configuration. The
adapter defaults to the Responses API and the same configured model, with
`store=False`. Set `api_mode="chat_completions"` explicitly for another compatible
endpoint. SDK transport retries are disabled: one provider request is one callback
call, and upstream's bounded JSON retry remains separately charged. No automatic
transport retry occurs after uncertain billing or timeout.

The adapter refuses validation, test or future records, even when they would have
fallen beyond its context cap. It omits grader/private fields, provider headers,
reasoning and encrypted blocks, response/call ids and non-visible native messages.
Credential values and recognizable authentication strings are redacted. These
filters supplement the runner's public-observation boundary; they cannot determine
whether arbitrary public prose semantically reveals a private fact.

Before dispatch, the adapter reserves one call and conservatively budgets input
using UTF-8 byte length plus 256 framing tokens, then caps output by both the
upstream requested maximum and the remaining total-token allowance. Supplementary
training context is truncated to fit that reservation. The byte bound deliberately
overestimates ordinary text tokenization; the framing allowance assumes the
configured provider's normal single-message text API. A provider that injects
additional hidden context can violate that assumption, so actual usage is checked
after the call and any overrun rejects adoption. A strict externally billed token
ceiling also requires provider-side budget support.

Successful receipts use exact provider `input_tokens + output_tokens` (including
reasoning counted in output); they never label estimates as measured usage. Missing
or inconsistent usage returns `tokens=None`, `accounting_complete=False`, so the
learning bridge retains its cost reservation and rejects the incomplete update.
Provider exception text never enters receipts or public audit records.

Every callback exposes `reflect.audit_records`, including its sanitized actual
optimizer prompt, SHA-256, adapter identity, token reservation, exact available
usage and status. The runner must persist these records with the experiment;
the bridge's pre-adapter prompt alone is not sufficient provenance for this
augmented baseline.

## Callback contract

### Optional native contrastive training rollouts

```python
learner = SkillOptLearner(rollouts_k=3)
```

`rollouts_k` is a positive integer, defaults to 1 and is recorded in each update's
configuration. Values greater than 1 call the pinned upstream
[`multi_rollout` and `contrastive_reflect`](https://github.com/microsoft/SkillOpt/blob/79124b37e9a6371e13b753f8bcd7adb1e493ade1/skillopt_sleep/rollout.py)
through `consolidate`; the adapter does not implement its own reflection selector
or gate. With `K > 1`, upstream first performs its ordinary initial train replay,
then **K additional fresh attempts per training task** under the incumbent skill.

For each training task, upstream chooses the best and worst repeated attempt by
the configured gate metric. It reflects on up to six tasks with positive score
spread; different soft scores can therefore be informative even when binary
success is unchanged. Its contrastive prompt contains the best/worst responses
and public failure feedback. The same bounded BigWorld training-context adapter
can append the available public trajectories. This is selection for reflection,
**not best-of-K task-performance evaluation**: all attempts remain recorded and
charged, and prospective work performance is unchanged by this option.

No score averaging occurs in this pinned path. Baseline validation, candidate
validation and final validation still run **one fresh attempt per validation
task per phase**. The strict improvement and optional per-task no-regression gates
are unchanged. `rollouts_k` does not make the validation decision robust to model
noise or supply a confidence interval.

If contrastive reflection yields no edits, upstream falls back to its **original
initial training replay's** failures. This has a specific limitation: when the
initial replay succeeds but all K additional attempts fail at the same score,
there is no repeated-attempt spread and no original failure, so no reflection
occurs. The adapter preserves that behavior rather than silently changing the
algorithm. Uniformly perfect repeats likewise need not produce an optimizer call.

For T training and V validation tasks, `K > 1` costs `(K + 1) * T + 2 * V` target
executions when no candidate is tested, or `(K + 1) * T + 3 * V` when the skill
candidate is tested. Reflection calls and any upstream JSON retry are additional.
For the default `K = 1` single-shot path, these counts are `T + 2 * V` and
`T + 3 * V`. Early budget exhaustion can stop either sequence; incomplete runs
cannot adopt a candidate.

Every callback invocation still receives a new isolated runtime from the runner.
`replay_evidence` and the cost ledger include `phase`, `sample_id` and globally
unique-in-update `attempt_index`. Upstream labels the initial train pass and extra
rollouts with phase `train`; the initial pass and first extra rollout both have
`sample_id=0`, but have different attempt indices and genuinely execute separately.
There is no target-response cache. A sample id is an audit label, not a controlled
provider random seed, and fresh sandboxes do not prove statistical independence
of hosted-model outputs.

### Execution and reflection callbacks

```python
from lifespan.evaluation.skillopt import LearningBudget, SkillOptLearner

result = SkillOptLearner().update(
    skill=current_skill_markdown,
    experiences=safe_experiences,
    replay=run_fresh_native_hermes_case,
    reflect=call_optimizer_model,
    current_day=simulation_day,
    budget=LearningBudget(max_replays=32, max_target_model_calls=256),
)
if result["status"] == "completed" and result["accepted"]:
    deploy_native_skill_atomically(result["skill"])
```

Each experience is an allowlisted public descriptor:

```json
{
  "id": "employee-3-order-41",
  "split": "train",
  "available_day": 8,
  "prompt": "Reconcile the supplied account ledger.",
  "context": "The authorized input is /workspace/ledger.csv.",
  "source_session": "employee-3-session-18",
  "feedback": "The refund was omitted from the total.",
  "feedback_available_day": 8
}
```

`train` and `val` must both be nonempty, with globally unique case ids. Exact
duplicate public task content and shared source sessions cannot cross the split.
`test` items and future tasks are rejected before any callback. Unrecognized
fields, including expected procedures and rubrics, are never copied into the
upstream `TaskRecord` or optimizer payload. The caller must still ensure that the
public prompt/context/feedback strings themselves contain only authorized data;
a field allowlist cannot detect privileged facts embedded in a public string.

**`replay(payload, limits)`** receives:

- `task`: the safe descriptor; use its id to look up private state inside the
  trusted runtime, never by handing the private case to the optimizer.
- `skill`: the proposed document, installed and loaded through native Hermes.
- `phase`: `baseline_val`, `train`, `gate_trial:skill` or `final_val`.
- `attempt_index`, `sample_id`, `current_day`: auditing and seed inputs.

For **every invocation**, the callback must restore an equivalent pre-task state
into a new isolated employee computer/profile, start fresh conversation context,
run the real target model and tools, then grade the resulting files and business
state. Reusing a recorded answer or inspecting only skill text is not an execution
of this baseline. Do not reuse a mutable validation workspace, cached score, target
conversation, pending commitments or optimizer profile between invocations.

The callback returns:

```json
{
  "status": "completed",
  "hard": 1.0,
  "soft": 1.0,
  "response": "The account reconciliation is written to the requested file.",
  "feedback": "The checks passed.",
  "score_available_day": 8,
  "feedback_available_day": 8,
  "tokens": 5140,
  "model_calls": 6,
  "tool_calls": 5,
  "latency_ms": 12700.0
}
```

`hard` and `soft` must be finite in `[0,1]`. `status=completed` means the execution
and grading completed, even if the task failed and scored zero. Timeouts, worker
crashes and incomplete grading must have another status; they invalidate the update
instead of becoming artificial zero-score examples. Empty answer text is allowed
when native execution successfully produces a file deliverable.

Only the explicitly public `feedback` becomes upstream reflection feedback.
`private_diagnostic`, `judge_rationale`, expected outputs and arbitrary raw receipt
fields are excluded. Later feedback is withheld; later-dated scores invalidate
the update because even selecting a replay as a failure would leak that score.
Missing availability fields mean the caller explicitly declares the fresh replay
checker result available on `current_day`.

**`reflect(payload, limits)`** receives the actual upstream reflection `prompt`
and an audit sidecar of **training-only** public task/response/feedback records.
It must call the configured optimizer model on that prompt and return `response`
as the raw JSON array of edits, with the same status and cost receipt. Returning
an `edits` list is supported as a JSON serialization convenience; upstream still
parses, bounds, applies and gates those edits. Neither validation task text nor
its grader ground truth is sent to this callback. An optimizer model is not a
target execution substitute.

The reflection payload also carries the upstream requested `max_output_tokens`
(1024). The provider callback should apply that output cap while independently
respecting the total-token and time budgets in `limits`.

## Budgets, failures and audit

Before each callback the bridge reserves its maximum permitted calls and tokens.
`limits` supplies `max_model_calls`, `max_tokens`, `timeout_seconds`, and remaining
totals. The callback must enforce these bounds, including native skill-loading
calls, model retries and failed attempts. The bridge settles reservations from
actual receipts; unknown costs retain the full reservation and mark accounting
incomplete. An overrun is reported at its actual amount and invalidates adoption.

The bridge can prevent the **next** operation and reject an overrunning result;
it cannot forcibly stop arbitrary Python callbacks. The native worker and provider
client must enforce call/output/time limits themselves. Input tokens count toward
the total token budget; a provider output cap alone is not a total-token cap.

The result records separate target/optimizer calls, tokens, tool calls per
operation, runtime, train/validation ids, skill hashes, gate trials, per-task
deltas and the actual safe optimizer inputs. Failed native runs or invalid scores
retain the incumbent skill and report `failed` or `budget_exhausted`. Dependency
or input-contract problems raise an explicit exception before an update can run.
No infrastructure failure is evidence of an algorithm's task competence.

Costs are model-call/token/time accounting, not monetary cost. Conversion to money
requires the provider, model, date, cache treatment and applicable prices in the
experiment manifest. Deterministic test callback receipts are synthetic test
fixtures and must never be reported as real model costs or learning results.

### Repeated employee epochs

The runner supports these optional configuration fields:

| Field | Meaning when supplied | Default when absent or `null` |
|---|---|---|
| `max_learning_calls_per_epoch` | Maximum combined target and optimizer physical calls for one epoch | No additional epoch call cap |
| `max_learning_tokens_per_epoch` | Maximum combined target and optimizer charged tokens for one epoch | No additional epoch token cap |
| `max_learning_seconds_per_epoch` | Maximum epoch wall time in seconds | 1,800 seconds |
| `update_days` | Sorted, distinct action days on which to check employee eligibility | Periodic `update_every` schedule |

Each numeric cap must be a positive integer. Effective calls and tokens are the
minimum of the epoch cap, the remaining world learning budget and that employee's
remaining equal lifetime allocation. Effective time is also bounded by the
remaining run deadline. Target and optimizer calls share the epoch total; the
optimizer's reserved call bucket is not extra allowance. Missing caps preserve
the earlier behavior in which a first epoch can consume the employee's remaining
lifetime budget. Unused quota is not transferred between employees.

The [frozen scale schedule](SCALE_STUDY_PLAN.md#learning-and-comparison) checks at
the end of **days 3, 7, 11 and 17**, with one-day feedback delay and **T=2, V=2,
K=2**. Day 3 cannot yet supply four released distinct observations, so there are
at most three eligible epochs per employee. Later opportunities can also be
ineligible: retries of one obligation never become additional distinct tasks.
Pool updates preserve the obligation's insertion order while retaining its latest
available observation. Future tasks and unreleased feedback stay outside learning.

The study caps each epoch at **200 physical calls, 4M charged tokens and 1,800
seconds**, within each employee's lifetime 600-call/12M-token allocation. A complete
K2/T2/V2 epoch executes ten fresh targets without a candidate, or twelve with a
candidate, plus any optimizer calls. These are ceilings and execution counts,
not cost or adoption predictions. Individual target limits and a shrinking run
deadline can exhaust an epoch before that full sequence finishes.

`employee_epoch_index` is one-based and local to the employee; it is also passed
to upstream as `night`. It counts recorded consolidation executions, including
no-op or rejected updates. It is neither the simulation day nor the number of
schedule opportunities: an eligibility or pre-dispatch budget skip does not
increment it. Each update records `epoch_allocation`, `parent_version`,
`deployed_version` and `available_from_day`; accepted skills first apply to later
online work, starting the following day. No-op and rolled-back updates retain the
incumbent.

### Reading durable progress and replay evidence

Within a run, `learning/dDDD-EMPLOYEE/progress.json` is saved before and after
target and optimizer dispatches. It records the employee epoch, effective
allocation, parent world/skill hashes, elapsed time, target progress and optimizer
dispatches. This makes a long epoch observable without exposing task bodies in
terminal progress lines.

Each `replay_artifacts` entry identifies its `attempt_index`, upstream `sample_id`,
phase, experience and underlying task, executed skill hash, source capsule path
and raw-byte hash, and native `trial-NNN/session.json` path and raw-byte hash. It
also retains dispatch limits, completion state, available usage, trusted scores
and observed native skill loading. Use the attempt index with the epoch directory
to identify a physical execution; sample ids repeat across initial and contrastive
TRAIN passes. Missing optional skill loading remains a measured behavior, not a
reason to discard that employee's work.

While dispatch is unresolved, `target_progress` retains its call/token reservation;
known returned usage replaces that reservation. These running totals are
provisional. The completed `update.json` contains the bridge's final cost ledger,
gate evidence, replay links and optimizer transport audit, and final progress
records its outcome. Reconcile these against native receipts and submitted files;
progress alone is neither proof of completion nor an independent adoption audit.
An unfinished dispatch or `INFLIGHT` record must remain explicit rather than being
silently replayed or reported as a zero-cost rejection.

## Drift and valid evaluation

Historical replay snapshots retain their historical requirements. A review rule
that expired today can still be required when replaying a case from last week.
Current generalization cases must use the currently effective policy and distinct
inputs. Retention cases should test capabilities that remain relevant. Future
prospective test work stays outside consolidation entirely.

The runner must declare which deployment feedback is available. An immediate
executable checker can be an allowed training signal. A delayed customer payment
or future outcome cannot be silently substituted for that signal. True rubric
scores used privately by the gate are distinct from employee-visible explanatory
feedback, and this extra validation access must be equal across eligible learning
baselines and charged to the learning budget.

Disjoint ids are necessary but insufficient for strong conclusions: vary input
content and task families, limit repeated gate queries, use fresh prospective
evaluation, and compare independent worlds or matched seed clusters rather than
treating dependent employee sessions as independent observations. SkillOpt has
no guaranteed gain under drift; report rejections, adaptation failures and costs.

For repeated epochs, group later online outcomes by employee, deployed version,
skill hash and effective day. An accepted update demonstrates that the candidate
passed the pinned gate on fresh recorded validation attempts. With K2, those
validation phases still use one attempt per task, so adoption can reflect rollout
noise. Retain all attempts in replay summaries; the best/worst TRAIN examples
selected for reflection are not a best-of-K performance metric. A subsequent
success under the new skill does not by itself establish improvement.

The scale study compares no-learning and learning arms across three fixed world
pairs. Within-world employees interact, and independently generated actor decisions
can make paired worlds diverge. Report unchanged-skill differences, rejected/no-op
epochs, later outcomes and learning costs alongside accepted versions. The
inferential units are the world pairs, not individual employee sessions; three
pairs provide limited uncertainty estimates. Prospective evidence must therefore
remain separate from the gate decision and from historical calibration outcomes.

## What the tests establish

The tests invoke the **installed upstream consolidation**, using offline target
and reflection callbacks. They check accepted improvement, rejected edits, rollback
when a fresh final replay fails, per-task regression rejection, validation and
future-label separation, private-field omission, distinct target/optimizer calls,
cost reservations and failure behavior. Integration tests explicitly skip if the
pinned dependency is absent; input-contract tests still run. A credible evaluation
also needs actual native Hermes execution tests and prospective multi-world runs.
