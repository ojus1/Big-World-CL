# Native calibration and employee skill-transfer study

The native study completed with **no adopted skill edit**. SkillOpt's candidate
failed the non-regression gate. Its unchanged deployed skill then scored 8/8 on
fresh probes while the identical seed arm scored 7/8. That difference is a
control observation, not a learning gain.

The completed fixed-skill calibration confirms that native replay variability
matters: **3 of 22 historical task capsules produced different strict outcomes
across two fresh executions**. All 44 attempts have valid native receipts and
independent artifact audits. This is development evidence from one historical
world, not an estimate of an algorithm's deployment-time learning benefit.

The [preregistered plan](CALIBRATION_PLAN.md) was committed as `da3009e` before
execution. The audited transfer implementation is in `88cc112`; employee
selection and all four future probe hashes were published in
[the frozen transfer manifest](transfer-preregistration-v1.json), commit
`02eab32`, before any learning or probe calls. Raw computer states, prompts,
model transcripts and rubric answers remain private. Public artifacts contain
aggregate results, synthetic identities and evidence hashes.

## Fixed-skill calibration

The bank selected the earliest session in each employee/regime cell without
looking at its outcome. It covers six employees, 22 populated cells and 20
underlying obligations. Two exception cells are absent, and two obligations
appear under more than one regime. Each capsule was restored twice with the
same initial skill, legitimate historical inputs and fresh native Hermes
execution. MiroFish/Persona state came from the completed no-learning pilot;
institutions did not make new decisions during these diagnostic replays.

| Regime | Successful attempts | Completed attempts |
|---|---:|---:|
| Base | 12 | 12 |
| Changed | 7 | 12 |
| Temporary exception | 3 | 8 |
| Reversal | 9 | 12 |
| Total | **31** | **44** |

These rows describe different sets of historical exposures. They do not isolate
the causal effect of a policy change, and their dependent attempts are not
independent world samples. Mean semantic score was 0.9583, while strict success
was 31/44 (70.45%). Partial correctness never committed unsuccessful work.

Fourteen capsules succeeded twice, five failed twice, and three disagreed. The
discordant cells were firm-1 renewal under changed requirements, firm-1 renewal
under the exception, and firm-0 incident under reversal. Original online outcomes
are a separate historical record: 18 of these 22 source sessions succeeded and
four failed. They are not a third randomized replicate or a learning comparison.

All 13 failures were substantive, rather than fully correct deliverables that
failed only the submission protocol. Eleven were incident attempts and two were
renewal attempts. Incident diagnosis failed in 10 of 16 incident attempts, and
minimum-compliance repair failed in three, with overlap. All incident replay
execution and report-accuracy checks passed. This distinction matters: an
executable configuration can still contain unnecessary settings or an incorrect
diagnosis. Both renewal failures missed discounts and dependent totals; one also
missed usage and overage calculations.

Every failed attempt loaded the expected skill and exhausted its work budget.
One successful onboarding attempt also exhausted its budget. Thus the exhaustion
flag is overlapping evidence, not a standalone causal explanation. These
observations motivate testing procedure improvement; they were not converted
into hand-written replacement skills.

The campaign completed in 1,988.28 seconds (33 minutes, 8 seconds), using **474
physical calls and 5,265,090 measured tokens**. Charged tokens equal measured
tokens; no unresolved reservations or missing attempts remain. Currency cost is
unavailable. These counts exclude historical actor generation and later learning.
See the [audited aggregate](calibration-summary-v1.json) and
[allowlisted failure taxonomy](calibration-failure-taxonomy-v1.json).

## Frozen employee-level experiment

The preregistered selection chose `firm-0__incident-regulated`: five failures in
eight calibration attempts and an eligible source pool of three unique training
and three validation obligations. The other incident employee had six failures
but only two training and one validation obligation, so it was ineligible.
Selection intentionally uses development failures and cannot establish unbiased
population performance.

The actual epoch uses the published selector's two training and two validation
obligations at day 9. Historical retries update an obligation's content without
moving its original selection position. SkillOpt uses `rollouts_k=2`, its
unchanged mixed-score gate, per-task non-regression and fresh final validation.
The extra training replays do not repeat or average validation.

Four new development tasks were frozen beforehand: changed requirements on days
10 and 11, then reversal on days 12 and 13. Each skill receives two executions
per task, with counterbalanced arm order. Both arms use fresh computers and
profiles and retain all outcomes. The deployed skill is frozen across probes;
these probes measure transfer and retention, not another adaptation cycle.

The native epoch completed and passed independent audit. Its two initial
training replays both succeeded, but three of four additional training replays
failed. That contrast triggered one actual optimizer call, which proposed four
skill additions. In total, the epoch executed two baseline-validation, six
training, two candidate-validation and two final-validation replays.

| Validation phase | Strict successes | Mean mixed score | Skill used |
|---|---:|---:|---|
| Original baseline | 1/2 | 0.716667 | Initial skill |
| Candidate trial | 1/2 | 0.733333 | Proposed skill |
| Fresh final check | 1/2 | 0.716667 | Initial skill after rejection |

The candidate's mean score rose slightly, but one task's mixed score fell from
1.0 to 0.466667 while the other rose from 0.433333 to 1.0. The per-task
non-regression rule therefore rejected it. Final replay correctly used the
original skill; **all four edits were rejected and the deployed version stayed
at zero**. A single stochastic trial does not prove the edit caused the
regression, but the recorded rejection faithfully follows the configured gate.

The proposed additions concerned checking current specifications, complete
deliverable coverage, envelope fields and approval/commit steps. Some also
hard-coded training-task counts, envelope values and a particular approver
instead of deriving them from current context. That suggests possible
task-specific overfitting, not a demonstrated explanation of the failed trial.
The optimizer saw six trajectories from two historical training obligations and
no validation-experience or future-probe identifiers. No manual replacement
skill was introduced.

The epoch took 692.27 seconds (11 minutes, 32 seconds): **133 target calls and
1,581,721 target tokens**, plus **one optimizer call and 5,212 optimizer tokens**.
Its total is 134 calls and 1,586,933 tokens, with complete accounting. The source
world, source files and withheld probes remained unchanged. See the
[native learning summary](learning-epoch-summary-v1.json).

Because no edit was adopted, both future-probe arms had the identical initial
skill. All 16 predeclared attempts completed and passed strict artifact audit.

| Fresh-probe arm | Changed tasks | Reversal tasks | Total success | Calls | Tokens |
|---|---:|---:|---:|---:|---:|
| Seed | 3/4 | 4/4 | 7/8 | 77 | 912,893 |
| Deployed, identical to seed | 4/4 | 4/4 | 8/8 | 72 | 821,822 |

The apparent 12.5-percentage-point advantage of the deployed arm is **not a
learning gain**: its skill bytes were identical to the seed. One of eight matched
arm/repeat pairs disagreed. The single failure was substantive, and all 16
attempts loaded the assigned skill. There were no missing or invalid attempts;
three budget-exhaustion flags included two successful attempts. No best-of-two
selection was used, and no confidence interval or population ranking is claimed.

The probe campaign took 582.64 seconds (9 minutes, 43 seconds), using 149 calls
and 1,734,715 tokens. Learning plus probes cost **283 calls and 3,321,648 tokens**;
the table's arm costs exclude the separately disclosed learning epoch. Had one
reported only probe accuracy and cost, identical skills would have appeared to
show both an accuracy and efficiency improvement. This control demonstrates why
small observed arm differences need stronger evidence. See the
[completed transfer summary](transfer-summary-v1.json).

| Study phase | Native work/replay attempts | Physical calls | Measured tokens |
|---|---:|---:|---:|
| Fixed-skill calibration | 44 | 474 | 5,265,090 |
| SkillOpt epoch, including optimizer cost | 12 | 134 | 1,586,933 |
| Frozen future probes | 16 | 149 | 1,734,715 |
| Total | **72** | **757** | **8,586,738** |

One of the 757 calls was an optimizer call; the remaining 756 were target-agent
calls. All measured token totals reconcile with charged totals. Currency cost,
the original pilot and historical actor/world-generation cost remain outside
this study's totals. The actor world was not regenerated for these diagnostics.

The release's CI ran 346 offline tests: 345 passed and one Persona-import test
was skipped because the CI job does not download that cohort. This includes 70
new transfer tests, with real pinned-upstream gate fixtures, filesystem checks
and independent tamper detection. Native evidence is supplied by the separately
audited runs above, not by fixture test scores.

The preserved v1 outer auditor has a metadata omission: its generic
`accounting_verified` flag stays false outside the learning helper. It still
strictly verifies every probe receipt and combined total, and returns
`valid_completed`. The public summary records separate verified epoch, probe
and combined-accounting facts with this note. Original audit/score files and
frozen execution code were preserved; no scores or measured costs were changed.

## Evidence limits and next research stage

This study is an outcome-selected, single-employee development diagnostic. It
does not supply independent world replication, an algorithm ranking or a
population confidence interval. The task bank contains three bounded synthetic
work families; enterprise realism and broad job performance remain unvalidated.
The fixed-environment probes do not measure new competitor, government or
consumer reactions, although their source world was generated by native actors.

A stronger comparative study must freeze development choices, run multiple
independent reacting worlds for both methods, give employees enough disjoint
experience for repeated updates, and measure prospective work and delayed
business outcomes. It also needs actor-compute accounting and explicit
comparisons against additional learning-compute controls. The present SkillOpt
validation gate remains single-shot; calibration demonstrates why that
limitation must remain visible when interpreting adoption.

Three concrete research questions follow from the observed evidence: can skill
updates preserve conditional procedures without embedding temporary task facts;
can validation distinguish a useful edit from replay variability within a fixed
compute budget; and do accepted updates improve prospective fulfillment across
reacting worlds? This study does not answer those questions. It supplies a
faithful reference baseline, native execution evidence and the controls needed
to investigate them without mistaking a replay fluctuation for learning.
