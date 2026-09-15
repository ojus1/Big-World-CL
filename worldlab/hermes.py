"""Native Hermes adapter for fully specified, offline task packages."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from scripts.source_world_calibration import save, sha
from lifespan.evaluation.hermes_transport import PIN, verify_source
from lifespan.evaluation.provider import provider_contract
from .hermes_deadline import clock_contract, validate_clock, audit_deadline, checkpoint_costs

ROOT = Path(__file__).resolve().parents[1]


def native_trajectory(native):
    return [{k: m[k] for k in ('role', 'content', 'tool_calls', 'tool_call_id', 'name') if k in m}
            for m in native.get('messages', []) if m.get('role') in ('user', 'assistant', 'tool')]


class Hermes:
    def __init__(self, hermes_root, model, base_url):
        self.root = Path(hermes_root).resolve()
        verify_source(self.root)
        self.provider = provider_contract(model, base_url)

    def identity(self):
        return {'name': 'native_hermes_task_package', 'version': 6, 'revision': PIN,
                'provider': self.provider, 'transport': 'nonstreaming',
                'sandbox': 'bubblewrap', 'state': 'fresh_profile_and_files_per_attempt',
                'nonstreaming_timeouts': 'request and stale windows are min(600 seconds, whole attempt budget)',
                'nonstreaming_watchdog': 'native no-first-SSE-event watchdog disabled by HERMES_CODEX_TTFB_TIMEOUT_SECONDS=0',
                'task_deadline': 'stop sandbox and admissions at active deadline; settle accepted inference for min(600, active_seconds)+15 seconds',
                'meter_persistence': 'atomic checkpoint before every dispatch and after every nonstreaming receipt',
                'tool_cleanup': 'pinned session and descendant PIDs; bounded pipe drain; lost sandbox execution is ungraded',
                'tool_resource_limits': 'external prlimit before bash; no Python preexec callback in threaded server',
                'tools': ['terminal', 'file', 'skills_list', 'skill_view']}

    def unsupported(self, public_task):
        reasons = []
        if public_task['source'] != 'internal_eurobench':
            reasons.append('JobBench research and document-tool capability qualification pending')
        if public_task.get('requires_app_state'):
            reasons.append('Native app-state tools not connected')
        if public_task.get('budgets', {}).get('user_turns', 0):
            reasons.append('Interactive employee channel not connected')
        formats = set(public_task['input_formats']) - {'.md', '.txt', '.csv', '.json', '.py'}
        if formats:
            reasons.append('Document runtime qualification pending: ' + ','.join(sorted(formats)))
        return reasons

    def run(self, request, artifact_root):
        artifact_root = Path(artifact_root).resolve()
        started = time.monotonic()
        clock = clock_contract(request.budget.seconds, started)
        cfg = {**asdict(request), 'workspace': str(request.workspace.resolve()),
               'provider': self.provider, 'hermes_root': str(self.root), 'execution_clock': clock}
        save(artifact_root / 'REQUEST.json', cfg)
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'USER', 'LOGNAME') if k in os.environ}
        env.update(HOME=str(artifact_root / 'home'), HERMES_HOME=str(artifact_root / 'hermes'),
                   HERMES_AGENT_ROOT=str(self.root), PYTHONPATH=f'{ROOT}:{self.root}',
                   HERMES_YOLO='1', PYTHONUNBUFFERED='1',
                   WORLDLAB_API_KEY=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'))
        Path(env['HOME']).mkdir()
        with (artifact_root / 'worker.log').open('w') as log:
            process = subprocess.Popen([str(self.root / 'venv/bin/python'), '-u', '-m',
                                        'worldlab.hermes_worker', str(artifact_root / 'REQUEST.json')],
                                       cwd=artifact_root, env=env, stdout=log, stderr=log,
                                       start_new_session=True)
            save(artifact_root / 'WORKER_START.json', {'worker_pid': process.pid, 'execution_clock': clock})
            timed_out = False
            try:
                process.wait(timeout=request.budget.seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                save(artifact_root / 'PARENT_DEADLINE.json', {'clock': clock, 'observed_monotonic': time.monotonic(),
                     'worker_pid': process.pid, 'action': 'allow bounded settlement; no new native task actions'})
                try:
                    process.wait(timeout=clock['settlement_seconds'])
                except subprocess.TimeoutExpired:
                    save(artifact_root / 'SETTLEMENT_TIMEOUT.json', {'observed_monotonic': time.monotonic(),
                         'worker_pid': process.pid, 'action': 'terminate owned worker process group'})
            finally:
                # Own process group, including sandbox/tool descendants, even after a worker error.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        ended = time.monotonic()
        elapsed = ended - started
        save(artifact_root / 'WORKER_EXIT.json', {'worker_pid': process.pid, 'execution_clock': clock,
             'returncode': process.returncode, 'ended_monotonic': ended, 'seconds': elapsed,
             'active_deadline_wait_expired': timed_out,
             'settlement_wait_expired': (artifact_root / 'SETTLEMENT_TIMEOUT.json').exists()})
        result_path = artifact_root / 'NATIVE.json'
        if not result_path.is_file():
            incomplete = {'status': 'infrastructure_ambiguous' if timed_out else 'infrastructure_error',
                    'exit_code': process.returncode, 'seconds': elapsed,
                    'charged_tokens': request.budget.total_tokens, 'accounting_complete': False,
                    'physical_model_calls': None, 'reservation_reason': 'Worker did not return a final meter'}
            path = artifact_root / 'METER_CHECKPOINT.json'
            if path.exists():
                try:
                    incomplete.update(checkpoint_costs(path, self.provider, clock, request.budget),
                                      checkpoint_sha256=sha(path))
                except (ValueError, TypeError, KeyError, OSError):
                    incomplete['checkpoint_unverified'] = True
            return incomplete
        result = json.loads(result_path.read_text())
        meter = result['evaluation_budget']
        validate_clock(result['execution_clock'], request.budget.seconds)
        audit_deadline(artifact_root, clock, result)
        status = ('infrastructure_error' if meter.get('stopped') or process.returncode or result.get('worker_error')
                  else 'infrastructure_ambiguous' if not meter['accounting_complete']
                  else 'budget_exhausted' if meter.get('exhausted') else 'completed')
        return {'status': status, 'seconds': elapsed,
                'physical_model_calls': meter['physical_model_calls'],
                'charged_tokens': meter['charged_tokens'], 'reported_tokens': meter['reported_tokens'],
                'accounting_complete': meter['accounting_complete'],
                'skill_loaded': result['skill_loaded'], 'native_sha256': sha(result_path),
                'trajectory': native_trajectory(result),
                'skill_content_sha256': hashlib.sha256(request.skill.encode()).hexdigest(),
                'skill_sha256': sha(artifact_root / 'hermes/skills/work-process/SKILL.md'),
                'exit_code': process.returncode}

    @staticmethod
    def audit_execution(artifact_root, request, receipt):
        """Check native evidence without importing or running the Hermes agent."""
        from scripts.source_world_calibration import read
        from lifespan.evaluation.runtime import skill_loaded
        root = Path(artifact_root)
        native, native_request = read(root / 'NATIVE.json'), read(root / 'REQUEST.json')
        clock = native_request['execution_clock']
        validate_clock(clock, request['budget']['seconds'])
        if native['execution_clock'] != clock or read(root / 'READY.json')['execution_clock'] != clock:
            raise ValueError('Native execution clock readback differs')
        audit_deadline(root, clock, native)
        worker_start, worker_exit = read(root / 'WORKER_START.json'), read(root / 'WORKER_EXIT.json')
        if (worker_start['execution_clock'] != clock or worker_exit['execution_clock'] != clock
                or worker_start['worker_pid'] != worker_exit['worker_pid']
                or worker_exit['returncode'] != receipt['exit_code'] or worker_exit['seconds'] != receipt['seconds']
                or worker_exit['seconds'] != worker_exit['ended_monotonic'] - clock['admitted_monotonic']
                or worker_exit['settlement_wait_expired']):
            raise ValueError('Native worker lifecycle differs from the execution receipt')
        from .hermes_worker import native_timeouts, native_watchdog_environment
        expected_timeouts = native_timeouts(request['budget'])
        if native.get('native_timeouts') != expected_timeouts or read(root / 'READY.json').get('native_timeouts') != expected_timeouts:
            raise ValueError('Native nonstreaming timeout readbacks differ from the declared policy')
        if any(record.get('native_watchdog_environment') != native_watchdog_environment()
               for record in (native, read(root / 'READY.json'))):
            raise ValueError('Native nonstreaming watchdog readbacks differ from the declared policy')
        if any(native_request[k] != value for k, value in request.items()):
            raise ValueError('Native request differs from public execution contract')
        meter = native['evaluation_budget']
        expected_status = 'budget_exhausted' if meter.get('exhausted') else 'completed'
        if receipt['status'] != expected_status or worker_exit['returncode'] or native.get('worker_error'):
            raise ValueError('Native worker did not return a qualified completion or budget exhaustion')
        if (not meter['accounting_complete'] or meter.get('stopped') or
                meter['physical_model_calls'] != len(meter['operations']) or
                meter['charged_tokens'] != sum(r['charged_tokens'] for r in meter['operations']) or
                meter['physical_model_calls'] > request['budget']['model_calls'] or
                meter['charged_tokens'] > request['budget']['total_tokens'] or
                any(r['output_cap'] > request['budget']['output_tokens'] for r in meter['operations']) or
                meter['provider_contract'] != native_request['provider']):
            raise ValueError('Native accounting or provider contract mismatch')
        skill_path = root / 'hermes/skills/work-process/SKILL.md'
        expected_file = ('---\nname: work-process\ndescription: Employee work process learned from available experience.\n---\n\n'
                         + request['skill'])
        if skill_path.read_text() != expected_file:
            raise ValueError('Installed skill differs from requested content')
        if not native['skill_loaded'] or not skill_loaded(native.get('messages', []), sha(skill_path)):
            raise ValueError('Native skill was not loaded')
        checks = {'physical_model_calls': meter['physical_model_calls'], 'charged_tokens': meter['charged_tokens'],
                  'trajectory': native_trajectory(native), 'skill_loaded': native['skill_loaded'],
                  'skill_sha256': sha(skill_path), 'native_sha256': sha(root / 'NATIVE.json'),
                  'skill_content_sha256': hashlib.sha256(request['skill'].encode()).hexdigest()}
        if any(receipt.get(k) != value for k, value in checks.items()):
            raise ValueError('Normalized receipt differs from native evidence')
