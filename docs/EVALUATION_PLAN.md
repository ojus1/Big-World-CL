# Deployment-time learning evaluation: implementation and acceptance plan

Status: implementation, fixed-source native pilot, reporting correction,
fixed-skill native calibration and one employee's native SkillOpt proposal/gate
completed. Independent reacting-world replication remains open.
This document is the launch contract; checkboxes refer
to verified deliverables, not intended capabilities. The previous 16-day artifact
remains historical integration evidence and is not a baseline result.

## Objective

Compare deployment-time learning algorithms on consequential employee work in
changing enterprises. Preserve actual MiroFish/Persona actors and native Hermes
execution. Trainable state is initially employee-specific natural-language skills;
model weights remain frozen. Integrate pinned upstream SkillOpt-Sleep as a real
baseline, and compare against Hermes without cross-session private learning state.
Do not require or manufacture a SkillOpt win.

## Work allocation

| Owner | Deliverable | Independent acceptance |
|---|---|---|
| Coordinator | Protocol, Hermes execution bridge, world integration, experiment runner, reporting, release | Research reviewer examines state/feedback boundaries and live artifacts |
| Task implementation agent | Three substantive filesystem task families and deterministic executable rubrics | Adversarial rubric tests and reviewer inspection |
| SkillOpt implementation agent | Pinned upstream consolidation/gate bridge, dependency setup and accounting | Tests must invoke actual upstream code; reviewer inspects fidelity and leakage |
| Research/review agent | Threats to validity, acceptance checklist, final implementation review | Coordinator fixes material findings before score claims |

Implementers own disjoint modules. The coordinator integrates their interfaces,
runs combined checks and pushes useful verified milestones to GitHub. Reviews
must cite concrete code or artifacts, identify severity and distinguish verified
failures from future research limitations.

## Experimental contract

1. **Unit of comparison.** A world seed and scenario specification form a paired
   experimental unit. Employees in one world interact; sessions are not IID
   samples. Confidence intervals resample paired worlds, not tool calls.
2. **Online ordering.** Score work before using its feedback for learning. Skills
   adopted after a workday affect subsequent work only. Feedback availability is
   explicit. No future tasks, test outcomes or private expected procedures enter
   optimizer prompts.
3. **Baselines.** Both methods use the same frozen target model, initial generic
   skill, task instructions, tools and per-work-call budget. No-learning Hermes
   gets a fresh conversation/private profile state for each work session. It can
   reason and retry within a session. SkillOpt additionally carries its accepted
   employee skill and optimizer history between sessions. Extra optimization
   compute is separately reported, never called free or compute-matched.
4. **State modes.** The primary skill-transfer mode uses fresh execution context
   and task files for both methods, retaining skills only for SkillOpt. A full
   deployment mode may expose accumulated canonical business deliverables to
   both methods, but must not accidentally carry hidden notes, model histories,
   native memory stores or scripts into the no-learning arm. Canonical business
   state always persists in the economy.
5. **Skill mechanism.** Package adopted skills in native employee-scoped
   `SKILL.md` files. Audit the content hash supplied and native load call. Skill
   creation alone is not evidence of use; repeated history alone is not evidence
   of skill transfer. Versioning is evaluator bookkeeping, not an oracle that
   tells the algorithm how to forget or scope instructions.
6. **Candidate trials.** Replay incumbent and candidate on equivalent cloned
   pre-task world/filesystem/profile states. Execute actual Hermes tools and
   substantive grading. Trials do not consume live customer budgets, settle
   orders, change actor notes or mutate the deployed skill. Historical cases
   retain historical policy time; current tasks use current specifications.
7. **Splits.** Whole scenario seeds are assigned to development and held-out test.
   Within a deployment lifespan, previously available cases are deterministically
   divided into learning and validation pools with disjoint IDs. Separate
   prospective test work remains invisible to the optimizer until its online
   score is recorded; an offline held-out test case never enters the update pool.
8. **Changing requirements.** Test base rules, permanent changes, scoped temporary
   exceptions and reversals with varied parameters/timing. Publication and
   effective dates differ. Retention means keeping still-useful competence, not
   enforcing expired policy forever. Candidate validation and prospective drift
   evaluation answer different questions and are reported separately.
9. **Causal economy.** Match initial worlds and exogenous shocks across methods;
   regenerate endogenous institutional/consumer/employee decisions conditional
   on each method's outcomes. A fixed transcript is only an offline diagnostic.
   Do not overwrite obligations to make successful agents appear equivalent.
10. **Budget and failure.** Bound each agent turn, optimization cycle and run.
    Record failures and partial work. Checkpoint only at known boundaries and
    refuse ambiguous replay after interruption. Learning calls, validation calls,
    work calls, tools, tokens and wall time are separate. Missing monetary/actor
    usage is unavailable, never zero.

## Task and rubric requirements

Every work item contains inspectable source files and legitimate instructions,
requires actual computation/transformation, and produces a verifiable artifact.
The existing policy envelope remains necessary but is insufficient for success.
The trusted evaluator verifies the content before committing business effects.
Feedback identifies failed criteria without revealing the expected solution.

Rubrics must reject placeholder content, malformed JSON, omitted/duplicate
records, wrong totals, out-of-scope edits, inappropriate exception use and invalid
numeric values. Partial scores are bounded and accompanied by a strict success
flag. No model self-rating determines task success. Public files contain all
information needed to solve the task without containing its answer.

At least three families are required: reconciliation/onboarding, contract renewal
calculation, and incident/data repair. All employees receive recurring work; the
old distribution of 7/3/1/1/1/1 sessions is insufficient. Benchmark demand is
explicitly exogenous and documented; institutional reactions remain model-driven.

## Metrics and evaluation rubrics

Primary: pre-update strict task success and cumulative realized business utility.
Also report partial semantic score, work rejection rate, delay, unresolved work,
human assistance, policy compliance, skill adoption/rejection, skill-use evidence,
stale-rule failures and retention by workflow/regime.

Adaptation delay is measured from the first legitimately observable change to
subsequent correct work, with failures/censoring retained. Separate successful
completion after retries from first-attempt correctness. Report per-employee and
per-regime exposure counts before interpreting differences.

At the work horizon, stop new work and learning. Either settle already committed
work under a specified drain window or report unsettled rewards and pending
obligations separately. Never award future settlements twice or hide unfinished
work behind a successful-session denominator.

A strong SkillOpt baseline means a faithful optimizer/gate, adequate disjoint
experience, a valid starting skill, real execution, bounded but usable compute
and explicit accounting. Tune only on development worlds. A negative or flat
result is valid; one successful skill adoption is an integration milestone, not
proof of aggregate superiority.

## Milestones

- [x] M0: Active goal, explicit protocol and parallel implementation/review owners.
- [x] M1: Executable semantic tasks, rubric tests and deterministic scenario specs.
- [x] M2: Fresh-context Hermes and native versioned-skill execution with isolation tests.
- [x] M3: Actual pinned SkillOpt-Sleep consolidation and gates with isolated native
      replay; no edit was adopted in the live pilot.
- [x] M4: Persistent-world benchmark runner, causal feedback, recurring workloads,
      split/config manifests, budgets, horizon accounting and metric reports.
- [x] M5a: Bounded paired native pilot showing actual task execution, exact skill
      loading and conservative consolidation behavior.
- [ ] M5b (research follow-up): Full-workforce development calibration and a
      replicated comparison with adequate employee/regime exposure. The short
      pilot is insufficient and must not be relabeled as this milestone.
- [x] M6: Independent implementation review, material findings resolved, full
      relevant test suite, secret scans and committed/pushed release documentation.

## Validation ladder

1. Offline deterministic task/rubric, protocol, state isolation and cost tests.
2. Actual upstream SkillOpt tests with stub execution/reflection to prove gate
   behavior; clearly label stubs and never report their scores as live results.
3. Native Hermes tool smoke check with a skill loaded through its skill tool.
4. Bounded live world pilot; retain skill-load omission and declared budget
   exhaustion as behavioral outcomes. Fail on incomplete accounting, state
   contamination, infrastructure failures or missing evaluation evidence.
5. Paired development runs and reviewer audit before holding out new scenarios.

No single run establishes a frontier-research result. The deliverable is a
reproducible, reviewable evaluation system and validated baseline integration.

## Verified implementation checkpoint

Commit `47c7609` adds the controlled evaluator. Independent review passed 193
offline tests, including real filesystem/transaction fixtures over eight simulated
days, actual pinned upstream SkillOpt with fixture callbacks, rubric mutation
tests, chronology, isolated replay and paired-report audits. The upstream/local
verification script additionally passed 131 backend, 28 upstream integration and
18 local adapter tests, plus the frontend build. Both staged credential scanners
passed before publication.

A native Hermes smoke executed eight physically metered Responses calls with
69,852 total tokens, verified the exact deployed native skill content, and
committed a substantively correct artifact. This validates execution and
accounting; it does not demonstrate learning. The paired eight-day pilot completed
90 prospective work attempts and six native historical replays under the exact
28-file source manifest of `47c7609`. Both completed strict audits pass. Two
SkillOpt consolidation cycles retained the incumbent because their training
replays passed. A separate real optimizer smoke produced four edits that were
never deployed. No native learning gain is claimed.

Post-run review identified a reporting error: task availability was mistaken for
commitment placement, omitting three late-arriving obligations from the
no-learning denominator. Version-2 reporting preserves the original report and
corrects commitment/backlog accounting from the checkpoint. A separate evidence
fix preserves exact submitted raw bytes, including rejected submissions, even
after file rewrite/deletion. The updated lifespan suite passes 195 tests, and the
independent artifact/reporting suite passes 35 tests. Automatic reporting failure
also preserves completed execution evidence. See
[pilot results and evidence limits](EVALUATION_RESULTS.md).

The next development study completed 44 native calibration attempts, followed by
one K2/T2/V2 SkillOpt epoch. It produced four actual proposed edits, rejected the
candidate under the recorded non-regression gate, and retained the seed skill.
This establishes proposal and gate execution, not successful adaptation. The
[study report](LEARNING_STUDY_RESULTS.md) records calibration variability and the
predeclared fresh-task control; it does not mark M5b's world replication complete.

M5b remains the next comparative research stage. Difficulty/noise calibration is
now available, but repeated online updating, prospective reuse of accepted
skills, and independent world replication still need empirical evidence. Do not
manufacture an adoption to satisfy an integration milestone.
