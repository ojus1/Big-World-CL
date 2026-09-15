"""Independent Linux/systemd cleanup for a dead native Fluso controller.

The guardian never retries inference or changes model-accounting evidence. It
can only remove containers with the exact attempt name, image and owner label.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time

LABEL = 'io.worldlab.fluso-owner'


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def start_ticks(pid):
    return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])


def contract(token, seconds):
    return {'owner': token, 'parent_pid': os.getpid(), 'parent_start_ticks': start_ticks(os.getpid()),
            'unit': f'worldlab-fluso-{token}-guardian.service',
            'deadline_monotonic': time.monotonic() + seconds + 60,
            'settle_seconds': 5, 'cleanup_seconds': 60}


def validate_plan(plan):
    guardian = plan['guardian']
    token = guardian['owner']
    if not re.fullmatch('[0-9a-f]{20}', token):
        raise ValueError('Invalid guardian owner')
    if [plan[k] for k in ('solver', 'relay')] != [f'worldlab-{token}-{k}' for k in ('solver', 'relay')]:
        raise ValueError('Guardian container names differ from attempt ownership')
    if guardian['unit'] != f'worldlab-fluso-{token}-guardian.service':
        raise ValueError('Guardian service identity differs')
    if guardian['settle_seconds'] != 5 or guardian['cleanup_seconds'] != 60:
        raise ValueError('Guardian cleanup policy differs')
    return guardian


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    except subprocess.TimeoutExpired:
        return {'argv': argv, 'returncode': None, 'stdout': '', 'stderr': 'CommandTimeout'}


def owned_container(plan, name, run=command):
    listed = run(['docker', 'container', 'ls', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}'])
    if listed['returncode'] != 0:
        raise RuntimeError('Container listing failed')
    ids = listed['stdout'].split()
    if not ids:
        return None
    if len(ids) != 1:
        raise ValueError('Ambiguous container identity')
    inspected = run(['docker', 'inspect', ids[0]])
    if inspected['returncode'] != 0:
        raise RuntimeError('Container inspection failed')
    info, = json.loads(inspected['stdout'])
    if (info['Name'] != '/' + name or info['Image'] != plan['identity']['image']
            or info['Config'].get('Labels', {}).get(LABEL) != plan['guardian']['owner']):
        raise ValueError('Refusing cleanup of a container outside this attempt')
    return info


def disarm_valid(root, plan):
    acknowledgement = read(root / 'GUARDIAN_DISARM.json')
    cleanup = read(root / 'CLEANUP.json')
    result = read(root / 'RESULT.json')
    return (acknowledgement == {'plan_sha256': digest(root / 'PLAN.json'),
                               'cleanup_sha256': digest(root / 'CLEANUP.json'),
                               'result_sha256': digest(root / 'RESULT.json')}
            and len(cleanup) == 2
            and [r['argv'] for r in cleanup] == [['docker', 'rm', '-f', plan[k]] for k in ('solver', 'relay')]
            and all(r['returncode'] == 0 for r in cleanup) and not result['cleanup_error'])


def cleanup(root, plan, reason, run=command):
    """Repeated scans also catch a create command completing after parent death."""
    guardian = validate_plan(plan)
    save(root / 'GUARDIAN_INTERVENTION.json', {'reason': reason, 'plan_sha256': digest(root / 'PLAN.json'),
        'parent_pid': guardian['parent_pid'], 'at_monotonic': time.monotonic(),
        'grading_allowed': False, 'accounting_finalized': False})
    deadline, quiet_since, events = time.monotonic() + guardian['cleanup_seconds'], None, []
    while time.monotonic() < deadline:
        absent, failed = True, False
        for name in (plan['solver'], plan['relay']):
            try:
                info = owned_container(plan, name, run)
                if info is None:
                    continue
                absent = False
                # Use the inspected immutable ID for mutation, never a broad filter.
                if info['State']['Running']:
                    events.append(run(['docker', 'stop', '--time', '2', info['Id']]))
                events.append(run(['docker', 'rm', '-f', info['Id']]))
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                absent, failed = False, True
                events.append({'container': name, 'error_type': type(exc).__name__})
        save(root / 'GUARDIAN_CLEANUP.json', events)
        if absent and not failed:
            if quiet_since is None:
                quiet_since = time.monotonic()
            if time.monotonic() - quiet_since >= guardian['settle_seconds']:
                return True
        else:
            quiet_since = None
        time.sleep(.25)
    return False


def supervise(root):
    root = Path(root).resolve()
    plan = read(root / 'PLAN.json')
    guardian = validate_plan(plan)
    parent = None
    try:
        # pidfd pins the exact process; /proc start ticks reject PID reuse before open.
        parent = os.pidfd_open(guardian['parent_pid'])
        if start_ticks(guardian['parent_pid']) != guardian['parent_start_ticks']:
            os.close(parent); parent = None
    except ProcessLookupError:
        parent = None
    except FileNotFoundError:
        if parent is not None:
            os.close(parent); parent = None
    poll = select.poll()
    if parent is not None:
        poll.register(parent, select.POLLIN)
    save(root / 'GUARDIAN_READY.json', {'guardian_pid': os.getpid(), 'guardian': guardian,
                                      'plan_sha256': digest(root / 'PLAN.json')})
    try:
        while True:
            if (root / 'GUARDIAN_DISARM.json').exists():
                if disarm_valid(root, plan):
                    save(root / 'GUARDIAN_EXIT.json', {'status': 'disarmed', 'guardian': guardian,
                        'plan_sha256': digest(root / 'PLAN.json')})
                    return
                reason = 'invalid_cleanup_acknowledgement'; break
            if parent is None or poll.poll(100):
                reason = 'controller_exited'; break
            if time.monotonic() >= guardian['deadline_monotonic']:
                reason = 'controller_cleanup_deadline'; break
        ok = cleanup(root, plan, reason)
        save(root / 'GUARDIAN_EXIT.json', {'status': 'cleaned_after_interruption' if ok else 'cleanup_failed',
            'reason': reason, 'guardian': guardian, 'plan_sha256': digest(root / 'PLAN.json'),
            'grading_allowed': False, 'accounting_finalized': False})
    finally:
        if parent is not None:
            os.close(parent)


async def launch(root, plan, run):
    guardian = validate_plan(plan)
    argv = ['systemd-run', '--user', '--quiet', '--collect', '--service-type=exec',
            '--unit=' + guardian['unit'], '--working-directory=' + str(Path(__file__).resolve().parent.parent),
            '--property=RuntimeMaxSec=' + str(math.ceil(plan['request']['budget']['seconds'] + 180)),
            sys.executable, '-m', 'worldlab.fluso_guardian', '--root', str(root)]
    save(root / 'GUARDIAN_LAUNCH_INTENT.json', {'argv': argv, 'guardian': guardian})
    save(root / 'GUARDIAN_LAUNCH_RESULT.json', await run(argv))
    for _ in range(100):
        if (root / 'GUARDIAN_READY.json').exists():
            ready = read(root / 'GUARDIAN_READY.json')
            if ready['guardian'] != guardian or ready['plan_sha256'] != digest(root / 'PLAN.json'):
                raise ValueError('Guardian ready receipt differs from execution plan')
            return
        await asyncio.sleep(.1)
    raise RuntimeError('Independent cleanup guardian did not become ready')


async def disarm(root, plan):
    save(root / 'GUARDIAN_DISARM.json', {'plan_sha256': digest(root / 'PLAN.json'),
        'cleanup_sha256': digest(root / 'CLEANUP.json'), 'result_sha256': digest(root / 'RESULT.json')})
    for _ in range(150):
        if (root / 'GUARDIAN_EXIT.json').exists():
            audit_disarm(root, plan)
            return
        await asyncio.sleep(.1)
    raise RuntimeError('Independent cleanup guardian did not acknowledge removal')


def audit_disarm(root, plan):
    expected = {'status': 'disarmed', 'guardian': validate_plan(plan), 'plan_sha256': digest(root / 'PLAN.json')}
    if read(root / 'GUARDIAN_EXIT.json') != expected or not disarm_valid(root, plan):
        raise ValueError('Guardian did not acknowledge clean native completion')
    if (root / 'GUARDIAN_INTERVENTION.json').exists():
        raise ValueError('Guardian interruption cannot be graded as completion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    supervise(parser.parse_args().root)
