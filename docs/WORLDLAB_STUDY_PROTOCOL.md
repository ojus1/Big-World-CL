# Progression to a defensible continual-learning study

The goal remains a realistic, diverse workplace experiment with many sessions
and a statistically supported skill-learning effect. A working adapter, a
changed skill file, a passing rubric control, or a positive single-world delta
does not establish that result. A null or negative result must remain visible.

## Development scale configuration

`configs/worldlab/development_workplace_scale_v1.json` expands 12 employees in
three departments and three working languages over 20 simulated days. It gives
each employee one arriving obligation and two work opportunities per day, so
rework competes for real capacity. Feedback, deadlines, colleague messages and
skill deployment retain the native workplace timing rules.

Use the existing one-employee overlay
`configs/worldlab/development_coverage_examples_v1.json`. The simulator supplies
all other employee profiles. One employee has direct examples, two same-role
colleagues may inherit the recorded task-mixture assumption, and nine use
defaults. These are synthetic assignments, not observed workforce prevalence.

The development seed list is fixed as `401 409 419 421 431 433` before execution.
Each pair plans 480 arriving obligations across its two arms, with at most 960
work attempts including rework, and 36 possible learner updates. Six pairs
therefore plan 2,880 obligations, at most 5,760 work attempts and 216 possible
updates. Actual updates depend on having enough released, distinct experiences;
zero proposals or adoptions remain legitimate outcomes. These counts are plans,
not completed sessions or evidence of adequate statistical power.

The smaller ten-day pair remains an integration step to verify native employee
state, delayed feedback, consolidation and deployment together. It cannot
substitute for the scale study. Preparation of either study does not authorize
combining its outcomes with historical runs using different grading contracts.

## Evidence required for learning

1. Freeze workload generation, role/language assignments, sparse calibration,
   model/server configuration, harness, learner, evaluator and budgets before
   dispatch. Keep all attempted seeds, including infrastructure failures.
2. Compare the learner with the unchanged seed-skill control on matched worlds.
   Isolate state between arms; preserve the same model and task distribution.
   Current execution counterbalances arm order across world indices.
3. Learn only from released pre-probe experience. Keep connected task families
   and translations in one split. Validation gates must remain disjoint from
   reflection data; future probe feedback cannot affect an update.
4. Verify proposed edits, the held-out adoption gate, the resulting skill bytes
   and native skill reads on later work. Report proposals, rejected edits,
   adoptions and unchanged-skill comparisons separately.
5. Count every planned probe obligation in on-time acceptance, including
   deferrals and unattempted work. Report rework, late completion, employee
   decisions, inference failures and all measured/reserved costs separately.
6. Audit the complete paired execution before interpreting its effect. A
   successful audit establishes provenance and arithmetic, not judge truth.

The current frozen native workplace does not establish the context isolation
required by item 3. A source-bound audit of the pilot's first update found that
all four selected training requests were produced from employee views containing
released validation feedback. Nine exposures to prior validation outcomes
occurred across those views, all from families used by the current gate. The
employee's request is retained in the training prompt and replay. This establishes
an information path, not proof that the optimizer used that feedback or that it
affected a skill. Task-family separation and delayed-feedback checks alone cannot
certify an independent gate. Treat the current native gates as development
selection; a future confirmatory protocol needs an evaluation context with no
path into training employee memory, requests, colleague messages or reflection.
The running studies retain their original source and budgets. Their original
auditors do not test this semantic separation.

New configurations can use `validation_context: isolated_public_tasks_v1`. This
selects a prospective gate catalog from the validation partition and removes
validation tasks from live arrivals. The employee adapter sees no gate catalog;
the learner replays original public gate instructions in separate workspaces
without employee requests or prior observed grades. Original training feedback
still drives workplace memory and social messages. Gate replays consume the
existing learner budget, and their results never enter workplace state. They
remain adaptive development selection data across successive updates. Fixture
and native-algorithm canary tests cover this routing; a fresh native study and
complete audit are still required before claiming it works in live experiments.

## Statistical boundary

The primary workplace metric is the paired difference in the fraction of
planned post-learning probe obligations accepted on time. Sessions and
employees within a world interact and are not independent statistical units.
Use the world pair as the unit; do not inflate sample size with repeated tasks,
translations, replays, multiple rubric criteria, or multiple calls.

Before a confirmatory run, use separate development data to estimate variability
and choose a fixed number of world pairs for a declared minimum useful effect,
test and error rate. Freeze that analysis before examining the final outcomes.
Report the paired effect and uncertainty, not only a p-value. Do not keep adding
seeds until significance appears or select which runs to include by their score.
Infrastructure failures need a prospective handling rule and separate cost
accounting; a partial study is not a completed confirmatory result.

The current bank is development/calibration-only. The compiler deliberately
rejects a final-study claim using it. The reserved internal test tasks have not
been used in these experiments. Confirmatory execution needs an independently
frozen final bank, qualified scoring coverage and a complete analysis protocol.

## Executable development analysis

`scripts/analyze_worldlab.py prepare` freezes a separate analysis artifact before
the first study dispatch. It binds the study bytes, complete seed list, analysis
code and the original source checkout used for offline auditing. Keep this
artifact outside the experiment directory. For example:

For configured adapters, pass the same `--harness-config`, `--learner-config`
and `--judge-config`
when preparing the analysis. Their bytes are frozen and the recorded original
auditor receives those configurations after execution. New analysis preparations
also retain `REPRODUCE.py`; run that copy to analyze the study if the repository
has changed. Previously frozen plans must use their preserved analysis source.

```bash
python3 scripts/analyze_worldlab.py prepare \
  --study /path/to/native-workplace-scale-v1 \
  --frozen-source /path/to/frozen-experiment-checkout \
  --python /path/to/controller/python \
  --out /path/to/native-workplace-scale-analysis-v1

python3 scripts/analyze_worldlab.py analyze \
  --bank /path/to/frozen-calibration-bank \
  --out /path/to/native-workplace-scale-analysis-v1
```

Analysis requires every planned pair to complete and pass the original frozen
audit. Missing or failed pairs do not become a smaller, more favorable sample.
The script rechecks the full planned probe denominator and weights each world
equally. It reports the mean difference, between-world standard deviation and
standard error, positive/zero/negative pair counts, adoptions, measured optimizer
calls and later sessions using adopted skill bytes. It preserves unknown usage.

For this small development study, the predeclared statistical diagnostic is an
exact two-sided sign-flip test of the paired mean, with all `2^n` assignments,
including ties. Rational arithmetic avoids floating-point tail ambiguity. This
requires independent differences with exchangeable signs under the null;
counterbalanced execution order does not establish random assignment. The
procedure is therefore an exploratory sensitivity diagnostic, never an automatic
confirmatory claim. See the [SciPy paired permutation documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html)
for the exchangeability requirement and sign-flip construction.

A separate conservative 95% interval for the expected mean uses the bounded
difference range `[-1, 1]`: radius `sqrt(2 log(40) / n)`, clipped to that range.
This follows [Hoeffding's bounded independent-sum inequality](https://www.tandfonline.com/doi/abs/10.1080/01621459.1963.10500830).
It needs independent world differences and is conditional on this simulator,
bank and evaluator. At six pairs it is necessarily wide; a small sign-flip
p-value does not erase that uncertainty. The exact implementation supports at
most 20 pairs. A larger confirmatory run requires a separately frozen analysis
and power calculation, not silently switching methods after observing results.

## Remaining requirements

Public numerical supplements currently cover reviewed omissions in two source
tasks. They preserve the corrected r3 criteria and accepted output alternatives,
but do not certify complete task coverage across the bank. Further source and
semantic validation is required before making full-task or general judge
accuracy claims. Same-model semantic judging remains a development limitation.

The separate `worldlab.editorial_diagnostic` checks a remaining calculation in
the pinned editorial training task: working days exclude Sundays and the five
specified holidays, while Saturdays remain included. It also checks the strict
`<10` flag against recomputed days. `run --bank BANK --root COMPLETED_ARM --out OUT`
selects every completed attempt of that task in the named arm; `audit --bank BANK
--out OUT` verifies the complete selection and reproduces the results. Eight
hand-checked calendar boundaries are retained with the diagnostic. This neither
changes historical grades nor certifies date selection, translator allocation,
risk argumentation, or the complete scheduling task.

Native employee interview costs are metered. The running studies retain their
original unknown bootstrap/social usage. A separate two-employee native
qualification at `bafac6f` verifies optional simulation-bound social receipts for
future runs, without double-counting interviews; other bootstrap providers are
outside that receipt scope. The large native study, an audited
nontrivial skill adoption followed by later deployment, and a statistically
supported learning effect remain to be demonstrated. Harness/learner factories
permit new implementations; a production Fluso adapter is not yet supplied.
