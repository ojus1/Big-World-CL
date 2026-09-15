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

The historical native pilot using `workplace_history` did not establish the
context isolation required by item 3. A source-bound audit of its first update found that
all four selected training requests were produced from employee views containing
released validation feedback. Nine exposures to prior validation outcomes
occurred across those views, all from families used by the current gate. The
employee's request is retained in the training prompt and replay. This establishes
an information path, not proof that the optimizer used that feedback or that it
affected a skill. Task-family separation and delayed-feedback checks alone cannot
certify an independent gate. Treat the current native gates as development
selection; a future confirmatory protocol needs an evaluation context with no
path into training employee memory, requests, colleague messages or reflection.
Those historical studies retain their original source and budgets. Their original
auditors do not test this semantic separation.

The current development scale configuration uses
`validation_context: isolated_public_tasks_v1`. This
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

Before interpreting a large session count, inspect the prepared workload with
`scripts/report_worldlab_design.py --study STUDY --bank BANK`. This read-only
report binds the prepared study and bank, counts distinct tasks and connected
lineages, separates arriving obligations from isolated gate descriptors, and
checks whether scheduled feedback could supply each learning round. It never
loads execution outcomes. Scheduled supply assumes immediate successful work;
it does not establish actual eligibility, adoptions, completed sessions or power.

`scripts/report_worldlab_readiness.py` inspects the separate execution side:
captured published sessions, their receipt hashes, released feedback, distinct
training lineages and the frozen controller's actual selection. It reports
observed learner employees eligible at the current recorded day and those with
sufficient already completed work for the next update after scheduled feedback
release. It never assumes future work succeeds, counts unstarted arms as zero
results, or turns eligibility into an adoption claim.

The frozen `native-workplace-compact-v4` design has 1,152 training arrivals and
288 probe arrivals per arm across its six worlds. Those probe arrivals reuse
12 tasks from nine connected lineages. All 18 English research employee/world
instances have only one probe lineage each. Training uses 20 tasks from 17
lineages, and the isolated gate catalogs contain 144 descriptors drawn from
12 tasks and nine lineages. All 216 planned updates have sufficient hypothetical
scheduled supply. These are corpus-conditional development observations; neither
repetition nor additional world seeds broadens the task-family coverage itself.
The failed and stopped study remains unchanged. A final protocol needs enough probe
coverage within each intended role to support its declared transfer claim.

A September 15 catalog-only review of the reserved Internal EuroBench candidates
found 216 instances in 120 connected groups, with no recorded development
overlap after joining family, lineage and translation links. The catalog matches
the development bank's source metadata and repository commit
`331d85b67b4e990abc2f7d52c8498dd3b2d8ddf2`. It lists 48 instances each in German,
Spanish, French and Italian, and 24 in English. All 216 are marked uncertified
with independent vetting pending; their source mechanical-pass flags are not
independent validation. All are model-authored originals or bridge translations.
No reserved task bodies, rubrics, answers or historical outcomes were loaded for
this review, and no test inference was dispatched. Metadata separation alone
does not prove semantic independence or evaluator validity. The review artifact
is `lifespan/artifacts/final-source-metadata-v1/REPORT.json` in the local lab;
catalog SHA `52adb5793c7d3f9c137baa87866d2df8cd944161b45fe23a4a8125359d4202a3`.

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
p-value does not erase that uncertainty. The frozen version-5 study retains its original analysis implementation and
20-pair limit. New analysis preparations use integer-lattice dynamic programming
with exact multiplicities, avoiding repeated rational arithmetic and allowing
larger planned pair counts. The test statistic, two-sided tail including ties,
equal world weights and assumptions are unchanged.

`--max-exact-states` sets a preparation-time computational budget (default
100,000 reachable subset sums). Preparation checks a conservative bound from
the planned probe denominators before any outcomes exist. With 128 world pairs
and 48 probes per arm, the bound is 6,145 states. If the bound or runtime budget
is exceeded, analysis stops without substituting a random approximation or
selecting fewer pairs. Integer tail and total assignment counts remain exact;
an unrepresentably small floating-point p-value is reported as null with an
underflow flag, never as zero probability. These are computational capabilities,
not sample-size recommendations or evidence of power. A confirmatory run still
requires a separately frozen analysis, justified assignment/independence,
qualified final scoring and a prospective power calculation.

## Outcome-free power sensitivity

`scripts/plan_worldlab_power.py` supplies a separate planning step. Install
`requirements-worldlab-planning.txt` in an isolated environment, then run:

```bash
python scripts/plan_worldlab_power.py \
  --config configs/worldlab/power_scenarios_v1.json \
  --out /path/to/fresh-power-scenarios
```

The configuration declares absolute useful effects, the standard deviation of
the **paired world differences**, alpha, target power and a search limit. The
planner reads no execution outcomes. It preserves exact configuration bytes,
its reproduction source, numerical-library versions and checksums. None of
these inputs supplies a final sample size or changes a study's frozen analysis.
Assumptions have to be recorded explicitly; the example configuration contains
constructed scenarios, not estimates from the ongoing six-pair development run.

The paired-t calculation uses a two-sided alpha critical value and targets the
probability of rejection in the positive direction. It uses `n-1` degrees of
freedom and `sqrt(n) * effect / paired_SD` noncentrality, following the
[paired-t power convention](https://www.statsmodels.org/stable/generated/statsmodels.stats.power.TTestPower.power.html)
and [SciPy's noncentral t distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html).
The resulting integer N must meet the target while N-1 does not. A limit that is
too small produces an explicit unsatisfied scenario, not a selected smaller N.

At two-sided alpha 0.05 and target positive-rejection power 0.80, the constructed
normal-theory scenarios give these counts of independent world pairs:

| True improvement | Paired SD 5 points | Paired SD 10 points | Paired SD 20 points |
| --- | ---: | ---: | ---: |
| 2.5 percentage points | 34 | 128 | 505 |
| 5 percentage points | 10 | 34 | 128 |
| 10 percentage points | 5 | 10 | 34 |

These calculations assume independent, identically distributed normal world
differences. Bounded workplace fractions are not exactly normal, so this is a
planning sensitivity model that needs validation against the eventual design.
It does **not** calculate power for the existing sign-flip diagnostic, justify
changing the current analysis, or prove that a bank provides broad transfer
coverage. Detecting a positive effect against zero when the true effect is five
points is also different from proving that the effect exceeds five points.

For comparison the planner computes a distribution-free sufficient sample size
for a positive lower endpoint of the existing two-sided Hoeffding interval. For
independent differences in `[-1,1]`, radius `r=sqrt(2 log(2/alpha)/n)` and expected
mean at least `delta > r`, the power lower bound is
`1-exp(-n*(delta-r)^2/2)`. This follows the same bounded-sum inequality used above,
with no normality or variance assumption. At five points and 80% power, the
sufficient count is **8,138 pairs**; at ten points it is **2,035**. These are
conservative sufficient counts, not necessary sample sizes or affordable launch
recommendations. The 2.5-point scenario exceeds the example's 20,000-pair limit.

Before selecting a final protocol, use complete, audited development evidence
to assess variability and distributional assumptions, define a useful effect,
and qualify the eventual test and evaluator. Then freeze the chosen method, N,
assignment scheme, final bank and failure policy before final outcomes. Do not
calculate observed power from a final effect or add seeds until a desired
p-value appears. The current study, its six seeds and its analysis stay frozen.

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

Native employee interview costs are metered. Historical studies retain their
original unknown bootstrap/social usage. A separate two-employee native
qualification at `bafac6f` verifies optional simulation-bound social receipts for
future runs, without double-counting interviews; other bootstrap providers are
outside that receipt scope. The large native study, an audited
nontrivial skill adoption followed by later deployment, and a statistically
supported learning effect remain to be demonstrated. Harness/learner factories
permit new implementations; a production Fluso adapter is not yet supplied.
