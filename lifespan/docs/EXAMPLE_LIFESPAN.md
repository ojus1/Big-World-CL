# An actual generated lifespan

This walkthrough is generated from the seed-7 demonstration artifacts. It is a procedural simulation, not a real company or LLM transcript.

Enterprise: **Juniper Services 431**. Horizon: **84 days**. Active employees: **6**.

## People

| Employee | Workflow | Account scope | Document reading delay |
|---|---|---|---:|
| Devi-0 | onboarding | commercial | 4 days |
| Ari-1 | onboarding | regulated | 1 days |
| Alex-2 | renewal | commercial | 1 days |
| Ari-3 | renewal | regulated | 1 days |
| Sam-4 | incident | commercial | 1 days |
| Ari-5 | incident | regulated | 4 days |

Each employee has a separate persistent assistant state. Approvers are abstract authority queues in this PoC.

## Scheduled changes

| Change | Published | Effective | Expires | Mechanism |
|---|---:|---:|---:|---|
| regulated-review | 12 | 14 | — | A regulated customer audit changes the review procedure |
| tool-migration | 25 | 23 | — | Operations deploys a new interface; documentation arrives late |
| data-handling | 32 | 32 | — | Customer contract changes the incident disclosure boundary |
| temporary-channel | 42 | 43 | 51 | A temporary outage moves coordination to a war room |
| informal-rumor | 52 | 52 | — | A colleague repeats an obsolete approval shortcut |
| reorganization | 60 | 61 | — | A reorganization changes the default approver; the regulated exception remains |
| tool-rollback | 69 | 69 | — | A failed migration is rolled back |

This table is evaluator-only information. Assistants receive only published documents and delivered messages; an informal rumor does not change the authoritative procedure.

## Same task, two branches

On day 14, a controlled regulated-account renewal is inserted into a persisted enterprise snapshot. Both branches receive the same request. One branch is forced to reuse its old procedure; the other validates and uses the new procedure. This intervenes on controller mode and stored procedure together, so it is not an isolated estimate of the effect of one memory write.

### Reuse old procedure

| Action | Result | Immediate reward |
|---|---|---:|
| `draft.prepare {"channel": "renewal-desk", "redact": false}` | accepted | -0.03 |
| `check.perform {"name": "customer_check"}` | accepted | -0.03 |
| `approval.request {"approver": "renewal-lead-431"}` | recipient_does_not_own_this_approval | -1.03 |
| `session.end {}` | left_in_queue | -0.03 |

Final work status: **pending**. Probe-attributable utility after the two-day settlement window: **-1.12**.

### Validate and adapt

| Action | Result | Immediate reward |
|---|---|---:|
| `documents.search {}` | published procedures returned | -0.38 |
| `draft.prepare {"channel": "renewal-desk", "redact": false}` | accepted | -0.03 |
| `check.perform {"name": "customer_check"}` | accepted | -0.03 |
| `check.perform {"name": "risk_review"}` | accepted | -0.03 |
| `approval.request {"approver": "risk-lead-431"}` | accepted | -0.03 |
| `work.commit {"endpoint": "workspace-v1"}` | completed | -0.03 |

Final work status: **completed**. Probe-attributable utility after the two-day settlement window: **9.47**.

Successful work produces a delayed value of 10 in this probe. The reported utility subtracts action and query costs; unrelated background branch rewards are excluded. Failed work remains queued. The broader lifespan also retains trust and process effects; this narrow two-day comparison does not estimate all those later effects.

## What this makes trainable

The useful behavior is deciding whether to reuse, investigate, or revise a procedure, then executing work under the new requirements. A prose claim that the agent has learned earns no completion reward. The performed checks, actual approval, committed work, and later settlement determine the outcome.

See [raw counterfactual data](../artifacts/demo/private/counterfactual.json), [the drift report](../artifacts/demo/REPORT.md), and [the full research design](RESEARCH_DESIGN.md).
