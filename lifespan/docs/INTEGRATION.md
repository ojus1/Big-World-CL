# Integration contracts and next implementation steps

The v0.2 PoC now implements the Persona 8B and MiroFish path. See [the current implementation and run instructions](../README.md). `personas.py` imports six actual synthetic dataset records; `mirofish.py` creates the native project, graph, profiles and OASIS runtime; `integrated.py` couples employee decisions to the enterprise; `llm_agent.py` executes real model-generated work actions. The interface proposal below is retained as the original design; its first assistant/employee integration steps are now implemented, while RL training and broader evaluation remain future work.

Native MiroFish interviews default to not retaining interview history. The integration supplies persistent employee notes and actual outcome feedback on every call. Workplace colleague messages are validated and routed by the adapter. We do not assume that the social recommender implements enterprise permissions or that native interview memory persists automatically.

## Responsibility boundary

The inspected local MiroFish code has an `OasisAgentProfile` representation, profile generation and graph-memory services, and Twitter/Reddit simulation modes. We should adapt its participant and interaction machinery, while keeping business-state execution in the lifespan engine. Social conversation logs alone do not implement workplace permissions, workflow state, or business rewards.

| Component | May read | May produce | Cannot decide unilaterally |
|---|---|---|---|
| World compiler | Enterprise specification, approved task seeds, persona priors | Validated initial state and event mechanisms | Whether an arbitrary future agent action succeeds |
| Employee simulator | That employee's role, current beliefs, authorized observations, goals, workload and received outcomes | Message, clarification, delegation decision, proposed work action or process change | Hidden future events, other employees' private knowledge, committed state changes |
| Assistant | Current employee session, its own permitted history and adaptive state, tool responses | Tool actions, messages and allowed updates to its own state | Private evaluator state or synthetic future transcripts |
| Execution engine | Current canonical state and action | Tool results, state mutations, delayed consequences | Free-text invented success unsupported by state |
| Evaluator | World, execution log, delayed outcomes, experiment contract | Rewards and diagnostic metrics | Additional hidden hints in test observations |

## Employee simulator proposal

Send a constrained view, for example:

```json
{
  "schema_version": 1,
  "day": 23,
  "employee_id": "renewal-regulated",
  "role": "regulated-account renewal owner",
  "local_goals": ["complete the pending renewal without breaching review requirements"],
  "received_evidence": [],
  "known_procedures": [],
  "work_queue": [{"task_id": "job-23-renewal", "due": 26}],
  "recent_observed_outcomes": [],
  "collaboration_state": {"trust": 0.6, "available_minutes": 12},
  "allowed_actions": ["message_assistant", "ask_colleague", "delegate", "propose_process_change"]
}
```

Empty arrays in this example represent omitted example content, not access to the full enterprise state. Populate them from the projection layer, never from tomorrow's event schedule. A persona profile may be persistent, but its current knowledge must still follow observable events.

Require a typed response:

```json
{
  "employee_id": "renewal-regulated",
  "action": "message_assistant",
  "content": "The account lead rejected the renewal. Please check who owns this review now.",
  "references": ["approval-result-17"],
  "proposed_state_change": null
}
```

Validate entity references, available evidence, permissions, time, and action constraints before accepting it. Reject a claimed past conversation that never happened. Proposed changes become events only after the engine validates their authority and preconditions. Log rejected proposals separately from employee outcomes.

A message generator must not reward the assistant. For content-level work such as drafting an incident report, use a separate task-owned verifier and calibrate any model judge against human judgments. Typed rule constraints remain executable.

## Assistant adapter

The current interface is:

```python
observation = deepcopy(session.observation)
agent.run(observation, session.step)
```

`ReferenceAgent.run` can be replaced with an LLM tool loop. The initial observation includes a user request, a permitted employee/task view, unread notices and received settlement observations, and tool descriptions. It contains no current expected procedure, future schedule, regime label, or hidden score.

For a local model server, an adapter can translate the seven actions into tool schemas and return JSON actions to `SessionEnv.step`. For real agent harnesses with terminal access, expose the same interface through a local RPC service and isolate the trusted simulator process. The present Python separation is insufficient against arbitrary introspection.

Run one persistent assistant state per employee and enterprise. Session context may reset; declared memory or weights must persist. Export and version those states independently. Shared enterprise memory should be an explicit experimental condition with access control, rather than an accidental global dictionary.

Log model identifier, decoding settings, exact prompts, tool schemas, token counts, update operations, and persistent-state hashes. Generator models, employee models, assistant models, and judges should have distinct roles; evaluate across more than one simulator model to check whether gains depend on its style.

## RL collection and training boundary

Tool calls return `(observation, reward, terminated, truncated, info)`. In the PoC, `terminated` is false within a lifespan, and `info.session_done` switches the active session. A tool-budget truncation ends that session; unfinished work persists. The finite world horizon is recorded separately as a truncation.

Daily shared business rewards occur between sessions. They include settlements, lateness, and abandonment and must be merged chronologically with tool costs. Inbox messages may refer to the same settlements; do not count them twice. A production multi-agent trainer needs to declare whether it optimizes team reward, individual reward, or a credit-assignment estimator. No such optimizer exists in the PoC.

For weight or recurrent-state learning:

1. Freeze a training/validation/test generator split before collecting trajectories.
2. Collect chronological lifespans with the currently deployed learner and employee policies.
3. Preserve hidden adaptive state across sessions; carry the appropriate value bootstrap across session boundaries.
4. Compute returns over a horizon long enough to include delayed work outcomes, or bootstrap with explicit censoring.
5. Update on training lifespans and select hyperparameters on validation lifespans only.
6. Evaluate the selected update rule on fresh test enterprises with chronological feedback available but no cross-test tuning.

For skill or memory learning, follow the same event chronology and budget rules. Record update actions and resulting future behavior. A natural-language memory entry is not itself a business completion.

## Ordered next steps

1. **Add an LLM assistant adapter** against the current tool contract and establish initial task competence. Do not change the world engine while comparing memory substrates.
2. **Implement matched probes** for evidence-relative recovery, unaffected-skill retention, and recurring regimes. Add a stateless-with-retrieval baseline and persistent-state reset ablations.
3. **Add workflow topology changes**: prerequisite insertion, rerouted handoffs, schema changes requiring transformed payloads, and competing goals under resource budgets.
4. **Connect employee simulation** through MiroFish's persona and interaction machinery. Begin with six employees and validate each proposed event against the existing engine.
5. **Introduce multiple enterprise structures**, then hold out causal compositions and workflows. Parameter changes in the current single template are inadequate for transfer claims.
6. **Train adaptation actions**, initially selecting reuse, inspect, ask, test, revise and defer; later expand the action and update spaces. Compare learned decisions with the fixed heuristic currently named `adaptive`.
7. **Calibrate and stress test** using expert-reviewed or consented enterprise process histories and independently implemented employee simulators.

The useful integration milestone is one three-week trace in which an employee learns a changed procedure from another person, their assistant initially lacks it, business feedback changes the collaboration, and a later task verifies selective adaptation. Scale should follow that demonstration.
