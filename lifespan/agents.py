"""Transparent reference controllers, not trained LLMs or novel algorithms."""
from copy import deepcopy
from .world import Rule, resolve


POLICIES = ("frozen", "recency", "scoped", "adaptive", "revalidate")


class ReferenceAgent:
    def __init__(self, mode):
        if mode not in POLICIES:
            raise ValueError(mode)
        self.mode = mode
        # One persistent assistant per employee. No cross-employee memory pool.
        self.memory = {}
        self.last_checked = {}
        self.invalidated = set()

    def ingest(self, employee, docs):
        bank = self.memory.setdefault(employee, {})
        for doc in docs:
            if self.mode != "frozen" or doc["valid_from"] == 0:
                bank[doc["id"]] = deepcopy(doc)

    def procedure(self, observation):
        employee = observation["employee"]["id"]
        task = observation["task"]
        docs = list(self.memory.get(employee, {}).values())
        if self.mode == "recency":
            # Deliberately simple last-write retrieval: no scope, authority or
            # expiry resolution. This is not a claim about all RAG systems.
            plan = {}
            for doc in sorted(docs, key=lambda d: (d["published"], d["id"])):
                if doc["workflow"] == task["workflow"]:
                    plan.update(deepcopy(doc["patch"]))
            return plan
        return resolve([Rule(**d) for d in docs], task["workflow"], task["segment"], observation["day"])

    def run(self, observation, step):
        """The learner receives only a JSON observation and callable tool API."""
        employee = observation["employee"]["id"]
        for item in observation["inbox"]:
            if item["kind"] == "notice":
                self.ingest(employee, [item["document"]])
        def search():
            obs, _, _, _, info = step({"tool": "documents.search"})
            if obs["result"].get("ok"):
                self.ingest(employee, obs["result"]["documents"])
                self.last_checked[employee] = observation["day"]
                self.invalidated.discard(employee)
            return not info["session_done"]
        should_search = self.mode == "revalidate" or (self.mode == "adaptive" and (
            employee in self.invalidated or observation["day"] - self.last_checked.get(employee, 0) >= 7))
        if should_search and not search():
            return
        attempts = 2 if self.mode in ("adaptive", "revalidate") else 1
        for attempt in range(attempts):
            plan = self.procedure(observation)
            if not plan:
                step({"tool": "session.end"})
                return
            actions = [{"tool": "draft.prepare", "args": {"channel": plan["channel"], "redact": plan["redact"]}}]
            actions += [{"tool": "check.perform", "args": {"name": name}} for name in plan["checks"]]
            actions += [{"tool": "approval.request", "args": {"approver": plan["approver"]}},
                        {"tool": "work.commit", "args": {"endpoint": plan["endpoint"]}}]
            failed = False
            for action in actions:
                result, _, _, _, info = step(action)
                if info["session_done"]:
                    return
                if not result["result"].get("ok"):
                    failed = True
                    self.invalidated.add(employee)
                    break
            if failed and attempt + 1 < attempts:
                if not search():
                    return
            else:
                break
        step({"tool": "session.end"})
