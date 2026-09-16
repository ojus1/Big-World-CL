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
    def __init__(self, source, model, base_url, *, budget=None, edit_budget=2, rollouts_k=2,
                 scoped_edits=True, confirmation_cases=0, confirmation_repeats=2, confirmation_min_gain=0.05):
        self.source = Path(source).resolve()
        _load_upstream(self.source)
        self.provider = provider_contract(model, base_url)
        self.budget = LearningBudget(**budget) if budget else LearningBudget(
            max_replays=24, max_target_model_calls=1560, max_optimizer_model_calls=2,
            max_tokens=12_000_000, max_seconds=19000, replay_model_calls=65,
            replay_tokens=900_000, replay_seconds=1500, optimizer_tokens=32000)
        self.edit_budget, self.rollouts_k = edit_budget, rollouts_k
        from lifespan.evaluation.scoped_edits import POLICY
        if type(scoped_edits) is not bool: raise ValueError('scoped_edits must be boolean')
        self.edit_policy = POLICY if scoped_edits else None
        self.confirmation_cases, self.confirmation_repeats = confirmation_cases, confirmation_repeats
        self.confirmation_min_gain = confirmation_min_gain

    def validate_plan(self, spec, judge):
        """Reserve the entire declared epoch; never a knowingly truncated gate."""
        if not spec.get('update_days'): return
        train, val = spec.get('train_cases', 2), spec.get('val_cases', 2)
        if val <= self.confirmation_cases:
            raise ValueError('Learning needs separate nonempty proposal and confirmation validation slices')
        replays = train * (1 + self.rollouts_k) + 3 * (val - self.confirmation_cases)
        replays += 2 * self.confirmation_cases * self.confirmation_repeats
        b = self.budget
        required = {'max_replays': replays, 'max_target_model_calls': replays * b.replay_model_calls,
                    'max_tokens': replays * b.replay_tokens + b.max_optimizer_model_calls * b.optimizer_tokens,
                    'max_seconds': replays * b.replay_seconds + b.max_optimizer_model_calls * b.optimizer_seconds + 300}
        for name, minimum in required.items():
            if getattr(b, name) < minimum:
                raise ValueError('Learning budget cannot reserve the complete epoch: ' + name + ' >= ' + str(minimum))
        from .contracts import Budget
        work = Budget(**spec.get('work_budget', {}))
        if b.replay_tokens < work.total_tokens + judge.max_tokens or b.replay_model_calls < work.model_calls + judge.max_model_calls:
            raise ValueError('Replay must preserve the full online work and judge allocation')

    def identity(self):
        return {'name': 'skillopt_sleep', 'revision': REVISION, 'provider': self.provider,
                'edit_budget': self.edit_budget, 'rollouts_k': self.rollouts_k,
                'budget': asdict(self.budget), 'gate_metric': 'mixed', 'gate_no_regression': True,
                'edit_policy': self.edit_policy,
                'confirmation': ({'cases': self.confirmation_cases, 'repeats': self.confirmation_repeats,
                    'min_gain': self.confirmation_min_gain, 'selection': 'last_predeclared_validation_cases',
                    'no_case_regression': True} if self.confirmation_cases else None)}

    def update(self, skill, experiences, replay, *, current_day, artifact_root):
        # The world controller, not the optimizer, owns replay, private grading,
        # chronological selection and the task lookup. No final probes enter here.
        credentials = {'model': self.provider['model'], 'base_url': self.provider['base_url'],
                       'api_key': os.environ.get('WORLDLAB_API_KEY', 'EMPTY'),
                       'provider_profile': self.provider['profile']}
        from lifespan.evaluation.scoped_edits import BANNER
        reflector = make_reflector(credentials, augment_training_context=True, edit_policy=self.edit_policy)
        learner = SkillOptLearner(source=self.source, edit_budget=self.edit_budget, rollouts_k=self.rollouts_k,
            learned_banner=BANNER if self.edit_policy else None, confirmation_cases=self.confirmation_cases,
            confirmation_repeats=self.confirmation_repeats, confirmation_min_gain=self.confirmation_min_gain)
        result = learner.update(skill, experiences, replay, reflector,
                                current_day=current_day, budget=self.budget)
        result['optimizer_transport_audit'] = reflector.audit_records
        result['edit_policy'] = self.edit_policy
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
        if (configuration.get('confirmation') != expected_identity.get('confirmation') or
                update.get('edit_policy') != expected_identity.get('edit_policy')):
            raise ValueError('Scoped proposal or confirmation policy differs from frozen identity')
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
            optimizer_provider_check(receipt, expected_identity['provider'], edit_policy=expected_identity.get('edit_policy'))
            if expected_identity.get('edit_policy'):
                from lifespan.evaluation.scoped_edits import audit_receipt
                audit_receipt(receipt, set(update['train_ids']))
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
