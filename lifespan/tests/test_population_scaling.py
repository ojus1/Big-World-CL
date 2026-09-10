"""Offline population/kernel invariants; no native actor or quality evidence."""
from copy import deepcopy
import hashlib
import json
import unittest

from lifespan.ecosystem import Ecosystem, WORKFLOWS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class PopulationScalingTests(unittest.TestCase):
    def test_historical_default_checkpoint_is_preserved_exactly(self):
        # Captured from the previous two-enterprise implementation before adding
        # population parameters. Includes all tasks, rules, ledgers and assigned
        # employee metadata, rather than only matching roster counts.
        fixtures = {(16, 7): 'ba8862a77ddf0a09bd8c0ac6a52992ff762999f8f6dc9c2e1ed6ba050fd789f9',
                    (32, 101): 'd2f15bb21d7e436b1ded4a94f27c31cd5bef20cca1607ca7c2fabe70573b3b5d'}
        for (days, seed), expected in fixtures.items():
            eco = Ecosystem(days, seed)
            self.assertEqual(digest(eco.checkpoint()), expected)
            self.assertEqual(eco.checkpoint(), Ecosystem(days, seed, enterprise_count=2, consumer_count=3).checkpoint())

    def test_four_enterprises_twelve_employees_eight_consumers_and_unique_participants(self):
        eco = Ecosystem(32, 101, enterprise_count=4, consumer_count=8)
        self.assertEqual(len(eco.firms), 4)
        self.assertEqual(len(eco.consumers), 8)
        self.assertEqual(sum(len(world.employees) for world in eco.worlds.values()), 12)
        participants = eco.participants()
        self.assertEqual(len(participants), 25)  # 12 employees + 4 firms + agency + 8 consumers.
        self.assertEqual(len({row['id'] for row in participants}), 25)
        self.assertEqual(len({row['name'] for row in eco.firms.values()}), 4)
        for fid, world in eco.worlds.items():
            self.assertEqual({e.workflow for e in world.employees.values()}, set(WORKFLOWS))
            self.assertTrue(all(e.segment == 'regulated' for e in world.employees.values()))
            self.assertEqual(len(world.scheduled), 3)
            self.assertTrue(all(task['customer'] == eco.benchmark_consumer(fid) for task in world.scheduled))

    def test_multi_digit_firms_keep_distinct_accounts_task_owners_and_markets(self):
        eco = Ecosystem(32, 55, enterprise_count=12, consumer_count=24)
        self.assertEqual(eco.benchmark_consumer('firm-10'), 'consumer-10')
        self.assertEqual(eco.benchmark_consumer('firm-11'), 'consumer-11')
        self.assertNotEqual(eco.benchmark_consumer('firm-10'), eco.benchmark_consumer('firm-0'))
        for index in range(12):
            fid = f'firm-{index}'
            consumer = eco.consumers[eco.benchmark_consumer(fid)]
            self.assertEqual(consumer['provider'], fid)
            self.assertEqual(consumer['market'], eco.firms[fid]['target_market'])
            self.assertTrue(6 <= eco.firms[fid]['price'] <= 20)
            for task in eco.worlds[fid].scheduled:
                self.assertTrue(task['id'].startswith(fid + '-order-'))
                self.assertEqual(task['customer'], f'consumer-{index}')
                self.assertEqual(task['owner'], task['workflow'] + '-regulated')
            self.assertEqual({row['firm'] for row in consumer['pending']}, {fid})
        self.assertEqual(len({firm['name'] for firm in eco.firms.values()}), 12)
        for index in range(12, 24):
            self.assertIsNone(eco.consumers[f'consumer-{index}']['provider'])
            self.assertEqual(eco.consumers[f'consumer-{index}']['market'], eco.firms[f'firm-{index % 12}']['target_market'])

    def test_default_consumer_count_scales_to_cover_every_enterprise(self):
        self.assertEqual(len(Ecosystem(enterprise_count=1).consumers), 3)
        self.assertEqual(len(Ecosystem(enterprise_count=4).consumers), 4)
        self.assertEqual(len(Ecosystem(enterprise_count=12).consumers), 12)
        for size in (1, 2, 4, 12):
            eco = Ecosystem(enterprise_count=size)
            self.assertTrue(all(eco.benchmark_consumer(fid) in eco.consumers for fid in eco.firms))

    def test_population_parameters_reject_booleans_floats_and_unfunded_firms(self):
        for count in (True, False, 0, -1, 2.0, '4'):
            with self.assertRaises(ValueError):
                Ecosystem(enterprise_count=count)
        for count in (True, False, 0, -1, 3, 8.0, '8'):
            with self.assertRaises(ValueError):
                Ecosystem(enterprise_count=4, consumer_count=count)
        eco = Ecosystem()
        for identifier in ('firm-10', 'firm-x', 'consumer-0'):
            with self.assertRaises(ValueError):
                eco.benchmark_consumer(identifier)

    def test_old_checkpoint_restore_needs_no_new_metadata_and_can_continue(self):
        original = Ecosystem(32, 101)
        original.advance()
        old = original.checkpoint()
        self.assertNotIn('enterprise_count', old)
        self.assertNotIn('consumer_count', old)
        restored = Ecosystem.restore(deepcopy(old))
        self.assertEqual(restored.checkpoint(), old)
        self.assertEqual(restored.benchmark_consumer('firm-1'), 'consumer-1')
        original.advance()
        restored.advance()
        self.assertEqual(restored.checkpoint(), original.checkpoint())

    def test_scaled_checkpoint_roundtrip_retains_independent_worlds_and_dynamic_views(self):
        original = Ecosystem(32, 204, enterprise_count=12, consumer_count=24)
        original.advance()
        snapshot = original.checkpoint()
        restored = Ecosystem.restore(snapshot)
        self.assertEqual(restored.checkpoint(), snapshot)
        self.assertEqual(len(restored.public_view()['enterprises']), 12)
        self.assertEqual(len(restored.participants()), 73)
        self.assertEqual(restored.actor_view('firm-10')['own_state']['id'], 'firm-10')
        self.assertEqual(restored.actor_view('consumer-23')['own_state']['id'], 'consumer-23')
        restored.worlds['firm-10'].tasks['firm-10-order-0000'].status = 'completed'
        self.assertEqual(original.worlds['firm-10'].tasks['firm-10-order-0000'].status, 'pending')
        self.assertEqual(snapshot['worlds']['firm-10']['tasks']['firm-10-order-0000']['status'], 'pending')
        self.assertEqual(restored.worlds['firm-0'].tasks['firm-0-order-0000'].status, 'pending')

    def test_scaled_enterprise_and_government_decisions_apply_to_correct_worlds(self):
        eco = Ecosystem(32, 204, enterprise_count=12, consumer_count=24)
        eco.advance()
        before = deepcopy(eco.firms['firm-0'])
        decision = {'notes': 'offline fixture', 'reason': 'offline fixture', 'evidence_ids': [],
                    'objective': 'resilience', 'price': 14, 'target_market': 'domestic',
                    'priority_workflow': 'incident', 'procedure': 'alternate_route'}
        eco.apply_decision('firm-10', decision, eco.actor_view('firm-10'))
        self.assertEqual(eco.firms['firm-0'], before)
        self.assertEqual(eco.firms['firm-10']['objective'], 'resilience')
        self.assertEqual(len([r for r in eco.worlds['firm-10'].rules if r.id.startswith('strategy-')]), 3)
        self.assertFalse(any(r.id.startswith('strategy-') for r in eco.worlds['firm-0'].rules))
        eco.apply_decision('agency', {'notes': 'offline fixture', 'reason': 'offline fixture',
            'evidence_ids': [], 'policy': 'enhanced_review', 'duration': 2}, eco.actor_view('agency'))
        self.assertTrue(all(len([r for r in world.rules if r.id.startswith('agency-')]) == 3 for world in eco.worlds.values()))
        eco.advance()
        self.assertEqual(eco.firms['firm-10']['route'], 'alternate_route')
        self.assertEqual(eco.firms['firm-0']['route'], 'standard_route')

    def test_same_seed_is_deterministic_and_distinct_seed_changes_employee_metadata(self):
        first = Ecosystem(32, 101, enterprise_count=4, consumer_count=8)
        second = Ecosystem(32, 101, enterprise_count=4, consumer_count=8)
        other = Ecosystem(32, 102, enterprise_count=4, consumer_count=8)
        self.assertEqual(first.checkpoint(), second.checkpoint())
        self.assertNotEqual(first.worlds['firm-2'].blueprint, other.worlds['firm-2'].blueprint)
        self.assertEqual(set(first.firms), set(other.firms))


if __name__ == '__main__':
    unittest.main()
