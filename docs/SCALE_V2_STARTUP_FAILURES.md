# Scale-v2 stopped during employee startup

All six fresh worlds failed on day 3 while waiting for a new Hermes employee
worker to become ready. The campaign retained **274 returned employee sessions
and zero learning updates**. It did not reach the planned twenty workdays or
settlement drain. The registered primary comparison is unavailable; these
failures provide no estimate of SkillOpt's effectiveness.

The [public observation](scale-v2-startup-failures.json) retains every planned
slot and separates complete returned work from six unresolved startup attempts.
Its raw SHA-256 is
`ba7eaa2c4cc33b1705d3d25efc3e6810c95a6785a448ea97adfc4d8916b43651`.
The private capture contains 89 raw terminal/checkpoint/lifecycle evidence files
and all 48 registered execution/tool files. Their copied bytes and the original
files were independently rechecked. Raw task content and profiles remain private.

| Seed | Arm | Returned sessions | Measured employee calls | Measured employee tokens |
| --- | --- | ---: | ---: | ---: |
| 211 | no-learning | 47 | 478 | 5,043,705 |
| 211 | SkillOpt | 46 | 484 | 5,043,982 |
| 307 | SkillOpt | 45 | 483 | 5,064,711 |
| 307 | no-learning | 45 | 495 | 5,153,379 |
| 401 | no-learning | 45 | 482 | 5,173,627 |
| 401 | SkillOpt | 46 | 483 | 5,004,375 |

These 2,905 employee calls and 30,483,779 tokens reconcile between the copied
checkpoint physical meters and the saved final audit. They cover returned
online attempts, including unsuccessful work. The six unreturned startup slots retain conservative
reservations of 96 calls and 1,500,000 tokens; those reservations are not measured
spend. Contracted actor interviews separately account for 358 requests and
1,023,469 tokens. Bootstrap/social inference, possible server-orphan usage,
currency billing and all-in cost remain unknown.

## What failed

The recorded path is `execute_case` → `Computer.start` → `Computer.receive`,
which waits up to 150 seconds for the initial ready message. Each failure is a
`TimeoutError` at that boundary, before `Computer.run` sends the work request.
The failed attempts have no durable instance/session receipt and empty worker
logs. The exact stalled initialization stage is therefore unknown. This is not
evidence of a provider streaming error, optimizer rejection or task-quality
failure. Missing readiness also does not establish zero startup usage.

The world roots exited with code 1. No supervisor interruption or 24-hour outer
execution-limit breach was recorded. Recorded world failure-file modification
times fall between 08:02 and 08:05 UTC on September 10; these are filesystem
observations, not provider timestamps or independently measured failure onset.

Five startup workers were last observed in Linux `D` state and one in `R`
state. Host observations showed substantial I/O and memory pressure. Together,
these support a resource-pressure hypothesis, but empty logs cannot establish
the cause, an OOM event, or which initialization step stalled.

## Cleanup and audit interpretation

All 1,365 recorded owned process identities were absent at the captured process
inspection, and service cleanup was confirmed. World cleanup remains
**unconfirmed** for all six slots: the startup attempts lacked the instance
evidence needed to bind native cleanup. Four unbound control sockets remained
and were preserved. Absence of known processes and `env_alive=false` cannot
replace missing ownership evidence.

The saved strict audit reports `status=incomplete`, `ok=false`, and no additional
consistency errors. Its six failed prefixes pass their raw evidence checks, but
none is a completed world. Complete-prefix accounting does not turn an
interrupted startup into complete accounting or a failed arm into a zero-valued
quality outcome. No surviving pair, replacement world, timeout extension or
cross-campaign combination is used.

## Follow-up engineering

The scale-v2 source, registrations and artifacts remain unchanged. A separate
worktree is developing opt-in parent identity and worker startup-stage evidence,
with no automatic retry or larger startup timeout. That instrumentation is a
diagnostic improvement, not proof of startup reliability.

A bounded local process probe verified that this host can apply memory, swap,
CPU and process-count controls in a new user unit. The requested I/O weight had
no corresponding kernel controller file and was not effective. Resource limits
can contain the campaign's consumption; they do not reserve startup latency or
protect it from unrelated shared-host I/O pressure. No existing workload was
changed by that probe.

Further native qualification needs explicit resource and concurrency settings,
startup-stage and ownership evidence, fixed limits, and all attempted slots
retained. Another complete comparison requires a separate full registration;
none has been launched from this failure observation.
