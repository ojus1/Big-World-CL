"""Deterministic work cases and private, executable quality rubrics.

Only ``public_files`` and ``request`` belong in the employee computer. The whole
case, particularly ``private``, stays in the evaluator. Business authorization,
approval and endpoint validation are deliberately handled by SessionEnv.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
from collections import defaultdict


WORKFLOWS = ("onboarding", "renewal", "incident")
REGIMES = ("base", "changed", "exception", "reversal")
SPLITS = ("online", "train", "validation", "test", "heldout")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_ENVELOPE = {"task_id", "channel", "redact", "endpoint", "content"}


def _json(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _round_bps(amount, bps):
    """Nonnegative integer currency, round half up to the nearest cent."""
    return (amount * bps + 5000) // 10000


def _rules(regime, day, exception_window):
    start, end = exception_window
    changed = regime in ("changed", "exception")
    active_exception = regime == "exception" and start <= day < end
    policy = {
        "as_of_day": day,
        "version": "v2" if changed else "v1",
        "regulated_activation_floor_cents": 1200 if changed else 0,
        "regulated_annual_discount_bps": 0 if changed else 500,
        "sensitive_timeout_margin_ms": 200 if changed else 100,
    }
    # Announcement is observable only after publication, even in a case whose
    # scenario will later enter an exception. Expiry remains historical evidence.
    if regime == "exception" and day >= max(0, start - 2):
        policy["temporary_exception"] = {
            "published_day": max(0, start - 2), "valid_from": start,
            "valid_until_exclusive": end,
            "scope": {"segment": "regulated", "region": "domestic"},
            "activation_floor_cents": 0, "annual_discount_bps": 1500,
            "incident_scope": {"classification": "sensitive", "region": "domestic"},
            "timeout_margin_ms": 100,
            "active": active_exception,
        }
    if regime == "reversal":
        policy["notice"] = "The v2 requirements have been withdrawn; v1 applies again."
    return policy


def _scoped(record, policy, kind):
    key = {"activation": "regulated_activation_floor_cents",
           "discount": "regulated_annual_discount_bps",
           "timeout": "sensitive_timeout_margin_ms"}[kind]
    default = {"activation": 0, "discount": 1000, "timeout": 100}[kind]
    scoped = record.get("classification") == "sensitive" if kind == "timeout" else record.get("segment") == "regulated"
    result = policy[key] if scoped else default
    exception = policy.get("temporary_exception", {})
    if scoped and record["region"] == "domestic" and exception.get("active"):
        result = exception[{"activation": "activation_floor_cents", "discount": "annual_discount_bps",
                            "timeout": "timeout_margin_ms"}[kind]]
    return result


def _onboarding(rng, policy, heldout):
    accounts, ledger = [], []
    segments = [("commercial", "domestic"), ("regulated", "domestic"),
                ("regulated", "cross_border"), ("commercial", "cross_border")]
    for index, (segment, region) in enumerate(segments):
        account_id = f"acct-{index}-{rng.randrange(100, 999)}"
        credit, debit = rng.randrange(700, 2300), rng.randrange(200, 1200)
        balance = rng.randrange(200, 1000) if segment == "regulated" else rng.randrange(1400, 2800)
        if index == 3:
            balance = -rng.randrange(100, 800)
        reversal = credit if heldout and index % 2 == 0 else 0
        accounts.append({"account_id": account_id, "segment": segment, "region": region,
                         "opening_balance_cents": balance - credit + debit + reversal})
        posted = [
            {"event_id": f"{account_id}-credit", "account_id": account_id, "status": "posted",
             "kind": "posting", "amount_cents": credit, "reverses_event_id": ""},
            {"event_id": f"{account_id}-debit", "account_id": account_id, "status": "posted",
             "kind": "posting", "amount_cents": -debit, "reverses_event_id": ""},
        ]
        ledger.extend(posted)
        ledger.append(dict(posted[0]))  # Duplicate export row, not a second payment.
        ledger.append({"event_id": f"{account_id}-pending", "account_id": account_id,
                       "status": "pending", "kind": "posting", "amount_cents": rng.randrange(5000, 9000),
                       "reverses_event_id": ""})
        if reversal:
            ledger.append({"event_id": f"{account_id}-reversal", "account_id": account_id,
                           "status": "posted", "kind": "reversal", "amount_cents": 0,
                           "reverses_event_id": posted[0]["event_id"]})
    rng.shuffle(ledger)
    unique = {row["event_id"]: row for row in ledger if row["status"] == "posted"}
    changes = defaultdict(int)
    for row in unique.values():
        amount = row["amount_cents"]
        if row["kind"] == "reversal":
            amount = -unique[row["reverses_event_id"]]["amount_cents"]
        changes[row["account_id"]] += amount
    result = []
    for account in accounts:
        balance = account["opening_balance_cents"] + changes[account["account_id"]]
        result.append({"account_id": account["account_id"], "balance_cents": balance,
                       "activation": "activate" if balance >= _scoped(account, policy, "activation") else "hold"})
    specification = {
        "currency": "USD", "amount_format": "integer cents; no floats or formatted currency",
        "ledger": "Use posted events only; count each event_id once. Signed amounts add to the opening balance.",
        "activation": "Activate if reconciled balance is at least the applicable floor. Commercial floor is 0 cents. Use policy.json for regulated accounts and scoped exceptions.",
        "output": {"accounts": [{"account_id": "string", "balance_cents": "integer", "activation": "activate|hold"}],
                   "total_balance_cents": "integer sum of every account balance"},
        "coverage": "Return every input account exactly once, with exactly the fields shown. No other fields or accounts.",
    }
    if heldout:
        specification["reversal_events"] = "A posted reversal negates the signed amount of its referenced posted posting. Its own amount_cents is 0. References are same-account, unique, and never chained. Deduplicate reversal event IDs too."
    expected = {"accounts": result, "total_balance_cents": sum(row["balance_cents"] for row in result)}
    return {"accounts.csv": _csv(accounts), "ledger.csv": _csv(ledger),
            "specification.json": _json(specification)}, expected, {}


def _renewal(rng, policy, heldout):
    contracts, usage, result = [], [], []
    for index, (segment, region) in enumerate((("commercial", "domestic"), ("regulated", "domestic"),
                                             ("regulated", "cross_border"), ("commercial", "cross_border"))):
        contract_id = f"contract-{index}-{rng.randrange(100, 999)}"
        contract = {"contract_id": contract_id, "segment": segment, "region": region,
                    "seats": rng.randrange(3, 15), "monthly_seat_price_cents": rng.randrange(900, 2600),
                    "term_months": 6 if index == 3 else 12,
                    "included_units": rng.randrange(30, 60), "overage_unit_price_cents": rng.randrange(7, 29),
                    "tax_bps": rng.choice([500, 825, 1000])}
        contracts.append(contract)
        amounts = [rng.randrange(25, 55), rng.randrange(30, 65)]
        for period, units in enumerate(amounts):
            usage.append({"contract_id": contract_id, "period": f"p{period}", "units": units, "status": "final"})
        usage.append({"contract_id": contract_id, "period": "p2", "units": 999, "status": "forecast"})
        units = sum(amounts)
        seat_fee = contract["seats"] * contract["monthly_seat_price_cents"] * contract["term_months"]
        discount = _round_bps(seat_fee, _scoped(contract, policy, "discount")) if contract["term_months"] >= 12 else 0
        overage_units = max(0, units - contract["included_units"])
        rate = contract["overage_unit_price_cents"]
        overage = overage_units * rate
        if heldout:
            overage = min(20, overage_units) * rate + _round_bps(max(0, overage_units - 20) * rate, 15000)
        subtotal = seat_fee - discount + overage
        tax = _round_bps(subtotal, contract["tax_bps"])
        result.append({"contract_id": contract_id, "used_units": units, "seat_fee_cents": seat_fee,
                       "discount_cents": discount, "overage_cents": overage, "subtotal_cents": subtotal,
                       "tax_cents": tax, "total_cents": subtotal + tax})
    rng.shuffle(usage)
    specification = {
        "currency": "USD", "rounding": "All output amounts are integer cents. Round nonnegative fractional cents half up; do not use bankers' rounding.",
        "usage": "Sum final usage rows for each contract; ignore forecast rows. included_units applies once to the entire contract term.",
        "seat_fee": "seats * monthly_seat_price_cents * term_months",
        "discount": "Only terms of at least 12 months qualify. Discount applies to seat fees only, rounded once. Commercial annual discount is 1000 basis points. Regulated rates and scoped exceptions are in policy.json. A basis point is 1/10000.",
        "overage": ("First 20 units above included_units cost the listed rate; remaining excess units cost 15000 basis points of that rate. Round the aggregate premium-tier charge once, then add the first tier."
                    if heldout else "Units above included_units cost overage_unit_price_cents each; no charge for unused included units."),
        "subtotal": "seat_fee_cents minus discount_cents plus overage_cents",
        "tax": "Apply each contract's tax_bps to subtotal_cents and round once. total_cents is subtotal_cents plus tax_cents.",
        "output": {"contracts": [{"contract_id": "string", **{key: "integer" for key in result[0] if key != "contract_id"}}],
                   "portfolio_total_cents": "integer sum of all contract totals"},
        "coverage": "Return every input contract exactly once, with exactly the fields shown. No other fields or contracts.",
    }
    return {"contracts.csv": _csv(contracts), "usage.csv": _csv(usage), "specification.json": _json(specification)}, {
        "contracts": result, "portfolio_total_cents": sum(row["total_cents"] for row in result)}, {}


def _probe(config, service, probe):
    """Execute the small public request model against a proposed configuration."""
    if config["endpoint"] != service["healthy_endpoint"]:
        return "unavailable_endpoint"
    if config["schema_version"] != service["required_schema_version"]:
        return "wrong_schema"
    if config["retry_limit"] < probe["transient_failures"]:
        return "retry_exhausted"
    if config["timeout_ms"] < probe["latency_ms"]:
        return "timeout"
    return "pass"


def _incident(rng, policy, heldout):
    services, probes, repaired, diagnoses = [], [], [], []
    for index, (classification, region) in enumerate((("standard", "domestic"), ("sensitive", "domestic"),
                                                     ("sensitive", "cross_border"))):
        service_id = f"svc-{index}-{rng.randrange(100, 999)}"
        latency = rng.randrange(180, 690)
        endpoint = f"https://{service_id}-{region}.example.invalid/v{2 if heldout else 1}"
        service = {"service_id": service_id, "classification": classification, "region": region,
                   "healthy_endpoint": endpoint, "required_schema_version": 3 if heldout else 2}
        service_probes = [{"probe_id": f"{service_id}-r{i}", "service_id": service_id,
                           "latency_ms": latency + i * 80, "transient_failures": (i + index) % 3}
                          for i in range(3)]
        if heldout:
            # A cold start is a separately recorded probe rather than an oracle
            # repair value. Same replay semantics, additional input mechanism.
            service_probes.append({"probe_id": f"{service_id}-cold", "service_id": service_id,
                                   "latency_ms": latency + 390, "transient_failures": 3})
        timeout = ((max(row["latency_ms"] for row in service_probes) + _scoped(service, policy, "timeout") + 99) // 100) * 100
        correct = {"endpoint": endpoint, "schema_version": service["required_schema_version"],
                   "timeout_ms": timeout, "retry_limit": max(row["transient_failures"] for row in service_probes)}
        current = dict(correct)
        if index != 1:
            current["endpoint"] = f"https://retired-{service_id}.example.invalid/v1"
        if index != 0:
            current["schema_version"] = 1
        current["timeout_ms"] = 100
        if index == 1:
            current["retry_limit"] = 0
        service["current_config"] = current
        services.append(service)
        probes.extend(service_probes)
        repaired.append({"service_id": service_id, "config": correct})
        diagnoses.append({"service_id": service_id, "fields": sorted(key for key in correct if correct[key] != current[key])})
    logs = [{"probe_id": probe["probe_id"], "service_id": probe["service_id"],
             "observed_outcome": _probe(next(row for row in services if row["service_id"] == probe["service_id"])["current_config"],
                                        next(row for row in services if row["service_id"] == probe["service_id"]), probe)}
            for probe in probes]
    specification = {
        "objective": "Diagnose configuration drift, propose the minimal compliant configuration, and report the result of replaying every supplied probe against it.",
        "endpoint": "Use the service's healthy_endpoint; all other endpoints are unavailable in this simulated incident.",
        "schema_version": "Must match required_schema_version exactly.",
        "retry_limit": "Set exactly to the maximum transient_failures among the service's supplied probes; avoid unnecessary retry amplification.",
        "timeout_ms": "Set to the maximum supplied probe latency plus the applicable margin, rounded UP to a multiple of 100 ms. Standard margin is 100 ms; sensitive margins and domestic scoped exceptions are in policy.json. Do not inflate beyond this budget.",
        "diagnosis": "For every service list exactly the current_config fields that differ from the compliant repaired configuration.",
        "replay_order": ["unavailable_endpoint if endpoint differs from healthy_endpoint", "wrong_schema if schema version differs",
                         "retry_exhausted if retry_limit is less than transient_failures", "timeout if timeout_ms is less than latency_ms", "otherwise pass"],
        "output": {"repaired_services": [{"service_id": "string", "config": {"endpoint": "string", "schema_version": "integer", "timeout_ms": "integer", "retry_limit": "integer"}}],
                   "diagnoses": [{"service_id": "string", "fields": ["configuration field name"]}],
                   "replay": [{"probe_id": "string", "outcome": "pass|unavailable_endpoint|wrong_schema|retry_exhausted|timeout"}]},
        "coverage": "Return every service once in both service lists and every probe once in replay, with exactly the fields shown. No other fields, commands, endpoints or output files.",
    }
    expected = {"repaired_services": repaired, "diagnoses": diagnoses,
                "replay": [{"probe_id": row["probe_id"], "outcome": "pass"} for row in probes]}
    return {"services.json": _json(services), "probes.csv": _csv(probes), "observed_logs.csv": _csv(logs),
            "specification.json": _json(specification)}, expected, {"services": services, "probes": probes}


def make_case(workflow: str, seed: int, day: int, task_id: str, regime: str = "base", split: str = "online", *,
              exception_window: tuple[int, int] = (12, 18)) -> dict:
    """Generate one JSON-serializable work case without network/model calls.

    Input RNG excludes day and regime: paired probes may share work inputs while
    evaluating different rules. Caller chooses task IDs/seeds for fresh work.
    ``test``/``heldout`` introduce published, held-out mechanisms; they are not
    optimizer development sets. Exception validity uses [start, end).
    """
    if workflow not in WORKFLOWS:
        raise ValueError(f"Unknown workflow: {workflow}")
    if type(seed) is not int or type(day) is not int or day < 0:
        raise ValueError("seed must be an integer; day must be a nonnegative integer")
    if not isinstance(task_id, str) or not _ID.fullmatch(task_id) or task_id in (".", ".."):
        raise ValueError("task_id must be a safe, nonempty filename component of at most 96 characters")
    if regime == "change":
        regime = "changed"
    if regime not in REGIMES or split not in SPLITS:
        raise ValueError("Unknown regime or split")
    if (not isinstance(exception_window, (tuple, list)) or len(exception_window) != 2
            or any(type(value) is not int for value in exception_window)
            or not 0 <= exception_window[0] < exception_window[1]):
        raise ValueError("exception_window must contain nonnegative integer start < end")
    seed_bytes = json.dumps([workflow, seed, task_id, split], separators=(",", ":")).encode()
    rng = random.Random(int.from_bytes(hashlib.sha256(seed_bytes).digest(), "big"))
    policy = _rules(regime, day, exception_window)
    generator = {"onboarding": _onboarding, "renewal": _renewal, "incident": _incident}[workflow]
    files, expected, execution = generator(rng, policy, split in ("test", "heldout"))
    files["policy.json"] = _json(policy)
    prefix = f"tasks/{task_id}/"
    return {"schema_version": 1, "id": task_id, "workflow": workflow, "day": day,
            "regime": regime, "split": split,
            "public_files": {prefix + name: content for name, content in files.items()},
            "request": (f"Complete the {workflow} work for task {task_id}. Read the task inputs, specification.json, "
                        f"and policy.json in /workspace/{prefix}. Use the policy applicable on day {day}. "
                        "Write a deliverable using the workplace task_id/channel/redact/endpoint/content envelope. "
                        "Its content must be a JSON string encoding exactly the work output schema in specification.json. "
                        "Follow the separate workplace approval and submission procedure. Do not put prose or Markdown in content."),
            "private": {"expected": expected, "execution": execution, "rubric_version": "work-quality-v1",
                        "feedback_visibility": "Named failed check categories and aggregate score; no expected answers or hidden policy."}}


def _bad_json(_):
    raise ValueError("Nonfinite JSON numbers are forbidden")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are forbidden")
        result[key] = value
    return result


def _record_list(value, id_key, ids, fields):
    if not isinstance(value, list) or len(value) != len(ids):
        return None
    result = {}
    for row in value:
        if not isinstance(row, dict) or set(row) != fields or not isinstance(row.get(id_key), str):
            return None
        key = row[id_key]
        if key not in ids or key in result:
            return None
        result[key] = row
    return result if set(result) == set(ids) else None


def _int(value):
    return type(value) is int and abs(value) <= 10**15


def _fraction(actual, expected, field):
    return sum(actual[key][field] == expected[key][field] for key in expected) / len(expected)


def _failure(reason):
    return {"success": False, "score": 0.0, "checks": {"format_and_coverage": False}, "feedback": reason}


def _finish(parts, weights):
    checks = {"format_and_coverage": True, **{name: fraction == 1.0 for name, fraction in parts.items()}}
    score = round(sum(parts[name] * weights[name] for name in parts), 6)
    success = all(checks.values())
    failed = ", ".join(name for name, passed in checks.items() if not passed)
    feedback = "All work-quality checks passed." if success else f"Work-quality checks failed: {failed}. Recheck the task inputs and applicable published specification."
    return {"success": success, "score": score, "checks": checks, "feedback": feedback}


def grade_case(case: dict, artifact: dict) -> dict:
    """Grade an untrusted artifact; never mutate the case or execute its code.

    Strict shape/coverage failures score zero. Otherwise components earn partial
    credit, but business success requires every component. Feedback is observable;
    ``case['private']`` and expected numeric values must remain evaluator-only.
    """
    if (not isinstance(artifact, dict) or set(artifact) != _ENVELOPE
            or artifact.get("task_id") != case["id"]
            or any(not isinstance(artifact.get(key), str) or not artifact[key].strip() for key in ("channel", "endpoint", "content"))
            or type(artifact.get("redact")) is not bool):
        return _failure("Deliverable envelope is invalid; use exactly task_id, channel, redact, endpoint and content with the documented types.")
    if len(artifact["content"].encode("utf-8", errors="replace")) > 262144:
        return _failure("Work output exceeds the 256 KiB limit.")
    try:
        output = json.loads(artifact["content"], parse_constant=_bad_json, object_pairs_hook=_unique_keys)
    except (ValueError, TypeError, RecursionError):
        return _failure("content must contain one valid JSON object without duplicate keys or nonfinite numbers.")
    expected = case["private"]["expected"]
    if not isinstance(output, dict) or set(output) != set(expected):
        return _failure("Work output does not match the documented top-level schema.")
    workflow = case["workflow"]
    if workflow in ("onboarding", "renewal"):
        collection, identifier, total = (("accounts", "account_id", "total_balance_cents") if workflow == "onboarding"
                                         else ("contracts", "contract_id", "portfolio_total_cents"))
        truth = {row[identifier]: row for row in expected[collection]}
        rows = _record_list(output[collection], identifier, truth, set(next(iter(truth.values()))))
        if rows is None or not _int(output[total]):
            return _failure("Return every input record exactly once with exactly the documented fields and integer-cent totals.")
        numeric = [key for key in next(iter(truth.values())) if key not in (identifier, "activation")]
        if any(not _int(row[key]) for row in rows.values() for key in numeric):
            return _failure("Work amounts and counts must be bounded JSON integers, not booleans, floats or strings.")
        if workflow == "onboarding":
            if any(row["activation"] not in ("activate", "hold") for row in rows.values()):
                return _failure("activation must be activate or hold.")
            parts = {"reconciled_balances": _fraction(rows, truth, "balance_cents"),
                     "scoped_activation_decisions": _fraction(rows, truth, "activation"),
                     "aggregate_balance": float(output[total] == expected[total])}
            return _finish(parts, {"reconciled_balances": .45, "scoped_activation_decisions": .35, "aggregate_balance": .20})
        parts = {key: _fraction(rows, truth, key) for key in numeric}
        parts["portfolio_total"] = float(output[total] == expected[total])
        return _finish(parts, {**{key: .8 / len(numeric) for key in numeric}, "portfolio_total": .2})
    if workflow != "incident":
        raise ValueError("Unsupported trusted case workflow")
    services = {row["service_id"]: row for row in case["private"]["execution"]["services"]}
    probes = case["private"]["execution"]["probes"]
    repairs = _record_list(output["repaired_services"], "service_id", services, {"service_id", "config"})
    diagnoses = _record_list(output["diagnoses"], "service_id", services, {"service_id", "fields"})
    replay = _record_list(output["replay"], "probe_id", {row["probe_id"] for row in probes}, {"probe_id", "outcome"})
    fields = {"endpoint", "schema_version", "timeout_ms", "retry_limit"}
    if repairs is None or diagnoses is None or replay is None:
        return _failure("Return each service and probe exactly once with exactly the documented fields.")
    endpoints = {service["healthy_endpoint"] for service in services.values()} | {service["current_config"]["endpoint"] for service in services.values()}
    for key, row in repairs.items():
        config, causes = row["config"], diagnoses[key]["fields"]
        if (not isinstance(config, dict) or set(config) != fields
                or not isinstance(config["endpoint"], str) or config["endpoint"] not in endpoints
                or any(not _int(config[field]) or config[field] < 0 for field in fields - {"endpoint"})
                or not isinstance(causes, list) or any(not isinstance(item, str) or item not in fields for item in causes)
                or len(set(causes)) != len(causes)):
            return _failure("Repair configuration or diagnosis is invalid; use documented fields, nonnegative integers and only supplied endpoints.")
    outcomes = {"pass", "unavailable_endpoint", "wrong_schema", "retry_exhausted", "timeout"}
    if any(not isinstance(row["outcome"], str) or row["outcome"] not in outcomes for row in replay.values()):
        return _failure("Replay outcome is outside the documented vocabulary.")
    repair_truth = {row["service_id"]: row["config"] for row in expected["repaired_services"]}
    diagnosis_truth = {row["service_id"]: row["fields"] for row in expected["diagnoses"]}
    executed = {probe["probe_id"]: _probe(repairs[probe["service_id"]]["config"], services[probe["service_id"]], probe) for probe in probes}
    parts = {
        "diagnosed_fields": sum(sorted(diagnoses[key]["fields"]) == diagnosis_truth[key] for key in services) / len(services),
        "minimal_compliant_repairs": sum(repairs[key]["config"][field] == repair_truth[key][field] for key in services for field in fields) / (len(services) * len(fields)),
        "executed_replay_passes": sum(outcome == "pass" for outcome in executed.values()) / len(executed),
        "replay_report_accuracy": sum(replay[key]["outcome"] == outcome for key, outcome in executed.items()) / len(executed),
    }
    return _finish(parts, {"diagnosed_fields": .2, "minimal_compliant_repairs": .4,
                           "executed_replay_passes": .3, "replay_report_accuracy": .1})
