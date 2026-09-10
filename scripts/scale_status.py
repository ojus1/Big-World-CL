"""Bounded, read-only operational snapshot; never an execution or outcome audit."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024
HASH = re.compile(r'[0-9a-f]{64}')
SCHEDULE = [(seed, arm) for i, seed in enumerate((211, 307, 401))
            for arm in (('no_learning', 'skillopt') if i % 2 == 0 else ('skillopt', 'no_learning'))]
REPORT_STATUSES = {'completed', 'failed', 'exhausted_time_budget', 'exhausted_work_budget',
                   'paused_invocation_limit'}
HELPER = 'scripts/scale_v2_process.py'
RUNNER = 'lifespan/evaluation/runner.py'


class StatusError(ValueError):
    pass


def require(value, code):
    if not value:
        raise StatusError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError('nonfinite_json_number')
    return parsed


def safe_read(path, *, limit=MAX_JSON_BYTES, decode=True):
    """A fixed-size read of one regular, non-symlink file, with replacement check."""
    path = Path(path)
    try:
        if any(p.is_symlink() for p in (path, *path.parents)):
            return {'state': 'updating_unknown'}
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                return {'state': 'updating_unknown'}
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        latest = path.stat(follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) > limit or identity(before) != identity(after) or identity(after) != identity(latest):
            return {'state': 'updating_unknown'}
        value = json.loads(raw, parse_float=finite_float,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if decode else None
        return {'state': 'read', 'value': value, 'sha256': sha(raw), 'mtime': before.st_mtime}
    except FileNotFoundError:
        return {'state': 'missing'}
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {'state': 'updating_unknown'}


def process_identity(pid, *, proc_root=Path('/proc')):
    """Read only the named task; no process enumeration or signaling."""
    try:
        directory = proc_root / str(pid)
        fields = (directory / 'stat').read_text().rsplit(') ', 1)[1].split()
        uid = directory.stat().st_uid
        observed = {'pid': pid, 'start_ticks': int(fields[19]), 'uid': uid,
                'boot_id': (proc_root / 'sys/kernel/random/boot_id').read_text().strip(),
                'pgid': int(fields[2]), 'sid': int(fields[3]),
                'cwd': str((directory / 'cwd').resolve()),
                'command': [x.decode() for x in (directory / 'cmdline').read_bytes().split(b'\0') if x]}
        final = (directory / 'stat').read_text().rsplit(') ', 1)[1].split()
        if any(fields[k] != final[k] for k in (2, 3, 19)) or directory.stat().st_uid != uid:
            return None
        observed['state'] = final[0]
        return observed
    except (OSError, ValueError, IndexError, UnicodeError):
        return None


def registered_sources(campaign, root):
    combined = {}
    for key in ('source_sha256', 'registration_tools_sha256'):
        values = campaign.get(key)
        require(type(values) is dict and 0 < len(values) <= 100, 'invalid_source_inventory')
        for name, expected in values.items():
            require(type(name) is str and re.fullmatch(r'(lifespan|scripts)/[A-Za-z0-9_/]+\.py', name)
                    and '..' not in Path(name).parts and type(expected) is str and HASH.fullmatch(expected),
                    'invalid_source_inventory')
            require(name not in combined or combined[name] == expected, 'conflicting_source_inventory')
            combined[name] = expected
    require(len(combined) == 69 and HELPER in combined and RUNNER in combined, 'unsupported_source_inventory')
    matched = drift = unknown = 0
    for name, expected in combined.items():
        row = safe_read(root / name, decode=False, limit=4 * 1024 * 1024)
        if row['state'] != 'read':
            unknown += 1
        elif row['sha256'] == expected:
            matched += 1
        else:
            drift += 1
    return combined, {'state': 'drift' if drift else 'updating_unknown' if unknown else 'matched',
                      'registered_files': len(combined), 'matched_files': matched,
                      'drifted_files': drift, 'unavailable_files': unknown,
                      'scope': 'registered_local_source_bytes_only; dependencies_not_inspected'}


def owned_start(slot, run, root, sources, records, *, boot_id, monotonic, identity_reader):
    """Validate launch chain and current process before assigning a running clock."""
    try:
        start, intent, config = (records[name] for name in ('start', 'intent', 'config'))
        require(all(x['state'] == 'read' and type(x['value']) is dict for x in (start, intent, config)), 'unavailable')
        s, i = start['value'], intent['value']
        require(s.get('kind') == i.get('kind') == 'WORLD'
                and all(type(v.get('schema_version')) is int and v['schema_version'] == 1 for v in (s, i)),
                'shape')
        require(s['intent_sha256'] == intent['sha256'] and s['helper_sha256'] == i['helper_sha256'] == sources[HELPER]
                and all(canonical(s[k]) == canonical(i[k]) for k in ('command', 'cwd', 'binding', 'started_monotonic')), 'binding')
        require(canonical(config['value']) == canonical(slot['config'])
                and sha(canonical(config['value'])) == slot['config_sha256'], 'config')
        b, command = s['binding'], s['command']
        require(b['run_directory'] == str(run) and b['config_sha256'] == config['sha256']
                and b['runner_sha256'] == sources[RUNNER] and s['cwd'] == str(root), 'binding')
        require(type(command) is list and len(command) == 8 and type(command[0]) is str
                and command[1:] == ['-u', '-m', 'lifespan.evaluation.runner', '--out', str(run),
                                    '--config', str(run / 'config.json')], 'command')
        old = s['root_identity']
        require(type(old) is dict and all(type(old.get(k)) is int and old[k] > 0 for k in ('pid', 'start_ticks'))
                and type(old.get('uid')) is int and old['uid'] == os.getuid()
                and type(boot_id) is str and old.get('boot_id') == boot_id
                and all(type(old.get(k)) is int and old[k] == old['pid'] for k in ('pgid', 'sid')), 'identity')
        require(number(s['started_monotonic']) and number(monotonic) and s['started_monotonic'] <= monotonic, 'clock')
        current = identity_reader(old['pid'])
        require(type(current) is dict and all(current.get(k) == old[k] for k in ('pid', 'start_ticks', 'uid', 'boot_id', 'pgid', 'sid'))
                and current.get('state') not in (None, 'Z', 'X') and current.get('cwd') == str(root)
                and current.get('command') == command, 'not_current')
        return {'verified': True, 'elapsed_seconds': round(monotonic - s['started_monotonic'], 3)}
    except (StatusError, KeyError, ValueError, TypeError):
        return {'verified': False, 'elapsed_seconds': None}


def terminal_evidence(slot, results, records, sources):
    """Hash-bound supervisor return, not a scientific or cleanup audit."""
    if results['state'] != 'read':
        return None
    rows = results['value'].get('runs')
    if type(rows) is not list:
        return None
    matching = [r for r in rows if type(r) is dict and r.get('run_id') == slot['run_id']]
    if len(matching) != 1:
        return None
    row = matching[0]; start = records['start']; cleanup = records['cleanup']; intent = records['intent']
    if any(r['state'] != 'read' or type(r['value']) is not dict for r in (start, cleanup, intent)):
        return None
    s, i = start['value'], intent['value']; clean = cleanup['value']; chain = row.get('lifecycle', {})
    if not (all(type(r.get('schema_version')) is int and r['schema_version'] == 1 for r in (s, i, clean))
            and s.get('kind') == i.get('kind') == 'WORLD'
            and s.get('helper_sha256') == i.get('helper_sha256') == sources[HELPER]
            and s.get('intent_sha256') == intent['sha256']
            and all(k in s and k in i and canonical(s[k]) == canonical(i[k])
                    for k in ('command', 'cwd', 'binding', 'started_monotonic'))):
        return None
    if not (type(chain) is dict and chain.get('start_sha256') == start['sha256']
            and chain.get('cleanup_sha256') == cleanup['sha256'] and clean.get('start_sha256') == start['sha256']
            and clean.get('helper_sha256') == sources[HELPER]
            and type(row.get('exit_code')) is int and type(clean.get('root_exitcode')) is int
            and row['exit_code'] == clean['root_exitcode']
            and type(row.get('cleanup_confirmed')) is bool
            and clean.get('status') in ('confirmed', 'unconfirmed')
            and row['cleanup_confirmed'] == (clean['status'] == 'confirmed')):
        return None
    return {'exit_code': row['exit_code'], 'cleanup_reported_confirmed': row['cleanup_confirmed']}


def project_slot(slot, run, root, sources, results, *, now, monotonic, boot_id, identity_reader):
    paths = {'checkpoint': 'checkpoint.json', 'inflight': 'INFLIGHT.json', 'report': 'REPORT.json',
             'config': 'config.json', 'start': 'lifecycle/WORLD_START.json',
             'intent': 'lifecycle/WORLD_INTENT.json', 'cleanup': 'lifecycle/WORLD_CLEANUP.json'}
    records = {name: safe_read(run / path, limit=MAX_CHECKPOINT_BYTES if name == 'checkpoint' else MAX_JSON_BYTES)
               for name, path in paths.items()}
    cp = records['checkpoint']; inflight = records['inflight']; report = records['report']
    row = {'slot': slot['run_id'], 'seed': slot['seed'], 'algorithm': slot['algorithm'],
           'state': 'updating_unknown', 'phase': None, 'day': None, 'inflight_kind': None,
           'returned_sessions': None, 'recorded_updates': None, 'recorded_adoptions': None,
           'checkpoint_age_seconds': None, 'runner_report_status': None, 'terminal_evidence': None,
           'owned_process_verified': False, 'elapsed_seconds': None, 'remaining_seconds': None,
           'records': {name: value['state'] for name, value in records.items() if name != 'config'}}
    if cp['state'] == 'read':
        value = cp['value']; runner = value.get('runner') if type(value) is dict else None
        eco = value.get('ecosystem') if type(value) is dict else None
        if type(runner) is dict:
            phase = runner.get('phase')
            row['phase'] = phase if type(phase) is str and phase in ('advance', 'actors', 'work', 'learn') else None
            for field, key in (('sessions', 'returned_sessions'), ('updates', 'recorded_updates')):
                values = runner.get(field)
                if type(values) is list and all(type(r) is dict for r in values):
                    row[key] = len(values)
            updates = runner.get('updates')
            if type(updates) is list and all(type(u) is dict and type(u.get('accepted')) is bool for u in updates):
                row['recorded_adoptions'] = sum(u['accepted'] for u in updates)
        if type(eco) is dict and type(eco.get('day')) is int and -1 <= eco['day'] <= 22:
            row['day'] = eco['day']
        if number(now) and now >= cp['mtime']:
            row['checkpoint_age_seconds'] = round(now - cp['mtime'], 3)
    if inflight['state'] == 'read' and type(inflight['value']) is dict:
        kind = inflight['value'].get('kind')
        row['inflight_kind'] = kind if type(kind) is str and kind in ('actor', 'work', 'learning') else None
    if report['state'] == 'read' and type(report['value']) is dict:
        status = report['value'].get('status')
        row['runner_report_status'] = status if type(status) is str and status in REPORT_STATUSES else None
    owned = owned_start(slot, run, root, sources, records, boot_id=boot_id, monotonic=monotonic,
                        identity_reader=identity_reader)
    row['owned_process_verified'] = owned['verified']
    terminal = terminal_evidence(slot, results, records, sources)
    if terminal is not None:
        row.update(state='terminal_recorded', terminal_evidence=terminal)
    elif owned['verified']:
        row.update(state='running', elapsed_seconds=owned['elapsed_seconds'],
                   remaining_seconds=round(max(0, slot['config']['max_run_seconds'] - owned['elapsed_seconds']), 3))
    elif all(records[k]['state'] == 'missing' for k in ('start', 'intent', 'checkpoint', 'inflight', 'report', 'cleanup')):
        row['state'] = 'unlaunched'
    elif records['intent']['state'] == 'read' and records['start']['state'] == 'missing':
        row['state'] = 'launch_recorded'
    # A missing/reused PID, old boot, malformed record, or stale report is never
    # transformed into failure or completion. Report status is separately labeled.
    return row


def read_status(directory, *, campaign_sha256, source_root=ROOT, now=None, monotonic=None,
                boot_id=None, identity_reader=process_identity):
    root = Path(source_root).resolve(); directory = Path(directory).absolute()
    require(type(campaign_sha256) is str and HASH.fullmatch(campaign_sha256), 'invalid_campaign_hash')
    campaign = safe_read(directory / 'campaign.json', limit=4 * 1024 * 1024)
    require(campaign['state'] == 'read' and campaign['sha256'] == campaign_sha256, 'campaign_unavailable_or_hash_mismatch')
    c = campaign['value']
    require(type(c) is dict and c.get('schema_version') == 3 and c.get('kind') == 'scale-v3-six-world-registration',
            'unsupported_campaign')
    slots = c.get('slots')
    require(type(slots) is list and len(slots) == 6, 'six_registered_slots_required')
    for slot, (seed, arm) in zip(slots, SCHEDULE):
        expected = f'seed-{seed}-{arm}'
        require(type(slot) is dict and type(slot.get('seed')) is int and slot['seed'] == seed
                and slot.get('algorithm') == arm and slot.get('run_id') == expected
                and slot.get('relative_path') == 'runs/' + expected, 'invalid_slot_identity')
        config = slot.get('config')
        require(type(config) is dict and number(config.get('max_run_seconds'))
                and config['max_run_seconds'] > 0 and sha(canonical(config)) == slot.get('config_sha256'), 'invalid_slot_config')
    sources, source_status = registered_sources(c, root)
    results = safe_read(directory / 'execution_results.json')
    if results['state'] == 'read' and (type(results['value']) is not dict
            or results['value'].get('campaign_sha256') != campaign_sha256):
        results = {'state': 'updating_unknown'}
    scheduler = safe_read(directory / 'STATUS.json')
    if boot_id is None:
        try: boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except OSError: boot_id = None
    now = time.time() if now is None else now
    monotonic = time.monotonic() if monotonic is None else monotonic
    rows = [project_slot(slot, directory / slot['relative_path'], root, sources, results,
                         now=now, monotonic=monotonic, boot_id=boot_id, identity_reader=identity_reader)
            for slot in slots]
    # Concurrent writes cannot invalidate the external registration unnoticed.
    final = safe_read(directory / 'campaign.json', limit=4 * 1024 * 1024)
    require(final['state'] == 'read' and final['sha256'] == campaign_sha256, 'campaign_changed_during_read')
    return {'schema_version': 1, 'kind': 'scale-operational-status-v1', 'campaign_sha256': campaign_sha256,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'planned_slots': 6,
            'state_counts': dict(sorted(Counter(row['state'] for row in rows).items())),
            'registered_sources': source_status,
            'scheduler_record': scheduler['state'], 'terminal_results_record': results['state'], 'slots': rows,
            'scope': 'non_atomic_operational_snapshot; not_execution_audit_or_research_results',
            'counts_scope': 'checkpointed_returned_records_only; inflight_work_and_replays_not_counted',
            'timing_scope': 'current_owned_world_process_only; ceiling_remaining_is_not_a_completion_forecast'}


def table(value):
    lines = ['SLOT                     STATE               PHASE     DAY  SESSIONS  UPDATES  ADOPTED  AGE(s)  ELAPSED(s)  LEFT(s)']
    for row in value['slots']:
        def show(key): return '?' if row[key] is None else str(row[key])
        lines.append(f"{row['slot']:<24} {row['state']:<19} {show('phase'):<9} {show('day'):>3}  "
                     f"{show('returned_sessions'):>8}  {show('recorded_updates'):>7}  {show('recorded_adoptions'):>7}  "
                     f"{show('checkpoint_age_seconds'):>6}  {show('elapsed_seconds'):>10}  {show('remaining_seconds'):>7}")
    lines.append(f"6 planned slots; source bytes: {value['registered_sources']['state']}. Operational snapshot; not an audit or forecast.")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--campaign-sha256', required=True)
    parser.add_argument('--format', choices=('json', 'table'), default='json')
    args = parser.parse_args(argv)
    try:
        value = read_status(args.directory, campaign_sha256=args.campaign_sha256)
    except (StatusError, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'kind': 'scale-operational-status-v1', 'error': 'registration_unavailable_or_unsupported'}))
        return 2
    print(table(value) if args.format == 'table' else json.dumps(value, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
