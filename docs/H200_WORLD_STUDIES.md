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

Both live workplace-v1 and consolidation-v3 now have an
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
