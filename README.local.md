# MiroFish with GPT-5.6 Luna and local graph storage

The active model is `gpt-5.6-luna` with `reasoning_effort=low`. MiroFish runs at [http://127.0.0.1:3000](http://127.0.0.1:3000), with its backend at port 5001.

From this workspace:

```bash
python3 scripts/stack.py start
python3 scripts/stack.py status
python3 scripts/stack.py stop
```

Starting the stack launches only the backend and frontend. GPU inference is disabled, and `stack.py start llama` refuses to load a model. The previous llama.cpp build and GGUF downloads remain on disk for reference. These services remain running after the launcher exits, but do not start at login. Logs are in `logs/`; PID identities are in `run/`.

## Configuration

The supplied API key is in the ignored, permission-0600 `MiroFish/.env`. It is not included in the reproducible configuration or patches. The application reads `OPENAI_API_KEY` when `LLM_API_KEY` is unset. The active non-secret settings are:

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-5.6-luna
LLM_REASONING_EFFORT=low
GRAPH_BACKEND=local
LOCAL_GRAPH_ALLOW_REMOTE_LLM=true
LOCAL_GRAPH_WORKERS=4
```

Restart the backend after changing the environment. Simulations already running keep their original model configuration; start a new simulation after changing models.

Graph records, source episodes, provenance, simulation databases and reports remain on this computer. Entity and relationship extraction now sends source text to OpenAI using Luna low. `LOCAL_GRAPH_ALLOW_REMOTE_LLM=true` explicitly enables this while retaining SQLite storage. No Zep account is used. Search uses local FTS5/BM25 with CJK bigrams; this adapter does not implement Zep's semantic reranker or automatic temporal contradiction resolution. Failed ingestion remains visible, and simulation completion waits for pending graph writes.

OASIS recommendation embeddings use cached CPU-only PyTorch. The launcher keeps Hugging Face and Transformers offline. MiroFish does not use the GPU in this configuration.

## Luna API compatibility

MiroFish's text and JSON requests use Chat Completions with low reasoning and GPT-5-compatible token parameters. Luna requires the Responses API when combining function tools with reasoning. The adapter in `MiroFish/backend/app/utils/camel_responses.py` supplies that API to all three simulation runners, their interviews, and the report agent’s retrieval tools. Report sections require native tool calls before writing their conclusions; report chat also exposes the tools through the API. It preserves tool IDs and encrypted reasoning across tool-result follow-ups, separates concurrent agent histories, and uses `store=false`. It rejects incomplete tool calls. It does not implement streaming or structured-response mode for CAMEL; MiroFish's simulation runners use non-streaming text and function tools.

## Reproduce checks

```bash
python3 scripts/verify.py
MiroFish/backend/.venv/bin/python scripts/check_luna.py
MiroFish/backend/.venv/bin/python scripts/check_luna_tools.py
MiroFish/backend/.venv/bin/python scripts/tutorial_smoke.py university --output-dir results/tutorial-luna-university
MiroFish/backend/.venv/bin/python scripts/tutorial_smoke.py red_chamber --output-dir results/tutorial-luna-red_chamber
```

The live checks use the configured, billable OpenAI API. The first sends four short concurrent text requests; the second tests four concurrent tool-call round trips. The tutorial tests run two rounds on both Twitter and Reddit, with concurrent profile generation and four graph-extraction workers. They are workflow smoke tests, not API rate-limit stress tests.

Tutorial runners retain progress in `state.json`; choose a fresh output directory for a new run. They exercise upload/ontology, graph construction, profiles and configuration, simulation, graph-memory updates, interviews, reports and report chat. Checks reject inference errors, require new actions beyond manually seeded posts, and verify at least three retrievals per report section.

After a successful tutorial check, the script closes its simulation workers and verifies that the interview environment has stopped. Use `--keep-env` to leave workers available for additional live interviews; these workers otherwise wait indefinitely after simulation rounds finish. Resuming an already-passed tutorial closes its old environment without repeating model calls. Reports, graphs, interview history, and the backend/frontend services remain available.

The upstream repository links two demo videos rather than executable tutorial notebooks or the original source corpora. `tests/fixtures/` contains clearly labeled small adaptations of the university and Red Chamber examples. Their generated schedules are preserved in the results directory, then all fixture agents are activated for the two test rounds. These tests do not reproduce the original full datasets or establish predictive accuracy. Profile generation is creative simulation authoring, so personas can include invented details.

## Recreate or maintain the installation

The pinned MiroFish source revision and current provider settings are in `results/versions.json`. Tracked upstream edits are in `patches/mirofish-local.patch`; added modules and a secret-free environment template are in `local-overrides/`. To recreate, apply the patch to the pinned MiroFish checkout, copy `local-overrides/backend/` into its backend, and use `local-overrides/local.env` as a template for a new `MiroFish/.env`. Add your key privately and set file permissions to 0600. Do not overwrite an existing user configuration.

From MiroFish, run `npm ci`, `npm --prefix frontend ci`, and `uv sync --project backend`. Run `scripts/cache-runtime-models.py` from this workspace using the backend virtualenv once before starting offline embedding services.

See `LUNA-RESULTS.md` for current validation. Earlier local-inference experiments remain in `SETUP-RESULTS.md`, `OPENBMB-RESULTS.md` and `OPENBMB-Q8-RESULTS.md`; their scripts and GPU measurements describe the cancelled configurations.
