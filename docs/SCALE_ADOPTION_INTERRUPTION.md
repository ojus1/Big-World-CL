# First accepted update and a later learning interruption

The `seed-211-skillopt` world produced one accepted employee skill update on day
11. The pinned gate and raw replay/progress checks passed. The world then failed
in another employee's day-11 epoch, before any later online work used the new
skill. **This is a verified adoption with zero prospective exposures, not a
learning-gain result.**

The accepted update belongs to `firm-1__incident-regulated`, version 0 to 1,
available from day 12. Four edits applied. Its two-case mixed validation mean
was 0.70833325 for the incumbent, 1.0 for the first candidate evaluation and
0.73333325 for fresh final candidate validation. Both candidate evaluations
passed the per-task no-regression rule. The twelve replays used 135 target calls
and one optimizer call, with 1,628,935 measured tokens. The small validation set
and repeated measurements are selection evidence; they do not estimate future
business performance.

The later failed epoch belongs to `firm-2__incident-regulated`. Its final replay
recorded nine physical requests, including one stream closed without a usage
receipt and a `ReadError`. Eight reported receipts account for 93,640 tokens.
The unresolved request reserves 36,447 tokens, making the native charged total
130,087 while the true total remains unknown. The enclosing learning epoch
reserves the invalid callback's full slot under the frozen v1 contract; its
charged figures are not exact physical consumption. No recorded native budget
exhaustion explains this failure, and `ReadError` alone does not establish its
underlying provider or network cause.

The independent raw artifact audit checked 143 online sessions and 15 update
records. It retained one error: incomplete learning accounting in that final
epoch. The world remains failed and ineligible for paired inference. No original
record, acceptance rule, seed, or world was replaced.

[The allowlisted observation](scale-adoption-interruption-v1.json) contains exact
raw hashes, selection/gate check results and separate measured/reserved counts.
Task content, skill text, personas, prompts and provider traces remain private.
The earlier [fourteen-epoch observation](SCALE_LEARNING_OBSERVATION.md) remains a
fixed earlier observation and does not include this later adoption.
