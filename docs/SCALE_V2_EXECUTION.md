# Executing the six-world follow-up

The follow-up keeps the three paired development seeds, four firms and twelve
employees per world, twenty action days plus two feedback days, and the original
SkillOpt T2/V2/K2 and four-edit protocol. It uses six fresh worlds. The actor JSON
contract and nonstreaming employee transport apply to both arms. Positive gain
or a minimum number of adoptions is not a completion requirement.

`prepare_scale_v2.py` registers an explicit wall limit and evidence rationale;
it does not execute or certify the native prerequisites. The separate launcher
requires the independently reviewed raw campaign hash and exact private paths
to three reviewed observations. Before dispatch it re-audits the historical
actor capability evidence at its matching source, the corrected employee
transport evidence, and the captured six-slot horizon observation. It binds
those checks to the registered provider, installed dependencies and source.
Component and timing observations do not guarantee a long campaign will finish.

The actor proof covers the unchanged actor wire descriptor and installed native
dependencies. Its historical client files are audited at their original
revision. New client routing is additionally source-bound and audited in each
fresh world; the proof does not claim that the earlier preflight executed the
new whole-world launcher. The corrected employee proof retains its original
results and source inventory. The horizon snapshot describes streaming
development durations; it is not a nonstreaming completion forecast.

The private prerequisite-path file has exactly these keys, with absolute paths:

```json
{
  "actor": {"directory": "/private/actor-observation", "source_root": "/private/matching-source", "review_file": "/private/actor-review.json"},
  "employee": {"original_directory": "/private/employee-observation", "observation_directory": "/private/readback-correction", "review_file": "/private/employee-review.json"},
  "horizon": {"directory": "/private/horizon-observation", "review_file": "/private/horizon-review.json"}
}
```

Use the dedicated checkout with a fresh installed MiroFish backend, private
uploads/graph state and loopback port 5002. The original scale-v1 installation
on port 5001 is not a supported target. Source and registration-tool bytes must
match both the reviewed campaign and the recorded Git commit. Unrelated
documentation changes do not invalidate that byte comparison.

```bash
MiroFish/backend/.venv/bin/python -u -m scripts.run_scale_v2 \
  --out lifespan/artifacts/scale-v2 \
  --campaign-sha256 REVIEWED_RAW_CAMPAIGN_SHA256 \
  --prerequisite-paths /private/prerequisite-paths.json
```

This is a one-shot command. A durable `EXECUTION.json` prevents a second dispatch
even when setup fails before a model call. No world is resumed or replaced after
uncertain work. The launcher rechecks source/dependencies before each fixed slot.
It sends the canonical `python -m lifespan.evaluation.runner` command to each
world; the historical alias correction is not involved.

Each active world has a separate monitor for its deadline, native identities
and cleanup. A slow cleanup cannot block the other monitors. The parent owns
the service and signal handlers; interruption stops further dispatch and asks
all active monitors to clean up before service shutdown. Monitoring aims for
250 ms intervals. OS scheduling delays cannot enlarge the accepted wall budget.
Cleanup and startup allowances are separately frozen in the campaign budgets.
Process receipts verify identity before signaling and retain unconfirmed
cleanup as a failure.

`PREREQUISITES.json`, service/world lifecycle receipts, `execution_results.json`
and the final `AUDIT.json` stay in the ignored output directory. The audit keeps
all six slots and all measured costs. It emits the primary comparison only when
all six worlds, all three pairs, raw scientific checks and cleanup are valid.
Incomplete or invalid worlds never become zero-valued quality outcomes.

Offline supervisor tests use fabricated receipts, local Git fixtures and
threads; they establish scheduling, rejection and cleanup behavior, not native
reliability or learning effectiveness. Actual campaign results require the
separate preregistered execution and raw audit.
