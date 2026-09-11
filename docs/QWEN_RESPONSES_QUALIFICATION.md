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

The [initial native observation](qwen-initial-qualification.json) is bound to
commit `7a927581df0ed3fb76334dc96aa1bc6454a8257a`. The optimizer qualification
passed with one request, 699 tokens, 4.232 seconds and one parsed edit; all nine
startup slots also passed. Both passed independent raw-evidence review.

The actor preflight exposed a separate bootstrap client that bypassed the
profile and requested ontology generation without an output cap. It was stopped
after 131.826 seconds, before any contracted actor interview or OASIS environment
started. Its worker and server exited; bootstrap usage remains unknown. The
tunnel answered every health check. The employee preflight was prepared but
not executed. The corrected bootstrap path must be qualified before a new study;
the initial evidence cannot be relabelled as execution of changed source.

The corrected bootstrap helper uses the same explicit Responses policy, at most
8,192 output tokens per request, a 120-second timeout and zero SDK retries.
Provider and usage failures propagate through configuration and persona
generation, including batch workers, without retries or fabricated profiles.
Existing bounded content regeneration is retained. The patch passed 49 new
offline tests and 115 existing regressions, with independent review. Bootstrap
costs remain outside the contracted-interview meter.

## Native conversation compatibility

The next actor qualification, using commit
`032fd6f98f9c5815c604ffcc78601164317996c6`, completed bootstrap and started
the four-persona OASIS environment. Its first contracted interview failed with
HTTP 400. The failed run is preserved; it does not qualify the actor transport.

After the tunnel recovered on September 11, a bounded reconstruction of the
saved native conversation reproduced the server error, `System message must be
at the beginning.` The history contained two leading system messages. Combining
their contents, in order and separated by two newlines, into one system message
made the same request complete successfully: 1,259 input tokens and 56 output
tokens, with zero reasoning tokens. The schema and remaining conversation items
were unchanged. The reconstruction could not restore the original process's
cached Responses items, so this controlled probe is diagnostic evidence, not an
exact replay or a substitute for fresh native qualification.

The explicit no-thinking profile now combines multiple leading string-valued
system messages at the CAMEL-to-Responses boundary. It preserves all their
content, including repeated text, and retains the order of every subsequent
message and tool result. Unsupported fields or structured content in a prefix
requiring combination fail before dispatch. A single leading system message,
later system/developer instructions, and the legacy provider path are unchanged.

The subsequent native run, bound to commit
`f534ee56fea8afd0c1ac1dad234d18af8c620277`, confirmed that the HTTP 400 was
resolved. Both employee interviews completed with schema-valid JSON, but both
returned only `wire witness: ` instead of the full required string. The fixed
witness includes quotation marks, braces, a backslash, an accented character and
a newline. The original and repair calls together reported 2,736 input and 92
output tokens. This run remains a failed qualification, with its native traces,
receipts, source snapshot and cleanup evidence preserved.

Controlled diagnostics then isolated an interaction with string `maxLength`
constraints: the original prompt reproduced the exact decoded fixture without
a generation schema, and also with the same schema minus its `maxLength`
keywords. Each successful probe reported 131 tokens. Extra escaping instructions
with the original schema did not preserve the witness. These observations do
not identify the serving engine's internal cause; the endpoint reports version
`0.1.dev20051+g487ecf187`.

The compatibility rule separates the **generation schema** sent to the explicit
provider from the **acceptance schema** enforced by the application. Generation
omits only string `maxLength` keywords; the complete authoritative role schema,
including every string length limit, still validates returned data before it
can be accepted. Object fields, required keys, array limits, numeric ranges and
enums remain in the generation schema. The projection identifier and both
schema hashes are bound into profile-specific evidence, and the actual request
schema is checked before dispatch. The fixed witness and repair allowance are
unchanged. Changed sources require fresh qualification.

## Employee file readback

The first executed three-workflow Qwen Hermes qualification completed with
35 physical calls, 365,150 tokens and confirmed cleanup for every workflow.
Onboarding and incident passed the capability checks. Renewal remained
unqualified because the checker recognized separate `cat` and `sha256sum`
commands but not their combination. Independent review verified that its
post-submission command returned the exact immutable artifact bytes followed by
the correct checksum and path, then a final assistant response.

The checker now accepts the single literal command
`cat /workspace/deliverables/capability.json && sha256sum /workspace/deliverables/capability.json`.
It checks the complete output against the submitted bytes and checksum using
the pinned native terminal's whitespace transformation, with a typed zero exit
status and an exact success envelope. It does not interpret arbitrary shell
programs or strip unexplained output. Original receipts and the failed verdict
remain unchanged; a new qualification must use the reviewed checker. Business
scores and rejected submissions remain separate from transport capability.

Ordinary profiled MiroFish calls also configure both SDK clients with zero
retries and a 120-second timeout after CAMEL initialization. Constructor
arguments alone were insufficient: the pinned CAMEL base initializer reset the
retry count. Mocked connection-timeout and server-error tests exercise the
actual clients and require one dispatch. Contracted interviews retain their
remaining-deadline override; this does not claim to remove CAMEL's separate
rate-limit handling. The external tunnel watchdog remains active throughout
native work.

No complete Qwen comparison or learning gain is claimed.
For this execution, the user's stop condition is immediate suspension of runs
and further work if the Qwen tunnel becomes unreachable, followed by notification.
Do not switch providers or repeatedly retry an unavailable tunnel.
