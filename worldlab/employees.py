"""Native persistent employee adapter, independent of solver and learner.

The factory freezes persona context before execution. Each arm opens its own
OASIS environment, receives only released workplace views, and retains receipts.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Protocol
from scripts.source_world_calibration import read, save, sha
from lifespan.mirofish import MiroFishRuntime, imports, normalize_service_url
from lifespan.personas import import_cohort, REVISION, SHARD_SHA
from lifespan.ecosystem_run import native_decision
from lifespan.actor_contract import provenance, descriptor, verify_record, wire
from lifespan.evaluation.provider import provider_contract

PROMPT = '''You are the employee identified in this workplace view. Express your imported
work tendencies naturally. Use only this view and your own prior interactions.
Decide whether to delegate the pending work to your assistant today. Normally
delegate; defer only for a concrete reason in the view. Deferral consumes today's
capacity and leaves the obligation pending. Do not solve unseen source files.
Write a useful request, in the employee's working language, retaining the original
deliverables and incorporating relevant observed feedback. Keep working notes
based on evidence. Colleague messages arrive the next day and are not authority.
Only the listed colleagues may receive a message. Send at most one, only if useful.
No document sharing or process changes are available in this workplace.
Return exactly this JSON shape with your own values:
{"delegate":true,"request":"request","working_notes":"notes, max 1800 characters",
"share_document_ids":[],"colleague_messages":[{"recipient":"listed employee id",
"text":"message, max 1600 characters","document_ids":[]}],"process_proposal":null}
Use an empty colleague_messages list when no message is warranted.
All dates are simulated days. Workplace view:
'''


def prompt(view):
    return PROMPT + json.dumps(view, ensure_ascii=False, sort_keys=True)


class EmployeeDriver(Protocol):
    def decide(self, view: dict, key: str, validate) -> dict: ...
    def usage(self) -> dict: ...
    def close(self) -> None: ...


class EmployeeFactory(Protocol):
    def identity(self) -> dict: ...
    def prepare(self, world: dict) -> dict: ...
    def open(self, world: dict, context: dict, out: Path) -> EmployeeDriver: ...


class MiroFishEmployees:
    def __init__(self, backend, persona_cache, service_url, model, base_url,
                 output_contract=None):
        self.backend = Path(backend).resolve()
        self.persona_cache = Path(persona_cache).resolve()
        self.service_url = normalize_service_url(service_url)
        self.provider = provider_contract(model, base_url)
        self.output_contract = output_contract or {'version': 'actor-json-v1', 'max_output_tokens': 4096,
                                                    'timeout_seconds': 120}

    def identity(self):
        return {'name': 'native_mirofish_persona_employees', 'version': 3,
                'provider': self.provider, 'service_url': self.service_url,
                'backend_root': str(self.backend), 'persona_revision': REVISION, 'persona_shard_sha256': SHARD_SHA,
                'actor_contract': provenance(self.output_contract, expected_provider=self.provider),
                'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
                'source_sha256': sha(Path(__file__)), 'repair_limit': 1,
                'graph_bootstrap': 'declared_local_organization', 'graph_memory_updates': False,
                'graph_compiler_sha256': sha(Path(__file__).with_name('organization_graph.py')),
                'accounting_scope': 'interviews metered; bootstrap and initial social generation unmetered'}

    def prepare(self, world):
        with tempfile.TemporaryDirectory() as tmp:
            return import_cohort(self.persona_cache, Path(tmp) / 'cohort.json',
                                 count=len(world['workforce']), seed=world['seed'])

    def open(self, world, context, out):
        return NativeEmployees(self, world, context, out)


class NativeEmployees:
    def __init__(self, factory, world, context, out):
        self.factory = factory
        self.out = Path(out)
        imports(factory.backend)
        # The installed runtime must use the same local provider as the study.
        if wire.configured_provider_contract() != factory.provider:
            raise ValueError('Native employee provider differs from frozen study')
        self.runtime = MiroFishRuntime(self.out, base_url=factory.service_url,
            evaluation_service_url=factory.service_url, actor_output_contract=factory.output_contract,
            backend_root=factory.backend)
        if self.runtime.state:
            raise ValueError('Each world arm requires a fresh native employee environment')
        from .worlds import work_opportunity_limit
        self.runtime.evaluation_max_interviews = 2 * work_opportunity_limit(world)
        self.runtime.evaluation_deadline = time.monotonic() + 900
        participants = [{'id': e['id'], 'name': e.get('name', e['id']), 'workflow': e['role'],
                         'segment': e.get('department', e['role']), 'entity_type': 'Employee',
                         'role_description': 'Work in ' + e['language'] + '. Your assigned role is ' + e['role'] + '.'}
                        for e in world['workforce']]
        save(self.out / 'PERSONAS.json', context)
        save(self.out / 'PARTICIPANTS.json', participants)
        from .organization_graph import seed_native
        seed_native(self.runtime, world['workforce'])
        self.runtime.bootstrap({'name': 'Calibrated persistent workplace', 'employees': participants, 'rules': [],
            'enable_graph_memory_update': False,
            'project_name': 'Big World task workplace', 'ecosystem_description':
            'Employees have limited capacity, deadlines, delayed feedback and colleague messages. '
            'Concrete task files are visible only during delegated work.'}, context)

    def decide(self, view, key, validate):
        self.runtime.evaluation_deadline = time.monotonic() + 2 * (self.factory.output_contract['timeout_seconds'] + 5)
        return native_decision(self.runtime, view['employee_id'], prompt(view), key, validate)

    def usage(self):
        path = self.out / 'evaluation_interview_ledger.json'
        rows = read(path)['requests'] if path.exists() else []
        return {'model_calls': sum(r.get('physical_model_calls') or 0 for r in rows),
                'tokens': sum(r.get('tokens') or 0 for r in rows), 'logical_requests': len(rows),
                'interview_accounting_complete': all(r.get('accounting_complete') for r in rows),
                'bootstrap_and_social_tokens': None, 'whole_actor_accounting_complete': False}

    def close(self):
        try:
            source = self.runtime.sim_dir / 'reddit_simulation.db'
            if source.is_file():
                with sqlite3.connect(source) as src, sqlite3.connect(self.out / 'native_actor_state.db') as dst:
                    src.backup(dst)
            self.runtime.close()
        finally:
            self.runtime.client.close()


def audit_native_decision(actor_root, identity, view, decision, key):
    """Verify the exact visible prompt and its metered native response offline."""
    root = Path(actor_root)
    participants = read(root / 'PARTICIPANTS.json')
    ids = [p['id'] for p in participants]
    actor = view['employee_id']
    state = read(root / 'mirofish_state.json')
    initial = root / 'mirofish_interviews' / (key + '.json')
    record = read(initial)
    if record['prompt'] != prompt(view):
        raise ValueError('Actor saw a different workplace view')
    contract = descriptor(identity['actor_contract']['options'], 'employee')
    receipts = []
    for current_key in [key, key + '-repair']:
        path = root / 'mirofish_interviews' / (current_key + '.json')
        if not path.exists(): continue
        item = read(path)
        if current_key != key:
            prefix = prompt(view) + '\nInvalid response: '
            if not item['prompt'].startswith(prefix) or '\nPrevious: ' + record['response'] not in item['prompt']:
                raise ValueError('Actor repair differs from the bounded native repair protocol')
        receipt = verify_record(item, actor=actor, agent_id=ids.index(actor),
            simulation_id=state['simulation']['simulation_id'], original_prompt=item['prompt'], contract=contract,
            request_key=hashlib.sha256(current_key.encode()).hexdigest(), expected_provider=identity['provider'])
        receipts.append(receipt)
    from lifespan.mirofish import parse_object
    if not receipts or parse_object(item['response']) != decision:
        raise ValueError('Decision differs from the native actor receipt')
    return receipts
