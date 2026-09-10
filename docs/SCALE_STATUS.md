# Read-only campaign progress

Use the exact campaign hash from the published registration:

```bash
python3 -m scripts.scale_status /absolute/path/to/campaign \
  --campaign-sha256 <published-sha256> --format table
```

Omit `--format table` for allowlisted JSON. The command supports the registered
six-slot scale-v3 layout and preserves all six slots, including four unlaunched
worlds while the first pair runs. It reads fixed checkpoint and lifecycle files
and hashes the 69 registered local source files. It does not scan session trees,
start a service, query a provider, signal processes, or write outputs.

Session, update and adoption counts include checkpointed returned records only.
An in-flight operation may not yet appear; replay counts are not online session
counts. Phase and day come from the checkpoint; the separately shown in-flight
kind can be newer. Malformed, concurrently replaced, missing or oversized
records remain unknown. Each JSON read is capped at 32 MiB, and the registration
at 4 MiB. Missing first checkpoints produce unknown counts, never fabricated
zeroes or failures.

`unlaunched` means no launch evidence was found, not a promise of future dispatch.
The fixed protocol can leave later slots unlaunched after an earlier failure.

Running elapsed/remaining seconds require a matching launch-intent chain,
configuration, command, working directory, current boot and PID/start/UID
identity. Remaining seconds refer to the registered wall ceiling, not expected
completion time. Terminal timing stays unavailable after the owned process is
gone. `terminal_recorded` means a supervisor result matches the start/cleanup
receipt hashes; it does not certify successful work, cleanup or study validity.
The runner's reported terminal status is shown separately.

The snapshot is not atomic across worlds. Unknown or stale evidence is not an
instruction to restart anything. A matching registration prints status even
when progress is unknown; an unavailable, changed or unsupported registration
exits with code 2. Use the independent completed-study auditor and reporter for
research results. No scores, raw task text, provider identifiers, private paths,
learning comparison or completion forecast are exported.
