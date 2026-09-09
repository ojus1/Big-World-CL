"""Chronological protocol and state-integrity tests. No model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from lifespan.computers import Computer
from lifespan.ecosystem import Ecosystem
from lifespan.environment import SessionEnv
from lifespan.evaluation.protocol import ExperimentConfig, SEED_SKILL, scenario, regime_at, select_experiences
from lifespan.evaluation.runtime import install_skill, native_usage, write_public_files
from lifespan.evaluation.tasks import make_case, grade_case
from lifespan.tests.test_evaluation_tasks import solve_public
from lifespan.mirofish import MiroFishRuntime


class ProtocolTests(unittest.TestCase):
    def test_regimes_are_ordered_and_splits_disjoint(self):
        for days in range(8, 37):
            for seed in (0, 1, 999998, 999999):
                a = scenario(ExperimentConfig(days=days, seed=seed))
                b = scenario(ExperimentConfig(days=days, seed=seed, split='test'))
                self.assertLess(a['seed'], b['seed'])
                self.assertLess(0, a['change_day'])
                self.assertLess(a['change_day'], a['exception_window'][0])
                self.assertLess(a['exception_window'][0], a['reversal_day'])
                self.assertLess(a['reversal_day'], days)
                self.assertEqual({regime_at(a, d) for d in range(days)}, {'base','changed','exception','reversal'})

    def test_invalid_contracts_fail_before_calls(self):
        for kwargs in ({'days':7}, {'seed':-1}, {'seed':True}, {'seed':1000000},
                       {'max_iterations':False}, {'algorithm':'fake'}, {'state_mode':'all_history'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ExperimentConfig(**kwargs)

    def test_delayed_feedback_and_duplicate_obligations(self):
        def r(id, source, day, split='train', **kw):
            return dict(id=id, source_session=source, employee='a', available_day=day,
                        split=split, feedback_available_day=day, **kw)
        rows=[r('old','t1',0), r('new','t1',1), r('second','t2',1), r('validation','v1',1,'val'),
              r('future','t3',4), r('late_feedback','t4',1)]
        rows[-1]['feedback_available_day']=4
        rows.append(dict(rows[2],id='other',employee='b'))
        before=deepcopy(rows)
        self.assertEqual([r['id'] for r in select_experiences(rows,'a',2,2,1)], ['new','second','validation'])
        self.assertEqual(rows,before)

    def test_unknown_receipts_never_become_zero_cost(self):
        usage=native_usage({'api_calls':2,'input_tokens':4,'output_tokens':8,'total_tokens':12,
                            'estimated_cost_usd':0,'cost_status':'unknown'})
        self.assertFalse(usage['complete']); self.assertIsNone(usage['total_tokens'])
        self.assertIsNone(usage['estimated_cost_usd'])
        usage=native_usage({'api_calls':1, 'evaluation_budget':{'physical_model_calls':2,
            'input_tokens':120,'output_tokens':10,'total_tokens':130,'charged_tokens':130,'accounting_complete':True}})
        self.assertTrue(usage['complete']); self.assertEqual(usage['api_calls'],2)
        self.assertEqual(usage['native_logical_calls'],1); self.assertEqual(usage['total_tokens'],130)

    def test_native_skills_and_task_files_are_separate_and_safe(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            a=install_skill(root/'a', SEED_SKILL); b=install_skill(root/'b', SEED_SKILL+'\nChange')
            self.assertNotEqual(a['content_sha256'],b['content_sha256'])
            for path in ('../truth.json','/tmp/truth.json'):
                with self.assertRaises(ValueError): write_public_files(root, {path:'secret'})
            (root/'escape').symlink_to(root.parent,target_is_directory=True)
            with self.assertRaises(ValueError): write_public_files(root, {'escape/truth.json':'secret'})

    def test_actor_deadline_preserves_get_method_and_blocks_new_requests(self):
        from unittest.mock import Mock
        runtime=MiroFishRuntime.__new__(MiroFishRuntime)
        runtime.client=Mock()
        runtime.client.get.return_value.json.return_value={'data':{'ok':True}}
        runtime.evaluation_deadline=time.monotonic()+30
        self.assertEqual(runtime.call('/api/graph/project/x'),{'ok':True})
        runtime.client.get.assert_called_once()
        runtime.client.post.assert_not_called()
        runtime.evaluation_deadline=time.monotonic()-1
        with self.assertRaises(TimeoutError): runtime.call('/api/graph/project/x')
        self.assertEqual(runtime.client.get.call_count,1)


class CommitTests(unittest.TestCase):
    def test_quality_is_checked_before_business_and_commit_snapshot_is_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            eco=Ecosystem(12,101); eco.advance(); w=eco.worlds['firm-0']; t=next(iter(w.tasks.values()))
            case=make_case(t.workflow,101,0,t.id,'base','online',exception_window=[4,6])
            c=Computer(root,'employee',artifact_grader=lambda a:grade_case(case,a))
            env=SessionEnv(w,t); expected=w.expected(t)
            artifact=dict(task_id=t.id,channel=expected['channel'],redact=expected['redact'],
                          endpoint=expected['endpoint'],content='{"placeholder":true}')
            local=c.workspace/'deliverables/result.json'
            def prepare():
                local.write_text(json.dumps(artifact))
                c.action(env,{'tool':'draft.prepare','args':{'artifact_path':'/workspace/deliverables/result.json'}})
                for check in expected['checks']:
                    c.action(env,{'tool':'check.perform','args':{'name':check}})
                c.action(env,{'tool':'approval.request','args':{'approver':expected['approver']}})
            prepare(); c.action(env,{'tool':'work.commit','args':{}})
            self.assertFalse(env.success); self.assertEqual(t.status,'pending'); self.assertFalse(w.ledger)
            artifact['content']=json.dumps(solve_public(t.workflow,case['public_files']))
            prepare(); c.action(env,{'tool':'work.commit','args':{}})
            self.assertTrue(env.success); self.assertEqual(len(w.ledger),1)
            committed=deepcopy(c.committed_artifact)
            local.write_text(json.dumps(dict(artifact,content='{"private_learning_note":"UNVALIDATED"}')))
            self.assertEqual(c.committed_artifact,committed)
            self.assertTrue(grade_case(case,c.committed_artifact)['success'])

    def test_bad_artifact_shape_and_duplicate_keys_are_observed_errors(self):
        with tempfile.TemporaryDirectory() as root:
            c=Computer(root,'employee'); local=c.workspace/'deliverables/result.json'
            for raw in ('[]','1','null','{"task_id":"x","task_id":"y"}'):
                local.write_text(raw)
                with self.assertRaises(ValueError): c.read_artifact('/workspace/deliverables/result.json','x')


if __name__=='__main__': unittest.main()
