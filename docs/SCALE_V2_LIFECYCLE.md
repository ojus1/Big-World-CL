# Scale-v2 process lifecycle

`scripts/scale_v2_process.py` supplies lifecycle support for the separate scale-v2 checkout. It does not select cohorts, models, budgets, stopping rules, or campaign results. The launcher owns those decisions and the campaign auditor binds them to the registered contract.

The native entry points launch only this checkout's fixed MiroFish backend on `127.0.0.1:5002` and the canonical `python -u -m lifespan.evaluation.runner` command. Before service startup, a bounded interpreter probe checks the actual imported configuration module and mutable upload/graph paths. The immutable `SERVICE_READY.json` records the first successful health check and owned-socket observation, including its launch binding and readiness clock. Later observations do not overwrite that record. The service must own its loopback listening socket and retain the recorded PID, start tick, UID, boot identity, and working directory. The probe checks loaded configuration; it is not an inspection of the running process's Python memory. Environment values are never written to lifecycle receipts.

## Launcher interface

1. `validate_installation(..., env=...)` returns the source/configuration binding for the fresh installation. Its subprocess probe has a 20-second limit and requires pristine uploads by default.
2. `start_service(binding, receipt_dir, env=..., startup_seconds=120)` launches the fixed server and verifies its socket and health. Failure attempts bounded owned-process cleanup.
3. `spawn_world(run_dir=..., receipt_dir=..., env=...)` launches a fresh configured world. Each returned `Handle` exposes `process`, `poll()`, `started_monotonic`, and `ended_monotonic`.
4. Call `observe_world(handle, run_dir, service)` while the world runs. The registered interval is 0.25 seconds; scheduling delay can still cause a missed observation. Discovery visits the pinned online and learning-trial computer layouts without traversing their growing filesystem object stores.
5. `cleanup_world(..., timeout_seconds=120)` stops the controller and employee descendants, requests closure of its bound OASIS environment, then finishes owned-process and socket cleanup. `cleanup_service(..., timeout_seconds=30)` runs after every world cleanup has ended. Registration fixes these allowances separately from the execution wall budget.

Cleanup clocks include final native-file inventory, process polling and source-hash preparation. The final receipt write itself is explicitly excluded; these clocks are not a claim of zero persistence overhead. A missed cleanup bound remains unconfirmed.

A worker thread owns each world handle. Shared service observation and process discovery use a reentrant lock; HTTP requests execute outside that lock. The parent owns process-wide interruption flags. Cleanup in worker threads does not install signal handlers; main-thread cleanup temporarily defers SIGTERM/SIGINT and restores previous handlers. The launcher must stop dispatching after interruption and wait for bounded cleanup in all workers.

## Ownership and evidence

Process discovery retains observed ancestry even when a descendant starts a new session. A not-yet-created native run state, STARTING state with a null PID, or an in-progress native JSON write remains pending during bootstrap. Persistent missing identity at cleanup cannot become confirmed evidence. OASIS is a separate service descendant, bound to the world's exact simulation ID, native run-state PID, script, configuration, working directory, and service identity. Each employee worker and bubblewrap process must have been observed before its persisted `instance.json` can establish a cleanup inventory. An unobserved identity is **unknown**, not evidence that no process existed. There is no post-hoc PID guessing or claim of exhaustive kernel containment between observations.

Signals use Linux PID file descriptors. The helper opens a pidfd, rechecks the recorded identity, then signals that pinned task. It does not signal process groups, infer ownership from a PID alone, or fall back to signaling an unknown task. Replaced PIDs are left alone; a surviving or unreadable owned identity prevents confirmed cleanup. A zombie is recorded as nonrunning, distinct from PID absence. Only previously observed, correctly scoped bubblewrap aliases and their underlying Unix sockets can be removed.

`SERVICE_` and `WORLD_` receipts record intent, launch, latest observation, and cleanup. They bind helper/source bytes, configuration, fixed argv, identity, clocks, and raw receipt hashes. Service and world observation inventories must both be retained by final cleanup evidence; positively observed descendants cannot be dropped. They are private local consistency evidence, not authenticated provider attestations. Paths and argv must not be copied to public reports. Environment closure alone cannot establish process cleanup. Cleanup problems do not erase independently measured model usage or become behavioral scores.

The pure filesystem validators `validate_service_receipts` and `validate_world_receipts` perform no `/proc` access, imports of MiroFish, HTTP requests, or signaling. Their results provide raw hashes and execution/cleanup clocks for the campaign auditor. Service results also return the private launch record for world binding; public callers must omit it. Partial starts remain explicitly incomplete; completed worlds require a zero controller exit and confirmed cleanup. The campaign auditor must additionally enforce all registered slots, exact cleanup allowances, service lifetime, maximum simultaneous worlds, and the complete paired endpoint.

## Offline validation

`PYTHONDONTWRITEBYTECODE=1 python3 -S -m unittest tests.test_scale_v2_process`

Tests use temporary source/receipt fixtures, fake configuration imports and HTTP, and harmless local sleep processes. They cover detached-child ownership, unrelated-process survival, PID reuse, interrupted cleanup, concurrent service observations, launch-write failure, missing native identities, socket survival, source/identity tampering, and execution/cleanup bounds. They provide no native service or model capability evidence.
