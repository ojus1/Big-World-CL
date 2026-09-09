# Ecosystem Lifespans — MiroFish, Persona 8B, Hermes and bubblewrap

The current PoC adds **two competing enterprises, a government agency, independent consumers, and a dedicated Hermes/computer pair for each of six frontline employees**. Business objectives are state: institutions decide how to react to public offers, realized outcomes, policy and geopolitical conditions. Those choices change demand, priorities, deadlines, required procedures and later rewards.

[Read the formal design and algorithm](docs/ECOSYSTEM_DESIGN.md). The earlier [single-enterprise integration](README.integrated.md) and [procedural reference fixture](README.reference.md) remain separate experiments.

## Run

```bash
python3 scripts/stack.py start
command -v bwrap

# Uses the existing pinned Persona 8B cache and installed Hermes environment.
MiroFish/backend/.venv/bin/python -u -m lifespan ecosystem \
  --out /tmp/ecosystem-lifespan --days 16

# Optional pilot: --max-sessions 2. Resume using the same command without the cap.
# A completed output cannot be overwritten.

python3 -m unittest discover -s lifespan/tests -v
PYTHONPATH="$PWD:${HERMES_AGENT_ROOT:-$HOME/.hermes/hermes-agent}" \
  "${HERMES_AGENT_ROOT:-$HOME/.hermes/hermes-agent}/venv/bin/python" \
  -m lifespan.check_native_sandbox
python3 -m lifespan.validate_ecosystem /tmp/ecosystem-lifespan
```

The local stack uses the existing `gpt-5.6-luna` configuration. The adapter imports twelve distinct records from the pinned public Persona 8B coreset and compiles native MiroFish profiles. Six represent employees; two represent enterprise decisions, one the agency, and three consumers. The institutional profiles are modeling approximations, not claims about real organizations or representative human populations.

`lifespan/computers.py` locates the existing Hermes installation at `$HERMES_AGENT_ROOT` (default `~/.hermes/hermes-agent`). No Hermes source changes or user profile changes are required. The native model transport runs outside the employee sandbox; terminal and file operations run inside bubblewrap. Docker is not required by the default employee-computer backend.

## Persistent state

Each employee has these directories under the run output:

```text
computers/<employee>/
  workspace/
    inbox/current.json
    company/objectives.json
    company/procedures.json
    notes/
    deliverables/
  os_home/
  hermes/
    config.yaml
    state.db
    lifespan_history.json
    memories/
    skills/
```

Each employee gets a separate long-lived native Hermes `AIAgent` process and a separate bubblewrap supervisor during the run. Native Hermes terminal, file, memory and skill tools are used. The supervisor preserves its process namespace across work turns; employee workspaces, OS homes, Hermes histories, memory and skills persist on disk. A model session gets a fresh compute allowance while retaining learned state.

A new inbox does not erase the computer. Preparing work reads a real JSON artifact from the employee filesystem. Approval and commit validate that file's content hash. File snapshots retain prior content in `filesystem_objects/`; session records connect changed files to actual work results and later business events.

Bubblewrap is a Linux namespace sandbox, not a VM. It shares the host kernel and read-only system binaries. Workspace/home files survive a supervisor restart; background processes and temporary runtime files do not. There is no full machine snapshot/restore or filesystem quota in this PoC.

## Enterprise adaptation

Companies choose objective, price, target market, work priority and route. There are two available employee work sessions per firm per day. Existing obligations survive strategy changes. Consumers compare public offers and their own experience, then purchase, switch, complain or wait. Orders reserve consumer budget; payment follows successful delivery with delay.

The government can retain, add, withdraw or allow temporary enhanced review to expire. Effective dates differ from publication dates. Current rules use additive mandatory checks so a local peer-review procedure cannot remove jurisdiction review, and expiry does not accidentally preserve a temporary government check forever.

The default scenario's corridor disruption on day 4 and reopening on day 11 are exogenous fictional shocks. Institutional reactions are model decisions. The current experiment is a small integration PoC, not a validated economy or a trained RL agent.

## Artifacts and recovery

- `timeline.json`: shared causal events across entities.
- `actor_sessions/`: actual MiroFish decisions, observations and evidence references.
- `employee_sessions/`: native Hermes trajectories, work actions, file changes and private evaluation diagnostics.
- `daily/`: persistent enterprise, consumer and government snapshots.
- `checkpoint.json`: complete business state, queues and scheduler cursor.
- `computers/`: real employee workspaces and separate native agent states.
- `mirofish_simulation.db`: native OASIS evidence.
- `learner/`: exported observations, trajectories and rewards without private diagnostics.
- `REPORT.md` and `VALIDATION.json`: generated after the offline audit.

Completed checkpoints resume without replaying completed work. An `inflight.json` marker blocks automatic replay of interrupted work whose side effects may be uncertain. Such failures need reconciliation against native traces. The accepted integration artifact retains an early interrupted infrastructure attempt separately, rather than counting it as completed work or silently erasing its history. Its partial compute/work costs are outside reconciled completed-session utility totals.

Persona 8B data and derivatives retain the upstream non-commercial research terms. No RL training, weight updates, novelty result or advantage over memory baselines is claimed.
