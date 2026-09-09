"""World generation and transitions; never pass a World to a learner.

This module is the trusted simulator side of the observation boundary. Employee
beliefs, published evidence, and the policy actually in force are distinct.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import random


WORKFLOWS = ("onboarding", "renewal", "incident")
SEGMENTS = ("commercial", "regulated")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass
class Rule:
    id: str
    workflow: str
    scope: str
    valid_from: int
    valid_until: int | None
    published: int
    authority: str
    patch: dict
    reason: str

    def public(self):
        return asdict(self)


def resolve(rules, workflow, segment, day):
    """Fieldwise overlays: global then segment; publication != effective time.

    Corporate records are the only policy authority in this small domain.
    Expired exceptions cease to override the still-preserved base procedure.
    """
    applicable = [r for r in rules if r.workflow == workflow
                  and r.scope in ("*", segment) and r.authority == "policy_owner"
                  and r.valid_from <= day
                  and (r.valid_until is None or day < r.valid_until)]
    applicable.sort(key=lambda r: (r.scope != "*", r.valid_from, r.id))
    plan = {}
    additional_checks = set()
    for r in applicable:
        patch = deepcopy(r.patch)
        additional_checks.update(patch.pop('checks_add', []))
        plan.update(patch)
    if additional_checks:
        plan['checks'] = sorted(set(plan.get('checks', [])) | additional_checks)
    return plan


@dataclass
class Employee:
    id: str
    name: str
    workflow: str
    segment: str
    manager: str
    reading_delay: int
    communication: str
    trust: float = 0.8
    known: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    workflow: str
    segment: str
    owner: str
    customer: str
    created: int
    due: int
    value: float
    parent: str | None = None
    status: str = "pending"
    attempts: int = 0
    completed: int | None = None


def generate_blueprint(seed=7, days=84, enterprise_id="enterprise-0", drift=True):
    if days < 28:
        raise ValueError("Use at least 28 simulated days to retain separated changes.")
    rng = random.Random(seed)
    salt = rng.randrange(100, 999)
    employees = []
    for w in WORKFLOWS:
        for segment in SEGMENTS:
            employees.append(asdict(Employee(
                id=f"{w}-{segment}", name=f"{rng.choice(['Ari', 'Devi', 'Noor', 'Sam', 'Alex', 'Lee'])}-{len(employees)}",
                workflow=w, segment=segment, manager=f"{w}-lead-{salt}",
                reading_delay=rng.randint(1, 4),
                communication=rng.choice(["brief", "explanatory"])) ))
    rules = []
    for w in WORKFLOWS:
        rules.append(Rule(f"base-{w}", w, "*", 0, None, 0, "policy_owner",
                          {"approver": f"{w}-lead-{salt}", "checks": ["customer_check"],
                           "channel": f"{w}-desk", "endpoint": "workspace-v1", "redact": False},
                          "Initial operating procedure"))
    changes = []
    if drift:
        def at(fraction):
            return max(3, min(days - 4, int(days * fraction) + rng.choice([-1, 0, 1])))
        d1, d2, d3, d4, d5, d6, d7 = [at(p) for p in (.16, .29, .40, .51, .61, .72, .84)]
        changes = [
            Rule("regulated-review", "renewal", "regulated", d1, None, d1 - 2, "policy_owner",
                 {"approver": f"risk-lead-{salt}", "checks": ["customer_check", "risk_review"]},
                 "A regulated customer audit changes the review procedure"),
            Rule("tool-migration", "onboarding", "*", d2, None, d2 + 2, "policy_owner",
                 {"endpoint": "workspace-v2"}, "Operations deploys a new interface; documentation arrives late"),
            Rule("data-handling", "incident", "regulated", d3, None, d3, "policy_owner",
                 {"redact": True}, "Customer contract changes the incident disclosure boundary"),
            Rule("temporary-channel", "incident", "*", d4, d4 + max(3, days // 10), d4 - 1, "policy_owner",
                 {"channel": "incident-war-room"}, "A temporary outage moves coordination to a war room"),
            Rule("informal-rumor", "renewal", "commercial", d5, None, d5, "colleague",
                 {"approver": "retired-sales-lead"}, "A colleague repeats an obsolete approval shortcut"),
            Rule("reorganization", "renewal", "*", d6, None, d6 - 1, "policy_owner",
                 {"approver": f"revenue-lead-{salt}"}, "A reorganization changes the default approver; the regulated exception remains"),
            Rule("tool-rollback", "onboarding", "*", d7, None, d7, "policy_owner",
                 {"endpoint": "workspace-v1"}, "A failed migration is rolled back"),
        ]
    # All exogenous demand and random choices are drawn before policy execution.
    # Endogenous decisions never consume this RNG, preserving paired scenarios.
    arrivals = []
    for day in range(days):
        for i, w in enumerate(WORKFLOWS):
            segment = SEGMENTS[(day + i) % 2]
            arrivals.append(asdict(Task(
                id=f"job-{day}-{w}", workflow=w, segment=segment,
                owner=f"{w}-{segment}", customer=f"customer-{rng.randrange(12)}",
                created=day, due=day + rng.randint(2, 4), value=rng.choice([8., 10., 12.]))))
    result = {"schema_version": 1, "enterprise_id": enterprise_id,
              "name": f"{rng.choice(['Juniper', 'Harbor', 'Meridian'])} Services {salt}",
              "seed": seed, "days": days, "drift": drift, "employees": employees,
              "departments": list(WORKFLOWS), "rules": [r.public() for r in rules + changes],
              "arrivals": arrivals, "settlement_delay": 2}
    result["blueprint_hash"] = digest(result)
    return result


class World:
    def __init__(self, blueprint):
        self.blueprint = deepcopy(blueprint)
        self.day = -1
        self.employees = {e["id"]: Employee(**deepcopy(e)) for e in blueprint["employees"]}
        self.rules = [Rule(**deepcopy(r)) for r in blueprint["rules"]]
        self.tasks: dict[str, Task] = {}
        self.scheduled = deepcopy(blueprint["arrivals"])
        self.ledger = []
        self.outcomes = []
        self.events = []
        self.daily = []
        self.customers = {}
        self.total_utility = 0.
        self.human_minutes = 0.
        self.review_triggered = False
        self.failures = 0
        self.inboxes = {eid: [] for eid in self.employees}
        self.seen_notifications = {eid: set() for eid in self.employees}

    def expected(self, task):
        return resolve(self.rules, task.workflow, task.segment, self.day)

    def documents(self, employee):
        # Department ACL. Knowledge of a future announcement is allowed only
        # after publication, never because the generator knows the schedule.
        return [r for r in self.rules if r.workflow == employee.workflow and r.published <= self.day]

    def employee_belief(self, employee):
        # Employees can repeat a recent rumor and lag behind policy changes.
        plan = resolve([r for r in self.rules if r.id in employee.known],
                       employee.workflow, employee.segment, self.day)
        for r in self.rules:
            if r.id in employee.known and r.authority == "colleague" and r.scope == employee.segment:
                plan.update(deepcopy(r.patch))
        return plan

    def advance(self, day):
        if day != self.day + 1:
            raise ValueError("World time advances one day at a time.")
        self.day = day
        for item in list(self.ledger):
            if item["settles"] == day and not item["settled"]:
                item["settled"] = True
                self.total_utility += item["amount"]
                event = {"kind": "settlement", "day": day, "task_id": item["task_id"],
                         "owner": item["owner"], "reward": item["amount"],
                         "caused_by": item["session_id"]}
                self.events.append(event)
                self.inboxes[item["owner"]].append(event)
        for raw in self.scheduled:
            if raw["created"] == day:
                task = Task(**deepcopy(raw))
                self.tasks[task.id] = task
                self.events.append({"kind": "work_arrival", "day": day, "task_id": task.id,
                                    "caused_by": task.parent})
        for r in self.rules:
            if r.valid_from == day:
                self.events.append({"kind": "rule_effective", "day": day, "rule_id": r.id,
                                    "authority": r.authority, "reason": r.reason})
            if r.valid_until == day:
                self.events.append({"kind": "rule_expired", "day": day, "rule_id": r.id})
        for emp in self.employees.values():
            for r in self.documents(emp):
                delay = 0 if r.valid_from == 0 else emp.reading_delay
                if r.published + delay <= day and r.id not in emp.known:
                    emp.known.append(r.id)
                if r.id in emp.known and r.id not in self.seen_notifications[emp.id]:
                    self.seen_notifications[emp.id].add(r.id)
                    self.inboxes[emp.id].append({"kind": "notice", "day": day, "document": r.public()})
        for task in self.tasks.values():
            if task.status == "pending" and day > task.due:
                self.total_utility -= 0.5
                self.events.append({"kind": "lateness", "day": day, "task_id": task.id, "reward": -0.5})
                if day > task.due + 7:
                    task.status = "abandoned"
                    self.total_utility -= task.value
                    self.events.append({"kind": "abandonment", "day": day,
                                        "task_id": task.id, "reward": -task.value})

    def delegated_tasks(self):
        selected = []
        for emp in self.employees.values():
            candidates = [t for t in self.tasks.values() if t.owner == emp.id and t.status == "pending"]
            if not candidates:
                continue
            # Low trust causes employees to withhold delegation every other day.
            # Withheld work remains in the queue and incurs lateness; it cannot
            # disappear from the business denominator to improve an agent score.
            if emp.trust < 0.3 and self.day % 2:
                self.events.append({"kind": "delegation_withheld", "day": self.day, "employee": emp.id})
                continue
            selected.append(min(candidates, key=lambda t: (t.due, t.id)))
        return selected

    def record_failure(self, task, session_id):
        self.failures += 1
        emp = self.employees[task.owner]
        emp.trust = max(0.05, emp.trust - 0.12)
        # Minimal endogenous process evolution: repeated failed work leads to a
        # review protocol. Only enabled in drift worlds, starting next day.
        if (self.blueprint["drift"] and self.blueprint.get("endogenous_failure_rule", True)
                and self.failures >= 4 and not self.review_triggered):
            self.review_triggered = True
            rule = Rule("endogenous-review", "onboarding", "*", self.day + 1, None,
                        self.day + 1, "policy_owner", {"checks": ["customer_check", "peer_review"]},
                        "Repeated failed work causes operations to add peer review")
            self.rules.append(rule)
            self.events.append({"kind": "process_change_proposed", "day": self.day,
                                "rule_id": rule.id, "caused_by": session_id})

    def complete(self, task, session_id):
        task.status = "completed"
        task.completed = self.day
        emp = self.employees[task.owner]
        emp.trust = min(1., emp.trust + 0.04)
        customer = self.customers.setdefault(task.customer, {"onboardings": 0, "renewals": 0, "incidents_resolved": 0})
        customer[{"onboarding": "onboardings", "renewal": "renewals", "incident": "incidents_resolved"}[task.workflow]] += 1
        amount = max(0., task.value - max(0, self.day - task.due))
        self.ledger.append({"task_id": task.id, "owner": task.owner, "session_id": session_id,
                            "settles": self.day + self.blueprint["settlement_delay"],
                            "settled": False, "amount": amount})
        if task.workflow == "onboarding" and self.blueprint.get("automatic_renewals", True):
            followup = Task(task.id + ":renewal", "renewal", task.segment,
                            f"renewal-{task.segment}", task.customer, self.day + 7,
                            self.day + 10, task.value, task.id)
            self.scheduled.append(asdict(followup))
        self.events.append({"kind": "work_completed", "day": self.day, "task_id": task.id,
                            "caused_by": session_id, "settles": self.day + self.blueprint["settlement_delay"]})

    def snapshot(self):
        return {"day": self.day, "tasks": [asdict(t) for t in self.tasks.values()],
                "employees": [asdict(e) for e in self.employees.values()],
                "rules": [r.public() for r in self.rules], "ledger": deepcopy(self.ledger),
                "customers": deepcopy(self.customers), "total_utility": self.total_utility}

    def fork(self):
        """A complete counterfactual clone, including queued and delayed effects."""
        return deepcopy(self)
