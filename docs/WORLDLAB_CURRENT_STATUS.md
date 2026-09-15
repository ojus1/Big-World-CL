# Current development state — September 16, 2026 (India)

Fluso remains paused. At September 15 20:22 UTC, its experiment and both guardian
services were inactive with MainPID 0, and its former process was absent. The
shared gateway retains its global LLM concurrency limit of 64.

The pinned `bigworld-qwen38flashnext-throughput-v2` model container stopped at
20:18:20 UTC. Another workload, `fluso-meta-next-replica2-20260915`, now occupies
its GPUs 4–7 and port 8002. No new baseline was launched and neither runtime was
modified by this task. Resolve this resource conflict and verify the intended
inference identity before launching a fresh study.

Version 10 is now prepared offline at frozen source
`d936482b3f641fa670be774887e7e547fae23b00`, with no study execution or inference
calls during preparation. It retains six world pairs, 12 employees per arm,
20 days, 2,880 planned obligations and capacity for 5,760 work sessions. Each
world uses direct examples for one employee, role transfer for two and defaults
for nine; examples for every employee are not required. The native learner's
original budget is explicit in its factory configuration, including the
1,200-second replay allowance that fits 900 seconds of work plus 300 of judging.
The only specification change is `failure_policy: stop_after_current_wave`.
World assignments, validation cases, task coverage, personas and resource
reservations passed exact comparison with version 9. Original rubric rules,
request/validation methods and grade computation passed AST equality checks;
evidence projection and the qualified controller fixes are separately recorded.

Study SHA:
`936477c1fb9a35b2e11d88f3434bf751a872c81b875022aabfe459412f755348`.
Prospective analysis SHA:
`30c370c6cc9b64a41ed4f3a7bd0a0c743ffac1332819bb3cc68ea484001b2099`.
Preparation, the study, analysis, corrected coverage report and runtime refusal
are copied locally under `lifespan/artifacts/native-compact-v10-local/`, with
all 13 payload hashes and their cross-file bindings verified. Its operator is
`lifespan/artifacts/prepare-launch-native-compact-v10.py`: `prepare` performs no
inference; the separate `launch` checks the original model container, image,
arguments, GPUs and shared gateway before creating an execution service. The
replacement enables MTP and omits the qualified structured-output configuration,
so the runtime check correctly refuses it. No launch directory or study
`EXECUTION.json` exists. This remains a development comparison with narrow source
families and same-model grading, not a final significance study.

Shared controller commit `4114679e6b9f29d30c4f8e5cbbc8157c4720103a` adds
coordinated cancellation after terminal failures. New work stops at admission
boundaries while already admitted operations retain their original budgets and
receipts. Low scores and accounted budget exhaustion do not trigger cancellation.
All 25 focused checks passed locally and in the frozen H200 checkout
`Big-World-CL-cancellation-v1`, including real spawned process cancellation,
serial cancellation, normal complete study audit, employee cleanup and replay
accounting. The H200 test log and runtime snapshot are copied locally under
`lifespan/artifacts/cancellation-h200-v1/`. Test log SHA:
`f0409d77e13f4d297fec1e41ae25208ed5e07171d02d1509f466cded9a1de8fc`.

The frozen version-9 workplace study at `46c09c6` was stopped after terminal
world-pair failures were verified. Its service is inactive with MainPID 0; the
original PID is absent. No complete paired comparison or significance result
exists. Do not resume this artifact or combine its partial outcomes with a new
protocol as if they were a completed experiment.

The final snapshot contains 2,329 graded work/replay attempts, 36,618 physical
calls and 494,090,809 tokens in finalized attempts. This excludes unfinished
reservations, optimizer calls and employee/social costs; it is not a total bill.
Of 72 saved learning updates, 69 completed and three failed. Thirteen contain
accepted gates. The frozen-source offline audit verified 12 nontrivial updates
and 46 later sessions that loaded the deployed skills. The thirteenth gate was
written by a worker but had not been recorded by the controller when the run
stopped. It is not counted as a deployed update.

These are partial development observations. Same-model grading, narrow source
families, unfinished comparisons and the lack of a qualified final evaluation
still prevent a statistically supported learning-effect claim.

The reproduced failures were:

* Two replay callbacks had fewer than 300 seconds remaining. Reserving 300
  seconds for grading and clamping work to one second started empty native
  attempts, which could not load their skills.
* One replay produced an optional ZIP of its visible text deliverables, a format
  not supported by the duplicate-archive projection.
* One online task created a root `.venv`; the grader treated its runtime links
  and binary files as candidate deliverables and raised an error.

The next source version records an auditable, zero-dispatch budget stop when
the complete configured work window plus 300 seconds of grading cannot fit.
It never launches a shortened replay from the remainder. The skill remains unchanged and no
score is sent to SkillOpt. Root `scratch`, `.venv` and `__pycache__` directories
are runtime areas: their files and symlink targets remain in the artifact
inventory but do not enter text judging. The same names under `input/` or
`output/` receive ordinary evidence checks. ZIP bundles qualify only when every
ordinary file exactly duplicates a visible text file; links, new content,
changed bytes, unsafe paths and unsupported payloads remain rejected.

The initial change passed 99 local tests. The final full-window policy passed
28 local tests, and frozen source `64b00ac40c917fb142393d01836895d9ebe7b463`
passed 45 H200 checks with no skips, including native reference registration,
real pinned SkillOpt integration and spawned world/employee processes.

A real SkillOpt admission control ended as `budget_exhausted`, with unchanged
skill and zero model calls/tokens; its independent gate and admission audits
passed. Two fresh default-Hermes controls passed with 27 calls / 221,219 tokens.
New judgments of the exact previously rejected ZIP and virtual-environment
workspaces passed completion/accounting/audit checks with 7 calls / 71,021
tokens. Their scores were 1.0 and 0.0 respectively; the original workspaces and
old study results were not changed. No new workplace study has launched yet.

Public reference consultation is now an optional Hermes adapter. It exposes
complete, hash-verified named source snapshots through native tools, with an
audited access ledger. All three technical-writer tasks passed native adapter
qualification, including actual consultation of task-required references and
missing-output rejection. Their work executions exhausted their declared token
budgets; their graded rubric scores are 0.4545, 0.5667 and 0.3333. This is not full
task success or semantic-judge calibration. General web research and binary/visual
task support remain unfinished. See `WORLDLAB_JOBBENCH.md`.

Evidence on H200 under mutable lab `lifespan/artifacts/`:

* `compact-v9-stop-evidence-v1/`: before/after service state, stop intent and costs.
* `compact-v9-partial-adoption-audit-v1/`: exact-source update, replay and deployment checks.

The complete new qualification receipts, source snapshots, tests, operators and
partial v9 reports are copied locally in
`lifespan/artifacts/reference-admission-and-v9-evidence-v1-h200.tar.gz`.
All 1,605 payload hashes passed local verification after safe extraction.
Archive size: 7,904,200 bytes. Archive SHA:
`b6f528211aa226dc43d2cc060009f49cfaefb044ace7afa580c1e0b82a184952`.
Export manifest SHA:
`83ab059c17b948f448a3d396ce97f15a2c05e89fb00fb9c461427d5f0aa04e4d`.
The snapshot also lists 27 unfinished attempt directories and their available
receipts/reservations separately from finalized costs. No source worker remains
present. Runtime symlink targets are recorded without following or recreating them.

The full stopped study stays in the immutable version-9 checkout. The original
goal still requires broad realistic worlds, extensible harnesses and learners,
sparse representative-prompt calibration, and statistically supported effects.
Next work must complete fresh world comparisons under the qualified protocol,
broaden task/role coverage, qualify independent final evaluation, and freeze the
statistical design before observing final outcomes. Partial adoption counts do
not substitute for those requirements.
