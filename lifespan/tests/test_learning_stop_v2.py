"""Offline actual-upstream stop-contract tests, never model-quality evidence."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.evaluation import skillopt
from scripts.audit_learning_v2 import reconcile
from scripts.audit_transfer import gate_check


@unittest.skipUnless((skillopt.DEFAULT_SOURCE / 'skillopt_sleep/consolidate.py').exists(),
                     'Pinned upstream not installed')
class LearningStopV2Tests(unittest.TestCase):
    def simulate(self, *, kind='target', mode='latency', changes=None, budget=None, stop_phase=None):
        clock = [0.]
        tasks = [{'id': split + str(i), 'split': split, 'available_day': 0,
                  'prompt': split + ' fixture ' + str(i), 'source_session': split + str(i)}
                 for split in ('train', 'val') for i in range(2)]
        def callback(which, payload, limits):
            good = 'learned' in payload.get('skill', '')
            result = {'status': 'completed', 'tokens': 5, 'model_calls': 1,
                      'tool_calls': 0, 'latency_ms': 0.}
            if which == 'target':
                result.update(hard=float(good), soft=float(good), response='fixture', feedback='fixture')
            else:
                result['response'] = '[{"op":"add","content":"learned","rationale":"fixture"}]'
            if which == kind and (stop_phase is None or payload.get('phase') == stop_phase):
                if mode == 'wall':
                    clock[0] += 2.
                elif mode == 'latency':
                    result['latency_ms'] = 2000.
                    clock[0] += 2.
                elif mode == 'calls':
                    result['model_calls'] = limits['max_model_calls'] + 1
                elif mode == 'tokens':
                    result['tokens'] = limits['max_tokens'] + 1
                elif mode == 'mixed':
                    clock[0] += 2.
                    result['tokens'] = limits['max_tokens'] + 1
                if changes:
                    result.update(changes)
            return result
        original_load = skillopt._load_upstream
        def load(source):
            consolidate, *rest = original_load(source)
            def delayed(*args, **kwargs):
                value = consolidate(*args, **kwargs)
                if mode == 'finalization':
                    clock[0] += 200.
                return value
            return delayed, *rest
        with patch.object(skillopt, 'time', SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(skillopt, '_load_upstream', side_effect=load):
            return skillopt.SkillOptLearner(rollouts_k=2).update('seed', tasks,
                lambda p, l: callback('target', p, l), lambda p, l: callback('optimizer', p, l),
                current_day=7, budget=budget or skillopt.LearningBudget(
                    max_target_model_calls=200, max_tokens=4000000, max_seconds=100,
                    replay_seconds=1, optimizer_seconds=1))

    def test_known_target_and_optimizer_timing_stops_are_symmetric_without_fabricated_score(self):
        for kind, target_count, score_count in (('target', 1, 0), ('optimizer', 8, 8)):
            for mode in ('wall', 'latency'):
                with self.subTest(kind=kind, mode=mode):
                    result = self.simulate(kind=kind, mode=mode)
                    self.assertEqual(result['learning_evidence_version'], 2)
                    self.assertFalse(result['accepted'])
                    self.assertEqual(result['skill'], 'seed')
                    self.assertTrue(result['costs']['accounting_complete'])
                    self.assertEqual(result['costs']['replays'], target_count)
                    self.assertEqual(len(result['replay_evidence']), score_count)
                    identities = reconcile(result)
                    self.assertEqual(len(identities), target_count)
                    gate_check(result)
                    if kind == 'target':
                        self.assertFalse(identities[-1]['score_consumed'])
                        self.assertNotIn('hard', identities[-1])
                        self.assertNotIn('soft', identities[-1])
                    self.assertEqual(result['costs']['tokens'], 5 * len(result['costs']['operations']))

    def test_explicit_optimizer_budget_latency_is_accounted_but_failed_callback_is_rejected(self):
        valid = self.simulate(kind='optimizer', changes={'status': 'budget_exhausted'})
        reconcile(valid)
        for kind in ('target', 'optimizer'):
            invalid = self.simulate(kind=kind, changes={'status': 'failed'})
            self.assertFalse(invalid['accepted'])
            self.assertEqual(invalid['status'], 'failed')
            with self.assertRaises(ValueError):
                reconcile(invalid)

    def test_physical_and_mixed_overruns_are_never_a_valid_timing_stop(self):
        for kind in ('target', 'optimizer'):
            for mode in ('calls', 'tokens', 'mixed'):
                result = self.simulate(kind=kind, mode=mode)
                self.assertFalse(result['accepted'])
                self.assertTrue(result['costs']['accounting_complete'])
                with self.assertRaisesRegex(ValueError, 'physical_budget'):
                    reconcile(result)

    def test_missing_receipt_dimensions_retain_each_known_cost_and_unknown_reservation(self):
        for missing in ('tokens', 'model_calls', 'tool_calls'):
            result = self.simulate(mode='none', changes={missing: None})
            row = result['costs']['operations'][0]
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(result['accepted'])
            self.assertFalse(result['costs']['accounting_complete'])
            self.assertIsNone(row['reported_usage'][missing])
            self.assertEqual(row['tokens'], row['limits']['max_tokens'] if missing == 'tokens' else 5)
            self.assertEqual(row['model_calls'], row['limits']['max_model_calls'] if missing == 'model_calls' else 1)
            with self.assertRaisesRegex(ValueError, 'incomplete_operation_accounting'):
                reconcile(result)
        result = self.simulate(mode='none', changes={'latency_ms': None})
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['costs']['tokens'], 5)
        self.assertTrue(result['costs']['accounting_complete'])  # Costs known; timing invalid.
        with self.assertRaises((ValueError, KeyError)):
            reconcile(result)

    def test_terminal_identity_omission_extra_score_middle_operation_and_adoption_tampering_fail(self):
        original = self.simulate()
        mutations = [
            lambda r: r.update(accepted=True),
            lambda r: r.update(skill='forged'),
            lambda r: r.update(skill_after_sha256='0' * 64),
            lambda r: r.update(unscored_replay_evidence=[]),
            lambda r: r['unscored_replay_evidence'][0].update(phase='train'),
            lambda r: r['unscored_replay_evidence'][0].update(skill_sha256='0' * 64),
            lambda r: r['unscored_replay_evidence'][0].update(hard=1.),
            lambda r: r['replay_evidence'].append(deepcopy(r['unscored_replay_evidence'][0])),
            lambda r: r['costs']['operations'].append(deepcopy(r['costs']['operations'][0])),
        ]
        for mutate in mutations:
            result = deepcopy(original); mutate(result)
            with self.assertRaises((ValueError, KeyError)):
                reconcile(result)

    def test_predispatch_stop_has_complete_prefix_and_explicit_reason(self):
        budget = skillopt.LearningBudget(max_target_model_calls=1, max_seconds=100)
        result = self.simulate(mode='none', budget=budget)
        self.assertEqual(result['costs']['stop_evidence']['stage'], 'pre_dispatch')
        self.assertEqual(result['costs']['stop_evidence']['reason'], 'model_calls')
        self.assertEqual(len(reconcile(result)), 1)
        self.assertEqual(result['unscored_replay_evidence'], [])
        forged = deepcopy(result); forged['costs']['stop_evidence']['remaining_model_calls'] = 1
        with self.assertRaisesRegex(ValueError, 'predispatch_remaining'):
            reconcile(forged)

    def test_epoch_expiry_after_final_consolidation_still_cannot_adopt(self):
        result = self.simulate(mode='finalization')
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['costs']['stop_evidence']['stage'], 'post_consolidation')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['skill'], 'seed')
        self.assertEqual(result['unscored_replay_evidence'], [])
        self.assertEqual(len(reconcile(result)), 12)
        gate_check(result)

    def test_late_final_target_stop_rolls_back_tentatively_accepted_candidate(self):
        result = self.simulate(mode='wall', stop_phase='final_val')
        self.assertEqual(len(result['replay_evidence']), 10)
        self.assertEqual(result['costs']['replays'], 11)
        terminal = result['unscored_replay_evidence'][0]
        self.assertEqual(terminal['phase'], 'final_val')
        self.assertEqual(terminal['attempt_index'], 10)
        self.assertNotEqual(terminal['skill_sha256'], result['skill_before_sha256'])
        self.assertNotEqual(terminal['attempt_index'], result['costs']['stop_evidence']['operation_index'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['skill'], 'seed')
        self.assertEqual(len(reconcile(result)), 11)
        gate_check(result)

    def test_normal_completed_upstream_adoption_is_unchanged(self):
        result = self.simulate(mode='none')
        self.assertTrue(result['accepted'])
        self.assertIsNone(result['costs']['stop_evidence'])
        self.assertEqual(len(reconcile(result)), 12)
        gate_check(result)

    def test_clock_scope_and_epoch_clock_tampering_are_rejected(self):
        result = self.simulate()
        result['costs']['operations'][0]['wall_seconds'] = .1
        result['costs']['operations'][0]['budget_violations'] = ['receipt_latency_ms']
        result['costs']['stop_evidence']['violations'] = ['receipt_latency_ms']
        with self.assertRaisesRegex(ValueError, 'latency_outside_callback'):
            reconcile(result)
        for mutate in (
            lambda r: r['costs'].update(wall_seconds=-1.),
            lambda r: r['costs'].update(decision_elapsed_seconds=1000.),
            lambda r: r['costs']['operations'][1]['limits'].update(remaining_seconds=101.),
        ):
            result = self.simulate(mode='none'); mutate(result)
            with self.assertRaises(ValueError):
                reconcile(result)


if __name__ == '__main__':
    unittest.main()
