"""Isolate independent world pairs in processes; retain order inside each pair."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path

from scripts.source_world_calibration import save
from .cancellation import Cancellation, StudyCancelled, check


def run_pair(bank, world, harness, judge, learner, out, employee_factory, index, cancellation=None):
    from .contracts import NoLearning
    from .worlds import run_world
    from .reacting import run_world as run_reacting
    arms = [NoLearning(), learner]
    if index % 2:
        arms.reverse()
    root = Path(out) / 'worlds' / f'seed-{world["seed"]}'
    reports = []
    for arm in arms:
        name = arm.identity()['name']
        stop = cancellation.at(world_seed=world['seed'], arm=name) if cancellation is not None else None
        try:
            check(stop)
            if employee_factory is None:
                report = run_world(bank, world, harness, judge, arm, root / name, cancellation=stop)
            else:
                report = run_reacting(bank, world, harness, judge, arm, root / name, employee_factory, cancellation=stop)
            reports.append(report)
        except Exception as exc:
            if stop is not None and not isinstance(exc, StudyCancelled): stop.request(type(exc).__name__)
            result = {'status': 'cancelled' if isinstance(exc, StudyCancelled) else 'incomplete', 'index': index, 'reports': reports,
                      'error_type': type(exc).__name__, 'failed_world': world['seed'], 'failed_arm': name}
            save(root / 'PAIR_STATUS.json', result)
            return result
        save(root / 'PAIR_STATUS.json', {'status': 'running', 'index': index, 'reports': reports})
    result = {'status': 'completed', 'index': index, 'reports': reports}
    save(root / 'PAIR_STATUS.json', result)
    return result


def execute_pairs(bank, study, harness, judge, learner, out, employee_factory, workers):
    """Join all dispatched pairs and preserve failures; never drop or retry one."""
    completed = {}
    failures = []
    policy = study['worlds'][0]['specification'].get('failure_policy', 'stop_after_current_wave')
    cancellation = Cancellation(Path(out)) if policy == 'stop_after_current_wave' else None
    with ProcessPoolExecutor(max_workers=min(workers, len(study['worlds'])),
                             mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = {pool.submit(run_pair, bank, world, harness, judge, learner, out, employee_factory, index, cancellation): index
                   for index, world in enumerate(study['worlds'])}
        for future in as_completed(futures):
            index = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                if cancellation is not None:
                    cancellation.at(world_seed=study['worlds'][index]['seed'], stage='pair_process').request(type(exc).__name__)
                result = {'status': 'incomplete', 'index': index, 'reports': [],
                          'error_type': type(exc).__name__, 'failed_world': study['worlds'][index]['seed'],
                          'failed_arm': None}
            completed[index] = result['reports']
            if result['status'] != 'completed':
                failures.append({k: v for k, v in result.items() if k != 'reports'})
            reports = [report for key in sorted(completed) for report in completed[key]]
            save(Path(out) / 'STATUS.json', {'status': 'incomplete' if failures else 'running',
                'completed_arms': len(reports), 'planned_arms': 2 * len(study['worlds']),
                'finished_pair_workers': len(completed),
                'completed_pairs': len(completed) - len(failures), 'max_parallel_worlds': workers,
                'failure_policy': policy, 'stop_requested': cancellation is not None and cancellation.path.exists(),
                'failures': failures, 'reports': reports})
    if failures:
        raise RuntimeError('Parallel study has failed pairs; all started workers joined and evidence preserved')
    return [report for key in sorted(completed) for report in completed[key]]
