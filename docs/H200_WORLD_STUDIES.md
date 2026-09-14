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
| Fresh native workplace | `Big-World-CL-workplace-v5`, `31a59a7` | `lifespan/artifacts/native-workplace-v3` | Active at 21:52 UTC September 14; two completed work sessions |
| Six-world native study | `Big-World-CL-workplace-scale-v1`, `3e1719d` | `lifespan/artifacts/native-workplace-scale-v1` | Launched 21:59 UTC September 14; 12 employee decisions and first work wave dispatched by 22:03 UTC |

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
