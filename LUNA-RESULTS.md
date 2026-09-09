# MiroFish: GPT-5.6 Luna low

Current configuration: `gpt-5.6-luna`, low reasoning, OpenAI API, local SQLite graph storage and CPU-only recommendation embeddings. The supplied key is only in the ignored `MiroFish/.env` (0600). A scan found no copies in exported scripts, patches, documentation, logs or results. Start with `python3 scripts/stack.py start`; open [MiroFish](http://127.0.0.1:3000). Full instructions: [README.local.md](README.local.md).

## GPU release

The ROCm llama.cpp server and obsolete local-model simulation workers were stopped. During the Luna tutorials, ROCm reported 0% GPU use, no KFD compute processes, and 27,947,008 bytes (26.65 MiB) of VRAM used. See [runtime evidence](results/luna-runtime-status.txt). Normal startup launches only backend/frontend, and explicitly requesting `stack.py start llama` is refused. Existing GGUF downloads and the ROCm build remain on disk.

## API integration and response quality

The supplied API key successfully ran the exact requested model with low reasoning. All MiroFish text/JSON paths share the configured reasoning setting. Each simulation runner uses the new CAMEL Responses adapter, including agent interviews. The report agent also uses formal Responses function tools for both section retrieval and report chat.

Live testing found that Luna rejects function tools plus low reasoning on Chat Completions. The simulation adapter uses Responses with `reasoning={"effort":"low"}` and `store=false`, preserves encrypted reasoning and tool IDs across follow-ups, and keeps concurrent histories separate. It rejects incomplete function calls. An additional report check found that Luna could decline tool instructions embedded only in text, resulting in reports with no retrieved evidence. Report generation now requires formal API tool calls before writing, and each section must record at least three retrievals. Multiple sequential tool rounds are preserved rather than collapsed by CAMEL’s chat preprocessor. The earlier reports are retained as superseded evidence. The original Chat-only trial directories are marked invalidated; their seeded posts were not accepted as proof of successful inference. The tutorial checker now explicitly rejects logged model errors and requires new actions beyond the seed posts.

The implementation follows the official [Responses migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses) and [stateless reasoning guidance](https://developers.openai.com/api/docs/guides/reasoning). See the [Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna) for supported reasoning settings.

- Four simultaneous short text checks completed in 3.28 seconds total: correct arithmetic, a faithful source summary, an explicit admission that an unsurveyed support percentage is unknown, and a coherent four-turn dialogue. All stopped normally, with zero duplicated six-word sequences. [Prompts and exact outputs](results/luna-quality.json).
- Four simultaneous function-call/result round trips completed in 4.11 seconds total. All created the requested post and acknowledged the correct unique post ID. These used one shared model backend to exercise history isolation. [Tool evidence](results/luna-tools.json).
- These are small live compatibility and quality checks, not a long-context repetition evaluation or a paid API rate-limit stress test.

## Verification

177 tests passed: 131 backend, 28 repository utilities, 18 local adapter/Responses/report tests. The frontend production build passed with existing bundle-size and mixed-import warnings. [Verification log](logs/verification-luna-final.log).

Both tutorial adaptations completed two Twitter/Reddit simulation rounds with real new model actions, no model errors, durable graph updates and successful interviews:

| Tutorial adaptation | Agents | Rounds | Logged Twitter / Reddit actions* | Final graph nodes / edges |
|---|---:|---:|---:|---:|
| university | 4 | 2 | 16 / 16 | 6 / 40 |
| red_chamber | 6 | 2 | 24 / 24 | 11 / 49 |

*Action counters include seeded posts and upstream round-log bookkeeping. The strengthened checker separately verified successful newly generated actions beyond those seeds.

Report generation and report chat passed for both adaptations. The university report has 3 sections with 9 successful retrievals; Red Chamber has 4 sections with 12 successful retrievals. There were no recorded tool-execution failures. Every section retrieved evidence at least three times.

- [University report](results/tutorial-luna-university/report.md), [full workflow state](results/tutorial-luna-university/state.json): `report_5818ad638948`.
- [Red Chamber report](results/tutorial-luna-red_chamber/report.md), [full workflow state](results/tutorial-luna-red_chamber/state.json): `report_c5628694626b`.

The reports are coherent and use retrieved facts about the named participants. They distinguish proposed changes and simulated reactions from confirmed outcomes; they are not empirical forecasts.

The university run is `sim_20235e34c7bb`; the Red Chamber run is `sim_69563d2e5e4f`. Source fixtures are small reconstructions of the README's demo-video scenarios; the repository does not include the original video source datasets. These are smoke tests of the five-stage workflow, not full reproductions of the university source report or the 80-chapter literary example.

Graph storage and retrieval remain on disk, while graph extraction sends source text to OpenAI. The local adapter uses lexical FTS5/BM25 rather than Zep semantic reranking or temporal contradiction handling. Generated personas and simulated events may contain invented details. The two final reports are in English. Interviews inherited the upstream Chinese instruction prefix and returned Chinese responses despite English source material.
