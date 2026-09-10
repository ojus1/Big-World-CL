# Larger reacting-world development study

Status: implementation reviewed and 75 distinct pinned synthetic personas
imported. The [frozen campaign](scale-preregistration-v1.json) was prepared before
any native model calls; results will be reported separately. This study follows the rejected native SkillOpt candidate
and identical-skill A/A difference in [the earlier study](LEARNING_STUDY_RESULTS.md).
Its objective is to test repeated employee learning under more varied exposure,
not to require an improvement.

## Population and timeline

Three fixed development seeds, **211, 307 and 401**, each run both native Hermes
without learning and native Hermes with pinned SkillOpt-Sleep. Each world has
four competing enterprises, twelve frontline employees, eight consumers and one
government agency. Each frontline employee owns one workflow: onboarding,
renewal or incident response. Twenty action days are followed by two days of
settlement without new work or learning.

The population compiler imports 25 distinct synthetic Persona 8B records for
each seed from the already pinned MatrAIx shard. The three cohorts must be
disjoint (75 distinct records). Both arms of a seed receive identical cohort
bytes. Enterprise and agency profiles describe institutional decision tendencies;
they are not extra employee accounts. This remains a bounded service economy,
not a validated model of a real institution or a months-long lifespan.

MiroFish owns persistent actor interactions. Native institutions can change
business objectives, markets, prices, routes and policies in response to observed
conditions. Consumers can respond to outcomes and competing offers. Geopolitical
shocks occur on day 6 and day 15 for these seeds; substantive requirements have
base, changed, exception and reversal regimes on days 0–5, 6–9, 10–14 and 15–19.
Institutional choices are generated independently in each arm, not replayed from
the no-learning outcome. The work, messages, rules, orders and settlements remain
chronological and causal within each world.

Each employee receives one initial obligation on day 0, then one exogenous
obligation on each day 1–19. Each employee can attempt at most one pending obligation daily;
native consumer orders are additional. Therefore each run has 240 fixed demand
obligations and at most 240 online attempts. Failed tasks can consume later
attempts. Retries are never counted as distinct learning experiences or used to
remove unmet commitments from the denominator.

## Learning and comparison

All twelve employees are included in the SkillOpt treatment. At the end of days
3, 7, 11 and 17, the runner records each employee's available distinct TRAIN and VAL counts.
Day 3 cannot have the required four released distinct observations. The remaining
three dates are learning opportunities; eligibility is not guaranteed. The day 17
epoch can use reversal feedback from days 15–16 before prospective work on days
18–19. Feedback
arrives one day after scored work. The existing deterministic split keeps every
retry of an obligation in the same pool; the most recently observed contents
replace earlier contents while preserving the obligation's original pool order.

Each eligible epoch uses **T=2, V=2, K=2**, at most four skill edits and the pinned
upstream gate. K=2 adds contrastive TRAIN rollouts; it does not repeat or average
validation. Candidate validation must strictly improve mean mixed score and
avoid per-task regressions. Final validation and rollback follow unchanged
upstream semantics. There is no manual skill replacement, weakened gate,
post-result seed replacement or outcome-conditioned extension.

Accepted skills apply only to later online work. All future tasks are unseen by
the optimizer until their work has been scored and feedback released. Native
Hermes loads the actual employee skill file; its private conversation and profile
are fresh per task in both arms. Business state and the MiroFish employee's
interactions persist. This isolates skill transfer within the harness; it does
not measure memory stores, weight updates or persistent shell-session learning.
Bubblewrap provides filesystem/process isolation with a shared host kernel.

## Fixed budgets and supervision

| Quantity | Per world or epoch | Whole campaign ceiling |
|---|---:|---:|
| Native online work | 240 attempts/world | 1,440 attempts |
| Online target budget | 16 physical calls, 250,000 charged tokens, up to 420 s/attempt | 23,040 calls; 360M tokens |
| Learning opportunities after warmup | 3/employee, 12 employees/learning world | 108 epochs |
| Learning epoch | 200 physical target+optimizer calls; 4M charged tokens; 1,800 s | 21,600 calls; 432M tokens |
| Native learning target replays | at most 12/eligible K2 epoch | 1,296 attempts |
| Logical MiroFish interviews | 662/world, including repair requests | 3,972 requests |
| World execution wall time | 36,000 s | six concurrent runs, with bounded cleanup |

These are ceilings, not usage predictions. Actual employee-target and optimizer
receipts are reported separately: their combined maximum is 44,640 physical calls
and 792M charged tokens. Each employee has an equal lifetime learning allocation
of 600 calls and 12M tokens, with a 200-call/4M per-epoch cap. Unused allocation is
not silently redirected to a better-performing employee. A perfect TRAIN pool
can prevent a proposal under faithful upstream behavior.

Actor requests have a durable intent/completion ledger written before dispatch.
**Logical interview requests are not physical model calls.** Graph generation,
the initial social round and OASIS internal inference still lack complete token
accounting. Actor tokens and all-in currency cost remain unknown. Startup stages,
interview timeouts and each world's wall ceiling are bounded. Late work can receive
the runner's remaining wall budget; any exhaustion is retained in the results.

The supervisor writes progress snapshots every 30 seconds. Online attempts,
institutional decisions, learning replays and optimizer dispatches leave durable
progress records. Only independent worlds execute concurrently. Within each
world, actions and adoption remain sequential. An uncertain action is never
automatically replayed. A failed or incomplete arm remains in the planned study;
the other runs continue under their original limits.

## Evaluation and release

The primary endpoint is the equally weighted world-pair difference in fulfilled
fixed initial/benchmark commitments by the settlement horizon, using the corrected
v2 reporting contract. Secondary endpoints include all commitments, utility,
regime exposure, employee eligibility, proposals and adopted skill versions,
future online outcomes using each version, and measured employee/optimizer compute.

There are three independent scenario pairs, not 1,440 independent samples.
Within-world employees interact. Hosted actor and Hermes randomness is not
controlled by the scenario seed. Report every per-world delta; any bootstrap
interval from the existing comparator is descriptive and unstable at this sample
size. Skill adoption and subsequent success do not alone establish a causal
learning gain, and differences with unchanged skills must remain visible.

Independent auditing must reconstruct raw native grades, submitted bytes, skill
loads, chronological versions, learning gates, receipts, cohort identity, source
hashes and corrected commitment reports. Planned slots and unavailable results
remain explicit. The public release contains reviewed code, frozen configuration,
hashes and allowlisted aggregates. Private cases, answers, persona records,
credentials, conversations and native profiles remain outside Git.

The pure employee-exposure summary labels its hashes `canonical_json`: sorted
keys, compact separators, escaped non-ASCII characters and UTF-8 encoding. These
bind parsed values and are distinct from the raw-file-byte SHA256 hashes used by
the native artifact audit and the published campaign execution requirement.

Preparation performs no model calls:

```bash
MiroFish/backend/.venv/bin/python scripts/run_scale.py prepare \
  --out lifespan/artifacts/scale-v1
```

The exact prepared campaign SHA-256 is
`6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa`.
The safe manifest is published before execution.
Execution requires that reviewed hash:

```bash
MiroFish/backend/.venv/bin/python -u scripts/run_scale.py execute \
  --out lifespan/artifacts/scale-v1 --workers 6 \
  --campaign-sha256 6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa
python scripts/run_scale.py status --out lifespan/artifacts/scale-v1
python scripts/audit_scale.py lifespan/artifacts/scale-v1 --strict
```

Coordinator owns the protocol, supervisor, native execution and publication.
The population/task agent owns scale tests and employee exposure summaries. The
SkillOpt agent owns per-epoch accounting, replay evidence and upstream fidelity.
The independent review agent owns the campaign audit and publication review.
Frozen earlier artifacts are preserved; their strict historical audits require
their matching source revision.
