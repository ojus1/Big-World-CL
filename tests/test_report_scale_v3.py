"""Artificial completed records with an explicitly mocked native audit.

These offline fixtures validate publication logic, never native benchmark quality.
No active campaign, installed dependency or provider is accessed.
"""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import report_scale_v3 as report
from scripts import scale_v3_contract as contract
from lifespan.evaluation.metrics import _execution_costs
from tests.test_scale_publication import fixture, write, PRIVATE


def physical(calls=0, tokens=0, records=0):
    return {'records':records,'known_physical_calls':calls,'known_input_tokens':tokens,
        'known_output_tokens':0,'known_tokens':tokens,'charged_or_reserved_model_calls':calls,
        'charged_or_reserved_tokens':tokens,'unresolved_records':0,'accounting_complete':True}


def lifecycle(identity=None, *, service=False):
    prefix='SERVICE_' if service else 'WORLD_'
    return {'ok':True,'errors':[],'cleanup_confirmed':True,'root_exitcode':-15 if service else 0,
        'started_monotonic':0,'cleanup_started_monotonic':10,'ended_monotonic':11,
        'cleanup_limit_seconds':30 if service else 120,
        'hashes':{prefix+name+'.json':'c'*64 for name in ('INTENT','START','OBSERVATION','CLEANUP')},
        'simulation_id':PRIVATE,'private_absolute_path':'/private/'+PRIVATE,
        **({'run_id':identity} if identity else {})}


def stub_audit(root, *, campaign_sha256, strict=False):
    """Only these tests use this artificial substitute; it is not a native audit."""
    assert strict is True
    assert report.sha((root/'campaign.json').read_bytes())==campaign_sha256
    campaign=json.loads((root/'campaign.json').read_bytes());runs=[];pairs=[]
    for slot in campaign['slots']:
        path=root/slot['relative_path'];cp=json.loads((path/'checkpoint.json').read_bytes());s=cp['runner']
        online=physical(sum(x['usage']['api_calls'] for x in s['sessions']),sum(x['usage']['total_tokens'] for x in s['sessions']),len(s['sessions']))
        online['known_input_tokens']=sum(x['usage']['prompt_tokens'] for x in s['sessions'])
        online['known_output_tokens']=sum(x['usage']['completion_tokens'] for x in s['sessions'])
        opt_calls=sum(x['costs']['optimizer_model_calls'] for x in s['updates'])
        total_learning=sum(x['costs']['tokens'] for x in s['updates'])
        optimizer=physical(opt_calls,100*opt_calls,len(s['updates']))
        targets=physical(sum(x['costs']['target_model_calls'] for x in s['updates']),total_learning-optimizer['known_tokens'],sum(x['costs']['replays'] for x in s['updates']))
        scopes={'online':online,'learning_target':targets,'optimizer':optimizer,'learning_unknown':physical()}
        runs.append({'run_id':slot['run_id'],'seed':slot['seed'],'algorithm':slot['algorithm'],
            'ok':True,'status':'completed','completed':True,
            'evidence_sha256':{n:report.sha((path/n).read_bytes()) for n in report.common.RUN_FILES},
            'employee_costs':{'scopes':scopes,'total':report.accounting.totals(list(scopes.values()))},
            'contracted_interview_costs':{'logical_requests':10,'measured_physical_requests':10,
                'measured_tokens':500,'unknown_requests':0,'reserved_output_tokens':0,'accounting_complete':True,
                'request_id':PRIVATE,'provider_error':PRIVATE},'private':PRIVATE})
    for seed in (211,307,401):
        by_arm={s['algorithm']:json.loads((root/s['relative_path']/'REPORT.v2.json').read_bytes()) for s in campaign['slots'] if s['seed']==seed}
        fixed=lambda a:by_arm[a]['source_breakdown']['fixed_initial_and_benchmark']['fulfillment_rate']
        all_work=lambda a:by_arm[a]['commitments']['fulfillment_rate']
        pairs.append({'seed':seed,'deltas':{'fixed_demand_fulfillment_rate':fixed('skillopt')-fixed('no_learning'),
            'commitment_fulfillment_rate':all_work('skillopt')-all_work('no_learning')}})
    totals=report.accounting.totals([r['employee_costs']['total'] for r in runs]);totals['all_world_costs_reconciled']=True
    return {'ok':True,'status':'valid_completed','errors':[],'campaign_sha256':campaign_sha256,
        'planned_runs':6,'planned_pairs':3,'completed_runs':6,'complete_pairs':3,'primary_endpoint_available':True,'runs':runs,
        'comparison':{'eligible_pairs':pairs,'rejected_pairs':[],'incomplete_pairs':[],
            'canonical_headline':'commitment_fulfillment_rate','bootstrap_95_percent_interval':[-99,99],'private':PRIVATE},
        'accounting':{'employee_and_optimizer':totals,'contracted_interviews':{'logical_requests':60,
            'measured_physical_requests':60,'measured_tokens':3000,'unknown_requests':0,'reserved_output_tokens':0,
            'all_world_costs_reconciled':True},'private':PRIVATE},
        'lifecycle':{'ok':True,'service':lifecycle(service=True),'worlds':[lifecycle(s['run_id']) for s in campaign['slots']],
            'peak_parallel_worlds':2,'pair_barriers':{'planned_pair_batches':3,'observed_following_pair_barriers':2,'prior_pair_requires_normal_exit_and_confirmed_cleanup':True}},
        'outer_scope':{'ok':True,'scope_passed':True,'scope_complete':True,'inner_completed':True,
            'inner_supervisor_identity_bound':True,'native_wait_exit_code':0,'inner_result_exit_code':0,
            'raw_evidence_hashes':['d'*64]*9,'private':PRIVATE},'provider_id':PRIVATE}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.base=Path(self.temp)
        self.raw=self.base/'raw';self.out=self.base/'public';self.prereg=self.base/'published.json'
        self.campaign=fixture(self.raw)
        self.campaign.update(kind=contract.VERSION,schema_version=3,days=20,seeds=[211,307,401],population=contract.POPULATION,
            registration_tools_sha256={'scripts/audit_scale_v3.py':report.sha((report.ROOT/'scripts/audit_scale_v3.py').read_bytes())},
            launch_policy={'workers':2})
        by_key={(s['seed'],s['algorithm']):s for s in self.campaign['slots']}
        self.campaign['slots']=[by_key[k] for k in contract.schedule()]
        for s in self.campaign['slots']:
            path=self.raw/s['relative_path'];cp=json.loads((path/'checkpoint.json').read_bytes())
            for x in cp['runner']['sessions']:x['usage']['charged_tokens']=x['usage']['total_tokens']
            cp['runner']['sessions'][0]['skill_loaded']=False
            cp['runner']['sessions'][1].pop('skill_loaded')
            write(path/'checkpoint.json',cp)
            v1=json.loads((path/'REPORT.json').read_bytes());v1['costs']['execution']=_execution_costs(cp['runner']['sessions']);write(path/'REPORT.json',v1)
            self.rebind(s)
            write(path/'actors/evaluation_interview_ledger.json',{'fixture':True,'private':PRIVATE})
            for index in range(10):
                write(path/'actors/mirofish_interviews'/f'fixture-{index}.json',{'fixture':True,'private':PRIVATE})
        for name in ('INTENT','LAUNCH','HELLO','GATE','INNER_RESULT','DRAINED','RELEASE','CONTROLLER_EXIT','TERMINAL'):
            write(self.raw/'scope'/(name+'.json'),{'fixture':True,'private':PRIVATE})
        for name in ('INTENT','START','OBSERVATION','READY','CLEANUP'):
            write(self.raw/('SERVICE_'+name+'.json'),{'fixture':True,'private':PRIVATE})
        for s in self.campaign['slots']:
            path=self.raw/s['relative_path'];write(path/'config.json',s['config'])
            for name in ('INTENT','START','OBSERVATION','CLEANUP'):
                write(path/'lifecycle'/('WORLD_'+name+'.json'),{'fixture':True,'private':PRIVATE})
        write(self.raw/'campaign.json',self.campaign);write(self.raw/'PREREQUISITES.json',{'private':PRIVATE})
        self.registration()
        self.auditor=self.enterContext(patch.object(report.audit_scale_v3,'audit_campaign_v3',side_effect=stub_audit))

    def registration(self):
        self.prereg.write_bytes((self.raw/'campaign.json').read_bytes());self.sha=report.sha(self.prereg.read_bytes())

    def rebind(self,slot):
        path=self.raw/slot['relative_path'];v2=json.loads((path/'REPORT.v2.json').read_bytes())
        v2['source_hashes']={'checkpoint_sha256':report.sha((path/'checkpoint.json').read_bytes()),'v1_report_sha256':report.sha((path/'REPORT.json').read_bytes())}
        write(path/'REPORT.v2.json',v2)

    def generate(self):
        return report.report_scale_v3(self.raw,self.out,preregistration_path=self.prereg,campaign_sha256=self.sha)

    def bad_audit(self,fn):
        def altered(*args,**kw):
            value=stub_audit(*args,**kw);fn(value);return value
        self.auditor.side_effect=altered

    def test_complete_fixture_primary_all_worlds_and_all_epochs(self):
        result=self.generate()
        self.assertEqual((result['completed_worlds'],result['world_pairs']),(6,3))
        self.assertAlmostEqual(result['primary_endpoint']['value'],.05)
        self.assertNotAlmostEqual(result['primary_endpoint']['value'],result['comparison']['equal_world_mean_deltas']['all_commitment_fulfillment_rate'])
        self.assertEqual(result['primary_endpoint']['metric'],'fixed_demand_fulfillment_rate')
        self.assertIsNone(result['comparison']['confidence_interval'])
        self.assertEqual(result['learning_exposure']['planned_employee_world_instances'],72)
        self.assertEqual(result['learning_exposure']['planned_learning_boundaries'],288)
        self.assertEqual(result['learning_exposure']['recorded_updates'],9)
        self.assertEqual(sum(w['optimizer']['gate_unreported_epochs'] for w in result['worlds']),3)
        self.assertEqual(self.auditor.call_count,2)
        self.assertTrue(result['outer_scope']['scope_passed'])
        self.assertEqual(result['lifecycle']['pair_barriers']['observed_following_pair_barriers'],2)
        self.assertEqual(result['provenance']['strict_audit']['stable_completed_audits'],2)

    def test_startup_qualification_cannot_substitute_for_completed_study(self):
        self.campaign.update(kind='hermes-startup-scope-qualification-v3',schema_version=3)
        write(self.raw/'campaign.json',self.campaign);self.registration()
        with self.assertRaisesRegex(ValueError,'registered_design_mismatch'):self.generate()
        self.auditor.assert_not_called();self.assertFalse(self.out.exists())

    def test_scope_completion_identity_and_both_native_exits_are_mandatory(self):
        for key,value in (('ok',False),('scope_passed',False),('scope_complete',False),
                ('inner_completed',False),('inner_supervisor_identity_bound',False),
                ('native_wait_exit_code',None),('native_wait_exit_code',False),
                ('inner_result_exit_code',9)):
            with self.subTest(key=key,value=value):
                self.bad_audit(lambda a:a['outer_scope'].update({key:value}))
                with self.assertRaisesRegex(ValueError,'completed_outer_scope_required|completed_scope_native_exit_required'):self.generate()
                self.assertFalse(self.out.exists())

    def test_fixed_pair_barriers_and_two_worker_envelope_cannot_be_dropped(self):
        self.bad_audit(lambda a:a['lifecycle']['pair_barriers'].update(observed_following_pair_barriers=1))
        with self.assertRaisesRegex(ValueError,'completed_fixed_pair_barriers_required'):self.generate()
        self.bad_audit(lambda a:a['lifecycle'].update(peak_parallel_worlds=3))
        with self.assertRaisesRegex(ValueError,'concurrency_limit'):self.generate()
        self.bad_audit(lambda a:None)
        self.campaign['launch_policy']['workers']=6;write(self.raw/'campaign.json',self.campaign);self.registration()
        with self.assertRaisesRegex(ValueError,'registered_parallel_worlds_changed'):self.generate()

    def test_study_scope_receipt_required_even_if_stub_audit_claims_success(self):
        (self.raw/'scope/CONTROLLER_EXIT.json').unlink()
        with self.assertRaisesRegex(ValueError,'missing_study_scope_receipt'):self.generate()
        self.auditor.assert_not_called();self.assertFalse(self.out.exists())

    def test_scope_and_lifecycle_equivalent_json_reformat_cannot_hide_between_audits(self):
        original=report.common._pairs
        for relative in ('scope/TERMINAL.json','SERVICE_CLEANUP.json',
                self.campaign['slots'][0]['relative_path']+'/lifecycle/WORLD_CLEANUP.json'):
            with self.subTest(relative=relative):
                path=self.raw/relative;before=path.read_bytes()
                def mutate(worlds):
                    path.write_text(json.dumps(json.loads(path.read_bytes()),separators=(',',':')))
                    return original(worlds)
                with patch.object(report.common,'_pairs',side_effect=mutate):
                    with self.assertRaisesRegex(ValueError,'raw_receipt_inventory_changed'):self.generate()
                self.assertFalse(self.out.exists());path.write_bytes(before)

    def test_status_failure_and_extra_scope_receipt_inventory_changes_refuse(self):
        original=report.common._pairs
        for relative in ('STATUS.json','SUPERVISOR_INTERRUPTED.json','scope/new-diagnostic.json',
                self.campaign['slots'][0]['relative_path']+'/FAILURE.json',
                self.campaign['slots'][0]['relative_path']+'/REPORTING_FAILURE.json',
                self.campaign['slots'][0]['relative_path']+'/INFLIGHT',
                self.campaign['slots'][0]['relative_path']+'/learning/fixture/FAILURE.json'):
            with self.subTest(relative=relative):
                path=self.raw/relative
                def mutate(worlds):write(path,{'private':PRIVATE});return original(worlds)
                with patch.object(report.common,'_pairs',side_effect=mutate):
                    with self.assertRaisesRegex(ValueError,'raw_receipt_inventory_changed'):self.generate()
                self.assertFalse(self.out.exists());path.unlink()

    def test_scope_receipt_symlink_refused_before_audit(self):
        path=self.raw/'scope/TERMINAL.json';path.unlink();path.symlink_to(self.prereg)
        with self.assertRaisesRegex(ValueError,'receipt_inventory_symlink_or_escape'):self.generate()
        self.auditor.assert_not_called()

    def test_all_employee_boundaries_and_epochs_cannot_be_projected_as_subset(self):
        actual=report.scale_summary.build_scale_summary
        for key in ('planned_employee_world_instances','planned_learning_boundaries','observed_learning_boundaries','recorded_updates'):
            def subset(*args,**kwargs):
                value=actual(*args,**kwargs);value[key]-=1;return value
            with patch.object(report.scale_summary,'build_scale_summary',side_effect=subset):
                with self.assertRaisesRegex(ValueError,'complete_employee_boundary_epoch_inventory_required'):self.generate()
            self.assertFalse(self.out.exists())

    def test_loaded_not_loaded_unknown_distinct_from_deployed_exposure(self):
        result=self.generate();run=result['learning_exposure']['runs'][1]
        employee=next(x for x in run['actual_skill_loading'] if x['employee']=='firm-0__incident-regulated')
        self.assertEqual(employee['versions'],[{'version':0,'sessions':2,'loaded':0,'not_loaded':1,'unknown':1},
                                              {'version':1,'sessions':2,'loaded':2,'not_loaded':0,'unknown':0}])
        self.assertEqual(len(run['actual_skill_loading']),12)

    def test_separate_physical_costs_no_replay_double_count_unknown_environment(self):
        costs=self.generate()['costs']
        self.assertEqual(costs['online']['known_tokens'],2400)
        self.assertEqual(costs['learning_target']['known_tokens'],8100)
        self.assertEqual(costs['optimizer']['known_tokens'],900)
        self.assertEqual(costs['employee_and_optimizer']['known_tokens'],11400)
        self.assertEqual(costs['contracted_interviews']['measured_tokens'],3000)
        self.assertIsNone(costs['currency_cost']);self.assertIsNone(costs['all_in_cost'])
        self.assertIsNone(costs['unmetered_environment']['tokens'])

    def test_safe_export_and_source_bound_helpers(self):
        raw_before={str(p):p.read_bytes() for p in self.raw.rglob('*.json')}
        result=self.generate();public=(self.out/'SUMMARY.json').read_text()+(self.out/'REPORT.md').read_text()
        self.assertNotIn(PRIVATE,public);self.assertNotIn(str(self.base),public)
        self.assertNotIn('simulation_id',public);self.assertNotIn('provider_id',public)
        self.assertNotIn('bootstrap_95_percent_interval',public)
        self.assertEqual(set(result['provenance']['postprocessor']['helper_source_sha256']),set(report.HELPERS))
        self.assertEqual(raw_before,{str(p):p.read_bytes() for p in self.raw.rglob('*.json')})
        self.assertEqual({p.name for p in self.out.iterdir()},{'SUMMARY.json','REPORT.md'})

    def test_incomplete_and_invalid_audit_refuse_without_output(self):
        for status in ('incomplete','invalid'):
            with self.subTest(status=status):
                self.bad_audit(lambda a:a.update(ok=False,status=status))
                with self.assertRaisesRegex(ValueError,'strict_completed'):self.generate()
                self.assertFalse(self.out.exists())

    def test_five_runs_or_two_pairs_cannot_complete(self):
        self.bad_audit(lambda a:a['runs'].pop())
        with self.assertRaisesRegex(ValueError,'audit_inventory'):self.generate()
        self.bad_audit(lambda a:a['comparison']['eligible_pairs'].pop())
        with self.assertRaisesRegex(ValueError,'all_three'):self.generate()

    def test_subset_registration_rejected_even_with_matching_new_hash(self):
        self.campaign['slots'].pop();write(self.raw/'campaign.json',self.campaign);self.registration()
        with self.assertRaisesRegex(ValueError,'wrong_planned'):self.generate()
        self.auditor.assert_not_called()

    def test_registration_raw_hash_not_json_equivalence(self):
        self.prereg.write_bytes(self.prereg.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'raw_hash_mismatch'):self.generate()
        self.auditor.assert_not_called()

    def test_external_hash_required_after_coherent_registration_rewrite(self):
        write(self.raw/'campaign.json',{**self.campaign,'private':'rewritten'})
        self.prereg.write_bytes((self.raw/'campaign.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'raw_hash_mismatch'):self.generate()

    def test_cleanup_and_actor_unknowns_block_even_if_top_level_claims_pass(self):
        self.bad_audit(lambda a:a['lifecycle']['worlds'][0].update(cleanup_confirmed=False))
        with self.assertRaisesRegex(ValueError,'completed_cleanup'):self.generate()
        self.bad_audit(lambda a:a['runs'][0]['contracted_interview_costs'].update(accounting_complete=False,unknown_requests=1))
        with self.assertRaisesRegex(ValueError,'incomplete_contracted'):self.generate()

    def test_changed_native_audit_between_passes_refuses(self):
        count_calls=[0]
        def changing(*args,**kw):
            value=stub_audit(*args,**kw);count_calls[0]+=1
            if count_calls[0]==2:value['unseen_raw_hash']='d'*64
            return value
        self.auditor.side_effect=changing
        with self.assertRaisesRegex(ValueError,'native_evidence_changed'):self.generate()
        self.assertFalse(self.out.exists())

    def test_changed_checkpoint_after_audit_refuses(self):
        def mutate(*args,**kw):
            result=stub_audit(*args,**kw);p=self.raw/self.campaign['slots'][0]['relative_path']/'checkpoint.json'
            p.write_bytes(p.read_bytes()+b'\n');return result
        self.auditor.side_effect=mutate
        with self.assertRaisesRegex(ValueError,'raw_input_changed'):self.generate()

    def test_pair_primary_not_taken_from_generic_headline(self):
        self.bad_audit(lambda a:a['comparison']['eligible_pairs'][0]['deltas'].update(fixed_demand_fulfillment_rate=.9))
        with self.assertRaisesRegex(ValueError,'audited_pair_metric'):self.generate()

    def test_unsafe_source_metadata_and_source_mismatch_refuse(self):
        self.campaign['source_sha256']={'../../private/'+PRIVATE:'b'*64}
        write(self.raw/'campaign.json',self.campaign);self.registration()
        with self.assertRaisesRegex(ValueError,'unsafe_source'):self.generate()
        self.campaign['source_sha256']={'lifespan/evaluation/tasks.py':'b'*64}
        write(self.raw/'campaign.json',self.campaign);self.registration()
        with self.assertRaisesRegex(ValueError,'registered_source_changed'):self.generate()

    def test_existing_output_and_raw_nested_output_refuse(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError,'new_separate'):self.generate()
        self.out=self.raw/'public'
        with self.assertRaisesRegex(ValueError,'new_separate'):self.generate()

    def test_premature_version_exposure_and_unknown_employee_refuse(self):
        slot=self.campaign['slots'][1];p=self.raw/slot['relative_path']/'checkpoint.json';cp=json.loads(p.read_bytes())
        cp['runner']['sessions'][0]['skill_version']=1;write(p,cp);self.rebind(slot)
        with self.assertRaisesRegex(ValueError,'incomplete_learning_exposure'):self.generate()

    def test_scope_call_redistribution_cannot_hide_behind_equal_grand_total(self):
        def changed(a):
            row=next(r for r in a['runs'] if r['algorithm']=='skillopt')
            for key in ('known_physical_calls','charged_or_reserved_model_calls'):
                row['employee_costs']['scopes']['learning_target'][key]-=1
                row['employee_costs']['scopes']['optimizer'][key]+=1
        self.bad_audit(changed)
        with self.assertRaisesRegex(ValueError,'physical_report_cost_mismatch'):self.generate()
        self.assertFalse(self.out.exists())

    def test_online_token_split_cannot_compensate_with_equal_total(self):
        def changed(a):
            row=a['runs'][0]
            for target in (row['employee_costs']['scopes']['online'],row['employee_costs']['total'],a['accounting']['employee_and_optimizer']):
                target['known_input_tokens']-=1;target['known_output_tokens']+=1
        self.bad_audit(changed)
        with self.assertRaisesRegex(ValueError,'physical_report_cost_mismatch'):self.generate()

    def test_zero_adoptions_does_not_block_complete_endpoint(self):
        for slot in self.campaign['slots']:
            path=self.raw/slot['relative_path'];cp=json.loads((path/'checkpoint.json').read_bytes())
            for session in cp['runner']['sessions']:session['skill_version']=0
            for update in cp['runner']['updates']:
                update.update(accepted=False,parent_version=0,deployed_version=0)
                gate=update['gate_evidence']
                if 'applied_edits' in gate:
                    gate['rejected_edits']+=gate['applied_edits'];gate['applied_edits']=[]
                    for trial in gate['gate_trials']:trial['accepted']=False
            write(path/'checkpoint.json',cp);self.rebind(slot)
        result=self.generate()
        self.assertTrue(result['complete']);self.assertEqual(result['learning_exposure']['accepted_updates'],0)
        self.assertEqual(len(result['comparison']['pairs']),3)

    def test_fixed_denominator_cannot_be_changed_coherently(self):
        from tests.test_scale_publication import commitment
        slot=self.campaign['slots'][0];path=self.raw/slot['relative_path']/'REPORT.v2.json'
        value=json.loads(path.read_bytes());value['source_breakdown']['benchmark']=commitment(227,168)
        value['source_breakdown']['fixed_initial_and_benchmark']=commitment(239,180)
        value['commitments']=commitment(241,181);write(path,value)
        with self.assertRaisesRegex(ValueError,'fixed_demand_denominator_changed'):self.generate()

    def test_later_fulfillment_does_not_change_action_horizon_primary(self):
        # The artificial no-learning observations improve only after the work
        # horizon. A reporter must retain both numbers without switching which
        # one defines the registered paired endpoint.
        for slot in self.campaign['slots']:
            if slot['algorithm'] != 'no_learning':continue
            path=self.raw/slot['relative_path']/'REPORT.v2.json'
            value=json.loads(path.read_bytes())
            rows=[value['source_breakdown'][key] for key in ('benchmark','fixed_initial_and_benchmark')]
            rows.append(value['commitments'])
            for row in rows:
                row['fulfilled_at_observation']+=40
                row['unfulfilled_at_observation']-=40
                row['pending_at_observation']-=40
                row['right_censored_unfulfilled']-=40
                row['settled_at_observation']+=40
            write(path,value)
        result=self.generate()
        self.assertAlmostEqual(result['primary_endpoint']['value'],.05)
        for world in result['worlds']:
            if world['algorithm']=='no_learning':
                fixed=world['primary_fixed_demand']
                self.assertEqual(fixed['fulfilled_before_work_horizon'],180)
                self.assertEqual(fixed['fulfilled_at_observation'],220)
        self.assertIn('180 / 240',(self.out/'REPORT.md').read_text())

    def test_negative_mean_and_mixed_seed_differences_keep_all_three_pairs(self):
        from tests.test_scale_publication import commitment
        fulfilled={211:164,307:180,401:192}
        for slot in self.campaign['slots']:
            if slot['algorithm']!='skillopt':continue
            path=self.raw/slot['relative_path']/'REPORT.v2.json'
            value=json.loads(path.read_bytes());successes=fulfilled[slot['seed']]
            value['source_breakdown']['benchmark']=commitment(228,successes-12)
            value['source_breakdown']['fixed_initial_and_benchmark']=commitment(240,successes)
            value['commitments']=commitment(243,successes+2)
            write(path,value)
        result=self.generate()
        self.assertTrue(result['complete'])
        self.assertEqual(result['completed_worlds'],6)
        pairs=result['comparison']['pairs']
        self.assertEqual([row['seed'] for row in pairs],[211,307,401])
        self.assertLess(pairs[0]['deltas']['fixed_demand_fulfillment_rate'],0)
        self.assertEqual(pairs[1]['deltas']['fixed_demand_fulfillment_rate'],0)
        self.assertGreater(pairs[2]['deltas']['fixed_demand_fulfillment_rate'],0)
        self.assertAlmostEqual(result['primary_endpoint']['value'],-4/720)
        self.assertIsNone(result['comparison']['confidence_interval'])

    def test_reporting_helper_mutation_before_write_refuses(self):
        actual=report.common._pairs
        def changed(worlds):
            result=actual(worlds)
            # Fake just the final byte read; the tracked helper stays untouched.
            old=Path.read_bytes;target=report.ROOT/'scripts/scale_summary.py'
            self.enterContext(patch.object(Path,'read_bytes',lambda p: old(p)+b'\n' if p==target else old(p)))
            return result
        with patch.object(report.common,'_pairs',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'raw_inputs_changed'):self.generate()
        self.assertFalse(self.out.exists())

    def test_actor_cache_same_json_reformat_between_audits_refuses(self):
        original=report.common._pairs
        def change(worlds):
            p=next((self.raw/self.campaign['slots'][0]['relative_path']/'actors/mirofish_interviews').glob('*.json'))
            p.write_text(json.dumps(json.loads(p.read_bytes()),separators=(',',':')))
            return original(worlds)
        with patch.object(report.common,'_pairs',side_effect=change):
            with self.assertRaisesRegex(ValueError,'raw_receipt_inventory_changed'):self.generate()
        self.assertFalse(self.out.exists())

    def test_added_and_removed_actor_cache_entries_refuse(self):
        for remove in (False,True):
            with self.subTest(remove=remove):
                original=report.common._pairs
                cache=self.raw/self.campaign['slots'][0]['relative_path']/'actors/mirofish_interviews'
                def change(worlds):
                    if remove:next(cache.glob('*.json')).unlink()
                    else:write(cache/'extra.json',{'private':PRIVATE})
                    return original(worlds)
                with patch.object(report.common,'_pairs',side_effect=change):
                    with self.assertRaisesRegex(ValueError,'raw_receipt_inventory_changed'):self.generate()
                self.assertFalse(self.out.exists())

    def test_actor_cache_symlink_and_non_json_extra_refuse(self):
        cache=self.raw/self.campaign['slots'][0]['relative_path']/'actors/mirofish_interviews'
        extra=cache/'extra.json';extra.symlink_to(self.prereg)
        with self.assertRaisesRegex(ValueError,'receipt_inventory_symlink'):self.generate()
        extra.unlink();(cache/'extra.txt').write_text(PRIVATE)
        with self.assertRaisesRegex(ValueError,'unexpected_actor_cache_entry'):self.generate()

    def test_gate_trace_keeps_tentative_acceptance_final_rejection_and_unknown_stop(self):
        slot=self.campaign['slots'][1];path=self.raw/slot['relative_path']/'checkpoint.json';cp=json.loads(path.read_bytes())
        update=cp['runner']['updates'][2]
        update['gate_evidence'].update(baseline_score=.75,candidate_score=.75,gate_action='reject',gate_trials=[
            {'target':'skill','baseline_score':.75,'candidate_score':.8,'accepted':True,'blocked_by_regression':False,
             'task_deltas':[{'task_id':PRIVATE,'status':'improved'},{'task_id':PRIVATE,'status':'unchanged'}]},
            {'target':'final','baseline_score':.75,'candidate_score':.75,'accepted':False,'blocked_by_regression':True,
             'task_deltas':[{'task_id':PRIVATE,'status':'improved'},{'task_id':PRIVATE,'status':'regressed'}]}])
        write(path,cp);self.rebind(slot);result=self.generate()
        rows=result['worlds'][1]['optimizer']['updates'];trace=rows[2]['gate_trace']
        self.assertFalse(rows[2]['adopted']);self.assertEqual(trace['gate_action'],'reject')
        self.assertTrue(trace['gate_trials'][0]['accepted']);self.assertFalse(trace['gate_trials'][1]['accepted'])
        self.assertEqual(trace['gate_trials'][1]['task_status_counts'],{'improved':1,'unchanged':0,'regressed':1,'unknown':0})
        self.assertIsNone(rows[1]['gate_trace']['baseline_score']);self.assertIsNone(rows[1]['gate_trace']['gate_trials'])
        self.assertEqual(rows[1]['gate_trace']['gate_action'],'reject_incomplete')
        self.assertNotIn(PRIVATE,json.dumps(trace))

    def test_gate_trace_final_score_can_be_incumbent_after_rejected_trial(self):
        value=report._gate_trace({'configuration':{'gate_metric':'mixed','gate_mixed_weight':.5,'gate_no_regression':True},
            'gate_evidence':{'baseline_score':.6,'candidate_score':.7,'gate_action':'reject','gate_trials':[
                {'target':'skill','baseline_score':.6,'candidate_score':.55,'accepted':False},
                {'target':'final','baseline_score':.6,'candidate_score':.7,'accepted':False}]}})
        self.assertEqual(value['candidate_score'],.7);self.assertEqual(value['gate_trials'][0]['candidate_score'],.55)
        self.assertEqual((value['score_metric'],value['mixed_weight'],value['no_regression']),('mixed',.5,True))
        self.assertIn('incumbent',value['interpretation'])
        unknown=report._gate_trace({'gate_evidence':{}})
        self.assertTrue(all(unknown[k] is None for k in ('candidate_score','score_metric','mixed_weight','no_regression')))

    def test_cli_suppresses_private_exception_message(self):
        with patch.object(report,'report_scale_v3',side_effect=ValueError(PRIVATE)),contextlib.redirect_stdout(io.StringIO()) as stdout:
            code=report.main([str(self.raw),'--out',str(self.out),'--preregistration',str(self.prereg),'--campaign-sha256',self.sha])
        self.assertEqual(code,1);self.assertNotIn(PRIVATE,stdout.getvalue())


if __name__=='__main__':unittest.main()
