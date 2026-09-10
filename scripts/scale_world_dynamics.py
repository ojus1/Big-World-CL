#!/usr/bin/env python3
"""Allowlisted, descriptive trajectories from a persistent ecosystem checkpoint.

``summarize_world_dynamics(checkpoint)`` accepts either an evaluation checkpoint
with ``ecosystem`` or an Ecosystem.checkpoint() mapping. It returns every firm
and consumer identity, final scalar states, accepted decision-event counts and
safe event trajectories. It never exports reasons, notes, personas, requests,
responses, rules, work artifacts, or the private decision views.

Decision opportunities here mean *recorded, accepted kernel decision events*;
the checkpoint cannot count interviews that were never accepted. Strategy
revision increments on no-ops. Before/after strategy changes, explicit procedure
requests, and delivered route changes are therefore separate measures. Route
and government replay start from the frozen kernel's initial strategy,
standard-route and baseline-policy conditions, and reconcile with final state. A route request can
install rules and incur costs even when its delivered route value is unchanged.

Missing event history is unknown, never zero activity. Malformed recognized
evidence raises ValueError; reconciliation issues mark evidence_complete false.
Consumer orders are endogenous only when joined to the same consumer's purchase
or switch decision by exact cause, enterprise and day, and to ordered history.
Consumer actions are intents: a provider changes only after successful payment.
Consumer final scalars are validated for type/identity and reported as observed;
payments, balances and satisfaction are not independently replayed here.
Consumer budgets are reported as signed finite synthetic balances for faithful
reporting and robustness; this does not assert that valid kernel execution can
create an overdraft. Every order checks unreserved affordability. The evaluation
runner initializes balances to 10,000; the base Ecosystem uses 160.
This is a during-execution descriptive addition, not a preregistered endpoint or
causal efficacy estimate. The CLI hashes exact input bytes and writes stdout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

VERSION = 'scale-world-dynamics-v1'
FIELDS = ('objective', 'price', 'target_market', 'priority_workflow')
OBJECTIVES = ('growth', 'reliability', 'resilience', 'cost_control')
WORKFLOWS = ('onboarding', 'renewal', 'incident')
ROUTES = ('standard_route', 'alternate_route')
POLICIES = ('baseline', 'enhanced_review')
KINDS = {'enterprise_decision', 'enterprise_route_delivered', 'government_decision',
         'policy_delivered', 'policy_expired', 'geopolitical_shock', 'consumer_decision', 'order_placed'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid_integer')
    return value


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid_number')
    return value


def choice(value, values):
    require(value in values and type(value) is str, 'invalid_enum')
    return value


def strategy(raw):
    value = {'objective': choice(raw['objective'], OBJECTIVES), 'price': number(raw['price']),
        'target_market': choice(raw['target_market'], ('domestic', 'cross_border')),
        'priority_workflow': choice(raw['priority_workflow'], WORKFLOWS)}
    require(6 <= value['price'] <= 20, 'invalid_price')
    return value


def identity(value, prefix):
    require(type(value) is str and re.fullmatch(prefix + r'-[0-9]+', value), 'invalid_entity_identity')
    return value


def _events(eco, day):
    raw = eco.get('events')
    if raw is None:
        return None
    require(type(raw) is list, 'malformed_event_stream')
    result, ids, previous = [], set(), -1
    for event in raw:
        require(type(event) is dict and type(event.get('id')) is str
                and re.fullmatch(r'event-[0-9]+', event['id']) and event['id'] not in ids, 'invalid_event_identity')
        event_day = integer(event['day'], -1)
        require(previous <= event_day <= day and type(event.get('kind')) is str, 'invalid_event_chronology')
        ids.add(event['id']); previous = event_day
        if event['kind'] in KINDS:
            require(type(event.get('payload')) is dict and type(event.get('causes')) is list
                    and all(type(value) is str for value in event['causes']), 'malformed_recognized_event')
        result.append(event)
    return result


def _summarize_world_dynamics(checkpoint):
    eco = checkpoint.get('ecosystem', checkpoint)
    day = integer(eco['day'], -1)
    firms, consumers = eco['firms'], eco['consumers']
    require(type(firms) is dict and bool(firms) and type(consumers) is dict, 'missing_entity_roster')
    firm_ids = sorted((identity(fid, 'firm') for fid in firms), key=lambda fid: int(fid[5:]))
    consumer_ids = sorted((identity(cid, 'consumer') for cid in consumers), key=lambda cid: int(cid[9:]))
    require(all(firms[fid]['id'] == fid for fid in firm_ids)
            and all(consumers[cid]['id'] == cid for cid in consumer_ids), 'entity_state_identity_mismatch')
    agency = eco['agency']
    require(agency['id'] == 'agency', 'unknown_government_identity')
    final_policy = {'policy': choice(agency['policy'], POLICIES), 'effective_day': integer(agency['effective_day']),
        'expires': None if agency['expires'] is None else integer(agency['expires'])}
    geo = eco['geopolitics']
    final_geo = {'corridor': choice(geo['corridor'], ('open', 'disrupted')),
        'supply_delay': integer(geo['supply_delay']), 'revision': integer(geo['revision'])}
    schedule = eco.get('shock_schedule', [{'day': 4, 'corridor': 'disrupted', 'supply_delay': 2},
                                         {'day': 11, 'corridor': 'open', 'supply_delay': 0}])
    require(type(schedule) is list, 'malformed_shock_schedule')
    safe_schedule = [{'day': integer(row['day']), 'corridor': choice(row['corridor'], ('open', 'disrupted')),
                      'supply_delay': integer(row['supply_delay'])} for row in schedule]
    require([row['day'] for row in safe_schedule] == sorted({row['day'] for row in safe_schedule}), 'invalid_shock_schedule_days')
    expected_shocks = [row for row in safe_schedule if row['day'] <= day]
    events = _events(eco, day)
    known = events is not None
    events = events or []
    by_id = {event['id']: event for event in events}
    issues = [] if known else [{'kind': 'missing_event_stream'}]
    observed_strategy = {fid: {'objective': 'growth', 'price': 10 + (int(fid[5:]) % 6) * 2,
        'target_market': 'cross_border' if int(fid[5:]) % 2 == 0 else 'domestic',
        'priority_workflow': 'onboarding'} for fid in firm_ids}
    firm_rows, routes, revised = {}, {fid: 'standard_route' for fid in firm_ids}, Counter()
    for fid in firm_ids:
        final = {**strategy(firms[fid]), 'route': choice(firms[fid]['route'], ROUTES),
                 'strategy_revision': integer(firms[fid]['strategy_revision'])}
        firm_rows[fid] = {'enterprise': fid, 'final_state': final,
            'recorded_decision_opportunities': 0 if known else None,
            'strategy_change_events': 0 if known else None, 'strategy_noop_events': 0 if known else None,
            'field_change_counts': {key: 0 if known else None for key in FIELDS},
            'explicit_procedure_requests': 0 if known else None,
            'delivered_route_changes': 0 if known else None, 'delivered_route_noops': 0 if known else None,
            'decisions': [], 'route_deliveries': []}
    consumer_rows = {}
    for cid in consumer_ids:
        raw = consumers[cid]
        require(raw['provider'] is None or raw['provider'] in firms, 'unknown_consumer_provider')
        satisfaction, budget = number(raw['satisfaction']), number(raw['budget'])
        require(0 <= satisfaction <= 1 and type(raw['pending']) is list, 'invalid_consumer_state')
        consumer_rows[cid] = {'consumer': cid, 'final_state': {'provider': raw['provider'],
            'market': choice(raw['market'], ('domestic', 'cross_border')), 'satisfaction': satisfaction,
            'budget': budget, 'pending_orders': len(raw['pending'])},
            'final_state_reconciliation': 'observed_checkpoint_scalars_not_independently_replayed',
            'recorded_decision_opportunities': 0 if known else None,
            'action_counts': {key: 0 if known else None for key in ('wait', 'purchase', 'switch', 'complain')},
            'endogenous_orders': []}
    government = {'government': 'agency', 'final_state': final_policy,
        'recorded_decision_opportunities': 0 if known else None, 'decisions': [], 'deliveries': [], 'expiries': [],
        'delivered_policy_value_changes': 0 if known else None, 'delivered_policy_value_noops': 0 if known else None,
        'delivered_policy_record_changes': 0 if known else None}
    shocks, endogenous_orders = [], []
    policy_state = {'policy': 'baseline', 'effective_day': 0, 'expires': None}
    geo_state = {'corridor': 'open', 'supply_delay': 0, 'revision': 0}
    delivered, native_orders = set(), set()
    missing_expiries = set()

    def note_missing_expiry():
        window = (policy_state['effective_day'], policy_state['expires'])
        if window not in missing_expiries:
            issues.append({'kind': 'missing_policy_expiry', 'expected_day': policy_state['expires']})
            missing_expiries.add(window)

    def parent(event, kind):
        require(len(event['causes']) == 1, 'ambiguous_delivery_or_order_cause')
        source = by_id.get(event['causes'][0])
        require(source is not None and source['kind'] == kind
                and source['id'] in processed, 'missing_or_future_cause')
        return source

    processed = set()
    for event in events:
        eid, when, kind, actor = event['id'], event['day'], event['kind'], event.get('actor')
        # advance() delivers queued policies before expiring the current window.
        # A renewal delivered on the expiry day is valid; a later event cannot
        # erase evidence that the previous window should already have expired.
        if policy_state['expires'] is not None and policy_state['expires'] < when:
            note_missing_expiry()
        payload = event.get('payload')
        metadata = {'event_id': eid, 'day': when}
        if kind == 'enterprise_decision':
            require(actor in firms, 'unknown_enterprise_actor')
            before, after = strategy(payload['before']), strategy(payload['after'])
            procedure = choice(payload['procedure'], ('keep', *ROUTES))
            if actor in observed_strategy and before != observed_strategy[actor]:
                issues.append({'kind': 'enterprise_before_state_mismatch', 'enterprise': actor, 'event_id': eid})
            observed_strategy[actor] = after
            revised[actor] += 1
            row = firm_rows[actor]
            changed = [key for key in FIELDS if before[key] != after[key]]
            row['recorded_decision_opportunities'] += 1
            row['strategy_change_events' if changed else 'strategy_noop_events'] += 1
            for key in changed:
                row['field_change_counts'][key] += 1
            row['explicit_procedure_requests'] += procedure != 'keep'
            row['decisions'].append({**metadata, 'before': before, 'after': after, 'changed_fields': changed, 'procedure_request': procedure})
        elif kind == 'enterprise_route_delivered':
            source = parent(event, 'enterprise_decision')
            fid, route = payload['firm'], choice(payload['route'], ROUTES)
            require(actor == 'agency' and fid in firms and source['actor'] == fid
                    and source['payload']['procedure'] == route and when == source['day'] + 1
                    and source['id'] not in delivered, 'route_delivery_binding_mismatch')
            changed = routes[fid] != route
            row = firm_rows[fid]
            row['delivered_route_changes' if changed else 'delivered_route_noops'] += 1
            row['route_deliveries'].append({**metadata, 'decision_event_id': source['id'], 'before': routes[fid], 'after': route, 'changed': changed})
            routes[fid] = route; delivered.add(source['id'])
        elif kind == 'government_decision':
            require(actor == 'agency', 'unknown_government_actor')
            policy, duration = choice(payload['policy'], ('keep', *POLICIES)), integer(payload['duration'])
            require(2 <= duration <= 10, 'invalid_policy_duration')
            government['recorded_decision_opportunities'] += 1
            government['decisions'].append({**metadata, 'policy_request': policy, 'duration_days': duration})
        elif kind == 'policy_delivered':
            source = parent(event, 'government_decision')
            after = {'policy': choice(payload['policy'], POLICIES), 'effective_day': integer(payload['effective_day']),
                'expires': None if payload['expires'] is None else integer(payload['expires'])}
            expected_expiry = when + source['payload']['duration'] if after['policy'] == 'enhanced_review' else None
            require(actor == source['actor'] == 'agency' and source['payload']['policy'] == after['policy']
                    and when == source['day'] + 1 == after['effective_day'] and after['expires'] == expected_expiry
                    and source['id'] not in delivered, 'policy_delivery_binding_mismatch')
            value_changed, record_changed = policy_state['policy'] != after['policy'], policy_state != after
            government['delivered_policy_value_changes' if value_changed else 'delivered_policy_value_noops'] += 1
            government['delivered_policy_record_changes'] += record_changed
            government['deliveries'].append({**metadata, 'decision_event_id': source['id'], 'before': policy_state,
                'after': after, 'policy_changed': value_changed, 'policy_record_changed': record_changed})
            policy_state = after; delivered.add(source['id'])
        elif kind == 'policy_expired':
            require(actor == 'agency' and payload['policy'] == 'baseline' and not event['causes']
                    and policy_state['policy'] == 'enhanced_review' and policy_state['expires'] is not None
                    and when == policy_state['expires'], 'policy_expiry_without_active_window')
            after = {**policy_state, 'policy': 'baseline', 'expires': None}
            government['expiries'].append({**metadata, 'before': policy_state, 'after': after})
            policy_state = after
        elif kind == 'geopolitical_shock':
            after = {'corridor': choice(payload['corridor'], ('open', 'disrupted')),
                'supply_delay': integer(payload['supply_delay']), 'revision': integer(payload['revision'])}
            require(actor == 'environment' and not event['causes'] and after['revision'] == geo_state['revision'] + 1, 'invalid_exogenous_shock_binding')
            shocks.append({**metadata, 'source': 'exogenous_environment_schedule', 'before': geo_state, 'after': after,
                'changed_fields': [key for key in ('corridor', 'supply_delay') if geo_state[key] != after[key]]})
            geo_state = after
        elif kind == 'consumer_decision':
            require(actor in consumers, 'unknown_consumer_actor')
            action = choice(payload['action'], ('wait', 'purchase', 'switch', 'complain'))
            require(action == 'wait' or payload.get('firm') in firms, 'unknown_consumer_decision_enterprise')
            consumer_rows[actor]['recorded_decision_opportunities'] += 1
            consumer_rows[actor]['action_counts'][action] += 1
        elif kind == 'order_placed':
            require(actor in consumers, 'unknown_order_consumer')
            sources = [by_id.get(cause) for cause in event['causes']]
            if any(source is not None and source['kind'] == 'consumer_decision' for source in sources):
                source = parent(event, 'consumer_decision')
                fid, tid = payload['firm'], payload['task_id']
                require(fid in firms and type(tid) is str and re.fullmatch(re.escape(fid) + r'-order-[0-9]+', tid)
                        and (fid, tid) not in native_orders and source['actor'] == actor
                        and source['payload']['action'] in ('purchase', 'switch') and source['payload']['firm'] == fid
                        and type(payload['requested']) is int and source['day'] == when == payload['requested'], 'endogenous_order_binding_mismatch')
                price, due = number(payload['price']), integer(payload['due'])
                require(6 <= price <= 20 and due >= when, 'invalid_order_terms')
                history = consumers[actor]['history']
                require(type(history) is list, 'missing_consumer_history')
                matching = [row for row in history if row.get('kind') == 'ordered' and row.get('task_id') == tid and row.get('firm') == fid]
                if len(matching) != 1 or type(matching[0].get('day')) is not int or matching[0]['day'] != when:
                    issues.append({'kind': 'endogenous_order_history_mismatch', 'consumer': actor, 'event_id': eid})
                safe = {**metadata, 'consumer': actor, 'enterprise': fid, 'task_id': tid,
                    'decision_event_id': source['id'], 'workflow': choice(payload['workflow'], WORKFLOWS), 'price': price, 'due_day': due}
                endogenous_orders.append(safe); consumer_rows[actor]['endogenous_orders'].append(safe); native_orders.add((fid, tid))
            elif any(source is None for source in sources):
                issues.append({'kind': 'order_cause_missing', 'consumer': actor, 'event_id': eid})
        processed.add(eid)

    pending = []
    if known:
        if policy_state['expires'] is not None and policy_state['expires'] <= day:
            note_missing_expiry()
        require(type(eco.get('queue')) is list, 'missing_delivery_queue')
        for item in eco['queue']:
            if item['kind'] not in ('enterprise_route', 'policy'):
                continue
            source = by_id.get(item['cause'])
            expected_kind = 'enterprise_decision' if item['kind'] == 'enterprise_route' else 'government_decision'
            require(source is not None and source['kind'] == expected_kind and source['id'] not in delivered
                    and item['deliver_day'] == source['day'] + 1, 'pending_delivery_cause_mismatch')
            if item['kind'] == 'enterprise_route':
                require(item['payload']['firm'] == source['actor'] and item['payload']['route'] in ROUTES
                        and item['payload']['route'] == source['payload']['procedure'], 'pending_route_payload_mismatch')
            else:
                policy = source['payload']['policy']
                expiry = item['deliver_day'] + source['payload']['duration'] if policy == 'enhanced_review' else None
                require(policy in POLICIES and item['payload']['policy'] == policy
                        and item['payload']['effective_day'] == item['deliver_day']
                        and item['payload']['expires'] == expiry, 'pending_policy_payload_mismatch')
            pending.append({'decision_event_id': source['id'], 'kind': item['kind'], 'deliver_day': integer(item['deliver_day'])})
            if item['deliver_day'] <= day:
                issues.append({'kind': 'overdue_pending_delivery', 'event_id': source['id']})
        pending_ids = [row['decision_event_id'] for row in pending]
        require(len(pending_ids) == len(set(pending_ids)), 'duplicate_pending_delivery')
        for event in events:
            required = ((event['kind'] == 'enterprise_decision' and event['payload']['procedure'] != 'keep')
                        or (event['kind'] == 'government_decision' and event['payload']['policy'] != 'keep'))
            if required and event['id'] not in delivered and event['id'] not in pending_ids:
                issues.append({'kind': 'missing_scheduled_delivery', 'event_id': event['id']})
        for fid in firm_ids:
            if fid in observed_strategy and observed_strategy[fid] != strategy(firms[fid]):
                issues.append({'kind': 'enterprise_final_state_mismatch', 'enterprise': fid})
            if revised[fid] != firms[fid]['strategy_revision']:
                issues.append({'kind': 'enterprise_strategy_revision_mismatch', 'enterprise': fid})
            if routes[fid] != firms[fid]['route']:
                issues.append({'kind': 'enterprise_final_route_mismatch', 'enterprise': fid})
        if final_policy != policy_state:
            issues.append({'kind': 'government_final_policy_mismatch'})
        if final_geo != geo_state:
            issues.append({'kind': 'geopolitical_final_state_mismatch'})
        observed_shocks = [{'day': row['day'], 'corridor': row['after']['corridor'],
                            'supply_delay': row['after']['supply_delay']} for row in shocks]
        if expected_shocks != observed_shocks:
            issues.append({'kind': 'geopolitical_schedule_event_mismatch'})
        for event in events:
            if event['kind'] == 'consumer_decision' and event['payload']['action'] in ('purchase', 'switch'):
                matches = [row for row in endogenous_orders if row['decision_event_id'] == event['id']]
                if len(matches) != 1:
                    issues.append({'kind': 'consumer_purchase_order_count_mismatch', 'consumer': event['actor'], 'event_id': event['id']})
    return {'schema_version': 1, 'summary_version': VERSION,
        'analysis_registration': 'during_execution_descriptive_addition_not_preregistered_endpoint',
        'reconciliation_scope': ['enterprise_strategy_and_routes', 'government_policy',
            'geopolitical_schedule_and_state', 'consumer_decision_to_order_and_ordered_history'],
        'consumer_final_state_validation': 'type_and_identity_only_no_payment_balance_or_satisfaction_replay',
        'observed_day': day, 'event_history_present': known, 'evidence_complete': known and not issues,
        'evidence_issues': issues, 'enterprises': [firm_rows[fid] for fid in firm_ids], 'government': government,
        'geopolitics': {'final_state': final_geo, 'exogenous_shock_events': shocks,
            'schedule_source': 'checkpoint_shock_schedule' if 'shock_schedule' in eco else 'frozen_kernel_default',
            'expected_shocks_through_observation': expected_shocks},
        'consumers': [consumer_rows[cid] for cid in consumer_ids],
        'endogenous_order_count': len(endogenous_orders) if known else None,
        'pending_policy_or_route_deliveries': pending if known else None,
        'interpretation': 'Recorded decision opportunities count accepted kernel events, not all interview attempts. '
            'Strategy revisions and explicit procedure requests are not counts of changed state. '
            'Delivery and final-state reconciliation assess evidence consistency, not causal efficacy. '
            'Consumer purchases require exact causal joins; fixed benchmark demand is not labeled endogenous. '
            'Consumer actions are intents; provider, satisfaction, budget and pending counts are observed final scalars, not independently replayed. Budgets are signed synthetic balances. '
            'The evaluation runner initializes consumer balances to 10,000; the base kernel uses 160. Every order checks unreserved affordability; signed-balance support is reporting robustness only. '
            'Missing histories are unknown. These are dependent descriptive trajectories, not another primary endpoint.'}


def summarize_world_dynamics(checkpoint):
    """Pure safe trajectory summary; malformed evidence raises ValueError."""
    try:
        return _summarize_world_dynamics(checkpoint)
    except (KeyError, TypeError, IndexError, AttributeError):
        raise ValueError('malformed_checkpoint_evidence') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=Path)
    args = parser.parse_args(argv)
    try:
        raw = args.checkpoint.read_bytes()
        result = summarize_world_dynamics(json.loads(raw))
        result['input_sha256'] = hashlib.sha256(raw).hexdigest()
        result['input_hash_encoding'] = 'sha256_raw_file_bytes'
        result['postprocessor_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if result['evidence_complete'] else 1
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
