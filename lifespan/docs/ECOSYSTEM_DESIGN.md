# Persistent economies, changing objectives, and employee computers

The v0.3 PoC models two competing service enterprises, one government agency, three consumers and six frontline employees. Twelve distinct pinned Persona 8B records condition native MiroFish/OASIS actors. Each frontline employee has one native Hermes `AIAgent`, a separate profile, and a persistent bubblewrap computer. Organization actors represent collective decisions; they are not additional frontline employees.

The kernel owns business truth and authority. MiroFish chooses institutional, consumer and employee actions. Hermes chooses executable work and its own memory/file revisions. These are separate roles even when they use the same underlying model.

## State and objective evolution

Let the persistent world be

\[
S_t=(Z_t,\{B_t^j,G_t^j,P_t^j\}_j,\{U_t^c\}_c,Q_t,\{H_t^i,F_t^i,K_t^i,M_t^i\}_i).
\]

- `Z`: geopolitical and supply conditions.
- `B`: enterprise cash, commitments, backlog, public offers and realized outcomes.
- `G`: enterprise objectives, target markets, priorities and capacity allocation.
- `P`: published procedures, actual policy authority, effective dates and expiry.
- `U`: consumer budgets, pending orders, provider history and satisfaction.
- `Q`: queued notices, policy activation, orders, complaints and settlement.
- `H`: employee beliefs, notes, messages and observed collaboration outcomes.
- `F`: the employee's actual files, including stale copies and revised deliverables.
- `K`: computer runtime, process namespace, working directory and background processes.
- `M`: the employee's Hermes conversation, memory files and skills.

Enterprise objectives are endogenous:

\[
a_t^{org}\sim\pi_{org}(O_t^{org},H_t^{org}),\qquad
G_{t+1}^{org}=T_G(G_t^{org},a_t^{org}).
\]

The institution observes competitors' public offers and declared strategy decisions/reasons, its own cash and operating results, received complaints and public world conditions. It does not observe competitors' costs, their employees' conversations or future shocks. A reason and visible event references accompany each decision. The simulator checks authority and executes consequences; a plausible paragraph by itself changes nothing.

The generation problem is a partially observed multi-agent decision process with variable-length work sessions. Session completion does not terminate the world. A learner action changes a file or business object now and may change consumer behavior, management decisions and later tasks several days later.

## Executable reactions

| Decision | Persistent consequence |
|---|---|
| Company changes price | Consumers see the new offer; new orders reserve that price; realized payments change cash. |
| Company changes objective/priority | Capacity is limited to two work sessions per company per day. Priority affects which employee works; cost control selects higher-value pending tasks. Objective-dependent utility weights apply to new commitments. |
| Company exits a market | New consumers in that market cannot place orders there; existing commitments remain due. |
| Company changes route | Costs cash and utility; next-day endpoint requirements change. An alternate route avoids the simulated cross-border supply delay on new orders. |
| Government enhances review | Both regulated enterprises need jurisdiction review and redacted artifacts, from the next day until expiry. Withdrawal ends the agency overlay while preserving company routing choices. |
| Consumer purchases/switches | Creates a real work item after any supply delay and reserves budget. |
| Consumer complains | Requires an actual overdue commitment; the agency receives the complaint next day. |
| Hermes commits a file successfully | Completes the task; a later payment changes enterprise cash and consumer budget/satisfaction. |
| Employee proposes peer review after failure | Can introduce an additional local procedure; the proposal and outcome are recorded. |

The corridor disruption and subsequent reopening are **exogenous fictional initial scenario inputs**. Companies' objectives, regulatory responses and consumer choices are model decisions. The kernel does not force a particular response to a shock. The default calendar contains a disruption on day 4 and reopening on day 11; longer experiments should vary mechanism, timing, magnitude, and visibility, not merely repeat this scenario.

Institutional decision events publish the chosen objective, route, offer and short reason; working notes and raw internal ledgers are not published. This disclosure policy is a prototype assumption. Companies decide from a common public-market snapshot at each decision epoch. Consumers then see the resulting offers. Work executes under the capacity limit. This phase ordering is explicit and is part of the simulator distribution, not a claim about realistic institutional timing.

## Computer and Hermes architecture

```text
Trusted simulation process
  ├─ native MiroFish: institutions, consumers, employees
  ├─ canonical business/policy kernel and delayed effects
  └─ six separate Hermes worker processes
       ├─ own HERMES_HOME: conversation database, memory, skills
       ├─ enterprise_action RPC → trusted work validator
       └─ native Hermes terminal/file tools → Bubblewrap BaseEnvironment adapter
            └─ persistent employee namespace
                 /usr                  shared read-only system tools
                 /workspace            only this employee's mutable files
                 /home/employee        this employee's persistent OS home
                 /tmp                  namespace-local runtime scratch
                 /proc                 only this sandbox's processes
```

Bubblewrap constructs Linux namespaces; it is not a VM and does not virtualize a separate kernel. Its protection depends on the configured mounts and namespace flags. This implementation unshares mount, user, PID, IPC, UTS and network namespaces, clears the guest environment, drops capabilities, and mounts only the assigned employee's mutable directories plus system binaries and the small sandbox supervisor. [Bubblewrap upstream documentation](https://github.com/containers/bubblewrap).

A supervisor stays alive inside each employee namespace. Native Hermes file operations and terminal commands run through its socket. Shell working-directory/environment snapshots use Hermes' `BaseEnvironment`; background processes can survive separate commands and simulated workdays. The model transport remains outside the namespace so inference credentials need not enter the employee computer. The simulator's private world, other employees' directories, Docker socket and host home are absent.

Hermes has no built-in bubblewrap backend in the installed revision. Our adapter installs a `BaseEnvironment` in the worker's environment cache and replaces that worker's environment factory. Native `read_file`, `write_file`, `patch` and `terminal` remain Hermes tools. A fail-closed factory returns only that employee's sandbox. The profile's `terminal.backend: local` is the native dispatch setting used by the adapter, **not permission for native host execution**. Real native-tool tests verify the resulting execution location.

The earlier Docker adapter is retained as an optional code path. In the installed Hermes revision, arbitrary `HERMES_HOME` directories all have profile name `custom`; ordinary task IDs also collapse to `default`. Its native benchmark environment override API is therefore necessary to avoid cross-profile Docker reuse. This was found during integration and the affected exploratory runs were not used as the accepted bubblewrap experiment.

## File semantics and audit trail

An employee's inbox, company objectives and published procedure copies are materialized as JSON files. Refreshing those files does not reset notes, deliverables, skills or memory. A deliverable must exist under `/workspace/deliverables`, contain the matching task ID and a nonempty work product, and declare its channel, endpoint and redaction status. Preparing it binds a content hash; modifying the file after approval requires preparing and checking it again. Only a successful trusted commit changes business state.

Workspace snapshots record file hashes, sizes, modes and symbolic links. Content-addressed blobs retain both old and new bytes. Every work session records its before/after filesystem manifests, delta, business tool trace, native Hermes trajectory and computer state. Native memory and skills are recorded separately from the employee workspace. A symbolic link cannot cause the trusted artifact reader to follow a path into another employee's host directory.

The PoC's business checks are simplified executable checks against synthetic records and procedure fields. It does not yet evaluate substantive legal analysis, arbitrary reports, software changes or open-ended semantic quality. A successful commit is a result under this narrow verifier, not evidence of general professional competence.

## Lifespan generator

1. Sample institutional structure, initial obligations, market relationships, capacity, a world-shock process and distinct persona records. Assign organizational roles separately from persona demographics.
2. Compile native MiroFish profiles and start one Hermes/computer pair per frontline employee.
3. Advance the shared calendar. Deliver only due events, activate/expire policy overlays, settle successful work and penalize delay.
4. Construct authorized institutional observations. Query native actors for decisions and reject invalid actions. Record their evidence and execute the resulting state changes.
5. Construct each selected employee's view from received information, prior notes and actual outcomes. The employee decides what to delegate and communicate.
6. Publish authorized files. Resume that employee's own Hermes instance. Run real file/shell operations and trusted business tools until completion, deferral or the bounded session limit.
7. Record changed files and business state. Retain human and assistant state; schedule downstream consequences. Checkpoint at safe boundaries.
8. Continue until the lifespan horizon, retaining pending commitments and unsettled value in the final state.

`checkpoint.json` includes the complete business transition state, queues, notes and scheduler cursor. Completed checkpoints can resume with the same employee files and native Hermes histories. `inflight.json` marks an interrupted work session whose effects may not yet be reconciled; the runner refuses to silently replay it. Disk state persists across supervisor restarts, while process state and `/tmp` do not. This is not a full VM snapshot/replay system.

## Training and evaluation contract

The immediate artifact is a training-environment generator and recorded experience, not a trained lifelong model. It can support SFT or RL only after an explicit training loop is added.

For RL, expose authorized employee observations, filesystem tools and work tools. Treat the rest of the economy as a reacting environment. Rewards must include delayed business value, obligations left pending, errors, human help, execution cost and strategic constraints. The current business utility is in simulation units; API dollars and wall-clock time must be logged separately before cost-sensitive claims.

Changing management goals must be observed through legitimate organizational communication. The assistant must not rewrite its own success criteria. Evaluation should compare behavior under stable goals, announced goal changes, delayed announcements, temporary exceptions, conflicting evidence and reversals. Scores should include adaptation delay, stale-procedure reuse, unnecessary relearning, retained useful skills, completed obligations and cumulative return.

A defensible research contribution would require controlled interventions: identical initial files/personas/shocks, separate re-simulation of endogenous institutional and consumer decisions for each learner, and held-out change mechanisms. Never replay another learner's downstream customer decisions as though they were fixed external inputs. Compare frozen memory, recency overwrite, scoped/versioned skills, reward-trained memory policies and online state/weight methods with matched information and compute.

## Current limits

This is one hand-specified economic domain with small populations and bounded action menus. Institutional realism, persona causal influence and benchmark novelty are unvalidated. The same model family drives environment actors and Hermes, which creates correlated failure risk. Native MiroFish interviews do not automatically retain interview history in this setup; the adapter explicitly re-supplies durable notes and observed outcomes. Social-platform recommendation dynamics do not determine workplace communication routing. No RL training, weight updates, arbitrary application GUI, separate guest kernel, filesystem quota, or exact process checkpoint restore is claimed.

The accepted live integration run includes early adapter revisions and one audited infrastructure interruption. Its native evidence is retained, but it is not a fixed-code controlled research trial. The current source adds composable mandatory checks; the run's private rule snapshots are the authority for interpreting that recorded trajectory.
