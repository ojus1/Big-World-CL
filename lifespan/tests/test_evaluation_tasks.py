"""Contract tests using independent solvers that receive only public task files."""
from copy import deepcopy
import csv
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import PurePosixPath
import unittest

from lifespan.evaluation.tasks import WORKFLOWS, grade_case, make_case


def _read(public_files, name):
    content = next(text for path, text in public_files.items() if path.endswith("/" + name))
    return list(csv.DictReader(io.StringIO(content))) if name.endswith(".csv") else json.loads(content)


def _money(amount, bps):
    return int((Decimal(amount) * Decimal(bps) / 10000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _scope(policy, row, field):
    sensitive = row.get("classification") == "sensitive" if field == "timeout_margin_ms" else row.get("segment") == "regulated"
    default = {"activation_floor_cents": 0, "annual_discount_bps": 1000, "timeout_margin_ms": 100}[field]
    if not sensitive:
        return default
    base = policy["sensitive_timeout_margin_ms" if field == "timeout_margin_ms" else "regulated_" + field]
    exception = policy.get("temporary_exception")
    if (exception and exception["valid_from"] <= policy["as_of_day"] < exception["valid_until_exclusive"]
            and row["region"] == "domestic"):
        return exception[field]
    return base


def solve_public(workflow, public_files):
    """A test oracle: no access to case['private'] or generator internals."""
    policy = _read(public_files, "policy.json")
    if workflow == "onboarding":
        accounts = _read(public_files, "accounts.csv")
        events = {}
        for row in _read(public_files, "ledger.csv"):
            if row["status"] == "posted":
                events.setdefault(row["event_id"], row)
        result = []
        for account in accounts:
            balance = int(account["opening_balance_cents"])
            for event in events.values():
                if event["account_id"] == account["account_id"]:
                    if event["kind"] == "reversal":
                        balance -= int(events[event["reverses_event_id"]]["amount_cents"])
                    else:
                        balance += int(event["amount_cents"])
            result.append({"account_id": account["account_id"], "balance_cents": balance,
                           "activation": "activate" if balance >= _scope(policy, account, "activation_floor_cents") else "hold"})
        return {"accounts": result, "total_balance_cents": sum(row["balance_cents"] for row in result)}
    if workflow == "renewal":
        result = []
        usage = _read(public_files, "usage.csv")
        tiered = "First 20" in _read(public_files, "specification.json")["overage"]
        for contract in _read(public_files, "contracts.csv"):
            def number(key):
                return int(contract[key])
            units = sum(int(row["units"]) for row in usage if row["contract_id"] == contract["contract_id"] and row["status"] == "final")
            fee = number("seats") * number("monthly_seat_price_cents") * number("term_months")
            discount = _money(fee, _scope(policy, contract, "annual_discount_bps")) if number("term_months") >= 12 else 0
            excess = max(0, units - number("included_units"))
            overage = excess * number("overage_unit_price_cents")
            if tiered and excess > 20:
                overage = 20 * number("overage_unit_price_cents") + _money((excess - 20) * number("overage_unit_price_cents"), 15000)
            subtotal = fee - discount + overage
            tax = _money(subtotal, number("tax_bps"))
            result.append({"contract_id": contract["contract_id"], "used_units": units, "seat_fee_cents": fee,
                           "discount_cents": discount, "overage_cents": overage, "subtotal_cents": subtotal,
                           "tax_cents": tax, "total_cents": subtotal + tax})
        return {"contracts": result, "portfolio_total_cents": sum(row["total_cents"] for row in result)}
    services = _read(public_files, "services.json")
    probes = _read(public_files, "probes.csv")
    repairs, diagnoses = [], []
    for service in services:
        service_probes = [row for row in probes if row["service_id"] == service["service_id"]]
        margin = _scope(policy, service, "timeout_margin_ms")
        needed = max(int(row["latency_ms"]) for row in service_probes) + margin
        timeout = ((needed - 1) // 100 + 1) * 100
        config = {"endpoint": service["healthy_endpoint"], "schema_version": service["required_schema_version"],
                  "timeout_ms": timeout, "retry_limit": max(int(row["transient_failures"]) for row in service_probes)}
        repairs.append({"service_id": service["service_id"], "config": config})
        diagnoses.append({"service_id": service["service_id"],
                          "fields": sorted(key for key in config if config[key] != service["current_config"][key])})
    return {"repaired_services": repairs, "diagnoses": diagnoses,
            "replay": [{"probe_id": row["probe_id"], "outcome": "pass"} for row in probes]}


def envelope(case, work):
    return {"task_id": case["id"], "channel": "work-desk", "redact": False,
            "endpoint": "workspace-v1", "content": json.dumps(work)}


class WorkCaseGenerationTests(unittest.TestCase):
    def test_public_solvers_succeed_across_workflows_regimes_splits_and_seeds(self):
        # Subtests cover 300 independent cases, including both exception edges.
        for workflow in WORKFLOWS:
            for regime, day in (("base", 3), ("changed", 9), ("exception", 12), ("exception", 18), ("reversal", 22)):
                for split in ("online", "train", "validation", "test", "heldout"):
                    for seed in (1, 9, 83, 901):
                        with self.subTest(workflow=workflow, regime=regime, day=day, split=split, seed=seed):
                            case = make_case(workflow, seed, day, "work-3", regime, split)
                            result = grade_case(case, envelope(case, solve_public(workflow, case["public_files"])))
                            self.assertTrue(result["success"], result)
                            self.assertEqual(result["score"], 1.0)
                            self.assertTrue(all(result["checks"].values()))

    def test_deterministic_serializable_and_distinct_seed_instances(self):
        for workflow in WORKFLOWS:
            first = make_case(workflow, 21, 4, "task-safe")
            self.assertEqual(first, make_case(workflow, 21, 4, "task-safe"))
            self.assertEqual(first, json.loads(json.dumps(first, allow_nan=False)))
            self.assertNotEqual(first["private"]["expected"], make_case(workflow, 22, 4, "task-safe")["private"]["expected"])
            self.assertNotEqual(first["private"]["expected"], make_case(workflow, 21, 4, "task-other")["private"]["expected"])

    def test_paired_data_is_stable_under_time_and_regime_changes(self):
        for workflow in WORKFLOWS:
            base = make_case(workflow, 3, 2, "paired")
            changed = make_case(workflow, 3, 9, "paired", "changed")
            for path in base["public_files"]:
                if not path.endswith("/policy.json"):
                    self.assertEqual(base["public_files"][path], changed["public_files"][path])
            self.assertNotEqual(base["private"]["expected"], changed["private"]["expected"])

    def test_only_safe_relative_files_and_no_solution_objects_are_public(self):
        for workflow in WORKFLOWS:
            case = make_case(workflow, 1, 4, "legitimate.task-1")
            for path, content in case["public_files"].items():
                self.assertFalse(PurePosixPath(path).is_absolute())
                self.assertNotIn("..", PurePosixPath(path).parts)
                self.assertTrue(path.startswith("tasks/legitimate.task-1/"))
                self.assertIsInstance(content, str)
                self.assertNotIn('"expected"', content)
                self.assertNotIn('"private"', content)
                self.assertNotIn("def ", content)
            self.assertNotIn("heldout", case["request"])
            self.assertNotIn("split", case["request"])

    def test_unpublished_exception_dates_are_absent(self):
        case = make_case("onboarding", 2, 8, "future", "exception", exception_window=(12, 18))
        self.assertNotIn("temporary_exception", _read(case["public_files"], "policy.json"))
        announced = make_case("onboarding", 2, 10, "future", "exception", exception_window=(12, 18))
        policy = _read(announced["public_files"], "policy.json")
        self.assertFalse(policy["temporary_exception"]["active"])

    def test_bad_identifiers_and_parameters_are_rejected(self):
        for task_id in ("../secret", "/absolute", "x/y", "x\\y", "", ".", "..", "x\n", "a" * 97, None):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                make_case("renewal", 1, 0, task_id)
        for kwargs in ({"day": -1}, {"day": True}, {"seed": False}, {"regime": "mystery"},
                       {"split": "mystery"}, {"workflow": "mystery"}, {"exception_window": (9, 8)},
                       {"exception_window": (False, 8)}, {"exception_window": (1, 2, 3)}):
            args = {"workflow": "renewal", "seed": 1, "day": 0, "task_id": "safe", **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                make_case(**args)

    def test_alias_and_json_roundtrip_preserve_grading(self):
        case = make_case("onboarding", 1, 10, "alias", "change", exception_window=[12, 18])
        self.assertEqual(case["regime"], "changed")
        case = json.loads(json.dumps(case))
        self.assertTrue(grade_case(case, envelope(case, solve_public("onboarding", case["public_files"])))["success"])


class WorkRuleChangeTests(unittest.TestCase):
    def test_stale_base_skill_fails_changed_rules_and_recovers_after_reversal(self):
        for workflow in WORKFLOWS:
            base = make_case(workflow, 2, 3, "repeat", "base")
            changed = make_case(workflow, 2, 10, "repeat", "changed")
            reversal = make_case(workflow, 2, 24, "repeat", "reversal")
            stale = envelope(base, solve_public(workflow, base["public_files"]))
            self.assertFalse(grade_case(changed, stale)["success"])
            self.assertTrue(grade_case(reversal, stale)["success"])

    def test_exception_is_scoped_and_expires_at_exclusive_boundary(self):
        for workflow in WORKFLOWS:
            before = make_case(workflow, 5, 21, "scoped", "exception", exception_window=(22, 27))
            during = make_case(workflow, 5, 22, "scoped", "exception", exception_window=(22, 27))
            last = make_case(workflow, 5, 26, "scoped", "exception", exception_window=(22, 27))
            after = make_case(workflow, 5, 27, "scoped", "exception", exception_window=(22, 27))
            self.assertEqual(before["private"]["expected"], after["private"]["expected"])
            self.assertEqual(during["private"]["expected"], last["private"]["expected"])
            self.assertNotEqual(during["private"]["expected"], after["private"]["expected"])
            stale = envelope(during, solve_public(workflow, during["public_files"]))
            self.assertFalse(grade_case(after, stale)["success"])
            collection = {"onboarding": "accounts", "renewal": "contracts", "incident": "repaired_services"}[workflow]
            # The second entity is sensitive/regulated domestic; the third is
            # equally regulated but cross-border, so the exception cannot apply.
            self.assertNotEqual(before["private"]["expected"][collection][1], during["private"]["expected"][collection][1])
            self.assertEqual(before["private"]["expected"][collection][2], during["private"]["expected"][collection][2])

    def test_future_announcement_does_not_change_current_truth(self):
        for workflow in WORKFLOWS:
            ordinary = make_case(workflow, 7, 10, "announced", "changed")
            announced = make_case(workflow, 7, 10, "announced", "exception")
            self.assertEqual(ordinary["private"]["expected"], announced["private"]["expected"])


class WorkArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.case = make_case("onboarding", 29, 3, "artifact")
        self.work = solve_public("onboarding", self.case["public_files"])

    def assertRejected(self, artifact):
        result = grade_case(self.case, artifact)
        self.assertFalse(result["success"])
        self.assertEqual(result["score"], 0.0)
        return result

    def test_empty_prose_markdown_and_json_scalar_fail(self):
        for content in ("", "Completed all tasks.", "```json\n{}\n```", "null", "[]", "true", '"done"'):
            artifact = envelope(self.case, self.work)
            artifact["content"] = content
            with self.subTest(content=content):
                self.assertRejected(artifact)

    def test_wrong_envelope_or_extra_envelope_fields_fail(self):
        for field, value in (("task_id", "other"), ("redact", 0), ("endpoint", ""), ("content", {})):
            artifact = envelope(self.case, self.work)
            artifact[field] = value
            with self.subTest(field=field):
                self.assertRejected(artifact)
        artifact = envelope(self.case, self.work)
        artifact["shell_command"] = "publish elsewhere"
        self.assertRejected(artifact)

    def test_boolean_float_string_huge_and_nonfinite_numeric_fields_fail(self):
        for value in (True, 1.0, "100", 10**100, float("nan"), float("inf"), -float("inf")):
            work = deepcopy(self.work)
            work["accounts"][0]["balance_cents"] = value
            with self.subTest(value=value):
                self.assertRejected(envelope(self.case, work))

    def test_duplicate_json_keys_fail_instead_of_last_write_wins(self):
        artifact = envelope(self.case, self.work)
        artifact["content"] = artifact["content"].replace('"total_balance_cents":', '"total_balance_cents": 0, "total_balance_cents":')
        self.assertRejected(artifact)

    def test_missing_duplicate_extra_or_unknown_records_fail(self):
        mutations = [lambda rows: rows.pop(), lambda rows: rows.append(deepcopy(rows[0])),
                     lambda rows: rows.__setitem__(1, deepcopy(rows[0])),
                     lambda rows: rows[0].update(account_id="nonexistent")]
        for mutate in mutations:
            work = deepcopy(self.work)
            mutate(work["accounts"])
            self.assertRejected(envelope(self.case, work))

    def test_extra_fields_fail_even_with_correct_results(self):
        work = deepcopy(self.work)
        work["accounts"][0]["send_to"] = "outside@example.invalid"
        self.assertRejected(envelope(self.case, work))
        work = deepcopy(self.work)
        work["write_files"] = {"../../escape": "payload"}
        self.assertRejected(envelope(self.case, work))

    def test_order_does_not_change_semantics(self):
        self.work["accounts"].reverse()
        self.assertTrue(grade_case(self.case, envelope(self.case, self.work))["success"])

    def test_incorrect_numbers_earn_partial_credit_but_never_success(self):
        self.work["accounts"][0]["balance_cents"] += 99
        result = grade_case(self.case, envelope(self.case, self.work))
        self.assertFalse(result["success"])
        self.assertGreater(result["score"], 0)
        self.assertLess(result["score"], 1)
        self.assertFalse(result["checks"]["reconciled_balances"])
        self.assertTrue(result["checks"]["scoped_activation_decisions"])

    def test_grader_is_pure_and_feedback_has_no_answers(self):
        before = deepcopy(self.case)
        self.work["accounts"][0]["balance_cents"] += 7
        artifact = envelope(self.case, self.work)
        original = deepcopy(artifact)
        result = grade_case(self.case, artifact)
        self.assertEqual(self.case, before)
        self.assertEqual(artifact, original)
        self.assertNotIn(str(before["private"]["expected"]["total_balance_cents"]), result["feedback"])
        self.assertNotIn("expected", result["feedback"])

    def test_oversized_and_deep_json_fail_safely(self):
        artifact = envelope(self.case, self.work)
        artifact["content"] = " " * 262145
        self.assertRejected(artifact)
        artifact["content"] = "[" * 2000 + "0" + "]" * 2000
        self.assertRejected(artifact)

    def test_business_policy_validation_remains_separate(self):
        artifact = envelope(self.case, self.work)
        artifact.update(channel="syntactically-valid-but-wrong-channel", endpoint="workspace-unknown", redact=True)
        self.assertTrue(grade_case(self.case, artifact)["success"])


class WorkFamilyRubricTests(unittest.TestCase):
    def test_duplicate_and_pending_ledger_rows_change_naive_result(self):
        case = make_case("onboarding", 8, 3, "ledger")
        work = solve_public("onboarding", case["public_files"])
        account = _read(case["public_files"], "accounts.csv")[0]
        naive_balance = int(account["opening_balance_cents"]) + sum(int(row["amount_cents"]) for row in _read(case["public_files"], "ledger.csv") if row["account_id"] == account["account_id"])
        self.assertNotEqual(work["accounts"][0]["balance_cents"], naive_balance)
        work["accounts"][0]["balance_cents"] = naive_balance
        self.assertFalse(grade_case(case, envelope(case, work))["success"])

    def test_renewal_wrong_discount_tax_and_usage_are_separate_failures(self):
        case = make_case("renewal", 7, 15, "billing", "exception")
        good = solve_public("renewal", case["public_files"])
        for field in ("discount_cents", "tax_cents", "used_units", "total_cents"):
            work = deepcopy(good)
            work["contracts"][1][field] += 1
            result = grade_case(case, envelope(case, work))
            self.assertFalse(result["success"])
            self.assertFalse(result["checks"][field])
            self.assertGreater(result["score"], .8)
        # Six-month contracts have no annual discount despite segment eligibility.
        self.assertEqual(good["contracts"][3]["discount_cents"], 0)

    def test_rounding_is_half_up_using_explicit_public_inputs(self):
        # Public-only oracle is based on Decimal; verify the integer generator
        # across enough varied values to exercise tax and tier rounding.
        saw_half_cent = False
        for seed in range(40):
            case = make_case("renewal", seed, 15, "rounding", "exception", "test")
            work = solve_public("renewal", case["public_files"])
            for contract, row in zip(_read(case["public_files"], "contracts.csv"), work["contracts"]):
                if (row["subtotal_cents"] * int(contract["tax_bps"])) % 10000 == 5000:
                    saw_half_cent = True
            self.assertTrue(grade_case(case, envelope(case, work))["success"])
        self.assertTrue(saw_half_cent)

    def test_heldout_mechanisms_are_legitimately_published_and_required(self):
        onboarding = make_case("onboarding", 7, 2, "mechanism", split="test")
        self.assertIn("reversal_events", _read(onboarding["public_files"], "specification.json"))
        renewal = make_case("renewal", 7, 2, "mechanism", split="test")
        self.assertIn("First 20", _read(renewal["public_files"], "specification.json")["overage"])
        incident = make_case("incident", 7, 2, "mechanism", split="test")
        self.assertTrue(any("-cold" in row["probe_id"] for row in _read(incident["public_files"], "probes.csv")))
        for case in (onboarding, renewal, incident):
            self.assertNotIn("heldout", case["request"])
            self.assertNotIn("test split", case["request"])

    def test_incident_replay_is_executed_not_trusted_from_agent_report(self):
        case = make_case("incident", 11, 9, "incident", "changed")
        work = solve_public("incident", case["public_files"])
        work["repaired_services"][0]["config"]["timeout_ms"] = 0
        # Keep all claimed outcomes as pass: the private replay must refute them.
        result = grade_case(case, envelope(case, work))
        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["executed_replay_passes"])
        self.assertFalse(result["checks"]["replay_report_accuracy"])

    def test_inflating_resources_cannot_satisfy_minimal_repair_rubric(self):
        case = make_case("incident", 11, 9, "incident", "changed")
        work = solve_public("incident", case["public_files"])
        work["repaired_services"][0]["config"]["timeout_ms"] = 100000
        result = grade_case(case, envelope(case, work))
        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["minimal_compliant_repairs"])
        self.assertTrue(result["checks"]["executed_replay_passes"])

    def test_diagnoses_cannot_be_omitted_or_replaced_with_success_labels(self):
        case = make_case("incident", 11, 9, "incident", "changed")
        work = solve_public("incident", case["public_files"])
        work["diagnoses"][0]["fields"] = []
        result = grade_case(case, envelope(case, work))
        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["diagnosed_fields"])

    def test_unsafe_incident_fields_endpoints_and_boolean_numbers_rejected(self):
        case = make_case("incident", 11, 9, "incident", "changed")
        good = solve_public("incident", case["public_files"])
        for field, value in (("endpoint", "https://outside.example/collect"), ("timeout_ms", True),
                             ("retry_limit", -1), ("shell", "arbitrary command"), ("schema_version", 2.0)):
            work = deepcopy(good)
            work["repaired_services"][0]["config"][field] = value
            result = grade_case(case, envelope(case, work))
            self.assertEqual(result["score"], 0)
            self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
