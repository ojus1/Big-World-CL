"""Offline startup fixtures and harmless local child processes; no native/model work."""
from contextlib import ExitStack
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan import computers, startup_observability as observe
from lifespan.evaluation.protocol import ExperimentConfig

ROOT = Path(__file__).resolve().parents[2]
CANARY = 'PRIVATE-fixture-credential-and-prompt-never-journal'
CREDS = {'model': CANARY, 'base_url': 'https://fixture.example.invalid', 'api_key': CANARY}


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        self.computers = []
        self.addCleanup(self.close_pipes)
        self.enterContext(patch.dict(sys.modules, yaml=SimpleNamespace(safe_dump=lambda v: json.dumps(v))))

    def close_pipes(self):
        for computer in self.computers:
            if computer.process is not None:
                for name in ('stdin','stdout'):
                    pipe = getattr(computer.process,name,None)
                    if pipe is not None: pipe.close()

    def rows(self, root, role):
        return [json.loads(line) for line in (root/'startup'/f'{role}.jsonl').read_text().splitlines()]

    def computer(self, enabled=True):
        computer = computers.Computer(self.root/'computers', 'fixture', execution={
            'mode': 'evaluation', 'hermes_startup_observability': enabled})
        self.computers.append(computer)
        return computer

    def child(self, code):
        real = subprocess.Popen
        def launch(*args, **kwargs):
            # Replace the native executable and every argument with fixed harmless code.
            return real([sys.executable, '-S', '-u', '-c', code], **kwargs)
        return patch.object(computers.subprocess, 'Popen', side_effect=launch)

    def test_default_omitted_and_boolean_opt_in(self):
        self.assertNotIn('hermes_startup_observability', ExperimentConfig().public())
        self.assertEqual(observe.executor_options(ExperimentConfig()), {})
        self.assertEqual(observe.manifest_fields(ExperimentConfig()), {})
        config = ExperimentConfig(hermes_startup_observability=True)
        self.assertTrue(config.public()['hermes_startup_observability'])
        self.assertEqual(observe.executor_options(config), {'hermes_startup_observability': True})
        self.assertEqual(observe.manifest_fields(config)['startup_observation_provenance']['version'], observe.VERSION)
        for value in (1, None, 'true'):
            with self.assertRaises(ValueError): ExperimentConfig(hermes_startup_observability=value)

    def test_live_short_child_identity_bound_to_parent_and_worker(self):
        parent = observe.Observer(self.root, 'parent')
        code = ('from lifespan.startup_observability import Observer; import sys,time; '
                "o=Observer(sys.argv[1],'worker',expected_attempt=sys.argv[2]); o.event('worker_entered'); time.sleep(.15)")
        env = {'PATH':os.environ['PATH'], 'PYTHONPATH':str(ROOT)}
        with subprocess.Popen([sys.executable,'-S','-c',code,str(self.root),parent.attempt],env=env) as child:
            parent.event('popen_returned', pid=child.pid)
            self.assertTrue(observe.process_identity(child.pid)['available'])
            self.assertEqual(child.wait(timeout=3),0)
        prow, wrow = self.rows(self.root,'parent')[0], self.rows(self.root,'worker')[0]
        self.assertEqual(prow['attempt_id'],wrow['attempt_id'])
        self.assertEqual(prow['worker_identity'],wrow['worker_identity'])
        self.assertFalse(parent.summary()['usage_known'])
        self.assertFalse(parent.summary()['cleanup_known'])

    def test_missing_identity_remains_unknown_with_original_pid(self):
        with patch.object(Path,'read_text',side_effect=FileNotFoundError(CANARY)):
            result=observe.process_identity(123)
        self.assertEqual(result['pid'],123);self.assertFalse(result['available'])
        self.assertEqual(result['error_type'],'FileNotFoundError')
        self.assertNotIn(CANARY,json.dumps(result))

    def test_io_failure_is_explicit_class_only_and_nonfatal(self):
        parent=observe.Observer(self.root,'parent')
        with patch.object(Path,'open',side_effect=OSError(CANARY)):
            parent.event('popen_returned',pid=os.getpid())
        parent.event('startup_exception',exception=TimeoutError(CANARY))
        row=self.rows(self.root,'parent')[0]
        self.assertEqual(row['observation_errors'],['OSError'])
        self.assertEqual(row['error_type'],'TimeoutError')
        self.assertNotIn(CANARY,json.dumps(row))

    def test_missing_manifest_and_partial_journal_never_claim_ready(self):
        worker=observe.Observer(self.root,'worker')
        worker.event('worker_entered')
        self.assertIsNone(worker.summary()['attempt_id'])
        self.assertIn('FileNotFoundError',worker.summary()['observation_errors'])
        self.assertFalse(worker.summary()['usage_known'])

    def test_failed_initialization_cannot_append_to_previous_attempt(self):
        first=observe.Observer(self.root,'parent');first.event('popen_returned',pid=os.getpid())
        before={p.name:p.read_bytes() for p in (self.root/'startup').iterdir()}
        second=observe.Observer(self.root,'parent');second.event('popen_returned',pid=os.getpid())
        self.assertIn('FileExistsError',second.summary()['observation_errors'])
        self.assertIsNone(second.summary()['attempt_id'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'startup').iterdir()})
        wrong_worker=observe.Observer(self.root,'worker',expected_attempt=second.attempt)
        wrong_worker.event('worker_entered')
        self.assertIn('ValueError',wrong_worker.summary()['observation_errors'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'startup').iterdir()})
        path=self.root/'startup/manifest.json';path.write_text('{}')
        before={p.name:p.read_bytes() for p in (self.root/'startup').iterdir()}
        worker=observe.Observer(self.root,'worker');worker.event('worker_entered')
        self.assertIn('ValueError',worker.summary()['observation_errors'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'startup').iterdir()})

    def test_delayed_worker_retains_pid_and_timeout_without_ready(self):
        c=self.computer()
        try:
            with self.child('import time; time.sleep(.25)'):
                with self.assertRaises(TimeoutError):c.start(CREDS,timeout=.08)
            rows=self.rows(c.root,'parent')
            self.assertEqual([r['stage'] for r in rows],['popen_returned','startup_exception'])
            self.assertTrue(rows[0]['worker_identity']['available'])
            self.assertEqual(rows[-1]['error_type'],'TimeoutError')
            self.assertFalse((c.root/'instance.json').exists())
        finally:c.close()
        self.assertNotIn(CANARY,'\n'.join(p.read_text() for p in (c.root/'startup').glob('*')))

    def test_journal_io_failure_preserves_original_ready_timeout(self):
        c=self.computer();real_event=observe.Observer.event
        def broken_event(observer,stage,**kwargs):
            with patch.object(Path,'open',side_effect=OSError(CANARY)):
                real_event(observer,stage,**kwargs)
        try:
            with self.child('import time; time.sleep(.2)'),patch.object(observe.Observer,'event',broken_event):
                with self.assertRaises(TimeoutError):c.start(CREDS,timeout=.05)
            self.assertEqual(c.startup_observer.summary()['observation_errors'],['OSError','OSError'])
            self.assertEqual(c.startup_observer.summary()['last_stage'],'startup_exception')
            self.assertFalse(c.startup_observer.summary()['usage_known'])
            self.assertFalse((c.root/'instance.json').exists())
        finally:c.close()

    def test_crashed_worker_records_class_without_invented_ready(self):
        c=self.computer()
        try:
            with self.child('raise SystemExit(7)'):
                with self.assertRaises(RuntimeError):c.start(CREDS,timeout=1)
            rows=self.rows(c.root,'parent')
            self.assertEqual(rows[-1]['error_type'],'RuntimeError')
            self.assertNotIn('ready_received',[r['stage'] for r in rows])
        finally:c.close()

    def test_popen_failure_records_no_worker_identity(self):
        c=self.computer()
        try:
            with patch.object(computers.subprocess,'Popen',side_effect=OSError(CANARY)):
                with self.assertRaises(OSError):c.start(CREDS)
            row=self.rows(c.root,'parent')[0]
            self.assertEqual(row['stage'],'startup_exception');self.assertIsNone(row['worker_identity'])
            self.assertEqual(row['error_type'],'OSError')
        finally:c.close()

    def test_real_module_import_failure_journals_before_heavy_import(self):
        parent=observe.Observer(self.root,'parent')
        profile=self.root/'hermes';profile.mkdir()
        env={'PATH':os.environ['PATH'],'PYTHONPATH':str(ROOT),'HERMES_HOME':str(profile),
             'LIFESPAN_EXECUTION_CONFIG':json.dumps({'hermes_startup_observability':True,'_startup_observation_attempt_id':parent.attempt})}
        child=subprocess.run([sys.executable,'-S','-m','lifespan.hermes_worker'],cwd=self.root,env=env,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        self.assertNotEqual(child.returncode,0)
        rows=self.rows(self.root,'worker')
        self.assertEqual([r['stage'] for r in rows],['worker_entered','imports_before','startup_exception'])
        self.assertEqual(rows[-1]['error_type'],'ModuleNotFoundError')

    def test_all_worker_stages_with_strictly_fake_dependencies(self):
        from lifespan import hermes_worker
        profile=self.root/'hermes';profile.mkdir()
        parent=observe.Observer(self.root,'parent')
        sandbox=SimpleNamespace(sandbox=SimpleNamespace(process=SimpleNamespace(pid=os.getpid()),rpc_socket='fixture-socket'),cleanup=lambda:None)
        terminal=SimpleNamespace(terminal_tool=lambda **kw:json.dumps({'exit_code':0,'output':'/workspace\nfixture\n'}),
            register_task_env_overrides=lambda *args:None,_active_environments={'default':sandbox})
        class Agent:
            def __init__(self,**kwargs):self.tools=[]
        modules={'tools':SimpleNamespace(skills_tool=SimpleNamespace()),
            'tools.registry':SimpleNamespace(registry=SimpleNamespace(register=lambda **kw:None)),
            'toolsets':SimpleNamespace(create_custom_toolset=lambda *args,**kwargs:None),
            'run_agent':SimpleNamespace(AIAgent=Agent,IterationBudget=object),
            'hermes_state':SimpleNamespace(SessionDB=lambda:None),'tools.terminal_tool':terminal,
            'lifespan.bubblewrap':SimpleNamespace(install_hermes_backend=lambda root:sandbox),
            'lifespan.evaluation.budget':SimpleNamespace(install_native_budget=lambda *args,**kw:SimpleNamespace()),
            'lifespan.evaluation.hermes_transport':SimpleNamespace(install=lambda *args,**kw:{'fixture':True})}
        env={'HERMES_HOME':str(profile),'LIFESPAN_EMPLOYEE':'fixture','LIFESPAN_MODEL':CANARY,
             'LIFESPAN_API_KEY':CANARY,'LIFESPAN_BASE_URL':CANARY,
             'LIFESPAN_EXECUTION_CONFIG':json.dumps({'mode':'evaluation','hermes_startup_observability':True,'_startup_observation_attempt_id':parent.attempt})}
        with patch.dict(sys.modules,modules),patch.dict(os.environ,env),patch('sys.stdout',io.StringIO()),patch('sys.stderr',io.StringIO()),patch('sys.stdin',io.StringIO('{"kind":"close"}\n')):
            hermes_worker.main()
        stages=[r['stage'] for r in self.rows(self.root,'worker')]
        self.assertEqual(stages,['worker_entered','imports_before','imports_after','registry_before','registry_after',
            'sandbox_before','sandbox_after','agent_before','agent_after','budget_transport_before',
            'budget_transport_after','probe_before','probe_after','ready_write_attempt','ready_write_returned'])
        self.assertNotIn(CANARY,'\n'.join(p.read_text() for p in (self.root/'startup').glob('*')))

    def test_online_and_learning_executor_option_propagation(self):
        from lifespan.tests.test_evaluation_runner import FakeActors, offline_executor, offline_dependencies
        from lifespan.evaluation import runner
        seen=[]
        def executor(**kwargs):
            self.assertIs(kwargs.pop('hermes_startup_observability'),True)
            seen.append('learning' if '/learning/' in str(kwargs['root']) else 'online')
            return offline_executor(**kwargs)
        config=ExperimentConfig(algorithm='skillopt',days=8,max_work_sessions=48,
            focal_employee='firm-0__onboarding-regulated',train_cases=1,val_cases=1,update_every=2,
            hermes_startup_observability=True)
        with offline_dependencies(fake_learner=True):
            runner.run_experiment(self.root/'run',config,actor_factory=FakeActors,executor=executor,creds=CREDS)
        self.assertIn('online',seen);self.assertIn('learning',seen)
        manifest=json.loads((self.root/'run/manifest.json').read_bytes())
        self.assertTrue(manifest['hermes_startup_observability'])
        self.assertEqual(manifest['startup_observation_provenance'],observe.provenance())

    def test_disabled_success_creates_no_observation_files(self):
        c=self.computer(False)
        try:
            with self.child("import json,sys; print(json.dumps({'kind':'ready','tool_names':[]})); sys.stdout.flush(); sys.stdin.readline()"), patch.object(c,'runtime_state',return_value={}):
                c.start(CREDS,timeout=1)
            self.assertFalse((c.root/'startup').exists())
        finally:c.close()

    def test_pipe_write_events_do_not_claim_model_dispatch(self):
        c=self.computer()
        c.startup_observer=observe.Observer(c.root,'parent')
        c.process=SimpleNamespace(pid=os.getpid())
        with patch.object(c,'send') as send, patch.object(c,'receive',return_value={'kind':'result','result':{'fixture':True}}):
            value=c.run(None,CANARY)
        self.assertEqual(value['native'],{'fixture':True})
        rows=self.rows(c.root,'parent')
        self.assertEqual([r['stage'] for r in rows],['run_request_write_attempt','run_request_write_returned'])
        self.assertNotIn(CANARY,json.dumps(rows));self.assertFalse(c.startup_observer.summary()['usage_known'])

    def test_slow_prewrite_observation_cannot_send_after_run_deadline(self):
        c=self.computer();c.startup_observer=observe.Observer(c.root,'parent')
        c.process=SimpleNamespace(pid=os.getpid())
        real_event=c.startup_observer.event
        def slow_event(stage,**kwargs):real_event(stage,**kwargs);time.sleep(.06)
        with patch.object(c.startup_observer,'event',slow_event),patch.object(c,'send') as send,patch.object(c,'receive') as receive:
            with self.assertRaises(TimeoutError):c.run(None,CANARY,timeout=.03)
        send.assert_not_called();receive.assert_not_called()
        self.assertEqual(self.rows(c.root,'parent')[-1]['stage'],'run_request_write_attempt')
        self.assertFalse(c.startup_observer.summary()['usage_known'])

    def test_run_receive_uses_remaining_time_after_observation(self):
        c=self.computer();c.startup_observer=observe.Observer(c.root,'parent')
        c.process=SimpleNamespace(pid=os.getpid())
        real_event=c.startup_observer.event
        def slow_event(stage,**kwargs):
            real_event(stage,**kwargs)
            if stage=='run_request_write_attempt':time.sleep(.035)
        with patch.object(c.startup_observer,'event',slow_event),patch.object(c,'send'),patch.object(c,'receive',return_value={'kind':'result','result':{'fixture':True}}) as receive:
            c.run(None,CANARY,timeout=.3)
        self.assertLess(receive.call_args.args[0],.28)
        self.assertGreater(receive.call_args.args[0],0)

    def test_slow_observer_setup_cannot_launch_after_startup_deadline(self):
        c=self.computer();real_observer=observe.Observer
        def slow_observer(*args,**kwargs):
            value=real_observer(*args,**kwargs);time.sleep(.06);return value
        with patch.object(observe,'Observer',side_effect=slow_observer),patch.object(computers.subprocess,'Popen') as launch:
            try:
                with self.assertRaises(TimeoutError):c.start(CREDS,timeout=.03)
                launch.assert_not_called()
                row=self.rows(c.root,'parent')[0]
                self.assertEqual(row['error_type'],'TimeoutError');self.assertIsNone(row['worker_identity'])
            finally:c.close()

    def test_observation_overhead_does_not_grant_fresh_timeout(self):
        c=self.computer()
        real_event=observe.Observer.event
        def slow_event(observer,stage,**kwargs):
            real_event(observer,stage,**kwargs)
            if stage=='popen_returned':time.sleep(.08)
        try:
            with self.child('import time; time.sleep(.15)'),patch.object(observe.Observer,'event',slow_event),patch.object(c,'receive') as receive:
                with self.assertRaises(TimeoutError):c.start(CREDS,timeout=.04)
            receive.assert_not_called()
            self.assertEqual(self.rows(c.root,'parent')[-1]['error_type'],'TimeoutError')
        finally:c.close()

    def test_late_ready_is_observed_but_never_accepted(self):
        c=self.computer()
        def late_ready(timeout):time.sleep(.06);return {'kind':'ready','tool_names':[]}
        try:
            with self.child('import time; time.sleep(.15)'),patch.object(c,'receive',side_effect=late_ready):
                with self.assertRaises(TimeoutError):c.start(CREDS,timeout=.04)
            stages=[r['stage'] for r in self.rows(c.root,'parent')]
            self.assertIn('ready_observed_after_deadline',stages);self.assertNotIn('ready_received',stages)
        finally:c.close()


if __name__=='__main__':unittest.main()
