> Historical configuration: GPU inference was stopped at the user’s request. The active setup uses GPT-5.6 Luna low; see [LUNA-RESULTS.md](LUNA-RESULTS.md).

# Official MiniCPM5-2B Q8_0: setup and quality results

The local server uses the official [OpenBMB Q8_0 GGUF](https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/blob/main/MiniCPM5-2B-Q8_0.gguf). MiroFish is available at http://127.0.0.1:3000. All graph memory remains local.

**Assessment:** Q8 gives meaningful answers to simple source-based questions and can produce coherent summaries. It is not consistently reliable for long profiles or simulation reports. Higher precision improved one controlled repetition test, but did not remove hallucinations, length overruns, or occasional unwarranted refusals.

## What the quality probes showed

The same fictional source and fixed sampling seed were used for Q4/Q8 comparisons. Probes covered four factual questions, a summary, short and long upstream profile prompts, and a fictional discussion. Fast mode used temperature 0.7; thinking mode used temperature 1.0 and top-p 0.95. The main thinking comparison allowed up to 4096 reasoning tokens, with a separate total generation cap. This is a diagnostic screen, not a statistically robust model evaluation.

- Both official Q4 and Q8 answered all four basic questions correctly: the proposal was unapproved, the suggested trial was two weeks, Maya requested safe transport, and Daniel requested additional evening staff.
- Q8's thinking-mode summary was coherent, stayed grounded in the supplied facts, and met the requested 120–180-word range. Its fast summary was coherent but shorter than requested.
- On the same thinking-mode discussion task, Q4 reached the total token limit with a 23.3% repeated English six-word-sequence fraction. Q8 terminated normally with no repeated six-word sequences in its final answer. Q8's response was still slightly below the requested length and had awkward dialogue markers.
- Q8's fast discussion exceeded the requested 350–450 words, reached 818 English words and hit the 1024-token cap. It became circular in topic even though exact repeated six-word sequences were rare.
- The unmodified upstream group-profile prompt caused Q8 to invent a founding date and institutional history. Another profile switched to Chinese despite the English setting. Q4 had similar problems.
- A 512-token thinking budget caused premature reasoning termination and planning text to leak into visible Q4 answers. The 4096-budget tests were kept separate. Thinking was not enabled globally as a presumed universal fix.

Raw answers, prompts, limits and timings: [Q8 probes](results/quality-openbmb-q8.json), [Q4 fast/512-budget probes](results/quality-openbmb-q4.json), [Q4 long-profile probes](results/quality-openbmb-q4-long.json), [Q4 4096-budget probes](results/quality-openbmb-q4-thinking4096.json), and [comparison summary](results/quality-comparison.json).

The repetition metric only counts repeated English six-word sequences. It does not measure Chinese repetition, semantic circularity, correctness or usefulness; the conclusions above also rely on reading the outputs.

## Local application fixes

The initial official Q4 tutorial attempts were interrupted after two uncapped profile requests repeated for several minutes. The upstream generator also classified custom person labels, such as `StudentRepresentative`, as organizations and requested very long institutional profiles.

The local profile path now uses source facts to distinguish people from organizations, keeps unknown ages nullable, and asks for concise profiles with hypothetical simulation behavior distinguished from source facts. The JSON grammar limits biographies to 360 characters and personas to 2400 characters; each attempt has a 4096-token cap. Truncated local profiles are retried rather than repaired into apparently complete JSON.

The shared local request helper now applies a nonempty schema to bare JSON requests and limits otherwise uncapped generation to 8192 tokens. This covers the profile and simulation-config paths that bypassed `LLMClient.chat_json`. Cloud-provider request behavior is preserved.

The real Q8 integration check produced a concise Maya Chen profile describing a student representative, the transport request, and the unapproved proposal. Her unknown age stayed null. Some other attributes, such as gender, were still inferred, so this is not a guarantee of fully source-grounded persona attributes. Evidence: [inference and profile checks](results/inference-compatibility-openbmb-q8.json).

**166 tests passed** (129 backend, 28 repository utilities, 9 local integration-regression tests), and the frontend build passed. Evidence: [verification log](logs/verification-profile-limits-final.log). The prior build warnings remain unchanged.

## GPU concurrency and its limits

The running server retains ROCm GPU offload, Flash Attention, FP16 KV cache, 32 inference slots, 64 HTTP workers, a shared 131072-token KV pool and a 32768-token per-request limit. The default remains fast mode, with thinking disabled. Large histories share the same pool and may require fewer simultaneous requests.

The original synthetic load prompt repeated one sentence 32 times. In that workload, Q8 produced 2 empty responses among 64 requests at 32 clients, and 5 among 128 requests at 64 clients. Follow-up calls also included unwarranted refusals. These are model-output failures even though the HTTP/GPU service remained operational. They are preserved in [synthetic load results](results/benchmark-openbmb-q8-chat.json) and [diagnostic responses](results/q8-empty-response-diagnostic.json).

A coherent, fictional MiroFish-style summary prompt then passed without empty responses or request errors:

| Concurrent clients | Requests | Errors | Aggregate output tokens/s | Median first token | p95 completion |
| --- | --- | --- | --- | --- | --- |
| 1 | 2 | 0 | 66.5 | 0.54 s | 1.43 s |
| 32 | 64 | 0 | 275.8 | 0.88 s | 10.95 s |
| 64 | 128 | 0 | 208.2 | 9.42 s | 25.87 s |

The input was 459 tokens and the generation cap was 128 tokens, with prompt caching disabled. Rates include prefill and queue time. This workload differs from the earlier synthetic one and should not be compared as a controlled speed improvement. See the [coherent prompt](tests/fixtures/concurrency_prompt.txt) and [per-request results](results/benchmark-openbmb-q8-realistic.json).

A repeat at 64 clients captured all 128 responses. All were nonempty; the English keyword/refusal screen passed 125. The other three switched partly to Chinese while still discussing the requested transport, staffing and information concerns. Samples were readable and preserved the unapproved status. This repeat measured 161.0 aggregate output tokens/s, showing substantial run-to-run variation from the initial 208.2. Evidence: [captured responses](results/benchmark-openbmb-q8-realistic-samples.json) and [limited relevance review](results/q8-concurrent-response-review.json). These checks do not certify every factual claim.

The native fixed-output test (517 input tokens, exactly 256 output tokens, EOS disabled) passed all 64 requests at 32 clients at **307.6 aggregate output tokens/s**. Observers recorded **32 active GPU slots**, up to **98% GPU utilization** across the tests, and approximately **8.75 GB / 8.15 GiB total GPU VRAM used**. See [native results](results/benchmark-openbmb-q8-native.json). Sixty-four clients queue behind 32 inference slots; low latency at that load is not guaranteed.

## Artifact and operation

- File: `models/MiniCPM5-2B-Q8_0.gguf`, 2,679,710,688 bytes.
- Pinned repository revision: `f76b778717db10cae6f2ea6ffb0e86ce1f31d08d`.
- Verified SHA-256: `c5415f8989bf88a8288f1b55a3cc371af53c07b0faa220a63bd7a990cfaba078`.
- API: `http://127.0.0.1:8080/v1`, model alias `minicpm5-2b`.
- ROCm 7.2.4, Radeon RX 7900 XTX. The official embedded chat template is used.
- Earlier official Q4 and gooseyai files/results are retained for comparison.

See [README.local.md](README.local.md) for start/stop commands, [active versions](results/versions.json), [Q8 download manifest](results/openbmb-q8-model-manifest.json), and [running server properties](results/server-props-openbmb-q8.json). Services survive the launcher exiting but do not start automatically at boot.

To repeat the quality probes:

```bash
MiroFish/backend/.venv/bin/python scripts/quality_check.py --output results/quality-new.json
python3 scripts/benchmark.py --chat --tokens 128 --concurrency 1,32,64 --prompt-file tests/fixtures/concurrency_prompt.txt --output results/concurrency-new.json
```

The quality script explicitly selects fast and thinking modes per request. It does not change the server default.
