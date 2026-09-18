# H200 remediation and staged experiments

## Resilient v35 — September 18, 2026

The v34 study failed after native inference settlement consumed most of the
grading window. New task actions had stopped at the active deadline; the
bounded settlement was not additional task execution. Replay admission now
reserves active work, settlement and worker termination plus a separate
300-second grading allowance. For 1,800 seconds of active work this requires
2,725 seconds per replay; the large epoch allocation is 55,200 seconds. Existing
token/call limits and grading schemas remain unchanged.

New studies default to `record_and_continue`. Ungraded attempts retain known
usage and unknown-cost reservations. Failed decisions defer an opportunity;
failed learning keeps the prior skill and permits later scheduled updates.
Independent arms proceed after arm failures, while missing pairs stay
incomplete. Manual cancellation remains honored. Reports and audits distinguish
operational completion from complete grading or measured accounting. See
[the continuation contract](SIMULATION_RESILIENCE.md).

Frozen `d7139de240019937aab49125c1a5e9b1634ca407` passed 295 H200 tests with no
skips and a predeclared six-day native paired pilot. All ten online attempts,
ten interviews, six learning replay records and causal/failure ledgers passed
offline audit. Four injected faults were retained without stopping later work:
one grade, two employee decisions and one learning replay. After the failed
day-2 epoch, day 3 completed five replays, 48 calls and 282,435 measured tokens.
No optimizer proposal was generated on the full-score training cases; the
unchanged-skill gate rejected adoption and skipped confirmation. Both planned
pilot probes expired behind backlog, remaining in the denominator. The scope
is operational recovery, not representative performance or learning benefit.

Fresh grading of a copied v34 output completed in 55.04 seconds, eight calls and
73,860 tokens; full artifact/grading audit passed. The original partial grade
and unknown usage were not replaced. Original v34 receipts and stop state retain
their hashes. Native raw review preserved ordinary model errors too, including
recovered container-path tool errors and an inaccurate final-chat description of
a correct saved artifact. No new source task or grader rule was introduced.

The fresh six-pair study started at 10:25:32 UTC (15:55:32 IST), with the existing
Qwen3.8-Flash-Next-FP8 service and concurrency 64. It uses fresh actors and seed
skills. The failed v32/v33/v34 studies remain separate. Fluso remains paused and
reserved final EuroBench remains unopened. See the
[timestamped current status](WORLDLAB_CURRENT_STATUS.md).

## Historical v34 qualification and startup

The startup account below predates the subsequent v34 failure. Its frozen
qualification evidence and original study remain preserved.

The v33 study failed on September 17 after three native learning replays
completed without calling `skill_view`. Their native usage remained available,
but validation raised before finalizing attempts and the learner retained full
reservations. The run is preserved as failed, with 608 online attempts, 264
finalized replays, 21 completed updates and three failed updates. None of the
six pairs completed.

The qualified v34 repair preloads the deployed skill through the pinned
native reader, verifies its exact bytes, and checks its presence in every
physical Responses request. `SKILL_CONTEXT.json` retains startup provenance and
the exact instructions; each metered dispatch binds their hash. This is harness
startup, not a fabricated model tool call. Missing or changed context prevents
inference and grading. Execution validation failures now finalize ungraded
attempts and preserve independently known usage through the learning ledger.

Qualification passed 305 H200 tests with no skips, all three exact failure-context
reruns, and a complete 12-replay learning epoch. All 15 native attempts, 181 work
calls, grades and usage records passed their audits. The candidate regressed
in final validation and was rejected; confirmation was correctly skipped and
the seed skill retained. Total fresh qualification usage was 275 calls and
4,300,637 tokens. This is operational qualification, not a learning-effect claim.

The v34 evidence archive contains 835 hash-verified evidence files plus its
manifest (836 regular files total), with SHA-256
`71e0c31ec6cd44064a8d39c4f3c96b503017f7f54de0537d4d8ddeb5d29e0ca1`.
It contains completed qualification and fixed large-startup metadata, excluding
runtime homes and scratch files. The replacement started at September 17,
21:57:38 UTC; startup verification confirmed six fresh actor simulations and
64 concurrent inference requests. The study remains in progress.

Historical qualification: the v33 restart passed on September 17. Its source is
`cfe42f4cbedddb189733b63a9ae6a2657e7a6499`. A rejected artifact's
`public_requirements: null` now preserves the original zero, feedback and actual
usage through learning. The existing single judge-format retry uses a finite
structured recovery schema that retains all decisions and evidence choices,
while replacing open-ended rationale generation with an explicitly disclosed
fixed label. Valid verdicts and unknown-usage failures cannot trigger this retry.

All 266 H200 worldlab/optimizer tests passed. Live qualification retained all
12 positive/negative controls, three exact truncated-criterion repetitions, a
complete copied-workspace grade with an actual repair, and a complete 20-replay
learning epoch. Native artifact, context, optimizer, ledger and admission audits
passed. The candidate was rejected after confirmation mean gains of +0.083333
and -0.041667; the seed skill remained deployed. The qualification consumed
9,059,860 tokens and 463 model calls for the full learning epoch.

Same-model semantic judgments remain provisional. The grant-allocation source
register totals EUR 1,525,000, whereas its task premise and board minutes state
EUR 1,400,000; frozen inputs and grades were not rewritten. The rejected sorting
proposal was broader than its source-policy sequence. The replacement large
study starts independently and does not inherit that proposal or qualification
history. The failed v32 study remains separate and incomplete.

The historical v33 restart's evidence archive contains 1,183 verified regular files
and has SHA-256
`9eaf9240c90e8237e8f80c8ae544097528e030d2527dce9c570483b4a8bd2b01`.
It contains qualification and fixed startup evidence, not completed large-run
results. [Timestamped restart status](WORLDLAB_CURRENT_STATUS.md) supersedes the
historical stages below.

## Historical remediation plan and stages

Started 2026-09-16 following the frozen v10 deep QA. This plan authorizes no
reinterpretation of v10 outcomes. Each native stage uses a fresh artifact root,
frozen source/configuration, the already served Qwen3.8-Flash-Next-FP8 revision
236dfdf285828023ca3bcd3f37366c58a3469b13, and the existing 64-request gateway.
Fluso work stays paused. Reserved final EuroBench tasks stay unopened.

## Fix order and acceptance criteria

| Finding | Change | Required evidence |
|---|---|---|
| G1 false supplier note-length judgments | Source-bound CSV parsing and exact Unicode character counts; judge only the remaining language/substance conditions of R7. Preserve original rubric weight and conjunction. | Boundary, quoted-comma/newline, malformed CSV, changed-source controls; saved false-count cases; fresh semantic controls. No automatic semantic pass. |
| G2 unexplained integrity zeros | Explicit artifact-contract verdict and actionable paths in feedback, identically recomputed by audit. Keep declared output/scratch contract. | Passing rubric plus forbidden helper file yields zero with the actual reason; input deletion/change/link is detected without reading link targets. |
| G3 artifact rejection aborts study | Convert recognized candidate evidence violations into metered, auditable failed submissions before model judging. Infrastructure and unknown errors still fail closed. | Symlink, undecodable/binary output and malformed archive controls finalize ATTEMPT with known solver cost and zero judge calls; no unsafe traversal; tamper audit rejects changed artifacts. |
| S1 premature work charges | Admit and charge work at dispatch, not employee delegation; bind causal audit to the correct earlier decision. | Peer cancellation before dispatch leaves zero work starts/costs; completed and partial causal replay; concurrent wave ordering. |
| S2 misleading progress | Separate finished workers from successfully completed pairs. | Failed and cancelled workers never increment completed pairs. |
| L2 overbroad skills/false approval claim | Versioned scoped proposal contract, current-task precedence and truthful automatic-gate banner in the adapter; preserve pinned upstream source. | Invalid edit policy rejected with preserved optimizer cost; exact candidate bytes replayed and audited; semantic QA of every pilot adoption. |
| L1 noisy two-case gates | Measure unchanged-skill repeatability after grader fixes; introduce a prospective independent confirmation stage before adoption. | Complete repetitions retained including losses; all confirmation costs audited; no retry-until-pass or effect claim from adoption counts. |
| L3 incomplete epochs and slow roles | Size epoch budgets for the full planned replay sequence and judge reservations; profile slow operations tasks; equal work budgets between arms. | Pilot has no admission-only truncation and no systematically starved role; complete gates, measured utilization/latency and role-level exhaustion rates. |
| Decision inconsistency | Make obligation identity, task-local completion evidence and employee tool capabilities explicit in actor views/prompts. | Native decisions retain exact view binding; no claims of inspecting unavailable files; similar completed tasks cannot close current obligations. |
| Coverage and realism | Qualify runnable JobBench tasks separately; include only qualified tasks with honest split/role coverage. Preserve sparse calibration and explicit simulation limits. | Source and split isolation audit; actual native artifact receipts for each added capability; no web/PDF/app-state claim without qualification. |

## Stages and stop conditions

1. **Offline regressions.** Implement the fixes, run relevant tests and the
   broader worldlab/learning tests once; freeze a source commit. Save the test
   command, result and source identity. Do not rewrite failed v10 artifacts.
2. **Small native qualifications.** Regrade copied saved cases under the new
   contract; run predeclared pass/fail controls and a small task panel on the
   existing server. Include the symlink regression, supplier notes, slow French
   operations, and qualified JobBench coverage. Gate on complete usage and
   artifact audits, exact mechanical outcomes and semantic review.
3. **Matched pilot.** Run a small number of complete learning/control pairs,
   with an update followed by untouched probe tasks and unchanged-skill
   repetitions. Cover research, French/German communications and operations;
   examples may cover only a subset of employees. Freeze selection, budgets,
   order, confirmation rule and analysis before launch.
4. **Repeat deep QA.** Audit every attempt, employee decision, update, cost,
   source binding and causal transition. Inspect all proposed/adopted skills,
   all artifact failures, gate disagreements and a stratified set of raw
   trajectories. Any blocking defect requires a new version and targeted
   regression/pilot; retain the earlier failure.
5. **Larger development study.** Launch only after all preceding gates pass.
   Freeze the full workload and paired analysis before launch, including
   budgets derived from the pilot, coverage limits and failure policy. A
   completed study and independent semantic calibration are prerequisites for
   any strong learning-effect claim; launch alone is not evidence of benefit.

Large-run go/no-go: zero missing receipts or unexplained accounting, zero
mechanical-control errors, no silent integrity feedback, no unexecuted charged
starts, all pilot arms and adoption confirmations complete, source/split
audits clean, and no unresolved harmful skill generalization. Report measured
solver/judge variability and budget exhaustion rather than claiming they vanish.

## Execution record

Implementation and native evidence will be appended here as each stage closes.

### First implementation revision

Implemented source-bound R7 decomposition (all five existing language variants),
auditable candidate-evidence rejection in both rubric adapters, truthful artifact
feedback, dispatch-time starts, correct progress counters, explicit actor
capabilities/task-local outcomes, structured scoped edits, an adapter-owned
truthful learned-block banner, separate-task repeated confirmation, and complete
epoch reservation checks. UTF-8 CSV evidence preserves embedded CR/LF for exact
character counts. No arbitrary generated-text length limit was added.

Confirmation selects the last two of four prospectively compiled validation
families. They never enter upstream reflection or proposal validation. Each
accepted upstream proposal is tested on two fresh baseline/candidate repetitions
per confirmation family. Adoption requires no individual case regression and at
least 0.05 mean mixed-score gain in each repetition. This is a conservative
development veto, not a significance test. Rejected proposals and all completed
draws retain their costs. Pinned SkillOpt source files remain unchanged.

Local verification: 203 worldlab tests passed (9 environment-dependent skips),
23 learning tests, 16 optimizer tests, 9 provider tests, 9 deadline-observation
tests and 16 evaluation-audit tests passed. The latest 10-case targeted artifact
suite additionally covers complete ATTEMPT finalization with known solver usage.
Commands and logs are under `lifespan/artifacts/qa-remediation-local-v1`.
Native qualification uses the committed `scripts/qualify_worldlab_qa.py` driver:
64 predeclared semantic controls, eight mechanical controls, and five copied v10
workspaces. Historical inputs and outputs are hash-verified and never regraded
in place. Semantic outcome changes are reported individually, not interpreted
as a recovered v10 treatment effect.

### Native QA iteration 1 and resulting fixes

Frozen `ec65903` passed 204 H200 worldlab tests (one environment skip).
`qa-remediation-native-v1` matched all 72 initial labels: 64 physical judge calls
and eight zero-call mechanical controls, 401,262 tokens. Five copied historical
workspaces passed artifact audits with 20 new judge calls and 197,926 tokens.
The original symlink submission now yields an auditable failed grade; the
helper-file zero identifies `build_planning.py` and the scratch/output contract.

This was insufficient for scale-up. Semantic inspection found a false-positive
R7 on the German note calling an open Major a Minor, and a missing public status
check let an English matrix with incorrect K1 status receive full credit.
Judge v21 therefore requires separate structured language, factual-support and
substance judgments for every K1-K5 note, with host-computed conjunction, plus a
source-bound public matrix-status check. It retains the original R7 weight and
adds one explicitly versioned public-requirement weight. Its 64 semantic controls
now include plausible wrong-severity, wrong-date and wrong-amount notes. Exact
historical semantic expectations are frozen before calls.

The first scoped optimizer qualification returned HTTP 500 with unknown usage.
Serving logs attribute it to an xgrammar compilation failure caused by literal
CR/LF in the regex character class. Escaped regex controls compile successfully
in the same serving container without a model call. The failed receipt remains
retained; fresh native optimizer qualification is required before any pilot.

The 14-attempt native resource/JobBench panel and five native employee decisions
use separate frozen artifacts. Those executions are diagnostic until the revised
grading and optimizer controls pass. No larger experiment has been authorized by
these partial results.

### Native QA iteration 2: passed controls and newly exposed blockers

Frozen `2a14934` passed 208 H200 worldlab tests (one skip). The strengthened
supplier qualification passed all 72 labels, with 64 metered model calls and
440,500 tokens, plus 20 calls / 200,375 tokens for five historical regressions.
The corrected native scoped optimizer passed with one call and 570 tokens.
Five native employee decisions passed their source/view/usage audits.

The first resource panel finalized and audited 14 attempts, consuming 349 calls
and 8,354,202 tokens; five solver sessions exhausted one million work tokens.
A prospectively declared second panel used two million work tokens, 96 calls
and 1,800 seconds in both unchanged-skill repetitions. Thirteen of fourteen
attempts passed audit; three work sessions exhausted their allowance. The
remaining JobBench technical-writer session completed native work but its
400,000-token judge allocation could not reserve the eleventh criterion request.
Its saved receipt still contains complete physical usage: 39 combined calls and
1,625,362 tokens. The panel summary omits that failed row's costs and must not be
used as the total bill. A larger, prospectively reserved judge allowance needs
fresh qualification; no failing verdict is retried in place.

The resource panel exposed source defects independently verified from public
inputs. `euw_v1_fr_010` starts ENT-Est at 95 pallets versus 40 capacity and
requires a temporary 52-pallet peak while prohibiting stock reduction. The other
three warehouses also start above capacity. The `euw_v1_es_018` family has nine
instructors with more exams than available days, violating even a relaxed upper
bound under its 48-hour gap rule. Its original checker nevertheless passed
native schedules that violate that actual gap. These six task variants are
prospectively quarantined by exact source hashes, not by observed low scores.
Changed inputs require requalification. Original task-bank bytes remain intact.

The scheduling family's memo judgments also estimated 135-138 words where saved
bodies have 151 and 150 whitespace-separated tokens. A source-bound mechanical
counter now handles the benchmark's 145-155-word rule; the separately judged
format criterion cannot inherit an estimated word-count failure. The explicit
counting convention excludes title and standalone punctuation, preserves
hyphenated/apostrophe-containing tokens, and counts Unicode letters/digits. This
repairs diagnostics but does not requalify the infeasible scheduling task.

**Scale-up remains blocked by broader grade coverage.** An inventory found 179
development/calibration task variants whose r3 files omit one or more original
mechanical criterion IDs. This is a coverage flag, not 179 proven incorrect
grades: public supplements already cover some conditions. The original checker
cannot simply be turned on: supplier CSV checks reject required extra columns,
recommendation substring bans reject negated/contrasted language, and scheduling
checks miss same-day/actual-hour conflicts. An unqualified composition prototype
and source-only diagnostic are retained under the ignored operator artifacts;
they are not wired into a study or presented as repaired production grading.

Remaining gates, in order:

1. Qualify the new memo counts and source quarantine on frozen source; enlarge
   judge/replay reservations prospectively and regrade a copied complete JobBench
   submission without rerunning or selecting solver outputs.
2. Produce an explicit per-task coverage matrix for the prepared cohort. Restore
   omitted conditions with reviewed executable predicates or appropriate semantic
   judgments. Validate positive witnesses and targeted mutations; never import
   incorrect source gold strings as extra public requirements. Block any task
   without a complete, qualified grade contract.
3. Recompile the fresh two-pair, five-role pilot after source/grade changes, run
   complete arms, and audit every native decision, replay, update and deployment.
   Retain the prepared-but-unexecuted old pilot as superseded evidence.
4. Only after the complete coverage gate and repeated pilot QA pass, freeze and
   launch the larger development run. No large run has been launched.

### Source-obligation coverage candidate

Judge v24 prospectively restores original `verification=mechanical` rubric
obligations absent from r3 into the actual scoring contract, retaining their
source IDs and weights. It does **not** pretend the defective original checker
is qualified: restored obligations use structured model judgments unless a
reviewed executable predicate exists. Supplier R1-R5 now use source-bound CSV
structure/status predicates, avoiding untranslated labels and incorrect gold
column projections. Existing r3 criteria, ambiguity guidance, source precedence,
and registered supplements remain binding. Every grade and audit binds the full
effective criterion list to its original definition and r3 source hashes.

This is a new development metric; old results are not comparable treatment
estimates. Full public-contract completeness and independent judge correctness
remain unclaimed. Eligibility retains the previously qualified maximum of eight
original r3 criteria while allowing restored obligations, up to 32 total plus
one bounded format repair. Per-task allocation is now explicit. The prospective
replay reservation increases to 129 calls (96 work + 33 judge), three million
tokens (two million work + one million judge), with the unchanged full time
window. Native controls and the matched pilot must validate this version before
it can release the scale-up gate.

### Source-language corrections and second qualification

The 10-task resource panel completed and audited every attempt with no work
budget exhaustion: 231 calls and 6,375,480 tokens. It qualifies the prospective
two-million work / one-million judge allocation, not every grading criterion.
The v15 coverage panel subsequently audited all ten copied outputs, but five
of eight positive English recommendation controls failed because inherited R8
still required German `Ablehnung`. All eight negative controls were rejected.
These failed controls remain immutable; there is no pilot launch yet.

Judge v25 binds 35 reviewed corrections across 20 task variants to both source
definition and public-instruction hashes. It preserves explicitly required
machine labels, fixes translated heading/recommendation obligations and MRI
arithmetic instructions that disagreed with public sources, and records every
corrected criterion. Five report-length rules now use exact source-bound
Unicode word counts. Local QA passes 219 tests (nine environment skips).

The v15 optimizer returned a valid empty edit list with complete accounting
(one call, 402 tokens). Its qualification operator incorrectly required a
nonempty proposal; abstention is valid and must not be retried until an edit
appears. The earlier nonempty structured control remains separate evidence.
The v15 employee qualification stopped before inference because its controller
environment omitted the explicit provider profile. A fresh launch must set the
profile, model and gateway URL and pass the existing fail-closed identity check.

The v16 native controls passed 72/72 plus 16/16 recommendation controls; all ten
copied submissions passed artifact/accounting audits. Manual review still found
a calendar judgment contaminating arithmetic with date-policy assumptions,
including rejecting a prescribed negative interval and shifting FR despite the
explicit prohibition. Judge v26 therefore registers seven source-bound calendar
CSV checks. Arithmetic follows submitted dates; separate checks enforce original,
compression and delay dates. The inherited delay criterion is corrected to the
public rule that unaffected rows retain original dates. The source's arbitrary
mandatory risk-title reference is also removed in favor of its stated choice.
Positive fixtures, targeted mutations, Unicode/source bindings and calendar
boundaries pass; the complete local worldlab suite passes 221 tests (nine skips).
The matched pilot still awaits fresh qualification and native employee checks.

### Qualified pilot and prospective expansion review

Frozen `d2ce66c` passed 221 H200 tests (one skip), 72/72 supplier controls,
16/16 recommendation controls, four native-calendar arithmetic/policy checks,
and all ten copied-output audits. Five native employees passed their full view,
provider and usage checks. The valid empty optimizer receipt was adjudicated
without another model call; original reports were retained. The two-pair pilot
started at approximately 13:36 UTC on 2026-09-16 with study hash
`989605c42827b97c5f524ee2907238928d5744be03e2c27cbb3d99d6e276c378`.
It remains frozen in workplace-v17 while further prospective source QA proceeds.

The six-pair/twelve-employee/twenty-day large draft introduces five source
families beyond the pilot. Their source review found additional inherited
translation requirements, unsupported report-length limits and uncertainty
conversion examples that violate the supplied minimum-value policy. The new
candidate corrects only those newly introduced task variants, binds corrections
to exact sources, and supports measured length vetoes without automatically
passing a mixed semantic criterion. The German whitepaper has eight convertible
prose U values plus two without k, despite its claimed eleven; all actual source
values are required, no missing value is invented. Rounded U and directly stated
u are distinguished explicitly, and the supplied 0.01-bar floor applies globally.
The candidate passes 223 local worldlab tests (nine skips). New-family native
qualification and complete pilot QA still gate the large launch.

### Pilot stop, numeric predicates and resource requalification

The v17 pilot was operator-stopped at a wave boundary after semantic QA found
contradictory grading. All admitted work joined by 14:01:22 UTC on September 16.
It retains 30 online attempts, 598 solver/judge calls and 11,491,254 tokens, with
zero updates, zero adoptions and no unfinished executions. Two of six operations
attempts exhausted their allocation; both were the feasible de020 exam task.
This crosses the predeclared 20% role threshold. A fresh five-repeat resource
diagnostic will use four million work tokens and 128 calls (same 1,800-second
window), uniformly; at most one exhaustion and zero infrastructure/accounting
failures are required before a uniformly reconfigured matched pilot. No attempt
will be resumed or retried selectively.

Raw-source inspection corrected an initial hypothesis about fr018: day 92 is
correct; the submitted 79–91 interval has thirteen days, not the required
fourteen. Deterministic inclusive-day, permit and safety checks now cover all
four relevant criteria. Housing fr019 preserves mandatory CH-004/CH-006
eligibility while allowing the rubric's existing, justified CH-001 journal
reconciliation alternative; it does not accept fabricated certificate failures.

The v18 new-family panel finalized ten attempts, 203 calls and 2,812,008 tokens
with zero budget exhaustions. Artifact/accounting success did not establish
semantic accuracy: de024 repeat 1 received full marks despite five sub-minimum
converted uncertainties. Source-bound numeric vetoes now reject wrong values
in CSV and unambiguous Markdown sections, compare decimal values numerically
(0.010 equals 0.01), preserve the two missing-k originals, and send numerically
valid or ambiguous prose onward for semantic assessment. Exam-plan checks now
independently enforce source capacities, availability, deadlines, prerequisites,
equipment and unique room/examiner booking. All controls include source binding
and targeted mutations. The original bank and every failed grade are retained.

The stopped prefix passed all 78 causal/source/accounting checks. Manual review
then found an employee confusing unrelated released editing feedback with the
current fiber task. The new view preserves every stored feedback record and
numeric historical outcome but exposes detailed prose only for the current
source family, with explicit task identity and relationship. Current-obligation
feedback remains complete. Employee instructions and delegated task wrappers
explicitly prioritize the current public task over mistaken historical notes or
colleague messages. This is a prospective actor-view policy change, applied
identically to both arms; the old run remains unchanged. Native qualification
must replay the contaminated context before another matched pilot.

The v19 workflow qualification passed 17/17 predetermined controls and all nine
immutable-output regrade audits. The previous uncertainty full pass now scores
0.588235; arithmetic defects cannot be waved through by its semantic explanation.
A positive corrected CSV still went through the model and passed. Resource
qualification remains separate and pending.

Native resource submissions exposed a broad-criterion false room-clash claim and
a type-spelling source conflict: records use `muendlich`, the public description
uses `mündlich`, while both describe the same exam type. Judge v29 explicitly
accepts either value, still preserving proper names exactly. Independently
verified CSV constraints are now supplied as measured facts to the professional
prose assessment; an actual CSV violation vetoes that broad criterion, while a
correct CSV cannot auto-pass Markdown or fabricated conflict explanations. The
full local suite passes 228 tests; the targeted positive/negative/source-change
checks also verify that valid arithmetic does not bypass semantic review.


### Native QA iteration 7: conflict claims and optimizer output capacity

The v22 panel passed 20/20 controls and 14 artifact/accounting regrade audits,
but manual review found two false full passes: valid exam CSVs accompanied by
fabricated Paragraph-14 conflicts. A source-bound section-level structured check
now classifies affirmative priority-resolution claims independently in every
Markdown section. A checked constructive schedule demonstrates that the source
§14.3 trigger (no legal plan without priority) is absent. The host rejects the
conjunction if any section asserts an actual priority resolution, even if a later
section denies it. The remaining criterion conditions still require judgment.
These are development qualification changes, not new solver instructions.

The isolated v21 learning epoch completed eight native replays but its optimizer
response exhausted the upstream 1,024-token output request. All 2,972,001 tokens
(147 target calls plus one optimizer call) are accounted; no candidate was adopted.
The strict completed-epoch audit correctly did not pass this failed update.
The native worldlab adapter now explicitly registers a 4,096-token optimizer
output allowance, bounded by the existing input/total-token reservation. Partial
responses are preserved after redaction and never compiled or adopted. There is
no new character limit, silent retry, or change to pinned upstream SkillOpt.
A fresh epoch and native conflict-claim controls are required before the pilot.

The resource diagnostic finalized all five attempts with one time exhaustion,
zero artifact rejection and complete accounting (260 calls, 9,224,562 tokens).
The worker stopped at its 1,800-second active deadline with 1.5 seconds of
cleanup, then the retained output was graded. All six expanded employee context
checks preserved the current topic and deliverables; residual imperfect wording
remains a model behavior outcome. The large study remains gated and unlaunched.


### Native QA iteration 8: prioritize actual released learning failures

Manual inspection of the real optimizer input found that upstream's short
why-wrong excerpt started with passing JobBench ordering checks. A fresh native
proposal consequently claimed an ordering failure even though all observed
ordering subcriteria passed. The actual failures were missing code examples,
priority assignments and SDK coverage later in the feedback.

A deterministic learning-only projection now places already released failed
check IDs and rationales first, followed by passing IDs and the complete original
feedback. It adds no private criterion text, preserves grades and source files,
and labels evaluator feedback as fallible. Both observed TRAIN feedback and
fresh replay feedback use this projection. Registered learner replay audits
reconstruct it from the saved grade; unrelated learner policies retain their own
contracts. A fresh native epoch is needed to qualify this feedback policy. The
v23 epoch remains a separate output-cap diagnostic and is not relabeled.

The current audit also binds every optimizer-visible descriptor to released public task context and every training record to its native replay text and feedback. Regression tests reject tampered prompts, feedback and trajectories. Native qualification checks the same bindings.

### Native QA iteration 9: complete failure projection and MRI criterion consistency

The first two v24 native validation replays completed with full artifact and usage
proof. The MRI replay scored 0.863636 because the deterministic public supplement
correctly rejected supplier B's nonzero score and the model rejected the TCO
formula. Yet the overlapping restored CSV criterion passed, and the memo's
conditional award to excluded B passed professional review. French/German MRI
variants in the large workload did not have the English supplemental check.

The new source-bound procurement adapter vetoes an invalid scoring CSV under its
existing criterion, with language-specific EXCLUDED/EXCLUIDO markers, for all five
registered source variants. Valid numeric checks do not automatically pass other
CSV semantics. The prose judge receives independently computed seven-year CSV
sums and the mandatory B/C exclusions, including the absence of authority to
waive a minimum through a compensation clause. Criterion weights, public tasks
and source data are unchanged. Native positive/negative prose controls and copied
regrades must qualify this change before a new native learning epoch and pilot.

Learning feedback projection v2 also includes already released failed public
supplement checks; it does not lose those failures when all rubric checks pass.
Historical grading and learning runs are retained under their frozen source.

The v25 CSV controls passed 20/20 and three copied submissions passed full
artifact/usage audits. The first prose fixtures were too abbreviated for the
required public layout; corrected full fixtures and every failed response are
retained. On complete committee-facing controls, 11/12 outcomes matched; one
English positive was falsely rejected by applying the general policy TCO
formula instead of the explicit task rule and alleging a nonexistent Markdown
corruption. The source-bound grading instructions now explicitly resolve that
precedence, preserve decoded Markdown semantics and permit the required CSV
filename reference. The exact saved complete controls must be rerun under this
new source version; their contents and expected labels remain unchanged.

The v26 panel kept all12control-request hashes identical but matched10/12:
French/German positives were falsely rejected for nonexistent missing sections
or broken newlines (all negatives rejected correctly). Explicit precedence alone
was insufficient. The next scoped change presents complete MRI source/candidate
files as readable text blocks with per-file IDs, hashes and character counts,
while retaining the full structured grading context and exact saved evidence.
No content is truncated or changed, and output constraints remain structured.
This tests the evidence-presentation hypothesis; it is not yet a proven fix.

The readable v27 panel passed17/17controls and all3copied-grade audits (38calls,
506453tokens); all339non-MRI payloads remained unchanged. Manual raw review still
found a false pass in the redundant scoring_calculation_correctness criterion
for retained replay0: it endorsed A=9.7 although the source predicate correctly
requires10.0 and rejected the CSV. The same registered arithmetic veto now also
applies to that calculation criterion. Eligibility-only violations remain with
their own criterion; valid arithmetic still requires semantic TCO-method review.
This last deterministic change is qualified on the retained failing request and
source variants, with byte-equivalence checks carrying the passing v27 native
controls. A fresh complete learning epoch under the final source remains required.

### Native QA iteration 10: replay serialization and optimizer grammar

The retained v24 epoch failed after eight replays (136 target calls, 3,125,204
tokens) and one optimizer call (8,975 tokens). No skill was adopted. The replay
audit compared JSON strings whose object keys were reordered by artifact saving;
all eight parsed trajectories were identical. Audit now compares canonical JSON
while rejecting duplicate keys, changed content/types and changed message order.
Optimizer-context text remains bound exactly to the original replay text.

The optimizer separately exhausted 4,096 output tokens after omitting required
proposal fields and repeating whitespace. Four basic incompatible-prompt schema
probes passed. Six subsequent causal probes isolated the newline-exclusion regex:
both API families, bounded arrays and a wrapper object still failed with it;
removing only the two regex patterns produced a valid complete seven-field edit.
Server logs also show xgrammar state errors; their precise engine cause is not
established. The v2 scoped proposal policy uses the supported basic JSON subset
and keeps the existing client-side newline rejection before compilation/adoption.
No arbitrary text-length limits, server changes or selective retries are added.
Native concurrency and real-optimizer qualification are required before a fresh
complete learning epoch and matched pilot. Earlier failed results remain intact.

### Native QA iteration 11: preserve fresh reflection evidence

The v29 epoch completed all twelve required replays and its native audits:
202 target calls, one optimizer call and 4,558,983 tokens. Both proposed edits
were rejected; the original skill remained byte-identical and confirmation was
correctly skipped. Its native report passes, but semantic review blocks the pilot.

The exact optimizer request exposed an implementation defect. Prompt compaction
joined historical feedback, fresh replay feedback and tool output before taking
the beginning and end. All three JobBench replay failure explanations disappeared,
even though the feedback projection put them first in their individual records.
The retained prompt instead showed repeated historical prefixes and successful
terminal results. A text search for `error` also treated `error: null` as failure.

Context adapter v2 gives fresh feedback its own prefix-preserving allocation,
shows historical feedback once per task, identifies each replay, and separates
non-success tool results using execution fields. The input byte reservation and
native structured-output schema are unchanged. The prompt labels omitted
evidence honestly and distinguishes relative score from actual requirement
success. It does not force an edit or change the upstream learning algorithm.
The learner identity now binds this context adapter and rejects a mismatched
transport receipt. Source, split, timing and secret-filtering boundaries remain.

Offline replay of the retained payload now includes each of the three complete
first failure explanations; none appeared in the original native prompt. Both
TRAIN IDs are present, all four validation IDs absent, and the exact same output
schema fits within the original 32,000-token conservative reservation. Twenty-six
optimizer tests pass; the 241-test local worldlab suite passes with nine expected
skips. Fresh H200 native reflection and full-epoch qualification remain required
before the matched pilot. The prior rejected epoch and known grader variability
are retained without relabeling them as learning benefit.

### Native QA iteration 12: preserve structured tool receipts during redaction

The v30 epoch completed twelve fresh replays (203 target calls, one optimizer
call, 4,292,720 tokens) and rejected its one scoped proposal for no validation
gain. All native audits passed. Raw review found a remaining status-label defect:
regex redaction inside serialized JSON consumed an escaped closing quote in a
public example URL. The resulting parse failure made successful terminal output
containing the business word "failure" look like a failed tool operation.

Context adapter v3 parses intact JSON first, then sanitizes individual values.
This preserves execution fields and removes sensitive metadata structurally.
Regression tests cover terminal and patch success receipts, escaped example
credentials, metadata removal and preservation of an earlier real tool failure.
The output schema, serving, judge and learning gates remain unchanged. The v30
result is retained with its original rejection, receipt and diagnostic labels;
fresh context qualification and a complete learning epoch precede the pilot.

### V32 empty-submission guard (2026-09-16)

The v31 matched pilot exposed a concrete grading defect: the budget-exhausted
seed-461 control logistics attempt d005-communications-fr-001-001 submitted no
deliverables, but received 0.428571 quality from judgments based on source inputs.
A study-wide stop was requested after the current admitted waves; original
attempts, grades, learning outcomes and costs remain immutable.

Both source adapters now reject a submission containing no nonempty candidate
file before calling the model. The EuroBench adapter requires output/ content;
JobBench retains its source policy allowing root deliverables. Inputs, scratch,
blank files and duplicate-archive descriptors cannot establish a submission.
This adds no minimum length and does not certify correctness or completeness.
The native grade and offline auditor execute the same check, with zero judge
calls, explicit failure feedback, and retained solver costs.

Validation covers absent/blank/scratch-only and wrong-location submissions,
original inputs, archive projections, root JobBench outputs, single-character
nonempty controls, and post-grade mutation detection. Retained native cases and
fresh small runs are required before a replacement matched pilot. Existing
nonempty-case prompts, schemas and outcome aggregation must remain unchanged.
Large-run clearance remains blocked until the replacement pilot completes QA.
