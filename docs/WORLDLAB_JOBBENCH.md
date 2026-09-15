# JobBench task and rubric adapters

`ReviewedOfflineHermes` extends the existing native Hermes execution path with
source-reviewed task capabilities. `SourceRubricJudge` selects the original
scoring protocol by source, so one future study can contain both JobBench and
internal EuroBench tasks. Existing frozen studies keep their original adapters.
Fluso remains paused.

The initial reviewed task is `jobbench/web_administrators/task1`, from the
training partition of the verified calibration bank. Its required facts are
provided locally; the external firewall reference is explicitly optional. It
requires CSV findings/audit tables, Nginx and iptables configuration replacements,
and a populated HTML incident report. The files are outputs in a sandbox; no
configuration is applied to a real server. Eligibility pins the original public
instruction hash and input formats. It does not waive source requirements or
grant blanket support to a profession or format.

The JobBench scorer retains the original rubric bytes and all subcriteria. Each
rubric earns its full weight only when every subcriterion passes. The quality
score is the weighted sum divided by total weight, rounded to four decimals;
rubric pass rate is reported separately. The host computes conjunctions rather
than asking the model to repeat arithmetic. API schemas require every named
subcriterion and Boolean verdict, with evidence filenames drawn from the actual
submission. Prompts request concise rationales; API token, call and time budgets
bound inference. No generated-text character limits are imposed.

Evidence includes complete UTF-8 candidate outputs, including `.conf`, `.rules`,
HTML and CSV, without character or row truncation. Original inputs, employee
metadata and declared scratch work are excluded from submissions. Extra root
outputs remain visible; the EuroBench extra-file score penalty is not imported.
Input changes are recorded. Symlinks and unqualified binary/document evidence
raise an explicit error instead of disappearing from a partial text projection.

This scorer follows the scoring contract in
`prem-research/harness-benchmarks@331d85b67b4e990abc2f7d52c8498dd3b2d8ddf2`,
`internal_benchmarks/jobbench/eval/judge.py`, for JobBench dataset revision
`7ff2673ac78f42e492b204f5fffe0b8ccc11bf7d`. The configured local Qwen model,
structured Responses transport and bounded repair policy differ from the
official evaluation runner. Scores are development measurements, not official
leaderboard results or independently calibrated semantic judgments.

Use `configs/worldlab/h200_reviewed_hermes_v1.json` and
`configs/worldlab/h200_source_rubric_judge_v1.json` with the existing harness/judge
factory arguments when preparing a **new** study. They use the shared gateway at
port 8011 and its global LLM concurrency of 64. Native qualification is a separate
receipt, not implied by the capability registry or unit tests. The repeatable
qualification entry point is `python -m scripts.qualify_jobbench_worldlab`; it
requires a clean frozen checkout and a fresh output directory. It runs one real
training task plus a missing-output control, records every physical call and
audits both cases offline. It never requires a favorable task score.

Binary documents, general web research, visual evidence and the remaining
JobBench tasks still require source-specific review and native qualification.
Broad task coverage, independent grader calibration and statistically supported
learning effects remain outstanding. Partial skill adoption evidence is recorded
in `WORLDLAB_CURRENT_STATUS.md`.

## Optional named public references

`ReferenceHermes` adds native `list_references` and `read_reference` tools. The
library stores original fetched bytes, deterministic content projections, source
URLs, capture times and hashes. HTML projections preserve the full declared
article element; the Markdown gist uses its pinned revision. No model summaries
or character caps are applied. Native tool responses are checked against both
the library and the access ledger. References never include private rubrics or
benchmark answer files. This is recorded-source consultation, not live search.

The source-reviewed technical-writer tasks use the original training partition.
Task 1 requires the Swagger Markdown example; task 2 requires the Google style
highlights and Microsoft reference guidelines; task 3's GitLab reference is
optional. Required sources must be present for execution admission. Qualification
also verifies that the agent actually consulted them. The task-3 source's
1,500-word minimum remains an original task requirement, not an invented output
cap. Original JobBench rubrics do not cover every public requirement, which the
judge identity explicitly discloses.

Capture with `python -m scripts.source_world_references --help`, then use
`configs/worldlab/h200_reference_hermes_v1.json`. The qualification command accepts
`--reference-root` and `--task-id`. It retains the ordinary native task and the
missing-output control with unconstrained task scores. The per-task judge-call
allocation is the original rubric count plus one bounded format repair, within
the declared maximum of 13. Local snapshots and source review do not by themselves
constitute native inference qualification.

## Native reference qualification on September 15, 2026

Frozen source `64b00ac40c917fb142393d01836895d9ebe7b463` passed all three
technical-writer adapter checks with complete accounting and offline audit.
The two tasks requiring named references actually consulted those sources.
Task 3 optionally consulted the available guides. All three native work
executions ended as `budget_exhausted`; grading then completed normally.

| Training task | Work calls / tokens | Work + grading calls / tokens | Rubric score | Missing-output calls / tokens |
| --- | --- | --- | --- | --- |
| Technical writer 1 | 17 / 383,932 | 27 / 514,979 | 0.4545 | 10 / 4,367 |
| Technical writer 2 | 10 / 295,016 | 18 / 429,686 | 0.5667 | 8 / 4,930 |
| Technical writer 3 | 13 / 362,589 | 25 / 451,112 | 0.3333 | 12 / 5,890 |

All missing-output subcriteria failed, giving score zero in each control. The
six cases used 100 physical calls and 1,410,964 tokens. No unfavorable task score
was retried. This proves the tested source consultation, execution, original
rubric aggregation, missing-output rejection and receipt audit paths. It does
not establish complete public-contract compliance, an official benchmark score,
independent judgment accuracy or a learning effect.

Plans, native trajectories, complete source snapshots and audits are in the
locally verified evidence archive documented in `WORLDLAB_CURRENT_STATUS.md`.
General live web research and binary/visual task capabilities remain pending.

## Native qualification on September 15, 2026

Frozen `Big-World-CL-jobbench-text-v1` at
`2daa70a454128df465ee6246a2d08eda95969894` passed native qualification and the
complete frozen-source offline audit. All **33 relevant tests** passed locally
and on H200. The web-administrator task contains eight original rubrics,
34 subcriteria and a total rubric weight of 50.

The real task reached its work-token budget after **13 calls / 392,273 tokens**.
The remaining budget could not fit the next conservative request reservation.
Its eight grading calls used **108,280 tokens**, producing a weighted score of
**0.12**. Execution plus grading took **170.333 seconds** and used **21 calls /
500,553 tokens**. The combined attempt is completely graded and audited; its
underlying native execution remains `budget_exhausted`, not ordinary successful
task completion. This low score is retained without retrying for a better one.

A separate predeclared control supplied the original inputs with no candidate
outputs. All 34 subcriteria failed, yielding score zero in **8 calls / 5,188
tokens**. Both cases together used **29 calls / 505,741 tokens** with complete
accounting. Plan SHA:
`4dae5a282eed00ea019a2a21534be2c7385f312f1ed71c2e3441523b0569c4d0`.
This validates the tested adapter path and missing-output rejection; it does
not establish broad JobBench performance or semantic judge accuracy.

The complete qualification and version-8 study failure evidence are preserved
in `lifespan/artifacts/jobbench-v1-and-v8-stop-evidence-h200.tar.gz`, SHA
`d01bfc05ab470b88cb3bd91f000dcaedaa27407dfd637e0d08ef6a218ea3b858`.
The archive is **4,317,975 bytes**; all **178 payload hashes** passed local
verification after safe extraction. Export manifest SHA:
`1d5aaf612c432b52149b8dc49522213eeb2374f75c40b3ee1d707f36890a3f1b`.
The full original stopped study remains on H200. Its failure and unknown
pending costs are separate from this completed qualification.
