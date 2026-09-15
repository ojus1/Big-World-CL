# H200 task-world execution ledger

This ledger supplements [the architecture and calibration guide](WORLDLAB.md).
All paths below are on `inference-testing@h200-3` under
`/home/inference-testing/apps/`. Original evidence is preserved. No study here
establishes statistically significant skill learning.

## Frozen execution checkouts

| Study | Checkout / revision | Artifact directory inside checkout | State |
|---|---|---|---|
| First task world | `Big-World-CL-worlds-v1`, `4a3ab8a` | `lifespan/artifacts/development-world-v1` | Cancelled before execution after judge-format qualification failed |
| Serial engineering pair | `Big-World-CL-worlds-v2`, `6602bd1` | `lifespan/artifacts/development-world-v2` | Failed at day 4 in learning arm; incomplete judge output |
| Parallel adapter check | `Big-World-CL-adapters-v1`, `3efaa9f` | `lifespan/artifacts/adapter-qualification-v1` | Complete, both native audits passed |
| Larger coverage plan | `Big-World-CL-coverage-v1`, `da88f93` | `lifespan/artifacts/development-coverage-v1` | Cancelled before dispatch; zero work/learning calls |
| Judge count controls | `Big-World-CL-judge-v3`, `cf30158` | `lifespan/artifacts/judge-count-qualification-v3` | Complete, 12/12 correct |
| Revised parallel pair | `Big-World-CL-worlds-v3`, `437de52` | `lifespan/artifacts/development-world-v3` | Failed at day 5 in control arm; repeated judge whitespace |
| Native workplace pair | `Big-World-CL-workplace-v3`, `3aa4fa1` | `lifespan/artifacts/native-workplace-v1` | Failed in control day 1 at native first-byte timeout; no completed arm |
| Consolidation component | `Big-World-CL-learning-v3`, `7bcc1b8` | `lifespan/artifacts/consolidation-qualification-v3` | Failed in final validation; eight completed replays, zero optimizer calls or adoptions |
| Judge format corpus | `Big-World-CL-judge-v5`, `c79c2d7` | `lifespan/artifacts/judge-corpus-v5` | Complete, 210/210 valid responses; not semantic accuracy |
| Semantic controls | `Big-World-CL-semantics-v1`, `26d5cc4` | `lifespan/artifacts/semantic-controls-v1` | Complete, 33/33 source-grounded labels matched over one family |
| Native timeout fixture | `Big-World-CL-watchdogs-v2`, `343dc2d` | `lifespan/artifacts/nonstreaming-watchdogs-v2` | Complete, all three real-clock transport controls passed; zero model inference |
| Native adapter v4 | `Big-World-CL-adapter-v4`, `8cbf1d3` | `lifespan/artifacts/native-adapter-v4` | Complete; both concurrent task receipts audited |
| Public arithmetic v7 | `Big-World-CL-judge-v7`, `6f93d99` | `lifespan/artifacts/native-public-judge-v7` | Two native executions audited; one evaluator false negative preserved and corrected separately |
| Public arithmetic v8 | `Big-World-CL-judge-v8`, `31a59a7` | `lifespan/artifacts/native-public-regrade-v8` | Both unchanged native outputs accepted under fresh v8 grading |
| Fresh native workplace | `Big-World-CL-workplace-v5`, `31a59a7` | `lifespan/artifacts/native-workplace-v3` | Completed; full original-source audit passed, 52 work attempts, 24 replays, zero adoptions |
| Six-world native study | `Big-World-CL-workplace-scale-v1`, `3e1719d` | `lifespan/artifacts/native-workplace-scale-v1` | Failed September 15 at 00:23 UTC after 71 graded work attempts; no completed pair |
| Isolated validation pilot | `Big-World-CL-isolated-validation-v1`, `c833481` | `lifespan/artifacts/native-workplace-isolated-validation-v1` | Launched September 15 at 03:16 UTC, with separately prepared gate cases |

The stopped pair services are `bigworld-development-world-v2.service` and
`bigworld-development-world-v3.service`. Their main PIDs at launch were 1794740
and 1812325. Both run under `systemd --user` with process-group cleanup, a 16-GiB
controller memory ceiling and a six-hour runtime ceiling. The shared Qwen server
remains `bigworld-qwen38flashnext` at `http://127.0.0.1:8000/v1`, using GPUs 0–3.
The controller interpreter is `Big-World-CL/MiroFish/backend/.venv/bin/python`;
workers use the pinned native Hermes environment.

## Terminal development results

Both services are terminal failures, with `MainPID=0`; these are not observation
timeouts. v2 failed at **2026-09-14 19:55:56 UTC**, and v3 failed at
**19:58:41 UTC**. Original incomplete attempts and reservations are preserved.

| Pair / arm | Recorded work | Fully graded | Work + judge calls | Work + judge tokens |
|---|---:|---:|---:|---:|
| v2 control | 20 | 20 | 318 | 4,253,239 |
| v2 SkillOpt | 10 | 9 | 130 | 1,454,159 |
| v3 control | 12 | 11 | 184 | 2,509,041 |
| v3 SkillOpt | 0 | 0 | 0 | 0 |

The two pairs consumed **632 recorded calls and 8,216,439 tokens**, including
the incomplete judge responses. No learning arm reached an update. The v2
control's two update records are no-ops. No skill was proposed or adopted.
Nineteen v2 control attempts passed a partial execution audit before termination;
this does not establish judgment correctness.

The v2 judge sometimes contradicted its own evidence. v3 put the final Boolean
after evidence and reasoning and passed 12 exact-count controls, but later
repeated whitespace until reaching its output cap. The next version used a
finite ASCII grammar. Its range quantifiers were too slow at full field bounds:
both v4 checks timed out on their first call. These failures remain under
`Big-World-CL-judge-v4` at `f073579`, with unknown usage retained as reservations.

An equivalent right-recursive grammar completed a short preflight in 0.4 seconds.
It is frozen at `c79c2d7` in `Big-World-CL-judge-v5`. The v5 checks replay all 210
saved criterion contexts from the stopped studies and the same 12 constructed
count controls. Their completion and correctness must be read from their final
`QUALIFICATION.json` files; no successful full-corpus result is claimed here.
The corpus check measures format/completion, not general judgment accuracy.
The v5 count diagnostic completed with **9/12 correct** in 12 model calls and
70,136 tokens. In failed controls the model counted a changed 5.5 reference as
5.4 or ignored an appended fourth reference. This is failed count qualification.

The next judge uses an executable literal-count predicate only when the entire
frozen criterion and its original three-reference source match the registered
case. Changed or unknown criteria retain model judging. The original rubric and
all old judgments remain intact. This removes a mechanical counting failure;
it does not establish accuracy of the remaining semantic judgments.

Each small pair has two employees, ten days, one possible update per learning
employee, four probes per arm and a 60-million-token combined reservation ceiling.
This is a maximum reservation, not an expected consumption estimate. v2 uses seed
211; v3 uses seed 223. v3 keeps the original small specification, adds
`max_parallel_employees: 2`, and freezes it in `run/development-world-v3.json` and
`STUDY.json`. Its study SHA is
`49406f7d96992e8c3e5056df410a052f1206f3a9ba0e46d3e39b5da78be18cdb`.

The larger cancelled plan expanded 12 employees over three departments and three
languages, with one direct calibration anchor, two role transfers and nine
defaults. It planned 960 work attempts and 36 possible learning updates. Its
`EXECUTION.json` records cancellation before dispatch and prevents accidental
reuse through the single-execution guard. Prepare a new plan after qualification.

## Inspect and audit

Use `systemctl --user show SERVICE -p ActiveState -p SubState -p MainPID` and
`journalctl --user -u SERVICE -n 12 --no-pager` for process status. Inspect each
arm's `STATE.json` and `INFLIGHT.json`; top-level `STATUS.json` updates when an
entire arm finishes. Never infer completion from an old progress line.

After a pair completes, run the matching frozen checkout's
`python -m worldlab.audit_worlds --bank ../Big-World-CL/lifespan/artifacts/final-world-calibration-v1 --out lifespan/artifacts/development-world-vN`.
Keep audits beside the original evidence. The v2 limitation sidecar must remain
part of any interpretation even if its execution audit passes. Compare adopted
skill contents, future deployment receipts, probe results and learning costs;
a positive score difference without an adopted skill is not a learning result.

Local copies of the completed adapter and judge controls are under
`Big-World-CL-lab/lifespan/artifacts/`. All 80 adapter evidence files matched their
receipt hashes after transfer. Their combined qualification cost is 32 physical
calls and 196,431 tokens. The focused suite passes 36 task-world/calibration cases,
including alternate harness receipts, sparse examples and failed parallel waves.

## Reacting workplace implementation

Commit `897dfea` adds optional native MiroFish employee decisions to the task
runner. Its causal state includes capacity-limited queues, delayed feedback,
rework, deadlines, notes, trust and next-day colleague messages. Original source
requirements accompany each employee request; replay uses that same recorded
request. The kernel never exposes future tasks or unreleased grades to actors.

The factory, harness and learner remain separate adapters. Each paired arm gets
a new OASIS environment with the same pinned persona assignments. The primary
workplace metric is acceptance before deadline over every planned probe,
including deferred and unattempted probes. Rewards are configured synthetic
utility, not money. Native interview usage is measured; bootstrap and the initial
social round remain an explicit accounting gap.

The source is frozen in `Big-World-CL-workplace-v1`. The native employee qualifier
used two real role assignments and day-zero views, without solver work or invented
feedback. It failed before any employee interview: MiroFish's ontology-generation
request failed after roughly 120 seconds and the backend returned HTTP 500. Its
partial native project and controller evidence are preserved; the new adapter
is not qualified yet. Full
realistic-world learning and prospective significance evidence remain outstanding.

The installed canonical checkout at `897dfea` passed **1,027 tests, 6 skipped**
(`python -m pytest -q tests lifespan/tests`). Running all tests in a bare frozen
worktree first exposed missing local dependency paths (SkillOpt and the backend
venv), not product regressions; that failed test invocation is retained. The
focused suite after the deterministic count addition passes 39 tests.

`worldlab.qualify_learning` can independently exercise a bounded native SkillOpt
update from four temporally selected, already-recorded control experiences. It
preserves the historical work, starts new target replays, grades those with the
current frozen judge and audits completed replay receipts and the adoption gate.
This avoids rerunning a whole control arm merely to reach consolidation. It is a
component qualification, not a continuation or replacement of a failed study.


## Native workplace and consolidation follow-up

The declared-organization compiler at `33708c8` seeds only the assigned employees
and departments through the native local graph API. It uses no model for ontology
or initial graph extraction. It disables automatic graph-memory extraction in
this workplace mode; OASIS interviews, explicit notes and delayed colleague mail
retain state. Existing legacy bootstrap behavior remains the default elsewhere.

`Big-World-CL-workplace-v2/lifespan/artifacts/native-employees-v2` completed:
two actual Persona 8B employees, two verified native decisions, two model calls
and **4,914 interview tokens**. Its plan SHA is
`6c559a685a6c1e5e0ca51a6ceaebb313233214657297e85470816e86fa8beb2d`.
Native graph readbacks and the actor database are preserved. Initial social-round
model costs remain unknown; the 4,914 figure covers interviews only.

The v6 count check in `Big-World-CL-learning-v1` passed **12/12 with zero model
calls**, using the registered deterministic predicate. This is a mechanical
control result, not a model-accuracy claim. Its plan SHA is
`7952bc4376f191ab253d6e7f70a6a3b235d08cc44c1f6a19c05853f7d4911f16`.

The first standalone consolidation invocation failed during historical request
import before creating a plan or making model calls. Versioned import handles
Hermes v1's `REQUEST.json` and later normalized request receipts. The second
invocation (`Big-World-CL-learning-v2`, source `ebd2202`) failed on its first target
replay: six calls reported 70,803 tokens, and a seventh returned a connection error
after 120 seconds, retaining a 65,229-token reservation. This is not a scored
learning failure and not evidence that optimization is ineffective.

The corrected native Hermes configuration at `7bcc1b8` sets both request and
stale-response windows to `min(600 seconds, whole task budget)`, using supported
provider settings. Both values are checked against the actual native agent and
saved in `READY.json` and `NATIVE.json`. Whole work and consolidation budgets
remain unchanged. The native adapter is now version 3.

`bigworld-consolidation-v3.service` runs from `Big-World-CL-learning-v3`, with
artifacts at `lifespan/artifacts/consolidation-qualification-v3`. Its source
experiences are the research analyst's days 2 and 4 (train) and days 3 and 5
(validation), available at day 6 of the stopped v2 control. Selection is temporal,
not based on scores. Fresh replays use the current judge and seed skill. Read the
final `QUALIFICATION.json` and `AUDIT.json` before reporting completion or adoption.
The first actual native request readbacks confirmed both 600-second settings.

The focused suite passes **44 tests**. The full installed-environment rerun
at `7bcc1b8` passed **1,035 tests, 6 skipped** in 125.64 seconds, finishing at
2026-09-14 20:45:31 UTC under `bigworld-canonical-tests-v2.service`.

At **20:46:48 UTC**, consolidation v3 remained active with its first native target
replay in flight and both timeout readbacks verified at 600 seconds. The v5 judge
corpus had completed 92 of its 210 fixed contexts. Neither was complete at this
snapshot. No skill adoption or significant learning result is claimed.

## First complete native workplace protocol launched

Source `3aa4fa1` separates new task arrivals from work capacity. The new
`development_workplace_v1.json` specifies two employees in one department, English
research and French editing, one incoming task and two work opportunities per
employee/day, two-day deadlines and bounded rework. Only the research employee
has a representative prompt. This prevents an implicit assumption that a user
has examples for the whole workforce, and allows spare capacity to absorb rework.
The same frozen arrivals are used in both arms; subsequent decisions can differ.
Both local and installed H200 focused suites passed **46 tests**.

The frozen checkout is `/home/inference-testing/apps/Big-World-CL-workplace-v3`.
Its `lifespan/artifacts/native-workplace-v1/STUDY.json` SHA-256 is
`815a012ed6298ecb8c9909f273e0a7aa4d4389fb733e1a4b149e4dd17cc53643`.
Seed 317 has ten days, learning on day 6 and probes on days 8–9. There are 40
incoming obligations across the pair and at most 80 work attempts, including
rework. Work/judge reservations are 72 million tokens, learning reservations
24 million, and native interviews are reserved separately (160 logical calls,
including bounded repairs). These are ceilings, not expected or consumed tokens;
actor bootstrap/social usage remains unknown.

`bigworld-native-workplace-v1.service` started at **20:54:15 UTC** on September 14,
with invocation `7228b78af9e84d8b91fabffb19f7e4b2`, MainPID 1834682 and an 18-hour
service ceiling. It uses a fresh native employee environment per arm and the
already-running backend on loopback 5001. At **20:55:55 UTC**, it remained active:
one day-zero employee decision had completed (2,528 interview tokens), the second
was in flight, and no work attempt had completed. This is a development
integration run, not a powered or confirmatory experiment.

At that same snapshot, consolidation v3 had completed two native target replays:
18 calls / 285,933 tokens and 9 calls / 49,992 tokens, both with complete accounting.
It remained active with no final update/adoption decision. The v5 judge-format
corpus had completed 130/210 calls, charging 967,778 reported tokens. Its scope
remains format/completion, not judgment correctness.

The first consolidation replay (`internal/euw_v1_es_017_en_bridge`) included an
incorrect judge explanation that supplier B was factually supported. Direct
inspection of the original instruction and acquisition policy confirms supplier A:
pending on-site PACS validation is explicitly allowed with a clause; supplier B's
measured 3T noise exceeds the excluding threshold. The original rubric therefore
stands unchanged. The failed memo criterion's decision and its explanation must
not be treated as equally reliable evidence; semantic judging remains unqualified.

The completed native-employees-v2 qualification was copied locally as 18 regular
files, verified against source SHA-256 values and independently receipt-audited:
two decisions, two calls, 4,914 interview tokens. The archive SHA is
`520463516e4c7ad76b0d891da3e3da728dc45adcd6e9fc4503f964006f0d9cb7`;
the local audit is `lifespan/artifacts/native-employees-v2-local-audit.json`.

## Mechanical coverage audit and semantic controls

The read-only diagnostic at `cd6d9de` ran against every attempt receipt present
in the stopped worlds-v2/v3 studies and consolidation-v3 at snapshot time.
`Big-World-CL-mechanical-v1/lifespan/artifacts/mechanical-agreement-v1` contains
46 attempts from 13 lineage groups, with 44 complete qualitative judgments.
The plan SHA is `b1203a7f94604fc2f23da59d1018d42585de0eab4a93adaf41447a3e20619d93`.
It made zero model calls; a separate rerun verified all 46 mechanical results and
source artifact hashes. Five diagnostic/review JSON files were copied locally and
verified byte for byte. No historical grade or candidate output was changed.

| Qualitative result | Mechanical fail | Mechanical pass |
|---|---:|---:|
| Fail | 16 | 0 |
| Pass | 20 | 8 |

This is disagreement, not an accuracy confusion matrix. Source inspection of
three cases establishes why neither evaluator can simply replace the other:

* `euw_fr_003_en_bridge`: mechanical JSON gold requires a sixth workshop benefit,
  while the corrected r3 contract explicitly permits omission of that notes-only
  possibility. Requiring it would add an obligation absent from the corrected
  contract. A1–A5 coverage is not deficient merely because A6 is absent.
* `euw_v1_fr_014`: a qualitative-passing output reports zero calendar days for
  2025-01-20 through 2025-01-13. The public inclusive subtraction rule yields −6.
  The r3 criteria largely cover the decision prose and ordering; they do not
  replace this numerical obligation.
* `euw_v1_es_017_en_bridge`: the public CSV yields TCO totals A=955,306,
  B=875,758 and C=1,115,141, hence A's price score 9.2 and total 9.20. A passing
  candidate instead used report-summary TCO and produced 9.15. But mechanical
  requirements for Spanish `EXCLUIDO` markers conflict with public English
  `EXCLUDED`, and zeroing every weighted subrow is stricter than the public
  requirement for zero on the TOTAL row. Some failures in the same check group
  are therefore valid and others are not.

`SOURCE_REVIEW.json` preserves these findings with source and candidate hashes.
The reviewer is Codex source inspection, not an independent human. The diagnostic
initially could not import the document dependencies in MiroFish's environment;
no diagnostic plan or grading ran then. It completed using the original evaluator
environment `/home/inference-testing/benchmarks/eurobench-v1/.venv/bin/python`.

Both workplace-v1 and consolidation-v3 received an
`EVALUATION_LIMITATION.json` sidecar that binds this evidence and marks full-task
success unqualified. Their frozen protocols and results remain intact. The next
scoring contract must combine valid numerical/structural obligations with the
corrected qualitative requirements before supporting a learning-effect claim.

Semantic controls at `26d5cc4` run from `Big-World-CL-semantics-v1`, artifact
`lifespan/artifacts/semantic-controls-v1`. There are 11 constructed cases over one
source family (five positive, six negative), repeated three times. All cases,
expected labels and rationales are frozen before calls. They cover optional A6,
valid paraphrases, threshold direction, membership duration, invented guarantees,
heading requirements and appendix ordering. `bigworld-semantic-controls-v1`
started at **21:06:30 UTC**, invocation `7cb3782d77024d81a6d611c4702ba307`, with a
4,500-second service ceiling. At **21:11:57 UTC**, 12/33 calls were complete and
all 12 matched their labels (34,525 tokens). Even a full pass is one-family
qualification, not general judge accuracy or actual solver performance.

At that same snapshot, the original judge-format corpus was 169/210 (1,293,320
tokens); consolidation-v3 had six completed replays and no final adoption
decision; the native workplace was on day 1 with two completed work attempts and
four metered employee decisions (14,934 interview tokens). All four inference
services were confirmed active with nonzero MainPIDs.

## Configurable experiment adapters

`a4af361` adds operator-selected harness and learner factories to the existing
runner. Their configuration bytes and factory-module hashes enter frozen adapter
identity; changing them between prepare and execute is rejected before dispatch.
The offline harness auditor accepts the same factory configuration. Existing
direct Hermes/SkillOpt arguments retain their behavior; no Fluso implementation
is implied by the loader.

Both local and H200 focused suites passed **51 tests**. Actual installed Hermes
and SkillOpt factories successfully prepared seed 331 in
`Big-World-CL-factories-v1/lifespan/artifacts/factory-preparation-v1`, with study SHA
`62da8e213e79989d05b668300b7ab76db4b43331a4fc889d82d8af8fd9520964`.
That artifact is preparation-only: zero model calls and no experiment execution.
The complete canonical suite passed **1,042 tests, 6 skipped** in 125.77 seconds
at **21:13:33 UTC** under `bigworld-canonical-tests-v3`, invocation
`24866588d9a548c082fb58ec1c9d2b30`. Its MainPID was zero and service result success
when checked at 21:14:14 UTC. At that check, the semantic controls were 17/33
completed and correct, the format corpus was 173/210, and all four inference
services remained active. No consolidation adoption decision was available.

At **21:15:42 UTC**, a service-specific systemd drop-in changed the format corpus
service's observed `RuntimeMaxUSec` from 1h to 2h after a daemon reload. MainPID
1824041 and invocation `4d1db414e04d4828bcfd214939fe4ab1` were unchanged; the process
was not restarted. `judge-corpus-v5/RUNTIME_ADJUSTMENT.json` records before/after
readbacks. The fixed 210 cases, 120-second per-call deadline and model/token
budgets are unchanged. The original one-hour deadline had not yet elapsed when
this adjustment was recorded.

## First-byte timeout correction and completed component evidence

The native workplace pair failed at **21:15:22 UTC** on September 14. The two
employees produced four recorded work attempts, three fully graded, totaling
52 work/judge calls and 699,017 charged-or-reserved tokens. Of those tokens,
641,324 have provider receipts and 57,693 remain a reservation for the failed
request. Four employee decisions used another 14,934 interview tokens; native
bootstrap/social usage remains unknown. No arm or learning update completed.

Both request and stale timeout readbacks were 600 seconds. A separate native
Codex watchdog nevertheless closed the final-body HTTP request at 120 seconds
because it had emitted no SSE event. Hermes source remains pinned and unchanged.
Adapter version 4 uses the supported `HERMES_CODEX_TTFB_TIMEOUT_SECONDS=0`
environment setting in its isolated worker. It records and audits this setting
alongside the request/stale limits; the parent whole-attempt limit also remains.
The change neither invents stream activity nor adds retries.

The real-clock qualification at `343dc2d` used native construction, native SDK
clients, the native interruptible request helper and the actual final-body
adapter against an isolated loopback fixture. The legacy setting stopped at
120.029 seconds, the corrected setting returned the complete response at
130.059 seconds, and a two-second request budget stopped at 2.026 seconds.
All three cases passed, with no fabricated SSE events and zero model inference.
Plan SHA: `9ef0e52a6365fac66f938558738591a63e013b4b92dd5e28c81642a5d1233db6`.
The earlier fixture at `3d6ce09` retained correct timing observations but failed
its request-count assertion because native metadata probes were also counted;
its failed evidence remains in `nonstreaming-watchdogs-v1`.

Consolidation v3 also failed at the same native first-byte watchdog, on its ninth
replay during final validation. Eight replays completed, no optimizer call ran,
and no skill was adopted. Its 106 work/judge calls charged or reserved 957,952
tokens: 887,479 reported plus 70,473 reserved for the missing final receipt.
The native attempt correctly recorded incomplete accounting, but the replay
callback passed its charged total as measured usage to the learner. Thus the
historical aggregate's `accounting_complete: true` is incorrect.
`ACCOUNTING_LIMITATION.json` binds the original receipts and this correction.
Commit `8cbf1d3` passes unknown usage as unknown across that boundary, retaining
the learner's full replay reservation and known physical-call count. The
regression check covers both known and unknown usage after execution failure.
Original study, update, and attempt files remain unchanged.

The semantic controls finished at **21:21:02 UTC**, with 33/33 labels matched,
33 calls and 95,377 reported tokens. Their plan SHA is
`83093ab80eba01c414a72f9762d17fe92d40cb7dbe44a73bb4c44baedb5f33c9`.
All 47 evidence files were copied locally and checked against remote hashes.
The format corpus finished at **21:25:53 UTC**, with 210/210 valid responses,
210 calls and 1,613,226 reported tokens. Its process survived the original
one-hour deadline after the recorded extension, without restarting. All 424
evidence files were copied locally and checked against remote hashes. Neither
qualification establishes full-task correctness or a learning effect.

The focused suite after the timeout/accounting changes passes **52 tests**.
The complete canonical suite at `8cbf1d3` passed **1,043 tests, 6 skipped** in
125.85 seconds under `bigworld-canonical-tests-v4`, invocation
`99cd8dd7273841db82570f1a832560e2`; the service was inactive with MainPID zero
and result success afterward.
The new native adapter qualification at `8cbf1d3` uses two fresh concurrent
`internal/euw_fr_003_en_bridge` tasks, fixed before execution, on the same Qwen
server. Its service is `bigworld-adapter-v4`, invocation
`be196dc8b2ca4ea0bb9d60ef624cb3cb`. This is transport, worker isolation and receipt
qualification only. The earlier failed world and consolidation are not resumed.
Both new workers' `READY.json` receipts confirm request/stale limits of 600
seconds and the explicit zero first-byte watchdog setting.
At **21:30:57 UTC**, both native controls were complete and audited, using 8 and
11 work/judge calls respectively: 43,815 and 69,234 tokens, or 19 calls and
113,049 tokens combined, all with complete accounting. The service was inactive
with MainPID zero and result success. The qualification plan SHA is
`08e75c8728d34b1420a081e647c9f082e58c9110cb7b1d8fa4faacd6d4366e12`.

## Public arithmetic checks and the next native workplace pair

Commit `6f93d99` supplements the unchanged corrected r3 criteria with deterministic
public requirements for two reviewed tasks. The registry binds each task's public
contract and all source input hashes. The editorial checks cover rows, inclusive
calendar subtraction, signed dates, fourteen-day compression and fixed French
publication dates. The procurement checks cover source-derived scores, weighted
totals and supplier exclusions. Each check has a fixed weight; malformed output
fails the registered checks without reducing their denominator. Other tasks
remain in the workload. This is partial coverage, not a complete replacement
for qualitative judgment or certification of all 186 eligible tasks.

The first native procurement qualification exposed an overstrict rule in the new
checker: a valid output left intermediate weighted cells blank for excluded
suppliers. The public task requires their TOTAL to be zero but does not specify
the intermediate cells. Commit `31a59a7` accepts that alternative and explicitly
marked intermediate cells, and advances the judge to version 8. The original v7
receipts remain unchanged. The prepared workplace-v2 was cancelled before any
dispatch; its replacement uses a fresh artifact directory and source checkout.

The v7 native qualification completed two audited executions, with 31 work/judge
calls and 457,102 tokens. All original r3 criteria passed in both. The v7 public
checker accepted one and incorrectly rejected the blank-cell output. Fresh v8
grading of the exact same output bytes accepted both, using eight new judge calls
and 98,943 tokens; no solver reran. The fresh grading plan SHA is
`4e7fba27b6944900a09ad6fc01bfb2a67a429a5df4bf56203f33c7086b30a0c9`.
Its artifact is `Big-World-CL-judge-v8/lifespan/artifacts/native-public-regrade-v8`.
All 46 files in this fresh grading artifact were also copied locally and verified
against remote SHA-256 hashes.
The `bigworld-public-regrade-v8` service finished with MainPID zero and result
success. Its invocation is `98458ba890c643caada89e3efffa412e`.

All 18 fixed public-component controls pass at `31a59a7`, including the two valid
excluded-cell alternatives, with zero model calls. The editorial positive
fixtures are component controls, not full-task gold outputs. A separate read-only
diagnostic against the already frozen 46-attempt snapshot found nine registered
attempts, six of whose original passes fail the new public checks. This is a
dependent retrospective diagnostic, not an independent estimate of judge accuracy.
The v8 diagnostic plan SHA is
`d8c83b153fe748c39f2235fbeec1397edb02bbdb3d5e47708046af2e67a45565`.
All 24 component/diagnostic evidence files were copied locally and checked against
remote SHA-256 hashes. Historical outputs and grades were not changed.

The full canonical suite at `6f93d99` passed **1,046 tests, 6 skipped** in 126.67
seconds, under `bigworld-canonical-tests-v5`, invocation
`e6c5f47beba64a44a2cd00d038320756`. The focused suite after the v8 correction passed
**55 tests**. The full-suite result predates that correction.

Source inspection also explains consolidation-v3's zero optimizer calls: all six
training replays had hard and soft score 1. The pinned SkillOpt implementation
returns no reflection when there are no failures and no contrastive score spread.
Its failed validation example is not reflection training data. This was a
legitimate no-op, separate from the later timeout, and is not evidence of skill
learning. No cases were selected by their score to force an update.

The fresh ten-day seed-317 native pair launched at **21:46:55 UTC on September 14**
under `bigworld-native-workplace-v3`, invocation
`86cb332683f84371bb6830fabf9d14f0`, MainPID 1853105. It runs from the frozen
`Big-World-CL-workplace-v5` checkout at `31a59a7`; its artifact is
`lifespan/artifacts/native-workplace-v3` and study SHA is
`f56c80acfebaef75e37e463f154e257b932cd9d4869ca66fc0dedd48fcd9244c`.
At **21:49:58 UTC**, the service was active and one work session had completed.
At **21:52:13 UTC**, it had advanced to day 1 with two completed sessions and four
employee decisions. Those two work sessions used 35 work/judge calls and 534,950
tokens. MainPID 1853105 remained active.
The pair plans 40 obligations, at most 80 work attempts and two possible learner
updates. The analyst alone has calibration examples; the French editor uses
defaults. The 96-million-token work/judge/learning reservation is a ceiling,
not measured consumption. Bootstrap/social usage remains unknown.

At `3e1719d`, the separate six-world native development study is **prepared only**:
12 employees, three departments, three languages, 20 days and seeds
`401 409 419 421 431 433`. Every seed has one directly calibrated employee, two
recorded role transfers and nine defaults. The fixed schedule plans 2,880 arriving
obligations, at most 5,760 work attempts and 216 possible learner updates. Its
7,776,000,000-token reservation is a conservative ceiling, not an ETA or actual
cost. No model calls or native employee bootstrap have been dispatched for it.
The checkout is `Big-World-CL-workplace-scale-v1`, artifact
`lifespan/artifacts/native-workplace-scale-v1`, study SHA
`3105405bfb60e91cc84c00ea07674b701c2bc3ec22a93499b451eeae1a9ce9e1`.
The [study protocol](WORLDLAB_STUDY_PROTOCOL.md) describes the required adoption,
deployment, paired-outcome and statistical evidence. None of these preparation
counts establishes a statistically supported learning effect.

The separate prospective analysis was frozen at **21:56 UTC** before any scale
study execution, under `Big-World-CL-lab/lifespan/artifacts/native-workplace-scale-analysis-v1`.
Its plan SHA is `019ba6cbb8b1b63d5beaa40a7c47673e3a128cb8fc55a8e744ac6fdaa7daa74e`.
The implementation is at `c3bbd0e`; all 59 WorldLab tests passed locally. The
analysis requires all six planned pairs and their original offline audits before
computing the equal-world paired effect, uncertainty and exploratory sign-flip
diagnostic. No analysis results or statistical significance are available yet.

At **21:56:09 UTC**, the ten-day native pair remained active under the same
MainPID and invocation. Its control arm had reached day 2 with six completed work
sessions, eight recorded employee decisions, 92 work/judge calls and 1,265,579
work/judge tokens. No learning update had run. These are live progress counts,
not a completed paired result.

## Six-world native study launched

The scale study launched at **21:59:22 UTC on September 14**, from its unchanged
`3e1719d` checkout and original prepared study. Service
`bigworld-native-workplace-scale-v1` has invocation
`d321a4ee4152473b86daeb36a74d5c73` and MainPID 1861095. The prospective analysis
was already frozen; its plan and study hashes were checked before dispatch.
The service has a 32-GiB controller ceiling and an operational seven-day runtime
ceiling. Hitting that ceiling would leave an incomplete study; it does not change
the frozen task, learner or token budgets. Launch and readback receipts are under
`Big-World-CL/run/h200-20260914/native-workplace-scale-v1-{launch,started}.json`.

The pre-dispatch server snapshot at **21:58:41 UTC** showed two running requests,
zero waiting requests, zero preemptions and about 2.05% KV-cache use. The Qwen
server remains on GPUs 0–3; GPUs 4–7 were idle. The pilot continues alongside the
scale study. Their native simulations have separate project, graph, simulation
and employee-state identities. Neither running checkout or installed backend
was modified to start the larger study.

At **22:02:58 UTC**, both services were active with their original MainPIDs and
invocations. Scale seed 401's control arm had initialized all 12 native profiles,
completed 12 employee decisions (12 calls, 34,146 reported tokens), and dispatched
its first four work attempts. No scale work attempt had completed at that
snapshot. The pilot control arm was on day 4 with 11 completed work attempts,
177 work/judge calls and 2,463,650 work/judge tokens. Its 13 metered employee
decisions used 71,013 additional tokens. Neither study had a learner update yet.

A read-only inspection of scale simulation `sim_80f6a626cfc1` preserves a SQLite
backup, native log snapshots and the installed OASIS agent source under
`Big-World-CL-lab/lifespan/artifacts/native-actor-accounting-inspection-v1`.
Its inspection SHA is
`a98edd3790dbf2807a8f67f62a508e85a89526751329fc06d8e3be935b6bc9b8`.
`perform_action_by_llm` receives CAMEL's response but logs tool names, arguments
and results, not provider usage. Native trace rows likewise preserve actions
rather than physical-call receipts. The known interview receipts do not cover
these initial social calls. Shared-server counters cannot uniquely attribute
concurrent traffic to this simulation. Bootstrap/social usage therefore remains
unknown. Future metering belongs at the simulation-scoped provider dispatch and
response boundary; these running sources and historical costs remain unchanged.
All eight inspection files were copied locally and checked against remote hashes.

At **22:07:25 UTC**, the reusable progress command at `7ddea29` observed both
original service processes present and active, with no JSON read errors. The
scale study had two fully graded attempts: 18 work/judge calls and 105,817
reported tokens, plus its 12 employee interviews. Two other work attempts were
still missing final receipts. The pilot retained 11 fully graded attempts while
its next two were running; no arm or learner update had completed. These
nontransactional snapshots are saved under
`Big-World-CL-lab/lifespan/artifacts/workplace-progress-snapshots`.
The local WorldLab suite passed **62 tests**, and all three new progress-command
checks also passed on H200. Those checks cover unknown usage, a service polling
timeout, live/terminal process states, incomplete checkpoint writes and replay
costs already included in the learner ledger. They make no learning-effect claim.

## Learner audit extension and subset-calibration verification

At `0f8383d`, the learner adapter owns its policy-specific `audit_update` check.
The shared audit still enforces employee identity, feedback chronology, replay
provenance and accounting. SkillOpt retains its original gate checks and now
also checks frozen configuration, skill hashes and optimizer transport receipts.
Custom adapters must provide an auditor matching their recorded identity;
matching a built-in name alone cannot substitute for that contract. Newly
prepared analyses preserve their executable source and optional learner config.
The already running studies and their prospective analysis remain unchanged.

The H200 checks at this commit passed **1,060 tests, 6 skipped**, in two explicit
scopes: `tests` passed 748 with 4 skipped in 99.85 seconds under
`bigworld-canonical-tests-v6`; `lifespan/tests` passed 312 with 2 skipped in
26.13 seconds under `bigworld-lifespan-tests-v6`, invocation
`30742f8bab9a40258c2de66a40dcbd66`. These are software checks, including the
existing one-example/100-employee and zero-example calibration cases, rather
than evidence of a learning effect. Representative examples remain optional for
any subset of employees; same-role/language transfer is a recorded assumption
and uncovered employees retain simulator defaults.

At **22:22:04 UTC on September 14**, the read-only progress command found both
original study main processes present. The pilot control arm remained on day 5
with 15 fully graded work attempts, 249 work/judge calls and 3,451,236 reported
tokens. Scale seed 401's control arm was on day 0 with 11 fully graded work
attempts, 142 work/judge calls and 1,466,008 reported tokens. These counts exclude
separate employee interviews and unknown bootstrap/social usage. Neither study
had a finalized learner update or a completed paired learning comparison.

## Native social-call accounting qualified separately

At `bafac6f`, a new opt-in native recorder captures simulation-bound Responses
dispatch receipts, reported token usage and failures for uncontracted social
calls. Interviews retain their existing separate ledger. Missing usage and
unfinished requests remain unknown, and normalization failures retain any
usage already returned by the provider. The installed-module inventory includes
the recorder, and archived receipts are checked against their simulation,
provider, configuration, source hashes and reported totals.

The fresh qualification ran from `Big-World-CL-social-meter-v1`, using its own
MiroFish checkout, database and backend on port 5002. It used the unchanged Qwen
server and two employees from the existing workplace configuration; only the
analyst had representative prompts. Its artifact is
`lifespan/artifacts/native-social-usage-v1`, with plan SHA
`fa5f1d5474469d8d9f542aed1bf62e9f797a78de879c3d16272397e0e6a57b52`.
Both employee decisions passed their native receipt audits. The separate social
ledger records **2 dispatches and 5,123 reported tokens**; the interview ledger
records **2 calls and 5,218 reported tokens**. Neither ledger has unknown usage.
This qualifies these native receipt paths, not other bootstrap providers or a
learning effect. Historical runs remain unmetered in their original scope.

The qualification service `bigworld-native-social-usage-v1` completed
successfully (invocation `b1db7b84da6147bca78271b7eede3f7f`). Its temporary backend
was then stopped. The full `tests` and `lifespan/tests` suite passed **1,074 tests,
6 skipped**, in 118.15 seconds under `bigworld-social-meter-tests-v1`, invocation
`98482e1adf8c4b4894b16531b2d94091`. The isolated-checkout dependency issue and
old four-file preflight inventory found during validation were resolved before
this final run. All 22 qualification files were copied locally and checked
against remote SHA-256 hashes. The inventory SHA is
`7b41de8d4364927197c67a78fac7da4fe2f467aeb94e851a00529fb63a93ffe0`;
the local evidence is `lifespan/artifacts/native-social-usage-v1-h200`.

At **22:40:09 UTC on September 14**, both original study processes remained
present. The pilot control arm had reached day 8 with 23 fully graded attempts,
374 work/judge calls and 5,135,298 reported work/judge tokens. Scale seed 401's
control arm was on day 1 with 20 fully graded attempts, 281 work/judge calls and
3,514,676 reported work/judge tokens. No learner update or paired learning result
had completed. Neither active study checkout nor its installed backend changed.

## Pilot control complete; learner arm running

By **22:48:54 UTC on September 14**, the pilot had completed its control arm and
started a fresh SkillOpt arm under the original service PID and invocation. The
control produced 27 graded work attempts, using 445 work/judge calls and
6,119,480 reported work/judge tokens. Its 27 employee decisions used 28 metered
interview calls and 200,703 tokens. Initial social usage remains unknown.

The separate control-only audit uses the original `31a59a7` implementation. It
rebuilds the workplace chronology, verifies all 27 work attempts and native
employee receipts, checks the original seed skill throughout, and reconciles
the four planned probe obligations and resource totals. Both scheduled control
update records exactly match the zero-cost, unchanged-skill no-op policy. The
input inventory was unchanged by the audit, which made no model calls. This is
not the full paired audit or a statistical analysis.

The audit artifact is `Big-World-CL-lab/lifespan/artifacts/native-workplace-control-audit-v2`,
with plan SHA `903fc598e429d89365221dddd7529b91d3d816e8cc86f211701116f9da43b3e9`.
Its three files and exact audit driver were copied locally and hash-verified.
The earlier auxiliary v1 check is retained: its assertion incorrectly required
an empty control update list, instead of verifying the normal no-op records.
No experiment record or frozen source was changed to correct that check.

A zero-call timing diagnostic selects only control observations released by the
fixed first update cutoff, day 6, using the original chronology/lineage selector.
For the pinned K2 gate schedule, repeated observed work durations give candidate
cycle proxies of 3,054.41 seconds for the analyst and 3,398.25 seconds for the
editor, before optimizer/setup overhead, against a 3,600-second epoch budget.
These are planning proxies, not measured replay latency, feasibility guarantees,
ETAs or learning outcomes. Actual learner history and candidate execution can
differ. The diagnostic is `lifespan/artifacts/native-workplace-time-budget-v1`,
with timing SHA `28240cbb0f217f910900ee1f45e703e2e99c2a70a42aba19ab9a4f670aa130cc`;
the local copy's hash, selections and arithmetic were checked. The next relevant
resource evidence is the first actual learner epoch's ledger; budgets remain
frozen in both running studies.

At **22:54:20 UTC**, the pilot SkillOpt arm was on day 1 with three graded work
attempts. Scale seed 401's control arm was on day 2 with 26 graded attempts.
Both original main processes remained present. No SkillOpt update or paired
learning-effect result had completed at that snapshot.

## Replaceable evaluator and audit validation

Commits `d173d65` and `e1cefb7` add judge factories alongside the harness and
learner factories. The task-world CLI accepts `--judge-config`; the shared
controller validates normalized scores/accounting before releasing feedback and
routes both online and replay audits to the selected judge. The built-in r3
scoring function is unchanged. Its source/evidence/aggregation checks now live
with the grader. A configured evaluator binds its bank, provider, source and
configuration, and prospective analysis requires that exact configuration before
execution. Missing model identities leave same-model status unknown.

An alternate binary-evidence fixture completes a 20-session world pair and one
learner replay without Internal r3 rubric or verdict files. It checks native
receipt routing, score tampering, invalid returned grades, source-bank mismatch,
factory changes and analysis preparation. These are interface tests, not native
JobBench qualification or evidence of a learning effect.

On H200, the original `31a59a7` auditor and the configured `d173d65` auditor each
accepted all 27 completed pilot control attempts. They produced identical
attempt/hash/call/token rows and preserved the complete input inventory. AST
comparison confirms the runtime `FrozenRubricJudge.grade` function is unchanged.
This read-only regression made zero model calls; the 445 calls and 6,119,480
tokens in those receipts remain historical work, not new qualification costs.
The six qualified grader/controller/audit modules are byte-identical in
`e1cefb7`.

The final full suite at `e1cefb7` passed **1,083 tests, six skipped, in 118.29
seconds**. It ran under `bigworld-judge-adapter-tests-v3`, invocation
`9ac49d09193a4803a4f2fab99f7b966b`, and exited successfully with no main process
remaining. An earlier test launch was interrupted because it incorrectly set a
global inference profile without model/endpoint settings; a targeted existing
fixture reproduced `invalid_actor_provider_model`. The corrected environment
also passed the preceding `d173d65` suite, 1,080 tests and six skipped. Both logs
and the launch-error note are retained. No experiment was interrupted.

The evidence package is
`Big-World-CL-lab/lifespan/artifacts/judge-adapter-validation-v1` on H200, with a
verified local copy at `lifespan/artifacts/judge-adapter-validation-v1-h200`.
All 16 files (477,817 bytes) were checked after safe extraction. `VALIDATION.json`
SHA-256 is `2bc221d42326bce6c6a0307dba2ad57ec3785213737d0e69eb2630421065a890`;
the archive SHA-256 is
`4bcfaeaa793cd64f8f8895e6776cc01afa39351ba6cbab408e471ec0c8973357`.
This package establishes adapter/audit regression, not judge accuracy or a full
paired experiment result.

At **23:14:32 UTC September 14**, the original pilot and scale main processes
remained live with their original invocation IDs. The pilot SkillOpt arm was on
day 3 with nine graded attempts, 131 work/judge calls and 1,714,353 recorded
tokens. Scale seed 401's control arm was on day 2 with 38 graded attempts, 538
work/judge calls and 6,921,381 recorded tokens. Neither had a completed SkillOpt
update. The running studies, their budgets, backend, source checkouts and frozen
analysis remain unchanged; the next learning evidence is the pilot's first
scheduled update at day 6.

## Editorial working-day consistency diagnostic

The source task `internal/euw_v1_fr_014` explicitly includes Saturdays in
working days and excludes Sundays plus five named 2025 holidays. The production
supplement covers calendar subtraction but does not yet cover working-day
counts or the strict `<10` flag. Commit `07b9051` adds a separate read-only
diagnostic for these two calculations; it does not change the production
grader, historical scores, skills or active study configuration.

The H200 diagnostic selected every completed attempt of this calibration-training
task in the pilot control arm, independent of score: **four attempts, 144 CSV
rows**. All working-day counts and threshold flags matched the stated arithmetic.
No additional arithmetic defects were found. This checks consistency with the
candidate's stated delivery/review dates; it does not establish that every date
choice, translator assignment, status or narrative judgment is correct. The
four attempts belong to one dependent task family.

Eight hand-calculated controls cover Saturday inclusion, Sunday exclusion,
holiday boundaries, nine versus ten working days, and a negative interval.
The targeted suite passed **11 tests in 0.80 seconds** on H200, including comparison
against explicit date enumeration. The offline auditor reproduced the four
attempts, and a copied diagnostic with one attempt omitted was rejected even
after its results and summary were rebuilt. The complete original control file
inventory remained unchanged. All this work made zero model calls.

Frozen source is `/home/inference-testing/apps/Big-World-CL-editorial-arithmetic-v1`
at `07b9051`; artifacts are `lifespan/artifacts/editorial-arithmetic-control-v1`
there. The local copy is `lifespan/artifacts/editorial-arithmetic-control-v1-h200`:
11 files, 276,715 bytes, all hash-verified after extraction. The plan SHA-256 is
`104896dae3208c003d99b9b8b0cd1e4dffa1cc0b9ac79aa71ad4d6586170896d`, report SHA-256
is `5d444c4cda6d1edb1fa33d52397009102d7e7496dd7c4260b2324b91d4968e15`, and archive
SHA-256 is `2dc58959670f3aea30fa6dc2b504afed7ae57ebd2e26cd9200fe5cfd600f5e19`.

At **23:22:05 UTC September 14**, both original experiment main processes remained
live. The pilot learning arm had reached day 5 with 14 graded attempts, 197
work/judge calls and 2,346,201 recorded tokens. Scale seed 401's control arm was on
day 3 with 39 graded attempts, 559 calls and 7,357,173 recorded tokens. No
SkillOpt update had completed. Actual consolidation costs and adoption evidence
remain the next required observation; the original per-update budgets and study
service limits remain unchanged.

## First-update expectations and employee-context exposure

At **23:27:44 UTC September 14**, before any day-6 learning replay, the original
pilot source selected two released training cases and two validation cases for
each employee. The saved state and every selected attempt hash were verified.
Day-6 work releases its feedback on day 7 and cannot alter this selection. The
expectations artifact is `lifespan/artifacts/native-workplace-first-epoch-expectations-v1`
in the H200 lab checkout. Plan SHA-256 is
`4ae64467418436fbd6b66a0516bc63ef84d489e67b765d5ae8b3f0adab3e9338`;
the local `-h200` copy contains five verified files totaling 1,073,426 bytes.

A separate read-only diagnostic then reproduced all **17 saved employee views**
from the original workplace command log. All four selected training requests
were written with released validation feedback in their actor views: **nine
exposure edges**, all from families used by that employee's current validation
gate. The original request bytes are preserved in the training prompt and replay.
This confirms an available information path through employee context. It does
not prove semantic transfer, optimizer use of validation feedback, adoption or
an effect size. Original task-ID and chronology audits remain narrower than
context isolation; a passing gate in these native studies is a development
selection result, not independent held-out evidence.

The diagnostic ran twice against the same snapshot using original pilot source
`31a59a7`, reproduced identical findings, and verified its source attempt and
request receipts remained unchanged. It made zero model calls. The first
auxiliary collector incorrectly assumed that replay 000 was a training case;
its assertion failed after the exposure report was produced. That partial
artifact is preserved as v1. The corrected v2 identifies the replay against all
selected cases: replay 000 is the existing-skill validation of
`d003-french-editor-001`, completed with 10 work/judge calls and 60,468 tokens.
These are experiment costs, not diagnostic costs or a final learning ledger.

The verified H200 lab artifact is
`lifespan/artifacts/native-workplace-context-exposure-v2`; report SHA-256 is
`b60ac6ac3044e8ec3f303defddbc0761e30dcc9489bff45e9456af2527f309a5`.
Its local `-h200` copy contains five verified files totaling 31,361 bytes;
archive SHA-256 is
`0d583ef0919276646a7f03d27a7b417a45124aa33547608c873ef79e47374063`.
The diagnostic and expectations snapshot are evaluator-side evidence and must
not be mounted into solver or optimizer workspaces.

At **23:34:43 UTC September 14**, both original main processes were live with
their original invocation IDs. The pilot learning arm had 17 completed work
attempts, 242 work/judge calls and 2,914,074 recorded work tokens. Its first
French-editor epoch had one completed replay and replay 001 in progress, with
no finalized update or adoption. Scale seed 401's control arm had 47 completed
attempts, 683 calls and 9,306,398 recorded tokens on day 3. Frozen experiment
code, active backend, inference flags and per-update budgets remain unchanged.

## Prospective validation isolation

Commit `c833481` adds `validation_context: isolated_public_tasks_v1` for fresh
studies. It freezes distinct public validation families outside live arrivals,
omits the gate catalog from employee-adapter input, and supplies the original
public gate instruction to learner replays without employee context or an
invented observed grade. All ordinary pre-probe arrivals now use the training
pool. Work opportunities, deadlines and learner replay budgets retain their
declared limits. This changes the workload and is not a repair of either active
historical study. Repeated gates remain adaptive development selection data.

The local 26-test regression passed, followed by five targeted checks after the
final dispatch guard and employee projection changes. On H200, the full suite
passed **1,093 tests, 6 skipped, in 119.03 seconds**. The test service was
`bigworld-isolated-validation-tests-v1`, invocation
`af61379079684e199b1272b9aa132a4a`; its driver completed at **23:45:16 UTC
September 14**. Frozen source is `Big-World-CL-isolated-validation-v1` at
`c833481`. No new model calls were made by this qualification.

The tests include a complete saved fixed-world audit with validation replays
but no fabricated validation work attempts; a two-employee driver that
deliberately echoes feedback through notes and colleague messages; injected
validation context and wrong-bank-partition rejection; and pinned native
SkillOpt reflection with validation-only canaries and forced fixture training
failures. The latter verifies routing with callbacks, not live model behavior
or successful learning. Original native employee experiments remain necessary.

Deterministic compilation against the verified real bank passed twice for both
configurations. The small world has 20 arrivals (16 train, 4 probe) and four
gate descriptors across two employees. The larger world has 240 arrivals
(192 train, 48 probe) and 24 gate descriptors across 12 employees. Sparse
calibration remains one direct plus one default in the small world, and one
direct, two role transfers and nine defaults in the larger one.

The H200 qualification artifact is
`lifespan/artifacts/isolated-validation-qualification-v1` under the frozen source;
report SHA-256 is `b94adc78ac243566a3b4ec2a62cdceccae7e9bf8ee33cb934f6d87f5b1397329`.
Its local `-h200` copy contains seven verified files totaling 203,696 bytes.
Archive SHA-256 is
`703302365a17a839f58fe553ce712d3865f8fd36c21d8f34159fa5481c1df486`.

A fresh seed-317 native pilot is **prepared, not dispatched**, at
`Big-World-CL-isolated-validation-v1/lifespan/artifacts/native-workplace-isolated-validation-v1`.
Its study SHA-256 is `76255751d34445298b7974773a76211da8a5cbb766103bb9e10e875cccad6cf2`.
The pair plans 40 obligations, at most 80 work attempts and two employee updates;
its 96-million-token reservation ceiling is not measured cost. It uses the same
Qwen endpoint, native Hermes and SkillOpt pins, with separate social metering
enabled. Its employee backend is the previously qualified
`Big-World-CL-social-meter-v1/MiroFish/backend` on port 5002, stopped at preparation.
The existing experiments use their original backend on port 5001.

The two prepared files were copied locally to
`lifespan/artifacts/native-isolated-validation-plan-v1-h200`, totaling 160,510
bytes, with the study hash checked against `PREPARED.json`. Archive SHA-256 is
`58e2b5f9a97b59032e0448103aeebc0264ac8c15edf2e6105df1f9a2e1fa8a86`.
There is no execution marker or native world directory yet. Inspect the
original pilot's first finalized learning ledger before adding another model
workload; its unchanged one-hour per-update budget remains an operational
constraint. At preparation, backend startup, native execution, paired audit and
actual learning/deployment evidence were pending.

## Isolated pilot backend ready; original replay audit

At **23:50:54 UTC September 14**, the separate backend was live under
`bigworld-isolated-validation-backend-v1`, PID **1948435**, invocation
`f8d694fe190844189dfa3aff3905e82c`. Its process working directory and loopback
port-5002 listener matched the prepared pilot. The frozen `c833481` installation
checker verified all five tracked override files, the pinned MiroFish revision
and patch, and the local capability route with network/process dispatch denied.
The subsequent live capability GET matched the frozen client contract. This
qualifies installation and API readiness, not a new employee simulation.

The original pilot, scale controller and port-5001 backend retained PIDs
1853105, 1861095 and 1824221. The Qwen model-list GET and container start timestamp
confirmed the existing inference server. The separate backend startup and these
checks made zero model calls. The prepared isolated pilot still has no execution
marker. Its backend has an 8-GiB memory ceiling and a 24-hour service lifetime;
the frozen experiment budgets have not been changed.

The readiness artifact is
`Big-World-CL-isolated-validation-v1/lifespan/artifacts/isolated-validation-backend-readiness-v1`.
`READINESS.json` SHA-256 is
`a31bc40a9308023a29af42121ac7457eb681ac30458ef5ac2ac97923585154ab`.
The local `isolated-validation-backend-readiness-v1-h200` copy has four verified
files, 16,251 bytes; archive SHA-256 is
`118667a8c8866bc39f03278c4936728104530fa7c84fba0117c0e38150e896ab`.

A separate original-source audit at **23:51:55 UTC** covered all six replay
receipts finalized at capture in the first French-editor epoch: two validation
replays and four training replays, all using the seed skill. Each request matched
the pre-update selection and original employee message; original input hashes,
native execution, deployed skill, grader evidence and combined usage passed the
frozen `31a59a7` auditor. Source receipts remained unchanged. The six attempts
recorded **96 work/judge calls, 1,307,272 tokens and 1,246.46 seconds**. These
seconds are summed attempt durations, not the complete epoch's wall clock or
final ledger. No update receipt existed when the audit finished.

That audit made zero model calls and establishes neither optimizer activity nor
adoption or validation independence. Artifact
`Big-World-CL-lab/lifespan/artifacts/native-first-epoch-partial-audit-v1` has report
SHA-256 `4d46cac8825c5ace3db1a614074bd20cdfa50db5d1ff7f9d59761cea03c0ab1d`.
Its local `-h200` copy has three verified files, 15,863 bytes; archive SHA-256 is
`5b038d288e706f51cfc5655e09436a2487ef8fde9924a6139bdd80ed41b58d68`.

## Completed native pilot and preserved scale failure

By **03:14 UTC September 15**, the original pilot service was inactive with
`Result=success`. Its full audit ran under the original `31a59a7` source and
passed **52 work attempts, 24 learning replays, 52 employee decisions and one
world pair**. The study-file inventory was unchanged and the audit made zero
model calls. Neither employee adopted a skill.

| Arm | Work attempts | Rework | On-time probes | Work/judge tokens | Learning/replay tokens |
|---|---:|---:|---:|---:|---:|
| No learning | 27 | 7 | 2/4 | 6,119,480 | 0 |
| SkillOpt | 25 | 5 | 3/4 | 4,773,084 | 5,107,024 |

Employee interviews added 379,694 measured tokens; original bootstrap/social
usage remains unknown. The +0.25 probe fraction difference cannot demonstrate
skill learning because both arms deployed the seed skill throughout. The one
dependent world pair and documented validation-context exposure are additional
limitations.

Both day-six updates completed within their original budgets. The French
editor used 213 target calls and 3,200,659 tokens over 2,272.90 seconds. Its
candidate's mixed gate score fell from 0.5833 to 0.5, including a validation case
that fell from 0.1667 to zero. The analyst used 168 target calls and 1,906,365
tokens over 1,421.58 seconds; its candidate fell from 1.0 to 0.7083, with one case
falling to 0.4167. Each epoch made one optimizer call and 12 replays. Both
candidate edits were rejected; the subsequent final replays used the unchanged
seed skill. The finalized train/validation IDs matched the selection captured
before any learning replay at 23:27:44 UTC September 14.

Artifact `Big-World-CL-lab/lifespan/artifacts/native-workplace-paired-audit-v1`
has `AUDIT.json` SHA-256
`46f4bdfb5b664a07064febf396aa241819d45f4ff4480ad7a65def456fafb6a5`.
Its eight-file local `-h200` copy is hash-verified (649,513 bytes); archive SHA
is `4d5bd9fe498d4950789c51b20718ddbf680f66dcbee9f2bd08508f5125de432d`.

The original six-world scale service failed at **00:23:21 UTC September 15**,
with exit code 1 and no completed arm. Its first control world had 71 graded
attempts, 1,067 work/judge calls and 14,930,114 work/judge tokens. Both returned
responses for `d005-operations-fr-002-000` were complete, metered and within the
API token/time budgets, but their `working_notes` contained 1,900 characters
against the then-enforced 1,800-character acceptance limit. Every other field
passed the original schema. The permitted repair repeated the same overlong
notes; its generic error did not identify the field or limit. These two requests
consumed 14,770 measured tokens.

That failed study is preserved and cannot fulfill its original six-pair analysis.
The original-source diagnostic is
`Big-World-CL-lab/lifespan/artifacts/native-scale-wire-failure-v2`, with report SHA
`9a62b67e375060f1d43982978fcc67005397b7dcd5f2b8ce1a4d936ac5e27252`.
Its five-file local copy is verified (611,356 bytes); archive SHA is
`23edac2629704a60c18f2dddf411f4b5f4d39fc6b5961d9dc00d44840271d935`.
The first diagnostic collector stopped before source reads because it imported
a newer progress helper from the older checkout; that separate collector failure
is recorded and did not change the experiment.

The isolated pilot launched at **03:16:17 UTC September 15** under
`bigworld-native-workplace-isolated-validation-v1`, invocation
`f4fd3393ba9147fb97e5cfac824d2cb8`, PID 1981529. It uses the previously frozen
`c833481` study and port-5002 backend. Launch records are retained in
`native-isolated-pilot-launch-v1`; the three-file local copy is verified
(7,350 bytes), with archive SHA
`c5565b4cefe3524ead943222f43e327cb9426b161e8d797f8d857ac7e6fa4871`.

## Shared inference concurrency 64

The new gateway runs under `bigworld-inference-gateway-v1`, invocation
`34fb717a3e7246f4872518d4c321492a`, from frozen source
`Big-World-CL-concurrency64-v1` at `df3548e`. It serves
`http://127.0.0.1:8010/v1`, forwarding unchanged requests to the existing Qwen
server on port 8000. Port 8001 was already occupied and was not changed.
Its dedicated Python environment uses aiohttp 3.14.3. It admits at most **64
requests**, holds slots through streaming EOF and reports queue/concurrency/error
counters without logging prompts or retrying requests. Existing direct port-8000
clients are outside this new limit.

At **03:35:10 UTC September 15**, all **64 concurrent structured Qwen Responses
requests** completed with the expected IDs and JSON shape. The measured peak
was exactly 64, with no gateway or model response errors, and the batch took
**3.725 seconds**, consuming 2,870 input and 9,603 output tokens. This is a
constructed concurrency canary, not full-workplace throughput or learning evidence.
H200 artifact: `Big-World-CL-lab/lifespan/artifacts/inference64-native-v1`.

New source `c9d9fe3` removes unenforceable character limits from actor schemas,
employee notes/messages, generated profiles and learned skill documents. Prompt
guidance requests concise text; API output-token budgets remain. The generation
and acceptance schemas now agree. Native optimizer edit arrays also use a
registered JSON schema; its request/receipt audit passed a real one-call Qwen
qualification (113 tokens) in `concurrency64-optimizer-format-v1`.

The new scale configuration sets work, world-pair and employee-update concurrency
ceilings to 64 and uses isolated validation cases. Independent pairs and employee
epochs run in spawned processes; each employee's native SkillOpt replay/gate
sequence is preserved. A complete offline fixture audited two overlapping world
pairs, 80 work attempts and four replays, including separate employee update
processes. A failure fixture retained its failed pair and joined its successful
peer. These are execution tests, not measured model improvements.

The H200 source suite at `c9d9fe3` passed **1,094 tests**, with seven skips and
one stale test expecting the optimizer's old unstructured request. After updating
that expectation, all **nine provider-contract tests** passed against the same
frozen production code. The original and corrected test outputs are retained in
`concurrency64-qualification-v1`. The gateway's three real HTTP concurrency and
streaming tests passed separately in its dedicated environment. Initial broad
pytest collection encountered unrelated upstream `scripts` namespace collisions;
the source suite uses the established `tests lifespan/tests` scope.

The updated port-5003 backend passed installation/capability checks and **12/12
native employee decisions** across the declared roles and languages. Interviews
used 35,558 measured tokens; 12 initial social calls used 30,871 tokens, with no
failed or unknown-usage receipts in either category. Other bootstrap usage is
still outside that meter. The qualifier is
`Big-World-CL-concurrency64-v2/lifespan/artifacts/native-concurrency64-employees-v1`.

The fresh six-world study launched at **03:46:41 UTC September 15**, under
`bigworld-native-workplace-concurrency64-v1`, PID **1998836**, invocation
`f4139a9cc92d4f65b770f542f353ad08`. It has a 64-GiB controller-group ceiling and
the original seven-day maximum runtime. Frozen source is `c9d9fe3`; study SHA is
`0b59f2cf49d456965720ec2033a1f1b80b2b127579601a344b10e3ec4496efb6`.
Its separate analysis was frozen before dispatch, with plan SHA
`1629d82724d519f2506d87ba905ad80bef59366e471e2a7ecf5d857c1aa0e8eb`.

The study retains six seeds, 12 employees per world, three departments, three
languages and 20 simulated days. Only one employee has supplied examples per
world; two use explicit role/language transfer and nine retain defaults. There
are 2,880 planned obligations, at most 5,760 work attempts and 216 possible
learning epochs. The 7.776-billion-token reservation is a ceiling, not measured
consumption or a prediction. Work and learning budgets retain their prior values;
throughput comes from concurrent independent execution and the shared endpoint.
The study remains development-only and must finish all pairs and original-source
audits before its planned analysis can run.

### Sustained-load failure and throughput qualification

The short concurrency canary did not establish sustained workplace performance.
World 433 failed on its twelfth employee decision: native receipt
`5bc7e16e249bb2666b8adfec171ed3f9a4f883dd63f74842f2c11f7ca7c5aeb0`
records one dispatched request, `APITimeoutError` after 120.103 seconds and
unknown usage. The backend returned HTTP 504 at 03:50:41 UTC. Its failed pair and
inflight marker remain intact. By 03:56:57, 11 work attempts had finalized across
the other worlds: two fully graded and nine with incomplete grading. The
six-pair analysis cannot pass with this failed pair.

Original-server logs during this load show approximately 130–220 generated
tokens/second with roughly 48–62 running requests. The optional Hermes
`/v1/props` discovery probes returned 404; observed inference POSTs returned 200.
HTTP 200 does not establish complete inference or valid grading. A vLLM grammar
decoder error at 03:49:56 is retained, but cannot be causally bound to the timed
out actor from the available request IDs. Gateway cancellations include client
disconnects and cannot all be labeled inference failures from its aggregate
counters.

The completed qualifications, source test logs, immutable study/analysis plans,
launch record, native failure receipt and partial operational snapshot are copied
to `concurrency64-operational-evidence-v1-h200` locally. All **219 files** are
hash-verified (8,721,771 bytes). Archive SHA-256 is
`12a32b48f2eac5666eedad650856132292410781ac73a98bf86c9465724fecc9`;
provenance SHA-256 is
`f5e54939a2c97e0bd31f682b77eb973a5727b6492205d1f0eab5c267265346c8`.
The canary's response files are normalized JSON; its raw-wire hashes are distinct
from the stored-file hashes and raw response bytes were not retained.

A separate qualification-only container started at **03:55:14 UTC September 15**
on previously idle GPUs 4–7, exposing loopback port 8002. It keeps the same pinned
model, image and original flags except that MTP speculative decoding is disabled.
The original inference container and active studies are unchanged. This tests a
throughput configuration; no speedup is established yet. vLLM describes
[speculative decoding](https://docs.vllm.ai/en/latest/features/speculative_decoding/)
primarily as a latency optimization for medium-to-low request rates.

New source also replaces the judge's 900-rule character-bounding grammar with a
compact JSON schema. Criterion identity, exact keys and field types remain
enforced; explanation verbosity and quoting source language are prompt guidance.
The judge identity advances to version 9, so existing experiments continue to
audit against their frozen implementation. Nineteen targeted transport, provider
and world tests pass. Native sustained-load and semantic qualification of this
new judge/server combination remain pending.

### Qualified throughput endpoint and fresh six-world execution

At **04:00:42 UTC September 15**, the new no-MTP server and compact judge schema
completed all **64 concurrent semantic controls**, matching every known label.
The batch used 171,062 input and 17,747 output tokens in **19.550 seconds**
(907.76 output tokens/second over batch wall time). Median latency was 17.135
seconds, nearest-rank p95 19.144 seconds and maximum 19.542 seconds. Gateway peak
was exactly 64; there were no response errors, timeouts, cancellations or unknown
usage. These repeat 11 source-grounded development controls from one family,
with distinct request prefixes. They are not independent outcomes, a general
judge-accuracy estimate, or a measured workplace speedup over the previous run.
All raw response bodies are retained and checked against receipts and labels.

The new model container is `bigworld-qwen38flashnext-throughput-v1`, ID
`4c8b66ae53cf375ae7df068dbdafd06ac0ef5e94a2e5393b5c1ab6791f0782b8`,
started at `2026-09-15T03:55:14.893638712Z` on GPUs 4–7. Its gateway is
`bigworld-throughput-inference-gateway-v1`, invocation
`dae9ce4a2ad3459987e94a053820dee6`, serving `http://127.0.0.1:8011/v1`.
The native backend uses port 5004 under `bigworld-throughput-backend-v1`,
invocation `e27fd378875d46d7a01a3de1af629009`.

Both concurrent Hermes work controls completed and passed original-source
receipt audits: **19 calls and 110,101 tokens**. The optimizer's structured
edit-array call passed its request audit, consuming **111 tokens** in 1.054
seconds. All **12 native employee decisions** passed: interviews used 36,057
tokens and the 12 initial social calls used 30,810 tokens, with no unknown usage
in either measured category. Other bootstrap usage remains excluded. The native
qualifier's plan SHA is
`3e40e7660af341613efb03d9892a312d3ac5d818c1858980be7195732a0ecf84`;
the harness plan SHA is
`578d9e17d52c389fbc07eb9b1737fca51855c82d1ad474dbeb814242ecabbcb9`.
An additional 14 judge-adapter, parallel-execution and learner-audit tests passed,
bringing this source change's targeted verification to 33 passing tests.

Two operator setup errors were caught before model dispatch and preserved:
the new installation initially lacked the tracked `actor_contract_transport.json`
file, and the standalone optimizer qualifier initially omitted `current_day`.
The missing file was installed, the installation checker passed, and both
qualifiers were rerun in fresh output directories. Their failed destinations
remain visible; neither is a model-quality failure or a discarded experiment.

The fresh study launched at **04:05:17 UTC September 15**, from frozen
`2c65a2c735ef9c8bf0e556f86f8da06ba824b033`, under
`bigworld-native-workplace-throughput-v1`, PID **2032157**, invocation
`131820fd4ad14bcdaaee1517d0b79597`. It uses the qualified gateway, native backend
and judge v9, with the same six seeds, 12 employees, 20 days, sparse calibration,
isolated validation and original budgets. Its study SHA is
`e123fbef42107320a5e4a5b5e45e19da626dc873402431db594aff64f42be65c`;
its analysis was prepared before dispatch with plan SHA
`2e5ba605cb72f28947434e314bc841cd6d07dff0a5a7c868eb14c9676e95e3e4`.
At **04:08:04 UTC**, all 72 initial employee decisions were recorded and all
six work waves were active, with no finalized work receipts yet. No learning
effect or completed-pair result exists at that observation.

The preceding concurrency run was deliberately interrupted at **04:07:13 UTC**
after one pair had failed and 55 work attempts had finalized with widespread
incomplete/ambiguous accounting. SIGINT targeted only its controller service's
processes. Before/after snapshots and the stop intent are preserved in
`native-concurrency64-stop-v1`; by 04:08:04 its MainPID was zero and its transient
unit was absent. This is an operator-stopped failed run, not successful completion.
The separate isolated-validation pilot had already failed at **04:02:06 UTC**
with `Unscored or invalid work attempt`, preserving its day-seven work marker.
It was not stopped by that SIGINT. Both original inference-container flags and
start time remain unchanged; their frozen study artifacts were not rewritten.

The completed qualifications, raw 64-call benchmark, fixed study/analysis plans,
launch receipt and partial operational observation are in
`throughput-operational-evidence-v1`. It contains **423 files, 11,484,996 bytes**;
archive SHA is
`f59d511ec666a3d60e236a083c0add6862f9909fb92c3810c03acd6ddd2787b5`,
and provenance SHA is
`aa970ef0c74f08e477068104d00c6dfe13c2739795e1eefef84ec7c005a42eaf`.
The local `throughput-operational-evidence-v1-h200` copy is fully hash-verified.

At **04:10:06 UTC**, the replacement study had **23 finalized work attempts**,
all fully graded with complete recorded accounting: 219 work/judge calls and
1,337,722 charged tokens. All six worlds remained on their first work wave.
Recent server intervals reported 1,492–1,744 generated tokens/second. Those are
live workload observations, not a matched speedup measurement. No server engine
errors were present in the launch-to-observation log. Gateway aggregate counters
also include optional metadata probes and client cancellations; they must not
be interpreted as inference-failure counts without path-level evidence.

### Truncated verdicts and judge version 10 qualification

The throughput study subsequently produced incomplete judge responses at the
4,096-output-token API cap. At least two had long runs of whitespace outside
JSON string values; others continued deliberating through the token budget.
Five failed grades were copied before an operator SIGINT stopped the remaining
workers, with before/intent/dispatch/after observations retained in
`throughput-format-failures-v1`. The after snapshot records 112 finalized work
attempts, 106 fully graded, and eight attempts without a final receipt. Its
systemd unit is absent and MainPID is zero. The missing unit's default success
field is not evidence of successful experimental completion. Frozen source and
study receipts remain unchanged; all six originally planned pairs remain in the
denominator. No learning effect has been established.

Judge version 10 uses a six-rule compact Unicode JSON grammar, eliminating
inter-field whitespace without limiting explanation length. The installed
XGrammar parser accepted Unicode, escapes, empty strings and a 12,000-character
string, and rejected extra fields, wrong types and inter-field padding. Prompts
request concise final evidence and rationale without narrated deliberation.

One format-only regeneration per grade is permitted for a returned incomplete
or invalid verdict with known usage. It receives the same evidence and criterion
and stronger brevity guidance, with no prior answer content. Both physical calls
are retained and charged within the original eight-call, token and deadline
allocations. Valid failing judgments are never regenerated. API errors, timeouts
and unknown usage are never retried. The auditor binds each original/repair
input and response to its metered operation and rejects changed evidence or
outcome selection. Existing frozen studies continue using their original judge.

`worldlab.qualify_saved_judges` copies and regrades every saved evidence snapshot
from a stopped development study at concurrency 64, including failed and
interrupted grades. It audits complete grades under the new implementation and
preserves every qualification outcome. These are dependent development contexts
for completion and accounting checks, not an accuracy or learning estimate.

The live version-10 grammar failed its 64-request qualification: all requests
timed out at approximately 121 seconds with unknown usage, despite passing
CPU grammar acceptance checks. The retained artifact is
`judge-v10-semantic64-v1`; no study launched on that source. The full offline
suite recorded 1,102 passing tests, seven skips and one failure caused by stale
profile-length constraints in the canonical MiroFish installation.

Version 11 returns to native JSON Schema with Boolean-first property order,
keeping the metered format recovery and concise prompts. The pinned server's
installed `XgrammarBackend.compile_grammar` passes its global
`disable_any_whitespace` setting to `compile_json_schema`. The replacement
container therefore adds `--structured-outputs-config
'{"backend":"xgrammar","disable_any_whitespace":true}'`; all other pinned
no-MTP flags remain unchanged. This is a serving change after the study stopped
and the unsuccessful qualification ended, with an idle gateway. The old
container is stopped and retained. Startup and old-server evidence are in
`throughput-compact-json-server-v1`. Live qualification remains required before
launch; grammar validity alone was insufficient performance evidence.

At 04:32:34 UTC, version 11 completed all 64 semantic requests with valid JSON
and known usage in 18.867 seconds (13,876 output tokens; 735.48 output tokens per
wall second). However, only 63 of 64 known labels matched. One missing-heading
control explicitly identified the binding violation in its evidence/rationale
but emitted `passed: true`. The strict semantic qualification therefore failed;
the prepared study `60938c943e8084811d0776fe2c46a6a1799cb036389cdc78a0e0c2dfbe1d5b10`
was not launched. A separate completion-only run of all saved work evidence
continues, without treating that as semantic qualification.

Version 12 restores the final Boolean after the evidence/rationale and explicitly
requires agreement with the stated finding. It keeps native compact JSON Schema,
prompt-only verbosity and metered format recovery. The version-11 contradictory
verdict remains a failure; it is never rewritten or retried as a valid verdict.
New version-12 qualification must retain all newly planned outcomes.

At 04:36:35 UTC, version 12 passed all 64 semantic controls with known usage in
13.240 seconds: 172,854 input and 14,388 output tokens, or 1,086.75 output tokens
per wall second. Median latency was 10.940 seconds and p95 12.339 seconds.
The saved-evidence run nevertheless encountered a 120.145-second API timeout
on `grade-0008`, retaining a 26,960-token reservation and unknown actual usage.
Version 13 keeps the exact rules and schema but permits up to 300 seconds for
each request, clipped to the existing overall grade deadline. It does not add
calls, tokens, time to the overall job allocation, or retries for unknown usage.

Both version-12 native Hermes controls passed their source audits (16 calls,
86,844 tokens); the structured optimizer check passed (one call, 555 tokens).
The employee qualifier failed before opening the native runtime because its
operator command omitted the explicit provider environment used by study
services. This zero-dispatch setup error is retained; a correctly configured
fresh qualifier is required. Source profile generation already passed the new
installation check and targeted tests without character-length constraints.
