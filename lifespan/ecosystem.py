"""Persistent market, institutions and enterprises with executable causal effects.

Trusted simulator state: never mount this file or the private state in an employee
computer. MiroFish proposes actions; this kernel owns authority and accounting.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
from .world import World, Rule, Task, generate_blueprint

OBJECTIVES = ('growth', 'reliability', 'resilience', 'cost_control')
WORKFLOWS = ('onboarding', 'renewal', 'incident')


class Ecosystem:
    def __init__(self, days=16, seed=7):
        self.days, self.day = days, -1
        self.events, self.queue, self.decisions = [], [], []
        self.notes, self.feedback = {}, {}
        self.rule_causes, self.completion_causes = {}, {}
        self.geopolitics = {'corridor': 'open', 'supply_delay': 0, 'revision': 0}
        self.agency = {'id': 'agency', 'name': 'Fictional Commerce Authority',
                       'policy': 'baseline', 'effective_day': 0, 'expires': None,
                       'complaints': [], 'objective': 'consumer_protection_and_service_continuity'}
        self.firms, self.worlds = {}, {}
        for i, name in enumerate(('Harbor Services', 'Juniper Services')):
            fid = f'firm-{i}'
            bp = generate_blueprint(seed+i, max(28, days), fid, drift=False)
            bp.update(name=name, days=days, arrivals=[], endogenous_failure_rule=False, automatic_renewals=False)
            bp['employees'] = [e for e in bp['employees'] if e['segment'] == 'regulated']
            for e in bp['employees']:
                e['reading_delay'] = 0
            self.worlds[fid] = World(bp)
            self.firms[fid] = {'id': fid, 'name': name, 'objective': 'growth', 'price': 10+i*2,
                'target_market': 'cross_border' if i == 0 else 'domestic', 'priority_workflow': 'onboarding',
                'cash': 100.0, 'revenue': 0.0, 'orders': 0, 'completed': 0,
                'route': 'standard_route', 'daily_capacity': 2,
                'strategy_revision': 0, 'public_announcements': [], 'last_decision': None}
        self.consumers = {f'consumer-{i}': {'id': f'consumer-{i}', 'budget': 160.0,
            'provider': f'firm-{i%2}' if i < 2 else None, 'satisfaction': 0.65,
            'market': 'cross_border' if i != 1 else 'domestic', 'pending': [], 'history': []}
            for i in range(3)}
        # Initial obligations are initial conditions, not invented actor decisions.
        for fid in self.firms:
            for workflow in WORKFLOWS:
                self.order(f'consumer-{int(fid[-1])}', fid, workflow, cause=None, created=0)

    def emit(self, kind, actor, payload, causes=()):
        event = {'id': f'event-{len(self.events):06d}', 'day': self.day, 'kind': kind,
                 'actor': actor, 'payload': deepcopy(payload), 'causes': [c for c in causes if c]}
        self.events.append(event)
        return event['id']

    def schedule(self, kind, payload, delay, cause):
        self.queue.append({'kind': kind, 'payload': deepcopy(payload),
                           'deliver_day': self.day+delay, 'cause': cause})

    def order(self, cid, fid, workflow, cause, created=None):
        c, f, w = self.consumers[cid], self.firms[fid], self.worlds[fid]
        day = self.day+1 if created is None else created
        reserved = sum(p['price'] for p in c['pending'])
        if c['budget'] - reserved < f['price']:
            raise ValueError('Insufficient unreserved consumer budget')
        tid = f'{fid}-order-{f["orders"]:04d}'
        f['orders'] += 1
        delay = self.geopolitics['supply_delay'] if c['market'] == 'cross_border' and f.get('route','standard_route')!='alternate_route' else 0
        value = f['price'] * {'growth': 1.1, 'reliability': 1.2, 'resilience': 1.15, 'cost_control': 1.0}[f['objective']]
        t = Task(tid, workflow, 'regulated', f'{workflow}-regulated', cid, day+delay, day+3, value)
        w.scheduled.append(asdict(t))
        pending = {'task_id': tid, 'firm': fid, 'price': f['price'], 'workflow': workflow,
                   'requested': self.day, 'due': t.due}
        c['pending'].append(pending)
        eid = self.emit('order_placed', cid, pending, [cause])
        pending['event_id'] = eid
        c['history'].append({'day': self.day, 'kind': 'ordered', 'task_id': tid, 'firm': fid})
        return tid

    def advance(self):
        self.day += 1
        if self.day >= self.days:
            raise ValueError('Lifespan already finished')
        # Fictional exogenous world shocks, explicitly labeled. Agent reactions
        # and regulatory/enterprise choices are never supplied by this schedule.
        if self.day in (4, 11):
            disrupted = self.day == 4
            self.geopolitics = {'corridor': 'disrupted' if disrupted else 'open',
                'supply_delay': 2 if disrupted else 0, 'revision': self.geopolitics['revision']+1}
            self.emit('geopolitical_shock', 'environment', self.geopolitics)
        for item in list(self.queue):
            if item['deliver_day'] != self.day:
                continue
            if item['kind'] == 'complaint':
                self.agency['complaints'].append(item['payload'])
            elif item['kind'] == 'policy':
                self.agency.update(item['payload'])
            elif item['kind'] == 'enterprise_route':
                self.firms[item['payload']['firm']]['route']=item['payload']['route']
            self.emit(item['kind']+'_delivered', 'agency', item['payload'], [item['cause']])
            self.queue.remove(item)
        if self.agency['expires'] is not None and self.day >= self.agency['expires']:
            self.agency.update(policy='baseline', expires=None)
            self.emit('policy_expired', 'agency', {'policy': 'baseline'})
        for fid, w in self.worlds.items():
            before = len(w.events)
            w.advance(self.day)
            for ev in w.events[before:]:
                self.emit('work.'+ev['kind'], fid, ev,
                    [self.rule_causes.get(fid+'__'+str(ev.get('rule_id')))])
            for c in self.consumers.values():
                for pending in list(c['pending']):
                    if pending['firm'] != fid:
                        continue
                    task = w.tasks.get(pending['task_id'])
                    settlement = next((x for x in w.ledger if x['task_id']==pending['task_id'] and x['settled']), None)
                    if settlement:
                        price = pending['price']
                        c['budget'] -= price
                        c['satisfaction'] = min(1., c['satisfaction']+0.12-max(0, task.completed-task.due)*0.08)
                        c['provider'] = fid
                        self.firms[fid]['cash'] += price
                        self.firms[fid]['revenue'] += price
                        c['pending'].remove(pending)
                        self.emit('consumer_payment', c['id'], {'firm': fid, 'task_id': task.id,
                            'amount': price, 'satisfaction': c['satisfaction']},
                            [pending['event_id'],self.completion_causes.get(task.id)])
                        c['history'].append({'day': self.day, 'kind': 'paid', 'task_id': task.id, 'firm': fid})
                    elif task and task.status == 'abandoned':
                        c['pending'].remove(pending)
                        c['satisfaction'] = max(0., c['satisfaction']-0.25)
                        self.emit('consumer_service_lost', c['id'], pending, [pending['event_id']])

    def public_view(self):
        return {'day': self.day, 'geopolitics': deepcopy(self.geopolitics),
            'government': {k: deepcopy(v) for k,v in self.agency.items() if k != 'complaints'},
            'enterprises': [{k: deepcopy(f[k]) for k in ('id','name','price','target_market','public_announcements')}
                            for f in self.firms.values()]}

    def actor_view(self, aid):
        v = self.public_view()
        v.update(actor_id=aid, previous_working_notes=self.notes.get(aid, ''))
        if aid in self.firms:
            f, w = self.firms[aid], self.worlds[aid]
            v.update(role='enterprise', own_state=deepcopy(f), operations={
                'backlog': sum(t.status=='pending' for t in w.tasks.values()), 'failures': w.failures,
                'completed': sum(t.status=='completed' for t in w.tasks.values()),
                'by_workflow': {wf: sum(t.status=='pending' and t.workflow==wf for t in w.tasks.values()) for wf in WORKFLOWS},
                'recent_employee_outcomes': [deepcopy(x) for k,x in self.feedback.items() if k.startswith(aid+'__')]},
                received_complaints=[deepcopy(x) for x in self.agency['complaints'] if x['firm']==aid])
        elif aid == 'agency':
            v.update(role='government_agency', own_state=deepcopy(self.agency))
        else:
            v.update(role='consumer', own_state=deepcopy(self.consumers[aid]))
        # Causal evidence is restricted to events supporting this public/private view.
        allowed = {'geopolitical_shock','enterprise_decision','policy_delivered','policy_expired'}
        v['evidence_events'] = [deepcopy(e) for e in self.events if e['kind'] in allowed or
            (e['actor']==aid and e['kind'] in ('order_placed','consumer_payment','consumer_service_lost')) or
            (aid=='agency' and e['kind']=='complaint_delivered')][-12:]
        return v

    def apply_decision(self, aid, action, view):
        if not isinstance(action.get('notes'), str) or len(action['notes']) > 1800:
            raise ValueError('Provide working notes under 1800 characters')
        if not isinstance(action.get('reason'), str):
            raise ValueError('Decision needs an evidence-based reason')
        evidence = action.get('evidence_ids', [])
        if not isinstance(evidence, list) or any(x not in {e['id'] for e in view['evidence_events']} for x in evidence):
            raise ValueError('Decision cited evidence outside its observation')
        if aid in self.firms:
            self._enterprise(aid, action, evidence)
        elif aid == 'agency':
            self._government(action, evidence)
        else:
            self._consumer(aid, action, evidence)
        self.notes[aid] = action['notes']
        self.decisions.append({'day': self.day, 'actor': aid, 'view': deepcopy(view), 'decision': deepcopy(action)})

    def _enterprise(self, fid, a, evidence):
        if (a.get('objective') not in OBJECTIVES or a.get('target_market') not in ('domestic','cross_border')
                or a.get('priority_workflow') not in WORKFLOWS or type(a.get('price')) not in (int,float)
                or not 6 <= a['price'] <= 20 or a.get('procedure') not in ('keep','alternate_route','standard_route')):
            raise ValueError('Invalid enterprise objective/market/priority/price/procedure')
        f, w = self.firms[fid], self.worlds[fid]
        old = {k:deepcopy(f[k]) for k in ('objective','price','target_market','priority_workflow')}
        f.update({k:a[k] for k in old})
        f['strategy_revision'] += 1
        f['last_decision'] = {'day':self.day,'reason':a['reason']}
        f['public_announcements'] = [{'day':self.day,'price':a['price'],'target_market':a['target_market']}]
        eid = self.emit('enterprise_decision', fid, {'before':old,'after':{k:a[k] for k in old},
            'procedure':a['procedure'],'reason':a['reason']}, evidence)
        # Changing a route has real operating cost and tool validation effects.
        if a['procedure'] != 'keep':
            endpoint = 'workspace-v2' if a['procedure']=='alternate_route' else 'workspace-v1'
            f['cash'] -= 2
            w.total_utility -= 2
            self.schedule('enterprise_route',{'firm':fid,'route':a['procedure']},1,eid)
            for wf in WORKFLOWS:
                w.rules.append(Rule(f'strategy-{f["strategy_revision"]}-{wf}',wf,'regulated',self.day+1,
                    None,self.day,'policy_owner',{'endpoint':endpoint},a['reason']))
                self.rule_causes[fid+'__'+w.rules[-1].id]=eid
        self.emit('employee_objectives_updated', fid, {'objective':a['objective'],
            'priority_workflow':a['priority_workflow'],'target_market':a['target_market']}, [eid])

    def _government(self, a, evidence):
        if a.get('policy') not in ('keep','baseline','enhanced_review') or type(a.get('duration')) is not int or not 2<=a['duration']<=10:
            raise ValueError('Policy must be keep/baseline/enhanced_review, duration 2..10 days')
        eid = self.emit('government_decision','agency',a,evidence)
        if a['policy']=='keep':
            return
        until = self.day+1+a['duration'] if a['policy']=='enhanced_review' else None
        self.schedule('policy', {'policy':a['policy'],'effective_day':self.day+1,'expires':until},1,eid)
        for fid,w in self.worlds.items():
            for r in w.rules:
                if r.id.startswith('agency-') and (r.valid_until is None or r.valid_until > self.day+1):
                    r.valid_until=self.day+1
            for wf in WORKFLOWS:
                if a['policy']=='enhanced_review':
                    w.rules.append(Rule(f'agency-{self.day}-{wf}',wf,'regulated',self.day+1,until,
                        self.day,'policy_owner',{'checks_add':['jurisdiction_review'],'redact':True},
                        'Commerce Authority: '+a['reason']))
                    self.rule_causes[fid+'__'+w.rules[-1].id]=eid

    def _consumer(self, cid, a, evidence):
        c = self.consumers[cid]
        if a.get('action') not in ('wait','purchase','switch','complain'):
            raise ValueError('Consumer action must be wait/purchase/switch/complain')
        fid = a.get('firm')
        if a['action'] != 'wait' and fid not in self.firms:
            raise ValueError('Unknown enterprise')
        if a['action'] in ('purchase','switch'):
            if c['pending']:
                raise ValueError('Settle pending orders before new purchase/switch')
            if self.firms[fid]['target_market'] != c['market']:
                raise ValueError('Enterprise does not currently serve this consumer market')
            if c['budget'] < self.firms[fid]['price']:
                raise ValueError('Consumer cannot afford offer')
        if a['action']=='complain' and not any(p['firm']==fid and p['due']<self.day for p in c['pending']):
            raise ValueError('Complaint requires an observed overdue order at this enterprise')
        eid = self.emit('consumer_decision',cid,a,evidence)
        if a['action'] in ('purchase','switch'):
            self.order(cid,fid,'onboarding' if c['provider']!=fid else 'renewal',eid)
        elif a['action']=='complain':
            self.schedule('complaint',{'consumer':cid,'firm':fid,'reason':a['reason']},1,eid)
            c['satisfaction']=max(0.,c['satisfaction']-0.1)

    def record_session(self, fid, task, key, diagnostic, filesystem):
        qualified=f'{fid}__{task.owner}'
        self.feedback[qualified]={'day':self.day,'task_id':task.id,'success':diagnostic['success']}
        eid=self.emit('employee_work',qualified,{'session':key,'task_id':task.id,
            'success':diagnostic['success'],'filesystem_delta':filesystem})
        if diagnostic['success']:
            self.firms[fid]['completed']+=1
            self.completion_causes[task.id]=eid
        return eid

    def snapshot(self):
        return {'day':self.day,'days':self.days,'firms':deepcopy(self.firms),'agency':deepcopy(self.agency),
            'consumers':deepcopy(self.consumers),'geopolitics':deepcopy(self.geopolitics),
            'queue':deepcopy(self.queue),'notes':deepcopy(self.notes),'feedback':deepcopy(self.feedback),
            'worlds':{k:v.snapshot() for k,v in self.worlds.items()}}

    def participants(self):
        people=[]
        for fid,w in self.worlds.items():
            for emp in w.employees.values():
                people.append({'id':fid+'__'+emp.id,'name':fid+' '+emp.name,'workflow':emp.workflow,
                    'segment':'regulated','entity_type':'Employee', 'role_description':
                    f'You are a frontline employee of {fid}. You use your own persistent Hermes assistant and computer.'})
        for aid in [*self.firms,'agency',*self.consumers]:
            kind='Enterprise' if aid in self.firms else 'GovernmentAgency' if aid=='agency' else 'Consumer'
            people.append({'id':aid,'name':aid,'workflow':kind,'segment':'ecosystem','entity_type':kind,
                'role_description':f'You represent the decisions of the persistent {kind} {aid}. '
                    'Organization profiles represent collective decision policies; you are not an extra frontline employee. '
                    'Only your supplied private state and public evidence are known. Respond in English.'})
        return people

    def checkpoint(self):
        data=deepcopy({k:v for k,v in self.__dict__.items() if k!='worlds'})
        data['worlds']={}
        for fid,w in self.worlds.items():
            raw=deepcopy(w.__dict__)
            raw['employees']={k:asdict(v) for k,v in w.employees.items()}
            raw['tasks']={k:asdict(v) for k,v in w.tasks.items()}
            raw['rules']=[asdict(r) for r in w.rules]
            raw['seen_notifications']={k:sorted(v) for k,v in w.seen_notifications.items()}
            data['worlds'][fid]=raw
        return data

    @classmethod
    def restore(cls,data):
        from .world import Employee
        result=cls.__new__(cls)
        result.__dict__.update(deepcopy(data))
        result.worlds={}
        for fid,raw in data['worlds'].items():
            w=World(raw['blueprint'])
            w.__dict__.update(deepcopy(raw))
            w.employees={k:Employee(**v) for k,v in raw['employees'].items()}
            w.tasks={k:Task(**v) for k,v in raw['tasks'].items()}
            w.rules=[Rule(**v) for v in raw['rules']]
            w.seen_notifications={k:set(v) for k,v in raw['seen_notifications'].items()}
            result.worlds[fid]=w
        return result
