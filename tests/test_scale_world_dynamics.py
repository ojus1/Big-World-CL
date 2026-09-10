"""Offline kernel fixtures only; no native agents or benchmark efficacy evidence."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from lifespan.ecosystem import Ecosystem
from scripts import scale_world_dynamics as dynamics

PRIVATE = 'PRIVATE_REASON_NOTE_PERSONA_PROMPT_RESPONSE_SKILL_ARTIFACT'


def decision(eco, actor, **changes):
    if actor.startswith('firm-'):
        value = {key: eco.firms[actor][key] for key in dynamics.FIELDS}
        value['procedure'] = 'keep'
    elif actor == 'agency':
        value = {'policy': 'keep', 'duration': 2}
    else:
        value = {'action': 'wait'}
    value.update(reason=PRIVATE, notes=PRIVATE, evidence_ids=[])
    value.update(changes)
    eco.apply_decision(actor, value, eco.actor_view(actor))


def fixture():
    eco = Ecosystem(days=22, enterprise_count=4, consumer_count=8)
    eco.advance()  # day 0
    decision(eco, 'firm-0')
    decision(eco, 'firm-1', procedure='standard_route')  # installs a rule, same route
    decision(eco, 'agency', policy='enhanced_review')
    decision(eco, 'consumer-0')
    decision(eco, 'consumer-4', action='purchase', firm='firm-0')
    eco.advance()  # day 1, policy + no-op route delivery
    decision(eco, 'firm-0', objective='reliability', price=11, target_market='domestic',
             priority_workflow='incident', procedure='alternate_route')
    decision(eco, 'agency')
    eco.advance()  # day 2, alternate route delivery
    decision(eco, 'firm-0', procedure='standard_route')
    eco.advance()  # day 3, baseline expiry and standard route delivery
    decision(eco, 'agency', policy='baseline')
    eco.advance()  # day 4, baseline same-policy delivery and geopolitical shock
    return {'ecosystem': eco.checkpoint(), 'runner': {'private': PRIVATE}}


class WorldDynamicsTests(unittest.TestCase):
    def test_strategy_decisions_noops_and_delivered_route_changes_are_separate(self):
        result = dynamics.summarize_world_dynamics(fixture())
        self.assertTrue(result['evidence_complete'], result['evidence_issues'])
        firm = result['enterprises'][0]
        self.assertEqual(firm['recorded_decision_opportunities'], 3)
        self.assertEqual(firm['final_state']['strategy_revision'], 3)
        self.assertEqual(firm['strategy_change_events'], 1)
        self.assertEqual(firm['strategy_noop_events'], 2)
        self.assertEqual(firm['field_change_counts'], dict.fromkeys(dynamics.FIELDS, 1))
        self.assertEqual((firm['explicit_procedure_requests'], firm['delivered_route_changes'], firm['delivered_route_noops']), (2, 2, 0))
        self.assertEqual(firm['decisions'][0]['changed_fields'], [])
        other = result['enterprises'][1]
        self.assertEqual((other['explicit_procedure_requests'], other['delivered_route_changes'], other['delivered_route_noops']), (1, 0, 1))

    def test_policy_opportunities_deliveries_renewal_fields_and_expiry_reconcile(self):
        government = dynamics.summarize_world_dynamics(fixture())['government']
        self.assertEqual(government['recorded_decision_opportunities'], 3)
        self.assertEqual([row['policy_request'] for row in government['decisions']], ['enhanced_review', 'keep', 'baseline'])
        self.assertEqual((len(government['deliveries']), len(government['expiries'])), (2, 1))
        self.assertEqual((government['delivered_policy_value_changes'], government['delivered_policy_value_noops']), (1, 1))
        self.assertEqual(government['delivered_policy_record_changes'], 2)
        self.assertEqual(government['expiries'][0]['day'], 3)
        self.assertEqual(government['final_state'], {'policy': 'baseline', 'effective_day': 4, 'expires': None})

    def test_missing_expiry_cannot_be_hidden_by_later_baseline_delivery(self):
        cp = fixture()
        cp['ecosystem']['events'] = [event for event in cp['ecosystem']['events'] if event['kind'] != 'policy_expired']
        result = dynamics.summarize_world_dynamics(cp)
        self.assertFalse(result['evidence_complete'])
        self.assertEqual(result['evidence_issues'], [{'kind': 'missing_policy_expiry', 'expected_day': 3}])

    def test_unreported_expiry_at_final_observation_is_missing_even_without_later_events(self):
        eco = Ecosystem(days=22)
        eco.advance()
        decision(eco, 'agency', policy='enhanced_review')
        eco.advance(); eco.advance()
        cp = eco.checkpoint()
        # A damaged snapshot advances its clock but omits both expiry and the
        # final policy update, so final-state replay alone would falsely agree.
        cp['day'] = 3
        result = dynamics.summarize_world_dynamics(cp)
        self.assertFalse(result['evidence_complete'])
        self.assertEqual(result['evidence_issues'], [{'kind': 'missing_policy_expiry', 'expected_day': 3}])

    def test_same_day_policy_renewal_replaces_expiring_window_before_expiry_stage(self):
        eco = Ecosystem(days=22)
        eco.advance()
        decision(eco, 'agency', policy='enhanced_review')  # delivers day1, expires day3
        eco.advance(); eco.advance()
        decision(eco, 'agency', policy='enhanced_review', duration=3)
        eco.advance()  # day3 renewal delivers first; old window does not expire
        result = dynamics.summarize_world_dynamics(eco.checkpoint())
        self.assertTrue(result['evidence_complete'], result['evidence_issues'])
        self.assertEqual(result['government']['expiries'], [])
        self.assertEqual(result['government']['delivered_policy_value_changes'], 1)
        self.assertEqual(result['government']['delivered_policy_value_noops'], 1)
        self.assertEqual(result['government']['final_state']['expires'], 6)

    def test_exogenous_shocks_and_endogenous_orders_are_grounded_not_id_inferred(self):
        result = dynamics.summarize_world_dynamics(fixture())
        shock = result['geopolitics']['exogenous_shock_events'][0]
        self.assertEqual((shock['day'], shock['source']), (4, 'exogenous_environment_schedule'))
        self.assertEqual(shock['changed_fields'], ['corridor', 'supply_delay'])
        self.assertEqual(result['endogenous_order_count'], 1)
        own = next(row for row in result['consumers'] if row['consumer'] == 'consumer-4')
        self.assertEqual(own['action_counts']['purchase'], 1)
        self.assertEqual(len(own['endogenous_orders']), 1)
        self.assertEqual(own['endogenous_orders'][0]['enterprise'], 'firm-0')
        self.assertEqual(own['endogenous_orders'][0]['workflow'], 'onboarding')
        self.assertEqual(result['consumers'][0]['action_counts']['wait'], 1)

    def test_all_entities_including_full_numeric_ids_and_untouched_firms_remain(self):
        eco = Ecosystem(days=22, enterprise_count=12, consumer_count=24)
        eco.advance()
        decision(eco, 'firm-10', objective='resilience')
        result = dynamics.summarize_world_dynamics(eco.checkpoint())
        self.assertEqual(len(result['enterprises']), 12)
        self.assertEqual(len(result['consumers']), 24)
        self.assertEqual(result['enterprises'][10]['enterprise'], 'firm-10')
        self.assertEqual(result['enterprises'][10]['field_change_counts']['objective'], 1)
        self.assertEqual(result['enterprises'][0]['recorded_decision_opportunities'], 0)
        self.assertTrue(result['evidence_complete'])

    def test_pending_delivery_is_not_prematurely_counted_as_effective_route_change(self):
        eco = Ecosystem(days=22)
        eco.advance()
        decision(eco, 'firm-0', procedure='alternate_route')
        decision(eco, 'agency', policy='enhanced_review')
        result = dynamics.summarize_world_dynamics(eco.checkpoint())
        self.assertTrue(result['evidence_complete'])
        self.assertEqual(result['enterprises'][0]['explicit_procedure_requests'], 1)
        self.assertEqual(result['enterprises'][0]['delivered_route_changes'], 0)
        self.assertEqual(result['government']['delivered_policy_value_changes'], 0)
        self.assertEqual(len(result['pending_policy_or_route_deliveries']), 2)
        self.assertEqual(result['enterprises'][0]['final_state']['route'], 'standard_route')

    def test_pending_payload_cannot_diverge_from_the_authoritative_request(self):
        eco = Ecosystem(days=22)
        eco.advance()
        decision(eco, 'firm-0', procedure='alternate_route')
        decision(eco, 'agency', policy='enhanced_review')
        cp = eco.checkpoint()
        cp['queue'][0]['payload']['route'] = 'standard_route'
        with self.assertRaisesRegex(ValueError, 'pending_route_payload'):
            dynamics.summarize_world_dynamics(cp)
        cp = eco.checkpoint()
        cp['queue'][1]['payload']['expires'] = 100
        with self.assertRaisesRegex(ValueError, 'pending_policy_payload'):
            dynamics.summarize_world_dynamics(cp)

    def test_signed_synthetic_balance_is_reported_without_inventing_a_kernel_mechanism(self):
        cp = fixture()
        cp['ecosystem']['consumers']['consumer-0']['budget'] = -24.5
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual(result['consumers'][0]['final_state']['budget'], -24.5)
        self.assertTrue(result['evidence_complete'])
        self.assertIn('signed synthetic balances', result['interpretation'])
        self.assertIn('reporting robustness only', result['interpretation'])

    def test_missing_event_stream_is_unknown_not_zero(self):
        checkpoint = fixture()
        del checkpoint['ecosystem']['events']
        result = dynamics.summarize_world_dynamics(checkpoint)
        self.assertFalse(result['evidence_complete'])
        self.assertFalse(result['event_history_present'])
        self.assertEqual(result['evidence_issues'], [{'kind': 'missing_event_stream'}])
        self.assertIsNone(result['enterprises'][0]['recorded_decision_opportunities'])
        self.assertIsNone(result['government']['delivered_policy_value_changes'])
        self.assertIsNone(result['endogenous_order_count'])
        self.assertEqual(len(result['enterprises']), 4)

    def test_before_after_final_state_and_revision_mismatches_are_explicit(self):
        cp = fixture()
        firm_events = [event for event in cp['ecosystem']['events'] if event['kind'] == 'enterprise_decision' and event['actor'] == 'firm-0']
        firm_events[1]['payload']['before']['price'] = 19
        cp['ecosystem']['firms']['firm-0']['price'] = 18
        cp['ecosystem']['firms']['firm-1']['strategy_revision'] = 5
        cp['ecosystem']['firms']['firm-2']['route'] = 'alternate_route'
        result = dynamics.summarize_world_dynamics(cp)
        self.assertFalse(result['evidence_complete'])
        self.assertEqual({row['kind'] for row in result['evidence_issues']}, {
            'enterprise_before_state_mismatch', 'enterprise_final_state_mismatch',
            'enterprise_strategy_revision_mismatch', 'enterprise_final_route_mismatch'})

    def test_missing_first_decision_cannot_hide_a_changed_initial_or_final_strategy(self):
        eco = Ecosystem(days=22)
        eco.advance()
        cp = eco.checkpoint()
        cp['firms']['firm-0']['objective'] = 'resilience'
        result = dynamics.summarize_world_dynamics(cp)
        self.assertFalse(result['evidence_complete'])
        self.assertEqual(result['evidence_issues'], [{'kind': 'enterprise_final_state_mismatch', 'enterprise': 'firm-0'}])

    def test_final_government_and_geopolitical_state_mismatches_are_explicit(self):
        cp = fixture()
        cp['ecosystem']['agency']['effective_day'] = 19
        cp['ecosystem']['geopolitics']['supply_delay'] = 9
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual({row['kind'] for row in result['evidence_issues']}, {
            'government_final_policy_mismatch', 'geopolitical_final_state_mismatch'})

    def test_shocks_bind_exactly_to_configured_or_default_schedule(self):
        cp = fixture()
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual(result['geopolitics']['schedule_source'], 'frozen_kernel_default')
        self.assertEqual(result['geopolitics']['expected_shocks_through_observation'], [
            {'day': 4, 'corridor': 'disrupted', 'supply_delay': 2}])
        shock = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'geopolitical_shock')
        shock['payload']['supply_delay'] = 99
        cp['ecosystem']['geopolitics']['supply_delay'] = 99
        result = dynamics.summarize_world_dynamics(cp)
        self.assertFalse(result['evidence_complete'])
        self.assertEqual(result['evidence_issues'], [{'kind': 'geopolitical_schedule_event_mismatch'}])
        cp = fixture()
        cp['ecosystem']['events'] = [event for event in cp['ecosystem']['events'] if event['kind'] != 'geopolitical_shock']
        cp['ecosystem']['geopolitics'] = {'corridor': 'open', 'supply_delay': 0, 'revision': 0}
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual(result['evidence_issues'], [{'kind': 'geopolitical_schedule_event_mismatch'}])
        eco = Ecosystem(days=22)
        eco.shock_schedule = [{'day': 1, 'corridor': 'disrupted', 'supply_delay': 3}]
        eco.advance(); eco.advance()
        result = dynamics.summarize_world_dynamics(eco.checkpoint())
        self.assertTrue(result['evidence_complete'])
        self.assertEqual(result['geopolitics']['schedule_source'], 'checkpoint_shock_schedule')
        self.assertEqual(result['geopolitics']['exogenous_shock_events'][0]['after']['supply_delay'], 3)

    def test_missing_order_history_or_missing_order_emission_is_not_hidden(self):
        cp = fixture()
        cp['ecosystem']['consumers']['consumer-4']['history'] = []
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual(result['endogenous_order_count'], 1)
        self.assertIn('endogenous_order_history_mismatch', {row['kind'] for row in result['evidence_issues']})
        cp['ecosystem']['events'] = [event for event in cp['ecosystem']['events'] if not (event['kind'] == 'order_placed' and event['actor'] == 'consumer-4')]
        result = dynamics.summarize_world_dynamics(cp)
        self.assertEqual(result['endogenous_order_count'], 0)
        self.assertIn('consumer_purchase_order_count_mismatch', {row['kind'] for row in result['evidence_issues']})

    def test_wrong_order_causal_actor_enterprise_or_date_is_rejected(self):
        for key, value in (('actor', 'consumer-5'), ('day', 1)):
            cp = fixture()
            event = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'order_placed' and event['actor'] == 'consumer-4')
            event[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                dynamics.summarize_world_dynamics(cp)
        cp = fixture()
        event = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'consumer_decision' and event['actor'] == 'consumer-4')
        event['payload']['firm'] = 'firm-2'
        with self.assertRaisesRegex(ValueError, 'order_binding'):
            dynamics.summarize_world_dynamics(cp)

    def test_wrong_delivery_parent_or_policy_expiry_is_rejected(self):
        cp = fixture()
        event = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'enterprise_route_delivered')
        event['payload']['route'] = 'alternate_route'
        with self.assertRaisesRegex(ValueError, 'route_delivery_binding'):
            dynamics.summarize_world_dynamics(cp)
        cp = fixture()
        event = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'policy_delivered')
        event['payload']['expires'] = 99
        with self.assertRaisesRegex(ValueError, 'policy_delivery_binding'):
            dynamics.summarize_world_dynamics(cp)
        cp = fixture()
        expiry = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'policy_expired')
        expiry['day'] = 4
        cp['ecosystem']['events'].sort(key=lambda event: event['day'])
        with self.assertRaisesRegex(ValueError, 'policy_expiry_without_active_window'):
            dynamics.summarize_world_dynamics(cp)

    def test_consumer_final_scalar_scope_does_not_claim_payment_or_balance_replay(self):
        cp = fixture()
        cp['ecosystem']['consumers']['consumer-4']['provider'] = 'firm-2'
        result = dynamics.summarize_world_dynamics(cp)
        own = next(row for row in result['consumers'] if row['consumer'] == 'consumer-4')
        self.assertEqual(own['final_state']['provider'], 'firm-2')
        self.assertEqual(own['final_state_reconciliation'], 'observed_checkpoint_scalars_not_independently_replayed')
        self.assertEqual(result['consumer_final_state_validation'], 'type_and_identity_only_no_payment_balance_or_satisfaction_replay')
        self.assertIn('not independently replayed', result['interpretation'])

    def test_malformed_unknown_values_duplicate_events_and_nonfinite_data_rejected(self):
        for value in (True, float('nan'), float('inf'), PRIVATE):
            cp = fixture()
            cp['ecosystem']['firms']['firm-0']['price'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                dynamics.summarize_world_dynamics(cp)
        cp = fixture()
        cp['ecosystem']['events'].append(cp['ecosystem']['events'][-1])
        with self.assertRaisesRegex(ValueError, 'event_identity'):
            dynamics.summarize_world_dynamics(cp)
        cp = fixture()
        event = next(event for event in cp['ecosystem']['events'] if event['kind'] == 'enterprise_decision')
        event['payload'] = PRIVATE
        with self.assertRaisesRegex(ValueError, 'malformed_recognized'):
            dynamics.summarize_world_dynamics(cp)

    def test_summary_is_pure_safe_and_explicitly_not_a_new_primary_endpoint(self):
        checkpoint = fixture()
        before = deepcopy(checkpoint)
        result = dynamics.summarize_world_dynamics(checkpoint)
        text = json.dumps(result)
        self.assertNotIn(PRIVATE, text)
        self.assertNotIn('reason', text)
        self.assertNotIn('notes', text)
        self.assertNotIn('persona', text)
        self.assertEqual(checkpoint, before)
        self.assertIn('not_preregistered_endpoint', result['analysis_registration'])

    def test_cli_hashes_exact_bytes_excludes_absolute_paths_and_fails_on_missing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.json'
            raw = (json.dumps(fixture(), indent=4) + '\n').encode()
            path.write_bytes(raw)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = dynamics.main([str(path)])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result['input_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['input_hash_encoding'], 'sha256_raw_file_bytes')
            self.assertNotIn(directory, output.getvalue())
            self.assertNotIn(PRIVATE, output.getvalue())
            cp = fixture()
            del cp['ecosystem']['events']
            path.write_text(json.dumps(cp))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(dynamics.main([str(path)]), 1)


if __name__ == '__main__':
    unittest.main()
