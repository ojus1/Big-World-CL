# Descriptive world trajectories

This reporting supplement was added during scale-v1 execution, on simulated
days 4–5 before any learning update. It exposes the persistent, reacting world
state alongside employee outcomes. It is not an additional preregistered
endpoint, an independent replicate count, or a causal estimate of learning.

```bash
python3 scripts/scale_world_dynamics.py \
  lifespan/artifacts/scale-v1/runs/seed-211-no_learning/checkpoint.json
```

The read-only command summarizes the exact checkpoint bytes it reads and records
their SHA-256 plus the postprocessor hash. It retains every enterprise and
consumer, including those with no recorded state changes. Missing event history
remains unknown; an ongoing checkpoint describes only the history observed so
far.

The summary distinguishes accepted enterprise decision records from actual
changes in objective, price, market or workflow priority. Strategy revisions
increase even on a decision that leaves those values unchanged. Procedure
requests are also separate from delivered route changes: requesting the current
route can install rules and incur costs without changing the route value.

Government decisions, delivered policy changes and policy expiries retain
separate trajectories. Exogenous geopolitical events are checked against the
recorded shock schedule. Native consumer orders must join the same consumer's
purchase or switch decision by cause, enterprise and day, and match order
history. Initial and fixed benchmark obligations are not labeled endogenous.

Enterprise strategy, route, policy and geopolitical histories reconcile with
their final checkpoint state. Consumer final scalar values are observed state;
this helper does not replay payments or independently validate financial
balances. Its descriptive consistency checks supplement the native campaign
audit and do not rescore work or change learning eligibility, adoption rules,
primary endpoints or run inclusion.

The completed-study publication helper includes these trajectories and hashes
the additional source separately from the 34 frozen execution files. It refuses
to write a draft with an inconsistent trajectory summary, rather than omitting
a world or reclassifying an employee outcome. Raw reports remain unchanged.
Reasons, working notes, persona text, employee requests, responses, rules and
private work artifacts are excluded from the exported summary.
