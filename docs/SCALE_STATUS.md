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
records remain unknown. Checkpoint reads are capped at 128 MiB; other JSON reads
remain capped at 32 MiB, and registration/source reads at 4 MiB. Historical
scale-v1 checkpoints reached 50.4 MiB because they retain full session and
learning evidence, so the original 32 MiB checkpoint allowance was insufficient.
The higher limit provides bounded headroom, not a forecast or guaranteed maximum;
an oversized checkpoint still yields unknown progress. Missing first checkpoints
produce unknown counts, never fabricated zeroes or failures.

`unlaunched` means no launch evidence was found, not a promise of future dispatch.
The fixed protocol can leave later slots unlaunched after an earlier failure.

When the world is verified currently running and a SkillOpt learning operation
is recorded as in flight, an extra line shows
returned/dispatched target replay records, optimizer dispatch records, and
allowlisted phase names from that epoch's `progress.json`. The key, day,
employee membership, registered update day and SkillOpt configuration must agree before its derived
path is read. Missing, malformed, mismatched or changing receipts leave these
counts unknown. A known initial empty receipt can legitimately show zeroes.
Optimizer dispatch records count callback attempts, not physical model calls;
returned replays are not necessarily scored or successful. Pending phase means
an unreturned dispatch record, not independently verified current inference.
A stale in-flight receipt after exit or reboot leaves learning counts unknown.
No prompts, task or
employee identifiers, scores, costs, adoption predictions or ETA are added.

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
