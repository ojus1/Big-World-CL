# Original scale-v1 learner interrupted by host reboot

This bounded observation was made at `2026-09-10T08:49:02.585803+00:00`. The original campaign is `6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa`. The saved status still called seed 401’s SkillOpt arm “running”; the recorded boot identity differs from the current boot and all six checked prior process IDs are absent. Its present classification is **interrupted without a terminal receipt**. The reason for the reboot is unknown.

## All six original slots

The following values come from the saved status at `2026-09-10T08:32:18.027613+00:00`. They preserve earlier reported outcomes and are not newly re-audited full-run results. Adoption counts are historical selection metadata, not demonstrated skill benefit.

| Seed | Arm | Saved status | Current observation | Day | Online records | Updates | Adoptions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 211 | no_learning | completed | previously reported completed | 21 | 233 | 0 | 0 |
| 211 | skillopt | failed | previously reported failed | 11 | 143 | 15 | 1 |
| 307 | skillopt | failed | previously reported failed | 7 | 93 | 0 | 0 |
| 307 | no_learning | completed | previously reported completed | 21 | 239 | 0 | 0 |
| 401 | no_learning | failed | previously reported failed | 8 | 106 | 0 | 0 |
| 401 | skillopt | running | interrupted; no terminal receipt | 17 | 215 | 22 | 0 |

## Last durable learner evidence

The seed 401 SkillOpt checkpoint is on day 17 in the learning phase, with 215 online records, 22 completed updates and 0 recorded adoptions. Its last online record and last completed update match their selected raw files. All 215 session usage flags and 22 update accounting flags say complete; this observation does **not** certify the entire raw prefix or regrade its work.

The next learning epoch has two recorded baseline-validation dispatches. Attempt 0 returned a complete native meter: **8 physical calls and 81,914 tokens**. Attempt 1 retains its native INFLIGHT marker and instance record, but no returned session or failure receipt. Its actual call/token usage is unknown. The progress ledger reserves **16 calls and 250,000 tokens** for that attempt; its 24 calls and 331,914 tokens are known-plus-reserved totals, not measured epoch totals. No optimizer dispatch record or final epoch update exists.

No run REPORT, REPORT.v2, FAILURE or sixth supervisor result was written. Ending the old boot’s process lifetimes does not prove graceful or bounded cleanup. Earlier cleanup uncertainty remains unchanged. Neither the original nor scale-v2 comparison can be completed by reusing or resuming this prefix.

## Evidence scope

A new private snapshot preserves 16 selected raw files plus a bounded process observation and manifest. The capture rechecked source bytes, endpoint-record matches and the single returned replay’s native usage equations. It made no recursive artifact traversal, full-prefix audit, provider call, process signal or change to original artifacts. No private prompts, tasks, responses, skills, environment values, command lines or native profile paths are included here.

The [allowlisted JSON](scale-v1-reboot-interruption-v1.json) has raw SHA-256 `3d9170430e960ef444e8017fd811037ccdea1c10acd7d85657a6cdf684c9682b`. Its provenance binds the private capture manifest `a53e6ef0c943a8c1ce7a90675789214e22a07f837e9f21c49f9ef86b6a4125fb` and every selected input. Missing terminal evidence and unknown usage remain explicit.
