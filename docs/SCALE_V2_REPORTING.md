# Completed scale-v2 report

`scripts/report_scale_v2.py` creates a local publication draft after the full
campaign passes its strict native audit. It makes no model calls, starts no
agent sessions or services and publishes nothing. The reporter is an additive postprocessor
introduced during execution; its hashes are recorded separately from the
frozen execution and registration files.

From the registered checkout, after all six worlds have stopped and cleanup is
recorded:

```bash
PYTHONDONTWRITEBYTECODE=1 MiroFish/backend/.venv/bin/python -m scripts.report_scale_v2 \
  lifespan/artifacts/scale-v2 \
  --out lifespan/artifacts/scale-v2-publication-draft \
  --preregistration docs/scale-preregistration-v2.json \
  --campaign-sha256 4315bd53cc14870a291accbe5c71d7556a458ac0a9260d181dc30735c8f4b801
```

The output directory must be new and separate from the campaign directory.
The supplied registration must match the campaign's exact bytes and separately
reviewed raw hash. There is no incomplete-study bypass: all six fresh worlds,
all three pairs, measured employee/optimizer and contracted-interview costs,
native evidence and cleanup must pass. A refusal does not create a zero-valued
quality result. Use the [non-strict auditor](SCALE_V2_AUDIT.md) for an ongoing
engineering observation instead.

The draft contains `SUMMARY.json` and `REPORT.md`. Its primary result is the
equal-world mean paired difference in fixed initial/benchmark commitment
fulfillment, with 240 commitments per world. It reports all-demand fulfillment
separately even though the generic comparison's headline names all demand.
The JSON retains every planned employee and learning boundary, deployed-version
exposure, explicit skill-loading counts and all optimizer outcomes. Numerical
gate traces retain trial and final decisions, scores and per-task outcome
counts as historical selection evidence; unavailable scores stay unknown.
Online, replay, optimizer and contracted-interview costs remain separate; unmetered
environment inference and all-in currency cost remain unknown.

The reporter checks input and source provenance before writing and repeats the
strict audit to reject evidence changes during reporting. Raw file SHA-256 and
canonical-JSON summary hashes are labeled separately. Exported fields are
allowlisted aggregates, synthetic identities and provenance, excluding prompts,
task contents, persona text, answers, skill text and provider diagnostics.

Review the draft and run the repository's credential checks before copying
allowlisted results into tracked documentation. Do not attach the private run
directories. The reporter does not publish to GitHub or Hugging Face.

See [interpretation](SCALE_V2_INTERPRETATION.md) for the treatment's scope,
historical gate limitations, prospective exposure, dependence between
observations and permissible conclusions. Zero adoptions or a negative paired
difference remain valid completed research outcomes.
