"""Offline scope/transcript fixtures only; no systemd, native agent or provider."""
from copy import deepcopy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import hermes_startup_scope_qualification_v3 as q
from tests import test_hermes_startup_qualification as old

LABEL='fixture-unconfined'

def write(p,value):old.write(p,value)


@contextmanager
def guards():
    with patch.object(q,'committed'),patch.object(q,'boot',return_value=old.BOOT), \
         patch.object(q,'dependencies',return_value={'fixture':True}), \
         patch.object(q,'security_context',return_value=LABEL), \
         patch.object(q,'controller_environment',return_value={k:'fixture' for k in q.ENV_KEYS}), \
         patch.object(q,'controller_import_paths',return_value=[]):yield


def fixture(directory):
    m,_=old.fixture(directory)
    def convert(value):
        if type(value)is str:return value.replace('.service/app.slice/','.service/app.slice/').replace('.service','.scope') if value.startswith(q.child.UNIT_PREFIX) else value.replace('.service', '.scope') if value.startswith('/user.slice/') and value.endswith('.service') else value
        if type(value)is list:return [convert(v) for v in value]
        if type(value)is dict:
            result={k:convert(v) for k,v in value.items()}
            if set(('pid','start_ticks','ppid'))<=set(value):
                result['security_context']=LABEL
                if result['pid'] in range(1000,1090,10):result['ppid']=900
            return result
        return value
    # Change only the leaf unit suffix in cgroup paths, retaining user@UID.service.
    def fixgroups(value):
        if type(value)is str:return value.replace(f'user@{old.UID}.scope/',f'user@{old.UID}.service/')
        if type(value)is list:return [fixgroups(v) for v in value]
        if type(value)is dict:return {k:fixgroups(v) for k,v in value.items()}
        return value
    for p in directory.rglob('*.json'):
        write(p,fixgroups(convert(q.load(p)[0])))
    for p in directory.rglob('*.jsonl'):
        p.write_bytes(b'\n'.join(q.canonical(fixgroups(convert(json.loads(line)))) for line in p.read_bytes().splitlines())+b'\n')
    m=q.load(directory/'manifest.json')[0]
    m.update(schema_version=3,kind=q.VERSION,config=deepcopy(q.CONFIG),source_sha256=q.sources(),caller_security_context=LABEL)
    m.pop('resource_receipt_sha256',None);write(directory/'manifest.json',m)
    digest=q.load(directory/'manifest.json')[1]
    execution=q.load(directory/'EXECUTION.json')[0]
    execution.update(registered_manifest_sha256=digest,source_sha256=m['source_sha256']);write(directory/'EXECUTION.json',execution)
    receipts=[]
    for slot in m['slots']:
        trial=directory/'slots'/slot['slot_id']
        receipt=q.load(trial/'RECEIPT.json')[0];binding=receipt['unit_binding'];main=binding['main_identity']
        main['argv_sha256']=q.sha(q.canonical(q.native_argv(directory,slot)))
        binding['identity_role']='held_scope_controller'
        intent=q.load(trial/'INTENT.json')[0];intent.update(manifest_sha256=digest,command_sha256=q.sha(q.canonical(q.launch_argv(directory,slot))))
        write(trial/'INTENT.json',intent)
        launch=deepcopy(main);launch['argv_sha256']=intent['command_sha256']
        (trial/'CLIENT.json').unlink();write(trial/'LAUNCH.json',{'identity':launch,'observed_monotonic':intent['started_monotonic']+1})
        hello=q.load(trial/'HELLO.json')[0];hello.update(manifest_sha256=digest,identity=deepcopy(main));write(trial/'HELLO.json',hello)
        gate=q.load(trial/'GATE.json')[0];unit={k:gate['unit_observation'][k] for k in q.SHOW_KEYS}
        gate.update(manifest_sha256=digest,unit_binding=deepcopy(binding),unit_observation=unit,observed_monotonic=intent['started_monotonic']+1.5);write(trial/'GATE.json',gate)
        close=q.load(trial/'CLOSE_GATE.json')[0];close['manifest_sha256']=digest;write(trial/'CLOSE_GATE.json',close)
        start=q.load(trial/'native/STARTUP_INTENT.json')[0];start.update(kind=q.VERSION,helper_sha256=m['source_sha256']['scripts/hermes_startup_scope_qualification_v3.py']);write(trial/'native/STARTUP_INTENT.json',start)
        cleanup=receipt['cleanup'];finish=cleanup['started_monotonic']
        native_ids=q.load(trial/'NATIVE_IDENTITIES.json')[0]['identities']
        witness={'scope':unit,'controller_identity':deepcopy(main),'members':[main['pid']],
            'kernel':deepcopy(q.child.KERNEL_LIMITS),'socket_cleanup':{'confirmed':True},
            'native_processes':[{'identity':v,'state':'absent'} for v in native_ids.values()],
            'observed_monotonic':finish+3}
        write(trial/'SCOPE_WITNESS.json',witness)
        release={'slot_id':slot['slot_id'],'manifest_sha256':digest,'controller_identity':deepcopy(main),'observed_monotonic':finish+4}
        write(trial/'RELEASE.json',release)
        write(trial/'CONTROLLER_EXIT.json',{'slot_id':slot['slot_id'],'manifest_sha256':digest,'identity':deepcopy(main),
            'observed_monotonic':finish+5,'normal_release':True,'release_sha256':q.load(trial/'RELEASE.json')[1]})
        (trial/'UNIT_TERMINAL.json').unlink()
        final={k:cleanup['unit_final'][k] for k in q.SHOW_KEYS}
        cleanup={k:v for k,v in cleanup.items() if k not in ('unit_final','unit_stop','terminal_before_stop','control_client_exit_code')}
        cleanup.update(scope_final=final,scope_stop=None,controller_exit_code=0,released=True)
        write(trial/'CLEANUP.json',cleanup)
        receipt.pop('client_identity');receipt.update(launch_identity=launch,unit_binding=binding,cleanup=cleanup,
            intent_sha256=q.load(trial/'INTENT.json')[1]);write(trial/'RECEIPT.json',receipt)
        refresh(trial);receipts.append(q.load(trial/'RECEIPT.json')[0])
    write(directory/'REPORT.json',{'schema_version':3,'kind':q.VERSION,'manifest_sha256':digest,
        'status':'completed','planned_slots':9,'qualification_passed':True,'results':receipts})
    return m,digest


def refresh(trial):
    receipt=q.load(trial/'RECEIPT.json')[0];receipt['evidence_sha256']=q._inventory(trial);write(trial/'RECEIPT.json',receipt)


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)/'run'
        self.enterContext(guards())

    def test_nine_fixed_starts_scope_only_properties_and_scrubbed_env(self):
        self.assertEqual(q.BATCHES,(1,1,1,2,2,2))
        slot={'slot_id':'start-00','unit':q.child.UNIT_PREFIX+'1'*32+'.scope'}
        command=q.launch_argv(self.root,slot)
        self.assertIn('--scope',command);self.assertNotIn('--service-type=exec',command)
        self.assertTrue(all('RemainAfterExit' not in x and 'MainPID' not in x and 'Restart=' not in x for x in command))
        self.assertNotIn('MainPID',q.SHOW_KEYS)
        self.assertEqual(q.CONFIG['planned_slots'],9);self.assertEqual(q.CONFIG['startup_seconds'],150)
        self.assertEqual(q.child.KERNEL_LIMITS,{'memory.max':'4294967296','memory.swap.max':'0','pids.max':'128','cpu.max':'200000 100000'})

    def test_v3_has_separate_source_and_bootstrap_identity_without_study_drafts(self):
        self.assertEqual(q.VERSION,'hermes-startup-scope-qualification-v3')
        self.assertEqual(set(q.sources()),set(q.legacy.sources())|{'scripts/hermes_startup_scope_qualification_v3.py'})
        self.assertIn('lifespan/evaluation/provider.py',q.sources())
        self.assertNotIn('scripts/hermes_startup_scope_qualification.py',q.sources())
        self.assertFalse(any('scale_v3' in name for name in q.sources()))
        self.assertIn('scripts.hermes_startup_scope_qualification_v3 import _worker',q.BOOTSTRAP)
        self.assertNotIn('scripts.hermes_startup_scope_qualification import _worker',q.BOOTSTRAP)

    def test_environment_guard_requires_exact_keys_values_and_verified_inherited_id(self):
        manifest={'controller_environment':{key:'fixture' for key in q.ENV_KEYS}}
        gate={'unit_binding':{'invocation_id':'a'*32}}
        valid={**manifest['controller_environment'],'INVOCATION_ID':'a'*32}
        original=deepcopy(valid);q.validate_worker_environment(manifest,gate,valid)
        self.assertEqual(valid,original)
        bad_cases=[dict(valid,UNREGISTERED_INJECTION='fixture'),dict(valid,HOME='different-fixture'),
            {key:value for key,value in valid.items() if key!='INVOCATION_ID'},
            dict(valid,INVOCATION_ID='b'*32),dict(valid,INVOCATION_ID=''),
            dict(valid,INVOCATION_ID='not-a-scope-id'),dict(valid,INVOCATION_ID=None)]
        for bad in bad_cases:
            with self.subTest(keys=sorted(bad)):
                before=deepcopy(bad)
                with self.assertRaises(ValueError):q.validate_worker_environment(manifest,gate,bad)
                self.assertEqual(bad,before)
        with self.assertRaises(ValueError):
            q.validate_worker_environment(manifest,{'unit_binding':{'invocation_id':'b'*32}},valid)

    def test_actual_bootstrap_refuses_unregistered_environment_before_scrub_or_worker_import(self):
        import sys
        self.root.mkdir()
        registered={key:'fixture' for key in q.ENV_KEYS}
        manifest={'working_directory':str(q.ROOT),'root':str(self.root),
            'controller_environment':registered,'controller_import_paths':[]}
        write(self.root/'manifest.json',manifest)
        write(self.root/'EXECUTION.json',{'registered_manifest_sha256':q.load(self.root/'manifest.json')[1]})
        valid={**registered,'INVOCATION_ID':'a'*32}
        invalid=[dict(valid,UNREGISTERED_INJECTION='fixture'),dict(valid,HOME='different-fixture'),
            registered,dict(valid,INVOCATION_ID=''),dict(valid,INVOCATION_ID='z'*32)]
        for env in invalid:
            with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['fixture',str(q.ROOT),str(self.root),'start-00']),patch.object(sys,'path',list(sys.path)),patch.object(q,'_worker') as worker:
                with self.assertRaises(ValueError):exec(q.BOOTSTRAP,{})
                worker.assert_not_called();self.assertEqual(dict(os.environ),env)
        def worker(directory,slot):
            self.assertEqual((directory,slot),(self.root,'start-00'))
            self.assertEqual(dict(os.environ),valid)
        with patch.dict(os.environ,valid,clear=True),patch.object(sys,'argv',['fixture',str(q.ROOT),str(self.root),'start-00']),patch.object(sys,'path',list(sys.path)),patch.object(q,'_worker',side_effect=worker) as called:
            exec(q.BOOTSTRAP,{});called.assert_called_once()
            self.assertEqual(dict(os.environ),valid)

    def test_worker_rejects_missing_wrong_or_extra_environment_before_native_startup(self):
        m,d=fixture(self.root);slot=m['slots'][0];trial=self.root/'slots'/slot['slot_id']
        gate=q.load(trial/'GATE.json')[0];valid={**m['controller_environment'],'INVOCATION_ID':gate['unit_binding']['invocation_id']}
        invalid=[{k:v for k,v in valid.items() if k!='INVOCATION_ID'},
            dict(valid,INVOCATION_ID='f'*32),dict(valid,UNREGISTERED_INJECTION='fixture')]
        for env in invalid:
            for name in ('HELLO.json','CONTROLLER_EXIT.json'):(trial/name).unlink(missing_ok=True)
            with patch.dict(os.environ,env,clear=True),patch.object(q,'identity',return_value=gate['unit_binding']['main_identity']),patch.object(q.time,'monotonic',return_value=102.),patch.object(q,'_native_startup') as native:
                with self.assertRaisesRegex(ValueError,'controller_environment_not_scrubbed|inherited_scope_invocation_mismatch'):
                    q._worker(self.root,slot['slot_id'])
                native.assert_not_called()
                self.assertEqual(dict(os.environ),env)

    def test_worker_preserves_matching_inherited_id_through_native_startup_and_release(self):
        m,d=fixture(self.root);slot=m['slots'][0];trial=self.root/'slots'/slot['slot_id']
        gate=q.load(trial/'GATE.json')[0];env={**m['controller_environment'],'INVOCATION_ID':gate['unit_binding']['invocation_id']}
        for name in ('HELLO.json','CONTROLLER_EXIT.json'):(trial/name).unlink()
        def native(*args):
            self.assertEqual(dict(os.environ),env)
            self.assertEqual(args[1]['invocation_id'],env['INVOCATION_ID'])
            return {'cleanup_deadline':180.}
        with patch.dict(os.environ,env,clear=True),patch.object(q,'identity',return_value=gate['unit_binding']['main_identity']),patch.object(q.time,'monotonic',return_value=102.),patch.object(q,'_native_startup',side_effect=native) as callback:
            q._worker(self.root,slot['slot_id']);callback.assert_called_once()
            self.assertEqual(dict(os.environ),env)
        self.assertTrue(q.load(trial/'CONTROLLER_EXIT.json')[0]['normal_release'])

    def test_complete_scope_transcript_reconstructs_without_service_terminal(self):
        m,d=fixture(self.root);result=q.audit_qualification(self.root,manifest_sha256=d,strict=True)
        self.assertTrue(result['ok'],result);self.assertTrue(result['qualification_passed'])
        self.assertEqual(len(result['slots']),9)

    def test_coherently_relabelled_observations_cannot_change_registered_security_context(self):
        m,d=fixture(self.root)
        def relabel(value):
            if type(value)is list:return [relabel(v) for v in value]
            if type(value)is dict:return {k:'different-fixture-label' if k=='security_context' else relabel(v) for k,v in value.items()}
            return value
        for path in self.root.rglob('*.json'):
            if path.name!='manifest.json':write(path,relabel(q.load(path)[0]))
        for path in self.root.rglob('*.jsonl'):
            path.write_bytes(b'\n'.join(q.canonical(relabel(json.loads(line))) for line in path.read_bytes().splitlines())+b'\n')
        rows=[]
        for slot in m['slots']:
            trial=self.root/'slots'/slot['slot_id']
            self.tamper(trial/'CONTROLLER_EXIT.json',lambda r:r.update(release_sha256=q.load(trial/'RELEASE.json')[1]))
            refresh(trial);rows.append(q.load(trial/'RECEIPT.json')[0])
        self.tamper(self.root/'REPORT.json',lambda r:r.update(results=rows))
        self.assertEqual(q.load(self.root/'manifest.json')[1],d)
        result=q.audit_qualification(self.root,manifest_sha256=d,strict=True)
        self.assertFalse(result['ok'],result)
        self.assertEqual(result['errors'][0]['code'],'registered_supervisor_context_mismatch')

    def test_partial_execution_requires_registered_supervisor_uid_boot_and_context(self):
        m,d=fixture(self.root)
        import shutil
        shutil.rmtree(self.root/'slots');(self.root/'slots').mkdir()
        (self.root/'REPORT.json').unlink()
        original=q.load(self.root/'EXECUTION.json')[0]
        for key,value in (('uid',old.UID+1),('boot_id','different-fixture-boot'),('security_context','different-fixture-label')):
            altered=deepcopy(original);altered['supervisor'][key]=value
            write(self.root/'EXECUTION.json',altered)
            result=q.audit_qualification(self.root,manifest_sha256=d,strict=False)
            self.assertFalse(result['ok'],result)
            self.assertEqual(result['errors'][0]['code'],'registered_supervisor_context_mismatch')

    def test_hello_must_match_execed_popen_identity_not_a_separate_child(self):
        m,d=fixture(self.root);slot=m['slots'][0];trial=self.root/'slots'/slot['slot_id']
        gate=q.load(trial/'GATE.json')[0];proc=gate['unit_binding']['main_identity']
        launch=q.load(trial/'LAUNCH.json')[0]['identity'];supervisor=q.load(self.root/'EXECUTION.json')[0]['supervisor']
        for key in ('pid','start_ticks'):
            bad=deepcopy(launch);bad[key]+=1
            with self.assertRaisesRegex(ValueError,'scope_exec_identity'):
                q.validate_scope(slot,gate['unit_observation'],proc,proc,bad,supervisor,directory=self.root,kernel_values=q.child.KERNEL_LIMITS)
        bad=deepcopy(proc);bad['argv_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'scope_exec_configuration'):
            q.validate_scope(slot,gate['unit_observation'],bad,bad,launch,supervisor,directory=self.root,kernel_values=q.child.KERNEL_LIMITS)

    def tamper(self,path,fn):
        value=q.load(path)[0];fn(value);write(path,value)

    def test_service_defaults_or_wrong_invocation_cannot_certify_scope(self):
        m,d=fixture(self.root);s=m['slots'][0];t=self.root/'slots'/s['slot_id'];g=q.load(t/'GATE.json')[0]
        p=g['unit_binding']['main_identity'];l=q.load(t/'LAUNCH.json')[0]['identity'];supervisor=q.load(self.root/'EXECUTION.json')[0]['supervisor']
        for change in ({'LoadState':'not-found','ActiveState':'inactive'},{'RuntimeMaxUSec':'infinity'},{'ControlGroup':'/foreign'}, {'InvocationID':''}):
            with self.assertRaises(ValueError):q.validate_scope(s,dict(g['unit_observation'],**change),p,p,l,supervisor,directory=self.root,kernel_values=q.child.KERNEL_LIMITS)
        with self.assertRaises(ValueError):q.validate_scope(s,g['unit_observation'],p,p,l,supervisor,directory=self.root,kernel_values=dict(q.child.KERNEL_LIMITS,**{'memory.max':'max'}))

    def test_prehello_cleanup_requires_actual_owned_process_and_scope(self):
        m,d=fixture(self.root);s=m['slots'][0];t=self.root/'slots'/s['slot_id'];g=q.load(t/'GATE.json')[0]
        p=g['unit_binding']['main_identity'];launch=q.load(t/'LAUNCH.json')[0]['identity']
        supervisor=q.load(self.root/'EXECUTION.json')[0]['supervisor']
        binding=q._cleanup_binding(s,launch,p,g['unit_observation'],supervisor)
        self.assertFalse(binding['verified']);self.assertTrue(binding['ownership_only'])
        for proc,unit in ((None,g['unit_observation']),(dict(p,pid=p['pid']+1),g['unit_observation']),
                         (p,dict(g['unit_observation'],ControlGroup='/foreign'))):
            with self.assertRaises(ValueError):q._cleanup_binding(s,launch,proc,unit,supervisor)

    def test_name_only_stop_or_changed_invocation_is_refused(self):
        s={'unit':q.child.UNIT_PREFIX+'1'*32+'.scope'}
        observed={'LoadState':'loaded','InvocationID':'b'*32,'ControlGroup':'/foreign'}
        with patch.object(q,'show',return_value=observed),patch.object(q.subprocess,'run') as run:
            with self.assertRaises(ValueError):q._stop_owned(s,None,1e30)
            with self.assertRaises(ValueError):q._stop_owned(s,{'invocation_id':'a'*32,'cgroup':'/foreign'},1e30)
        run.assert_not_called()

    def test_disabled_loopback_current_namespace_and_scope_match_required(self):
        m,d=fixture(self.root);t=self.root/'slots'/m['slots'][0]['slot_id'];g=q.load(t/'GATE.json')[0];b=q.load(t/'native/BOUNDARY_BEFORE.json')[0]['observed']
        q.verify_boundary(g['expected_boundary'],b)
        for change in ({'interfaces':[{'name':'lo','up':True}]},{'interfaces':[{'name':'eth0','up':False}]},{'net_namespace':old.HOST_NET}):
            with self.assertRaises(ValueError):q.verify_boundary(g['expected_boundary'],dict(b,**change))

    def test_missing_release_nonzero_exit_native_member_or_late_cleanup_refuse(self):
        m,d=fixture(self.root);t=self.root/'slots'/m['slots'][0]['slot_id']
        original={p:p.read_bytes() for p in t.rglob('*') if p.is_file()}
        mutations=[('CLEANUP.json',lambda r:r.update(controller_exit_code=9)),
            ('SCOPE_WITNESS.json',lambda r:r.update(members=r['members']+[9999])),
            ('CLEANUP.json',lambda r:r.update(ended_monotonic=r['deadline_monotonic']+1)),
            ('CONTROLLER_EXIT.json',lambda r:r.update(normal_release=False))]
        for name,fn in mutations:
            self.tamper(t/name,fn);refresh(t)
            result=q.audit_qualification(self.root,manifest_sha256=d,strict=True);self.assertFalse(result['ok'],result)
            for p,raw in original.items():p.write_bytes(raw)
        (t/'RELEASE.json').unlink();refresh(t)
        self.assertFalse(q.audit_qualification(self.root,manifest_sha256=d,strict=True)['ok'])

    def test_request_stage_or_raw_journal_mutation_refuses(self):
        m,d=fixture(self.root);t=self.root/'slots'/m['slots'][0]['slot_id'];p=t/'native/computers/startup-qualification/startup/parent.jsonl'
        p.write_bytes(p.read_bytes()+q.canonical({'stage':'run_request_write_attempt'})+b'\n');refresh(t)
        self.assertFalse(q.audit_qualification(self.root,manifest_sha256=d,strict=True)['ok'])

    def test_native_evidence_rechecked_before_next_batch_can_continue(self):
        m,d=fixture(self.root);slot=m['slots'][0];t=self.root/'slots'/slot['slot_id']
        receipt=q.load(t/'RECEIPT.json')[0];execution=q.load(self.root/'EXECUTION.json')[0]
        intent=q.load(t/'INTENT.json')[0]
        self.assertTrue(q._validate_before_continue(t,self.root,m,execution,slot,intent,deepcopy(receipt))['safe_to_continue'])
        path=t/'native/computers/startup-qualification/startup/parent.jsonl';path.unlink()
        value=q._validate_before_continue(t,self.root,m,execution,slot,intent,receipt)
        self.assertFalse(value['safe_to_continue']);self.assertFalse(value['qualification_passed'])
        self.assertIsNone(value['native_inference_requests'])

    def test_halt_later_batches_after_failure_even_if_their_receipts_are_valid(self):
        m,d=fixture(self.root);t=self.root/'slots'/m['slots'][0]['slot_id']
        self.tamper(t/'RECEIPT.json',lambda r:r.update(status='startup_failed',qualification_passed=False,safe_to_continue=False))
        result=q.audit_qualification(self.root,manifest_sha256=d,strict=False)
        self.assertFalse(result['ok']);self.assertEqual(result['errors'][0]['code'],'later_batch_after_failure')

    def test_late_or_nonfinite_phase_cannot_extend_cleanup_deadline(self):
        from types import SimpleNamespace
        import threading
        for late in (170.,float('nan')):
            root=self.root/('late' if late==170 else 'nan');root.mkdir(parents=True)
            (root/'slots').mkdir();slot={'index':0,'slot_id':'start-00','batch':0,'unit':q.child.UNIT_PREFIX+'1'*32+'.scope'}
            supervisor=old.identity(900,ppid=899,ticks=50,net=old.HOST_NET,user=old.HOST_USER);supervisor['security_context']=LABEL
            m={'uid':old.UID,'controller_environment':{},'boot_id':old.BOOT};write(root/'manifest.json',m)
            write(root/'EXECUTION.json',{'supervisor':supervisor})
            digest=q.load(root/'manifest.json')[1];group=f'/user.slice/user-{old.UID}.slice/user@{old.UID}.service/app.slice/'+slot['unit']
            proc=old.identity(1000,ppid=900,group=group,argv=q.native_argv(root,slot));proc['security_context']=LABEL
            unit={k:v for k,v in old.active_unit(slot,proc).items() if k in q.SHOW_KEYS}
            binding={'main_identity':proc,'invocation_id':unit['InvocationID'],'cgroup':group,'kernel':q.child.KERNEL_LIMITS}
            fake=SimpleNamespace(pid=1000,poll=lambda:None)
            def launch(*args,**kwargs):
                trial=root/'slots'/slot['slot_id'];write(trial/'HELLO.json',{'slot_id':slot['slot_id'],'manifest_sha256':digest,'identity':proc})
                phase=trial/'native/STARTUP_FINISHED.json';phase.parent.mkdir()
                phase.write_text(json.dumps({'finished_monotonic':100.+late,'ready_observed':True}))
                return fake
            captured=[]
            def cleanup(slot,binding,known,process,trial,started,deadline,**kwargs):
                captured.append((started,deadline));return {'confirmed':False,'controller_exit_code':None,'ended_monotonic':deadline}
            with patch.object(q.time,'monotonic',return_value=100.),patch.object(q,'show',side_effect=[{'LoadState':'not-found'},unit]),patch.object(q,'identity',return_value=proc),patch.object(q,'kernel',return_value=q.child.KERNEL_LIMITS),patch.object(q,'validate_scope',return_value=binding),patch.object(q,'_collect',return_value=[1000]),patch.object(q.subprocess,'Popen',side_effect=launch),patch.object(q,'_cleanup',side_effect=cleanup):
                result=q._run_slot(root,m,slot,threading.Event())
            self.assertFalse(result['qualification_passed']);self.assertLessEqual(captured[0][1],280.)
            self.assertIsNone(result['startup_outcome'])
            self.assertTrue(any(e.get('code')=='startup_deadline_exceeded' for e in result['errors']))
            self.assertFalse((root/'slots'/slot['slot_id']/'CLOSE_GATE.json').exists())

    def test_published_registration_raw_hash_and_source_changes_refuse(self):
        m,d=fixture(self.root)
        self.assertFalse(q.audit_qualification(self.root,manifest_sha256='b'*64,strict=True)['ok'])
        with patch.object(q,'sources',return_value={}):self.assertFalse(q.audit_qualification(self.root,manifest_sha256=d,strict=True)['ok'])

    def test_execute_retains_fixed_slots_after_mock_first_failure_without_launch(self):
        m,d=fixture(self.root)
        # A fresh fixture manifest with native dispatch replaced by a labeled stub.
        import shutil
        shutil.rmtree(self.root/'slots');(self.root/'slots').mkdir()
        (self.root/'EXECUTION.json').unlink();(self.root/'REPORT.json').unlink()
        def fail(directory,manifest,slot,event):return {'slot':slot,'status':'fixture_failure','safe_to_continue':False,'qualification_passed':False}
        with patch.object(q,'_run_slot',side_effect=fail) as run,patch.object(q,'audit_qualification',return_value={'fixture':True}):q.execute(self.root,manifest_sha256=d)
        self.assertEqual(run.call_count,1)
        report=q.load(self.root/'REPORT.json')[0]
        self.assertEqual(len(report['results']),9);self.assertEqual(sum(r['status']=='skipped_after_stop' for r in report['results']),8)


if __name__=='__main__':unittest.main()
