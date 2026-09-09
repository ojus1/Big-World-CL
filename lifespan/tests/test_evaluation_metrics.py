from copy import deepcopy
import json
import unittest

from lifespan.evaluation.metrics import build_report, paired_report


def session(task_id, *, employee="firm0__worker", day=0, success=True,
            regime="base", score=None, tokens=100):
    return {"employee": employee, "day": day, "task_id": task_id,
            "success": success, "semantic_score": float(success) if score is None else score,
            "regime": regime, "skill_loaded": True, "infrastructure_valid": True,
            "usage": {"prompt_tokens": tokens - 20, "completion_tokens": 20, "api_calls": 2,
                      "estimated_cost_usd": .01, "cost_status": "estimated"},
            "diagnostic": {"cost": .3, "human_minutes": 2, "first_plan_correct": success},
            "elapsed_seconds": 3.0}


def task(task_id, *, created=0, completed=0, due=2, status="completed", owner="worker", attempts=1):
    return {"id": task_id, "owner": owner, "workflow": "onboarding", "created": created,
            "completed": completed, "due": due, "status": status, "attempts": attempts}


def snapshot(tasks, *, ledger=None, day=5, utility=9):
    if ledger is None:
        ledger = [{"task_id": row["id"], "owner": row["owner"], "amount": 10,
                   "settled": row["completed"] + 2 <= day, "settles": row["completed"] + 2}
                  for row in tasks if row["status"] == "completed" and type(row.get("completed")) is int]
    return {"day": day, "worlds": {"firm0": {"day": day, "tasks": deepcopy(tasks),
            "employees": [{"id": "worker"}, {"id": "unexposed"}],
            "ledger": deepcopy(ledger or []), "total_utility": utility}}}


def report(*, algorithm="no_learning", seed=1, sessions=None, tasks=None, updates=None,
           state=None, config=None, status="completed"):
    settings = {"algorithm": algorithm, "seed": seed, "split": "dev", "days": 4,
                "state_mode": "skill_transfer", "max_iterations": 16, "max_learning_calls": 100,
                **(config or {})}
    spec = {"seed": seed, "split": "dev", "days": settings["days"], "change_day": 1,
            "exception_window": [2, 3], "reversal_day": 3}
    return build_report(settings, spec,
                        [session("a")] if sessions is None else sessions,
                        [] if updates is None else updates,
                        snapshot([task("a")] if tasks is None else tasks) if state is None else state,
                        status=status, provenance={"target_model": "fixed-test-model", "source_revision": "revision-a",
                                                   "hermes_revision": "hermes-a", "skillopt_revision": "skillopt-a",
                                                   "mirofish_revision": "mirofish-a", "persona_cohort_sha256": "cohort-a"})


class ObligationMetricsTests(unittest.TestCase):
    def test_retries_do_not_inflate_obligations_or_hide_pending_work(self):
        records = [session("a", success=False, score=.4), session("a", day=1),
                   session("b", day=1, success=False, score=.2)]
        tasks = [task("a", completed=1, attempts=2), task("b", status="pending", completed=None),
                 task("c", status="pending", completed=None, attempts=0),
                 task("future", created=4, status="pending", completed=None, attempts=0)]
        result = report(sessions=records, tasks=tasks)
        obligations = result["obligations"]
        self.assertEqual(obligations["created_before_horizon"], 3)
        self.assertEqual(obligations["completed_before_horizon"], 1)
        self.assertEqual(obligations["success_rate"], 1 / 3)
        self.assertEqual(obligations["unattempted"], 1)
        self.assertEqual(obligations["pending_at_observation"], 2)
        self.assertEqual(obligations["right_censored_pending"], 2)
        self.assertEqual(obligations["recorded_retry_attempts"], 1)
        attempts = result["prospective"]
        self.assertEqual(attempts["attempts"], 3)
        self.assertEqual(attempts["distinct_obligations_attempted"], 2)
        self.assertEqual(attempts["retried_obligations"], 1)
        self.assertEqual(attempts["strict_success_rate"], 1 / 3)
        self.assertAlmostEqual(attempts["mean_semantic_score"], 1.6 / 3)

    def test_attempt_success_and_obligation_success_have_different_denominators(self):
        result = report(sessions=[session("a", success=False), session("a", day=1), session("b", day=2)],
                        tasks=[task("a", completed=1, attempts=2), task("b", completed=2)])
        self.assertEqual(result["obligations"]["success_rate"], 1)
        self.assertEqual(result["prospective"]["strict_success_rate"], 2 / 3)

    def test_completion_after_horizon_does_not_count_as_prospective_success(self):
        state = snapshot([task("a", completed=4)])
        result = report(sessions=[session("a", day=4)], state=state)
        self.assertEqual(result["obligations"]["completed_at_observation"], 1)
        self.assertEqual(result["obligations"]["completed_before_horizon"], 0)
        self.assertEqual(result["prospective"]["attempts"], 0)
        self.assertEqual(result["costs"]["execution"]["tokens"]["total"], 100)
        self.assertIn("work_attempts_after_action_horizon", result["audit"]["issues"])

    def test_two_firms_same_local_ids_remain_distinct(self):
        state = snapshot([task("a")])
        state["worlds"]["firm1"] = deepcopy(state["worlds"]["firm0"])
        result = report(sessions=[session("a"), session("a", employee="firm1__worker")], state=state)
        self.assertEqual(result["obligations"]["created_before_horizon"], 2)
        self.assertEqual(result["prospective"]["distinct_obligations_attempted"], 2)
        self.assertEqual(result["obligations"]["unattempted"], 0)

    def test_pending_and_abandoned_are_distinct_and_unserved_tasks_are_included(self):
        tasks = [task("a", status="pending", completed=None, attempts=0),
                 task("b", status="abandoned", completed=None, attempts=0)]
        result = report(sessions=[], tasks=tasks)
        self.assertEqual(result["obligations"]["success_rate"], 0)
        self.assertEqual(result["obligations"]["pending_at_observation"], 1)
        self.assertEqual(result["obligations"]["abandoned_at_observation"], 1)
        self.assertEqual(result["obligations"]["right_censored_pending"], 1)
        self.assertEqual(result["obligations"]["unattempted"], 2)
        self.assertIsNone(result["prospective"]["strict_success_rate"])

    def test_on_time_denominator_includes_all_due_obligations(self):
        tasks = [task("a", completed=2, due=1), task("b", status="pending", completed=None, due=2),
                 task("c", completed=1, due=2), task("d", completed=3, due=5)]
        result = report(tasks=tasks)
        self.assertEqual(result["obligations"]["due_before_horizon"], 3)
        self.assertEqual(result["obligations"]["on_time_success_rate"], 1 / 3)

    def test_unknown_completion_time_is_not_assumed_success(self):
        result = report(tasks=[task("a", completed=None)])
        self.assertIsNone(result["obligations"]["success_rate"])
        self.assertIn("unknown_completion_times", result["audit"]["issues"])

    def test_empty_trials_have_null_rates_and_are_not_comparison_evidence(self):
        result = report(tasks=[], sessions=[])
        self.assertIsNone(result["obligations"]["success_rate"])
        self.assertIsNone(result["prospective"]["mean_semantic_score"])
        self.assertIn("no_work_obligations", result["audit"]["issues"])


class ExposureAndCensoringTests(unittest.TestCase):
    def test_exposure_includes_employees_with_no_sessions(self):
        result = report(sessions=[session("a", day=0), session("a", day=1, regime="changed")])
        employees = {row["employee"]: row for row in result["exposure"]["employees"]}
        self.assertEqual(employees["firm0__unexposed"]["attempts"], 0)
        rows = result["exposure"]["employee_regimes"]
        self.assertEqual({row["regime"] for row in rows}, {"base", "changed"})
        self.assertEqual(next(row for row in rows if row["regime"] == "changed")["first_exposure_day"], 1)

    def test_success_delay_and_failed_next_regime_are_censored_separately(self):
        rows = [session("a", day=0), session("b", day=1, regime="changed", success=False),
                session("b", day=2, regime="changed"), session("c", day=3, regime="reversal", success=False)]
        result = report(sessions=rows, tasks=[task("a"), task("b", completed=2), task("c", status="pending", completed=None)])
        first, second = result["adaptation"]["events"]
        self.assertEqual(first["days_to_first_success"], 1)
        self.assertEqual(first["attempts_to_first_success"], 2)
        self.assertFalse(first["right_censored"])
        self.assertIsNone(second["days_to_first_success"])
        self.assertTrue(second["right_censored"])
        self.assertEqual(second["censor_day_exclusive"], 4)
        self.assertEqual(second["censor_reason"], "work_horizon")
        self.assertEqual(result["adaptation"]["right_censored_changes"], 1)

    def test_next_regime_success_does_not_retroactively_resolve_old_failure(self):
        rows = [session("a", day=0), session("b", day=1, regime="changed", success=False),
                session("c", day=2, regime="exception")]
        result = report(sessions=rows, tasks=[task("a"), task("b", status="pending", completed=None), task("c", completed=2)])
        events = result["adaptation"]["events"]
        self.assertTrue(events[0]["right_censored"])
        self.assertEqual(events[0]["censor_day_exclusive"], 2)
        self.assertEqual(events[0]["censor_reason"], "next_regime_exposure")
        self.assertEqual(events[1]["days_to_first_success"], 0)

    def test_initial_nonbase_exposure_is_not_an_observed_transition(self):
        result = report(sessions=[session("a", day=2, regime="changed")])
        self.assertEqual(result["adaptation"]["observed_changes"], 0)

    def test_incomplete_run_censoring_uses_actual_stop_not_planned_horizon(self):
        rows = [session("a"), session("b", day=1, regime="changed", success=False)]
        state = snapshot([task("a"), task("b", status="pending", completed=None)], day=1)
        result = report(sessions=rows, state=state, status="failed")
        event = result["adaptation"]["events"][0]
        self.assertEqual(event["censor_day_exclusive"], 2)
        self.assertEqual(event["censor_reason"], "run_stopped")
        self.assertFalse(result["audit"]["eligible_for_paired_inference"])


class SettlementAndCostTests(unittest.TestCase):
    def test_unsettled_rewards_are_not_added_to_realized_utility(self):
        ledger = [{"task_id": "a", "owner": "worker", "amount": 12, "settled": True, "settles": 2},
                  {"task_id": "b", "owner": "worker", "amount": 9, "settled": False, "settles": 7}]
        state = snapshot([task("a"), task("b", completed=3)], ledger=ledger, utility=10.2)
        result = report(state=state)
        business = result["business"]
        self.assertEqual(business["realized_utility"], 10.2)
        self.assertEqual(business["settled_reward"]["total"], 12)
        self.assertEqual(business["unsettled_reward"]["total"], 9)
        self.assertEqual(business["reward_censored_obligations"], 1)
        self.assertEqual(business["overdue_unsettled_entries"], 0)
        self.assertEqual(result["horizon"]["settlement_drain_days_observed"], 2)

    def test_missing_rewards_and_overdue_settlements_are_visible(self):
        ledger = [{"task_id": "a", "owner": "worker", "amount": 12, "settled": False, "settles": 2}]
        result = report(state=snapshot([task("a"), task("b")], ledger=ledger))
        self.assertEqual(result["business"]["overdue_unsettled_entries"], 1)
        self.assertEqual(result["business"]["completed_without_ledger"], 1)

    def test_execution_and_learning_costs_are_separate(self):
        updates = [{"employee": "firm0__worker", "day": 3, "accepted": True,
                    "costs": {"tokens": 700, "target_model_calls": 8, "optimizer_model_calls": 1,
                              "replays": 4, "wall_seconds": 20, "accounting_complete": True,
                              "estimated_cost_usd": .04}}]
        result = report(algorithm="skillopt", updates=updates)
        costs = result["costs"]
        self.assertEqual(costs["execution"]["tokens"]["total"], 100)
        self.assertEqual(costs["learning"]["tokens"]["total"], 700)
        self.assertEqual(costs["learner_total_tokens"], 800)
        self.assertAlmostEqual(costs["learner_estimated_usd"], .05)
        self.assertEqual(costs["learning"]["accepted_updates"], 1)
        self.assertIsNone(costs["all_in_estimated_usd"])
        self.assertIsNone(costs["environment"]["tokens"])

    def test_no_updates_is_known_zero_learning_cost(self):
        result = report()
        self.assertEqual(result["costs"]["learning"]["tokens"]["total"], 0)
        self.assertEqual(result["costs"]["learning"]["estimated_usd"]["total"], 0)
        self.assertTrue(result["costs"]["learning"]["accounting_complete"])

    def test_missing_costs_are_unknown_not_zero(self):
        good, missing = session("a"), session("b")
        missing["usage"] = {"cost_status": "unknown", "estimated_cost_usd": 0}
        result = report(sessions=[good, missing], tasks=[task("a"), task("b")])
        execution = result["costs"]["execution"]
        self.assertIsNone(execution["tokens"]["total"])
        self.assertEqual(execution["tokens"]["recorded_total"], 100)
        self.assertEqual(execution["tokens"]["missing_records"], 1)
        self.assertIsNone(execution["estimated_usd"]["total"])
        self.assertIsNone(result["costs"]["learner_total_tokens"])
        self.assertIn("incomplete_execution_or_learning_accounting", result["audit"]["issues"])

    def test_native_usage_aliases_and_explicit_total_tokens_work(self):
        row = session("a")
        row["usage"] = {"input_tokens": 60, "output_tokens": 30, "api_calls": 3, "complete": True}
        result = report(sessions=[row])
        self.assertEqual(result["costs"]["execution"]["tokens"]["total"], 90)
        row["usage"]["total_tokens"] = 95
        result = report(sessions=[row])
        self.assertEqual(result["costs"]["execution"]["tokens"]["total"], 95)
        self.assertIsNone(result["costs"]["execution"]["estimated_usd"]["total"])

    def test_reservations_are_not_reported_as_measured_learning_tokens(self):
        update = {"costs": {"tokens": 500, "target_model_calls": 8, "optimizer_model_calls": 1,
                            "accounting_complete": False}}
        result = report(algorithm="skillopt", updates=[update])
        tokens = result["costs"]["learning"]["tokens"]
        self.assertIsNone(tokens["total"])
        self.assertEqual(tokens["recorded_total"], 500)
        self.assertTrue(tokens["includes_unreconciled_reservations"])
        self.assertFalse(result["costs"]["learning"]["accounting_complete"])

    def test_partial_native_receipt_and_invalid_numbers_remain_unknown(self):
        row = session("a")
        row["usage"]["complete"] = False
        result = report(sessions=[row])
        self.assertIsNone(result["costs"]["execution"]["tokens"]["total"])
        row["usage"] = {"total_tokens": True, "api_calls": float("nan"), "estimated_cost_usd": float("inf")}
        result = report(sessions=[row])
        self.assertIsNone(result["costs"]["execution"]["tokens"]["total"])
        self.assertIsNone(result["costs"]["execution"]["model_calls"]["total"])
        self.assertIsNone(result["costs"]["execution"]["estimated_usd"]["total"])

    def test_infrastructure_failures_are_not_silently_removed_from_attempts(self):
        row = session("a", success=False)
        row["infrastructure_valid"] = False
        result = report(sessions=[row], tasks=[task("a", status="pending", completed=None)])
        self.assertEqual(result["prospective"]["attempts"], 1)
        self.assertEqual(result["prospective"]["strict_success_rate"], 0)
        self.assertEqual(result["prospective"]["infrastructure_invalid_or_unknown_attempts"], 1)
        self.assertFalse(result["audit"]["eligible_for_paired_inference"])

    def test_budget_exhaustion_and_not_loading_a_skill_are_behavioral_outcomes(self):
        row = session("a", success=False)
        row["budget_exhausted"] = True
        row["skill_loaded"] = False
        result = report(sessions=[row], tasks=[task("a", status="pending", completed=None)])
        self.assertTrue(result["audit"]["eligible_for_paired_inference"])
        self.assertEqual(result["prospective"]["budget_exhaustion_rate"], 1)
        self.assertEqual(result["prospective"]["skill_not_loaded_attempts"], 1)

    def test_physical_call_alias_and_charged_tokens_preserve_reservation_boundary(self):
        row = session("a")
        row["usage"] = {"physical_model_calls": 2, "charged_tokens": 800, "complete": False}
        result = report(sessions=[row])
        self.assertIsNone(result["costs"]["execution"]["tokens"]["total"])
        self.assertEqual(result["costs"]["execution"]["charged_tokens"]["total"], 800)
        self.assertEqual(result["costs"]["execution"]["model_calls"]["recorded_total"], 2)
        row["usage"] = {"physical_model_calls": 2, "input_tokens": 60, "output_tokens": 20}
        result = report(sessions=[row])
        self.assertEqual(result["costs"]["execution"]["model_calls"]["total"], 2)


class PairedWorldTests(unittest.TestCase):
    def test_single_pair_is_descriptive_without_confidence_interval(self):
        result = paired_report([report(), report(algorithm="skillopt")])
        self.assertEqual(len(result["eligible_pairs"]), 1)
        metric = result["metric_summaries"]["obligation_success_rate"]
        self.assertEqual(metric["mean_delta"], 0)
        self.assertEqual(metric["world_pairs"], 1)
        self.assertIsNone(metric["bootstrap_95_percent_interval"])
        self.assertEqual(metric["interpretation"], "descriptive_single_world_pair_no_ci")

    def test_bootstrap_unit_is_world_pair_not_correlated_sessions(self):
        failed_tasks = [task("a", status="pending", completed=None)]
        many_ids = ["a" + str(index) for index in range(100)]
        baseline_one = report(seed=1, tasks=[task(key, status="pending", completed=None) for key in many_ids],
                              sessions=[session(key, success=False) for key in many_ids])
        skill_one = report(seed=1, algorithm="skillopt", tasks=[task(key) for key in many_ids],
                           sessions=[session(key) for key in many_ids])
        baseline_two = report(seed=2)
        skill_two = report(seed=2, algorithm="skillopt", tasks=failed_tasks, sessions=[session("a", success=False)])
        result = paired_report([baseline_one, skill_one, baseline_two, skill_two])
        metric = result["metric_summaries"]["obligation_success_rate"]
        self.assertEqual(metric["world_pairs"], 2)
        self.assertEqual(metric["mean_delta"], 0)
        self.assertEqual(metric["bootstrap_95_percent_interval"], [-1, 1])
        # Hundreds of correlated employee tasks in seed 1 never make it weigh more than
        # the seed-2 ecosystem, nor create hundreds of independent replicates.
        self.assertEqual(result["metric_summaries"]["attempt_success_rate"]["world_pairs"], 2)
        self.assertEqual(result["metric_summaries"]["attempt_success_rate"]["mean_delta"], 0)

    def test_incompatible_shared_knobs_are_rejected(self):
        result = paired_report([report(), report(algorithm="skillopt", config={"max_iterations": 32})])
        self.assertFalse(result["eligible_pairs"])
        self.assertEqual(result["rejected_pairs"][0]["reason"], "incompatible_scenario_or_shared_configuration")
        self.assertIn("max_iterations", result["rejected_pairs"][0]["different_config_fields"])

    def test_missing_or_changed_provenance_is_rejected(self):
        missing = report(algorithm="skillopt")
        missing.pop("provenance")
        result = paired_report([report(), missing])
        self.assertEqual(result["rejected_pairs"][0]["reason"], "missing_treatment_independent_provenance")
        for key in ("target_model", "source_revision", "hermes_revision", "skillopt_revision", "mirofish_revision", "persona_cohort_sha256"):
            other = report(algorithm="skillopt")
            other["provenance"][key] = "different"
            result = paired_report([report(), other])
            self.assertEqual(result["rejected_pairs"][0]["reason"], "incompatible_model_source_or_population_provenance")
            self.assertIn(key, result["rejected_pairs"][0]["different_provenance_fields"])

    def test_different_realized_settlement_windows_are_rejected(self):
        other = report(algorithm="skillopt", state=snapshot([task("a")], day=6))
        result = paired_report([report(), other])
        self.assertEqual(result["rejected_pairs"][0]["reason"], "incompatible_observation_or_settlement_window")

    def test_scenario_changes_are_not_hidden_by_same_seed(self):
        other = report(algorithm="skillopt")
        other["scenario"]["change_day"] = 2
        result = paired_report([report(), other])
        self.assertTrue(result["rejected_pairs"][0]["scenario_differs"])

    def test_missing_and_incomplete_pairs_are_reported(self):
        result = paired_report([report(seed=1), report(seed=2), report(seed=2, algorithm="skillopt", status="failed")])
        self.assertEqual(len(result["incomplete_pairs"]), 2)
        self.assertEqual({row["reason"] for row in result["incomplete_pairs"]}, {"missing_algorithm", "run_not_completed"})
        self.assertFalse(result["eligible_pairs"])

    def test_ambiguous_duplicate_runs_are_rejected_not_arbitrarily_selected(self):
        result = paired_report([report(), report(), report(algorithm="skillopt")])
        self.assertEqual(result["rejected_pairs"][0]["reason"], "ambiguous_duplicate_algorithm_runs")

    def test_invalid_accounting_pair_is_explicitly_rejected(self):
        row = session("a")
        row["usage"] = {}
        result = paired_report([report(), report(algorithm="skillopt", sessions=[row])])
        self.assertEqual(result["rejected_pairs"][0]["reason"], "trial_audit_failed")

    def test_unknown_currency_is_missing_metric_not_zero_delta(self):
        rows = [session("a")]
        rows[0]["usage"].pop("estimated_cost_usd")
        result = paired_report([report(sessions=rows), report(algorithm="skillopt", sessions=rows)])
        self.assertEqual(len(result["eligible_pairs"]), 1)
        metric = result["metric_summaries"]["learner_estimated_usd"]
        self.assertIsNone(metric["mean_delta"])
        self.assertEqual(metric["world_pairs"], 0)
        self.assertEqual(metric["missing_metric_pairs"], 1)

    def test_state_modes_do_not_cross_pair(self):
        result = paired_report([report(), report(algorithm="skillopt", config={"state_mode": "full_deployment"})])
        self.assertFalse(result["eligible_pairs"])
        self.assertEqual(len(result["incomplete_pairs"]), 2)

    def test_paired_report_is_deterministic_and_does_not_mutate_inputs(self):
        reports = [report(seed=seed, algorithm=algorithm) for seed in (1, 2, 3) for algorithm in ("no_learning", "skillopt")]
        before = deepcopy(reports)
        first = paired_report(reports)
        self.assertEqual(first, paired_report(reports))
        self.assertEqual(reports, before)
        json.dumps(first, allow_nan=False)


class EvidenceIntegrityTests(unittest.TestCase):
    def test_completed_obligation_requires_one_successful_audited_session(self):
        for records in ([], [session("a", success=False)], [session("a"), session("a")]):
            result = report(sessions=records)
            self.assertFalse(result["audit"]["eligible_for_paired_inference"])
        result = report(sessions=[session("a", day=1)])
        self.assertIn("successful_session_world_state_disagreement", result["audit"]["issues"])

    def test_pending_world_task_cannot_have_a_successful_session(self):
        result = report(tasks=[task("a", status="pending", completed=None)])
        self.assertIn("successful_session_world_state_disagreement", result["audit"]["issues"])

    def test_missing_duplicate_and_overdue_settlements_invalidate_inference(self):
        result = report(state=snapshot([task("a")], ledger=[]))
        self.assertIn("completed_obligations_missing_ledger", result["audit"]["issues"])
        ledger = {"task_id": "a", "owner": "worker", "amount": 10, "settled": True, "settles": 2}
        result = report(state=snapshot([task("a")], ledger=[ledger, ledger]))
        self.assertIn("duplicate_obligation_ledger_entries", result["audit"]["issues"])
        ledger["settled"] = False
        result = report(state=snapshot([task("a")], ledger=[ledger]))
        self.assertIn("overdue_undelivered_settlements", result["audit"]["issues"])

    def test_completed_status_requires_configured_settlement_observation_drain(self):
        result = report(state=snapshot([task("a")], day=3))
        self.assertIn("required_settlement_drain_not_observed", result["audit"]["issues"])
        result = report(config={"settlement_delay": 4}, state=snapshot([task("a")], day=5))
        self.assertIn("required_settlement_drain_not_observed", result["audit"]["issues"])
        result = report(config={"settlement_delay": 0}, state=snapshot([task("a")], day=3))
        self.assertNotIn("required_settlement_drain_not_observed", result["audit"]["issues"])


if __name__ == "__main__":
    unittest.main()
