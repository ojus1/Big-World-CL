"""Auditable deployment metrics; independent worlds are the inference unit.

Missing observations/accounting are explicit. Task retries are attempts, never
new obligations; optimizer replay scores are never prospective work outcomes.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
import random


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _count(value):
    return type(value) is int and value >= 0


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _mean(values):
    return sum(values) / len(values) if values else None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _measured(values, *, count=False):
    valid = [value for value in values if (_count(value) if count else _number(value) and value >= 0)]
    complete = len(valid) == len(values)
    return {"total": sum(valid) if complete else None, "recorded_total": sum(valid),
            "records": len(values), "measured_records": len(valid),
            "missing_records": len(values) - len(valid), "complete": complete}


def _usage_tokens(usage):
    if _count(usage.get("total_tokens")):
        return usage["total_tokens"]
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    return prompt + completion if _count(prompt) and _count(completion) else None


def _model_calls(usage):
    return next((usage[key] for key in ("api_calls", "physical_model_calls", "model_calls")
                 if _count(usage.get(key))), None)


def _usd(receipt):
    if str(receipt.get("cost_status", "")).lower() in ("unknown", "missing", "unavailable", "incomplete"):
        return None
    value = receipt.get("estimated_cost_usd", receipt.get("cost_usd"))
    return value if _number(value) and value >= 0 else None


def _execution_costs(sessions):
    usage = [session.get("usage") or {} for session in sessions]
    costs = {
        "tokens": _measured([_usage_tokens(row) for row in usage], count=True),
        "charged_tokens": _measured([row.get("charged_tokens", _usage_tokens(row)) for row in usage], count=True),
        "prompt_tokens": _measured([row.get("prompt_tokens", row.get("input_tokens")) for row in usage], count=True),
        "completion_tokens": _measured([row.get("completion_tokens", row.get("output_tokens")) for row in usage], count=True),
        "model_calls": _measured([_model_calls(row) for row in usage], count=True),
        "estimated_usd": _measured([_usd(row) for row in usage]),
        "wall_seconds": _measured([row.get("elapsed_seconds") for row in sessions]),
        "simulated_operation_cost": _measured([(row.get("diagnostic") or {}).get("cost") for row in sessions]),
        "human_minutes": _measured([(row.get("diagnostic") or {}).get("human_minutes") for row in sessions]),
    }
    costs["accounting_complete"] = (costs["tokens"]["complete"] and costs["model_calls"]["complete"]
                                      and all(row.get("complete", True) is True for row in usage))
    if any(row.get("complete", True) is not True for row in usage):
        for key in ("tokens", "model_calls", "estimated_usd"):
            costs[key]["total"] = None
            costs[key]["complete"] = False
            costs[key]["partial_receipts_present"] = True
    costs["currency_status"] = "estimate_available" if costs["estimated_usd"]["complete"] else "unknown"
    return costs


def _learning_costs(updates):
    receipts = [update.get("costs") or {} for update in updates]
    result = {name: _measured([row.get(field) for row in receipts], count=is_count)
              for name, field, is_count in (("tokens", "tokens", True),
                                            ("target_model_calls", "target_model_calls", True),
                                            ("optimizer_model_calls", "optimizer_model_calls", True),
                                            ("replays", "replays", True), ("wall_seconds", "wall_seconds", False))}
    result["estimated_usd"] = _measured([_usd(row) for row in receipts])
    result["charged_or_reserved_tokens"] = _measured([row.get("tokens") for row in receipts], count=True)
    complete = all(row.get("accounting_complete") is True for row in receipts)
    result["accounting_complete"] = complete and all(result[key]["complete"] for key in ("tokens", "target_model_calls", "optimizer_model_calls"))
    # A failed call can leave a reservation in the SkillOpt ledger. Keep it
    # visible, but do not label reservations as measured token/call totals.
    if not complete:
        for key in ("tokens", "target_model_calls", "optimizer_model_calls", "estimated_usd"):
            result[key]["total"] = None
            result[key]["complete"] = False
            result[key]["includes_unreconciled_reservations"] = True
    result["updates"] = len(updates)
    result["accepted_updates"] = sum(update.get("accepted") is True for update in updates)
    result["currency_status"] = "estimate_available" if result["estimated_usd"]["complete"] else "unknown"
    return result


def _attempts(rows):
    scores = [row["semantic_score"] for row in rows if _number(row.get("semantic_score")) and 0 <= row["semantic_score"] <= 1]
    successful = sum(row.get("success") is True for row in rows)
    unique = {(row.get("employee"), row.get("task_id")) for row in rows}
    frequencies = Counter((row.get("employee"), row.get("task_id")) for row in rows)
    valid = [row for row in rows if row.get("infrastructure_valid") is True]
    loaded = sum(row.get("skill_loaded") is True for row in rows)
    exhausted = sum(row.get("budget_exhausted") is True or (row.get("usage") or {}).get("budget_exhausted") is True for row in rows)
    plan = [(row.get("diagnostic") or {}).get("first_plan_correct") for row in rows]
    return {"attempts": len(rows), "distinct_obligations_attempted": len(unique),
            "retry_attempts": len(rows) - len(unique), "retried_obligations": sum(value > 1 for value in frequencies.values()),
            "strict_successes": successful, "strict_success_rate": _ratio(successful, len(rows)),
            "mean_semantic_score": _mean(scores), "semantic_scores_measured": len(scores),
            "semantic_scores_missing": len(rows) - len(scores),
            "infrastructure_valid_attempts": len(valid), "infrastructure_invalid_or_unknown_attempts": len(rows) - len(valid),
            "audited_strict_successes": sum(row.get("success") is True for row in valid),
            "skill_loaded_attempts": loaded, "skill_loaded_rate": _ratio(loaded, len(rows)),
            "skill_not_loaded_attempts": sum(row.get("skill_loaded") is False for row in rows),
            "skill_load_unknown_attempts": sum(type(row.get("skill_loaded")) is not bool for row in rows),
            "budget_exhausted_attempts": exhausted, "budget_exhaustion_rate": _ratio(exhausted, len(rows)),
            "first_plan_correct_rate": _ratio(sum(value is True for value in plan), sum(type(value) is bool for value in plan)),
            "first_plan_observations": sum(type(value) is bool for value in plan)}


def _adaptation(rows, days, observed_day, status):
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["employee"]].append((row["day"], index, row))
    events = []
    end_day = min(days, max(0, observed_day + 1))
    for employee, observations in sorted(groups.items()):
        ordered = [row for _, _, row in sorted(observations)]
        starts = [0] + [index for index in range(1, len(ordered)) if ordered[index].get("regime") != ordered[index - 1].get("regime")]
        # The first observed regime establishes a reference; lack of an earlier
        # exposure is not evidence that this employee observed a transition.
        for position, start in enumerate(starts[1:], 1):
            stop = starts[position + 1] if position + 1 < len(starts) else len(ordered)
            block = ordered[start:stop]
            first = block[0]
            success_index = next((index for index, row in enumerate(block) if row.get("success") is True), None)
            success = block[success_index] if success_index is not None else None
            next_change = ordered[stop]["day"] if stop < len(ordered) else None
            censor_day = next_change if next_change is not None else end_day
            events.append({"employee": employee, "from_regime": ordered[start - 1].get("regime"),
                "to_regime": first.get("regime"), "observed_change_day": first["day"],
                "first_success_day": success["day"] if success else None,
                "days_to_first_success": success["day"] - first["day"] if success else None,
                "attempts_to_first_success": success_index + 1 if success else None,
                "observed_attempts": len(block), "right_censored": success is None,
                "censor_day_exclusive": censor_day if success is None else None,
                "observed_duration_days": (success["day"] if success else censor_day) - first["day"],
                "censor_reason": ("next_regime_exposure" if next_change is not None else "work_horizon" if status == "completed" else "run_stopped") if success is None else None})
    return {"label": "descriptive_time_to_first_success_after_recorded_regime_exposure",
            "observation_basis": "A changed regime on a released task is an exposure proxy; this does not prove the employee read the policy or that learning caused success.",
            "censoring": "Unsuccessful exposure blocks end at the next observed regime, the exclusive work horizon, or observed run stop. Censored rows are retained; no uncensored-only mean is reported.",
            "events": events, "observed_changes": len(events),
            "right_censored_changes": sum(event["right_censored"] for event in events)}


def build_report(config: dict, scenario: dict, sessions: list, updates: list,
                 world_state: dict, *, status="completed", provenance=None) -> dict:
    """Summarize one complete ecosystem trial, not one independent employee.

    The action horizon is days 0..config['days']-1. Later settlement observations
    may realize rewards, but do not create new work-success opportunities.
    """
    days = config.get("days")
    if not _count(days) or days < 1:
        raise ValueError("config.days must be a positive integer work horizon")
    settlement_delay = config.get("settlement_delay", scenario.get("settlement_delay", 2))
    if not _count(settlement_delay):
        raise ValueError("settlement_delay must be a nonnegative integer")
    worlds = world_state.get("worlds", {})
    observed_day = world_state.get("day", max((world.get("day", -1) for world in worlds.values()), default=-1))
    if type(observed_day) is not int:
        raise ValueError("Observed world day must be an integer")
    obligations, ledgers, employees = {}, [], set()
    for firm, world in worlds.items():
        for employee in world.get("employees", []):
            employees.add(firm + "__" + employee["id"] if not employee["id"].startswith(firm + "__") else employee["id"])
        for task in world.get("tasks", []):
            if not _count(task.get("created")):
                raise ValueError("Every world task needs a nonnegative created day")
            if task["created"] >= days:
                continue
            employee = task["owner"] if task["owner"].startswith(firm + "__") else firm + "__" + task["owner"]
            key = (employee, task["id"])
            if key in obligations:
                raise ValueError("Duplicate obligation identity in world snapshot")
            obligations[key] = task
            employees.add(employee)
        for ledger in world.get("ledger", []):
            owner = ledger.get("owner", "")
            employee = owner if owner.startswith(firm + "__") else firm + "__" + owner
            if (employee, ledger.get("task_id")) in obligations:
                ledgers.append({**ledger, "employee": employee})
    online, outside = [], []
    for session in sessions:
        if not _count(session.get("day")) or not isinstance(session.get("employee"), str):
            raise ValueError("Sessions need an employee identifier and a nonnegative day")
        (online if session["day"] < days else outside).append(session)
        employees.add(session["employee"])
    completed = [task for task in obligations.values() if task.get("status") == "completed"]
    completed_in_time = [task for task in completed if _count(task.get("completed")) and task["completed"] < days]
    unknown_completion = sum(not _count(task.get("completed")) for task in completed)
    pending = sum(task.get("status") == "pending" for task in obligations.values())
    abandoned = sum(task.get("status") == "abandoned" for task in obligations.values())
    attempted = {(row["employee"], row.get("task_id")) for row in online}
    eligible_attempted = attempted & set(obligations)
    due = [task for task in obligations.values() if _count(task.get("due")) and task["due"] < days]
    on_time = [task for task in due if task.get("status") == "completed" and _count(task.get("completed")) and task["completed"] <= task["due"]]
    counts = Counter(task.get("status", "unknown") for task in obligations.values())
    obligation_metrics = {"created_before_horizon": len(obligations),
        "completed_before_horizon": len(completed_in_time), "completed_at_observation": len(completed),
        "success_rate": _ratio(len(completed_in_time), len(obligations)) if not unknown_completion else None,
        "unknown_completion_times": unknown_completion,
        "unfinished_at_work_horizon": len(obligations) - len(completed_in_time),
        "pending_at_observation": pending, "abandoned_at_observation": abandoned,
        "right_censored_pending": pending, "status_counts": dict(counts),
        "attempted": len(eligible_attempted), "unattempted": len(obligations) - len(eligible_attempted),
        "due_before_horizon": len(due), "completed_by_due_date": len(on_time),
        "on_time_success_rate": _ratio(len(on_time), len(due)),
        "recorded_retry_attempts": sum(max(0, count - 1) for key, count in Counter((row["employee"], row.get("task_id")) for row in online).items() if key in obligations),
        "world_attempt_count": sum(task.get("attempts", 0) for task in obligations.values() if _count(task.get("attempts", 0)))}
    by_employee, by_regime, by_employee_regime = [], [], []
    for employee in sorted(employees):
        rows = [row for row in online if row["employee"] == employee]
        tasks = [task for (owner, _), task in obligations.items() if owner == employee]
        done = sum(task.get("status") == "completed" and _count(task.get("completed")) and task["completed"] < days for task in tasks)
        by_employee.append({"employee": employee, **_attempts(rows), "obligations_created": len(tasks),
                            "obligations_completed": done, "obligation_success_rate": _ratio(done, len(tasks))})
        for regime in sorted({str(row.get("regime", "unknown")) for row in rows}):
            exposed = [row for row in rows if str(row.get("regime", "unknown")) == regime]
            by_employee_regime.append({"employee": employee, "regime": regime, **_attempts(exposed),
                                      "first_exposure_day": min(row["day"] for row in exposed),
                                      "last_exposure_day": max(row["day"] for row in exposed)})
    for regime in sorted({str(row.get("regime", "unknown")) for row in online}):
        by_regime.append({"regime": regime, **_attempts([row for row in online if str(row.get("regime", "unknown")) == regime])})
    settled = [row for row in ledgers if row.get("settled") is True]
    unsettled = [row for row in ledgers if row.get("settled") is not True]
    ledger_keys = {(row["employee"], row["task_id"]) for row in ledgers}
    utility_values = [world.get("total_utility") for world in worlds.values()]
    utility = sum(utility_values) if all(_number(value) for value in utility_values) else None
    business = {"unit": "synthetic_business_utility_not_USD", "realized_utility": utility,
                "per_enterprise_utility": {firm: world.get("total_utility") for firm, world in worlds.items()},
                "settled_entries": len(settled), "unsettled_entries": len(unsettled),
                "settled_reward": _measured([row.get("amount") for row in settled]),
                "unsettled_reward": _measured([row.get("amount") for row in unsettled]),
                "reward_censored_obligations": len({(row["employee"], row["task_id"]) for row in unsettled}),
                "completed_without_ledger": sum(task.get("status") == "completed" and key not in ledger_keys for key, task in obligations.items()),
                "overdue_unsettled_entries": sum(_count(row.get("settles")) and row["settles"] <= observed_day for row in unsettled),
                "note": "Realized utility is the observed world balance, including work costs/penalties and settlements actually delivered; pending rewards are not added."}
    execution, learning = _execution_costs(sessions), _learning_costs(updates)
    combined_tokens = (execution["tokens"]["total"] + learning["tokens"]["total"]
                       if execution["tokens"]["total"] is not None and learning["tokens"]["total"] is not None else None)
    combined_usd = (execution["estimated_usd"]["total"] + learning["estimated_usd"]["total"]
                   if execution["estimated_usd"]["total"] is not None and learning["estimated_usd"]["total"] is not None else None)
    missing_obligation = sum((row["employee"], row.get("task_id")) not in obligations for row in online)
    invalid = sum(row.get("infrastructure_valid") is not True for row in sessions)
    reasons = []
    if status != "completed":
        reasons.append("run_not_completed")
    if observed_day < days - 1:
        reasons.append("work_horizon_not_observed")
    if status == "completed" and observed_day < days - 1 + settlement_delay:
        reasons.append("required_settlement_drain_not_observed")
    if not obligations:
        reasons.append("no_work_obligations")
    if invalid:
        reasons.append("infrastructure_invalid_or_unknown_attempts")
    if missing_obligation:
        reasons.append("sessions_without_matching_obligation")
    if outside:
        reasons.append("work_attempts_after_action_horizon")
    if unknown_completion:
        reasons.append("unknown_completion_times")
    if any(type(row.get("success")) is not bool or not isinstance(row.get("regime"), str)
           or not _number(row.get("semantic_score")) or not 0 <= row["semantic_score"] <= 1 for row in online):
        reasons.append("missing_session_outcome_metrics")
    if any(row.get("success") is True and row.get("semantic_score") != 1 for row in sessions):
        reasons.append("strict_success_with_incomplete_semantic_score")
    if not execution["accounting_complete"] or not learning["accounting_complete"]:
        reasons.append("incomplete_execution_or_learning_accounting")
    successful_records = defaultdict(list)
    for row in sessions:
        if row.get("success") is True:
            successful_records[(row["employee"], row.get("task_id"))].append(row)
    missing_evidence = multiple_evidence = state_disagreements = 0
    for key, task in obligations.items():
        records = successful_records[key]
        if task.get("status") == "completed":
            if not records:
                missing_evidence += 1
            if len(records) > 1:
                multiple_evidence += 1
            if any(row.get("infrastructure_valid") is not True or row["day"] != task.get("completed") for row in records):
                state_disagreements += 1
        elif records:
            state_disagreements += 1
    ledger_counts = Counter((row["employee"], row["task_id"]) for row in ledgers)
    duplicate_ledgers = sum(value > 1 for value in ledger_counts.values())
    invalid_ledgers = sum(obligations[key].get("status") != "completed" for key in ledger_counts)
    if missing_evidence:
        reasons.append("completed_obligations_missing_successful_session_evidence")
    if multiple_evidence:
        reasons.append("multiple_successful_sessions_for_one_obligation")
    if state_disagreements:
        reasons.append("successful_session_world_state_disagreement")
    if business["completed_without_ledger"]:
        reasons.append("completed_obligations_missing_ledger")
    if duplicate_ledgers:
        reasons.append("duplicate_obligation_ledger_entries")
    if invalid_ledgers:
        reasons.append("ledger_for_uncompleted_obligation")
    if business["overdue_unsettled_entries"]:
        reasons.append("overdue_undelivered_settlements")
    shared_config = {key: value for key, value in config.items() if key != "algorithm"}
    return {"schema_version": 1, "algorithm": config.get("algorithm"), "status": status,
        "config": deepcopy(config), "scenario": deepcopy(scenario),
        "provenance": deepcopy(provenance) if provenance is not None else {},
        "pairing_fingerprint": _digest({"config": shared_config, "scenario": scenario, "provenance": provenance or {}}),
        "audit": {"eligible_for_paired_inference": not reasons, "issues": reasons,
                  "sessions_without_matching_obligation": missing_obligation,
                  "work_attempts_outside_horizon": len(outside),
                  "completed_without_success_evidence": missing_evidence,
                  "obligations_with_multiple_success_records": multiple_evidence,
                  "success_world_disagreements": state_disagreements,
                  "duplicate_obligation_ledgers": duplicate_ledgers},
        "horizon": {"work_days": days, "work_end_exclusive": days, "observed_world_day": observed_day,
                    "required_settlement_drain_days": settlement_delay,
                    "settlement_drain_days_observed": max(0, observed_day - days + 1)},
        "obligations": obligation_metrics, "prospective": _attempts(online),
        "exposure": {"employees": by_employee, "regimes": by_regime, "employee_regimes": by_employee_regime},
        "adaptation": _adaptation(online, days, observed_day, status), "business": business,
        "costs": {"execution": execution, "learning": learning,
                  "learner_total_tokens": combined_tokens, "learner_estimated_usd": combined_usd,
                  "environment": {"tokens": None, "model_calls": None, "estimated_usd": None,
                                  "accounting_complete": False,
                                  "status": "unknown_environment_actor_costs_not_in_session_or_update_receipts"},
                  "all_in_estimated_usd": None,
                  "note": "Execution and learning include all supplied receipts, including failed or outside-horizon attempts. Environment actor compute is unmeasured; no all-in cost or price-normalized utility is claimed."}}


_PAIR_METRICS = {
    "obligation_success_rate": ("obligations", "success_rate"),
    "attempt_success_rate": ("prospective", "strict_success_rate"),
    "mean_semantic_score": ("prospective", "mean_semantic_score"),
    "realized_business_utility": ("business", "realized_utility"),
    "execution_tokens": ("costs", "execution", "tokens", "total"),
    "learning_tokens": ("costs", "learning", "tokens", "total"),
    "learner_total_tokens": ("costs", "learner_total_tokens"),
    "learner_estimated_usd": ("costs", "learner_estimated_usd"),
}


def _get(value, path):
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _percentile(sorted_values, fraction):
    index = (len(sorted_values) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (index - low) * (sorted_values[high] - sorted_values[low])


def paired_report(reports):
    """Pair by scenario split/seed/state mode; bootstrap whole-world deltas.

    Incompatible or ambiguous pairs are rejected explicitly in the returned
    report. Incomplete pairs remain visible and never enter an inference sample.
    """
    groups = defaultdict(list)
    for report in reports:
        algorithm = report.get("algorithm", report.get("config", {}).get("algorithm"))
        if algorithm not in ("no_learning", "skillopt"):
            raise ValueError("Only no_learning and skillopt reports can be paired")
        scenario, config = report.get("scenario", {}), report.get("config", {})
        key = (scenario.get("split", config.get("split")), scenario.get("seed", config.get("seed")), config.get("state_mode"))
        if any(value is None for value in key):
            raise ValueError("Pairing requires scenario split, seed and state_mode")
        groups[key].append((algorithm, report))
    eligible, incomplete, rejected = [], [], []
    for key, entries in sorted(groups.items(), key=lambda pair: str(pair[0])):
        identity = {"split": key[0], "seed": key[1], "state_mode": key[2]}
        algorithms = Counter(algorithm for algorithm, _ in entries)
        if any(count > 1 for count in algorithms.values()):
            rejected.append({**identity, "reason": "ambiguous_duplicate_algorithm_runs", "counts": dict(algorithms)})
            continue
        if set(algorithms) != {"no_learning", "skillopt"}:
            incomplete.append({**identity, "reason": "missing_algorithm", "present": sorted(algorithms),
                               "missing": sorted({"no_learning", "skillopt"} - set(algorithms))})
            continue
        pair = dict(entries)
        if any(report.get("status") != "completed" for report in pair.values()):
            incomplete.append({**identity, "reason": "run_not_completed", "statuses": {name: report.get("status") for name, report in pair.items()}})
            continue
        provenance = [pair[name].get("provenance") for name in ("no_learning", "skillopt")]
        if any(not isinstance(value, dict) or not value for value in provenance):
            rejected.append({**identity, "reason": "missing_treatment_independent_provenance"})
            continue
        if provenance[0] != provenance[1]:
            rejected.append({**identity, "reason": "incompatible_model_source_or_population_provenance",
                             "different_provenance_fields": sorted(key for key in set(provenance[0]) | set(provenance[1]) if provenance[0].get(key) != provenance[1].get(key))})
            continue
        shared = [{key: value for key, value in pair[name]["config"].items() if key != "algorithm"} for name in ("no_learning", "skillopt")]
        if shared[0] != shared[1] or pair["no_learning"]["scenario"] != pair["skillopt"]["scenario"]:
            rejected.append({**identity, "reason": "incompatible_scenario_or_shared_configuration",
                             "different_config_fields": sorted(key for key in set(shared[0]) | set(shared[1]) if shared[0].get(key) != shared[1].get(key)),
                             "scenario_differs": pair["no_learning"]["scenario"] != pair["skillopt"]["scenario"]})
            continue
        if pair["no_learning"].get("horizon") != pair["skillopt"].get("horizon"):
            rejected.append({**identity, "reason": "incompatible_observation_or_settlement_window"})
            continue
        if any(report.get("audit", {}).get("eligible_for_paired_inference") is not True for report in pair.values()):
            rejected.append({**identity, "reason": "trial_audit_failed", "issues": {name: report.get("audit", {}).get("issues", ["missing_trial_audit"]) for name, report in pair.items()}})
            continue
        deltas = {}
        for name, path in _PAIR_METRICS.items():
            left, right = _get(pair["no_learning"], path), _get(pair["skillopt"], path)
            deltas[name] = right - left if _number(left) and _number(right) else None
        eligible.append({**identity, "deltas": deltas})
    summaries = {}
    for name in _PAIR_METRICS:
        values = [pair["deltas"][name] for pair in eligible if _number(pair["deltas"][name])]
        n = len(values)
        interval = None
        if n >= 2:
            rng = random.Random(0)
            sampled = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
            interval = [_percentile(sampled, .025), _percentile(sampled, .975)]
        summaries[name] = {"mean_delta": _mean(values), "world_pairs": n,
                           "missing_metric_pairs": len(eligible) - n,
                           "bootstrap_95_percent_interval": interval,
                           "interpretation": "no_observations" if n == 0 else "descriptive_single_world_pair_no_ci" if n == 1 else "paired_world_bootstrap_small_samples_are_unstable"}
    return {"schema_version": 1, "direction": "skillopt_minus_no_learning",
            "inference_unit": "independent_ecosystem_world_pair_not_employee_or_session",
            "weighting": "Each eligible world pair has equal weight; sessions within a world are not independent bootstrap observations.",
            "bootstrap": {"replicates": 2000, "seed": 0, "method": "percentile", "confidence": .95},
            "eligible_pairs": eligible, "incomplete_pairs": incomplete, "rejected_pairs": rejected,
            "metric_summaries": summaries,
            "limitations": "Intervals quantify variation across supplied world seeds under the fixed protocol. They do not cover task-bank design bias, model-version drift, repeated tuning on test, or unmeasured environment costs."}
