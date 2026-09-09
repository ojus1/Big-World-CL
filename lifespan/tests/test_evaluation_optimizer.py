"""Pure mocked-transport tests; no model API calls or external dependencies."""
import copy
import json
import unittest
from unittest.mock import patch

from lifespan.evaluation.optimizer import (
    CONTEXT_ADAPTER, EXACT_ADAPTER, OptimizerInputError, make_reflector,
)


CREDENTIALS = {"model": "gpt-5.6-luna", "base_url": "https://api.openai.com/v1",
               "api_key": "unit-test-secret-key"}


def payload():
    return {"prompt": "UPSTREAM REFLECTION PROMPT", "current_day": 3, "max_output_tokens": 1024,
            "train_experiences": [{"task": {"id": "train-1", "split": "train", "available_day": 2,
                "prompt": "Reconcile account ledger", "context": "Refund amounts are negative entries.",
                "source_session": "session-1", "feedback": "The refund was omitted."},
                "response": "The ledger total is incomplete.", "feedback": "Include signed adjustments."}]}


def limits():
    return {"max_model_calls": 1, "max_tokens": 8192, "timeout_seconds": 10.0}


def response(**kwargs):
    result = {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": '[{"op":"add","content":"Include refunds."}]'}]}],
        "usage": {"input_tokens": 130, "output_tokens": 50, "total_tokens": 180}}
    result.update(kwargs)
    return result


class Transport:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or response()

    def __call__(self, request, *, timeout, api_mode):
        self.calls.append({"request": copy.deepcopy(request), "timeout": timeout, "api_mode": api_mode})
        return self.result


class ReflectorTests(unittest.TestCase):
    def test_real_provider_request_uses_configured_model_and_exact_usage(self):
        transport = Transport()
        reflector = make_reflector(CREDENTIALS, transport=transport)
        result = reflector(payload(), limits())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tokens"], 180)
        self.assertEqual(result["input_tokens"], 130)
        self.assertEqual(result["output_tokens"], 50)
        self.assertEqual(result["model_calls"], 1)
        request = transport.calls[0]["request"]
        self.assertEqual(request["model"], CREDENTIALS["model"])
        self.assertFalse(request["store"])
        self.assertNotIn("include", request)
        self.assertEqual(request["max_output_tokens"], 1024)
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertLessEqual(transport.calls[0]["timeout"], 10)
        self.assertEqual(result["context_adapter"], CONTEXT_ADAPTER)

    def test_training_context_appends_without_replacing_upstream_prompt(self):
        transport = Transport()
        result = make_reflector(CREDENTIALS, transport=transport)(payload(), limits())
        prompt = transport.calls[0]["request"]["input"]
        self.assertTrue(prompt.startswith("UPSTREAM REFLECTION PROMPT\n"))
        self.assertIn("Refund amounts are negative entries.", prompt)
        self.assertIn("Include signed adjustments.", prompt)
        self.assertEqual(result["optimizer_prompt"], prompt)
        self.assertGreater(result["supplemental_bytes"], 0)

    def test_exact_upstream_variant_omits_adapter(self):
        transport = Transport()
        reflector = make_reflector(CREDENTIALS, augment_training_context=False, transport=transport)
        result = reflector(payload(), limits())
        self.assertEqual(transport.calls[0]["request"]["input"], "UPSTREAM REFLECTION PROMPT")
        self.assertEqual(result["context_adapter"], EXACT_ADAPTER)
        self.assertEqual(result["supplemental_bytes"], 0)

    def test_validation_test_and_future_records_rejected_before_dispatch(self):
        for split, day in (("val", 2), ("test", 2), ("train", 4), ("train", None)):
            data = payload()
            data["train_experiences"][0]["task"].update(split=split, available_day=day)
            transport = Transport()
            with self.subTest(split=split, day=day), self.assertRaises(OptimizerInputError):
                make_reflector(CREDENTIALS, transport=transport)(data, limits())
            self.assertEqual(transport.calls, [])

    def test_visibility_is_checked_beyond_context_rendering_cap(self):
        data = payload()
        data["train_experiences"] = [copy.deepcopy(data["train_experiences"][0]) for _ in range(33)]
        data["train_experiences"][-1]["task"]["split"] = "test"
        transport = Transport()
        with self.assertRaises(OptimizerInputError):
            make_reflector(CREDENTIALS, transport=transport)(data, limits())
        self.assertEqual(transport.calls, [])

    def test_exact_mode_still_rejects_invalid_sidecar(self):
        data = payload()
        data["train_experiences"][0]["task"]["split"] = "test"
        with self.assertRaises(OptimizerInputError):
            make_reflector(CREDENTIALS, augment_training_context=False, transport=Transport())(data, limits())

    def test_private_grader_and_native_reasoning_metadata_are_excluded(self):
        data = payload()
        record = data["train_experiences"][0]
        record["task"].update(rubric="SECRET_RUBRIC", expected_procedure="SECRET_EXPECTED")
        record["private_diagnostic"] = "SECRET_DIAGNOSTIC"
        record["native"] = {"api_key": "SECRET_NATIVE_KEY", "messages": [
            {"role": "system", "content": "SECRET_SYSTEM"},
            {"role": "assistant", "content": "Read the ledger", "reasoning_content": "SECRET_REASONING",
             "encrypted_content": "SECRET_ENCRYPTED", "response_id": "SECRET_RESPONSE_ID",
             "tool_calls": [{"id": "SECRET_CALL_ID", "function": {"name": "read_file",
                 "arguments": json.dumps({"path": "/workspace/ledger.csv", "api_key": "SECRET_ARGUMENT"})}}]},
            {"role": "tool", "content": json.dumps({"result": "refund -3", "headers": {"x-key": "SECRET_HEADER"},
                 "private_rubric": "SECRET_TOOL_RUBRIC", "token_usage": 123})},
            {"role": "assistant", "content": [{"type": "reasoning", "text": "SECRET_BLOCK"},
                {"type": "output_text", "text": "Visible completion"}]}]}
        transport = Transport()
        result = make_reflector(CREDENTIALS, transport=transport)(data, limits())
        self.assertNotIn("SECRET_", result["optimizer_prompt"])
        self.assertIn("refund -3", result["optimizer_prompt"])
        self.assertIn("Visible completion", result["optimizer_prompt"])
        self.assertIn("read_file", result["optimizer_prompt"])

    def test_credential_values_removed_from_inputs_outputs_and_audit(self):
        data = payload()
        data["prompt"] += " " + CREDENTIALS["api_key"]
        data["train_experiences"][0]["response"] = "Authorization: Bearer madeup-provider-value"
        output = response()
        output["output"][0]["content"][0]["text"] = CREDENTIALS["api_key"]
        reflector = make_reflector(CREDENTIALS, transport=Transport(output))
        result = reflector(data, limits())
        text = json.dumps([result, reflector.audit_records])
        self.assertNotIn(CREDENTIALS["api_key"], text)
        self.assertNotIn("madeup-provider-value", text)

    def test_future_feedback_withheld(self):
        data = payload()
        record = data["train_experiences"][0]
        record["task"].update(feedback="FUTURE_TASK_FEEDBACK", feedback_available_day=4)
        record.update(feedback="FUTURE_REPLAY_FEEDBACK", feedback_available_day=4)
        result = make_reflector(CREDENTIALS, transport=Transport())(data, limits())
        self.assertNotIn("FUTURE_", result["optimizer_prompt"])

    def test_no_transport_dispatch_when_base_prompt_does_not_fit(self):
        transport = Transport()
        result = make_reflector(CREDENTIALS, transport=transport)(payload(), dict(limits(), max_tokens=100))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["tokens"], 0)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(transport.calls, [])

    def test_context_and_output_fit_total_pre_dispatch_reservation(self):
        data = payload()
        data["train_experiences"][0]["response"] = "日" * 15000
        transport = Transport()
        result = make_reflector(CREDENTIALS, transport=transport)(data, dict(limits(), max_tokens=3000))
        self.assertLessEqual(result["input_token_reservation"] + result["max_output_tokens"], 3000)
        self.assertIn("bounded", result["optimizer_prompt"])

    def test_large_serialized_runner_trajectory_retains_latest_failure_and_each_case(self):
        data = payload()
        messages = [{"role": "user", "content": "Initial public request"}]
        for index in range(40):
            messages.append({"role": "assistant", "content": "Long work log " + "x" * 1800,
                             "tool_call_id": "SECRET_CALL_ID", "reasoning_content": "SECRET_REASONING"})
            messages.append({"role": "tool", "tool_call_id": "SECRET_CALL_ID",
                             "content": json.dumps({"output": "earlier result " + "y" * 1000,
                                                    "headers": {"auth": "SECRET_HEADER"}})})
        messages.append({"role": "tool", "tool_call_id": "SECRET_LATE_CALL_ID",
                         "content": '{"error":"LATEST_FAILURE_REFUND_MISSING","endpoint":"workspace-v2"}'})
        messages.append({"role": "assistant", "content": "Could not finish this work."})
        data["train_experiences"][0]["response"] = json.dumps({"messages": messages, "feedback": "Public feedback"})
        second = copy.deepcopy(data["train_experiences"][0])
        second["task"].update(id="train-2", prompt="SECOND_CASE_REQUEST", context="SECOND_CASE_DATA")
        second["response"] = "Another account result"
        data["train_experiences"].append(second)
        result = make_reflector(CREDENTIALS, transport=Transport())(data, limits())
        prompt = result["optimizer_prompt"]
        self.assertNotIn("SECRET_", prompt)
        self.assertIn("LATEST_FAILURE_REFUND_MISSING", prompt)
        self.assertIn("SECOND_CASE_REQUEST", prompt)
        self.assertIn("SECOND_CASE_DATA", prompt)
        self.assertIn("workspace-v2", prompt)
        self.assertEqual(result["trajectory_summaries"][0]["messages_supplied"], len(messages))
        self.assertLess(result["trajectory_summaries"][0]["messages_retained"], len(messages))

    def test_public_business_endpoints_and_provider_fields_are_preserved(self):
        data = payload()
        data["train_experiences"][0]["task"]["context"] = json.dumps({
            "healthy_endpoint": "https://healthy.example.invalid", "current_config": {"endpoint": "workspace-v2"},
            "provider": "Fictional business provider", "api_base_url": "SECRET_API_BASE_URL"})
        result = make_reflector(CREDENTIALS, transport=Transport())(data, limits())
        prompt = result["optimizer_prompt"]
        self.assertIn("healthy.example.invalid", prompt)
        self.assertIn("workspace-v2", prompt)
        self.assertIn("Fictional business provider", prompt)
        self.assertNotIn("SECRET_API_BASE_URL", prompt)

    def test_large_tool_json_is_sanitized_before_excerpting(self):
        data = payload()
        huge_tool_result = json.dumps({"output": "earlier log " + "x" * 40000 + "\nEND_FAILURE_SIGNAL",
                                      "headers": {"authorization": "SECRET_LARGE_HEADER"}})
        data["train_experiences"][0]["messages"] = [{"role": "tool", "content": huge_tool_result}]
        result = make_reflector(CREDENTIALS, transport=Transport())(data, limits())
        self.assertIn("END_FAILURE_SIGNAL", result["optimizer_prompt"])
        self.assertNotIn("SECRET_LARGE_HEADER", result["optimizer_prompt"])

    def test_remaining_budget_takes_precedence_over_per_call_limit(self):
        transport = Transport()
        result = make_reflector(CREDENTIALS, transport=transport)(payload(), dict(limits(), remaining_tokens=100))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(transport.calls, [])

    def test_transport_failure_is_counted_without_retry_or_secret_exception(self):
        calls = []
        def transport(*args, **kwargs):
            calls.append(args)
            raise RuntimeError("SECRET_PROVIDER_RESPONSE " + CREDENTIALS["api_key"])
        reflector = make_reflector(CREDENTIALS, transport=transport)
        result = reflector(payload(), limits())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["model_calls"], 1)
        self.assertIsNone(result["tokens"])
        self.assertFalse(result["accounting_complete"])
        self.assertEqual(result["status"], "transport_failed")
        self.assertNotIn("SECRET_PROVIDER_RESPONSE", json.dumps(reflector.audit_records))

    def test_missing_or_inconsistent_usage_is_not_estimated(self):
        for usage in (None, {"input_tokens": 5}, {"input_tokens": 5, "output_tokens": 2, "total_tokens": 100}):
            with self.subTest(usage=usage):
                result = make_reflector(CREDENTIALS, transport=Transport(response(usage=usage)))(payload(), limits())
                self.assertIsNone(result["tokens"])
                self.assertFalse(result["accounting_complete"])
                self.assertEqual(result["status"], "invalid_usage")

    def test_provider_overrun_is_not_a_completed_optimizer_reply(self):
        output = response(usage={"input_tokens": 8100, "output_tokens": 200, "total_tokens": 8300})
        result = make_reflector(CREDENTIALS, transport=Transport(output))(payload(), limits())
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["tokens"], 8300)
        self.assertEqual(result["response"], "")

    def test_incomplete_generation_keeps_exact_known_usage(self):
        result = make_reflector(CREDENTIALS, transport=Transport(response(status="incomplete")))(payload(), limits())
        self.assertEqual(result["status"], "incomplete_response")
        self.assertEqual(result["tokens"], 180)

    def test_chat_compatible_endpoint_is_explicit_and_counts_usage(self):
        output = {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}],
                  "usage": {"prompt_tokens": 40, "completion_tokens": 2, "total_tokens": 42}}
        transport = Transport(output)
        result = make_reflector(dict(CREDENTIALS, api_mode="chat_completions", model="local-model"),
                                transport=transport)(payload(), limits())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tokens"], 42)
        self.assertIn("max_tokens", transport.calls[0]["request"])
        self.assertNotIn("reasoning", transport.calls[0]["request"])

    def test_no_credentials_in_validation_error(self):
        with self.assertRaises(OptimizerInputError) as caught:
            make_reflector(dict(CREDENTIALS, base_url="https://username:demo@example.com"))
        self.assertNotIn("SECRET_URL", str(caught.exception))

    def test_elapsed_deadline_prevents_dispatch(self):
        transport = Transport()
        with patch("lifespan.evaluation.optimizer.time.monotonic", side_effect=[0.0, 20.0, 20.0]):
            result = make_reflector(CREDENTIALS, transport=transport)(payload(), limits())
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(transport.calls, [])

    def test_upstream_bridge_serialized_replay_reaches_augmented_provider_prompt(self):
        from lifespan.evaluation.skillopt import DEFAULT_SOURCE, SkillOptLearner
        if not (DEFAULT_SOURCE / "skillopt_sleep/consolidate.py").is_file():
            self.skipTest("Pinned upstream missing: python3 scripts/install_skillopt.py")
        cases = [
            {"id": "train-case", "split": "train", "available_day": 1,
             "prompt": "TRAIN_REAL_TASK", "context": "TRAIN_REAL_INPUTS"},
            {"id": "val-case", "split": "val", "available_day": 1,
             "prompt": "VALIDATION_PRIVATE_CASE", "context": "VALIDATION_PRIVATE_INPUTS"},
        ]
        def replay(request, bound):
            correct = "Include refunds" in request["skill"]
            trace = {"messages": [{"role": "tool", "tool_call_id": "SECRET_TRANSPORT_ID",
                      "content": "TRAIN_TERMINAL_ERROR refund missing" if request["task"]["split"] == "train"
                      else "VALIDATION_PRIVATE_RESULT"}], "feedback": "Check the refund."}
            return {"status": "completed", "hard": float(correct), "soft": float(correct),
                    "response": json.dumps(trace), "feedback": "Check signed amounts", "tokens": 25,
                    "model_calls": 1, "tool_calls": 1, "latency_ms": 1}
        transport = Transport()
        reflector = make_reflector(CREDENTIALS, transport=transport)
        result = SkillOptLearner().update("Account for sales", cases, replay, reflector, current_day=2)
        self.assertTrue(result["accepted"])
        actual_prompt = transport.calls[0]["request"]["input"]
        self.assertIn("TRAIN_REAL_TASK", actual_prompt)
        self.assertIn("TRAIN_REAL_INPUTS", actual_prompt)
        self.assertIn("TRAIN_TERMINAL_ERROR", actual_prompt)
        self.assertNotIn("VALIDATION_PRIVATE", actual_prompt)
        self.assertNotIn("SECRET_TRANSPORT_ID", actual_prompt)


if __name__ == "__main__":
    unittest.main()
