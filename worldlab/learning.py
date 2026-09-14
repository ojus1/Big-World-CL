"""Native upstream SkillOpt plugged into task-package replays."""
from dataclasses import asdict
import hashlib
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

    @staticmethod
    def audit_update(artifact_root, update, *, skill_before, expected_identity):
        """Keep the registered native SkillOpt policy outside the world auditor."""
        from scripts.audit_transfer import gate_check
        configuration = update['configuration']
        if (update['upstream_revision'] != expected_identity['revision'] or
                any(configuration[key] != expected_identity[key]
                    for key in ('edit_budget', 'rollouts_k', 'gate_metric', 'gate_no_regression', 'budget'))):
            raise ValueError('SkillOpt configuration differs from the frozen learner identity')
        if (update['skill_before_sha256'] != hashlib.sha256(skill_before.encode()).hexdigest() or
                update['skill_after_sha256'] != hashlib.sha256(update['skill'].encode()).hexdigest()):
            raise ValueError('SkillOpt update differs from the actual skill before or after learning')
        for payload in update['optimizer_inputs']:
            if not all(e['task']['id'] in update['train_ids'] and e['task']['split'] == 'train'
                       for e in payload['train_experiences']):
                raise ValueError('Optimizer saw non-training evidence')
        from scripts.audit_evaluation import optimizer_provider_check
        operations = [row for row in update['costs']['operations'] if row['kind'] == 'optimizer']
        receipts = update['optimizer_transport_audit']
        if len(operations) != len(receipts):
            raise ValueError('Missing native optimizer transport evidence')
        for row, receipt in zip(operations, receipts):
            optimizer_provider_check(receipt, expected_identity['provider'])
            if (receipt['accounting_complete'] is not True or
                    any(receipt[k] != row[k] for k in ('tokens', 'model_calls', 'tool_calls', 'latency_ms')) or
                    receipt['status'] != row['callback_status'] or
                    receipt['input_tokens'] + receipt['output_tokens'] != receipt['tokens']):
                raise ValueError('Optimizer transport differs from the learning ledger')
            if receipt['model_calls'] and (
                    hashlib.sha256(receipt['optimizer_prompt'].encode()).hexdigest() != receipt['optimizer_prompt_sha256'] or
                    receipt['output_tokens'] > receipt['max_output_tokens']):
                raise ValueError('Optimizer prompt or output cap differs from native evidence')
        gate_check(update)
