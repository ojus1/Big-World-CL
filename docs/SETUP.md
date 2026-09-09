# Reproducing the integration

The accepted run used Linux, bubblewrap 0.9.0, Python 3.11 for MiroFish, a separate Hermes virtualenv, and `gpt-5.6-luna` with low reasoning effort. The upstream revisions are pinned below; model availability and generated decisions are not deterministic. Tests of the original installed stack are recorded in `LUNA-RESULTS.md`.

Prerequisites: Git, Python 3.11–3.13, `uv`, Node.js 18+, npm, and bubblewrap (`bwrap`). On Debian/Ubuntu, bubblewrap is the `bubblewrap` package. The host must permit unprivileged user namespaces; run the native sandbox check below before a live experiment. No Docker setup is needed for the default backend.

## MiroFish

From this repository root, for a fresh checkout:

```bash
git clone https://github.com/666ghj/MiroFish.git MiroFish
git -C MiroFish checkout 39d849138ef254f6c737ab4c4705e5545dbe31d4
git -C MiroFish apply --check ../patches/mirofish-local.patch
git -C MiroFish apply ../patches/mirofish-local.patch
cp -r local-overrides/backend/. MiroFish/backend/
npm --prefix MiroFish ci
npm --prefix MiroFish/frontend ci
uv sync --project MiroFish/backend --python 3.11 --frozen
uv pip install --python MiroFish/backend/.venv/bin/python -r lifespan/requirements-integrated.txt
MiroFish/backend/.venv/bin/python scripts/cache-runtime-models.py
```

The patch provides local SQLite graph extraction and a CAMEL Responses API adapter. Added modules live in `local-overrides/backend`. Runtime embeddings are downloaded once; the service launcher then uses the offline CPU cache. Graph extraction and agent inference still call the configured model service.

Create a private configuration without replacing an existing one:

```bash
test -e MiroFish/.env || (umask 077; cp local-overrides/local.env MiroFish/.env)
chmod 600 MiroFish/.env
```

Edit `MiroFish/.env` locally and set `OPENAI_API_KEY`. Do not place keys in commands, source files, notebooks or dataset cards. The template sets the model, base URL, low reasoning effort, local graph storage, remote extraction opt-in and loopback ports 5001/3000. It contains no credential. Review `README.local.md` for adapter limitations and service management.

## Hermes and employee computers

Use a dedicated installation or point at an existing compatible checkout. The PoC creates new run-local employee profiles and does not reuse personal Hermes configuration.

```bash
export HERMES_AGENT_ROOT="$HOME/.local/share/big-world-cl/hermes-agent"
git clone https://github.com/NousResearch/hermes-agent.git "$HERMES_AGENT_ROOT"
git -C "$HERMES_AGENT_ROOT" checkout 2c8a2b65aa148ceb178d2251c54a523af12092c9
uv venv --python 3.11 "$HERMES_AGENT_ROOT/venv"
uv pip install --python "$HERMES_AGENT_ROOT/venv/bin/python" -e "$HERMES_AGENT_ROOT"

PYTHONPATH="$PWD:$HERMES_AGENT_ROOT" \
  "$HERMES_AGENT_ROOT/venv/bin/python" -m lifespan.check_native_sandbox
```

Set `HERMES_AGENT_ROOT` in every shell that launches a run. When unset, the default is `~/.hermes/hermes-agent`. It must contain `venv/bin/python`. Hermes has no native bubblewrap backend at the pinned revision; this repository supplies a fail-closed `BaseEnvironment` adapter for its native terminal and file tools.

## Persona import and live run

The importer downloads the pinned source card, schema, manifest and one shard, verifies its SHA-256, and deterministically selects synthetic records. The ecosystem runner imports 12 distinct records itself; no separately generated substitute personas are used.

```bash
python3 scripts/stack.py start
MiroFish/backend/.venv/bin/python -u -m lifespan ecosystem \
  --out lifespan/artifacts/my-run --days 16 --max-sessions 2

# Continue the same persistent world beyond the pilot.
MiroFish/backend/.venv/bin/python -u -m lifespan ecosystem \
  --out lifespan/artifacts/my-run --days 16
python3 -m lifespan.validate_ecosystem lifespan/artifacts/my-run
```

A completed horizon cannot be overwritten. Completed checkpoints resume without repeating reconciled work. A remaining `inflight.json` requires checking native history and effects rather than deleting the marker and blindly replaying. See `lifespan/README.md` for state layout and `lifespan/docs/ECOSYSTEM_DESIGN.md` for lifecycle semantics.

Run-local Hermes and bubblewrap workers stop at the horizon. MiroFish backend/frontend services remain available until `python3 scripts/stack.py stop`. Do not delete run directories if you intend to resume or audit them.

## Validation

```bash
python3 -m unittest discover -s lifespan/tests -v
python3 scripts/verify.py
```

The first command exercises world transitions, authority, temporal changes, memory baselines, file validation, sandbox isolation and export integrity. The second checks the patched upstream backend, root tests, local adapters and frontend build. Live tutorial scripts documented in `README.local.md` make additional billable model calls; offline publication checks do not rerun them.

The released trajectory is historical integration evidence. Current code includes fixes made during and after the run, including additive mandatory checks; source hashes in the run manifest are not a claim that one fixed revision produced every recorded step. Re-running the current implementation produces a new experiment.
