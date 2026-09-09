"""OFFLINE orchestration fixtures, never live benchmark or model-quality evidence.

Actors and the executor below are deterministic public-input test oracles. The
executor performs actual Computer filesystem writes and action dispatch through
SessionEnv and the substantive grader, but never starts Hermes or calls a model.
The fake learner exercises callbacks only; it is not SkillOpt algorithm evidence.
"""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.computers import Computer, file_delta
from lifespan.environment import SessionEnv
from lifespan.evaluation import runner
from lifespan.evaluation.protocol import ExperimentConfig, SEED_SKILL, digest, regime_at
from lifespan.evaluation.runtime import install_skill, write_public_files
from lifespan.evaluation.tasks import grade_case
from lifespan.tests.test_evaluation_tasks import solve_public
from lifespan.world import Rule, resolve


FIXTURE = "offline-public-input-oracle-not-live-evidence"
CREDS = {"model": FIXTURE, "base_url": "https://offline.example.invalid", "api_key": "unused-offline-fixture"}


class FakeActors:
    """Stateless replayable decisions; no native actor history is simulated."""
    instances = []

    def __init__(self, out, eco, spec):
        self.spec = deepcopy(spec)
        self.closed = False
        self.calls = []
        self.__class__.instances.append(self)

    def set_deadline(self, deadline):
        self.deadline = deadline

    def institutional(self, eco, actor, view, key):
        self.calls.append((eco.day, actor, key))
        base = {"notes": FIXTURE, "reason": "Deterministic integration-test fixture.", "evidence_ids": []}
        if actor == "agency":
            return {**base, "policy": "enhanced_review" if eco.day == self.spec["change_day"] else "keep", "duration": 2}
        if actor in eco.firms:
            firm = view["own_state"]
            return {**base, "objective": "reliability", "price": firm["price"],
                    "target_market": firm["target_market"], "priority_workflow": "onboarding",
                    "procedure": "alternate_route" if eco.day == 0 else "keep"}
        return {**base, "action": "wait"}

    def employee(self, eco, task, employee, notes, case, key):
        self.calls.append((eco.day, employee, key))
        return ({"delegate": True, "request": "Read the published files and perform the work.",
                 "working_notes": f"{FIXTURE}: last observed day {eco.day}."},
                {"employee": employee, "day": eco.day, "task_id": task.id, "fixture": FIXTURE})

    def close(self):
        self.closed = True


def _offline_execute(*, root, employee, world, task_id, case, request, skill, credentials,
                     objectives, max_iterations=16, max_tokens=4096, business_files=None,
                     max_total_tokens=None, timeout_seconds=420, corrupt=False):
    """Use public inputs as an oracle but real filesystem/submission semantics."""
    root = Path(root)
    if root.exists():
        raise AssertionError("A rollout must have a unique fresh root")
    root.mkdir(parents=True)
    computer = Computer(root / "computers", employee, execution={"mode": "evaluation"},
                        artifact_grader=lambda artifact: grade_case(case, artifact))
    env = SessionEnv(world, world.tasks[task_id], employee_message=request, shared_inbox=[],
                     employee_ask=lambda question: "Read the published task and procedure files.")
    skill_info = install_skill(computer.profile, skill)
    write_public_files(computer.workspace, case["public_files"])
    if business_files:
        write_public_files(computer.workspace, {"business_archive/" + key: value for key, value in business_files.items()})
    computer.publish(env.observation, objectives, [rule.public() for rule in world.documents(world.employees[world.tasks[task_id].owner])])
    before = computer.snapshot()
    # The task oracle receives actual public workspace bytes, never case.private.
    public = {name: (computer.workspace / name).read_text() for name in case["public_files"]}
    work = solve_public(case["workflow"], public)
    if corrupt:
        work = {"unsupported_claim": "I completed it"}
    # Resolve only the published department procedure records available to the
    # employee. This test oracle does not call world.expected/private diagnostics.
    published = json.loads((computer.workspace / "company/procedures.json").read_text())
    if any(rule["published"] > world.day for rule in published):
        raise AssertionError("Future procedure leaked into employee files")
    task = world.tasks[task_id]
    procedure = resolve([Rule(**rule) for rule in published], task.workflow, task.segment, world.day)
    artifact = {"task_id": task_id, "channel": procedure["channel"], "redact": procedure["redact"],
                "endpoint": procedure["endpoint"], "content": json.dumps(work, sort_keys=True)}
    (computer.workspace / "deliverables/result.json").write_text(json.dumps(artifact, sort_keys=True))
    native = {"messages": [{"role": "system", "content": "fixture-system-message-must-not-export"},
                           {"role": "user", "content": request}],
              "transport_private": "fixture-transport-state-must-not-export"}
    actions = [{"tool": "draft.prepare", "args": {"artifact_path": "/workspace/deliverables/result.json"}},
               *[{"tool": "check.perform", "args": {"name": check}} for check in procedure["checks"]],
               {"tool": "approval.request", "args": {"approver": procedure["approver"]}},
               {"tool": "work.commit", "args": {}}]
    for index, action in enumerate(actions):
        answer = computer.action(env, action)
        if answer.get("ok") is False:
            raise AssertionError("Unexpected fixture action error: " + str(answer))
        call_id = f"offline-call-{index}"
        native["messages"].extend([
            {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function",
             "function": {"name": "enterprise_action", "arguments": json.dumps(action)}}]},
            {"role": "tool", "tool_call_id": call_id, "name": "enterprise_action", "content": json.dumps(answer)},
        ])
    if not env.done:
        env.step({"tool": "session.end", "args": {}})
    after = computer.snapshot()
    grade = computer.last_grade
    if grade is None:
        raise AssertionError("Fixture did not exercise the substantive grader")
    record = {"fixture": FIXTURE, "employee": employee, "day": world.day, "task_id": task_id,
              "case_id": case["id"], "regime": case["regime"], "skill": skill_info,
              "skill_loaded": True, "skill_text_for_fixture_audit": skill,
              "success": env.success and grade["success"], "semantic_score": grade["score"],
              "feedback": grade["feedback"], "checks": grade["checks"],
              "usage": {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0,
                        "api_calls": 0, "physical_model_calls": 0, "complete": True,
                        "cost_status": "offline_fixture_no_model_call", "estimated_cost_usd": 0},
              "tool_calls": len(actions), "elapsed_seconds": .001,
              "trace": env.trace, "result": {"native": native}, "diagnostic": env.diagnostic(),
              "filesystem_before": before, "filesystem_after": after,
              "filesystem_delta": file_delta(before, after), "artifact": computer.committed_artifact,
              "artifact_sha256": computer.committed_hash, "infrastructure_valid": True}
    (root / "session.json").write_text(json.dumps(record, sort_keys=True))
    computer.close()
    return record


def offline_executor(**kwargs):
    return _offline_execute(**kwargs)


def invalid_infrastructure_executor(**kwargs):
    result = _offline_execute(**kwargs)
    result["infrastructure_valid"] = False
    return result


def incorrect_work_executor(**kwargs):
    return _offline_execute(**kwargs, corrupt=True)


class FakeCallbackLearner:
    """Callback test double, not upstream SkillOpt or optimization evidence."""
    calls = []
    replay_receipts = []

    def __init__(self, **kwargs):
        self.options = kwargs

    def update(self, skill, experiences, replay, reflector, *, current_day, night, budget):
        self.__class__.calls.append({"day": current_day, "experiences": deepcopy(experiences), "skill": skill})
        if any(item["available_day"] > current_day or item["feedback_available_day"] > current_day for item in experiences):
            raise AssertionError("Future feedback entered a learning update")
        if {item["split"] for item in experiences} != {"train", "val"}:
            raise AssertionError("Both disjoint experience pools are required")
        if len({item["employee"] for item in experiences}) != 1:
            raise AssertionError("Cross-employee experience leak")
        candidate = skill + f"\nOffline callback fixture revision on day {current_day}.\n"
        receipts = []
        for experience in experiences:
            # Run two candidate trials from the very same historical capsule.
            # Both must start before submission; otherwise duplicate execution
            # would see an already-completed task or changed balances.
            for proposed in (skill, candidate):
                receipt = replay({"task": {"id": experience["id"]}, "skill": proposed, "phase": experience["split"]},
                                 {"max_model_calls": 16, "max_tokens": 10000, "timeout_seconds": 10})
                if receipt["status"] != "completed" or receipt["hard"] != 1:
                    raise AssertionError("Independent historical fixture replay failed")
                if "fixture-transport-state-must-not-export" in receipt["response"] or "fixture-system-message-must-not-export" in receipt["response"]:
                    raise AssertionError("Private transport/system state leaked to the optimizer")
                receipts.append(receipt)
        self.__class__.replay_receipts.extend(deepcopy(receipts))
        return {"status": "completed", "accepted": True, "skill": candidate,
                "fixture": FIXTURE, "costs": {"tokens": 0, "target_model_calls": 0,
                "optimizer_model_calls": 0, "replays": len(receipts), "wall_seconds": .01,
                "accounting_complete": True, "estimated_cost_usd": 0}}


@contextmanager
def offline_dependencies(*, fake_learner=False):
    """Fix external provenance and make accidental model/network use fail."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, "source_hashes", return_value={"offline-fixture": hashlib.sha256(FIXTURE.encode()).hexdigest()}))
        stack.enter_context(patch.object(runner, "dependency_provenance", return_value={name: {"revision": FIXTURE} for name in ("hermes", "mirofish", "skillopt")}))
        stack.enter_context(patch.object(runner, "credentials", side_effect=AssertionError("Offline fixture tried to load real credentials")))
        stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Offline fixture attempted network access")))
        stack.enter_context(redirect_stdout(io.StringIO()))
        if fake_learner:
            stack.enter_context(patch("lifespan.evaluation.skillopt.SkillOptLearner", FakeCallbackLearner))
            stack.enter_context(patch("lifespan.evaluation.optimizer.make_reflector", return_value=lambda *args: (_ for _ in ()).throw(AssertionError("Offline fixture invoked model reflection"))))
        yield


def read_checkpoint(out):
    return json.loads((Path(out) / "checkpoint.json").read_text())


def stable_checkpoint(checkpoint):
    result = deepcopy(checkpoint)
    result["runner"].pop("elapsed_seconds", None)
    return result


class OfflineRunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        FakeActors.instances.clear()
        FakeCallbackLearner.calls.clear()
        FakeCallbackLearner.replay_receipts.clear()
        self.temp = tempfile.TemporaryDirectory(prefix="big-world-offline-runner-test-")
        self.root = Path(self.temp.name)
        self.config = ExperimentConfig(days=8, seed=100, max_work_sessions=100, feedback_delay=2)

    def tearDown(self):
        self.temp.cleanup()

    def run_offline(self, name, config=None, **kwargs):
        return runner.run_experiment(self.root / name, config or self.config,
                                     actor_factory=FakeActors, executor=offline_executor,
                                     creds=CREDS, **kwargs)

    def test_all_employees_all_regimes_execute_real_submission_and_keep_seed_skill(self):
        with offline_dependencies():
            result = self.run_offline("complete")
        checkpoint = read_checkpoint(self.root / "complete")
        state = checkpoint["runner"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(state["sessions"]), 48)
        self.assertEqual(len(state["skills"]), 6)
        self.assertEqual(set(state["skills"].values()), {SEED_SKILL})
        self.assertEqual(set(state["skill_versions"].values()), {0})
        self.assertEqual(state["updates"], [])
        self.assertTrue(all(actor.closed for actor in FakeActors.instances))
        for employee in state["skills"]:
            records = [row for row in state["sessions"] if row["employee"] == employee]
            self.assertEqual(len(records), 8)
            self.assertEqual({row["regime"] for row in records}, {"base", "changed", "exception", "reversal"})
            self.assertTrue(all(row["fixture"] == FIXTURE and row["success"] and row["semantic_score"] == 1 for row in records))
            self.assertTrue(all(row["skill_text_for_fixture_audit"] == SEED_SKILL for row in records))
            self.assertEqual(len(list((self.root / "complete/skills" / employee).glob("v*.json"))), 1)
        self.assertEqual(result["obligations"]["created_before_horizon"], 48)
        self.assertEqual(result["obligations"]["success_rate"], 1)
        self.assertTrue(result["audit"]["eligible_for_paired_inference"], result["audit"])
        self.assertEqual(result["business"]["unsettled_entries"], 0)
        self.assertEqual(result["horizon"]["observed_world_day"], 9)
        # Evidence comes from real trusted checks, not the test oracle's claim.
        self.assertTrue(all(any(transition.get("action", {}).get("tool") == "work.commit" for transition in row["trace"])
                            for row in state["sessions"]))
        self.assertTrue(all(row["artifact_sha256"] for row in state["sessions"]))

    def test_pause_resume_invocation_limits_match_uninterrupted_world_and_timeline(self):
        with offline_dependencies():
            self.run_offline("continuous")
            first = self.run_offline("resumed", stop_after_sessions=7)
            self.assertEqual(first["status"], "paused_invocation_limit")
            self.assertEqual(len(read_checkpoint(self.root / "resumed")["runner"]["sessions"]), 7)
            self.assertFalse((self.root / "resumed/INFLIGHT.json").exists())
            second = self.run_offline("resumed", stop_after_sessions=5)
            self.assertEqual(second["status"], "paused_invocation_limit")
            self.assertEqual(len(read_checkpoint(self.root / "resumed")["runner"]["sessions"]), 12)
            final = self.run_offline("resumed")
        self.assertEqual(final["status"], "completed")
        continuous = read_checkpoint(self.root / "continuous")
        resumed = read_checkpoint(self.root / "resumed")
        self.assertEqual(stable_checkpoint(continuous), stable_checkpoint(resumed))
        self.assertEqual(json.loads((self.root / "continuous/timeline.json").read_text()),
                         json.loads((self.root / "resumed/timeline.json").read_text()))
        self.assertEqual(len({row["id"] for row in resumed["runner"]["sessions"]}), 48)

    def test_substantive_failures_never_commit_or_create_payments(self):
        with offline_dependencies():
            result = runner.run_experiment(self.root / "bad-work", self.config,
                actor_factory=FakeActors, executor=incorrect_work_executor, creds=CREDS)
        checkpoint = read_checkpoint(self.root / "bad-work")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["obligations"]["completed_at_observation"], 0)
        self.assertEqual(result["obligations"]["success_rate"], 0)
        self.assertGreater(result["prospective"]["retry_attempts"], 0)
        self.assertEqual(result["business"]["settled_entries"], 0)
        self.assertTrue(all(not row["success"] and row["artifact"] is None for row in checkpoint["runner"]["sessions"]))
        self.assertTrue(all(not world["ledger"] for world in checkpoint["ecosystem"]["worlds"].values()))
        self.assertTrue(any(transition.get("action", {}).get("tool") == "artifact.reject"
                            for row in checkpoint["runner"]["sessions"] for transition in row["trace"]))

    def test_invalid_infrastructure_preserves_inflight_and_blocks_automatic_replay(self):
        out = self.root / "invalid"
        with offline_dependencies():
            with self.assertRaisesRegex(RuntimeError, "validation"):
                runner.run_experiment(out, self.config, actor_factory=FakeActors,
                                      executor=invalid_infrastructure_executor, creds=CREDS)
            self.assertTrue((out / "INFLIGHT.json").exists())
            self.assertEqual(json.loads((out / "REPORT.json").read_text())["status"], "failed")
            self.assertEqual(len(read_checkpoint(out)["runner"]["sessions"]), 1)
            before = deepcopy(read_checkpoint(out))
            with self.assertRaisesRegex(RuntimeError, "reconciliation"):
                runner.run_experiment(out, self.config, actor_factory=FakeActors,
                                      executor=invalid_infrastructure_executor, creds=CREDS)
            self.assertEqual(read_checkpoint(out), before)

    def test_feedback_cutoff_and_replay_callbacks_leave_live_world_unchanged(self):
        config = ExperimentConfig(algorithm="skillopt", days=8, seed=100,
            max_work_sessions=100, feedback_delay=2, update_every=2, train_cases=1, val_cases=1,
            max_learning_calls=600, max_learning_tokens=6000000)
        with offline_dependencies(fake_learner=True):
            self.run_offline("frozen")
            learned = self.run_offline("learned", config=config)
        frozen = read_checkpoint(self.root / "frozen")
        checkpoint = read_checkpoint(self.root / "learned")
        state = checkpoint["runner"]
        self.assertTrue(FakeCallbackLearner.calls)
        self.assertTrue(FakeCallbackLearner.replay_receipts)
        self.assertTrue(state["updates"])
        self.assertTrue(all(update["day"] < config.days - 1 for update in state["updates"]),
                        "Do not spend a learning update after the final work opportunity")
        self.assertEqual(learned["status"], "completed")
        self.assertTrue(learned["audit"]["eligible_for_paired_inference"], learned["audit"])
        for call in FakeCallbackLearner.calls:
            self.assertTrue(all(experience["available_day"] <= call["day"] for experience in call["experiences"]))
            self.assertTrue(all(experience["feedback_available_day"] <= call["day"] for experience in call["experiences"]))
            self.assertTrue(all(experience["split"] in ("train", "val") for experience in call["experiences"]))
            self.assertFalse(any('"expected"' in experience["context"] for experience in call["experiences"]))
        self.assertEqual(digest(frozen["ecosystem"]), digest(checkpoint["ecosystem"]))
        self.assertEqual(len(state["sessions"]), 48)
        self.assertGreater(sum(row["costs"]["replays"] for row in state["updates"]), 0)
        # Replays never append live sessions, settle live payments, or duplicate
        # effects, and accepted skills become visible only in later work.
        for update in state["updates"]:
            self.assertEqual(update["available_from_day"], update["day"] + 1)
            later = [row for row in state["sessions"] if row["employee"] == update["employee"]
                     and row["skill_version"] == update["deployed_version"]]
            self.assertTrue(all(row["day"] > update["day"] for row in later))
        self.assertTrue(any(version > 0 for version in state["skill_versions"].values()))
        self.assertTrue(all(row["tokens"] == 0 and row["model_calls"] == 0 for row in FakeCallbackLearner.replay_receipts))


if __name__ == "__main__":
    unittest.main()
