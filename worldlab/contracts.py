"""Public execution contracts; evaluator answers never enter these objects."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Budget:
    model_calls: int = 32
    output_tokens: int = 8192
    total_tokens: int = 500_000
    seconds: int = 1200

    def __post_init__(self):
        for value in (self.model_calls, self.output_tokens, self.total_tokens, self.seconds):
            if type(value) is not int or value <= 0:
                raise ValueError('Budgets must be positive integers')
        if self.total_tokens < self.output_tokens:
            raise ValueError('Total token ceiling is smaller than the output ceiling')


@dataclass(frozen=True)
class TaskRequest:
    """Only this task's public files, employee identity, skill and budget."""
    attempt_id: str
    employee_id: str
    instruction: str
    language: str
    workspace: Path
    skill: str
    budget: Budget


@dataclass(frozen=True)
class Feedback:
    """Released experience; private grader internals and future cases are absent."""
    task_id: str
    lineage_group: str
    observed_day: int
    released_day: int
    partition: str
    request: str
    trajectory: list
    score: float
    feedback: str


class Harness(Protocol):
    """Adapter owns native logs and exposes a normalized, auditable receipt.

    Completed receipts include trajectory, skill_loaded, skill_content_sha256,
    skill_sha256, physical_model_calls, charged_tokens and accounting_complete.
    The adapter's offline auditor checks these claims against native evidence.
    Controller code must not know a harness's log names or skill directory.
    """
    def identity(self) -> dict: ...
    def unsupported(self, public_task: dict) -> list[str]: ...
    def run(self, request: TaskRequest, artifact_root: Path) -> dict: ...
    def audit_execution(self, artifact_root: Path, request: dict, receipt: dict) -> None: ...


def validate_execution(receipt, budget, skill):
    """Reject unusable learning evidence before sending it to a grader."""
    if receipt['status'] not in ('completed', 'budget_exhausted'):
        return
    if receipt.get('accounting_complete') is not True:
        raise ValueError('Completed harness receipt has incomplete accounting')
    for key, ceiling in [('physical_model_calls', budget.model_calls), ('charged_tokens', budget.total_tokens)]:
        if type(receipt.get(key)) is not int or not 0 <= receipt[key] <= ceiling:
            raise ValueError('Invalid or exceeded harness budget: ' + key)
    if not isinstance(receipt.get('trajectory'), list):
        raise ValueError('Harness receipt lacks normalized trajectory')
    if (receipt.get('skill_loaded') is not True or
            receipt.get('skill_content_sha256') != hashlib.sha256(skill.encode()).hexdigest() or
            not isinstance(receipt.get('skill_sha256'), str) or len(receipt['skill_sha256']) != 64):
        raise ValueError('Harness receipt does not prove the requested skill was loaded')


class Learner(Protocol):
    """Learner policy with evaluator-owned replay callbacks and explicit evidence."""
    def identity(self) -> dict: ...
    def update(self, skill: str, experiences: list[dict], replay, *, current_day: int,
               artifact_root: Path) -> dict: ...


class NoLearning:
    def identity(self):
        return {'name': 'no_learning', 'version': 1}

    def propose(self, skill, training, budget, artifact_root):
        return {'skill': skill, 'changed': False, 'model_calls': 0, 'charged_tokens': 0}

    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        return {'status': 'completed', 'skill': skill, 'accepted': False,
                'costs': {'tokens': 0, 'target_model_calls': 0, 'optimizer_model_calls': 0,
                          'accounting_complete': True, 'operations': []}}


def released_training(experiences, day):
    """One latest observation per lineage, no future or validation feedback."""
    selected = {}
    previous = -1
    for e in experiences:
        if e.observed_day < previous or e.released_day < e.observed_day:
            raise ValueError('Experience chronology is invalid')
        previous = e.observed_day
        if e.partition == 'train' and e.released_day <= day:
            selected[e.lineage_group] = e
    return tuple(selected.values())
