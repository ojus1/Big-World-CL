# Independent evaluation review

Review date: 2026-09-10. This document records requirements and acceptance criteria for the transition from the published integration PoC to a deployment-time learning benchmark. A checklist item is a requirement, not a claim that it has passed. Implementation evidence must be recorded against a fixed source commit and experiment manifest.

The research question is whether an employee assistant learns reusable work procedures from its own permitted deployment experience and improves subsequent work under changing requirements, at an acceptable learning cost. A convincing result does not require SkillOpt to win. A null result, a regression after a policy reversal, or an optimization method that costs more than it saves can be valid findings.

## What the published PoC establishes

The published run establishes native MiroFish/Persona-conditioned actors, native Hermes execution, employee-specific persistent files, business transitions, and auditable trajectories. Its 14 reconciled Hermes sessions are unevenly distributed across six employees; four employees have only one session. No native skill-management invocation or persisted `SKILL.md` was demonstrated. The accepted run includes an infrastructure-interrupted attempt and early adapter changes, so it is not a fixed-code comparative trial.

The initial verifier in `lifespan/environment.py` checks procedure fields and recorded check names. `Computer.read_artifact` in `lifespan/computers.py` requires a nonempty content field, but does not establish substantive work quality. The ecosystem retains notes in both the simulated employee and Hermes. Its horizon preserves outstanding commitments and unsettled ledger entries. These are appropriate integration features; each needs an explicit experimental contract before comparative scores are meaningful.

## Priority and release gates

| Priority | Issue | Required resolution | Evidence to retain |
|---|---|---|---|
| P0 | A nominal no-learning baseline can learn through notes, home files, conversation databases, skills, caches, or employee prompts. | Declare and enforce each persistence channel. Use identical harness capabilities and initial skill content across methods. | State manifests before/after boundaries; tests with distinctive sentinel text in every forbidden channel. |
| P0 | A candidate can be evaluated from a different state or contaminate its incumbent/live world. | Fresh, separate candidate and incumbent branches with equivalent immutable input snapshots and separate writable state. | Input hashes, branch identities, before/after parent hashes, rejected-candidate cleanup tests. |
| P0 | Future rules, expected answers, grader code, held-out tasks, or premature rewards can reach an optimizer. | Construct learner-visible records by allowlist, schedule feedback by availability time, and keep test/evaluator state outside employee mounts and optimizer input. | Leak tests across observations, prompts, tool results, snapshots, feedback, archives, and error paths. |
| P0 | Nonempty prose or recorded check names can satisfy the rubric without doing the work. | Trusted executable content checks with hard validity gates, bounded artifacts, and independent negative cases. | Mutation tests, correct independent fixtures, hashes of submitted/evaluated bytes, rubric version. |
| P0 | A published result may call a custom rewrite loop or fixture “SkillOpt.” | Execute the pinned upstream optimizer with a native Hermes environment adapter; record the upstream revision, configuration and actual invocations. | Candidate proposals, edits, branch rollouts, accepted/rejected decisions, upstream provenance. |
| P0 | Horizon truncation, retries, or selective omission can favor one method. | Predeclare obligation accounting, settlement drain/censoring, model-error policy, and all-attempt cost accounting. | Ledger reconciliation, unsuccessful attempts, pending-work table, drain events and cost records. |
| P1 | Same-task history reuse is mistaken for reusable skill learning. | Add fresh-context probes with held-out task instances and deployed skill versions. | Skill creation → fresh-session reuse → post-change revision → reversal behavior. |
| P1 | Multiple dependent sessions inflate the sample size. | Pair by initial world/shock realization; compute uncertainty over independent world replicates. | Per-world scores, paired differences, interval procedure, missing-pair policy. |
| P1 | Environment changes differ for reasons unrelated to the treatment. | Match initial conditions, exogenous shocks, actor policy/configuration and randomness conventions; re-simulate endogenous reactions in each arm. | Scenario hash, external actor configuration, actor transcripts, event causes. |
| P1 | Optimizer feedback overfits a repeatedly queried validation set. | Separate chronological experience, candidate development, adoption validation and final evaluation. Bound selection queries and retain all query costs. | Split manifests, availability timestamps, query counts and complete selection history. |
| P1 | Sparse or trivial tasks cannot distinguish methods. | Recurring task families across stable periods, change, delayed discovery, expiry and reversal; calibrate difficulty before a held-out comparison. | Coverage table per employee/family/regime; baseline ceiling/floor report. |
| P2 | Economic/persona realism and generalization are assumed from fluent outputs. | Label constructed mechanisms and test held-out organizations, task mechanisms, timings and actor configurations. | Mechanism ablations, sensitivity analysis, persona provenance and limits. |

P0 gates block a credible head-to-head result. P1 gates block broad claims about continual learning. A runnable smoke test may precede these gates, but must be labeled as an integration check.

## Define the treatments precisely

“Frozen model weights” is not a sufficient definition of no learning: a frozen model can learn through persistent context, files and skills. Separate the employee assistant's private learning state from the world it operates in.

| State channel | No private learning | Skill-only learning | Full deployment learning |
|---|---|---|---|
| Model weights, execution settings, initial system instruction | Fixed | Same fixed executor | Same fixed executor unless a separately named weight-learning treatment |
| Current task, public procedures, authorized business records | Available | Same access policy | Same access policy |
| Private conversation history and automatic summaries | Fresh at each declared session boundary | Fresh | May persist; version and size recorded |
| Private workspace notes, shell/home artifacts, native memories, hidden caches | Cleared/reconstructed at boundary | Cleared/reconstructed, except approved skill artifact | May persist under declared limits |
| Native skill text | Fixed initial version, or empty in all arms | Only optimizer-accepted revisions persist | Declared learning mechanism controls revisions |
| Optimizer experience buffer | None | Own past permitted experience | Own past permitted experience |
| Simulated human/institution state | Continues as environment state | Same actor policy, reacting to this arm's outcomes | Same actor policy, reacting to this arm's outcomes |

The no-learning employee may reason from current evidence, retry within its normal work budget and use competent fixed instructions. Disabling basic reasoning or reducing its tools would create a weak baseline. Give both methods the same initial skill and executor budget. Report the optimizer's additional budget separately, and include a budget-matched execution baseline if making efficiency claims.

Operational state must survive a lifespan. The simulator may publish validated business records created by past work into future observations. Treat this as ordinary environmental persistence and expose it under the same rule in every arm. Arbitrary assistant-written notes must not be reclassified as business records to evade a private-state reset. If freeform committed code/documents are intentionally reusable, label that as an artifact-carryover setting: it does not isolate skill-only transfer. For the strict transfer setting, build the next workspace from a trusted business-state projection plus task-specific inputs and the permitted skill.

MiroFish employees can themselves retain improved working notes and give better requests over time. Keep that behavior explicit and equal in policy across arms. An improvement caused by a better human request is an environment effect, not evidence that Hermes learned a skill. A useful diagnostic evaluates the same task with and without the learned skill under a fixed employee request.

## Substantive task rubrics

Use multiple work families with independently generated task data, observable requirements and evaluator-held reference computations. Each task must have enough authorized evidence to be solvable; a hidden answer is legitimate, a hidden requirement that is never discoverable is not. When a policy is intentionally announced late, measure detection/recovery opportunities and recognize unavoidable failures before sufficient evidence exists.

Examples of suitable executable work:

| Family | Work product | Correctness gates | Drift and retention probes |
|---|---|---|---|
| Account reconciliation | Structured reconciliation derived from invoice/payment records | Correct joins, balances, duplicates/unknown-reference handling, rounding and exact unresolved-item sets | Schema/identifier changes, a temporary payment rule, new exception class, reversion with new records |
| Data/interface migration | Converted records or a bounded transformation applied to test inputs | Schema validity, field semantics, missing/null treatment, preservation of unaffected records | Renamed keys, changed units, scoped compatibility period, rollback without losing independent improvements |
| Incident triage | Structured affected-record analysis and executable remediation plan | Correct affected population, severity/SLA calculation, permitted remediation and preservation constraints | Revised severity policy, regional exception, expiry, incident with a distinct root cause |

The learner may receive public tool errors and declared validation feedback. The grader must not be a model-writable test file or a check that merely records an assertion of success. Bind preparation, review and final scoring to actual artifact bytes. Changing a prepared artifact must invalidate prior checks/approval. Validate structure and finite numeric values before scoring; reject missing, duplicate, unexpected or oversized items as specified. Where code runs, trusted hidden tests must execute outside the learner's writable test environment.

Use a rubric vector before a composite score:

- **Functional correctness:** required records and calculations are correct.
- **Scope and policy correctness:** the right authority, date, jurisdiction and exception apply.
- **Integrity:** unaffected business state is preserved and a committed artifact matches the reviewed bytes.
- **Completion and timeliness:** work reaches trusted completion within the available deadline and budget.
- **Assistance and cost:** clarification, execution, optimization, validation and rework are charged.

Critical integrity or policy violations should fail task success even if a weighted average looks high. Publish rubric weights/gates before the evaluation; retain components so a change of weights cannot hide a failure. A one-character mutation, deleted record, wrong unit, stale policy, forged check, and irrelevant verbose answer should each fail for the expected reason. Correct task solutions should be independently constructed rather than generated by the same function the grader calls.

## Temporal experience and candidate validation

Every experience/feedback record should carry `event_time`, `available_at`, `employee_id`, `task_id`, `source`, and whether it is learner-visible. An optimizer called at time `t` receives only permitted records with `available_at <= t`, scoped to the correct employee. A success acknowledgment can be immediate while payment/customer consequences arrive later. The implementation must not backdate later outcomes into an earlier update.

Use four distinct roles, even if an initial small study uses only some of them:

1. **Deployment experience:** the employee's actual past authorized observations, actions and revealed outcomes.
2. **Candidate development tasks:** permitted past/replay tasks used for proposing and revising a skill. They are training resources and consume budget.
3. **Adoption validation:** bounded feedback for selecting a candidate; every repeated query is logged. These data cannot simultaneously serve as an unbiased final test.
4. **Prospective evaluation:** subsequent work or held-out probes that were inaccessible during that candidate's selection. Evaluation outcomes may join later deployment experience only when the online protocol explicitly allows it; scores must be attributed to the skill deployed before the work.

Historical replay must restore the historical policy, task inputs and information boundary. A task completed during a temporary enhanced-review policy is not a valid current-policy retention test unless it is deliberately reconstructed with current requirements. A policy reversal can make a previously correct action wrong. Distinguish historical capability retention from stale-rule retention: the latter should be penalized.

Do not let the learner read scenario seeds, hidden future schedules, rubric implementations, expected outputs, or privileged diagnostics simply because those files exist in the controller checkout. Split IDs and future task filenames can themselves leak structure. Avoid exposing future probe membership. Canonicalize exported experiences by an explicit schema rather than deleting a few known private fields.

Repeated validation may produce adaptive overfitting. Bound candidate count and validation calls, use a disjoint gate where affordable, and report final prospective performance separately from the score that selected the winner. Learning from public errors is allowed; unrestricted oracle queries need a separate, labeled information budget.

## Candidate branches and Hermes deployment

Candidate and incumbent must execute through the same native Hermes tools, executor model, context policy and task interface. A chat-only surrogate is not a Hermes rollout. Each trial starts from an equivalent snapshot: business/task state, policy time, input files, permitted profile/skill state, pending effects, RNG conventions and execution configuration. Record the snapshot hash and the skill hash; only the intended skill treatment should differ.

Branches need separate writable directories, native profiles, process identities, sockets and environment caches. No branch may mutate the live queue, ledger, inbox, employee notes, API budget or parent skill. Stop branch processes before cleanup. Disk copying is not restoration of a live process tree: either validate at quiescent fresh-worker boundaries or explicitly constrain the state model. Hard links to mutable files are not isolated copies. Refuse unsafe symbolic links/path traversal, or snapshot links under a documented policy that cannot resolve outside the branch.

Adoption is an atomic, validated deployment step. Record parent/candidate/deployed version IDs, content hashes, evidence cutoff, optimizer configuration, validation outcomes, rejection reason, costs and subsequent sessions using that version. Ensure Hermes rebuilds its skill index/system context after adoption. The presence of a `SKILL.md` file alone does not prove it was available to or loaded by the executor. Record native `skill_view` use where applicable and the exact skill text/index included in the session prompt.

Resume must never silently adopt an unvalidated candidate, repeat a charged update without attribution, or replay work with uncertain committed effects. Test interruptions before/after candidate generation, validation and adoption. Preserve failed attempts in the audit trail. If exact continuation is not supported, fail closed with a clear checkpoint/restart contract.

## Ecosystem reactions and experimental units

For a fleet comparison, each algorithm gets a separate world initialized from the same scenario, Persona records, business files, actor policies and exogenous shock realization. Re-run consumer, enterprise and government decisions against that arm's actual outcomes. Replaying a competitor's downstream reaction from another algorithm's world would erase a causal pathway through which learning matters.

Use independent exogenous random streams or keys for initial conditions, task data, shocks and model sampling. Branching decisions must not shift the later exogenous event stream. Deterministic external event timing does not make hosted LLM calls reproducible; record sampling parameters, provider/model revision when available and actual transcripts. Pair by scenario seed but do not claim identical model randomness unless the provider guarantees it.

An employee-focused study can vary one employee algorithm while holding other agents' policies fixed. Its effect is still embedded in a reacting world. A full-fleet treatment answers a different question because one employee's improvements change others' workloads, cooperation and market conditions. Label the estimand and avoid interpreting fleet utility as an isolated employee treatment effect.

Sessions, employees and tasks within one world are dependent. Report per-world metrics and paired algorithm differences; estimate uncertainty by resampling independent paired worlds, or use a justified hierarchical analysis. Do not bootstrap individual sessions as independent samples. Report the number of worlds and employees in addition to the number of work attempts. A one-world paired run has descriptive differences but no empirical between-world uncertainty estimate. Pilot several worlds to estimate variance and choose a larger, predeclared evaluation size; a fixed small sample count is not automatically sufficient.

## Metrics, horizons and costs

The primary outcome should be subsequent trusted work success or business return, reported with costs. Keep skill-selection validation scores secondary. Recommended metrics are:

| Metric | Definition and caveat |
|---|---|
| Task success | Unique obligations completed correctly / all eligible obligations; retries are attempts, not new successes. Include withheld/unfinished work in an appropriate denominator. |
| Subsequent quality | Rubric components on tasks encountered after the update; group by stable/change/reversal regimes and family. |
| Adaptation delay | Number of eligible opportunities (and simulated time) between observable change evidence and a prespecified recovery criterion. Censor rather than invent a delay if no later task occurs. |
| Stale-procedure error | Failure attributable to applying an obsolete rule when newer authoritative evidence is available; report counts/opportunities. |
| Retention | Performance on still-relevant earlier capabilities using new task data; separate historical-policy replay from current-policy performance. |
| Business return | Reconciled delivery value minus operating/error/late costs under a fixed accounting contract; report simulator units separately from currency cost. |
| Assistance | Simulated human requests and minutes; distinguish actor generation cost from assistance charged to the employee. |
| Learning cost | All candidate generation, edits, replay, validation, rejected candidates, retries, exceptions and profile refresh calls. |
| Execution cost | All actual executor calls, tokens, latency and billable usage, including unsuccessful and interrupted attempts. |

Predeclare the action horizon and the outcome horizon. One defensible initial protocol stops new work and learning at day `H`, then drains already-caused settlements for a fixed `D` days without opening new tasks or taking new algorithm actions. Another censors unsettled outcomes and reports them explicitly. Do not count both an accrued receivable and its later settlement as separate value. Pending obligations, unresolved customer consequences and post-horizon penalties need declared treatment; the scorer must not make postponement an uncharged escape.

Learning and execution can run in wall-clock time while the world advances in simulated time. Declare whether learning consumes simulated work capacity or is an overnight budget. If learning has no simulated delay, report that assumption and its real latency; do not infer operational feasibility from accelerated simulation throughput.

Track input, cached-input, output/reasoning tokens, model requests, wall time, estimated currency cost and measurement completeness separately by executor, optimizer, validator and environment actor. Missing usage is `unknown`, not zero. Record the price-table date if estimating currency cost. Include unsuccessful candidate calls and infrastructure failures in cost totals even if their work results cannot be scored. Predeclare whether a service failure invalidates a pair or counts as deployment failure; never silently drop the worse arm.

## Acceptance checklist and evidence register

These gates should be accompanied by test names or immutable artifact paths as implementation proceeds.

### Runnable baseline integration

- [ ] A no-learning native Hermes run uses the declared fresh-state policy and succeeds on independently verified solvable work.
- [ ] The pinned upstream SkillOpt optimizer produces at least one bounded candidate edit and calls the actual native Hermes evaluation adapter.
- [ ] Candidate and incumbent receive the same non-skill inputs, model/tools and execution limits.
- [ ] A native Hermes session consumes an adopted skill version after its deployment boundary.
- [ ] Rejected/failed candidates cannot change the deployed version or live business state.
- [ ] Missing external dependencies/authentication fail explicitly; no fixture or heuristic silently substitutes for the named baseline.
- [ ] Configuration, revisions, prices/budgets and data provenance are saved without credential values.

### Isolation and information boundaries

- [ ] Canary state in history, memory, notes, OS home, shell snapshots, skills and hidden profile files cannot cross a no-learning reset.
- [ ] Candidate/incumbent/live-world isolation is checked with destructive writes to branch-local test files and parent hashes.
- [ ] Files, symlinks, native tool state and profile caches cannot expose another branch/employee or evaluator truth.
- [ ] Future events, expected answers and unavailable feedback are absent from all learner-visible surfaces and error paths.
- [ ] Cross-employee experience is rejected unless explicitly authorized by a separate shared-learning treatment.
- [ ] Candidate replay preserves the task's policy time and cannot settle or submit work in the live world.

### Rubrics and accounting

- [ ] Each substantive family has independently solved positive examples and meaningful negative/mutation cases.
- [ ] Wrong content cannot pass by supplying a valid wrapper, approval flag, plausible explanation or known check name.
- [ ] Missing/extra/duplicate/nonfinite/oversized outputs and attempted grader modification have specified outcomes.
- [ ] Artifact changes after preparation invalidate approval/checks; evaluated bytes are auditable.
- [ ] Each eligible obligation appears exactly once in task-level denominators; all attempts and charges remain visible.
- [ ] Immediate, delayed and horizon outcomes reconcile with the ledger and are disclosed on schedule.
- [ ] Candidate, validator, environment and executor costs include rejected/failed attempts and mark incomplete usage.

### Learning evidence and comparisons

- [ ] At least one employee demonstrates skill creation, reuse on new data in a fresh session, update after change and correct reversal/expiry behavior.
- [ ] Every employee/family/regime has enough eligible opportunities to interpret its metrics, or sparse strata are explicitly unscored.
- [ ] Current-policy performance, historical replay and retention probes have separate labels and denominators.
- [ ] Adoption validation and final evaluation are distinct; test outcomes cannot retroactively select the tested skill.
- [ ] Every arm re-simulates endogenous world reactions from its own observed outcomes.
- [ ] Paired-world summaries, all failures, uncertainty method and missing-pair rules are included.
- [ ] Results can be audited from fixed-commit manifests, task/rubric versions, skill hashes and native trajectories.

## Review status

This initial review is based on the published PoC implementation. It does not certify the new implementation or establish an algorithm ranking. Append implementation review findings and verified evidence after the new baseline, task rubric and runner code is available. A smoke run should be published as a smoke run, and a comparative experiment should remain explicitly provisional until its applicable gates are satisfied.

## Implementation review, first pass

The initial review of `evaluation/protocol.py`, `runtime.py`, `skillopt.py`, `tasks.py` and their Hermes/computer integration found these concrete issues:

1. A four-day configuration with the default odd seed generated an empty exception interval and failed task generation. The accepted configuration range must guarantee ordered, nonempty regime windows.
2. The original additive dev/test seed namespace overlapped for unrestricted input seeds. Seed validation or split-aware derivation must make the permitted namespaces disjoint.
3. Metering only `AIAgent._interruptible_api_call` misses the pinned Hermes iteration-summary path and internal physical Responses stream retries. Hermes can also increase a continuation's output cap beyond the nominal `max_tokens`. Logical `api_calls` therefore cannot establish the physical request budget or its total cost.

The bounded correction for issue 3 is `evaluation/budget.py`. It meters dedicated SDK clients at `responses.create`, wraps newly created request clients, disables SDK retries, clamps the actual wire output cap, and reads usage from terminal Responses stream events. Missing usage retains the pre-dispatch reservation and marks accounting incomplete. Auxiliary summary and compression inference are disabled in controlled trials. The meter exposes physical dispatch count separately from known usage and conservative charges; a reservation is never represented as measured provider usage.

Verification at this review checkpoint:

- 53 task/SkillOpt bridge tests passed, including independent public-input solvers, meaningful rubric mutations, real pinned upstream consolidation with deterministic execution fixtures, rejection, rollback and information-boundary tests.
- 12 transport-budget tests passed, covering output-cap increases, hidden retries, lost/invalid receipts, provider overrun, call/token refusal before dispatch, client factories and disabled auxiliary inference.
- A check using the installed OpenAI SDK and an in-memory `httpx.MockTransport` confirmed the actual Responses streaming wrapper, cap clamping, SDK retry setting and terminal-event usage extraction. No network or model request was made.

These results establish selected implementation contracts. The deterministic SkillOpt callbacks do not establish native learning improvement. The transport adapter still needs a metered native Hermes smoke run and fixed-commit evidence before a comparative experiment. A provider token overrun is detectable and blocks subsequent work; a conservative request reservation is not a provider billing guarantee. The runner, aggregate metrics and full lifespan comparison require their own subsequent review.

### Runner and report review findings

The second review found these concrete issues to resolve before accepting comparative output:

- **Atomic learning cursor:** the learning update's original `finish()` checkpoint included the updated skill and costs before the caller advanced `update_index`. A process exit between these writes could replay the same update on resume. Skill adoption, update evidence, charges and scheduler-cursor advancement must share the checkpoint that clears `INFLIGHT`.
- **Per-dispatch elapsed budget:** an outer-day time check did not bound the remaining actor/work/update loop. Learning epochs used the full configured maximum rather than remaining elapsed allowance. Check and cap each dispatch against the remaining run allowance. A run stopped by an immutable cumulative budget is not automatically resumable with that same budget.
- **Pairing provenance:** reports originally compared configuration and scenario but omitted target-model, harness/source and actor/provenance details that existed only in the manifest. Require a common treatment-independent comparison contract before accepting a world pair.
- **Completion evidence:** a completed world-task flag is insufficient without a matching successful audited work record and its ledger entry. Missing/duplicate completion evidence, success/world disagreement, overdue undelivered settlements and insufficient outcome horizon must invalidate the relevant audit instead of merely appearing as informational counts.
- **Fleet budget allocation:** one shared learning pool consumed in sorted employee order can leave later employees with no updates. Per-employee exposure, spending and accepted-update counts must be visible; a focal-employee study or fair allocation avoids implying all employees received comparable learning opportunities.
- **Behavior versus infrastructure:** omission of a requested `skill_view` can be model behavior, rather than a broken transport. Either load the deployed skill deterministically through the harness, or score and label that protocol violation without treatment-dependent silent attrition.
- **Committed artifact identity:** the first runtime reread the mutable prepared file after the native conversation ended. A successful commit followed by a terminal edit could then archive ungraded content as a validated business record. This was reproduced offline with the real `Computer`, `SessionEnv`, content grader and an independent public-input solver. Preserve the bytes accepted by the trusted commit, and build business carryover from that immutable snapshot; do not reread a mutable path to establish past committed content.
- **Native actor resume:** clearing MiroFish's `started`/`social_round` markers and restarting the same native simulation does not restore it. The pinned Reddit runner deletes an existing `reddit_simulation.db` before resetting its environment. A safe native pause must preserve and reconnect to the live actor process, or use a real supported restore path. Never silently restart actors and call that an equivalent continuation; preserve native evidence before any restart.

Historical replay restoration, separate fresh rollout directories, employee-scoped experience selection and the recorded chronological availability cutoff were present in the reviewed runner. These observations do not substitute for native interrupted-run and branch-isolation tests. Resolved issues should be linked to regression tests and fixed-commit run artifacts; this section records the review findings, not an assertion that every fix has already passed.

### Fix verification before the native world pilot

The follow-up source review verified these corrections:

| Finding | Verified correction / regression evidence |
|---|---|
| Invalid short horizon and overlapping split seeds | `ExperimentConfig` now requires at least eight days and integer seeds in `[0, 1000000)`. Protocol tests cover both seed extremes and every horizon from 8 through 36 days. |
| Post-commit artifact mutation | `Computer.action` freezes `committed_artifact` and `committed_hash` when trusted commit succeeds. `execute_case` returns that snapshot. `test_quality_is_checked_before_business_and_commit_snapshot_is_immutable` reproduces and blocks ungraded carryover. |
| Native actor database reset | `NativeActors` refuses a closed or no-longer-live environment, preserves the running native process on a clean invocation pause, and reconnects using the environment-status API. Restarting a dead native actor environment remains unsupported rather than silently resetting it. |
| Atomic learning checkpoint | The accepted version, cost/update records and `next_update_index` are set before the checkpoint that clears `INFLIGHT`. Failed/incompletely accounted learning leaves the marker for reconciliation. |
| Version-history overwrite | Only accepted updates write a new version file; rejected updates retain the deployed version's original metadata. |
| Learning-pool duplicates | Experience selection deduplicates source obligations and respects task/feedback availability, with a protocol regression test. |
| Elapsed and startup bounds | The runner uses remaining elapsed allowance per dispatch, installs the native actor deadline before bootstrap, and caps worker startup. A deadline regression that changed GET requests into POST was corrected and tested. |
| Fleet starvation | Per-employee quotas prevent earlier employees consuming the whole pool. Reviewed defaults allocate 480 learning calls and 6 million learning tokens per employee in the six-employee fleet; these are upper bounds, not measured consumption. |
| Skill-use attribution | The audit compares the exact installed skill-file hash to the native `skill_view` result. Missing skill use is recorded as behavior; it no longer automatically invalidates infrastructure. |
| Transport bounds | The controlled worker installs the physical Responses meter. Provider overruns invalidate infrastructure; ordinary bounded stops remain distinct from missing receipts. |
| Comparative evidence | Reports now carry treatment-independent provenance, reconcile task completion and ledger evidence, require the declared settlement observation window, and reject incompatible or incomplete pairs. |

The reviewer independently inspected `lifespan/artifacts/evaluation-native-meter-smoke-v1/session.json`: the exact installed skill-file hash appeared in the native tool result; substantive score was 1.0 with a successful trusted commit. All eight physical Responses dispatches had valid terminal usage receipts, totaling 69,852 tokens. No budget overrun, blocked dispatch or auxiliary inference was recorded. This is one native runtime smoke check, not a SkillOpt learning result or a world-level algorithm comparison.

The live world pilot must still validate the combined native actor/employee/optimizer loop and its prospective evidence. In particular, a passed source/fixture review does not establish an accepted skill improvement, safe native pause/reconnect under a real interruption, or enough independent worlds for comparative claims.

Final checks before interpreting the pilot:

- `python3 -m unittest discover -s lifespan/tests -q` passed **193 tests in 37.659 seconds**. This includes the actual-filesystem offline runner fixtures, protocol and post-commit regression tests, transport tests, pinned upstream SkillOpt bridge, optimizer transport and paired-metrics audits. Offline fixtures are not labeled as native model evidence.
- Final-day consolidation is excluded: an update cannot be charged after the last useful workday when its deployment date lies beyond the action horizon.
- Evaluation profiles explicitly disable skill template substitution and inline shell preprocessing, preserving exact skill-content attribution and the declared tool execution boundary.
- The initial paired native pilot at source commit `47c7609` used matching scenario, source hashes, target model/provider configuration, dependency provenance and Persona cohort hash in both arms. Independent native actor decisions were present in both runs at review time. Work and learning outcomes were still in progress and were not used to assert an algorithm ranking.

The first day-0 onboarding work record subsequently completed in each arm. The reviewer verified successful trusted commits, substantive score 1.0, exact loaded skill hashes and complete physical usage receipts: 7 calls / 66,822 tokens for no-learning and 9 calls / 92,645 tokens for SkillOpt's initial fixed-skill execution. Both frozen committed artifacts independently passed regrading against their saved case. These precede any SkillOpt update and provide integration evidence only.

This pass identified no remaining high-impact blocker to starting the bounded native pilot. That assessment applies to the inspected source and verified contracts, not to unobserved pilot outcomes or the broader scientific claims in the acceptance checklist.

## Completed native pilot and post-run evidence review

Both arms completed the eight-day action horizon and two-day outcome window at execution source `47c76094334ae139a246f462a2c25edf5d5aba3d`. The independent artifact auditor passed all 43 prospective no-learning sessions and all 47 SkillOpt sessions, including the two SkillOpt updates and six historical replay sessions. Neither run contained an uncheckpointed work session, an unreconciled learning directory, a failure marker, an invalid physical-usage receipt, a missing accepted-artifact object, or a completion/settlement disagreement. The strict pair check accepted one development world pair and returned no confidence interval. These are evidence-integrity results, not a learning-effect estimate.

Every deployed employee skill remained version zero. Both consolidation cycles reached the upstream no-change path after successful historical replays, with no optimizer proposal request and no adopted edit. The outcome differences therefore cannot demonstrate the benefit or harm of learned skills. The separate optimizer smoke is transport evidence, and the failure-selected incident diagnostic is exploratory calibration; neither belongs in the prospective pair. The reviewer inspected [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md) and found its scope, outcome counts, zero-adoption disclosure, cost exclusions and replication limits consistent with the retained evidence.

The independent audit checks checkpoint/disk equality, installed skill bytes and the matching native load result, per-employee version chains, the configured feedback-delay floor and update cutoff, train/validation source separation, immutable raw committed artifacts, trusted substantive regrading, physical dispatch equations and totals, replay/optimizer receipt reconciliation, regenerated reports and ledger eligibility. Its report comparison permits only finite floating-point roundoff at relative/absolute tolerance `1e-12`; JSON structure and types, integer counts, booleans, strings and null remain exact. Tests reject meaningful score changes, nonfinite values, count/type changes, forged load receipts, altered artifacts, future or cross-employee experience, unaccounted replays and report/ledger tampering.

### Commitment denominator correction

Independent reconstruction from `order_placed` events and consumer history found 48 pre-horizon commitments in the no-learning world and 49 in the SkillOpt world. Initial conditions and documented exogenous demand supplied 48 in each arm; one native consumer decision added a SkillOpt-world order. No-learning completed 36 commitments and SkillOpt completed 33. Three no-learning orders were placed on day 5 but became available on day 8, after work stopped. Version 1 counted availability rather than placement and consequently omitted those three obligations from its denominator.

The corrected commitment rates are **36/48 = 75.00%** and **33/49 = 67.35%**. On the fixed initial/exogenous subset they are **36/48** and **32/48**. These arithmetic corrections preserve the original sessions, rewards, task outputs, business balances and `REPORT.json` files. The versioned postprocessor joins scheduled and materialized task records by `(firm, task_id)`, gives materialized state precedence over the immutable template, retains unavailable/unmaterialized commitments and binds the derived report to the original report and checkpoint hashes. Its partitions and actual-run totals independently reconcile. Source attribution follows causal order events, rather than assuming that all synthetic work came from native consumer decisions.

The corrected comparison still has one world pair and no interval: it supplies descriptive commitment and fixed-demand differences alongside the original actionable-work comparison. It does not turn different endogenous demand or sampled downstream world paths into independent employee observations.

The final reporting review verified completed-only/in-flight guards, causal actor/day/target-firm checks for demand attribution, byte-preserving versioned writes, raw input hashes, and an exact match between the recorded processor hash and the actual local processor before regeneration. Paused/failed input cannot prematurely finalize an immutable v2 report. The **19 reporting-correction tests** passed together with **16 artifact-audit tests** in a combined **35-test** offline run. Both native v1 strict audits and both v2 correction audits passed again against the final checkpoints. The reviewer then loaded the final raw-file v2 reports, verified processor SHA-256 `56e346e2342fa930b6ee98dcc069e758595e4db4115a639b6c8a6aa0e8d2664b` and both source-file hashes, and independently regenerated the saved comparison. The corrected pair contained no rejected or incomplete pair.

The automatic v2 runner hook initially placed postprocessing inside the catch that rewrote execution failure status. Review identified that a derivative-report exception could overwrite a valid completed v1 report. The correction introduces a separate `ReportPostprocessingError` and `REPORTING_FAILURE.json`, preserving completed execution bytes and checkpoint while surfacing the derivative failure. The real-filesystem injection test verifies those exact bytes remain unchanged and that no execution `FAILURE.json` is written.

### Exact submitted-byte evidence after the pilot

The pilot preserved raw accepted objects for every successful commitment. Its seven no-learning and fourteen SkillOpt failed sessions did not all retain an immutable last rejected output, so the auditor explicitly leaves their partial substantive scores unsupported by independent regrading. Their failed completion status remains in the denominators; missing historical bytes are not reconstructed or silently credited.

The subsequent computer/runtime hardening persists each validated envelope's exact bytes in the trusted object store before grading, verifies existing objects rather than silently accepting collisions, records the last substantive submission hash, and resets that state between runs. Regression tests rewrite/delete both rejected and accepted workspace files and verify that the original bytes survive without relying on a later filesystem snapshot. The auditor regrades the optional last-submission object against the saved private case even when business commit failed; a null hash must correspond to the explicit ungraded default. Legacy records without this field retain the evidence limitation.

Historical verification remains strict after this evidence-only change. The auditor no longer imports mutable runtime helpers for usage or skill-load interpretation; it independently checks the primitive receipts. The trusted task grader, report builder and world restoration modules must still match the execution manifest's exact source hashes. A future change to those grading/reporting modules requires the matching historical source, rather than relaxing the source check.

The reviewer independently ran **194 offline lifespan tests in 30.35 seconds** after the byte-persistence change. After the final automatic-reporting guard, the coordinator reported **195 lifespan tests passed in 38.69 seconds**, including the injected derivative-failure regression; the reviewer separately ran the **35 audit/reporting tests**. Offline acceptance of synthetic skill edits is implementation evidence only. No release-blocking execution inconsistency remains in the completed native artifacts, versioned reporting or reviewed evidence hardening. Native adopted-skill improvement, reversal retention, calibration and replication remain unverified research acceptance gates, rather than claims established by this pilot.

## Calibration and frozen-skill transfer design review

The next development calibration selects the first historical session by employee/regime identity and time before attaching its original outcome. The source supplies 22 cells and 20 underlying obligations, producing 44 planned native repeats. Repeated regimes of the same obligation do not create additional independent tasks. Two seeded permutations counterbalance execution order; every planned slot remains in the report, and infrastructure or time-budget stops leave explicit missing attempts. The reviewer independently audited the first completed native repeat: an unsuccessful substantive attempt with score 0.571429, 14 physical calls and 172,949 reported tokens, exact seed-skill load provenance and reproducible immutable submitted-artifact grading. That establishes first-slot integration only; it is not a completed calibration or a learning result.

The proposed transfer stage is conditional on complete, independently audited calibration. Employee selection uses the declared failure-count/tie-break rule among employees with two distinct historical training and two distinct historical validation obligations. It preserves the existing experience selector's original obligation order and its latest observed retry content. This is outcome-selected development work. Four fresh future capsules are frozen before one historical learning epoch; none may enter upstream training or validation. The subsequent 16 counterbalanced seed/deployed probe attempts all execute, including identical-skill A/A runs when no edit is adopted. These fixed-environment probes measure frozen-skill transfer and retention; they do not constitute a new reacting world, another adaptation cycle, or a final-test comparison.

The independent transfer auditor verifies current recorded execution/dependency revisions, source and calibration raw hashes, reconstructed selection and probes, exact experience/capsule identity and availability, all learning and probe native receipts, immutable last-submission grades, arm-specific installed skill hashes, and regenerated aggregate reports. New failed sessions must retain last-submission evidence. It reconciles the separate epoch and probe charges with the combined 456-call / 8-million-token reservation ceiling. An incomplete learning epoch explicitly has `accounting_verified=false`; its structural consistency cannot justify treating unverified low usage as measured cost or deploying its candidate. Strict completion requires all 16 valid probe receipts and no unresolved execution artifacts.

Gate acceptance is also independently reconstructed from the native replay scores. The audit checks the exact K2/T2/V2 phase/task/sample schedule, mixed metric with weight 0.5, candidate trial and fresh final validation against the original baseline, strict mean improvement, and per-task non-regression. A noisy final improvement with no applied edit still rejects. A tentatively accepted candidate whose final replay regresses rolls back. Budget-exhausted prefixes retain the distinct `reject_incomplete` result and cannot claim adoption. Raw comparison decisions use the upstream strict inequalities; only report serialization comparison allows tiny floating-point roundoff.

At this review point, `python3 -m unittest discover -s tests -p 'test_transfer*.py'` passed **70 offline tests in 10.08 seconds**, including **23 independent audit tests**. These include actual pinned-upstream consolidation with deterministic fixture callbacks and tamper cases for forged acceptance, weakened gate metric, final regression, a mean improvement that sacrifices one validation task, wrong arm skills, altered source/capsule/session bytes, incomplete schedules, hidden costs and invalid phase transitions. Fixture outcomes are not native model evidence. No remaining implementation blocker was identified for preparing the bounded transfer diagnostic after calibration completes; native epoch and probe evidence must still pass their strict audits before any result is reported.

## Completed calibration and transfer study: publication signoff

The reviewer independently reran the final strict calibration, learning-epoch and transfer audits. All **44 calibration attempts, 12 historical learning replays and 16 fresh probes** passed their evidence checks, with no missing or invalid receipts or unresolved execution markers. The calibration yielded 31/44 strict successes and three discordant repeat pairs among 22 cells. The single native optimizer proposed four edits. Its candidate improved the validation mixed mean from 0.71666675 to 0.73333325, but regressed on a previously successful task; independent score reconstruction confirmed rejection under the declared per-task non-regression gate. Fresh final validation used the original skill, and no edit was adopted. The original source files and world, the four withheld probe capsules, and the published execution-source bindings remained unchanged.

All future probes loaded identical seed-skill bytes in both arms. The arm labels scored 7/8 and 8/8, with one discordant matched pair; this is an A/A control observation and establishes no learning gain or efficiency improvement. The entire bounded study contains **72 native work/replay attempts, 757 physical calls and 8,586,738 measured tokens**. One call was the optimizer; 756 were target-agent calls. The per-phase, per-arm and combined totals reconcile with raw receipts. Currency, the original pilot and historical actor-generation costs remain outside these totals. These are dependent, outcome-selected development observations, not independent world replication or a population comparison.

The reviewer checked [LEARNING_STUDY_RESULTS.md](LEARNING_STUDY_RESULTS.md) and all four public calibration, taxonomy, learning and transfer summaries against the audited private artifacts. The published report contents and raw evidence hashes match; outcome counts, gate scores, failure categories and cost arithmetic reconcile. Public fields contain aggregate outcomes, synthetic identities, check categories and hashes, with no raw requests, workspace contents, rubric answers, model/optimizer transcripts, skill text or credential-pattern matches. All 38 transfer execution-source hashes match preregistration commit `02eab32786d493ae5a8f5201fb24ddd32cd04179`. The reviewer independently inspected successful GitHub Actions run `34414505316` for that commit: **346 tests ran, 345 passed and one Persona-import test was skipped** because the cohort was not downloaded in CI; its four suites ran 204, 35, 37 and 70 tests.

The frozen v1 outer auditor leaves its generic `accounting_verified` field at its default `false`; only the learning helper sets that field. This is a metadata omission, not an unreconciled receipt or score correction: the strict outer audit verifies all 16 native probes and combined totals and returns `valid_completed`. The public transfer summary preserves original audit/score hashes, explains the omission, and records separately verified epoch, probe and combined-accounting facts. No execution code, original audit file, score or measured cost was altered to change the result. No publication-blocking inconsistency remains in the reviewed evidence or summaries. An adopted skill with validated prospective benefit, repeated deployment-time updates and independent reacting-world replication remain future research acceptance gates.

## Multi-seed reacting-world study: pre-execution review

The larger development study preregisters seeds 211, 307 and 401, paired no-learning/SkillOpt arms, four firms, 12 employees, eight consumers and one agency per world. All six worlds retain all employees and run for 20 work days. Explicit learning boundaries are days 3, 7, 11 and 17: day 3 cannot yet supply four distinct released obligations, and day 17 can use reversal feedback from days 15–16 before work on days 18–19. The primary endpoint is the equal-world mean difference in fixed initial/benchmark commitment fulfillment. Three world pairs are descriptive replication; employee sessions, retries and replay samples do not become independent world units. No outcome-conditioned replacement, extension, stopping or employee filtering is allowed.

The independent campaign auditor binds all six slots to their exact source/dependency/configuration hashes and three disjoint, paired persona cohorts. Completed runs must pass native immutable-artifact regrading, installed-skill provenance, full upstream gate reconstruction, v2 commitment-report verification and independent eligibility/exposure reconstruction. Every additive replay/progress record is linked to its raw capsule, session, phase, attempt/sample identity and budget operation. The selected historical pool must match the declared selector and the actual optimizer inputs. Per-epoch, employee-lifetime and fleet budgets are checked separately. Actor logical requests reconcile with cached responses and enacted decisions; physical actor calls and tokens remain unknown. Unfinished or invalid worlds stay visible and cannot be scored as behavioral failures.

Strict campaign completion additionally requires six supervisor exit receipts and confirmed shutdown receipts bound to each world's own native environment. A cleanup error preserves already verified employee-compute totals and is explicitly distinct from model quality. Bootstrap checkpoints preceding initial skill-file creation are reported as initializing. The reviewer ran **19 new scale-auditor tests in 2.42 seconds**, including actual pinned-upstream K2 consolidation with synthetic physical receipts and tamper tests for quotas, raw session bytes, optimizer receipts, selected pools, cohorts, source revisions, eligibility logs, incomplete campaigns and cleanup. These fixtures establish implementation checks, not native learning efficacy. The new transfer-auditor revision also sets the completed accounting flag correctly; its 23 audit regressions passed, and historical execution artifacts remain unchanged.

No remaining launch-blocking issue was identified in the reviewed protocol, supervisor, population integration, independent exposure summary or evidence checks. This signoff permits freezing and preparing the declared campaign; it does not establish adoption, prospective benefit or an all-in compute measurement. Native results require a fresh strict audit after execution.


## Scale study launch verification

Execution launched after publication of commit `b72fdda` and the exact prepared
campaign hash. Independent read-only review verified all 34 execution source
hashes, current dependency provenance, 75 distinct imported synthetic personas,
identical profile bytes within each pair, and six distinct native MiroFish
project/graph/simulation identities, live actor processes and SQLite databases.
Each world compiled 25 profiles. The startup campaign audit reported incomplete
with no integrity errors. All 417 local tests passed; GitHub CI run 34424931008
also passed (its explicit Persona-import skip does not represent a native test).
This is bootstrap verification; employee learning outcomes remain under study.
