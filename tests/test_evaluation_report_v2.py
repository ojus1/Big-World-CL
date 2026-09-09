"""Fabricated accounting fixtures; these never establish native/model quality."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.metrics import build_report
from scripts.evaluation_report_v2 import (ROOT, build_report_v2, compare_reports_v2,
    load_verified_report_v2, validate_report_v2, write_report_v2)


def fixture(*, delay=2, native=False, algorithm="no_learning", status="completed"):
    """Six initial fulfilled orders plus one benchmark commitment, optionally native demand."""
    eco = Ecosystem(20, seed=301)
    eco.shock_schedule = []
    sessions = []
    def complete(firm, task_id):
        world = eco.worlds[firm]
        task = world.tasks[task_id]
        identifier = "fixture-" + task_id
        task.attempts += 1
        world.complete(task, identifier)
        sessions.append({"id": identifier, "employee": firm + "__" + task.owner,
            "task_id": task_id, "day": eco.day, "success": True, "semantic_score": 1.0,
            "regime": "base", "skill_loaded": True, "infrastructure_valid": True,
            "usage": {"total_tokens": 0, "api_calls": 0, "complete": True,
                      "estimated_cost_usd": 0, "cost_status": "offline_fixture"},
            "diagnostic": {"cost": 0, "human_minutes": 0, "first_plan_correct": True},
            "elapsed_seconds": 0})
    eco.advance()
    for firm, world in eco.worlds.items():
        for task_id in list(world.tasks):
            complete(firm, task_id)
    eco.advance()
    cause = eco.emit("benchmark_demand", "environment", {"for_day": 2, "orders_per_employee": 1})
    eco.geopolitics["supply_delay"] = delay
    benchmark = eco.order("consumer-0", "firm-0", "onboarding", cause, created=2)
    native_id = None
    if native:
        eco.geopolitics["supply_delay"] = 0
        action = {"action": "purchase", "firm": "firm-0", "notes": "Offline fabricated fixture.",
                  "reason": "Exercise endogenous order provenance.", "evidence_ids": []}
        eco.apply_decision("consumer-2", action, eco.actor_view("consumer-2"))
        native_id = eco.consumers["consumer-2"]["pending"][0]["task_id"]
    while eco.day < 5:
        eco.advance()
        if native_id and eco.day == 2:
            complete("firm-0", native_id)
    config = {"algorithm": algorithm, "days": 4, "seed": 301, "split": "dev",
              "state_mode": "skill_transfer", "max_iterations": 16}
    scenario = {"days": 4, "seed": 301, "split": "dev", "settlement_delay": 2}
    state = {"sessions": sessions, "updates": []}
    report = build_report(config, scenario, sessions, [], eco.snapshot(), status=status,
                          provenance={"executor": "fabricated-accounting-fixture", "source": "fixture-only"})
    assert report["audit"]["eligible_for_paired_inference"] or status != "completed", report["audit"]
    return {"ecosystem": eco.checkpoint(), "runner": state}, report, benchmark, native_id


class CommitmentCorrectionTests(unittest.TestCase):
    def test_arrival_during_drain_is_in_commitments_but_not_actionable_denominator(self):
        checkpoint, old, delayed, _ = fixture(delay=2)
        result = build_report_v2(checkpoint, old)
        self.assertEqual(old["obligations"]["success_rate"], 1)
        self.assertEqual(result["headline"], {"metric": "pre_horizon_commitment_fulfillment_rate",
                         "numerator": 6, "denominator": 7, "value": 6 / 7})
        metrics = result["commitments"]
        self.assertEqual(metrics["pending_at_observation"], 1)
        self.assertEqual(metrics["awaiting_availability_at_work_horizon"], 1)
        self.assertEqual(metrics["arrived_during_outcome_window"], 1)
        self.assertEqual(metrics["actionable_before_work_horizon"], 6)
        row = next(row for row in result["commitment_records"] if row["task_id"] == delayed)
        self.assertEqual((row["placed_day"], row["nominal_release_day"], row["available_day"]), (1, 2, 4))
        self.assertTrue(result["correction_audit"]["eligible_for_paired_inference"])

    def test_unmaterialized_future_arrival_is_retained_as_pending_commitment(self):
        checkpoint, old, delayed, _ = fixture(delay=5)
        result = build_report_v2(checkpoint, old)
        row = next(row for row in result["commitment_records"] if row["task_id"] == delayed)
        self.assertEqual(row["status"], "scheduled")
        self.assertEqual(row["available_day"], 7)
        self.assertFalse(row["materialized"])
        self.assertEqual(result["commitments"]["scheduled_not_materialized_at_observation"], 1)
        self.assertEqual(result["commitments"]["pending_at_observation"], 1)
        self.assertEqual(result["commitments"]["arrived_during_outcome_window"], 0)
        self.assertEqual(result["headline"]["denominator"], 7)
        self.assertTrue(result["correction_audit"]["eligible_for_paired_inference"])

    def test_materialized_state_overrides_stale_scheduled_pending_template(self):
        checkpoint, old, _, _ = fixture()
        result = build_report_v2(checkpoint, old)
        initial = [row for row in result["commitment_records"] if row["source"] == "initial"]
        self.assertEqual(len(initial), 6)
        self.assertTrue(all(row["status"] == "completed" and row["settled"] for row in initial))
        self.assertEqual(sum(len(world["scheduled"]) for world in checkpoint["ecosystem"]["worlds"].values()), 7)
        self.assertEqual(result["commitments"]["accepted_before_work_horizon"], 7)

    def test_native_orders_have_separate_provenance_and_fixed_demand_denominator(self):
        checkpoint, old, _, native_id = fixture(native=True, algorithm="skillopt")
        result = build_report_v2(checkpoint, old)
        native = result["source_breakdown"]["native_consumer"]
        self.assertEqual(native["accepted_before_work_horizon"], 1)
        self.assertEqual(native["fulfilled_before_work_horizon"], 1)
        self.assertEqual(result["headline"]["value"], 7 / 8)
        self.assertEqual(result["source_breakdown"]["fixed_initial_and_benchmark"]["fulfillment_rate"], 6 / 7)
        row = next(row for row in result["commitment_records"] if row["task_id"] == native_id)
        self.assertEqual(row["source"], "native_consumer")
        self.assertTrue(row["source_event_ids"])

    def test_duplicates_are_deduplicated_and_flagged_not_counted_twice(self):
        checkpoint, old, _, _ = fixture()
        history = checkpoint["ecosystem"]["consumers"]["consumer-0"]["history"]
        history.append(deepcopy(next(row for row in history if row["kind"] == "ordered")))
        result = build_report_v2(checkpoint, old)
        self.assertEqual(result["headline"]["denominator"], 7)
        self.assertFalse(result["correction_audit"]["eligible_for_paired_inference"])
        self.assertIn("duplicate_ordered_history", {row["code"] for row in result["correction_audit"]["issues"]})

    def test_missing_scheduled_evidence_is_unknown_not_hidden(self):
        checkpoint, old, delayed, _ = fixture(delay=5)
        world = checkpoint["ecosystem"]["worlds"]["firm-0"]
        world["scheduled"] = [row for row in world["scheduled"] if row["id"] != delayed]
        result = build_report_v2(checkpoint, old)
        self.assertEqual(result["headline"]["denominator"], 7)
        self.assertIsNone(result["headline"]["value"])
        self.assertEqual(result["commitments"]["missing_task_evidence"], 1)
        self.assertFalse(result["correction_audit"]["eligible_for_paired_inference"])

    def test_source_attribution_rejects_wrong_actor_time_and_target_firm(self):
        for field, value in (("actor", "wrong-actor"), ("day", 0)):
            checkpoint, old, _, _ = fixture()
            parent = next(row for row in checkpoint["ecosystem"]["events"] if row["kind"] == "benchmark_demand")
            parent[field] = value
            result = build_report_v2(checkpoint, old)
            self.assertIn("benchmark_source_time_or_actor_disagreement", {row["code"] for row in result["correction_audit"]["issues"]})
        checkpoint, old, _, _ = fixture(native=True)
        parent = next(row for row in checkpoint["ecosystem"]["events"] if row["kind"] == "consumer_decision")
        parent["payload"]["firm"] = "firm-1"
        result = build_report_v2(checkpoint, old)
        self.assertIn("native_source_time_or_firm_disagreement", {row["code"] for row in result["correction_audit"]["issues"]})

    def test_completion_joins_exact_original_obligation(self):
        checkpoint, old, _, _ = fixture()
        checkpoint["runner"]["sessions"][0]["task_id"] = "different-obligation"
        result = build_report_v2(checkpoint, old)
        codes = {row["code"] for row in result["correction_audit"]["issues"]}
        self.assertIn("completion_evidence_disagreement", codes)
        self.assertIn("session_without_accepted_order", codes)

    def test_regeneration_is_deterministic_and_inputs_remain_unchanged(self):
        checkpoint, old, _, _ = fixture()
        original = deepcopy((checkpoint, old))
        self.assertEqual(build_report_v2(checkpoint, old), build_report_v2(checkpoint, old))
        self.assertEqual((checkpoint, old), original)

    def test_checkpoint_and_report_must_describe_same_observation(self):
        checkpoint, old, _, _ = fixture()
        checkpoint["ecosystem"]["day"] += 1
        with self.assertRaisesRegex(ValueError, "observation days"):
            build_report_v2(checkpoint, old)
        checkpoint, old, _, _ = fixture()
        checkpoint["runner"]["sessions"].pop()
        with self.assertRaisesRegex(ValueError, "session counts"):
            build_report_v2(checkpoint, old)

    def test_corrected_pair_headlines_and_world_unit_are_preserved(self):
        cp_a, old_a, _, _ = fixture()
        cp_b, old_b, _, _ = fixture(native=True, algorithm="skillopt")
        result = compare_reports_v2([build_report_v2(cp_a, old_a), build_report_v2(cp_b, old_b)])
        summary = result["metric_summaries"]["commitment_fulfillment_rate"]
        self.assertAlmostEqual(summary["mean_delta"], 7 / 8 - 6 / 7)
        self.assertEqual(summary["world_pairs"], 1)
        self.assertIsNone(summary["bootstrap_95_percent_interval"])
        self.assertEqual(result["metric_summaries"]["fixed_demand_fulfillment_rate"]["mean_delta"], 0)
        self.assertNotIn("obligation_success_rate", result["metric_summaries"])

    def test_tampered_headline_or_breakdown_is_rejected(self):
        checkpoint, old, _, _ = fixture()
        corrected = build_report_v2(checkpoint, old)
        corrected["headline"]["value"] = 1
        with self.assertRaisesRegex(ValueError, "headline"):
            validate_report_v2(corrected)
        corrected = build_report_v2(checkpoint, old)
        corrected["source_breakdown"]["benchmark"]["fulfillment_rate"] = .5
        with self.assertRaisesRegex(ValueError, "breakdown"):
            validate_report_v2(corrected)


class VersionedFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source_files(self, *, status="completed"):
        checkpoint, old, _, _ = fixture(status=status)
        (self.root / "checkpoint.json").write_text(json.dumps(checkpoint, indent=3) + "\n\n")
        (self.root / "REPORT.json").write_text(json.dumps(old, indent=3) + "\n\n")
        return checkpoint, old

    def test_original_bytes_are_preserved_and_hashes_match(self):
        self.source_files()
        old = (self.root / "REPORT.json").read_bytes()
        checkpoint = (self.root / "checkpoint.json").read_bytes()
        result = write_report_v2(self.root)
        self.assertEqual((self.root / "REPORT.json").read_bytes(), old)
        self.assertEqual((self.root / "checkpoint.json").read_bytes(), checkpoint)
        self.assertEqual(result["source_hashes"]["v1_report_sha256"], hashlib.sha256(old).hexdigest())
        self.assertEqual(result["source_hashes"]["checkpoint_sha256"], hashlib.sha256(checkpoint).hexdigest())
        self.assertEqual(load_verified_report_v2(self.root / "REPORT.v2.json"), result)
        self.assertEqual(write_report_v2(self.root), result)

    def test_changed_source_after_correction_is_rejected(self):
        self.source_files()
        write_report_v2(self.root)
        with (self.root / "checkpoint.json").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            load_verified_report_v2(self.root / "REPORT.v2.json")
        with self.assertRaisesRegex(ValueError, "already exists"):
            write_report_v2(self.root)

    def test_inflight_and_noncompleted_inputs_never_write_final_v2(self):
        for status in ("failed", "paused_invocation_limit", "exhausted_work_budget"):
            self.source_files(status=status)
            with self.assertRaisesRegex(ValueError, "Only completed"):
                write_report_v2(self.root)
            self.assertFalse((self.root / "REPORT.v2.json").exists())
        self.source_files()
        (self.root / "INFLIGHT.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "reconciliation"):
            write_report_v2(self.root)

    def test_cli_exits_nonzero_on_noncompleted_or_invalid_evidence(self):
        self.source_files(status="failed")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluation_report_v2.py"), str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "REPORT.v2.json").exists())
        checkpoint, old = self.source_files()
        checkpoint["runner"]["sessions"][0]["task_id"] = "wrong"
        (self.root / "checkpoint.json").write_text(json.dumps(checkpoint))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluation_report_v2.py"), str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Correction audit failed", result.stderr)
        self.assertFalse((self.root / "REPORT.v2.json").exists())

    def test_comparison_cli_requires_explicit_legacy_opt_in(self):
        self.source_files()
        script = str(ROOT / "scripts/compare_evaluations.py")
        result = subprocess.run([sys.executable, script, str(self.root / "REPORT.json"), "--out", str(self.root / "comparison.json")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical REPORT.v2.json", result.stderr)
        write_report_v2(self.root)
        result = subprocess.run([sys.executable, script, str(self.root / "REPORT.v2.json"), "--out", str(self.root / "comparison.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        comparison = json.loads((self.root / "comparison.json").read_text())
        self.assertEqual(comparison["canonical_headline"], "commitment_fulfillment_rate")
        self.assertEqual(len(comparison["incomplete_pairs"]), 1)

    def test_comparison_rejects_different_correction_implementation_hashes(self):
        self.source_files()
        first = write_report_v2(self.root)
        second = deepcopy(first)
        second["source_hashes"]["postprocessor_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "same pinned postprocessor"):
            compare_reports_v2([first, second])

    def test_matching_but_fabricated_processor_hash_cannot_pass_local_verification(self):
        self.source_files()
        value = write_report_v2(self.root)
        value["source_hashes"]["postprocessor_sha256"] = "b" * 64
        (self.root / "REPORT.v2.json").write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "matching historical processor"):
            load_verified_report_v2(self.root / "REPORT.v2.json")


if __name__ == "__main__":
    unittest.main()
