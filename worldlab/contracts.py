"""Public execution contracts; evaluator answers never enter these objects."""
from dataclasses import dataclass
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
    def identity(self) -> dict: ...
    def unsupported(self, public_task: dict) -> list[str]: ...
    def run(self, request: TaskRequest, artifact_root: Path) -> dict: ...


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
