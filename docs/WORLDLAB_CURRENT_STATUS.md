# Development status — September 18, 2026 (India)

The resilient v35 study started on September 18 at 10:25:32 UTC (15:55:32 IST),
using frozen production source `d7139de240019937aab49125c1a5e9b1634ca407`.
It defaults to `record_and_continue`: execution, grading, employee-decision and
learning errors retain their evidence while later scheduled work continues.
Failed learning keeps the prior skill; unknown usage retains reservations, and
missing grades never become fabricated training scores. Manual stop remains
available. An unrecoverable arm failure is reported as incomplete while other
arms continue. See [failure policy and time allocation](SIMULATION_RESILIENCE.md).

The v34 predecessor failed on September 18 at 02:36:12 UTC. It retains 626 online
attempts (625 complete grades and one incomplete grade), 276 finalized learning
replays and 24 completed updates; no pair completed. The triggering task stopped
new actions at its active deadline, then settled an admitted inference request.
That settlement left about 48 seconds for judging under the old shared deadline.
The new contract reserves a full 300 seconds for grading separately from work,
bounded settlement and worker termination. Replay wall time is 2,725 seconds;
epoch wall allowance is 55,200 seconds. Token and call budgets are unchanged.

Qualification passed 295 H200 tests without skips and a complete six-day paired
native pilot. The pilot retained one grading error, two employee-decision errors
and one learning-replay error while completing later work. Its ten online
attempts, ten native interviews, six replay records and all causal/failure/cost
evidence passed offline audit. The failed epoch retained its prior skill; the
next epoch completed five native replays with complete accounting. It generated
no optimizer proposal because selected training results were full-score, then
rejected unchanged-skill adoption at equal validation scores. There is no new
learning-benefit or candidate-adoption claim. Both planned pilot probes expired
unattempted behind backlog and remain in the denominator.

A separate grade of copied v34 outputs passed in 55.04 seconds, eight calls and
73,860 measured tokens using the unchanged grader and full time allowance. The
old partial grade and unknown-cost reservation remain untouched. Synthetic
pilot faults made no model calls themselves; their conservative reservations
must not be described as measured inference consumption.

The fresh large run retains six matched pairs, twelve employees, twenty days,
2,880 obligations and representative examples for only 2 of 12 employees. It
starts with fresh actors and seed skills. The model remains
`Qwen/Qwen3.8-Flash-Next-FP8` on the same H200 machine with LLM concurrency 64.
Fluso stays paused; the reserved final EuroBench split remains unopened. The unit
is `bigworld-development-large-v35`, with artifacts beneath the frozen v35
checkout at `lifespan/artifacts/development-large-v4`. The study hash is
`1c9e57bdcd1d9ef12fce1dda5e5d6531c4e343c99c47672bb44852f9bcfee3ed`.

## Historical v34 startup — September 18, 2026

The following startup observations predate the v34 failure described above.

Fresh run v34 started on September 17 at 21:57:38 UTC (September 18, 03:27:38
IST), using frozen source `016d542837fddc5b0d9be65141ec173c1fadc6f9`.
Startup verification at 22:04:00 UTC found six fresh simulations, 72 work
requests and three finalized native attempts whose artifacts, context, grades
and accounting passed offline audit. All six simulations had made their first
12 employee decisions. The study was active with no stop request. These are
startup observations; the six-pair study is still in progress.

The served model remains `Qwen/Qwen3.8-Flash-Next-FP8` on the same H200 machine.
The gateway was handling 64 simultaneous requests at the configured cap of 64.
The model container retained its original ID and September 15 start time, with
zero restarts. No GPU reassignment or serving reconfiguration was performed.

The repair loads each deployed skill through the pinned native reader before
work, verifies its bytes, and checks its presence in every physical inference
request. Separate startup/context receipts preserve the actual model trajectory.
Execution-validation failures now finalize ungraded attempts and retain known
costs through learning. Three retained failures reproduced rejection while
preserving their 32 calls and 325,227 tokens; original results were not changed.

Qualification passed 305 H200 tests with no skips and three fresh executions of
the exact failure contexts. A complete learning epoch then finished all 12
executed replays with full native, grading, context, optimizer and ledger audits.
Across qualification, all 15 attempts and 181 native work calls were verified,
including both seed and candidate skills. Fresh qualification consumed 275 total
model calls and 4,300,637 tokens. The three failure contexts share one task family;
the epoch executed four families, with two further confirmation families unused.

The candidate initially improved a validation draw but regressed at the final
proposal gate: mixed score 0.663462 versus baseline 0.692308. Adoption was rejected,
confirmation correctly skipped, and the exact seed skill retained. All scores,
source conflicts and recovered native-tool errors remain in the evidence. This
establishes operational behavior, not a learning benefit or independent semantic
correctness; same-model judgments remain provisional.

The replacement retains six matched pairs, twelve employees, twenty days, 2,880
planned obligations and representative examples for only 2 of 12 employees.
It starts with fresh actor state and the seed skill. Fluso stays paused and the
reserved final EuroBench split remains unopened. The unit is
`bigworld-development-large-v34`; artifacts are under the frozen v34 checkout's
`lifespan/artifacts/development-large-v3`. See the
[remediation record](H200_QA_REMEDIATION.md) for qualification details.

## Historical v33 — September 17, 2026

The v33 run later failed at 17:47:20 UTC after three learning replays omitted
skill loading. It retained 608 finalized online attempts, 264 finalized learning
replays, 21 completed updates and three failed updates; no pair completed.
Its original receipts, grades, failure state and in-flight records are preserved.
The earlier startup observations below are historical.

The repaired v33 large development study started on September 17 at 14:23:17 UTC
(19:53:17 IST), using frozen source `cfe42f4cbedddb189733b63a9ae6a2657e7a6499`.
The served model remains `Qwen/Qwen3.8-Flash-Next-FP8` on the shared H200 server,
with global LLM concurrency 64. No model-container restart or GPU reassignment
was performed. The study retains six matched pairs, twelve employees, twenty
days, 2,880 planned obligations and representative examples for 2 of 12 employees.
Fluso experiments remain paused and reserved final EuroBench tasks remain unopened.

The v32 predecessor failed at 01:06:39 UTC after 650 finalized online attempts
and 427 learning replays; no matched pair completed. Its original grades,
failure records and in-flight markers remain preserved. The fixes handle null
public requirements from rejected-artifact grades and use a compact structured
schema for the existing bounded judge-format retry. Normal judge requests are
unchanged. The new run uses fresh actor state and starts from the seed skill.

Qualification passed 250 worldlab tests and 16 optimizer tests on H200, with no
skips; all 7,986 retained normal criterion contexts remained identical. Twelve
positive/negative live controls matched, three fixed repetitions of the formerly
truncated criterion completed, and a complete fresh grade exercised the actual
repair path. A full fresh learning epoch completed and audited all 20 replays.
Its candidate passed proposal validation but regressed in repeated independent
confirmation, so adoption was rejected and the seed skill retained. These checks
establish execution and gate behavior, not a learning benefit or infallible judging.

Startup verification at 14:27:11 UTC found six fresh simulations, 72 work requests,
27 finalized attempts and three passing native attempt audits. A later snapshot
at 14:29:51 UTC found the unit active with 60 completed attempts, complete grades
and accounting, and no stop request. These are timestamped observations, not
current progress or completed-study results. The unit is
`bigworld-development-large-v33`; artifacts are under the frozen v33 checkout's
`lifespan/artifacts/development-large-v2`. See [the remediation record](H200_QA_REMEDIATION.md)
for qualification scope and limitations.

## Historical v10 state — September 16, 2026

Version 10 launched on September 15 at 21:47:58 UTC, after the user selected
the model already served on the GPUs. It uses `Qwen/Qwen3.8-Flash-Next-FP8`,
revision `236dfdf285828023ca3bcd3f37366c58a3469b13`, in the existing
`fluso-meta-next-replica2-20260915` container on GPUs 4–7, port 8002. Its current
MTP configuration and model service were left unchanged. The study's shared
gateway remains at port 8011 with LLM concurrency 64; unrelated clients can also
use the model server. Fluso experiment and guardian services remain paused.

The fresh serving checks passed: all 64 concurrent structured controls were
valid and matched their declared labels, with no unknown usage, in 39.501 seconds.
They used 174,198 input and 9,899 output tokens. Two native Hermes controls passed
full audits with 25 calls / 195,210 tokens. All 12 native employee decisions and
the structured optimizer transport check passed; the optimizer used one call
and 111 tokens. These are operational qualifications under shared load, not
workplace speedup or learning-effect estimates. The first semantic launcher used
a Python environment missing `aiohttp` and failed before any requests; that
startup failure is preserved, and the existing gateway Python environment ran
the successful check. No server package or configuration was changed.

Service `bigworld-native-workplace-compact-v10` has main PID `1573076` and
invocation `d9cc6a3038594ec5a3efc61c831e098b`. At 21:59:49 UTC its process was
present and 68 work attempts had finalized, all with completed execution and
grading statuses and no grading error. The six initial arms were on days 0–1;
no learning update had run yet and no stop marker existed. The gateway had seven
active calls and no transport errors. The execution pipeline runs the frozen audit and analysis
only after the entire study succeeds. A failure ends the pipeline and preserves
all evidence; no failed world or judgment is retried automatically.

Version 10 was prepared offline at frozen source
`d936482b3f641fa670be774887e7e547fae23b00`, with no inference calls during
preparation. It retains six world pairs, 12 employees per arm,
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
replacement enables MTP and omits the former server's compact-JSON setting, so
the original runtime check refused it. That historical refusal is retained.
The user then selected the currently served model; fresh qualification and
`launch-current-served-model-v10.py` bind the new serving identity to the
unchanged study and analysis. Launch receipts are in H200 lab artifacts
`native-compact-launch-v10/`, and native qualification receipts are in the frozen
study checkout under `shared-model-qualification-v1/`. This remains a development
comparison with narrow source families and same-model grading. A statistically
supported learning effect is not yet established.

The local lab copy of compact qualification and launch evidence is
`lifespan/artifacts/shared-runtime-v10-evidence-20260915T215949Z/`.
All 29 payload hashes and the archive hash verified; full native traces and the
running study remain on H200.

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
