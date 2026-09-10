"""Offline source/receipt/unit fixtures; no systemd, agent, provider or native call.

The synthetic successful transcripts test evidence reconstruction only. They are
not startup qualification results and cannot be used by the native entrypoint.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import os
import shutil
import sys
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import hermes_startup_qualification as q
from lifespan.evaluation.hermes_transport import contract
from lifespan.startup_observability import provenance, VERSION as OBS_VERSION


UID = os.getuid()
BOOT = 'fixture-boot'
HOST_NET = 'net:[10]'
HOST_USER = 'user:[20]'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(q.canonical(value) + b'\n')


def slots():
    return [{'index': i, 'slot_id': f'start-{i:02d}', 'batch': batch,
             'unit': q.child.UNIT_PREFIX + f'{i+1:032x}' + '.service'}
            for i, batch in enumerate([0, 1, 2, 3, 3, 4, 4, 5, 5])]


def identity(pid, *, ppid=900, group='/fixture', cwd=None, argv=None, ticks=100, net='net:[30]', user='user:[40]'):
    return {'pid': pid, 'ppid': ppid, 'start_ticks': ticks, 'uid': UID, 'boot_id': BOOT,
            'state': 'S', 'cgroup': group, 'cwd': str(q.ROOT) if cwd is None else cwd,
            'argv_sha256': q.sha(q.canonical(argv or ['fixture'])),
            'net_namespace': net, 'user_namespace': user}


def group(slot):
    return f'/user.slice/user-{UID}.slice/user@{UID}.service/app.slice/' + slot['unit']


def active_unit(slot, main):
    return {'Id': slot['unit'], 'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
        'MainPID': str(main['pid']), 'ControlGroup': group(slot), 'InvocationID': f'{slot["index"]+50:032x}',
        'ExecMainCode': '0', 'ExecMainStatus': '0', 'Result': 'success', 'KillMode': 'control-group',
        'TimeoutStopUSec': '5s', 'RuntimeMaxUSec': '3min', 'Restart': 'no', 'Delegate': 'no', 'RemainAfterExit':'yes','UnsetEnvironment':' '.join(q.UNSET_ENV)}


def terminal_unit(active):
    return dict(active, ActiveState='inactive', SubState='dead', MainPID='0', ExecMainCode='1')


def manifest(directory):
    return {'schema_version': 1, 'kind': q.VERSION, 'config': deepcopy(q.CONFIG), 'slots': slots(),
        'source_sha256': q.sources(), 'repository_commit': 'a'*40, 'dependencies': {'fixture': True},
        'boot_id': BOOT, 'uid': UID, 'root': str(directory), 'working_directory': str(q.ROOT),
        'python': q.interpreter(), 'resource_receipt_sha256': {},
        'controller_environment': {key:'fixture' for key in q.ENV_KEYS}, 'controller_import_paths': [],
        'child_execution': deepcopy(q.child.EXECUTION), 'created_at': 'fixture'}


@contextmanager
def isolated_guards():
    with patch.object(q, 'committed'), patch.object(q, 'verify_resource', return_value={}), \
         patch.object(q, 'boot', return_value=BOOT), patch.object(q, 'dependencies', return_value={'fixture': True}), \
         patch.object(q, 'controller_environment', return_value={key:'fixture' for key in q.ENV_KEYS}), \
         patch.object(q, 'controller_import_paths', return_value=[]):
        yield


def fixture(directory, *, overlap=False):
    directory.mkdir()
    (directory / 'slots').mkdir()
    m = manifest(directory)
    write(directory / 'manifest.json', m)
    digest = q.load(directory / 'manifest.json')[1]
    supervisor = identity(900, ppid=899, ticks=50, net=HOST_NET, user=HOST_USER)
    execution = {'registered_manifest_sha256': digest, 'supervisor': supervisor,
        'started_monotonic': 90., 'boot_id': BOOT, 'source_sha256': m['source_sha256'], 'dependencies': m['dependencies']}
    write(directory / 'EXECUTION.json', execution)
    receipts = []
    for slot in m['slots']:
        trial = directory / 'slots' / slot['slot_id']; trial.mkdir()
        start = 100. + slot['batch'] * 100
        if overlap and slot['index'] == 1:
            start = 120.
        finish = start + 30
        end = start + 40
        main = identity(1000+slot['index']*10, ppid=800, group=group(slot), argv=q.native_argv(directory, slot))
        client = identity(2000+slot['index'], ppid=900, argv=q.launch_argv(directory, slot))
        commands = q.expected_native_commands(trial,m)
        workspace = str(trial/'native/computers/startup-qualification/workspace')
        worker = identity(main['pid']+1, ppid=main['pid'], ticks=101, group=group(slot),argv=commands['worker'],cwd=workspace)
        sandbox = identity(main['pid']+2, ppid=worker['pid'], ticks=102, group=group(slot),argv=commands['sandbox'],cwd=workspace)
        unit = active_unit(slot, main)
        binding = {'verified': True, 'invocation_id': unit['InvocationID'], 'cgroup': group(slot),
                   'main_identity': main, 'kernel': deepcopy(q.child.KERNEL_LIMITS)}
        expected = {'uid': UID, 'boot_id': BOOT, 'host_net_namespace': HOST_NET,
                    'host_user_namespace': HOST_USER, 'unit': slot['unit'], 'invocation_id': unit['InvocationID']}
        before = {'uid': UID, 'boot_id': BOOT, 'net_namespace': main['net_namespace'],
                  'user_namespace': main['user_namespace'], 'interfaces': [{'name':'lo','up':False}],
                  'cgroup': group(slot), 'invocation_id': unit['InvocationID'], 'kernel': deepcopy(q.child.KERNEL_LIMITS)}
        intent = {'slot_id':slot['slot_id'], 'unit':slot['unit'], 'started_monotonic':start,
                  'startup_deadline_monotonic':start+150, 'manifest_sha256':digest,
                  'command_sha256':q.sha(q.canonical(q.launch_argv(directory, slot)))}
        write(trial / 'INTENT.json', intent)
        write(trial / 'CLIENT.json', {'identity':client, 'observed_monotonic':start+1})
        write(trial / 'HELLO.json', {'slot_id':slot['slot_id'], 'manifest_sha256':digest,
                                    'identity':main, 'observed_monotonic':start+1})
        write(trial / 'GATE.json', {'slot_id':slot['slot_id'], 'manifest_sha256':digest,
            'startup_deadline_monotonic':start+150, 'unit_binding':binding, 'unit_observation':unit,
            'expected_boundary':expected})
        computer = trial / 'native/computers/startup-qualification'
        native = trial / 'native'
        instance = {'kind':'ready','backend':'bubblewrap','employee':'startup-qualification',
            'pid':worker['pid'],'sandbox_pid':sandbox['pid'],'evaluation_transport':contract('nonstreaming'),
            'tool_names':['terminal','skill_view','enterprise_action'],
            'probe':json.dumps({'exit_code':0,'output':'/workspace\nstartup-qualification\n'})}
        write(computer / 'instance.json', instance)
        write(trial / 'NATIVE_IDENTITIES.json', {'instance_sha256':q.load(computer/'instance.json')[1],
                                                'identities':{'worker':worker,'sandbox':sandbox}})
        write(trial / 'CLOSE_GATE.json', {'slot_id':slot['slot_id'],'manifest_sha256':digest,
              'cleanup_deadline_monotonic':finish+30, 'native_identities':{'worker':worker,'sandbox':sandbox}})
        write(native / 'BOUNDARY_BEFORE.json', {'expected':expected,'observed':before,'verification':{'verified':True}})
        write(native / 'BOUNDARY_AFTER.json', {'observed':before,'verification':{'verified':True}})
        write(native / 'STARTUP_INTENT.json', {'kind':q.child.VERSION,'execution':q.child.EXECUTION,
            'helper_sha256':m['source_sha256']['scripts/hermes_startup_probe.py'],'work_requests_sent':0})
        phase = {'entered_monotonic':start+2,'startup_deadline':start+150,'finished_monotonic':finish,
                 'startup_elapsed_seconds':28.,'ready_observed':True,'error_type':None}
        write(native / 'STARTUP_FINISHED.json', phase)
        write(native / 'CLOSE_STARTED.json', {'started_monotonic':finish,'cleanup_deadline':finish+30})
        result = {'ready_observed':True,'error_type':None,'close_error_type':None,'pre_close_error_type':None,
            'outcome_receipt_error_type':None,'entered_monotonic':start+2,'startup_deadline':start+150,
            'startup_finished_monotonic':finish,'cleanup_deadline':finish+30,'close_finished_monotonic':finish+2,
            'close_returned_within_allowance':True,'work_requests_sent':0,'provider_credentials_supplied':False,
            'boundary_verified_before_and_after':True}
        write(native / 'CHILD_RESULT.json', result)
        attempt = f'{slot["index"]+90:032x}'
        write(computer / 'startup/manifest.json', {'version':OBS_VERSION,'attempt_id':attempt,**provenance()})
        stages = {'parent':['popen_returned','ready_received'],'worker':['worker_entered','imports_before',
            'imports_after','registry_before','registry_after','sandbox_before','sandbox_after','agent_before',
            'agent_after','budget_transport_before','budget_transport_after','probe_before','probe_after',
            'ready_write_attempt','ready_write_returned']}
        for role, values in stages.items():
            records = [{'version':OBS_VERSION,'attempt_id':attempt,'sequence':i,'role':role,'stage':stage,
                'monotonic_seconds':start+3+i, 'observer_identity':worker if role=='worker' else main,
                'worker_identity':worker,'error_type':None,'observation_errors':[]} for i,stage in enumerate(values)]
            (computer / 'startup' / (role+'.jsonl')).write_bytes(b'\n'.join(q.canonical(x) for x in records)+b'\n')
        retained = dict(unit, SubState='exited', MainPID='0', ExecMainCode='1')
        write(trial / 'UNIT_TERMINAL.json', {'unit':retained,'observed_monotonic':finish+5})
        cleanup = {'terminal_before_stop':retained,'unit_stop':{'requested':True,'returncode':0},'started_monotonic':finish,'ended_monotonic':end,'deadline_monotonic':finish+30,
            'limit_seconds':30,'unit_final':terminal_unit(unit),'members_remaining':[],
            'observed_processes':[{'identity':p,'state':'absent'} for p in (main,worker,sandbox)],
            'socket_cleanup':{'confirmed':True},'control_client_exit_code':0,'errors':[],'confirmed':True}
        write(trial / 'CLEANUP.json', cleanup)
        receipt = {'slot':slot,'status':'ready','intent_sha256':q.load(trial/'INTENT.json')[1],
            'client_identity':client,'unit_binding':binding,'startup_outcome':phase,'cleanup':cleanup,
            'boundary_verified':True,'errors':[],'qualification_passed':True,'safe_to_continue':True,
            'native_inference_requests':0,'work_requests_sent':0,'evidence_sha256':{}}
        write(trial / 'RECEIPT.json', receipt)
        refresh(trial)
        receipts.append(q.load(trial/'RECEIPT.json')[0])
    write(directory / 'REPORT.json', {'manifest_sha256':digest,'status':'completed','planned_slots':9,
        'qualification_passed':True,'results':receipts})
    return m, digest


def refresh(trial):
    receipt,_ = q.load(trial/'RECEIPT.json')
    receipt['evidence_sha256'] = {str(p.relative_to(trial)):q.sha(p.read_bytes()) for p in trial.rglob('*')
        if p.is_file() and p.suffix in ('.json','.jsonl') and p.name!='RECEIPT.json'}
    write(trial/'RECEIPT.json',receipt)


class ContractTests(unittest.TestCase):
    def test_fixed_nine_slot_schedule_and_literal_unit_command(self):
        self.assertEqual([len([x for x in slots() if x['batch']==b]) for b in range(6)], [1,1,1,2,2,2])
        command = q.launch_argv(Path('/fixture'),slots()[0])
        self.assertEqual(command[-len(q.native_argv(Path('/fixture'),slots()[0])):],q.native_argv(Path('/fixture'),slots()[0]))
        for value in q.PROPERTIES:
            self.assertIn('--property='+value, command)
        self.assertIn('--net',command); self.assertIn('--map-current-user',command)
        self.assertNotIn('--collect',command)
        self.assertEqual(q.CONFIG['startup_seconds'],150); self.assertEqual(q.CONFIG['cleanup_seconds'],30)

    def test_unit_main_is_not_control_client_and_exact_scope_required(self):
        slot=slots()[0]; directory=Path('/fixture')
        main=identity(1001,group=group(slot),argv=q.native_argv(directory,slot))
        observed=active_unit(slot,main)
        expected={'main_identity':deepcopy(main),'uid':UID,'boot_id':BOOT,
                  'host_net_namespace':HOST_NET,'host_user_namespace':HOST_USER}
        result=q.validate_unit(slot,observed,main,expected,directory=directory,kernel_values=q.child.KERNEL_LIMITS)
        self.assertTrue(result['verified'])
        for key,value in [('pid',999),('start_ticks',999),('uid',UID+1),('boot_id','other'),
                          ('cgroup','/foreign'),('cwd','/foreign'),('argv_sha256','0'*64),('net_namespace',HOST_NET)]:
            changed=dict(main,**{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                q.validate_unit(slot,observed,changed,expected,directory=directory,kernel_values=q.child.KERNEL_LIMITS)

    def test_exact_memory_cpu_and_lifecycle_readbacks(self):
        slot=slots()[0]; directory=Path('/fixture'); main=identity(1,group=group(slot),argv=q.native_argv(directory,slot))
        expected={'main_identity':main,'uid':UID,'boot_id':BOOT,'host_net_namespace':HOST_NET,'host_user_namespace':HOST_USER}
        for key,value in [('KillMode','process'),('Restart','always'),('Delegate','yes'),('RuntimeMaxUSec','5min'),('TimeoutStopUSec','30s')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                q.validate_unit(slot,dict(active_unit(slot,main),**{key:value}),main,expected,
                                directory=directory,kernel_values=q.child.KERNEL_LIMITS)
        for key in q.child.KERNEL_LIMITS:
            with self.subTest(key=key), self.assertRaises(ValueError):
                q.validate_unit(slot,active_unit(slot,main),main,expected,directory=directory,
                                kernel_values=dict(q.child.KERNEL_LIMITS,**{key:'max'}))

    def test_uncommitted_source_refused(self):
        with patch.object(q.subprocess,'check_output',return_value=b'actual'):
            with self.assertRaisesRegex(ValueError,'uncommitted_execution_source'):
                q.committed({'scripts/test.py':'0'*64},'a'*40)
        with self.assertRaisesRegex(ValueError,'invalid_source_commit'):
            q.committed({},'HEAD:invalid')

    def test_native_names_cannot_be_caller_arbitrary(self):
        for name in ['sshd.service','../'+slots()[0]['unit'], '--user',None]:
            with self.assertRaises(ValueError): q.checked_unit(name)

    def test_stop_requires_exact_invocation_before_control(self):
        slot=slots()[0]; main=identity(1,group=group(slot)); unit=active_unit(slot,main)
        binding={'invocation_id':'different','cgroup':group(slot)}
        with patch.object(q,'show',return_value=unit),patch.object(q.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'refuse_unbound_unit_stop'):
                q._stop_owned(slot,binding,deadline=q.time.monotonic()+10)
            run.assert_not_called()
        with patch.object(q,'show',return_value=unit),patch.object(q.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            q._stop_owned(slot,{'invocation_id':unit['InvocationID'],'cgroup':group(slot)},deadline=q.time.monotonic()+10)
            self.assertEqual(run.call_args.args[0][-2:],['stop',slot['unit']])

    def test_cgroup_inventory_includes_detached_nested_members(self):
        slot=slots()[0]
        with tempfile.TemporaryDirectory() as root,patch.object(q,'CGROUP_ROOT',Path(root)):
            base=Path(root)/group(slot).lstrip('/'); (base/'nested').mkdir(parents=True)
            (base/'cgroup.procs').write_text('1\n2\n'); (base/'nested/cgroup.procs').write_text('3\n')
            self.assertEqual(q.members(slot['unit'],group(slot),UID),[1,2,3])
            (base/'nested/cgroup.procs').unlink(); (base/'nested/cgroup.procs').symlink_to('/proc/self/stat')
            with self.assertRaises(ValueError):q.members(slot['unit'],group(slot),UID)

    def test_cleanup_inventory_time_is_inside_allowance(self):
        slot=slots()[0]; main=identity(1,group=group(slot)); unit=active_unit(slot,main)
        binding={'invocation_id':unit['InvocationID'],'cgroup':group(slot),'main_identity':main}
        with patch.object(q,'_stop_owned',return_value={'requested':True}),patch.object(q,'show',return_value=terminal_unit(unit)),\
             patch.object(q,'members',return_value=[]),patch.object(q,'identity',return_value=None),\
             patch.object(q,'_clean_sockets',return_value={'confirmed':True}),\
             patch.object(q.time,'monotonic',side_effect=[0.,1.,2.,3.,40.]):
            result=q._cleanup(slot,binding,{1:main},Mock(wait=Mock(return_value=0)),Path('/fixture'),0.,30.)
        self.assertFalse(result['confirmed'])
        self.assertGreater(result['ended_monotonic'],result['deadline_monotonic'])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'qualification'
        self.guards=isolated_guards();self.guards.__enter__();self.addCleanup(self.guards.__exit__,None,None,None)
        self.m,self.digest=fixture(self.root)
        self.trial=self.root/'slots/start-00'

    def audit(self):return q.audit_qualification(self.root,manifest_sha256=self.digest,strict=True)

    def test_complete_fake_receipts_reconcile_nine_slots_without_process_calls(self):
        with patch.object(q.subprocess,'Popen') as popen,patch.object(q,'show') as show:
            result=self.audit()
        self.assertTrue(result['ok'],result);self.assertTrue(result['qualification_passed']);self.assertEqual(len(result['slots']),9)
        popen.assert_not_called();show.assert_not_called()

    def test_published_hash_and_current_source_guard(self):
        self.assertFalse(q.audit_qualification(self.root,manifest_sha256='0'*64,strict=True)['ok'])
        with patch.object(q,'sources',return_value={}):self.assertFalse(self.audit()['ok'])

    def test_raw_equivalent_reformat_is_detected(self):
        path=self.trial/'native/CHILD_RESULT.json'; data,_=q.load(path)
        path.write_text(json.dumps(data,indent=4))
        self.assertFalse(self.audit()['ok'])

    def test_compensating_native_identity_rewrite_is_rejected(self):
        path=self.trial/'native/computers/startup-qualification/instance.json'; data,_=q.load(path)
        data['pid']+=10;write(path,data);refresh(self.trial)
        self.assertFalse(self.audit()['ok'])

    def test_added_work_request_journal_is_rejected_even_with_updated_hash(self):
        path=self.trial/'native/computers/startup-qualification/startup/parent.jsonl'
        rows=[json.loads(x) for x in path.read_bytes().splitlines()]
        rows.append(dict(rows[-1],stage='run_request_write_attempt',sequence=2))
        path.write_bytes(b'\n'.join(q.canonical(x) for x in rows)+b'\n');refresh(self.trial)
        self.assertFalse(self.audit()['ok'])

    def test_callback_error_prevents_forged_success(self):
        path=self.trial/'native/CHILD_RESULT.json'; data,_=q.load(path)
        data['pre_close_error_type']='TimeoutError';write(path,data);refresh(self.trial)
        self.assertFalse(self.audit()['ok'])

    def test_cleanup_native_identity_omission_and_unit_invocation_rejected(self):
        for mutation in ('identity','invocation','late'):
            with self.subTest(mutation=mutation):
                original,_=q.load(self.trial/'RECEIPT.json'); receipt=deepcopy(original)
                cleanup=receipt['cleanup']
                if mutation=='identity':cleanup['observed_processes'].pop()
                if mutation=='invocation':cleanup['unit_final']['InvocationID']='f'*32
                if mutation=='late':cleanup['ended_monotonic']=cleanup['deadline_monotonic']+1
                write(self.trial/'CLEANUP.json',cleanup);write(self.trial/'RECEIPT.json',receipt);refresh(self.trial)
                self.assertFalse(self.audit()['ok'])
                write(self.trial/'RECEIPT.json',original);write(self.trial/'CLEANUP.json',original['cleanup']);refresh(self.trial)

    def test_native_controller_parent_is_systemd_not_control_client(self):
        receipt,_=q.load(self.trial/'RECEIPT.json')
        self.assertNotEqual(receipt['unit_binding']['main_identity']['ppid'],receipt['client_identity']['pid'])
        self.assertTrue(self.audit()['ok'])
        client,_=q.load(self.trial/'CLIENT.json');client['identity']['ppid']=123
        receipt['client_identity']=client['identity'];write(self.trial/'CLIENT.json',client);write(self.trial/'RECEIPT.json',receipt);refresh(self.trial)
        self.assertFalse(self.audit()['ok'])

    def test_missing_slot_and_terminal_report_are_incomplete_not_zero_success(self):
        (self.root/'slots/start-08/RECEIPT.json').unlink();(self.root/'REPORT.json').unlink()
        result=self.audit();self.assertFalse(result['ok']);self.assertEqual(result['status'],'incomplete')
        self.assertEqual(len(result['slots']),9);self.assertEqual(result['slots'][-1]['status'],'missing')

    def test_batch_overlap_is_rejected(self):
        other=Path(self.tmp.name)/'overlap';_,digest=fixture(other,overlap=True)
        result=q.audit_qualification(other,manifest_sha256=digest,strict=True)
        self.assertFalse(result['ok']);self.assertEqual(result['errors'][0]['code'],'batch_barrier_broken')

    def test_self_consistent_changed_host_namespace_is_rejected(self):
        path=self.trial/'GATE.json';gate,_=q.load(path)
        gate['expected_boundary']['host_net_namespace']='net:[999]';write(path,gate);refresh(self.trial)
        self.assertFalse(self.audit()['ok'])


class OrchestrationTests(unittest.TestCase):
    def execute_fixture(self, root, *, fail=None, unknown=None):
        root.mkdir();(root/'slots').mkdir();m=manifest(root);write(root/'manifest.json',m)
        digest=q.load(root/'manifest.json')[1]; seen=[]
        def run(directory,man,slot,stop):
            seen.append(slot['index'])
            if slot['index']==unknown:raise RuntimeError('fixture failure')
            ok=slot['index']!=fail
            return {'slot':slot,'status':'ready' if ok else 'startup_failed',
                    'qualification_passed':ok,'safe_to_continue':ok,'native_inference_requests':0}
        with isolated_guards(),patch.object(q,'identity',return_value=identity(900)),patch.object(q,'_run_slot',side_effect=run),\
             patch.object(q,'audit_qualification',return_value={'ok':True}):
            q.execute(root,manifest_sha256=digest)
            with self.assertRaisesRegex(ValueError,'one_shot'):q.execute(root,manifest_sha256=digest)
        return seen,q.load(root/'REPORT.json')[0]

    def test_all_nine_fixed_slots_execute_once_in_counterbalanced_batches(self):
        with tempfile.TemporaryDirectory() as root:seen,report=self.execute_fixture(Path(root)/'new')
        self.assertEqual(sorted(seen),list(range(9)));self.assertEqual(report['status'],'completed')
        self.assertTrue(report['qualification_passed']);self.assertEqual(len(report['results']),9)

    def test_any_failed_first_start_halts_future_batches_keeps_all_slots(self):
        with tempfile.TemporaryDirectory() as root:seen,report=self.execute_fixture(Path(root)/'new',fail=0)
        self.assertEqual(seen,[0]);self.assertEqual(report['status'],'incomplete')
        self.assertEqual([x['status'] for x in report['results']],['startup_failed']+['skipped_after_stop']*8)

    def test_unknown_in_pair_keeps_already_planned_peer_and_skips_remaining(self):
        with tempfile.TemporaryDirectory() as root:seen,report=self.execute_fixture(Path(root)/'new',unknown=3)
        self.assertEqual(sorted(seen),list(range(5)));self.assertEqual(len(report['results']),9)
        self.assertEqual(report['results'][3]['status'],'unresolved')
        self.assertEqual([x['status'] for x in report['results'][5:]],['skipped_after_stop']*4)


class AdditionalGuardsTests(unittest.TestCase):
    def test_bootstrap_clears_provider_proxy_loader_and_plugin_environment(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'new';directory.mkdir();m=manifest(directory)
            write(directory/'manifest.json',m)
            write(directory/'EXECUTION.json',{'registered_manifest_sha256':q.load(directory/'manifest.json')[1]})
            observed={}
            def worker(path,slot):
                observed.update(environment=dict(os.environ),path=str(path),slot=slot,imports=list(sys.path))
            fake=SimpleNamespace(_worker=worker)
            original_path=list(sys.path)
            try:
                with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-secret','HTTPS_PROXY':'fixture-proxy',
                        'LD_PRELOAD':'fixture-loader','HERMES_MANAGED_DIR':'fixture-override','INVOCATION_ID':'a'*32},clear=True), \
                     patch.object(sys,'argv',['bootstrap',str(q.ROOT),str(directory),'start-00']), \
                     patch.dict(sys.modules,{'scripts.hermes_startup_qualification':fake}):
                    exec(compile(q.BOOTSTRAP,'<isolated bootstrap fixture>','exec'),{})
            finally:
                sys.path[:]=original_path
            self.assertEqual(observed['environment'],{**m['controller_environment'],'INVOCATION_ID':'a'*32})
            self.assertEqual(observed['slot'],'start-00')
            self.assertEqual(observed['imports'][0],str(q.ROOT))
            self.assertNotIn('fixture-secret',json.dumps(observed))

    def test_isolated_bootstrap_refuses_changed_manifest_before_import(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root);write(directory/'manifest.json',manifest(directory))
            write(directory/'EXECUTION.json',{'registered_manifest_sha256':'0'*64})
            with patch.object(sys,'argv',['bootstrap',str(q.ROOT),str(directory),'start-00']),self.assertRaises(AssertionError):
                exec(compile(q.BOOTSTRAP,'<bad bootstrap fixture>','exec'),{})

    def test_source_discovery_prunes_private_and_test_trees(self):
        with tempfile.TemporaryDirectory() as root,patch.object(q,'ROOT',Path(root)):
            base=Path(root);(base/'lifespan/artifacts/deep').mkdir(parents=True)
            (base/'lifespan/tests').mkdir();(base/'scripts').mkdir()
            (base/'lifespan/good.py').write_text('pass')
            (base/'lifespan/artifacts/deep/secret.py').write_text('must not read')
            (base/'lifespan/tests/test.py').write_text('must not read')
            for name in ('hermes_startup_qualification.py','hermes_startup_probe.py','startup_resource_controls.py'):
                (base/'scripts'/name).write_text('pass')
            self.assertEqual(set(q.sources()),{'lifespan/good.py','scripts/hermes_startup_qualification.py',
                'scripts/hermes_startup_probe.py','scripts/startup_resource_controls.py'})

    def test_observation_failure_forbids_socket_mutation(self):
        slot=slots()[0];main=identity(1,group=group(slot));unit=active_unit(slot,main)
        binding={'invocation_id':unit['InvocationID'],'cgroup':group(slot),'main_identity':main}
        for failure in ('show','members'):
            with self.subTest(failure=failure),patch.object(q,'_stop_owned',return_value={'requested':True}), \
                 patch.object(q,'show',side_effect=OSError if failure=='show' else None,
                              return_value=terminal_unit(unit)), \
                 patch.object(q,'members',side_effect=OSError if failure=='members' else None,return_value=[]), \
                 patch.object(q,'identity',return_value=None),patch.object(q,'_clean_sockets') as clean:
                result=q._cleanup(slot,binding,{1:main},Mock(wait=Mock(return_value=0)),Path('/fixture'),
                                  q.time.monotonic(),q.time.monotonic()+2)
                self.assertFalse(result['confirmed']);clean.assert_not_called()

    def test_symlink_control_ancestor_cannot_delete_foreign_socket(self):
        with tempfile.TemporaryDirectory() as root:
            trial=Path(root)/'trial';trial.mkdir();foreign=Path(root)/'foreign';foreign.mkdir()
            (trial/'native').symlink_to(foreign,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'control_parent_symlink'),patch.object(Path,'unlink') as unlink:
                q._clean_sockets(trial)
            unlink.assert_not_called()

    def test_ready_write_returned_after_parent_finish_is_valid_before_close(self):
        with tempfile.TemporaryDirectory() as root,isolated_guards():
            directory=Path(root)/'new';m,digest=fixture(directory);trial=directory/'slots/start-00'
            path=trial/'native/computers/startup-qualification/startup/worker.jsonl'
            rows=[json.loads(x) for x in path.read_bytes().splitlines()]
            rows[-1]['monotonic_seconds']=131.  # parent finish130, native close complete132
            path.write_bytes(b'\n'.join(q.canonical(x) for x in rows)+b'\n');refresh(trial)
            report,_=q.load(directory/'REPORT.json');report['results'][0]=q.load(trial/'RECEIPT.json')[0];write(directory/'REPORT.json',report)
            result=q.audit_qualification(directory,manifest_sha256=digest,strict=True)
            self.assertTrue(result['ok'],result)
            rows[-1]['monotonic_seconds']=133.
            path.write_bytes(b'\n'.join(q.canonical(x) for x in rows)+b'\n');refresh(trial)
            self.assertFalse(q.audit_qualification(directory,manifest_sha256=digest,strict=True)['ok'])

    def test_collected_unit_needs_retained_invocation_success(self):
        with tempfile.TemporaryDirectory() as root,isolated_guards():
            directory=Path(root)/'new';m,digest=fixture(directory);trial=directory/'slots/start-00'
            receipt,_=q.load(trial/'RECEIPT.json');cleanup=receipt['cleanup']
            cleanup['unit_final'].update(LoadState='not-found',InvocationID='',ControlGroup='')
            write(trial/'CLEANUP.json',cleanup);write(trial/'RECEIPT.json',receipt);refresh(trial)
            report,_=q.load(directory/'REPORT.json');report['results'][0]=q.load(trial/'RECEIPT.json')[0];write(directory/'REPORT.json',report)
            result=q.audit_qualification(directory,manifest_sha256=digest,strict=True)
            self.assertTrue(result['ok'],result)
            (trial/'UNIT_TERMINAL.json').unlink();refresh(trial)
            self.assertFalse(q.audit_qualification(directory,manifest_sha256=digest,strict=True)['ok'])

    def test_actual_supervisor_loop_late_phase_cannot_extend_cleanup(self):
        with tempfile.TemporaryDirectory() as root,isolated_guards():
            directory=Path(root)/'new';m,digest=fixture(directory);slot=m['slots'][0]
            trial=directory/'slots/start-00';donor=directory/'donor';trial.rename(donor)
            original,_=q.load(donor/'RECEIPT.json')
            main=original['unit_binding']['main_identity'];client=original['client_identity']
            native_ids=q.load(donor/'NATIVE_IDENTITIES.json')[0]['identities']
            identities={x['pid']:x for x in [main,client,*native_ids.values()]}
            phase_path=donor/'native/STARTUP_FINISHED.json';phase,_=q.load(phase_path)
            phase['finished_monotonic']=270.;write(phase_path,phase) # start100 +150 deadline250
            def spawn(*args,**kwargs):
                shutil.copytree(donor/'native',trial/'native')
                shutil.copy2(donor/'HELLO.json',trial/'HELLO.json')
                return Mock(pid=client['pid'],poll=Mock(return_value=0))
            cleanup=deepcopy(original['cleanup']);cleanup['confirmed']=False
            with patch.object(q.time,'monotonic',return_value=100.), \
                 patch.object(q.subprocess,'Popen',side_effect=spawn), \
                 patch.object(q,'show',side_effect=[{'LoadState':'not-found'},active_unit(slot,main)]), \
                 patch.object(q,'identity',side_effect=lambda pid:identities.get(pid)), \
                 patch.object(q,'kernel',return_value=q.child.KERNEL_LIMITS), \
                 patch.object(q,'members',return_value=list(native_ids[x]['pid'] for x in native_ids)), \
                 patch.object(q,'_cleanup',return_value=cleanup) as clean:
                receipt=q._run_slot(directory,m,slot,q.threading.Event())
            self.assertFalse(receipt['qualification_passed'])
            self.assertLessEqual(clean.call_args.args[-1],280.)
            self.assertFalse((trial/'CLOSE_GATE.json').exists())
            self.assertIn('startup_deadline_exceeded',[x['code'] for x in receipt['errors']])


if __name__=='__main__':unittest.main()
