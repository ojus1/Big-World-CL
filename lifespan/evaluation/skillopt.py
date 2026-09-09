"""Pinned upstream SkillOpt-Sleep with isolated native execution supplied by the caller.

Only safe task descriptors cross the optimizer boundary. The replay callback owns
the private case lookup, sandbox fork, native Hermes execution and trusted grader.
This module never mines personal sessions, loads personal SkillOpt configuration,
or substitutes a text-only model for the employee's execution harness.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable

REVISION = "79124b37e9a6371e13b753f8bcd7adb1e493ade1"
DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / ".cache" / "SkillOpt"
_UPSTREAM_LOCK = threading.RLock()


class SkillOptUnavailable(RuntimeError):
    """The verified upstream dependency is missing or has changed."""


class InvalidExperience(ValueError):
    """An experience violates the split or visibility contract."""


class ReplayFailure(RuntimeError):
    """A replay or optimizer call lacks valid execution/accounting evidence."""


class BudgetExhausted(ReplayFailure):
    """The next operation cannot fit the declared learning budget."""


@dataclass(frozen=True)
class LearningBudget:
    max_replays: int = 64
    max_target_model_calls: int = 1024
    max_optimizer_model_calls: int = 4
    max_tokens: int = 1_000_000
    max_seconds: float = 3600
    replay_model_calls: int = 16
    replay_tokens: int = 32_000
    replay_seconds: float = 180
    optimizer_model_calls: int = 1
    optimizer_tokens: int = 8192
    optimizer_seconds: float = 120

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
            if not name.endswith("seconds") and not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_upstream(source: Path):
    source = source.resolve()
    if not (source / "skillopt_sleep" / "consolidate.py").is_file():
        raise SkillOptUnavailable("Run python3 scripts/install_skillopt.py to fetch pinned SkillOpt")
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=normal"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise SkillOptUnavailable("SkillOpt must be a verifiable pinned git checkout") from exc
    if revision != REVISION or dirty:
        raise SkillOptUnavailable("SkillOpt checkout must be clean and at the reviewed revision")
    for name, module in tuple(sys.modules.items()):
        if name == "skillopt_sleep" or name.startswith("skillopt_sleep."):
            path = Path(getattr(module, "__file__", "")).resolve()
            if not path.is_relative_to(source):
                raise SkillOptUnavailable("A different SkillOpt package is already imported")
    sys.path.insert(0, str(source))
    try:
        return (
            importlib.import_module("skillopt_sleep.consolidate").consolidate,
            importlib.import_module("skillopt_sleep.backend").CliBackend,
            importlib.import_module("skillopt_sleep.types").TaskRecord,
            importlib.import_module("skillopt_sleep.prompts"),
        )
    finally:
        sys.path.remove(str(source))


@contextmanager
def _frozen_upstream_settings(prompts):
    # consolidate's replay_batch reads this process variable, and CliBackend
    # normally consults user prompt overrides. Serialize our calls and replace
    # only the renderer temporarily, without reading/writing personal config.
    previous_workers = os.environ.get("SKILLOPT_SLEEP_WORKERS")
    previous_render = prompts.render

    def render(name, replacements):
        result = prompts.DEFAULTS[name]["text"]
        for key, value in replacements.items():
            result = result.replace(key, str(value))
        return result

    os.environ["SKILLOPT_SLEEP_WORKERS"] = "1"
    prompts.render = render
    try:
        yield
    finally:
        prompts.render = previous_render
        if previous_workers is None:
            os.environ.pop("SKILLOPT_SLEEP_WORKERS", None)
        else:
            os.environ["SKILLOPT_SLEEP_WORKERS"] = previous_workers


def _day(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidExperience(f"{field} must be a nonnegative integer")
    return value


def _safe_experiences(experiences: list[dict], current_day: int) -> list[dict]:
    _day(current_day, "current_day")
    safe = []
    ids, fingerprints, source_splits = set(), {}, {}
    for raw in experiences:
        if not isinstance(raw, dict):
            raise InvalidExperience("Experience must be a mapping")
        case_id, split = raw.get("id"), raw.get("split")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise InvalidExperience("Experience ids must be nonempty and globally unique")
        ids.add(case_id)
        if split not in {"train", "val"}:
            raise InvalidExperience("Only train and val are permitted; test cases never enter updates")
        available_day = _day(raw.get("available_day"), "available_day")
        if available_day > current_day:
            raise InvalidExperience("Future cases cannot enter deployment-time learning")
        prompt = raw.get("prompt")
        context = raw.get("context", "")
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(context, str):
            raise InvalidExperience("Experiences need a public prompt and string context")
        # Distinct ids do not make copies of one task a valid held-out set.
        fingerprint = _hash(json.dumps([prompt, context], ensure_ascii=False))
        if fingerprint in fingerprints and fingerprints[fingerprint] != split:
            raise InvalidExperience("Identical task content occurs in train and validation")
        fingerprints[fingerprint] = split
        source_session = raw.get("source_session", "")
        if not isinstance(source_session, str):
            raise InvalidExperience("source_session must be a string")
        if source_session:
            if source_session in source_splits and source_splits[source_session] != split:
                raise InvalidExperience("A source session cannot contribute to both train and validation")
            source_splits[source_session] = split
        feedback = raw.get("feedback", "")
        if not isinstance(feedback, str):
            raise InvalidExperience("feedback must be a public string")
        feedback_day = _day(raw.get("feedback_available_day", available_day), "feedback_available_day")
        safe.append({
            "id": case_id, "split": split, "available_day": available_day,
            "prompt": prompt, "context": context, "source_session": source_session,
            "feedback": feedback if feedback_day <= current_day else "",
            "feedback_available_day": feedback_day,
        })
    if {item["split"] for item in safe} != {"train", "val"}:
        raise InvalidExperience("Nonempty disjoint train and validation slices are required")
    return safe


class _Ledger:
    def __init__(self, budget: LearningBudget):
        self.budget = budget
        self.started = time.monotonic()
        self.rows = []
        self.tokens = 0
        self.target_model_calls = 0
        self.optimizer_model_calls = 0
        self.replays = 0
        self.accounting_complete = True

    def invoke(self, kind: str, callback: Callable, payload: dict) -> dict:
        b = self.budget
        target = kind == "target"
        category = "target_model_calls" if target else "optimizer_model_calls"
        remaining_calls = getattr(b, f"max_{category}") - getattr(self, category)
        remaining_tokens = b.max_tokens - self.tokens
        remaining_seconds = b.max_seconds - (time.monotonic() - self.started)
        if target and self.replays >= b.max_replays:
            raise BudgetExhausted("Replay budget exhausted")
        if remaining_calls < 1 or remaining_tokens < 1 or remaining_seconds <= 0:
            raise BudgetExhausted(f"{kind} budget exhausted")
        limits = {
            "remaining_model_calls": remaining_calls, "remaining_tokens": remaining_tokens,
            "remaining_seconds": remaining_seconds,
            "max_model_calls": min(remaining_calls, b.replay_model_calls if target else b.optimizer_model_calls),
            "max_tokens": min(remaining_tokens, b.replay_tokens if target else b.optimizer_tokens),
            "timeout_seconds": min(remaining_seconds, b.replay_seconds if target else b.optimizer_seconds),
        }
        # Reserve before dispatch. If a call crashes without receipts the full
        # reservation stays charged, and the report marks accounting incomplete.
        self.tokens += limits["max_tokens"]
        setattr(self, category, getattr(self, category) + limits["max_model_calls"])
        if target:
            self.replays += 1
        row = {"kind": kind, "task_id": payload.get("task", {}).get("id"),
               "phase": payload.get("phase", "reflect"), "limits": limits,
               "attempt_index": payload.get("attempt_index"), "sample_id": payload.get("sample_id"),
               "tokens": limits["max_tokens"], "model_calls": limits["max_model_calls"],
               "tool_calls": None, "accounting": "reservation", "status": "dispatched"}
        self.rows.append(row)
        started = time.monotonic()
        try:
            result = callback(payload, dict(limits))
        except Exception as exc:
            self.accounting_complete = False
            row.update(status="callback_failed", wall_seconds=time.monotonic() - started)
            # Error text can contain provider headers or secrets; expose the
            # exception class only. The caller owns private operational logs.
            raise ReplayFailure(f"{kind} callback raised {type(exc).__name__}") from None
        wall_seconds = time.monotonic() - started
        row["wall_seconds"] = wall_seconds
        if not isinstance(result, dict):
            self.accounting_complete = False
            row["status"] = "invalid_receipt"
            raise ReplayFailure("Callback must return an execution receipt")
        for name in ("tokens", "model_calls", "tool_calls"):
            value = result.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                self.accounting_complete = False
                row["status"] = "invalid_receipt"
                raise ReplayFailure(f"Callback omitted valid {name} accounting")
        latency = result.get("latency_ms")
        if (isinstance(latency, bool) or not isinstance(latency, (int, float))
                or not math.isfinite(latency) or latency < 0):
            self.accounting_complete = False
            row["status"] = "invalid_receipt"
            raise ReplayFailure("Callback omitted valid latency accounting")
        self.tokens += result["tokens"] - limits["max_tokens"]
        setattr(self, category, getattr(self, category) + result["model_calls"] - limits["max_model_calls"])
        row.update({key: result[key] for key in ("tokens", "model_calls", "tool_calls", "latency_ms")})
        row.update(accounting="reported", status=str(result.get("status", "missing_status")))
        if (result["tokens"] > limits["max_tokens"] or result["model_calls"] > limits["max_model_calls"]
                or wall_seconds > limits["timeout_seconds"] or latency > limits["timeout_seconds"] * 1000):
            row["status"] = "budget_exceeded"
            raise BudgetExhausted("Callback exceeded its reserved budget; candidate cannot be accepted")
        if result.get("status") != "completed":
            raise ReplayFailure(f"{kind} execution did not complete")
        return result

    def report(self):
        return {
            "tokens": self.tokens, "target_model_calls": self.target_model_calls,
            "optimizer_model_calls": self.optimizer_model_calls, "replays": self.replays,
            "wall_seconds": time.monotonic() - self.started,
            "accounting_complete": self.accounting_complete, "operations": self.rows,
        }


class SkillOptLearner:
    """One upstream consolidation epoch, with explicit execution and learning costs.

    replay(payload, limits) must create a fresh isolated native-Hermes replay and
    return completed/hard/soft/response/feedback plus an accounting receipt.
    reflect(payload, limits) calls the optimizer model on payload['prompt'] and
    returns completed/response (JSON edits) plus the same accounting receipt.
    Neither callback is an arbitrary optimizer plugin: upstream code still owns
    reflection formatting/parsing, applying edits and both validation gates.
    """

    name = "skillopt_sleep"

    def __init__(self, *, source: str | Path = DEFAULT_SOURCE, edit_budget: int = 4,
                 gate_metric: str = "mixed", gate_no_regression: bool = True,
                 gate_mixed_weight: float = 0.5, max_skill_chars: int = 32_000,
                 rollouts_k: int = 1):
        if not isinstance(edit_budget, int) or isinstance(edit_budget, bool) or edit_budget < 1:
            raise ValueError("edit_budget must be a positive integer")
        if gate_metric not in {"hard", "soft", "mixed"}:
            raise ValueError("gate_metric must be hard, soft or mixed")
        if not math.isfinite(gate_mixed_weight) or not 0 <= gate_mixed_weight <= 1:
            raise ValueError("gate_mixed_weight must be in [0, 1]")
        if not isinstance(max_skill_chars, int) or max_skill_chars < 1:
            raise ValueError("max_skill_chars must be positive")
        if type(rollouts_k) is not int or rollouts_k < 1:
            raise ValueError("rollouts_k must be a positive integer")
        self.source, self.edit_budget = Path(source), edit_budget
        self.gate_metric, self.gate_no_regression = gate_metric, gate_no_regression
        self.gate_mixed_weight, self.max_skill_chars = gate_mixed_weight, max_skill_chars
        self.rollouts_k = rollouts_k

    def update(self, skill: str, experiences: list[dict], replay: Callable, reflect: Callable,
               *, current_day: int, budget: LearningBudget | dict | None = None,
               night: int = 1) -> dict:
        safe = _safe_experiences(experiences, current_day)
        if not isinstance(skill, str) or len(skill) > self.max_skill_chars:
            raise ValueError("Initial skill must be a string within max_skill_chars")
        budget = LearningBudget(**budget) if isinstance(budget, dict) else budget or LearningBudget()
        ledger = _Ledger(budget)
        attempts, optimizer_inputs = [], []
        result = {
            "algorithm": self.name, "upstream_revision": REVISION,
            "accepted": False, "skill": skill, "skill_before_sha256": _hash(skill),
            "current_day": current_day, "train_ids": [x["id"] for x in safe if x["split"] == "train"],
            "validation_ids": [x["id"] for x in safe if x["split"] == "val"],
            "configuration": {"edit_budget": self.edit_budget, "gate_metric": self.gate_metric,
                "gate_mixed_weight": self.gate_mixed_weight, "gate_no_regression": self.gate_no_regression,
                "gate_mode": "on", "evolve_memory": False, "rollouts_k": self.rollouts_k,
                "budget": asdict(budget)},
        }
        with _UPSTREAM_LOCK:
            consolidate, CliBackend, TaskRecord, prompts = _load_upstream(self.source)
            descriptors = {x["id"]: x for x in safe}
            tasks = [TaskRecord(id=x["id"], project="big-world-cl", intent=x["prompt"],
                                context_excerpt=x["context"], split=x["split"],
                                reference_kind="none", source_sessions=[x["source_session"]] if x["source_session"] else [])
                     for x in safe]
            max_chars = self.max_skill_chars

            class NativeBridge(CliBackend):
                name = "big-world-native-hermes"

                def __init__(self):
                    super().__init__(model="callback-optimizer")
                    self.pending = {}

                def attempt(self, task, candidate, memory, sample_id=0):
                    if memory or len(candidate) > max_chars:
                        raise ReplayFailure("Candidate violated the skill-only document boundary")
                    public = dict(descriptors[task.id])
                    receipt = ledger.invoke("target", replay, {
                        "task": public, "skill": candidate,
                        "phase": self.evidence_phase, "sample_id": sample_id,
                        "attempt_index": len(attempts), "current_day": current_day,
                    })
                    for name in ("hard", "soft"):
                        score = receipt.get(name)
                        if (isinstance(score, bool) or not isinstance(score, (int, float))
                                or not math.isfinite(score) or not 0 <= score <= 1):
                            raise ReplayFailure("Replay returned a missing, nonfinite or out-of-range score")
                    score_day = _day(receipt.get("score_available_day", current_day), "score_available_day")
                    if score_day > current_day:
                        raise ReplayFailure("Future scores cannot drive reflection or validation")
                    response, feedback = receipt.get("response"), receipt.get("feedback", "")
                    if not isinstance(response, str) or not isinstance(feedback, str):
                        raise ReplayFailure("Replay response and public feedback must be strings")
                    feedback_day = _day(receipt.get("feedback_available_day", current_day), "replay feedback_available_day")
                    if feedback_day > current_day:
                        feedback = ""
                    # No raw receipts/diagnostics are retained or sent to reflect.
                    attempt = {"id": task.id, "split": task.split, "phase": self.evidence_phase,
                               "sample_id": sample_id, "attempt_index": len(attempts),
                               "skill_sha256": _hash(candidate), "hard": receipt["hard"],
                               "soft": receipt["soft"], "response": response, "feedback": feedback}
                    attempts.append(attempt)
                    self.pending[task.id] = attempt
                    return response

                def judge(self, task, response):
                    record = self.pending.pop(task.id, None)
                    if record is None or record["response"] != response:
                        raise ReplayFailure("Score is not attached to this exact native replay")
                    return record["hard"], record["soft"], record["feedback"]

                def tokens_used(self):
                    return ledger.tokens

                def _call(self, prompt, *, max_tokens=1024):
                    train = [{"task": dict(descriptors[x["id"]]),
                              "sample_id": x["sample_id"], "attempt_index": x["attempt_index"],
                              "phase": x["phase"],
                              "response": x["response"], "feedback": x["feedback"]}
                             for x in attempts if x["split"] == "train"]
                    payload = {"prompt": prompt, "train_experiences": train,
                               "max_output_tokens": max_tokens,
                               "phase": "reflect", "current_day": current_day}
                    optimizer_inputs.append(payload)
                    receipt = ledger.invoke("optimizer", reflect, payload)
                    response = receipt.get("response")
                    if response is None and isinstance(receipt.get("edits"), list):
                        response = json.dumps(receipt["edits"], allow_nan=False)
                    if not isinstance(response, str):
                        raise ReplayFailure("Optimizer must return raw JSON edits as a string")
                    return response

            bridge = NativeBridge()
            try:
                with _frozen_upstream_settings(prompts):
                    consolidated = consolidate(
                        bridge, tasks, skill, "", edit_budget=self.edit_budget,
                        gate_metric=self.gate_metric, gate_mixed_weight=self.gate_mixed_weight,
                        gate_no_regression=self.gate_no_regression, gate_mode="on",
                        rollouts_k=self.rollouts_k, evolve_skill=True, evolve_memory=False, night=night,
                    )
                evidence = asdict(consolidated)
                # Raw optimizer replies are allowed text, but unneeded duplicate
                # copies are removed from the public gate record.
                evidence.pop("reflect_raw", None)
                evidence.pop("call_error", None)
                result.update(status="completed", accepted=consolidated.accepted,
                              skill=consolidated.new_skill if consolidated.accepted else skill,
                              gate_evidence=evidence)
            except (ReplayFailure, InvalidExperience) as exc:
                result.update(status="budget_exhausted" if isinstance(exc, BudgetExhausted) else "failed",
                              error=str(exc), gate_evidence={"accepted": False, "gate_action": "reject_incomplete"})
        result.update(skill_after_sha256=_hash(result["skill"]), costs=ledger.report(),
                      replay_evidence=attempts, optimizer_inputs=optimizer_inputs)
        return result
