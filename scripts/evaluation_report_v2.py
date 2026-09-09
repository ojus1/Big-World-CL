#!/usr/bin/env python3
"""Versioned commitment/availability correction; never rewrites REPORT.json v1.

Task.created is availability, not order placement. This postprocessor joins the
accepted-order history/events to scheduled and materialized task state. It does
not change observations, rollouts, rewards, or the frozen evaluator implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VERSION = "commitment-report-v2.0"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _integer(value):
    return type(value) is int


def _summary(rows, horizon, observed_day):
    fulfilled = [row for row in rows if row["status"] == "completed" and _integer(row["completed_day"]) and row["completed_day"] < horizon]
    known_availability = [row for row in rows if _integer(row["available_day"])]
    actionable = [row for row in known_availability if row["available_day"] < horizon]
    deferred = [row for row in known_availability if row["available_day"] >= horizon]
    complete_observed = sum(row["status"] == "completed" for row in rows)
    missing_state = sum(row["status"] == "missing_task_evidence" for row in rows)
    return {
        "accepted_before_work_horizon": len(rows), "fulfilled_before_work_horizon": len(fulfilled),
        "fulfillment_rate": len(fulfilled) / len(rows) if rows and not missing_state else None,
        "fulfilled_at_observation": complete_observed,
        "unfulfilled_at_work_horizon": len(rows) - len(fulfilled),
        "unfulfilled_at_observation": len(rows) - complete_observed,
        "actionable_before_work_horizon": len(actionable),
        "available_but_unfinished_at_work_horizon": sum(not (row["status"] == "completed" and _integer(row["completed_day"]) and row["completed_day"] < horizon) for row in actionable),
        "awaiting_availability_at_work_horizon": len(deferred),
        "availability_unknown": len(rows) - len(known_availability),
        "pending_at_observation": sum(row["status"] in ("pending", "scheduled") for row in rows),
        "abandoned_at_observation": sum(row["status"] == "abandoned" for row in rows),
        "materialized_at_observation": sum(row["materialized"] for row in rows),
        "arrived_during_outcome_window": sum(row["materialized"] and horizon <= row["available_day"] <= observed_day for row in known_availability),
        "scheduled_not_materialized_at_observation": sum(not row["materialized"] and row["status"] == "scheduled" for row in rows),
        "settled_at_observation": sum(row["settled"] for row in rows),
        "right_censored_unfulfilled": sum(row["status"] in ("pending", "scheduled") for row in rows),
        "missing_task_evidence": missing_state,
    }


def build_report_v2(checkpoint, legacy_report, *, source_hashes=None):
    """Pure correction from trusted input dictionaries; raw-byte hashes optional.

    Initial commitments at day -1 are included. A scheduled task is not a second
    commitment: the identity is (firm, task_id), with materialized status taking
    precedence over the original immutable scheduled template.
    """
    eco, state = checkpoint["ecosystem"], checkpoint["runner"]
    horizon = legacy_report["config"]["days"]
    observed_day = eco["day"]
    if not _integer(horizon) or horizon < 1 or not _integer(observed_day):
        raise ValueError("Invalid work/observation horizon")
    if legacy_report["horizon"]["observed_world_day"] != observed_day:
        raise ValueError("Checkpoint and v1 report have different observation days")
    sessions = state["sessions"]
    if sum(row["day"] < horizon for row in sessions) != legacy_report["prospective"]["attempts"]:
        raise ValueError("Checkpoint and v1 report have different work-session counts")
    issues = []
    def issue(code, key=None):
        value = {"code": code}
        if key is not None:
            value.update(firm=key[0], task_id=key[1])
        if value not in issues:
            issues.append(value)
    events = {}
    for event in eco.get("events", []):
        if event["id"] in events:
            issue("duplicate_event_id")
        events[event["id"]] = event
    placements = {}
    for consumer, data in eco.get("consumers", {}).items():
        for history in data.get("history", []):
            if history.get("kind") != "ordered":
                continue
            key = (history["firm"], history["task_id"])
            value = {"placed_day": history["day"], "consumer": consumer}
            if key in placements:
                issue("duplicate_ordered_history", key)
                if placements[key] != value:
                    issue("inconsistent_ordered_history", key)
            else:
                placements[key] = value
    order_events = {}
    for event in events.values():
        if event.get("kind") != "order_placed":
            continue
        payload = event["payload"]
        key = (payload["firm"], payload["task_id"])
        if key in order_events:
            issue("duplicate_order_placement_event", key)
        order_events[key] = event
        value = {"placed_day": event["day"], "consumer": event["actor"]}
        if key not in placements:
            placements[key] = value
            issue("order_event_without_consumer_history", key)
        elif placements[key] != value or payload.get("requested") != event["day"]:
            issue("placement_history_event_disagreement", key)
    templates, materialized, ledgers = {}, {}, defaultdict(list)
    for firm, world in eco["worlds"].items():
        for template in world.get("scheduled", []):
            key = (firm, template["id"])
            if key in templates:
                issue("duplicate_scheduled_template", key)
            templates[key] = template
        tasks = world["tasks"].values() if isinstance(world["tasks"], dict) else world["tasks"]
        for task in tasks:
            key = (firm, task["id"])
            if key in materialized:
                issue("duplicate_materialized_task", key)
            materialized[key] = task
            if key in templates and any(task.get(field) != templates[key].get(field)
                                        for field in ("id", "workflow", "owner", "customer", "created", "due")):
                issue("scheduled_materialized_identity_disagreement", key)
        for row in world.get("ledger", []):
            ledgers[(firm, row["task_id"])].append(row)
    for key in set(templates) | set(materialized):
        if key not in placements:
            issue("task_without_accepted_order_provenance", key)
    successful = defaultdict(list)
    for session in sessions:
        firm = session["employee"].split("__", 1)[0]
        key = (firm, session["task_id"])
        if key not in placements:
            issue("session_without_accepted_order", key)
        if session.get("success") is True:
            successful[key].append(session)
    records, post_horizon = [], []
    for key, placement in sorted(placements.items()):
        firm, task_id = key
        placed = placement["placed_day"]
        if not _integer(placed) or placed < -1:
            issue("invalid_placement_day", key)
            continue
        event = order_events.get(key)
        if event is None:
            issue("consumer_history_without_order_event", key)
        source, nominal = "unknown", None
        causes = event.get("causes", []) if event else []
        parents = [events[cause] for cause in causes if cause in events]
        if len(parents) != len(causes):
            issue("missing_order_cause_event", key)
        benchmark = [parent for parent in parents if parent["kind"] == "benchmark_demand"]
        native = [parent for parent in parents if parent["kind"] == "consumer_decision"
                  and parent["actor"] == placement["consumer"] and parent["payload"].get("action") in ("purchase", "switch")]
        if event and placed == -1 and not causes:
            source, nominal = "initial", 0
        elif len(benchmark) == 1 and not native:
            source, nominal = "benchmark", benchmark[0]["payload"].get("for_day")
            if benchmark[0]["actor"] != "environment" or benchmark[0]["day"] != placed or not _integer(nominal) or nominal != placed + 1:
                issue("benchmark_source_time_or_actor_disagreement", key)
        elif len(native) == 1 and not benchmark:
            source = "native_consumer"
            if native[0]["day"] != placed or native[0]["payload"].get("firm") != firm:
                issue("native_source_time_or_firm_disagreement", key)
        else:
            issue("unknown_or_ambiguous_order_source", key)
        if _integer(nominal) and nominal < max(0, placed):
            issue("nominal_release_precedes_commitment", key)
        task = materialized.get(key, templates.get(key))
        if task is None:
            issue("accepted_order_missing_task_state", key)
            task = {}
        available = task.get("created")
        if not _integer(available) or available < 0:
            issue("missing_or_invalid_availability_day", key)
            available = None
        elif available < placed:
            issue("availability_precedes_order_placement", key)
        status = task.get("status", "missing_task_evidence") if key in materialized else "scheduled" if task else "missing_task_evidence"
        if key not in materialized and available is not None and available <= observed_day:
            issue("available_task_not_materialized_by_observation", key)
        if key in materialized and available is not None and available > observed_day:
            issue("materialized_task_from_future", key)
        done = task.get("completed") if key in materialized else None
        evidence = successful.get(key, [])
        owner = task.get("owner")
        employee = firm + "__" + owner if owner else None
        if status == "completed":
            if len(evidence) != 1 or not _integer(done) or any(
                    row.get("infrastructure_valid") is not True or row["day"] != done
                    or row["employee"] != employee or row.get("semantic_score") != 1 for row in evidence):
                issue("completion_evidence_disagreement", key)
            if len(ledgers[key]) != 1:
                issue("completion_ledger_count_disagreement", key)
        elif evidence or ledgers[key]:
            issue("unfulfilled_order_has_completion_or_ledger", key)
        if status == "completed" and _integer(done) and done >= horizon:
            issue("completion_outside_work_horizon", key)
        row = {"firm": firm, "task_id": task_id, "consumer": placement["consumer"],
               "employee": employee, "workflow": task.get("workflow"), "placed_day": placed,
               "nominal_release_day": nominal, "available_day": available, "due_day": task.get("due"),
               "source": source, "order_event_id": event["id"] if event else None,
               "source_event_ids": causes, "materialized": key in materialized,
               "status": status, "attempts": task.get("attempts", 0) if key in materialized else 0,
               "completed_day": done, "successful_session_ids": [item.get("id") for item in evidence],
               "settled": len(ledgers[key]) == 1 and ledgers[key][0].get("settled") is True}
        (records if placed < horizon else post_horizon).append(row)
    commitments = _summary(records, horizon, observed_day)
    actionable = [row for row in records if row["available_day"] is not None and row["available_day"] < horizon]
    old = legacy_report["obligations"]
    if len(actionable) != old["created_before_horizon"]:
        issue("v1_actionable_denominator_disagreement")
    if commitments["fulfilled_before_work_horizon"] != old["completed_before_horizon"]:
        issue("v1_completion_numerator_disagreement")
    if post_horizon:
        issue("orders_placed_during_outcome_only_window")
    missing = commitments["availability_unknown"]
    partition_ok = commitments["accepted_before_work_horizon"] == (
        commitments["fulfilled_before_work_horizon"] + commitments["available_but_unfinished_at_work_horizon"]
        + commitments["awaiting_availability_at_work_horizon"] + missing)
    if not partition_ok:
        issue("commitment_partition_does_not_reconcile")
    breakdown = {source: _summary([row for row in records if row["source"] == source], horizon, observed_day)
                 for source in ("initial", "benchmark", "native_consumer", "unknown")}
    breakdown["fixed_initial_and_benchmark"] = _summary([row for row in records if row["source"] in ("initial", "benchmark")], horizon, observed_day)
    derived_hashes = source_hashes or {"encoding": "canonical_json_inputs",
        "v1_report_sha256": _sha(_canonical(legacy_report)), "checkpoint_sha256": _sha(_canonical(checkpoint))}
    return {"metric_schema_version": 2, "report_version": VERSION,
            "algorithm": legacy_report.get("algorithm"), "status": legacy_report["status"],
            "source_hashes": deepcopy(derived_hashes), "config": deepcopy(legacy_report["config"]),
            "scenario": deepcopy(legacy_report["scenario"]), "provenance": deepcopy(legacy_report.get("provenance", {})),
            "horizon": deepcopy(legacy_report["horizon"]),
            "headline": {"metric": "pre_horizon_commitment_fulfillment_rate",
                "numerator": commitments["fulfilled_before_work_horizon"],
                "denominator": commitments["accepted_before_work_horizon"], "value": commitments["fulfillment_rate"]},
            "commitments": commitments,
            "actionable_work": {"definition": "Task.created is availability; this conditional execution denominator excludes commitments unavailable before the action horizon.",
                                "legacy_v1_metrics": deepcopy(old)},
            "source_breakdown": breakdown, "commitment_records": records,
            "post_horizon_commitment_records": post_horizon,
            "correction_audit": {"eligible_for_paired_inference": not issues and legacy_report.get("audit", {}).get("eligible_for_paired_inference") is True,
                                 "issues": issues, "commitment_partition_reconciles": partition_ok,
                                 "legacy_trial_audit_passed": legacy_report.get("audit", {}).get("eligible_for_paired_inference") is True},
            "legacy_actionable_report": deepcopy(legacy_report),
            "interpretation": "Canonical business headline counts all accepted pre-horizon commitments, including initial conditions and work delayed beyond the action horizon. Actionable-work completion is a separate conditional execution metric. Endogenous demand may differ by arm; fixed initial/benchmark fulfillment is reported separately. No rollout, reward, or v1 report was changed."}


def write_report_v2(directory):
    """Write a new version atomically and verify both source files stay identical."""
    directory = Path(directory)
    if (directory / "INFLIGHT.json").exists():
        raise ValueError("Cannot finalize v2 while an action needs reconciliation")
    original_path, checkpoint_path = directory / "REPORT.json", directory / "checkpoint.json"
    original, checkpoint = original_path.read_bytes(), checkpoint_path.read_bytes()
    legacy = json.loads(original)
    if legacy.get("status") != "completed":
        raise ValueError("Only completed runs can finalize REPORT.v2.json")
    value = build_report_v2(json.loads(checkpoint), legacy, source_hashes={
        "encoding": "raw_file_bytes", "v1_report_sha256": _sha(original),
        "checkpoint_sha256": _sha(checkpoint), "postprocessor_sha256": _sha(Path(__file__).read_bytes())})
    if not value["correction_audit"]["eligible_for_paired_inference"]:
        raise ValueError("Correction audit failed; retain v1 and reconcile the source evidence before finalizing v2: "
                         + json.dumps(value["correction_audit"], sort_keys=True))
    target = directory / "REPORT.v2.json"
    content = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if target.exists() and target.read_bytes() != content:
        raise ValueError("REPORT.v2.json already exists with different inputs or processor; preserve it and choose a new version")
    if original_path.read_bytes() != original or checkpoint_path.read_bytes() != checkpoint or (directory / "INFLIGHT.json").exists():
        raise RuntimeError("Input changed during correction; wait for the run to finish")
    if not target.exists():
        temporary = target.with_suffix(".json.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
    if original_path.read_bytes() != original:
        raise RuntimeError("Original REPORT.json changed unexpectedly")
    return value


def _equivalent(left, right):
    """Permit only tiny float summation differences; integers and booleans exact."""
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(_equivalent(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equivalent(a, b) for a, b in zip(left, right))
    if type(left) is float and type(right) is float:
        return math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=0, abs_tol=1e-12)
    return type(left) is type(right) and left == right


def validate_report_v2(report):
    if report.get("metric_schema_version") != 2 or report.get("report_version") != VERSION:
        raise ValueError("Comparison requires compatible REPORT.v2.json inputs")
    for field in ("v1_report_sha256", "checkpoint_sha256"):
        value = report.get("source_hashes", {}).get(field)
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("Corrected report has invalid source hashes")
    encoding = report["source_hashes"].get("encoding")
    if encoding not in ("raw_file_bytes", "canonical_json_inputs"):
        raise ValueError("Corrected report has unknown source-hash encoding")
    legacy = report["legacy_actionable_report"]
    for key in ("algorithm", "status", "config", "scenario", "provenance", "horizon"):
        if not _equivalent(report.get(key), legacy.get(key)):
            raise ValueError("Corrected report metadata differs from its legacy execution report")
    rows = report["commitment_records"]
    horizon, observed = report["config"]["days"], report["horizon"]["observed_world_day"]
    if len({(row["firm"], row["task_id"]) for row in rows}) != len(rows) or any(not _integer(row["placed_day"]) or not -1 <= row["placed_day"] < horizon for row in rows):
        raise ValueError("Corrected commitment identities or placement days are inconsistent")
    summary = _summary(rows, horizon, observed)
    headline = {"metric": "pre_horizon_commitment_fulfillment_rate", "numerator": summary["fulfilled_before_work_horizon"],
                "denominator": summary["accepted_before_work_horizon"], "value": summary["fulfillment_rate"]}
    if not _equivalent(summary, report["commitments"]) or not _equivalent(headline, report["headline"]):
        raise ValueError("Corrected headline or commitments do not reconcile to the records")
    if set(report["source_breakdown"]) != {"initial", "benchmark", "native_consumer", "unknown", "fixed_initial_and_benchmark"}:
        raise ValueError("Corrected source breakdown is incomplete")
    for source, metrics in report["source_breakdown"].items():
        selected = [row for row in rows if row["source"] in ("initial", "benchmark")] if source == "fixed_initial_and_benchmark" else [row for row in rows if row["source"] == source]
        if not _equivalent(_summary(selected, horizon, observed), metrics):
            raise ValueError("Corrected source breakdown does not reconcile to the records")
    audit = report["correction_audit"]
    if audit.get("eligible_for_paired_inference") is not (not audit.get("issues") and legacy.get("audit", {}).get("eligible_for_paired_inference") is True):
        raise ValueError("Corrected audit eligibility is inconsistent with its evidence")
    if report["source_hashes"].get("encoding") == "canonical_json_inputs" and _sha(_canonical(report["legacy_actionable_report"])) != report["source_hashes"]["v1_report_sha256"]:
        raise ValueError("Canonical legacy report hash disagrees")


def load_verified_report_v2(path):
    """Verify raw local source bytes and regenerate the correction for CLI use.

    This checks report integrity, not native execution; strict directory auditing
    with scripts/audit_evaluation.py is a separate required step.
    """
    path = Path(path)
    value = json.loads(path.read_bytes())
    validate_report_v2(value)
    if value["source_hashes"].get("encoding") != "raw_file_bytes":
        raise ValueError("CLI comparison requires raw-file reports, not fabricated pure-function fixtures")
    if value["source_hashes"].get("postprocessor_sha256") != _sha(Path(__file__).read_bytes()):
        raise ValueError("Recorded postprocessor does not match current script bytes; use the matching historical processor")
    legacy = (path.parent / "REPORT.json").read_bytes()
    checkpoint = (path.parent / "checkpoint.json").read_bytes()
    if _sha(legacy) != value["source_hashes"]["v1_report_sha256"] or _sha(checkpoint) != value["source_hashes"]["checkpoint_sha256"]:
        raise ValueError("Raw checkpoint/report hash differs from corrected report")
    regenerated = build_report_v2(json.loads(checkpoint), json.loads(legacy), source_hashes=value["source_hashes"])
    if not _equivalent(regenerated, value):
        raise ValueError("Corrected report does not regenerate from its recorded source files")
    return value


def compare_reports_v2(reports):
    """Reuse frozen world-pair audit/bootstrap with corrected headline values."""
    from lifespan.evaluation.metrics import paired_report
    for report in reports:
        validate_report_v2(report)
    if len({report["source_hashes"]["encoding"] for report in reports}) > 1:
        raise ValueError("Do not mix raw-file execution reports with canonical fixture reports")
    processors = {report["source_hashes"].get("postprocessor_sha256") for report in reports if report["source_hashes"].get("encoding") == "raw_file_bytes"}
    if len(processors) > 1 or any(not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in processors):
        raise ValueError("Raw-byte corrected reports must use the same pinned postprocessor implementation")
    legacy = [report["legacy_actionable_report"] for report in reports]
    def project(source):
        projected = []
        for corrected in reports:
            report = deepcopy(corrected["legacy_actionable_report"])
            metric = corrected["commitments"] if source == "all" else corrected["source_breakdown"]["fixed_initial_and_benchmark"]
            report["obligations"]["success_rate"] = metric["fulfillment_rate"]
            if corrected["correction_audit"]["eligible_for_paired_inference"] is not True:
                report["audit"]["eligible_for_paired_inference"] = False
                report["audit"]["issues"] += ["commitment_v2_correction_audit_failed"]
            projected.append(report)
        return paired_report(projected)
    result = project("all")
    fixed = project("fixed")
    result["metric_summaries"]["commitment_fulfillment_rate"] = result["metric_summaries"].pop("obligation_success_rate")
    result["metric_summaries"]["fixed_demand_fulfillment_rate"] = fixed["metric_summaries"]["obligation_success_rate"]
    for index, pair in enumerate(result["eligible_pairs"]):
        pair["deltas"]["commitment_fulfillment_rate"] = pair["deltas"].pop("obligation_success_rate")
        pair["deltas"]["fixed_demand_fulfillment_rate"] = fixed["eligible_pairs"][index]["deltas"]["obligation_success_rate"]
    result.update(metric_schema_version=2, report_version=VERSION,
                  canonical_headline="commitment_fulfillment_rate",
                  legacy_actionable_comparison=paired_report(legacy),
                  source_reports=[{"algorithm": report["algorithm"], "source_hashes": report["source_hashes"],
                                   "headline": report["headline"], "source_breakdown": report["source_breakdown"]} for report in reports])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path, help="Completed run directories containing REPORT.json and checkpoint.json")
    args = parser.parse_args()
    for directory in args.directories:
        report = write_report_v2(directory)
        print(json.dumps({"output": str(directory / "REPORT.v2.json"), "headline": report["headline"],
                          "correction_audit": report["correction_audit"]}, allow_nan=False))


if __name__ == "__main__":
    main()
