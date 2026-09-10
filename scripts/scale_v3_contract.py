"""Immutable six-world follow-up design; registration is not an execution audit.

The historical scale-v1 launcher and acceptance contract are deliberately not
used to dispatch this new configuration. No credentials or models are loaded.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from lifespan.evaluation.protocol import digest
from scripts.run_scale import ALGORITHMS, BUDGETS, DESIGN, SEEDS, study_config
from scripts.scale_v2_contract import REGISTRATION_TOOLS as V2_TOOLS

VERSION = 'scale-v3-six-world-registration'
POPULATION = {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1}
ACTOR_CONTRACT = {'version': 'actor-json-v1', 'max_output_tokens': 4096, 'timeout_seconds': 120}
EVIDENCE_KINDS = ('actor_native_capability', 'employee_native_capability', 'horizon_feasibility',
                  'scope_startup_qualification', 'employee_source_compatibility')
REGISTRATION_TOOLS = tuple(dict.fromkeys((*V2_TOOLS,
    'scripts/scale_v3_contract.py', 'scripts/prepare_scale_v3.py',
    'scripts/run_scale_v3_inner.py', 'scripts/run_scale_v3.py', 'scripts/audit_scale_v3.py',
    'scripts/scale_v3_prerequisites.py',
    'scripts/hermes_startup_scope_qualification.py', 'scripts/hermes_startup_scope_qualification_v3.py',
    'scripts/hermes_startup_qualification.py',
    'scripts/hermes_startup_probe.py', 'scripts/startup_resource_controls.py',
    # Freeze the intended endpoint projection and its transitive local helpers
    # before outcomes, as well as recording their bytes when reporting runs.
    'scripts/report_scale_v3.py', 'scripts/report_scale_v2.py', 'scripts/report_scale.py',
    'scripts/scale_world_dynamics.py', 'scripts/audit_scale_cli.py',
    'scripts/audit_calibration.py', 'scripts/calibration_bank.py',
    'scripts/transfer_analysis.py', 'scripts/transfer_probes.py')))
LAUNCH_LIMITS = {'world_cleanup_seconds': 120, 'service_cleanup_seconds': 30,
                'service_startup_seconds': 120, 'observation_interval_seconds': 0.25}
# One shared campaign ceiling, not separate world or service reservations.
SCOPE_LIMITS = {'memory_max_bytes': 12 * 1024**3, 'memory_swap_max_bytes': 0,
    'tasks_max': 512, 'cpu_quota_percent': 400, 'cpu_quota_period_usec': 100000,
    'cpu_max_usec': 400000, 'controller_startup_seconds': 120,
    'execution_seconds': 3 * (86400 + 120) + 120 + 30 + 600,
    'cleanup_seconds': 180, 'runtime_max_seconds': 260490, 'timeout_stop_seconds': 5}
DISPATCH_POLICY = 'fixed_pair_waves_stop_on_infrastructure_failure'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def same(a, b):
    # Distinguish JSON booleans from numeric caps and exact serialized config.
    return digest(a) == digest(b)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def policy(value):
    require(type(value) is dict and set(value) == {'per_world_wall_seconds', 'workers',
            'mirofish_service_url', 'wall_budget_rationale', 'evidence', 'scope_limits',
            'dispatch_policy'}, 'v3_policy_fields')
    require(type(value['per_world_wall_seconds']) is int and value['per_world_wall_seconds'] == 86400,
            'v3_wall_budget_requires_explicit_positive_seconds')
    require(type(value['workers']) is int and value['workers'] == 2, 'v3_parallel_world_limit')
    require(type(value['wall_budget_rationale']) is str and 20 <= len(value['wall_budget_rationale']) <= 4000,
            'v3_wall_budget_requires_evidence_rationale')
    # The first-class config validator owns URL normalization. Never silently
    # send these new worlds to the historical service on port 5001.
    configured = replace(study_config(SEEDS[0], ALGORITHMS[0]),
                         mirofish_service_url=value['mirofish_service_url'])
    require(configured.mirofish_service_url is not None and
            configured.mirofish_service_url == value['mirofish_service_url'], 'v3_service_url_not_canonical')
    require(urlsplit(configured.mirofish_service_url).port != 5001, 'v3_requires_separate_service')
    require(same(value['scope_limits'], SCOPE_LIMITS) and
            value['dispatch_policy'] == DISPATCH_POLICY, 'v3_fixed_scope_and_dispatch_policy')
    evidence = value['evidence']
    require(type(evidence) is list and len(evidence) == len(EVIDENCE_KINDS) and
            [row.get('kind') for row in evidence if type(row) is dict] == list(EVIDENCE_KINDS),
            'v3_prerequisite_reference_inventory')
    for row in evidence:
        require(set(row) == {'kind', 'artifact_sha256', 'review_sha256'}, 'v3_prerequisite_reference_fields')
        require(all(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}', row[key])
                    for key in ('artifact_sha256', 'review_sha256')), 'v3_prerequisite_reference_hash')
    return deepcopy(value)


def config(seed, algorithm, launch_policy):
    p = policy(launch_policy)
    return replace(study_config(seed, algorithm), max_run_seconds=p['per_world_wall_seconds'],
        actor_output_contract=deepcopy(ACTOR_CONTRACT), hermes_transport='nonstreaming',
        mirofish_service_url=p['mirofish_service_url'], hermes_startup_observability=True)


def schedule():
    return [(seed, algorithm) for i, seed in enumerate(SEEDS)
            for algorithm in (ALGORITHMS if i % 2 == 0 else ALGORITHMS[::-1])]


def pair_waves():
    return [[f'seed-{seed}-{arm}' for seed, arm in schedule()[i:i+2]] for i in (0, 2, 4)]


def budgets(launch_policy):
    p = policy(launch_policy)
    return {**deepcopy(BUDGETS), 'max_parallel_worlds': p['workers'],
            'per_world_wall_seconds': p['per_world_wall_seconds'],
            'launch_limits': deepcopy(LAUNCH_LIMITS), 'scope_limits': deepcopy(SCOPE_LIMITS),
            'pair_waves': pair_waves(),
            'contracted_interview_physical_requests': 3972,
            'contracted_interview_output_tokens_per_request': 4096,
            'contracted_interview_timeout_seconds': 120}


def design():
    return {**deepcopy(DESIGN),
        'actor_compute': 'Contracted interviews have per-request physical/usage receipts and caps; '
                         'bootstrap and social calls remain outside this meter.',
        'development_reuse': 'All three scale-v1 seeds and paired cohorts are reused in six fresh '
                             'worlds; this is development evidence, not held-out confirmation.',
        'completion': 'All six fresh worlds and all three valid complete pairs; no surviving-pair endpoint.',
        'adoption': 'No minimum adoption count or positive learning gain is required.',
        'execution_envelope': 'One shared scope: no per-world fairness or guaranteed I/O isolation.',
        'dispatch': 'Three fixed pair waves; both prior worlds must exit normally with confirmed '
                    'cleanup before the next wave. No failed replacements or rolling refill.',
        'startup_observability': 'Enabled in both arms and all replays; diagnostic stages do not score work.',
        'prerequisites': 'References bind independently reviewed evidence. Registration validation '
                         'does not re-audit native capability or certify execution readiness.'}


def model_metadata(model, base_url):
    require(type(model) is str and 0 < len(model.strip()) <= 200 and
            not any(c in model for c in '\r\n'), 'v3_model_name')
    require(type(base_url) is str and not any(c.isspace() for c in base_url), 'v3_provider_url')
    parsed = urlsplit(base_url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname and
            not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            'v3_provider_url_must_not_contain_credentials')


def child(root, relative):
    require(type(relative) is str and relative and not Path(relative).is_absolute(), 'v3_relative_path')
    path = root / relative
    require('..' not in Path(relative).parts and path.resolve().is_relative_to(root.resolve()) and
            not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), 'v3_path_escape_or_symlink')
    return path


def validate(directory, *, source_sha256, dependencies, registration_tools_sha256,
             campaign_sha256, target_model=None, model_base_url=None, require_pristine=True):
    """Revalidate the frozen design and bytes, not native prerequisite results."""
    root = Path(directory).resolve()
    manifest_path = child(root, 'campaign.json')
    require(type(campaign_sha256) is str and re.fullmatch('[0-9a-f]{64}', campaign_sha256) and
            sha(manifest_path) == campaign_sha256, 'v3_reviewed_campaign_hash_mismatch')
    manifest = read(manifest_path)
    require(set(manifest) == {'schema_version', 'kind', 'created_at', 'seeds', 'algorithms', 'population',
            'days', 'budgets', 'design', 'source_sha256', 'dependencies', 'registration_tools_sha256',
            'target_model', 'model_base_url', 'launch_policy', 'slots'}, 'v3_registration_fields')
    p = policy(manifest['launch_policy'])
    fixed = {'schema_version': 3, 'kind': VERSION, 'seeds': SEEDS, 'algorithms': ALGORITHMS,
        'population': POPULATION, 'days': 20, 'budgets': budgets(p), 'design': design(),
        'source_sha256': source_sha256, 'dependencies': dependencies,
        'registration_tools_sha256': registration_tools_sha256}
    require(all(same(manifest.get(key), value) for key, value in fixed.items()), 'v3_registration_contract_changed')
    model_metadata(manifest['target_model'], manifest['model_base_url'])
    if target_model is not None or model_base_url is not None:
        require((manifest['target_model'], manifest['model_base_url']) ==
                (target_model, model_base_url), 'v3_provider_changed')
    slots = manifest['slots']
    require(type(slots) is list and len(slots) == 6 and
            [(s['seed'], s['algorithm']) for s in slots] == schedule(), 'v3_all_six_slots_required')
    cohorts = {}; ids_seen = set()
    for seed in SEEDS:
        path = child(root, f'cohorts/{seed}.json')
        data = read(path); ids = [row['persona_id'] for row in data['personas']]
        require(len(ids) == len(set(ids)) == 25 and not ids_seen.intersection(ids), 'v3_distinct_persona_cohorts')
        ids_seen.update(ids); cohorts[seed] = sha(path)
    for slot in slots:
        require(set(slot) == {'seed', 'algorithm', 'run_id', 'relative_path', 'config',
                'config_sha256', 'persona_cohort_sha256'}, 'v3_slot_fields')
        run_id = f"seed-{slot['seed']}-{slot['algorithm']}"
        require(slot['run_id'] == run_id and slot['relative_path'] == 'runs/' + run_id, 'v3_run_identity')
        run = child(root, slot['relative_path'])
        expected = config(slot['seed'], slot['algorithm'], p).public()
        require(same(slot['config'], expected) and same(read(child(run, 'config.json')), expected) and
                slot['config_sha256'] == digest(expected), 'v3_run_config_changed')
        require(slot['persona_cohort_sha256'] == cohorts[slot['seed']] ==
                sha(child(run, 'persona_cohort.json')), 'v3_paired_cohort_bytes_changed')
        if require_pristine:
            require({f.name for f in run.iterdir()} == {'config.json', 'persona_cohort.json'},
                    'v3_uncertain_work_must_not_be_restarted')
    require({f.name for f in child(root, 'runs').iterdir()} == {s['run_id'] for s in slots},
            'v3_unregistered_or_missing_run')
    require({f.name for f in child(root, 'cohorts').iterdir()} == {f'{s}.json' for s in SEEDS},
            'v3_unregistered_or_missing_cohort')
    if require_pristine:
        require(not any((root / name).exists() for name in ('EXECUTION.json', 'execution_results.json',
                    'SUPERVISOR_INTERRUPTED.json')), 'v3_execution_intent_already_exists')
    return manifest
