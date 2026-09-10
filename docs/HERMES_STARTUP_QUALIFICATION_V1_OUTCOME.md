# Native Hermes startup qualification v1 outcome

The registered qualification did not pass. The first attempted slot failed during user-namespace setup, before a worker `HELLO` or native Hermes child was observed. The supervisor retained the other eight slots as `skipped_after_stop`; none has an audited slot receipt. The strict independent audit therefore reports `incomplete`, `ok=false`, and `qualification_passed=false`. Its empty error list does not imply success.

| Slots | Supervisor declaration | Audited evidence |
| --- | --- | --- |
| start-00 | infrastructure_failed | One failed receipt; boundary and cleanup unconfirmed |
| start-01 through start-08 | skipped_after_stop | Eight missing slot receipts |

The controller's single-line diagnostic reports permission denied when `unshare` writes its user-ID map. Two targeted kernel records for the parent-observed process, on the same boot and within the attempt, show a transition from `unconfined` to `unprivileged_userns`, followed by an AppArmor denial of `sys_admin`. The direct tool shell had the distinct `chatgpt (unconfined)` label. These records explain the failure in this service context; they do not supply the missing audited unit/native identity or qualify another launch method. No host policy was changed for this observation.

The systemd-run client and unit both returned status 1. Cleanup began about 0.1085 seconds after the attempt started and its recorded end followed about 30.0001 seconds later. The recorded cleanup end exceeds its declared deadline by about 0.000125 seconds; no successful timing or cleanup qualification is claimed. Although the final unit observation reports MainPID zero, its state is failed, the unit binding is absent, remaining cgroup membership is unknown, and socket cleanup is unconfirmed. Native startup latency was not measured.

The receipt declares zero employee work requests. Native inference count, tokens, and cost remain unknown because no successful no-inference boundary or physical usage meter was established. Missing native evidence is not converted into zero usage.

The [allowlisted outcome](hermes-startup-qualification-v1-outcome.json) binds all 13 original run files, both targeted kernel/context records, the original [preregistration](HERMES_STARTUP_QUALIFICATION_V1.md), and the recomputed strict audit. All 34 registered execution source files still match commit `8763faad91ed18e77e385e017d7039ccd6c1b29a`; execution and current dependency bindings, current boot, and resource receipts match the manifest. Original artifacts and registered execution code were preserved.

This is an engineering failure observation, with no Hermes latency, provider, learning, or full-world efficacy result. The nine-slot registration has not been retried or replaced. Any different startup context requires a separately reviewed qualification.
