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

VERSION = 'scale-v2-six-world-registration'
POPULATION = {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1}
ACTOR_CONTRACT = {'version': 'actor-json-v1', 'max_output_tokens': 4096, 'timeout_seconds': 120}
EVIDENCE_KINDS = ('actor_native_capability', 'employee_native_capability', 'horizon_feasibility')
REGISTRATION_TOOLS = ('scripts/scale_v2_contract.py', 'scripts/prepare_scale_v2.py',
    'scripts/run_scale_v2.py', 'scripts/scale_v2_process.py', 'scripts/audit_scale_v2.py',
    'scripts/scale_v2_prerequisites.py', 'scripts/audit_hermes_readback_v2.py',
    'scripts/audit_hermes_preflight.py', 'scripts/hermes_transport_preflight.py',
    'scripts/hermes_preflight_process.py', 'scripts/scale_horizon_observations.py')
LAUNCH_LIMITS = {'world_cleanup_seconds': 120, 'service_cleanup_seconds': 30,
                'service_startup_seconds': 120, 'observation_interval_seconds': 0.25}


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
            'mirofish_service_url', 'wall_budget_rationale', 'evidence'}, 'v2_policy_fields')
    require(type(value['per_world_wall_seconds']) is int and value['per_world_wall_seconds'] > 0,
            'v2_wall_budget_requires_explicit_positive_seconds')
    require(type(value['workers']) is int and 1 <= value['workers'] <= 6, 'v2_parallel_world_limit')
    require(type(value['wall_budget_rationale']) is str and 20 <= len(value['wall_budget_rationale']) <= 4000,
            'v2_wall_budget_requires_evidence_rationale')
    # The first-class config validator owns URL normalization. Never silently
    # send these new worlds to the historical service on port 5001.
    configured = replace(study_config(SEEDS[0], ALGORITHMS[0]),
                         mirofish_service_url=value['mirofish_service_url'])
    require(configured.mirofish_service_url is not None and
            configured.mirofish_service_url == value['mirofish_service_url'], 'v2_service_url_not_canonical')
    require(urlsplit(configured.mirofish_service_url).port != 5001, 'v2_requires_separate_service')
    evidence = value['evidence']
    require(type(evidence) is list and len(evidence) == 3 and
            [row.get('kind') for row in evidence if type(row) is dict] == list(EVIDENCE_KINDS),
            'v2_prerequisite_reference_inventory')
    for row in evidence:
        require(set(row) == {'kind', 'artifact_sha256', 'review_sha256'}, 'v2_prerequisite_reference_fields')
        require(all(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}', row[key])
                    for key in ('artifact_sha256', 'review_sha256')), 'v2_prerequisite_reference_hash')
    return deepcopy(value)


def config(seed, algorithm, launch_policy):
    p = policy(launch_policy)
    return replace(study_config(seed, algorithm), max_run_seconds=p['per_world_wall_seconds'],
        actor_output_contract=deepcopy(ACTOR_CONTRACT), hermes_transport='nonstreaming',
        mirofish_service_url=p['mirofish_service_url'])


def schedule():
    return [(seed, algorithm) for i, seed in enumerate(SEEDS)
            for algorithm in (ALGORITHMS if i % 2 == 0 else ALGORITHMS[::-1])]


def budgets(launch_policy):
    p = policy(launch_policy)
    return {**deepcopy(BUDGETS), 'max_parallel_worlds': p['workers'],
            'per_world_wall_seconds': p['per_world_wall_seconds'],
            'launch_limits': deepcopy(LAUNCH_LIMITS),
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
        'prerequisites': 'References bind independently reviewed evidence. Registration validation '
                         'does not re-audit native capability or certify execution readiness.'}


def model_metadata(model, base_url):
    require(type(model) is str and 0 < len(model.strip()) <= 200 and
            not any(c in model for c in '\r\n'), 'v2_model_name')
    require(type(base_url) is str and not any(c.isspace() for c in base_url), 'v2_provider_url')
    parsed = urlsplit(base_url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname and
            not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            'v2_provider_url_must_not_contain_credentials')


def child(root, relative):
    require(type(relative) is str and relative and not Path(relative).is_absolute(), 'v2_relative_path')
    path = root / relative
    require('..' not in Path(relative).parts and path.resolve().is_relative_to(root.resolve()) and
            not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), 'v2_path_escape_or_symlink')
    return path


def validate(directory, *, source_sha256, dependencies, registration_tools_sha256,
             campaign_sha256, target_model=None, model_base_url=None, require_pristine=True):
    """Revalidate the frozen design and bytes, not native prerequisite results."""
    root = Path(directory).resolve()
    manifest_path = child(root, 'campaign.json')
    require(type(campaign_sha256) is str and re.fullmatch('[0-9a-f]{64}', campaign_sha256) and
            sha(manifest_path) == campaign_sha256, 'v2_reviewed_campaign_hash_mismatch')
    manifest = read(manifest_path)
    require(set(manifest) == {'schema_version', 'kind', 'created_at', 'seeds', 'algorithms', 'population',
            'days', 'budgets', 'design', 'source_sha256', 'dependencies', 'registration_tools_sha256',
            'target_model', 'model_base_url', 'launch_policy', 'slots'}, 'v2_registration_fields')
    p = policy(manifest['launch_policy'])
    fixed = {'schema_version': 2, 'kind': VERSION, 'seeds': SEEDS, 'algorithms': ALGORITHMS,
        'population': POPULATION, 'days': 20, 'budgets': budgets(p), 'design': design(),
        'source_sha256': source_sha256, 'dependencies': dependencies,
        'registration_tools_sha256': registration_tools_sha256}
    require(all(same(manifest.get(key), value) for key, value in fixed.items()), 'v2_registration_contract_changed')
    model_metadata(manifest['target_model'], manifest['model_base_url'])
    if target_model is not None or model_base_url is not None:
        require((manifest['target_model'], manifest['model_base_url']) ==
                (target_model, model_base_url), 'v2_provider_changed')
    slots = manifest['slots']
    require(type(slots) is list and len(slots) == 6 and
            [(s['seed'], s['algorithm']) for s in slots] == schedule(), 'v2_all_six_slots_required')
    cohorts = {}; ids_seen = set()
    for seed in SEEDS:
        path = child(root, f'cohorts/{seed}.json')
        data = read(path); ids = [row['persona_id'] for row in data['personas']]
        require(len(ids) == len(set(ids)) == 25 and not ids_seen.intersection(ids), 'v2_distinct_persona_cohorts')
        ids_seen.update(ids); cohorts[seed] = sha(path)
    for slot in slots:
        require(set(slot) == {'seed', 'algorithm', 'run_id', 'relative_path', 'config',
                'config_sha256', 'persona_cohort_sha256'}, 'v2_slot_fields')
        run_id = f"seed-{slot['seed']}-{slot['algorithm']}"
        require(slot['run_id'] == run_id and slot['relative_path'] == 'runs/' + run_id, 'v2_run_identity')
        run = child(root, slot['relative_path'])
        expected = config(slot['seed'], slot['algorithm'], p).public()
        require(same(slot['config'], expected) and same(read(child(run, 'config.json')), expected) and
                slot['config_sha256'] == digest(expected), 'v2_run_config_changed')
        require(slot['persona_cohort_sha256'] == cohorts[slot['seed']] ==
                sha(child(run, 'persona_cohort.json')), 'v2_paired_cohort_bytes_changed')
        if require_pristine:
            require({f.name for f in run.iterdir()} == {'config.json', 'persona_cohort.json'},
                    'v2_uncertain_work_must_not_be_restarted')
    require({f.name for f in child(root, 'runs').iterdir()} == {s['run_id'] for s in slots},
            'v2_unregistered_or_missing_run')
    require({f.name for f in child(root, 'cohorts').iterdir()} == {f'{s}.json' for s in SEEDS},
            'v2_unregistered_or_missing_cohort')
    if require_pristine:
        require(not any((root / name).exists() for name in ('EXECUTION.json', 'execution_results.json',
                    'SUPERVISOR_INTERRUPTED.json')), 'v2_execution_intent_already_exists')
    return manifest
