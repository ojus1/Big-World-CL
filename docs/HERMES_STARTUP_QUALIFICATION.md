# Hermes startup qualification components

These components prepare a separately registered native startup qualification. They do not constitute a completed qualification or a deployment-learning result.

## Resource control probe

`scripts.startup_resource_controls` launches one uniquely named user service containing only a fixed, harmless Python readback. It checks the actual service MainPID and InvocationID, independent process identity and cgroup membership, and kernel CPU/memory/swap/process limits. The parent releases the child's private input pipe; it never stops an existing service. The service has a 15-second runtime backstop. Failures and missing identities remain failures rather than inferred cleanup.

A fresh probe after the host reboot verified 64 MiB memory, zero swap, 32 tasks and one CPU quota. The service was collected, its worker was absent and the control client exited zero. No native agent or model call occurred. All four raw receipt hashes and kernel values were independently reviewed. The [allowlisted observation](startup-resource-controls-v1.json) binds the exact helper and payload hashes. The I/O controller file was absent; I/O isolation and startup latency are unqualified. This tiny probe does not establish that the larger native workload fits its proposed limits.

## Native startup-only child

`scripts.hermes_startup_probe.native_startup` has no standalone execution CLI. A future owned-unit supervisor must independently establish its boundaries before releasing it. The child requires a new user/network namespace, the original unprivileged UID and boot, an exactly bound qualification cgroup/InvocationID, only a disabled loopback interface, and 4 GiB memory/zero swap/128 tasks/two CPUs. The current host supports the required unshare mapping and a nested bubblewrap namespace, as checked using harmless local commands.

The child accepts no provider credential or model configuration. It uses a fixed dummy credential and loopback endpoint, installs the initial work-process skill in a fresh native profile, calls Computer.start once and Computer.close once, and never calls Computer.run. Both source and dependency identities must be frozen by the supervisor before dispatch. A successful child result does not certify the whole qualification or independently prove descendant/socket cleanup.

The parent may supply an absolute monotonic startup deadline, at most 150 seconds away. Boundary checks, imports and profile setup consume that allowance; only remaining time is passed into native startup. STARTUP_FINISHED.json and CLOSE_STARTED.json are written before close. Receipt writes consume the at-most-30-second cleanup allowance, which cannot extend the original startup deadline plus 30 seconds. Those receipts allow the independent supervisor to distinguish startup delay from cleanup delay. An optional before-close gate lets the registered supervisor capture live worker and sandbox identities. Its wait consumes the same cleanup allowance, and callback errors remain explicit; the gate grants no extra time. Blocking filesystem operations and Computer.close still require the outer unit watchdog. Missing or failed phase receipts must fail the qualification audit.

## Why a network boundary is required

The pinned Hermes constructor is not HTTP-free. Source review found that accessing ContextCompressor.context_length can resolve model metadata, and custom loopback endpoints may trigger local server detection, model-list requests and Ollama metadata probes. Initialization also starts local environment probes and discovers configured plugins. No conversation-generation call was found in the inspected custom-provider constructor, but a dummy key or absence of a work request cannot prove absence of network activity or plugin side effects.

The qualification therefore confines provider networking before importing native Hermes and keeps metadata-request attempts distinct from model-inference evidence. A network-isolated startup is a component test with an explicit environmental difference from live deployment. It does not test the provider transport, model reliability, actor simulation or long-horizon learning.

## Validation and next step

The resource helper has 22 offline tests. The native child has 18 pure/fake-computer tests, including namespace/cgroup rejection, fresh-state refusal, deadline consumption, no work dispatch, sanitized errors and incomplete-evidence handling. Independent reviewers checked both components and the timing changes. These tests do not launch Hermes or model calls.

The next step is the owned-unit supervisor and immutable nine-slot registration described in [the scale execution plan](NEXT_SCALE_EXECUTION.md). It must retain all failures and unattempted slots, forbid retries/replacements, inspect real descendant and alias cleanup, and require all nine bounded starts before treating the component qualification as passed. No new full six-world campaign has been launched.
