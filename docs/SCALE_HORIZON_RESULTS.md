# Scale-v1 duration evidence and prospective wall budget

**A 24-hour execution cap per world, with at most six concurrent worlds, is a
defensible limit for the next development campaign. It is not a completion
forecast.** This recommendation requires the separate native capability,
provenance, accounting and cleanup prerequisites. It does not launch new worlds
or change the existing ten-hour campaign.

The [public review metadata](scale-horizon-review-v1.json) commits the private
REPORT and capture inventory and retains all six slots. It contains 21 online
workflow/regime/arm duration groups, nine learning workflow/day/proposal groups
and 52 replay workflow/regime/day/phase groups. Statistics use recorded seconds;
absent groups mean unobserved combinations, not zero duration.

## Verified snapshot

The sequential capture ran on **2026-09-10, 06:40:44.834927–06:41:00.920412 UTC**.
Independent `verify_snapshot` execution matched both supplied hashes,
reconstructed the saved summary and found no source or raw-binding errors:

- REPORT SHA-256: `80d9dd728299f23646478c529c1ad7ff49010253dd31a86a926bbdaaeb1d7f13`
- Capture SHA-256: `f92b6de9053b04e55a643fdb54c86b413be8236aa4108b1a7eeb8a0bd4df090a`
- Diagnostic SHA-256: `7bd43a99860ef916129934446fc1c645fc7fa466c20de3b6a76b85cc437fea2d`

The inventory contains 2,391 raw files, 960 returned online attempts, 34 learning
epochs and 370 returned replays. All 34 frozen execution source files match.
Seed 401 SkillOpt's checkpoint and INFLIGHT marker changed during capture; their
first captured bytes remain the evidence. The table describes that window only.

| Slot | Recorded status | Checkpoint day | Online attempts | Epochs | Replays | Supervisor elapsed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 211 no-learning | completed | 21 | 233 | 0 | 0 | 3.99 h |
| 211 SkillOpt | failed | 11 | 143 | 15 | 162 | 4.63 h |
| 307 no-learning | completed | 21 | 239 | 0 | 0 | 4.15 h |
| 307 SkillOpt | failed | 7 | 93 | 0 | 0 | 1.59 h |
| 401 no-learning | failed | 8 | 106 | 0 | 0 | 1.90 h |
| 401 SkillOpt | running | 12 | 146 | 19 | 208 | unknown |

The running world's checkpoint reports 5.35 hours of runner elapsed time; that
is a different clock from terminal supervisor elapsed. Recorded status does not
certify the original scientific acceptance gate. All three failed slots remain.

## Durations and unknowns

Online workflow/regime/arm medians range from 33.4 to 58.7 seconds; their p90s
range from 41.4 to 123.7 seconds. The longest returned online attempt took
277.4 seconds. Every captured online, epoch and replay duration is numeric, but
complete duration records do not imply complete usage records.

| Recorded epoch class | Count | Median learner wall | p90 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| No proposal observed | 19 | 415.8 s | 569.4 s | 642.0 s |
| Proposal observed | 14 | 736.7 s | 844.7 s | 925.4 s |
| Incomplete, proposal class unknown | 1 | 815.8 s | 815.8 s | 815.8 s |

These pooled descriptions are accompanied by the separate day/workflow groups
in the JSON. They are not independent samples or estimates of future epochs.
Only learning days 7 and 11 are represented; there is no day-17 learning or
SkillOpt online reversal evidence in this snapshot.

One online attempt and one replay record have incomplete usage and invalid
infrastructure. The latter belongs to the failed learning epoch: 33 epochs have
complete recorded accounting and one does not. These overlapping records must
not be counted as three independent cost failures or summed as separate costs.
The JSON preserves their charged/reserved amounts and known token prefix under
those labels; total measured consumption remains unknown. The epoch-level
infrastructure field is not recorded, separately from its status and accounting.
Actor physical usage, all-in cost and physical inference time remain unknown.

One accepted update is recorded in a world that subsequently failed. This
duration diagnostic neither regrades its gate nor establishes learning gains;
see the [adoption interruption record](SCALE_ADOPTION_INTERRUPTION.md).

## Why choose 24 hours prospectively?

The two completed no-learning worlds took about four hours. Proposal-generating
epochs are materially longer than the observed no-proposal epochs. A 24-hour
cap provides operational headroom for repeated learning while retaining a finite
equal-arm stopping rule. The three recorded failures occurred before ten hours;
a larger ceiling does not repair their failure modes.

The cap deliberately remains below the sum of individual maxima: 240 online
attempts at 420 seconds permit 28 hours, and 36 possible learning epochs at
1,800 seconds permit another 18 hours, before actor and other overhead. Those
46 hours are allocation arithmetic, not a forecast. The evidence cannot assign
a probability of completion within 24 hours. Future provider latency, six-world
contention, new actor behavior and later learning workloads remain uncertain.
Six workers retains the configured concurrency ceiling; it is not proof of
sustained six-world reliability. Streaming scale-v1 timings do not establish
long-horizon reliability of the prospective non-streaming transport.

Retain four enterprises and twelve employees per world, all three seed pairs,
20 action days plus two settlement days, T2/V2/K2 and the unchanged faithful gate.
Keep 1,440 total online-attempt slots, at most 108 learning epochs, the existing
44,640 employee target/optimizer physical-call ceiling and 792 million charged
token ceiling. No additional model-call allowance follows from the longer wall
cap. Record 120 seconds of world cleanup and 30 seconds of service cleanup
separately from execution, under the reviewed lifecycle contract.

Register all six fresh worlds with the same 24-hour cap before dispatch. Do not
combine surviving old arms with reruns or extend, replace or retry slots based
on outcomes. The full endpoint still requires all three complete valid pairs;
a cap-stopped or accounting-invalid world remains incomplete. The
[follow-up plan](SCALE_FOLLOWUP_PLAN.md) and
[diagnostic contract](SCALE_HORIZON_OBSERVATIONS.md) describe the remaining
requirements and overlapping timing scopes.
