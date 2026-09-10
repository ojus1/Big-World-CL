# Native startup scope qualification v3 outcome

All **nine registered slots passed** the independent strict audit. The fixed batches [1,1,1,2,2,2] completed with maximum concurrency two, normal controller release and exit status zero, confirmed cleanup, and no skipped or replacement slots. This qualifies the tested startup component; it does not complete the six-world learning study.

The first slot start through final cleanup spanned **51.893 seconds**. Every slot stayed within its 150-second setup/startup and 30-second cleanup allowances. These are disjoint charged phases; cleanup includes the pre-close gate, native close, scope witness, release, wait, and final checks. They are not isolated inference or Computer.close timings.

| Slot | Batch | Setup + startup (s) | Cleanup (s) | Outcome |
| --- | --- | ---: | ---: | --- |
| start-00 | 0 | 11.881 | 1.151 | pass |
| start-01 | 1 | 4.089 | 1.400 | pass |
| start-02 | 2 | 3.921 | 1.416 | pass |
| start-03 | 3 | 6.036 | 1.491 | pass |
| start-04 | 3 | 6.015 | 1.391 | pass |
| start-05 | 4 | 10.964 | 1.394 | pass |
| start-06 | 4 | 10.853 | 1.458 | pass |
| start-07 | 5 | 6.654 | 1.400 | pass |
| start-08 | 5 | 6.710 | 1.397 | pass |

The native journals bind each worker and bubblewrap sandbox to its fresh controller, workspace, command and scope. They cover imports, tool registration, sandbox setup, agent construction, budget/transport setup, the built-in sandbox terminal probe, and readiness. Agent-construction spans ranged from 2.098 to 8.734 seconds. These descriptive stage timings do not identify a causal reason for variation.

All nine live scope bindings matched the registered 4 GiB memory, zero swap, 128-task and two-CPU limits. The inherited scope invocation matched the parent’s independent observation, the caller security context was preserved, and native boundary checks before and after startup observed separate user/network namespaces with only disabled loopback. No host security-policy change was required. I/O isolation and latency under arbitrary blocking operations remain unqualified.

All 79 distinct process identities observed by the supervisor were recorded absent at cleanup. A separate read-only check found them absent, all nine scope cgroup paths absent, all nine scopes collected/inactive/dead, and exact control-socket/alias inventories clear. Each controller returned through normal release and actual wait status zero; no scope-stop request was needed. The parent removed one remaining underlying control socket per slot after native descendants exited and before saving the live cleanup witness and releasing the controller; no aliases required removal.

No employee work requests were dispatched. The reviewed path calls Computer.start and Computer.close, never Computer.run; the built-in terminal probe is part of startup. Complete source/journal and disabled-loopback boundary evidence supports a no-inference interpretation. Constructor metadata activity is included in startup timing. There was no independent physical model-usage meter, so physical calls, tokens and currency cost remain unspecified rather than measured zero.

The [allowlisted outcome](hermes-startup-scope-v3-outcome.json) binds manifest SHA-256 094dbd85fe01c49ef5d3e847c8a6b8b042ce8b2b7d077e58e9a465b14511b588 and terminal report SHA-256 78b0d6058ead87caf6ae0d6484a3bbdebc640f6cfe114cc5ff0ee5037fde317c. It includes exact selected raw evidence hashes, a commitment to all 336 private regular files, detailed stage timings, and the strict audit digest. All 35 current and committed source files and current installed dependency, boot and context bindings match the [registration](HERMES_STARTUP_SCOPE_V3.md). This review changed no raw artifact or registered source.

These nine starts on one host and boot establish the registered startup qualification at concurrency at most two. They do not measure live provider reliability, long-horizon enterprise execution, learned-skill performance, or a causal speed improvement. The failed v1/v2 qualifications remain preserved as separate observations.
