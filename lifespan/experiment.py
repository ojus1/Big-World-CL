"""Reproducible paired reference runs and artifact export."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
from statistics import mean

from .agents import POLICIES, ReferenceAgent
from .environment import SessionEnv
from .world import World, generate_blueprint


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def run_lifespan(blueprint, mode, output=None, collect_traces=True):
    world = World(blueprint)
    agent = ReferenceAgent(mode)
    audits, traces, rewards = [], [], []
    for day in range(blueprint["days"]):
        before = world.total_utility
        world.advance(day)
        # Trainer-visible shared business reward; no privileged event labels.
        rewards.append({"type": "day_transition", "day": day,
                        "reward": round(world.total_utility - before, 6),
                        "terminated": False, "truncated": False})
        sessions = []
        for task in world.delegated_tasks():
            env = SessionEnv(world, task)
            agent.run(deepcopy(env.observation), env.step)
            audit = env.diagnostic()
            audits.append(audit)
            sessions.append(audit)
            if collect_traces:
                traces.append({"enterprise_id": blueprint["enterprise_id"], "policy": mode,
                               "session_id": env.session_id, "employee_id": task.owner,
                               "day": day, "events": env.trace})
        world.daily.append({"day": day, "sessions": len(sessions),
                            "first_plan_success": mean(a["first_plan_correct"] for a in sessions) if sessions else None,
                            "completion": mean(a["success"] for a in sessions) if sessions else None,
                            "cumulative_utility": round(world.total_utility, 6),
                            "backlog": sum(t.status == "pending" for t in world.tasks.values()),
                            "mean_employee_trust": round(mean(e.trust for e in world.employees.values()), 6)})
    rewards.append({"type": "lifespan_boundary", "day": blueprint["days"], "reward": 0,
                    "terminated": False, "truncated": True,
                    "reason": "finite observation window; pending consequences retained in private snapshot"})
    root_tasks = [t for t in world.tasks.values() if t.parent is None]
    metrics = {
        "enterprise_id": blueprint["enterprise_id"], "policy": mode,
        "blueprint_hash": blueprint["blueprint_hash"], "days": blueprint["days"],
        "employees": len(world.employees), "sessions": len(audits),
        "root_tasks": len(root_tasks), "root_completed": sum(t.status == "completed" for t in root_tasks),
        "root_completion_rate": mean(t.status == "completed" for t in root_tasks),
        "session_completion_rate": mean(a["success"] for a in audits) if audits else 0,
        "first_plan_success_rate": mean(a["first_plan_correct"] for a in audits) if audits else 0,
        "net_utility": round(world.total_utility, 6),
        "net_utility_per_root_task": round(world.total_utility / len(root_tasks), 6),
        "queries": sum(a["queries"] for a in audits), "human_minutes": world.human_minutes,
        "backlog": sum(t.status == "pending" for t in world.tasks.values()),
        "abandoned": sum(t.status == "abandoned" for t in world.tasks.values()),
        "completed_followups": sum(t.status == "completed" and t.parent is not None for t in world.tasks.values()),
        "unsettled_value": sum(e["amount"] for e in world.ledger if not e["settled"]),
        "mean_employee_trust": mean(e.trust for e in world.employees.values()),
        "endogenous_review_triggered": world.review_triggered,
    }
    if output:
        output = Path(output)
        write_json(output / "metrics.json", metrics)
        write_jsonl(output / "learner" / "sessions.jsonl", traces)
        write_jsonl(output / "learner" / "business_rewards.jsonl", rewards)
        write_jsonl(output / "private" / "session_audits.jsonl", audits)
        write_jsonl(output / "private" / "world_events.jsonl", world.events)
        write_json(output / "private" / "final_state.json", world.snapshot())
        write_json(output / "daily.json", world.daily)
    return metrics, world, audits, traces


def counterfactual_example(blueprint):
    """Same live snapshot, different actions; contrast includes delayed effects."""
    world = World(blueprint)
    agent = ReferenceAgent("revalidate")
    target_day = next(r["valid_from"] for r in blueprint["rules"] if r["id"] == "regulated-review")
    while world.day < target_day:
        world.advance(world.day + 1)
        for task in world.delegated_tasks():
            env = SessionEnv(world, task)
            agent.run(deepcopy(env.observation), env.step)
    # Insert the same controlled probe into a factual snapshot, and fork both
    # world AND assistant memory. This is a diagnostic intervention, not demand.
    from .world import Task
    probe = Task("controlled-probe", "renewal", "regulated", "renewal-regulated",
                 "counterfactual-customer", world.day, world.day + 2, 10.)
    world.tasks[probe.id] = probe
    old_rule = next(r for r in world.rules if r.id == "base-renewal")
    results = {}
    for label in ("reuse_old_procedure", "validate_and_adapt"):
        branch = world.fork()
        policy = deepcopy(agent)
        if label == "reuse_old_procedure":
            policy.mode = "frozen"
            policy.memory[probe.owner] = {old_rule.id: old_rule.public()}
        env = SessionEnv(branch, branch.tasks[probe.id])
        before = branch.total_utility
        policy.run(deepcopy(env.observation), env.step)
        immediate_delta = branch.total_utility - before
        for _ in range(blueprint["settlement_delay"]):
            branch.advance(branch.day + 1)
        # Report only probe-attributable utility, not background branch accruals.
        settlement = sum(e["amount"] for e in branch.ledger if e["task_id"] == probe.id and e["settled"])
        results[label] = {"audit": env.diagnostic(), "probe_utility": round(immediate_delta + settlement, 6),
                          "events": env.trace, "status": branch.tasks[probe.id].status}
    return {"description": "Controlled approval-change probe from the same persisted world and assistant snapshot.",
            "day": world.day, "results": results}


def report_text(metrics):
    grouped = defaultdict(list)
    for row in metrics:
        grouped[row["policy"]].append(row)
    lines = ["# Reference-controller smoke experiment", "",
             "These are deterministic simulator checks, not LLM results or evidence of a new learning algorithm.", "",
             "Every controller starts from the same generated enterprises and exogenous demand. Actions can change later workloads and procedures.", "",
             "| Controller | Sessions | Root work completed | First plan correct | Net utility / root job | Document queries | Abandoned work |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for policy, rows in grouped.items():
        sessions = sum(r["sessions"] for r in rows)
        roots = sum(r["root_tasks"] for r in rows)
        lines.append(f"| {policy} | {sessions} | {sum(r['root_completed'] for r in rows)/roots:.1%} | "
                     f"{sum(r['first_plan_success_rate']*r['sessions'] for r in rows)/sessions:.1%} | "
                     f"{sum(r['net_utility'] for r in rows)/roots:.2f} | {sum(r['queries'] for r in rows)} | "
                     f"{sum(r['abandoned'] for r in rows)} |")
    lines += ["", "Net utility includes settled work value, tool and validation costs, failed-operation penalties, lateness, and abandonment. Follow-up work can add value. Units are arbitrary and fixed in source, not money estimates.", "",
              "Root work completion uses common exogenous arrivals as its denominator. Session success has an endogenous denominator: retries and withheld delegation change the number of sessions.", "",
              "The finite horizon leaves unsettled value and pending jobs; metrics.json reports both. These outcomes are censored, not declared failures or free successes.", "",
              "The reference controllers parse structured policy evidence. This does not test natural-language understanding, weight updates, learned memory, or realistic employee simulation.", ""]
    return "\n".join(lines)


def demo(out, seed=7, days=84, enterprises=3, policies=POLICIES, drift=True):
    out = Path(out)
    if enterprises < 1:
        raise ValueError("enterprises must be positive")
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Output directory is not empty: {out}. Choose a fresh directory.")
    all_metrics = []
    blueprints = []
    for i in range(enterprises):
        bp = generate_blueprint(seed + i * 1009, days, f"enterprise-{i}", drift)
        blueprints.append(bp)
        write_json(out / "private" / "blueprints" / f"enterprise-{i}.json", bp)
        for mode in policies:
            metrics, *_ = run_lifespan(bp, mode, out / "runs" / mode / f"enterprise-{i}")
            all_metrics.append(metrics)
    if drift:
        write_json(out / "private" / "counterfactual.json", counterfactual_example(blueprints[0]))
    write_json(out / "metrics.json", all_metrics)
    write_json(out / "manifest.json", {"version": 1, "seed": seed, "days": days,
               "enterprises": enterprises, "policies": list(policies), "drift": drift,
               "blueprint_hashes": [b["blueprint_hash"] for b in blueprints],
               "generator": "procedural", "llm_calls": 0, "training_performed": False,
               "split": "demonstration only; no train/test generalization claim",
               "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(Path(__file__).parent.glob("*.py"))}})
    report = report_text(all_metrics)
    (out / "REPORT.md").write_text(report)
    return report
