# Scale-v1 execution observations

The [frozen six-world study](SCALE_STUDY_PLAN.md) launched on 2026-09-10.
This document records operational observations made during execution. It is
neither a preregistration amendment nor a completed comparison. All six planned
worlds and all three pairs remain in the study inventory.

## First completed SkillOpt epochs

The first incident-response employee in seeds 211 and 401 completed its day-7
epoch. Each epoch performed 12 native target replays and one optimizer call,
produced four edit records and retained skill version 0 after rejection by the
unchanged upstream gate. Independent review checked the raw replays, grades,
upstream gate reconstruction, chronological experience selection, progress
receipts and allocation limits. Neither epoch had a recorded timing or physical
budget overrun, unknown cost receipt, or scored/dispatched replay mismatch.

| Seed | Baseline validation | Edited-skill validation | Fresh incumbent final validation | Target / optimizer calls | Measured tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| 211 | 1.00000000 | 1.00000000 | 0.73333325 | 128 / 1 | 1,493,894 |
| 401 | 0.73333325 | 0.73333325 | 0.71666675 | 127 / 1 | 1,460,775 |

These are mean mixed scores on two validation capsules, not prospective work
outcomes. Seed 211's edit did not strictly improve validation. Seed 401's edit
had equal mean score and a per-case regression. The final validation reran the
unchanged incumbent in each case, so its score must not be described as another
edited-skill score. Variation across fresh incumbent replays reinforces the need
to separate gate decisions from evidence of future learning benefit.

The raw `learning/d007-firm-0__incident-regulated/update.json` receipts have these
SHA-256 hashes; private skill text and capsules remain outside the repository:

| World | Immutable update SHA-256 |
| --- | --- |
| `seed-211-skillopt` | `ade32aef1cacb370fac92e4056f2a6dac9515c30c559ef4acd1ffb16b85b10a5` |
| `seed-401-skillopt` | `c0eddf4c925f70707d0985f791c81351cd2929d5cdf5140d7eee098dffb2043f` |

Later employees and scheduled epochs continue under the same protocol. These
first epochs establish executed optimization and audited rejection; they do not
establish a learning gain or summarize the eventual campaign.

## Day-7 interruption in seed 307, SkillOpt arm

The supervisor recorded exit code 1 and confirmed closure of this world's actor
environment at **2026-09-10 02:53:53 UTC**. The employee actor's original response
and its one permitted repair both failed JSON parsing at the end of the string.
The original contained 2,313 characters and the repair 2,140; both lacked a final
closing brace. No complete decision object could be extracted. The original
parser did not accept a decision, and this action never dispatched Hermes.

The strings already had this defect at OASIS's immediate model-output log;
their SQLite and MiroFish cache copies match exactly. Inspection found no
delimiter-removing operation on that path. The Responses adapter rejects a
provider response whose status is incomplete, but per-interview provider
completion receipts were not retained. **The precise generation cause is
unknown; a token-limit truncation has not been established.**

An offline diagnostic addition of the missing delimiter passed the original
schema validator. That is a diagnostic observation only. Neither response was
rewritten, accepted or enacted, and no additional repair was requested. Changing
the parser after this observation would change the frozen execution protocol.

The [allowlisted observation receipt](scale-interruption-observation-v1.json)
binds the private checkpoint, failure markers, completed interview caches and
cleanup receipt using raw-byte SHA-256 hashes. It contains no prompts, persona
records, response text, credentials or private local paths.

| Evidence scope | Observed amount |
| --- | ---: |
| Prior checkpointed employee sessions | 93 |
| Prior completed SkillOpt epochs | 0 |
| Physical employee calls in those sessions | 963 |
| Measured and charged employee tokens in those sessions | 10,309,804 |
| Hermes calls for the interrupted action | 0 |
| Completed logical actor interviews for that action | 2 |
| Physical actor calls and tokens | Unknown |

The frozen native artifact auditor checked all 93 prior employee sessions with
zero errors and returned **incomplete**, as expected for a failed world. This
validates the recorded prefix, not the unobserved remainder of the world. The
runner's failure report marks overall accounting incomplete; complete employee
receipts do not make environment or all-in accounting complete.

## Recovery and study interpretation

Lossless reopening of this closed native environment is unsupported. The pinned
MiroFish Reddit startup creates new agents, deletes an existing simulation
database and calls environment reset. Closing does not serialize all executable
agent memory. Surviving profiles, graph state, SQLite records and explicit
employee working notes are useful evidence, but they are not a complete restart
checkpoint. The evaluation runner correctly refuses this destructive restart.

The failed world stays closed and its artifacts remain intact. The other five
worlds initially continued within their original budgets; the second interruption
below later reduced the active count to four. No replacement world has been
launched. An infrastructure interruption is not an employee task failure, and
missing future outcomes must not be converted to zeros or omitted from the
planned-world inventory.

Consequently the full preregistered three-pair endpoint cannot be estimated from
this execution. The completed-study publication helper must continue to refuse
this campaign. Any later report of surviving worlds must retain the interrupted
slot and label its results as a partial development study; it must not substitute
a two-pair mean for the planned three-pair endpoint.

Future execution changes are developed in isolated checkouts while all 34 frozen
execution files remain unchanged. The next protocol needs a supported
per-interview structured-output contract, bounded generation and repair, and
completion/usage receipts. These fixes require offline validation and prospective
registration before new native comparisons. They do not establish that SkillOpt
improves future work, nor do they justify resuming a reconstructed actor state as
the original world.

## Day-8 transport interruption in seed 401, no-learning arm

This world's employee actor returned valid JSON. Hermes then produced an
immutable committed artifact that independently passed trusted grading with
strict success and semantic score 1.0. The intended skill was loaded. However,
one of twelve physical model requests had a stream `ReadError` without a usage
receipt. A retry in the native Hermes conversation loop succeeded. SDK retries
were disabled, and both physical requests passed through the budget meter.

The [transport observation receipt](scale-transport-interruption-v1.json) keeps
the successful artifact separate from incomplete session accounting:

| Interrupted action accounting | Recorded amount |
| --- | ---: |
| Physical model requests | 12 |
| Requests with usage receipts | 11 |
| Known measured tokens | 121,790 |
| Retained reservation for the unknown request | 62,029 |
| Charged tokens, including that reservation | 183,819 |
| True total tokens | Unknown |

There was no recorded physical-call, output-token, reservation or wall-limit
overrun. The full action took approximately 135.82 seconds under its 420-second
limit. The request's retained `error_type` is `ReadError`; stream closure overwrote
its status with `stream_closed_without_receipt`. This records a stream transport
failure but does not establish an underlying provider or network cause.

The checkpoint contains 105 earlier sessions with complete usage receipts
(1,135 calls and 12,362,220 measured tokens), followed by the interrupted action.
The frozen accounting gate correctly marks that action infrastructure-invalid
and terminates the world. Its supervisor closed the actor environment. The world
cannot be resumed losslessly, and a successful artifact does not make its missing
usage known. No retry or replacement was initiated after the failure.

This is separate from the malformed actor JSON failure and the future learning
deadline fix. The reviewed [stream-evidence fix](https://github.com/ojus1/Big-World-CL/pull/2)
preserves the original stream error through closure; it cannot recover a lost provider receipt or change current
eligibility. Resolving transport receipt reliability remains a preflight item for
a fresh full comparison.

The [follow-up implementation and launch plan](SCALE_FOLLOWUP_PLAN.md) preserves
the complete three-pair scope and defines the required preflight evidence before
another native campaign can be registered.

The [fixed 14-epoch learning observation](SCALE_LEARNING_OBSERVATION.md) extends
the first two epoch checks with independently reconciled replay, gate, cost and
regime-exposure evidence. It separates edited candidates from repeated incumbent
validation and leaves later learning boundaries unobserved.
