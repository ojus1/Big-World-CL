# Public data export

The GitHub repository contains source, documentation, tests, patches and credential-free templates. Runtime directories and raw datasets are ignored. The Hugging Face repository contains a curated export of the accepted `ecosystem-bwrap` run.

## Learner and evaluator boundaries

- `data/sessions.jsonl`: 14 viewer-friendly rows with day, employee, task and a serialized `session_json`. This duplicates `runs/ecosystem-bwrap/learner/sessions.jsonl` for convenient loading.
- `runs/ecosystem-bwrap/learner/`: authorized tool observations, native Hermes messages, before/after file manifests, work-tool calls and reward exports.
- `runs/ecosystem-bwrap/computers/`: final employee workspace/home files and any recorded memory/skill files. These are end-of-run snapshots, **not initial observations**.
- `runs/ecosystem-bwrap/filesystem_objects/`: versioned employee file bytes. Resolve only the hashes in the employee/session's authorized manifest.
- `runs/ecosystem-bwrap/evaluator/`: global timeline, actor sessions, full world state, private diagnostics, daily snapshots, checkpoint, provenance, native evidence and interrupted-attempt history. These are privileged audit material.
- `data/events.jsonl`: viewer-friendly copy of the global timeline, also privileged.

The `train` split is a packaging convention for one recorded experience, not a proposed training/test partition. Do not shuffle sessions or treat accumulated native conversations as independent episodes. Histories can repeat earlier messages. End-of-run memory, global events and future filesystem versions must not be exposed to an earlier learner. Delayed rewards are labels delivered at their recorded times; the full reward table is not an advance observation.

## Sanitization and integrity

The exporter reads an explicit allowlist and fails on unexpected binary content or symlinks. It excludes native credential/configuration stores, native profile databases, raw runtime logs, sockets and caches. OASIS trace rows are exported as logical JSONL instead of copying its SQLite database, which could otherwise retain unused pages.

Host absolute paths are normalized. Provider transport fields, encrypted reasoning payloads and reasoning-only fields are omitted while user/assistant/tool content and tool calls remain. Sanitized filesystem objects receive new SHA-256 addresses; references and sizes are updated. `release_manifest.json` lists changed object hashes, omitted field counts, release code revision and every published file's size and SHA-256 (except the manifest itself).

The original run's `VALIDATION.json` is retained as historical validation of raw evidence. Export validation separately checks event causality, session counts and the normalized before/after file hashes. The historical live run includes early source revisions and one separately retained infrastructure interruption. Publishing code is not retroactive fixed-revision provenance.

## Commands

```bash
python3 -m lifespan.validate_ecosystem lifespan/artifacts/ecosystem-bwrap
python3 scripts/export_dataset.py lifespan/artifacts/ecosystem-bwrap \
  release/BigWorld-PoC --code-revision "$(git rev-parse HEAD)" \
  --env-file MiroFish/.env
python3 scripts/scan_release.py --git-index --env-file MiroFish/.env
python3 scripts/scan_release.py release/BigWorld-PoC --env-file MiroFish/.env

# Also run a maintained scanner, with full redaction in any saved report.
gitleaks dir release/BigWorld-PoC --redact=100
gitleaks git . --redact=100

# Explicit publication; provide HF_TOKEN privately in this process environment.
MiroFish/backend/.venv/bin/python scripts/publish_dataset.py release/BigWorld-PoC
```

Do not paste credentials into documentation or check them into Git. Exact configured-secret scans do not print values and supplement common token patterns; they do not prove absence of every possible form of sensitive data. Inspect the export allowlist and review any scanner findings before publishing.
