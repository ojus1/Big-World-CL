#!/usr/bin/env python3
"""Outcome-blind historical replay selection and descriptive repeat aggregation.

This module makes no model or network calls. Private capsules are inputs only;
the output bank exposes hashes and identifiers, never files, requests, or rubric
answers. Native execution and its preregistered budgets belong to the caller.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGIMES = ("base", "changed", "exception", "reversal")
VERSION = "outcome-blind-replay-bank-v1"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,239}\Z")


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _integer(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _employees(checkpoint):
    result = {}
    for firm, world in checkpoint["ecosystem"]["worlds"].items():
        values = world["employees"].values() if isinstance(world["employees"], dict) else world["employees"]
        for employee in values:
            identifier = firm + "__" + employee["id"]
            result[identifier] = {"firm": firm, "local_id": employee["id"], "workflow": employee["workflow"]}
    if not result:
        raise ValueError("Source has no employee roster")
    return result


def _verify_source(checkpoint, manifest, report):
    config = manifest["config"]
    if config.get("algorithm") != "no_learning" or config.get("split") != "dev" or config.get("state_mode") != "skill_transfer":
        raise ValueError("Calibration source must be a no_learning/dev/skill_transfer run; final test cases are forbidden")
    if report.get("status") != "completed" or report.get("audit", {}).get("eligible_for_paired_inference") is not True:
        raise ValueError("Source report must be completed and pass its execution audit")
    if report.get("config") != config or report.get("scenario") != manifest.get("scenario"):
        raise ValueError("Source manifest and report configuration/scenario disagree")
    provenance = report.get("provenance", {})
    for field in ("target_model", "model_base_url", "source_sha256", "dependencies"):
        if not manifest.get(field) or provenance.get(field) != manifest[field]:
            raise ValueError("Source execution provenance is missing or inconsistent: " + field)
    if not provenance.get("persona_cohort_sha256"):
        raise ValueError("Source population provenance is missing")
    if report["horizon"]["observed_world_day"] != checkpoint["ecosystem"]["day"]:
        raise ValueError("Source checkpoint/report observation day disagrees")
    sessions = checkpoint["runner"]["sessions"]
    if len(sessions) != report["prospective"]["attempts"]:
        raise ValueError("Source checkpoint/report session count disagrees")
    return config


def _select_source_rows(checkpoint, manifest, report):
    """Selection reads identity/scope/time only; no success/score/budget fields."""
    from lifespan.evaluation.protocol import regime_at
    config = _verify_source(checkpoint, manifest, report)
    employees = _employees(checkpoint)
    rows = checkpoint["runner"]["sessions"]
    seen = set()
    for row in rows:
        identifier = row.get("id")
        if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier) or identifier in seen:
            raise ValueError("Source session IDs must be unique safe path components")
        seen.add(identifier)
        if row.get("employee") not in employees or not _integer(row.get("day")) or row["day"] >= config["days"]:
            raise ValueError("Source session is outside the employee/work-horizon scope")
        if row.get("regime") not in REGIMES or row["regime"] != regime_at(manifest["scenario"], row["day"]):
            raise ValueError("Source session regime disagrees with its historical day")
        if not isinstance(row.get("task_id"), str) or not _SAFE_ID.fullmatch(row["task_id"]):
            raise ValueError("Source task identifier is invalid")
    chosen = {}
    for row in sorted(rows, key=lambda value: (value["day"], value["id"])):
        chosen.setdefault((row["employee"], row["regime"]), row)
    return employees, chosen


def select_bank(checkpoint, source_manifest, capsules_by_session, source_report, *,
                source_hashes=None, repeats=2):
    """Select the earliest released session per employee/regime, then annotate.

    Do not prefilter by skill loading, original success, semantic score, or budget
    exhaustion. Missing cells remain missing; malformed selected evidence raises
    rather than replacing the selected task with a more convenient later one.
    """
    if type(repeats) is not int or repeats != 2:
        raise ValueError("This calibration protocol preregisters exactly two repeats per selected capsule")
    employees, chosen = _select_source_rows(checkpoint, source_manifest, source_report)
    # Selection is now complete. Original outcomes may be attached below only.
    selected, missing = [], []
    for employee in sorted(employees):
        identity = employees[employee]
        for regime in REGIMES:
            row = chosen.get((employee, regime))
            if row is None:
                missing.append({"employee": employee, "regime": regime,
                                "reason": "no_released_source_session_in_this_cell"})
                continue
            identifier = row["id"]
            if identifier not in capsules_by_session:
                raise ValueError("First selected source capsule is missing; do not substitute a later session: " + identifier)
            capsule = capsules_by_session[identifier]
            case = capsule["case"]
            if (capsule.get("employee") != employee or capsule.get("firm") != identity["firm"]
                    or capsule.get("task_id") != row["task_id"] or case.get("id") != row["task_id"]
                    or row.get("case_id", row["task_id"]) != case.get("id")):
                raise ValueError("Selected capsule crosses employee or task boundaries")
            if (case.get("day") != row["day"] or case.get("regime") != regime
                    or capsule.get("ecosystem", {}).get("day") != row["day"]):
                raise ValueError("Selected capsule does not describe the historical session state")
            if case.get("split") != "online" or case.get("workflow") != identity["workflow"]:
                raise ValueError("Selected capsule has a forbidden split or different employee workflow")
            original_tasks = capsule["ecosystem"]["worlds"][identity["firm"]]["tasks"]
            task = original_tasks.get(row["task_id"]) if isinstance(original_tasks, dict) else next((task for task in original_tasks if task["id"] == row["task_id"]), None)
            if not task or task.get("owner") != identity["local_id"] or task.get("status") != "pending":
                raise ValueError("Historical replay must start from that employee's pending obligation")
            hashes = (source_hashes or {}).get("capsule_file_sha256", {})
            selected.append({"selection_id": identifier, "source_session_id": identifier,
                "source_case_path": "private/cases/" + identifier + ".json",
                "employee": employee, "workflow": identity["workflow"], "regime": regime,
                "source_day": row["day"], "source_task_id": row["task_id"], "case_split": case["split"],
                "case_sha256": _sha(_json_bytes(case)),
                "capsule_sha256": hashes.get(identifier, _sha(_json_bytes(capsule))),
                "capsule_hash_encoding": "raw_file_bytes" if identifier in hashes else "canonical_json",
                "original_outcome": {key: deepcopy(row.get(key)) for key in
                    ("success", "semantic_score", "budget_exhausted", "skill_loaded", "infrastructure_valid")},
                "original_outcome_usage": "Attached after the outcome-blind selection; never a selection criterion."})
    groups = defaultdict(list)
    for row in selected:
        groups[(row["employee"], row["source_task_id"])].append(row)
    duplicate_groups = [{"employee": key[0], "source_task_id": key[1],
                         "selection_ids": [row["selection_id"] for row in rows],
                         "regimes": [row["regime"] for row in rows]}
                        for key, rows in sorted(groups.items()) if len(rows) > 1]
    hashes = source_hashes or {"encoding": "canonical_json_inputs",
        "checkpoint_sha256": _sha(_json_bytes(checkpoint)), "manifest_sha256": _sha(_json_bytes(source_manifest)),
        "report_sha256": _sha(_json_bytes(source_report))}
    return {"schema_version": 1, "bank_version": VERSION, "repeats_per_selection": repeats,
            "selection_rule": "First session by (day, source session id) in each employee/regime cell; selection is outcome-blind.",
            "source": {"hashes": {key: deepcopy(value) for key, value in hashes.items() if key != "capsule_file_sha256"},
                       "config": deepcopy(source_manifest["config"]), "scenario": deepcopy(source_manifest["scenario"]),
                       "target_model": source_manifest["target_model"],
                       "provenance_sha256": _sha(_json_bytes(source_report["provenance"]))},
            "expected_cell_count": len(employees) * len(REGIMES), "selected_cell_count": len(selected),
            "expected_rollout_count": len(selected) * repeats, "missing_cells": missing,
            "selections": selected,
            "dependence": {"underlying_obligation_count": len(groups),
                           "repeated_obligation_groups": duplicate_groups,
                           "warning": "Employee/regime cells and repeats are not independent tasks or world samples; no confidence interval is justified from treating them as independent."},
            "public_summary_boundary": "Only identifiers, provenance hashes, scope metadata and post-selection source outcomes are public. Private capsule state, requests, files and expected work outputs are excluded."}


def build_bank(source_run, *, repeats=2):
    source_run = Path(source_run)
    if (source_run / "INFLIGHT.json").exists():
        raise ValueError("Source run has an unresolved in-flight action")
    raw = {name: (source_run / name).read_bytes() for name in ("checkpoint.json", "manifest.json", "REPORT.json")}
    checkpoint, manifest, report = (json.loads(raw[name]) for name in ("checkpoint.json", "manifest.json", "REPORT.json"))
    _, chosen = _select_source_rows(checkpoint, manifest, report)
    capsules, capsule_hashes = {}, {}
    for row in chosen.values():
        data = (source_run / "private/cases" / (row["id"] + ".json")).read_bytes()
        capsules[row["id"]] = json.loads(data)
        capsule_hashes[row["id"]] = _sha(data)
    hashes = {"encoding": "raw_file_bytes", "checkpoint_sha256": _sha(raw["checkpoint.json"]),
              "manifest_sha256": _sha(raw["manifest.json"]), "report_sha256": _sha(raw["REPORT.json"]),
              "selector_sha256": _sha(Path(__file__).read_bytes()), "capsule_file_sha256": capsule_hashes}
    bank = select_bank(checkpoint, manifest, capsules, report, source_hashes=hashes, repeats=repeats)
    if any((source_run / name).read_bytes() != data for name, data in raw.items()):
        raise RuntimeError("Source changed while selecting calibration cases")
    return bank


def expected_slots(bank):
    if bank.get("bank_version") != VERSION or bank.get("repeats_per_selection") != 2:
        raise ValueError("Incompatible calibration bank version/repeat contract")
    identifiers = [row["selection_id"] for row in bank["selections"]]
    if len(set(identifiers)) != len(identifiers) or any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in identifiers):
        raise ValueError("Calibration selection IDs must be unique and safe")
    cells = [(row["employee"], row["regime"]) for row in bank["selections"]]
    if len(set(cells)) != len(cells) or any(regime not in REGIMES for _, regime in cells):
        raise ValueError("Calibration employee/regime cells must be unique and recognized")
    if (bank.get("selected_cell_count") != len(identifiers)
            or bank.get("expected_rollout_count") != 2 * len(identifiers)
            or bank.get("expected_cell_count") != len(identifiers) + len(bank.get("missing_cells", []))):
        raise ValueError("Calibration coverage or rollout counts are inconsistent")
    return [{"selection_id": identifier, "repeat_index": index, "rollout_id": identifier + "-r" + str(index)}
            for identifier in identifiers for index in range(bank["repeats_per_selection"])]


def _tokens(usage):
    if _integer(usage.get("total_tokens")):
        return usage["total_tokens"]
    prompt, completion = usage.get("prompt_tokens", usage.get("input_tokens")), usage.get("completion_tokens", usage.get("output_tokens"))
    return prompt + completion if _integer(prompt) and _integer(completion) else None


def _cost(values, expected):
    known = [value for value in values if _number(value) and value >= 0]
    complete = len(known) == expected
    return {"total": sum(known) if complete else None, "recorded_total": sum(known),
            "measured_receipts": len(known), "missing_or_unknown_slots": expected - len(known), "complete": complete}


def aggregate_repeats(bank, results):
    """Describe every preregistered slot, retaining errors and missing receipts."""
    slots = expected_slots(bank)
    allowed = {(row["selection_id"], row["repeat_index"]): row for row in slots}
    indexed = {}
    for result in results:
        key = (result.get("selection_id"), result.get("repeat_index"))
        if type(result.get("repeat_index")) is not int or key not in allowed:
            raise ValueError("Receipt refers to an unknown calibration slot")
        if key in indexed:
            raise ValueError("Duplicate calibration receipt; reconcile it instead of counting twice")
        if result.get("rollout_id", allowed[key]["rollout_id"]) != allowed[key]["rollout_id"]:
            raise ValueError("Receipt rollout ID disagrees with its preregistered slot")
        status = result.get("status")
        if status not in ("completed", "infrastructure_invalid", "infrastructure_error"):
            raise ValueError("Unrecognized calibration receipt status")
        if status == "completed":
            if (result.get("infrastructure_valid") is not True or type(result.get("success")) is not bool
                    or not _number(result.get("semantic_score")) or not 0 <= result["semantic_score"] <= 1
                    or (result["success"] and result["semantic_score"] != 1)):
                raise ValueError("Completed receipt lacks a valid strict/substantive execution outcome")
        elif result.get("infrastructure_valid") is True:
            raise ValueError("Infrastructure status disagrees with valid-execution flag")
        for field in ("artifact_path", "artifact_relative_path"):
            if result.get(field):
                path = PurePosixPath(result[field])
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Receipt artifact reference must stay relative to calibration output")
        indexed[key] = result
    counts = Counter()
    cells, valid, usd, tokens, calls, charged, elapsed, costs = [], [], [], [], [], [], [], []
    for selection in bank["selections"]:
        repeats = []
        for repeat_index in range(bank["repeats_per_selection"]):
            key = (selection["selection_id"], repeat_index)
            result = indexed.get(key)
            if result is None:
                counts["missing"] += 1
                repeats.append({**allowed[key], "status": "missing", "outcome": "unknown"})
                continue
            status = result["status"]
            counts[status] += 1
            outcome = status
            if status == "completed":
                valid.append(result)
                outcome = "strict_success" if result["success"] else "substantive_incomplete" if result["semantic_score"] < 1 else "protocol_incomplete"
                counts[outcome] += 1
                counts["budget_exhausted"] += result.get("budget_exhausted") is True
                counts["skill_loaded"] += result.get("skill_loaded") is True
                counts["skill_not_loaded"] += result.get("skill_loaded") is False
                counts["skill_load_unknown"] += type(result.get("skill_loaded")) is not bool
            usage = result.get("usage") or {}
            actual = _tokens(usage) if usage.get("complete", True) is True else None
            tokens.append(actual)
            calls.append(next((usage[field] for field in ("api_calls", "physical_model_calls", "model_calls") if _integer(usage.get(field))), None))
            charged.append(usage.get("charged_tokens", actual))
            unknown_cost = str(usage.get("cost_status", "")).lower() in ("unknown", "missing", "unavailable", "incomplete")
            usd.append(None if unknown_cost or usage.get("complete", True) is not True else usage.get("estimated_cost_usd", usage.get("cost_usd")))
            elapsed.append(result.get("elapsed_seconds"))
            costs.append((result.get("diagnostic") or {}).get("cost"))
            repeats.append({**allowed[key], "status": status, "outcome": outcome,
                "success": result.get("success") if status == "completed" else None,
                "semantic_score": result.get("semantic_score") if status == "completed" else None,
                "budget_exhausted": result.get("budget_exhausted"), "skill_loaded": result.get("skill_loaded")})
        both = all(row["status"] == "completed" for row in repeats)
        cells.append({"selection_id": selection["selection_id"], "employee": selection["employee"],
            "regime": selection["regime"], "source_task_id": selection["source_task_id"], "repeats": repeats,
            "evaluable_repeat_pair": both,
            "strict_success_disagreement": repeats[0]["success"] != repeats[1]["success"] if both else None,
            "semantic_score_absolute_difference": abs(repeats[0]["semantic_score"] - repeats[1]["semantic_score"]) if both else None})
    evaluable = [cell for cell in cells if cell["evaluable_repeat_pair"]]
    disagreed = sum(cell["strict_success_disagreement"] for cell in evaluable)
    scores = [row["semantic_score"] for row in valid]
    total = len(slots)
    count_names = ("completed", "infrastructure_invalid", "infrastructure_error", "missing", "strict_success",
                   "substantive_incomplete", "protocol_incomplete", "budget_exhausted", "skill_loaded", "skill_not_loaded", "skill_load_unknown")
    return {"schema_version": 1, "bank_version": VERSION, "bank_sha256": _sha(_json_bytes(bank)),
            "expected_slots": total, "received_receipts": len(indexed), "counts": {name: counts[name] for name in count_names},
            "coverage": {"expected_employee_regime_cells": bank["expected_cell_count"],
                         "selected_cells": len(cells), "missing_source_cells": deepcopy(bank["missing_cells"]),
                         "underlying_obligation_count": bank["dependence"]["underlying_obligation_count"],
                         "repeated_obligation_groups": deepcopy(bank["dependence"]["repeated_obligation_groups"])},
            "outcomes": {"strict_success_rate_completed_receipts": counts["strict_success"] / len(valid) if valid else None,
                         "confirmed_success_fraction_all_planned_slots": counts["strict_success"] / total if total else None,
                         "mean_semantic_score_completed_receipts": sum(scores) / len(scores) if scores else None,
                         "planned_slot_fraction_note": "With missing/invalid execution, this is a confirmed-success lower bound; missing results are not asserted behavioral failures.",
                         "failure_categories": "Substantive incomplete means score below1; protocol incomplete means score1 without strict commit. Budget exhaustion overlaps either category."},
            "repeat_stability": {"evaluable_case_pairs": len(evaluable), "unevaluable_case_pairs": len(cells) - len(evaluable),
                                 "disagreeing_case_pairs": disagreed, "strict_success_disagreement_rate": disagreed / len(evaluable) if evaluable else None,
                                 "mean_absolute_semantic_difference": sum(cell["semantic_score_absolute_difference"] for cell in evaluable) / len(evaluable) if evaluable else None,
                                 "confidence_interval": None,
                                 "interpretation": "Descriptive within-capsule repeat variation under a fixed skill; dependent employee/regime cells and repeated underlying obligations do not supply independent population samples."},
            "costs": {"tokens": _cost(tokens, total), "charged_tokens": _cost(charged, total),
                      "model_calls": _cost(calls, total), "estimated_usd": _cost(usd, total),
                      "wall_seconds": _cost(elapsed, total), "simulated_operation_cost": _cost(costs, total),
                      "scope": "Replay receipts only; missing/unknown slots do not become measured zeros. Historical actor generation and source-run compute are excluded."},
            "cells": cells,
            "complete": counts["missing"] == 0,
            "all_native_receipts_valid": len(valid) == total and total > 0,
            "accounting_complete": _cost(tokens, total)["complete"] and _cost(calls, total)["complete"],
            "inference": "Calibration describes fixed-skill native repeatability and failure modes. It does not estimate deployment-time learning gains and reports no confidence interval across dependent cells."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    bank = build_bank(args.source_run)
    content = json.dumps(bank, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out.exists() and args.out.read_text() != content:
        raise SystemExit("Existing calibration bank differs; preserve it and use a new preregistration")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(content)
    print(json.dumps({"out": str(args.out), "selected_cells": bank["selected_cell_count"],
                      "expected_rollouts": bank["expected_rollout_count"], "missing_cells": bank["missing_cells"]}))


if __name__ == "__main__":
    main()
