"""JSON observation/action interface with session and lifespan boundaries.

Only observations and tool results may be serialized to a learner. Private World
objects and diagnostic audit records belong in the trusted evaluator process.
"""
from copy import deepcopy


TOOLS = {
    "documents.search": "Read published procedures for your department (includes historical and announced versions).",
    "employee.ask": "Ask the employee for their understanding; it can be stale or mistaken.",
    "draft.prepare": "Start/restart a work artifact. Arguments: channel, redact (boolean).",
    "check.perform": "Execute a named check. Argument: name.",
    "approval.request": "Request actual approval. Argument: approver.",
    "work.commit": "Commit the prepared artifact to a tool endpoint. Argument: endpoint.",
    "session.end": "Stop this session, leaving unfinished work in the queue.",
}


class SessionEnv:
    def __init__(self, world, task, max_steps=18, employee_message=None, employee_ask=None, shared_inbox=None):
        self._world = world
        self._task = task
        self.session_id = f"{world.blueprint['enterprise_id']}:{world.day}:{task.id}:{task.attempts}"
        self.max_steps = max_steps
        self.steps = 0
        self.done = False
        self.success = False
        self.draft = None
        self.checks = set()
        self.approved = False
        self.cost = 0.
        self.queries = 0
        self.human_minutes = 0.
        self.trace = []
        self.first_plan_correct = None
        self.failed_operations = 0
        self._charged_failure = False
        self._employee_ask = employee_ask
        task.attempts += 1
        emp = world.employees[task.owner]
        self.observation = {
            "session_id": self.session_id, "day": world.day,
            "employee": {"id": emp.id, "name": emp.name, "workflow": emp.workflow, "segment": emp.segment},
            "task": {"id": task.id, "workflow": task.workflow, "segment": task.segment,
                     "customer": task.customer, "due": task.due, "parent": task.parent},
            "message": (f"Please handle {task.workflow} for {task.customer}. "
                        f"This is a {task.segment} account, due on day {task.due}. "
                        + ("Keep the update brief." if emp.communication == "brief" else
                           "Explain any changes you make to our process.")),
            "inbox": deepcopy(world.inboxes[emp.id]),
            "tools": TOOLS,
        }
        world.inboxes[emp.id].clear()
        if employee_message is not None:
            self.observation["message"] = employee_message
        if shared_inbox is not None:
            self.observation["inbox"] = deepcopy(shared_inbox)
        self.trace.append({"type": "observation", "observation": deepcopy(self.observation)})

    def _failure(self):
        self.failed_operations += 1
        if not self._charged_failure:
            self._charged_failure = True
            self.cost += 1.
            self._world.total_utility -= 1.
            self._world.record_failure(self._task, self.session_id)

    def step(self, action):
        """Return (observation, reward, terminated, truncated, info).

        terminated is always False: a session boundary does not terminate the
        enterprise. session_done in info requests the next employee session.
        Truncation denotes the session tool budget. Business settlement is later.
        """
        if self.done:
            raise RuntimeError("Session already ended")
        if not isinstance(action, dict):
            action = {"tool": "invalid_action"}
        self.steps += 1
        world, task = self._world, self._task
        before = self.cost
        cost = .03
        tool = action.get("tool")
        args = action.get("args", {})
        result = {"ok": False, "error": "unknown_tool"}
        if not isinstance(args, dict):
            args = {}
            tool = "invalid_arguments"
        if tool == "documents.search":
            cost += .35
            self.queries += 1
            result = {"ok": True, "documents": [r.public() for r in world.documents(world.employees[task.owner])]}
        elif tool == "employee.ask":
            cost += .8
            self.human_minutes += 2
            world.human_minutes += 2
            if self._employee_ask is not None:
                result = {"ok": True, "response": self._employee_ask(args.get("question", "Please clarify the current procedure.")),
                          "source": "MiroFish employee; may be mistaken"}
            else:
                result = {"ok": True, "understanding": world.employee_belief(world.employees[task.owner]),
                          "source": "employee recollection; verify disputed procedures with their owner"}
        elif tool == "draft.prepare":
            if isinstance(args.get("channel"), str) and isinstance(args.get("redact"), bool):
                self.draft = {"channel": args["channel"], "redact": args["redact"]}
                self.checks.clear()
                self.approved = False
                result = {"ok": True, "artifact_id": task.id + ":draft"}
            else:
                result = {"ok": False, "error": "channel_and_boolean_redact_required"}
        elif tool == "check.perform":
            if self.draft is None:
                result = {"ok": False, "error": "prepare_artifact_first"}
            elif args.get("name") in ("customer_check", "risk_review", "peer_review", "jurisdiction_review"):
                self.checks.add(args["name"])
                result = {"ok": True, "check_recorded": args["name"]}
            else:
                result = {"ok": False, "error": "unknown_check"}
        elif tool == "approval.request":
            if self.draft is None:
                result = {"ok": False, "error": "prepare_artifact_first"}
            elif args.get("approver") == world.expected(task)["approver"]:
                self.approved = True
                result = {"ok": True, "approval_record": task.id + ":approval"}
            else:
                self.first_plan_correct = False if self.first_plan_correct is None else self.first_plan_correct
                self._failure()
                result = {"ok": False, "error": "recipient_does_not_own_this_approval"}
        elif tool == "work.commit":
            expected = world.expected(task)
            correct = bool(self.draft is not None and self.approved
                           and expected["channel"] == self.draft["channel"]
                           and expected["redact"] == self.draft["redact"]
                           and set(expected["checks"]).issubset(self.checks)
                           and args.get("endpoint") == expected["endpoint"])
            if self.first_plan_correct is None:
                self.first_plan_correct = correct
            if correct:
                self.success = self.done = True
                world.complete(task, self.session_id)
                result = {"ok": True, "status": "completed", "task_id": task.id,
                          "payment_status": "pending_settlement"}
            else:
                self._failure()
                result = {"ok": False, "error": "work_rejected",
                          "message": "The artifact, checks, approval, or interface do not meet the current procedure."}
        elif tool == "session.end":
            self.done = True
            result = {"ok": True, "status": "left_in_queue"}
        self.cost += cost
        world.total_utility -= cost
        truncated = self.steps >= self.max_steps and not self.done
        if truncated:
            self.done = True
        reward = -(self.cost - before)
        info = {"session_done": self.done, "lifespan_done": False,
                "success": self.success, "session_id": self.session_id}
        obs = {"day": world.day, "tool": tool, "result": result}
        self.trace.append({"type": "transition", "action": deepcopy(action), "observation": deepcopy(obs),
                           "reward": round(reward, 6), "terminated": False, "truncated": truncated, "info": info})
        return deepcopy(obs), reward, False, truncated, info

    def diagnostic(self):
        """Privileged offline analysis; never included in the agent trace."""
        return {"session_id": self.session_id, "day": self._world.day,
                "task_id": self._task.id, "employee": self._task.owner,
                "workflow": self._task.workflow, "segment": self._task.segment,
                "success": self.success, "first_plan_correct": self.first_plan_correct is True,
                "queries": self.queries, "human_minutes": self.human_minutes,
                "cost": round(self.cost, 6), "failed_operations": self.failed_operations,
                "expected_procedure": self._world.expected(self._task)}
