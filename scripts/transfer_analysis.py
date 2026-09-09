"""Pure, descriptive selection and analysis for the development transfer study.

Neither helper calls a model, reads a file, trains a skill, or exposes private
experience text in public summaries. The caller pins raw artifacts and verifies
native receipts before passing their parsed contents here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re

from lifespan.evaluation.protocol import experience_split, select_experiences
from scripts.calibration_bank import expected_slots
from scripts.transfer_probes import VERSION as PROBE_VERSION


VERSION = "development-transfer-analysis-v1"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,239}\Z")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _integer(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def select_employee(source_checkpoint, bank, calibration_state, *, cutoff_day=9):
    """Select the eligible employee with most failed valid calibration repeats.

    Ties use employee ID. Eligibility requires at least two distinct underlying
    train obligations and two val obligations released by both observation and
    feedback cutoffs. Historical retries do not increase eligibility. Returned
    ``experiences`` are PRIVATE optimizer inputs; only ``ranking`` is public.
    """
    if not _integer(cutoff_day):
        raise ValueError("cutoff_day must be a nonnegative integer")
    if calibration_state.get("status") != "completed":
        raise ValueError("Employee selection requires completed calibration")
    planned = expected_slots(bank)
    if len(planned) != 44:
        raise ValueError("This preregistered selection requires all 44 historical calibration slots")
    allowed = {(row["selection_id"], row["repeat_index"]): row for row in planned}
    selections = {row["selection_id"]: row for row in bank["selections"]}
    roster = {firm + "__" + local for firm, world in source_checkpoint["ecosystem"]["worlds"].items()
              for local in world["employees"]}
    sessions = source_checkpoint["runner"]["sessions"]
    by_id = {row["id"]: row for row in sessions}
    if len(by_id) != len(sessions):
        raise ValueError("Source session identities must be unique")
    for identifier, selection in selections.items():
        row = by_id.get(identifier)
        if (selection["employee"] not in roster or row is None
                or any(row.get(key) != selection[field] for key, field in
                       (("employee", "employee"), ("task_id", "source_task_id"),
                        ("day", "source_day"), ("regime", "regime")))):
            raise ValueError("Calibration selection disagrees with the source roster or original session")
    results, seen, attempts, failures = calibration_state.get("results", []), set(), Counter(), Counter()
    for result in results:
        key = (result.get("selection_id"), result.get("repeat_index"))
        if type(result.get("repeat_index")) is not int or key not in allowed or key in seen:
            raise ValueError("Calibration results must form a bijection with the planned slots")
        if (result.get("rollout_id") != allowed[key]["rollout_id"] or result.get("status") != "completed"
                or result.get("infrastructure_valid") is not True or type(result.get("success")) is not bool):
            raise ValueError("Every calibration slot needs an identified, valid completed boolean outcome")
        employee = selections[key[0]]["employee"]
        if result.get("employee", employee) != employee:
            raise ValueError("Calibration receipt employee contradicts its selected source session")
        seen.add(key)
        attempts[employee] += 1
        failures[employee] += not result["success"]
    if seen != set(allowed):
        raise ValueError("Missing calibration receipts cannot drive employee selection")
    records = source_checkpoint["runner"]["experiences"]
    seen_experiences = set()
    for record in records:
        source_row = by_id.get(record.get("id"))
        if (record.get("id") in seen_experiences or record.get("employee") not in roster
                or source_row is None or source_row["employee"] != record["employee"]
                or source_row["task_id"] != record.get("source_session")
                or record.get("split") != experience_split(record["source_session"])
                or not _integer(record.get("available_day"))
                or not _integer(record.get("feedback_available_day", record.get("available_day")))
                or record["available_day"] < source_row["day"]
                or record.get("feedback_available_day", record["available_day"]) < source_row["day"]):
            raise ValueError("Original experience identity, split or release metadata is inconsistent")
        seen_experiences.add(record["id"])
    observed_days = [by_id[row["id"]]["day"] for row in records]
    if any(right < left for left, right in zip(observed_days, observed_days[1:])):
        raise ValueError("Original experience pool must already be chronological; do not silently reorder it")
    ranking = []
    for employee in sorted(roster):
        eligible = select_experiences(records, employee, cutoff_day, len(records), len(records))
        counts = Counter(row["split"] for row in eligible)
        ranking.append({"employee": employee, "eligible": counts["train"] >= 2 and counts["val"] >= 2,
                        "train_unique_count": counts["train"], "val_unique_count": counts["val"],
                        "calibration_failures": failures[employee], "calibration_attempts": attempts[employee]})
    ranking.sort(key=lambda row: (not row["eligible"], -row["calibration_failures"], row["employee"]))
    if not ranking or not ranking[0]["eligible"]:
        raise ValueError("No source employee has two released unique train and two val obligations")
    employee = ranking[0]["employee"]
    selected = select_experiences(records, employee, cutoff_day, 2, 2)
    if Counter(row["split"] for row in selected) != {"train": 2, "val": 2}:
        raise ValueError("Published experience selector did not supply the required two plus two pool")
    return {"employee": employee, "experiences": deepcopy(selected), "ranking": ranking,
            "cutoff_day": cutoff_day, "source_checkpoint_sha256": _hash(source_checkpoint),
            "bank_sha256": _hash(bank), "calibration_state_sha256": _hash(calibration_state),
            "selection_rule": "Among employees with two released unique train and two val obligations, "
                "choose most failed valid calibration repeats; ties use employee ID. Take the published "
                "selector's two train and two val records from the complete original ordered pool. "
                "Retries update content while preserving each obligation's first-appearance position.",
            "visibility": "experiences are private optimizer inputs; ranking and selection metadata may be public."}


def _design(manifest, slots):
    probes = manifest.get("probes", [])
    if (manifest.get("generator_version") != PROBE_VERSION or manifest.get("probe_count") != 4
            or len(probes) != 4 or not _integer(manifest.get("cutoff_day"))
            or [row.get("probe_index") for row in probes] != [0, 1, 2, 3]
            or [row.get("regime") for row in probes] != ["changed", "changed", "reversal", "reversal"]
            or any(type(row.get("probe_index")) is not int or row.get("split") != "validation" or row.get("day") != manifest["cutoff_day"] + index + 1
                   or row.get("employee") != manifest.get("employee") for index, row in enumerate(probes))
            or len({row.get("task_id") for row in probes}) != 4):
        raise ValueError("A four-probe frozen development manifest with the declared future regime sequence is required")
    if not isinstance(slots, list) or len(slots) != 16:
        raise ValueError("Transfer evaluation requires sixteen planned slots: four probes, two arms, two repeats")
    by_id, cells = {}, set()
    for slot in slots:
        identifier = slot.get("rollout_id")
        key = (slot.get("probe_index"), slot.get("repeat_index"), slot.get("arm"))
        if (not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier) or identifier in by_id
                or type(key[0]) is not int or key[0] not in range(4)
                or type(key[1]) is not int or key[1] not in range(2) or key[2] not in ("seed", "deployed")
                or key in cells):
            raise ValueError("Transfer slots must uniquely cover every probe, repeat and arm with safe rollout IDs")
        cells.add(key)
        by_id[identifier] = slot
    return by_id


def _measure(values, planned):
    known = [value for value in values if _number(value) and value >= 0]
    complete = len(known) == planned
    return {"total": sum(known) if complete else None, "recorded_total": sum(known),
            "measured_slots": len(known), "unknown_slots": planned - len(known), "complete": complete}


def _cost_values(result):
    usage = result.get("usage") or {}
    complete = usage.get("complete") is True
    tokens = usage.get("total_tokens")
    if not _integer(tokens):
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        tokens = prompt + completion if _integer(prompt) and _integer(completion) else None
    calls = next((usage[field] for field in ("api_calls", "physical_model_calls", "model_calls")
                  if _integer(usage.get(field))), None)
    charged = usage.get("charged_tokens")
    if not _integer(charged):
        charged = result.get("reserved_tokens")
    unknown_currency = str(usage.get("cost_status", "")).lower() in ("unknown", "missing", "unavailable", "incomplete")
    currency = usage.get("estimated_cost_usd", usage.get("cost_usd"))
    return {"tokens": tokens if complete and _integer(tokens) else None,
            "physical_model_calls": calls if complete else None,
            "charged_tokens": charged if _integer(charged) else None,
            "estimated_usd": currency if complete and not unknown_currency else None,
            "wall_seconds": result.get("elapsed_seconds"),
            "simulated_operation_cost": (result.get("diagnostic") or {}).get("cost")}


def _summarize(slots, indexed):
    counts = Counter()
    valid, costs = [], {key: [] for key in _cost_values({})}
    for slot in slots:
        result = indexed.get(slot["rollout_id"])
        if result is None:
            counts["missing"] += 1
            continue
        counts[result["status"]] += 1
        for key, value in _cost_values(result).items():
            costs[key].append(value)
        if result["status"] != "completed":
            continue
        valid.append(result)
        outcome = "successes" if result["success"] else "substantive_incomplete" if result["semantic_score"] < 1 else "protocol_incomplete"
        counts[outcome] += 1
        counts["failures"] += not result["success"]
        counts["budget_exhausted"] += result.get("budget_exhausted") is True
        counts["skill_loaded"] += result.get("skill_loaded") is True
        counts["skill_not_loaded"] += result.get("skill_loaded") is False
        counts["skill_load_unknown"] += type(result.get("skill_loaded")) is not bool
    names = ("completed", "missing", "infrastructure_invalid", "infrastructure_error", "successes", "failures",
             "substantive_incomplete", "protocol_incomplete", "budget_exhausted", "skill_loaded", "skill_not_loaded", "skill_load_unknown")
    return {"planned": len(slots), "received": len(slots) - counts["missing"],
            **{name: counts[name] for name in names},
            "strict_success_rate_completed": counts["successes"] / len(valid) if valid else None,
            "confirmed_success_fraction_planned": counts["successes"] / len(slots),
            "mean_semantic_score_completed": sum(row["semantic_score"] for row in valid) / len(valid) if valid else None,
            "costs": {key: _measure(values, len(slots)) for key, values in costs.items()}}


def aggregate_probes(probe_manifest, slots, results, *, same_skill):
    """Describe every planned native transfer slot without treating errors as failure.

    ``same_skill=True`` labels an A/A diagnostic (including non-adoption). Arms
    and repeat indices come only from the frozen slots, not from inferred native
    outcomes. ``complete`` requires all sixteen valid native receipts; the
    independent ``receipts_complete`` flag reports whether every slot has a row.
    """
    if type(same_skill) is not bool:
        raise ValueError("same_skill must be an explicit boolean from the frozen skill hashes")
    allowed, indexed = _design(probe_manifest, slots), {}
    for result in results:
        identifier = result.get("rollout_id")
        slot = allowed.get(identifier)
        if slot is None or identifier in indexed:
            raise ValueError("Unknown or duplicate transfer receipt identity")
        if any(result.get(key) != slot[key] for key in ("probe_index", "repeat_index", "arm")) or any(
                type(result.get(key)) is not int for key in ("probe_index", "repeat_index")):
            raise ValueError("Transfer receipt disagrees with its frozen probe, repeat or arm")
        status = result.get("status")
        if status not in ("completed", "infrastructure_invalid", "infrastructure_error"):
            raise ValueError("Unknown transfer receipt status")
        if status == "completed":
            if (result.get("infrastructure_valid") is not True or type(result.get("success")) is not bool
                    or not _number(result.get("semantic_score")) or not 0 <= result["semantic_score"] <= 1
                    or (result["success"] and result["semantic_score"] != 1)):
                raise ValueError("Completed transfer receipt lacks a valid strict/substantive outcome")
        elif result.get("infrastructure_valid") is True:
            raise ValueError("Invalid transfer infrastructure cannot carry a valid native receipt flag")
        indexed[identifier] = result
    total = _summarize(slots, indexed)
    arms = {arm: {**_summarize([slot for slot in slots if slot["arm"] == arm], indexed),
                  "regimes": {regime: _summarize([slot for slot in slots if slot["arm"] == arm and
                      probe_manifest["probes"][slot["probe_index"]]["regime"] == regime], indexed)
                              for regime in ("changed", "reversal")}}
            for arm in ("seed", "deployed")}
    by_cell = {(slot["probe_index"], slot["repeat_index"], slot["arm"]): slot for slot in slots}
    pairs, public_slots = [], []
    for probe_index in range(4):
        for repeat in range(2):
            arm_results = {arm: indexed.get(by_cell[(probe_index, repeat, arm)]["rollout_id"])
                           for arm in ("seed", "deployed")}
            both = all(result is not None and result["status"] == "completed" for result in arm_results.values())
            seed, deployed = arm_results["seed"], arm_results["deployed"]
            pairs.append({"probe_index": probe_index, "repeat_index": repeat,
                          "regime": probe_manifest["probes"][probe_index]["regime"], "evaluable": both,
                          "seed_success": seed["success"] if both else None,
                          "deployed_success": deployed["success"] if both else None,
                          "strict_disagreement": seed["success"] != deployed["success"] if both else None,
                          "semantic_delta_deployed_minus_seed": deployed["semantic_score"] - seed["semantic_score"] if both else None})
    evaluable = [row for row in pairs if row["evaluable"]]
    disagreements = sum(row["strict_disagreement"] for row in evaluable)
    for slot in slots:
        result = indexed.get(slot["rollout_id"])
        valid = result is not None and result["status"] == "completed"
        public_slots.append({**{key: slot[key] for key in ("rollout_id", "probe_index", "repeat_index", "arm")},
                             "status": result["status"] if result else "missing",
                             "success": result["success"] if valid else None,
                             "semantic_score": result["semantic_score"] if valid else None})
    return {"schema_version": 1, "analysis_version": VERSION, "probe_manifest_sha256": _hash(probe_manifest),
            "slots_sha256": _hash(slots), "same_skill": same_skill,
            "comparison_type": "A/A fixed-skill diagnostic" if same_skill else "frozen seed versus deployed skill transfer",
            "totals": total, "arms": arms, "slots": public_slots,
            "paired": {"planned_pairs": 8, "evaluable_pairs": len(evaluable), "unevaluable_pairs": 8 - len(evaluable),
                       "disagreeing_pairs": disagreements, "disagreement_rate": disagreements / len(evaluable) if evaluable else None,
                       "seed_only_success_pairs": sum(row["seed_success"] and not row["deployed_success"] for row in evaluable),
                       "deployed_only_success_pairs": sum(row["deployed_success"] and not row["seed_success"] for row in evaluable),
                       "mean_semantic_delta_deployed_minus_seed": sum(row["semantic_delta_deployed_minus_seed"] for row in evaluable) / len(evaluable) if evaluable else None,
                       "pairs": pairs, "confidence_interval": None},
            "receipts_complete": total["missing"] == 0, "complete": total["completed"] == 16,
            "accounting_complete": all(total["costs"][key]["complete"] for key in ("tokens", "physical_model_calls", "charged_tokens")),
            "interpretation": "Descriptive frozen-skill transfer and retention on four dependent development probes. "
                "No confidence intervals or continual-adaptation claim. Missing and infrastructure-invalid outcomes "
                "are unknown, not behavioral failures; the confirmed-success fraction is only a lower bound when "
                "coverage is incomplete. Reservation charges remain separate from measured model use. "
                "Per-arm and probe totals exclude historical actor generation and learning-phase compute; "
                "the outer campaign reports learning and combined compute in separate fields."}
