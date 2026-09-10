# Native startup scope qualification v2 outcome

The nine-slot qualification did not pass. Its first controller passed the live scope checks, then failed the environment allowlist check before native Hermes startup. The attempt and cleanup took about **0.427 seconds**; this is not a Hermes startup latency measurement. The remaining eight slots were declared `skipped_after_stop`, and each lacks an audited slot receipt. The strict audit reports `incomplete`, `ok=false`, and `qualification_passed=false`.

| Slots | Recorded outcome | Evidence |
| --- | --- | --- |
| start-00 | infrastructure_failed | One failed receipt; live scope binding verified; cleanup confirmed; controller exit 1 |
| start-01 through start-08 | skipped_after_stop | Eight missing slot receipts |

The first slot's independently reconstructed binding matches its parent gate: the held controller retains its supervisor's security label, has distinct user and network namespaces, and runs in the expected scope with 4 GiB memory, zero swap, 128 tasks and CPU quota `200000/100000`. These are the recorded live controller checks. No native child directory or native before/after boundary record exists, so the loopback state and Hermes startup were not verified by this attempt.

The controller log reports `controller_environment_not_scrubbed`. The frozen implementation rejects any key outside its seven-key allowlist before calling native startup. A separate successful scope environment diagnostic found exactly one additional key, `INVOCATION_ID`, consistent with systemd's scope environment propagation. That diagnostic recorded key names only; it did not retain the value or establish that it equals the live scope's independently observed InvocationID.

The earlier diagnostic included dependency metadata lookup but returned status 1, no result, and a count of 1,199 stderr bytes. Its stderr text was not saved. The failing operation and cause cannot be established from the retained records, and this failed diagnostic is not treated as corroborating evidence for the extra key.

Cleanup of the first controller is confirmed: the recorded original process is absent, cgroup membership is empty, the scope is collected (`not-found`, `inactive`, `dead`), and socket cleanup is confirmed with nothing removed. The scope was already absent when cleanup checked it; no scope stop was requested. Cleanup took about 0.00994 seconds within its 30-second allowance. The controller exited with status 1 without normal release; successful cleanup does not make the startup qualification pass.

The [allowlisted outcome](hermes-startup-scope-v2-outcome.json) binds all ten original qualification files and all five files retained across the two diagnostics, together with the [original registration](HERMES_STARTUP_SCOPE_V2.md). All 35 registered source files still match commit `ee7e34b44560d0430fb3daba9a6076e9e42f75a8`; execution source and dependency records match the manifest. Raw artifacts and registered code were preserved.

Native inference count, tokens and cost remain unknown; no physical usage meter or native result was produced. No native startup, learning, provider, or full-world performance claim follows from this engineering failure. This registration was not retried or replaced. A corrected environment contract requires its own versioned qualification.
