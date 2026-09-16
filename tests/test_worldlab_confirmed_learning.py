from copy import deepcopy
import hashlib
import json
import unittest

from lifespan.evaluation.skillopt import SkillOptLearner, LearningBudget, DEFAULT_SOURCE
from lifespan.evaluation.scoped_edits import POLICY, BANNER, compile_response, audit_receipt
from lifespan.evaluation.optimizer import make_reflector
from scripts.audit_transfer import gate_check
from scripts.audit_evaluation import optimizer_provider_check
from test_optimizer_preflight import CREDS, response


@unittest.skipUnless(DEFAULT_SOURCE.is_dir(), 'Pinned upstream required')
class Tests(unittest.TestCase):
    def test_basic_native_schema_retains_strict_client_rejection_of_embedded_lines(self):
        from lifespan.evaluation.scoped_edits import schema
        props = schema()['json']['items']['properties']
        self.assertEqual(props['content'], {'type':'string'})
        self.assertEqual(props['applies_when'], {'type':'string'})
        edit = {'target':'skill','op':'add','content':'One procedure.','anchor':'',
                'rationale':'Training evidence.','applies_when':'Current task needs a CSV.',
                'source_task_ids':['train0']}
        self.assertIn('One procedure.', compile_response(json.dumps([edit]), {'train0'}))
        for field in ('content','applies_when'):
            for newline in ('\n','\r'):
                bad=deepcopy(edit);bad[field]+=newline+'Injected bullet'
                with self.assertRaises(ValueError):compile_response(json.dumps([bad]), {'train0'})

    def test_preparation_rejects_an_epoch_that_cannot_reserve_all_gates(self):
        from types import SimpleNamespace
        from worldlab.learning import SkillOpt
        learner = SkillOpt(DEFAULT_SOURCE, 'fixture', 'http://127.0.0.1:8011/v1')
        spec = {'update_days': [2], 'train_cases': 2, 'val_cases': 2}
        judge = SimpleNamespace(max_tokens=400000, max_model_calls=9)
        learner.validate_plan(spec, judge)
        learner.budget = LearningBudget(**{**learner.identity()['budget'], 'max_seconds': 3600})
        with self.assertRaisesRegex(ValueError, 'complete epoch: max_seconds'):
            learner.validate_plan(spec, judge)

    def run_epoch(self, *, confirmation_gain=True, final_regression=False, max_replays=24, propose=True):
        seed = '# Work process\nFollow the current request.\n'
        experiences = [{'id': f'{split}{i}', 'split': split, 'available_day': 0, 'feedback_available_day': 0,
                        'source_session': f'{split}-family-{i}', 'prompt': f'Unique {split} task {i}', 'context': ''}
                       for split, count in [('train', 2), ('val', 4)] for i in range(count)]
        seen = []
        def target(payload, limits):
            seen.append(deepcopy(payload))
            score = .8 if payload['skill'] != seed else .2
            if payload['phase'] == 'confirmation_candidate' and not confirmation_gain:
                score = .1
            if payload['phase'] == 'confirmation_candidate' and final_regression and payload['sample_id'] == 1:
                score = .1
            return {'status': 'completed', 'model_calls': 1, 'tokens': 10, 'tool_calls': 0, 'latency_ms': 0.,
                    'hard': 0., 'soft': score, 'response': 'Fixture outcome', 'feedback': 'Observed feedback'}
        def reflect(payload, limits):
            self.assertNotIn('Unique val', payload['prompt'])
            self.assertTrue(all(x['task']['split'] == 'train' for x in payload['train_experiences']))
            return {'status': 'completed', 'model_calls': 1, 'tokens': 5, 'tool_calls': 0, 'latency_ms': 0.,
                    'response': json.dumps([{'target': 'skill', 'op': 'add', 'content': 'Fixture reusable procedure.',
                                            'anchor': '', 'rationale': 'Observed training error'}] if propose else [])}
        learner = SkillOptLearner(rollouts_k=2, edit_budget=2, learned_banner=BANNER,
                                 confirmation_cases=2, confirmation_repeats=2, confirmation_min_gain=.05)
        result = learner.update(seed, experiences, target, reflect, current_day=1,
            budget=LearningBudget(max_replays=max_replays, max_tokens=100000, max_seconds=1000))
        gate_check(result)
        return result, seen, seed

    def test_adoption_requires_full_fresh_confirmation_and_audits_exact_candidates(self):
        result, seen, seed = self.run_epoch()
        self.assertTrue(result['accepted']); self.assertEqual(result['costs']['replays'], 20)
        self.assertEqual(result['confirmation_validation_ids'], ['val2', 'val3'])
        self.assertTrue(all(r['task']['id'] not in ('val2', 'val3') for r in seen[:12]))
        self.assertIn(BANNER, result['skill']); self.assertNotIn('adopted only after you', result['skill'])
        self.assertEqual({p['skill'] for p in seen if p['phase'] == 'confirmation_candidate'}, {result['skill']})
        for field in ['accepted', 'skill', 'confirmation']:
            corrupt = deepcopy(result)
            if field == 'accepted': corrupt[field] = False
            if field == 'skill': corrupt[field] = seed
            if field == 'confirmation': corrupt[field]['repeat_mean_gains'][0] = 99
            with self.assertRaises(ValueError): gate_check(corrupt)

    def test_noisy_candidate_is_rejected_even_after_upstream_accepts(self):
        for options in [{'confirmation_gain': False}, {'final_regression': True}]:
            with self.subTest(options=options):
                result, seen, seed = self.run_epoch(**options)
                self.assertTrue(result['proposal_gate_evidence']['accepted'])
                self.assertFalse(result['accepted']); self.assertEqual(result['skill'], seed)
                self.assertEqual(result['costs']['replays'], 20, 'Retain all predeclared draws, including losses')

    def test_exhausted_confirmation_never_adopts_partial_success(self):
        result, seen, seed = self.run_epoch(max_replays=15)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertFalse(result['accepted']); self.assertEqual(result['skill'], seed)
        self.assertTrue(result['costs']['accounting_complete']); self.assertEqual(len(seen), 15)

    def test_no_proposal_skips_confirmation_without_claiming_it_passed(self):
        result, seen, seed = self.run_epoch(propose=False)
        self.assertEqual(result['status'], 'completed'); self.assertFalse(result['accepted'])
        self.assertIsNone(result['confirmation']); self.assertEqual(result['skill'], seed)
        self.assertEqual(len(seen), 10)

    def test_scoped_optimizer_preserves_physical_response_and_cost_on_policy_rejection(self):
        for task_ids, rejected in [(['train0'], False), (['val-secret'], True)]:
            with self.subTest(task_ids=task_ids):
                raw = json.dumps([{'target': 'skill', 'op': 'add', 'content': 'Check CSV quoting.', 'anchor': '',
                    'rationale': 'Observed training failure', 'applies_when': 'the current task requests CSV',
                    'source_task_ids': task_ids}])
                reflector = make_reflector(CREDS, edit_policy=POLICY,
                    transport=lambda request, **kwargs: response(raw))
                record = reflector({'prompt': 'Reflect on training.', 'max_output_tokens': 1024,
                    'current_day': 1, 'train_experiences': [{'task': {'id': 'train0', 'split': 'train',
                    'available_day': 0, 'prompt': 'Make CSV'}, 'response': 'Observed malformed CSV'}]},
                    {'max_model_calls': 1, 'max_tokens': 32000, 'timeout_seconds': 10})
                self.assertEqual(record['status'], 'completed'); self.assertEqual(record['tokens'], 180)
                self.assertIs(record['proposal_rejected'], rejected)
                self.assertEqual(record['raw_proposal_response'], raw)
                audit_receipt(record, {'train0'})
                optimizer_provider_check(record, record['provider_contract'], edit_policy=POLICY)
                if rejected: self.assertEqual(record['response'], '[]')
                else: self.assertIn('current request and source evidence', record['response'])
                corrupt = deepcopy(record); corrupt['response'] = 'fabricated compiled edits'
                with self.assertRaises(ValueError): audit_receipt(corrupt, {'train0'})


if __name__ == '__main__': unittest.main()
