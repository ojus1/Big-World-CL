# Executable work-quality rubrics

The deployment-time learning benchmark needs evidence that an employee performed
useful work, in addition to following the enterprise's submission procedure.
`lifespan/evaluation/tasks.py` generates three deterministic filesystem task
families and evaluates their deliverables without an LLM judge. All data is
synthetic. These are bounded work simulations, not validated models of actual
accounting practice or production incident response.

Each case has two distinct boundaries:

1. **Work quality:** Did the submitted calculations, transformations, diagnoses,
   and repairs satisfy the task's input-derived specification?
2. **Enterprise authorization:** Did the employee use the applicable channel,
   endpoint, redaction, checks, and approval?

The existing workplace environment owns the second boundary. The runner must
require both boundaries to pass **before** committing work, changing business
state, or scheduling payment. A positive work-quality score alone must never
settle a task.

## Interface and visibility

```python
case = make_case(
    workflow="renewal", seed=24, day=15, task_id="renewal-24",
    regime="exception", split="online", exception_window=(12, 18),
)
result = grade_case(case, submitted_artifact)
```

The generated case is JSON serializable and contains:

| Field | Visibility and purpose |
|---|---|
| `id`, `workflow`, `day` | Public task identity and current simulated date. |
| `regime`, `split` | Evaluator scenario metadata; do not use these labels as employee hints. |
| `public_files` | Mapping of safe relative paths to UTF-8 text. Materialize these under the employee workspace. |
| `request` | Employee instruction pointing to the inputs and published specification. |
| `private` | Evaluator-only expected results, executable replay inputs, and rubric version. Never copy to the worker, optimizer, skill prompts, or employee filesystem. |

Inputs are under `tasks/<task_id>/`. Task IDs must be safe filename components:
ASCII letters, digits, underscores, hyphens, and periods, starting with a letter
or digit and at most 96 characters. Neither absolute paths nor parent traversal
are accepted. All service URLs use the reserved `.invalid` domain.

The artifact has exactly the existing five envelope fields:

```json
{
  "task_id": "renewal-24",
  "channel": "the-current-workplace-channel",
  "redact": false,
  "endpoint": "the-current-workplace-endpoint",
  "content": "a JSON string encoding the documented work output object"
}
```

Each public `specification.json` defines the work output schema and calculation
rules. These are legitimate operating instructions, not solved examples or
expected answers. Numeric outputs use integer cents, counts, or milliseconds.
The grader rejects duplicate JSON keys, duplicate or unknown record IDs, omitted
records, additional fields, booleans as numbers, floats, nonfinite values,
unbounded integers, and oversized output. Output list ordering is immaterial.
Incident output also forbids endpoints not supplied in the task.

`grade_case` returns `success`, a score in `[0, 1]`, named boolean `checks`, and
`feedback`. Format or coverage failures score zero. Otherwise correctly completed
components earn partial credit; **success requires every component to pass**.
The function is pure: grading never mutates the case or executes submitted code.

The returned feedback identifies failed categories, for example `tax_cents` or
`minimal_compliant_repairs`. It does not supply corrected numbers, expected
answers, private policy, or future outcomes. A benchmark may expose this feedback
as the simulated business tool's response, but must apply the same visibility and
attempt budget to every baseline. Delayed business rewards become optimizer
experience only when the runner releases them at their simulated time. Private
rubric truth remains inaccessible even after failure.

## Onboarding: reconcile account activity and decide activation

**Files:** `accounts.csv`, `ledger.csv`, `policy.json`, `specification.json`.

The employee reconciles signed posted activity with each account's opening
balance. Pending activity is excluded and duplicate event IDs count once. The
employee then applies the activation floor appropriate to the account's segment,
region, and the policy's effective date. Held-out cases add reversal events whose
references negate earlier postings; their interpretation is documented in that
case's public specification.

**Output:** every account's ID, reconciled balance in cents, and `activate` or
`hold`, plus an aggregate balance.

| Component | Weight | Executable check |
|---|---:|---|
| Reconciled balances | 45% | Fraction of accounts with the input-derived balance. |
| Scoped activation decisions | 35% | Fraction with the correct decision under the applicable threshold. |
| Aggregate balance | 20% | Exact sum of the required account balances. |

Fixtures include positive and negative balances, duplicate export rows, pending
transactions, regulated domestic accounts, and regulated cross-border accounts.
Consequently, summing all ledger rows or applying an exception to every regulated
account fails independently of submission formatting.

## Renewal: calculate contract charges from usage and terms

**Files:** `contracts.csv`, `usage.csv`, `policy.json`, `specification.json`.

The employee aggregates final usage, excluding forecasts. They calculate seat
fees, term-eligible discounts, usage overage, subtotal, tax, and total. All rounding
is explicit: nonnegative fractional cents round half up. Discounts apply to seat
fees only; tax applies after discount and overage. A six-month contract does not
receive an annual discount. Held-out cases introduce a documented progressive
overage tariff in place of the flat tariff.

**Output:** a row per contract containing `used_units`, `seat_fee_cents`,
`discount_cents`, `overage_cents`, `subtotal_cents`, `tax_cents`, and `total_cents`,
plus `portfolio_total_cents`.

| Component | Weight | Executable check |
|---|---:|---|
| Seven per-contract fields | 80% total, equal weight | For each field, fraction of contracts with the exact input-derived value. |
| Portfolio total | 20% | Exact aggregate of required contract totals. |

Intermediate fields make a superficially plausible total insufficient. The score
exposes whether failures arise in usage aggregation, discount applicability,
rounding, or other billing stages. Success still requires all fields and totals.

## Incident: diagnose configuration drift and execute probe replay

**Files:** `services.json`, `probes.csv`, `observed_logs.csv`, `policy.json`,
`specification.json`.

The employee diagnoses differences between current configuration and service
requirements, produces repaired configurations, and reports the outcomes of
replaying supplied probes. Configuration has four bounded fields: endpoint,
schema version, timeout, and retry limit. The public specification gives exact
budget requirements, including scoped timeout margins. The current logs reflect
the existing faulty configuration; the employee must reason through additional
failures that could remain after the first visible failure is fixed.

The evaluator executes the documented request model against the **submitted**
configuration. It checks endpoint availability, schema compatibility, sufficient
retry count, and sufficient timeout in that order. Merely claiming that replay
passed cannot make it pass. Increasing every resource limit also fails the
minimal-compliant-configuration check. Held-out cases include cold-start probes
and different endpoint/schema versions.

**Output:** a repaired configuration and diagnosed field list for every service,
and a predicted outcome for every probe.

| Component | Weight | Executable check |
|---|---:|---|
| Diagnosed fields | 20% | Fraction of services whose diagnosis identifies exactly the mismatched fields. |
| Minimal compliant repairs | 40% | Fraction of configuration fields matching the input-derived minimum compliant setting. |
| Executed replay passes | 30% | Fraction of actual evaluator replays that pass with the submitted configuration. |
| Replay report accuracy | 10% | Fraction of reported outcomes matching actual replay outcomes. |

This is an executable deterministic service model, not a launched production
service, arbitrary program repair benchmark, or proof that files outside the
submitted artifact were correctly modified. The runner may persist accepted
configurations as work products. Evaluating actual repository patches, deployed
services, or filesystem mutations would require additional task-specific tests
and state transitions.

## Policy changes, scope, and expiry

All workflows support `base`, `changed`, `exception`, and `reversal`; `change` is
an alias for `changed`. The scenario runner chooses phases and timing. The
generator does not choose an algorithm-dependent schedule.

| Rule | Base / reversal | Changed | Active domestic exception |
|---|---|---|---|
| Regulated onboarding activation floor | 0 cents | 1200 cents | 0 cents |
| Regulated annual renewal discount | 500 basis points | 0 basis points | 1500 basis points |
| Sensitive incident timeout margin | 100 ms | 200 ms | 100 ms |

Commercial activation remains 0 cents, commercial annual discount remains 1000
basis points, and standard incident margin remains 100 ms. The temporary
exception affects only domestic regulated/sensitive records. Cross-border
records retain the changed requirements.

`exception_window=(start, end)` is half open: valid on `start`, expired on `end`.
Outside the window, the `exception` regime uses the changed rule. The exception
is published two days before its effective date, bounded below by day zero.
Before publication, its dates and details are absent from public files. An
announcement does not change current applicability. After expiry, the historical
notice remains visible but inactive. `reversal` explicitly withdraws the changed
requirements and returns to the base rules.

The input RNG is derived from workflow, seed, task ID, and split, **excluding day
and regime**. This permits controlled paired probes with the same work inputs
under different rules. For fresh work, use fresh task IDs or seeds. Never compare
an old answer to a new policy and call that a historical retention failure:
historical validation replays the original case and original policy, while
prospective adaptation is measured on newly released current work.

## Splits and the limits of this task bank

`online`, `train`, and `validation` use the development mechanisms with disjoint
deterministic input streams. `test` and `heldout` add the mechanisms described
above. Split and regime labels are absent from the employee request. The held-out
mechanism's legitimate operating specification is available when its task is
released; it is not a hidden rule the employee must guess.

A split label alone does not establish a valid experiment. The runner must use
disjoint world/task seeds, keep test outcomes out of candidate selection and
prompt tuning, record the release time of every observation, and limit repeated
feedback queries. Source code for this task bank is public, so publication does
not provide protection against benchmark-specific hand tuning. Keep fresh final
seeds and preferably additional mechanisms outside development.

These rubrics establish verifiable competence on three small work families.
They do not establish economic realism, broad job performance, or superiority of
any learning method. In particular:

- Published instructions can be followed afresh by a strong frozen agent. That is
  an appropriate baseline, not a defect to hide by withholding instructions.
- The input bank currently has four accounts/contracts and three services per
  case, with fixed policy dimensions and hand-designed changes.
- Reusable skill creation, retrieval, revision, retirement, and cost must be
  measured by the harness; the grader cannot infer that a skill caused success.
- Cross-employee collaboration, customer utility, and competitor reactions need
  separate world-level outcomes. They cannot be inferred from these local scores.
- Task generation is deterministic; native Hermes/model execution can still be
  stochastic. Report paired world seeds, budgets, repeats, and uncertainty.

## Verification

```bash
python3 -m unittest lifespan.tests.test_evaluation_tasks -q
```

The tests include independent public-input solvers for 300 workflow/regime/split/
seed combinations, cent rounding checks, scope and exclusive-expiry boundaries,
rollback recovery, announced-but-not-effective rules, duplicate/pending ledger
handling, executed incident replay, minimal resource budgets, strict artifact
validation, feedback non-disclosure, deterministic generation, and grader purity.
They make no network or model calls.

## Prospective metrics and paired inference

`lifespan/evaluation/metrics.py` builds a report from one ecosystem's released
work sessions, learning-update receipts, final world snapshot, configuration,
scenario, and treatment-independent provenance. Candidate replay scores never
enter prospective success metrics.

The v1 local execution denominator is **every task available before the exclusive
work horizon**, including unattempted, pending, and abandoned available tasks.
`Task.created` records availability, not when the enterprise accepted the order.
Use the corrected v2 commitment headline below for business fulfillment.
Retries are separate execution attempts against the same obligation. Reports
therefore distinguish obligation completion rate, attempt success rate, number
of retry attempts, and mean partial work-quality score. Employee and regime
exposure tables include employees with no sessions. Skill-loading and budget-
exhaustion rates describe behavior; failing to load a skill or using the entire
per-session budget is not, by itself, an infrastructure failure.

Completion evidence must reconcile. A completed obligation needs exactly one
successful audited session on its recorded completion day and one ledger entry.
Success against an uncompleted world task, multiple successful completion records,
missing or duplicate settlements, and overdue undelivered settlements invalidate
paired inference. Invalid attempts remain in descriptive counts rather than
silently disappearing from the denominator.

The action horizon ends at `config.days`. Observation continues for the configured
fixed settlement delay, with no new work attempts. `scenario.settlement_delay`
specifies this drain (default two days, matching the PoC world); an explicit
`config.settlement_delay` takes precedence. The report distinguishes completed
work, pending obligations, settled rewards, unsettled rewards, and right-censored
outcomes. Realized business utility is the actual observed world balance in
**synthetic business units**, not USD. Unsettled rewards are not added to it.

Adaptation is reported as a descriptive event sequence: first recorded exposure
to a changed task regime through first subsequent strict success in that regime.
Task exposure is a proxy for observability, not proof that the employee read the
policy. An unsuccessful sequence is right-censored at the next observed regime,
actual early stop, or exclusive work horizon. Censored cases remain visible; the
report does not average only the successfully adapted cases or interpret this
delay as a causal effect of learning.

Execution and learning costs have separate receipts. Recorded totals, missing
receipt counts, actual measured totals, and charged token reservations are
distinct. An unresolved reservation is not represented as measured usage. Missing
provider currency estimates remain `null`, not zero. Actor/environment model
tokens and currency cost are explicitly unknown until separate actor accounting
is implemented, so the report does not claim an all-in dollar cost or dollar-
normalized utility.

`paired_report` compares `skillopt` minus `no_learning` only when both completed
trials share scenario split, seed, state mode, all other shared configuration,
observation window, and identical nonempty provenance. The runner must populate
the complete provenance contract: executor model/settings, source and task/harness
hashes, Hermes/SkillOpt/MiroFish versions, persona cohort hashes, and actor policy
configuration. Credentials and treatment-specific learned artifacts do not belong
in that contract. Missing or incompatible provenance, failed trial audits,
ambiguous duplicate runs, and incomplete pairs are reported explicitly.

Each eligible **whole-world pair** contributes one equally weighted difference.
The deterministic percentile bootstrap resamples those world-pair differences,
never correlated employee sessions. A single world pair is descriptive and has no
confidence interval. For two or more pairs the report gives a 95% interval and
the number of contributing world pairs for each metric; small samples remain
unstable. Metrics with unknown values retain explicit missing-pair counts. These
intervals do not cover repeated test-set tuning, source/model changes, task-bank
bias, or unmeasured environment costs.

```bash
python3 -m unittest lifespan.tests.test_evaluation_metrics -q
```

Synthetic reporting tests cover retries, unserved work, partial outcomes, scope
exposure, censoring, delayed settlement, missing receipts and reservations,
completion/ledger reconciliation, model/source provenance, incompatible budgets,
incomplete trials, and correlated sessions within independent world pairs.

## Canonical v2 headline: accepted commitments and fulfillment

During the first native pilot, a reporting defect became visible: supply-delayed
orders accepted before the action horizon could become actionable only during the
settlement drain. The frozen v1 `obligations.created_before_horizon` field excluded
those commitments. Its conditional execution rate is useful, but calling it total
business fulfillment would hide accepted, unserved work.

`REPORT.v2.json` is the canonical business report. It preserves the full original
report under `legacy_actionable_report` and gives raw SHA256 hashes of the unchanged
`REPORT.json`, checkpoint, and versioned postprocessor. Neither native execution,
the work grader, nor historical rewards are changed by this correction.

The corrected headline divides commitments fulfilled during the action horizon
by **all orders accepted before that horizon**, including initial conditions at
day -1. Placement comes from consumer ordered history and `order_placed` events;
availability comes from the scheduled task. Scheduled and materialized copies
share one `(firm, task_id)` identity. Materialized status overrides the original
pending scheduled template. A commitment still scheduled beyond the observation
horizon remains in the denominator and is explicitly right-censored.

The report separates:

- Accepted commitments, fulfilled work, and all unfulfilled commitments.
- Work available but unfinished at the action horizon.
- Commitments awaiting availability when work execution ends.
- Arrivals during the outcome-only observation window.
- Orders still scheduled beyond observation, and all pending commitments.
- Initial/benchmark demand and endogenous native consumer purchases or switches.

Source classification follows causal event links. It does not infer the source
from a task ID. The fixed initial-plus-benchmark fulfillment rate is reported
separately because native demand can change in response to either arm's outcomes.
Completion evidence must refer to the same accepted obligation, and source,
placement, availability, completion, and denominator partitions must reconcile.

For the first eight-day pilot, the correction gives no-learning Hermes **36/48
commitments fulfilled (75.0%)**, with 12 pending; its v1 rate was 36/45 available
tasks (80.0%) with only nine of those pending commitments visible. Three accepted
orders arrived during the drain. SkillOpt fulfilled **33/49 commitments (67.35%)**,
with 16 pending. Its fixed initial/benchmark result was 32/48; one additional native
consumer order was fulfilled. This is one descriptive world pair, not evidence of
a statistically established advantage for either method.

New completed runs generate v2 automatically after writing v1. To correct a
historical completed run explicitly, first run the strict native directory audit,
then generate the versioned report:

```bash
python3 scripts/audit_evaluation.py PATH_TO_RUN --strict
python3 scripts/evaluation_report_v2.py PATH_TO_RUN
python3 scripts/compare_evaluations.py \
  PATH_TO_NO_LEARNING/REPORT.v2.json PATH_TO_SKILLOPT/REPORT.v2.json \
  --out corrected-comparison.json
```

The postprocessor refuses incomplete or in-flight runs and invalid correction
audits. It never overwrites v1; rerunning identical correction inputs is idempotent,
while different inputs or implementation hashes require a new preserved version.
Comparison verifies source-file hashes and regenerates each correction, checks
matching postprocessor implementations, then applies the frozen configuration,
provenance, and whole-world pairing controls. Original v1 pairing remains nested
and explicitly labeled as legacy. Comparing v1 alone requires the intentional
`--legacy-actionable` flag. Report consistency checks do not substitute for the
strict native directory audit.

```bash
python3 -m unittest discover -s tests -p test_evaluation_report_v2.py -q
```
