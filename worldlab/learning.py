"""Native upstream SkillOpt plugged into task-package replays."""
from dataclasses import asdict
import os
from pathlib import Path
from scripts.source_world_calibration import save
from lifespan.evaluation.optimizer import make_reflector
from lifespan.evaluation.skillopt import SkillOptLearner, LearningBudget, REVISION, _load_upstream
from lifespan.evaluation.provider import provider_contract


class SkillOpt:
    def __init__(self, source, model, base_url, *, budget=None, edit_budget=2, rollouts_k=2):
        self.source = Path(source).resolve()
        _load_upstream(self.source)
        self.provider = provider_contract(model, base_url)
        self.budget = LearningBudget(**budget) if budget else LearningBudget(
            max_replays=24, max_target_model_calls=960, max_optimizer_model_calls=2,
            max_tokens=12_000_000, max_seconds=3600, replay_model_calls=40,
            replay_tokens=900_000, replay_seconds=1200, optimizer_tokens=32000)
        self.edit_budget, self.rollouts_k = edit_budget, rollouts_k

    def identity(self):
        return {'name': 'skillopt_sleep', 'revision': REVISION, 'provider': self.provider,
                'edit_budget': self.edit_budget, 'rollouts_k': self.rollouts_k,
                'budget': asdict(self.budget), 'gate_metric': 'mixed', 'gate_no_regression': True}

    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        # The world controller, not the optimizer, owns replay, private grading,
        # chronological selection and the task lookup. No final probes enter here.
        credentials = {'model': self.provider['model'], 'base_url': self.provider['base_url'],
                       'api_key': os.environ.get('WORLDLAB_API_KEY', 'EMPTY'),
                       'provider_profile': self.provider['profile']}
        reflector = make_reflector(credentials, augment_training_context=True)
        learner = SkillOptLearner(source=self.source, edit_budget=self.edit_budget, rollouts_k=self.rollouts_k)
        result = learner.update(skill, experiences, replay, reflector,
                                current_day=current_day, budget=self.budget)
        result['optimizer_transport_audit'] = reflector.audit_records
        save(Path(artifact_root) / 'UPDATE.json', result)
        return result
