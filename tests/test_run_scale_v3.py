"""Offline outer-scope evidence fixtures; no units, agents, APIs or signals."""
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
import json
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_scale_v3 as outer


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, separators=(',', ':')) + '\n')


class ScopeFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(outer, 'ROOT', self.root))
        self.directory=self.root/'lifespan/artifacts/fixture'; self.scope=self.directory/'scope';self.scope.mkdir(parents=True)
        self.campaign={'source_sha256':{'fixture.py':'a'*64},'registration_tools_sha256':{'scripts/run_scale_v3.py':'b'*64}}
        write(self.directory/'campaign.json',self.campaign);self.hash=outer.load(self.directory/'campaign.json')[1]
        self.sources={**self.campaign['source_sha256'],**self.campaign['registration_tools_sha256']}
        self.enterContext(patch.object(outer,'verify_sources',return_value=self.sources))
        self.unit=outer.PREFIX+'1'*32+'.scope';self.invocation='2'*32
        self.cap=outer.limits(); self.group='/user.slice/user-1000.slice/user@1000.service/app.slice/'+self.unit
        self.parent={'pid':100,'start_ticks':10,'uid':1000,'boot_id':'fixture',
            'security_context':'fixture (unconfined)','net_namespace':'net:[1]','user_namespace':'user:[2]'}
        self.qualification_dir=self.root/'lifespan/artifacts/qualification-fixture'
        self.qualified={'dependencies':{'fixture':'pinned'},'boot_id':'fixture',
            'caller_security_context':self.parent['security_context']}
        write(self.qualification_dir/'manifest.json',self.qualified)
        self.controller={**self.parent,'pid':101,'ppid':100,'start_ticks':11,'state':'R',
            'cwd':str(self.root),'cgroup':self.group,
            'argv_sha256':outer.sha(outer.canonical(outer.native_argv(self.directory,self.hash,'/usr/bin/python3')))}
        self.intent={'campaign_sha256':self.hash,'source_sha256':self.sources,'limits':self.cap,
            'unit':self.unit,'outer_identity':self.parent,'python':'/usr/bin/python3',
            'started_monotonic':1000,'startup_deadline':1000+self.cap['controller_startup_seconds'],
            'execution_deadline':1000+self.cap['execution_seconds']}
        self.intent.update(prerequisite_paths={'startup':{'directory':str(self.qualification_dir)}},
            qualification_manifest_sha256=outer.load(self.qualification_dir/'manifest.json')[1],
            qualified_dependencies_sha256=outer.sha(outer.canonical(self.qualified['dependencies'])),
            qualified_boot_id='fixture')
        self.intent['command_sha256']=outer.sha(outer.canonical(outer.launch_argv(self.directory,self.intent)))
        self.live={'Id':self.unit,'LoadState':'loaded','ActiveState':'active','SubState':'running',
            'InvocationID':self.invocation,'ControlGroup':self.group,'RuntimeMaxUSec':str(self.cap['runtime_seconds'])+'s',
            'TimeoutStopUSec':str(self.cap['stop_seconds'])+'s','KillMode':'control-group','Delegate':'no'}
        self.binding=outer.validate_binding(self.directory,self.intent,self.controller,self.controller,
            self.live,self.controller,self.cap['kernel_limits'])
        self.evidence={
            'INTENT.json':self.intent,
            'LAUNCH.json':{'identity':self.controller,'observed_monotonic':1000.1},
            'HELLO.json':{'identity':self.controller,'observed_monotonic':1000.2,'campaign_sha256':self.hash},
            'GATE.json':{'campaign_sha256':self.hash,'binding':self.binding,'unit_observation':self.live,
                'execution_started_monotonic':1000,'execution_deadline':self.intent['execution_deadline'],'observed_monotonic':1001},
            'INNER_RESULT.json':{'returned_normally':True,'inner_completed':True,'exit_code':0,'error_type':None,
                'campaign_sha256':self.hash,'controller_identity':self.controller,'finished_monotonic':1010},
            'DRAINED.json':{'controller_identity':self.controller,'unit_observation':self.live,'members':[101],
                'kernel':self.cap['kernel_limits'],'resources':{},'observed_monotonic':1011,
                'qualified_dependencies_sha256':self.intent['qualified_dependencies_sha256']},
            'RELEASE.json':{'campaign_sha256':self.hash,'controller_identity':self.controller,'observed_monotonic':1012},
            'CONTROLLER_EXIT.json':{'campaign_sha256':self.hash,'identity':self.controller,'exit_code':0,
                'release_sha256':None,'observed_monotonic':1013},
            'TERMINAL.json':{'campaign_sha256':self.hash,'started_monotonic':1010,
                'cleanup_deadline':1010+self.cap['cleanup_seconds'],'ended_monotonic':1014,'native_wait_exit_code':0,
                'released':True,'forced_stop':False,'errors':[],'members_remaining':[],'controller_state':'absent',
                'unit_final':{**self.live,'LoadState':'not-found','ActiveState':'inactive','SubState':'dead',
                    'InvocationID':'','ControlGroup':''}}}
        for name,value in self.evidence.items(): write(self.scope/name,value)
        self.evidence['CONTROLLER_EXIT.json']['release_sha256']=outer.load(self.scope/'RELEASE.json')[1]
        write(self.scope/'CONTROLLER_EXIT.json',self.evidence['CONTROLLER_EXIT.json'])

    def change(self,name,**updates):
        value=deepcopy(self.evidence[name]);value.update(updates);write(self.scope/name,value)

    def inspect(self):return outer.audit_scope(self.directory,campaign_sha256=self.hash,strict=True)


class AuditTests(ScopeFixture):
    def test_complete_requires_native_return_wait_and_owned_terminal_evidence(self):
        result=self.inspect();self.assertTrue(result['ok'],result)
        self.assertEqual(result['native_wait_exit_code'],0)
        self.assertEqual(result['inner_result_exit_code'],0)
        self.assertEqual(result['inner_supervisor_identity'],self.controller)
        self.assertEqual(len(result['raw_evidence_sha256']),9)

    def test_missing_receipt_remains_incomplete_not_qualified(self):
        (self.scope/'CONTROLLER_EXIT.json').unlink();result=self.inspect()
        self.assertEqual(result['status'],'incomplete');self.assertFalse(result['scope_passed'])

    def test_completed_inner_or_systemd_success_cannot_replace_wait(self):
        for wait in (None,1,True):
            self.change('TERMINAL.json',native_wait_exit_code=wait)
            with self.subTest(wait=wait):self.assertFalse(self.inspect()['ok'])

    def test_abnormal_inner_return_rejected_even_with_zero_native_wait(self):
        self.change('INNER_RESULT.json',returned_normally=False,error_type='FixtureError')
        self.assertFalse(self.inspect()['ok'])

    def test_native_controller_identity_cannot_be_substituted(self):
        self.change('HELLO.json',identity={**self.controller,'start_ticks':12})
        self.assertFalse(self.inspect()['ok'])

    def test_current_context_must_preserve_registered_parent_and_label(self):
        for key,value in [('ppid',999),('uid',999),('security_context','foreign'),
                ('user_namespace','other'),('net_namespace','other'),('cwd','/foreign')]:
            current={**self.controller,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):
                outer.validate_binding(self.directory,self.intent,current,current,self.live,current,self.cap['kernel_limits'])

    def test_active_limits_and_invocation_must_match(self):
        for values in ({**self.cap['kernel_limits'],'memory.max':'max'},
                       {**self.cap['kernel_limits'],'cpu.max':'max 100000'}):
            with self.assertRaises(ValueError):
                outer.validate_binding(self.directory,self.intent,self.controller,self.controller,
                    self.live,self.controller,values)
        with self.assertRaises(ValueError):
            outer.validate_binding(self.directory,self.intent,self.controller,self.controller,
                {**self.live,'InvocationID':''},self.controller,self.cap['kernel_limits'])

    def test_final_drain_requires_only_controller_and_unchanged_limits(self):
        self.change('DRAINED.json',members=[101,102]);self.assertFalse(self.inspect()['ok'])
        self.change('DRAINED.json',kernel={**self.cap['kernel_limits'],'pids.max':'max'})
        self.assertFalse(self.inspect()['ok'])

    def test_terminal_members_forced_cleanup_or_unknown_state_prevent_pass(self):
        for field,value in [('members_remaining',[102]),('members_remaining',None),('forced_stop',True),
                ('controller_state','alive'),('errors',[{'code':'fixture'}])]:
            self.change('TERMINAL.json',**{field:value})
            with self.subTest(field=field):self.assertFalse(self.inspect()['ok'])

    def test_collected_unit_cannot_claim_active_running_state(self):
        final=deepcopy(self.evidence['TERMINAL.json']['unit_final'])
        final.update(ActiveState='active',SubState='running')
        self.change('TERMINAL.json',unit_final=final)
        self.assertFalse(self.inspect()['ok'])

    def test_measured_cleanup_clock_cannot_extend_allowance(self):
        self.change('TERMINAL.json',cleanup_deadline=1010+self.cap['cleanup_seconds']+1)
        self.assertFalse(self.inspect()['ok'])
        self.change('TERMINAL.json',ended_monotonic=1010+self.cap['cleanup_seconds']+1)
        self.assertFalse(self.inspect()['ok'])

    def test_scope_intent_or_gate_cannot_extend_execution_clock(self):
        self.change('GATE.json',execution_deadline=self.intent['execution_deadline']+1)
        self.assertFalse(self.inspect()['ok'])

    def test_release_raw_hash_is_required(self):
        self.change('CONTROLLER_EXIT.json',release_sha256='0'*64)
        self.assertFalse(self.inspect()['ok'])

    def test_source_or_campaign_binding_cannot_change(self):
        self.change('INTENT.json',source_sha256={});self.assertFalse(self.inspect()['ok'])
        write(self.scope/'INTENT.json',self.evidence['INTENT.json'])
        self.change('INNER_RESULT.json',campaign_sha256='0'*64);self.assertFalse(self.inspect()['ok'])

    def test_no_service_shortcut_or_borrowed_scope_invocation(self):
        bad=deepcopy(self.live);bad['InvocationID']='3'*32
        self.change('DRAINED.json',unit_observation=bad)
        self.assertFalse(self.inspect()['ok'])

    def test_qualified_dependency_or_boot_context_tamper_rejected(self):
        for key,value in [('qualified_dependencies_sha256','0'*64),('qualified_boot_id','foreign'),
                ('qualification_manifest_sha256','0'*64)]:
            self.change('INTENT.json',**{key:value})
            with self.subTest(key=key):self.assertFalse(self.inspect()['ok'])
        write(self.scope/'INTENT.json',self.evidence['INTENT.json'])
        self.change('DRAINED.json',qualified_dependencies_sha256='0'*64)
        self.assertFalse(self.inspect()['ok'])

    def test_same_manifest_boot_with_changed_launching_label_rejected(self):
        changed={**self.qualified,'caller_security_context':'foreign (unconfined)'}
        write(self.qualification_dir/'manifest.json',changed)
        self.change('INTENT.json',qualification_manifest_sha256=outer.load(self.qualification_dir/'manifest.json')[1])
        self.assertFalse(self.inspect()['ok'])


class ControlTests(unittest.TestCase):
    def test_scope_stop_refuses_unbound_or_foreign_invocation(self):
        unit=outer.PREFIX+'1'*32+'.scope';intent={'unit':unit};binding={'invocation_id':'2'*32,'cgroup':'/fixture'}
        with patch.object(outer,'show',return_value={'LoadState':'loaded','InvocationID':'3'*32,'ControlGroup':'/fixture'}), \
             patch.object(outer.subprocess,'run') as run:
            with self.assertRaises(ValueError):outer._stop_scope(intent,binding,1e20)
            with self.assertRaises(ValueError):outer._stop_scope(intent,None,1e20)
        run.assert_not_called()

    def test_duration_parser_rejects_infinite_or_missing_limits(self):
        self.assertEqual(outer.seconds('3d 21min 30s'),260490)
        for value in ('infinity','',None,'15s garbage'):
            with self.subTest(value=value),self.assertRaises(ValueError):outer.seconds(value)


class AddedGuardTests(ScopeFixture):
    def test_signal_delegates_to_pidfd_guard_without_raw_pid_kill(self):
        with patch('scripts.scale_v2_process._signal_owned',return_value=True) as send, \
             patch.object(outer.os,'kill') as raw:
            self.assertTrue(outer._signal_controller(self.binding,signal.SIGINT))
        send.assert_called_once_with(self.controller,'INT');raw.assert_not_called()

    def test_prehello_binding_is_cleanup_only_and_requires_original_child(self):
        with patch.object(outer,'identity',return_value=self.controller),patch.object(outer,'show',return_value=self.live):
            value=outer.cleanup_binding(self.intent,self.controller)
        self.assertTrue(value['cleanup_only'])
        with patch.object(outer,'identity',return_value={**self.controller,'start_ticks':12}):
            with self.assertRaisesRegex(ValueError,'child_unbound'):
                outer.cleanup_binding(self.intent,self.controller)

    def test_malformed_or_future_inner_phase_cannot_extend_live_cleanup(self):
        for value in (None,float('nan'),999,1002):
            self.change('INNER_RESULT.json',finished_monotonic=value)
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'clock_invalid'):
                outer.checked_inner_result(self.scope,self.intent,1001)
        self.change('INNER_RESULT.json',finished_monotonic=1000.5)
        self.assertEqual(outer.checked_inner_result(self.scope,self.intent,1001)['finished_monotonic'],1000.5)

    def test_retained_live_observation_is_hashed_and_contradictions_reject(self):
        record={'kernel':self.cap['kernel_limits'],'invocation_id':self.invocation,'controller_present':True,
                'member_count':3,'observed_monotonic':1005,'resources':{}}
        write(self.scope/'OBSERVATION.json',record)
        value=self.inspect();self.assertTrue(value['ok'],value)
        self.assertIn('OBSERVATION.json',value['raw_evidence_sha256'])
        write(self.scope/'OBSERVATION.json',{**record,'kernel':{**self.cap['kernel_limits'],'memory.max':'max'}})
        self.assertFalse(self.inspect()['ok'])


class ExecutionLoopTests(unittest.TestCase):
    """Exercise only Python orchestration; every process/control operation mocked."""
    def setUp(self):
        from scripts import audit_scale_v3 as audit
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(outer,'ROOT',self.root))
        self.directory=self.root/'lifespan/artifacts/fixture';self.directory.mkdir(parents=True)
        self.campaign={'source_sha256':{},'registration_tools_sha256':{}}
        write(self.directory/'campaign.json',self.campaign);self.hash=outer.load(self.directory/'campaign.json')[1]
        self.parent={'pid':100,'start_ticks':10,'uid':1000,'boot_id':'fixture',
            'security_context':'fixture (unconfined)','net_namespace':'net:[1]','user_namespace':'user:[2]'}
        from scripts import hermes_startup_scope_qualification_v3 as qualification
        self.qualification_dir=self.root/'lifespan/artifacts/qualification-fixture'
        self.qualified={'dependencies':{'fixture':'pinned'},'boot_id':'fixture',
            'caller_security_context':self.parent['security_context']}
        write(self.qualification_dir/'manifest.json',self.qualified)
        self.prerequisite_paths={'startup':{'directory':str(self.qualification_dir)}}
        self.prereqs=self.enterContext(patch.object(outer,'verify_prerequisites',return_value={'verified':True}))
        self.current_qualification=self.enterContext(patch.object(qualification,'validate_manifest',return_value=self.qualified))
        self.enterContext(patch.object(qualification,'dependencies',return_value=self.qualified['dependencies']))
        self.enterContext(patch.object(outer,'verify_sources',return_value={}))
        self.enterContext(patch.object(outer.base,'committed'))
        self.enterContext(patch.object(outer.subprocess,'check_output',return_value='fixture-commit'))
        self.enterContext(patch.object(outer.base,'controller_environment',return_value={}))
        self.enterContext(patch.object(outer.base,'controller_import_paths',return_value=[]))
        self.enterContext(patch.object(outer.base,'interpreter',return_value='/usr/bin/python3'))
        self.enterContext(patch.object(outer.base,'interrupt_scope',return_value=nullcontext()))
        self.enterContext(patch.object(audit,'audit_campaign_v3',return_value={'ok':False,'fixture_only':True}))
        self.enterContext(patch.object(outer.time,'sleep'))
        self.enterContext(patch.object(outer,'resource_observation',return_value={}))
        self.signal=self.enterContext(patch('scripts.scale_v2_process._signal_owned',return_value=True))
        self.native=None;self.mode='released_timeout';self.waits=0
        owner=self
        class Process:
            pid=101
            alive=True
            def poll(self):return None if self.alive else 0
            def wait(self,timeout):
                owner.waits+=1
                if owner.mode=='released_timeout' and owner.waits==1:
                    raise subprocess.TimeoutExpired('offline-fixture',timeout)
                self.alive=False
                return -9 if owner.mode=='released_timeout' else 0
        def popen(*args,**kwargs):
            self.native=Process(); intent=outer.load(self.directory/'scope/INTENT.json')[0]
            self.unit=intent['unit'];self.group='/user.slice/user-1000.slice/user@1000.service/app.slice/'+self.unit
            self.controller={**self.parent,'pid':101,'ppid':100,'start_ticks':11,'state':'R','cgroup':self.group,
                'cwd':str(self.root),'argv_sha256':outer.sha(outer.canonical(outer.native_argv(self.directory,self.hash,'/usr/bin/python3')))}
            self.live={'Id':self.unit,'LoadState':'loaded','ActiveState':'active','SubState':'running',
                'InvocationID':'2'*32,'ControlGroup':self.group,'RuntimeMaxUSec':str(outer.limits()['runtime_seconds'])+'s',
                'TimeoutStopUSec':'5s','KillMode':'control-group','Delegate':'no'}
            if self.mode=='released_timeout':
                write(self.directory/'scope/HELLO.json',{'identity':self.controller,'campaign_sha256':self.hash,'observed_monotonic':1001})
                write(self.directory/'scope/INNER_RESULT.json',{'controller_identity':self.controller,'finished_monotonic':1001,
                    'campaign_sha256':self.hash,'returned_normally':True,'inner_completed':True,'exit_code':0,'error_type':None})
            return self.native
        self.popen=self.enterContext(patch.object(outer.subprocess,'Popen',side_effect=popen))
        def identity(pid):
            if pid==101:return self.controller if self.native and self.native.alive else None
            return self.parent
        self.enterContext(patch.object(outer,'identity',side_effect=identity))
        self.enterContext(patch.object(outer,'show',side_effect=lambda unit: deepcopy(self.live) if self.native and self.native.alive else
            {'Id':unit,'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','InvocationID':'','ControlGroup':''}))
        self.enterContext(patch.object(outer,'kernel',side_effect=lambda *args:outer.limits()['kernel_limits']))
        self.enterContext(patch.object(outer,'group_members',side_effect=lambda *args:[101] if self.native.alive else []))
        self.stop=self.enterContext(patch.object(outer,'_stop_scope',return_value=True))

    def test_released_controller_wait_timeout_still_forces_owned_cleanup_and_reaps(self):
        with patch.object(outer.time,'monotonic',return_value=1001):
            outer.execute(self.directory,campaign_sha256=self.hash,prerequisite_paths=self.prerequisite_paths)
        self.assertTrue((self.directory/'scope/RELEASE.json').exists())
        self.stop.assert_called_once();self.assertEqual(self.waits,2)
        self.signal.assert_called_once_with(self.controller,'KILL')
        value=outer.load(self.directory/'scope/TERMINAL.json')[0]
        self.assertTrue(value['released']);self.assertTrue(value['forced_stop'])
        self.assertEqual(value['native_wait_exit_code'],-9)
        self.assertIn('scope_wait_unconfirmed',[x['code'] for x in value['errors']])

    def test_missing_hello_uses_owned_cleanup_binding_without_qualifying_scope(self):
        self.mode='missing_hello';clock=iter([1000,2000])
        with patch.object(outer.time,'monotonic',side_effect=lambda:next(clock,2000)):
            outer.execute(self.directory,campaign_sha256=self.hash,prerequisite_paths=self.prerequisite_paths)
        self.assertFalse((self.directory/'scope/GATE.json').exists())
        self.assertTrue(outer.load(self.directory/'scope/CLEANUP_BINDING.json')[0]['cleanup_only'])
        self.stop.assert_called_once();self.assertEqual(self.waits,1)
        terminal=outer.load(self.directory/'scope/TERMINAL.json')[0]
        self.assertFalse(terminal['released']);self.assertIsNone(terminal['members_remaining'])
        self.signal.assert_not_called()

    def test_unconfirmed_prehello_scope_only_signals_original_owned_child(self):
        self.mode='missing_hello';clock=iter([1000,2000])
        with patch.object(outer.time,'monotonic',side_effect=lambda:next(clock,2000)), \
             patch.object(outer,'cleanup_binding',side_effect=ValueError('fixture_scope_unbound')):
            outer.execute(self.directory,campaign_sha256=self.hash,prerequisite_paths=self.prerequisite_paths)
        self.signal.assert_called_once_with(self.controller,'TERM')
        self.assertIsNone(self.stop.call_args.args[1])
        self.assertFalse((self.directory/'scope/GATE.json').exists())

    def test_current_qualification_failure_prevents_scope_process_and_intent(self):
        self.current_qualification.side_effect=ValueError('fixture_dependency_changed')
        with self.assertRaisesRegex(ValueError,'dependency_changed'):
            outer.execute(self.directory,campaign_sha256=self.hash,prerequisite_paths=self.prerequisite_paths)
        self.popen.assert_not_called();self.assertFalse((self.directory/'scope').exists())

    def test_prerequisite_failure_precedes_current_qualification_and_any_launch(self):
        self.prereqs.side_effect=ValueError('fixture_prerequisite_changed')
        with self.assertRaisesRegex(ValueError,'prerequisite_changed'):
            outer.execute(self.directory,campaign_sha256=self.hash,prerequisite_paths=self.prerequisite_paths)
        self.current_qualification.assert_not_called();self.popen.assert_not_called()
        self.assertFalse((self.directory/'scope').exists())


if __name__=='__main__':unittest.main()
