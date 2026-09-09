> Historical configuration: GPU inference was stopped at the user’s request. The active setup uses GPT-5.6 Luna low; see [LUNA-RESULTS.md](LUNA-RESULTS.md).

# Official OpenBMB Q4 GGUF baseline

These are historical Q4 results. The active model was subsequently switched to Q8_0; see [OPENBMB-Q8-RESULTS.md](OPENBMB-Q8-RESULTS.md). The Q4 tutorial attempts were interrupted after unbounded profile requests repeated for several minutes; they did not pass end-to-end. Their states and logs remain in `results/tutorial-openbmb-*` and `logs/tutorial-openbmb-*`.

This baseline used the official [OpenBMB MiniCPM5-2B Q4_K_M GGUF](https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/blob/main/MiniCPM5-2B-Q4_K_M.gguf). MiroFish continues to use `http://127.0.0.1:8080/v1`, model alias `minicpm5-2b`. The app is available at http://127.0.0.1:3000.

## Artifact and configuration

- Repository revision: `f76b778717db10cae6f2ea6ffb0e86ce1f31d08d`.
- Local file: `models/MiniCPM5-2B-Q4_K_M.gguf`, 1,561,318,368 bytes.
- Verified SHA-256: `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd`.
- The server now uses the GGUF's embedded chat template, verified identical to the earlier OpenBMB template override.
- ROCm 7.2.4, RX 7900 XTX, FP16 KV cache, Flash Attention, 32 inference slots, 64 HTTP workers, shared 131072-token KV pool, 32768-token individual limit, thinking disabled.
- Local SQLite graph memory and cached CPU recommendation embeddings remain configured as before.

The official file differs from the earlier gooseyai artifact; it is not a renamed copy. Its GGUF metadata has a different tensor quantization mix. The earlier model file, benchmark results and tutorial artifacts are retained. Current provenance is in [versions.json](results/versions.json); earlier provenance is in [versions-gooseyai.json](results/versions-gooseyai.json).

Evidence: [pinned download manifest](results/openbmb-model-manifest.json), [verified checksum](results/model-sha256-openbmb.txt), [GGUF metadata](results/openbmb-gguf-metadata.json), and [running server properties](results/server-props-openbmb.json).

## Compatibility and GPU concurrency

Real-server checks passed for plain chat, JSON parsing, MiroFish schema-enforced JSON, required function calls and tool-result follow-up. Bare `json_object` responses can still contain Markdown fences; MiroFish's existing schema handling remains necessary. See [compatibility results](results/inference-compatibility-openbmb.json).

Streamed OpenAI chat, 536 input tokens, up to 96 output tokens, two requests per concurrent client, prompt caching disabled:

| Concurrent clients | Requests | Errors | Aggregate output tokens/s | Median first token | p95 completion |
| --- | --- | --- | --- | --- | --- |
| 1 | 2 | 0 | 145.1 | 0.11 s | 0.67 s |
| 32 | 64 | 0 | 268.5 | 1.51 s | 16.10 s |
| 64 | 128 | 0 | 175.3 | 16.38 s | 40.74 s |

The fixed-length native completion test used 517 input tokens and exactly 256 output tokens, with EOS disabled. At 32 concurrent clients, all 64 requests passed, achieving **321.7 aggregate output tokens/s**, 6.39 s median first-token latency, and 38.22 s p95 completion latency.

The observer recorded **32 busy inference slots**, **98% peak GPU utilization**, and approximately **7.84 GB / 7.30 GiB total GPU VRAM used**. Sixty-four clients share 32 active slots; excess work queues. Rates include prompt processing and queue time. Short-prompt results do not establish long-context or sustained large-simulation capacity.

Compared with the earlier runs, 32-client streamed chat was essentially unchanged (268.5 versus 269.9 tokens/s). Fixed-length generation was lower in this run (321.7 versus 354.7 tokens/s); switching to the official artifact does not imply a speed improvement. These are individual benchmark runs, not a statistical performance study.

Raw results: [streamed chat](results/benchmark-openbmb-chat.json), [native generation](results/benchmark-openbmb-native.json). Each new result records its model revision and hash.

## Reproduce

Use the start/status/stop commands in [README.local.md](README.local.md). The [server launcher](scripts/llama-server.sh) selects the official file on every restart. No frontend or MiroFish API-key changes are required.

```bash
MiroFish/backend/.venv/bin/python scripts/check_inference.py --output results/inference-compatibility-openbmb.json
python3 scripts/benchmark.py --chat --tokens 96 --concurrency 1,32,64 --output results/benchmark-openbmb-chat.json
MiroFish/backend/.venv/bin/python scripts/tutorial_smoke.py university --output-dir results/tutorial-openbmb-university
MiroFish/backend/.venv/bin/python scripts/tutorial_smoke.py red_chamber --output-dir results/tutorial-openbmb-red_chamber
```

Tutorial runners resume the chosen result directory. For a fresh rerun, choose a new directory. They record model provenance and reject resuming a result produced by another model. The existing repository test/build results are preserved in [SETUP-RESULTS.md](SETUP-RESULTS.md); the initial Q4 switch preceded the subsequent profile-generation fixes documented with Q8.
