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
