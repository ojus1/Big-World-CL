# Full six-world follow-up registration

`scripts/prepare_scale_v2.py` prepares and revalidates the follow-up design in a
new private artifact directory. It makes no model calls and does not execute a
campaign. The original scale-v1 launcher and acceptance contract remain intact.

The registration retains three development seeds (211, 307, 401), both arms,
four enterprises, twelve employees, eight consumers and one agency per world,
twenty workdays and two settlement days. Paired worlds receive byte-identical
Persona cohorts; the three seed cohorts must be disjoint. All six worlds are
fresh. No interrupted old arm can be substituted into the new comparison.

The pinned SkillOpt method remains T2/V2/K2 with four candidate edits, updates
on days 3/7/11/17 when eligible, strict improvement and no validation-task
regression. All online and learning execution uses the same nonstreaming Hermes
option. All actors use the reviewed 4096-output-token, 120-second JSON contract.
The service must be a canonical loopback origin on a port other than 5001.

## Explicit launch policy

Preparation requires a JSON policy with exactly these fields:

| Field | Requirement |
| --- | --- |
| `per_world_wall_seconds` | Explicit positive integer; no default duration or forecast. |
| `workers` | Explicit integer from 1 to 6, fixed for this registration. |
| `mirofish_service_url` | Canonical separate local service origin. |
| `wall_budget_rationale` | Written assessment of duration evidence and remaining uncertainty. |
| `evidence` | Ordered actor capability, employee capability, and horizon feasibility references. |

Each evidence reference has `kind`, `artifact_sha256`, and `review_sha256`.
Kinds, in order, are `actor_native_capability`, `employee_native_capability`,
and `horizon_feasibility`. These are hash references to independently reviewed
artifacts. This registration validator checks their inventory and format;
**it does not re-audit those artifacts or certify that launch prerequisites
passed**. The execution supervisor must verify actual prerequisite evidence,
installed service identity and cleanup ownership before dispatch. A policy is
not an executable authorization by itself.

After those reviews, prepare with explicit model/provider metadata and the
reviewed policy; revalidate against the same installed source and dependencies.
Neither command reads an API key. Preparation requires installed dependency
provenance, a new output beneath `lifespan/artifacts`, and writes no raw evidence
into the public registration.

```bash
python scripts/prepare_scale_v2.py prepare \
  --out lifespan/artifacts/scale-v2 \
  --policy /path/to/reviewed-policy.json \
  --target-model MODEL \
  --model-base-url PROVIDER_URL
python scripts/prepare_scale_v2.py validate --out lifespan/artifacts/scale-v2 \
  --campaign-sha256 SEPARATELY_REVIEWED_RAW_MANIFEST_SHA256
```

The manifest binds all run configurations and cohort bytes, execution sources,
dependency revisions, registration tooling, selected transports, limits and
evidence references. Revalidation rejects changed methods, reduced horizons,
omitted or extra worlds, cohort substitutions, source changes, symlinks and
prior native output or execution intent. Publish the scanned manifest and use
its raw SHA-256 at the future one-shot execution boundary.

Revalidation requires the separately reviewed raw manifest hash; it never
substitutes the hash of a newly rewritten manifest. Structural validity alone
cannot establish that a coherent policy or cohort rewrite was the reviewed
registration. Preparation uses the pinned importer, but registration validation
checks cohort identities and bytes rather than independently re-auditing the
Persona source dataset. Dataset authenticity remains part of the native
campaign prerequisite audit.

Employee and optimizer call/token caps are unchanged. Contracted actor
interviews now have physical request receipts and caps; bootstrap/social calls
and whole-environment token/currency totals remain unmetered. A successful
registration is not a cost, task-quality, adoption or learning-gain result.
Completion still requires all three complete valid pairs, with zero gain or
zero accepted skills permitted as research outcomes.
