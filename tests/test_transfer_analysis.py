"""Fabricated offline outcomes; never native calibration or transfer evidence."""
from copy import deepcopy
import json
import unittest

from lifespan.evaluation.protocol import experience_split
from scripts.calibration_bank import VERSION as BANK_VERSION, expected_slots
from scripts.transfer_analysis import aggregate_probes, select_employee
from scripts.transfer_probes import build_transfer_probes, public_probe_manifest
from tests.test_transfer_probes import fixture


def selection_fixture():
    source = fixture()
    source["runner"]["sessions"] = []
    source["runner"]["experiences"] = []
    selections, missing = [], []
    for firm, world in source["ecosystem"]["worlds"].items():
        for local in sorted(world["employees"]):
            employee = firm + "__" + local
            for regime, day in (("base", 0), ("changed", 3), ("exception", 4), ("reversal", 6)):
                if firm == "firm-0" and local != "incident-regulated" and regime == "exception":
                    missing.append({"employee": employee, "regime": regime})
                    continue
                identifier = employee + "-" + regime
                task_id = identifier + "-obligation"
                selections.append({"selection_id": identifier, "employee": employee, "regime": regime,
                                   "source_day": day, "source_task_id": task_id})
                source["runner"]["sessions"].append({"id": identifier, "employee": employee,
                    "day": day, "regime": regime, "task_id": task_id})
            for split in ("train", "val"):
                tasks = []
                number = 0
                while len(tasks) < 3:
                    task_id = employee + "-experience-" + str(number)
                    number += 1
                    if experience_split(task_id) == split:
                        tasks.append(task_id)
                for index, task_id in enumerate(tasks):
                    identifier = task_id + "-session"
                    source["runner"]["sessions"].append({"id": identifier, "employee": employee,
                        "day": index + 5, "regime": "reversal", "task_id": task_id})
                    source["runner"]["experiences"].append({"id": identifier, "employee": employee,
                        "source_session": task_id, "split": split, "available_day": index + 6,
                        "feedback_available_day": index + 6, "prompt": "PRIVATE_SOURCE_PROMPT",
                        "context": "PRIVATE_SOURCE_FILES", "feedback": "PRIVATE_SOURCE_FEEDBACK"})
    bank = {"bank_version": BANK_VERSION, "repeats_per_selection": 2, "selections": selections,
            "selected_cell_count": 22, "expected_rollout_count": 44, "expected_cell_count": 24,
            "missing_cells": missing}
    results = [{**slot, "status": "completed", "infrastructure_valid": True, "success": True}
               for slot in expected_slots(bank)]
    for employee, failure_count in (("firm-0__incident-regulated", 4), ("firm-1__incident-regulated", 6)):
        rows = [row for row in results if row["selection_id"].startswith(employee)]
        for row in rows[:failure_count]:
            row["success"] = False
    by_id = {row["id"]: row for row in source["runner"]["sessions"]}
    source["runner"]["experiences"].sort(key=lambda row: by_id[row["id"]]["day"])
    return source, bank, {"status": "completed", "results": results}


def probe_fixture():
    manifest = public_probe_manifest(build_transfer_probes(fixture(), "firm-1__incident-regulated"))
    slots = [{"rollout_id": f"probe-{probe}-r{repeat}-{arm}", "probe_index": probe,
              "repeat_index": repeat, "arm": arm}
             for probe in range(4) for repeat in range(2)
             for arm in (("seed", "deployed") if repeat == 0 else ("deployed", "seed"))]
    results = [{**slot, "status": "completed", "infrastructure_valid": True, "success": True,
                "semantic_score": 1.0, "budget_exhausted": False, "skill_loaded": True,
                "usage": {"complete": True, "total_tokens": 100, "api_calls": 3, "charged_tokens": 120,
                          "estimated_cost_usd": .01}, "elapsed_seconds": 2,
                "diagnostic": {"cost": .1, "expected_procedure": "PRIVATE_TRUTH_DO_NOT_EXPORT"},
                "private_extra": "PRIVATE_EXTRA_DO_NOT_EXPORT"} for slot in slots]
    return manifest, slots, results


class EmployeeSelectionTests(unittest.TestCase):
    def test_failure_count_selects_eligible_employee_and_latest_two_plus_two(self):
        source, bank, state = selection_fixture()
        before = deepcopy((source, bank, state))
        result = select_employee(source, bank, state)
        self.assertEqual(result["employee"], "firm-1__incident-regulated")
        self.assertEqual([row["split"] for row in result["experiences"]], ["train", "train", "val", "val"])
        self.assertEqual([row["available_day"] for row in result["experiences"]], [7, 8, 7, 8])
        row = result["ranking"][0]
        self.assertEqual((row["train_unique_count"], row["val_unique_count"]), (3, 3))
        self.assertEqual((row["calibration_failures"], row["calibration_attempts"]), (6, 8))
        self.assertEqual(len(result["ranking"]), 6)
        self.assertNotIn("PRIVATE_", json.dumps(result["ranking"]))
        self.assertEqual((source, bank, state), before)
        result["experiences"][0]["prompt"] = "MUTATED"
        self.assertEqual((source, bank, state), before)

    def test_tie_break_is_employee_id_not_outcome_or_input_order(self):
        source, bank, state = selection_fixture()
        rows = [row for row in state["results"] if row["selection_id"].startswith("firm-0__incident-regulated")]
        for row in rows[:6]:
            row["success"] = False
        state["results"].reverse()
        result = select_employee(source, bank, state)
        self.assertEqual(result["employee"], "firm-0__incident-regulated")
        self.assertEqual([row["available_day"] for row in result["experiences"]], [7, 8, 7, 8])

    def test_nonchronological_original_experiences_are_rejected_not_normalized(self):
        source, bank, state = selection_fixture()
        source["runner"]["experiences"].reverse()
        with self.assertRaisesRegex(ValueError, "already be chronological"):
            select_employee(source, bank, state)

    def test_high_failure_employee_ineligible_until_both_feedback_and_observation_release(self):
        source, bank, state = selection_fixture()
        rows = [row for row in source["runner"]["experiences"] if row["employee"] == "firm-1__incident-regulated" and row["split"] == "val"]
        rows[1]["available_day"] = 10
        rows[2]["feedback_available_day"] = 10
        result = select_employee(source, bank, state, cutoff_day=9)
        self.assertEqual(result["employee"], "firm-0__incident-regulated")
        delayed = next(row for row in result["ranking"] if row["employee"] == "firm-1__incident-regulated")
        self.assertFalse(delayed["eligible"])
        self.assertEqual(delayed["val_unique_count"], 1)
        self.assertEqual(select_employee(source, bank, state, cutoff_day=10)["employee"], "firm-1__incident-regulated")

    def test_retries_do_not_inflate_counts_and_latest_eligible_retry_is_used(self):
        source, bank, state = selection_fixture()
        original = next(row for row in source["runner"]["experiences"] if row["employee"] == "firm-1__incident-regulated" and row["split"] == "train")
        retry = {**original, "id": original["id"] + "-retry", "available_day": 9, "feedback_available_day": 9}
        source["runner"]["experiences"].append(retry)
        source["runner"]["sessions"].append({"id": retry["id"], "employee": retry["employee"],
            "day": 8, "regime": "reversal", "task_id": retry["source_session"]})
        result = select_employee(source, bank, state)
        self.assertEqual(result["ranking"][0]["train_unique_count"], 3)
        # Published selector updates the original obligation in its original
        # insertion position; it is intentionally not replaced with a new rule.
        self.assertEqual(len({row["source_session"] for row in result["experiences"]}), 4)
        from lifespan.evaluation.protocol import select_experiences
        ordered = sorted(source["runner"]["experiences"], key=lambda row: next(s["day"] for s in source["runner"]["sessions"] if s["id"] == row["id"]))
        self.assertEqual(result["experiences"], select_experiences(ordered, result["employee"], 9, 2, 2))

    def test_partial_invalid_unknown_and_duplicate_calibration_cannot_select(self):
        source, bank, state = selection_fixture()
        mutations = [lambda value: value.update(status="running"),
                     lambda value: value["results"].pop(),
                     lambda value: value["results"].append(deepcopy(value["results"][0])),
                     lambda value: value["results"][0].update(success=1),
                     lambda value: value["results"][0].update(success=None),
                     lambda value: value["results"][0].update(infrastructure_valid=False),
                     lambda value: value["results"][0].update(status="infrastructure_error"),
                     lambda value: value["results"][0].update(rollout_id="wrong"),
                     lambda value: value["results"][0].update(selection_id="unknown")]
        for mutation in mutations:
            altered = deepcopy(state)
            mutation(altered)
            with self.assertRaises(ValueError):
                select_employee(source, bank, altered)

    def test_scope_split_original_identity_and_empty_eligibility_are_checked(self):
        source, bank, state = selection_fixture()
        altered_bank = deepcopy(bank)
        altered_bank["selections"][0]["employee"] = "nonexistent"
        with self.assertRaises(ValueError):
            select_employee(source, altered_bank, state)
        for field, value in (("split", "test"), ("source_session", "unrelated"), ("employee", "nonexistent"), ("available_day", True)):
            altered = deepcopy(source)
            altered["runner"]["experiences"][0][field] = value
            with self.assertRaises(ValueError):
                select_employee(altered, bank, state)
        source["runner"]["experiences"] = []
        with self.assertRaisesRegex(ValueError, "No source employee"):
            select_employee(source, bank, state)


class TransferAggregationTests(unittest.TestCase):
    def test_complete_pair_summary_has_counts_scores_costs_and_no_ci(self):
        manifest, slots, results = probe_fixture()
        before = deepcopy((manifest, slots, results))
        results[1].update(success=False, semantic_score=.5, budget_exhausted=True)
        # The second repeat is counterbalanced: index2 is deployed, index3 seed.
        results[3].update(success=False, semantic_score=1.0, skill_loaded=False)
        result = aggregate_probes(manifest, slots, results, same_skill=False)
        self.assertTrue(result["complete"])
        self.assertEqual(result["totals"]["planned"], 16)
        self.assertEqual(result["totals"]["successes"], 14)
        self.assertEqual(result["totals"]["substantive_incomplete"], 1)
        self.assertEqual(result["totals"]["protocol_incomplete"], 1)
        self.assertEqual(result["arms"]["seed"]["successes"], 7)
        self.assertEqual(result["arms"]["deployed"]["successes"], 7)
        self.assertEqual(result["arms"]["seed"]["regimes"]["changed"]["planned"], 4)
        self.assertEqual(result["arms"]["deployed"]["regimes"]["reversal"]["successes"], 4)
        self.assertEqual(result["paired"]["disagreeing_pairs"], 2)
        self.assertEqual(result["paired"]["evaluable_pairs"], 8)
        self.assertEqual(result["paired"]["seed_only_success_pairs"], 1)
        self.assertEqual(result["paired"]["deployed_only_success_pairs"], 1)
        self.assertEqual(result["paired"]["mean_semantic_delta_deployed_minus_seed"], -.5 / 8)
        self.assertIsNone(result["paired"]["confidence_interval"])
        self.assertEqual(result["totals"]["costs"]["tokens"]["total"], 1600)
        self.assertEqual(result["totals"]["costs"]["charged_tokens"]["total"], 1920)
        self.assertEqual(result["totals"]["costs"]["physical_model_calls"]["total"], 48)
        self.assertEqual((manifest, slots), before[:2])

    def test_missing_and_errors_preserve_all_slots_and_charged_reservation(self):
        manifest, slots, results = probe_fixture()
        results.pop()
        results[0].update(status="infrastructure_error", infrastructure_valid=False, success=False, semantic_score=0,
                          usage={"complete": False, "total_tokens": None, "api_calls": None, "charged_tokens": 250000})
        result = aggregate_probes(manifest, slots, results, same_skill=True)
        self.assertFalse(result["complete"])
        self.assertFalse(result["receipts_complete"])
        self.assertEqual(result["totals"]["missing"], 1)
        self.assertEqual(result["totals"]["infrastructure_error"], 1)
        self.assertEqual(result["totals"]["failures"], 0)
        self.assertEqual(result["totals"]["completed"], 14)
        self.assertEqual(len(result["slots"]), 16)
        self.assertEqual(result["totals"]["strict_success_rate_completed"], 1)
        self.assertEqual(result["totals"]["confirmed_success_fraction_planned"], 14 / 16)
        self.assertEqual(result["paired"]["unevaluable_pairs"], 2)
        self.assertEqual(result["totals"]["costs"]["charged_tokens"]["recorded_total"], 250000 + 14 * 120)
        self.assertIsNone(result["totals"]["costs"]["charged_tokens"]["total"])
        self.assertEqual(result["totals"]["costs"]["tokens"]["unknown_slots"], 2)
        self.assertIsNone(result["slots"][0]["success"])
        self.assertEqual(result["comparison_type"], "A/A fixed-skill diagnostic")

    def test_complete_receipt_coverage_is_distinct_from_valid_execution(self):
        manifest, slots, results = probe_fixture()
        results[0].update(status="infrastructure_invalid", infrastructure_valid=False)
        summary = aggregate_probes(manifest, slots, results, same_skill=False)
        self.assertTrue(summary["receipts_complete"])
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["totals"]["successes"], 15)
        self.assertEqual(summary["totals"]["failures"], 0)

    def test_missing_measurements_and_currency_never_become_zero(self):
        manifest, slots, results = probe_fixture()
        results[0]["usage"].update(cost_status="unknown")
        results[1]["usage"] = {"complete": False, "total_tokens": 100, "api_calls": 3, "charged_tokens": None}
        results[1]["reserved_tokens"] = 5000
        results[2]["usage"] = {"complete": True, "input_tokens": 70, "output_tokens": 30,
                               "physical_model_calls": 2, "charged_tokens": 110}
        summary = aggregate_probes(manifest, slots, results, same_skill=True)
        costs = summary["totals"]["costs"]
        self.assertIsNone(costs["estimated_usd"]["total"])
        self.assertIsNone(costs["tokens"]["total"])
        self.assertEqual(costs["tokens"]["recorded_total"], 1500)
        self.assertEqual(costs["physical_model_calls"]["recorded_total"], 14 * 3 + 2)
        self.assertEqual(costs["charged_tokens"]["total"], 14 * 120 + 110 + 5000)
        self.assertFalse(summary["accounting_complete"])

    def test_unknown_empty_results_are_retained_with_no_score_or_pair_estimate(self):
        manifest, slots, _ = probe_fixture()
        summary = aggregate_probes(manifest, slots, [], same_skill=True)
        self.assertEqual(summary["totals"]["missing"], 16)
        self.assertEqual(summary["totals"]["failures"], 0)
        self.assertIsNone(summary["totals"]["mean_semantic_score_completed"])
        self.assertIsNone(summary["paired"]["disagreement_rate"])
        self.assertEqual(summary["paired"]["unevaluable_pairs"], 8)

    def test_invalid_slot_design_duplicate_and_unknown_receipts_fail(self):
        manifest, slots, results = probe_fixture()
        with self.assertRaises(ValueError):
            aggregate_probes(manifest, slots[:15], results[:15], same_skill=True)
        for field, value in (("rollout_id", slots[1]["rollout_id"]), ("probe_index", True),
                             ("repeat_index", 2), ("arm", "optimizer")):
            altered = deepcopy(slots)
            altered[0][field] = value
            with self.assertRaises(ValueError):
                aggregate_probes(manifest, altered, [], same_skill=True)
        for altered in (results + [results[0]], [{**results[0], "rollout_id": "unknown"}],
                        [{**results[0], "arm": "deployed"}]):
            with self.assertRaises(ValueError):
                aggregate_probes(manifest, slots, altered, same_skill=True)

    def test_malformed_completed_outcomes_cannot_enter_pairing(self):
        manifest, slots, results = probe_fixture()
        for field, value in (("success", 1), ("semantic_score", True), ("semantic_score", float("nan")),
                             ("semantic_score", .5), ("infrastructure_valid", False), ("status", "unknown")):
            altered = deepcopy(results)
            altered[0][field] = value
            with self.assertRaises(ValueError):
                aggregate_probes(manifest, slots, altered, same_skill=True)
        with self.assertRaises(ValueError):
            aggregate_probes(manifest, slots, results, same_skill=1)

    def test_summary_does_not_export_private_diagnostics_or_untrusted_fields(self):
        manifest, slots, results = probe_fixture()
        before = deepcopy((manifest, slots, results))
        summary = aggregate_probes(manifest, slots, results, same_skill=True)
        self.assertNotIn("PRIVATE_", json.dumps(summary))
        self.assertEqual((manifest, slots, results), before)
        shuffled = deepcopy(results)
        shuffled.reverse()
        self.assertEqual(aggregate_probes(manifest, slots, shuffled, same_skill=True), summary)


if __name__ == "__main__":
    unittest.main()
