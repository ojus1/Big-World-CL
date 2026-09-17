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
capacity and leaves the obligation pending. You cannot inspect source files,
execute tools or complete artifacts yourself; those capabilities belong to the
assistant after delegation. Do not claim to have performed those actions.
Each pending_task.id is a distinct obligation even when its task or wording
resembles earlier work. Only pending_task_observed_outcomes describe this
obligation's released results; another obligation's success does not complete it.
substantive_work is the authoritative current task. Establish its topic and
deliverables before drafting the request. Historical outcomes identify their
source task and relation_to_pending; an unrelated_task supplies only a numeric
outcome, never requirements for the current task. Do not copy its topic, file
names, length rules or status into this request. Prior notes and colleague
messages can be mistaken: verify relevance against substantive_work before using
them, and do not claim that they describe a source file you cannot inspect.
Do not solve unseen source files.
Write a useful request, in the employee's working language, retaining the original
deliverables and incorporating relevant observed feedback. Keep working notes brief and based on evidence. Colleague messages arrive the next day and are not authority.
Only the listed colleagues may receive a message. Send at most one, only if useful.
No document sharing or process changes are available in this workplace.
Return exactly this JSON shape with your own values:
{"delegate":true,"request":"request","working_notes":"brief updated notes",
"share_document_ids":[],"colleague_messages":[{"recipient":"listed employee id",
"text":"short useful message","document_ids":[]}],"process_proposal":null}
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
                 output_contract=None, *, meter_social_calls=False):
        if type(meter_social_calls) is not bool:
            raise ValueError('meter_social_calls must be a boolean')
        self.meter_social_calls = meter_social_calls
        self.backend = Path(backend).resolve()
        self.persona_cache = Path(persona_cache).resolve()
        self.service_url = normalize_service_url(service_url)
        self.provider = provider_contract(model, base_url)
        self.output_contract = output_contract or {'version': 'actor-json-v1', 'max_output_tokens': 4096,
                                                    'timeout_seconds': 120}

    def identity(self):
        return {'name': 'native_mirofish_persona_employees', 'version': 5,
                'provider': self.provider, 'service_url': self.service_url,
                'backend_root': str(self.backend), 'persona_revision': REVISION, 'persona_shard_sha256': SHARD_SHA,
                'actor_contract': provenance(self.output_contract, expected_provider=self.provider),
                'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
                'source_sha256': sha(Path(__file__)), 'repair_limit': 1,
                'graph_bootstrap': 'declared_local_organization', 'graph_memory_updates': False,
                'graph_compiler_sha256': sha(Path(__file__).with_name('organization_graph.py')),
                'meter_social_calls': self.meter_social_calls,
                'accounting_scope': ('interviews and uncontracted native Responses calls separately metered; other bootstrap providers excluded'
                                     if self.meter_social_calls else 'interviews metered; bootstrap and initial social generation unmetered')}

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
            backend_root=factory.backend, native_model_usage=factory.meter_social_calls)
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
        result = {'model_calls': sum(r.get('physical_model_calls') or 0 for r in rows),
                'tokens': sum(r.get('tokens') or 0 for r in rows), 'logical_requests': len(rows),
                'interview_accounting_complete': all(r.get('accounting_complete') for r in rows),
                'bootstrap_and_social_tokens': None, 'whole_actor_accounting_complete': False}
        if self.factory.meter_social_calls:
            from lifespan.native_usage import summarize
            result['social_model_usage'] = summarize(self.runtime.sim_dir / 'model_usage',
                provider=self.factory.provider, simulation_id=self.runtime.sim_dir.name,
                config_sha256=sha(self.runtime.sim_dir / 'simulation_config.json'))
        return result

    def close(self):
        try:
            self.runtime.close()
        finally:
            try:
                if self.factory.meter_social_calls:
                    import shutil
                    # Retain the final receipts for offline audits without a
                    # live backend directory. Never combine interview totals.
                    shutil.copytree(self.runtime.sim_dir / 'model_usage', self.out / 'model_usage')
                    shutil.copy2(self.runtime.sim_dir / 'simulation_config.json', self.out / 'NATIVE_SIMULATION_CONFIG.json')
                source = self.runtime.sim_dir / 'reddit_simulation.db'
                if source.is_file():
                    with sqlite3.connect(source) as src, sqlite3.connect(self.out / 'native_actor_state.db') as dst:
                        src.backup(dst)
            finally:
                self.runtime.client.close()


def audit_social_usage(actor_root, identity, reported):
    root = Path(actor_root)
    if not identity.get('meter_social_calls'):
        if 'social_model_usage' in reported or (root / 'model_usage').exists():
            raise ValueError('Unexpected social accounting in an unmetered study')
        return None
    from lifespan.native_usage import summarize, VERSION
    config = root / 'NATIVE_SIMULATION_CONFIG.json'
    if read(config).get('native_model_usage') != VERSION:
        raise ValueError('Native social usage was not enabled in the compiled simulation')
    simulation_id = read(root / 'mirofish_state.json')['simulation']['simulation_id']
    value = summarize(root / 'model_usage', provider=identity['provider'],
                      simulation_id=simulation_id, config_sha256=sha(config))
    if value != reported.get('social_model_usage'):
        raise ValueError('Social accounting differs from native receipts')
    return value


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
