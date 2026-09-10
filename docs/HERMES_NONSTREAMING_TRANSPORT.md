# Opt-in final-body Hermes Responses transport

This future-run option targets the observed failure where an interrupted SSE
stream lost its usage receipt even though a later native Hermes retry completed
the employee's work. It has not been validated with live provider calls. It does
not recover historical receipts or guarantee reliable execution over a longer
horizon. Existing campaigns and their accounting rules remain unchanged.

Add `"hermes_transport": "nonstreaming"` to both arms' evaluation configuration
to select the adapter. The default is `"streaming"`, which leaves the native
Hermes transport method unchanged. Public default configurations retain their
historical shape; new manifests and reports state the transport explicitly.
Paired comparisons require matching configuration and transport provenance.
The population, learning schedule and compute limits are independent of this
option; it does not reduce the four-enterprise, twelve-employee, twenty-day,
three-pair study design.

The opt-in adapter is installed on each fresh employee agent instance after its
native physical-call meter. It supports exactly Hermes revision
`2c8a2b65aa148ceb178d2251c54a523af12092c9`. Before changing the instance hook, it
checks the clean tracked Python source, ten relevant source-file hashes and the
loaded native module/instance identities. It never patches installed Hermes
files, global classes or another employee's agent.

Hermes still converts messages and tool definitions, performs request preflight,
normalizes responses and executes the native conversation/tool loop. The adapter
replaces only that instance's `_run_codex_stream` dispatch with a final-body
Responses request through the existing meter and native Relay seam. The complete
response object reaches Hermes's native parser unchanged, including its status,
tool-call IDs, reasoning items and usage. Failed, cancelled or incomplete output
is not promoted to successful work by the adapter. A successful HTTP return is
not evidence of a successful artifact or valid accounting.

Every final-body request has `stream=False` and `store=False`. SDK retries remain
zero; a later Hermes retry is another metered physical attempt. The adapter does
not introduce a streaming fallback, extra model calls or a receipt query. A Relay
interception that bypasses the physical call or replaces its returned object is
rejected, while any incurred usage remains recorded. Native output/call/token
limits still apply, and request overrides cannot shadow storage, streaming or
the output cap through `extra_body`.

For final-body responses, a physical operation's existing `status="completed"`
means the transport callback returned. The separate `provider_response_status`
retains the provider's allowlisted completed/incomplete/failed/cancelled/queued/
in-progress status before native normalization. It is `null` when missing or
unrecognized, and never contains provider error text. This is diagnostic
evidence; receipt validity, costs, native retry decisions and task eligibility
keep their existing rules.

Cancellation and the native outer watchdogs remain active. In particular, the
existing no-event timeout still applies while waiting for a final body. The
adapter does not fabricate a first-byte event or extend that deadline. If
cancellation happens after a receipt arrives, its measured usage is retained;
if no valid receipt arrives, the reservation stays unknown. Unknown usage and
physical cap violations remain ineligible. A final JSON body can still be lost,
malformed, delayed or rejected, and some backends may support only streaming.
The existing streaming parser also reconstructs output items when a provider's
terminal `output` field is incomplete; the final-body route cannot assume that
same recovery is available.

Online work and every SkillOpt target replay receive the same configured mode.
Historical calibration, the bounded transfer-learning epoch and its future
transfer probes inherit the source experiment's mode and record it explicitly.
There is no silent transport override for a historical source. Comparing a new
transport requires a new, clearly registered source experiment rather than
combining old and new arms.

Manifests and reports record `hermes_transport` and
`hermes_transport_provenance`; native results record `evaluation_transport`, and
each session binds that descriptor. Every physical meter operation records the
actual `request_stream` argument. Independent audits reconcile these fields,
reject mixed online/replay transport modes and require the descriptor for the
new worker source. The manifest and audit bind the exact helper, worker, runtime and
runner source hashes. Removing session metadata cannot hide remaining native
or physical transport markers. Older evidence without these fields retains its historical
interpretation. No provider credentials or response bodies enter the transport
descriptor.

Offline validation includes unconditional standard-library dispatch, budget,
cancellation, propagation and audit-tampering tests. An optional subprocess test
uses the actual installed pinned Hermes converter, preflight, stream assembler,
normalizer and instance hook with fake final responses. It covers text, parallel
tool calls, reasoning continuity, refusal and incomplete/failed/cancelled output.
That subprocess has a temporary home/profile, blocks network connections and
does not construct or run a native work agent. Missing optional native source or
runtime dependencies produce an explicit skip; independent contract tests still
run in CI. These are compatibility fixtures, not model-quality or provider
reliability evidence.

A separately authorized, bounded native capability check is still required
before preregistering a full comparison. Its pass condition should include a
real file/tool round trip, exact usage receipts and explicit transport
provenance under the same limits. It must not require skill adoption or a
favorable benchmark outcome.
