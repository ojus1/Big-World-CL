# Early scale-v1 learning observation

This additive, descriptive observation covers a fixed set of **14 completed day-7 epochs**, seven each from the seed-211 and seed-401 SkillOpt worlds. It includes 12 epochs beyond the previously reviewed first incident epoch in each world. It is not a preregistered endpoint or a completed-campaign comparison. The [safe metadata inventory](scale-learning-observation-v1.json) records every immutable update SHA-256, the source bindings, curriculum counts and gate results; it contains no prompts, answers, skill text, personas or private filesystem paths.

All 14 completed epochs passed the frozen per-update audit, including replay regrading and cost reconciliation. Independent arithmetic reproduced the recorded mixed gate scores and per-task regression flags. The update files remained byte-identical during inspection. None adopted a skill: every recorded transition was version 0 → 0. Nine epochs made no optimizer call and proposed no edit; all their six TRAIN replays succeeded. The other five made one optimizer call each, returned four parsed edits each, and had all 20 edits rejected. There were no unmatched edits or learning-accounting failures in this inventory.

| Seed / incident employee | Incumbent validation score | Edited candidate score | Candidate rejection |
| --- | ---: | ---: | --- |
| 211 / firm-0 | 1.000000 | 1.000000 | No strict improvement |
| 211 / firm-1 | 1.000000 | 1.000000 | No strict improvement |
| 211 / firm-3 | 0.450000 | 0.716667 | One validation task regressed |
| 401 / firm-0 | 0.733333 | 0.733333 | One validation task regressed |
| 401 / firm-1 | 0.716667 | 0.733333 | One validation task regressed |

These are the edited candidate trials. Every subsequent `final_val` replay used the **unchanged incumbent hash** after the edits were rejected. For example, seed-401 firm-1 incident's final score of 1.0 is an incumbent repeat, not a successful candidate. Across 28 matched incumbent baseline/final case pairs, hard success differed in three and hard or soft score differed in six, spread across five epochs. This establishes repeated-measurement variation in these samples; it does not establish that the candidates' per-task regressions were merely noise.

At day 3, all 36 SkillOpt employees lacked the required distinct experience. At the day-7 cutoff, recomputing the published selector for the 24 employees in the two observed worlds gave 16 eligible and eight ineligible. The fixed inventory contains 14 completed epochs; both remaining eligible firm-3 renewal epochs were in flight when observed. Seed-307's interrupted world had not reached its day-7 learning boundary. These pending/unreached cases are not counted as completed failures or removed from the campaign.

The first boundary has a specific exposure limitation. Change began on day 6, feedback was delayed one day, and the update ran on day 7. Among the completed epochs' 28 TRAIN obligations, 19 were base-regime and nine changed-regime; among 28 VAL obligations, 23 were base and five changed. Each epoch had exactly one changed-regime obligation across its four selected cases. **No epoch had changed-regime examples in both TRAIN and VAL.** Nine placed the changed case in TRAIN; five placed it in VAL. The strict improvement gate also had a ceiling for the two candidate batches whose incumbent scored 1.0. These facts limit what this first boundary can establish about adaptation.

The 14 epochs used 150 native target replays, 1,487 target model calls, five optimizer calls and 15,817,367 reported tokens. The 12 newly reviewed epochs account for 126 replays, 1,232 target calls, three optimizer calls and 12,862,698 tokens. These are learning costs only; online employee work and environment-actor compute are excluded, and currency cost is unknown. Repeated attempts of the same historical obligations are not independent new tasks.

Day-11 and day-17 learning are **unobserved in this fixed observation**. This report does not conclude that the complete curriculum is inadequate or that SkillOpt is ineffective. For a future registered study, the findings motivate checking recent-regime TRAIN/VAL coverage and repeated gate measurements before drawing learning-effect conclusions. They do not authorize changing the active protocol, relaxing its gates, editing skills manually, or replacing interrupted worlds.

The relevant frozen semantics are in `lifespan/evaluation/protocol.py` (`select_experiences`), `lifespan/evaluation/runner.py` (scheduled eligibility and deployment), `scripts/audit_evaluation.py` (`update_check`), and pinned upstream SkillOpt's `skillopt_sleep/consolidate.py` (candidate gate and fresh final validation). Source hashes are included in the metadata inventory.
