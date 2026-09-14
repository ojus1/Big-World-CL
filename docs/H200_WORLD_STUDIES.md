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
