# Auditing all six scale-v2 worlds

`scripts/audit_scale_v2.py` audits the separately registered six-world follow-up.
It does not modify the scale-v1 contract, grader, learning gate, reports, or raw
evidence. Registration validation requires the separately reviewed raw
`campaign.json` SHA-256 and the current source, dependency and registration-tool
hashes. Preparation alone is not native evidence or authorization to dispatch.

```bash
MiroFish/backend/.venv/bin/python -m scripts.audit_scale_v2 \
  lifespan/artifacts/scale-v2 --campaign-sha256 REVIEWED_RAW_SHA256 --strict
```

Use the registered checkout and interpreter. The Python API is
`audit_campaign_v2(directory, *, campaign_sha256, strict=False)`. It reads local
evidence and prerequisite audits; it never starts services, resumes worlds,
signals processes or calls a model. With `strict=True`, any incomplete world or
unconfirmed cleanup makes the command fail. Non-strict mode can describe a
consistent incomplete snapshot. Reading an actively changing directory may
produce a transient consistency error; that is not an employee failure.
An observed execution overrun in any terminal world is a budget invalidity even
when the remaining campaign is incomplete. Known costs remain visible.

All six planned slots remain in the result, including when the registration
itself fails. `completed_runs` and `complete_pairs` describe the independently
validated world reports. The primary comparison appears only after **all six
worlds, all three pairs, launch provenance and cleanup pass**. Two surviving
pairs never substitute for three. Missing or invalid outcomes are not filled
with zero. No positive gain or minimum adoption count is required.

Each world is checked by the unchanged `scripts.audit_scale.run_check`, including
native sessions, immutable submissions and grades, chronological training
selection, SkillOpt gates, learning budgets, actual deployed versions and v2
commitment denominators. Thus the primary business endpoint remains the
equal-world change in fixed initial/benchmark commitment fulfillment. The v2
all-commitment endpoint retains endogenous orders separately. These are three
development pairs with reused seeds/cohorts; neither employees nor retries are
independent world replicates.

The new lifecycle checks additionally require source-bound service and world
intent/start/observation/cleanup chains. They verify the isolated service,
simulation and native sandbox identities, configuration hashes, declared wall
and cleanup limits, terminal exit status, final nonrunning processes and owned
socket cleanup. Observed environment closure alone cannot prove cleanup. World
overlap is reconstructed from launch through cleanup end and must remain within
the registered concurrency limit. Receipt validators read stored process
evidence; they do not claim cryptographic provider attestation or a fresh
host-wide process census.

Costs remain independent of behavioral acceptance:

- Online and learning-target native physical meters retain known input/output
  tokens, complete totals and unresolved request reservations separately.
- Optimizer transport receipts count physical requests. Proposals and prepared
  optimizer inputs do not become model calls. Replay sessions are counted once,
  rather than again through the learning ledger.
- Unreturned actions and missing native receipts retain conservative reserved
  calls/tokens. A work action reservation can precede target dispatch while its
  employee actor is planning. It is an upper bound, not measured spend.
- A later malformed learning record cannot erase an earlier known receipt.
  Malformed epochs retain their unresolved allowance; such evidence prevents a
  complete campaign claim.
- Contracted actor interviews have a separate client-cache receipt meter. A
  later uncertain request does not erase the independently reconciled earlier
  cache prefix. Server-side orphan receipts may contain additional costs that
  are outside this client-cache summary. Output-token reservations neither
  estimate nor bound unknown actor input tokens.
- Bootstrap, graph/social inference, currency billing and all-in campaign cost
  remain unknown. Complete employee accounting does not change that scope.

For completed worlds, independent receipt totals must close to the existing raw
world audit. Cleanup failure can invalidate scientific eligibility while leaving
those measured costs visible. Public output uses metadata, counts and hashes;
it does not export prompts, persona content, task files, answers, skill text,
provider exception messages or absolute private paths.

Offline tests use synthetic cohorts, fabricated receipts and stubbed validators
where explicitly labeled. They establish rejection and accounting logic, not
native execution or learning effectiveness:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -S -m unittest tests.test_scale_v2_audit -q
```
