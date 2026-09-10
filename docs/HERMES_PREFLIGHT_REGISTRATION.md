# Prospective native Hermes capability registration

The exact manifest is [hermes-preflight-registration-v1.json](hermes-preflight-registration-v1.json).
Its raw SHA-256 is
`ea5e5e66be002a3f497d24c7bc2b60a85312e9174e84e323f0c5b154633da0f4`.

This fixes six synthetic component slots across onboarding, renewal and incident,
with streaming and nonstreaming execution for each workflow. The source commit
is `cf25e505fe11a0b3f128229f7dea1599f53d4d2d`; all 40 declared source bytes
were independently checked against both the checkout and that commit before
execution. The independent auditor returned `valid_prepared`, with no execution
artifacts or attempted slots. These are preparation results, not native capability
results.

Each slot has 16 physical calls, 4,096 output tokens per call, 250,000 charged or
reserved tokens and 420 seconds, followed by a separate 30-second cleanup bound.
The invocation has 2,700 seconds, 96 calls and 1,500,000 charged or reserved tokens.
Full next-slot reservations can stop dispatch before all six slots fit the wall
budget; such a run cannot claim a completed capability pass.

Task semantics and accepted commits are observed separately from transport
capability. Unknown usage or unsafe/unconfirmed cleanup halts further dispatch.
All six slots remain in the inventory. There is no uncertain-action replay,
replacement slot, learning update or business-world comparison in this preflight.
The broader research objective remains a complete fresh six-world comparison.

See [the preflight protocol](HERMES_TRANSPORT_PREFLIGHT.md) for native skill,
submitted artifact, post-submission readback, receipt and process evidence.
Raw traces remain private; this manifest contains hashes and metadata only.
