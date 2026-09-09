import json
from pathlib import Path
import tempfile
import unittest
from lifespan.ecosystem import Ecosystem, WORKFLOWS
from lifespan.computers import Computer, file_delta, snapshot_files
from lifespan.environment import SessionEnv


def strategy(**kw):
    return dict(objective='resilience',price=9,target_market='domestic',priority_workflow='incident',
                procedure='alternate_route',notes='Observed disruption',reason='Respond to corridor risk',
                evidence_ids=[],**kw)


class EcosystemTests(unittest.TestCase):
    def test_firm_objective_changes_executable_route_allocation_and_market(self):
        e=Ecosystem()
        e.advance()
        w=e.worlds['firm-0']
        task=next(iter(w.tasks.values()))
        e.apply_decision('firm-0',strategy(),e.actor_view('firm-0'))
        self.assertEqual(e.firms['firm-0']['objective'],'resilience')
        self.assertEqual(e.firms['firm-0']['cash'],98)
        self.assertEqual(w.expected(task)['endpoint'],'workspace-v1')
        e.advance()
        self.assertEqual(w.expected(task)['endpoint'],'workspace-v2')
        self.assertEqual(e.public_view()['enterprises'][0]['price'],9)
        # A company exiting cross-border cannot accept a new cross-border buyer.
        with self.assertRaises(ValueError):
            e.apply_decision('consumer-2',{'action':'purchase','firm':'firm-0','notes':'','reason':'','evidence_ids':[]},
                             e.actor_view('consumer-2'))

    def test_private_competitor_state_and_future_shocks_not_observed(self):
        e=Ecosystem()
        e.advance()
        e.firms['firm-1']['cash']=123456
        view=e.actor_view('firm-0')
        self.assertNotIn('123456',json.dumps(view))
        self.assertNotIn('disrupted',json.dumps(view))
        self.assertEqual(view['geopolitics']['corridor'],'open')
        self.assertNotIn('complaints',view['government'])

    def test_geopolitics_does_not_script_institutional_response(self):
        e=Ecosystem()
        for _ in range(5): e.advance()
        self.assertEqual(e.geopolitics['corridor'],'disrupted')
        self.assertEqual(e.agency['policy'],'baseline')
        self.assertTrue(all(f['objective']=='growth' for f in e.firms.values()))

    def test_government_rule_effective_later_all_workflows_then_expires(self):
        e=Ecosystem()
        e.advance()
        a={'policy':'enhanced_review','duration':2,'notes':'','reason':'Concern','evidence_ids':[]}
        e.apply_decision('agency',a,e.actor_view('agency'))
        self.assertEqual(e.agency['policy'],'baseline')
        for w in e.worlds.values():
            self.assertTrue(all('jurisdiction_review' not in w.expected(t)['checks'] for t in w.tasks.values()))
        e.advance()
        self.assertEqual(e.agency['policy'],'enhanced_review')
        for w in e.worlds.values():
            for t in w.tasks.values():
                self.assertIn('jurisdiction_review',w.expected(t)['checks'])
                self.assertTrue(w.expected(t)['redact'])
        e.advance(); e.advance()
        self.assertEqual(e.agency['policy'],'baseline')
        for w in e.worlds.values():
            self.assertTrue(all('jurisdiction_review' not in w.expected(t)['checks'] for t in w.tasks.values()))

    def test_withdrawing_government_policy_preserves_company_route(self):
        e=Ecosystem(); e.advance()
        e.apply_decision('firm-0',strategy(),e.actor_view('firm-0'))
        e.apply_decision('agency',{'policy':'enhanced_review','duration':8,'notes':'','reason':'risk','evidence_ids':[]},e.actor_view('agency'))
        e.advance()
        e.apply_decision('agency',{'policy':'baseline','duration':2,'notes':'','reason':'cleared','evidence_ids':[]},e.actor_view('agency'))
        e.advance()
        for t in e.worlds['firm-0'].tasks.values():
            self.assertEqual(e.worlds['firm-0'].expected(t)['endpoint'],'workspace-v2')
            self.assertFalse(e.worlds['firm-0'].expected(t)['redact'])

    def test_consumer_order_payment_depends_on_real_completion_and_delay(self):
        e=Ecosystem(); e.advance()
        c=e.consumers['consumer-2']
        e.apply_decision(c['id'],{'action':'purchase','firm':'firm-0','notes':'','reason':'offer','evidence_ids':[]},e.actor_view(c['id']))
        self.assertEqual(c['budget'],160)
        tid=c['pending'][0]['task_id']
        e.advance()
        w=e.worlds['firm-0']; task=w.tasks[tid]
        w.complete(task,'session-real')
        e.record_session('firm-0',task,'session-real',{'success':True},{})
        self.assertEqual(c['budget'],160)
        e.advance(); e.advance()
        self.assertEqual(c['budget'],150)
        self.assertEqual(c['provider'],'firm-0')
        self.assertEqual(e.firms['firm-0']['revenue'],10)
        payment=next(ev for ev in e.events if ev['kind']=='consumer_payment' and ev['actor']==c['id'])
        kinds={ev['id']:ev['kind'] for ev in e.events}
        self.assertEqual({kinds[x] for x in payment['causes']},{'order_placed','employee_work'})
        # Renewals require consumer choice in this ecosystem, not automatic duplicate orders.
        self.assertFalse(any(t['parent']==tid for t in w.scheduled))

    def test_complaint_requires_observed_failure_and_arrives_later(self):
        e=Ecosystem(); e.advance()
        a={'action':'complain','firm':'firm-0','notes':'','reason':'late','evidence_ids':[]}
        with self.assertRaises(ValueError):e.apply_decision('consumer-0',a,e.actor_view('consumer-0'))
        for _ in range(4):e.advance()
        e.apply_decision('consumer-0',a,e.actor_view('consumer-0'))
        self.assertEqual(e.agency['complaints'],[])
        e.advance()
        self.assertEqual(len(e.agency['complaints']),1)

    def test_local_review_cannot_remove_regulation_and_does_not_keep_it_after_expiry(self):
        from lifespan.integrated import enact_proposal
        e=Ecosystem();e.advance()
        e.apply_decision('agency',{'policy':'enhanced_review','duration':2,'notes':'','reason':'risk','evidence_ids':[]},e.actor_view('agency'))
        e.advance()
        w=e.worlds['firm-0'];task=next(iter(w.tasks.values()))
        d={'process_proposal':{'action':'require_peer_review','reason':'Observed failed work'}}
        enact_proposal(w,task,d,{task.owner:{'success':False,'task_id':'failure'}})
        e.advance()
        self.assertIn('jurisdiction_review',w.expected(task)['checks'])
        self.assertIn('peer_review',w.expected(task)['checks'])
        e.advance()
        self.assertNotIn('jurisdiction_review',w.expected(task)['checks'])
        self.assertIn('peer_review',w.expected(task)['checks'])

    def test_alternate_route_avoids_disruption_delay_on_future_orders(self):
        e=Ecosystem()
        for _ in range(5):e.advance()
        # Consumer-2 has no existing reservations and can compare both routes.
        plain=Ecosystem.restore(e.checkpoint())
        plain.order('consumer-2','firm-0','onboarding',None)
        delayed=plain.worlds['firm-0'].scheduled[-1]
        a=strategy();a['target_market']='cross_border'
        e.apply_decision('firm-0',a,e.actor_view('firm-0'))
        e.advance()
        e.order('consumer-2','firm-0','onboarding',None)
        routed=e.worlds['firm-0'].scheduled[-1]
        self.assertEqual(delayed['created'],7)
        self.assertEqual(routed['created'],6)
        self.assertEqual(routed['due'],9)

    def test_checkpoint_restores_queued_effects_and_continues_identically(self):
        e=Ecosystem(); e.advance()
        e.apply_decision('agency',{'policy':'enhanced_review','duration':5,'notes':'','reason':'risk','evidence_ids':[]},e.actor_view('agency'))
        other=Ecosystem.restore(json.loads(json.dumps(e.checkpoint())))
        for _ in range(7):e.advance(); other.advance()
        self.assertEqual(e.checkpoint(),other.checkpoint())
        other.firms['firm-0']['price']=19
        self.assertNotEqual(e.firms['firm-0']['price'],19)

    def test_causal_evidence_cannot_reference_unseen_or_future_events(self):
        e=Ecosystem();e.advance()
        a=strategy();a['evidence_ids']=['future']
        before=e.checkpoint()
        with self.assertRaises(ValueError):e.apply_decision('firm-0',a,e.actor_view('firm-0'))
        self.assertEqual(before,e.checkpoint())


class ComputerTests(unittest.TestCase):
    def test_real_file_required_and_edit_invalidates_prepared_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Computer(tmp,'one')
            e=Ecosystem();e.advance();w=e.worlds['firm-0'];task=next(iter(w.tasks.values()))
            env=SessionEnv(w,task)
            request={'tool':'draft.prepare','args':{'artifact_path':'/workspace/deliverables/task.json'}}
            self.assertFalse(c.action(env,request)['ok'])
            plan=w.expected(task)
            artifact={'task_id':task.id,'channel':plan['channel'],'redact':False,'endpoint':plan['endpoint'],'content':'Deliverable'}
            p=c.workspace/'deliverables/task.json';p.write_text(json.dumps(artifact))
            self.assertTrue(c.action(env,request)['observation']['result']['ok'])
            c.action(env,{'tool':'check.perform','args':{'name':'customer_check'}})
            c.action(env,{'tool':'approval.request','args':{'approver':plan['approver']}})
            artifact['content']='Changed after approval';p.write_text(json.dumps(artifact))
            self.assertFalse(c.action(env,{'tool':'work.commit','args':{}})['ok'])
            self.assertEqual(task.status,'pending')
            c.action(env,request)
            c.action(env,{'tool':'check.perform','args':{'name':'customer_check'}})
            c.action(env,{'tool':'approval.request','args':{'approver':plan['approver']}})
            self.assertTrue(c.action(env,{'tool':'work.commit','args':{}})['info']['success'])

    def test_artifact_traversal_and_cross_employee_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Computer(tmp,'a'),Computer(tmp,'b')
            target=b.workspace/'deliverables/private.json';target.write_text('{}')
            (a.workspace/'deliverables/escape.json').symlink_to(target)
            for path in ('/workspace/deliverables/escape.json','/workspace/deliverables/../../b/private.json','/etc/passwd'):
                with self.assertRaises(ValueError):a.read_artifact(path,'task')

    def test_file_content_history_preserves_old_and_new_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Computer(tmp,'a');p=c.workspace/'notes/process.md'
            p.write_text('old process');before=c.snapshot()
            p.write_text('new process');after=c.snapshot()
            self.assertIn('notes/process.md',file_delta(before,after)['modified'])
            self.assertEqual((c.objects/before['notes/process.md']['sha256']).read_text(),'old process')
            # A fresh wrapper for the same identity preserves filesystem contents.
            again=Computer(tmp,'a')
            self.assertEqual(again.snapshot(),after)

    def test_publishing_new_work_does_not_reset_employee_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Computer(tmp,'a')
            p=c.workspace/'notes/process.md';p.write_text('employee learned procedure')
            c.publish({'day':1},{'objective':'growth'},[])
            c.publish({'day':2},{'objective':'reliability'},[])
            self.assertEqual(p.read_text(),'employee learned procedure')
            self.assertEqual(json.loads((c.workspace/'company/objectives.json').read_text())['objective'],'reliability')

if __name__=='__main__':unittest.main()
