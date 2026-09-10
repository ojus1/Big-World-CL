#!/usr/bin/env python3
"""Prepare, supervise and inspect the frozen larger native development study.

Preparation imports pinned personas but makes no model calls. Execution is
one-shot: uncertain actions are never automatically rerun. Logs and raw records
remain in the ignored artifact directory. Status prints allowlisted metadata.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.evaluation.protocol import ExperimentConfig, digest
from lifespan.evaluation.runner import credentials, dependency_provenance, source_hashes
from lifespan.mirofish import save
from lifespan.personas import import_cohort

SEEDS = [211, 307, 401]
ALGORITHMS = ['no_learning', 'skillopt']
PYTHON = ROOT / 'MiroFish/backend/.venv/bin/python'

BUDGETS = {'max_parallel_worlds': 6,
 'per_world_wall_seconds': 36000,
 'max_online_sessions': 1440,
 'max_learning_epochs': 108,
 'max_learning_target_replays': 1296,
 'employee_target_and_optimizer_physical_calls': 44640,
 'employee_target_and_optimizer_charged_tokens': 792000000,
 'logical_actor_interviews': 3972,
 'actor_physical_model_calls': None,
 'actor_tokens': None,
 'currency_cost': None}
DESIGN = {'primary': 'Equal-world mean difference in fixed initial/benchmark commitment fulfillment.',
 'secondary': ['all commitment fulfillment',
               'net utility',
               'native skill adoption',
               'future online sessions by deployed skill version',
               'measured learner compute'],
 'inference_unit': 'world pair; three development pairs are descriptive',
 'updates': 'Days 7, 11 and 17 when 2 TRAIN + 2 VAL distinct tasks have released feedback; day 3 cannot '
            'be eligible.',
 'selection': 'All employees; no outcome-conditioned selection, replacement, extension or stopping.',
 'actor_compute': 'Logical interview requests capped; graph/social/OASIS physical calls and tokens '
                  'unknown.',
 'randomness': 'Scenario/persona seeds fixed; hosted actor and Hermes sampling not controlled.',
 'state': 'Persistent institutional/employee actor histories and business state; fresh Hermes task '
          'profile carrying only deployed skill.',
 'recovery': 'One-shot campaign. No automatic retry or resume of uncertain native work.'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def study_config(seed, algorithm):
    return ExperimentConfig(algorithm=algorithm, seed=seed, days=20,
        enterprise_count=4, consumer_count=8, split='dev', state_mode='skill_transfer',
        decision_every=4, update_every=4, update_days=(3, 7, 11, 17), feedback_delay=1,
        max_iterations=16, max_output_tokens=4096, max_work_sessions=240,
        max_run_seconds=36000, max_learning_calls=7200, max_learning_tokens=144000000,
        max_learning_calls_per_epoch=200, max_learning_tokens_per_epoch=4000000,
        max_learning_seconds_per_epoch=1800, max_actor_interviews=662,
        train_cases=2, val_cases=2, edit_budget=4, skillopt_rollouts_k=2,
        focal_employee=None, schema_version=2)


def prepare(out, *, creds=None, cohort_importer=import_cohort):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Preparation requires a new output directory')
    creds = creds or credentials()
    out.mkdir(parents=True)
    slots, all_personas = [], set()
    for index, seed in enumerate(SEEDS):
        # Counterbalance arm launch order across seeds; outcome-independent.
        arms = ALGORITHMS if index % 2 == 0 else list(reversed(ALGORITHMS))
        cohort_path = out / 'cohorts' / f'{seed}.json'
        cohort = cohort_importer(ROOT / 'lifespan/data/persona8b', cohort_path, count=25, seed=seed)
        ids = [p['persona_id'] for p in cohort['personas']]
        if len(ids) != 25 or len(set(ids)) != 25 or all_personas.intersection(ids):
            raise ValueError('The frozen seeds must produce distinct, disjoint persona cohorts')
        all_personas.update(ids)
        for algorithm in arms:
            config = study_config(seed, algorithm)
            run_id = f'seed-{seed}-{algorithm}'
            run = out / 'runs' / run_id
            run.mkdir(parents=True)
            (run / 'persona_cohort.json').write_bytes(cohort_path.read_bytes())
            save(run / 'config.json', config.public())
            slots.append({'seed': seed, 'algorithm': algorithm, 'run_id': run_id,
                'relative_path': 'runs/' + run_id, 'config': config.public(),
                'config_sha256': digest(config.public()),
                'persona_cohort_sha256': sha(cohort_path)})
    manifest = {'schema_version': 1, 'kind': 'multi_seed_reacting_world_comparison',
        'created_at': utc(), 'seeds': SEEDS, 'algorithms': ALGORITHMS,
        'population': {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1},
        'days': 20, 'slots': slots, 'source_sha256': source_hashes(),
        'dependencies': dependency_provenance(), 'target_model': creds['model'],
        'model_base_url': creds['base_url'],
        'budgets': BUDGETS, 'design': DESIGN}
    save(out / 'campaign.json', manifest)
    return manifest


def validate_prepared(out, *, creds=None):
    out = Path(out).resolve()
    manifest = read(out / 'campaign.json')
    if manifest['source_sha256'] != source_hashes() or manifest['dependencies'] != dependency_provenance():
        raise ValueError('Execution source or dependencies changed after preparation')
    if manifest['seeds'] != SEEDS or manifest['algorithms'] != ALGORITHMS:
        raise ValueError('Campaign seed or arm contract changed')
    fixed = {'schema_version': 1, 'kind': 'multi_seed_reacting_world_comparison',
        'population': {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1},
        'days': 20, 'budgets': BUDGETS, 'design': DESIGN}
    if any(manifest.get(k) != v for k, v in fixed.items()):
        raise ValueError('Campaign population, budget or design contract changed')
    if len(manifest['slots']) != 6:
        raise ValueError('Six frozen run slots required')
    expected = [(seed, arm) for i, seed in enumerate(SEEDS)
                for arm in (ALGORITHMS if i % 2 == 0 else list(reversed(ALGORITHMS)))]
    if [(s['seed'], s['algorithm']) for s in manifest['slots']] != expected:
        raise ValueError('Frozen dispatch order changed')
    seen_personas = set()
    for seed in SEEDS:
        cohort = read(out / 'cohorts' / f'{seed}.json')
        ids = [p['persona_id'] for p in cohort['personas']]
        if len(ids) != 25 or len(set(ids)) != 25 or seen_personas.intersection(ids):
            raise ValueError('Frozen persona cohorts must be distinct and disjoint')
        seen_personas.update(ids)
    for slot in manifest['slots']:
        run = (out / slot['relative_path']).resolve()
        if (not run.is_relative_to(out) or slot['run_id'] != f"seed-{slot['seed']}-{slot['algorithm']}"
                or slot['relative_path'] != 'runs/' + slot['run_id']):
            raise ValueError('Invalid run identity/path')
        cfg = study_config(slot['seed'], slot['algorithm']).public()
        if slot['config'] != cfg or read(run / 'config.json') != cfg or slot['config_sha256'] != digest(cfg):
            raise ValueError('Frozen per-run configuration changed')
        if sha(run / 'persona_cohort.json') != slot['persona_cohort_sha256']:
            raise ValueError('Frozen persona cohort changed')
        if sha(out / 'cohorts' / f"{slot['seed']}.json") != slot['persona_cohort_sha256']:
            raise ValueError('Paired cohort differs from frozen seed cohort')
        if any(p.name not in ('config.json', 'persona_cohort.json') for p in run.iterdir()):
            raise ValueError('Native output already exists; uncertain work is not resumed')
    if creds is not None and (creds['model'], creds['base_url']) != (manifest['target_model'], manifest['model_base_url']):
        raise ValueError('Model/provider changed after preparation')
    return manifest


def status(out):
    out = Path(out).resolve()
    manifest = read(out / 'campaign.json')
    rows = []
    for slot in manifest['slots']:
        run = out / slot['relative_path']
        row = {'run_id': slot['run_id'], 'status': 'not_started'}
        cp = run / 'checkpoint.json'
        if cp.exists():
            data = read(cp); state = data['runner']
            row.update(status='running', day=data['ecosystem']['day'], phase=state['phase'],
                sessions=len(state['sessions']), successes=sum(r['success'] for r in state['sessions']),
                updates=len(state['updates']), accepted_updates=sum(u['accepted'] for u in state['updates']),
                learning_replays=sum(u['costs']['replays'] for u in state['updates']),
                learning_calls=state['learning_calls'], learning_tokens=state['learning_tokens'],
                checkpoint_age_seconds=round(max(0, time.time() - cp.stat().st_mtime)))
        if (run / 'REPORT.json').exists():
            row['status'] = read(run / 'REPORT.json')['status']
        if (run / 'INFLIGHT.json').exists():
            action = read(run / 'INFLIGHT.json')
            row['inflight'] = {k: action[k] for k in ('kind', 'key', 'day')}
            if action['kind'] == 'learning':
                progress = run / 'learning' / action['key'] / 'progress.json'
                if progress.exists():
                    p = read(progress)
                    row['learning_progress'] = {'status': p['status'],
                        **{k: p.get('target_progress', {}).get(k) for k in
                           ('dispatched_replays', 'returned_replays', 'charged_or_reserved_model_calls',
                            'charged_or_reserved_tokens')}}
        ledger = run / 'actors/evaluation_interview_ledger.json'
        if ledger.exists():
            row['logical_actor_requests'] = len(read(ledger)['requests'])
        rows.append(row)
    return {'as_of': utc(), 'runs': rows}


def close_actor_environment(run):
    """Close only this run's recorded OASIS environment and verify liveness.

    OASIS is spawned by the shared server, outside the world process group.
    A successful close request can mean "still closing", so it is not proof.
    """
    run = Path(run)
    state_path = run / 'actors/mirofish_state.json'
    if not state_path.exists():
        return {'status': 'no_recorded_environment'}
    result = {'at': utc(), 'status': 'close_unconfirmed'}
    def request(path, body, timeout):
        req = Request('http://127.0.0.1:5001/api/simulation/' + path,
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    try:
        state = read(state_path)
        simulation_id = state.get('simulation', {}).get('simulation_id')
        if not isinstance(simulation_id, str) or not simulation_id:
            result['status'] = 'no_recorded_environment'
        else:
            result['simulation_id'] = simulation_id
            save(run / 'SUPERVISOR_ACTOR_CLEANUP.json', result)
            if not state.get('closed'):
                request('close-env', {'simulation_id': simulation_id, 'timeout': 15}, 35)
            payload = request('env-status', {'simulation_id': simulation_id}, 10)
            if payload.get('success') is True and payload.get('data', {}).get('env_alive') is False:
                result['status'] = 'closed'
    except Exception as exc:
        result['error_class'] = type(exc).__name__
    try:
        save(run / 'SUPERVISOR_ACTOR_CLEANUP.json', result)
    except OSError:
        result['record_write_failed'] = True
    return result


def execute(out, *, workers=6, python=PYTHON, campaign_sha256=None):
    if type(workers) is not int or not 1 <= workers <= 6:
        raise ValueError('workers must be in 1..6')
    out = Path(out).resolve()
    if not campaign_sha256 or sha(out / 'campaign.json') != campaign_sha256:
        raise ValueError('Execute requires the reviewed, published campaign SHA-256')
    creds = credentials()
    manifest = validate_prepared(out, creds=creds)
    # Exclusive intent prevents concurrent supervisors and unreviewed retries.
    with (out / 'EXECUTION.json').open('x') as f:
        json.dump({'started_at': utc(), 'supervisor_pid': os.getpid(),
                   'workers': workers, 'campaign_sha256': sha(out / 'campaign.json')}, f)
    pending = list(manifest['slots']); running = {}; results = []
    def terminate(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        last_status = 0
        while pending or running:
            while pending and len(running) < workers:
                slot = pending.pop(0); run = out / slot['relative_path']
                log = (run / 'execution.log').open('wb')
                child = subprocess.Popen([str(python), '-u', '-m', 'lifespan.evaluation.runner',
                    '--out', str(run), '--config', str(run / 'config.json')], cwd=ROOT,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                log.close()
                running[slot['run_id']] = (child, time.monotonic(), slot)
                print(json.dumps({'event': 'started', 'run_id': slot['run_id'], 'pid': child.pid}), flush=True)
            for run_id, (child, started, slot) in list(running.items()):
                # Extra minute permits bounded native close and final report.
                if child.poll() is None and time.monotonic() - started > 36060:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL); child.wait()
                if child.poll() is not None:
                    result = {'run_id': run_id, 'exit_code': child.returncode,
                              'elapsed_seconds': round(time.monotonic() - started, 3),
                              'actor_cleanup': close_actor_environment(out / slot['relative_path'])}
                    results.append(result); del running[run_id]
                    save(out / 'execution_results.json', {'runs': results})
                    print(json.dumps({'event': 'process_finished', **result}), flush=True)
            if time.monotonic() - last_status >= 30:
                snapshot = status(out); save(out / 'STATUS.json', snapshot)
                print(json.dumps(snapshot), flush=True); last_status = time.monotonic()
            if running:
                time.sleep(2)
        from scripts.audit_scale import audit_campaign
        audit = audit_campaign(out, strict=True)
        save(out / 'AUDIT.json', audit)
        print(json.dumps({'event': 'campaign_finished', 'status': audit['status'], 'ok': audit['ok']}), flush=True)
        return audit
    except BaseException as exc:
        save(out / 'SUPERVISOR_INTERRUPTED.json', {'at': utc(), 'type': type(exc).__name__,
            'running_slots': list(running), 'pending_slots': [s['run_id'] for s in pending]})
        for child, _, _ in running.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        cleanup_deadline = time.monotonic() + 30
        for child, _, _ in running.values():
            try:
                child.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for _, _, slot in running.values():
            close_actor_environment(out / slot['relative_path'])
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'execute', 'status'])
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--campaign-sha256', help='Required for execute: SHA-256 published after preparation')
    a = p.parse_args()
    if a.mode == 'prepare':
        m = prepare(a.out)
        print(json.dumps({'status': 'prepared', 'runs': len(m['slots']), 'campaign_sha256': sha(a.out / 'campaign.json')}))
    elif a.mode == 'status':
        print(json.dumps(status(a.out), indent=2))
    else:
        return 0 if execute(a.out, workers=a.workers, campaign_sha256=a.campaign_sha256)['ok'] else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
