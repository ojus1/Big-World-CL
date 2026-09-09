"""Pure development-only transfer probes, never a causal world benchmark.

Only the returned public manifest may leave the evaluator. Capsules contain
trusted simulator state and private rubric answers. This module makes no model
calls, actor decisions, file writes, or skill changes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.tasks import make_case
from lifespan.world import Task


VERSION = "fixed-environment-transfer-probes-v1"
REGIMES = ("changed", "changed", "reversal", "reversal")
LABEL = "Synthetic fixed-environment transfer probes; development diagnostics, not a causal world benchmark."
_OBJECTIVE_FIELDS = ("id", "name", "objective", "price", "target_market", "priority_workflow",
                     "route", "daily_capacity", "strategy_revision", "public_announcements")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _identities(checkpoint):
    identities = set()
    for world in checkpoint["ecosystem"]["worlds"].values():
        identities.update(world["tasks"])
        identities.update(task["id"] for task in world["scheduled"])
    for row in checkpoint.get("runner", {}).get("sessions", []):
        identities.update(row[key] for key in ("id", "task_id", "case_id") if row.get(key))
    for row in checkpoint.get("runner", {}).get("experiences", []):
        identities.update(row[key] for key in ("id", "source_session") if row.get(key))
    return identities


def build_transfer_probes(source_checkpoint, employee, *, cutoff_day=9, seed=20260910):
    """Return four independent private replay capsules after an observed cutoff.

    ``source_checkpoint`` is a parsed full checkpoint with an ``ecosystem`` key.
    Its canonical JSON hash binds all supplied source data; a caller loading a
    file should additionally pin the raw file hash in its experiment manifest.
    Selection of the employee and learning cutoffs belongs to the caller. The
    generator never inspects outcomes or picks a skill, training set, or employee.
    The caller must withhold these probes from both optimizer training and
    validation. ``split='validation'`` selects development task mechanisms; it
    does not assign the probes to an optimizer experience pool.

    Each clone advances inherited schedules and expiry independently, without
    new MiroFish decisions. The work specification deliberately reintroduces v2
    for two fresh tasks, then restores v1 for two more. These controlled task
    policies do not assert that the source world's actors chose these changes.
    """
    if type(cutoff_day) is not int or cutoff_day < 0 or type(seed) is not int or seed < 0:
        raise ValueError("cutoff_day and seed must be nonnegative integers")
    if not isinstance(source_checkpoint, dict) or "ecosystem" not in source_checkpoint:
        raise ValueError("A parsed full source checkpoint with ecosystem state is required")
    source = source_checkpoint["ecosystem"]
    if type(source.get("day")) is not int or not -1 <= source["day"] <= cutoff_day:
        raise ValueError("Source observation must be on or before the learning cutoff")
    eco = Ecosystem.restore(source)
    roster = {firm + "__" + local: (firm, local) for firm, world in eco.worlds.items()
              for local in world.employees}
    if not isinstance(employee, str) or employee not in roster:
        raise ValueError("Employee must identify a member of the source checkpoint roster")
    if any(world.day != eco.day for world in eco.worlds.values()):
        raise ValueError("Source employee worlds and ecosystem must share the observation day")
    firm, local = roster[employee]
    worker = eco.worlds[firm].employees[local]
    source_hash, used = _digest(source_checkpoint), _identities(source_checkpoint)
    namespace = _digest([VERSION, employee, cutoff_day, seed])[:24]
    probes = []
    for index, regime in enumerate(REGIMES):
        day = cutoff_day + index + 1
        task_id = f"transfer-{namespace}-{index}"
        if task_id in used:
            raise ValueError("A generated transfer identity already occurs in the source; use a fresh seed")
        used.add(task_id)
        branch = Ecosystem.restore(source)
        branch.days = max(branch.days, day + 1)
        while branch.day < day:
            branch.advance()
        world = branch.worlds[firm]
        task = Task(id=task_id, workflow=worker.workflow, segment=worker.segment,
                    owner=local, customer="synthetic-transfer-customer-" + namespace[:12],
                    created=day, due=day + 3, value=0.0)
        world.tasks[task_id] = task
        # A direct evaluator insertion is not a consumer order or actor decision.
        case = make_case(worker.workflow, seed, day, task_id, regime, "validation")
        objectives = {key: deepcopy(branch.firms[firm][key]) for key in _OBJECTIVE_FIELDS
                      if key in branch.firms[firm]}
        documents = [rule.public() for rule in world.documents(world.employees[local])]
        request = (f"Please handle the new {worker.workflow} task {task_id} for "
                   f"{task.customer}, a {task.segment} account, on day {day}; it is due on day {task.due}. "
                   "Read the current company objectives in /workspace/company/objectives.json "
                   "and published submission procedures in /workspace/company/procedures.json. "
                   "The task's published specification states the requirements for this work.\n\n"
                   + case["request"])
        state = branch.checkpoint()
        metadata = {"generator_version": VERSION, "label": LABEL, "probe_index": index,
                    "employee": employee, "workflow": worker.workflow, "segment": worker.segment,
                    "task_id": task_id, "day": day, "regime": regime, "split": "validation",
                    "cutoff_day": cutoff_day, "seed": seed, "source_observed_day": source["day"],
                    "source_checkpoint_sha256": source_hash, "source_hash_encoding": "canonical_json",
                    "source_horizon_days": source["days"], "clone_horizon_days": branch.days,
                    "case_sha256": _digest(case), "task_sha256": _digest(asdict(task)),
                    "ecosystem_sha256": _digest(state), "request_sha256": _digest(request),
                    "public_files_sha256": _digest(case["public_files"]),
                    "public_procedures_sha256": _digest(documents), "objectives_sha256": _digest(objectives),
                    "new_institutional_decisions": 0, "synthetic_task_business_value": 0.0}
        probes.append({"ecosystem": state, "case": case, "request": request,
                       "employee": employee, "firm": firm, "task_id": task_id,
                       "objectives": objectives, "business_files": None,
                       "public_company_procedures": documents, "probe": metadata})
    return probes


def public_probe_manifest(probes):
    """Validate capsule bindings and expose metadata/hashes, never case content.

    This manifest is evaluator-facing and must be frozen before learning. Future
    probe identities, dates and policy sequence are not employee observations.
    """
    if not isinstance(probes, list) or len(probes) != 4:
        raise ValueError("The transfer protocol requires exactly four private capsules")
    records, common = [], None
    ids = set()
    for index, capsule in enumerate(probes):
        meta, case = capsule["probe"], capsule["case"]
        identity = (meta["source_checkpoint_sha256"], meta["employee"], meta["cutoff_day"], meta["seed"])
        if common is None:
            common = identity
        if identity != common or meta.get("generator_version") != VERSION:
            raise ValueError("Transfer capsules must share source, employee, cutoff, seed and generator version")
        firm, task_id = capsule["firm"], capsule["task_id"]
        state = capsule["ecosystem"]
        task = state["worlds"][firm]["tasks"][task_id]
        if (task_id in ids or meta["probe_index"] != index or meta["day"] != meta["cutoff_day"] + index + 1
                or meta["regime"] != REGIMES[index] or meta["split"] != "validation"
                or meta["employee"] != capsule["employee"] or meta["task_id"] != task_id
                or any(case.get(key) != meta[key] for key in ("workflow", "day", "regime", "split"))
                or case["id"] != task_id or task["id"] != task_id
                or firm + "__" + task["owner"] != capsule["employee"]
                or task["workflow"] != meta["workflow"] or task["segment"] != meta["segment"]
                or task["status"] != "pending" or task["attempts"] != 0 or task["completed"] is not None
                or task["created"] != meta["day"] or state["day"] != meta["day"]
                or state["worlds"][firm]["day"] != meta["day"] or capsule["business_files"] is not None):
            raise ValueError("Transfer capsule scope, timeline or new pending task identity disagrees")
        bindings = {"case_sha256": case, "task_sha256": task, "ecosystem_sha256": state,
                    "request_sha256": capsule["request"], "public_files_sha256": case["public_files"],
                    "public_procedures_sha256": capsule["public_company_procedures"],
                    "objectives_sha256": capsule["objectives"]}
        if any(meta.get(key) != _digest(value) for key, value in bindings.items()):
            raise ValueError("Transfer capsule no longer matches its frozen content hashes")
        ids.add(task_id)
        # Explicit allowlist: adding private metadata cannot silently publish it.
        fields = ("probe_index", "employee", "workflow", "segment", "task_id", "day", "regime", "split",
                  "source_observed_day", "source_horizon_days", "clone_horizon_days", *bindings.keys())
        records.append({**{key: deepcopy(meta[key]) for key in fields}, "capsule_sha256": _digest(capsule)})
    return {"schema_version": 1, "generator_version": VERSION, "label": LABEL,
            "source_checkpoint_sha256": common[0], "source_hash_encoding": "canonical_json",
            "employee": common[1], "cutoff_day": common[2], "seed": common[3],
            "probe_count": len(records), "probes": records,
            "new_institutional_decisions": 0, "final_test_namespace_used": False,
            "evaluation_role": "post_learning_frozen_skill_transfer_and_retention",
            "optimizer_exposure": "withheld_from_both_training_and_validation",
            "interpretation": "Fixed inherited schedules advance independently; no new MiroFish decisions. "
                "Four fresh development tasks test frozen-skill transfer and retention, not continual "
                "adaptation during probe execution. They are dependent diagnostic exposures, not independent worlds.",
            "visibility": "Evaluator manifest only. Withhold all future probes from learning and reveal "
                "each task's public inputs only in its own replay; private rubric truth never enters the worker."}
