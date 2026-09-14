# Employee calibration and task-package experiments

Representative examples are optional and may cover **any subset of employees**.
The simulator owns the full workforce. A user can supply examples for just one
employee without describing every colleague.

Examples for every employee are never required. Supplying no examples at all
is valid. These examples currently calibrate task selection; they do not prove
that an individual's writing style or workplace behavior has been reproduced.

This module connects the locked JobBench/Internal EuroBench bank to reproducible
development calibration. It is an extension of the H200 work, not a claim that
the final large-world learning study has been completed.
The [study protocol](WORLDLAB_STUDY_PROTOCOL.md) records the scale configuration,
required learning evidence and the boundary between development and confirmation.

For a running workplace study, use the read-only progress command on its host:

```bash
python3 scripts/report_worldlab_progress.py \
  --study /path/to/frozen-study-artifacts \
  --service bigworld-native-workplace-scale-v1.service
```

The optional service is an operator-selected systemd user unit. Its current
MainPID and state are reported separately from saved experiment progress; the
command does not start or restart anything. It lists all planned world arms,
completed and unfinished attempts, learning receipts, employee interviews and
unknown accounting. Learner-ledger tokens already include replays, so the report
keeps those categories separate and provides no misleading combined cost total.
An in-flight marker does not prove that a process is alive, and service success
does not prove a successful experiment audit or a learning effect.

## Calibrate a subset

The simulator-generated workforce provides employee IDs, roles and languages.
The user supplies only an overlay such as:

```json
{
  "finance-alex": [
    {
      "prompt": "Reconcile supplier invoices against changing tariffs and explain discrepancies.",
      "matches": 2,
      "weight": 1,
      "selector": {"sources": ["internal_eurobench"]}
    }
  ]
}
```

Use the overlay with the existing workforce specification:

```bash
python3 -m worldlab fit \
  --bank ../Big-World-CL/lifespan/artifacts/final-world-calibration-v1 \
  --spec generated-workforce.json --employee-examples employee-examples.json
```

Programmatic callers can use `attach_examples(workforce_spec, examples)` followed
by `fit(bank, specification)`. Neither operation changes the input workforce.
Inline `representative_tasks` remains available in the employee specification.
See [the partial example](../configs/worldlab/partial_employee_examples.json).

Every employee remains in the returned workforce:

| Evidence | Status | Behavior |
|---|---|---|
| Usable examples supplied for this employee | `direct_examples` | Use its retrieved task mixture |
| No examples, but matching role and language have examples | `role_transfer` | Use that role's mixture and record donor IDs and the transfer assumption |
| No applicable matches | `uncalibrated_default` | Return `task_mixture: null` and `default_action: retain_simulator_default` |

`calibration_role` can group differently named job titles; otherwise the exact
role label is used, ignoring case. Languages must match. An employee's own
unmatched examples remain visibly uncovered; they do not silently get replaced
by someone else's examples. No examples at all is valid and leaves everyone on
defaults. The calling simulator is responsible for retaining those defaults;
the optional native employee mode uses this calibrated workforce and role-based arrival schedule.

The test suite exercises a 100-employee workforce with examples for only one
employee. Transferring its mixture to colleagues does **not** manufacture 99
additional observed examples or calibration replays.

The simulator can also expand `workforce_templates` into a roster. A template
specifies role, language, headcount and default task pool; no employee prompts
are required. IDs are stable, such as `research-en-001`. The user then supplies
the same optional examples overlay. Templates cannot contain representative
examples, so one observation cannot accidentally become every employee's data.
See [the 12-employee coverage configuration](../configs/worldlab/development_coverage_v1.json)
and [its one-employee overlay](../configs/worldlab/development_coverage_examples_v1.json).
These synthetic defaults span three departments and three languages; they are
not measurements of a real workforce. The configuration plans 960 work attempts
per world pair and 36 possible learning epochs, before any outcomes are observed.

## What the fit means

Only calibration-training task briefs are searched. An explicit task-ID selector
must also stay in that partition. The transparent TF-IDF cosine ranking reads
public briefs, never gold, prior outcomes, private criteria, validation briefs or
holdout briefs. Each employee's retrieved tasks have distinct connected lineage
groups. Translations and shared templates remain grouped.

This is task retrieval, not a semantic-equivalence certificate. In the five-person
example, one employee has direct examples, two inherit the same-role mixture and
two retain defaults. `weighted_retrieval_coverage: 1` refers only to finding the
requested number of matches for supplied anchors; it does not mean the entire
workforce has been empirically calibrated. Employee coverage is reported
separately. User-specified weights describe the desired task mixture and are not
measured workplace frequencies.

The world compiler separately reports `calibration_application`: the retrieved
weight actually available in that employee's supported training pool and any
unavailable matched task IDs. Finding an example is not enough to call it applied
when the selected harness cannot execute it; those employees retain defaults.

## Execution boundaries and extension points

```mermaid
flowchart LR
  E[Examples for a subset] --> F[Public task retrieval]
  B[Locked source bank] --> F
  F --> P[Frozen calibration plan]
  P --> H[Harness interface]
  B --> W[One task's public workspace]
  W --> H
  H --> A[Native artifacts and usage receipts]
  G[Evaluator-only definitions and graders] --> R[Independent regrading]
  A --> R
  R --> D[Calibration diagnostics]
```

`worldlab/contracts.py` defines independent `Harness`, `Learner`, `TaskRequest`,
`Budget` and released `Feedback` contracts. The campaign accepts harness and
grader instances, rather than embedding a model loop in task generation. A new
harness supplies identity, capability checks and execution receipts. It receives
the current public request, workspace, deployed skill and budget; private grading
definitions and sibling tasks stay with the controller.

The implemented harness runs the pinned **native Hermes AIAgent** with its
terminal/file/skill tools in bubblewrap and the already qualified nonstreaming
Responses transport. Every replay has a fresh profile and filesystem. The
physical-call meter enforces token reservations and disables unmetered auxiliary
inference. Logs are outside the task workspace. Original input bytes and all
native outputs are preserved.

The calibration campaign's grader calls the original EuroBench mechanical evaluator. It
returns `quality_score: null` and `quality_judging: not_executed`; mechanical
checks alone are not the frozen qualitative rubric. The following capabilities
remain explicit gaps, and affected tasks are reported as unsupported:

- JobBench research and document-tool qualification.
- Native app state and interactive employee tools.
- Binary document runtime qualification and private executable grading.
- Visual judging and the official JobBench rubric adapter.

The chronological task-world runner now connects native Hermes, the frozen
Internal EuroBench text rubric and pinned SkillOpt. `NoLearning` provides the
matched control. A Fluso adapter remains to be implemented and qualified.

### Chronological task worlds

`worldlab/worlds.py` compiles a complete schedule before execution. Each employee
has a role/language task pool and optional calibration mixture. It maintains
employee skills, delayed feedback, scheduled obligations and work receipts across
days. The current execution mode is controlled skill transfer: each work attempt
starts with fresh files and a fresh harness session. Its optional native employee mode adds reacting colleagues and persistent workplace consequences, described below. Neither mode currently supplies long multiturn user conversations or a broader institutional economy.

Training, validation and probe families retain the bank's original separation.
Released learning cases are selected by chronology and lineage, never by score.
SkillOpt sees training feedback; validation stays in evaluator-owned callbacks.
Accepted skill changes affect subsequent work. The final probe phase never enters
learning. Paired arms have identical fixed schedules and opposite execution order
on alternating seeds. An interrupted plan cannot automatically restart.

```bash
python -m worldlab.run_worlds prepare --bank BANK --out OUT \
  --spec configs/worldlab/development_world_v1.json --seeds 211 \
  --hermes-root HERMES --skillopt-root SKILLOPT
python -m worldlab.run_worlds execute --bank BANK --out OUT \
  --hermes-root HERMES --skillopt-root SKILLOPT
python -m worldlab.audit_worlds --bank BANK --out OUT
```

For operator-supplied adapters, replace `--hermes-root` with `--harness-config FILE`
and/or `--skillopt-root` with `--learner-config FILE` in both prepare and execute.
Each JSON file contains exactly `factory` (an importable `module:attribute`) and
`kwargs` (constructor arguments). The factory implements the `Harness` or `Learner`
protocol in `worldlab/contracts.py`; it supplies native receipts and an honest
identity including its external dependency versions. The experimental learner's
name must be a safe path component distinct from the reserved `no_learning` arm.
The loader additionally binds configuration bytes and factory-module bytes in the
frozen identity. Changed factories/configurations fail before execution. Keep
credentials in the runtime environment. Only operator-selected trusted code is
loaded; task files do not select adapters.

`configs/worldlab/h200_hermes_factory_v1.json` and
`configs/worldlab/h200_skillopt_factory_v1.json` select the installed H200 baseline
without changing its parameters. A custom harness audit uses the same
`--harness-config FILE` with `worldlab.audit_worlds`. A Fluso implementation can
use this interface, but no operational Fluso adapter is bundled yet.

The preparation records source and bank hashes, model/provider identities,
complete schedules and token reservation ceilings. All model costs include
judging: online work, target replays, replay judges and optimizer calls. The
SkillOpt adapter uses the existing pinned upstream implementation, including its
strict mixed-score improvement, per-case nonregression and fresh final validation
gate. It does not substitute a locally invented learning algorithm.

The qualitative judge uses each original frozen r3 criterion and complete text
files, with one metered schema-constrained verdict per criterion. Private rubrics
remain outside the worker sandbox. Judge-derived feedback is a constructed
training signal, not feedback from a natural user. The current judge shares the
solver model; offline audits verify evidence and arithmetic, not judgment truth.

Two format controls passed on H200 at `6602bd1`: an intact editing artifact
scored 1.0 and its copy with the required deliverable removed scored 0.5 and
failed overall. These used eight calls and 26,456 tokens. An earlier unstructured
negative control emitted prose outside JSON and was retained as an incomplete
judgment. Schema-constrained output fixed that formatting failure. Two controls
do not establish broad judge accuracy.

The running `development-world-v2` study subsequently exposed a semantic
contradiction: `fig54_exact_count` returned `passed: false`, while its explanation
counted three occurrences and concluded the criterion passed. Direct file
inspection confirmed three corresponding references. Its original outcomes
remain unchanged, with a `JUDGE_QUALIFICATION_LIMITATION.json` sidecar restricting
interpretation to engineering evidence. The prepared 960-attempt coverage plan
was cancelled before any dispatch because it contained that judge version.

Judge version 3 emits evidence and a short justification before its Boolean
decision. The shared production transport passed 12 fixed count controls on H200:
three repetitions each of the original three references, a case-variation copy,
an extra-reference copy and a missing-reference copy. All twelve decisions matched
independently counted expectations; 12 calls consumed 72,120 tokens. This is a
qualification of that diagnosed count error and decision format, not broad
semantic accuracy. Plan SHA:
`1638ba837cb46de0a92f754f26ab39aca850314c8d929c2b2b1cacfbfbeec6fd`.
The reusable diagnostic is `python -m worldlab.qualify_judge`; it writes new
evidence and never changes the original study's grades or learning feedback.

### Adding and scaling harnesses

Learners also supply `audit_update(artifact_root, update, *, skill_before,
expected_identity)`. The world auditor owns chronology, released train/validation
selection, replay scores and costs, and later skill deployment. The learner's
auditor owns proposal provenance and its acceptance policy. A different learner
does not need to imitate SkillOpt's `configuration`, `optimizer_inputs` or gate
record format. The native SkillOpt implementation still runs its original gate
checker and additionally binds the recorded configuration, incoming/outgoing skill
hashes and optimizer transport receipts to its frozen identity and ledger.

All non-control learners return the common fields `status`, `accepted`, `skill`,
`train_ids`, `validation_ids`, `replay_evidence` and `costs`. Scored replay records
identify the selected experience, zero-based attempt index, hard/soft score and
skill-content hash. Target cost operations remain in that attempt order and
include solver and judge usage. They point to the controller-created
`replay-NNN` directories; algorithm-specific evidence can live alongside them.
The adapter's policy auditor remains responsible for verifying how optimizer
inputs and proposals were derived, including keeping validation out of training.

Supply `--learner-config` as well as `--harness-config` to
`python -m worldlab.audit_worlds` when those factories were used. A configured
implementation cannot silently use a built-in auditor just because its name
matches. Factory preparation requires the learner audit method before dispatch.
The non-SkillOpt routing test uses a deterministic rule fixture; it is interface
evidence, not a demonstrated learning algorithm.

`Harness.run()` returns normalized trajectory, usage and skill-loading evidence;
`Harness.audit_execution()` independently checks that receipt against native
logs. `PUBLIC_REQUEST.json` is controller-owned. Harness-specific filenames and
skill directories stay inside the adapter. The attempt controller rejects
over-budget, incompletely accounted or wrong-skill receipts before grading.
An alternate adapter test executes without any Hermes files. The existing
calibration CLI retains its older native audit; the task-world API uses the new
adapter contract.

To integrate another harness, implement `identity`, `unsupported`, `run` and
`audit_execution`, then pass the adapter to `prepare_study` and `execute_study`.
Pass its offline auditor to `audit`. A learner supplies `identity` and `update`;
the replay callback remains controller-owned. Native Fluso runtime, isolation,
physical-call accounting and skill-loading evidence must be qualified before
labeling that adapter operational.

Set `max_parallel_employees` in the world specification to run bounded waves of
independent employees. Each employee's sessions remain ordered; daily feedback
and learning wait for the day's work. The scheduler records all started peers if
one fails, retains the wave reservation and stops further dispatch. It never
retries a failed attempt or chooses work according to completion speed. The
frozen `development-world-v2` study at `6602bd1` uses the earlier serial runner;
later adapter and parallel-dispatch changes do not alter its execution checkout.

Native parallel qualification at `3efaa9f` completed on H200: two simultaneous
fresh profiles, both offline audits passed, 20 physical calls and 124,311 tokens.
The frozen plan hash is
`2c085718906eaebc82c56ddc04be44b43bf451f7576b6c1aa866cea0468d77a2`.
Run the reusable qualification with `python -m worldlab.qualify_harness`, passing
`--bank`, `--out`, `--hermes-root`, a development `--task-id` and `--parallel 2`.
This verifies the adapter and metering at that concurrency, not the learning
effect or high-concurrency server capacity.

## Native H200 calibration

The first eligible package slice was chosen by task identity before model calls:
research editing and facilities reconciliation, two fresh executions each, seed
20260915, 32 calls / 8,192 output tokens / 500,000 reserved total tokens / 1,200
seconds per attempt. The combined reservation ceiling is two million tokens.
These are development tasks and dependent repeats, not final test worlds.

The controller uses `/home/inference-testing/benchmarks/eurobench-v1/.venv/bin/python`;
Hermes uses its own pinned environment. The original grader package is separately
hashed at `/home/inference-testing/apps/worldlab-eurobench-331d85b`.

```bash
python -m worldlab prepare --bank BANK --spec configs/worldlab/calibration_h200_v1.json \
  --out OUT --hermes-root HERMES --eurobench-package EUROBENCH
python -m worldlab execute --bank BANK --out OUT \
  --hermes-root HERMES --eurobench-package EUROBENCH
python -m worldlab audit --bank BANK --out OUT --eurobench-package EUROBENCH
```

Preparation makes no model calls and binds source hashes, provider, grader,
task bank, fixed skill, order and budgets. Execution is single-use. Behavioral
failures remain in the results. Infrastructure ambiguity preserves the in-flight
marker, charges an unresolved reservation and stops further dispatch; it never
automatically replays the attempt. The auditor rehashes evidence and reruns the
original mechanical checks. Unsupported and missing slots remain in the report.

The first run, `task-calibration-h200-v1`, exposed harness-generated
`trajectory_samples.jsonl` files in employee workspaces. All four attempts are
preserved with `INVALIDATION.json`; they are not valid employee-performance
evidence. Commit `6487c39` moved the host working directory outside the workspace
and excluded generated Python deliverables from the execution-source inventory.
`task-calibration-h200-v2` completed the same four preselected cases after these
infrastructure corrections. Original mechanical regrading passed its audit. Both
research-editing attempts passed mechanics; both facilities attempts failed them.
All four loaded the exact seed skill, preserved inputs and had no unauthorized
workspace files. The run used 42 physical calls and 642,834 tokens with complete
accounting. Full qualitative judging of all four calibration attempts has not
been executed; the separate judge controls above cover one artifact and its
deliberately incomplete copy.

The invalid first run also consumed 49 calls and 862,695 tokens. Across both
calibration runs, the recorded cost is **91 physical calls and 1,505,529 tokens**.
Those infrastructure costs are retained, not hidden in the corrected-run total.
See [the verified aggregate receipt](h200-task-calibration-v2-summary.json).

The facilities task exposed a separate source-contract concern: its public CSV
brief requests a `justification` column, but the original SQL comparison omits
that column and rejects it as extra. Both outputs hit that check; additional
report checks also failed. The original grader is preserved. This task needs
contract review before interpreting failures as skill-addressable errors or
using its score as a learning reward. No expected answers or checks were altered.

Remote frozen checkouts `Big-World-CL-lab-frozen-v1` and
`Big-World-CL-lab-frozen-v2` preserve each run's execution source for re-auditing.
Run the matching version's auditor with the absolute artifact path; subsequent
development commits intentionally have different source identities.

## Remaining path to the final study

The final objective requires rich employee/world generation using this partial
calibration, long-lived work and consequences, scalable sessions, harness/learner
adapters, calibrated grading and prospectively frozen independent world pairs.
The current task-world runner is a working development component of that system.

Statistical inference must use independent world pairs, not thousands of
dependent sessions or repetitions of the 329 sourced tasks. Freeze the primary
contrast, task-generation version, minimum meaningful effect, budgets and sample
size before final outcomes. Estimate world-pair variability in development;
one pilot pair cannot estimate it. Paired power calculations use the variation
of paired differences ([Statsmodels documentation](https://www.statsmodels.org/stable/_modules/statsmodels/stats/power.html)).
Any paired permutation analysis additionally needs its exchangeability or
random-assignment assumptions to hold ([SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html)).

A positive score difference with no adopted skill is not evidence of successful
learning. The completed H200 integration pair illustrates that: SkillOpt made
two consolidation epochs and six target replays, spent 686,487 learning tokens,
and adopted no change. Its 43 work attempts versus the control's 42 attempts
produced different outcomes, but both deployed the same seed skill. Both audits
passed. This result establishes execution, accounting and stochastic variation;
it does not meet the requested learning or significance objective.


## Optional native employee workplace

Pass `--mirofish-backend BACKEND --persona-cache CACHE` and
`--mirofish-service-url http://127.0.0.1:5001` to both `worldlab.run_worlds prepare` and `execute`.
The explicit native provider environment must match the frozen model/base URL;
see the H200 runbook. The backend directory is independent of the frozen controller
checkout, so no copied or changed MiroFish source is needed in each worktree.

`EmployeeFactory` freezes persona context and opens a new persistent driver for
each arm. `EmployeeDriver` receives an exact released view, returns an auditable
decision, reports interview costs and closes its own native environment. The
current adapter uses actual pinned Persona 8B profiles in MiroFish/OASIS.
Swapping the work harness or learner does not require changing this driver.

`workplace` parameters in the specification control `max_attempts` (default 2),
`retry_delay` (1 day), `grace_days` (2), `settlement_delay` (1),
`work_cost_units` (1) and `completion_value_units` (10). Employee
`sessions_per_day` is available daily capacity. `arrivals_per_day` independently
sets new obligations per day, defaulting to that capacity for older specs. Both
are integers from 1 to 64. Independent arrival/capacity settings require the native
workplace mode. Work arrives on the frozen role/calibration schedule. A failure can occupy later capacity through rework;
a deferral leaves the obligation pending and consumes that day's opportunity.
The observation window then drains feedback and payments without extra work.
Work and actor reservations cover all capacity slots, including rework, even when
there are fewer new obligations. `planned_obligations` counts incoming work;
the preparation result's `planned_work_sessions` is the maximum delegation count.
`configs/worldlab/development_workplace_v1.json` declares two colleagues, one new
task per employee/day, two daily work slots, a two-day deadline, delayed feedback
and a fixed day-six learning opportunity. This is an integration protocol, not a
sample-size justification or a final significance study.

Native decisions retain private working notes and can send one message to a
listed colleague in the same department. Messages and grade feedback arrive
later. Actors cannot see future task briefs, hidden grading evidence or another
employee's private files. Original task requirements remain in each solver
request; the actor's request is recorded separately and reused unchanged during
learning replays. The grader still uses the original task's rubric and brief.

The offline audit reconstructs every causal command, regenerates visible views,
checks native interview receipts and binds outcomes to actual task artifacts.
All planned probes remain in the denominator. The primary workplace metric is
on-time accepted work; soft quality and configured synthetic utility are secondary.
Bootstrap/social model costs remain unmetered and explicitly unknown. There is
still no operational Fluso adapter, multiturn employee channel, qualified JobBench
document solver, human-calibrated judge or completed final significance study.


The judge keeps original r3 criterion bytes. Its registered exact-reference-count
predicate checks the full criterion definition and original source count before
handling that criterion without a model call. It records match offsets and is
recomputed by the offline auditor. Other criteria remain model judged, using a
finite ASCII response grammar; these judgments still need independent semantic
calibration. Deterministic control passes are never reported as model accuracy.


Native employee mode now seeds the declared employee/department graph directly
through MiroFish's local graph implementation, with native episode storage,
validation and API readbacks. No task or feedback content enters that initial
graph. The old social-media ontology generator is not needed for known simulator
assignments. Automatic graph-memory extraction is disabled in this mode; native
interview history, employee notes and delayed messages still persist. The two-role
native qualification passed; full workplace learning remains to be demonstrated.

For long nonstreaming tool responses, the Hermes adapter configures both native
request and stale-response windows to the lesser of 600 seconds and the whole
attempt budget. It verifies the effective values before dispatch and audits their
saved readbacks. No transport retry or increase in total calls/tokens is implied.

## Cross-checking evaluator coverage

`python -m worldlab.mechanical_diagnostic run --bank BANK --eurobench-root PACKAGE
--roots STUDY_OR_QUALIFICATION ... --out FRESH_OUT` snapshots all available attempt
receipts, verifies their original files and then runs the original EuroBench
mechanics without model calls. The output must be outside every source root.
The `audit` subcommand reruns these checks against the frozen snapshot; later
attempts from a live source do not enter it. On H200 this diagnostic needs
`/home/inference-testing/benchmarks/eurobench-v1/.venv/bin/python`, which contains
the original evaluator's document dependencies.

Mechanical disagreement is not automatically a qualitative false positive.
Original exact-match checks can conflict with the source-corrected r3 contract,
including optional benefits and translated labels. Conversely, the current r3
reward can miss quantitative errors outside its criterion coverage. Full-task
success must eventually cover both valid structural/numerical obligations and
source-grounded qualitative requirements. Neither score alone currently proves it.

`worldlab.qualify_semantics` freezes source-grounded positive and negative controls
before calling the production judge. Its first suite has 11 cases, three repeats
each, over one English benefits-synthesis family. It checks optional content,
semantic paraphrases, threshold direction, invented guarantees, exact headings
and appendix ordering. These are constructed evaluator controls, never solver
performance or employee training data; passing them does not establish general
professional-quality calibration.
