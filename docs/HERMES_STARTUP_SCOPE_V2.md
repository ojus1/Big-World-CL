# Native Hermes startup scope qualification v2

## Preregistration

The private manifest SHA-256 is `bee0bbe3f6d4942922125d7b2d001a66799424b5f0daa393686642fd4797f1f7`. The [allowlisted registration](hermes-startup-scope-v2-registration.json) binds source commit `ee7e34b44560d0430fb3daba9a6076e9e42f75a8`, all 35 execution source files, native dependencies and nine unique planned slots. Host identifiers, private paths, environment values and exact unit names are omitted and committed by hashes. This registration was prepared before any native dispatch.

This is a new qualification of a different process-ownership model. The [failed service-context registration](HERMES_STARTUP_QUALIFICATION_V1_OUTCOME.md) remains unchanged. A caller-launched systemd user scope preserves the existing caller security context; no host policy or AppArmor profile is changed. The harmless [scope diagnostics](SCOPE_CONTEXT_PROBES.md) motivate this launch method, but do not establish native startup capacity.

The fixed schedule is three sequential starts followed by three batches of two: nine fresh native Hermes/bubblewrap instances, maximum concurrency two. Each startup has 150 seconds including setup and observation overhead, followed by at most 30 seconds for cleanup. The owned scope has 4 GiB RAM, zero swap, 128 tasks, a two-CPU quota, a 180-second runtime backstop and a 5-second stop setting. Backstops do not guarantee the stricter measured deadline. Every slot independently reads the actual live scope identity and kernel limits before native startup is released.

The parent binds the same process through systemd-run exec using PID, process start time, UID, boot, parent, command and working directory, then verifies its inherited security context against the registration. There is no service MainPID assumption. A separate user/network namespace with only disabled loopback is required before native imports. The fresh profile receives the initial employee process skill and a fixed dummy credential/loopback endpoint. The child calls Computer.start and Computer.close once each; it never calls Computer.run. Constructor metadata probes remain distinct from inference, and zero-inference evidence is a source/network-boundary claim rather than a physical usage meter.

The controller remains alive while the parent observes actual native worker and sandbox identities, native close, process absence and exact socket cleanup. The parent releases that controller only after it is the sole remaining scope member. A pass then requires the recorded controller exit, actual wait status zero, terminal scope/cgroup evidence, complete stage journals, source/dependency closure and measured timing within the original allowance. Scope collection alone does not prove native success.

All nine slots are retained. Any failed start, uncertain boundary or uncertain cleanup halts later batches; already active peers remain in the result. No retries, replacement slots, longer deadlines or selected successful subset are allowed. All nine must pass the strict auditor. A failed result remains engineering evidence and cannot complete the full learning study.

The code received independent review. Review fixes prevent late native phase receipts from extending cleanup and bind recorded security context to the registration. The 108 focused offline tests passed before preparation. Preparation creates no native agent; execution is one-shot under the exact published manifest hash.

Native outcome: pending at preregistration. A passing result only qualifies this bounded startup component. The six-world study still requires complete native actors, employee work, prospective SkillOpt deployment, matched no-learning Hermes baselines and independent scoring/accounting audits.
