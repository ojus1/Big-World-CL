# H200 task-world execution ledger

This ledger supplements [the architecture and calibration guide](WORLDLAB.md).
All paths below are on `inference-testing@h200-3` under
`/home/inference-testing/apps/`. Original evidence is preserved. No study here
establishes statistically significant skill learning.

## Frozen execution checkouts

| Study | Checkout / revision | Artifact directory inside checkout | State |
|---|---|---|---|
| First task world | `Big-World-CL-worlds-v1`, `4a3ab8a` | `lifespan/artifacts/development-world-v1` | Cancelled before execution after judge-format qualification failed |
| Serial engineering pair | `Big-World-CL-worlds-v2`, `6602bd1` | `lifespan/artifacts/development-world-v2` | Running; v2 judge contradiction limits quality interpretation |
| Parallel adapter check | `Big-World-CL-adapters-v1`, `3efaa9f` | `lifespan/artifacts/adapter-qualification-v1` | Complete, both native audits passed |
| Larger coverage plan | `Big-World-CL-coverage-v1`, `da88f93` | `lifespan/artifacts/development-coverage-v1` | Cancelled before dispatch; zero work/learning calls |
| Judge count controls | `Big-World-CL-judge-v3`, `cf30158` | `lifespan/artifacts/judge-count-qualification-v3` | Complete, 12/12 correct |
| Revised parallel pair | `Big-World-CL-worlds-v3`, `437de52` | `lifespan/artifacts/development-world-v3` | Running with v3 judge and two parallel employees |

The active pair services are `bigworld-development-world-v2.service` and
`bigworld-development-world-v3.service`. Their main PIDs at launch were 1794740
and 1812325. Both run under `systemd --user` with process-group cleanup, a 16-GiB
controller memory ceiling and a six-hour runtime ceiling. The shared Qwen server
remains `bigworld-qwen38flashnext` at `http://127.0.0.1:8000/v1`, using GPUs 0–3.
The controller interpreter is `Big-World-CL/MiroFish/backend/.venv/bin/python`;
workers use the pinned native Hermes environment.

## Timestamped progress, not final results

At **2026-09-14 19:55:34 UTC**:

| Pair / arm | Recorded work sessions | Physical work + judge calls | Work + judge tokens |
|---|---:|---:|---:|
| v2 control | 20 / 20 | 318 | 4,253,239 |
| v2 SkillOpt | 9 / 20 | 120 | 1,373,502 |
| v3 control | 4 / 20 | 59 | 830,995 |
| v3 SkillOpt | 0 / 20 | 0 | 0 |

These counts exclude in-flight reservations and any later work. Neither learning
arm had reached its first update at this snapshot. The control's two update
records are no-ops, with no optimization or learning tokens. Nineteen completed
v2 control attempts had passed their partial offline execution audit; that audit
does not validate judgment truth.

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
calls and 196,431 tokens. Tests currently pass 25 task-world/calibration cases,
including alternate harness receipts, sparse examples and failed parallel waves.
