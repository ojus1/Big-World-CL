"""Offline validation of the real integrated run; makes no model calls."""
from collections import Counter
import json
from pathlib import Path
import sqlite3


def validate(out):
    out = Path(out)
    result = json.loads((out / "RESULTS.json").read_text())
    cohort = json.loads((out / "persona_cohort.json").read_text())["personas"]
    profiles = json.loads((out / "imported_mirofish_profiles.json").read_text())
    assert len({p["persona_id"] for p in cohort}) == result["employees"] == 6
    for persona, profile in zip(cohort, profiles):
        assert persona["source"] == "synthetic"
        assert profile["persona8b_provenance"]["persona_id"] == persona["persona_id"]
        for key, value in persona["work_attributes"].items():
            assert json.dumps(key) + ": " + json.dumps(value) in profile["persona"]
    with sqlite3.connect(out / "mirofish_simulation.db") as db:
        native = dict(db.execute("SELECT action,count(*) FROM trace GROUP BY action"))
        interviews = [json.loads(row[0]) for row in db.execute("SELECT info FROM trace WHERE action='interview'")]
    assert native["interview"] >= result["employee_interactions"] > 6
    assert native.get("create_post", 0) > 1 or native.get("create_comment", 0) > 0
    native_responses = Counter(x["response"] for x in interviews)
    for path in (out / "mirofish_interviews").glob("*.json"):
        cached = json.loads(path.read_text())
        assert native_responses[cached["response"]] > 0, "Cached employee output is missing from native OASIS trace"
        native_responses[cached["response"]] -= 1
    employees = [json.loads(line) for line in (out / "employee_interactions.jsonl").read_text().splitlines()]
    learner = [json.loads(line) for line in (out / "learner/sessions.jsonl").read_text().splitlines()]
    rewards = [json.loads(line) for line in (out / "learner/business_rewards.jsonl").read_text().splitlines()]
    assert len(employees) == result["employee_interactions"]
    assert len(learner) == result["assistant_sessions"]
    requests = {(r["day"],r["employee"],r["task_id"]): r["decision"]["request"] for r in employees}
    for record in employees:
        view = record["view"]
        assert all(d["published"] <= record["day"] for d in view["visible_documents"])
        assert all(d["workflow"] == view["workflow"] for d in view["visible_documents"])
        assert '"expected_procedure"' not in json.dumps(view)
    total_reward = sum(r["reward"] for r in rewards)
    for session in learner:
        observation = session["events"][0]["observation"]
        assert observation["message"] == requests[(session["day"],session["employee"],observation["task"]["id"])]
        assert "attributes" not in observation and "persona" not in observation
        for event in session["events"]:
            assert '"expected_procedure"' not in json.dumps(event)
            if event["type"] == "transition":
                total_reward += event["reward"]
                for document in event["observation"]["result"].get("documents", []):
                    assert document["published"] <= session["day"]
    assert abs(total_reward - result["net_utility"]) < 1e-5
    completions = [json.loads(p.read_text()) for p in (out / "completed_sessions").glob("*.json")]
    assert sum(len(s["model_calls"]) for s in completions) == result["assistant_model_calls"] > 0
    assert any(s["prior_memory"] for s in completions), "No persistent assistant memory was consumed"
    assert any(r["view"]["own_previous_working_notes"] for r in employees), "No employee state was carried forward"
    assert any(r["view"]["recent_observed_outcome"] for r in employees), "No work feedback reached employees"
    summary = {"validated": True, "checks": ["actual dataset traits in native profiles", "native OASIS output correspondence",
        "generated requests drive learner", "publication and department boundaries", "persistent employee and assistant states",
        "model calls present", "business reward reconciliation"], "employee_interactions": len(employees),
        "assistant_sessions":len(learner), "native_actions":native}
    (out / "VALIDATION.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("out",nargs="?",default="lifespan/artifacts/integrated")
    print(json.dumps(validate(p.parse_args().out),indent=2))
