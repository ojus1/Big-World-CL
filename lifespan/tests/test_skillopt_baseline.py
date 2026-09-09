"""Offline bridge tests execute the real pinned SkillOpt-Sleep consolidation.

The target/optimizer callbacks are deterministic fixtures; these are contract
tests and supply no evidence of model learning gains.
"""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from lifespan.evaluation.skillopt import (
    DEFAULT_SOURCE, InvalidExperience, LearningBudget, SkillOptLearner,
    SkillOptUnavailable,
)


def experiences():
    return [
        {"id": "train-a", "split": "train", "available_day": 1,
         "prompt": "Reconcile account A", "context": "The ledger is in /workspace/a.csv",
         "source_session": "session-a", "feedback": "The total excluded a refund."},
        {"id": "val-b", "split": "val", "available_day": 1,
         "prompt": "Reconcile account B", "context": "The ledger is in /workspace/b.csv",
         "source_session": "session-b"},
    ]


def receipt(**extra):
    return dict(status="completed", tokens=10, model_calls=1, tool_calls=2,
                latency_ms=1.0, **extra)


class RecordingTarget:
    def __init__(self, rule="Include refunds"):
        self.calls = []
        self.rule = rule

    def __call__(self, payload, limits):
        self.calls.append(copy.deepcopy(payload))
        score = float(self.rule in payload["skill"])
        return receipt(hard=score, soft=score,
                       response="Reconciled ledger" if score else "Refund omitted",
                       feedback="The refund is missing from the computed total." if not score else "")


class RecordingOptimizer:
    def __init__(self, content="Include refunds when reconciling account ledgers."):
        self.calls = []
        self.content = content

    def __call__(self, payload, limits):
        self.calls.append(copy.deepcopy(payload))
        return receipt(response=json.dumps([{"op": "add", "content": self.content,
                                              "rationale": "Account for signed adjustments"}]))


class InputContractTests(unittest.TestCase):
    def reject(self, cases):
        with self.assertRaises(InvalidExperience):
            SkillOptLearner().update("Skill", cases, None, None, current_day=2)

    def test_test_cases_never_enter_the_optimizer(self):
        cases = experiences()
        cases.append(dict(cases[0], id="test", split="test"))
        self.reject(cases)

    def test_no_duplicate_ids_across_slices(self):
        cases = experiences()
        cases[1]["id"] = cases[0]["id"]
        self.reject(cases)

    def test_no_duplicate_task_with_different_id(self):
        cases = experiences()
        cases[1]["prompt"] = cases[0]["prompt"]
        cases[1]["context"] = cases[0]["context"]
        self.reject(cases)

    def test_no_same_source_session_on_both_sides(self):
        cases = experiences()
        cases[1]["source_session"] = cases[0]["source_session"]
        self.reject(cases)

    def test_missing_validation_has_no_upstream_fallback(self):
        self.reject(experiences()[:1])

    def test_no_future_task(self):
        cases = experiences()
        cases[0]["available_day"] = 3
        self.reject(cases)

    def test_budget_configuration_rejects_nonfinite_and_negative(self):
        for kwargs in ({"max_tokens": 0}, {"max_seconds": math.inf}, {"max_tokens": 1.5},
                       {"max_replays": True}, {"replay_seconds": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LearningBudget(**kwargs)

    def test_rollouts_k_requires_positive_integer(self):
        for value in (0, -1, True, 1.5, None, "3"):
            with self.subTest(rollouts_k=value), self.assertRaises(ValueError):
                SkillOptLearner(rollouts_k=value)

    def test_missing_upstream_has_no_silent_mock_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SkillOptUnavailable):
                SkillOptLearner(source=Path(root)).update(
                    "Skill", experiences(), RecordingTarget(), RecordingOptimizer(), current_day=2)


@unittest.skipUnless((DEFAULT_SOURCE / "skillopt_sleep" / "consolidate.py").is_file(),
                     "Pinned upstream missing: python3 scripts/install_skillopt.py")
class UpstreamIntegrationTests(unittest.TestCase):
    def update(self, target=None, optimizer=None, cases=None, learner_options=None, **kwargs):
        return SkillOptLearner(**(learner_options or {})).update(
            "# Accounting\nFollow the task instructions.", cases or experiences(),
            target or RecordingTarget(), optimizer or RecordingOptimizer(), current_day=2, **kwargs)

    def test_native_k_rollouts_execute_fresh_and_charge_all_attempts(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()

        def variable_train(payload, limits):
            outcome = target(payload, limits)
            if payload["task"]["split"] == "train" and payload["sample_id"] == 1:
                outcome.update(hard=1.0, soft=1.0, response="Good signed-amount reconciliation", feedback="")
            return outcome

        result = self.update(variable_train, optimizer, learner_options={"rollouts_k": 3})
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["configuration"]["rollouts_k"], 3)
        train = [call for call in target.calls if call["task"]["split"] == "train"]
        # Upstream does an initial replay PLUS K contrastive replays. The
        # original and first extra sample both use sample_id=0, but they still
        # invoke the target twice: this bridge never caches target executions.
        self.assertEqual([call["sample_id"] for call in train], [0, 0, 1, 2])
        self.assertEqual([call["attempt_index"] for call in train], [1, 2, 3, 4])
        self.assertEqual([row["attempt_index"] for row in result["replay_evidence"]], list(range(7)))
        self.assertEqual([row["sample_id"] for row in result["replay_evidence"] if row["split"] == "train"], [0, 0, 1, 2])
        validation = [call["phase"] for call in target.calls if call["task"]["split"] == "val"]
        self.assertEqual(validation, ["baseline_val", "gate_trial:skill", "final_val"])
        self.assertIn("CONTRASTIVE reflection", optimizer.calls[0]["prompt"])
        self.assertIn("GOOD attempt", optimizer.calls[0]["prompt"])
        self.assertIn("BAD  attempt", optimizer.calls[0]["prompt"])
        self.assertEqual(result["costs"]["replays"], 7)
        self.assertEqual(result["costs"]["target_model_calls"], 7)
        self.assertEqual(result["costs"]["optimizer_model_calls"], 1)
        self.assertEqual(result["costs"]["tokens"], 80)
        operations = [row for row in result["costs"]["operations"] if row["kind"] == "target"]
        self.assertEqual([row["attempt_index"] for row in operations], list(range(7)))
        self.assertEqual(len(optimizer.calls[0]["train_experiences"]), 4)
        self.assertNotIn("val-b", json.dumps(optimizer.calls))

    def test_native_contrast_uses_configured_soft_metric_spread(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()

        def variable_soft(payload, limits):
            outcome = target(payload, limits)
            if payload["task"]["split"] == "train":
                outcome.update(hard=0.0, soft=0.75 if payload["sample_id"] == 1 else 0.0)
            return outcome

        result = self.update(variable_soft, optimizer, learner_options={"rollouts_k": 2, "gate_metric": "soft"})
        self.assertTrue(result["accepted"])
        self.assertIn("CONTRASTIVE reflection", optimizer.calls[0]["prompt"])
        self.assertIn("soft score 0.750", optimizer.calls[0]["prompt"])

    def test_no_spread_falls_back_to_original_train_failures(self):
        optimizer = RecordingOptimizer()
        result = self.update(optimizer=optimizer, learner_options={"rollouts_k": 3})
        self.assertTrue(result["accepted"])
        self.assertEqual(result["costs"]["replays"], 7)
        self.assertNotIn("CONTRASTIVE reflection", optimizer.calls[0]["prompt"])
        self.assertIn("Recurring failures", optimizer.calls[0]["prompt"])

    def test_repeated_uniform_failures_do_not_replace_initial_upstream_failure_set(self):
        seen_train = [0]
        optimizer = RecordingOptimizer()

        def target(payload, limits):
            score = 0.0
            if payload["task"]["split"] == "train":
                score = float(seen_train[0] == 0)
                seen_train[0] += 1
            return receipt(hard=score, soft=score, response="Result", feedback="Observed check result")

        # The pinned fallback consults initial train failures. If that one
        # succeeds but all K later attempts fail identically, no contrast exists
        # and upstream proposes no edits. Preserve and disclose this limitation.
        result = self.update(target, optimizer, learner_options={"rollouts_k": 3})
        self.assertFalse(result["accepted"])
        self.assertEqual(seen_train[0], 4)
        self.assertEqual(optimizer.calls, [])
        self.assertEqual(result["costs"]["replays"], 6)

    def test_k_rollout_final_gate_remains_a_fresh_rollout_and_can_rollback(self):
        target = RecordingTarget()

        def final_regression(payload, limits):
            outcome = target(payload, limits)
            if payload["phase"] == "final_val":
                outcome.update(hard=0.0, soft=0.0)
            return outcome

        result = self.update(final_regression, learner_options={"rollouts_k": 2})
        self.assertTrue(result["gate_evidence"]["gate_trials"][0]["accepted"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["skill_before_sha256"], result["skill_after_sha256"])
        self.assertEqual([call["phase"] for call in target.calls].count("final_val"), 1)

    def test_nonfinite_repetition_is_not_averaged_away(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()

        def malformed(payload, limits):
            outcome = target(payload, limits)
            if payload["task"]["split"] == "train" and payload["sample_id"] == 1:
                outcome["hard"] = math.nan
            return outcome

        result = self.update(malformed, optimizer, learner_options={"rollouts_k": 3})
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["costs"]["target_model_calls"], 4)
        self.assertEqual(optimizer.calls, [])

    def test_repeated_rollouts_stop_at_total_token_budget(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()
        result = self.update(target, optimizer, learner_options={"rollouts_k": 3},
                             budget=LearningBudget(max_tokens=30))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertFalse(result["accepted"])
        self.assertEqual(len(target.calls), 3)
        self.assertEqual(result["costs"]["tokens"], 30)
        self.assertEqual(optimizer.calls, [])

    def test_repeated_rollouts_stop_at_physical_model_call_budget(self):
        target = RecordingTarget()
        result = self.update(target, learner_options={"rollouts_k": 3},
                             budget=LearningBudget(max_target_model_calls=3))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(len(target.calls), 3)
        self.assertEqual(result["costs"]["target_model_calls"], 3)
        self.assertFalse(result["accepted"])

    def test_real_upstream_accepts_and_freshly_replays_final(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()
        result = self.update(target, optimizer)
        self.assertTrue(result["accepted"], result)
        self.assertIn("Include refunds", result["skill"])
        self.assertEqual([x["phase"] for x in target.calls],
                         ["baseline_val", "train", "gate_trial:skill", "final_val"])
        self.assertEqual([x["task"]["id"] for x in target.calls],
                         ["val-b", "train-a", "val-b", "val-b"])
        self.assertEqual(result["gate_evidence"]["gate_trials"][-1]["target"], "final")
        self.assertEqual(result["costs"]["target_model_calls"], 4)
        self.assertEqual(result["costs"]["optimizer_model_calls"], 1)
        self.assertEqual(result["costs"]["tokens"], 50)
        self.assertTrue(result["costs"]["accounting_complete"])
        self.assertEqual(len(optimizer.calls), 1)

    def test_real_upstream_rejects_nonimproving_candidate(self):
        result = self.update(optimizer=RecordingOptimizer("Always use a pleasant tone."))
        self.assertFalse(result["accepted"])
        self.assertEqual(result["skill_before_sha256"], result["skill_after_sha256"])
        self.assertEqual(result["gate_evidence"]["gate_action"], "reject")
        self.assertTrue(result["gate_evidence"]["rejected_edits"])

    def test_fresh_final_failure_rolls_back_tentative_acceptance(self):
        target = RecordingTarget()

        def unstable(payload, limits):
            outcome = target(payload, limits)
            if payload["phase"] == "final_val":
                outcome.update(hard=0.0, soft=0.0)
            return outcome

        result = self.update(unstable)
        self.assertTrue(result["gate_evidence"]["gate_trials"][0]["accepted"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["skill_before_sha256"], result["skill_after_sha256"])
        self.assertEqual(result["gate_evidence"]["applied_edits"], [])

    def test_strict_gate_blocks_individual_regression_despite_mean_improvement(self):
        cases = experiences()
        cases.extend([dict(cases[1], id="val-c", prompt="Reconcile account C", source_session="session-c"),
                      dict(cases[1], id="val-d", prompt="Reconcile account D", source_session="session-d")])

        def target(payload, limits):
            changed = "Include refunds" in payload["skill"]
            score = float(not changed) if payload["task"]["id"] == "val-b" else float(changed)
            return receipt(hard=score, soft=score, response="Result", feedback="Ledger is incorrect")

        for rollouts_k in (1, 3):
            with self.subTest(rollouts_k=rollouts_k):
                result = self.update(target, cases=cases, learner_options={"rollouts_k": rollouts_k})
                self.assertFalse(result["accepted"])
                self.assertTrue(result["gate_evidence"]["gate_trials"][0]["blocked_by_regression"])

    def test_optimizer_never_sees_validation_or_privileged_fields(self):
        cases = experiences()
        cases[0].update(expected_procedure="SECRET_EXPECTED", rubric={"answer": "SECRET_RUBRIC"})
        cases[1]["prompt"] = "HELD_OUT_PROMPT"
        optimizer = RecordingOptimizer()

        def target(payload, limits):
            outcome = RecordingTarget()(payload, limits)
            outcome["private_diagnostic"] = "SECRET_DIAGNOSTIC"
            outcome["judge_rationale"] = "SECRET_JUDGE"
            return outcome

        result = self.update(target, optimizer, cases)
        text = json.dumps(optimizer.calls)
        for secret in ["SECRET_EXPECTED", "SECRET_RUBRIC", "SECRET_DIAGNOSTIC", "SECRET_JUDGE", "HELD_OUT_PROMPT", "val-b"]:
            self.assertNotIn(secret, text)
        self.assertEqual(result["train_ids"], ["train-a"])

    def test_future_feedback_is_withheld_from_descriptors_and_reflection(self):
        cases = experiences()
        cases[0].update(feedback="SECRET_FUTURE_REWARD", feedback_available_day=4)
        optimizer = RecordingOptimizer()

        def target(payload, limits):
            outcome = RecordingTarget()(payload, limits)
            outcome.update(feedback="SECRET_FUTURE_REPLAY_FEEDBACK", feedback_available_day=4)
            return outcome

        self.update(target, optimizer, cases)
        text = json.dumps(optimizer.calls)
        self.assertNotIn("SECRET_FUTURE", text)

    def test_future_scores_cannot_leak_via_failure_selection(self):
        optimizer = RecordingOptimizer()

        def target(payload, limits):
            outcome = RecordingTarget()(payload, limits)
            outcome["score_available_day"] = 4
            return outcome

        result = self.update(target, optimizer)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(optimizer.calls, [])

    def test_target_is_native_callback_and_never_optimizer_text_backend(self):
        target, optimizer = RecordingTarget(), RecordingOptimizer()
        self.update(target, optimizer)
        self.assertEqual(len(target.calls), 4)
        self.assertTrue(all("task" in call and "skill" in call for call in target.calls))
        self.assertTrue(all("task" not in call and "prompt" in call for call in optimizer.calls))

    def test_nonfinite_scores_fail_closed(self):
        for bad in (math.nan, math.inf, -0.1, 1.1, None):
            def target(payload, limits):
                return receipt(hard=bad, soft=0.0, response="Output")
            with self.subTest(score=bad):
                result = self.update(target)
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["accepted"])
                self.assertEqual(result["costs"]["target_model_calls"], 1)

    def test_incomplete_execution_is_not_scored_as_task_failure(self):
        def target(payload, limits):
            result = receipt(hard=0.0, soft=0.0, response="")
            result["status"] = "timeout"
            return result
        result = self.update(target)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["replay_evidence"], [])
        self.assertEqual(result["costs"]["target_model_calls"], 1)

    def test_missing_receipt_keeps_reservation_and_marks_incomplete(self):
        def target(payload, limits):
            return {"status": "completed", "hard": 0.0, "soft": 0.0, "response": "Output"}
        result = self.update(target)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["costs"]["accounting_complete"])
        self.assertEqual(result["costs"]["target_model_calls"], LearningBudget().replay_model_calls)

    def test_callback_exception_does_not_leak_sensitive_error_message(self):
        def target(payload, limits):
            raise RuntimeError("SECRET_PROVIDER_HEADER")
        result = self.update(target)
        self.assertNotIn("SECRET_PROVIDER_HEADER", json.dumps(result))
        self.assertFalse(result["costs"]["accounting_complete"])

    def test_budget_exhaustion_prevents_further_dispatch_and_adoption(self):
        target = RecordingTarget()
        result = self.update(target, budget=LearningBudget(max_replays=2))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(len(target.calls), 2)
        self.assertFalse(result["accepted"])

    def test_callback_limits_reserve_all_remaining_calls_and_tokens(self):
        seen = []

        def target(payload, limits):
            seen.append(limits)
            return RecordingTarget()(payload, limits)

        result = self.update(target, budget=LearningBudget(max_target_model_calls=1, max_tokens=15))
        self.assertEqual(seen[0]["max_model_calls"], 1)
        self.assertEqual(seen[0]["max_tokens"], 15)
        self.assertEqual(result["status"], "budget_exhausted")

    def test_callback_overrun_is_reported_and_rejected(self):
        def target(payload, limits):
            result = RecordingTarget()(payload, limits)
            result["model_calls"] = limits["max_model_calls"] + 1
            return result
        result = self.update(target)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["costs"]["target_model_calls"], LearningBudget().replay_model_calls + 1)

    def test_upstream_settings_restore_after_success_and_failure(self):
        original = os.environ.get("SKILLOPT_SLEEP_WORKERS")
        os.environ["SKILLOPT_SLEEP_WORKERS"] = "7"
        try:
            self.update()
            self.assertEqual(os.environ["SKILLOPT_SLEEP_WORKERS"], "7")
            self.update(lambda *_: None)
            self.assertEqual(os.environ["SKILLOPT_SLEEP_WORKERS"], "7")
        finally:
            if original is None:
                os.environ.pop("SKILLOPT_SLEEP_WORKERS", None)
            else:
                os.environ["SKILLOPT_SLEEP_WORKERS"] = original


if __name__ == "__main__":
    unittest.main()
