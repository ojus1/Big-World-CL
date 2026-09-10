# Native startup scope qualification v3

This registration precedes native dispatch and binds private manifest SHA-256 `094dbd85fe01c49ef5d3e847c8a6b8b042ce8b2b7d077e58e9a465b14511b588`, source commit `4b75d4f190417df085865cf1c89c6a8bed44e385`, 35 execution source files and installed dependencies. The [allowlisted projection](hermes-startup-scope-v3-registration.json) publishes the schedule, limits, source hashes and hashes of omitted private context. It contains no credentials, environment values or raw host identifiers.

The [v2 qualification failed](HERMES_STARTUP_SCOPE_V2_OUTCOME.md) because its environment allowlist rejected systemd's inherited `INVOCATION_ID`. That fixed attempt and its eight skipped slots remain unchanged. This separately versioned implementation accepts exactly the registered seven environment variables plus `INVOCATION_ID`. It checks the inherited ID's format and requires its value to match the independently observed live scope invocation before native imports. It neither invents that ID nor allows arbitrary environment keys. No security profile or host policy is changed.

All other qualification requirements remain the same: nine fresh native Hermes/bubblewrap starts in batches `[1,1,1,2,2,2]`, maximum concurrency two, 150 seconds for setup/startup and at most 30 seconds for cleanup. Every scope requires live readbacks for 4 GiB RAM, zero swap, 128 tasks and two CPUs, with the declared 180-second runtime backstop and 5-second stop setting. These are containment settings, not I/O isolation, latency reservations or guarantees that blocking operations meet the measured deadline.

A new user/network namespace with only disabled loopback precedes native imports. The fresh native profile receives the initial employee skill, a dummy credential and fixed loopback endpoint. The child calls Computer.start and Computer.close, never Computer.run. Constructor metadata activity is distinguished from inference. A zero-inference interpretation requires complete source/boundary evidence; no physical model-usage meter is claimed.

The parent binds the same process through exec, its security context, actual scope invocation, cgroup, command and working directory. It holds the controller until native worker/sandbox identities, stage journals, close, process absence and exact socket cleanup are verified. Normal parent release, controller exit, actual wait status zero and terminal scope/cgroup evidence must all fit the original clock. Missing or contradictory evidence fails the slot.

The failure policy is fixed before execution: retain every slot, halt later batches after any failure or uncertain boundary/cleanup, and preserve already active peers. There are no retries, replacements, timeout increases or selected-success endpoint. All nine must pass the strict auditor. Execution is one-shot with the exact published manifest hash.

Independent review approved the exact implementation and 21 new offline tests, including actual bootstrap/worker environment guards. A combined 109-test related suite passed without native or model calls. The previous failed qualifier sources and artifacts remain frozen. Preparation alone does not execute Hermes.

Native outcome: pending at preregistration. This component result cannot establish provider reliability, learning gain or completion of the separate six-world deployment-learning study.
