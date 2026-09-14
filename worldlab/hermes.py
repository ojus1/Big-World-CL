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
        return {'name': 'native_hermes_task_package', 'version': 2, 'revision': PIN,
                'provider': self.provider, 'transport': 'nonstreaming',
                'sandbox': 'bubblewrap', 'state': 'fresh_profile_and_files_per_attempt',
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
        cfg = {**asdict(request), 'workspace': str(request.workspace.resolve()),
               'provider': self.provider, 'hermes_root': str(self.root)}
        save(artifact_root / 'REQUEST.json', cfg)
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'USER', 'LOGNAME') if k in os.environ}
        env.update(HOME=str(artifact_root / 'home'), HERMES_HOME=str(artifact_root / 'hermes'),
                   HERMES_AGENT_ROOT=str(self.root), PYTHONPATH=f'{ROOT}:{self.root}',
                   HERMES_YOLO='1', PYTHONUNBUFFERED='1',
                   WORLDLAB_API_KEY=os.environ.get('WORLDLAB_API_KEY', 'EMPTY'))
        Path(env['HOME']).mkdir()
        started = time.monotonic()
        with (artifact_root / 'worker.log').open('w') as log:
            process = subprocess.Popen([str(self.root / 'venv/bin/python'), '-u', '-m',
                                        'worldlab.hermes_worker', str(artifact_root / 'REQUEST.json')],
                                       cwd=artifact_root, env=env, stdout=log, stderr=log,
                                       start_new_session=True)
            timed_out = False
            try:
                process.wait(timeout=request.budget.seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
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
        result_path = artifact_root / 'NATIVE.json'
        if not result_path.is_file():
            return {'status': 'infrastructure_ambiguous' if timed_out else 'infrastructure_error',
                    'exit_code': process.returncode, 'seconds': time.monotonic() - started,
                    'charged_tokens': request.budget.total_tokens, 'accounting_complete': False,
                    'physical_model_calls': None, 'reservation_reason': 'Worker did not return a final meter'}
        result = json.loads(result_path.read_text())
        meter = result['evaluation_budget']
        status = ('infrastructure_error' if meter.get('stopped') or process.returncode or result.get('worker_error')
                  else 'budget_exhausted' if meter.get('exhausted') else 'completed')
        return {'status': status, 'seconds': time.monotonic() - started,
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
        if any(native_request[k] != value for k, value in request.items()):
            raise ValueError('Native request differs from public execution contract')
        meter = native['evaluation_budget']
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
