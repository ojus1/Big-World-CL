# Enterprise Lifespans

A research design and standard-library Python PoC for synthetic enterprises whose employees, work, and assistant relationships persist while operating procedures change.

Start with [the research design](docs/RESEARCH_DESIGN.md), which formalizes the problem, compares related work, sketches world generation and training, and defines the evaluation contract. [An actual generated lifespan](docs/EXAMPLE_LIFESPAN.md) shows employees, dated changes, and a matched work example. [Integration notes](docs/INTEGRATION.md) describe the planned MiroFish and LLM interfaces.

## Run

From the repository root:

```bash
python3 -m unittest discover -s lifespan/tests -v
python3 -m lifespan demo --out /tmp/lifespan-new-run --days 84 --enterprises 3 --seed 7
python3 -m lifespan demo --out /tmp/lifespan-static-run --days 84 --enterprises 3 --seed 7 --no-drift
```

Python 3.10+; tested with Python 3.12.3. No packages, network, credentials, LLM calls, or running MiroFish installation are required. Output directories must be empty to avoid replacing previous experiments. Simulated days are calendar days; the PoC does not model weekends.

The existing [drift demonstration](artifacts/demo/REPORT.md) and [stationary control](artifacts/stationary/REPORT.md) each cover three enterprise instances over 84 days. The five controllers share each scenario's exogenous demand and changes. Their actions can create different subsequent work, review requirements, and employee trust.

## What executes

- Six employee–assistant relationships per enterprise, across onboarding, renewal, and incident departments; each employee handles a customer segment.
- Persistent business tasks, actual performed checks, approval records, tool commits, delayed settlement, backlogs, abandonment, and onboarding-generated follow-ups.
- Time- and scope-dependent procedure changes: regulated-account reviews, interface migration, disclosure rules, temporary channels, rumors, reorganization, and rollback.
- Employee reading delays and stale beliefs; trust affects delegation and repeated failures can cause a new review procedure.
- Separate observable and privileged data, a JSON tool-call interface, deterministic generation, and an in-memory counterfactual fork.

The rule controllers are mechanism probes:

| Controller | Behavior |
|---|---|
| `frozen` | Reuses initial procedures. |
| `recency` | Applies received documents in publication order, ignoring authority, effective dates, scope, and expiration. This intentionally weak baseline is not representative of all retrieval systems. |
| `scoped` | Resolves received evidence by authority, effective interval, and scope. |
| `adaptive` | Uses scoped procedures; checks documents periodically or following failure, with one repair attempt. The seven-day interval is a fixed heuristic. |
| `revalidate` | Searches published documents on every task and can retry after failure. This is not a clairvoyant oracle: unpublished changes remain hidden. |

There is no trained policy or neural memory in this release. Employee language is templated, and enterprise instances vary parameters within one shared structural template. Complex planning, realistic document contents, rich persona behavior, MiroFish execution, and train/test generalization experiments remain future work.

## Files

| Path | Purpose |
|---|---|
| `world.py` | Blueprint generation, procedure semantics, employee beliefs, shared state and delayed events. Trusted evaluator code. |
| `environment.py` | Learner observation, seven tool actions, server-side effects and session budgets. |
| `agents.py` | Five hand-written persistent reference controllers. |
| `experiment.py` | Paired runs, artifact export, metrics and a controlled counterfactual probe. |
| `tests/test_simulator.py` | Causal and temporal invariants, observation boundaries, actual state changes, reward accounting and reproducibility. |

Artifact layout:

```text
manifest.json                         Generation parameters and blueprint hashes
metrics.json                          Per-enterprise metrics (analysis only)
REPORT.md                             Aggregated reference results
private/blueprints/*.json              Full scenario, including future changes
private/counterfactual.json            Matched intervention with evaluator labels
runs/<policy>/<enterprise>/
  learner/sessions.jsonl               Only received observations and tool results
  learner/business_rewards.jsonl       Between-session shared business rewards
  private/session_audits.jsonl         Expected procedures and diagnostic labels
  private/world_events.jsonl          Ground-truth event chronology
  private/final_state.json             End-of-window audit state
  daily.json                          Aggregate daily measurements
  metrics.json                        Final measurements
```

Only the `learner` streams are eligible agent training inputs. The split is a logical contract, not an OS security sandbox. For actual LLM agents with file or shell access, run the simulator in a different process/container and mount only permitted observations. A same-process Python policy can inspect objects if given arbitrary execution privileges.

Within `learner/sessions.jsonl`, `info.session_done` ends a conversation. It does not terminate the enterprise. The horizon boundary is a truncation, and outstanding rewards remain censored. Sum tool transition rewards and `business_rewards.jsonl` rewards to recover the reported net utility. Settlement notifications in the employee inbox are observations of those rewards, not extra rewards to sum again.

`World.fork()` copies the live state, queues, employee beliefs and notification state. A valid counterfactual also copies assistant memory. The exported final audit snapshot is **not** a complete resumable checkpoint; deterministic reruns use the generator seed and parameters. Full disk checkpoint/resume is a planned extension.

## Interpreting the demonstration

The drift run produced 4,784 sessions across five controllers and three enterprises; the stationary run produced 4,920. These are controller-specific trajectories, not independent experimental samples. Each run contains 756 common exogenous jobs, plus endogenous follow-up work.

In the drift run, frozen initial procedures completed 44.2% of root work. Scoped evidence resolution reached 98.8%; the adaptive and always-revalidate references reached 99.5%. Adaptive used 213 document queries versus 999 for always-revalidate and achieved higher net utility under the chosen costs. In the stationary control all initial plans were correct, so additional revalidation only added cost. See the linked reports and raw metrics for full denominators.

These results establish that the simulator creates a temporal and cost-sensitive adaptation problem. They do not establish a new algorithm, superiority over δ-mem or any LLM system, realistic enterprise behavior, or transferable learning.
