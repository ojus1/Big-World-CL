> Historical configuration: GPU inference was stopped at the user’s request. The active setup uses GPT-5.6 Luna low; see [LUNA-RESULTS.md](LUNA-RESULTS.md).

# Local MiroFish acceptance results

Verified on 9 September 2026. MiroFish, the ROCm llama.cpp server, and local graph memory are installed and running. The frontend, backend and inference health checks all pass.

The active model has subsequently been switched to the official OpenBMB GGUF. Current Q8 model verification is recorded in [OPENBMB-Q8-RESULTS.md](OPENBMB-Q8-RESULTS.md). The performance and demo tables below preserve the earlier gooseyai baseline.

- App: http://127.0.0.1:3000
- Backend: http://127.0.0.1:5001
- OpenAI-compatible inference: http://127.0.0.1:8080/v1, model `minicpm5-2b`
- Start/status/stop: `python3 scripts/stack.py start`, `status`, or `stop`, from this directory.
- Detailed operation and rebuild instructions: [README.local.md](README.local.md).

Services bind to loopback and survive the launcher exiting. They are not configured to start at boot. The earlier reports remain available; current live workflow results are documented with Q8.

## Installed configuration

The official [MiniCPM Q8_0 GGUF](https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/blob/main/MiniCPM5-2B-Q8_0.gguf) runs on the Radeon RX 7900 XTX (gfx1100, 24 GB), using a source build of llama.cpp with ROCm 7.2.4. The exact Git revisions, model revision, embedding revision and verified model SHA-256 are in [versions.json](results/versions.json).

The selected server configuration uses GPU offload, Flash Attention, FP16 KV cache, continuous batching, 32 inference slots and 64 HTTP workers. Thinking is disabled. There is a shared 131072-token KV pool, with a 32768-token per-request limit; the pool cannot accommodate 32 requests each using the full individual limit. See the exact [launch command](scripts/llama-server.sh).

Graph memory uses SQLite WAL, source-episode provenance, local schema-constrained LLM extraction and FTS5/BM25 retrieval. This removes the Zep Cloud dependency. It provides the APIs used by these MiroFish workflows, but does not reproduce Zep's semantic reranking or automatic temporal contradiction resolution. OASIS recommendation embeddings run locally on CPU, while LLM inference runs on the GPU. The launcher enables offline Hugging Face/Transformers operation after caching the runtime models.

## Earlier gooseyai inference performance

These are aggregate output-token rates including prompt processing and queue time, measured with two requests per client. Prompt caching was disabled. These short-prompt runs establish concurrent operation, not sustained performance for long histories or thousands of agents.

Final 32-slot configuration, streamed OpenAI chat API, 536 input tokens and up to 96 output tokens per request:

| Concurrent clients | Requests | Errors | Output tokens/s | Median first token | p95 completion latency |
| --- | --- | --- | --- | --- | --- |
| 1 | 2 | 0 | 140.5 | 0.12 s | 0.72 s |
| 32 | 64 | 0 | 269.9 | 1.51 s | 15.54 s |
| 64 | 128 | 0 | 189.8 | 16.91 s | 41.30 s |

The observer recorded **32 busy inference slots**, **98% peak GPU utilization**, and approximately **7.90 GB / 7.36 GiB total GPU VRAM used** during these runs. Sixty-four clients share 32 active inference slots; excess work queues. The higher latency at 64 clients is a measured capacity limit. Raw per-request results and sampled peaks: [benchmark-openai-chat.json](results/benchmark-openai-chat.json).

Final 32-slot configuration, native completion API, 517 input tokens and exactly 256 output tokens per request (EOS disabled for consistent generation length):

| Concurrent clients | Requests | Errors | Output tokens/s | Median first token | p95 completion latency |
| --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 354.7 | 2.96 s | 33.37 s |
| 64 | 128 | 0 | 241.8 | 35.73 s | 86.04 s |

Raw results: [benchmark-f16-slots32.json](results/benchmark-f16-slots32.json). Fixed-length native and shorter chat results are different workloads and should not be directly compared as an API performance effect.

Tuning evidence: moving from Q8 to FP16 KV cache at 16 slots improved native single-client throughput from 131.4 to 153.5 tokens/s and 16-client aggregate throughput from 281.0 to 354.5 tokens/s on this machine. Moving to 32 slots improved 32-client throughput from the original Q8 baseline's 232.5 to 354.7 tokens/s. It improved queue latency at 64 clients but did not improve aggregate throughput there. Earlier runs are preserved in [benchmark-native.json](results/benchmark-native.json) and [benchmark-f16.json](results/benchmark-f16.json).

## Repository checks and earlier gooseyai demo workflows

**162 tests passed:** 129 backend tests, 28 repository utility tests, and 5 added local graph/lifecycle tests. The frontend production build passed. Build output retains upstream chunk-size/dynamic-import warnings; pytest retains one plugin rewrite warning. Evidence: [verification-final.log](logs/verification-final.log).

Real inference compatibility checks passed for plain chat, MiroFish JSON parsing, enforced JSON schema, required function calls, and tool-result follow-up. See [inference-compatibility.json](results/inference-compatibility.json) and [check_inference.py](scripts/check_inference.py).

The [upstream README](https://github.com/666ghj/MiroFish) links two video demonstrations but does not bundle executable tutorials or their original input corpora. Both scenarios were therefore tested with explicitly reconstructed, small fixtures: a fictional university library-hours proposal and a five-character Red Chamber scenario. These are engineering smoke tests of the demonstrated workflow, not exact reproductions of the Wuhan University report or the full first-80-chapters demo.

Both tests passed upload/ontology creation, graph extraction, profiles and configuration, two active rounds on Twitter and Reddit, persistent graph-memory updates, a live agent interview, report generation/download, and report chat. The smoke runner preserves the generated configuration and overrides activity scheduling for its fixtures so both rounds actually exercise agents. It does not change the app's normal scheduling defaults.

| Adapted scenario | Initial graph | Final graph | Logged actions after round 0 | Failed actions | Result |
| --- | --- | --- | --- | --- | --- |
| University, 4 initial entities | 4 nodes / 6 edges | 4 nodes / 22 edges | 11 Twitter + 23 Reddit | 0 | Passed |
| Red Chamber, 5 initial entities | 5 nodes / 12 edges | 12 nodes / 33 edges | 15 Twitter + 9 Reddit | 0 | Passed |

Action totals include recorded no-op actions. Final graph growth includes extracted new names and aliases; it is not an entity-resolution accuracy score. Evidence and identifiers: [tutorial-summary.json](results/tutorial-summary.json), [university state](results/tutorial-university/state.json), and [Red Chamber state](results/tutorial-red_chamber/state.json).

Generated artifacts and live interaction pages:

- [University report](results/tutorial-university/report.md), [live university interaction](http://127.0.0.1:3000/interaction/report_1852cd9cc524).
- [Red Chamber report](results/tutorial-red_chamber/report.md), [live Red Chamber interaction](http://127.0.0.1:3000/interaction/report_26cdd4d04722).

The browser UI was checked through project history, the completed report, and the interaction screen showing all four university agents available.

## Fixes and observed limitations

Local extraction now uses two schema-enforced passes: entities, then relationships restricted to known extracted entity names. Bare `json_object` output from this model/server combination produced malformed or fenced responses, so the local MiroFish client uses a nonempty JSON schema. Failed extraction remains recorded and cannot silently produce a successful graph.

The local simulation completion path drains queued graph writes before marking a run completed while retaining its worker for interviews. This resolves the upstream lifecycle mismatch where completed simulation loops stayed marked running while their worker waited for interaction commands. Tests cover successful draining and failure propagation. The graph adapter also has persistence, concurrent ingestion, deduplication, provenance, paging, English/CJK search and failed-ingestion coverage.

**Report completion does not establish report accuracy.** The earlier gooseyai model runs produced repetitive, mixed Chinese/English reports with unsupported claims. For example, the university report discussed older generations and young professionals beyond the fixture's named actors. Some extracted relationships had incorrect direction, and cross-language aliases can become separate nodes. Reports and graph facts need review before substantive use. The requested model has been retained; no stronger cloud model was substituted.

Earlier malformed-extraction and idle-round attempts are preserved alongside the final passing states. An interrupted local graph batch leaves an inspectable processing record rather than providing automatic crash recovery. The final tests do not establish full Zep parity, long-context saturation behavior, or predictive validity.

All source changes are retained locally, with a [tracked-change patch](patches/mirofish-local.patch) and [adapter copy](local-overrides/backend/app/utils/local_graph.py) for rebuilding the pinned checkout.
