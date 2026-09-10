#!/usr/bin/env python3
"""Capture and summarize partial scale-v1 duration evidence without forecasting."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'scale-v1-horizon-observations-v1'
EMPLOYEE = re.compile(r'firm-[0-9]+__(onboarding|renewal|incident)-regulated\Z')
EPOCH = re.compile(r'd[0-9]{3}-firm-[0-9]+__(onboarding|renewal|incident)-regulated\Z')
WORK = re.compile(r'd[0-9]{3}-firm-[0-9]+__(onboarding|renewal|incident)-regulated-[A-Za-z0-9_-]+\Z')
REGIMES = {'base', 'changed', 'exception', 'reversal'}
PHASES = {'train', 'baseline_val', 'final_val', 'reflect', 'train_post_skill',
          'gate_trial:skill', 'gate_trial:memory'}
STATUSES = {'completed', 'running', 'failed', 'budget_exhausted', 'failed_or_interrupted',
            'paused_invocation_limit', 'exhausted_time_budget', 'exhausted_work_budget',
            'exhausted_work_sessions', 'exhausted_compute_budget', 'not_started'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value):
    try:
        return type(value) in (float, int) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def count(value):
    return type(value) is int and value >= 0


def equal(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':')) == json.dumps(b, sort_keys=True, separators=(',', ':'))


def numeric(value):
    return value if number(value) else None


def finite_sum(values):
    try: return numeric(math.fsum(values))
    except OverflowError: return None


def record_path(name):
    if not isinstance(name, str): return False
    if name in ('campaign.json','EXECUTION.json','execution_results.json','STATUS.json'): return True
    match = re.fullmatch(r'runs/seed-(211|307|401)-(no_learning|skillopt)/(.+)', name)
    if not match: return False
    tail = match.group(3)
    if tail in ('checkpoint.json','REPORT.json','REPORT.v2.json','INFLIGHT.json','manifest.json','config.json'): return True
    parts = tail.split('/')
    return bool((len(parts)==3 and parts[0]=='work' and WORK.fullmatch(parts[1]) and parts[2]=='session.json')
        or (len(parts)==3 and parts[:2]==['private','cases'] and parts[2].endswith('.json') and WORK.fullmatch(parts[2][:-5]))
        or (len(parts) in (3,4) and parts[0]=='learning' and EPOCH.fullmatch(parts[1])
            and ((len(parts)==3 and parts[2] in ('update.json','progress.json'))
                 or (len(parts)==4 and re.fullmatch('trial-[0-9]{3}',parts[2]) and parts[3]=='session.json'))))


def state(value):
    return value if isinstance(value, str) and value in STATUSES else 'unknown'


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def distribution(values):
    known = sorted(v for v in values if number(v))
    return {'observations': len(values), 'known': len(known), 'unknown': len(values)-len(known),
        'sum_seconds': finite_sum(known) if known else None,
        'min_seconds': known[0] if known else None, 'max_seconds': known[-1] if known else None,
        'mean_seconds': finite_sum(v/len(known) for v in known) if known else None,
        'median_seconds': (known[len(known)//2] if len(known)%2 else
            known[len(known)//2-1]/2+known[len(known)//2]/2) if known else None,
        'p90_seconds_nearest_rank': known[max(0, math.ceil(.9*len(known))-1)] if known else None}


def buckets(rows, dimensions, duration_fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key, 'unknown') for key in dimensions)].append(row)
    result = []
    for key in sorted(groups, key=lambda value: tuple(str(v) for v in value)):
        group = groups[key]
        result.append({**dict(zip(dimensions, key)), 'observations': len(group),
            'infrastructure_invalid': sum(r.get('infrastructure_valid') is False for r in group),
            'infrastructure_unknown': sum(r.get('infrastructure_valid') is None for r in group),
            'usage_complete': sum(r.get('usage_complete') is True for r in group),
            'usage_incomplete_or_unknown': sum(r.get('usage_complete') is not True for r in group),
            'binding_problem_observations': sum(bool(r.get('binding_issues')) for r in group),
            'durations': {field: distribution([r.get(field) for r in group]) for field in duration_fields}})
    return result


def work_observation(record):
    """Allowlist scalar receipt facts; never export prompts, tools or error text."""
    record = record if isinstance(record, dict) else {}
    employee = record.get('employee'); match = EMPLOYEE.fullmatch(employee) if isinstance(employee, str) else None
    usage = record.get('usage') if isinstance(record.get('usage'), dict) else {}
    elapsed = record.get('elapsed_seconds')
    calls = usage.get('api_calls'); tokens = usage.get('total_tokens'); charged = usage.get('charged_tokens')
    return {'employee': employee if match else 'unknown', 'workflow': match.group(1) if match else 'unknown',
        'regime': record.get('regime') if isinstance(record.get('regime'), str) and record['regime'] in REGIMES else 'unknown',
        'day': record.get('day') if count(record.get('day')) else None,
        'runtime_seconds': numeric(elapsed),
        'duration_status': 'missing' if elapsed is None else 'known' if number(elapsed) else 'malformed',
        'infrastructure_valid': record.get('infrastructure_valid') if type(record.get('infrastructure_valid')) is bool else None,
        'success': record.get('success') if type(record.get('success')) is bool else None,
        'budget_exhausted': record.get('budget_exhausted') if type(record.get('budget_exhausted')) is bool else None,
        'usage_complete': usage.get('complete') is True and count(calls) and count(tokens),
        'reported_usage_complete': usage.get('complete') if type(usage.get('complete')) is bool else None,
        'recorded_physical_calls': calls if count(calls) else None,
        'recorded_total_tokens': tokens if count(tokens) else None,
        'recorded_charged_tokens': charged if count(charged) else None}


def learning_observation(update, progress=None):
    update = update if isinstance(update, dict) else {}
    progress = progress if isinstance(progress, dict) else {}
    employee = update.get('employee', progress.get('employee'))
    match = EMPLOYEE.fullmatch(employee) if isinstance(employee, str) else None
    costs = update.get('costs') if isinstance(update.get('costs'), dict) else {}
    gate = update.get('gate_evidence') if isinstance(update.get('gate_evidence'), dict) else {}
    lists = [gate.get(k) for k in ('applied_edits', 'rejected_edits', 'unmatched_edits')]
    edits = sum(map(len, lists)) if all(isinstance(v, list) and all(isinstance(edit,dict)
        and edit.get('target') in ('skill','memory') and edit.get('op') in ('add','delete','replace')
        for edit in v) for v in lists) else None
    proposal = 'proposal_observed' if edits is not None and edits > 0 else (
        'no_proposal_observed' if edits == 0 and update.get('status') == 'completed' else 'unknown_incomplete')
    ops = costs.get('operations') if isinstance(costs.get('operations'), list) else []
    valid_ops = isinstance(costs.get('operations'), list) and all(
        isinstance(op, dict) and op.get('kind') in ('target', 'optimizer') for op in ops)
    target = [op for op in ops if isinstance(op, dict) and op.get('kind') == 'target']
    optimizer = [op for op in ops if isinstance(op, dict) and op.get('kind') == 'optimizer']
    def total(rows):
        return finite_sum(row['wall_seconds'] for row in rows) if all(number(row.get('wall_seconds')) for row in rows) else None
    known = costs.get('accounting_complete') is True and all(count(costs.get(k)) for k in ('tokens', 'target_model_calls', 'optimizer_model_calls'))
    artifacts = update.get('replay_artifacts', progress.get('replay_artifacts'))
    artifacts = artifacts if isinstance(artifacts, list) else []
    return {'employee': employee if match else 'unknown', 'workflow': match.group(1) if match else 'unknown',
        'learning_day': update.get('day', progress.get('day')) if count(update.get('day', progress.get('day'))) else None,
        'status': state(update.get('status', progress.get('status'))), 'proposal_class': proposal,
        'observed_edit_records': edits, 'accepted': update.get('accepted') if type(update.get('accepted')) is bool else None,
        'learner_wall_seconds': numeric(costs.get('wall_seconds')), 'progress_elapsed_seconds': numeric(progress.get('elapsed_seconds')),
        'target_callback_seconds': total(target) if valid_ops else None,
        'optimizer_callback_seconds': total(optimizer) if valid_ops else None,
        'target_operations': len(target) if valid_ops else None,
        'optimizer_operations': len(optimizer) if valid_ops else None,
        'malformed_operation_records': sum(not isinstance(op, dict) or op.get('kind') not in ('target', 'optimizer') for op in ops),
        'recorded_optimizer_calls': costs.get('optimizer_model_calls') if count(costs.get('optimizer_model_calls')) else None,
        'usage_complete': known, 'infrastructure_valid': None,
        'recorded_total_tokens': costs.get('tokens') if known else None,
        'recorded_charged_or_reserved_tokens': costs.get('tokens') if count(costs.get('tokens')) else None,
        'recorded_charged_or_reserved_calls': costs['target_model_calls']+costs['optimizer_model_calls']
            if all(count(costs.get(k)) for k in ('target_model_calls','optimizer_model_calls')) else None,
        'recorded_reported_tokens_known_prefix': sum(op['tokens'] for op in ops if isinstance(op,dict)
            and op.get('accounting')=='reported' and count(op.get('tokens'))),
        'failed_target_infrastructure_records': sum(isinstance(a,dict) and a.get('infrastructure_valid') is False for a in artifacts),
        'unknown_target_infrastructure_records': sum(not isinstance(a,dict) or type(a.get('infrastructure_valid')) is not bool for a in artifacts),
        'unknown_target_usage_records': sum(not isinstance(a,dict) or a.get('usage_known') is not True for a in artifacts),
        'accounting_label': 'recorded_ledger_complete' if known else 'unknown_or_reserved; not_measured_total'}


def _campaign(value):
    if (not isinstance(value, dict) or value.get('seeds') != [211, 307, 401]
            or value.get('algorithms') != ['no_learning', 'skillopt'] or len(value.get('slots', [])) != 6
            or value.get('kind') != 'multi_seed_reacting_world_comparison' or value.get('days') != 20
            or value.get('population') != {'firms':4,'employees':12,'consumers':8,'agencies':1}
            or not isinstance(value.get('source_sha256'), dict) or len(value['source_sha256']) != 34):
        raise ValueError('Expected the six-slot scale-v1 campaign and34 frozen source files')
    expected = {(seed, arm) for seed in (211, 307, 401) for arm in ('no_learning', 'skillopt')}
    seen = set()
    for slot in value['slots']:
        pair = (slot.get('seed'), slot.get('algorithm')); seen.add(pair)
        if pair not in expected or slot.get('run_id') != f'seed-{pair[0]}-{pair[1]}':
            raise ValueError('Invalid fixed run identity')
        if slot.get('relative_path') != 'runs/' + slot['run_id']:
            raise ValueError('Invalid fixed run path')
    if seen != expected:
        raise ValueError('Missing or duplicated campaign slot')
    for name, expected_hash in value['source_sha256'].items():
        if (not isinstance(name, str) or not re.fullmatch(r'(lifespan|scripts)/[A-Za-z0-9_/]+\.py', name)
                or not isinstance(expected_hash, str) or not re.fullmatch('[0-9a-f]{64}', expected_hash)):
            raise ValueError('Invalid frozen source binding')


def capture(campaign, out):
    """One sequential partial snapshot. Never lock, retry, edit or stop a world."""
    campaign, out = Path(campaign).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(campaign) or not out.is_relative_to(ROOT/'lifespan/artifacts'):
        raise ValueError('Observation must use a new separate ignored artifact directory')
    if subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--quiet', str(out)], check=False).returncode != 0:
        raise ValueError('Observation destination must be git-ignored')
    raw_campaign = (campaign/'campaign.json').read_bytes(); manifest = json.loads(raw_campaign); _campaign(manifest)
    frozen = {}
    for name, expected in manifest['source_sha256'].items():
        raw = (ROOT/name).read_bytes()
        if sha(raw) != expected:
            raise ValueError('Frozen execution source mismatch; capture refused')
        frozen[name] = raw
    out.mkdir(parents=True, mode=0o700); os.chmod(out, 0o700)
    metadata = {'schema_version': 1, 'kind': VERSION, 'started_at': datetime.now(timezone.utc).isoformat(),
        'campaign_sha256': sha(raw_campaign), 'diagnostic_sha256': sha(Path(__file__).read_bytes()),
        'source_sha256': manifest['source_sha256'], 'files': [], 'missing': [], 'read_errors': [],
        'mutable_changed_during_capture': [], 'immutable_changed_during_capture': []}
    captured = set()
    def keep(name, kind, *, initial=None):
        if name in captured:
            return None
        path = campaign/name
        if not path.resolve().is_relative_to(campaign):
            raise ValueError('Source artifact leaves campaign directory')
        try:
            raw = path.read_bytes() if initial is None else initial
        except FileNotFoundError:
            metadata['missing'].append(name); return None
        except OSError:
            metadata['read_errors'].append(name); return None
        target = out/'private/raw'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        metadata['files'].append({'path': name, 'sha256': sha(raw), 'bytes': len(raw), 'kind': kind})
        captured.add(name)
        if kind not in ('mutable_progress', 'immutable_update'):
            return None
        try: return json.loads(raw)
        except (ValueError, UnicodeDecodeError): return None
    keep('campaign.json', 'immutable', initial=raw_campaign)
    for name in ('EXECUTION.json', 'execution_results.json', 'STATUS.json'):
        keep(name, 'mutable_control')
    for slot in manifest['slots']:
        prefix = slot['relative_path']; run = campaign/prefix
        for name in ('checkpoint.json', 'REPORT.json', 'REPORT.v2.json', 'INFLIGHT.json', 'manifest.json', 'config.json'):
            keep(prefix+'/'+name, 'mutable_control' if name in ('checkpoint.json', 'INFLIGHT.json') else 'immutable')
        work_paths = sorted((run/'work').glob('*/session.json'))
        for path in work_paths:
            key = path.parent.name
            if not WORK.fullmatch(key): raise ValueError('Invalid work record directory')
            keep(str(path.relative_to(campaign)), 'immutable_work')
            keep(prefix+'/private/cases/'+key+'.json', 'immutable_capsule')
        for directory in sorted((run/'learning').glob('*')):
            if not directory.is_dir(): continue
            if not EPOCH.fullmatch(directory.name): raise ValueError('Invalid learning directory')
            for name in ('update.json', 'progress.json'):
                data = keep(str((directory/name).relative_to(campaign)), 'mutable_progress' if name == 'progress.json' else 'immutable_update')
                if isinstance(data, dict):
                    for row in data.get('replay_artifacts', []) if isinstance(data.get('replay_artifacts'), list) else []:
                        rel = row.get('capsule_path') if isinstance(row, dict) else None
                        if isinstance(rel, str) and rel.startswith('private/cases/') and WORK.fullmatch(Path(rel).stem) and rel == 'private/cases/'+Path(rel).name:
                            keep(prefix+'/'+rel, 'immutable_capsule')
            for path in sorted(directory.glob('trial-*/session.json')):
                if not re.fullmatch('trial-[0-9]{3}', path.parent.name): raise ValueError('Invalid trial directory')
                keep(str(path.relative_to(campaign)), 'immutable_replay')
    for item in metadata['files']:
        try: changed = sha((campaign/item['path']).read_bytes()) != item['sha256']
        except OSError: changed = True
        if changed:
            key = 'mutable_changed_during_capture' if item['kind'].startswith('mutable') else 'immutable_changed_during_capture'
            metadata[key].append(item['path'])
    for name, raw in frozen.items():
        target = out/'private/source'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        if sha((ROOT/name).read_bytes()) != manifest['source_sha256'][name]:
            metadata['immutable_changed_during_capture'].append('source/'+name)
    (out/'private/diagnostic.py').write_bytes(Path(__file__).read_bytes())
    metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(out/'capture.json', metadata)
    report = summarize(out); save(out/'REPORT.json', report)
    return report


def summarize(out):
    """Reproduce allowlisted summaries solely from frozen captured bytes."""
    out = Path(out).resolve(); errors = []
    def issue(code, run_id=None, path=None):
        errors.append({k: v for k, v in {'code': code, 'run_id': run_id, 'path': path}.items() if v is not None})
    capture_raw = (out/'capture.json').read_bytes(); meta = json.loads(capture_raw)
    if meta.get('kind') != VERSION or meta.get('schema_version') != 1: raise ValueError('Invalid observation schema')
    for key in ('campaign_sha256','diagnostic_sha256'):
        if not isinstance(meta.get(key), str) or not re.fullmatch('[0-9a-f]{64}', meta[key]):
            raise ValueError('Invalid observation source digest')
    for key in ('missing','read_errors','mutable_changed_during_capture','immutable_changed_during_capture'):
        if not isinstance(meta.get(key), list) or not all(record_path(name) or
                (key=='immutable_changed_during_capture' and isinstance(name,str) and
                 re.fullmatch(r'source/(lifespan|scripts)/[A-Za-z0-9_/]+\.py',name)) for name in meta[key]):
            raise ValueError('Invalid capture observation path')
    for key in ('started_at','finished_at'): datetime.fromisoformat(meta[key])
    files = {}
    for item in meta['files']:
        name = item['path']; path = out/'private/raw'/name
        if (not isinstance(item.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or not record_path(name) or Path(name).is_absolute() or '..' in Path(name).parts
                or name in files or not path.resolve().is_relative_to(out/'private/raw')):
            raise ValueError('Invalid captured path inventory')
        raw = path.read_bytes()
        if sha(raw) != item['sha256'] or len(raw) != item['bytes']: issue('captured_bytes_mutated', path=name)
        try: files[name] = json.loads(raw)
        except (ValueError, UnicodeDecodeError): files[name] = None; issue('malformed_json', path=name)
    if {str(p.relative_to(out/'private/raw')) for p in (out/'private/raw').rglob('*') if p.is_file()} != set(files):
        issue('captured_raw_inventory_mismatch')
    campaign = files['campaign.json']; _campaign(campaign)
    if sha((out/'private/raw/campaign.json').read_bytes()) != meta['campaign_sha256']: issue('campaign_hash_mismatch')
    source_ok = meta['source_sha256'] == campaign['source_sha256'] and all(
        sha((out/'private/source'/name).read_bytes()) == value for name, value in campaign['source_sha256'].items())
    if not source_ok: issue('frozen_source_mismatch')
    if {str(p.relative_to(out/'private/source')) for p in (out/'private/source').rglob('*') if p.is_file()} != set(campaign['source_sha256']):
        issue('captured_source_inventory_mismatch')
    if sha((out/'private/diagnostic.py').read_bytes()) != meta['diagnostic_sha256']: issue('diagnostic_source_mismatch')
    if sha(Path(__file__).read_bytes()) != meta['diagnostic_sha256']: issue('current_diagnostic_source_mismatch')
    for name in meta['immutable_changed_during_capture']: issue('immutable_changed_during_capture', path=name)
    for name in meta['read_errors']: issue('source_read_error', path=name)
    terminal = files.get('execution_results.json'); terminal = terminal.get('runs', []) if isinstance(terminal, dict) else []
    if not isinstance(terminal,list):
        terminal=[]; issue('supervisor_terminal_inventory_malformed')
    terminals = {r['run_id']: r for r in terminal if isinstance(r, dict) and r.get('run_id') in {s['run_id'] for s in campaign['slots']}}
    if len(terminals)!=len(terminal): issue('supervisor_terminal_inventory_malformed')
    worlds, work, epochs, replays = [], [], [], []
    hashes = {item['path']: item['sha256'] for item in meta['files']}
    for slot in campaign['slots']:
        rid, prefix, arm = slot['run_id'], slot['relative_path'], slot['algorithm']
        cp = files.get(prefix+'/checkpoint.json'); cp = cp if isinstance(cp, dict) else {}
        runner = cp.get('runner') if isinstance(cp.get('runner'), dict) else {}
        ecosystem = cp.get('ecosystem') if isinstance(cp.get('ecosystem'), dict) else {}
        sessions = runner.get('sessions') if isinstance(runner.get('sessions'), list) else []
        updates = runner.get('updates') if isinstance(runner.get('updates'), list) else []
        indexed = {r['id']: r for r in sessions if isinstance(r, dict) and isinstance(r.get('id'), str)}
        indexed_updates = {(r.get('day'), r.get('employee')): r for r in updates if isinstance(r, dict)
                           and count(r.get('day')) and isinstance(r.get('employee'), str)}
        terminal_row = terminals.get(rid, {}); report = files.get(prefix+'/REPORT.json')
        report = report if isinstance(report, dict) else {}
        exitcode = terminal_row.get('exit_code') if type(terminal_row.get('exit_code')) is int else None
        reported = state(report.get('status'))
        observed_status = reported if reported != 'unknown' else 'failed' if exitcode not in (0, None) else 'running' if cp else 'not_started'
        world = {'run_id': rid, 'algorithm': arm, 'seed': slot['seed'], 'status': observed_status,
            'checkpoint_present': bool(cp), 'checkpoint_sha256': hashes.get(prefix+'/checkpoint.json'),
            'report_sha256': hashes.get(prefix+'/REPORT.json'), 'report_v2_sha256': hashes.get(prefix+'/REPORT.v2.json'),
            'observed_day': ecosystem.get('day') if count(ecosystem.get('day')) else None,
            'checkpoint_runner_elapsed_seconds': numeric(runner.get('elapsed_seconds')),
            'reported_status': reported, 'supervisor_exit_code': exitcode,
            'supervisor_elapsed_seconds': numeric(terminal_row.get('elapsed_seconds')),
            'reported_elapsed_seconds': numeric(report.get('elapsed_seconds')),
            'inflight_marker_present': prefix+'/INFLIGHT.json' in files,
            'checkpointed_work_records': len(sessions) if cp else None, 'checkpointed_updates': len(updates) if cp else None}
        if report and not cp: issue('terminal_report_without_checkpoint', rid)
        if len(indexed) != len(sessions): issue('checkpoint_session_inventory_malformed', rid)
        if len(indexed_updates) != len(updates): issue('checkpoint_update_inventory_malformed', rid)
        seen_work = set(); seen_updates = set()
        for name, raw in sorted(files.items()):
            if name.startswith(prefix+'/work/') and name.endswith('/session.json'):
                key = Path(name).parent.name; seen_work.add(key); problems = []
                if key in indexed:
                    expected = {k:v for k,v in indexed[key].items() if k not in ('id', 'skill_version')}
                    if not equal(raw, expected): problems.append('checkpoint_raw_session_mismatch')
                capsule = files.get(prefix+'/private/cases/'+key+'.json')
                if not isinstance(capsule, dict) or not isinstance(raw, dict): problems.append('missing_or_malformed_case_binding')
                else:
                    case = capsule.get('case') if isinstance(capsule.get('case'), dict) else {}
                    if (any(raw.get(k) != capsule.get(k) for k in ('employee', 'task_id'))
                            or any(raw.get(left) != case.get(right) for left,right in
                                   (('case_id','id'), ('regime','regime'), ('day','day')))
                            or work_observation(raw)['workflow'] != case.get('workflow')):
                        problems.append('case_identity_mismatch')
                    if not count(raw.get('day')) or key != f"d{raw['day']:03d}-{raw.get('employee')}-{raw.get('task_id')}":
                        problems.append('work_directory_identity_mismatch')
                row = {**work_observation(raw), 'run_id': rid, 'algorithm': arm, 'checkpointed': key in indexed,
                    'source_path': name, 'source_sha256': hashes[name], 'raw_record_present': True, 'binding_issues': problems}
                work.append(row)
                for problem in problems: issue(problem, rid, name)
        for key in sorted(set(indexed)-seen_work):
            issue('checkpoint_session_raw_missing', rid)
            work.append({**work_observation(indexed[key]), 'run_id': rid, 'algorithm': arm, 'checkpointed': True,
                'source_path': prefix+'/checkpoint.json', 'source_sha256': hashes.get(prefix+'/checkpoint.json'),
                'raw_record_present': False, 'binding_issues': ['checkpoint_session_raw_missing']})
        dirs = sorted({'/'.join(Path(name).parts[:4]) for name in files if name.startswith(prefix+'/learning/')})
        for directory in dirs:
            update = files.get(directory+'/update.json'); progress = files.get(directory+'/progress.json')
            chosen = update if isinstance(update, dict) else progress if isinstance(progress, dict) else {}
            key = (chosen.get('day') if count(chosen.get('day')) else None,
                   chosen.get('employee') if isinstance(chosen.get('employee'), str) else None); problems = []
            checkpointed = key in indexed_updates; seen_updates.add(key)
            if chosen and (not count(chosen.get('day')) or not isinstance(chosen.get('employee'), str)
                    or not EMPLOYEE.fullmatch(chosen['employee'])
                    or Path(directory).name != f"d{chosen['day']:03d}-{chosen['employee']}"):
                problems.append('epoch_directory_identity_mismatch')
            if checkpointed and not equal(update, indexed_updates[key]): problems.append('checkpoint_raw_update_mismatch')
            if isinstance(update, dict) and isinstance(progress, dict):
                for field in ('employee','day','status','costs','replay_artifacts','optimizer_transport_audit','accepted'):
                    if not equal(update.get(field), progress.get(field)): problems.append('update_progress_binding_mismatch'); break
            row = {**learning_observation(update, progress), 'run_id': rid, 'algorithm': arm,
                'checkpointed': checkpointed, 'returned_update': isinstance(update, dict),
                'update_sha256': hashes.get(directory+'/update.json'), 'progress_sha256': hashes.get(directory+'/progress.json'),
                'binding_issues': problems}
            epochs.append(row)
            references = chosen.get('replay_artifacts', []) if isinstance(chosen.get('replay_artifacts'), list) else []
            if 'replay_artifacts' in chosen and not isinstance(chosen['replay_artifacts'], list):
                problems.append('declared_replay_inventory_malformed')
            refs = {}
            for attempt, reference in enumerate(references):
                expected = directory[len(prefix)+1:] + f'/trial-{attempt:03d}/session.json'
                if (not isinstance(reference, dict) or type(reference.get('attempt_index')) is not int
                        or reference['attempt_index'] != attempt or reference.get('session_path') != expected
                        or isinstance(chosen.get('employee'), str) and reference.get('employee') != chosen['employee']):
                    problems.append('declared_replay_identity_mismatch')
                name = prefix+'/'+reference['session_path'] if isinstance(reference, dict) and isinstance(reference.get('session_path'), str) else None
                if name is not None:
                    if name in refs: problems.append('duplicate_declared_replay_session')
                    else: refs[name] = reference
            row['declared_replay_records'] = len(references)
            row['declared_sessions_missing'] = sum(name not in files for name in refs)
            for name, raw in sorted(files.items()):
                if not name.startswith(directory+'/trial-') or not name.endswith('/session.json'): continue
                ref = refs.get(name, {}); replay_problems = []
                if not ref: replay_problems.append('pending_replay_without_declared_binding')
                elif ref.get('session_sha256') != hashes[name]: replay_problems.append('replay_session_hash_missing_or_mismatch')
                capsule_path = prefix+'/'+ref['capsule_path'] if isinstance(ref.get('capsule_path'), str) else None
                if ref and (capsule_path not in hashes or hashes[capsule_path] != ref.get('capsule_sha256')):
                    replay_problems.append('replay_capsule_hash_missing_or_mismatch')
                if ref and isinstance(raw, dict):
                    capsule = files.get(capsule_path)
                    if (not isinstance(capsule, dict) or ref.get('employee') != raw.get('employee')
                            or ref.get('source_task_id') != raw.get('task_id')
                            or capsule.get('employee') != raw.get('employee') or capsule.get('task_id') != raw.get('task_id')
                            or isinstance(chosen.get('employee'), str) and raw.get('employee') != chosen['employee']):
                        replay_problems.append('replay_identity_mismatch')
                    case = capsule.get('case', {}) if isinstance(capsule, dict) else {}
                    if (not isinstance(case, dict) or raw.get('regime') != case.get('regime')
                            or raw.get('day') != case.get('day') or work_observation(raw)['workflow'] != case.get('workflow')):
                        replay_problems.append('replay_case_scope_mismatch')
                replay = {**work_observation(raw), 'run_id': rid, 'algorithm': arm, 'learning_day': row['learning_day'],
                    'phase': ref.get('phase') if isinstance(ref.get('phase'), str) and ref['phase'] in PHASES else 'unknown',
                    'source_path': name, 'source_sha256': hashes[name], 'binding_issues': replay_problems}
                replays.append(replay)
                for problem in replay_problems: issue(problem, rid, name)
            for problem in problems: issue(problem, rid, directory)
        for key in sorted(set(indexed_updates)-seen_updates):
            issue('checkpoint_update_raw_missing', rid)
            epochs.append({**learning_observation(indexed_updates[key]), 'run_id': rid, 'algorithm': arm,
                'checkpointed': True, 'returned_update': True, 'update_sha256': None, 'progress_sha256': None,
                'declared_replay_records': None, 'declared_sessions_missing': None,
                'binding_issues': ['checkpoint_update_raw_missing']})
        world.update(returned_work_records=sum(r['run_id']==rid for r in work),
                     captured_learning_records=sum(r['run_id']==rid for r in epochs),
                     returned_replay_records=sum(r['run_id']==rid for r in replays))
        worlds.append(world)
    return {'schema_version': 1, 'kind': VERSION, 'ok': not errors, 'errors': errors,
        'scope': 'sequential_partial_snapshot; worlds_and_sessions_are_not_independent_samples',
        'forecast_seconds': None, 'all_in_cost': None, 'physical_inference_seconds': None,
        'changes_original_audit': False, 'nonstreaming_long_horizon_claim': False,
        'provenance': {'capture_sha256': sha(capture_raw), 'campaign_sha256': meta['campaign_sha256'], 'diagnostic_sha256': meta['diagnostic_sha256'],
            'frozen_source_files': len(campaign['source_sha256']), 'frozen_source_bytes_match': source_ok,
            'captured_files': len(meta['files']), 'capture_started_at': meta['started_at'], 'capture_finished_at': meta['finished_at'],
            'mutable_changed_during_capture': meta['mutable_changed_during_capture'], 'missing_files': meta['missing']},
        'worlds': worlds, 'work_observations': work, 'learning_observations': epochs, 'replay_observations': replays,
        'online_work_buckets': buckets(work, ('algorithm','workflow','regime'), ('runtime_seconds',)),
        'learning_epoch_buckets': buckets(epochs, ('algorithm','workflow','learning_day','proposal_class'),
            ('learner_wall_seconds','progress_elapsed_seconds','target_callback_seconds','optimizer_callback_seconds')),
        'learning_replay_buckets': buckets(replays, ('algorithm','workflow','regime','learning_day','phase'), ('runtime_seconds',))}


def verify_snapshot(out, *, expected_capture_sha256=None, expected_report_sha256=None):
    """Verify exact captured originals and derived public report; no live reads."""
    out = Path(out).resolve()
    result = {'schema_version': 1, 'kind': VERSION, 'ok': False, 'errors': [], 'summary_reproduced': False}
    try:
        capture_raw = (out/'capture.json').read_bytes(); report_raw = (out/'REPORT.json').read_bytes()
        result.update(capture_sha256=sha(capture_raw), report_sha256=sha(report_raw))
        if expected_capture_sha256 is not None and expected_capture_sha256 != result['capture_sha256']:
            result['errors'].append({'code': 'registered_capture_hash_mismatch'})
        if expected_report_sha256 is not None and expected_report_sha256 != result['report_sha256']:
            result['errors'].append({'code': 'registered_report_hash_mismatch'})
        rebuilt = summarize(out); persisted = json.loads(report_raw)
        result['summary_reproduced'] = equal(rebuilt, persisted)
        result['errors'].extend(rebuilt['errors'])
        if not result['summary_reproduced']: result['errors'].append({'code': 'derived_report_mismatch'})
        result['world_slots'] = len(rebuilt['worlds'])
        result['capture_window_is_partial'] = True
        result['ok'] = not result['errors']
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        result['errors'].append({'code': type(exc).__name__})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture'); cap.add_argument('campaign'); cap.add_argument('--out', required=True)
    inspect = sub.add_parser('summarize'); inspect.add_argument('observation')
    verify = sub.add_parser('verify'); verify.add_argument('observation')
    args = parser.parse_args()
    try:
        result = capture(args.campaign, args.out) if args.command == 'capture' else (
            verify_snapshot(args.observation) if args.command == 'verify' else summarize(args.observation))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)); return 0 if result['ok'] else 1
    except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
