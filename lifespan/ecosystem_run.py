"""Native MiroFish + Persona 8B + one persistent Hermes/computer per employee."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from .computers import Computer, HERMES, file_delta
from .ecosystem import Ecosystem, WORKFLOWS
from .environment import SessionEnv
from .integrated import EMPLOYEE_PROMPT, employee_view, validate_decision, enact_proposal
from .mirofish import MiroFishRuntime, ROOT, imports, parse_object, save
from .personas import import_cohort

ACTOR_PROMPT='''You are the persistent actor identified by the supplied role and view in a fictional economy.
Use your imported persona tendencies and prior notes, but respond only using visible evidence.
Make a consequential decision to pursue your goals in response to competitors, customer outcomes,
government policy or geopolitical conditions. You can retain a good decision; do not change for novelty.
Do not invent hidden competitor costs, future shocks or unobserved incidents. All dates are simulated days.
Only PUBLIC prices, markets and announcements of competitors are visible. Cash and employee feedback are private.
Return ONLY one JSON object, in English, with notes (updated working notes <=1800 chars), reason,
and evidence_ids (IDs of supplied evidence events supporting the decision, may be empty at initialization), plus:
Enterprise role: objective (growth|reliability|resilience|cost_control), price (number 6..20),
target_market (domestic|cross_border), priority_workflow (onboarding|renewal|incident),
procedure (keep|alternate_route|standard_route). Prices/markets become public immediately; objectives guide
employee work. A route change costs 2 cash and changes every employee's required endpoint next day.
Growth favors acquisition; reliability favors overdue service; resilience favors continuity during disruption;
cost_control favors high-value work. Existing obligations survive a market exit. Consider competitors' prices,
backlog and realized outcomes before setting these fields.
Government agency role: policy (keep|baseline|enhanced_review), duration (integer 2..10).
The authority balances continuity and consumer protection. Enhanced review requires jurisdiction_review and
redacted deliverables at all regulated firms, takes effect tomorrow and expires after duration days.
A policy is your decision, not prescribed by the geopolitical shock. You may issue, revise or withdraw it.
Consumer role: action (wait|purchase|switch|complain), firm (a visible firm ID, or null for wait).
Compare actual offers and own experience. Purchase/switch requires no pending orders, sufficient budget,
and the firm serving your market. A complaint requires a currently overdue pending order at that firm.
Orders reserve budget; payment follows successful delivery with delay. You may wait.
Your workplace view:
'''


def native_decision(runtime,aid,prompt,key,validate):
    raw=runtime.interview(aid,prompt,key)
    for attempt in range(2):
        try:
            if hasattr(runtime, 'validate_output_contract'):
                runtime.validate_output_contract(raw, aid)
            result=parse_object(raw)
            validate(result)
            return result
        except (ValueError,TypeError,KeyError) as exc:
            if attempt:
                raise
            raw=runtime.interview(aid,prompt+'\nInvalid response: '+str(exc)+'\nPrevious: '+raw+
                '\nReturn corrected JSON only.',key+'-repair')


def actor_prompt(view):
    intro=ACTOR_PROMPT.split('Enterprise role:')[0]
    role=view['role']
    if role=='enterprise':
        instructions=ACTOR_PROMPT.split('Enterprise role:')[1].split('Government agency role:')[0]
        example={'objective':'growth','price':10,'target_market':'domestic','priority_workflow':'onboarding','procedure':'keep'}
    elif role=='government_agency':
        instructions=ACTOR_PROMPT.split('Government agency role:')[1].split('Consumer role:')[0]
        example={'policy':'keep','duration':4}
    else:
        instructions=ACTOR_PROMPT.split('Consumer role:')[1].split('Your workplace view:')[0]
        example={'action':'wait','firm':None}
    example.update(notes='Your updated notes',reason='Your evidence-based reason',evidence_ids=[])
    return (intro+'\nYour sole role is '+role+'. Required decision fields: '+instructions+
        '\nUse this FLAT JSON shape (example values are illustrative, choose your own): '+json.dumps(example)+
        '\nDo not nest decision fields under a role key.\nYour workplace view:\n'+json.dumps(view))


def checkpoint(out,eco,state):
    save(out/'checkpoint.json',{'ecosystem':eco.checkpoint(),'runner':state})


def run(out,days=16,seed=7,decision_every=4,max_sessions=None):
    if days<2 or decision_every<1:
        raise ValueError('days >=2 and decision_every >=1 required')
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/'RESULTS.json').exists():
        raise ValueError('Completed run exists; choose a new output directory')
    if (out/'inflight.json').exists():
        raise RuntimeError('An interrupted model session has uncertain side effects. Inspect inflight.json before resuming; no silent replay.')
    saved=json.loads((out/'checkpoint.json').read_text()) if (out/'checkpoint.json').exists() else None
    eco=Ecosystem.restore(saved['ecosystem']) if saved else Ecosystem(days,seed)
    state=saved['runner'] if saved else {'phase':'advance','actor_index':0,'employee_index':0,
        'sessions':0,'notes':{},'employee_records':0,'phase_views':{},'days':days,'seed':seed,
        'decision_every':decision_every,'message_queue':[],'mailbox':{}}
    if (state['days'],state['seed'],state['decision_every'])!=(days,seed,decision_every):
        raise ValueError('Resume configuration differs from checkpoint')
    participants=eco.participants()
    cohort_path=out/'persona_cohort.json'
    cohort=json.loads(cohort_path.read_text()) if cohort_path.exists() else import_cohort(
        ROOT/'lifespan/data/persona8b',cohort_path,count=len(participants),seed=seed)
    runtime=MiroFishRuntime(out)
    runtime.bootstrap({'name':'Persistent fictional economy','employees':participants,'rules':[],
        'project_name':'Ecosystem Lifespans · Hermes + Persona 8B',
        'ecosystem_description':'Two competing enterprises with three frontline employees each, '
            'one government agency, three independent consumers. Geopolitical conditions may evolve. '
            'Enterprise and agency profiles represent institutional decisions; only frontline employees use Hermes.'},cohort)
    imports()
    from app.config import Config
    credentials={'model':Config.LLM_MODEL_NAME,'base_url':Config.LLM_BASE_URL,'api_key':Config.LLM_API_KEY}
    computers={p['id']:Computer(out/'computers',p['id']) for p in participants if p['entity_type']=='Employee'}
    started=time.monotonic()
    try:
        # All six instances exist simultaneously and stay alive across simulated days.
        for eid,c in computers.items():
            print('Starting Hermes/computer '+eid,flush=True)
            c.start(credentials)
        while eco.day<days:
            if state['phase']=='advance':
                if eco.day+1==days:
                    break
                eco.advance()
                for msg in list(state['message_queue']):
                    if msg['deliver_day']==eco.day:
                        state['mailbox'].setdefault(msg['recipient'],[]).append(msg)
                        fid,local=msg['recipient'].split('__',1)
                        recipient=eco.worlds[fid].employees[local]
                        recipient.known=list(dict.fromkeys(recipient.known+msg.get('document_ids',[])))
                        eco.emit('employee_message_delivered',msg['recipient'],msg,[msg['cause']])
                        state['message_queue'].remove(msg)
                state.update(phase='actors',actor_index=0,employee_index=0)
                # Firms use a simultaneous public-market snapshot at each decision epoch.
                state['phase_views']={aid:eco.actor_view(aid) for aid in ['agency',*eco.firms]}
                checkpoint(out,eco,state)
            actors=['agency',*eco.firms,*eco.consumers] if eco.day%decision_every==0 or eco.day==11 else []
            if state['phase']=='actors':
                for idx in range(state['actor_index'],len(actors)):
                    aid=actors[idx]
                    view=state['phase_views'].get(aid,eco.actor_view(aid))
                    key=f'd{eco.day:03d}-actor-{aid}-v2'
                    print(f'Day {eco.day}: MiroFish decision {aid}',flush=True)
                    # Validate on a complete fork; correction cannot partially mutate the live world.
                    a=native_decision(runtime,aid,actor_prompt(view),key,
                        lambda a: Ecosystem.restore(eco.checkpoint()).apply_decision(aid,a,view))
                    eco.apply_decision(aid,a,view)
                    save(out/'actor_sessions'/f'{key}.json',eco.decisions[-1])
                    state['actor_index']=idx+1
                    checkpoint(out,eco,state)
                state['worklist']=[]
                for fid,w in eco.worlds.items():
                    for emp in w.employees.values():
                        tasks=[t for t in w.tasks.values() if t.owner==emp.id and t.status=='pending']
                        if tasks:
                            # Strategy changes actual allocation, not just employee prose.
                            objective=eco.firms[fid]['objective']
                            key=(lambda t:(-t.value,t.due,t.id)) if objective=='cost_control' else (lambda t:(t.due,t.id))
                            task=min(tasks,key=key)
                            state['worklist'].append([fid,task.id])
                state['worklist'].sort(key=lambda x:(eco.worlds[x[0]].tasks[x[1]].workflow!=eco.firms[x[0]]['priority_workflow'],x))
                allocated={fid:0 for fid in eco.firms}
                limited=[]
                for item in state['worklist']:
                    fid=item[0]
                    if allocated[fid]<eco.firms[fid].get('daily_capacity',2):
                        limited.append(item)
                        allocated[fid]+=1
                state['worklist']=limited
                state['phase']='employees'
                checkpoint(out,eco,state)
            for idx in range(state['employee_index'],len(state['worklist'])):
                if max_sessions is not None and state['sessions']>=max_sessions:
                    print('Pilot paused at durable checkpoint; rerun without --max-sessions.',flush=True)
                    return {'status':'paused','sessions':state['sessions'],'day':eco.day}
                fid,tid=state['worklist'][idx]
                w=eco.worlds[fid]
                task=w.tasks[tid]
                eid=fid+'__'+task.owner
                c=computers[eid]
                key=f'd{eco.day:03d}-{eid}-{tid}'
                recoveries=list((out/'infrastructure_failures').glob(key+'*'))
                if recoveries:
                    key+='-retry'+str(len(recoveries))
                view=employee_view(w,task,{task.owner:state['notes'].get(eid,'')},
                                   {task.owner:eco.feedback.get(eid)}, {})
                view['enterprise_objectives']=deepcopy(eco.firms[fid])
                # Frontline employees receive their own firm's strategy, not competitor private state.
                view['enterprise_objectives'].pop('cash',None)
                view['geopolitical_bulletin']=deepcopy(eco.geopolitics)
                view['received_colleague_messages']=deepcopy(state['mailbox'].get(eid,[]))
                # Same firm colleagues; IDs are local in the employee interface.
                view['colleagues']=[x for x in w.employees if x!=task.owner]
                view['computer']={'workspace':'/workspace','files':list(c.snapshot()),
                                  'assistant':'Your dedicated persistent Hermes instance'}
                prompt=EMPLOYEE_PROMPT+'\nYour assistant has a real persistent filesystem. Ask it to create a real deliverable and maintain useful notes.\n'+json.dumps(view)
                d=native_decision(runtime,eid,prompt,key,lambda d:validate_decision(d,view))
                state['notes'][eid]=d['working_notes']
                state['mailbox'][eid]=[]
                for msg in d.get('colleague_messages',[]):
                    cause=eco.emit('employee_message_sent',eid,msg)
                    state['message_queue'].append(dict(msg,sender=eid,recipient=fid+'__'+msg['recipient'],
                                                       deliver_day=eco.day+1,cause=cause))
                proposal=enact_proposal(w,task,d,{task.owner:eco.feedback.get(eid)})
                if proposal:
                    eco.emit('employee_process_proposal',eid,proposal)
                record={'day':eco.day,'employee':eid,'task_id':tid,'view':view,'decision':d,
                        'persona_id':cohort['personas'][runtime.employee_ids[eid]]['persona_id']}
                state['employee_records']+=1
                if d['delegate']:
                    visible={r['id']:r for r in view['visible_documents']}
                    shared=[{'kind':'notice','day':eco.day,'document':visible[k]} for k in d['share_document_ids']]
                    ask_count=[0]
                    def ask(question):
                        ask_count[0]+=1
                        return runtime.interview(eid,'The Hermes assistant asks: '+question+
                            '\nAnswer using only your view and notes:\n'+json.dumps(view),key+'-clarification-'+str(ask_count[0]))
                    env=SessionEnv(w,task,employee_message=d['request'],employee_ask=ask,shared_inbox=shared)
                    before_publish=c.snapshot()
                    c.publish(env.observation,view['enterprise_objectives'],[r.public() for r in w.documents(w.employees[task.owner])])
                    env.trace[0]['observation']=deepcopy(env.observation)
                    before=c.snapshot()
                    eco.emit('computer_inbox_updated',eid,{'session':key,'delta':file_delta(before_publish,before)})
                    save(out/'inflight.json',{'session':key,'employee':eid,'pid':c.process.pid,'day':eco.day})
                    print(f'Day {eco.day}: Hermes {eid} executes {tid}',flush=True)
                    result=c.run(env,d['request']+'\nSimulated day '+str(eco.day)+
                        '. The current task and received evidence are in /workspace/inbox/current.json. '
                        'Complete it with your terminal, file tools and enterprise_action. Save updated working notes.')
                    if not env.done:
                        env.step({'tool':'session.end','args':{}})
                    after=c.snapshot()
                    record.update(result=result,trace=env.trace,diagnostic=env.diagnostic(),
                                  computer_state=c.runtime_state(),
                                  filesystem_before=before,filesystem_after=after,filesystem_delta=file_delta(before,after))
                    eco.record_session(fid,task,key,env.diagnostic(),record['filesystem_delta'])
                    state['sessions']+=1
                    save(out/'employee_sessions'/f'{key}.json',record)
                    state['employee_index']=idx+1
                    checkpoint(out,eco,state)
                    (out/'inflight.json').unlink()
                else:
                    eco.emit('delegation_withheld',eid,{'reason':d['request'],'task_id':tid})
                    save(out/'employee_sessions'/f'{key}.json',record)
                    state['employee_index']=idx+1
                    checkpoint(out,eco,state)
            save(out/'daily'/f'd{eco.day:03d}.json',eco.snapshot())
            state['phase']='advance'
            checkpoint(out,eco,state)
            save(out/'progress.json',{'day':eco.day,'days':days,'sessions':state['sessions'],
                'elapsed_s':round(time.monotonic()-started),'events':len(eco.events)})
            print(f'Day {eco.day+1}/{days}: {state["sessions"]} Hermes sessions, {len(eco.events)} causal events',flush=True)
        with sqlite3.connect(runtime.sim_dir/'reddit_simulation.db') as src:
            with sqlite3.connect(out/'mirofish_simulation.db') as dst:
                src.backup(dst)
        save(out/'private/final_world.json',eco.snapshot())
        save(out/'timeline.json',eco.events)
        save(out/'actor_decisions.json',eco.decisions)
        result={'days':days,'enterprises':len(eco.firms),'government_agencies':1,'consumers':len(eco.consumers),
            'frontline_employees':len(computers),'hermes_instances':len(computers),'hermes_sessions':state['sessions'],
            'mirofish_actor_decisions':len(eco.decisions),'timeline_events':len(eco.events),
            'completed_tasks':sum(t.status=='completed' for w in eco.worlds.values() for t in w.tasks.values()),
            'pending_tasks':sum(t.status=='pending' for w in eco.worlds.values() for t in w.tasks.values()),
            'business_utility':round(sum(w.total_utility for w in eco.worlds.values()),2),
            'firms':deepcopy(eco.firms),'model':Config.LLM_MODEL_NAME,'training_performed':False,
            'hermes_revision':subprocess.check_output(['git','-C',str(HERMES),'rev-parse','HEAD'],text=True).strip()}
        save(out/'RESULTS.json',result)
        runtime.close()
        return result
    finally:
        for c in computers.values():
            c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True)
    p.add_argument('--days',type=int,default=16)
    p.add_argument('--seed',type=int,default=7)
    p.add_argument('--decision-every',type=int,default=4)
    p.add_argument('--max-sessions',type=int)
    a=p.parse_args()
    print(json.dumps(run(a.out,a.days,a.seed,a.decision_every,a.max_sessions),indent=2))
