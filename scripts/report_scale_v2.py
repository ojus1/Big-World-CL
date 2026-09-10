#!/usr/bin/env python3
"""Completed-only public scale-v2 draft; no publishing or native/model execution.

Strict native audit is mandatory. Tests replace it explicitly with fabricated
receipts; fixture output is never native study evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import audit_scale_v2, report_scale as common, scale_summary, scale_world_dynamics
from scripts import scale_v2_contract as contract

VERSION = 'scale-publication-v2.0'
require, count, number, close, sha = common.require, common.count, common.number, common.close, common.sha
HELPERS = ('scripts/report_scale.py', 'scripts/scale_summary.py', 'scripts/scale_world_dynamics.py',
           'scripts/audit_scale_v2.py', 'scripts/evaluation_report_v2.py',
           'lifespan/evaluation/metrics.py', 'lifespan/evaluation/protocol.py')
CAVEATS = [
    'Three reused development world pairs support descriptive differences only; no confidence interval, statistical significance, held-out confirmation or population-generalization claim is made.',
    'All six fresh worlds and three valid complete pairs are required. No surviving-pair, accepted-only, loaded-only or successful-session endpoint is substituted.',
    'The primary is fixed initial/benchmark fulfillment. All-demand fulfillment and synthetic utility are secondary; native actors and demand can respond differently in the two arms.',
    'Scheduled eligibility, rejected/no-op/budget-stopped epochs and all deployed versions remain visible. Gate replay scores and adoption do not establish prospective benefit.',
    'A deployed skill file does not prove use. Actual loading is a separate audited native-message observation; nonloading remains a behavioral outcome.',
    'Employees, sessions, retries and replays within a world are dependent. These observations do not isolate causal forgetting or establish indefinite lifelong learning.',
    'Employee online, learning-target and optimizer receipts are counted separately. Contracted actor interviews cover reconciled client receipts; bootstrap, social inference and possible server-orphan usage are outside that scope.',
    'Currency and all-in costs remain unknown. Synthetic utility is not money; summed session/epoch durations are not campaign elapsed time.',
    'Only allowlisted aggregates and provenance are exported. Prompts, responses, skills, artifacts, provider IDs, native profiles and private absolute paths remain private.',
]


def _digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'invalid_sha256')
    return value


def _sources(values):
    require(type(values) is dict and bool(values), 'missing_source_inventory')
    for name, value in values.items():
        require(type(name) is str and re.fullmatch(r'(lifespan|scripts)/[A-Za-z0-9_/]+\.py', name), 'unsafe_source_inventory')
        _digest(value)
    return dict(values)



def _receipt_inventory(root, slots):
    """Hash selected raw receipt bytes, including actor caches without exposing names."""
    inventory = {}
    for slot in slots:
        run = root / slot['relative_path']
        cache = run / 'actors/mirofish_interviews'
        require(cache.is_dir(), 'missing_contracted_actor_cache')
        entries = list(cache.iterdir())
        require(all(p.is_file() and p.suffix == '.json' for p in entries), 'unexpected_actor_cache_entry')
        paths = entries + [run / 'actors/evaluation_interview_ledger.json']
        for pattern in ('work/*/session.json', 'learning/*/update.json', 'learning/*/progress.json',
                        'learning/*/trial-*/session.json', 'private/cases/*.json'):
            paths.extend(run.glob(pattern))
        for path in paths:
            require(path.resolve().is_relative_to(root)
                and not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), 'receipt_inventory_symlink_or_escape')
            require(path.is_file(), 'missing_receipt_inventory_file')
            relative = str(path.relative_to(root))
            require(relative not in inventory, 'duplicate_receipt_inventory_entry')
            inventory[relative] = sha(path.read_bytes())
    return inventory


def _gate_trace(update):
    """Numerical historical selection evidence only; no task IDs or text."""
    gate = update.get('gate_evidence') or {}
    def score(value):
        if value is None: return None
        value = number(value)
        require(value <= 1, 'gate_score_range')
        return value
    baseline, candidate = (score(gate.get(k)) for k in ('baseline_score','candidate_score'))
    config = update.get('configuration') or {}
    metric = config.get('gate_metric')
    if metric not in ('hard','soft','mixed'): metric = None
    action = gate.get('gate_action')
    if action not in ('accept_new_best','accept','reject','reject_incomplete','reject_unverified'):
        action = None
    raw_trials = gate.get('gate_trials'); trials = None
    if type(raw_trials) is list:
        trials = []
        for row in raw_trials:
            require(row.get('target') in ('skill','memory','final'), 'invalid_gate_target')
            raw_deltas = row.get('task_deltas'); statuses = None
            if type(raw_deltas) is list:
                statuses = {key:sum(type(r) is dict and r.get('status') == key for r in raw_deltas)
                            for key in ('improved','unchanged','regressed')}
                statuses['unknown'] = len(raw_deltas) - sum(statuses.values())
            trials.append({'target':row['target'],'baseline_score':score(row.get('baseline_score')),
                'candidate_score':score(row.get('candidate_score')),
                'accepted':row['accepted'] if type(row.get('accepted')) is bool else None,
                'blocked_by_regression':row['blocked_by_regression'] if type(row.get('blocked_by_regression')) is bool else None,
                'task_status_counts':statuses})
    return {'baseline_score':baseline,'candidate_score':candidate,'gate_action':action,'gate_trials':trials,
        'score_metric':metric,'mixed_weight':score(config.get('gate_mixed_weight')),
        'no_regression':config['gate_no_regression'] if type(config.get('gate_no_regression')) is bool else None,
        'interpretation':'Historical selection evidence only. baseline_score is the original VAL reference; candidate_score is fresh final VAL and evaluates the incumbent if no edit survived the trial stage. Candidate trial scores are in gate_trials. Trial acceptance is not deployed adoption. Missing values stay unknown.'}


def _physical(raw):
    fields = audit_scale_v2.FIELDS
    result = {k: count(raw[k]) for k in fields}
    require(raw['accounting_complete'] is True and result['unresolved_records'] == 0,
            'incomplete_physical_accounting')
    require(result['known_input_tokens'] + result['known_output_tokens'] == result['known_tokens']
            and result['charged_or_reserved_model_calls'] == result['known_physical_calls']
            and result['charged_or_reserved_tokens'] == result['known_tokens'], 'physical_cost_closure')
    return {**result, 'accounting_complete': True}


def _actor(raw):
    fields = ('logical_requests', 'measured_physical_requests', 'measured_tokens', 'unknown_requests', 'reserved_output_tokens')
    result = {k: count(raw[k]) for k in fields}
    require(raw['accounting_complete'] is True and result['unknown_requests'] == 0 and not raw.get('issues'),
            'incomplete_contracted_actor_accounting')
    return {**result, 'accounting_complete': True,
        'scope': 'reconciled_contracted_client_interviews_only; bootstrap_social_and_native_server_orphans_excluded'}


def _loaded(exposure, state):
    """Supplement frozen deployment exposure without claiming a file was used."""
    rows = []
    for employee in exposure['employees']:
        versions = []
        for version in employee['versions']:
            selected = [r for r in state['sessions'] if r['employee'] == employee['employee']
                        and r['skill_version'] == version['version']]
            require(len(selected) == version['sessions'], 'version_load_exposure_mismatch')
            versions.append({'version': version['version'], 'sessions': len(selected),
                'loaded': sum(r.get('skill_loaded') is True for r in selected),
                'not_loaded': sum(r.get('skill_loaded') is False for r in selected),
                'unknown': sum(type(r.get('skill_loaded')) is not bool for r in selected)})
        rows.append({'employee': employee['employee'], 'versions': versions})
    return rows


def _lifecycle(raw, identifiers, workers):
    require(raw.get('ok') is True, 'completed_lifecycle_required')
    worlds = raw['worlds']
    require(len(worlds) == 6 and {r['run_id'] for r in worlds} == identifiers, 'lifecycle_inventory_mismatch')
    def safe(row, service=False):
        require(row.get('ok') is True and row.get('cleanup_confirmed') is True and not row.get('errors'),
                'completed_cleanup_required')
        require(type(row['root_exitcode']) is int and (service or row['root_exitcode'] == 0), 'world_exit_failure')
        start, cleanup, end = (number(row[k]) for k in ('started_monotonic', 'cleanup_started_monotonic', 'ended_monotonic'))
        require(start <= cleanup <= end, 'lifecycle_clock_order')
        hashes = row['hashes']; prefix = 'SERVICE_' if service else 'WORLD_'
        require(type(hashes) is dict and bool(hashes), 'missing_lifecycle_hashes')
        require(all(re.fullmatch(prefix + r'(INTENT|START|OBSERVATION|READY|CLEANUP)\.json', k)
                    for k in hashes), 'unsafe_lifecycle_hash_key')
        return {'cleanup_confirmed': True, 'root_exitcode': row['root_exitcode'],
            'execution_elapsed_seconds': cleanup - start, 'cleanup_elapsed_seconds': end - cleanup,
            'cleanup_limit_seconds': count(row['cleanup_limit_seconds']),
            'receipt_sha256': {k: _digest(v) for k, v in hashes.items()}}
    result = {'service': safe(raw['service'], True),
        'worlds': [{'run_id': r['run_id'], **safe(r)} for r in worlds],
        'peak_parallel_worlds': count(raw['peak_parallel_worlds'])}
    require(result['peak_parallel_worlds'] <= workers, 'concurrency_limit')
    return result


def _audit(root, campaign_sha, identifiers):
    result = audit_scale_v2.audit_campaign_v2(root, campaign_sha256=campaign_sha, strict=True)
    require(result.get('ok') is True and result.get('status') == 'valid_completed' and not result.get('errors')
            and result.get('completed_runs') == 6 and result.get('complete_pairs') == 3
            and result.get('primary_endpoint_available') is True
            and result.get('campaign_sha256') == campaign_sha, 'strict_completed_campaign_audit_required')
    runs = result['runs']
    require(len(runs) == 6 and {r['run_id'] for r in runs} == identifiers
            and all(r.get('ok') is True and r.get('completed') is True and r.get('status') == 'completed'
                    for r in runs), 'audit_inventory_mismatch')
    comparison = result['comparison']
    require(not comparison.get('rejected_pairs') and not comparison.get('incomplete_pairs')
            and len(comparison['eligible_pairs']) == 3
            and {r['seed'] for r in comparison['eligible_pairs']} == {211,307,401}, 'all_three_audited_pairs_required')
    for scope in ('employee_and_optimizer', 'contracted_interviews'):
        require(result['accounting'][scope]['all_world_costs_reconciled'] is True,
                'completed_campaign_costs_required')
    return result


def _markdown(summary):
    lines = ['# Scale-v2 completed development comparison — draft', '',
        'All six registered worlds and all three pairs passed the strict native audit and cleanup checks.',
        f"Registered campaign SHA-256: `{summary['provenance']['campaign_raw_sha256']}`.", '',
        'Primary: equal-world mean SkillOpt-minus-no-learning fixed-demand fulfillment. Each world has 240 fixed commitments.', '',
        '| Seed | Arm | Fixed fulfilled / placed | All fulfilled / placed | Epochs / adoptions |',
        '| --- | --- | --- | --- | --- |']
    for r in summary['worlds']:
        fixed, all_work, opt = r['primary_fixed_demand'], r['all_commitments'], r['optimizer']
        lines.append(f"| {r['seed']} | {r['algorithm']} | {fixed['fulfilled_before_work_horizon']} / 240 | "
            f"{all_work['fulfilled_before_work_horizon']} / {all_work['accepted_before_work_horizon']} | {opt['epochs']} / {opt['accepted_epochs']} |")
    lines += ['', '| Seed | Fixed-demand difference | All-demand difference | Synthetic utility difference |',
              '| --- | --- | --- | --- |']
    for r in summary['comparison']['pairs']:
        d=r['deltas']; lines.append(f"| {r['seed']} | {d['fixed_demand_fulfillment_rate']:+.4f} | {d['all_commitment_fulfillment_rate']:+.4f} | {d['realized_synthetic_utility']:+.4f} |")
    mean=summary['comparison']['equal_world_mean_deltas']['fixed_demand_fulfillment_rate']
    lines += ['', f'Equal-world mean primary difference: **{mean:+.4f}**. No inferential interval or learning-gain claim is made.', '',
        'JSON retains all employees, eligibility boundaries, epochs, deployed versions and actual loaded/not-loaded/unknown counts.', '',
        '| Measured scope | Physical calls/requests | Tokens |', '| --- | --- | --- |']
    for name in ('online','learning_target','optimizer'):
        r=summary['costs'][name]; lines.append(f"| {name} | {r['known_physical_calls']:,} | {r['known_tokens']:,} |")
    r=summary['costs']['contracted_interviews']
    lines += [f"| Contracted actor interviews | {r['measured_physical_requests']:,} | {r['measured_tokens']:,} |", '',
              'Bootstrap/social inference, server-orphan usage, currency and all-in cost remain unknown.', '',
              *['- '+line for line in CAVEATS], '']
    return '\n'.join(lines)


def report_scale_v2(campaign_dir, out_dir, *, preregistration_path, campaign_sha256):
    """Require externally supplied raw registration hash and strict completed audit.

    Two deterministic strict audits bracket aggregation; source and raw input
    bytes are checked again before any output is created. No bypass or resume.
    """
    root, out, prereg = (Path(p).resolve() for p in (campaign_dir,out_dir,preregistration_path))
    expected_sha = _digest(campaign_sha256)
    require(not out.exists() and not out.is_relative_to(root) and not root.is_relative_to(out), 'new_separate_output_required')
    require(not prereg.is_relative_to(out), 'output_contains_preregistration')
    campaign, raw_sha = common._load(root/'campaign.json'); _, prereg_sha=common._load(prereg)
    require(raw_sha == prereg_sha == expected_sha, 'published_preregistration_raw_hash_mismatch')
    require(campaign['kind'] == contract.VERSION and campaign['schema_version'] == 2
            and campaign['days'] == 20 and campaign['seeds'] == [211,307,401]
            and campaign['population'] == contract.POPULATION, 'registered_design_mismatch')
    slots=campaign['slots']; expected=contract.schedule()
    require(len(slots)==6 and [(s['seed'],s['algorithm']) for s in slots]==expected, 'wrong_planned_worlds')
    for s in slots:
        identifier=f"seed-{s['seed']}-{s['algorithm']}"
        require(s['run_id']==identifier and s['relative_path']=='runs/'+identifier, 'unsafe_or_unplanned_run_identity')
    identifiers={s['run_id'] for s in slots}
    sources=_sources(campaign['source_sha256']); tools=_sources(campaign['registration_tools_sha256'])
    helpers={name:sha((ROOT/name).read_bytes()) for name in HELPERS}
    processor_sha=sha(Path(__file__).read_bytes())
    for name,value in {**sources,**tools}.items():
        require(sha((ROOT/name).read_bytes())==value, 'registered_source_changed')
    hashes={'campaign.json':raw_sha}
    for name in ('EXECUTION.json','execution_results.json','PREREQUISITES.json'):
        hashes[name]=sha((root/name).read_bytes())
    receipt_inventory=_receipt_inventory(root,slots)
    audited=_audit(root,expected_sha,identifiers)
    lifecycle=_lifecycle(audited['lifecycle'],identifiers,campaign['launch_policy']['workers'])
    by_audit={r['run_id']:r for r in audited['runs']}
    records,worlds,states=[],[],{}
    for s in slots:
        identifier=s['run_id']; path=root/s['relative_path']; receipt=by_audit[identifier]; loaded={}
        for name in common.RUN_FILES:
            value,h=common._load(path/name)
            require(receipt['evidence_sha256'].get(name)==h, 'raw_input_changed_since_audit')
            hashes[s['relative_path']+'/'+name]=h;loaded[name]=value
        cp,v1,v2=(loaded[n] for n in ('checkpoint.json','REPORT.json','REPORT.v2.json'))
        require(v1['status']==v2['status']=='completed' and v1['algorithm']==v2['algorithm']==s['algorithm']
                and v2['metric_schema_version']==2 and v2['correction_audit']['eligible_for_paired_inference'] is True
                and not v2['correction_audit']['issues'], 'ineligible_corrected_report')
        require(v2['source_hashes']['checkpoint_sha256']==hashes[s['relative_path']+'/checkpoint.json']
                and v2['source_hashes']['v1_report_sha256']==hashes[s['relative_path']+'/REPORT.json'], 'corrected_report_raw_binding')
        breakdown={k:common._commitments(v2['source_breakdown'][k]) for k in common.SOURCES}
        all_work=common._commitments(v2['commitments'])
        for k in common.COMMITMENT_FIELDS:
            require(breakdown['initial'][k]+breakdown['benchmark'][k]==breakdown['fixed_initial_and_benchmark'][k]
                and sum(breakdown[a][k] for a in ('initial','benchmark','native_consumer','unknown'))==all_work[k], 'commitment_source_partition')
        require(breakdown['fixed_initial_and_benchmark']['accepted_before_work_horizon']==240, 'fixed_demand_denominator_changed')
        state=cp['runner']; states[identifier]=state
        # Reuse the existing checkpoint/report accounting reconciliation too.
        reported_costs=common._costs(v1,state)
        physical={k:_physical(receipt['employee_costs']['scopes'][k]) for k in ('online','learning_target','optimizer','learning_unknown')}
        require(physical['learning_unknown']['records']==0, 'unresolved_learning_costs')
        total=_physical(receipt['employee_costs']['total'])
        require(audit_scale_v2.totals(list(physical.values()))==total, 'world_physical_scope_totals')
        require(physical['online']['known_tokens']==reported_costs['online']['tokens']['total']
                and physical['online']['known_physical_calls']==reported_costs['online']['model_calls']['total']
                and physical['online']['charged_or_reserved_tokens']==reported_costs['online']['charged_tokens']['total']
                and physical['online']['known_input_tokens']==reported_costs['online']['prompt_tokens']['total']
                and physical['online']['known_output_tokens']==reported_costs['online']['completion_tokens']['total']
                and physical['learning_target']['known_tokens']+physical['optimizer']['known_tokens']==reported_costs['learning']['tokens']['total']
                and physical['learning_target']['known_physical_calls']==reported_costs['learning']['target_model_calls']['total']
                and physical['optimizer']['known_physical_calls']==reported_costs['learning']['optimizer_model_calls']['total']
                and physical['learning_target']['charged_or_reserved_tokens']+physical['optimizer']['charged_or_reserved_tokens']==reported_costs['learning']['charged_or_reserved_tokens']['total'], 'physical_report_cost_mismatch')
        actor=_actor(receipt['contracted_interview_costs'])
        dynamics=scale_world_dynamics.summarize_world_dynamics(cp)
        require(dynamics['evidence_complete'] is True and not dynamics['evidence_issues'], 'world_dynamics_evidence_incomplete')
        native_orders=[o for c in dynamics['consumers'] for o in c['endogenous_orders'] if o['day']<20]
        require(len(native_orders)==breakdown['native_consumer']['accepted_before_work_horizon'], 'world_dynamics_native_commitment_count_mismatch')
        business={'realized_utility':number(v1['business']['realized_utility'],nonnegative=False), 'unit':'synthetic_utility_not_currency',
            **{k:count(v1['business'][k]) for k in ('settled_entries','unsettled_entries','reward_censored_obligations')}}
        optimizer=common._optimizer(state['updates'])
        for row, update in zip(optimizer['updates'], state['updates']):
            row['gate_trace']=_gate_trace(update)
        worlds.append({'run_id':identifier,'seed':s['seed'],'algorithm':s['algorithm'],'status':'completed',
            'primary_fixed_demand':breakdown['fixed_initial_and_benchmark'],'all_commitments':all_work,
            'commitment_sources':breakdown,'business':business,'online':common._online(state,v1),
            'optimizer':optimizer,'costs':{**physical,'employee_and_optimizer':total,'contracted_interviews':actor},
            'world_dynamics':dynamics})
        records.append({'run_id':identifier,'checkpoint':cp,'report':v1})
    exposure=scale_summary.build_scale_summary(campaign,records)
    require(exposure['complete'] is True and not exposure['evidence_issues'], 'incomplete_learning_exposure')
    for run in exposure['runs']:
        run['actual_skill_loading']=_loaded(run,states[run['run_id']])
    costs={k:audit_scale_v2.totals([w['costs'][k] for w in worlds]) for k in ('online','learning_target','optimizer','employee_and_optimizer')}
    require(costs['employee_and_optimizer']==_physical(audited['accounting']['employee_and_optimizer']), 'audit_campaign_cost_mismatch')
    actor_fields=('logical_requests','measured_physical_requests','measured_tokens','unknown_requests','reserved_output_tokens')
    costs['contracted_interviews']={k:sum(w['costs']['contracted_interviews'][k] for w in worlds) for k in actor_fields}
    require(all(costs['contracted_interviews'][k]==audited['accounting']['contracted_interviews'][k] for k in actor_fields), 'actor_campaign_cost_mismatch')
    costs['contracted_interviews'].update(accounting_complete=True,scope='reconciled_contracted_client_interviews_only')
    costs.update(unmetered_environment={'physical_model_calls':None,'tokens':None,'accounting_complete':False},
                 currency_cost=None,all_in_cost=None,all_in_accounting_complete=False,
                 replay_count_interpretation='Learning-target physical receipt records may include an unscored terminal timing stop; they are not a count of scored gate trials.')
    comparison=common._pairs(worlds)
    # The generic auditor also reports all-demand as canonical_headline. Explicitly
    # select the registered fixed-demand primary and reconcile both deltas.
    for pair in comparison['pairs']:
        raw=next(p for p in audited['comparison']['eligible_pairs'] if p['seed']==pair['seed'])
        for ours,theirs in (('fixed_demand_fulfillment_rate','fixed_demand_fulfillment_rate'),
                            ('all_commitment_fulfillment_rate','commitment_fulfillment_rate')):
            require(close(pair['deltas'][ours],raw['deltas'][theirs]), 'audited_pair_metric_mismatch')
    summary={'schema_version':1,'report_version':VERSION,'kind':'completed_scale_v2_development_publication_draft',
        'complete':True,'planned_worlds':6,'completed_worlds':6,'world_pairs':3,'work_days':20,'settlement_only_days':2,
        'primary_endpoint':{'metric':'fixed_demand_fulfillment_rate','denominator_per_world':240,
            'direction':'skillopt minus no_learning','weighting':'equal world pair',
            'value':comparison['equal_world_mean_deltas']['fixed_demand_fulfillment_rate']},
        'provenance':{'hash_encoding':'sha256_raw_file_bytes','campaign_raw_sha256':raw_sha,
            'published_preregistration_raw_sha256':prereg_sha,
            'postprocessor':{'path':'scripts/report_scale_v2.py','version':VERSION,'sha256':processor_sha,'helper_source_sha256':helpers},
            'execution_source_sha256':sources,'registration_tools_sha256':tools,'raw_input_sha256':hashes,
            'raw_receipt_inventory':{'files':len(receipt_inventory),
                'sha256':sha(json.dumps(receipt_inventory,sort_keys=True,separators=(',',':')).encode()),
                'hash_encoding':'sorted_compact_json_mapping_private_relative_names_to_raw_sha256',
                'scope':'contracted actor cache and ledger; online/replay sessions; learning update/progress; case capsules'},
            'strict_audit':{'status':'valid_completed','completed_runs':6,'complete_pairs':3,'primary_endpoint_available':True,
                'audit_result_sha256':sha(json.dumps(audited,sort_keys=True,allow_nan=False).encode()),'audit_result_hash_encoding':'sorted_json_default_separators'}},
        'lifecycle':lifecycle,'worlds':worlds,'comparison':comparison,'learning_exposure':exposure,'costs':costs,'limitations':CAVEATS}
    # Re-audit complete native evidence to reject changes to source sessions,
    # grades, profiles, actor receipts or lifecycle evidence during aggregation.
    require(_audit(root,expected_sha,identifiers)==audited, 'native_evidence_changed_during_reporting')
    require(_receipt_inventory(root,slots)==receipt_inventory, 'raw_receipt_inventory_changed_during_reporting')
    require(sha(prereg.read_bytes())==prereg_sha and sha(Path(__file__).read_bytes())==processor_sha
            and all(sha((ROOT/n).read_bytes())==h for n,h in {**sources,**tools,**helpers}.items())
            and all(sha((root/n).read_bytes())==h for n,h in hashes.items()), 'raw_inputs_changed_during_reporting')
    text=json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n'; markdown=_markdown(summary)
    out.mkdir(parents=True,exist_ok=False)
    (out/'SUMMARY.json').write_text(text,encoding='utf-8');(out/'REPORT.md').write_text(markdown,encoding='utf-8')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--preregistration',type=Path,required=True)
    p.add_argument('--campaign-sha256',required=True);a=p.parse_args(argv)
    try: result=report_scale_v2(a.campaign,a.out,preregistration_path=a.preregistration,campaign_sha256=a.campaign_sha256)
    except audit_scale_v2.ERRORS as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__}));return 1
    print(json.dumps({'ok':True,'completed_worlds':result['completed_worlds'],'world_pairs':result['world_pairs'],
                      'outputs':['SUMMARY.json','REPORT.md']}));return 0


if __name__=='__main__':
    raise SystemExit(main())
