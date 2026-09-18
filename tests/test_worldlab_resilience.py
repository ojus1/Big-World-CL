"""Run real controllers through failures; later days, arms and audits must survive."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import read, save
from worldlab.attempts import execute_task
from worldlab.audit_worlds import audit, audit_attempt
from worldlab.audit_reacting import replay_commands
from worldlab.contracts import Budget
from worldlab.worlds import prepare_study, execute_study
from worldlab.resilience import attempt_seconds
from worldlab.hermes import Hermes
from worldlab.experience_update import replay_admission
from lifespan.evaluation.skillopt import DEFAULT_SOURCE
from test_worldlab_judge_adapter import Bank, Harness, Judge, ReplayLearner
from test_worldlab_worlds import SPEC
from test_worldlab_reacting import Driver, Factory


class FlakyHarness(Harness):
    def run(self, request, artifact_root):
        if request.attempt_id.startswith('d000'):
            raise ConnectionError('Injected lost execution; do not expose provider text')
        return super().run(request, artifact_root)


class FlakyJudge(Judge):
    def grade(self, task_id, workspace, baseline, out, **kwargs):
        if out.parent.name.startswith('d001'):
            raise TimeoutError('Injected lost judge receipt')
        return super().grade(task_id, workspace, baseline, out, **kwargs)


class BrokenLearner(ReplayLearner):
    def update(self, *args, **kwargs):
        raise TimeoutError('Injected failed learning epoch')


class FlakyDriver(Driver):
    def decide(self, view, key, validate):
        if view['day'] == 2:
            raise TimeoutError('Injected employee decision failure')
        return super().decide(view, key, validate)


class FlakyFactory(Factory):
    def open(self, world, context, out):
        driver = FlakyDriver(); self.drivers.append(driver); return driver


class Tests(unittest.TestCase):
    def test_new_studies_default_to_continuation_and_manual_stop_still_works(self):
        from worldlab.cancellation import Cancellation, StudyCancelled
        from worldlab.dispatch import dispatch_day
        with tempfile.TemporaryDirectory() as tmp:
            spec={k:v for k,v in SPEC.items() if k!='failure_policy'}
            out=Path(tmp)/'study'
            prepare_study(Bank(),spec,[211],Harness(),Judge(),ReplayLearner(),out)
            self.assertEqual(read(out/'STUDY.json')['worlds'][0]['specification']['failure_policy'],'record_and_continue')
            cancellation=Cancellation(out);cancellation.request('OperatorStop')
            with self.assertRaises(StudyCancelled):
                dispatch_day([{'id':'one','employee_id':'writer'}],lambda _:self.fail('Dispatched after stop'),
                             lambda *args:None,lambda *args:None,cancellation=cancellation,continue_on_error=True)

    def test_parallel_failed_updates_do_not_cancel_later_employees(self):
        from worldlab.experience_update import dispatch_updates
        from worldlab.cancellation import Cancellation
        selected=[{'id':'observed','split':'train','day':0,'feedback_day':1,'lineage_group':'family',
                   'task_id':'train-0','grade':{'feedback':'Observed'},'work_budget':Budget().__dict__}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recorded=[];waves=[]
            dispatch_updates(Bank(),Harness(),Judge(),BrokenLearner(),[(e,selected) for e in ('a','b','c')],
                day=2,skills={e:'seed' for e in ('a','b','c')},out=root,
                record=lambda e,r:recorded.append((e,r)),journal=waves.append,max_parallel=2,
                cancellation=Cancellation(root),continue_on_error=True)
            self.assertEqual([e for e,_ in recorded],['a','b','c'])
            self.assertTrue(all(r['status']=='failed' and not r['accepted'] and r['skill']=='seed' for _,r in recorded))
            self.assertEqual(waves[-1],[])
            self.assertFalse((root/'STOP_REQUESTED.json').exists())

    @unittest.skipUnless(DEFAULT_SOURCE.is_dir(),'Pinned upstream required')
    def test_real_skillopt_preserves_unknown_replay_cost_and_audits_failed_epoch(self):
        from worldlab.learning import SkillOpt
        from worldlab.experience_update import update_employee
        from worldlab.audit_failures import audit_failed_learning
        class LostJudge(Judge):
            def grade(self,*args,**kwargs):
                return {'grading_complete':False,'success':False,'quality_score':None,'feedback':'',
                        'usage':{'physical_model_calls':1,'charged_tokens':50,'accounting_complete':False}}
        selected=[{'id':split+'-0','task_id':split+'-0','split':label,'day':0,'feedback_day':1,
                   'lineage_group':split,'grade':{'feedback':'Observed'},'work_budget':Budget(seconds=900).__dict__}
                  for split,label in [('train','train'),('validation','val')]]
        learner=SkillOpt(DEFAULT_SOURCE,'fixture','http://127.0.0.1:8011/v1')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bank,harness,judge=Bank(),Harness(),LostJudge()
            update=update_employee(bank,harness,judge,learner,selected,employee='writer',day=2,skill='seed',
                                   update_root=root,continue_on_error=True)
            self.assertEqual(update['status'],'failed')
            self.assertFalse(update['costs']['accounting_complete'])
            self.assertEqual(update['replay_evidence'],[])
            self.assertEqual(len(update['unscored_replay_evidence']),1)
            counts={'learning_replays':0}
            audit_failed_learning(bank,root,update,selected,'seed',harness,judge,learner.identity(),counts)
            self.assertEqual(counts['learning_replays'],1)
            changed=deepcopy(update);changed['costs']['tokens']-=1
            with self.assertRaises(ValueError):
                audit_failed_learning(bank,root,changed,selected,'seed',harness,judge,learner.identity(),counts)

    def test_settlement_cannot_consume_judging_window(self):
        budget = Budget(seconds=1800)
        self.assertEqual(attempt_seconds(Hermes, budget), 2725)
        self.assertEqual(replay_admission({'timeout_seconds':2100,'max_model_calls':50,'max_tokens':10000},
            budget.__dict__, Hermes)['minimum'], 2725)
        now = [100.]
        class Settling(Harness):
            wall_seconds = staticmethod(lambda b: b.seconds + 625)
            def run(self, *args):
                result = super().run(*args); now[0] += 2052; return result
        class Capturing(Judge):
            def grade(self, *args, **kwargs):
                self.timeout = kwargs['timeout_seconds']; return super().grade(*args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch('worldlab.attempts.time.monotonic', side_effect=lambda:now[0]):
            judge = Capturing()
            result = execute_task(Bank(), Settling(), judge, task_id='train-0', employee_id='writer',
                skill='seed', budget=budget, out=Path(tmp)/'case')
            self.assertEqual(judge.timeout,300)
            self.assertEqual(result['status'],'completed')

    def test_ungraded_online_and_lost_learning_continue_all_days_and_pass_failure_audit(self):
        spec = {**deepcopy(SPEC), 'failure_policy':'record_and_continue'}
        for parallel in (1,2):
            with self.subTest(parallel=parallel), tempfile.TemporaryDirectory() as tmp:
                spec['max_parallel_worlds'] = parallel
                out=Path(tmp)/'study';bank,harness,judge,learner=Bank(),FlakyHarness(),FlakyJudge(),BrokenLearner()
                prepare_study(bank,spec,[211,223],harness,judge,learner,out)
                result=execute_study(bank,harness,judge,learner,out)
                self.assertEqual(result['status'],'completed')
                self.assertEqual(len(result['world_pairs']),2)
                self.assertFalse((out/'STOP_REQUESTED.json').exists())
                for state_path in out.glob('worlds/*/*/STATE.json'):
                    root=state_path.parent
                    state=read(root/'STATE.json')
                    self.assertEqual(len(state['sessions']),10)
                    self.assertEqual(state['sessions'][0]['status'],'infrastructure_error')
                    self.assertEqual(state['sessions'][1]['status'],'grading_error')
                    self.assertIsNone(state['sessions'][0]['grade'])
                    self.assertEqual(state['sessions'][-1]['status'],'completed')
                    self.assertFalse((root/'INFLIGHT.json').exists())
                    self.assertFalse(read(root/'REPORT.json')['failures']['accounting_complete'])
                self.assertTrue(audit(bank,out,harness,learner,judge)['ok'])

    def test_reacting_errors_defer_without_fake_decisions_or_semantic_scores(self):
        spec={**deepcopy(SPEC),'failure_policy':'record_and_continue'}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'study';bank,harness,judge,learner=Bank(),FlakyHarness(),FlakyJudge(),BrokenLearner()
            factory=FlakyFactory()
            prepare_study(bank,spec,[211],harness,judge,learner,out,factory)
            result=execute_study(bank,harness,judge,learner,out,factory)
            self.assertEqual(result['status'],'completed')
            world=read(out/'STUDY.json')['worlds'][0]
            for state_path in out.glob('worlds/*/*/STATE.json'):
                root=state_path.parent
                state=read(root/'STATE.json')
                replay_commands(bank,world,state)
                self.assertEqual(len(state['decision_failures']),1)
                self.assertFalse(any(d['day']==2 for d in state['decisions']))
                self.assertTrue(any(s['day']==9 for s in state['sessions']))
                self.assertFalse(any(o['status']=='working' for o in state['workplace']['obligations'].values()))
                self.assertFalse(any(s['status']!='completed' and s['grade'] is not None for s in state['sessions']))
                self.assertFalse((root/'INFLIGHT.json').exists())

    def test_partial_grade_keeps_unknown_usage_and_cannot_pass_success_audit(self):
        class Partial(Judge):
            def grade(self,*args,**kwargs):
                return {'grading_complete':False,'success':False,'quality_score':None,'feedback':'',
                        'usage':{'physical_model_calls':1,'charged_tokens':50,'accounting_complete':False}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'case';bank,harness,judge=Bank(),Harness(),Partial()
            result=execute_task(bank,harness,judge,task_id='train-0',employee_id='writer',skill='seed',
                                budget=Budget(),out=root,continue_on_error=True)
            self.assertEqual(result['status'],'grading_incomplete')
            self.assertFalse(result['accounting_complete'])
            audit_attempt(bank,root,'train-0','seed',harness,judge=judge,allow_incomplete=True)
            with self.assertRaises(ValueError):
                audit_attempt(bank,root,'train-0','seed',harness,judge=judge)
            changed=read(root/'ATTEMPT.json');changed['tokens']-=1;save(root/'ATTEMPT.json',changed)
            with self.assertRaises(ValueError):
                audit_attempt(bank,root,'train-0','seed',harness,judge=judge,allow_incomplete=True)


if __name__=='__main__': unittest.main()
