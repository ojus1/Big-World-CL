# H200 Flash Next baseline runbook

## Locations

* SSH: `inference-testing@h200-3`, the host used by Codex task
  `01a08fbe-18ee-7922-86e3-3c68299b98c9`.
* Local repository: `/Users/surya/Documents/ChatGPT/bigworld-fluso/Big-World-CL`.
* Remote repository: `/home/inference-testing/apps/Big-World-CL`.
* Branch: `codex/h200-flash-next`; frozen study revisions are recorded in
  [the execution ledger](H200_WORLD_STUDIES.md).
* Dedicated Hermes: `/home/inference-testing/apps/Big-World-Hermes`.
* Current model container: `fluso-meta-next-replica2-20260915` on GPUs 4–7,
  reused unchanged at the user's request after fresh qualification.
* Shared model API, concurrency **64**: `http://127.0.0.1:8011/v1` on H200.
* Current underlying vLLM API: `http://127.0.0.1:8002/v1`.
* Original vLLM API on GPUs 0–3: `http://127.0.0.1:8000/v1`.
* Latest scale output:
  `/home/inference-testing/apps/Big-World-CL-workplace-v10/lifespan/artifacts/native-workplace-compact-v10`.
* Current scale service: `bigworld-native-workplace-compact-v10`, launched
  September 15, 21:47:58 UTC. Earlier failed studies remain preserved.
* Native employee backend: `http://127.0.0.1:5005`, installed under
  `/home/inference-testing/apps/Big-World-CL-judge-v11/MiroFish/backend`.
* Current native qualification: `Big-World-CL-workplace-v10/lifespan/artifacts/shared-model-qualification-v1` on H200.
* Calibration bank: `lifespan/artifacts/final-world-calibration-v1` on both machines.

The inference container and experiment service survive SSH disconnects. The
experiment is a transient systemd user service, not a reboot/resume scheduler.
The experiment does not update source or replace the shared model server. Its
frozen audit and analysis run only after the complete experiment succeeds.

The gateway service `bigworld-throughput-inference-gateway-v2` applies one shared limit
across employee, Hermes, judge and SkillOpt requests. `GET /status` on port 8011
reports active/peak requests, queue depth and errors. It forwards JSON and SSE
without retries. All new scale adapters use this endpoint. Existing frozen
studies using ports 8000/8010 retain their original configuration.

The scale spec sets `max_parallel_employees`, `max_parallel_worlds` and
`max_parallel_updates` to 64. Pools use only as many workers as there are jobs;
this study has six world pairs and 12 employees per world. Independent worlds
and employee epochs have separate processes, while each employee's gate/replay
sequence and each pair's arm order remain fixed.

Actor/profile/optimizer JSON uses supported structured constraints. Text verbosity
is prompt guidance, with API output-token budgets and no separate character
limits. The native optimizer edit array uses vLLM's
[structured-output JSON interface](https://docs.vllm.ai/en/latest/features/structured_outputs/).
The latest source uses JSON Schema for judge verdicts: citations select actual
evidence filenames, while explanation length is guided by the prompt. There are
no character limits. Reviewed source-defined file counts use direct checks.
The active model's complete serving configuration is recorded in the launch
receipt. It passed request-level structured-output checks without changing its
server settings. One returned
incomplete or invalid verdict may be regenerated within the original call,
token and time budgets. Both calls are charged and retained; valid verdicts
(including failures) are final. Timeouts and unknown usage are not retried.
Existing frozen studies keep their original judge.

### Historical qualification on the earlier dedicated server

The earlier 64-call short canary passed, but the first sustained six-world load produced
an employee timeout and incomplete grading. Do not treat that run as qualified
high-load success. The replacement uses the same pinned settings except MTP
disabled. It passed 64 concurrent semantic grading controls in 19.550 seconds,
all expected labels matching, with no timeouts or unknown usage. Native employee
decisions, two concurrent Hermes work cases and the optimizer transport also
passed before the fresh study launched at 04:05:17 UTC September 15. This is
development qualification, not a completed study or a learning-effect result.
That replacement study subsequently encountered truncated judge responses and
was operator-stopped; it is not a completed six-pair result. Judge version 13
passed all 113 saved-evidence grades with complete accounting. Its unchanged
semantic prompts/schema passed 64 concurrent controls in 13.240 seconds.
Twelve native employee decisions, two Hermes controls and the explicitly
profiled optimizer call also passed. The fresh six-world experiment launched
at 04:48:17 UTC September 15, but later failed in pair 409 before grading a
solver's output: the old evidence reader rejected virtual-environment symlinks
under the otherwise excluded `scratch/` directory. The remaining study workers
were stopped, with MainPID zero and gateway idle verified at 05:22:19 UTC.
The inference server remains available. The broader 76-call semantic check then
completed with known usage but matched only 75 labels. Fresh-source qualification
is required before another scale launch. No successful-learning result exists.
The version-14 suite also matched 75/76 labels and failed qualification. The
version-15 judge explicitly requests temperature zero and top-p one, with
dispatch enforcement and audited sampling metadata. It passed 76/76 semantic
controls in 8.994 seconds, all 226 saved-output grading audits and two fresh
native Hermes controls. The fresh complete six-pair study launched at 06:09:20
UTC with its analysis frozen beforehand. Its initial checkpoint has no observed
pair failure; no completed-pair or successful-learning result exists yet.
See the execution ledger for receipts and corrections.

## Serving configuration

Model `Qwen/Qwen3.8-Flash-Next-FP8` is pinned to revision
`236dfdf285828023ca3bcd3f37366c58a3469b13`.
The image is
`vllm/vllm-openai@sha256:fc120ece0a388cc0aa1caad4a9f1cd92113484ab7ec2fd0efadd62585be05bf8`.
The pinned image's recorded vLLM version is `0.1.dev20073+g8e685d198`.

The active shared runtime retains the following Flash Next flags, including
MTP with three speculative tokens. Its exact argument array, container ID,
start time and GPU assignment are in `native-compact-launch-v10/DISPATCH.json`:

```text
Qwen/Qwen3.8-Flash-Next-FP8
--max-num-seqs 256
--enable-prefix-caching
--no-enable-flashinfer-autotune
--tensor-parallel-size 4
--moe-backend triton
--gpu-memory-utilization 0.85
--enable-auto-tool-choice
--tool-call-parser qwen3_xml
--reasoning-parser qwen3
--speculative-config {"method":"mtp","num_speculative_tokens":3}
--revision 236dfdf285828023ca3bcd3f37366c58a3469b13
```

The earlier dedicated container, `bigworld-qwen38flashnext-throughput-v2`, is
stopped. It omitted `--speculative-config` and its value and added:

```text
--structured-outputs-config {"backend":"xgrammar","disable_any_whitespace":true}
```

Its exact Docker argument array and predecessor identity are in
`Big-World-CL-lab/lifespan/artifacts/throughput-compact-json-server-v1/INTENT.json`.
That receipt reproduces the historical dedicated configuration; the preceding
`throughput-server-no-mtp-v1` receipt predates compact JSON. The current shared
runtime was separately qualified before version 10 launched.

The current shared container binds host port 8002 to container port 8000 only on
loopback and is restricted to GPUs 4–7. The original container still serves
host port 8000 using GPUs 0–3. The current argument array has no CPU KV offload
flag. The API reports a 262,144-token context limit.

Requests use the explicit `responses-no-thinking-v1` profile: nonstreaming
Responses, storage disabled and thinking disabled. The same endpoint supplies
actors, Hermes target work/replays and the SkillOpt reflector. The API credential
is the dummy value `EMPTY`, kept in private runtime configuration.

The previous idle container `qwen38-27b-all-gpus-20260911` was stopped and retained.
The prior regression supervisor had already failed and was not running when the
serving change was made.

## Runtime dependencies and configuration

* MiroFish: `39d849138ef254f6c737ab4c4705e5545dbe31d4` plus this branch's
  `patches/mirofish-local.patch` and all four files under
  `local-overrides/backend/app/utils/`.
* Hermes: clean `2c8a2b65aa148ceb178d2251c54a523af12092c9` in its own venv.
* SkillOpt: clean `79124b37e9a6371e13b753f8bcd7adb1e493ade1` in `.cache/SkillOpt`.
* Backend Python: 3.11.16; bubblewrap: 0.9.0. Embeddings are cached and run on CPU.
* The model and MiroFish services bind loopback. No frontend was needed for these
  command-line experiments.

Set `HERMES_AGENT_ROOT` whenever launching native work. Put `LLM_MODEL_NAME`,
`LLM_BASE_URL`, and dummy API keys in the private `MiroFish/.env`. Set
`BIGWORLD_PROVIDER_PROFILE=responses-no-thinking-v1` in live launching shells.
Keep the profile selector and `FLASK_PORT`/`FLASK_HOST`/`FLASK_DEBUG` out of `.env`:
pinned MiroFish loads that file with `override=True`.

The normal experiment service uses port 5001. The fresh actor qualifier owns port
5002 and requires an empty backend uploads directory. Never run it against an
active experiment service. Completed actor qualification snapshots retain their
own native uploads, so moving a stopped run's working uploads preserves evidence.

For setup validation, use the backend venv and
`scripts/check_mirofish_installation.py`. Offline tests must run without the live
`BIGWORLD_PROVIDER_PROFILE` selector. Otherwise legacy mock-provider fixtures
inherit the real provider contract and fail before their intended assertions.

## Native qualification evidence

The historical `h200-q3` artifacts use the execution source containing the mailbox
fix. Read-only auditors were run against raw manifests, native receipts,
submissions, file readbacks, SQLite traces and cleanup observations.

| Component | Result | Measured scope |
|---|---|---|
| MiroFish actor roles | Pass | 4 contracted interviews, 5,232 tokens; exact employee, enterprise, consumer and government fixtures |
| Hermes employee transport | Pass | 3 workflows, 35 physical model calls, 384,385 tokens; native skill load, submission and file readback |
| SkillOpt reflector | Pass | 1 real request, 735 tokens, 1 parsed edit from a synthetic TRAIN fixture; no adoption claim |

Actor bootstrap/social calls are outside its contracted-interview meter. Audit
JSON files are siblings of the component directories: `actor.AUDIT.json`,
`employee.AUDIT.json`, `optimizer.AUDIT.json`. Do not add derived audit files
inside a frozen raw evidence tree, whose inventory is immutable.

To invoke the optimizer qualifier directly, use
`python -m scripts.preflight_optimizer`, or set the repository PYTHONPATH. The
script's direct-file import path does not add the repository root automatically.

The final offline suite passed **994 tests**, with three skips, in 124.24 seconds.
The regression set covers custom Hermes paths, reply ID normalization, task-bank
path safety, file tampering and connected-family partitioning.

Earlier failed attempts remain under `h200-flashnext-qualification-v1` and
`h200-pilot-v1`; `h200-q2` preserves passing qualification of the preceding
runtime revision. The first pilot stopped after seven completed work
sessions in each arm because of mixed colleague-ID namespaces. Its interrupted
work is excluded from completed comparisons. The replacement has a fresh world,
new manifests and newly qualified source; no failed checkpoint was edited.

## Integration pilot and live inspection

The two arms have matching seed-101 personas and configurations. They each run
eight action days with up to 48 work sessions and delayed settlement. Only the
focal onboarding employee may learn in SkillOpt; all six employees do work.
TRAIN=1, VAL=1, K=1, update cadence=2 days. The pilot preserves the repository's
protocol apart from provider routing and explicit actor contracts.

`scripts/run_h200_baselines.py` binds configurations, cohort bytes, dependencies,
provider, source and fresh qualifications. It owns the MiroFish backend and two
runner processes inside `bigworld-h200-baselines.service`. The service has 64 GiB
RAM, zero swap, 2,048 tasks, a 15,600-second lifetime and control-group cleanup.
The launcher stops on a native failure and runs strict completed-world audits
before writing `pilot/PAIRED_REPORT.json`. It does not require positive scores or
an accepted skill edit. It does not automatically launch the final world.

Run these read-only commands on the H200 host:

```bash
cd /home/inference-testing/apps/Big-World-CL
systemctl --user status bigworld-h200-baselines.service --no-pager
cat lifespan/artifacts/h200-pilot-v2/STATUS.json
tail -20 lifespan/artifacts/h200-pilot-v2/pilot/skillopt.log
tail -20 lifespan/artifacts/h200-pilot-v2/pilot/no_learning.log
curl -fsS http://127.0.0.1:8000/v1/models
nvidia-smi
```

`STATUS.json` records the update time, day, phase, work count, learning epochs and
adoptions. `INFLIGHT.json` distinguishes work from learning underway. Inspect
`FAILURE.json` and native logs if the service stops. Retain incomplete attempts;
do not delete an inflight marker to force a replay. The service's graceful stop
command is `systemctl --user stop bigworld-h200-baselines.service`.

## Sourced calibration bank

The source checkout is
`/Users/surya/Documents/ChatGPT/bigworld-fluso/harness-benchmarks`, at
`331d85b67b4e990abc2f7d52c8498dd3b2d8ddf2`.
JobBench data are pinned to Hugging Face revision
`7ff2673ac78f42e492b204f5fffe0b8ccc11bf7d`, with all 398 official locked files
verified. Internal r3 rubrics match the exact 264 released definitions.

The bank's manifest SHA-256 is
`d526c0943ea6639e73cb7e64c5784aaa616b788ea996e91640d146ceced26e4f`.
It was verified independently after copying to H200:

```bash
python3 scripts/source_world_calibration.py verify \
  --out lifespan/artifacts/final-world-calibration-v1
```

`TASKS.jsonl` indexes every task, source, language/workflow, family, partition,
public input directory, private rubric directory and content hashes.
`FILES.json` covers 2,791 files. `MANIFEST.json` explains provenance, exclusions,
partitioning and execution requirements. `VERIFICATION.json` contains the local
verification receipt. The raw bank is ignored by Git; it has not been published.

The source importer groups translated/template-related tasks before assigning
calibration TRAIN/VAL/holdout. It never imports historical solver outputs, judge
labels or JobBench reference answers. The final world's multi-file/native app
adapter and budget calibration are not represented as completed by this bank.
See `H200_CODEBASE_REVIEW.md` for the concrete runtime changes they require.
