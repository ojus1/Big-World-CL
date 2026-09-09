"""Fabricated selection/receipt fixtures; no native execution or quality evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.calibration_bank import aggregate_repeats, build_bank, expected_slots, select_bank


def source_fixture():
    config = {"algorithm": "no_learning", "split": "dev", "state_mode": "skill_transfer", "days": 8,
              "seed": 101, "max_iterations": 16, "max_output_tokens": 4096}
    scenario = {"seed": 101, "split": "dev", "days": 8, "change_day": 3,
                "exception_window": [4, 6], "reversal_day": 6}
    manifest = {"config": config, "scenario": scenario, "target_model": "offline-fixture-model",
                "model_base_url": "https://fixture.example.invalid", "source_sha256": {"fixture.py": "a" * 64},
                "dependencies": {"hermes": "offline-fixture"}}
    provenance = {key: deepcopy(manifest[key]) for key in ("target_model", "model_base_url", "source_sha256", "dependencies")}
    provenance["persona_cohort_sha256"] = "b" * 64
    worlds, sessions, capsules = {}, [], {}
    missing = {("firm-0__onboarding-regulated", "exception"), ("firm-0__renewal-regulated", "exception")}
    for firm in ("firm-0", "firm-1"):
        employees = {}
        for workflow in ("onboarding", "renewal", "incident"):
            local = workflow + "-regulated"
            employee = firm + "__" + local
            employees[local] = {"id": local, "workflow": workflow}
            for regime, day in (("base", 0), ("changed", 3), ("exception", 4), ("reversal", 6)):
                if (employee, regime) in missing:
                    continue
                identifier = employee + "-" + regime + "-first"
                task_id = employee + "-task-" + regime
                if workflow == "incident" and ((firm == "firm-0" and regime in ("changed", "exception"))
                                               or (firm == "firm-1" and regime in ("exception", "reversal"))):
                    task_id = employee + "-repeated-obligation"
                success = len(sessions) % 4 != 0
                row = {"id": identifier, "task_id": task_id, "case_id": task_id, "employee": employee,
                       "day": day, "regime": regime, "success": success, "semantic_score": float(success),
                       "budget_exhausted": not success, "skill_loaded": True, "infrastructure_valid": True}
                sessions.append(row)
                capsules[identifier] = {"employee": employee, "firm": firm, "task_id": task_id,
                    "request": "PRIVATE_REQUEST_NEVER_IN_BANK",
                    "case": {"id": task_id, "workflow": workflow, "day": day, "regime": regime, "split": "online",
                             "public_files": {"task.json": "PRIVATE_TASK_CONTENT_NEVER_IN_BANK"},
                             "private": {"expected": "PRIVATE_RUBRIC_TRUTH_NEVER_IN_BANK"}},
                    "ecosystem": {"day": day, "worlds": {firm: {"tasks": {task_id: {"id": task_id, "owner": local, "status": "pending"}}}}}}
        worlds[firm] = {"employees": employees}
    # A later successful session must never replace an earlier failed selection.
    row = deepcopy(sessions[0])
    row.update(id="later-success", day=1, success=True, semantic_score=1.0, budget_exhausted=False)
    sessions.append(row)
    later = deepcopy(capsules[sessions[0]["id"]])
    later["case"]["day"] = later["ecosystem"]["day"] = 1
    capsules[row["id"]] = later
    checkpoint = {"ecosystem": {"day": 9, "worlds": worlds}, "runner": {"sessions": sessions}}
    report = {"status": "completed", "audit": {"eligible_for_paired_inference": True},
              "config": deepcopy(config), "scenario": deepcopy(scenario), "provenance": provenance,
              "horizon": {"observed_world_day": 9}, "prospective": {"attempts": len(sessions)}}
    return checkpoint, manifest, capsules, report


def receipt(slot, *, success=True, score=None, status="completed", budget=False):
    return {**slot, "status": status, "success": success,
            "semantic_score": float(success) if score is None else score,
            "infrastructure_valid": status == "completed", "budget_exhausted": budget, "skill_loaded": True,
            "usage": {"total_tokens": 100, "input_tokens": 75, "output_tokens": 25, "api_calls": 3,
                      "charged_tokens": 100, "complete": True, "estimated_cost_usd": .01},
            "diagnostic": {"cost": .2, "expected_procedure": "DO_NOT_EXPORT_PRIVATE_DIAGNOSTIC"},
            "elapsed_seconds": 4,
            "artifact_relative_path": "replays/" + slot["rollout_id"] + "/session.json"}


class OutcomeBlindSelectionTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint, self.manifest, self.capsules, self.report = source_fixture()

    def select(self):
        return select_bank(self.checkpoint, self.manifest, self.capsules, self.report)

    def test_earliest_selection_is_outcome_blind_and_order_independent(self):
        original = self.select()
        selected = [row["selection_id"] for row in original["selections"]]
        self.assertNotIn("later-success", selected)
        for row in self.checkpoint["runner"]["sessions"]:
            row["success"] = not row["success"]
            row["semantic_score"] = .5
            row["budget_exhausted"] = not row["budget_exhausted"]
            row["skill_loaded"] = False
        self.checkpoint["runner"]["sessions"].reverse()
        result = self.select()
        self.assertEqual([row["selection_id"] for row in result["selections"]], selected)
        self.assertNotEqual([row["original_outcome"] for row in original["selections"]],
                            [row["original_outcome"] for row in result["selections"]])

    def test_lexical_session_id_breaks_day_ties_without_outcome_use(self):
        source = deepcopy(self.checkpoint["runner"]["sessions"][0])
        source.update(id="a-chronological-tie", success=True, semantic_score=1)
        self.checkpoint["runner"]["sessions"].append(source)
        self.capsules[source["id"]] = deepcopy(self.capsules[self.checkpoint["runner"]["sessions"][0]["id"]])
        self.report["prospective"]["attempts"] += 1
        result = self.select()
        self.assertIn(source["id"], [row["selection_id"] for row in result["selections"]])

    def test_missing_cells_and_repeated_obligations_remain_visible(self):
        result = self.select()
        self.assertEqual(result["expected_cell_count"], 24)
        self.assertEqual(result["selected_cell_count"], 22)
        self.assertEqual(result["expected_rollout_count"], 44)
        self.assertEqual(len(result["missing_cells"]), 2)
        self.assertEqual(result["dependence"]["underlying_obligation_count"], 20)
        self.assertEqual(len(result["dependence"]["repeated_obligation_groups"]), 2)

    def test_public_bank_has_hashes_but_no_private_capsule_content(self):
        result = self.select()
        text = json.dumps(result)
        for marker in ("PRIVATE_REQUEST_NEVER_IN_BANK", "PRIVATE_TASK_CONTENT_NEVER_IN_BANK", "PRIVATE_RUBRIC_TRUTH_NEVER_IN_BANK"):
            self.assertNotIn(marker, text)
        for row in result["selections"]:
            self.assertEqual(len(row["case_sha256"]), 64)
            self.assertEqual(len(row["capsule_sha256"]), 64)
            self.assertEqual(row["source_case_path"], "private/cases/" + row["source_session_id"] + ".json")

    def test_scope_split_and_provenance_fail_closed(self):
        for field, value in (("algorithm", "skillopt"), ("split", "test"), ("state_mode", "full_deployment")):
            checkpoint, manifest, capsules, report = source_fixture()
            manifest["config"][field] = value
            report["config"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                select_bank(checkpoint, manifest, capsules, report)
        self.report["provenance"]["target_model"] = "other-model"
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.select()

    def test_selected_capsule_cannot_change_employee_split_or_workflow(self):
        identifier = self.checkpoint["runner"]["sessions"][0]["id"]
        for mutate in (lambda cap: cap.update(employee="another-employee"),
                       lambda cap: cap["case"].update(split="test"),
                       lambda cap: cap["case"].update(workflow="incident"),
                       lambda cap: cap["case"].update(day=7)):
            original = deepcopy(self.capsules[identifier])
            mutate(self.capsules[identifier])
            with self.assertRaises(ValueError):
                self.select()
            self.capsules[identifier] = original

    def test_missing_first_capsule_does_not_fall_back_to_later_success(self):
        identifier = self.checkpoint["runner"]["sessions"][0]["id"]
        del self.capsules[identifier]
        with self.assertRaisesRegex(ValueError, "do not substitute"):
            self.select()

    def test_source_and_manifest_inputs_are_not_mutated(self):
        before = deepcopy((self.checkpoint, self.manifest, self.capsules, self.report))
        self.assertEqual(self.select(), self.select())
        self.assertEqual((self.checkpoint, self.manifest, self.capsules, self.report), before)

    def test_source_regime_and_id_integrity_are_checked(self):
        self.checkpoint["runner"]["sessions"][0]["regime"] = "reversal"
        with self.assertRaisesRegex(ValueError, "regime"):
            self.select()
        self.checkpoint, self.manifest, self.capsules, self.report = source_fixture()
        self.checkpoint["runner"]["sessions"][1]["id"] = self.checkpoint["runner"]["sessions"][0]["id"]
        with self.assertRaisesRegex(ValueError, "unique safe"):
            self.select()

    def test_file_builder_pins_raw_checkpoint_manifest_and_capsule_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            for name, value in (("checkpoint.json", self.checkpoint), ("manifest.json", self.manifest), ("REPORT.json", self.report)):
                (path / name).write_text(json.dumps(value, indent=3) + "\n\n")
            (path / "private/cases").mkdir(parents=True)
            for identifier, value in self.capsules.items():
                (path / "private/cases" / (identifier + ".json")).write_text(json.dumps(value, indent=2) + "\n")
            result = build_bank(path)
            self.assertEqual(result["source"]["hashes"]["checkpoint_sha256"], hashlib.sha256((path / "checkpoint.json").read_bytes()).hexdigest())
            first = result["selections"][0]
            self.assertEqual(first["capsule_sha256"], hashlib.sha256((path / first["source_case_path"]).read_bytes()).hexdigest())
            self.assertEqual(first["capsule_hash_encoding"], "raw_file_bytes")


class RepeatAggregationTests(unittest.TestCase):
    def setUp(self):
        self.bank = select_bank(*source_fixture())
        self.slots = expected_slots(self.bank)

    def test_expected_slots_are_unique_zero_based_and_consistent(self):
        self.assertEqual(len(self.slots), 44)
        self.assertEqual({slot["repeat_index"] for slot in self.slots}, {0, 1})
        self.assertEqual(len({slot["rollout_id"] for slot in self.slots}), 44)
        self.bank["expected_rollout_count"] += 1
        with self.assertRaisesRegex(ValueError, "counts"):
            expected_slots(self.bank)

    def test_disagreement_and_failure_categories_are_not_conflated_with_budget(self):
        results = [receipt(slot) for slot in self.slots]
        results[0] = receipt(self.slots[0], success=False, score=.7, budget=True)
        results[2] = receipt(self.slots[2], success=False, score=1, budget=True)
        report = aggregate_repeats(self.bank, results)
        self.assertEqual(report["repeat_stability"]["evaluable_case_pairs"], 22)
        self.assertEqual(report["repeat_stability"]["disagreeing_case_pairs"], 2)
        self.assertEqual(report["counts"]["substantive_incomplete"], 1)
        self.assertEqual(report["counts"]["protocol_incomplete"], 1)
        self.assertEqual(report["counts"]["budget_exhausted"], 2)
        self.assertEqual(report["counts"]["strict_success"], 42)
        self.assertIsNone(report["repeat_stability"]["confidence_interval"])
        self.assertTrue(report["complete"])
        self.assertTrue(report["all_native_receipts_valid"])

    def test_partial_results_and_infrastructure_errors_remain_in_planned_counts(self):
        results = [receipt(self.slots[0]), {**self.slots[1], "status": "infrastructure_error", "infrastructure_valid": False},
                   receipt(self.slots[2], status="infrastructure_invalid")]
        report = aggregate_repeats(self.bank, results)
        self.assertEqual(report["expected_slots"], 44)
        self.assertEqual(report["counts"]["missing"], 41)
        self.assertEqual(report["counts"]["infrastructure_error"], 1)
        self.assertEqual(report["counts"]["infrastructure_invalid"], 1)
        self.assertEqual(report["outcomes"]["strict_success_rate_completed_receipts"], 1)
        self.assertEqual(report["outcomes"]["confirmed_success_fraction_all_planned_slots"], 1 / 44)
        self.assertEqual(report["repeat_stability"]["evaluable_case_pairs"], 0)
        self.assertEqual(report["repeat_stability"]["unevaluable_case_pairs"], 22)
        self.assertIsNone(report["costs"]["tokens"]["total"])
        self.assertEqual(report["costs"]["tokens"]["recorded_total"], 200)
        self.assertFalse(report["complete"])

    def test_unknown_or_duplicate_receipts_are_rejected(self):
        result = receipt(self.slots[0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            aggregate_repeats(self.bank, [result, result])
        for fields in ({"selection_id": "not-in-bank"}, {"repeat_index": 2}, {"repeat_index": True}, {"rollout_id": "wrong-id"}):
            invalid = {**result, **fields}
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                aggregate_repeats(self.bank, [invalid])

    def test_complete_receipts_need_consistent_execution_outcomes(self):
        for change in ({"infrastructure_valid": False}, {"success": 1}, {"semantic_score": float("nan")},
                       {"success": True, "semantic_score": .7}, {"status": "infrastructure_error"}):
            result = {**receipt(self.slots[0]), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                aggregate_repeats(self.bank, [result])

    def test_missing_currency_and_reserved_tokens_are_not_reported_as_actual(self):
        results = [receipt(slot) for slot in self.slots]
        results[0]["usage"] = {"charged_tokens": 10000, "physical_model_calls": 3, "complete": False, "cost_status": "unknown"}
        report = aggregate_repeats(self.bank, results)
        self.assertIsNone(report["costs"]["tokens"]["total"])
        self.assertEqual(report["costs"]["charged_tokens"]["total"], 14300)
        self.assertIsNone(report["costs"]["estimated_usd"]["total"])
        self.assertFalse(report["accounting_complete"])

    def test_receipt_paths_stay_relative_and_private_diagnostics_are_excluded(self):
        result = receipt(self.slots[0])
        report = aggregate_repeats(self.bank, [result])
        self.assertNotIn("DO_NOT_EXPORT_PRIVATE_DIAGNOSTIC", json.dumps(report))
        result["artifact_relative_path"] = "../../private.json"
        with self.assertRaisesRegex(ValueError, "relative"):
            aggregate_repeats(self.bank, [result])

    def test_aggregation_is_deterministic_and_ignores_result_order(self):
        results = [receipt(slot) for slot in self.slots]
        before = deepcopy(results)
        first = aggregate_repeats(self.bank, results)
        self.assertEqual(first, aggregate_repeats(self.bank, list(reversed(results))))
        self.assertEqual(results, before)
        self.assertEqual(first["coverage"]["underlying_obligation_count"], 20)


if __name__ == "__main__":
    unittest.main()
