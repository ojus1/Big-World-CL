# First controlled native evaluation pilot

Completed 2026-09-10. This is a **baseline integration result**, with one development
world pair and no demonstrated skill-learning gain. Both arms used the execution
source from commit `47c7609`, the same initial skill, model, Persona cohort,
scenario and work budget. Independent audits checked all 90 prospective sessions
and six historical replay sessions. No infrastructure-invalid attempt was dropped.

## Protocol and provenance

The committed [pilot configs](../configs/evaluation/) specify eight workdays,
followed by two settlement-only days, seed 101, fresh private agent state per
session, six working employees and two reacting enterprises. Only
`firm-0__onboarding-regulated` was eligible for SkillOpt learning; the other five
employees retained the initial skill in both arms. This is an employee-focused
integration pilot, not the full-workforce development configuration.

The model was `gpt-5.6-luna` through the Responses API with low reasoning effort.
Work sessions had a 16-physical-call limit, a 4,096-token output cap and a
250,000-token conservative reservation budget. Model sampling and institutional
decisions are not made deterministic by the world seed. Each arm generated its
own downstream decisions in response to its own outcomes.

| Dependency | Recorded revision |
|---|---|
| Hermes Agent | `2c8a2b65aa148ceb178d2251c54a523af12092c9` |
| MiroFish | `39d849138ef254f6c737ab4c4705e5545dbe31d4` plus recorded local compatibility patch hash |
| SkillOpt | `79124b37e9a6371e13b753f8bcd7adb1e493ade1` |
| Persona cohort | 12 records; SHA-256 `7e9e22221e3bc96a6f39411a4e278353a477d1c3c6cf4bb9380a8ea243b532dd` |

Full execution source hashes, dependency patch hashes, report/checkpoint hashes and
aggregate measurements are retained in the
[machine-readable summary](evaluation-pilot-summary.json).
Post-run changes strengthen artifact evidence and correct reporting; they do not
retroactively claim to have governed these model executions.

## Observed outcomes

| Measurement | No-learning Hermes | SkillOpt-Sleep adapter |
|---|---:|---:|
| Accepted commitments before action horizon | 48 | 49 |
| Correctly completed commitments | 36 | 33 |
| Commitment fulfillment | 75.00% | 67.35% |
| Fulfilled fixed initial/exogenous commitments | 36 / 48 | 32 / 48 |
| Pending commitments at observation | 12 | 16 |
| Prospective work attempts | 43 | 47 |
| Successful work attempts | 36 | 33 |
| Successful attempts / all attempts | 83.72% | 70.21% |
| Intended native skill loaded | 43 / 43 | 47 / 47 |
| Attempts exhausting declared budget | 7 | 15 |
| Realized synthetic business utility | 365.87 | 334.40 |
| Work model calls | 454 | 510 |
| Work tokens, including prompt and output | 5,014,853 | 5,707,543 |
| Learning replay model calls | 0 | 54 |
| Learning replay tokens | 0 | 527,103 |
| Optimizer proposal calls in paired run | 0 | 0 |
| Total measured learner tokens | 5,014,853 | 6,234,646 |
| Consolidation cycles / accepted edits | 0 / 0 | 2 / 0 |

Both worlds received the same 48 initial/exogenous commitments. The SkillOpt world
also accepted one native consumer order. All committed rewards settled within the
declared observation window. Business utility includes actual simulated costs and
penalties; it is not dollars. Environment-actor tokens and all-in monetary cost
remain unmeasured and are reported as unknown.

These are descriptive observations, **not evidence that learning caused the
difference between arms**. All deployed employee skill versions remained zero.
The worlds differ in sampled execution, institutional reactions, work availability
and retries. There is one independent world pair, so no confidence interval or
algorithm ranking is justified.

| Regime | No-learning successes / attempts | SkillOpt successes / attempts |
|---|---:|---:|
| Base | 16 / 18 | 18 / 18 |
| Changed requirements | 5 / 6 | 5 / 6 |
| Scoped exception | 5 / 7 | 6 / 11 |
| Reversal | 10 / 12 | 4 / 12 |

Each employee had only 6–8 attempts in the no-learning arm and 7–8 in the SkillOpt
arm. Exposure within individual employee/regime cells is too sparse to establish
adaptation or retention. Failed work stayed pending; retries consumed real budget.

## What actually happened during learning

The native pinned SkillOpt-Sleep consolidation ran on days 3 and 5. Each cycle used
one distinct past training obligation and one distinct validation obligation,
restored into isolated computers under their historical policies. Baseline
validation, training and final validation all passed. Upstream SkillOpt therefore
made no reflection request and adopted no change. Six replays used 54 physical
model calls and 527,103 tokens; learning was not free merely because the skill
stayed unchanged.

Two separate diagnostics are **excluded** from all paired measurements:

- A real optimizer-provider smoke used one recorded past incident failure. It
  made one physical call, used 4,652 tokens and returned four upstream-format
  edits. Those edits were never deployed or credited with better performance.
- A retrospective incident diagnostic selected a different employee after
  observing failures. Two past training tasks and one validation task yielded
  four successful fresh replays, using 39 calls and 437,336 tokens. Again, no
  reflection or adoption occurred. This exploratory selection is not a
  prospective test or an independent third world.

The diagnostics verify the real proposal transport and reveal a calibration
problem: some observed failures disappear on replay. A credible strong-baseline
study now needs development calibration for repeatable, skill-addressable failure,
larger disjoint experience pools, adequate budgets and replication across worlds.
It must retain a competent starting skill and the upstream acceptance gate.
See the [calibration protocol](SKILLOPT_BASELINE.md).

## Reporting correction and audit boundary

The original version-1 obligation count used `Task.created`, which means
**availability day**, as if it meant order-placement day. Three no-learning orders
were accepted on day 5 but became available on day 8, after action stopped. The
original report consequently showed 36/45 completion and nine pending tasks.
Correct commitment accounting is 36/48 completion and twelve pending commitments.
The SkillOpt arm has no corresponding delayed-availability exclusion.

Original `REPORT.json` files are preserved byte-for-byte. Version-2 reports bind to
those files and their checkpoints by hash, distinguish commitments from actionable
arrivals, and include scheduled orders even if they have not materialized by the
observation horizon. This is a disclosed post-run reporting correction, not a
change to tasks, scoring, execution or business balances.

The strict artifact audit verifies native skill bytes/load calls, committed raw
artifact bytes and substantive grades, temporal training/validation boundaries,
immutable skill versions, replay records, physical call/token accounting,
checkpoint consistency and task/settlement reconciliation. All committed artifacts
in this pilot have matching immutable objects. Legacy failed sessions did not
consistently retain exact rejected bytes, so their **partial scores** cannot all be
independently regraded; their failed completion status remains counted.

The subsequent evidence fix preserves exact submitted bytes before employees can
rewrite/delete files, including rejected submissions. Tests exercise both paths.
It does not reconstruct missing historical evidence or authenticate provider
billing receipts. The live reconnect check verified an unchanged running native
environment/database; it did not test full process-kill recovery.

## Readiness and remaining research work

The release provides executable rubrics, a controlled no-learning Hermes
baseline, actual upstream SkillOpt-Sleep integration, chronological updates,
isolated replay, native skill deployment/versioning, bounded accounting and
auditable world-level evaluation. Offline acceptance tests exercise successful
adoption; the live pilot exercised conservative no-adoption behavior.

Before claiming a competitive learning baseline or algorithm improvement, run the
full-workforce development configuration, calibrate replay variability and task
difficulty, freeze design choices, then evaluate multiple unseen world seeds and
change mechanisms. Native post-adoption improvement and policy-reversal retention
remain unverified. Online weight updates, RL training, broad economic realism and
persona causal validity are separate research extensions.
