"""Audit and export a completed MiroFish/Persona/Hermes ecosystem run offline."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from .mirofish import save


def validate(out):
    out=Path(out).resolve()
    results=json.loads((out/'RESULTS.json').read_text())
    final=json.loads((out/'private/final_world.json').read_text())
    timeline=json.loads((out/'timeline.json').read_text())
    decisions=json.loads((out/'actor_decisions.json').read_text())
    people=json.loads((out/'persona_cohort.json').read_text())['personas']
    profiles=json.loads((out/'imported_mirofish_profiles.json').read_text())
    assert len(people)==len(profiles)==12
    assert len({p['persona_id'] for p in people})==12
    for p,profile in zip(people,profiles):
        assert profile['persona8b_provenance']['persona_id']==p['persona_id']
        for k,v in p['work_attributes'].items():
            assert json.dumps(k)+': '+json.dumps(v) in profile['persona']
    with sqlite3.connect(out/'mirofish_simulation.db') as db:
        native=Counter(json.loads(x[0])['response'] for x in db.execute("SELECT info FROM trace WHERE action='interview'"))
    caches=[json.loads(p.read_text()) for p in (out/'mirofish_interviews').glob('*.json')]
    for r in caches:
        assert native[r['response']]>0
        native[r['response']]-=1
    prior=set()
    for ev in timeline:
        assert ev['id'] not in prior and all(c in prior for c in ev['causes']),ev
        prior.add(ev['id'])
    for d in decisions:
        a=d['actor'];v=d['view']
        assert 'expected_procedure' not in json.dumps(v)
        assert all(ev['day']<=d['day'] for ev in v['evidence_events'])
        assert all('cash' not in f and 'objective' not in f for f in v['enterprises'])
        assert any(json.loads(c['response'])==d['decision'] for c in caches
                   if c['employee_id']==a and c['response'].strip().startswith('{'))
    sessions=[json.loads(p.read_text()) for p in sorted((out/'employee_sessions').glob('*.json'))]
    work=[s for s in sessions if 'result' in s]
    by_employee=defaultdict(list)
    for s in work:by_employee[s['employee']].append(s)
    assert len(by_employee)==6,'All six employees must actually use Hermes'
    assert len(work)==results['hermes_sessions']
    namespaces=defaultdict(set)
    total_calls=0
    all_files=0
    for s in work:
        state=s['computer_state']
        assert state['backend']=='bubblewrap'
        assert state['workspace_identity']==s['employee']
        namespaces[s['employee']].add(state['namespaces']['mnt'])
        assert s['trace'][0]['observation']['message']==s['decision']['request']
        assert 'expected_procedure' not in json.dumps(s['trace'])
        for d in s['view']['visible_documents']:assert d['published']<=s['day']
        native_result=s['result']['native']
        assert native_result['api_calls']>0
        total_calls+=native_result['api_calls']
        assert any(m.get('role')=='user' and s['decision']['request'] in str(m.get('content'))
                   for m in native_result['messages'])
        if s['diagnostic']['success']:
            committed=[r for r in s['result']['workplace_rpc'] if r['action']['tool']=='work.commit'
                       and r['response'].get('info',{}).get('success')]
            assert committed
            sha=committed[-1]['response']['artifact_sha256']
            assert any(v.get('sha256')==sha for v in s['filesystem_after'].values())
        for name,entry in s['filesystem_after'].items():
            if 'sha256' in entry:
                blob=out/'filesystem_objects'/entry['sha256']
                assert hashlib.sha256(blob.read_bytes()).hexdigest()==entry['sha256']
                all_files+=1
    # Linux may recycle namespace inode numbers after supervisor restart.
    # Compare the six contemporaneous final worker states, not inode unions
    # spanning disconnected supervisor lifetimes.
    final_computers=[json.loads(p.read_text()) for p in (out/'computers').glob('*/computer_state.json')]
    assert len(final_computers)==6
    assert len({s['namespaces']['mnt'] for s in final_computers})==6
    assert len({s['namespaces']['net'] for s in final_computers})==6
    assert any(len(v)>1 for v in by_employee.values()),'No longitudinal Hermes interaction occurred'
    persistent_files=0
    for seq in by_employee.values():
        for a,b in zip(seq,seq[1:]):
            notes={k:v for k,v in a['filesystem_after'].items() if k.startswith(('notes/','deliverables/'))}
            for k,v in notes.items():
                assert b['filesystem_before'].get(k)==v,('Employee files reset between sessions',k)
                persistent_files+=1
    # Work-step rewards plus delayed kernel effects and institution expenses.
    tool_reward=sum(ev['reward'] for s in work for ev in s['trace'] if ev['type']=='transition')
    delayed_reward=sum(ev['payload'].get('reward',0) for ev in timeline if ev['kind'].startswith('work.'))
    strategy_cost=-2*sum(d['actor'].startswith('firm-') and d['decision']['procedure']!='keep' for d in decisions)
    total=round(tool_reward+delayed_reward+strategy_cost,2)
    assert total==results['business_utility'],(total,results['business_utility'])
    counts=Counter(e['kind'] for e in timeline)
    changes=[e for e in timeline if e['kind']=='enterprise_decision' and e['payload']['before']!=e['payload']['after']]
    summary={'validated':True,'checks':['pinned Persona records match all native profiles',
        'MiroFish outputs found in native OASIS database','causal edges refer to prior events',
        'competitor privacy and time boundaries','six real Hermes users with distinct bubblewrap namespaces',
        'native model trajectories contain actual employee requests','commits match real file content hashes',
        'files persist between workdays','all business rewards reconcile'],
        'hermes_sessions':len(work),'hermes_model_calls':total_calls,'persistent_file_links':persistent_files,
        'verified_file_instances':all_files,'objective_or_offer_changes':len(changes),'event_counts':dict(counts),
        'business_utility':total}
    save(out/'VALIDATION.json',summary)
    learner=out/'learner';learner.mkdir(exist_ok=True)
    with (learner/'sessions.jsonl').open('w') as f:
        for s in work:
            row={k:s[k] for k in ('day','employee','task_id','trace','filesystem_before','filesystem_after','filesystem_delta')}
            row['native_hermes']=s['result']['native']
            row['workplace_rpc']=s['result']['workplace_rpc']
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (learner/'delayed_rewards.jsonl').open('w') as f:
        for e in timeline:
            if e['kind'].startswith('work.') and 'reward' in e['payload']:
                f.write(json.dumps({'day':e['day'],'enterprise':e['actor'],'reward':e['payload']['reward'],
                                   'task_id':e['payload'].get('task_id'),'event_id':e['id']})+'\n')
    # Private institution expenses are retained as separate fleet-level rewards.
    save(learner/'institution_costs.json',[
        {'day':d['day'],'enterprise':d['actor'],'reward':-2} for d in decisions
        if d['actor'].startswith('firm-') and d['decision']['procedure']!='keep'])
    lines=['# Persistent ecosystem: actual run','',
        f"{results['days']} simulated days; 2 enterprises, 1 government agency, 3 consumers, 6 employees with dedicated Hermes/bubblewrap computers.",'',
        f"{len(work)} actual Hermes work sessions; {results['completed_tasks']} completed tasks; {results['pending_tasks']} pending at the horizon. {total_calls} native Hermes model calls. No RL training was performed.",'',
        '## Observed enterprise decisions','',
        '| Day | Company | Objective before → after | Price | Market | Route decision |',
        '|---|---|---|---|---|---|']
    for d in decisions:
        if not d['actor'].startswith('firm-'):continue
        a=d['decision'];old=d['view']['own_state']
        lines.append(f"| {d['day']} | {d['actor']} | {old['objective']} → {a['objective']} | {a['price']} | {a['target_market']} | {a['procedure']} |")
    lines+=['','## Recorded consequences','',
        f"- Government decisions: {counts['government_decision']}; policy activations: {counts['policy_delivered']}; expiries: {counts['policy_expired']}.",
        f"- Consumer decisions: {counts['consumer_decision']}; orders: {counts['order_placed']}; payments: {counts['consumer_payment']}.",
        f"- {persistent_files} unchanged note/deliverable files verified across successive work sessions.",
        f"- Simulation business utility: {total}; this is not API spend.",'',
        '## Files and evidence','',
        '- `timeline.json`: ordered causal events, institutional choices and delayed consequences.',
        '- `actor_sessions/`: actual MiroFish decisions and their authorized observations.',
        '- `employee_sessions/`: employee requests, Hermes native trajectories, file changes and private diagnostics.',
        '- `computers/<employee>/workspace/`: real inbox, notes and deliverables.',
        '- `computers/<employee>/hermes/`: separate native Hermes histories, memory and skills.',
        '- `filesystem_objects/`: old and new file contents addressed by SHA-256.',
        '- `learner/`: observations, native trajectories and rewards without private diagnostic fields.',
        '- `VALIDATION.json`: offline audit results.','',
        'This is an integration PoC, not a controlled benchmark. Early integration errors and bounded-session failures remain in its trace. The current adapter corrects draft-file descriptions and replenishes the per-session compute budget without resetting learned state. The simulator uses simplified business checks; broader semantic task quality and institutional realism remain unvalidated.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('out')
    print(json.dumps(validate(p.parse_args().out),indent=2))
