from copy import deepcopy
import json
import tempfile
import unittest

from lifespan.agents import ReferenceAgent
from lifespan.environment import SessionEnv
from lifespan.experiment import counterfactual_example, demo, run_lifespan
from lifespan.world import Rule, Task, World, generate_blueprint, resolve


class SimulatorTests(unittest.TestCase):
    def world(self, drift=True):
        return World(generate_blueprint(7, 42, drift=drift))

    def task(self, world, workflow="renewal", segment="regulated"):
        task = Task("probe", workflow, segment, f"{workflow}-{segment}", "customer", world.day, world.day + 3, 10.)
        world.tasks[task.id] = task
        return task

    def run_actions(self, env, plan, omit_check=False):
        env.step({"tool": "draft.prepare", "args": {"channel": plan["channel"], "redact": plan["redact"]}})
        if not omit_check:
            for name in plan["checks"]:
                env.step({"tool": "check.perform", "args": {"name": name}})
        env.step({"tool": "approval.request", "args": {"approver": plan["approver"]}})
        return env.step({"tool": "work.commit", "args": {"endpoint": plan["endpoint"]}})

    def test_seed_reproducibility_and_variation(self):
        self.assertEqual(generate_blueprint(7, 42), generate_blueprint(7, 42))
        self.assertNotEqual(generate_blueprint(7, 42)["blueprint_hash"], generate_blueprint(8, 42)["blueprint_hash"])

    def test_scope_survives_newer_global_rule(self):
        world = self.world()
        day = next(r.valid_from for r in world.rules if r.id == "reorganization")
        regulated = resolve(world.rules, "renewal", "regulated", day)
        commercial = resolve(world.rules, "renewal", "commercial", day)
        self.assertTrue(regulated["approver"].startswith("risk-lead"))
        self.assertTrue(commercial["approver"].startswith("revenue-lead"))
        self.assertIn("risk_review", regulated["checks"])

    def test_announced_change_is_not_effective_early(self):
        world = self.world()
        r = next(r for r in world.rules if r.id == "regulated-review")
        self.assertNotEqual(resolve(world.rules, "renewal", "regulated", r.valid_from - 1)["approver"], r.patch["approver"])
        self.assertEqual(resolve(world.rules, "renewal", "regulated", r.valid_from)["approver"], r.patch["approver"])

    def test_expiry_restores_base_without_deleting_history(self):
        world = self.world()
        r = next(r for r in world.rules if r.id == "temporary-channel")
        self.assertEqual(resolve(world.rules, "incident", "commercial", r.valid_until - 1)["channel"], "incident-war-room")
        self.assertEqual(resolve(world.rules, "incident", "commercial", r.valid_until)["channel"], "incident-desk")

    def test_rumor_does_not_change_policy(self):
        world = self.world()
        rumor = next(r for r in world.rules if r.id == "informal-rumor")
        self.assertNotEqual(resolve(world.rules, "renewal", "commercial", rumor.valid_from)["approver"], "retired-sales-lead")

    def test_future_schedule_does_not_leak_through_observation_or_search(self):
        a = self.world()
        b = a.fork()
        b.rules[-1].patch["endpoint"] = "SECRET_FUTURE_ENDPOINT"
        a.advance(0)
        b.advance(0)
        ea = SessionEnv(a, self.task(a, "onboarding", "commercial"))
        eb = SessionEnv(b, self.task(b, "onboarding", "commercial"))
        self.assertEqual(ea.observation, eb.observation)
        self.assertEqual(ea.step({"tool": "documents.search"}), eb.step({"tool": "documents.search"}))
        encoded = json.dumps(ea.trace)
        self.assertNotIn("expected_procedure", encoded)
        self.assertNotIn("tool-rollback", encoded)
        self.assertNotIn("SECRET_FUTURE_ENDPOINT", encoded)

    def test_department_visibility(self):
        world = self.world()
        world.advance(0)
        docs = world.documents(world.employees["renewal-regulated"])
        self.assertTrue(all(r.workflow == "renewal" for r in docs))

    def test_employee_can_be_stale_and_asking_has_cost(self):
        world = self.world()
        migration = next(r for r in world.rules if r.id == "tool-migration")
        for day in range(migration.valid_from + 1):
            world.advance(day)
        task = self.task(world, "onboarding", "commercial")
        env = SessionEnv(world, task)
        obs, reward, *_ = env.step({"tool": "employee.ask"})
        self.assertEqual(obs["result"]["understanding"]["endpoint"], "workspace-v1")
        self.assertEqual(world.expected(task)["endpoint"], "workspace-v2")
        self.assertLess(reward, -.8)
        self.assertEqual(world.human_minutes, 2)

    def test_unread_notice_survives_days_without_session(self):
        world = self.world()
        for day in range(3):
            world.advance(day)
        env = SessionEnv(world, self.task(world))
        self.assertTrue(any(i.get("document", {}).get("id") == "base-renewal" for i in env.observation["inbox"]))
        self.assertEqual(world.inboxes["renewal-regulated"], [])

    def test_textual_claim_cannot_replace_performed_checks(self):
        world = self.world(False)
        world.advance(0)
        task = self.task(world)
        env = SessionEnv(world, task)
        obs, *_ = self.run_actions(env, world.expected(task), omit_check=True)
        self.assertFalse(obs["result"]["ok"])
        self.assertEqual(task.status, "pending")
        self.assertEqual(len(world.ledger), 0)

    def test_success_has_real_state_and_delayed_reward(self):
        world = self.world(False)
        world.advance(0)
        task = self.task(world, "onboarding", "commercial")
        env = SessionEnv(world, task)
        _, reward, terminated, _, info = self.run_actions(env, world.expected(task))
        self.assertTrue(info["success"])
        self.assertFalse(terminated)
        self.assertLess(reward, 0)  # Completion value hasn't settled yet.
        self.assertEqual(world.customers["customer"]["onboardings"], 1)
        self.assertEqual(world.scheduled[-1]["parent"], task.id)
        world.advance(1)
        self.assertFalse(world.ledger[0]["settled"])
        world.advance(2)
        self.assertTrue(world.ledger[0]["settled"])
        self.assertEqual(sum(e.get("reward", 0) for e in world.events if e["kind"] == "settlement"), 10.)
        self.assertTrue(any(i["kind"] == "settlement" for i in world.inboxes[task.owner]))
        with self.assertRaises(RuntimeError):
            env.step({"tool": "work.commit", "args": {"endpoint": "workspace-v1"}})

    def test_budget_truncates_session_not_lifespan(self):
        world = self.world()
        world.advance(0)
        env = SessionEnv(world, self.task(world), max_steps=1)
        _, _, terminated, truncated, info = env.step({"tool": "documents.search"})
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        self.assertTrue(info["session_done"])
        self.assertFalse(info["lifespan_done"])

    def test_malformed_actions_do_not_mutate_work(self):
        world = self.world()
        world.advance(0)
        task = self.task(world)
        env = SessionEnv(world, task)
        for action in (None, {"tool": "work.commit", "args": []},
                       {"tool": "draft.prepare", "args": {"channel": "renewal-desk", "redact": "false"}}):
            obs, *_ = env.step(action)
            self.assertFalse(obs["result"]["ok"])
        self.assertEqual(task.status, "pending")
        self.assertEqual(world.customers, {})

    def test_actions_change_future_processes_but_not_exogenous_event_tape(self):
        world = self.world()
        twin = world.fork()
        world.advance(0)
        twin.advance(0)
        task = self.task(world, "onboarding", "commercial")
        for i in range(4):
            world.record_failure(task, f"failure-{i}")
        self.assertEqual(world.blueprint, twin.blueprint)
        self.assertNotIn("peer_review", world.expected(task)["checks"])
        world.advance(1)
        twin.advance(1)
        self.assertIn("peer_review", world.expected(task)["checks"])
        self.assertNotIn("peer_review", resolve(twin.rules, "onboarding", "commercial", twin.day)["checks"])
        self.assertTrue(any(e.get("caused_by") == "failure-3" for e in world.events))

    def test_counterfactuals_isolate_state_and_change_business_outcomes(self):
        bp = generate_blueprint(7, 42)
        result = counterfactual_example(bp)["results"]
        self.assertEqual(result["reuse_old_procedure"]["status"], "pending")
        self.assertEqual(result["validate_and_adapt"]["status"], "completed")
        self.assertGreater(result["validate_and_adapt"]["probe_utility"], result["reuse_old_procedure"]["probe_utility"])
        world = World(bp)
        clone = world.fork()
        clone.employees["renewal-regulated"].trust = .1
        self.assertNotEqual(world.employees["renewal-regulated"].trust, clone.employees["renewal-regulated"].trust)

    def test_stationary_control_and_drift_expose_stale_skill_failure(self):
        stable = generate_blueprint(7, 42, drift=False)
        static, *_ = run_lifespan(stable, "frozen", collect_traces=False)
        bp = generate_blueprint(7, 42)
        frozen, *_ = run_lifespan(bp, "frozen", collect_traces=False)
        adaptive, *_ = run_lifespan(bp, "adaptive", collect_traces=False)
        self.assertEqual(static["first_plan_success_rate"], 1.)
        self.assertGreater(adaptive["root_completion_rate"], frozen["root_completion_rate"])
        self.assertGreater(adaptive["net_utility"], frozen["net_utility"])

    def test_reward_accounting_matches_cash_utility(self):
        metrics, world, audits, traces = run_lifespan(generate_blueprint(7, 28), "adaptive")
        tool_reward = sum(t["reward"] for s in traces for t in s["events"] if t["type"] == "transition")
        world_reward = sum(e.get("reward", 0) for e in world.events)
        self.assertAlmostEqual(tool_reward + world_reward, metrics["net_utility"], places=5)

    def test_export_is_reproducible_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = demo(first, days=28, enterprises=1, policies=["adaptive"])
            b = demo(second, days=28, enterprises=1, policies=["adaptive"])
            self.assertEqual(a, b)
            with self.assertRaises(ValueError):
                demo(first, days=28, enterprises=1, policies=["adaptive"])


if __name__ == "__main__":
    unittest.main()
