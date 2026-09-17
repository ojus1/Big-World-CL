"""Persistent workplace consequences over a frozen, calibrated arrival schedule.

The kernel supplies chronology and authority; an employee driver supplies actual
delegation, requests, notes and messages. It never supplies scripted dialogue.
Rewards are declared synthetic utility units, not monetary revenue.
"""
from collections import Counter
from copy import deepcopy
import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Workplace:
    def __init__(self, world):
        self.world = deepcopy(world)
        self.spec = world['specification']
        self.options = self.spec.get('workplace', {})
        self.delay = self.spec.get('feedback_delay', 1)
        self.max_attempts = self.options.get('max_attempts', 2)
        self.grace = self.options.get('grace_days', 2)
        self.retry_delay = self.options.get('retry_delay', 1)
        self.settlement_delay = self.options.get('settlement_delay', 1)
        for name, value, minimum in [('feedback_delay', self.delay, 1), ('max_attempts', self.max_attempts, 1),
                                     ('grace_days', self.grace, 0), ('retry_delay', self.retry_delay, 1),
                                     ('settlement_delay', self.settlement_delay, 1)]:
            require(type(value) is int and minimum <= value <= 100, 'Invalid workplace option: ' + name)
        self.work_cost = self.options.get('work_cost_units', 1.0)
        self.value = self.options.get('completion_value_units', 10.0)
        for value in [self.work_cost, self.value]:
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                    'Utility parameters must be finite and nonnegative')
        self.profiles = {e['id']: deepcopy(e) for e in world['workforce']}
        require(len(self.profiles) == len(world['workforce']), 'Duplicate employee identity')
        self.arrivals = {s['id']: deepcopy(s) for s in world['schedule']}
        require(len(self.arrivals) == len(world['schedule']), 'Duplicate obligation identity')
        require(all(s['employee_id'] in self.profiles and s['due_day'] >= s['day'] for s in self.arrivals.values()),
                'Invalid obligation owner or deadline')
        self.state = {'day': -1, 'employees': {e: {'notes': '', 'trust': .7, 'used_capacity': 0,
                       'mailbox': [], 'released_feedback': []} for e in self.profiles},
                      'obligations': {}, 'messages': [], 'reviews': [], 'settlements': [],
                      'events': [], 'ledger': [], 'commands': []}

    @property
    def day(self):
        return self.state['day']

    def _command(self, operation, arguments):
        self.state['commands'].append({'operation': operation, 'arguments': deepcopy(arguments)})

    def _emit(self, kind, actor, payload, causes=()):
        event = {'id': f'event-{len(self.state["events"]):07d}', 'day': self.day,
                 'kind': kind, 'actor': actor, 'payload': deepcopy(payload), 'causes': list(causes)}
        self.state['events'].append(event)
        return event['id']

    def advance(self, day):
        require(type(day) is int and day == self.day + 1, 'Workplace days must advance exactly once')
        require(not any(o['status'] in ('assigned', 'working') for o in self.state['obligations'].values()),
                'Cannot advance past unresolved work')
        self._command('advance', {'day': day})
        self.state['day'] = day
        for employee in self.state['employees'].values():
            employee['used_capacity'] = 0
        for slot in self.arrivals.values():
            if slot['day'] != day: continue
            event = self._emit('obligation_arrived', slot['employee_id'], {'obligation_id': slot['id']})
            self.state['obligations'][slot['id']] = {**deepcopy(slot), 'status': 'pending',
                'attempts': 0, 'next_eligible_day': day, 'arrival_event': event, 'last_result': None,
                'last_session': None, 'accepted_day': None, 'completed_day': None, 'settled': False}
        for message in list(self.state['messages']):
            if message['deliver_day'] > day: continue
            self.state['employees'][message['recipient']]['mailbox'].append(deepcopy(message))
            self._emit('colleague_message_delivered', message['recipient'], message, [message['cause']])
            self.state['messages'].remove(message)
        for review in list(self.state['reviews']):
            if review['release_day'] > day: continue
            obligation = self.state['obligations'][review['obligation_id']]
            employee = self.state['employees'][obligation['employee_id']]
            feedback = {k: deepcopy(review[k]) for k in ('obligation_id', 'session_id', 'success',
                                                        'quality_score', 'feedback', 'release_day')}
            employee['released_feedback'].append(feedback)
            employee['trust'] = min(1., max(0., employee['trust'] + (.03 if review['success'] else -.08)))
            event = self._emit('feedback_released', obligation['employee_id'], feedback, [review['cause']])
            if review['success']:
                obligation.update(status='accepted', accepted_day=day, completed_day=review['completed_day'])
                lateness = max(0, review['completed_day'] - obligation['due_day'])
                value = self.value * review['quality_score'] * max(0., 1. - .1 * lateness)
                self.state['settlements'].append({'obligation_id': obligation['id'], 'due_day': day + self.settlement_delay,
                                                  'value': value, 'cause': event})
            elif obligation['attempts'] < self.max_attempts and day <= obligation['due_day'] + self.grace:
                obligation.update(status='pending', next_eligible_day=day + self.retry_delay)
                self._emit('rework_requested', obligation['employee_id'],
                           {'obligation_id': obligation['id'], 'earliest_day': obligation['next_eligible_day']}, [event])
            else:
                obligation['status'] = 'failed'
            self.state['reviews'].remove(review)
        for obligation in self.state['obligations'].values():
            if obligation['status'] == 'pending' and day > obligation['due_day'] + self.grace:
                obligation['status'] = 'expired'
                self._emit('obligation_expired', obligation['employee_id'], {'obligation_id': obligation['id']},
                           [obligation['arrival_event']])
        for settlement in list(self.state['settlements']):
            if settlement['due_day'] > day: continue
            obligation = self.state['obligations'][settlement['obligation_id']]
            require(not obligation['settled'], 'Obligation cannot settle twice')
            obligation['settled'] = True
            event = self._emit('completion_settled', obligation['employee_id'], settlement, [settlement['cause']])
            self.state['ledger'].append({'day': day, 'kind': 'completion', 'obligation_id': obligation['id'],
                                         'utility_units': settlement['value'], 'cause': event})
            self.state['settlements'].remove(settlement)

    def available(self, employee_id):
        require(employee_id in self.profiles, 'Unknown employee')
        capacity = self.profiles[employee_id].get('sessions_per_day', 1)
        remaining = max(0, capacity - self.state['employees'][employee_id]['used_capacity'])
        candidates = [o for o in self.state['obligations'].values() if o['employee_id'] == employee_id
                      and o['status'] == 'pending' and o['next_eligible_day'] <= self.day]
        candidates.sort(key=lambda o: (o['due_day'], o['day'], o['id']))
        return [o['id'] for o in candidates[:remaining]]

    def view(self, employee_id, obligation_id, bank):
        require(obligation_id in self.available(employee_id), 'Employee cannot observe unavailable work')
        profile = self.profiles[employee_id]
        employee = self.state['employees'][employee_id]
        obligation = self.state['obligations'][obligation_id]
        department = profile.get('department', profile['role'])
        history = []
        for feedback in employee['released_feedback'][-6:]:
            source = self.arrivals[feedback['obligation_id']]
            same_family = source['lineage_group'] == obligation['lineage_group']
            history.append({**deepcopy(feedback), 'task_id': source['task_id'],
                            'relation_to_pending': ('same_obligation' if source['id'] == obligation_id else
                                                    'same_source_family' if same_family else 'unrelated_task'),
                            'feedback': feedback['feedback'] if same_family else '',
                            'feedback_scope': ('released feedback for this task family' if same_family else
                                               'numeric outcome only; detailed feedback belongs to another task family')})
        return {'day': self.day, 'employee_id': employee_id, 'role': profile['role'], 'language': profile['language'],
                'department': department, 'own_previous_working_notes': employee['notes'], 'trust': employee['trust'],
                'pending_task': {k: obligation[k] for k in ('id', 'task_id', 'due_day', 'attempts', 'status')},
                'pending_task_observed_outcomes': deepcopy([f for f in employee['released_feedback']
                                                            if f['obligation_id'] == obligation_id]),
                'employee_capabilities': {'inspect_source_files': False, 'execute_tools': False,
                                          'complete_artifacts': False, 'delegate_to_assistant': True},
                'substantive_work': bank.public(obligation['task_id'])['instruction'],
                'recent_observed_outcomes': history,
                'received_colleague_messages': deepcopy(employee['mailbox']),
                'backlog': sum(o['employee_id'] == employee_id and o['status'] in ('pending', 'awaiting_feedback')
                               for o in self.state['obligations'].values()),
                'colleagues': [e for e, p in self.profiles.items() if e != employee_id and
                               p.get('department', p['role']) == department], 'visible_documents': []}

    def decide(self, employee_id, obligation_id, decision):
        require(obligation_id in self.available(employee_id), 'Decision exceeds available work or capacity')
        require(type(decision.get('delegate')) is bool and isinstance(decision.get('request'), str)
                and (not decision['delegate'] or bool(decision['request'].strip())), 'Invalid delegation')
        require(isinstance(decision.get('working_notes'), str),
                'Invalid employee notes')
        require(decision.get('share_document_ids') == [] and decision.get('process_proposal') is None,
                'This workplace does not grant document-sharing or process-change authority')
        messages = decision.get('colleague_messages')
        require(isinstance(messages, list) and len(messages) <= 1, 'At most one colleague message per decision')
        profile = self.profiles[employee_id]
        department = profile.get('department', profile['role'])
        for message in messages:
            recipient = self.profiles.get(message.get('recipient'))
            require(recipient is not None and recipient['id'] != employee_id and
                    recipient.get('department', recipient['role']) == department and
                    isinstance(message.get('text'), str) and bool(message['text'].strip()) and
                    message.get('document_ids', []) == [], 'Invalid or cross-department message')
        self._command('decide', {'employee_id': employee_id, 'obligation_id': obligation_id, 'decision': decision})
        employee = self.state['employees'][employee_id]
        employee['notes'] = decision['working_notes']
        employee['mailbox'] = []
        employee['used_capacity'] += 1
        event = self._emit('employee_decision', employee_id,
                           {'obligation_id': obligation_id, 'decision': decision})
        for message in messages:
            self.state['messages'].append({**deepcopy(message), 'sender': employee_id,
                                           'deliver_day': self.day + 1, 'cause': event})
        obligation = self.state['obligations'][obligation_id]
        obligation['decision_event'] = event
        if decision['delegate']:
            obligation['status'] = 'assigned'
        else:
            obligation['next_eligible_day'] = self.day + 1
        return decision['delegate']

    def start(self, obligation_id, session_id):
        obligation = self.state['obligations'][obligation_id]
        require(obligation['status'] == 'assigned' and isinstance(session_id, str) and session_id,
                'Work must follow a current delegation')
        require(not any(c['operation'] == 'start' and c['arguments']['session_id'] == session_id
                        for c in self.state['commands']), 'Duplicate session identity')
        self._command('start', {'obligation_id': obligation_id, 'session_id': session_id})
        obligation.update(status='working', attempts=obligation['attempts'] + 1, last_session=session_id)
        event = self._emit('work_started', obligation['employee_id'],
                           {'obligation_id': obligation_id, 'session_id': session_id}, [obligation['decision_event']])
        obligation['start_event'] = event
        self.state['ledger'].append({'day': self.day, 'kind': 'work', 'obligation_id': obligation_id,
                                    'session_id': session_id, 'utility_units': -self.work_cost, 'cause': event})

    def complete(self, obligation_id, session_id, outcome):
        obligation = self.state['obligations'][obligation_id]
        require(obligation['status'] == 'working' and obligation['last_session'] == session_id,
                'Completion must match the running attempt')
        require(type(outcome.get('success')) is bool and type(outcome.get('quality_score')) in (int, float)
                and math.isfinite(outcome['quality_score']) and 0 <= outcome['quality_score'] <= 1
                and isinstance(outcome.get('feedback'), str), 'An unscored attempt cannot change the world')
        self._command('complete', {'obligation_id': obligation_id, 'session_id': session_id, 'outcome': outcome})
        event = self._emit('work_returned', obligation['employee_id'],
                           {'obligation_id': obligation_id, 'session_id': session_id}, [obligation['start_event']])
        obligation.update(status='awaiting_feedback', last_result=deepcopy(outcome))
        self.state['reviews'].append({**deepcopy(outcome), 'obligation_id': obligation_id, 'session_id': session_id,
                                     'release_day': self.day + self.delay, 'completed_day': self.day, 'cause': event})

    def summary(self):
        obligations = self.state['obligations']
        probes = [s for s in self.arrivals.values() if s['split'] == 'probe']
        def on_time(slot):
            o = obligations.get(slot['id'], {})
            return o.get('status') == 'accepted' and o['completed_day'] <= o['due_day']
        return {'planned_obligations': len(self.arrivals), 'arrived_obligations': len(obligations),
                'status_counts': dict(Counter(o['status'] for o in obligations.values())),
                'work_attempts': sum(o['attempts'] for o in obligations.values()),
                'rework_attempts': sum(max(0, o['attempts'] - 1) for o in obligations.values()),
                'probe_obligations': len(probes), 'probe_accepted_on_time': sum(on_time(s) for s in probes),
                'probe_accepted_on_time_fraction': sum(on_time(s) for s in probes) / len(probes) if probes else None,
                'probe_quality_mean': sum((obligations.get(s['id'], {}).get('last_result') or {}).get('quality_score', 0.)
                                          for s in probes) / len(probes) if probes else None,
                'utility_units': sum(r['utility_units'] for r in self.state['ledger']),
                'unsettled_accepted': sum(o['status'] == 'accepted' and not o['settled'] for o in obligations.values()),
                'metric_scope': 'All planned obligations stay in denominators; outcomes depend on the configured grader.'}

    @classmethod
    def replay(cls, world, commands):
        workplace = cls(world)
        for command in commands:
            require(command['operation'] in ('advance', 'decide', 'start', 'complete'), 'Unknown workplace command')
            getattr(workplace, command['operation'])(**deepcopy(command['arguments']))
        return workplace
