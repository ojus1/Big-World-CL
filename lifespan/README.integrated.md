# Enterprise Lifespans — MiroFish + Persona 8B PoC

The integrated PoC uses **actual Persona 8B records**, **native MiroFish/OASIS employee inference**, and **LLM-generated work actions and persistent skills**. The original rule-controller experiment remains a unit-test fixture; it does not satisfy the integrated PoC on its own.

The implementation is `integrated.py`. It creates a MiroFish project and graph, compiles six dataset-derived OASIS profiles, launches the installed native Reddit simulation runner, and uses its interview interface for workplace interactions across simulated days. Model-generated employee requests drive a separate LLM assistant that operates executable enterprise tools.

## Run

From the repository root:

```bash
python3 scripts/stack.py status
python3 scripts/stack.py start
uv pip install --python MiroFish/backend/.venv/bin/python -r lifespan/requirements-integrated.txt
MiroFish/backend/.venv/bin/python -m lifespan.personas

# Bounded three-interaction pilot, then continue the same run through four weeks.
MiroFish/backend/.venv/bin/python -u -m lifespan.integrated \
  --out /tmp/enterprise-live-run --days 28 --work-every 3 --max-sessions 3
MiroFish/backend/.venv/bin/python -u -m lifespan.integrated \
  --out /tmp/enterprise-live-run --days 28 --work-every 3

python3 -m unittest discover -s lifespan/tests -v
python3 -m lifespan.validate_live lifespan/artifacts/integrated
```

The installed model is `gpt-5.6-luna` with low reasoning, using the existing MiroFish credentials. Live runs make billable API calls. Requests have timeouts; invalid employee outputs are corrected through one real model interaction, then fail visibly if still invalid. There is no scripted-employee or reference-agent fallback.

The default workload introduces three jobs every three calendar days. Follow-ups and rework can occur on intervening days. Set `--work-every 1` for daily arrivals. At least 28 days are required by the current change schedule.

## What is connected

1. **Persona 8B import.** The importer reads full-release `persona-1m-0006.parquet` at revision `8b1073ab23d0c0ba0928386a041bac55e5365ddc`, verifies its published SHA-256, decodes packed attributes and missingness, and samples six synthetic rows with seed 7. Each record retains source and shard row indices, revision and file hashes. Sixteen work-relevant attributes enter the native employee profile. Job assignments and fictional names are separate simulation choices.
2. **Native MiroFish execution.** The integration uses the installed graph upload/build APIs, `OasisAgentProfile`, simulation configuration/state classes, `run_reddit_simulation.py`, OASIS environment, and interview API. Real model calls are recorded in MiroFish's SQLite trace. Existing projects, model configuration and MiroFish source files are not changed.
3. **Employee decisions.** Employees choose whether to delegate, write the request, decide which known documents to share, send colleague messages, and optionally propose a scoped peer-review step after an observed failure. These outputs change execution.
4. **Persistent collaboration.** Working notes and observed outcomes persist separately for each employee. Installed OASIS interviews default to `interview_record=False`; the adapter explicitly supplies saved notes and feedback rather than assuming hidden conversation persistence. Colleague messages arrive the next day and obey department/document access boundaries.
5. **LLM work agent.** A separate assistant uses MiroFish's configured model adapter with native function calls. It chooses queries, checks, approvals, commits and memory revisions. Procedure notes persist per employee; the engine does not correct them to the answer.
6. **Executable outcomes.** The engine verifies performed checks and approvals, applies business mutations, creates follow-ups, settles rewards later, and retains late or abandoned work. The old automatic failure-count process-change rule is disabled; employee proposals are validated explicitly.

## Inspect the run

- [Observed adaptation walkthrough](artifacts/integrated/WALKTHROUGH.md)
- [Integrated report](artifacts/integrated/REPORT.md) and [measurements](artifacts/integrated/RESULTS.json)
- [Imported cohort](data/cohort.json) and [native MiroFish profiles](artifacts/integrated/imported_mirofish_profiles.json)
- [Assistant skills](artifacts/integrated/assistant_skills.json) and [employee notes](artifacts/integrated/employee_states.json)
- [Research formalization](docs/RESEARCH_DESIGN.md)

During execution, `progress.json` identifies the latest completed day. Final result files are created after the full run.

| Artifact | Contents |
|---|---|
| `persona_cohort.json` | Exact selected records and provenance |
| `mirofish_state.json` | Real project, graph and simulation IDs |
| `mirofish_source.txt` | Initial enterprise source; excludes future changes |
| `mirofish_interviews/*.json` | Exact employee prompts, outputs and native responses |
| `mirofish_simulation.db` | SQLite backup of the actual OASIS trace |
| `employee_sessions/*.json` | Employee views, decisions and feedback |
| `completed_sessions/*.json` | Learner inputs, native calls, usage, effects and skills |
| `learner/sessions.jsonl` | Authorized assistant observations and tool transitions |
| `learner/business_rewards.jsonl` | Rewards arriving between sessions |
| `private/` | Hidden scenario, expected procedures and evaluator state |
| `manifest.json` | Source hashes, dataset revision and stack provenance |

Employee state is private to the simulator. An assistant receives the generated request, documents the employee chooses to share, its own notes and permitted tool responses. No full persona or hidden future schedule enters its prompt. This is a logical boundary, not an OS sandbox for arbitrary code; terminal agents would require process/container isolation.

Utility uses synthetic work and tool-cost units, not a monetary billing estimate. Assistant token usage is reported separately; employee token usage is not available from the native interview response.

Session completion does not terminate the enterprise. Settlement observations are not extra rewards to count twice. The horizon censors outstanding work and settlements, reported as backlog and unsettled value.

Interrupted runs replay **completed** sessions without calling the assistant again. Employee inputs must match stored prompts exactly. An incomplete learner session may need fresh inference. Completed runs refuse to overwrite results. This is event replay, not identical regeneration from stochastic model calls.

## Limits

This is one integrated simulation, not an RL training result or a validated enterprise model. The environment has one workflow template. The cohort is a sample from one synthetic shard, not a representative workforce. Persona data is non-commercial research-only, including subsets and derivatives; the software license does not relicense it.

MiroFish supplies employee inference and an initial social round. Workplace messages are routed by the adapter; their visibility and delay do not come from the social recommender. Business state and scheduled changes remain executable mechanisms. Employee realism, causal effects of persona conditioning, and gains from persistent memory still require controlled experiments.

The earlier controls remain available through `python3 -m lifespan demo --out <fresh-path>`. Their reports in `artifacts/demo` and `artifacts/stationary` are archived mechanism checks. See [the reference-fixture README](README.reference.md).
