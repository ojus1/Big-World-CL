# Native CLI actor-name audit correction

The scale study was launched from published commit `b72fdda` using
`python -m lifespan.evaluation.runner`. Python gives classes defined by that
entry point the module name `__main__`. Consequently the native actor class is
recorded as `__main__.NativeActors`; importing the same module records it as
`lifespan.evaluation.runner.NativeActors`.

The frozen campaign auditor accepts only the imported spelling. Independent
review confirmed this false rejection using the exact runner source without
starting an experiment, then checked the six live child command lines. The
native executor remains `lifespan.evaluation.runtime.execute_case`. This issue
was identified on simulated day 1, before any learning update.

The correction is an additional auditor, `scripts/audit_scale_cli.py`. It must
verify the exact published campaign and frozen source bytes before changing one
actor-name comparison in an isolated copy of the original auditor. Only the
proven CLI spelling is additionally accepted. The executor, cohort, native
receipts, grades, skill versions, learning gate, split boundaries, costs and
cleanup checks retain their original requirements. Running processes and all
34 frozen execution files remain unchanged.

The original audit result is retained alongside the corrected result. Raw
manifests, reports and their recorded actor names are preserved. This is an
audit implementation correction, with no change to the study's tasks, methods,
selection, scientific endpoints or budgets.

An additional private observation receipt was written at
**2026-09-10 01:36:28 UTC**, while all six children were alive. It records their
distinct process identities, exact declared entry point and arguments, matching
supervisor identity and workspace, and configuration/cohort/source hashes.
It is a during-execution observation, **not a preregistration receipt**. Full
arguments and local paths stay private; environment variables were not read.

| Recorded object | Raw SHA-256 |
|---|---|
| Published campaign | `6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa` |
| `CLI_LAUNCH_RECEIPTS.json` | `e9356a3ddc08579697c648593b840db505ff51d8a8191cda86f7b3d99c088ec1` |

The additional auditor and publication helper report their own source hashes
separately from the frozen simulation code. Their tests must reject other actor
names, incorrect executors, mismatched cohorts, altered launcher/source bytes and
unbound launch receipts, while verifying that original artifacts are unchanged.

Independent review passed the exact-source correction and the publication
helper. All 10 correction tests and 19 publication tests passed. The original
auditor remains frozen, so the campaign supervisor is expected to retain its
actor-name rejection in `AUDIT.json`. Run the additional audit after execution:

```bash
python3 scripts/audit_scale_cli.py lifespan/artifacts/scale-v1 --strict
```

Once all six worlds and their cleanup receipts pass, generate a separate local
publication draft:

```bash
python3 scripts/report_scale.py lifespan/artifacts/scale-v1 \
  --preregistration docs/scale-preregistration-v1.json \
  --out lifespan/artifacts/scale-v1-publication
```

This writes allowlisted `SUMMARY.json` and `REPORT.md` files to a new directory;
it does not publish them. It refuses incomplete evidence, changed source or
artifact bytes, unexpected original audit failures, and an existing output
directory. Test fixtures are explicitly offline and are not campaign results.

Review the separate [learning deadline observations](SCALE_DEADLINE_OBSERVATIONS.md)
alongside the campaign audit before publication. That diagnostic records timing
and cost evidence; it does not change this actor-name correction or the frozen
auditor's acceptance rules.

The draft also includes [descriptive world trajectories](SCALE_WORLD_DYNAMICS.md)
with a separately hashed postprocessor. This supplement distinguishes recorded
decisions from actual enterprise, route and policy changes; the preregistered
primary endpoint remains unchanged.
