# Figures from the completed scale-v3 public report

`scripts/plot_scale_v3.py` converts the audited public `SUMMARY.json` produced by
`scripts/report_scale_v3.py` into a standalone SVG and PNG. It is a separate
postprocessor, outside the registered execution. No completed study values or
figures are supplied here while the campaign runs.

Use a separate plotting environment with Python 3.10+ and matplotlib. For example,
create a virtual environment and install matplotlib there; do not modify the
registered native execution environments. The command reads only the public
summary and its own source. It does not access private campaign artifacts or
contact a model or service.

```bash
python scripts/plot_scale_v3.py /path/to/audited-public/SUMMARY.json \
  --summary-sha256 <separately-reviewed-raw-summary-sha256> \
  --out /path/to/new-figure-directory
```

Obtain the expected hash from the reviewed publication record. Computing a hash
from an unreviewed file and passing it straight back does not establish its
authenticity. The command requires a completed six-world, three-pair v3 report,
completed audit/scope markers, seeds 211/307/401 with both arms, and consistent
counts, rates, paired differences and mean. Hash verification and these public
checks do not repeat the native evidence audit performed by the reporter.

The new output directory contains:

- `fixed-demand-pairs.svg`: editable vector figure, with text retained as text.
- `fixed-demand-pairs.png`: the same figure at 180 dpi.
- `FIGURES.json`: raw summary and plotter hashes, matplotlib version, plotted
  counts and differences, and exact SVG/PNG hashes. It contains no private input
  paths or unrecognized summary fields.

The left panel shows both arms for each seed, including fulfilled counts out of
the planned **240 commitments per world**. Fulfillment is measured before the
20-day work horizon; later settlement does not change this numerator. The right
panel shows SkillOpt minus no-learning in percentage points, with a zero line.
All three pairs remain visible. A separate diamond row gives the equal-world
mean; it is not an additional world. These are descriptive development results,
with no confidence interval, significance test or causal claim about learning.

The command refuses an existing output directory and rechecks the summary bytes
before writing. Rendering depends on the recorded matplotlib version; hashes
identify the exact generated files rather than promising identical rendering
across library versions.

Offline rendering checks may use a private artificial summary with the same
required shape, `fixture_only: true`, and the explicit `--synthetic-fixture` flag.
Every resulting figure is visibly labeled **SYNTHETIC FIXTURE — NOT STUDY
RESULTS**, and its manifest retains that designation. Such a fixture is not
native evidence and must not be published as a study result.
