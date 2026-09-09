"""One long-lived native Hermes AIAgent per employee (isolated process globals).

stdin/stdout are a private simulator RPC channel, never a model-visible tool.
Native terminal/file tools execute in Hermes' persistent Docker backend.
"""
import json
import hashlib
import os
from pathlib import Path
import sys
import traceback


def main():
    wire = sys.stdout
    sys.stdout = sys.stderr  # Hermes logging must not corrupt JSON RPC.
    def send(record):
        wire.write(json.dumps(record, ensure_ascii=False, default=str)+'\n')
        wire.flush()
    def receive():
        line = sys.stdin.readline()
        if not line:
            raise EOFError('Simulator closed worker pipe')
        return json.loads(line)
    from tools.registry import registry
    from toolsets import create_custom_toolset
    from run_agent import AIAgent, IterationBudget
    from hermes_state import SessionDB
    from tools.terminal_tool import terminal_tool, register_task_env_overrides, _active_environments

    def enterprise_action(args, **kwargs):
        send({'kind':'action','action':{'tool':args['operation'],'args':args.get('arguments',{})}})
        return json.dumps(receive())
    registry.register(name='enterprise_action',toolset='enterprise_lifespan',handler=enterprise_action,
        schema={'name':'enterprise_action','description':
            'Execute a workplace operation. draft.prepare requires artifact_path: an existing /workspace/deliverables/*.json '
            'file containing task_id, channel (string), redact (boolean), endpoint (string), and content (nonempty string). '
            'Prepare the file, run check.perform with name, request approval.request with approver, then work.commit. '
            'check.perform executes the simulator-owned synthetic customer verification and returns its result; '
            'no outside customer evidence is needed when it succeeds. '
            'work.commit verifies the actual prepared file is unchanged. documents.search queries current published '
            'department documents; employee.ask takes question; session.end leaves task pending.',
            'parameters':{'type':'object','properties':{
                'operation':{'type':'string','enum':['documents.search','employee.ask','draft.prepare','check.perform','approval.request','work.commit','session.end']},
                'arguments':{'type':'object'}},'required':['operation','arguments']}},check_fn=lambda:True)
    create_custom_toolset('enterprise_lifespan','Trusted workplace API',tools=['enterprise_action'])
    profile=Path(os.environ['HERMES_HOME'])
    eid=os.environ['LIFESPAN_EMPLOYEE']
    computer_id='lifespan-'+hashlib.sha256(str(profile).encode()).hexdigest()[:16]
    # Hermes classifies arbitrary HERMES_HOME paths as profile "custom" and
    # collapses ordinary tool task IDs to "default". Its native benchmark
    # override API is required to prevent cross-employee container reuse.
    backend=os.environ.get('LIFESPAN_SANDBOX','bubblewrap')
    if backend=='bubblewrap':
        from lifespan.bubblewrap import install_hermes_backend
        sandbox_env=install_hermes_backend(profile.parent)
    else:
        register_task_env_overrides(computer_id,{'env_type':'docker','docker_image':'python:3.12-slim','cwd':'/workspace'})
    system=(f'You are the persistent Hermes assistant of employee {eid} in a fictional business simulation. '
        'Complete the employee request using the real filesystem and enterprise_action tool. '
        'Your computer is /workspace. Read /workspace/inbox/current.json and /workspace/company/objectives.json, '
        'and consult /workspace/company/procedures.json when needed. These are published documents, not guaranteed '
        'to be effective on every date. Use only policy_owner authority; apply global rules then scoped rules in '
        'valid_from order, ignoring expired rules. New scoped patches preserve other fields. '
        'checks_add lists mandatory additional checks while that rule is effective; union them with checks. '
        'Your private files, memory and skills persist across workdays. Save useful process revisions in '
        '/workspace/notes/working_procedure.md; keep scope, evidence and expiry. Use terminal/file tools to create '
        'a concrete deliverable, then execute checks, approval and submission. Never claim completion without a '
        'successful work.commit. If blocked, retain evidence and leave work pending. Use English. '
        'Do not ask the outside user or access external systems; employee.ask reaches the simulated employee.')
    agent=AIAgent(model=os.environ['LIFESPAN_MODEL'],provider='custom',
        api_key=os.environ['LIFESPAN_API_KEY'],base_url=os.environ['LIFESPAN_BASE_URL'],
        api_mode='codex_responses',enabled_toolsets=['terminal','file','memory','skills','enterprise_lifespan'],
        max_iterations=12,max_tokens=4096,reasoning_config={'enabled':True,'effort':'low'},
        quiet_mode=True,save_trajectories=True,session_id='lifespan-'+eid,
        session_db=SessionDB(),skip_context_files=True,skip_background_review=True,
        checkpoints_enabled=False)
    # Materialize and exercise the native backend even before the first model turn.
    probe=terminal_tool(command='pwd; cat /workspace/.employee_identity; test ! -S /var/run/docker.sock',
                        task_id=computer_id)
    probe_result=json.loads(probe)
    if probe_result.get('exit_code')!=0 or eid not in probe_result.get('output','').splitlines():
        raise RuntimeError('Native Docker workspace identity probe failed: '+probe)
    sandbox=_active_environments.get(computer_id,_active_environments.get('default'))
    send({'kind':'ready','employee':eid,'pid':os.getpid(),'probe':probe,
          'backend':backend,'computer_id':computer_id,
          **({'sandbox_pid':sandbox.sandbox.process.pid,'rpc_socket':str(sandbox.sandbox.rpc_socket)}
             if backend=='bubblewrap' else {'container_id':sandbox._container_id}),
          'tool_names':[t['function']['name'] if 'function' in t else t.get('name') for t in agent.tools]})
    history_path=profile/'lifespan_history.json'
    history=json.loads(history_path.read_text()) if history_path.exists() else []
    while True:
        request=receive()
        if request['kind']=='close':
            if backend=='bubblewrap':sandbox.cleanup()
            send({'kind':'closed'})
            return
        try:
            # AIAgent's budget is instance-owned; replenish work-session compute
            # without clearing its conversation, memory, filesystem or identity.
            agent.iteration_budget=IterationBudget(agent.max_iterations)
            result=agent.run_conversation(request['prompt'],system_message=system,
                                          conversation_history=history,task_id=computer_id)
            if isinstance(result.get('messages'),list):
                history=result['messages']
                temp=history_path.with_suffix('.tmp')
                temp.write_text(json.dumps(history,ensure_ascii=False,default=str))
                temp.replace(history_path)
            send({'kind':'result','result':result})
        except Exception as exc:
            traceback.print_exc()
            send({'kind':'error','error':str(exc)})

if __name__=='__main__':
    main()
