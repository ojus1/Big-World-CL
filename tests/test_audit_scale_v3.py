"""Fabricated offline v3 audit evidence; never native qualification or results."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from lifespan.mirofish import save
from scripts import audit_scale_v3 as audit
from tests.test_scale_v2_audit import native_fixture


def campaign_fixture():
    slots = [{'seed': seed, 'algorithm': arm, 'run_id': f'seed-{seed}-{arm}',
        'relative_path': f'runs/seed-{seed}-{arm}', 'config': {}} for seed, arm in audit.contract.schedule()]
    return {'slots': slots, 'launch_policy': {'workers': 2, 'per_world_wall_seconds': 86400},
        'budgets': {'employee_target_and_optimizer_physical_calls': 44640,
            'employee_target_and_optimizer_charged_tokens': 792000000,
            'logical_actor_interviews': 3972, 'contracted_interview_physical_requests': 3972}}


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.campaign = campaign_fixture()
        save(self.root / 'campaign.json', self.campaign)
        self.reviewed = audit.sha(self.root / 'campaign.json')
        self.registration = self.enterContext(patch.object(audit, 'registration', return_value=self.campaign))
        for slot in self.campaign['slots']:
            (self.root / slot['relative_path']).mkdir(parents=True)

    def inspect(self, **kw):
        return audit.audit_campaign_v3(self.root, campaign_sha256=self.reviewed, **kw)

    def complete_record(self, root, campaign, slot):
        return ({'status': 'completed', 'ok': True, 'completed': True,
            'sessions': 1, 'updates': 0, 'accepted_updates': 0,
            'learner_physical_calls': 1, 'learner_measured_tokens': 5,
            'private': 'PRIVATE_CANARY'}, {'seed': slot['seed'], 'algorithm': slot['algorithm']})

    def complete(self):
        for slot in self.campaign['slots']:
            save(self.root / slot['relative_path'] / 'work/fixture/session.json', native_fixture())
        save(self.root / 'EXECUTION.json', {'fixture_only': True})
        self.raw = self.enterContext(patch.object(audit, 'run_check', side_effect=self.complete_record))
        self.enterContext(patch.object(audit, 'actor_accounting', return_value={
            'logical_requests': 1, 'measured_physical_requests': 1, 'measured_tokens': 3,
            'unknown_requests': 0, 'reserved_output_tokens': 0, 'accounting_complete': True}))
        self.inner = self.enterContext(patch.object(audit, 'lifecycle_audit', return_value={'ok': True}))
        self.outer = self.enterContext(patch.object(audit, 'outer_scope_audit', return_value={
            'ok': True, 'scope_passed': True, 'scope_complete': True, 'inner_completed': True}))
        self.comparison = self.enterContext(patch.object(audit, 'compare_reports_v2', return_value={
            'rejected_pairs': [], 'eligible_pairs': [{'seed': seed} for seed in audit.contract.SEEDS]}))

    def test_six_worlds_three_pairs_required_without_any_adoption_requirement(self):
        self.complete(); value = self.inspect(strict=True)
        self.assertTrue(value['ok'], value); self.assertTrue(value['primary_endpoint_available'])
        self.assertEqual((value['completed_runs'], value['complete_pairs']), (6, 3))
        self.assertEqual(value['accounting']['employee_and_optimizer']['known_tokens'], 30)
        self.assertEqual(value['accounting']['contracted_interviews']['measured_tokens'], 18)
        self.assertIsNone(value['accounting']['unmetered_environment']['tokens'])
        self.assertFalse(value['accounting']['all_in_accounting_complete'])
        self.assertNotIn('PRIVATE_CANARY', json.dumps(value))

    def test_one_invalid_world_keeps_every_slot_and_known_costs_without_substitution(self):
        self.complete()
        def raw(root, campaign, slot):
            if slot == campaign['slots'][0]: raise ValueError('fixture_world_invalid')
            return self.complete_record(root, campaign, slot)
        self.raw.side_effect = raw; value = self.inspect(strict=True)
        self.assertFalse(value['ok']); self.assertEqual(len(value['runs']), 6)
        self.assertEqual(value['complete_pairs'], 2); self.comparison.assert_not_called()
        self.assertEqual(value['accounting']['employee_and_optimizer']['known_tokens'], 30)
        self.assertIsNone(value['comparison'])

    def test_explicit_not_ok_world_cannot_become_completed(self):
        self.complete()
        def raw(root, campaign, slot):
            a, b = self.complete_record(root, campaign, slot); a['ok'] = False; return a, b
        self.raw.side_effect = raw; value = self.inspect(strict=True)
        self.assertFalse(value['ok']); self.assertEqual(value['completed_runs'], 0)
        self.comparison.assert_not_called()

    def test_outer_scope_failure_does_not_erase_known_physical_receipts(self):
        self.complete(); self.outer.side_effect = ValueError('outer_native_wait_failed')
        value = self.inspect(strict=True)
        self.assertFalse(value['primary_endpoint_available']); self.comparison.assert_not_called()
        self.assertEqual(value['accounting']['employee_and_optimizer']['known_physical_calls'], 6)
        self.assertFalse(value['ok'])

    def test_complete_worlds_still_wait_for_outer_proof_without_invalidating_snapshot(self):
        self.complete(); self.outer.return_value={'ok':False,'scope_passed':False,'status':'incomplete'}
        value=self.inspect()
        self.assertTrue(value['ok']);self.assertEqual(value['status'],'incomplete')
        self.assertFalse(value['primary_endpoint_available']);self.comparison.assert_not_called()
        self.assertEqual(value['accounting']['employee_and_optimizer']['known_tokens'],30)
        self.assertFalse(self.inspect(strict=True)['ok'])

    def test_unknown_startup_reservation_retained_without_success_or_zero_fill(self):
        self.complete(); run = self.root / self.campaign['slots'][0]['relative_path']
        save(run / 'INFLIGHT.json', {'kind': 'work', 'key': 'unknown'})
        value = self.inspect(strict=True)
        costs = value['accounting']['employee_and_optimizer']
        self.assertEqual(costs['known_tokens'], 30)
        self.assertEqual(costs['charged_or_reserved_tokens'], 250030)
        self.assertEqual(costs['charged_or_reserved_model_calls'], 22)
        self.assertEqual(costs['unresolved_records'], 1)
        self.assertFalse(value['primary_endpoint_available'])

    def test_prepared_has_all_slots_and_no_primary(self):
        value = self.inspect(strict=True)
        self.assertFalse(value['ok']); self.assertEqual(value['status'], 'incomplete')
        self.assertEqual(len(value['runs']), 6); self.assertIsNone(value['comparison'])

    def test_outer_intent_before_inner_execution_still_audited(self):
        (self.root / 'scope').mkdir()
        with patch.object(audit, 'outer_scope_audit', side_effect=ValueError('outer_setup_failed')) as outer:
            value = self.inspect(strict=True)
        outer.assert_called_once(); self.assertFalse(value['ok'])
        self.assertEqual(len(value['runs']), 6); self.assertFalse(value['primary_endpoint_available'])

    def test_missing_or_tampered_registration_retains_planned_slots(self):
        self.registration.side_effect = ValueError('v3_reviewed_campaign_hash_mismatch')
        value = self.inspect(strict=True)
        self.assertFalse(value['ok']); self.assertEqual(len(value['runs']), 6)
        self.assertFalse(value['primary_endpoint_available'])

    def test_private_failure_text_not_exported(self):
        self.complete(); self.outer.side_effect = ValueError('PRIVATE_CANARY /private/path')
        value = self.inspect(strict=True)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(value))


class OuterScopeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        save(self.root / 'campaign.json', campaign_fixture())
        self.identity = {'pid': 100, 'start_ticks': 10, 'uid': 1000, 'boot_id': 'PRIVATE_CANARY'}
        save(self.root / 'EXECUTION.json', {'supervisor_identity': self.identity})
        self.result = {'ok': True, 'errors': [], 'campaign_sha256': audit.sha(self.root / 'campaign.json'),
            'scope_passed': True, 'scope_complete': True, 'inner_completed': True,
            'native_wait_exit_code': 0, 'inner_result_exit_code': 0,
            'inner_supervisor_identity': self.identity, 'raw_evidence_sha256': {'scope/fixture': 'a' * 64},
            'private': 'PRIVATE_CANARY'}
        self.hook = SimpleNamespace(audit_scope=lambda *a, **k: deepcopy(self.result))
        self.enterContext(patch.dict('sys.modules', {'scripts.run_scale_v3': self.hook}))

    def inspect(self, completed=True):
        return audit.outer_scope_audit(self.root, campaign_fixture(), completed)

    def test_binds_exact_campaign_supervisor_wait_and_drops_private_fields(self):
        result = self.inspect(); self.assertTrue(result['inner_supervisor_identity_bound'])
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))
        self.assertEqual(result['raw_evidence_hashes'], ['a' * 64])

    def test_absent_outer_auditor_is_not_a_placeholder_pass(self):
        self.hook.__dict__.pop('audit_scope')
        with self.assertRaisesRegex(ValueError, 'auditor_pending'): self.inspect()

    def test_scope_success_cannot_replace_native_return_and_wait(self):
        for field, value in [('native_wait_exit_code', None), ('native_wait_exit_code', 1),
            ('inner_result_exit_code', 1), ('native_wait_exit_code', True), ('inner_result_exit_code', False)]:
            original = deepcopy(self.result); self.result[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): self.inspect()
            self.result = original

    def test_wrong_campaign_or_foreign_inner_identity_rejected(self):
        self.result['campaign_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'campaign_binding'): self.inspect()
        self.result['campaign_sha256'] = audit.sha(self.root / 'campaign.json')
        for field, value in [('pid', 101), ('start_ticks', 11), ('uid', 1), ('boot_id', 'different')]:
            self.result['inner_supervisor_identity'] = {**self.identity, field: value}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'supervisor_binding'): self.inspect()

    def test_complete_requires_every_scope_flag_and_nonempty_raw_hashes(self):
        for field in ('scope_passed', 'scope_complete', 'inner_completed'):
            self.result[field] = False
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'unconfirmed'): self.inspect()
            self.result[field] = True
        self.result['raw_evidence_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'evidence_hashes'): self.inspect()

    def test_partial_does_not_forward_arbitrary_native_exit_text(self):
        self.result['native_wait_exit_code'] = 'PRIVATE_CANARY'
        with self.assertRaisesRegex(ValueError, 'exit_code_shape'): self.inspect(False)

    def test_pending_receipts_remain_incomplete_even_when_inner_worlds_are_complete(self):
        self.result={'ok':False,'status':'incomplete','errors':[],
            'campaign_sha256':audit.sha(self.root/'campaign.json'),
            'scope_passed':False,'scope_complete':False,'inner_completed':False}
        value=self.inspect(True)
        self.assertFalse(value['ok']);self.assertFalse(value['scope_passed'])
        self.assertFalse(value['inner_supervisor_identity_bound'])


class PairBarrierTests(unittest.TestCase):
    def setUp(self):
        self.campaign = campaign_fixture(); self.worlds=[]; self.results=[]
        for index, slot in enumerate(self.campaign['slots']):
            self.worlds.append({'run_id': slot['run_id'], 'started_monotonic': 10 + (index // 2) * 30,
                'ended_monotonic': 30 + (index // 2) * 30, 'root_exitcode': 0, 'cleanup_confirmed': True})
            self.results.append({'run_id': slot['run_id'], 'exit_code': 0, 'termination_reason': 'exited'})

    def inspect(self): return audit.pair_barriers(self.campaign, self.worlds, self.results)

    def test_exact_three_pairs_including_cleanup_barriers(self):
        self.assertEqual(self.inspect()['observed_following_pair_barriers'], 2)

    def test_next_seed_cannot_start_during_prior_cleanup(self):
        self.worlds[2]['started_monotonic'] = 29
        with self.assertRaisesRegex(ValueError, 'cleanup_barrier'): self.inspect()

    def test_skipped_prior_arm_cannot_be_replaced_by_later_pair(self):
        self.worlds.pop(0)
        with self.assertRaisesRegex(ValueError, 'prior_pair_terminal'): self.inspect()

    def test_prior_world_failure_or_uncertain_cleanup_halts_next_pair(self):
        for key, value in [('root_exitcode', 1), ('root_exitcode', True),
                ('cleanup_confirmed', False), ('ended_monotonic', None)]:
            original=deepcopy(self.worlds[0]); self.worlds[0][key]=value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'prior_failure'): self.inspect()
            self.worlds[0]=original
        self.results[0]['termination_reason']='observation_failed'
        with self.assertRaisesRegex(ValueError, 'prior_failure'): self.inspect()

    def test_first_failed_pair_only_remains_descriptive_without_later_dispatch(self):
        self.worlds=self.worlds[:2];self.results=self.results[:2]
        self.worlds[0]['root_exitcode']=1
        self.assertEqual(self.inspect()['observed_following_pair_barriers'],0)


class LifecycleTests(unittest.TestCase):
    """Only the existing pure native receipt validators are stubbed."""
    def setUp(self):
        from scripts import scale_v2_process as process
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.campaign=campaign_fixture()
        save(self.root/'campaign.json',self.campaign);self.reviewed=audit.sha(self.root/'campaign.json')
        parent={'pid':100,'start_ticks':10,'uid':1000,'boot_id':'fixture'}
        execution={'campaign_sha256':self.reviewed,'installation':{'fixture':'PRIVATE_CANARY'},
            'supervisor_identity':parent,'started_monotonic':0,'execution_deadline':102}
        self.enterContext(patch.object(audit,'execution_check',return_value=execution))
        save(self.root/'SERVICE_START.json',{'binding':execution['installation'],'root_identity':{
            'pid':110,'ppid':100,'uid':1000,'boot_id':'fixture','start_ticks':11}})
        save(self.root/'SERVICE_CLEANUP.json',{'fixture':True})
        self.service={'ok':True,'hashes':{},'started_monotonic':1,'ended_monotonic':101,
            'cleanup_started_monotonic':100,'cleanup_limit_seconds':30,'root_exitcode':0,
            'cleanup_confirmed':True,'ready_monotonic':2}
        self.worlds={};terminal=[]
        for index,slot in enumerate(self.campaign['slots']):
            path=self.root/slot['relative_path']/'lifecycle'
            save(path/'WORLD_START.json',{'root_identity':{'pid':120+index,'ppid':100,
                'uid':1000,'boot_id':'fixture','start_ticks':20+index}})
            begin=10+(index//2)*30+(index%2)
            hashes={'WORLD_START.json':str(index)*64,'WORLD_CLEANUP.json':str(index+1)*64}
            self.worlds[slot['run_id']]={'ok':True,'hashes':hashes,'started_monotonic':begin,
                'ended_monotonic':begin+20,'cleanup_started_monotonic':begin+19,
                'cleanup_limit_seconds':120,'root_exitcode':0,'cleanup_confirmed':True,
                'simulation_id':f'fixture-simulation-{index}'}
            terminal.append({'run_id':slot['run_id'],'exit_code':0,'elapsed_seconds':20,
                'termination_reason':'exited','lifecycle':{'start_sha256':hashes['WORLD_START.json'],
                'cleanup_sha256':hashes['WORLD_CLEANUP.json']}})
        save(self.root/'execution_results.json',{'schema_version':3,'campaign_sha256':self.reviewed,'runs':terminal})
        self.enterContext(patch.object(process,'validate_service_receipts',side_effect=lambda *a,**k:deepcopy(self.service)))
        self.enterContext(patch.object(process,'validate_world_receipts',side_effect=lambda d,r,*a,**k:deepcopy(self.worlds[r.name])))

    def inspect(self,completed=True):return audit.lifecycle_audit(self.root,self.campaign,completed)

    def test_existing_direct_process_proofs_plus_fixed_pair_barriers(self):
        result=self.inspect();self.assertTrue(result['ok']);self.assertEqual(result['peak_parallel_worlds'],2)
        self.assertEqual(result['pair_barriers']['observed_following_pair_barriers'],2)
        self.assertNotIn('PRIVATE_CANARY',json.dumps(result))

    def test_service_cleanup_is_inside_inner_deadline_even_for_partial_campaign(self):
        self.service['ended_monotonic']=103
        with self.assertRaisesRegex(ValueError,'inner_execution_deadline'):self.inspect(False)

    def test_service_cannot_precede_registered_inner_start(self):
        self.service['started_monotonic']=-1
        with self.assertRaisesRegex(ValueError,'precedes_inner_execution'):self.inspect()

    def test_partial_world_cleanup_cannot_overrun_while_service_receipt_is_missing(self):
        self.service['ended_monotonic']=None
        (self.root/'SERVICE_CLEANUP.json').unlink()
        name=self.campaign['slots'][0]['run_id'];self.worlds[name]['ended_monotonic']=103
        with self.assertRaisesRegex(ValueError,'world_cleanup_after_inner_deadline'):self.inspect(False)

    def test_partial_future_or_nonfinite_world_start_rejected(self):
        name=self.campaign['slots'][0]['run_id']
        for value in (103,float('nan'),True):
            self.worlds[name]['started_monotonic']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'outside_inner_execution_clock'):
                self.inspect(False)

    def test_world_cleanup_cannot_overlap_next_pair(self):
        name=self.campaign['slots'][2]['run_id'];self.worlds[name]['started_monotonic']=30
        self.worlds[name]['ended_monotonic']=50;self.worlds[name]['cleanup_started_monotonic']=49
        with self.assertRaisesRegex(ValueError,'concurrency_limit|pair_cleanup_barrier'):self.inspect()

    def test_foreign_service_parent_or_reused_native_simulation_rejected(self):
        path=self.root/'SERVICE_START.json';value=audit.read(path);value['root_identity']['ppid']=999;save(path,value)
        with self.assertRaisesRegex(ValueError,'service_supervisor_process_binding'):self.inspect()
        value['root_identity']['ppid']=100;save(path,value)
        for world in self.worlds.values():world['simulation_id']='same-fixture'
        with self.assertRaisesRegex(ValueError,'shared_native_simulation'):self.inspect()


class ExecutionBindingTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.campaign=campaign_fixture()
        digest=hashlib.sha256(b'fixture').hexdigest()
        self.campaign.update(source_sha256={'fixture.py':digest},
            registration_tools_sha256={'scripts/fixture.py':digest},dependencies={'fixture':True})
        save(self.root/'campaign.json',self.campaign)
        self.prerequisites={'schema_version':1,'verified':True,'checks':[{'fixture':True}]}
        save(self.root/'PREREQUISITES.json',self.prerequisites)
        self.deadline=1+audit.contract.SCOPE_LIMITS['execution_seconds']
        save(self.root/'scope/GATE.json',{'execution_started_monotonic':1,'execution_deadline':self.deadline})
        self.execution={'schema_version':3,'kind':'scale-v3-native-execution',
            'campaign_sha256':audit.sha(self.root/'campaign.json'),'workers':2,'repository_commit':'a'*40,
            'source_commit_verified':True,'supervisor_pid':100,
            'supervisor_identity':{'pid':100,'start_ticks':10,'uid':1000,'boot_id':'fixture'},
            'prerequisites_sha256':audit.sha(self.root/'PREREQUISITES.json'),'prerequisite_paths':{},
            'scope_gate_sha256':audit.sha(self.root/'scope/GATE.json'),
            'started_monotonic':1,'execution_deadline':self.deadline,
            **{k:self.campaign[k] for k in ('source_sha256','registration_tools_sha256','dependencies')}}
        save(self.root/'EXECUTION.json',self.execution)
        self.enterContext(patch.object(audit.subprocess,'check_output',return_value=b'fixture'))
        self.hook=SimpleNamespace(verify_prerequisites=lambda *a,**k:deepcopy(self.prerequisites))
        self.enterContext(patch.dict('sys.modules',{'scripts.run_scale_v3':self.hook}))

    def inspect(self):return audit.execution_check(self.root,self.campaign)

    def test_exact_committed_tools_prerequisite_and_scope_gate_required(self):
        self.assertEqual(self.inspect(),self.execution)
        save(self.root/'scope/GATE.json',{'fixture':'changed'})
        with self.assertRaisesRegex(ValueError,'outer_scope_gate_hash'):self.inspect()

    def test_pending_v3_prerequisite_hook_does_not_reuse_old_validator(self):
        self.hook.__dict__.pop('verify_prerequisites')
        with self.assertRaisesRegex(ValueError,'prerequisite_verifier_pending'):self.inspect()

    def test_source_dependency_or_commit_claim_tamper_rejected(self):
        for key,value in [('source_sha256',{}),('registration_tools_sha256',{}),('dependencies',{}),
                ('source_commit_verified',False),('supervisor_pid',True)]:
            save(self.root/'EXECUTION.json',{**self.execution,key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):self.inspect()

    def test_prerequisite_reaudit_must_equal_saved_bytes_object(self):
        self.prerequisites={'schema_version':1,'verified':True,'checks':[]}
        with self.assertRaisesRegex(ValueError,'prerequisite_audit'):self.inspect()


class RegistrationIntegrationTests(unittest.TestCase):
    """Real v3 registration over fabricated cohorts; no installed dependencies."""
    from tests.test_scale_v3_contract import RegistrationTests as _fixture
    setUp=_fixture.setUp

    def inspect(self,**kwargs):
        with patch.object(audit,'source_hashes',return_value=self.sources), \
             patch.object(audit,'dependency_provenance',return_value=self.deps), \
             patch.object(audit,'tooling',return_value=self.tools):
            return audit.audit_campaign_v3(self.out,campaign_sha256=self.reviewed_hash,**kwargs)

    def test_prepared_real_registration_preserves_all_fixed_scientific_slots(self):
        value=self.inspect();self.assertTrue(value['ok'],value)
        self.assertEqual(value['status'],'incomplete');self.assertEqual(len(value['runs']),6)
        self.assertTrue(all(s['config']['max_work_sessions']==240 for s in self.manifest['slots']))
        self.assertFalse(value['primary_endpoint_available'])

    def test_coherent_scope_policy_rewrite_still_rejected_by_external_raw_hash(self):
        changed=deepcopy(self.manifest);changed['launch_policy']['scope_limits']['tasks_max']=1024
        save(self.out/'campaign.json',changed)
        value=self.inspect();self.assertFalse(value['ok']);self.assertEqual(len(value['runs']),6)

    def test_current_tool_or_dependency_change_invalidates_registration(self):
        self.tools={**self.tools,'scripts/audit_scale_v3.py':'f'*64}
        value=self.inspect();self.assertFalse(value['ok']);self.assertFalse(value['primary_endpoint_available'])


if __name__ == '__main__': unittest.main()
