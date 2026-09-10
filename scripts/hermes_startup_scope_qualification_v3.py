#!/usr/bin/env python3
"""Scope qualification v3: caller security context, fixed startup-only slots.

No native execution occurs during import/prepare/audit. execute requires a new
published manifest hash. All observations remain private until a separate review.
No service MainPID, RemainAfterExit, or post-collection default can certify a scope.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from scripts import hermes_startup_qualification as legacy
from scripts import hermes_startup_probe as child

ROOT=Path(__file__).resolve().parents[1]
VERSION='hermes-startup-scope-qualification-v3'
BATCHES=(1,1,1,2,2,2)
CONFIG={**legacy.CONFIG,'ownership':'caller_exec_scope_with_held_controller',
        'resource_gate':'per_slot_live_scope_kernel_namespace_readbacks',
        'invocation_environment_authority':'inherited_scope_id_matches_parent_verified_readback'}
PROPERTIES=('MemoryMax=4G','MemorySwapMax=0','TasksMax=128','CPUQuota=200%',
            'CPUQuotaPeriodSec=100ms','RuntimeMaxSec=180','TimeoutStopSec=5','KillMode=control-group','Delegate=no')
SHOW_KEYS=('Id','LoadState','ActiveState','SubState','ControlGroup','InvocationID','Result',
           'RuntimeMaxUSec','TimeoutStopUSec','KillMode','Delegate')
ENV_KEYS=legacy.ENV_KEYS
CGROUP_ROOT=Path('/sys/fs/cgroup')
require,canonical,sha,load,save=legacy.require,legacy.canonical,legacy.sha,legacy.load,legacy.save
finite,boot,same=legacy.finite,legacy.boot,legacy.same
interpreter,binary=legacy.interpreter,legacy.binary
controller_environment,controller_import_paths=legacy.controller_environment,legacy.controller_import_paths
dependencies,committed=legacy.dependencies,legacy.committed
expected_native_commands=legacy.expected_native_commands
_capture_native,_socket_inventory,_clean_sockets=legacy._capture_native,legacy._socket_inventory,legacy._clean_sockets
interrupt_scope=legacy.interrupt_scope
BOOTSTRAP=legacy.BOOTSTRAP.replace('scripts.hermes_startup_qualification import _worker',
                                  'scripts.hermes_startup_scope_qualification_v3 import _worker')
BOOTSTRAP=BOOTSTRAP.replace("invocation=os.environ.get('INVOCATION_ID')", """
if set(os.environ)!=set(allowed)|{'INVOCATION_ID'} or any(os.environ.get(k)!=v for k,v in allowed.items()):
    raise ValueError('controller_environment_not_scrubbed')
invocation=os.environ['INVOCATION_ID']
if type(invocation) is not str or len(invocation)!=32 or any(c not in '0123456789abcdef' for c in invocation):
    raise ValueError('invalid_inherited_scope_invocation')
""")


def security_context(pid):
    return (Path('/proc')/str(pid)/'attr/current').read_text().strip()


def identity(pid):
    value=legacy.identity(pid)
    if value is not None:value['security_context']=security_context(pid)
    return value


def checked_unit(name):
    require(type(name) is str and re.fullmatch(child.UNIT_PREFIX+r'[0-9a-f]{32}\.scope',name),
            'invalid_owned_scope_name')
    return name


def native_argv(directory,slot):
    return [interpreter(),'-I','-S','-u','-c',BOOTSTRAP,str(ROOT),str(directory),slot['slot_id']]


def launch_argv(directory,slot):
    return [binary('systemd-run'),'--user','--scope','--quiet','--unit='+checked_unit(slot['unit']),
            *['--property='+p for p in PROPERTIES],binary('unshare'),'--user','--map-current-user','--net',
            *native_argv(directory,slot)]


def sources():
    return {**legacy.sources(),'scripts/hermes_startup_scope_qualification_v3.py':sha(Path(__file__).read_bytes())}


def show(name, timeout=2):
    checked_unit(name)
    result = subprocess.run([binary('systemctl'), '--user', 'show', name,
        *['--property=' + key for key in SHOW_KEYS]], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=max(.01, timeout), check=False)
    require(len(result.stdout) <= 32768, 'unit_observation_too_large')
    values = {}
    for line in result.stdout.decode().splitlines():
        key, sep, value = line.partition('=')
        require(sep and key in SHOW_KEYS and key not in values, 'invalid_unit_observation')
        values[key] = value
    require(set(values) == set(SHOW_KEYS) and values['Id'] == name and
            (result.returncode == 0 or values['LoadState'] == 'not-found'), 'unit_observation_failed')
    return values

def group_path(name, group, uid):
    checked_unit(name)
    require(type(group) is str and group.startswith(f'/user.slice/user-{uid}.slice/user@{uid}.service/')
            and '..' not in Path(group).parts and Path(group).name == name, 'foreign_unit_cgroup')
    base = CGROUP_ROOT / group.lstrip('/')
    require(base.resolve().is_relative_to(CGROUP_ROOT.resolve()), 'cgroup_path_escape')
    return base

def kernel(name, group, uid):
    base = group_path(name, group, uid)
    return {key: (base / key).read_text().strip() for key in child.KERNEL_LIMITS}

def members(name, group, uid):
    """Only the positively bound unit subtree, including detached descendants."""
    base = group_path(name, group, uid)
    if not base.exists():
        return []
    ids = set()
    files = [base / 'cgroup.procs'] + list(base.glob('**/cgroup.procs'))
    require(len(files) <= 512, 'cgroup_inventory_too_large')
    for path in files:
        require(not path.is_symlink() and path.resolve().is_relative_to(base.resolve()), 'cgroup_inventory_escape')
        try:
            ids.update(int(value) for value in path.read_text().split())
        except FileNotFoundError:
            continue
    require(len(ids) <= 512 and all(value > 0 for value in ids), 'invalid_cgroup_members')
    return sorted(ids)


def validate_scope(slot, observed, proc, hello, launch, supervisor, *, directory, kernel_values):
    require(same(proc,hello) and same(proc,launch), 'scope_exec_identity_mismatch')
    require(proc['ppid']==supervisor['pid'] and proc['uid']==supervisor['uid']
        and proc['boot_id']==supervisor['boot_id'] and proc['start_ticks']>=supervisor['start_ticks']
        and proc['cwd']==str(ROOT) and proc['argv_sha256']==sha(canonical(native_argv(directory,slot)))
        and proc['state'] not in ('Z','X') and proc['security_context']==supervisor['security_context'],
        'scope_exec_configuration_mismatch')
    require(observed['Id']==slot['unit'] and observed['LoadState']=='loaded'
        and observed['ActiveState']=='active' and observed['SubState']=='running'
        and observed['ControlGroup']==proc['cgroup']
        and re.fullmatch('[0-9a-f]{32}',observed['InvocationID']), 'scope_live_binding_mismatch')
    group_path(slot['unit'],proc['cgroup'],proc['uid'])
    require(observed['RuntimeMaxUSec']=='3min' and observed['TimeoutStopUSec']=='5s'
        and observed['KillMode']=='control-group' and observed['Delegate']=='no', 'scope_lifecycle_properties_mismatch')
    require(kernel_values==child.KERNEL_LIMITS, 'scope_kernel_limits_mismatch')
    require(proc['net_namespace']!=supervisor['net_namespace']
        and proc['user_namespace']!=supervisor['user_namespace'], 'scope_namespace_not_separate')
    return {'verified':True,'invocation_id':observed['InvocationID'],'cgroup':proc['cgroup'],
            'main_identity':proc,'kernel':kernel_values,'identity_role':'held_scope_controller'}


def verify_boundary(expected,current):
    checked_unit(expected['unit'])
    require(type(expected['uid']) is int and expected['uid']>0 and
            re.fullmatch('[0-9a-f]{32}',expected['invocation_id']), 'invalid_expected_boundary')
    require(current['uid']==expected['uid'] and current['boot_id']==expected['boot_id'], 'boundary_user_or_boot_changed')
    for key,prefix in (('net_namespace','net'),('user_namespace','user')):
        require(re.fullmatch(prefix+r':\[[0-9]+\]',current[key])
            and re.fullmatch(prefix+r':\[[0-9]+\]',expected['host_'+key])
            and current[key]!=expected['host_'+key], 'boundary_namespace_not_isolated')
    require(current['interfaces']==[{'name':'lo','up':False}], 'network_interface_not_isolated')
    group_path(expected['unit'],current['cgroup'],expected['uid'])
    require(current['invocation_id']==expected['invocation_id'] and current['kernel']==child.KERNEL_LIMITS,
            'boundary_scope_or_kernel_mismatch')
    return {'verified':True,'provider_network':'separate_namespace_disabled_loopback_only',
        'invocation_id_authority':'parent_verified_live_scope','kernel':dict(child.KERNEL_LIMITS),
        'io_isolation_qualified':False}


def prepare(out, *, model=None, provider_profile=None):
    require((model is None) == (provider_profile is None), 'startup_model_and_profile_required_together')
    configuration = None if model is None else {'model': model, 'provider_profile': provider_profile}
    execution, _ = child.startup_settings(configuration)
    directory=Path(out).absolute()
    require(directory.parent.is_dir() and directory.parent.resolve()==directory.parent
        and not directory.exists() and not directory.is_symlink(),'fresh_real_output_required')
    source_map=sources()
    revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True,timeout=10).strip()
    committed(source_map,revision)
    slots=[]
    for batch,size in enumerate(BATCHES):
        for _ in range(size):
            i=len(slots);slots.append({'index':i,'slot_id':f'start-{i:02d}','batch':batch,
                'unit':child.UNIT_PREFIX+uuid.uuid4().hex+'.scope'})
    manifest={'schema_version':3,'kind':VERSION,'config':CONFIG,'slots':slots,
        'source_sha256':source_map,'repository_commit':revision,'dependencies':dependencies(),
        'boot_id':boot(),'uid':os.getuid(),'caller_security_context':security_context(os.getpid()),'root':str(directory),'working_directory':str(ROOT),
        'python':interpreter(),'controller_environment':controller_environment(),
        'controller_import_paths':controller_import_paths(),'child_execution':execution,
        'created_at':datetime.now(timezone.utc).isoformat()}
    if configuration is not None: manifest['startup_configuration'] = configuration
    directory.mkdir(mode=0o700);(directory/'slots').mkdir(mode=0o700)
    save(directory/'manifest.json',manifest)
    return {'prepared':True,'manifest_sha256':load(directory/'manifest.json')[1],'slots':9}


def validate_manifest(directory,expected_hash,*,current=True):
    manifest,actual=load(directory/'manifest.json')
    require(actual==expected_hash and re.fullmatch('[0-9a-f]{64}',expected_hash or ''),'registered_manifest_mismatch')
    configuration = manifest.get('startup_configuration')
    require('startup_configuration' not in manifest or type(configuration) is dict,
            'invalid_startup_configuration')
    execution, _ = child.startup_settings(configuration)
    require(manifest['schema_version']==3 and manifest['kind']==VERSION
        and canonical(manifest['config'])==canonical(CONFIG)
        and canonical(manifest['child_execution'])==canonical(execution),'qualification_contract_mismatch')
    require(manifest['root']==str(directory) and manifest['working_directory']==str(ROOT)
        and manifest['python']==interpreter(),'execution_location_mismatch')
    require(type(manifest['controller_environment']) is dict
        and set(manifest['controller_environment'])==set(ENV_KEYS)
        and all(type(v)is str for v in manifest['controller_environment'].values())
        and type(manifest['controller_import_paths']) is list
        and all(type(p)is str and Path(p).is_absolute() and Path(p).is_dir()
                for p in manifest['controller_import_paths']),'bootstrap_contract_mismatch')
    slots=manifest['slots'];batches=[b for b,n in enumerate(BATCHES) for _ in range(n)]
    require(type(slots)is list and len(slots)==9,'nine_fixed_slots_required')
    for index,slot in enumerate(slots):
        require(set(slot)=={'index','slot_id','batch','unit'} and type(slot['index'])is int
            and slot['index']==index and slot['slot_id']==f'start-{index:02d}'
            and type(slot['batch'])is int and slot['batch']==batches[index],'slot_schedule_mismatch')
        checked_unit(slot['unit'])
    require(len({s['unit'] for s in slots})==9,'unit_reuse_forbidden')
    require(manifest['source_sha256']==sources(),'execution_source_changed')
    committed(manifest['source_sha256'],manifest['repository_commit'])
    if current:
        require(manifest['boot_id']==boot() and manifest['uid']==os.getuid()
            and manifest['caller_security_context']==security_context(os.getpid()),'boot_user_or_security_context_changed')
        require(manifest['dependencies']==dependencies(),'dependency_changed')
        require(manifest['controller_environment']==controller_environment()
            and manifest['controller_import_paths']==controller_import_paths(),'bootstrap_environment_changed')
    return manifest


def _wait_file(path,deadline):
    while not path.exists():
        require(time.monotonic()<deadline,'private_gate_deadline_exhausted')
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
    require(time.monotonic()<deadline,'private_gate_arrived_late')
    return load(path)[0]


def _native_startup(trial,expected,deadline,manifest_hash,slot_id, *, startup_configuration=None):
    """Actual native Computer.start/close, no Computer.run and fixed dummy endpoint."""
    execution, credentials = child.startup_settings(startup_configuration)
    before=child.observe_boundary();verification=verify_boundary(expected,before)
    entered=time.monotonic();require(entered<deadline,'native_startup_deadline_exhausted')
    native=trial/'native';native.mkdir(mode=0o700)
    save(native/'BOUNDARY_BEFORE.json',{'expected':expected,'observed':before,'verification':verification})
    from lifespan.computers import Computer
    from lifespan.evaluation.runtime import install_skill
    from lifespan.evaluation.protocol import SEED_SKILL
    from lifespan.evaluation.hermes_transport import contract
    computer=Computer(native/'computers','startup-qualification',backend='bubblewrap',execution=execution)
    skill=install_skill(computer.profile,SEED_SKILL)
    save(native/'STARTUP_INTENT.json',{'kind':VERSION,'execution':execution,'skill':skill,
        'helper_sha256':sha(Path(__file__).read_bytes()),'work_requests_sent':0})
    ready=None;error=None;close_error=None;pre_close_error=None
    try:
        require(not any((computer.profile/n).exists() or (computer.profile/n).is_symlink()
                        for n in ('.env','.op.env')),'profile_environment_file_present')
        remaining=deadline-time.monotonic();require(remaining>0,'native_startup_deadline_exhausted')
        ready=computer.start(credentials,timeout=min(150,remaining))
        require(ready['kind']=='ready' and ready['backend']=='bubblewrap'
            and ready['evaluation_transport']==contract('nonstreaming')
            and not {'memory','skill_manage'} & set(ready['tool_names']),'native_ready_contract_mismatch')
        require(canonical(ready.get('provider_contract')) == canonical(execution.get('provider_contract')),
                'native_provider_contract_mismatch')
        require(time.monotonic()<=deadline,'late_native_ready')
    except Exception as exc:error=type(exc).__name__
    finally:
        finish=time.monotonic();close_deadline=min(finish+30,deadline+30)
        save(native/'STARTUP_FINISHED.json',{'entered_monotonic':entered,'startup_deadline':deadline,
            'finished_monotonic':finish,'startup_elapsed_seconds':finish-entered,
            'ready_observed':ready is not None and error is None,'error_type':error})
        save(native/'CLOSE_STARTED.json',{'started_monotonic':finish,'cleanup_deadline':close_deadline})
        if ready is not None and error is None:
            try:
                gate=_wait_file(trial/'CLOSE_GATE.json',close_deadline)
                require(gate['slot_id']==slot_id and gate['manifest_sha256']==manifest_hash
                    and gate['cleanup_deadline_monotonic']==close_deadline,'close_gate_binding_mismatch')
                require(all(same(item,identity(item['pid'])) for item in gate['native_identities'].values()),
                    'native_identity_changed_before_close')
            except Exception as exc:pre_close_error=type(exc).__name__
        try:computer.close()
        except Exception as exc:close_error=type(exc).__name__
        close_finish=time.monotonic()
    after=child.observe_boundary();after_verification=verify_boundary(expected,after)
    save(native/'BOUNDARY_AFTER.json',{'observed':after,'verification':after_verification})
    result={'ready_observed':ready is not None and error is None,'error_type':error,
        'close_error_type':close_error,'pre_close_error_type':pre_close_error,
        'entered_monotonic':entered,'startup_deadline':deadline,'startup_finished_monotonic':finish,
        'cleanup_deadline':close_deadline,'close_finished_monotonic':close_finish,
        'close_returned_within_allowance':close_error is None and close_finish<=close_deadline,
        'work_requests_sent':0,'provider_credentials_supplied':False,
        'boundary_verified_before_and_after':True,'independent_cleanup_confirmed':False}
    save(native/'CHILD_RESULT.json',result)
    return result


def validate_worker_environment(manifest,gate,environ):
    """Permit only the scrubbed keys plus systemd's independently verified ID.

    The inherited ID is never synthesized or overwritten. No arbitrary inherited
    variable, absent ID, or ID from a different scope reaches native startup.
    """
    require(set(environ)==set(ENV_KEYS)|{'INVOCATION_ID'}
        and {k:environ.get(k) for k in ENV_KEYS}==manifest['controller_environment'],
        'controller_environment_not_scrubbed')
    inherited=environ['INVOCATION_ID']
    require(type(inherited)is str and re.fullmatch('[0-9a-f]{32}',inherited)
        and inherited==gate['unit_binding']['invocation_id'],
        'inherited_scope_invocation_mismatch')


def _worker(directory,slot_id):
    raw,manifest_hash=load(directory/'manifest.json');execution,_=load(directory/'EXECUTION.json')
    require(execution['registered_manifest_sha256']==manifest_hash,'worker_manifest_not_registered')
    manifest=validate_manifest(directory,manifest_hash,current=False)
    require(manifest['uid']==os.getuid() and manifest['boot_id']==boot(),'worker_boot_or_user_changed')
    slot=next(s for s in manifest['slots'] if s['slot_id']==slot_id);trial=directory/'slots'/slot_id
    intent,_=load(trial/'INTENT.json');deadline=intent['startup_deadline_monotonic']
    require(finite(deadline) and time.monotonic()<deadline,'worker_start_deadline_exhausted')
    save(trial/'HELLO.json',{'slot_id':slot_id,'manifest_sha256':manifest_hash,
         'identity':identity(os.getpid()),'observed_monotonic':time.monotonic()})
    gate=_wait_file(trial/'GATE.json',deadline)
    require(gate['slot_id']==slot_id and gate['manifest_sha256']==manifest_hash
        and gate['startup_deadline_monotonic']==deadline
        and same(gate['unit_binding']['main_identity'],identity(os.getpid())),'worker_gate_identity_mismatch')
    require(manifest['source_sha256']==sources() and manifest['dependencies']==dependencies(),
            'post_gate_source_or_dependency_changed')
    validate_worker_environment(manifest,gate,os.environ)
    options = {'startup_configuration': manifest['startup_configuration']} if 'startup_configuration' in manifest else {}
    result=_native_startup(trial,gate['expected_boundary'],deadline,manifest_hash,slot_id, **options)
    release=_wait_file(trial/'RELEASE.json',result['cleanup_deadline'])
    require(release['slot_id']==slot_id and release['manifest_sha256']==manifest_hash
        and same(release['controller_identity'],identity(os.getpid())),'controller_release_mismatch')
    save(trial/'CONTROLLER_EXIT.json',{'slot_id':slot_id,'manifest_sha256':manifest_hash,
        'identity':identity(os.getpid()),'release_sha256':load(trial/'RELEASE.json')[1],
        'observed_monotonic':time.monotonic(),'normal_release':True})


def _collect(slot,binding,known,uid):
    current=members(slot['unit'],binding['cgroup'],uid)
    for pid in current:
        proc=identity(pid)
        if proc is not None:
            require(proc['uid']==uid and proc['boot_id']==binding['main_identity']['boot_id']
                and (proc['cgroup']==binding['cgroup'] or proc['cgroup'].startswith(binding['cgroup']+'/')),'foreign_scope_member')
            known[(proc['pid'],proc['start_ticks'])]=proc
    return current


def _cleanup_binding(slot,launch,proc,observed,supervisor):
    """Ownership-only fallback, never qualification or namespace certification."""
    require(same(launch,proc) and proc['ppid']==supervisor['pid']
        and proc['uid']==supervisor['uid'] and proc['boot_id']==supervisor['boot_id']
        and proc['start_ticks']>=supervisor['start_ticks'],'cleanup_launch_identity_mismatch')
    require(observed['Id']==slot['unit'] and observed['LoadState']=='loaded'
        and re.fullmatch('[0-9a-f]{32}',observed['InvocationID'])
        and observed['ControlGroup']==proc['cgroup'],'cleanup_scope_binding_mismatch')
    group_path(slot['unit'],proc['cgroup'],proc['uid'])
    return {'verified':False,'ownership_only':True,'invocation_id':observed['InvocationID'],
        'cgroup':proc['cgroup'],'main_identity':proc,'identity_role':'owned_exec_before_hello'}


def _stop_owned(slot,binding,deadline):
    observed=show(slot['unit'],timeout=min(2,max(.01,deadline-time.monotonic())))
    if observed['LoadState']=='not-found':return {'requested':False,'already_absent':True}
    require(binding is not None and observed['InvocationID']==binding['invocation_id']
        and observed['ControlGroup'] in ('',binding['cgroup']),'refuse_unbound_scope_stop')
    require(time.monotonic()<deadline,'scope_cleanup_time_exhausted')
    value=subprocess.run([binary('systemctl'),'--user','stop',slot['unit']],stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=min(7,max(.01,deadline-time.monotonic())))
    return {'requested':True,'returncode':value.returncode}


def _cleanup(slot,binding,known,process,trial,started,deadline,*,released):
    errors=[];stop=None;unit=None;remaining=None;sockets={'confirmed':False};exit_code=None
    if not released:
        try:stop=_stop_owned(slot,binding,deadline)
        except Exception as exc:errors.append(type(exc).__name__)
    if process is not None:
        try:exit_code=process.wait(timeout=max(.01,min(7,deadline-time.monotonic())))
        except subprocess.TimeoutExpired:errors.append('ControllerExitUnknown')
    while time.monotonic()<deadline:
        try:
            unit=show(slot['unit'],timeout=min(2,max(.01,deadline-time.monotonic())))
            remaining=members(slot['unit'],binding['cgroup'],os.getuid()) if binding else None
            if remaining==[] and (unit['LoadState']=='not-found' or unit['ActiveState'] in ('inactive','failed')):break
        except Exception as exc:errors.append(type(exc).__name__);break
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
    observations=[]
    for item in known.values():
        try:
            now=identity(item['pid'])
            state='absent' if now is None else 'replaced' if not same(item,now) else 'zombie' if now['state']=='Z' else 'alive'
        except Exception:state='unknown'
        observations.append({'identity':item,'state':state})
    terminal=bool(binding and unit and remaining==[] and
        (unit['LoadState']=='not-found' and not unit['InvocationID'] and not unit['ControlGroup'] or
         unit['LoadState']=='loaded' and unit['InvocationID']==binding['invocation_id']
         and unit['ActiveState'] in ('inactive','failed')))
    clear=bool(binding) and all(o['state'] in ('absent','replaced','zombie') for o in observations)
    if terminal and clear and not errors:
        try:sockets=_clean_sockets(trial)
        except Exception as exc:errors.append(type(exc).__name__)
    ended=time.monotonic()
    return {'started_monotonic':started,'ended_monotonic':ended,'deadline_monotonic':deadline,
        'limit_seconds':30,'scope_stop':stop,'scope_final':unit,'members_remaining':remaining,
        'observed_processes':observations,'socket_cleanup':sockets,'controller_exit_code':exit_code,
        'released':released,'errors':errors,'confirmed':bool(terminal and clear and sockets['confirmed']
            and exit_code is not None and ended<=deadline and not errors)}


def _inventory(trial):
    result={}
    for path in sorted(trial.rglob('*')):
        require(not path.is_symlink(),'symlink_evidence')
        if path.is_file() and path.suffix in ('.json','.jsonl') and path.name!='RECEIPT.json':
            result[str(path.relative_to(trial))]=sha(path.read_bytes())
    return result


def _run_slot(directory,manifest,slot,stop_event):
    trial=directory/'slots'/slot['slot_id'];trial.mkdir(mode=0o700)
    started=time.monotonic();deadline=started+150;manifest_hash=load(directory/'manifest.json')[1]
    execution,_=load(directory/'EXECUTION.json');supervisor=execution['supervisor']
    intent={'slot_id':slot['slot_id'],'unit':slot['unit'],'started_monotonic':started,
        'startup_deadline_monotonic':deadline,'manifest_sha256':manifest_hash,
        'command_sha256':sha(canonical(launch_argv(directory,slot)))}
    save(trial/'INTENT.json',intent)
    process=None;launch=None;binding=None;known={};errors=[];outcome=None;startup_end=None
    status='infrastructure_failed';released=False;gate=None;native_result=None
    log=(trial/'controller.log').open('xb')
    try:
        require(show(slot['unit'])['LoadState']=='not-found','scope_name_already_exists')
        require(not stop_event.is_set() and time.monotonic()<deadline,'dispatch_deadline_or_interrupt')
        process=subprocess.Popen(launch_argv(directory,slot),cwd=ROOT,env=manifest['controller_environment'],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        launch=identity(process.pid);require(launch is not None,'scope_launch_identity_unavailable')
        known[(launch['pid'],launch['start_ticks'])]=launch
        save(trial/'LAUNCH.json',{'identity':launch,'observed_monotonic':time.monotonic()})
        while time.monotonic()<deadline and not stop_event.is_set():
            if (trial/'HELLO.json').exists():
                hello,_=load(trial/'HELLO.json')
                require(hello['slot_id']==slot['slot_id'] and hello['manifest_sha256']==manifest_hash,'hello_binding_mismatch')
                unit=show(slot['unit']);proc=identity(process.pid)
                binding=validate_scope(slot,unit,proc,hello['identity'],launch,supervisor,directory=directory,
                    kernel_values=kernel(slot['unit'],unit['ControlGroup'],manifest['uid']))
                known[(proc['pid'],proc['start_ticks'])]=proc
                gate={'slot_id':slot['slot_id'],'manifest_sha256':manifest_hash,'startup_deadline_monotonic':deadline,
                    'unit_binding':binding,'unit_observation':unit,'observed_monotonic':time.monotonic(),'expected_boundary':{'uid':manifest['uid'],
                    'boot_id':manifest['boot_id'],'host_net_namespace':supervisor['net_namespace'],
                    'host_user_namespace':supervisor['user_namespace'],'unit':slot['unit'],'invocation_id':binding['invocation_id']}}
                require(time.monotonic()<deadline,'gate_deadline_exhausted');save(trial/'GATE.json',gate);break
            require(process.poll() is None,'controller_exited_before_hello');time.sleep(.05)
        require(binding is not None,'scope_not_bound')
        while not stop_event.is_set():
            _collect(slot,binding,known,manifest['uid'])
            if (trial/'native/STARTUP_FINISHED.json').exists():
                candidate_outcome,_=load(trial/'native/STARTUP_FINISHED.json');candidate_end=candidate_outcome['finished_monotonic']
                require(finite(candidate_end) and started<=candidate_end<=deadline,'startup_deadline_exceeded')
                startup_end=candidate_end;outcome=candidate_outcome
                status='ready' if outcome['ready_observed'] is True else 'startup_failed'
                if status=='ready':
                    native=_capture_native(trial,binding,manifest)
                    known.update({(i['pid'],i['start_ticks']):i for i in native['identities'].values()})
                    save(trial/'NATIVE_IDENTITIES.json',native)
                    save(trial/'CLOSE_GATE.json',{'slot_id':slot['slot_id'],'manifest_sha256':manifest_hash,
                        'cleanup_deadline_monotonic':startup_end+30,'native_identities':native['identities']})
                break
            if time.monotonic()>=deadline:status='startup_timed_out';break
            require(process.poll() is None,'controller_exited_before_native_result');time.sleep(.05)
        if stop_event.is_set():status='interrupted'
        close_deadline=(startup_end if startup_end is not None else min(time.monotonic(),deadline))+30
        while binding and startup_end is not None and not stop_event.is_set() and time.monotonic()<close_deadline-7:
            _collect(slot,binding,known,manifest['uid'])
            if (trial/'native/CHILD_RESULT.json').exists():
                native_result,_=load(trial/'native/CHILD_RESULT.json')
                current=identity(process.pid);unit=show(slot['unit'])
                live=validate_scope(slot,unit,current,current,launch,supervisor,directory=directory,
                    kernel_values=kernel(slot['unit'],binding['cgroup'],manifest['uid']))
                require(live['invocation_id']==binding['invocation_id'],'scope_invocation_changed')
                require(members(slot['unit'],binding['cgroup'],manifest['uid'])==[current['pid']],
                        'native_descendants_remain_before_release')
                observations=[]
                for item in known.values():
                    if same(item,current):continue
                    now=identity(item['pid'])
                    state='absent' if now is None else 'replaced' if not same(item,now) else 'zombie' if now['state']=='Z' else 'alive'
                    observations.append({'identity':item,'state':state})
                require(all(x['state'] in ('absent','replaced','zombie') for x in observations),'native_identity_alive_before_release')
                sockets=_clean_sockets(trial);require(sockets['confirmed'],'native_socket_cleanup_unconfirmed')
                save(trial/'SCOPE_WITNESS.json',{'scope':unit,'controller_identity':current,'members':[current['pid']],
                    'kernel':live['kernel'],'native_processes':observations,'socket_cleanup':sockets,
                    'observed_monotonic':time.monotonic()})
                save(trial/'RELEASE.json',{'slot_id':slot['slot_id'],'manifest_sha256':manifest_hash,
                    'controller_identity':current,'observed_monotonic':time.monotonic()})
                released=True;break
            require(process.poll() is None,'controller_exited_without_release');time.sleep(.05)
    except Exception as exc:
        errors.append({'error_type':type(exc).__name__,
            'code':str(exc) if type(exc)is ValueError and re.fullmatch('[a-z_]+',str(exc)) else None})
    if binding is None and process is not None and launch is not None:
        try:
            proc=identity(process.pid);unit=show(slot['unit'])
            binding=_cleanup_binding(slot,launch,proc,unit,supervisor)
            known[(proc['pid'],proc['start_ticks'])]=proc
            save(trial/'OWNERSHIP_ONLY.json',{'binding':binding,'scope_observation':unit,
                'intent_sha256':load(trial/'INTENT.json')[1],'observed_monotonic':time.monotonic()})
        except Exception as exc:
            errors.append({'error_type':type(exc).__name__,'code':'pre_hello_ownership_unresolved'})
    cleanup_start=startup_end if startup_end is not None else min(time.monotonic(),deadline)
    cleanup=_cleanup(slot,binding,known,process,trial,cleanup_start,cleanup_start+30,released=released)
    save(trial/'CLEANUP.json',cleanup);log.close()
    boundary_ok=bool(native_result and native_result['boundary_verified_before_and_after'] is True
        and native_result['work_requests_sent']==0 and native_result['provider_credentials_supplied'] is False
        and native_result['close_returned_within_allowance'] is True
        and all(native_result[k] is None for k in ('error_type','close_error_type','pre_close_error_type')))
    passed=bool(status=='ready' and cleanup['confirmed'] and cleanup['controller_exit_code']==0
                and released and boundary_ok and not errors)
    receipt={'slot':slot,'status':status,'intent_sha256':load(trial/'INTENT.json')[1],
        'launch_identity':launch,'unit_binding':binding,'startup_outcome':outcome,'cleanup':cleanup,
        'boundary_verified':boundary_ok,'errors':errors,'qualification_passed':passed,'safe_to_continue':passed,
        'work_requests_sent':0,'native_inference_requests':0 if passed else None,
        'usage_scope':'verified_no_external_network_and_no_work_request_not_a_provider_meter',
        'evidence_sha256':_inventory(trial)}
    _validate_before_continue(trial,directory,manifest,execution,slot,intent,receipt)
    save(trial/'RECEIPT.json',receipt)
    return receipt


def _validate_before_continue(trial,directory,manifest,execution,slot,intent,receipt):
    if receipt['qualification_passed']:
        try:
            _completed_evidence(trial,directory,manifest,execution,slot,intent,receipt)
            gate,_=load(trial/'GATE.json')
            for name in ('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json'):
                verify_boundary(gate['expected_boundary'],load(trial/'native'/name)[0]['observed'])
        except Exception as exc:
            receipt.update(status='infrastructure_failed',qualification_passed=False,
                safe_to_continue=False,native_inference_requests=None)
            receipt['errors'].append({'error_type':type(exc).__name__,
                'code':str(exc) if type(exc)is ValueError and re.fullmatch('[a-z_]+',str(exc)) else None})
    return receipt


def execute(out,*,manifest_sha256):
    directory=Path(out).absolute();manifest=validate_manifest(directory,manifest_sha256)
    require(not (directory/'EXECUTION.json').exists() and not any((directory/'slots').iterdir()),'qualification_is_one_shot')
    save(directory/'EXECUTION.json',{'schema_version':3,'registered_manifest_sha256':manifest_sha256,
        'supervisor':identity(os.getpid()),'started_monotonic':time.monotonic(),'boot_id':boot(),
        'dependencies':manifest['dependencies'],'source_sha256':manifest['source_sha256']})
    stop=threading.Event();results=[]
    with interrupt_scope(stop),ThreadPoolExecutor(max_workers=2) as pool:
        for batch in range(len(BATCHES)):
            planned=[s for s in manifest['slots'] if s['batch']==batch]
            if stop.is_set():
                results.extend({'slot':s,'status':'skipped_after_stop','qualification_passed':False,
                    'safe_to_continue':False,'native_inference_requests':None} for s in planned);continue
            futures=[pool.submit(_run_slot,directory,manifest,s,stop) for s in planned]
            rows=[]
            for slot,future in zip(planned,futures):
                try:rows.append(future.result())
                except Exception as exc:
                    rows.append({'slot':slot,'status':'unresolved','error_type':type(exc).__name__,
                        'qualification_passed':False,'safe_to_continue':False,'native_inference_requests':None})
            results.extend(rows)
            if any(not row['safe_to_continue'] for row in rows):stop.set()
    complete=len(results)==9 and all(r['safe_to_continue'] for r in results)
    save(directory/'REPORT.json',{'schema_version':3,'kind':VERSION,'manifest_sha256':manifest_sha256,
        'status':'completed' if complete else 'incomplete','qualification_passed':complete,
        'planned_slots':9,'results':results,'scope':'Caller-context, network-isolated startup component only; no model-quality or long-horizon proof.'})
    return audit_qualification(directory,manifest_sha256=manifest_sha256,strict=True)


def _completed_evidence(trial, directory, manifest, execution, slot, intent, receipt):
    """Reconstruct a claimed pass from native, boundary and lifecycle artifacts."""
    require(receipt['status'] == 'ready' and receipt['safe_to_continue'] is True
            and receipt['qualification_passed'] is True and receipt['boundary_verified'] is True
            and not receipt['errors'], 'completed_receipt_contradiction')
    require(execution['dependencies'] == manifest['dependencies']
            and execution['source_sha256'] == manifest['source_sha256'], 'execution_provenance_mismatch')
    expected_inventory = _inventory(trial)
    require(receipt['evidence_sha256'] == expected_inventory, 'evidence_inventory_mismatch')
    gate, _ = load(trial / 'GATE.json')
    hello, _ = load(trial / 'HELLO.json')
    client, _ = load(trial / 'LAUNCH.json')
    binding = receipt['unit_binding']
    supervisor = execution['supervisor']
    require(gate['slot_id'] == slot['slot_id'] and gate['manifest_sha256'] == intent['manifest_sha256']
            and gate['startup_deadline_monotonic'] == intent['startup_deadline_monotonic']
            and hello['slot_id'] == slot['slot_id'] and hello['manifest_sha256'] == intent['manifest_sha256'], 'gate_launch_mismatch')
    require(all(finite(v) for v in (client['observed_monotonic'],hello['observed_monotonic'],gate['observed_monotonic']))
        and intent['started_monotonic'] <= client['observed_monotonic'] <= gate['observed_monotonic'] <= intent['startup_deadline_monotonic']
        and intent['started_monotonic'] <= hello['observed_monotonic'] <= gate['observed_monotonic'], 'hello_launch_gate_timing_mismatch')
    require(client['identity'] == receipt['launch_identity'] and client['identity']['ppid'] == supervisor['pid']
            and client['identity']['uid'] == manifest['uid'] and client['identity']['boot_id'] == manifest['boot_id']
            and client['identity']['start_ticks'] >= supervisor['start_ticks']
            and same(client['identity'], binding['main_identity']), 'control_client_parent_mismatch')
    rebuilt = validate_scope(slot, gate['unit_observation'], binding['main_identity'], hello['identity'],
        client['identity'], supervisor, directory=directory, kernel_values=binding['kernel'])
    require(rebuilt == binding and gate['unit_binding'] == binding, 'unit_binding_changed')
    require(gate['expected_boundary'] == {'uid': manifest['uid'], 'boot_id': manifest['boot_id'],
        'host_net_namespace': supervisor['net_namespace'], 'host_user_namespace': supervisor['user_namespace'],
        'unit': slot['unit'], 'invocation_id': binding['invocation_id']}, 'host_boundary_changed')
    close_gate, _ = load(trial / 'CLOSE_GATE.json')
    native_ids, _ = load(trial / 'NATIVE_IDENTITIES.json')
    computer = trial / 'native/computers/startup-qualification'
    instance, instance_hash = load(computer / 'instance.json')
    require(native_ids['instance_sha256'] == instance_hash and close_gate['native_identities'] == native_ids['identities']
            and close_gate['slot_id'] == slot['slot_id'] and close_gate['manifest_sha256'] == intent['manifest_sha256'],
            'native_identity_receipt_mismatch')
    ids = native_ids['identities']
    require(set(ids) == {'worker', 'sandbox'} and ids['worker']['net_namespace'] == binding['main_identity']['net_namespace']
            and ids['worker']['user_namespace'] == binding['main_identity']['user_namespace']
            and ids['worker']['pid'] == instance['pid']
            and ids['sandbox']['pid'] == instance['sandbox_pid']
            and ids['worker']['ppid'] == binding['main_identity']['pid']
            and ids['sandbox']['ppid'] == ids['worker']['pid'], 'native_identity_parent_mismatch')
    commands = expected_native_commands(trial, manifest)
    for key, proc in ids.items():
        require(proc['argv_sha256'] == sha(canonical(commands[key]))
                and proc['cwd'] == str(computer / 'workspace'), 'native_descendant_command_changed')
        require(proc['cgroup'] == binding['cgroup'] and proc['uid'] == manifest['uid']
                and proc['boot_id'] == manifest['boot_id'] and proc['state'] not in ('Z', 'X')
                and proc['start_ticks'] >= binding['main_identity']['start_ticks'], 'native_identity_scope_mismatch')
        require(any(same(proc, row['identity']) for row in receipt['cleanup']['observed_processes']),
                'native_identity_missing_in_cleanup')
    from lifespan.evaluation.hermes_transport import contract
    require(instance['kind'] == 'ready' and instance['backend'] == 'bubblewrap'
            and instance['employee'] == 'startup-qualification'
            and instance['evaluation_transport'] == contract('nonstreaming')
            and {'terminal', 'skill_view', 'enterprise_action'} <= set(instance['tool_names'])
            and not {'memory', 'skill_manage'} & set(instance['tool_names']), 'native_ready_contract_mismatch')
    require(canonical(instance.get('provider_contract')) == canonical(manifest['child_execution'].get('provider_contract')),
            'native_provider_contract_mismatch')
    terminal_probe = json.loads(instance['probe'])
    require(type(terminal_probe['exit_code']) is int and terminal_probe['exit_code'] == 0
            and 'startup-qualification' in terminal_probe['output'].splitlines(), 'native_sandbox_probe_invalid')
    journal_manifest, _ = load(computer / 'startup/manifest.json')
    from lifespan.startup_observability import provenance, VERSION as observation_version
    require(journal_manifest == {'version': observation_version, 'attempt_id': journal_manifest['attempt_id'], **provenance()}
            and re.fullmatch('[0-9a-f]{32}', journal_manifest['attempt_id']), 'startup_journal_manifest_mismatch')
    stages = {'parent': ['popen_returned', 'ready_received'], 'worker': ['worker_entered',
        'imports_before', 'imports_after', 'registry_before', 'registry_after', 'sandbox_before', 'sandbox_after',
        'agent_before', 'agent_after', 'budget_transport_before', 'budget_transport_after', 'probe_before',
        'probe_after', 'ready_write_attempt', 'ready_write_returned']}
    phase, _ = load(trial / 'native/STARTUP_FINISHED.json')
    journal_result, _ = load(trial / 'native/CHILD_RESULT.json')
    for role, expected_stages in stages.items():
        records = [json.loads(line) for line in (computer / 'startup' / (role + '.jsonl')).read_bytes().splitlines()]
        require([row['stage'] for row in records] == expected_stages, 'startup_stage_or_work_request_mismatch')
        require(all(finite(row['monotonic_seconds']) for row in records)
                and all(a['monotonic_seconds'] <= b['monotonic_seconds'] for a,b in zip(records,records[1:])),
                'startup_stage_order_changed')
        for index, row in enumerate(records):
            end = journal_result['close_finished_monotonic'] if row['stage'] == 'ready_write_returned' else phase['finished_monotonic']
            require(type(row['sequence']) is int and row['sequence'] == index and row['role'] == role
                    and row['attempt_id'] == journal_manifest['attempt_id'] and row['version'] == observation_version
                    and row['error_type'] is None and row['observation_errors'] == []
                    and same(row['observer_identity'], ids['worker'] if role == 'worker' else binding['main_identity'])
                    and same(row['worker_identity'], ids['worker'])
                    and finite(row['monotonic_seconds']) and intent['started_monotonic'] <= row['monotonic_seconds']
                    <= end, 'startup_journal_binding_mismatch')
    result, _ = load(trial / 'native/CHILD_RESULT.json')
    close, _ = load(trial / 'native/CLOSE_STARTED.json')
    start_intent, _ = load(trial / 'native/STARTUP_INTENT.json')
    require(start_intent['kind'] == VERSION and canonical(start_intent['execution']) == canonical(manifest['child_execution'])
            and start_intent['helper_sha256'] == manifest['source_sha256']['scripts/hermes_startup_scope_qualification_v3.py']
            and start_intent['work_requests_sent'] == 0, 'native_startup_intent_mismatch')
    require(phase['ready_observed'] is True and phase['error_type'] is None and result['ready_observed'] is True
            and all(result[key] is None for key in ('error_type', 'close_error_type', 'pre_close_error_type'))
            and result['close_returned_within_allowance'] is True, 'native_child_error')
    require(result['startup_finished_monotonic'] == phase['finished_monotonic']
            and result['entered_monotonic'] == phase['entered_monotonic']
            and result['startup_deadline'] == phase['startup_deadline'] == intent['startup_deadline_monotonic']
            and gate['observed_monotonic'] <= phase['entered_monotonic'] <= phase['finished_monotonic']
            and phase['startup_elapsed_seconds'] == phase['finished_monotonic'] - phase['entered_monotonic'],
            'native_timing_mismatch')
    require(close['started_monotonic'] == phase['finished_monotonic']
            and close['cleanup_deadline'] == close['started_monotonic'] + CONFIG['cleanup_seconds']
            == result['cleanup_deadline'] == close_gate['cleanup_deadline_monotonic']
            and close['started_monotonic'] <= result['close_finished_monotonic'] <= close['cleanup_deadline'],
            'native_close_timing_mismatch')
    raw_cleanup, _ = load(trial / 'CLEANUP.json')
    require(raw_cleanup == receipt['cleanup'], 'cleanup_receipt_mismatch')
    witness, _ = load(trial / 'SCOPE_WITNESS.json')
    release, release_hash = load(trial / 'RELEASE.json')
    exited, _ = load(trial / 'CONTROLLER_EXIT.json')
    rebuilt_witness = validate_scope(slot, witness['scope'], witness['controller_identity'],
        hello['identity'], client['identity'], supervisor, directory=directory, kernel_values=witness['kernel'])
    require(rebuilt_witness['invocation_id'] == binding['invocation_id']
        and witness['members'] == [binding['main_identity']['pid']]
        and witness['socket_cleanup']['confirmed'] is True
        and all(x['state'] in ('absent','replaced','zombie') for x in witness['native_processes']),
        'scope_cleanup_witness_invalid')
    for proc in ids.values():
        require(any(same(proc,x['identity']) for x in witness['native_processes']),
            'native_identity_missing_from_live_witness')
    require(release['slot_id'] == slot['slot_id'] and release['manifest_sha256'] == intent['manifest_sha256']
        and same(release['controller_identity'],binding['main_identity'])
        and exited['slot_id'] == slot['slot_id'] and exited['manifest_sha256'] == intent['manifest_sha256']
        and exited['release_sha256'] == release_hash and exited['normal_release'] is True
        and same(exited['identity'],binding['main_identity']), 'controller_release_binding_mismatch')
    require(result['close_finished_monotonic'] <= witness['observed_monotonic']
        <= release['observed_monotonic'] <= exited['observed_monotonic'] <= raw_cleanup['ended_monotonic']
        <= result['cleanup_deadline'], 'scope_witness_timing_mismatch')
    final = raw_cleanup['scope_final']
    require(final['Id'] == slot['unit'] and (final['LoadState'] == 'not-found'
        and not final['InvocationID'] and not final['ControlGroup'] or final['LoadState'] == 'loaded'
        and final['ActiveState'] == 'inactive' and final['InvocationID'] == binding['invocation_id']),
        'scope_final_not_terminated')
    require(raw_cleanup['controller_exit_code'] == 0 and raw_cleanup['released'] is True
        and raw_cleanup['scope_stop'] is None, 'controller_exit_not_normal_release')


def audit_qualification(out, *, manifest_sha256, strict=False):
    """Read-only independent closure for this new ownership model, not v2 audit."""
    directory = Path(out).absolute()
    errors = []; rows = []
    try:
        manifest = validate_manifest(directory, manifest_sha256, current=False)
        if not (directory / 'EXECUTION.json').exists():
            return {'ok': not strict, 'status': 'prepared', 'planned_slots': 9, 'qualification_passed': False, 'errors': []}
        execution, _ = load(directory / 'EXECUTION.json')
        require(execution['registered_manifest_sha256'] == manifest_sha256
                and execution['boot_id'] == manifest['boot_id'], 'execution_binding_mismatch')
        require(execution['supervisor']['uid'] == manifest['uid']
                and execution['supervisor']['boot_id'] == manifest['boot_id']
                and execution['supervisor']['security_context'] == manifest['caller_security_context'],
                'registered_supervisor_context_mismatch')
        for slot in manifest['slots']:
            trial = directory / 'slots' / slot['slot_id']
            if not (trial / 'RECEIPT.json').exists():
                rows.append({'slot_id': slot['slot_id'], 'status': 'missing', 'qualification_passed': False})
                continue
            receipt, receipt_hash = load(trial / 'RECEIPT.json')
            require(receipt['evidence_sha256']==_inventory(trial),'raw_evidence_inventory_changed')
            require(receipt['slot'] == slot, 'receipt_slot_mismatch')
            for name, expected in receipt['evidence_sha256'].items():
                path = Path(name)
                require(not path.is_absolute() and '..' not in path.parts and name != 'RECEIPT.json', 'receipt_path_escape')
                require((trial / path).is_file() and not (trial / path).is_symlink()
                        and sha((trial / path).read_bytes()) == expected, 'raw_evidence_changed')
            intent, intent_hash = load(trial / 'INTENT.json')
            require(intent_hash == receipt['intent_sha256'] and intent['slot_id'] == slot['slot_id']
                    and intent['unit'] == slot['unit'] and intent['manifest_sha256'] == manifest_sha256
                    and intent['command_sha256'] == sha(canonical(launch_argv(directory, slot))), 'launch_intent_mismatch')
            require(finite(intent['started_monotonic']) and intent['startup_deadline_monotonic']
                    == intent['started_monotonic'] + CONFIG['startup_seconds'], 'startup_allowance_changed')
            passed = receipt.get('qualification_passed') is True
            if passed or receipt.get('safe_to_continue') is True:
                _completed_evidence(trial, directory, manifest, execution, slot, intent, receipt)
                gate, _ = load(trial / 'GATE.json')
                before, _ = load(trial / 'native/BOUNDARY_BEFORE.json')
                after, _ = load(trial / 'native/BOUNDARY_AFTER.json')
                result, _ = load(trial / 'native/CHILD_RESULT.json')
                phase, _ = load(trial / 'native/STARTUP_FINISHED.json')
                verify_boundary(gate['expected_boundary'], before['observed'])
                verify_boundary(gate['expected_boundary'], after['observed'])
                require(before['expected'] == gate['expected_boundary']
                        and gate['unit_binding'] == receipt['unit_binding'], 'boundary_binding_mismatch')
                require(result['work_requests_sent'] == 0 and result['provider_credentials_supplied'] is False
                        and receipt['native_inference_requests'] == 0
                        and result['boundary_verified_before_and_after'] is True, 'inference_boundary_not_verified')
                require(phase == receipt['startup_outcome'] and finite(phase['finished_monotonic'])
                        and intent['started_monotonic'] <= phase['finished_monotonic']
                        <= intent['startup_deadline_monotonic'], 'startup_phase_mismatch')
                cleanup = receipt['cleanup']
                require(cleanup['started_monotonic'] == phase['finished_monotonic']
                        and cleanup['deadline_monotonic'] == cleanup['started_monotonic'] + CONFIG['cleanup_seconds']
                        and cleanup['limit_seconds'] == CONFIG['cleanup_seconds']
                        and cleanup['started_monotonic'] <= cleanup['ended_monotonic'] <= cleanup['deadline_monotonic'],
                        'cleanup_allowance_changed')
                require(cleanup['confirmed'] is True and not cleanup['members_remaining'] and not cleanup['errors']
                        and cleanup['socket_cleanup']['confirmed'] is True
                        and cleanup['controller_exit_code'] is not None
                        and all(x['state'] in ('absent', 'replaced', 'zombie') for x in cleanup['observed_processes']),
                        'cleanup_unconfirmed')
                require(any(same(x['identity'], receipt['unit_binding']['main_identity'])
                            for x in cleanup['observed_processes']), 'native_main_missing_from_cleanup')
                require(passed == (phase['ready_observed'] is True and result['ready_observed'] is True), 'startup_pass_forged')
            rows.append({'slot_id': slot['slot_id'], 'status': receipt['status'],
                         'qualification_passed': passed, 'receipt_sha256': receipt_hash,
                         'safe_to_continue': receipt.get('safe_to_continue') is True,
                         'started_monotonic': intent['started_monotonic'],
                         'ended_monotonic': receipt['cleanup']['ended_monotonic']})
        complete = len(rows) == 9 and all(x.get('safe_to_continue') for x in rows)
        for batch in range(1, len(BATCHES)):
            previous = [r for r, s in zip(rows, manifest['slots']) if s['batch'] == batch - 1 and 'ended_monotonic' in r]
            current_rows = [r for r, s in zip(rows, manifest['slots']) if s['batch'] == batch and 'started_monotonic' in r]
            if previous and current_rows:
                require(min(x['started_monotonic'] for x in current_rows) >= max(x['ended_monotonic'] for x in previous),
                        'batch_barrier_broken')
        stopped=False
        for batch in range(len(BATCHES)):
            batch_rows=[r for r,s in zip(rows,manifest['slots']) if s['batch']==batch]
            require(not stopped or not any('started_monotonic' in r for r in batch_rows),'later_batch_after_failure')
            if any(not r.get('safe_to_continue') for r in batch_rows):stopped=True
        if (directory / 'REPORT.json').exists():
            report, _ = load(directory / 'REPORT.json')
            require(report['manifest_sha256'] == manifest_sha256 and report['planned_slots'] == 9
                    and [x['slot'] for x in report['results']] == manifest['slots'], 'report_plan_mismatch')
            for expected_slot, reported in zip(manifest['slots'], report['results']):
                raw_path = directory / 'slots' / expected_slot['slot_id'] / 'RECEIPT.json'
                if raw_path.exists():
                    require(reported == load(raw_path)[0], 'report_receipt_mismatch')
                else:
                    require(reported['status'] in ('skipped_after_stop', 'unresolved')
                            and reported['qualification_passed'] is False
                            and reported['safe_to_continue'] is False, 'report_missing_slot_misrepresented')
            require((report['status'] == 'completed') == complete
                    and report['qualification_passed'] == (complete and all(x['qualification_passed'] for x in rows)),
                    'report_outcome_mismatch')
        elif complete:
            complete = False
        return {'ok': complete or not strict, 'status': 'completed' if complete else 'incomplete',
                'planned_slots': 9, 'slots': rows, 'qualification_passed': complete and all(x['qualification_passed'] for x in rows),
                'errors': errors, 'postprocessor_sha256': sha(Path(__file__).read_bytes())}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
        return {'ok': False, 'status': 'invalid', 'planned_slots': 9, 'slots': rows,
                'qualification_passed': False, 'errors': [{'error_type': type(exc).__name__,
                    'code': str(exc) if type(exc) is ValueError and re.fullmatch('[a-z_]+', str(exc)) else None}]}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true');action.add_argument('--execute',action='store_true')
    action.add_argument('--audit',action='store_true')
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--manifest-sha256')
    parser.add_argument('--model');parser.add_argument('--provider-profile')
    args=parser.parse_args(argv)
    try:
        if args.prepare:result=prepare(args.out, model=args.model, provider_profile=args.provider_profile)
        elif args.execute:result=execute(args.out,manifest_sha256=args.manifest_sha256)
        else:result=audit_qualification(args.out,manifest_sha256=args.manifest_sha256,strict=True)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__}));return 1
    print(json.dumps(result,sort_keys=True));return 0 if result.get('ok',result.get('prepared',False)) else 1


if __name__=='__main__':raise SystemExit(main())
