# Explicit Responses provider registration

This branch retains the nonstreaming Responses transport and adds the optional
`responses-no-thinking-v1` provider profile. The canonical descriptor binds the
model and base URL, `api_mode: responses`, `stream: false`, `store: false`, and
`chat_template_kwargs.enable_thinking: false`. It contains no credential. A
selected profile appears in every paired world config and the campaign's
`provider_contract`; the default legacy config omits both fields.

Preparation accepts `--provider-profile responses-no-thinking-v1` together with
an explicitly matching `launch_policy.provider_profile`, model and canonical
base URL. The policy alone may supply the profile to the Python preparation API.
Preparation does not dispatch model requests. Native execution remains a separate
one-shot operation after reviewed evidence and source commitments are registered.

The six fresh worlds, three fixed seed pairs, 20 action days plus two settlement
days, fixed primary denominator, update days, T2/V2/K2 selection, edit limit,
physical call/token caps, pair barriers and resource/time ceilings are unchanged.
Both arms and their employee replays, the reflector, and contracted actor calls
must use the registered provider policy. A provider migration does not make
earlier worlds eligible for the new comparison.

An explicit profile requires five independently reviewed prerequisites, in order:

1. Fresh actor capability: the four role fixtures, exact current installation,
   native claim/receipt/database joins, known contracted usage and recorded cleanup.
2. Fresh employee capability: three workflows in nonstreaming mode, native
   tool/file/submission/readback evidence, complete physical usage and cleanup.
3. The fixed historical horizon snapshot, used as operational planning context.
4. Fresh current-model startup qualification: all nine slots, the original
   150-second startup and 30-second cleanup bounds, owned scope and disabled
   network namespace, with no work request.
5. Fresh optimizer capability: one production reflector request on a synthetic
   TRAIN fixture and the pinned upstream parser. A valid empty edit list is
   permitted; neither adoption nor improvement is required.

For actor, employee and optimizer prerequisites, the review JSON binds
`manifest_sha256`, `artifact_sha256`, and
`decision: approved_for_prospective_evaluation`. The artifact is `SUMMARY.json`
for actors and `REPORT.json` for employee/optimizer components. The policy pins
the raw artifact and review hashes. Strict component auditors are rerun, all
campaign execution sources must occur unchanged in the component manifest, and
every additional component source must be registered. Source and reviewed raw
reference bytes are checked again after auditing. The registration also freezes
all four tracked MiroFish overlays, the patch and installation checker, including
the JSON descriptor that an installed Python-only diff cannot bind.

The private prerequisite path map uses `actor`, `employee`, `horizon`, `startup`
and `optimizer`. Each supplies `directory` and `review_file`; `actor` additionally
supplies `source_root`, which must resolve to the current checkout. Absolute
paths stay private. The legacy path retains its original historical source
compatibility gate. That gate cannot substitute for any fresh profile component.

The startup qualifier's preparation accepts `--model` and `--provider-profile`
together. Those two fields are the only configurable startup inputs. It derives
the full descriptor using the fixed loopback dummy endpoint and fixed invalid
credential, rather than the production endpoint. The same descriptor must appear
in the native READY and instance records. Existing scope, environment, source,
dependency, deadline and cleanup checks still apply. Startup completion proves
the inspected initialization path, not provider inference or long-run reliability.

These gates establish bounded component compatibility. They do not forecast
Qwen throughput, study completion, available funding, or learning gain. The
historical horizon is not a timing measurement of this model. Contracted actor
usage remains distinct from unmetered bootstrap/social usage, and unknown
physical usage cannot be converted to zero or accepted as a completed component.
