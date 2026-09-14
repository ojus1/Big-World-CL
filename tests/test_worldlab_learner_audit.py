"""A non-SkillOpt policy must be auditable without adopting SkillOpt's gate."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import save, read
from worldlab.audit_worlds import audit_updates, resolve_auditors
from worldlab.campaign import SEED_SKILL
from worldlab.learning import SkillOpt


class RuleLearner:
    def identity(self):
        return {'name': 'deterministic_fixture_rule', 'rule': 'Inspect the required column names.'}

    def audit_update(self, root, update, *, skill_before, expected_identity):
        if expected_identity != self.identity() or read(root / 'RULE.json') != {'text': self.identity()['rule']}:
            raise ValueError('Wrong rule provenance')
        if update['skill'] != skill_before + '\n' + self.identity()['rule'] or update['accepted'] is not True:
            raise ValueError('Rule policy did not produce the recorded skill')


class Harness:
    def identity(self): return {'name': 'fixture_harness'}
    def audit_execution(self, *args): raise AssertionError('No native execution in this routing fixture')


def fixture(root):
    learner = RuleLearner()
    sessions = [{'id': f'{split}-{i}', 'employee_id': 'editor', 'day': i,
                 'feedback_day': i + 1, 'split': split, 'lineage_group': f'{split}-{i}',
                 'task_id': f'{split}-{i}', 'status': 'completed', 'grade': {'quality_score': .5}}
                for split in ('train', 'val') for i in (0, 1)]
    update = {'status': 'completed', 'accepted': True, 'skill': SEED_SKILL + '\n' + learner.identity()['rule'],
              'train_ids': ['train-0', 'train-1'], 'validation_ids': ['val-0', 'val-1'],
              'replay_evidence': [], 'costs': {'tokens': 0, 'operations': [], 'accounting_complete': True}}
    directory = root / 'learning/d006-editor'
    save(directory / 'UPDATE.json', update)
    save(directory / 'RULE.json', {'text': learner.identity()['rule']})
    state = {'sessions': sessions, 'updates': [{'day': 6, 'employee_id': 'editor', 'result': update}]}
    world = {'workforce': [{'id': 'editor'}], 'specification': {'update_days': [6]}}
    return learner, world, state, directory


class Tests(unittest.TestCase):
    def test_custom_policy_audits_without_skillopt_specific_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner, world, state, directory = fixture(root)
            counts = {'adoptions': 0, 'learning_replays': 0}
            audit_updates(None, world, root, state, learner.identity()['name'], None, counts,
                          learner, learner.identity())
            self.assertEqual(counts['adoptions'], 1)
            self.assertNotIn('configuration', state['updates'][0]['result'])
            self.assertNotIn('optimizer_inputs', state['updates'][0]['result'])
            save(directory / 'RULE.json', {'text': 'Different source rule'})
            with self.assertRaisesRegex(ValueError, 'Wrong rule provenance'):
                audit_updates(None, world, root, state, learner.identity()['name'], None, counts,
                              learner, learner.identity())

    def test_shared_audit_rejects_future_examples_before_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner, world, state, _ = fixture(root)
            state['sessions'][0]['feedback_day'] = 7
            with patch.object(learner, 'audit_update') as policy:
                with self.assertRaisesRegex(ValueError, 'Learning leaked future or wrong cases'):
                    audit_updates(None, world, root, state, learner.identity()['name'], None,
                                  {'adoptions': 0, 'learning_replays': 0}, learner, learner.identity())
                policy.assert_not_called()

    def test_configured_implementations_require_their_exact_auditor(self):
        harness, learner = Harness(), RuleLearner()
        study = {'harness': harness.identity(), 'learner': learner.identity()}
        self.assertEqual(resolve_auditors(study, harness, learner), (harness, learner))
        changed = deepcopy(study); changed['learner']['rule'] = 'Other rule'
        with self.assertRaisesRegex(ValueError, 'learner auditor differs'):
            resolve_auditors(changed, harness, learner)
        builtins = {'harness': {'name': 'native_hermes_task_package'},
                    'learner': {'name': 'skillopt_sleep', 'operator_factory': {'configuration_sha256': 'fixed'}}}
        with self.assertRaisesRegex(ValueError, 'frozen learner factory configuration'):
            resolve_auditors(builtins)

    def test_skillopt_checks_original_gate_and_frozen_configuration(self):
        identity = {'revision': 'revision', 'edit_budget': 2, 'rollouts_k': 2,
                    'gate_metric': 'mixed', 'gate_no_regression': True, 'budget': {'max_tokens': 100}}
        update = {'configuration': {k: v for k, v in identity.items() if k != 'revision'},
                  'upstream_revision': 'revision', 'skill': 'seed', 'optimizer_inputs': [],
                  'costs': {'operations': []}, 'optimizer_transport_audit': [],
                  'train_ids': ['train'], 'skill_before_sha256': hashlib.sha256(b'seed').hexdigest(),
                  'skill_after_sha256': hashlib.sha256(b'seed').hexdigest()}
        with patch('scripts.audit_transfer.gate_check') as gate:
            SkillOpt.audit_update(None, update, skill_before='seed', expected_identity=identity)
            gate.assert_called_once_with(update)
        update['configuration']['budget'] = {'max_tokens': 1000}
        with self.assertRaisesRegex(ValueError, 'configuration differs'):
            SkillOpt.audit_update(None, update, skill_before='seed', expected_identity=identity)

    def test_skillopt_rejects_missing_optimizer_receipt(self):
        identity = {'revision': 'revision', 'edit_budget': 2, 'rollouts_k': 2,
                    'gate_metric': 'mixed', 'gate_no_regression': True, 'budget': {}}
        update = {'configuration': {k: v for k, v in identity.items() if k != 'revision'},
                  'upstream_revision': 'revision', 'skill': 'seed', 'optimizer_inputs': [],
                  'train_ids': [], 'costs': {'operations': [{'kind': 'optimizer'}]},
                  'optimizer_transport_audit': [],
                  'skill_before_sha256': hashlib.sha256(b'seed').hexdigest(),
                  'skill_after_sha256': hashlib.sha256(b'seed').hexdigest()}
        with self.assertRaisesRegex(ValueError, 'Missing native optimizer transport evidence'):
            SkillOpt.audit_update(None, update, skill_before='seed', expected_identity=identity)
