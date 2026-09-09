"""Offline public-input fixtures; no native-model or learning-effect evidence."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lifespan.computers import Computer
from lifespan.ecosystem import Ecosystem
from lifespan.environment import SessionEnv
from lifespan.evaluation.runtime import write_public_files
from lifespan.evaluation.tasks import grade_case
from lifespan.tests.test_evaluation_tasks import envelope, solve_public
from lifespan.world import Rule, resolve
from scripts.transfer_probes import build_transfer_probes, public_probe_manifest


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fixture():
    eco = Ecosystem(days=10, seed=712)
    for _ in range(10):
        eco.advance()
    return {"ecosystem": eco.checkpoint(), "runner": {"sessions": [], "experiences": [],
            "private_fixture_marker": "SOURCE_PRIVATE_MARKER_DO_NOT_EXPORT"}}


class FreshTransferProbeTests(unittest.TestCase):
    def setUp(self):
        self.source = fixture()
        self.employee = "firm-1__incident-regulated"

    def test_deterministic_fresh_ids_data_and_bound_hashes(self):
        first = build_transfer_probes(self.source, self.employee)
        self.assertEqual(first, build_transfer_probes(deepcopy(self.source), self.employee))
        self.assertNotEqual([p["task_id"] for p in first],
                            [p["task_id"] for p in build_transfer_probes(self.source, self.employee, seed=9)])
        source_ids = {task["id"] for world in self.source["ecosystem"]["worlds"].values()
                      for task in list(world["tasks"].values()) + world["scheduled"]}
        self.assertFalse(source_ids.intersection(p["task_id"] for p in first))
        self.assertEqual(len({p["task_id"] for p in first}), 4)
        # Distinct raw datasets, beyond changes to the enclosing task directory.
        inputs = [{Path(key).name: value for key, value in p["case"]["public_files"].items()
                   if key.endswith(".csv")} for p in first]
        self.assertEqual(len({digest(value) for value in inputs}), 4)
        manifest = public_probe_manifest(first)
        self.assertEqual(manifest["source_checkpoint_sha256"], digest(self.source))
        for capsule, row in zip(first, manifest["probes"]):
            self.assertEqual(row["case_sha256"], digest(capsule["case"]))
            self.assertEqual(row["capsule_sha256"], digest(capsule))
            self.assertEqual(row["task_sha256"], digest(capsule["ecosystem"]["worlds"][capsule["firm"]]["tasks"][capsule["task_id"]]))

    def test_four_future_dates_both_regimes_development_split_only(self):
        probes = build_transfer_probes(self.source, self.employee)
        self.assertEqual([p["case"]["day"] for p in probes], [10, 11, 12, 13])
        self.assertEqual([p["case"]["regime"] for p in probes], ["changed", "changed", "reversal", "reversal"])
        for index, capsule in enumerate(probes):
            meta = capsule["probe"]
            self.assertEqual(capsule["case"]["split"], "validation")
            self.assertGreater(capsule["case"]["day"], meta["cutoff_day"])
            self.assertEqual(meta["clone_horizon_days"], 11 + index)
            self.assertEqual(meta["source_horizon_days"], 10)
            policies = [json.loads(value) for key, value in capsule["case"]["public_files"].items()
                        if key.endswith("policy.json")]
            self.assertEqual(len(policies), 1)
            self.assertEqual(policies[0]["version"], "v2" if index < 2 else "v1")
            if index >= 2:
                self.assertIn("withdrawn", policies[0]["notice"])

    def test_source_and_other_capsules_remain_unchanged(self):
        before = deepcopy(self.source)
        probes = build_transfer_probes(self.source, self.employee)
        self.assertEqual(self.source, before)
        second_before = deepcopy(probes[1])
        first = probes[0]
        first["ecosystem"]["worlds"][first["firm"]]["tasks"][first["task_id"]]["status"] = "completed"
        first["objectives"]["objective"] = "MUTATED"
        first["case"]["private"]["expected"].clear()
        self.assertEqual(probes[1], second_before)
        self.assertEqual(self.source, before)

    def test_each_clone_is_exact_deterministic_advance_plus_one_pending_task(self):
        for capsule in build_transfer_probes(self.source, self.employee):
            expected = Ecosystem.restore(self.source["ecosystem"])
            expected.days = max(expected.days, capsule["case"]["day"] + 1)
            while expected.day < capsule["case"]["day"]:
                expected.advance()
            actual = deepcopy(capsule["ecosystem"])
            task = actual["worlds"][capsule["firm"]]["tasks"].pop(capsule["task_id"])
            self.assertEqual(actual, expected.checkpoint())
            self.assertEqual(task["owner"], "incident-regulated")
            self.assertEqual(task["workflow"], "incident")
            self.assertEqual(task["segment"], "regulated")
            self.assertEqual(task["status"], "pending")
            self.assertEqual(task["attempts"], 0)
            self.assertIsNone(task["completed"])
            self.assertIsNone(task["parent"])
            self.assertEqual(task["value"], 0)
            self.assertFalse(any(task["id"] == row["id"] for row in actual["worlds"][capsule["firm"]]["scheduled"]))

    def test_request_and_current_company_context_are_public_and_relevant(self):
        for capsule in build_transfer_probes(self.source, self.employee):
            eco = Ecosystem.restore(capsule["ecosystem"])
            world = eco.worlds[capsule["firm"]]
            documents = [rule.public() for rule in world.documents(world.employees["incident-regulated"])]
            self.assertEqual(capsule["public_company_procedures"], documents)
            self.assertTrue(all(doc["published"] <= capsule["case"]["day"] for doc in documents))
            self.assertEqual(capsule["objectives"]["objective"], eco.firms[capsule["firm"]]["objective"])
            self.assertNotIn("cash", capsule["objectives"])
            self.assertIn(capsule["case"]["request"], capsule["request"])
            self.assertIn("/workspace/company/procedures.json", capsule["request"])
            self.assertIn("/workspace/company/objectives.json", capsule["request"])
            self.assertNotIn(json.dumps(capsule["case"]["private"]["expected"], sort_keys=True), capsule["request"])
            self.assertNotIn("SOURCE_PRIVATE_MARKER", capsule["request"])

    def test_every_employee_case_is_solvable_using_only_published_task_inputs(self):
        for firm, world in self.source["ecosystem"]["worlds"].items():
            for local in world["employees"]:
                for capsule in build_transfer_probes(self.source, firm + "__" + local):
                    case = capsule["case"]
                    work = solve_public(case["workflow"], deepcopy(case["public_files"]))
                    self.assertTrue(grade_case(case, envelope(case, work))["success"])

    def test_real_filesystem_submission_commits_only_fresh_clone_task(self):
        before = deepcopy(self.source)
        for workflow in ("onboarding", "renewal", "incident"):
            for capsule in build_transfer_probes(self.source, "firm-0__" + workflow + "-regulated"):
                eco = Ecosystem.restore(capsule["ecosystem"])
                world = eco.worlds[capsule["firm"]]
                task = world.tasks[capsule["task_id"]]
                other_tasks = {key: asdict(value) for key, value in world.tasks.items() if key != task.id}
                case = capsule["case"]
                with tempfile.TemporaryDirectory() as directory:
                    computer = Computer(Path(directory), capsule["employee"],
                                        artifact_grader=lambda artifact: grade_case(case, artifact))
                    env = SessionEnv(world, task, employee_message=capsule["request"])
                    computer.publish(env.observation, capsule["objectives"], capsule["public_company_procedures"])
                    write_public_files(computer.workspace, case["public_files"])
                    inputs = {key: (computer.workspace / key).read_text() for key in case["public_files"]}
                    work = solve_public(workflow, inputs)
                    published = json.loads((computer.workspace / "company/procedures.json").read_text())
                    procedure = resolve([Rule(**rule) for rule in published], task.workflow, task.segment, world.day)
                    artifact = {"task_id": task.id, "channel": procedure["channel"], "redact": procedure["redact"],
                                "endpoint": procedure["endpoint"], "content": json.dumps(work, sort_keys=True)}
                    (computer.workspace / "deliverables/result.json").write_text(json.dumps(artifact))
                    actions = [{"tool": "draft.prepare", "args": {"artifact_path": "/workspace/deliverables/result.json"}},
                               *[{"tool": "check.perform", "args": {"name": check}} for check in procedure["checks"]],
                               {"tool": "approval.request", "args": {"approver": procedure["approver"]}},
                               {"tool": "work.commit", "args": {}}]
                    for action in actions:
                        computer.action(env, action)
                    self.assertTrue(env.success)
                    self.assertTrue(computer.last_grade["success"])
                    self.assertEqual(task.status, "completed")
                    self.assertEqual(other_tasks, {key: asdict(value) for key, value in world.tasks.items() if key != task.id})
                self.assertEqual(self.source, before)

    def test_public_manifest_excludes_all_private_content_with_an_allowlist(self):
        probes = build_transfer_probes(self.source, self.employee)
        probes[0]["probe"]["accidental_private_extra"] = "DO_NOT_PUBLISH_PRIVATE_RUBRIC"
        manifest = public_probe_manifest(probes)
        text = json.dumps(manifest)
        self.assertNotIn("SOURCE_PRIVATE_MARKER", text)
        self.assertNotIn("DO_NOT_PUBLISH_PRIVATE_RUBRIC", text)
        self.assertIn("not a causal world benchmark", manifest["label"])
        self.assertEqual(manifest["new_institutional_decisions"], 0)
        self.assertFalse(manifest["final_test_namespace_used"])
        forbidden = {"case", "request", "public_files", "private", "expected", "ecosystem", "business_files"}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(manifest)

    def test_future_snapshot_unknown_employee_and_invalid_parameters_are_rejected(self):
        for kwargs in ({"cutoff_day": 8}, {"cutoff_day": True}, {"cutoff_day": -1}, {"seed": True}, {"seed": -1}):
            with self.assertRaises(ValueError):
                build_transfer_probes(self.source, self.employee, **kwargs)
        with self.assertRaises(ValueError):
            build_transfer_probes(self.source, "firm-unknown__incident-regulated")
        with self.assertRaises(ValueError):
            build_transfer_probes(self.source["ecosystem"], self.employee)
        source = deepcopy(self.source)
        source["ecosystem"]["worlds"]["firm-0"]["day"] -= 1
        with self.assertRaisesRegex(ValueError, "share the observation day"):
            build_transfer_probes(source, self.employee)

    def test_existing_namespace_collision_fails_without_silent_replacement(self):
        probes = build_transfer_probes(self.source, self.employee)
        self.source["runner"]["sessions"].append({"task_id": probes[0]["task_id"]})
        with self.assertRaisesRegex(ValueError, "already occurs"):
            build_transfer_probes(self.source, self.employee)

    def test_manifest_rejects_wrong_scope_split_timeline_duplicates_and_content(self):
        probes = build_transfer_probes(self.source, self.employee)
        mutations = [lambda p: p[0]["case"].update(split="test"),
                     lambda p: p[0]["case"].update(day=8),
                     lambda p: p[0].update(employee="firm-0__incident-regulated"),
                     lambda p: p[0]["probe"].update(source_checkpoint_sha256="a" * 64),
                     lambda p: p[0].update(request="CHANGED_AFTER_FREEZE"),
                     lambda p: p[0]["case"]["private"]["expected"].clear(),
                     lambda p: p[0]["ecosystem"]["worlds"][p[0]["firm"]]["tasks"][p[0]["task_id"]].update(status="completed")]
        for mutation in mutations:
            altered = deepcopy(probes)
            mutation(altered)
            with self.assertRaises(ValueError):
                public_probe_manifest(altered)
        with self.assertRaises(ValueError):
            public_probe_manifest(probes[:3])
        with self.assertRaises(ValueError):
            public_probe_manifest([probes[0]] * 4)


if __name__ == "__main__":
    unittest.main()
