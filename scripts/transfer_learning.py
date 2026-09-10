#!/usr/bin/env python3
"""One bounded historical SkillOpt epoch; future transfer probes stay external.

This script reuses the native evaluation runner and pinned upstream optimizer.
It does not advance the source world, select employees/cases, or evaluate any
future task. Injected executors are for offline integration tests only.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.protocol import ExperimentConfig, SEED_SKILL, digest, experience_split
from lifespan.evaluation.runner import _learn, credentials, dependency_provenance, source_hashes
from lifespan.evaluation.hermes_transport import mode, manifest_fields
from lifespan.evaluation.runtime import execute_case
from lifespan.mirofish import save
from scripts.audit_evaluation import audit_run, session_check

VERSION = "historical-transfer-learning-epoch-v1"
LIMITS = {"max_model_calls": 200, "max_target_model_calls": 196, "max_replays": 12,
          "max_optimizer_model_calls": 4, "max_tokens": 4_000_000,
          "max_seconds": 1800, "max_iterations": 16, "max_output_tokens": 4096,
          "train_cases": 2, "val_cases": 2, "rollouts_k": 2, "edit_budget": 4}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_bytes())


def _identity(value):
    if (not isinstance(value, str) or not value or value in (".", "..")
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in value)):
        raise ValueError("Unsafe historical identity")
    return value


def _child(root, relative):
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Historical artifact escapes its source directory")
    return path


def _source(source, employee, experiences, cutoff_day):
    """Bind selected public descriptors to audited immutable historical evidence."""
    if type(cutoff_day) is not int or cutoff_day < 0:
        raise ValueError("cutoff_day must be a nonnegative integer")
    _identity(employee)
    cp, manifest = _read(source / "checkpoint.json"), _read(source / "manifest.json")
    eco = Ecosystem.restore(cp["ecosystem"])
    if eco.day != cutoff_day or any(w.day != cutoff_day for w in eco.worlds.values()):
        raise ValueError("Source checkpoint must be exactly at the declared cutoff day")
    if digest(eco.checkpoint()) != digest(cp["ecosystem"]):
        raise ValueError("Restoring the source checkpoint changed its ecosystem")
    roster = {firm + "__" + local for firm, world in eco.worlds.items() for local in world.employees}
    state = cp["runner"]
    if (employee not in roster or state["skills"].get(employee) != SEED_SKILL
            or state["skill_versions"].get(employee) != 0):
        raise ValueError("Selected employee must have the unchanged initial skill")
    if (manifest["config"]["split"] != "dev" or manifest["config"]["algorithm"] != "no_learning"
            or manifest["config"]["state_mode"] != "skill_transfer"):
        raise ValueError("This epoch requires the no-learning skill-transfer development source")
    if not isinstance(experiences, list) or len(experiences) != 4 or not all(isinstance(e, dict) for e in experiences):
        raise ValueError("Select exactly four existing source experience records")
    by_id = {e["id"]: e for e in state["experiences"]}
    sessions = {s["id"]: s for s in state["sessions"]}
    if len(by_id) != len(state["experiences"]) or len(sessions) != len(state["sessions"]):
        raise ValueError("Source has duplicate experience or session identities")
    ids, tasks, selected, capsules = set(), set(), [], {}
    bindings = {"checkpoint.json": file_hash(source / "checkpoint.json"),
                "manifest.json": file_hash(source / "manifest.json")}
    initial_path = "skills/" + employee + "/v000.json"
    bindings[initial_path] = file_hash(_child(source, initial_path))
    for item in experiences:
        identifier = _identity(item.get("id"))
        if identifier in ids or by_id.get(identifier) != item or identifier not in sessions:
            raise ValueError("Selected experience is duplicated, altered, or absent from the source")
        ids.add(identifier)
        record = sessions[identifier]
        case_path, session_path = "private/cases/" + identifier + ".json", "work/" + identifier + "/session.json"
        capsule_file, session_file = _child(source, case_path), _child(source, session_path)
        capsule = _read(capsule_file)
        if "probe" in capsule or capsule["case"].get("split") != "online":
            raise ValueError("Future probes and nonhistorical case namespaces cannot enter learning")
        task_id = _identity(item.get("source_session"))
        if (task_id in tasks or item.get("split") not in ("train", "val")
                or item["split"] != experience_split(task_id)):
            raise ValueError("Learning cases must have unique underlying tasks and their original split")
        tasks.add(task_id)
        if (item.get("employee") != employee or record["employee"] != employee
                or capsule["employee"] != employee or capsule["task_id"] != task_id
                or record["task_id"] != task_id or capsule["case"]["id"] != task_id):
            raise ValueError("Historical case, employee, and source task identity disagree")
        world = capsule["ecosystem"]["worlds"][capsule["firm"]]
        task = world["tasks"][task_id]
        day = capsule["ecosystem"]["day"]
        if (type(day) is not int or day > cutoff_day or world["day"] != day
                or record["day"] != day or capsule["case"]["day"] != day
                or capsule["firm"] + "__" + task["owner"] != employee):
            raise ValueError("Historical task ownership or snapshot day disagrees")
        earliest = day + manifest["config"]["feedback_delay"]
        if any(type(item.get(k)) is not int or not earliest <= item[k] <= cutoff_day
               for k in ("available_day", "feedback_available_day")):
            raise ValueError("Selected task and feedback must already be available at cutoff")
        if (item.get("prompt") != capsule["case"]["request"]
                or json.loads(item.get("context", "null")) != capsule["case"]["public_files"]
                or item.get("feedback") != record["feedback"]):
            raise ValueError("Experience contains altered public task context or feedback")
        session_check(record, session_file.parent, capsule, transport_manifest=manifest)
        bindings[case_path], bindings[session_path] = file_hash(capsule_file), file_hash(session_file)
        selected.append({"id": identifier, "source_task_id": task_id, "employee": employee,
                         "split": item["split"], "source_day": day,
                         "available_day": item["available_day"], "feedback_available_day": item["feedback_available_day"],
                         "experience_sha256": digest(item), "capsule_path": case_path,
                         "capsule_sha256": bindings[case_path], "source_session_path": session_path,
                         "source_session_sha256": bindings[session_path]})
        capsules[identifier] = capsule_file.read_bytes()
    if sorted(e["split"] for e in selected) != ["train", "train", "val", "val"]:
        raise ValueError("The epoch requires exactly two TRAIN and two disjoint VAL tasks")
    audit = audit_run(source, strict=True)
    if audit.get("ok") is not True:
        raise ValueError("Historical source failed strict native artifact audit")
    return cp, manifest, eco, selected, capsules, bindings


def run_learning_epoch(source_run, out, employee, experiences, *, cutoff_day=9,
                       creds=None, executor=execute_case):
    """Run one native epoch; return a durable report, including valid no adoption.

    ``experiences`` must be exact records from the source checkpoint, not future
    probe capsules or newly synthesized descriptors. Output must be fresh. A
    failed/interrupted epoch preserves INFLIGHT evidence and cannot auto-resume.
    Preflight contract errors raise before dispatch; execution errors produce a
    failed report with only the exception class, never provider exception text.
    """
    source, out = Path(source_run).resolve(), Path(out).resolve()
    if type(cutoff_day) is not int or cutoff_day != 9:
        raise ValueError("This preregistered epoch requires the day-nine historical cutoff")
    if source.is_relative_to(out) or out.is_relative_to(source):
        raise ValueError("Source and learning output must be separate directories")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Learning output must be fresh; interrupted epochs require reconciliation")
    cp, original, eco, selected, capsules, bindings = _source(source, employee, experiences, cutoff_day)
    creds = credentials() if creds is None else creds
    if (creds["model"], creds["base_url"]) != (original["target_model"], original["model_base_url"]):
        raise ValueError("Historical learning must use the source target model and provider")
    config = ExperimentConfig(algorithm="skillopt", seed=original["config"]["seed"],
        days=original["config"]["days"], split="dev", state_mode="skill_transfer",
        feedback_delay=original["config"]["feedback_delay"], max_iterations=16,
        max_output_tokens=4096, max_learning_calls=200, max_learning_tokens=4_000_000,
        max_run_seconds=1800, train_cases=2, val_cases=2, edit_budget=4,
        skillopt_rollouts_k=2, focal_employee=employee, hermes_transport=mode(original['config']))
    sources = source_hashes()
    sources["scripts/transfer_learning.py"] = file_hash(Path(__file__))
    parent_hash = digest(eco.checkpoint())
    manifest = {"schema_version": 1, "version": VERSION, "kind": "one_historical_learning_epoch",
        **manifest_fields(config),
        "learning_evidence_version": 2,
        "execution_mode": "native" if executor is execute_case else "injected_executor_fixture",
        "source_directory": str(source), "source_files_sha256": bindings,
        "source_checkpoint_sha256": bindings["checkpoint.json"], "parent_ecosystem_sha256": parent_hash,
        "employee": employee, "cutoff_day": cutoff_day, "selected_experiences": selected,
        "config": config.public(), "limits": deepcopy(LIMITS), "source_sha256": sources,
        "dependencies": dependency_provenance(), "target_model": original["target_model"],
        "model_base_url": original["model_base_url"], "initial_skill_sha256": hashlib.sha256(SEED_SKILL.encode()).hexdigest(),
        "information_contract": "Four observed historical tasks only; original public inputs and chronological feedback. Future probes excluded.",
        "interpretation": "One development epoch. Upstream K2 adds TRAIN attempts; validation uses one attempt per gate phase. Target timeout is at most 420 seconds, shortened by remaining epoch time; native transport/output reservations can stop a rollout earlier. No future evaluation or learning-effect claim.",
        "future_probes_evaluated": False}
    state = {"status": "initialized", "skills": {employee: SEED_SKILL},
             "skill_versions": {employee: 0}, "experiences": deepcopy(experiences),
             "sessions": [], "updates": [], "learning_calls": 0, "learning_tokens": 0,
             "elapsed_seconds": 0.0}
    out.mkdir(parents=True, exist_ok=True)
    save(out / "manifest.json", manifest)
    save(out / "skills" / employee / "v000.json", {"skill": SEED_SKILL,
         "hash": manifest["initial_skill_sha256"], "adopted_after_day": -1, "version": 0})
    for identifier, raw in capsules.items():
        path = out / "private/cases" / (identifier + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp"); temp.write_bytes(raw); temp.replace(path)
    evidence = {"schema_version": 1, "target_sessions": [], "optimizer_receipts": []}
    started = time.monotonic()

    def unchanged():
        try:
            return digest(eco.checkpoint()) == parent_hash and all(
                _child(source, name).is_file() and file_hash(_child(source, name)) == value
                for name, value in bindings.items())
        except (OSError, ValueError):
            return False

    def checkpoint():
        state["elapsed_seconds"] = time.monotonic() - started
        save(out / "state.json", state)
        save(out / "checkpoint.json", {"ecosystem": eco.checkpoint(), "runner": state})
        save(out / "evidence.json", evidence)

    def begin(kind, key):
        if not unchanged():
            raise RuntimeError("Historical parent changed before learning dispatch")
        state["status"] = "running"
        checkpoint()
        save(out / "INFLIGHT.json", {"kind": kind, "key": key, "cutoff_day": cutoff_day,
            "source_checkpoint_sha256": bindings["checkpoint.json"], "limits": deepcopy(LIMITS),
            "recovery": "Do not automatically repeat. Reconcile every physical receipt before a new epoch."})

    def finish():
        if not unchanged():
            raise RuntimeError("Historical parent changed during learning")
        checkpoint()  # Final status and INFLIGHT removal follow evidence reconciliation.

    selected_by_task = {row["source_task_id"]: row for row in selected}

    def checked_executor(**kwargs):
        if not unchanged():
            raise RuntimeError("Historical parent changed before target dispatch")
        if len(evidence["target_sessions"]) >= LIMITS["max_replays"]:
            raise RuntimeError("Upstream exceeded the declared twelve replay epoch")
        if (not 0 < kwargs["max_iterations"] <= 16 or kwargs["max_tokens"] != 4096
                or not 0 < kwargs["max_total_tokens"] <= 250000
                or not 0 < kwargs["timeout_seconds"] <= 420):
            raise RuntimeError("Upstream target dispatch differs from the declared limits")
        selected_row = selected_by_task[kwargs["task_id"]]
        case_file = out / selected_row["capsule_path"]
        if file_hash(case_file) != selected_row["capsule_sha256"]:
            raise ValueError("Copied historical capsule changed")
        path = kwargs["root"] / "session.json"
        row = {"attempt_index": len(evidence["target_sessions"]),
               "experience_id": selected_row["id"], "source_task_id": kwargs["task_id"],
               "session_path": str(path.relative_to(out)),
               "session_sha256": None, "dispatch_status": "dispatched",
               "skill_sha256": hashlib.sha256(kwargs["skill"].encode()).hexdigest()}
        evidence["target_sessions"].append(row)
        save(out / "evidence.json", evidence)
        result = None
        try:
            result = executor(**kwargs)
        finally:
            row["session_sha256"] = file_hash(path) if path.is_file() else None
            row["dispatch_status"] = "returned" if result is not None else "interrupted_or_failed"
            save(out / "evidence.json", evidence)
        if file_hash(case_file) != selected_row["capsule_sha256"]:
            raise RuntimeError("Copied historical capsule changed during target execution")
        session_check(result, path.parent, _read(case_file), transport_manifest=manifest)
        if not unchanged():
            raise RuntimeError("Historical parent changed during target execution")
        print(f"Learning replay {len(evidence['target_sessions'])} (cap {LIMITS['max_replays']}) "
              f"{employee} success={result['success']} calls={result['usage']['api_calls']}", flush=True)
        return result

    checkpoint()
    error_class = None
    try:
        _learn(out, config, eco, state, employee, deepcopy(experiences), creds,
               checked_executor, begin, finish, remaining_seconds=lambda: max(.001, 1800 - (time.monotonic() - started)))
        if len(state["updates"]) != 1:
            raise RuntimeError("The bounded epoch did not produce exactly one update")
        update = state["updates"][0]
        if (update["configuration"]["rollouts_k"] != 2 or len(update["train_ids"]) != 2
                or len(update["validation_ids"]) != 2):
            raise RuntimeError("Upstream update differs from the declared K2/T2/V2 epoch")
        targets = [r for r in update["costs"]["operations"] if r["kind"] == "target"]
        from scripts.audit_learning_v2 import reconcile, version
        identities = reconcile(update) if version(update) == 2 else update["replay_evidence"]
        if len(targets) != len(evidence["target_sessions"]) or len(targets) != len(identities):
            raise RuntimeError("Target sessions and upstream replay receipts do not reconcile")
        for row, operation, replay in zip(evidence["target_sessions"], targets, identities):
            path = out / row["session_path"]
            native = _read(path)
            if (row["experience_id"] != operation["task_id"] or row["experience_id"] != replay["id"]
                    or row["skill_sha256"] != replay["skill_sha256"]
                    or row["session_sha256"] != file_hash(path)
                    or row["attempt_index"] != replay["attempt_index"]
                    or any(operation[k] != replay[k] for k in ("phase", "sample_id", "attempt_index"))
                    or native["usage"]["api_calls"] != operation["model_calls"]
                    or native["usage"]["total_tokens"] != operation["tokens"]):
                raise RuntimeError("Target session identity differs from upstream evidence")
            row.update(phase=replay["phase"], sample_id=replay["sample_id"], cost=deepcopy(operation))
        optimizers = [r for r in update["costs"]["operations"] if r["kind"] == "optimizer"]
        audits = update["optimizer_transport_audit"]
        if len(optimizers) != len(audits) or any(
                receipt.get("accounting_complete") is not True
                or receipt.get("model_calls") != operation["model_calls"]
                or receipt.get("tokens") != operation["tokens"]
                or receipt["input_tokens"] + receipt["output_tokens"] != receipt["tokens"]
                for operation, receipt in zip(optimizers, audits)):
            raise RuntimeError("Optimizer transport receipts do not reconcile")
        if (state["learning_calls"] > LIMITS["max_model_calls"] or state["learning_tokens"] > LIMITS["max_tokens"]
                or not unchanged() or any(file_hash(out / row["capsule_path"]) != row["capsule_sha256"]
                                           for row in selected)):
            raise RuntimeError("Learning exceeded budget or altered its historical parent")
        state["status"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error_class = type(exc).__name__
        state["status"] = "failed"
        save(out / "FAILURE.json", {"error_class": error_class,
             "recovery": "Epoch failed; retain INFLIGHT and native receipts. Automatic resumption is forbidden."})
    update = state["updates"][0] if state["updates"] else None
    if update:
        evidence["optimizer_receipts"] = deepcopy(update["optimizer_transport_audit"])
        # Even a failed callback has an upstream reservation. Preserve the link
        # to its dispatched native directory when no usable replay was returned.
        targets = [r for r in update["costs"]["operations"] if r["kind"] == "target"]
        for row, operation in zip(evidence["target_sessions"], targets):
            row.setdefault("phase", operation["phase"])
            row.setdefault("sample_id", operation["sample_id"])
            row.setdefault("cost", deepcopy(operation))
    checkpoint()
    complete = bool(update and update["costs"]["accounting_complete"])
    costs = update["costs"] if update else {}
    update_path = "learning/d%03d-%s/update.json" % (cutoff_day, employee)
    report = {"schema_version": 1, "version": VERSION, "status": state["status"],
        "execution_mode": manifest["execution_mode"], "employee": employee, "cutoff_day": cutoff_day,
        "accepted": bool(update and update["accepted"] and state["status"] == "completed"),
        "learning_status": update["status"] if update else "not_completed",
        "error_class": error_class, "skill_version": state["skill_versions"][employee],
        "skill_sha256": hashlib.sha256(state["skills"][employee].encode()).hexdigest(),
        "usage": {"accounting_complete": complete,
            "target_model_calls": costs.get("target_model_calls") if complete else None,
            "optimizer_model_calls": costs.get("optimizer_model_calls") if complete else None,
            "model_calls": state["learning_calls"] if complete else None,
            "tokens": state["learning_tokens"] if complete else None,
            "charged_or_reserved_model_calls": state["learning_calls"] if update else 200,
            "charged_or_reserved_tokens": state["learning_tokens"] if update else 4_000_000,
            "reserved_max_model_calls": 200, "reserved_max_tokens": 4_000_000,
            "elapsed_seconds": state["elapsed_seconds"]},
        "update_path": update_path if update else None,
        "update_sha256": file_hash(out / update_path) if update else None,
        "evidence_path": "evidence.json", "evidence_sha256": file_hash(out / "evidence.json"),
        "manifest_sha256": file_hash(out / "manifest.json"),
        "parent_unchanged": unchanged(), "future_probes_evaluated": False,
        "deployed_to_future_probes": False,
        "interpretation": "Completed no adoption is valid. An accepted local skill still requires independent future probes; no learning improvement is established here."}
    save(out / "REPORT.json", report)
    if state["status"] == "completed":
        (out / "INFLIGHT.json").unlink(missing_ok=True)
    return report
