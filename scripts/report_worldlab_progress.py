"""Read-only progress for frozen workplace studies; never restart a worker.

Service state and saved experiment state are reported separately. Counts are
observations, not an execution audit, a complete cost total or a learning claim.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def integer(value):
    return type(value) is int and value >= 0


def service_state(unit):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]*', unit):
        raise ValueError('Invalid service name')
    fields = ['LoadState', 'ActiveState', 'SubState', 'MainPID', 'Result', 'InvocationID',
              'ExecMainStartTimestamp', 'WorkingDirectory']
    try:
        result = subprocess.run(['systemctl', '--user', 'show', unit] +
            [item for f in fields for item in ('-p', f)], capture_output=True, text=True, timeout=10, check=True)
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        pid = int(props.get('MainPID', '0'))
        present = False
        if pid > 0:
            try:
                os.kill(pid, 0)
                present = True
            except PermissionError:
                present = True
            except ProcessLookupError:
                pass
        if props.get('LoadState') == 'not-found':
            observation = 'unit_missing'
        elif props.get('ActiveState') in ('inactive', 'failed'):
            observation = 'terminal'
        elif pid > 0 and present:
            observation = 'main_process_present'
        else:
            observation = 'transition_or_no_main_process'
        return {'unit': unit, 'observation': observation, 'properties': props,
                'main_process_present': present,
                'binding': 'Operator-selected service; reported separately from study artifacts'}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'unit': unit, 'observation': 'unavailable', 'error_type': type(exc).__name__}


def attempt_totals(records):
    calls = [r.get('model_calls') for r in records]
    charged = [r.get('tokens') for r in records]
    return {'recorded_attempts': len(records),
            'status_counts': dict(Counter(r.get('status', 'unknown') for r in records)),
            'fully_graded': sum((r.get('grade') or {}).get('grading_complete') is True for r in records),
            'known_physical_model_calls': sum(v for v in calls if integer(v)),
            'attempts_with_unknown_call_count': sum(not integer(v) for v in calls),
            'charged_or_reserved_tokens': sum(v for v in charged if integer(v)),
            'attempts_with_unknown_charge': sum(not integer(v) for v in charged),
            'attempts_with_incomplete_accounting': sum(r.get('accounting_complete') is not True for r in records)}


def snapshot(root, unit=None):
    root = Path(root).resolve()
    raw = (root / 'STUDY.json').read_bytes()
    study = json.loads(raw)
    expected = json.loads((root / 'PREPARED.json').read_text())['study_sha256']
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Study bytes differ from preparation')
    errors = []

    def optional(path):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError('Expected an object')
            return value
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            errors.append({'path': str(path.relative_to(root)), 'error_type': type(exc).__name__})
            return None

    arms = []
    for world in study['worlds']:
        for name in ('no_learning', study['learner']['name']):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name) or type(world['seed']) is not int:
                raise ValueError('Unsafe world or arm identity')
            arm = root / 'worlds' / f'seed-{world["seed"]}' / name
            state = optional(arm / 'STATE.json') or {}
            report = optional(arm / 'REPORT.json') or {}
            work_paths = list(arm.glob('sessions/*/ATTEMPT.json'))
            replay_paths = list(arm.glob('learning/*/replay-*/ATTEMPT.json'))
            work = [r for p in work_paths if (r := optional(p)) is not None]
            replays = [r for p in replay_paths if (r := optional(p)) is not None]
            updates = [r for p in arm.glob('learning/*/UPDATE.json') if (r := optional(p)) is not None]
            pending = [p for glob in ('sessions/*/PUBLIC_REQUEST.json', 'learning/*/replay-*/PUBLIC_REQUEST.json')
                       for p in arm.glob(glob) if not (p.parent / 'ATTEMPT.json').exists()]
            ledger = optional(arm / 'actors/evaluation_interview_ledger.json') or {}
            interviews = ledger.get('requests', [])
            arms.append({'seed': world['seed'], 'arm': name, 'directory_exists': arm.exists(),
                'saved_report_status': report.get('status'),
                'day': state.get('workplace', {}).get('day', state.get('day')),
                'planned_obligations': len(world['schedule']),
                'planned_probe_obligations': sum(s['split'] == 'probe' for s in world['schedule']),
                'recorded_employee_decisions': len(state.get('decisions', [])),
                'recorded_state_sessions': len(state.get('sessions', [])),
                'work_finalized_attempts': attempt_totals(work),
                'replay_finalized_attempts': attempt_totals(replays),
                'attempts_without_final_receipt': [str(p.parent.relative_to(arm)) for p in pending],
                'inflight_marker': optional(arm / 'INFLIGHT.json'),
                'learning': {'finalized_update_receipts': len(updates),
                    'adoptions': sum(u.get('accepted') is True for u in updates),
                    'charged_or_reserved_tokens_including_replays': sum(u['costs']['tokens'] for u in updates if integer(u.get('costs', {}).get('tokens'))),
                    'epochs_with_unknown_charge': sum(not integer(u.get('costs', {}).get('tokens')) for u in updates),
                    'epochs_with_incomplete_accounting': sum(u.get('costs', {}).get('accounting_complete') is not True for u in updates)},
                'actor_interviews': {'recorded_logical_requests': len(interviews),
                    'known_physical_model_calls': sum(r['physical_model_calls'] for r in interviews if integer(r.get('physical_model_calls'))),
                    'reported_tokens': sum(r['tokens'] for r in interviews if integer(r.get('tokens'))),
                    'requests_with_incomplete_accounting': sum(r.get('accounting_complete') is not True for r in interviews)},
                'bootstrap_and_social_tokens': None,
                'saved_social_model_usage': report.get('actor_usage', state.get('actor_usage', {})).get('social_model_usage')})
    saved_status = optional(root / 'STATUS.json') or {}
    saved_report = optional(root / 'REPORT.json') or {}
    value = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'study_root': str(root),
        'study_sha256': expected, 'service': service_state(unit) if unit else None,
        'execution_marker_exists': (root / 'EXECUTION.json').exists(),
        'saved_study_status': {k: saved_status[k] for k in ('status', 'completed_arms', 'planned_arms', 'error_type', 'failed_world', 'failed_arm') if k in saved_status},
        'saved_study_report_status': saved_report.get('status'),
        'planned_world_pairs': len(study['worlds']),
        'completed_arm_reports': sum(a['saved_report_status'] == 'completed' for a in arms),
        'arms': arms, 'read_errors': errors, 'whole_study_accounting_complete': False,
        'scope': 'Read-only nontransactional progress snapshot. Finalized receipts omit pending work. Learning ledger tokens already include replays: do not add those categories. Service success is not an experiment audit or learning-effect result. Inflight markers alone do not prove liveness.'}
    if (root / 'STUDY.json').read_bytes() != raw:
        raise ValueError('Study changed during observation')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study', type=Path, required=True)
    p.add_argument('--service', help='Optional systemd user service on this machine; never started or restarted')
    a = p.parse_args()
    print(json.dumps(snapshot(a.study, a.service), indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
