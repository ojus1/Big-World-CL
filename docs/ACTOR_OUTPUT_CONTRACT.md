# Opt-in native actor output contract

`actor-json-v1` is a future experiment option for the pinned MiroFish Reddit/OASIS pipeline and its Responses bridge. It has offline fixture coverage. It has **not** been installed into the active stack or validated with a native model call. Existing campaign artifacts and their execution protocol remain unchanged. A new study registration and a bounded native preflight are required before using this option for research evidence.

The option requests strict JSON from the existing persona-backed native actor. It preserves the native interview, database, employee delegation, institutional decision and business validation paths. JSON shape does not grant access to evidence, authorize a policy, establish affordability, or accept delegated work. Existing validators still decide those matters. The existing `native_decision` loop permits the first interview plus at most one repair; infrastructure, usage or receipt failures stop the action.

## Activation and installation

For a **new** installation, use the pinned checkout, tracked patch and complete `local-overrides/backend` copy described in [SETUP.md](SETUP.md). This version adds `actor_output_contract.py`, `actor_contract_transport.json`, the scoped Responses change, and API → runner → IPC → native handler plumbing. Do not apply it to an active campaign stack. The transport manifest pins the four patched native Python files; changing a transport file requires deliberately regenerating that manifest and registering a new source contract.

Add the following field to a new evaluation JSON config supplied to `python -m lifespan.evaluation.runner --config CONFIG.json --out NEW_OUTPUT`:

```json
{
  "actor_output_contract": {
    "version": "actor-json-v1",
    "max_output_tokens": 4096,
    "timeout_seconds": 120
  }
}
```

This is a field excerpt; retain the other planned experiment settings. The default is disabled and omitted from the historical public config. The same options can be passed to `MiroFishRuntime(..., actor_output_contract=...)`. The server derives each role from the registered simulation participant, and the client derives it from the same cohort roster. Clients cannot submit schemas, receipt paths or role identities outside that registration.

The web-server capability handshake precedes bootstrap generation. The server and worker check installed transport hashes; the worker advertises its exact support. The contracted handler also checks the actual agent backend before `env.step`. A missing, mixed, unsupported or mismatched stack fails closed. Support currently requires the patched Responses model in the asynchronous Reddit interview path. Ordinary social actions, uncontracted interviews and tools keep their existing settings.

## Wire and concurrency contract

The server owns four strict schemas: employee, enterprise, government and consumer. Every object declares every property required and forbids extra properties. Nullable proposal/firm fields remain explicit. The schemas bound strings, lists, prices and policy duration and reject duplicate properties, nonfinite numbers and booleans used as numbers locally. The Responses request uses `text.format` with a named JSON schema and `strict: true`; root objects avoid unsupported conditional/composition keywords. These choices follow the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs). Hosted model support still requires native preflight; fixture validation does not prove provider enforcement.

A `ContextVar` is set inside the native interview task. OASIS's awaited task handoff inherits it. The shared bridge creates a request with the role schema and without tools, while concurrent ordinary calls retain their original tool settings. Neither the model's shared config nor another actor's scope is changed. The opt-in SDK request disables retries and permits one physical dispatch. Failure conversion and a durable dispatch guard prevent hidden retry layers from making a second call.

The client hashes its logical cache key. The server validates that fixed hexadecimal identity and exclusively claims it within the simulation, independently of the actor, prompt or contract. Reusing the key with different content is still rejected. Distinct keys may legitimately submit identical prompts. A second hash binds the simulation, actor, logical key, original prompt, optimized prompt, descriptor, schema and support version. Receipts additionally hash the actual provider input/request and returned output. Only a fresh, unique database trace after the action boundary with the same actor and stored prompt can become its native result. There is no delimiter repair, response stripping or stale-row fallback.

## Completion, costs and failure semantics

`status: completed` on a native receipt means the transport returned and its database trace was bound. It does **not** mean shape-valid or business-valid. The client requires one dispatched request, provider completion, output/native-result hashes, complete consistent token accounting, the output cap and the deadline before returning text to the decision loop. A recorded shape failure is checked inside that loop and can use its one repair. Unknown accounting, stale/mismatched evidence, unsupported backends or limit failures stop; they do not request another model response.

`max_output_tokens` is an **output-only** provider limit, including reported reasoning output. It is not an input limit, total-token reservation, or currency estimate. Each independently typed nonnegative token dimension is retained even when another is missing or totals disagree. Complete usage requires input + output = total. A received malformed output body retains available usage. A dispatched SDK timeout retains one physical dispatch, unknown usage and the full output reservation; it never becomes zero cost. Currency remains unknown. Claims and receipts are private, server-owned files written before dispatch and updated durably.

The client persists logical intent before HTTP dispatch. An HTTP timeout may occur before the native task stops; its durable native receipt can still finish later. The client neither cancels that evidence nor retries the logical key. It refuses to start a contracted request unless its complete declared time window plus two seconds fits the remaining runner budget. `elapsed_seconds` covers native setup, the provider await and database/receipt work; it is not physical inference duration. The provider timeout is bounded within the native task; outer queue/network time remains separately observable. Full lossless native process resume is outside this change. Do not delete intent or claim records to resume uncertain work.

The run manifest and report carry `actor_output_contract_provenance`: descriptor, schema/support/helper/bridge/transport hashes and tracked patch hash. Existing source-hash path conventions remain intact; the client helper is already included in lifespan source hashing. Installed dependency provenance remains recorded separately. The opt-in artifact audit verifies the client/runner/auditor source hashes, this metadata and each completed cached receipt against its logical ledger, actor roster and totals. This is local consistency checking, not cryptographic provider authentication. The frozen scale-v1 launcher/auditor does not authorize this new option or source revision.

Contract accounting covers these interviews only. Graph construction, bootstrap/social actions and other uncontracted model use remain outside it; a report must not present these interview totals as complete environment-actor cost. Whole-run actor input/output budgets and new campaign planning are separate work.

## Offline verification and limits

Run in a compatible installed MiroFish Python environment, pointing `BIGWORLD_TEST_MIROFISH_SOURCE` at a read-only pinned upstream checkout if this checkout lacks one:

```bash
PYTHONDONTWRITEBYTECODE=1 MiroFish/backend/.venv/bin/python -m pytest \
  tests/test_actor_output_contract.py tests/test_evaluation_audit.py -q
```

The fixtures explicitly import this checkout's overrides. The transport fixture applies the tracked patch to pinned upstream files in a temporary directory and executes the actual Flask/API, SimulationRunner, file IPC and native-handler methods. It substitutes deterministic native actors and a mock HTTP provider, then checks the actual bridge and SQLite roundtrip, including escapes and final delimiters. Tests also cover concurrent mixed contracts, ordinary tools, old/mixed installs, backend rejection, schema/business separation, uncertain timeouts, partial usage, malformed bodies, caps, logical-key reuse, stale traces, cached receipt tampering and audit provenance. These tests make no model calls and are not native benchmark evidence.


The dedicated `actor-contract` job in `.github/workflows/evaluation.yml` installs
`tests/requirements-actor-contract.txt`, checks out MiroFish at the exact pinned
revision for read-only `git show`, and runs every actor-contract fixture without
credentials or native startup. An explicitly configured missing source fails
rather than skipping transport coverage. Core SkillOpt CI separately fetches
its reviewed pinned checkout and exercises real upstream consolidation code with
mocked model callbacks. A local worktree should provide that checkout before
claiming the full suite; its absence otherwise skips the upstream-dependent
learning tests. The optional `test_actual_cohort_is_distinct_synthetic_and_has_provenance`
requires an explicitly imported private Persona cohort and is intentionally
skipped in credential-free CI. Bubblewrap tests require the installed executable
and permitted namespaces; CI installs it on Ubuntu 22.04.

Two historical CLI-correction AST fixtures deliberately skip outside their exact
frozen auditor revision. Their unsupported-source rejection still runs; this
future change does not rewrite that historical adapter or make it accept new
revisions. In this isolated worktree, the initial 47 lifespan skips were 46
missing-upstream SkillOpt cases plus the one optional Persona-cohort case.
Providing the reviewed SkillOpt checkout exercises all 46; only the cohort case
remains skipped.
