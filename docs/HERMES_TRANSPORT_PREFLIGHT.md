# Native Hermes transport capability preflight

This additive preflight checks whether the pinned Hermes harness can load its
native skill, write an artifact, submit it to the trusted workplace grader,
read the submitted artifact back, and continue responding through each supported
Responses transport. It does not run MiroFish actors, learn a skill, compare
learning algorithms, or establish long-horizon reliability. No native result is
claimed by the implementation or its fabricated offline tests.

The fixed plan has six slots:

| Slots | Workflow | Transport order |
| --- | --- | --- |
| 0–1 | Onboarding | Streaming, nonstreaming |
| 2–3 | Renewal | Nonstreaming, streaming |
| 4–5 | Incident | Streaming, nonstreaming |

Each workflow uses one deterministic, non-study synthetic case and identical
initial business state, public request, seed skill and limits across the two
transports. Fixture seed 930117 and its next two integers are fixed in source.
Every slot restores its own state and calls the unchanged `execute_case` once
in a fresh directory. Each has a fresh native Hermes profile and bubblewrap
filesystem. No prior study tasks, future probes, actor state, personal profile,
or optimizer input is used.

## Limits and outcomes

Each slot permits at most 16 physical provider requests, 4,096 output tokens per
request, 250,000 charged or reserved tokens, and 420 seconds of outer execution.
The separate cleanup allowance is 30 seconds. The whole invocation permits
2,700 seconds, 96 requests and 1,500,000 charged or reserved tokens. A full next
slot is reserved before dispatch. Cleanup cannot extend the 420-second
execution limit; cleanup following an interrupted execution is still attempted
within its own bound. Six worst-case slots plus orchestration overhead are not
guaranteed to fit the total deadline.

The existing native streaming default and opt-in final-body adapter retain
their physical meter, zero SDK retries, native behavior and source guards.
Hermes' own bounded retry behavior remains observable in physical request rows.
The wrapper never repeats a slot after uncertainty and refuses a second execute
invocation against an existing execution lock. It never clips an observed
physical overrun or converts missing usage into measured usage.

SIGTERM requests a scoped cooperative stop in the outer process. An active slot
finishes bounded owned cleanup and persists an `interrupted` receipt and state;
known returned costs remain recorded. A stop before dispatch preserves the
completed prefix. The previous signal handler is restored on exit. Repeated
SIGTERM cannot skip cleanup, while SIGKILL remains an uncatchable interruption
whose in-flight reservation must remain unknown.

Complete, bounded rejected submissions are valid component observations. The
capability check requires a verified `skill_view`, a real submitted artifact,
its matching `work.commit` tool result, a subsequent native file-read tool and
matching result, and a final assistant response. A perfect semantic score or
accepted business commit is unnecessary. Those outcomes are independently
reconstructed and reported separately. Text alone, no submission, cap summaries,
missing readback, or a fabricated executor cannot pass capability.
Readback matches the submitted JSON content, or its raw SHA-256 when the native
terminal uses `sha256sum`; line-number formatting is removed from `read_file`
results before comparison.

Physical request mode is bound in the native meter and independently audited.
The unchanged runtime does not record a per-request hash connecting a specific
provider response to each conversation message. The post-tool continuation
claim therefore uses the pinned native harness and trajectory sequence; it is
not a new wire-level response attestation or a receipt-recovery mechanism.

A completed invocation can have `capability_pass: false`. Infrastructure,
unknown accounting, physical cap, deadline or cleanup failure halts further
dispatches. Unattempted fixed slots remain visible; they are not replaced or
removed from the plan. Known receipt costs survive a failed grade, later
exception or unsuccessful cleanup. Missing or unreconciled receipts retain a
full slot reservation and any observed numeric fields separately, without a
claim that those observations are verified usage.

## Preparation, registration and execution

Use a reviewed, committed checkout with the pinned Hermes installation and
bubblewrap available. Preparation verifies read-only dependency metadata and
writes a mode-0700 output directory; it does not load credentials or call a
provider. Do not prepare a registered native artifact while execution source is
still being integrated.

```bash
python3 -m scripts.hermes_transport_preflight prepare \
  --out lifespan/artifacts/hermes-transport-preflight-v1 \
  --model MODEL --base-url https://SERVICE/v1
sha256sum lifespan/artifacts/hermes-transport-preflight-v1/manifest.json
```

Review and separately record that manifest hash before execution. The manifest
binds all six slots and raw case hashes, initial skill, exact source inventory,
repository commit, native transport descriptors, model/service metadata, pinned
Hermes source, Python/SDK versions and bubblewrap binary. A native execution
requires every declared source byte to exist at the recorded commit. A
credential-bearing URL is refused.

The execution process reads `BIGWORLD_PREFLIGHT_API_KEY` from its environment,
or accepts a credentials dictionary through the Python API. Credentials are
passed to the child in memory, never written by this wrapper to its manifest,
arguments or receipts. The native worker's existing credential handling is
unchanged.

```bash
python3 -m scripts.hermes_transport_preflight execute \
  --out lifespan/artifacts/hermes-transport-preflight-v1 \
  --manifest-sha256 REGISTERED_SHA256
python3 -m scripts.audit_hermes_preflight \
  lifespan/artifacts/hermes-transport-preflight-v1 --strict \
  --manifest-sha256 REGISTERED_SHA256
```

The API is `prepare(out, *, target_model, model_base_url)` followed by
`execute(out, *, creds=None, executor=execute_case,
expected_manifest_sha256=registered_hash)`. Injected executors are explicitly
marked fixtures and can never establish native capability. There is no resume
or uncertain-retry API.

## Evidence and cleanup

`manifest.json`, `EXECUTION.json`, `state.json` and `REPORT.json` contain the
plan, dispatch binding, progress and aggregate outcome. Private case capsules,
skill bytes, raw native sessions, process logs, immutable artifact objects,
per-slot receipts and supervision records remain under `private/`. Public
report fields contain counts, booleans, scores and provenance hashes rather
than provider bodies or task answers. The raw directory is not a public dataset
export.

`scripts/hermes_preflight_process.py` supervises the unchanged executor in an
isolated child session. It records process ancestry and stable PID/start-time/
UID/boot identity without reading process arguments or environments. Before
signaling any descendant, it checks that identity again. Cleanup records which
owned processes are absent, replaced, or nonrunning zombies, plus any scoped
TERM/KILL signals. A zombie observation does not claim PID absence.

The supervisor binds the native worker and sandbox to their `instance.json`,
observes the owned temporary RPC alias, and records the final alias and actual
trial control-socket states separately. It can remove only that exact owned
socket inode and alias after the observed processes are nonrunning. Unknown
identity, missing ownership evidence, a substituted path or a live descendant
cannot yield confirmed cleanup. Polling and the pinned native parent-death
behavior provide process-lifecycle evidence; this is not a general host-wide
process containment proof.

The independent auditor reconstructs physical usage, native mode, seeded skill,
artifact bytes and trusted grade, the post-submission tool sequence, process
ownership and cleanup, fixed slot inventory, and aggregate report. Historical
scale-v1 launchers and their scientific acceptance rules remain unchanged.

Offline checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_hermes_transport_preflight tests.test_hermes_preflight_audit -q
```

These tests use fabricated receipts and local process/socket fixtures. They
prove orchestration and rejection logic, not native model quality or provider
transport capability. A later separately registered native run is required.
