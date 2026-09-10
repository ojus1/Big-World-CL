#!/usr/bin/env python3
"""Prepare or revalidate a full follow-up registration; never dispatch a model.

This tool records an explicit launch policy and evidence references. It cannot
certify the referenced native preflight evidence or execute a campaign.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lifespan.evaluation.protocol import digest
from lifespan.evaluation.runner import dependency_provenance, source_hashes
from lifespan.mirofish import save
from lifespan.personas import import_cohort
from scripts import scale_v3_contract as contract


def tooling():
    return {name: contract.sha(ROOT / name) for name in contract.REGISTRATION_TOOLS}


def prepare(out, *, launch_policy, target_model, model_base_url, cohort_importer=import_cohort,
            sources=None, dependencies=None, registration_tools=None):
    p = contract.policy(launch_policy)
    contract.model_metadata(target_model, model_base_url)
    sources = source_hashes() if sources is None else sources
    dependencies = dependency_provenance() if dependencies is None else dependencies
    registration_tools = tooling() if registration_tools is None else registration_tools
    contract.require(all(dependencies.get(name, {}).get('revision') for name in ('hermes', 'mirofish', 'skillopt')),
                     'v3_requires_installed_dependency_provenance')
    out = Path(out).resolve()
    contract.require(out.is_relative_to(ROOT / 'lifespan/artifacts'), 'v3_output_must_be_private_artifact_directory')
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    slots = []; seen = set()
    for seed in contract.SEEDS:
        path = out / f'cohorts/{seed}.json'
        cohort = cohort_importer(ROOT / 'lifespan/data/persona8b', path, count=25, seed=seed)
        ids = [row['persona_id'] for row in cohort['personas']]
        contract.require(len(ids) == len(set(ids)) == 25 and not seen.intersection(ids), 'v3_distinct_persona_cohorts')
        seen.update(ids)
    for seed, algorithm in contract.schedule():
        run_id = f'seed-{seed}-{algorithm}'; run = out / 'runs' / run_id
        run.mkdir(parents=True)
        cohort_path = out / f'cohorts/{seed}.json'
        (run / 'persona_cohort.json').write_bytes(cohort_path.read_bytes())
        cfg = contract.config(seed, algorithm, p).public(); save(run / 'config.json', cfg)
        slots.append({'seed': seed, 'algorithm': algorithm, 'run_id': run_id,
            'relative_path': 'runs/' + run_id, 'config': cfg, 'config_sha256': digest(cfg),
            'persona_cohort_sha256': contract.sha(cohort_path)})
    manifest = {'schema_version': 3, 'kind': contract.VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
        'seeds': contract.SEEDS, 'algorithms': contract.ALGORITHMS, 'population': contract.POPULATION,
        'days': 20, 'slots': slots, 'source_sha256': sources, 'dependencies': dependencies,
        'registration_tools_sha256': registration_tools, 'target_model': target_model,
        'model_base_url': model_base_url, 'launch_policy': p, 'budgets': contract.budgets(p), 'design': contract.design()}
    save(out / 'campaign.json', manifest)
    return contract.validate(out, source_sha256=sources, dependencies=dependencies,
                             registration_tools_sha256=registration_tools,
                             campaign_sha256=contract.sha(out / 'campaign.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'validate'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--target-model')
    parser.add_argument('--model-base-url')
    parser.add_argument('--campaign-sha256', help='Required for validate: separately reviewed raw manifest hash')
    args = parser.parse_args()
    if args.mode == 'prepare':
        if not all((args.policy, args.target_model, args.model_base_url)):
            parser.error('prepare requires --policy, --target-model and --model-base-url')
        prepare(args.out, launch_policy=contract.read(args.policy), target_model=args.target_model,
                model_base_url=args.model_base_url)
    else:
        if not args.campaign_sha256:
            parser.error('validate requires the separately reviewed --campaign-sha256')
        contract.validate(args.out, source_sha256=source_hashes(), dependencies=dependency_provenance(),
                          registration_tools_sha256=tooling(), campaign_sha256=args.campaign_sha256)
    print(json.dumps({'status': 'registration_valid', 'campaign_sha256': contract.sha(args.out / 'campaign.json'),
                      'planned_worlds': 6, 'planned_pairs': 3, 'native_prerequisites_reaudited': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
