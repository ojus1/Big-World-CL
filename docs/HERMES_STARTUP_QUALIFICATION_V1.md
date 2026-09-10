# Native Hermes startup qualification v1

## Preregistration

This registration precedes native dispatch. It binds private manifest SHA-256 `e709a7a5d5a405abf18becb27ebfc43bc95d61db78d0b207d19b1efb16d1fca1` and execution source commit `8763faad91ed18e77e385e017d7039ccd6c1b29a`. The [allowlisted manifest projection](hermes-startup-qualification-v1-registration.json) includes all 34 source hashes, installed dependency identities, resource-evidence hashes and the fixed schedule. Private paths, environment values and host identifiers are omitted and committed by hashes. A documentation commit does not change these registered execution bytes.

The planned nine fresh native Hermes/bubblewrap starts run in batches of one, one, one, two, two and two. Every slot is retained. Each has a measured 150-second startup allowance and at most 30 seconds for cleanup. Every owned service contains its controller and native descendants, with 4 GiB memory, zero swap, 128 tasks and a two-CPU quota. These are containment limits, not reservations of startup latency or I/O capacity. The current-boot resource probe verified control availability with a smaller harmless payload, not native capacity.

Each startup installs the initial employee process skill in a fresh profile. A new user/network namespace with only disabled loopback is established before native imports. The fixed dummy credential and loopback endpoint cannot dispatch employee work: the implementation calls Computer.start and Computer.close, never Computer.run. Source inspection and the enforced network boundary support zero inference requests; this is not a physical usage-meter observation, and constructor metadata probes remain distinct from inference.

A failed start, uncertain boundary or uncertain cleanup halts later batches; already active peers finish under their registered limits. No retries, replacement slots or increased timeouts are allowed. Passing requires all nine slots to pass the strict independent lifecycle audit, including native identities, actual namespace/cgroup boundaries, measured deadlines and terminal descendant/socket cleanup. Missing evidence fails the qualification. Execution is authorized only once with the exact registered manifest hash.

An independent reviewer checked the manifest, all source and dependency hashes, resource receipts, slot schedule, current boot and private permissions before dispatch. EXECUTION.json was absent and no slots had run at that review. The implementation has 92 passing focused offline tests across the observer, resource helper, native child and supervisor; those tests did not launch native agents.

## Scope

This component test addresses the startup failure that stopped all six scale-v2 worlds on day 3. It does not exercise MiroFish actors, provider transport, employee work or SkillOpt learning. A pass permits planning the next full comparison; it does not replace six complete worlds or establish learning gain. The full endpoint remains three paired seeds, four enterprises and twelve employees per world, prospective skill deployment and independently audited outcomes, as described in [the execution plan](NEXT_SCALE_EXECUTION.md).

Native outcome: pending at preregistration. All outcomes, including failures and unattempted slots, will be reported separately without changing this manifest.
