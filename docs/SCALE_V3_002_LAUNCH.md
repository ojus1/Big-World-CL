# Six-world registration after repairing the installation

**Terminal status:** This registration stopped during day-7 work after the API
reported exhausted credits. Two worlds stopped with confirmed cleanup and four
were never launched. See the [reviewed termination evidence](SCALE_V3_002_CREDIT_EXHAUSTION.md).
There is no completed learning comparison. The launch details below are historical;
do not dispatch or resume this registration.

This new six-world study uses
[scale-preregistration-v3-002.json](scale-preregistration-v3-002.json), raw SHA-256
`72b19a41eb00f90761302df0d55e5051ec166d7240215b2302a68ae294b1c6ce`.
All six private run directories were fresh at registration. The
[failed first registration](SCALE_V3_LAUNCH_FAILURE.md) remains unchanged, with
two initialization failures and four unlaunched slots.
The [independent registration review](scale-v3-002-registration-review.json)
binds these new inputs, repaired installation evidence and current readiness
before dispatch. The production launcher repeats its five prerequisite audits.

Only the manifest creation timestamp differs from the first registration. All
69 execution/reporting sources, paired cohorts, models, configs, rubrics,
learning rules, schedules, resource limits and primary denominator are
identical. The study still requires all six complete worlds and three complete
pairs. It does not substitute a new world into a failed old slot.

The installation now contains the two previously omitted, checked-in actor
contract files. All four utility overlays match their source bytes. The
[installation observation](scale-v3-installation-repair.json) records an actual
local Flask capability request returning HTTP 200 with the exact expected
descriptor, verified by the [independent repair review](scale-v3-installation-repair-review.json).
The new setup checker passed 13 independently reviewed tests; the
frozen execution/reporting implementation previously passed 163 tests. The
capability check is separate from the nine native Hermes startup passes and
does not establish full-world reliability or learning benefit.

The launch used the [v3 execution guide](SCALE_V3_EXECUTION.md) with private output
`lifespan/artifacts/scale-v3-002`, the above reviewed hash, and the new public
registration path. Both baselines were planned over 20 action days plus
settlement, with 4 enterprises, 12 employees, 8 consumers and 1 agency per world.
Three fixed paired waves allow up to 1,440 online sessions and repeated SkillOpt
training and validation. Registration is not a completed result; no learning
gain is claimed here.

The campaign was dispatched once. The [dated startup observation](SCALE_V3_002_PROGRESS.md)
records both first-pair worlds running with native actor simulations and returned
employee sessions. Inspect current local progress with the independently reviewed
[status command](SCALE_STATUS.md):

```bash
python3 -m scripts.scale_status lifespan/artifacts/scale-v3-002 \
  --campaign-sha256 72b19a41eb00f90761302df0d55e5051ec166d7240215b2302a68ae294b1c6ce \
  --format table
```

This only reads operational state. The existing registration has one dispatch;
do not invoke the launcher again or resume its worlds.

For a future registration whose six worlds pass the completed-study audit and
whose public report is reviewed, the separate [figure command](SCALE_V3_FIGURES.md) renders all three
paired primary outcomes from that report. It requires the reviewed summary hash
and preserves negative and zero differences; it does not plot active prefixes.
