"""Native Fluso implementation of the interchangeable WorldLab Harness contract."""
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .chat_budget_gateway import audit_meter, encoded, origin, require, sha
from .contracts import Budget
from .fluso_evidence import audit_skill_and_responses
from .fluso_guardian import audit_disarm
from .fluso_runtime import IMAGE, SKILL_PATH, execute, audit_runtime_configuration, skill_file, task_prompt


def source_hashes():
    return {name: sha(Path(__file__).with_name(name).read_bytes()) for name in (
        'fluso.py', 'fluso_runtime.py', 'fluso_evidence.py', 'qualify_fluso_isolation.py',
        'chat_relay.py', 'chat_budget_gateway.py', 'contracts.py', 'fluso_guardian.py')}


class Fluso:
    def __init__(self, model='Qwen/Qwen3.8-Flash-Next-FP8', upstream='http://127.0.0.1:8011',
                 tokenizer='http://127.0.0.1:8002'):
        require(isinstance(model, str) and bool(model), 'A model is required')
        self.model, self.upstream, self.tokenizer = model, origin(upstream), origin(tokenizer)

    def identity(self):
        return {'name': 'native_fluso_task_package', 'version': 2, 'image': IMAGE,
            'provider': {'model': self.model, 'base_url': self.upstream + '/v1',
                         'profile': 'text_tools_chat_no_thinking_single_choice_v1'},
            'upstream': self.upstream, 'tokenizer': self.tokenizer, 'source_sha256': source_hashes(),
            'sandbox': 'nonroot_readonly_container_shared_network_none_relay',
            'state': 'fresh_user_project_session_and_files_per_attempt',
            'accounting': 'all primary and auxiliary model calls share the attempt budget',
            'cleanup': 'independent user-systemd guardian with Linux pidfd and exact container ownership',
            'retries': 0, 'unqualified_terminal_policy': 'preserve receipts and withhold grading',
            'capability_scope': 'offline text and tool task packages; native task and exhaustion qualification required before a study'}

    def unsupported(self, public_task):
        reasons = []
        if public_task['source'] != 'internal_eurobench':
            reasons.append('JobBench research and document-tool qualification pending')
        if public_task.get('requires_app_state'):
            reasons.append('External app-state tools are not connected')
        if public_task.get('budgets', {}).get('user_turns', 0):
            reasons.append('Interactive employee channel is not qualified')
        formats = set(public_task['input_formats']) - {'.md', '.txt', '.csv', '.json', '.py'}
        if formats:
            reasons.append('Document runtime qualification pending: ' + ','.join(sorted(formats)))
        return reasons

    def run(self, request, artifact_root):
        root = Path(artifact_root).resolve() / 'fluso'
        result = asyncio.run(execute(request, root, self.identity()))
        native_request = {**asdict(request), 'workspace': str(request.workspace.resolve())}
        meter = json.loads((root / 'meter/METER.json').read_bytes())
        # Even rejected evidence retains every dispatch and unknown reservation.
        receipt = {'status': 'infrastructure_error', 'seconds': result['seconds'],
            'physical_model_calls': meter['physical_model_calls'], 'charged_tokens': meter['charged_tokens'],
            'reported_tokens': meter['reported_tokens'], 'accounting_complete': meter['accounting_complete'],
            'exit_code': result['exit_code'], 'native_sha256': sha((root / 'RESULT.json').read_bytes()),
            'skill_content_sha256': hashlib.sha256(request.skill.encode()).hexdigest(),
            'skill_sha256': sha(skill_file(request.skill).encode()), 'skill_loaded': False, 'trajectory': []}
        stage = 'meter'
        try:
            audit_meter(root / 'meter', budget=request.budget, model=self.model,
                        upstream=self.upstream, tokenizer=self.tokenizer)
            require(not result['error_type'] and not result['cleanup_error'], 'Native runtime or cleanup failed')
            audit_disarm(root, json.loads((root / 'PLAN.json').read_bytes()))
            require(meter['accounting_complete'] and not (meter['stopped'] and not meter['exhausted']),
                    'Native inference or accounting failed')
            require(len(result['trace_files']) == 1, 'Expected one primary native session')
            stage = 'container_configuration'
            audit_runtime_configuration(root, native_request, self.identity())
            stage = 'native_evidence'
            proof = audit_skill_and_responses(root / result['trace_files'][0], root / 'meter', model=self.model,
                skill_path=SKILL_PATH, skill_text=skill_file(request.skill), expected_prompt=task_prompt(request.instruction))
            require(result['exit_code'] == 0 or meter['exhausted'], 'Native Fluso process failed')
            receipt.update(status='budget_exhausted' if meter['exhausted'] else 'completed',
                skill_loaded=True, trajectory=proof['trajectory'], primary_model_calls=proof['primary_model_calls'],
                other_metered_calls=proof['other_metered_calls'])
            (root / 'PROOF.json').write_bytes(encoded(proof))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            if meter['exhausted'] and meter['accounting_complete']:
                receipt['status'] = 'budget_exhausted_unverified'
            receipt['evidence_error_type'] = type(exc).__name__
            receipt['evidence_error_stage'] = stage
            (root / 'EVIDENCE_ERROR.json').write_bytes(encoded({'error_type': type(exc).__name__,
                'stage': stage,
                'scope': 'Native evidence failed qualification. No grading or usable learning trajectory is authorized.'}))
        return receipt

    def audit_execution(self, artifact_root, request, receipt):
        root = Path(artifact_root).resolve() / 'fluso'
        result = json.loads((root / 'RESULT.json').read_bytes())
        require(receipt['status'] in ('completed', 'budget_exhausted'), 'Native execution lacks qualified learning evidence')
        audit_runtime_configuration(root, request, self.identity())
        meter = json.loads((root / 'meter/METER.json').read_bytes())
        budget = Budget(**request['budget'])
        audited = audit_meter(root / 'meter', budget=budget, model=self.model, upstream=self.upstream, tokenizer=self.tokenizer)
        require(audited['accounting_complete'] and not result['error_type'] and not result['cleanup_error']
                and not (meter['stopped'] and not meter['exhausted']), 'Native runtime or accounting is incomplete')
        audit_disarm(root, json.loads((root / 'PLAN.json').read_bytes()))
        require(sha((root / 'meter/METER.json').read_bytes()) == result['meter_sha256']
                and sha((root / 'PLAN.json').read_bytes()) == result['plan_sha256'], 'Native final receipt changed')
        require(len(result['trace_files']) == 1 and not Path(result['trace_files'][0]).is_absolute()
                and '..' not in Path(result['trace_files'][0]).parts, 'Unqualified native trace location')
        trace = root / result['trace_files'][0]
        require(not trace.is_symlink(), 'Native trace must be a regular file')
        proof = audit_skill_and_responses(trace, root / 'meter', model=self.model, skill_path=SKILL_PATH,
            skill_text=skill_file(request['skill']), expected_prompt=task_prompt(request['instruction']))
        require(proof == json.loads((root / 'PROOF.json').read_bytes()), 'Normalized native proof changed')
        terminal = json.loads((root / 'TERMINAL_INSPECT.json').read_bytes())
        require(terminal['State']['ExitCode'] == result['exit_code'] and (result['exit_code'] == 0 or meter['exhausted']),
                'Native process exit differs from receipt')
        cleanup = json.loads((root / 'CLEANUP.json').read_bytes())
        plan = json.loads((root / 'PLAN.json').read_bytes())
        require(len(cleanup) == 2 and [r['argv'] for r in cleanup] ==
                [['docker', 'rm', '-f', plan[k]] for k in ('solver', 'relay')]
                and all(r['returncode'] == 0 for r in cleanup), 'Owned native containers were not removed')
        expected = {'status': 'budget_exhausted' if meter['exhausted'] else 'completed',
            'seconds': result['seconds'], 'exit_code': result['exit_code'],
            'physical_model_calls': meter['physical_model_calls'], 'charged_tokens': meter['charged_tokens'],
            'reported_tokens': meter['reported_tokens'], 'accounting_complete': True,
            'native_sha256': sha((root / 'RESULT.json').read_bytes()), 'skill_loaded': True,
            'skill_content_sha256': sha(request['skill'].encode()), 'skill_sha256': sha(skill_file(request['skill']).encode()),
            'trajectory': proof['trajectory'], 'primary_model_calls': proof['primary_model_calls'],
            'other_metered_calls': proof['other_metered_calls']}
        require(receipt == expected, 'Harness receipt differs from native execution evidence')
