"""Synthetic snapshot fixtures only; no live world or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import scale_horizon_observations as horizon


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def work(workflow='onboarding', regime='base', seconds=12.):
    return {'employee': 'firm-0__'+workflow+'-regulated', 'task_id': 'firm-0-order-0000',
        'case_id': 'firm-0-order-0000', 'regime': regime, 'day': 1, 'elapsed_seconds': seconds,
        'infrastructure_valid': True, 'success': False, 'budget_exhausted': False,
        'usage': {'api_calls': 2, 'total_tokens': 90, 'charged_tokens': 90, 'complete': True},
        'private_trace': 'DO_NOT_EXPORT_PROVIDER_BODY'}


def epoch(employee, proposals=0):
    return {'employee': employee, 'day': 7, 'status': 'completed', 'accepted': False,
        'gate_evidence': {'applied_edits': [], 'rejected_edits': [{'target':'skill','op':'add','content': 'DO_NOT_EXPORT_EDIT'}]*proposals,
                         'unmatched_edits': []},
        'costs': {'wall_seconds': 30., 'accounting_complete': True, 'tokens': 90,
                  'target_model_calls': 2, 'optimizer_model_calls': 0,
                  'operations': [{'kind': 'target', 'wall_seconds': 20., 'accounting': 'reported',
                                  'model_calls': 2, 'tokens': 90}]},
        'replay_artifacts': [], 'optimizer_transport_audit': []}


class ScalarTests(unittest.TestCase):
    def test_nonfinite_negative_bool_and_missing_durations_remain_unknown(self):
        for value in (None, float('nan'), float('inf'), -2., True, 'DO_NOT_EXPORT'):
            result = horizon.work_observation(work(seconds=value))
            self.assertIsNone(result['runtime_seconds'])
            self.assertNotIn('DO_NOT_EXPORT', json.dumps(result, allow_nan=False))
        result = horizon.distribution([1., 3., None, True, float('nan')])
        self.assertEqual((result['observations'], result['known'], result['unknown']), (5, 2, 3))
        self.assertEqual(result['mean_seconds'], 2.)
        self.assertIsNone(horizon.distribution([])['sum_seconds'])
        huge=horizon.distribution([1e308,1e308]); self.assertIsNone(huge['sum_seconds'])
        self.assertEqual(huge['mean_seconds'],1e308); json.dumps(huge,allow_nan=False)
        self.assertFalse(horizon.number(10**500))

    def test_missing_costs_do_not_erase_a_returned_duration_or_success(self):
        raw = work(); raw.update(success=True, infrastructure_valid=False)
        raw['usage'] = {'complete': False, 'api_calls': 3, 'total_tokens': None, 'charged_tokens': 150000}
        result = horizon.work_observation(raw)
        self.assertEqual(result['runtime_seconds'], 12.)
        self.assertTrue(result['success']); self.assertFalse(result['infrastructure_valid'])
        self.assertFalse(result['usage_complete']); self.assertIsNone(result['recorded_total_tokens'])
        self.assertEqual(result['recorded_charged_tokens'], 150000)

    def test_proposals_rejections_and_noop_are_separate_from_acceptance(self):
        employee = work()['employee']
        self.assertEqual(horizon.learning_observation(epoch(employee))['proposal_class'], 'no_proposal_observed')
        proposed = horizon.learning_observation(epoch(employee, 3))
        self.assertEqual(proposed['proposal_class'], 'proposal_observed'); self.assertFalse(proposed['accepted'])
        stopped = epoch(employee); stopped.update(status='budget_exhausted', gate_evidence={'accepted': False})
        self.assertEqual(horizon.learning_observation(stopped)['proposal_class'], 'unknown_incomplete')
        broken = epoch(employee); broken['costs']['operations'] = [None]
        self.assertIsNone(horizon.learning_observation(broken)['target_callback_seconds'])
        self.assertIsNone(horizon.learning_observation({}, {})['learner_wall_seconds'])
        stopped['costs']['accounting_complete']=False
        stopped['costs']['tokens']=250000
        summary=horizon.learning_observation(stopped)
        self.assertEqual(summary['recorded_charged_or_reserved_tokens'],250000)
        self.assertIsNone(summary['recorded_total_tokens'])
        self.assertEqual(summary['recorded_reported_tokens_known_prefix'],90)

    def test_arm_workflow_regime_and_phase_are_not_mixed(self):
        rows = [{**horizon.work_observation(work(w, r, secs)), 'algorithm': a}
                for a,w,r,secs in [('no_learning','onboarding','base',1), ('skillopt','onboarding','base',20),
                                    ('no_learning','renewal','base',30), ('no_learning','onboarding','reversal',40)]]
        groups = horizon.buckets(rows, ('algorithm','workflow','regime'), ('runtime_seconds',))
        self.assertEqual(len(groups), 4)
        self.assertTrue(all(g['observations'] == 1 for g in groups))


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.campaign = self.root/'lifespan/artifacts/scale-v1'
        self.out = self.root/'lifespan/artifacts/horizon-fixture'
        self.root_patch = patch.object(horizon, 'ROOT', self.root); self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        self.ignore_patch = patch.object(horizon.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
        self.ignore_patch.start(); self.addCleanup(self.ignore_patch.stop)
        sources = {}
        for i in range(34):
            name = f'scripts/frozen{i:02}.py'; path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# synthetic frozen source\n'); sources[name] = horizon.sha(path.read_bytes())
        slots = []; self.records = {}
        for seed in (211,307,401):
            for arm in ('no_learning','skillopt'):
                rid = f'seed-{seed}-{arm}'; run = self.campaign/'runs'/rid
                slot = {'seed':seed,'algorithm':arm,'run_id':rid,'relative_path':'runs/'+rid}; slots.append(slot)
                record = work(); key = f"d001-{record['employee']}-{record['task_id']}"
                capsule = {'employee':record['employee'], 'task_id':record['task_id'], 'case': {
                    'id':record['case_id'],'workflow':'onboarding','regime':'base','day':1}, 'private':'DO_NOT_EXPORT_CAPSULE'}
                write(run/'work'/key/'session.json', record)
                case_path = run/'private/cases'/(key+'.json'); write(case_path,capsule)
                updates = []
                if arm == 'skillopt':
                    update = epoch(record['employee'], int(seed==401)); directory = run/'learning'/('d007-'+record['employee'])
                    write(directory/'trial-000/session.json', record)
                    update['replay_artifacts'] = [{'attempt_index':0,'session_path':str((directory/'trial-000/session.json').relative_to(run)),
                        'session_sha256':horizon.sha((directory/'trial-000/session.json').read_bytes()),
                        'capsule_path':str(case_path.relative_to(run)), 'capsule_sha256':horizon.sha(case_path.read_bytes()),
                        'phase':'baseline_val','employee':record['employee'],'source_task_id':record['task_id']}]
                    write(directory/'update.json',update); write(directory/'progress.json',{**update,'elapsed_seconds':35.})
                    updates.append(update)
                checkpoint = {'ecosystem':{'day':7}, 'runner':{'elapsed_seconds':100.,
                    'sessions':[{**record,'id':key,'skill_version':0}], 'updates':updates}}
                write(run/'checkpoint.json',checkpoint)
                self.records[rid] = (run,key,checkpoint)
        write(self.campaign/'campaign.json',{'seeds':[211,307,401],'algorithms':['no_learning','skillopt'],
                                            'kind':'multi_seed_reacting_world_comparison','days':20,
                                            'population':{'firms':4,'employees':12,'consumers':8,'agencies':1},
                                            'source_sha256':sources,'slots':slots})
        write(self.campaign/'execution_results.json', {'runs':[{'run_id':r,'exit_code':1,'elapsed_seconds':500.}
            for r in ('seed-307-skillopt','seed-401-no_learning')]})
        for rid in ('seed-307-skillopt','seed-401-no_learning'):
            write(self.records[rid][0]/'REPORT.json', {'status':'failed','elapsed_seconds':490.,'private':'DO_NOT_EXPORT'})

    def capture(self):
        return horizon.capture(self.campaign,self.out)

    def test_all_six_slots_failed_worlds_and_raw_bindings_survive(self):
        before = {str(p):p.read_bytes() for p in self.campaign.rglob('*.json')}
        result = self.capture()
        self.assertTrue(result['ok'],result['errors']); self.assertEqual(len(result['worlds']),6)
        self.assertEqual(sum(r['status']=='failed' for r in result['worlds']),2)
        self.assertEqual(len(result['work_observations']),6); self.assertEqual(len(result['replay_observations']),3)
        self.assertEqual(len(result['learning_observations']),3)
        self.assertFalse(result['changes_original_audit']); self.assertIsNone(result['forecast_seconds'])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result)); self.assertNotIn(str(self.root),json.dumps(result))
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.campaign.rglob('*.json')})
        self.assertTrue(horizon.verify_snapshot(self.out)['ok'])

    def test_verify_uses_only_captured_originals_and_registered_hashes(self):
        original = self.capture(); report_hash=horizon.sha((self.out/'REPORT.json').read_bytes())
        capture_hash=horizon.sha((self.out/'capture.json').read_bytes())
        run,key,_=self.records['seed-211-no_learning']; (run/'work'/key/'session.json').write_text('mutated live original')
        self.assertEqual(horizon.summarize(self.out),original)
        self.assertTrue(horizon.verify_snapshot(self.out,expected_capture_sha256=capture_hash,expected_report_sha256=report_hash)['ok'])
        self.assertFalse(horizon.verify_snapshot(self.out,expected_report_sha256='0'*64)['ok'])

    def test_frozen_source_mismatch_refuses_before_output_creation(self):
        (self.root/'scripts/frozen00.py').write_text('changed source')
        with self.assertRaisesRegex(ValueError,'Frozen execution source mismatch'): self.capture()
        self.assertFalse(self.out.exists())

    def test_copied_raw_source_and_summary_mutation_are_rejected(self):
        self.capture(); run,key,_=self.records['seed-211-no_learning']
        path=self.out/'private/raw'/run.relative_to(self.campaign)/'work'/key/'session.json'
        value=json.loads(path.read_text()); value['elapsed_seconds']=400; write(path,value)
        self.assertFalse(horizon.verify_snapshot(self.out)['ok'])
        self.assertIn('captured_bytes_mutated',{e['code'] for e in horizon.summarize(self.out)['errors']})

    def test_missing_raw_checkpoint_copy_stays_in_duration_denominator(self):
        run,key,_=self.records['seed-211-no_learning']; (run/'work'/key/'session.json').unlink()
        result=self.capture(); self.assertFalse(result['ok'])
        self.assertEqual(len(result['work_observations']),6)
        fallback=[r for r in result['work_observations'] if not r['raw_record_present']]
        self.assertEqual(len(fallback),1); self.assertEqual(fallback[0]['runtime_seconds'],12.)

    def test_uncheckpointed_returned_work_is_retained(self):
        run,key,cp=self.records['seed-211-no_learning']; cp['runner']['sessions']=[]; write(run/'checkpoint.json',cp)
        result=self.capture(); self.assertTrue(result['ok'],result['errors'])
        row=[r for r in result['work_observations'] if r['run_id']=='seed-211-no_learning'][0]
        self.assertFalse(row['checkpointed']); self.assertEqual(len(result['work_observations']),6)

    def test_nonfinite_missing_costs_and_malformed_record_do_not_leak(self):
        run,key,cp=self.records['seed-211-no_learning']; record=work(seconds=float('nan'))
        record['usage']=None; record['infrastructure_valid']=False
        write(run/'work'/key/'session.json',record); cp['runner']['sessions']=[{**record,'id':key,'skill_version':0}]
        write(run/'checkpoint.json',cp); result=self.capture()
        row=[r for r in result['work_observations'] if r['run_id']=='seed-211-no_learning'][0]
        self.assertEqual(row['duration_status'],'malformed'); self.assertFalse(row['usage_complete'])
        self.assertIsNone(row['runtime_seconds']); json.dumps(result,allow_nan=False)

    def test_extra_capture_inventory_is_rejected(self):
        self.capture(); write(self.out/'private/raw/extra.json',{})
        self.assertFalse(horizon.verify_snapshot(self.out)['ok'])

    def test_report_hash_commits_capture_inventory_and_summary_tamper_rejects(self):
        result=self.capture()
        self.assertEqual(result['provenance']['capture_sha256'],horizon.sha((self.out/'capture.json').read_bytes()))
        result['online_work_buckets'][0]['observations']=0; write(self.out/'REPORT.json',result)
        self.assertFalse(horizon.verify_snapshot(self.out)['ok'])

    def test_missing_checkpoint_stays_unknown_and_does_not_remove_slot(self):
        run,_,_=self.records['seed-211-no_learning']; (run/'checkpoint.json').unlink()
        result=self.capture(); self.assertEqual(len(result['worlds']),6)
        row=[w for w in result['worlds'] if w['run_id']=='seed-211-no_learning'][0]
        self.assertFalse(row['checkpoint_present']); self.assertIsNone(row['checkpointed_work_records'])
        self.assertEqual(len(result['work_observations']),6)

    def test_malformed_json_is_retained_as_unknown_observation(self):
        run,key,_=self.records['seed-211-no_learning']; (run/'work'/key/'session.json').write_text('{broken-private')
        result=self.capture(); self.assertFalse(result['ok'])
        self.assertEqual(len(result['work_observations']),6)
        self.assertNotIn('broken-private',json.dumps(result)); json.dumps(result,allow_nan=False)

    def test_pending_returned_replay_without_update_stays_separate(self):
        run,_,cp=self.records['seed-211-skillopt']; cp['runner']['updates']=[]; write(run/'checkpoint.json',cp)
        directory=run/'learning'/('d007-'+work()['employee']); (directory/'update.json').unlink()
        progress=json.loads((directory/'progress.json').read_text()); progress['status']='running'; progress.pop('costs')
        write(directory/'progress.json',progress)
        result=self.capture(); row=[u for u in result['learning_observations'] if u['run_id']=='seed-211-skillopt'][0]
        self.assertFalse(row['returned_update']); self.assertEqual(row['proposal_class'],'unknown_incomplete')
        self.assertIsNone(row['learner_wall_seconds']); self.assertEqual(row['progress_elapsed_seconds'],35.)
        self.assertEqual(len(result['replay_observations']),3)

    def test_mutable_checkpoint_window_change_is_explicit_without_retry(self):
        run,_,_=self.records['seed-211-no_learning']; source=run/'checkpoint.json'
        original=Path.read_bytes; calls=[0]
        def changed(path):
            raw=original(path)
            if path==source:
                calls[0]+=1
                if calls[0]>1: return raw+b'\n'
            return raw
        with patch.object(Path,'read_bytes',changed): result=self.capture()
        self.assertTrue(result['ok'],result['errors']); self.assertEqual(calls[0],2)
        self.assertEqual(result['provenance']['mutable_changed_during_capture'],[str(source.relative_to(self.campaign))])

    def test_tampered_metadata_cannot_export_freeform_private_path(self):
        self.capture(); path=self.out/'capture.json'; meta=json.loads(path.read_text())
        meta['missing'].append('DO_NOT_EXPORT_PROVIDER_BODY'); write(path,meta)
        result=horizon.verify_snapshot(self.out); self.assertFalse(result['ok'])
        self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))

    def test_replay_hash_or_case_regime_mixing_is_rejected_and_not_dropped(self):
        run,key,_=self.records['seed-211-skillopt']; directory=run/'learning'/('d007-'+work()['employee'])
        value=work(regime='reversal'); write(directory/'trial-000/session.json',value)
        result=self.capture(); self.assertFalse(result['ok'])
        replay=[r for r in result['replay_observations'] if r['run_id']=='seed-211-skillopt'][0]
        self.assertIn('replay_session_hash_missing_or_mismatch',replay['binding_issues'])
        self.assertIn('replay_case_scope_mismatch',replay['binding_issues'])
        self.assertEqual(len(result['replay_observations']),3)

    def test_epoch_directory_day_and_employee_bind_reported_epoch(self):
        run,_,cp=self.records['seed-211-skillopt'];directory=run/'learning'/('d007-'+work()['employee'])
        for name in ('update.json','progress.json'):
            value=json.loads((directory/name).read_text());value['day']=11;write(directory/name,value)
        cp['runner']['updates'][0]['day']=11;write(run/'checkpoint.json',cp)
        report=self.capture();self.assertFalse(report['ok'])
        self.assertIn('epoch_directory_identity_mismatch',{row['code'] for row in report['errors']})
        self.assertEqual(len(report['learning_observations']),3)

    def test_replay_employee_cannot_be_relabelled_as_another_epoch_owner(self):
        run,_,cp=self.records['seed-211-skillopt'];old=run/'learning'/('d007-'+work()['employee'])
        employee='firm-1__incident-regulated';directory=old.with_name('d007-'+employee);old.rename(directory)
        for name in ('update.json','progress.json'):
            value=json.loads((directory/name).read_text());value['employee']=employee
            value['replay_artifacts'][0]['session_path']=str((directory/'trial-000/session.json').relative_to(run))
            write(directory/name,value)
        cp['runner']['updates'][0]=json.loads((directory/'update.json').read_text());write(run/'checkpoint.json',cp)
        report=self.capture();self.assertFalse(report['ok'])
        codes={row['code'] for row in report['errors']}
        self.assertIn('declared_replay_identity_mismatch',codes);self.assertIn('replay_identity_mismatch',codes)
        self.assertEqual(len(report['replay_observations']),3)

    def test_duplicate_replay_declarations_are_visible_and_invalid(self):
        run,_,cp=self.records['seed-211-skillopt'];directory=run/'learning'/('d007-'+work()['employee'])
        for name in ('update.json','progress.json'):
            value=json.loads((directory/name).read_text());value['replay_artifacts']*=2;write(directory/name,value)
        cp['runner']['updates'][0]['replay_artifacts']*=2;write(run/'checkpoint.json',cp)
        report=self.capture();self.assertFalse(report['ok'])
        codes={row['code'] for row in report['errors']}
        self.assertIn('duplicate_declared_replay_session',codes);self.assertIn('declared_replay_identity_mismatch',codes)
        row=next(r for r in report['learning_observations'] if r['run_id']=='seed-211-skillopt')
        self.assertEqual(row['declared_replay_records'],2)
        self.assertEqual(len(report['replay_observations']),3)

    def test_noninteger_or_wrong_attempt_identity_is_invalid(self):
        run,_,cp=self.records['seed-211-skillopt'];directory=run/'learning'/('d007-'+work()['employee'])
        for name in ('update.json','progress.json'):
            value=json.loads((directory/name).read_text());value['replay_artifacts'][0]['attempt_index']=True;write(directory/name,value)
        cp['runner']['updates'][0]['replay_artifacts'][0]['attempt_index']=True;write(run/'checkpoint.json',cp)
        report=self.capture();self.assertFalse(report['ok'])
        self.assertIn('declared_replay_identity_mismatch',{row['code'] for row in report['errors']})

    def test_repeated_attempt_index_with_distinct_sessions_is_invalid(self):
        run,_,cp=self.records['seed-211-skillopt'];directory=run/'learning'/('d007-'+work()['employee'])
        extra=directory/'trial-001/session.json';write(extra,work())
        for name in ('update.json','progress.json'):
            value=json.loads((directory/name).read_text());ref=deepcopy(value['replay_artifacts'][0])
            ref.update(session_path=str(extra.relative_to(run)),session_sha256=horizon.sha(extra.read_bytes()))
            value['replay_artifacts'].append(ref);write(directory/name,value)
        cp['runner']['updates'][0]=json.loads((directory/'update.json').read_text());write(run/'checkpoint.json',cp)
        report=self.capture();self.assertFalse(report['ok'])
        codes={row['code'] for row in report['errors']}
        self.assertIn('declared_replay_identity_mismatch',codes);self.assertNotIn('duplicate_declared_replay_session',codes)
        self.assertEqual(len(report['replay_observations']),4)

    def test_pending_unreturned_declared_replay_remains_unknown(self):
        run,_,cp=self.records['seed-211-skillopt'];directory=run/'learning'/('d007-'+work()['employee'])
        cp['runner']['updates']=[];write(run/'checkpoint.json',cp);(directory/'update.json').unlink()
        (directory/'trial-000/session.json').unlink()
        progress=json.loads((directory/'progress.json').read_text());progress['status']='running';progress.pop('costs')
        progress['replay_artifacts'][0].update(session_sha256=None,usage_known=False,
            limits={'max_model_calls':16,'max_tokens':250000},dispatch_status='dispatched')
        write(directory/'progress.json',progress)
        report=self.capture();self.assertTrue(report['ok'],report['errors'])
        row=next(r for r in report['learning_observations'] if r['run_id']=='seed-211-skillopt')
        self.assertFalse(row['returned_update']);self.assertEqual(row['declared_sessions_missing'],1)
        self.assertEqual(row['declared_replay_records'],1);self.assertIsNone(row['learner_wall_seconds'])
        self.assertIsNone(row['recorded_total_tokens']);self.assertFalse(row['usage_complete'])

    def test_malformed_digest_cannot_be_exported_as_provenance(self):
        self.capture();path=self.out/'capture.json';meta=json.loads(path.read_text())
        meta['diagnostic_sha256']='DO_NOT_EXPORT_PROVIDER_TEXT';write(path,meta)
        result=horizon.verify_snapshot(self.out);self.assertFalse(result['ok'])
        self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))

    def test_archived_diagnostic_cannot_replace_current_processor_binding(self):
        self.capture();path=self.out/'capture.json';meta=json.loads(path.read_text())
        archive=self.out/'private/diagnostic.py';archive.write_text('# unsupported historical processor fixture\n')
        meta['diagnostic_sha256']=horizon.sha(archive.read_bytes());write(path,meta)
        rebuilt=horizon.summarize(self.out)
        self.assertFalse(rebuilt['ok']);self.assertIn('current_diagnostic_source_mismatch',{row['code'] for row in rebuilt['errors']})
        self.assertNotIn('diagnostic_source_mismatch',{row['code'] for row in rebuilt['errors']})
        self.assertFalse(horizon.verify_snapshot(self.out)['ok'])

    def test_immutable_change_during_read_is_recorded_without_retry(self):
        run,key,_=self.records['seed-211-no_learning']; source=run/'work'/key/'session.json'
        original=Path.read_bytes; calls=[0]
        def changed(path):
            raw=original(path)
            if path==source:
                calls[0]+=1
                if calls[0]>1: return raw+b'\n'
            return raw
        with patch.object(Path,'read_bytes',changed): result=self.capture()
        self.assertFalse(result['ok']); self.assertEqual(calls[0],2)
        self.assertIn('immutable_changed_during_capture',{e['code'] for e in result['errors']})


if __name__=='__main__': unittest.main()
