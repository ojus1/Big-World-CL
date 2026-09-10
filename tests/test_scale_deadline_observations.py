"""Offline ledger/latency fixtures; no native calls or model-quality evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lifespan.evaluation.skillopt import DEFAULT_SOURCE, LearningBudget, SkillOptLearner
from scripts.scale_deadline_observations import observe_campaign, summarize_update


def operation(kind='target', **changes):
    return {'kind': kind, 'accounting': 'reported', 'status': 'completed', 'model_calls': 1, 'tokens': 20,
        'wall_seconds': .5, 'latency_ms': 400.,
        'limits': {'max_model_calls': 16, 'max_tokens': 250000, 'timeout_seconds': 1.}, **changes}


def update(ops, *, status='budget_exhausted', scored=None):
    targets = sum(isinstance(row, dict) and row.get('kind') == 'target' for row in ops)
    return {'employee': 'firm-0__incident-regulated', 'day': 7, 'status': status,
        'costs': {'operations': ops, 'replays': targets, 'accounting_complete': True},
        'replay_evidence': [{} for _ in range(targets if scored is None else scored)],
        'replay_artifacts': [{} for _ in range(targets)]}


class DeadlineObservationTests(unittest.TestCase):
    def test_valid_predispatch_exhaustion_is_distinct_from_overrun(self):
        for rows in ([], [operation()]):
            result = summarize_update(update(rows))
            self.assertEqual(result['stop_classification'], 'pre_dispatch_stop_consistent')
            self.assertEqual(result['post_dispatch_budget_exceeded_operations'], 0)
            self.assertFalse(result['replay_count_disagreement'])
            self.assertIsNone(result['physical_inference_seconds'])

    def test_cleanup_inclusive_wall_overrun_does_not_imply_physical_cap_violation(self):
        result = summarize_update(update([operation(wall_seconds=2., status='budget_exceeded')], scored=0))
        self.assertEqual(result['callback_wall_overruns'], 1)
        self.assertEqual(result['receipt_latency_overruns'], 0)
        self.assertEqual(result['time_overruns_without_recorded_call_or_token_overrun'], 1)
        self.assertEqual(result['reported_physical_call_cap_overruns'], 0)
        self.assertEqual(result['reported_physical_token_cap_overruns'], 0)
        self.assertEqual(result['dispatched_minus_scored'], 1)
        self.assertEqual(result['stop_classification'], 'post_dispatch_budget_exceeded')

    def test_call_and_token_caps_are_independent_of_timing_and_each_other(self):
        row = operation(model_calls=17, tokens=250001, status='budget_exceeded')
        result = summarize_update(update([row], scored=0))
        self.assertEqual(result['reported_physical_call_cap_overruns'], 1)
        self.assertEqual(result['reported_physical_token_cap_overruns'], 1)
        self.assertEqual(result['callback_wall_overruns'], 0)
        row['limits']['max_model_calls'] = None
        result = summarize_update(update([row], scored=0))
        self.assertEqual(result['reported_physical_token_cap_overruns'], 1)
        self.assertEqual(result['malformed_records'], 1)
        row['limits']['max_model_calls'] = 16; row['tokens'] = None
        result = summarize_update(update([row], scored=0))
        self.assertEqual(result['reported_physical_call_cap_overruns'], 1)
        self.assertEqual(result['recorded_known_physical_calls'], 17)
        self.assertEqual(result['unknown_cost_records'], 1)

    def test_unknown_reservations_and_malformed_timing_cannot_claim_consistent_stop(self):
        row = operation(accounting='reservation', status='dispatched', model_calls=16, tokens=250000)
        row.pop('wall_seconds'); row.pop('latency_ms')
        result = summarize_update(update([row], scored=0))
        self.assertEqual(result['known_cost_records'], 0)
        self.assertEqual(result['unknown_cost_records'], 1)
        self.assertEqual(result['recorded_known_tokens'], 0)
        self.assertEqual(result['unknown_callback_wall_records'], 1)
        self.assertEqual(result['stop_classification'], 'unresolved')
        for bad in (True, float('nan'), -1, 'PRIVATE_TRACE'):
            result = summarize_update(update([operation(wall_seconds=bad)]))
            self.assertEqual(result['malformed_records'], 1)
            self.assertEqual(result['stop_classification'], 'unresolved')
            self.assertNotIn('PRIVATE_TRACE', json.dumps(result))

    def test_bad_operation_container_and_replay_counter_are_unknown(self):
        data = update([operation()]); data['costs']['replays'] = 99
        result = summarize_update(data)
        self.assertTrue(result['replay_count_disagreement'])
        self.assertEqual(result['stop_classification'], 'unresolved')
        data['costs']['operations'] = None; data['replay_evidence'] = None
        result = summarize_update(data)
        self.assertIsNone(result['dispatched_minus_scored'])
        self.assertIsNone(result['replay_count_disagreement'])
        self.assertEqual(result['malformed_records'], 1)
        self.assertEqual(result['stop_classification'], 'unresolved')

    def test_identity_and_free_text_never_pass_through(self):
        data = update([operation()]); data['employee'] = 'PRIVATE_PROMPT'
        with self.assertRaises(ValueError):
            summarize_update(data)
        data = update([operation()]); data['status'] = ['PRIVATE_PROMPT']
        self.assertEqual(summarize_update(data)['update_status'], 'unknown')
        with self.assertRaises(ValueError):
            summarize_update(None)

    def test_readonly_campaign_retains_missing_and_pending_without_trace_export(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); run = root / 'runs/seed-211-skillopt'; run.mkdir(parents=True)
            def save(path, value):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
            save(root / 'campaign.json', {'source_sha256': {}, 'slots': [
                {'run_id': 'seed-211-skillopt', 'relative_path': 'runs/seed-211-skillopt'},
                {'run_id': 'seed-211-no_learning', 'relative_path': 'runs/seed-211-no_learning'}]})
            save(run / 'checkpoint.json', {'ecosystem': {'day': 7}, 'runner': {'updates': [update([operation()])]}})
            save(run / 'learning/d011-firm-0__incident-regulated/progress.json', {
                'employee': 'firm-0__incident-regulated', 'day': 11, 'status': 'running',
                'replay_artifacts': [{'usage_known': True, 'private': 'PRIVATE_TRACE'}, {'usage_known': False}],
                'optimizer_dispatches': [], 'private': 'PRIVATE_TRACE'})
            before = {str(p): p.read_bytes() for p in root.rglob('*.json')}
            result = observe_campaign(root)
            self.assertTrue(result['ok'])
            self.assertFalse(result['worlds'][1]['checkpoint_present'])
            self.assertEqual(result['totals']['pending_learning_progress_records'], 1)
            self.assertEqual(result['worlds'][0]['checkpoint_sha256'], hashlib.sha256((run / 'checkpoint.json').read_bytes()).hexdigest())
            text = json.dumps(result)
            self.assertNotIn('PRIVATE_TRACE', text); self.assertNotIn(name, text)
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*.json')})


@unittest.skipUnless((DEFAULT_SOURCE / 'skillopt_sleep/consolidate.py').exists(), 'Pinned upstream not installed')
class ActualUpstreamStopTests(unittest.TestCase):
    def simulate(self, overrun):
        experiences = [{'id': f'{split}-{i}', 'split': split, 'available_day': 0,
            'feedback_available_day': 0, 'source_session': f'{split}-{i}',
            'prompt': f'Offline {split} task {i}', 'context': 'No native evidence'}
            for split in ('train', 'val') for i in range(2)]
        def replay(payload, limits):
            return {'status': 'completed', 'hard': 0., 'soft': 0., 'response': 'offline unsuccessful fixture',
                'feedback': 'offline feedback', 'tokens': 1, 'model_calls': 1, 'tool_calls': 0,
                'latency_ms': 2000. if overrun == 'target' else 0.}
        def reflect(payload, limits):
            return {'status': 'completed', 'response': '[]', 'tokens': 1, 'model_calls': 1,
                    'tool_calls': 0, 'latency_ms': 2000. if overrun == 'optimizer' else 0.}
        result = SkillOptLearner(rollouts_k=2).update('Offline seed skill', experiences, replay, reflect,
            current_day=7, budget=LearningBudget(max_target_model_calls=1 if overrun == 'predispatch' else 200,
                max_optimizer_model_calls=4, max_tokens=4000000, max_seconds=100,
                replay_seconds=1, optimizer_seconds=1))
        result.update(employee='firm-0__incident-regulated', day=7,
                      replay_artifacts=[{'fixture': 'placeholder only'}] * result['costs']['replays'])
        return result, summarize_update(result)

    def test_postdispatch_target_and_optimizer_branches_have_different_scored_prefixes(self):
        for kind, dispatched, scored in (('target', 1, 0), ('optimizer', 8, 8)):
            native, result = self.simulate(kind)
            self.assertEqual(native['status'], 'budget_exhausted')
            self.assertFalse(native['accepted']); self.assertTrue(native['costs']['accounting_complete'])
            self.assertEqual((result['target_operations'], result['scored_replays']), (dispatched, scored))
            self.assertEqual(result['receipt_latency_overruns'], 1)
            self.assertEqual(result['post_dispatch_budget_exceeded_operations'], 1)
            self.assertEqual(result['reported_physical_call_cap_overruns'], 0)
            self.assertEqual(result['reported_physical_token_cap_overruns'], 0)

    def test_actual_predispatch_budget_stop_retains_complete_scored_prefix(self):
        native, result = self.simulate('predispatch')
        self.assertFalse(native['accepted'])
        self.assertEqual(result['stop_classification'], 'pre_dispatch_stop_consistent')
        self.assertEqual((result['target_operations'], result['scored_replays']), (1, 1))


if __name__ == '__main__':
    unittest.main()
