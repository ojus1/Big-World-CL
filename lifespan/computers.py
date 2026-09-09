"""Persistent employee computer state and native Hermes worker supervision."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
from .mirofish import ROOT, save

HERMES = Path(os.environ.get('HERMES_AGENT_ROOT', Path.home() / '.hermes/hermes-agent')).expanduser().resolve()


def snapshot_files(root, objects=None):
    root=Path(root).resolve()
    result={}
    for p in sorted(root.rglob('*')):
        rel=str(p.relative_to(root))
        if p.is_symlink():
            result[rel]={'symlink':os.readlink(p)}
        elif p.is_file():
            data=p.read_bytes()
            sha=hashlib.sha256(data).hexdigest()
            result[rel]={'sha256':sha,'bytes':len(data),'mode':p.stat().st_mode & 0o777}
            if objects is not None:
                target=Path(objects)/sha
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():
                    target.write_bytes(data)
    return result


def file_delta(before,after):
    return {'created':sorted(after.keys()-before.keys()),'deleted':sorted(before.keys()-after.keys()),
            'modified':sorted(k for k in before.keys() & after.keys() if before[k]!=after[k])}


class Computer:
    def __init__(self,root,eid,backend='bubblewrap', *, execution=None, artifact_grader=None):
        self.eid=eid
        self.backend=backend
        self.execution=execution or {}
        self.artifact_grader=artifact_grader
        self.last_grade=None
        self.last_submission_hash=None
        self.committed_artifact=None
        self.committed_hash=None
        self.root=Path(root).resolve()/eid
        self.workspace=self.root/'workspace'
        self.profile=self.root/'hermes'
        self.objects=self.root.parent.parent/'filesystem_objects'
        for p in (self.profile,self.workspace/'inbox',self.workspace/'company',
                  self.workspace/'notes',self.workspace/'deliverables'):
            p.mkdir(parents=True,exist_ok=True)
        self.process=None
        (self.workspace/'.employee_identity').write_text(eid+'\n')
        self.prepared=None
        self.prepared_hash=None

    def publish(self,observation,objectives,documents):
        # Only adapter-owned files are refreshed. Employee notes/artifacts remain.
        observation['tools']=dict(observation.get('tools',{}),**{
            'draft.prepare':'Read an existing /workspace/deliverables/*.json file. Required argument: artifact_path. The FILE must contain task_id, channel, redact (boolean), endpoint, content (nonempty string). Preparing resets checks and approval.',
            'work.commit':'Submit the unchanged prepared file after checks and approval. No arguments; the endpoint is read from the file.'})
        save(self.workspace/'inbox/current.json',observation)
        save(self.workspace/'company/objectives.json',objectives)
        save(self.workspace/'company/procedures.json',documents)

    def snapshot(self):
        return snapshot_files(self.workspace,self.objects)

    def read_artifact(self,path,task_id):
        path=Path(path)
        if not path.is_absolute() or not path.is_relative_to('/workspace/deliverables'):
            raise ValueError('Use an absolute /workspace/deliverables/*.json path')
        host=(self.workspace/path.relative_to('/workspace')).resolve()
        if not host.is_relative_to((self.workspace/'deliverables').resolve()) or host.suffix!='.json':
            raise ValueError('Artifact path leaves employee deliverables directory')
        if not host.is_file() or host.stat().st_size>100_000:
            raise ValueError('Deliverable missing or larger than 100KB')
        raw=host.read_bytes()
        def unique_object(pairs):
            value={}
            for key,item in pairs:
                if key in value:
                    raise ValueError('Duplicate artifact JSON key: '+key)
                value[key]=item
            return value
        artifact=json.loads(raw,object_pairs_hook=unique_object)
        if (not isinstance(artifact,dict) or artifact.get('task_id')!=task_id or not isinstance(artifact.get('channel'),str)
            or not isinstance(artifact.get('redact'),bool) or not isinstance(artifact.get('endpoint'),str)
            or not isinstance(artifact.get('content'),str) or not artifact['content'].strip()):
            raise ValueError('Deliverable needs matching task_id, channel, redact, endpoint and nonempty content')
        sha=hashlib.sha256(raw).hexdigest()
        # Preserve the exact bytes read by the trusted process. A later workspace
        # snapshot may see a rewritten or deleted file, including after rejection.
        self.objects.mkdir(parents=True,exist_ok=True)
        target=self.objects/sha
        try:
            with target.open('xb') as stream:
                stream.write(raw)
        except FileExistsError:
            if target.read_bytes()!=raw:
                raise ValueError('Immutable artifact object has conflicting content')
        return artifact,sha

    def action(self,env,action):
        if env.done:
            return {'ok':False,'error':'Work session already ended'}
        tool,args=action.get('tool'),action.get('args',{})
        try:
            if tool=='draft.prepare':
                path=args.get('artifact_path','')
                artifact,sha=self.read_artifact(path,env._task.id)
                self.prepared,self.prepared_hash=path,sha
                converted={'tool':tool,'args':{'channel':artifact['channel'],'redact':artifact['redact']}}
            elif tool=='work.commit':
                artifact,sha=self.read_artifact(self.prepared or '',env._task.id)
                if sha!=self.prepared_hash:
                    raise ValueError('Prepared artifact changed; prepare again and repeat checks/approval')
                converted={'tool':tool,'args':{'endpoint':artifact['endpoint']}}
                if self.artifact_grader is not None:
                    self.last_grade=self.artifact_grader(artifact)
                    self.last_submission_hash=sha
                    # Content is checked in the trusted process before business
                    # effects. The expected answer never enters a tool response.
                    if not self.last_grade['success']:
                        converted={'tool':'artifact.reject','args':{
                            'feedback':self.last_grade['feedback']}}
            else:
                converted=action
            result=env.step(converted)
            if tool=='work.commit' and env.success:
                # Business state is the accepted snapshot, even if the native
                # agent edits its local file after the transaction completes.
                self.committed_artifact=deepcopy(artifact)
                self.committed_hash=sha
            return {'observation':result[0],'reward':result[1],'terminated':result[2],
                    'truncated':result[3],'info':result[4],
                    **({'artifact_sha256':self.prepared_hash} if tool in ('draft.prepare','work.commit') else {})}
        except (ValueError,TypeError,OSError,json.JSONDecodeError) as exc:
            return {'ok':False,'error':str(exc)}

    def start(self,credentials,timeout=150):
        import yaml
        config={'model':{'default':credentials['model'],'provider':'custom','base_url':credentials['base_url'],
                         'api_mode':'codex_responses'},
            'terminal':{'backend':'docker','docker_image':'python:3.12-slim','cwd':'/workspace',
                'docker_mount_cwd_to_workspace':False,'docker_volumes':[f'{self.workspace}:/workspace'],
                'docker_forward_env':[],'docker_env':{},'docker_network':False,
                'docker_run_as_host_user':True,'container_persistent':True,
                'docker_persist_across_processes':True,'docker_orphan_reaper':False,
                'container_cpu':1,'container_memory':768,'container_disk':0,'timeout':30},
            'agent':{'max_turns':12,'reasoning_effort':'low'},
            'memory':{'memory_enabled':True,'user_profile_enabled':True},
            'checkpoints':{'enabled':False},'display':{'tool_progress':'off'}}
        config['tools']={'tool_search':{'enabled':'off'}}
        if self.execution.get('mode')=='evaluation':
            config['skills']={'template_vars':False,'inline_shell':False}
            config['memory']={'memory_enabled':False,'user_profile_enabled':False}
        if self.backend=='bubblewrap':
            config['terminal']={'backend':'local','cwd':'/workspace','timeout':30,'lifetime_seconds':86400}
            config['lifespan_sandbox']={'backend':'bubblewrap','native_environment_adapter':True}
        (self.profile/'config.yaml').write_text(yaml.safe_dump(config))
        # Do not inherit the user's personal Hermes config, plugins or tool credentials.
        process_env={k:os.environ[k] for k in ('PATH','HOME','LANG','USER','LOGNAME','XDG_RUNTIME_DIR') if k in os.environ}
        process_env.update(HERMES_HOME=str(self.profile),PYTHONPATH=f'{ROOT}:{HERMES}',
            LIFESPAN_EMPLOYEE=self.eid,LIFESPAN_MODEL=credentials['model'],
            LIFESPAN_BASE_URL=credentials['base_url'],LIFESPAN_API_KEY=credentials['api_key'],
            PYTHONUNBUFFERED='1',HERMES_YOLO='1',LIFESPAN_SANDBOX=self.backend)
        process_env['LIFESPAN_EXECUTION_CONFIG']=json.dumps(self.execution)
        self.log=(self.root/'worker.log').open('a')
        self.process=subprocess.Popen([str(HERMES/'venv/bin/python'),'-u','-m','lifespan.hermes_worker'],
            cwd=self.workspace,env=process_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=self.log,text=True,bufsize=1)
        ready=self.receive(timeout)
        if ready.get('kind')!='ready':
            raise RuntimeError(f'Hermes startup failed: {ready}')
        self.ready=ready
        self.container_id=ready.get('container_id')
        self.runtime_state()
        save(self.root/'instance.json',ready)
        return ready

    def runtime_state(self):
        if self.backend=='bubblewrap':
            from .bubblewrap import rpc
            state=rpc(self.ready['rpc_socket'],{'kind':'inspect'})
            if state['workspace_identity']!=self.eid:
                raise RuntimeError('Employee computer identity changed')
            state.update(backend='bubblewrap',sandbox_pid=self.ready['sandbox_pid'],
                os_home=snapshot_files(self.root/'os_home',self.objects),
                hermes_memory=snapshot_files(self.profile/'memories',self.objects),
                hermes_skills=snapshot_files(self.profile/'skills',self.objects))
            save(self.root/'computer_state.json',state)
            return state
        data=json.loads(subprocess.check_output(['docker','inspect',self.container_id],text=True,timeout=15))[0]
        if data['HostConfig']['NetworkMode']!='none' or data['HostConfig']['Privileged']:
            raise RuntimeError('Employee computer isolation configuration changed')
        mounts=data['Mounts']
        if not all(Path(m['Source']).resolve().is_relative_to(self.root) for m in mounts):
            raise RuntimeError('Employee container has a mount outside its own computer directory')
        workspace=next((m for m in mounts if m['Destination']=='/workspace'),None)
        if workspace is None or Path(workspace['Source']).resolve()!=self.workspace:
            raise RuntimeError('Hermes attached the wrong employee workspace')
        processes=subprocess.check_output(['docker','top',self.container_id,'-eo','pid,comm'],text=True,timeout=15)
        state={'container_id':self.container_id,'image':data['Image'],'network':'none',
            'running':data['State']['Running'],'mounts':[{k:m[k] for k in ('Source','Destination','RW')} for m in mounts],
            'processes':processes,'layer_changes':subprocess.check_output(['docker','diff',self.container_id],text=True,timeout=15),
            'hermes_memory':snapshot_files(self.profile/'memories',self.objects),
            'hermes_skills':snapshot_files(self.profile/'skills',self.objects)}
        save(self.root/'computer_state.json',state)
        return state

    def receive(self,timeout):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            if not selector.select(timeout):
                raise TimeoutError(f'Hermes {self.eid} exceeded {timeout}s; inspect {self.root}/worker.log')
        line=self.process.stdout.readline()
        if not line:
            raise RuntimeError(f'Hermes {self.eid} exited {self.process.poll()}; inspect {self.root}/worker.log')
        return json.loads(line)

    def send(self,value):
        self.process.stdin.write(json.dumps(value)+'\n')
        self.process.stdin.flush()

    def run(self,env,prompt,timeout=420):
        self.prepared=self.prepared_hash=None
        self.last_grade=self.last_submission_hash=None
        self.committed_artifact=self.committed_hash=None
        self.send({'kind':'run','prompt':prompt})
        rpc=[]
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            msg=self.receive(min(150,max(1,deadline-time.monotonic())))
            if msg['kind']=='action':
                response=self.action(env,msg['action'])
                rpc.append({'action':msg['action'],'response':response})
                self.send(response)
            elif msg['kind']=='result':
                return {'native':msg['result'],'workplace_rpc':rpc}
            else:
                raise RuntimeError(f'Hermes worker error: {msg}')
        raise TimeoutError(f'Hermes session exceeded {timeout}s: {self.eid}')

    def close(self):
        if self.process and self.process.poll() is None:
            try:
                self.send({'kind':'close'})
                self.process.wait(timeout=10)
            except (OSError,subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if hasattr(self,'log'):
            self.log.close()
