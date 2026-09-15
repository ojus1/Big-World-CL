"""Execute one native Fluso task with isolated files and a controller-owned meter."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import time
import uuid

from aiohttp import web

from . import chat_relay
from .chat_budget_gateway import METER, create_app, encoded, require, sha
from .qualify_fluso_isolation import IMAGE, DATA, WORKSPACE, catalog, environment, common, command

PROJECT = WORKSPACE + '/projects/Home'
TASK_DIRECTORY = PROJECT + '/task'
SKILL_PATH = WORKSPACE + '/skills/work-process/SKILL.md'
THREAD = 'worldlab-task'


def skill_file(content):
    return ('---\nname: work-process\ndescription: Employee work process. Read before every task.\n'
            'compatibility: fluso-native\n---\n\n' + content)


def task_prompt(instruction):
    return ('Read the complete work-process skill at ' + SKILL_PATH + ' before doing this task. '
            'The task working directory is ' + TASK_DIRECTORY + '. All relative input and output paths '
            'in the task are relative to that directory. Use it as the working directory for shell '
            'commands and use absolute paths within it for file tools. Create the requested deliverables '
            'there. Keep the final reply short.\n\n' + instruction)


def bind(source, destination, readonly=False):
    source = str(Path(source).resolve())
    require(not any(c in source for c in (',', '\x00', '\n', '\r')), 'Unsupported Docker mount path')
    return f'type=bind,src={source},dst={destination}' + (',readonly' if readonly else '')


def audit_container(info, *, image, network, mounts, user):
    """Check the actual Docker configuration, not just an intended command."""
    host, config = info['HostConfig'], info['Config']
    require(info['Image'] == image and host['NetworkMode'] == network, 'Container image or network differs')
    require(config['User'] == user and user.split(':')[0] != '0', 'Container must use the declared nonroot user')
    require(host['CapDrop'] == ['ALL'] and not host.get('CapAdd') and not host['Privileged']
            and host['ReadonlyRootfs'] and host['SecurityOpt'] == ['no-new-privileges'],
            'Container privileges differ from isolated profile')
    require(not host.get('Devices') and not host.get('DeviceRequests') and not host.get('PortBindings')
            and not host.get('ExtraHosts') and not host.get('VolumesFrom')
            and host.get('PidMode', '') == '' and host.get('IpcMode') == 'private',
            'Unqualified container device, namespace or host access')
    require(host['PidsLimit'] == 256 and host['Memory'] == 4 * 1024**3 and host['NanoCpus'] == 2 * 10**9,
            'Container resource limits changed')
    require(host['Tmpfs'] == {'/tmp': 'rw,nosuid,size=512m'}, 'Unexpected writable temporary mount')
    actual = {m['Destination']: (m['Source'], m['RW']) for m in info['Mounts'] if m['Type'] == 'bind'}
    require(len(actual) == len(mounts) and len(info['Mounts']) == len(mounts)
            and actual == mounts, 'Container mounted unexpected files or write permissions')


def audit_runtime_configuration(root, request, identity):
    root = Path(root)
    read = lambda p: json.loads(p.read_bytes())
    plan = read(root / 'PLAN.json')
    require(plan['request'] == request and plan['identity'] == identity, 'Native execution contract changed')
    require(plan['prompt'] == task_prompt(request['instruction'])
            and plan['catalog'] == catalog(identity['provider']['model'], request['budget']['output_tokens'])
            and plan['environment'] == environment(identity['provider']['model'], request['budget']['seconds']),
            'Native prompt, catalog or environment changed')
    require((root / 'models.json').read_bytes() == encoded(plan['catalog']), 'Native model catalog changed')
    require((root / 'skill/SKILL.md').read_text() == skill_file(request['skill']), 'Installed skill changed')
    relay, solver = read(root / 'RELAY_INSPECT.json'), read(root / 'SOLVER_INSPECT.json')
    image = identity['image']
    relay_mounts = {'/run/meter.sock': (plan['socket'], False),
                    '/run/relay.py': (str(Path(chat_relay.__file__).resolve()), False)}
    solver_mounts = {DATA: (str(root / 'data'), True), '/run/models.json': (str(root / 'models.json'), False),
                    WORKSPACE + '/skills/work-process': (str(root / 'skill'), False),
                    TASK_DIRECTORY: (request['workspace'], True)}
    audit_container(relay, image=image, network='none', mounts=relay_mounts, user=plan['user'])
    audit_container(solver, image=image, network='container:' + relay['Id'], mounts=solver_mounts, user=plan['user'])
    require(relay['Name'] == '/' + plan['relay'] and solver['Name'] == '/' + plan['solver'], 'Container identity changed')
    require(relay['Config']['Entrypoint'] == ['python3'] and relay['Config']['Cmd'] ==
            ['/run/relay.py', '--socket', '/run/meter.sock', '--timeout', str(request['budget']['seconds'])],
            'Relay command differs from qualified path')
    require(solver['Config']['Entrypoint'] == ['/usr/local/bin/bun'] and solver['Config']['Cmd'] ==
            ['harness.ts', 'send', '--thread', THREAD, plan['prompt']]
            and solver['Config']['WorkingDir'] == '/opt/fluso/agents/dev-harness', 'Native Fluso command changed')
    for key, value in plan['environment'].items():
        require([entry for entry in solver['Config']['Env'] if entry.startswith(key + '=')] == [key + '=' + value],
                'Native environment differs from declared provider and budget')
    if (root / 'TERMINAL_INSPECT.json').exists():
        terminal = read(root / 'TERMINAL_INSPECT.json')
        audit_container(terminal, image=image, network='container:' + relay['Id'], mounts=solver_mounts, user=plan['user'])
        require(terminal['Id'] == solver['Id'] and terminal['Config'] == solver['Config'], 'Native container configuration changed during execution')
        require(not terminal['State']['Running'], 'Native process is still running')
    return plan


async def execute(request, root, identity):
    """Never replay a failed attempt; stop the owned solver and drain accepted work."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    workspace = request.workspace.resolve()
    require(workspace.is_dir() and not request.workspace.is_symlink(), 'Expected a real public task workspace')
    require(not any(p.is_symlink() for p in workspace.rglob('*')), 'Task input symlinks are not qualified')
    model = identity['provider']['model']
    budget = request.budget
    native_request = {**asdict(request), 'workspace': str(workspace)}
    model_catalog, env = catalog(model, budget.output_tokens), environment(model, budget.seconds)
    (root / 'data' / TASK_DIRECTORY.removeprefix(DATA + '/')).mkdir(parents=True)
    (root / 'data' / WORKSPACE.removeprefix(DATA + '/') / 'skills/work-process').mkdir(parents=True)
    (root / 'skill').mkdir(); (root / 'skill/SKILL.md').write_text(skill_file(request.skill))
    (root / 'models.json').write_bytes(encoded(model_catalog))
    suffix = uuid.uuid4().hex[:20]
    relay_name, solver_name = ('worldlab-' + suffix + name for name in ('-relay', '-solver'))
    app = create_app(identity['upstream'], identity['tokenizer'], model, budget, root / 'meter')
    runner = web.AppRunner(app, handler_cancellation=True, shutdown_timeout=budget.seconds)
    started = time.monotonic()
    prepared, process, solver_id = False, None, None
    exit_code, error, cleanup, cleanup_error = None, None, [], None
    temporary = tempfile.TemporaryDirectory(prefix='worldlab-fluso-')
    socket = str(Path(temporary.name) / 'meter.sock')
    save = lambda name, value: (root / name).write_bytes(encoded(value))
    common_flags = common('none', relay_name)
    user = common_flags[common_flags.index('--user') + 1]
    plan = {'version': 1, 'identity': identity, 'request': native_request, 'prompt': task_prompt(request.instruction),
            'catalog': model_catalog, 'environment': env, 'relay': relay_name, 'solver': solver_name,
            'user': user, 'socket': socket}
    save('PLAN.json', plan)
    try:
        image = json.loads((await command(['docker', 'image', 'inspect', identity['image']]))['stdout'])[0]
        require(image['Id'] == identity['image'], 'Pinned Fluso image is unavailable')
        save('IMAGE.json', {'Id': image['Id'], 'Created': image['Created']})
        await runner.setup(); prepared = True
        await web.UnixSite(runner, socket).start()
        relay_cmd = ['docker', 'create', *common_flags, '--mount', bind(socket, '/run/meter.sock', True),
            '--mount', bind(Path(chat_relay.__file__), '/run/relay.py', True), '--entrypoint', 'python3',
            identity['image'], '/run/relay.py', '--socket', '/run/meter.sock', '--timeout', str(budget.seconds)]
        save('RELAY_COMMAND.json', relay_cmd)
        relay_id = (await command(relay_cmd))['stdout'].strip()
        await command(['docker', 'start', relay_id])
        relay = json.loads((await command(['docker', 'inspect', relay_id]))['stdout'])[0]
        save('RELAY_INSPECT.json', relay)
        solver_cmd = ['docker', 'create', *common('container:' + relay_id, solver_name),
            '--mount', bind(root / 'data', DATA), '--mount', bind(root / 'models.json', '/run/models.json', True),
            '--mount', bind(root / 'skill', WORKSPACE + '/skills/work-process', True),
            '--mount', bind(workspace, TASK_DIRECTORY), '--workdir', '/opt/fluso/agents/dev-harness']
        for key, value in env.items(): solver_cmd += ['--env', key + '=' + value]
        solver_cmd += ['--entrypoint', '/usr/local/bin/bun', identity['image'], 'harness.ts', 'send', '--thread', THREAD, plan['prompt']]
        save('SOLVER_COMMAND.json', solver_cmd)
        solver_id = (await command(solver_cmd))['stdout'].strip()
        save('SOLVER_INSPECT.json', json.loads((await command(['docker', 'inspect', solver_id]))['stdout'])[0])
        audit_runtime_configuration(root, native_request, identity)
        with (root / 'stdout.log').open('wb') as stdout, (root / 'stderr.log').open('wb') as stderr:
            process = await asyncio.create_subprocess_exec('docker', 'start', '-a', solver_id, stdout=stdout, stderr=stderr)
            while process.returncode is None:
                if app[METER].stopped or not app[METER].remaining_seconds():
                    if not app[METER].stopped: app[METER].stop('time_budget', exhausted=True)
                    save('STOP_INTENT.json', {'reason': app[METER].stop_reason, 'container': solver_id})
                    save('STOP_RESULT.json', await command(['docker', 'stop', '--time', '2', solver_id]))
                    break
                await asyncio.sleep(.1)
            exit_code = await process.wait()
        save('TERMINAL_INSPECT.json', json.loads((await command(['docker', 'inspect', solver_id]))['stdout'])[0])
    except Exception as exc:
        error = type(exc).__name__
        save('RUNTIME_ERROR.json', {'error_type': error})
    finally:
        # Stop the owned native process before closing admissions. The relay
        # continues draining already accepted requests until their own deadline.
        if solver_id and process is not None and process.returncode is None:
            await command(['docker', 'stop', '--time', '2', solver_id], check=False)
        if prepared:
            try:
                await runner.cleanup()
            except Exception as exc:
                cleanup_error = type(exc).__name__
        for name in (solver_name, relay_name):
            try:
                row = await command(['docker', 'rm', '-f', name], check=False)
                cleanup.append(row)
                if row['returncode'] and 'No such container' not in row['stderr']:
                    cleanup_error = 'ContainerRemovalFailed'
            except Exception as exc:
                cleanup_error = type(exc).__name__
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill(); await process.wait(); cleanup_error = 'DockerClientExitTimeout'
        temporary.cleanup()
        app[METER].flush()
        save('CLEANUP.json', cleanup)
    traces = sorted((root / 'data').glob('tenants/dev/users/dev-user/sessions/*/.fluso-agent-core/session/*.jsonl'))
    result = {'seconds': time.monotonic() - started, 'exit_code': exit_code,
              'error_type': error, 'cleanup_error': cleanup_error,
              'trace_files': [str(p.relative_to(root)) for p in traces],
              'meter_sha256': sha((root / 'meter/METER.json').read_bytes()),
              'plan_sha256': sha((root / 'PLAN.json').read_bytes())}
    save('RESULT.json', result)
    return result
