from copy import deepcopy
import json
from pathlib import Path
import unittest

from lifespan.personas import decode
from lifespan.environment import SessionEnv
from lifespan.integrated import employee_view, validate_decision, enact_proposal, deliver
from lifespan.mirofish import parse_object
from lifespan.world import World, generate_blueprint, Task


class IntegratedTests(unittest.TestCase):
    def scenario(self):
        world = World(generate_blueprint(7, 28))
        world.advance(0)
        task = world.tasks["job-0-onboarding"]
        view = employee_view(world,task,{}, {}, {})
        decision = {"delegate": True, "request": "Please onboard the customer.", "working_notes": "Check the procedure.",
                    "share_document_ids": ["base-onboarding"], "colleague_messages": [], "process_proposal": None}
        return world,task,view,decision

    def test_packed_persona_decoding_with_missing_and_overrides(self):
        cols=[{"id":"a","values":["low","high"]}, {"id":"b","values":["slow","fast"]}]
        self.assertEqual(decode(bytes([0x10]),None,cols),{"a":"low","b":"fast"})
        self.assertEqual(decode(bytes([0x10]),bytes([1]),cols,{"b":"custom"}),{"b":"custom"})

    def test_actual_cohort_is_distinct_synthetic_and_has_provenance(self):
        path=Path(__file__).resolve().parents[1]/"data/cohort.json"
        if not path.exists():
            self.skipTest("Run the explicit Persona importer first")
        cohort=json.loads(path.read_text())
        self.assertEqual(len({p["persona_id"] for p in cohort["personas"]}),6)
        self.assertTrue(all(p["source"]=="synthetic" and p["work_attributes"] for p in cohort["personas"]))
        self.assertEqual(len(cohort["shard_sha256"]),64)
        self.assertTrue(all(p["revision"]==cohort["revision"] for p in cohort["personas"]))

    def test_employee_view_has_no_future_or_other_department_evidence(self):
        world,task,view,_=self.scenario()
        self.assertTrue(all(d["published"]<=0 and d["workflow"]==task.workflow for d in view["visible_documents"]))
        self.assertNotIn("tool-migration",json.dumps(view))
        self.assertNotIn("expected_procedure",json.dumps(view))

    def test_model_cannot_share_unseen_document(self):
        _,_,view,d=self.scenario()
        d["share_document_ids"]=["tool-migration"]
        with self.assertRaises(ValueError): validate_decision(d,view)

    def test_colleague_channel_enforces_acl(self):
        _,_,view,d=self.scenario()
        d["colleague_messages"]=[{"recipient":"renewal-regulated","text":"hello","document_ids":[]}]
        with self.assertRaises(ValueError): validate_decision(d,view)

    def test_real_employee_request_and_clarification_reach_learner(self):
        world,task,_,d=self.scenario()
        calls=[]
        def ask(q):
            calls.append(q)
            return "Employee-generated clarification"
        env=SessionEnv(world,task,employee_message="Model generated request",employee_ask=ask,shared_inbox=[])
        self.assertEqual(env.observation["message"],"Model generated request")
        self.assertEqual(env.observation["inbox"],[])
        obs,*_=env.step({"tool":"employee.ask","args":{"question":"Who approves?"}})
        self.assertEqual(calls,["Who approves?"])
        self.assertEqual(obs["result"]["response"],"Employee-generated clarification")

    def test_employee_proposal_requires_observed_failure_and_applies_later(self):
        world,task,view,d=self.scenario()
        d["process_proposal"]={"action":"require_peer_review","reason":"Previous work was rejected"}
        self.assertFalse(enact_proposal(world,task,d,{})["accepted"])
        result=enact_proposal(world,task,d,{task.owner:{"success":False,"task_id":"prior"}})
        self.assertTrue(result["accepted"])
        self.assertNotIn("peer_review",world.expected(task)["checks"])
        world.advance(1)
        self.assertIn("peer_review",world.expected(task)["checks"])

    def test_colleague_messages_are_delayed_and_change_received_knowledge(self):
        world,task,_,_=self.scenario()
        msg={"id":"m1","sender":task.owner,"recipient":"onboarding-regulated","deliver_day":1,
             "document_ids":["base-onboarding"],"text":"Please use the current onboarding steps."}
        box={}
        deliver(world,[msg],box)
        self.assertEqual(box,{})
        world.advance(1)
        deliver(world,[msg],box)
        self.assertEqual(box[msg["recipient"]][0]["text"],msg["text"])

    def test_invalid_employee_text_is_not_silently_replaced(self):
        with self.assertRaises(ValueError): parse_object("I would delegate this task.")
        with self.assertRaises(ValueError): parse_object("[]")


if __name__ == "__main__": unittest.main()
