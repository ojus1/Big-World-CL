"""Persona 8B -> native MiroFish employees -> LLM assistants -> enterprise work."""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .environment import SessionEnv
from .llm_agent import LLMAgent
from .mirofish import MiroFishRuntime, parse_object, save, ROOT
from .personas import import_cohort
from .world import World, Rule, generate_blueprint, resolve, digest


EMPLOYEE_PROMPT = """You are participating in an enterprise lifespan as the employee identified below.
Your imported Persona 8B profile describes your tendencies; express them naturally without mentioning the dataset.
This workplace view is all newly available information. Retain/revise your previous working notes using it.
Do not invent earlier conversations or future policy changes. A new message need not be authoritative.
Decide whether to delegate this real pending task to your assistant today; if withholding, work remains pending.
You are expected to use your assistant normally; withhold only for a concrete reason supported by this view.
Write the actual request your assistant should receive, including context you decide is useful.
Choose which of the visible documents to share. You can message the other employee in your department;
only supplied visible document IDs can be attached. Messages arrive next day. Do not send redundant messages.
After a real observed failure, you may propose adding peer_review to your own scoped working procedure.
You cannot change corporate approval ownership, disclosure rules or tools by personal preference.
Return ONLY a JSON object with these keys:
{"delegate":true,"request":"actual request", "working_notes":"updated notes, max 1800 chars",
 "share_document_ids":["visible IDs"], "colleague_messages":[{"recipient":"employee ID","text":"message","document_ids":[]}],
 "process_proposal":null}
process_proposal can be {"action":"require_peer_review","reason":"reason tied to observed failure"}.
Use at most one colleague message. All dates below are simulated days; ignore real-world dates.
Workplace view:
"""


def employee_view(world, task, notes, feedback, mailbox):
    emp = world.employees[task.owner]
    return {"day": world.day, "employee_id": emp.id, "workflow": emp.workflow, "segment": emp.segment,
            "pending_task": {"id": task.id, "customer": task.customer, "due": task.due,
                             "workflow": task.workflow, "segment": task.segment},
            "own_previous_working_notes": notes.get(emp.id, ""),
            "recent_observed_outcome": feedback.get(emp.id),
            "unread_inbox": deepcopy(world.inboxes[emp.id]),
            "received_colleague_messages": deepcopy(mailbox.get(emp.id, [])),
            "visible_documents": [r.public() for r in world.rules if r.id in emp.known],
            "collaboration_state": {"trust": emp.trust},
            "colleagues": [e.id for e in world.employees.values() if e.workflow == emp.workflow and e.id != emp.id]}


def validate_decision(decision, view):
    if not isinstance(decision.get("delegate"), bool) or not isinstance(decision.get("request"), str):
        raise ValueError("Employee must supply a delegation decision and request")
    if not isinstance(decision.get("working_notes"), str) or len(decision["working_notes"]) > 1800:
        raise ValueError("Invalid employee working notes")
    docs = {r["id"] for r in view["visible_documents"]}
    shared = decision.get("share_document_ids")
    if not isinstance(shared, list) or any(x not in docs for x in shared):
        raise ValueError("Employee tried to share a document it has not received")
    messages = decision.get("colleague_messages", [])
    if not isinstance(messages, list) or len(messages) > 1:
        raise ValueError("At most one colleague message per work session")
    for message in messages:
        if (message.get("recipient") not in view["colleagues"] or not isinstance(message.get("text"), str)
                or not isinstance(message.get("document_ids", []), list)
                or any(x not in docs for x in message.get("document_ids", []))):
            raise ValueError("Colleague message violates visibility or department boundary")
    proposal = decision.get("process_proposal")
    if proposal is not None and (not isinstance(proposal, dict) or proposal.get("action") != "require_peer_review"
                                 or not isinstance(proposal.get("reason"), str)):
        raise ValueError("Unsupported process proposal")
    return decision


def deliver(world, queued, mailbox):
    for message in queued:
        if message["deliver_day"] == world.day:
            target = world.employees[message["recipient"]]
            for doc_id in message["document_ids"]:
                if doc_id not in target.known:
                    target.known.append(doc_id)
            mailbox.setdefault(target.id, []).append(deepcopy(message))
            world.events.append({"kind": "colleague_message_delivered", "day": world.day,
                                 "from": message["sender"], "to": target.id, "caused_by": message["id"]})


def enact_proposal(world, task, decision, feedback):
    proposal = decision.get("process_proposal")
    if proposal is None:
        return None
    recent = feedback.get(task.owner)
    accepted = bool(recent and recent.get("success") is False)
    rule_id = "employee-review-" + task.owner
    if any(r.id == rule_id for r in world.rules):
        accepted = False
    if accepted:
        current = world.expected(task)
        rule = Rule(rule_id, task.workflow, task.segment, world.day + 1, None, world.day + 1,
                    "policy_owner", {"checks_add": ["peer_review"]},
                    "Employee-requested local working procedure: " + proposal["reason"])
        world.rules.append(rule)
    event = {"kind": "employee_process_proposal", "day": world.day, "employee": task.owner,
             "proposal": proposal, "accepted": accepted,
             "caused_by": recent.get("task_id") if recent else None, "rule_id": rule_id if accepted else None}
    world.events.append(event)
    return event


def append(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")


def run(out, days=28, seed=7, max_sessions=None, work_every=3):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "RESULTS.json").exists():
        raise ValueError("Completed output already exists; choose a fresh --out")
    cohort_path = ROOT / "lifespan/data/cohort.json"
    cohort = (json.loads(cohort_path.read_text()) if cohort_path.exists() else
              import_cohort(ROOT / "lifespan/data/persona8b", cohort_path))
    blueprint = generate_blueprint(seed, days, "persona-enterprise-0")
    if work_every < 1:
        raise ValueError("work_every must be positive")
    blueprint["arrivals"] = [a for a in blueprint["arrivals"] if a["created"] % work_every == 0]
    blueprint["work_every"] = work_every
    blueprint["endogenous_failure_rule"] = False
    blueprint["blueprint_hash"] = digest({k:v for k,v in blueprint.items() if k != "blueprint_hash"})
    save(out / "private/blueprint.json", blueprint)
    save(out / "persona_cohort.json", cohort)
    runtime = MiroFishRuntime(out)
    runtime.bootstrap(blueprint, cohort)
    world, agent = World(blueprint), LLMAgent()
    notes, employee_feedback, mailbox, queued = {}, {}, {}, []
    audits, sessions, employee_records, daily, reward_events = [], [], [], [], []
    started = time.monotonic()
    for day in range(days):
        before_day = world.total_utility
        world.advance(day)
        reward_events.append({"day": day, "reward": round(world.total_utility - before_day, 6), "kind": "day_transition"})
        deliver(world, queued, mailbox)
        # Delegate decisions now belong to MiroFish employees. The old scripted
        # trust-threshold scheduler is not used in this integrated experiment.
        tasks = []
        for emp in world.employees.values():
            pending = [t for t in world.tasks.values() if t.owner == emp.id and t.status == "pending"]
            if pending:
                tasks.append(min(pending, key=lambda t:(t.due,t.id)))
        for task in tasks:
            if max_sessions is not None and len(employee_records) >= max_sessions:
                save(out / "pilot_checkpoint.json", {"day": day, "employee_sessions": len(employee_records),
                     "assistant_sessions": len(sessions), "status": "pilot_paused"})
                print("Pilot limit reached; rerun without --max-sessions to continue through cached completed sessions.", flush=True)
                return
            session_key = f"d{day:03d}-{task.id}-a{task.attempts}"
            view = employee_view(world, task, notes, employee_feedback, mailbox)
            prompt = EMPLOYEE_PROMPT + json.dumps(view)
            raw = runtime.interview(task.owner, prompt, session_key)
            try:
                decision = validate_decision(parse_object(raw), view)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                # A real corrective interaction, never substitution by a scripted employee.
                raw = runtime.interview(task.owner, prompt + "\nYour previous response was invalid: " + str(error)
                    + "\nPrevious response: " + raw + "\nReturn a corrected JSON object only.", session_key + "-repair")
                decision = validate_decision(parse_object(raw), view)
            notes[task.owner] = decision["working_notes"]
            mailbox[task.owner] = []
            record = {"day": day, "employee": task.owner, "task_id": task.id,
                      "view": view, "decision": decision,
                      "persona_id": cohort["personas"][runtime.employee_ids[task.owner]]["persona_id"]}
            employee_records.append(record)
            for msg in decision.get("colleague_messages", []):
                queued.append({"id": session_key + "-message", "sender": task.owner,
                    "deliver_day": day + 1, "recipient": msg["recipient"], "text": msg["text"],
                    "document_ids": msg.get("document_ids", [])})
            proposal = enact_proposal(world, task, decision, employee_feedback)
            if not decision["delegate"]:
                world.events.append({"kind": "delegation_withheld", "day": day, "employee": task.owner,
                                     "reason": decision["request"], "caused_by": session_key})
                world.inboxes[task.owner].clear()
                save(out / "employee_sessions" / (session_key + ".json"), record)
                continue
            available = {r["id"]: r for r in view["visible_documents"]}
            shared = [{"kind": "notice", "day": day, "document": available[rid]} for rid in decision["share_document_ids"]]
            shared += [i for i in world.inboxes[task.owner] if i["kind"] == "settlement"]
            ask_count = [0]
            def ask(question):
                ask_count[0] += 1
                return runtime.interview(task.owner,
                    "The assistant asks: " + str(question) + ". Answer briefly using only this workplace view and your notes.\n"
                    + json.dumps(view) + "\nYour latest decision: " + json.dumps(decision),
                    session_key + f"-ask{ask_count[0]}")
            env = SessionEnv(world, task, employee_message=decision["request"], employee_ask=ask, shared_inbox=shared)
            completed_path = out / "completed_sessions" / (session_key + ".json")
            if completed_path.exists():
                cached = json.loads(completed_path.read_text())
                if cached["observation"] != env.observation or cached["prior_memory"] != agent.memory.get(task.owner, ""):
                    raise ValueError("Resume state differs from cached learner input")
                for transition in cached["trace"][1:]:
                    obs, reward, *_ = env.step(transition["action"])
                    if obs != transition["observation"] or round(reward,6) != transition["reward"]:
                        raise ValueError("Replay transition differs from stored execution")
                reply = cached["reply"]
                agent.memory[task.owner] = cached["memory"]
                agent.feedback[task.owner] = cached["feedback"]
            else:
                prior_memory = agent.memory.get(task.owner, "")
                print(f"Day {day:02d}: {task.owner} -> LLM work on {task.id}", flush=True)
                reply, calls = agent.run(env)
                save(completed_path, {"observation": env.observation, "prior_memory": prior_memory,
                    "trace": env.trace, "reply": reply, "memory": agent.memory.get(task.owner,""),
                    "feedback": agent.feedback[task.owner], "model_calls": calls})
            employee_feedback[task.owner] = deepcopy(agent.feedback[task.owner])
            audits.append(env.diagnostic())
            sessions.append({"session_id": env.session_id, "day": day, "employee": task.owner,
                             "persona_id": record["persona_id"], "events": env.trace, "reply": reply})
            record["outcome"] = employee_feedback[task.owner]
            save(out / "employee_sessions" / (session_key + ".json"), record)
        daily.append({"day": day, "cumulative_utility": round(world.total_utility,6),
                      "completed": sum(t.status == "completed" for t in world.tasks.values()),
                      "backlog": sum(t.status == "pending" for t in world.tasks.values())})
        save(out / "progress.json", {"day": day, "days": days, "employee_interactions": len(employee_records),
              "assistant_sessions": len(sessions), "elapsed_s": round(time.monotonic()-started,1), "latest": daily[-1]})
        print(f"Day {day+1}/{days}: completed={daily[-1]['completed']}, backlog={daily[-1]['backlog']}", flush=True)
    # Copy native DB using SQLite's snapshot API while MiroFish remains live.
    with sqlite3.connect(runtime.sim_dir / "reddit_simulation.db") as source:
        with sqlite3.connect(out / "mirofish_simulation.db") as destination:
            source.backup(destination)
        native_counts = dict(source.execute("SELECT action,count(*) FROM trace GROUP BY action"))
    roots = [t for t in world.tasks.values() if t.parent is None]
    completed = sum(t.status == "completed" for t in roots)
    calls = []
    for path in sorted((out / "completed_sessions").glob("*.json")):
        calls += json.loads(path.read_text())["model_calls"]
    result = {"days": days, "work_every": work_every, "enterprises": 1, "employees": 6, "employee_interactions": len(employee_records),
              "assistant_sessions": len(sessions), "root_tasks": len(roots), "root_completed": completed,
              "root_completion_rate": completed / len(roots),
              "first_plan_success_rate": sum(a["first_plan_correct"] for a in audits)/len(audits) if audits else 0,
              "net_utility": round(world.total_utility,6), "document_queries": sum(a["queries"] for a in audits),
              "human_minutes": world.human_minutes, "backlog": daily[-1]["backlog"],
              "abandoned": sum(t.status == "abandoned" for t in world.tasks.values()),
              "unsettled_value": sum(x["amount"] for x in world.ledger if not x["settled"]),
              "colleague_messages": len(queued), "employee_process_proposals": sum(e["kind"] == "employee_process_proposal" for e in world.events),
              "accepted_process_proposals": sum(e["kind"] == "employee_process_proposal" and e["accepted"] for e in world.events),
              "withheld_delegations": sum(not r["decision"]["delegate"] for r in employee_records),
              "model": agent.model_name, "assistant_model_calls": len(calls),
              "assistant_input_tokens": sum(c["usage"].get("prompt_tokens",0) for c in calls),
              "assistant_output_tokens": sum(c["usage"].get("completion_tokens",0) for c in calls),
              "native_mirofish_action_counts": native_counts,
              "mirofish_simulation_id": runtime.state["simulation"]["simulation_id"],
              "persona_revision": cohort["revision"], "training_performed": False,
              "employee_state": "Explicit persistent notes and outcome feedback supplied to actual OASIS interviews; native interview_record is false",
              "scope": "One live integration run; not a controlled estimate of learning or persona effects"}
    save(out / "RESULTS.json", result)
    save(out / "private/session_audits.json", audits)
    save(out / "private/final_world.json", world.snapshot())
    save(out / "private/world_events.json", world.events)
    save(out / "employee_states.json", notes)
    save(out / "assistant_skills.json", agent.memory)
    save(out / "daily.json", daily)
    # Replace these aggregate exports atomically on successful completion.
    for name, rows in [("learner/sessions.jsonl", sessions), ("learner/business_rewards.jsonl",reward_events),
                       ("employee_interactions.jsonl",employee_records)]:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows))
    save(out / "manifest.json", {"version": "0.2", "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "lifespan").glob("*.py"))}, "settings": {"days":days,"seed":seed,"work_every":work_every},
            "mirofish_revision": json.loads((ROOT/"results/versions.json").read_text()),
            "persona_revision":cohort["revision"], "persona_shard_sha256":cohort["shard_sha256"]})
    report = ["# Persona 8B + MiroFish enterprise lifespan", "", "Actual imported personas, native MiroFish/OASIS employee interactions, and model-generated work actions.", "",
              "| Measurement | Value |", "|---|---:|"]
    report += [f"| {k.replace('_',' ')} | {v} |" for k,v in result.items() if isinstance(v,(int,float,str))]
    report += ["", "This is one integration run. It demonstrates the data and execution path; it does not establish persona realism, RL training gains, or superiority over a baseline.",
               "", "The social platform is used for initial native interaction and its interview runtime. Cross-employee workplace messages are explicitly routed by the enterprise adapter. Business tools and rewards are executable mechanisms, not generated by the employee model.",
               "", "Persona data is a research-only subset of the public Persona 8B coreset. All six sampled records are synthetic.", ""]
    (out/"REPORT.md").write_text("\n".join(report))
    runtime.close()
    print(json.dumps(result,indent=2),flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="lifespan/artifacts/integrated")
    p.add_argument("--days",type=int,default=28)
    p.add_argument("--seed",type=int,default=7)
    p.add_argument("--max-sessions",type=int)
    p.add_argument("--work-every",type=int,default=3,help="New exogenous work every N calendar days; follow-ups and rework run daily")
    args=p.parse_args()
    run(args.out,args.days,args.seed,args.max_sessions,args.work_every)
