# H200 remediation and staged experiments

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
