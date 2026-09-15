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

Research access, binary documents, visual evidence and the remaining JobBench
tasks still require source-specific review and native qualification. In
particular, the technical-writer tasks requiring external references cannot be
admitted by merely adding their file extensions. Broad task coverage, independent
grader calibration, successful skill adoption and statistically supported
learning effects remain outstanding.
