# Qwen Responses integration

The supplied vLLM endpoint passed four bounded `/v1/responses` capability
requests on September 10, 2026: a text answer, a strict function call, a stateless
continuation containing the function result, and strict JSON-schema output.
Every request returned HTTP 200 and `status: completed`, with complete input and
output usage. Together they reported 742 tokens and zero reasoning tokens.
The requests used `stream: false`, `store: false`, and
`chat_template_kwargs: {"enable_thinking": false}`. These API probes do not
qualify native Hermes, MiroFish or SkillOpt execution and do not measure learning.

The new explicit `responses-no-thinking-v1` provider profile uses
`Qwen/Qwen3.8-27B-FP8` with the existing Responses transport. There is no automatic
provider fallback. The model and canonical base URL are supplied by private
configuration; neither is inferred from a historical run. Credentials are kept
in ignored files outside release artifacts. Authentication uses the SDK's Bearer
authorization header.

## Configuration and evidence

Set `BIGWORLD_PROVIDER_PROFILE=responses-no-thinking-v1` alongside the private
MiroFish provider configuration (`LLM_MODEL_NAME`, `LLM_BASE_URL`, and
`LLM_API_KEY`). The matching evaluation configuration must set
`provider_profile` to the same value and `hermes_transport` to `nonstreaming`.
Preparation commands accept model/base URL metadata, never a credential argument.

The manifest records a canonical, nonsecret provider contract. The worker,
physical-request meter, optimizer, actor bridge and independent auditors bind
the actual model, client base URL, API family, streaming, storage and thinking
settings to that contract. Numeric zero cannot stand in for a JSON boolean.
Missing usage remains unknown and retains its reservation. Omitting the explicit
profile preserves the historical request and manifest format.

The Responses bridge retains native tool conversion and stateless tool-result
continuations. The optimizer still uses pinned upstream SkillOpt rendering and
parsing, chronological public training experience, separate validation and a
fresh final replay. This provider change does not alter those learning gates.

## Fresh qualification before a scaled run

The profile requires fresh evidence from committed current sources:

| Component | Bounded qualification |
|---|---|
| Actor contract | Four fixed MiroFish roles, at most eight logical interviews, one repair per role, 900 seconds plus 120 seconds for cleanup |
| Employee transport | Three native Hermes workflows, at most 48 physical calls and 750,000 tokens in total, 420 seconds plus 30 seconds cleanup per workflow |
| SkillOpt optimizer | One real reflector request, at most 32,768 tokens and 120 seconds, using a synthetic training fixture and the actual upstream parser |
| Startup | Nine native startup slots, including concurrent starts, with the Qwen model/profile and a fixed dummy endpoint in a network namespace with no provider access |
| Horizon feasibility | A reviewed bound for the unchanged complete six-world campaign |

Each capability gate reconstructs raw artifacts and checks source, dependency,
provider, usage and cleanup evidence. Actor, employee and optimizer reports also
require an independent review tied to their exact manifest and artifact hashes.
A valid empty optimizer edit array can qualify transport and parsing; it is not
an adoption or improvement. Native employee task scores remain measured outcomes,
while execution, skill loading, tool submission and artifact readback must pass.

The scaled design remains six fresh worlds, three paired seeds, four enterprises
and twelve employees per world, twenty action days, and up to 1,440 online work
attempts. All six worlds must complete and pass audit for the primary comparison.
The earlier credit-exhausted registration is preserved and cannot be resumed or
relabelled as a Qwen run.

Current status: API capability probes passed; the fresh native qualifications
and complete Qwen comparison have not yet run. No Qwen learning gain is claimed.
For this execution, the user's stop condition is immediate suspension of runs
and further work if the Qwen tunnel becomes unreachable, followed by notification.
Do not switch providers or repeatedly retry an unavailable tunnel.
