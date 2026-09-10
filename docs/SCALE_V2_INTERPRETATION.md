# Interpreting the six-world deployment-learning study

This reporting guide was added during execution. It explains the existing
[registration](scale-preregistration-v2.json); it does not change its endpoint,
learning gate, budgets, worlds, or stopping rule. The campaign raw SHA-256 is
`4315bd53cc14870a291accbe5c71d7556a458ac0a9260d181dc30735c8f4b801`.

## What the comparison measures

Each seed supplies two fresh worlds with the same starting Persona cohort and
exogenous schedule. Both contain four enterprises, twelve employees, eight
consumers and an agency. Enterprise decisions, policies, purchases and employee
work affect later world state. Each employee works through native Hermes with
an isolated filesystem; the `skill_transfer` setting creates a fresh task
profile carrying the employee's deployed skill.

Both arms retain the simulation's actor histories, working notes and business
state. The treatment adds employee skill consolidation using the pinned
SkillOpt method. Therefore this is a comparison of adding skill consolidation
to an already adapting enterprise simulation. A no-learning Hermes label does
not imply that the surrounding enterprise has no history or adaptive behavior.

The primary outcome is fixed initial/benchmark commitments fulfilled before
day 20, divided by **240 commitments per world**. A commitment accepted before
the work horizon stays in that denominator even if its availability is delayed
beyond the horizon. Work ends after day 19; days 20–21 drain settlement and
feedback without adding work attempts. Fulfillment at the observation endpoint
and pending/abandoned/delayed categories are reported separately.

For seed s, report:

    delta_s = fixed_fulfillment_rate_skillopt_s
              - fixed_fulfillment_rate_no_learning_s
    primary_difference = (delta_211 + delta_307 + delta_401) / 3

The unit is a world pair, with equal weight for every planned pair. Do not pool
sessions or employees to obtain a larger apparent sample size. These are three
development pairs using previously observed cohorts and seeds. Report their
individual values and descriptive mean, without a significance claim or an
inferential confidence interval.

All-demand commitment fulfillment, native-consumer demand, online task success
and synthetic business utility are secondary. The generic canonical report
names all-demand fulfillment in its `canonical_headline`; this campaign's
registered primary is specifically `fixed_demand_fulfillment_rate`. The
completed study reporter must select that field explicitly.

Native consumers and enterprises may respond differently in the two arms.
Even fixed-demand fulfillment can change through task availability, routing,
pricing, priorities and competition. The paired difference describes the
deployment policy's performance in these reacting worlds; it does not isolate
an individual skill edit or hold every later task exposure constant.

## Evidence that a skill changed and was used

Keep every employee and every scheduled learning boundary (days 3/7/11/17),
including ineligible boundaries, rejected changes, no proposals and budget
stops. Reconstruct eligibility from released observations and feedback, using
distinct underlying obligations in separate TRAIN and VAL pools. Day 3 cannot
be eligible under the registered release schedule.

For every update, retain the parent and deployed versions, gate decision,
available-from day and all measured replay/optimizer costs. An accepted version
becomes available the next day. Then distinguish these observations:

| Observation | Supported interpretation |
| --- | --- |
| A candidate passes a trial gate | Tentative selection; the fresh final gate may still reject it. |
| The final-gated update records adoption | Recorded deployment decision, not future benefit. |
| A new version becomes available | The employee can receive it in subsequent tasks. |
| An online session records that version | Prospective exposure to the deployed profile. |
| Native `skill_view` evidence sets `skill_loaded=true` | Hermes loaded the skill during that task. |
| Work succeeds after loading | A successful prospective task with that skill; not proof the skill caused success. |

Version exposure is not evidence of loading. Explicit non-loading and unknown
loading evidence must remain separate. Likewise, an adopted skill with no later
work exposure cannot demonstrate useful adaptation.

The pinned T2/V2/K2 method uses two TRAIN cases and two VAL cases. After the
initial TRAIN replay, K2 adds two contrastive replays per TRAIN case: six TRAIN
replays in a fully executed epoch. K2 does not provide best-of-two validation:
each validation stage uses one fresh attempt per case. Adoption requires strict improvement
and no per-task regression, followed by a fresh final gate. A perfect baseline
on the small historical VAL set leaves no improvement headroom. Stochastic
replays and repeated selection on historical VAL cases limit interpretation;
those scores are not independent generalization evidence.

Report prospective exposure by deployed version and by the four regimes:
base (days 0–5), changed (6–9), exception (10–14), reversal (15–19). Negative
business differences or worse later performance may show operational harm.
They do not alone establish causal forgetting: task mix, world decisions and
adoption are endogenous. This campaign does not replay identical future cases
under both old and new skills. If examining the native report's time to first
success, retain its censoring and descriptive exposure interpretation;
an unobserved success is not an arbitrarily long latency. The publication draft
reports version exposure and success counts without exporting that latency
statistic.

## Costs and completion

Keep online target calls, learning-target replay calls and optimizer calls
separate. Count each physical replay receipt once. Report known input/output
tokens and complete measured totals separately from charged or unresolved
reservations. Equal registered caps do not imply equal consumed compute.
Contracted actor interviews have their own receipt meter; bootstrap and social
inference remain outside it. Whole-environment model costs and currency billing
remain unknown. Synthetic business utility is not dollars.

The primary endpoint is available only after all six fresh worlds and all
three pairs pass the strict raw and composite audits, including settlement,
immutable work/grade reconstruction, chronology, usage reconciliation, source
provenance and confirmed native cleanup. A failed or missing arm is not a zero
quality score. Two surviving pairs cannot replace the registered three; an old
scale-v1 arm cannot substitute for a fresh scale-v2 arm.

Zero accepted updates and zero or negative differences are valid completed
research outcomes. They do not justify replacements, additional seeds,
extended limits or a revised primary metric in this campaign. An invalid or
incomplete campaign instead produces an engineering/accounting observation
with the primary endpoint unavailable.

## Source anchors

- [Registered design and budgets](../scripts/run_scale.py)
- [Fresh-world contract](../scripts/scale_v2_contract.py)
- [Native employee and consolidation execution](../lifespan/evaluation/runner.py)
- [Chronological experience selection](../lifespan/evaluation/protocol.py)
- [Native skill-load provenance audit](../scripts/audit_evaluation.py)
- [All-employee boundary and exposure summary](../scripts/scale_summary.py)
- [Canonical commitment comparison](../scripts/evaluation_report_v2.py)
- [Six-world completion and cost audit](../scripts/audit_scale_v2.py)
- [Pinned SkillOpt gate](https://github.com/microsoft/SkillOpt/blob/79124b37e9a6371e13b753f8bcd7adb1e493ade1/skillopt_sleep/consolidate.py)
