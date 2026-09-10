"""Offline lifecycle fixtures; no MiroFish, Hermes, provider or study execution."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from scripts import scale_v2_process as lifecycle


def process(pid, parent=1, birth=100):
    return dict(pid=pid, ppid=parent, pgid=pid, sid=pid, start_ticks=birth,
                uid=os.getuid(), state='S', boot_id='offline-fixture-boot')


class LifecycleFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'; self.root.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(lifecycle, 'ROOT', self.root).start()
        self.campaign = self.root / 'lifespan/artifacts/campaign'
        self.run = self.campaign / 'run'; self.world = self.run / 'lifecycle'
        self.backend = self.root / 'MiroFish/backend'
        for name in ('run.py', 'app/config.py', 'scripts/run_reddit_simulation.py'):
            path = self.backend / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# offline source fixture\n')
        helper = self.root / 'scripts/scale_v2_process.py'; helper.parent.mkdir(); helper.write_bytes(Path(lifecycle.__file__).read_bytes())
        runner = self.root / 'lifespan/evaluation/runner.py'; runner.parent.mkdir(parents=True); runner.write_text('# offline canonical runner fixture\n')
        self.python = self.backend / '.venv/bin/python'; self.python.parent.mkdir(parents=True); self.python.symlink_to(sys.executable)
        self.service_identity = process(900001)
        self.world_identity = process(900002, birth=200)
        self.oasis_identity = process(900003, parent=900001, birth=201)
        self.sandbox_identity = process(900004, parent=900002, birth=202)
        self.worker_identity = process(900005, parent=900004, birth=203)
        self.config = dict(mirofish_service_url=lifecycle.SERVICE_URL)
        lifecycle.save(self.run / 'config.json', self.config)
        self.service_binding = dict(schema_version=1, worktree=str(self.root), backend=str(self.backend),
            python=str(self.python), python_sha256=lifecycle.sha(self.python), server_url=lifecycle.SERVICE_URL,
            configuration=dict(config_module=str(self.backend/'app/config.py'), uploads=str(self.backend/'uploads'),
                graph_database=str(self.backend/'uploads/local_graph.sqlite3'), graph_backend='local',
                debug=False, host='127.0.0.1', port='5002'),
            source_sha256={name:lifecycle.sha(self.root/name) for name in
                ('MiroFish/backend/run.py','MiroFish/backend/app/config.py','scripts/scale_v2_process.py')})
        self.world_binding = dict(run_directory=str(self.run),config_sha256=lifecycle.sha(self.run/'config.json'),
            service_url=lifecycle.SERVICE_URL,runner_sha256=lifecycle.sha(runner),python_sha256=lifecycle.sha(sys.executable))

    def launch(self, directory, kind, command, cwd, binding, root, started):
        intent=dict(schema_version=1,kind=kind,command=command,cwd=str(cwd),binding=binding,
                    helper_sha256=lifecycle.sha(lifecycle.__file__),started_monotonic=started)
        lifecycle.save(directory/(kind+'_INTENT.json'),intent)
        start=dict(intent,root_identity=root,intent_sha256=lifecycle.sha(directory/(kind+'_INTENT.json')))
        lifecycle.save(directory/(kind+'_START.json'),start)
        return start

    def base(self):
        self.service_start=self.launch(self.campaign,'SERVICE',[str(self.python),'run.py'],self.backend,
            self.service_binding,self.service_identity,10)
        self.world_start=self.launch(self.world,'WORLD',[sys.executable,'-u','-m','lifespan.evaluation.runner','--out',str(self.run),
            '--config',str(self.run/'config.json')],self.root,self.world_binding,self.world_identity,20)

    def complete(self):
        self.base()
        observation=dict(schema_version=1,helper_sha256=lifecycle.sha(lifecycle.__file__),
            start_sha256=lifecycle.sha(self.campaign/'SERVICE_START.json'),observed_monotonic=29,
            socket=dict(address='127.0.0.1',port=5002,inode='789',owner_identity=self.service_identity),
            owned_processes=[self.service_identity,self.oasis_identity])
        lifecycle.save(self.campaign/'SERVICE_OBSERVATION.json',observation)
        initial=deepcopy(observation);initial['observed_monotonic']=11;initial['owned_processes']=[self.service_identity]
        raw=(json.dumps(initial,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        lifecycle.save(self.campaign/'SERVICE_READY.json',dict(schema_version=1,helper_sha256=lifecycle.sha(lifecycle.__file__),
            start_sha256=lifecycle.sha(self.campaign/'SERVICE_START.json'),ready_monotonic=12,health={'status':'ok'},
            observation=initial,observation_sha256=lifecycle.hashlib.sha256(raw).hexdigest()))
        directory=self.backend/'uploads/simulations/fixture-simulation'; directory.mkdir(parents=True)
        (directory/'simulation_config.json').write_text('{}\n')
        (directory/'run_state.json').write_text(json.dumps(dict(process_pid=self.oasis_identity['pid'])))
        lifecycle.save(self.run/'actors/mirofish_state.json',dict(simulation=dict(simulation_id=directory.name)))
        computer=self.run/'work/fixture/computers/employee'; computer.mkdir(parents=True)
        self.alias=Path('/tmp')/('lifespan-bwrap-fixture-'+Path(self.temporary.name).name)
        self.addCleanup(self.remove_alias)
        self.instance=computer/'instance.json'; self.control=computer/'control'; self.control.mkdir()
        value=dict(backend='bubblewrap',pid=self.worker_identity['pid'],sandbox_pid=self.sandbox_identity['pid'],
                   rpc_socket=str(self.alias/'control/command.sock'))
        lifecycle.save(self.instance,value)
        instance=dict(instance_path=str(self.instance),instance_sha256=lifecycle.sha(self.instance),
            worker_identity=self.worker_identity,sandbox_identity=self.sandbox_identity,rpc_socket=value['rpc_socket'],
            alias=str(self.alias),control_target=str(self.control),owned_alias_observed=True)
        simulation=dict(simulation_id=directory.name,state_path=str(self.run/'actors/mirofish_state.json'),
            state_sha256_at_binding=lifecycle.sha(self.run/'actors/mirofish_state.json'),
            run_state_sha256_at_binding=lifecycle.sha(directory/'run_state.json'),identity=self.oasis_identity,cwd=str(directory),
            script=str(self.backend/'scripts/run_reddit_simulation.py'),
            script_sha256=lifecycle.sha(self.backend/'scripts/run_reddit_simulation.py'),
            config_path=str(directory/'simulation_config.json'),config_sha256=lifecycle.sha(directory/'simulation_config.json'),
            service_identity=self.service_identity)
        known=[self.world_identity,self.oasis_identity,self.sandbox_identity,self.worker_identity]
        self.world_observation=dict(schema_version=1,helper_sha256=lifecycle.sha(lifecycle.__file__),
            start_sha256=lifecycle.sha(self.world/'WORLD_START.json'),observed_monotonic=28,
            owned_processes=known,native_instances=[instance],simulation=simulation)
        lifecycle.save(self.world/'WORLD_OBSERVATION.json',self.world_observation)
        def cleanup(kind,folder,items,begin,end):
            return dict(schema_version=1,helper_sha256=lifecycle.sha(lifecycle.__file__),status='confirmed',
                start_sha256=lifecycle.sha(folder/(kind+'_START.json')),
                observation_sha256=lifecycle.sha(folder/(kind+'_OBSERVATION.json')),
                started_monotonic=begin,ended_monotonic=end,limit_seconds=30,root_exitcode=0,failures=[],
                clock_scope='through_final_inventory_and_poll; excludes_terminal_receipt_write',
                processes=dict(signals=[],observations_after=[dict(identity=item,state='absent',observed_current=None) for item in items]))
        self.world_cleanup=cleanup('WORLD',self.world,known,30,31)
        self.world_cleanup.update(environment_close=dict(simulation_id=directory.name,env_alive=False),
                                  sockets=[dict(instance_sha256=instance['instance_sha256'],alias_absent=True,underlying_socket_absent=True)])
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)
        self.service_cleanup=cleanup('SERVICE',self.campaign,[self.service_identity,self.oasis_identity],32,33)
        lifecycle.save(self.campaign/'SERVICE_CLEANUP.json',self.service_cleanup)

    def remove_alias(self):
        if self.alias.is_symlink(): self.alias.unlink()
        elif self.alias.exists():
            if (self.alias/'control').is_symlink(): (self.alias/'control').unlink()
            self.alias.rmdir()

    def world_audit(self,completed=True):
        return lifecycle.validate_world_receipts(self.world,self.run,self.service_start,completed=completed)

    def update_observation(self):
        lifecycle.save(self.world/'WORLD_OBSERVATION.json',self.world_observation)
        self.world_cleanup['observation_sha256']=lifecycle.sha(self.world/'WORLD_OBSERVATION.json')
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)

    def test_complete_pure_receipts_and_public_clock_fields(self):
        self.complete()
        with patch.object(lifecycle,'identity',side_effect=AssertionError('pure audit used proc')),patch.object(lifecycle,'_request',side_effect=AssertionError('pure audit used HTTP')):
            service=lifecycle.validate_service_receipts(self.campaign,completed=True); world=self.world_audit()
        self.assertTrue(service['ok'],service);self.assertTrue(world['ok'],world)
        self.assertEqual((world['started_monotonic'],world['cleanup_started_monotonic'],world['ended_monotonic']),(20,30,31))
        self.assertEqual(world['cleanup_limit_seconds'],30)
        self.assertEqual(len(world['hashes']),4)

    def test_partial_start_is_explicit_and_strict_refused(self):
        self.base()
        for audit in (lambda strict:lifecycle.validate_service_receipts(self.campaign,completed=strict),self.world_audit):
            partial=audit(False);self.assertTrue(partial['ok'],partial);self.assertFalse(partial['cleanup_confirmed'])
            self.assertIsNone(partial['ended_monotonic']);self.assertFalse(audit(True)['ok'])

    def test_unknown_live_and_false_absence_never_confirm(self):
        for state,current in (('unknown',None),('same_alive',self.worker_identity),('absent',self.worker_identity)):
            with self.subTest(state=state):
                self.complete(); row=self.world_cleanup['processes']['observations_after'][-1]
                row.update(state=state,observed_current=current)
                lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)
                self.assertFalse(self.world_audit()['ok'])
                # Fixture creation is idempotent except mkdir; reset local tree.
                if state != 'absent': self.tear_fixture_files()

    def tear_fixture_files(self):
        import shutil
        shutil.rmtree(self.backend/'uploads',ignore_errors=True)
        shutil.rmtree(self.run/'work',ignore_errors=True)

    def test_unowned_signal_and_ancestry_rejected(self):
        self.complete();self.world_cleanup['processes']['signals']=[dict(identity=process(999999),signal='TERM')]
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup);self.assertFalse(self.world_audit()['ok'])
        self.world_cleanup['processes']['signals']=[]
        self.world_cleanup['processes']['observations_after'][-1]['identity']=dict(self.worker_identity,ppid=999999)
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup);self.assertFalse(self.world_audit()['ok'])

    def test_cleanup_bounds_source_and_clock_tamper(self):
        self.complete()
        for key,value in (('limit_seconds',999),('limit_seconds',True),('ended_monotonic',float('inf')),('started_monotonic',1),('helper_sha256','0'*64)):
            with self.subTest(key=key,value=value):
                modified=dict(self.world_cleanup);modified[key]=value
                (self.world/'WORLD_CLEANUP.json').write_text(json.dumps(modified))
                self.assertFalse(self.world_audit()['ok'])
        modified=dict(self.world_cleanup,ended_monotonic=62)
        lifecycle.save(self.world/'WORLD_CLEANUP.json',modified);self.assertFalse(self.world_audit()['ok'])

    def test_completed_nonzero_exit_is_not_behavioral_zero(self):
        self.complete();self.world_cleanup['root_exitcode']=1
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)
        self.assertTrue(self.world_audit(False)['ok']);self.assertFalse(self.world_audit(True)['ok'])

    def test_simulation_other_service_or_changed_native_config_rejected(self):
        self.complete(); self.world_observation['simulation']['service_identity']=process(987654)
        self.update_observation();self.assertFalse(self.world_audit()['ok'])
        self.world_observation['simulation']['service_identity']=self.service_identity;self.update_observation()
        Path(self.world_observation['simulation']['config_path']).write_text('{"changed":true}')
        self.assertFalse(self.world_audit()['ok'])

    def test_instance_pid_drop_or_failed_startup_rejected(self):
        self.complete();self.world_observation['native_instances']=[];self.update_observation()
        self.assertFalse(self.world_audit()['ok'])
        self.instance.unlink();self.world_cleanup['sockets']=[];self.update_observation()
        hermes=self.instance.parent/'hermes';hermes.mkdir();(hermes/'config.yaml').write_text('# fixture')
        self.assertFalse(self.world_audit()['ok'])

    def test_socket_survival_and_dangling_alias_rejected(self):
        self.complete();self.alias.symlink_to('/nonexistent-offline-fixture')
        self.assertFalse(self.world_audit()['ok']);self.alias.unlink()
        self.alias.mkdir();(self.alias/'control').symlink_to(self.control)
        with socket.socket(socket.AF_UNIX) as sock: sock.bind(str(self.alias/'control/command.sock'))
        (self.alias/'control').unlink();self.alias.rmdir()
        self.assertFalse(self.world_audit()['ok'])

    def test_malformed_nested_data_and_missing_observation_fail_safely(self):
        self.complete();self.world_observation['owned_processes']=None;self.update_observation()
        result=self.world_audit();self.assertFalse(result['ok']);self.assertNotIn(str(self.root),json.dumps(result))
        (self.world/'WORLD_OBSERVATION.json').unlink();self.world_cleanup['observation_sha256']=None
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)
        self.assertFalse(self.world_audit(False)['ok'])

    def test_service_socket_source_and_owner_guards(self):
        self.complete();path=self.campaign/'SERVICE_OBSERVATION.json';item=lifecycle.read(path)[0]
        item['socket']['owner_identity']=self.world_identity;lifecycle.save(path,item)
        self.service_cleanup['observation_sha256']=lifecycle.sha(path);lifecycle.save(self.campaign/'SERVICE_CLEANUP.json',self.service_cleanup)
        self.assertFalse(lifecycle.validate_service_receipts(self.campaign,completed=True)['ok'])
        item['socket']['owner_identity']=self.service_identity;lifecycle.save(path,item)
        self.service_cleanup['observation_sha256']=lifecycle.sha(path);lifecycle.save(self.campaign/'SERVICE_CLEANUP.json',self.service_cleanup)
        (self.backend/'run.py').write_text('# changed source')
        self.assertFalse(lifecycle.validate_service_receipts(self.campaign,completed=True)['ok'])

    def test_service_ready_is_immutable_and_required_for_completed(self):
        self.complete();audit=lifecycle.validate_service_receipts(self.campaign,completed=True)
        self.assertTrue(audit['ok'],audit);self.assertEqual(audit['ready_monotonic'],12)
        path=self.campaign/'SERVICE_READY.json';ready=lifecycle.read(path)[0]
        ready['ready_monotonic']=131;lifecycle.save(path,ready)
        self.assertFalse(lifecycle.validate_service_receipts(self.campaign,completed=True)['ok'])
        path.unlink();self.assertFalse(lifecycle.validate_service_receipts(self.campaign,completed=True)['ok'])

    def test_service_cannot_drop_previously_observed_descendant(self):
        self.complete();self.service_cleanup['processes']['observations_after']=self.service_cleanup['processes']['observations_after'][:1]
        lifecycle.save(self.campaign/'SERVICE_CLEANUP.json',self.service_cleanup)
        self.assertFalse(lifecycle.validate_service_receipts(self.campaign,completed=True)['ok'])

    def test_bootstrap_starting_null_pid_and_partial_native_write_are_pending(self):
        from unittest.mock import Mock
        self.base();sid='pending-fixture';directory=self.backend/'uploads/simulations'/sid;directory.mkdir(parents=True)
        lifecycle.save(self.run/'actors/mirofish_state.json',dict(simulation=dict(simulation_id=sid)))
        handle=lifecycle.Handle(Mock(),self.world,'WORLD',self.root,20,self.world_identity,self.world_binding,
                               known={self.world_identity['pid']:self.world_identity})
        native=directory/'run_state.json'
        native.write_text('{"runner_status":"starting","process_pid":null}')
        with patch.object(lifecycle,'discover_owned'):
            row=lifecycle.observe_world(handle,self.run,None)
        self.assertIsNone(row['simulation']);self.assertEqual(row['simulation_pending']['reason'],'native_process_not_yet_started')
        self.assertTrue(self.world_audit(False)['ok'])
        native.write_text('{"runner_status":')
        with patch.object(lifecycle,'discover_owned'):
            row=lifecycle.observe_world(handle,self.run,None)
        self.assertEqual(row['simulation_pending']['reason'],'native_run_state_write_in_progress_or_malformed')
        native.write_text('{"runner_status":"failed","process_pid":null}')
        with patch.object(lifecycle,'discover_owned'):
            with self.assertRaisesRegex(ValueError,'simulation_pid_missing'):lifecycle.observe_world(handle,self.run,None)

    def test_final_inventory_time_is_inside_cleanup_cap(self):
        from unittest.mock import Mock
        self.complete();handle=lifecycle.Handle(Mock(),self.world,'WORLD',self.root,0,self.world_identity,self.world_binding,
            known={item['pid']:item for item in self.world_observation['owned_processes']},
            instances={str(self.instance):self.world_observation['native_instances'][0]},simulation=self.world_observation['simulation'])
        handle.process.poll.return_value=0;(self.world/'WORLD_CLEANUP.json').unlink()
        now=[0.0]
        def inventory(_):now[0]=6.0;return [self.instance.parent]
        with patch.object(lifecycle,'observe_world',return_value=self.world_observation),\
             patch.object(lifecycle,'_stop_known',return_value=self.world_cleanup['processes']),\
             patch.object(lifecycle,'_request',return_value={'data':{'env_alive':False}}),\
             patch.object(lifecycle,'_computer_roots',side_effect=inventory),patch.object(lifecycle.time,'monotonic',side_effect=lambda:now[0]):
            result=lifecycle.cleanup_world(handle,self.run,None,timeout_seconds=5)
        self.assertEqual(result['ended_monotonic'],6);self.assertEqual(result['status'],'unconfirmed')

    def test_cleanup_environment_close_cannot_name_another_world(self):
        self.complete();self.world_cleanup['environment_close']['simulation_id']='another-world'
        lifecycle.save(self.world/'WORLD_CLEANUP.json',self.world_cleanup)
        self.assertFalse(self.world_audit()['ok'])

    def test_service_start_failure_attempts_bounded_cleanup(self):
        from unittest.mock import Mock
        handle=Mock();handle.started_monotonic=time.monotonic();handle.poll.return_value=1
        with patch.object(lifecycle,'validate_installation',return_value=self.service_binding),\
             patch.object(lifecycle.socket,'socket') as socket_mock,patch.object(lifecycle,'_spawn',return_value=handle),\
             patch.object(lifecycle,'cleanup_service') as cleanup:
            with self.assertRaisesRegex(ValueError,'service_startup_failed'):
                lifecycle.start_service(self.service_binding,self.campaign,env={},startup_seconds=1)
        socket_mock.return_value.__enter__.return_value.bind.assert_called_once_with(('127.0.0.1',5002))
        cleanup.assert_called_once_with(handle,timeout_seconds=20)

    def test_service_request_has_no_proxy_or_redirect_and_fixed_scope(self):
        from unittest.mock import Mock
        response=Mock();response.read.return_value=b'{"status":"ok"}'
        opener=MagicMock();opener.open.return_value.__enter__.return_value=response
        with patch.object(lifecycle,'verify_service'),patch.object(lifecycle,'build_opener',return_value=opener) as build:
            self.assertEqual(lifecycle._request(object(),'/health',timeout=2),{'status':'ok'})
        self.assertEqual(build.call_args.args[0].proxies,{})
        self.assertIsInstance(build.call_args.args[1],lifecycle._NoRedirect)
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:5002/health');self.assertEqual(request.get_method(),'GET')
        with self.assertRaisesRegex(ValueError,'service_redirect_forbidden'):lifecycle._NoRedirect().redirect_request()
        with patch.object(lifecycle,'verify_service'),patch.object(lifecycle,'build_opener') as build:
            with self.assertRaisesRegex(ValueError,'unexpected_service_operation'):lifecycle._request(object(),'/arbitrary')
        build.assert_not_called()

    def test_private_paths_reject_symlink_even_within_artifacts(self):
        target=self.campaign/'target';target.mkdir();alias=self.campaign/'alias';alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError,'private_path_escape'): lifecycle.private_path(alias/'x')
        with self.assertRaisesRegex(ValueError,'private_path_escape'): lifecycle.private_path(self.root/'outside')

    def test_import_probe_configuration_isolation_without_native_import(self):
        expected=json.dumps(self.service_binding['configuration']).encode()
        with patch.object(lifecycle.subprocess,'check_output',return_value=expected) as probe:
            result=lifecycle.validate_installation(worktree=self.root,env={'PRIVATE_EXAMPLE':'not-stored'})
        self.assertEqual(result,self.service_binding)
        self.assertNotIn('PRIVATE_EXAMPLE',json.dumps(result));self.assertEqual(probe.call_args.kwargs['timeout'],20)
        bad=dict(self.service_binding['configuration'],uploads='/other/installation')
        with patch.object(lifecycle.subprocess,'check_output',return_value=json.dumps(bad).encode()):
            with self.assertRaisesRegex(ValueError,'native_mutable_state'):lifecycle.validate_installation(worktree=self.root,env={})

    def test_canonical_world_launch_and_no_rerun(self):
        with patch.object(lifecycle,'_spawn',return_value='fixture') as spawn:
            self.assertEqual(lifecycle.spawn_world(run_dir=self.run,receipt_dir=self.world,env={}), 'fixture')
        command=spawn.call_args.args[0]
        self.assertEqual(command[1:4],['-u','-m','lifespan.evaluation.runner'])
        lifecycle.save(self.run/'INFLIGHT.json',{})
        with self.assertRaisesRegex(ValueError,'world_not_pristine'):lifecycle.spawn_world(run_dir=self.run,receipt_dir=self.world,env={})

    def test_scoped_socket_removal_does_not_touch_other_control(self):
        self.complete();self.alias.mkdir();(self.alias/'control').symlink_to(self.control)
        with socket.socket(socket.AF_UNIX) as sock: sock.bind(str(self.alias/'control/command.sock'))
        result=lifecycle._remove_sockets(self.world_observation['native_instances'])
        self.assertTrue(result[0]['alias_absent']);self.assertTrue(result[0]['underlying_socket_absent'])
        self.alias.mkdir();other=self.run/'other-control';other.mkdir();(self.alias/'control').symlink_to(other)
        result=lifecycle._remove_sockets(self.world_observation['native_instances'])
        self.assertFalse(result[0]['alias_absent']);self.assertTrue((self.alias/'control').is_symlink())


class LocalProcesses(unittest.TestCase):
    setUp = LifecycleFixtures.setUp
    def spawn_sleep(self):
        # Private internal launch seam is used only for a harmless offline process.
        return lifecycle._spawn([sys.executable,'-c','import time;time.sleep(30)'],self.root,os.environ.copy(),
                                 self.campaign/'local-process','SERVICE',{})

    def test_local_owned_process_cleanup_preserves_unrelated_process(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        handle=self.spawn_sleep()
        try:
            receipt=lifecycle.cleanup_service(handle,timeout_seconds=5)
            self.assertEqual(receipt['status'],'confirmed',receipt)
            self.assertIsNone(unrelated.poll())
            self.assertTrue(receipt['processes']['signals'])
            self.assertEqual({row['identity']['pid'] for row in receipt['processes']['signals']},{handle.process.pid})
        finally:
            if handle.poll() is None: handle.process.kill()
            handle.process.wait(timeout=3);unrelated.kill();unrelated.wait(timeout=3)

    def test_reused_pid_is_never_signaled(self):
        old=process(777); replacement=dict(old,start_ticks=old['start_ticks']+1)
        handle=lifecycle.Handle(None,self.world,'WORLD',self.root,time.monotonic(),old,{},known={777:old})
        with patch.object(lifecycle,'identity',return_value=replacement),patch.object(lifecycle,'discover_owned'),\
             patch.object(lifecycle.os,'kill') as kill,patch.object(handle,'poll',return_value=0):
            # _stop_known polls process directly, so use a minimal fixture handle.
            from unittest.mock import Mock
            handle.process=Mock();handle.process.poll.return_value=0
            result=lifecycle._stop_known(handle,time.monotonic()+.1)
        kill.assert_not_called();self.assertEqual(result['observations_after'][0]['state'],'identity_replaced')

    def test_detached_local_descendant_is_retained_and_stopped(self):
        from unittest.mock import Mock
        command=[sys.executable,'-c',"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True);time.sleep(30)"]
        handle=lifecycle._spawn(command,self.root,os.environ.copy(),self.campaign/'detached','SERVICE',{})
        try:
            deadline=time.monotonic()+3
            while len(handle.known)<2 and time.monotonic()<deadline:
                lifecycle.discover_owned(handle.known);time.sleep(.02)
            self.assertEqual(len(handle.known),2)
            child=next(row for pid,row in handle.known.items() if pid!=handle.process.pid)
            self.assertEqual(child['sid'],child['pid'])
            receipt=lifecycle.cleanup_service(handle,timeout_seconds=5)
            self.assertEqual(receipt['status'],'confirmed',receipt)
            self.assertEqual(len(receipt['processes']['observations_after']),2)
        finally:
            if handle.poll() is None:handle.process.kill()
            handle.process.wait(timeout=3)
            # Owned child only; never infer a PID from an arbitrary artifact.
            for item in handle.known.values():
                if lifecycle.process_observation(item)['state']=='same_alive' and lifecycle.same_identity(item,lifecycle.identity(item['pid'])):
                    os.kill(item['pid'],signal.SIGKILL)

    def test_world_observation_failure_still_stops_owned_root(self):
        handle=lifecycle._spawn([sys.executable,'-c','import time;time.sleep(30)'],self.root,os.environ.copy(),
                               self.world,'WORLD',dict(run_directory=str(self.run)))
        try:
            with patch.object(lifecycle,'observe_world',side_effect=ValueError('offline_failure')):
                receipt=lifecycle.cleanup_world(handle,self.run,None,timeout_seconds=5)
            self.assertEqual(receipt['status'],'unconfirmed')
            self.assertIsNotNone(handle.poll())
            self.assertEqual(receipt['failures'][0]['stage'],'observe')
            self.assertTrue(receipt['processes']['observations_after'])
        finally:
            if handle.poll() is None:handle.process.kill()
            handle.process.wait(timeout=3)

    def test_unbound_native_startup_never_confirms_cleanup(self):
        handle=lifecycle._spawn([sys.executable,'-c','import time;time.sleep(30)'],self.root,os.environ.copy(),
                               self.world,'WORLD',dict(run_directory=str(self.run)))
        path=self.run/'work/fixture/computers/employee/hermes/config.yaml';path.parent.mkdir(parents=True);path.write_text('# offline')
        try:
            receipt=lifecycle.cleanup_world(handle,self.run,None,timeout_seconds=5)
            self.assertEqual(receipt['status'],'unconfirmed')
            self.assertIn('UnboundNativeInstance',{row['error_type'] for row in receipt['failures']})
            self.assertIsNotNone(handle.poll())
        finally:
            if handle.poll() is None:handle.process.kill()
            handle.process.wait(timeout=3)

    def test_worker_thread_cleanup_leaves_parent_signal_handlers_alone(self):
        from concurrent.futures import ThreadPoolExecutor
        def cleanup():
            with lifecycle.cleanup_scope(): return 'bounded-cleanup'
        with patch.object(lifecycle.signal,'signal',side_effect=AssertionError('worker changed parent handler')):
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(cleanup).result(timeout=2),'bounded-cleanup')

    def test_concurrent_service_observations_are_serialized(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import Mock
        handle=lifecycle.Handle(Mock(),self.campaign,'SERVICE',self.backend,1,self.service_identity,{})
        lifecycle.save(self.campaign/'SERVICE_START.json',{})
        active=0;peak=0
        def socket_check(_):
            nonlocal active,peak
            active+=1;peak=max(peak,active);time.sleep(.01);active-=1
            return dict(address='127.0.0.1',port=5002,inode='123',owner_identity=self.service_identity)
        with patch.object(lifecycle,'socket_owned',side_effect=socket_check),patch.object(lifecycle,'discover_owned'):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:lifecycle.verify_service(handle),range(8)))
        self.assertEqual(peak,1);self.assertEqual(len(results),8)
        self.assertEqual(lifecycle.read(self.campaign/'SERVICE_OBSERVATION.json')[0],max(results,key=lambda item:item['observed_monotonic']))

    def test_pidfd_checks_identity_after_open_before_signal(self):
        old=process(777);replacement=dict(old,start_ticks=old['start_ticks']+1)
        with patch.object(lifecycle.os,'pidfd_open',return_value=123),patch.object(lifecycle.os,'close') as close,\
             patch.object(lifecycle,'identity',return_value=replacement),patch.object(lifecycle.signal,'pidfd_send_signal') as send:
            self.assertFalse(lifecycle._signal_owned(old,'TERM'))
        send.assert_not_called();close.assert_called_once_with(123)

    def test_start_receipt_failure_does_not_lose_owned_child(self):
        native_save=lifecycle.save; captured=[]
        def fail_start(path,value,**kwargs):
            if Path(path).name=='SERVICE_START.json':
                captured.append(value['root_identity']);raise OSError('offline disk failure')
            return native_save(path,value,**kwargs)
        with patch.object(lifecycle,'save',side_effect=fail_start):
            with self.assertRaises(OSError):self.spawn_sleep()
        self.assertEqual(len(captured),1)
        self.assertIn(lifecycle.process_observation(captured[0])['state'],('absent','zombie','identity_replaced'))

    def test_world_cleanup_thread_owns_its_process(self):
        from concurrent.futures import ThreadPoolExecutor
        handle=lifecycle._spawn([sys.executable,'-c','import time;time.sleep(30)'],self.root,os.environ.copy(),
                               self.world,'WORLD',dict(run_directory=str(self.run)))
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                receipt=pool.submit(lifecycle.cleanup_world,handle,self.run,None,timeout_seconds=5).result(timeout=7)
            self.assertEqual(receipt['status'],'confirmed',receipt)
            self.assertIsNotNone(handle.poll())
        finally:
            if handle.poll() is None:handle.process.kill()
            handle.process.wait(timeout=3)

    def test_cleanup_signal_handlers_restored(self):
        old={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
        with lifecycle.cleanup_scope():
            for sig in old:signal.getsignal(sig)(sig,None)
        self.assertEqual({sig:signal.getsignal(sig) for sig in old},old)


if __name__=='__main__':unittest.main()
