# Running the fresh six-world comparison

The v3 launcher runs three fixed seed pairs through native MiroFish/OASIS and
Hermes/bubblewrap. Each pair compares pinned SkillOpt-Sleep with no-learning
Hermes. See the [resource design](SCALE_V3_RESOURCE_DESIGN.md) for the scientific
protocol, population, compute limits, failure handling and reviewed prerequisites.

Prepare a new private directory with an explicit policy and model metadata:

```bash
MiroFish/backend/.venv/bin/python -m scripts.prepare_scale_v3 prepare \
  --out lifespan/artifacts/scale-v3 \
  --policy /absolute/private/policy.json \
  --target-model MODEL --model-base-url PROVIDER_URL
```

The policy fixes the service origin, three pair waves, two concurrent worlds,
24-hour world ceilings, shared resource limits and five reviewed evidence
references. Preparation imports 75 distinct Persona records, copies identical
cohort bytes into each pair, and pins execution and reporting sources. It makes
no model calls. Review and publish the credential-scanned `campaign.json` before
dispatch; retain its raw SHA-256 independently of the private directory.

Revalidate and execute once with that reviewed hash:

```bash
MiroFish/backend/.venv/bin/python -m scripts.prepare_scale_v3 validate \
  --out lifespan/artifacts/scale-v3 --campaign-sha256 REVIEWED_SHA256
MiroFish/backend/.venv/bin/python -u -m scripts.run_scale_v3 \
  --out lifespan/artifacts/scale-v3 --campaign-sha256 REVIEWED_SHA256 \
  --prerequisite-paths /absolute/private/prerequisite-paths.json
```

Use the prepared installation's Python path: resolving a virtualenv interpreter
symlink can change its import environment. The MiroFish installation needs its
own graph/uploads state, private configuration and registered loopback port.
Provider credentials stay in private configuration; they do not belong in
commands, policies, registration files, scope properties or published receipts.

The outer process launches and observes one owned systemd user scope. The inner
controller waits for the identity/resource gate before it starts MiroFish or
worlds. Both worlds in a pair must return normally and finish cleanup before the
next pair starts. A failed world stops further dispatch; its slot and any
unlaunched slots remain in the study inventory. There is no same-directory
restart, uncertain-state resume or replacement-world option.

Read-only audit and reporting commands are separate from execution:

```bash
MiroFish/backend/.venv/bin/python -m scripts.audit_scale_v3 \
  lifespan/artifacts/scale-v3 --campaign-sha256 REVIEWED_SHA256 --strict
MiroFish/backend/.venv/bin/python -m scripts.report_scale_v3 \
  lifespan/artifacts/scale-v3 --out lifespan/artifacts/scale-v3-public-draft \
  --preregistration docs/scale-preregistration-v3.json \
  --campaign-sha256 REVIEWED_SHA256
```

Reporting requires all six completed audited worlds and three complete pairs,
normal native controller/wait exits, cleanup closure, unchanged raw evidence and
the published registration bytes. It retains all 72 employee-world instances,
288 scheduled learning boundaries and every recorded epoch, including rejected
and budget-stopped updates. Fixed-demand fulfillment is primary; native-demand
fulfillment, synthetic utility, adoption and actual skill loading are secondary.
No positive effect or minimum adoption count is required.

The reporter creates an allowlisted local draft. Review and scan that draft
before publishing it. Startup qualification and incomplete prefixes have their
own evidence reports; neither can be substituted for a completed comparison.
