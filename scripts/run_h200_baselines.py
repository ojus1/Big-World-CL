#!/usr/bin/env python3
"""Fresh H200 integration pilot using the existing baseline configs.

Run execute in its own systemd user service with KillMode=control-group so the
backend, OASIS and employee descendants share one cleanup boundary. vLLM is an
independent service. This launcher does not resume historical registrations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lifespan.mirofish import save
from lifespan.evaluation.runner import source_hashes, dependency_provenance, credentials
from lifespan.evaluation.protocol import ExperimentConfig
from lifespan.evaluation.provider import contract

ARMS = ('no_learning', 'skillopt')
STAGES = ('pilot',)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def qualifications(directory):
    from scripts.preflight_actor_contract import audit as actors
    from scripts.audit_hermes_preflight import audit_preflight as employees
    from scripts.preflight_optimizer import audit_preflight as optimizer
    result = {}
    for name, audit in (('actor', actors), ('employee', employees), ('optimizer', optimizer)):
        path = directory / name
        bound = sha(path / 'manifest.json')
        kwargs = ({'expected_manifest_sha256': bound, 'strict': True} if name == 'employee'
                  else {'manifest_sha256': bound, **({'strict': True} if name == 'actor' else {})})
        report = audit(path, **kwargs)
        if report.get('ok') is not True:
            raise ValueError('Qualification failed: ' + name)
        result[name] = {'directory': str(path), 'manifest_sha256': bound, 'audit': report}
    return result


def prepare(out, evidence):
    from lifespan.personas import import_cohort
    if out.exists():
        raise ValueError('Choose a fresh output directory')
    provider = contract(credentials())
    proof = qualifications(evidence)
    if provider is None or any(row['audit']['provider_contract'] != provider for row in proof.values()):
        raise ValueError('All qualification components must use this provider')
    configs = {}
    out.mkdir(parents=True)
    for stage in STAGES:
        seed = 101 if stage == 'pilot' else 211
        cohort = out / stage / 'persona_cohort.json'
        import_cohort(ROOT / 'lifespan/data/persona8b', cohort, count=12, seed=seed)
        for arm in ARMS:
            template = ('pilot_' if stage == 'pilot' else 'dev_contrastive_') + arm + '.json'
            cfg = read(ROOT / 'configs/evaluation' / template)
            cfg.update(seed=seed, provider_profile=provider['profile'], hermes_transport='nonstreaming',
                       mirofish_service_url='http://127.0.0.1:5001',
                       actor_output_contract={'version': 'actor-json-v1', 'max_output_tokens': 4096,
                                              'timeout_seconds': 120})
            ExperimentConfig(**cfg)
            path = out / stage / (arm + '.config.json')
            save(path, cfg)
            run = out / stage / arm
            run.mkdir()
            shutil.copyfile(cohort, run / 'persona_cohort.json')
            configs[str(path.relative_to(out))] = sha(path)
    manifest = {'kind': 'h200-fresh-baselines-v1', 'prepared_at_unix': time.time(),
        'repository_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'launcher_sha256': sha(__file__), 'source_sha256': source_hashes(),
        'dependencies': dependency_provenance(), 'provider_contract': provider,
        'qualifications': proof, 'configs': configs,
        'cohorts': {s: sha(out / s / 'persona_cohort.json') for s in STAGES},
        'stages': list(STAGES), 'arms': list(ARMS),
        'advance_gate': 'Both pilot worlds complete, pass strict artifact audits, and form one compatible pair. No gain or accepted edit required.',
        'scope': 'One eight-day focal-employee integration pair. The final calibrated world is separately sourced from JobBench and internal EuroBench; this pilot supplies no final-world result.'}
    save(out / 'MANIFEST.json', manifest)
    return {'status': 'prepared', 'manifest_sha256': sha(out / 'MANIFEST.json')}


def snapshot(run):
    path = run / 'checkpoint.json'
    if not path.exists():
        return {'status': 'initializing'}
    cp = read(path); state = cp['runner']
    return {'day': cp['ecosystem']['day'], 'phase': state['phase'],
            'work_sessions': len(state['sessions']), 'learning_epochs': len(state['updates']),
            'adoptions': sum(u['accepted'] for u in state['updates']),
            'inflight': read(run / 'INFLIGHT.json') if (run / 'INFLIGHT.json').exists() else None,
            'report_status': read(run / 'REPORT.json')['status'] if (run / 'REPORT.json').exists() else None}


def execute(out, expected):
    from scripts.audit_evaluation import audit_run
    from scripts.evaluation_report_v2 import load_verified_report_v2, compare_reports_v2
    manifest = read(out / 'MANIFEST.json')
    if sha(out / 'MANIFEST.json') != expected or sha(__file__) != manifest['launcher_sha256']:
        raise ValueError('Prepared launch binding changed')
    if source_hashes() != manifest['source_sha256'] or dependency_provenance() != manifest['dependencies']:
        raise ValueError('Execution sources or dependencies changed')
    if contract(credentials()) != manifest['provider_contract']:
        raise ValueError('Provider changed')
    if any(sha(out / p) != h for p, h in manifest['configs'].items()):
        raise ValueError('Prepared configuration changed')
    for stage, digest in manifest['cohorts'].items():
        if any(sha(out / stage / arm / 'persona_cohort.json') != digest for arm in ARMS):
            raise ValueError('Paired population changed')
    for row in manifest['qualifications'].values():
        if sha(Path(row['directory']) / 'manifest.json') != row['manifest_sha256']:
            raise ValueError('Qualification manifest changed')
    qualifications(Path(manifest['qualifications']['actor']['directory']).parent)
    if not os.environ.get('INVOCATION_ID') or 'bigworld-h200-baselines.service' not in Path('/proc/self/cgroup').read_text():
        raise ValueError('Execute inside bigworld-h200-baselines.service for descendant cleanup')
    import socket
    with socket.socket() as port:
        port.bind(('127.0.0.1', 5001))
    with urlopen(manifest['provider_contract']['base_url'] + '/models', timeout=5) as response:
        models = json.load(response)
    if manifest['provider_contract']['model'] not in {m['id'] for m in models['data']}:
        raise ValueError('Prepared model unavailable')
    with (out / 'EXECUTION.json').open('x') as f:
        json.dump({'started_unix': time.time(), 'pid': os.getpid(), 'manifest_sha256': expected,
                   'systemd_invocation_id': os.environ['INVOCATION_ID']}, f)
    processes = []; logs = []
    try:
        backend_log = (out / 'backend.log').open('xb'); logs.append(backend_log)
        backend = subprocess.Popen([sys.executable, 'run.py'], cwd=ROOT / 'MiroFish/backend',
            stdout=backend_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        processes.append(backend)
        for _ in range(120):
            if backend.poll() is not None:
                raise RuntimeError('Backend exited')
            try:
                with urlopen('http://127.0.0.1:5001/health', timeout=1):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise TimeoutError('Backend readiness deadline')
        for stage in STAGES:
            active = {}
            for arm in ARMS:
                log = (out / stage / (arm + '.log')).open('xb'); logs.append(log)
                process = subprocess.Popen([sys.executable, '-u', '-m', 'lifespan.evaluation.runner',
                    '--config', str(out / stage / (arm + '.config.json')), '--out', str(out / stage / arm)],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
                active[arm] = process; processes.append(process)
            started = time.monotonic()
            while True:
                state = {arm: {**snapshot(out / stage / arm), 'pid': p.pid, 'exit_code': p.poll()} for arm, p in active.items()}
                save(out / 'STATUS.json', {'status': 'running', 'stage': stage, 'updated_unix': time.time(), 'arms': state})
                if backend.poll() is not None or any(p.poll() not in (None, 0) for p in active.values()):
                    raise RuntimeError('Native component failed; later stages are cancelled')
                if all(p.poll() is not None for p in active.values()):
                    break
                if time.monotonic() - started > 15000:
                    raise TimeoutError('Stage exceeded four-hour allowance plus cleanup margin')
                time.sleep(5)
            reports = []
            for arm in ARMS:
                run = out / stage / arm
                audit = audit_run(run, strict=True)
                save(out / stage / (arm + '.AUDIT.json'), audit)
                if not audit['ok']:
                    raise RuntimeError('Completed world failed independent artifact audit: ' + stage + '/' + arm)
                reports.append(load_verified_report_v2(run / 'REPORT.v2.json'))
            paired = compare_reports_v2(reports)
            save(out / stage / 'PAIRED_REPORT.json', paired)
            if len(paired['eligible_pairs']) != 1:
                raise RuntimeError('Completed worlds are not an eligible pair')
        save(out / 'STATUS.json', {'status': 'completed', 'updated_unix': time.time(), 'stages': list(STAGES)})
    except BaseException as exc:
        save(out / 'FAILURE.json', {'error_type': type(exc).__name__, 'at_unix': time.time(),
            'note': 'Inspect immutable run receipts and logs. No automatic retry or replacement.'})
        status = read(out / 'STATUS.json') if (out / 'STATUS.json').exists() else {}
        status.update(status='failed', updated_unix=time.time(), error_type=type(exc).__name__)
        save(out / 'STATUS.json', status)
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'execute'))
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--qualifications', type=Path)
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    result = (prepare(args.out.resolve(), args.qualifications.resolve()) if args.mode == 'prepare'
              else execute(args.out.resolve(), args.manifest_sha256))
    if result:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
