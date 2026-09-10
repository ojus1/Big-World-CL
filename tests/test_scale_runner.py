"""Offline campaign/import and analysis fixtures; no model or native evidence."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.mirofish import save
from scripts import run_scale
from scripts.scale_summary import build_scale_summary


CREDS = {'model': 'offline-fixture-model', 'base_url': 'https://offline.example.invalid', 'api_key': 'PRIVATE_UNUSED_KEY'}


def importer(cache, out, *, count, seed):
    cohort = {'fixture': 'offline-not-persona-import-evidence', 'selection_seed': seed,
              'personas': [{'persona_id': f'fixture-{seed}-{index}', 'work_attributes': {'private': 'DO_NOT_EXPORT_PERSONA'}} for index in range(count)]}
    save(out, cohort)
    return cohort


class ScalePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'campaign'
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(run_scale, 'source_hashes', return_value={'offline.py': 'a' * 64}))
        stack.enter_context(patch.object(run_scale, 'dependency_provenance', return_value={'fixture': 'offline'}))
        stack.enter_context(patch.object(run_scale, 'credentials', side_effect=AssertionError('No real credentials in offline fixtures')))
        stack.enter_context(patch.object(run_scale.subprocess, 'Popen', side_effect=AssertionError('No model processes in offline fixtures')))
        stack.enter_context(patch.object(run_scale, 'utc', return_value='2030-01-01T00:00:00+00:00'))

    def prepare(self, cohort_importer=importer):
        return run_scale.prepare(self.out, creds=CREDS, cohort_importer=cohort_importer)

    def manifest(self):
        return run_scale.read(self.out / 'campaign.json')

    def test_preparation_freezes_six_slots_paired_cohorts_and_budgets(self):
        manifest = self.prepare()
        self.assertEqual(run_scale.validate_prepared(self.out, creds=CREDS), manifest)
        self.assertEqual([(s['seed'], s['algorithm']) for s in manifest['slots']],
                         [(211, 'no_learning'), (211, 'skillopt'), (307, 'skillopt'), (307, 'no_learning'), (401, 'no_learning'), (401, 'skillopt')])
        self.assertEqual(manifest['population'], {'firms': 4, 'employees': 12, 'consumers': 8, 'agencies': 1})
        self.assertEqual(len(manifest['slots']), 6)
        self.assertEqual(manifest['budgets']['max_online_sessions'], 1440)
        self.assertEqual(manifest['budgets']['max_learning_epochs'], 108)
        self.assertEqual(manifest['budgets']['max_learning_target_replays'], 1296)
        seen = set()
        for seed in run_scale.SEEDS:
            cohort = run_scale.read(self.out / 'cohorts' / f'{seed}.json')
            ids = {row['persona_id'] for row in cohort['personas']}
            self.assertEqual(len(ids), 25)
            self.assertFalse(seen.intersection(ids))
            seen.update(ids)
            arms = [slot for slot in manifest['slots'] if slot['seed'] == seed]
            self.assertEqual(arms[0]['persona_cohort_sha256'], arms[1]['persona_cohort_sha256'])
            self.assertEqual((self.out / arms[0]['relative_path'] / 'persona_cohort.json').read_bytes(),
                             (self.out / arms[1]['relative_path'] / 'persona_cohort.json').read_bytes())
        for slot in manifest['slots']:
            config = slot['config']
            self.assertEqual((config['days'], config['max_work_sessions']), (20, 240))
            self.assertEqual((config['train_cases'], config['val_cases'], config['skillopt_rollouts_k']), (2, 2, 2))
            self.assertEqual(config['update_days'], [3, 7, 11, 17])
            self.assertEqual(config['max_learning_calls_per_epoch'], 200)
            self.assertEqual(config['max_learning_tokens_per_epoch'], 4000000)
            self.assertEqual(config['max_learning_seconds_per_epoch'], 1800)
            self.assertEqual(config['max_actor_interviews'], 662)
        self.assertNotIn(CREDS['api_key'], (self.out / 'campaign.json').read_text())

    def test_existing_directory_duplicate_personas_and_cross_seed_overlap_fail(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.prepare()
        for mode in ('duplicate', 'overlap', 'short'):
            out = Path(self.temp.name) / mode
            def invalid(cache, path, *, count, seed):
                data = importer(cache, path, count=count - 1 if mode == 'short' else count, seed=0 if mode == 'overlap' else seed)
                if mode == 'duplicate':
                    data['personas'][1]['persona_id'] = data['personas'][0]['persona_id']
                    save(path, data)
                return data
            with self.assertRaises(ValueError):
                run_scale.prepare(out, creds=CREDS, cohort_importer=invalid)

    def test_top_level_contract_and_dispatch_tampering_fail(self):
        self.prepare()
        original = self.manifest()
        mutations = [lambda m: m.update(days=21), lambda m: m['population'].update(employees=13),
                     lambda m: m['budgets'].update(max_online_sessions=2000), lambda m: m['design'].update(primary='tampered'),
                     lambda m: m['slots'].reverse(), lambda m: m['slots'].pop(),
                     lambda m: m['slots'][0].update(relative_path='../outside'),
                     lambda m: m['slots'][0].update(relative_path='other-inside-path'),
                     lambda m: m['source_sha256'].update(other='changed')]
        for mutation in mutations:
            altered = deepcopy(original)
            mutation(altered)
            save(self.out / 'campaign.json', altered)
            with self.assertRaises(ValueError):
                run_scale.validate_prepared(self.out, creds=CREDS)
        save(self.out / 'campaign.json', original)

    def test_config_native_output_and_model_provider_changes_fail(self):
        manifest = self.prepare()
        run = self.out / manifest['slots'][0]['relative_path']
        original = (run / 'config.json').read_bytes()
        config = run_scale.read(run / 'config.json')
        config['max_learning_calls_per_epoch'] += 1
        save(run / 'config.json', config)
        with self.assertRaises(ValueError):
            run_scale.validate_prepared(self.out, creds=CREDS)
        (run / 'config.json').write_bytes(original)
        save(run / 'checkpoint.json', {'fixture': True})
        with self.assertRaises(ValueError):
            run_scale.validate_prepared(self.out, creds=CREDS)
        (run / 'checkpoint.json').unlink()
        with self.assertRaises(ValueError):
            run_scale.validate_prepared(self.out, creds={**CREDS, 'model': 'changed'})
        with self.assertRaises(ValueError):
            run_scale.validate_prepared(self.out, creds={**CREDS, 'base_url': 'https://changed.example.invalid'})

    def test_cohort_edit_and_self_consistent_slot_hash_rewrite_cannot_change_pair(self):
        manifest = self.prepare()
        slot = manifest['slots'][0]
        path = self.out / slot['relative_path'] / 'persona_cohort.json'
        data = run_scale.read(path)
        data['personas'][0]['persona_id'] = 'new-different-persona'
        save(path, data)
        manifest = self.manifest()
        manifest['slots'][0]['persona_cohort_sha256'] = run_scale.sha(path)
        save(self.out / 'campaign.json', manifest)
        with self.assertRaises(ValueError):
            run_scale.validate_prepared(self.out, creds=CREDS)

    def test_cross_seed_cohort_replacement_is_rejected_even_with_all_hashes_changed(self):
        self.prepare()
        source = self.out / 'cohorts/211.json'
        replaced = self.out / 'cohorts/307.json'
        replaced.write_bytes(source.read_bytes())
        manifest = self.manifest()
        for slot in manifest['slots']:
            if slot['seed'] == 307:
                path = self.out / slot['relative_path'] / 'persona_cohort.json'
                path.write_bytes(source.read_bytes())
                slot['persona_cohort_sha256'] = run_scale.sha(path)
        save(self.out / 'campaign.json', manifest)
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            run_scale.validate_prepared(self.out, creds=CREDS)

    def test_status_retains_all_runs_and_exports_only_allowlisted_progress(self):
        manifest = self.prepare()
        self.assertEqual([row['status'] for row in run_scale.status(self.out)['runs']], ['not_started'] * 6)
        run = self.out / manifest['slots'][0]['relative_path']
        save(run / 'checkpoint.json', {'ecosystem': {'day': 7}, 'runner': {
            'phase': 'learn', 'sessions': [{'success': True, 'artifact': 'PRIVATE_ANSWER'}, {'success': False}],
            'updates': [{'accepted': False, 'costs': {'replays': 3}, 'skill': 'PRIVATE_SKILL'}],
            'learning_calls': 27, 'learning_tokens': 10100, 'private': 'PRIVATE_STATE'}})
        save(run / 'INFLIGHT.json', {'kind': 'learning', 'key': 'd007-worker', 'day': 7, 'private': 'PRIVATE_INPUT'})
        save(run / 'learning/d007-worker/progress.json', {'status': 'running',
            'target_progress': {'dispatched_replays': 3, 'returned_replays': 2,
                                'charged_or_reserved_model_calls': 27, 'charged_or_reserved_tokens': 10100},
            'prompt': 'PRIVATE_PROMPT'})
        save(run / 'actors/evaluation_interview_ledger.json', {'requests': [{}, {}, {}], 'private': 'PRIVATE_ACTOR'})
        save(self.out / manifest['slots'][1]['relative_path'] / 'REPORT.json', {'status': 'failed', 'private': 'PRIVATE_REPORT'})
        result = run_scale.status(self.out)
        self.assertEqual(len(result['runs']), 6)
        self.assertEqual(result['runs'][0]['sessions'], 2)
        self.assertEqual(result['runs'][0]['successes'], 1)
        self.assertEqual(result['runs'][0]['logical_actor_requests'], 3)
        self.assertEqual(result['runs'][0]['learning_progress']['returned_replays'], 2)
        self.assertEqual(result['runs'][1]['status'], 'failed')
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_execution_requires_published_hash_before_native_dispatch(self):
        self.prepare()
        with patch.object(run_scale, 'credentials', return_value=CREDS):
            with self.assertRaises(ValueError):
                run_scale.execute(self.out, campaign_sha256='0' * 64)
        self.assertFalse((self.out / 'EXECUTION.json').exists())


def summary_fixture():
    slots = []
    for seed in run_scale.SEEDS:
        for algorithm in run_scale.ALGORITHMS:
            slots.append({'run_id': f'seed-{seed}-{algorithm}', 'seed': seed, 'algorithm': algorithm,
                          'config': run_scale.study_config(seed, algorithm).public()})
    campaign = {'slots': slots}
    selected = slots[1]
    employee = 'firm-0__incident-regulated'
    experiences = [{'id': f'e-{index}', 'employee': employee, 'source_session': f'underlying-{index}',
                    'split': split, 'available_day': day, 'feedback_available_day': feedback,
                    'prompt': 'PRIVATE_PROMPT', 'context': 'PRIVATE_FILES', 'feedback': 'PRIVATE_FEEDBACK'}
                   for index, (split, day, feedback) in enumerate([('train', 1, 1), ('train', 2, 2),
                       ('val', 3, 3), ('val', 4, 5), ('train', 17, 17)])]
    experiences.append({**experiences[0], 'id': 'retry', 'available_day': 8, 'feedback_available_day': 8})
    logs = []
    for firm in range(4):
        for workflow in ('onboarding', 'renewal', 'incident'):
            owner = f'firm-{firm}__{workflow}-regulated'
            for day in (3, 7, 11, 17):
                train, val = (3 if day == 17 else 2, 1 if day == 3 else 2) if owner == employee else (0, 0)
                logs.append({'employee': owner, 'day': day, 'available_unique_train': train,
                             'available_unique_val': val, 'eligible': train >= 2 and val >= 2,
                             'treatment_enabled': True, 'selected_ids': ['PRIVATE_SELECTED_ID']})
    sessions = [{'id': f's-{day}', 'employee': employee, 'day': day, 'regime': regime, 'task_id': f'task-{day}',
                 'skill_version': version, 'success': success, 'semantic_score': 1.0 if success else .5,
                 'infrastructure_valid': True, 'artifact': 'PRIVATE_ANSWER', 'skill': 'PRIVATE_SKILL'}
                for day, regime, version, success in [(1, 'base', 0, True), (7, 'changed', 0, False),
                                                      (8, 'changed', 1, True), (16, 'reversal', 1, True)]]
    updates = [{'employee': employee, 'day': day, 'accepted': accepted, 'parent_version': parent,
                'deployed_version': 1, 'available_from_day': day + 1, 'status': 'completed', 'skill': 'PRIVATE_SKILL',
                'costs': {'tokens': 1000, 'target_model_calls': 20, 'optimizer_model_calls': 1, 'replays': 4,
                          'accounting_complete': True, 'private': 'PRIVATE_OPERATIONS'}}
               for day, accepted, parent in [(7, True, 0), (11, False, 1)]]
    checkpoint = {'ecosystem': {'day': 21}, 'runner': {'phase': 'advance', 'experiences': experiences,
        'sessions': sessions, 'updates': updates, 'learning_eligibility': logs}}
    record = {'run_id': selected['run_id'], 'checkpoint': checkpoint, 'report': {'status': 'completed', 'private': 'PRIVATE_REPORT'}}
    return campaign, record, employee


class ScaleSummaryTests(unittest.TestCase):
    def test_all_planned_employees_missing_runs_and_each_boundary_remain_visible(self):
        campaign, record, employee = summary_fixture()
        result = build_scale_summary(campaign, [record])
        self.assertEqual(result['planned_runs'], 6)
        self.assertEqual(result['hash_encoding'], 'canonical_json')
        self.assertIn('not raw file bytes', result['hash_format'])
        self.assertEqual(result['missing_checkpoints'], 5)
        self.assertEqual(result['planned_employee_world_instances'], 72)
        self.assertEqual(result['planned_learning_boundaries'], 288)
        self.assertEqual(result['observed_learning_boundaries'], 48)
        self.assertEqual(result['observed_ineligible_boundaries'], 45)
        self.assertEqual(result['recorded_updates'], 2)
        self.assertEqual(result['accepted_updates'], 1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['evidence_issues'], [])
        for run in result['runs']:
            self.assertEqual(len(run['employees']), 12)
            self.assertEqual(run['scheduled_boundaries'], [3, 7, 11, 17])
        missing = result['runs'][0]['employees'][0]
        self.assertIsNone(missing['sessions'])
        self.assertIsNone(missing['learning_boundaries'][0]['available_unique_train'])

    def test_unique_release_counts_do_not_count_retries_or_future_feedback(self):
        campaign, record, employee = summary_fixture()
        result = build_scale_summary(campaign, [record])
        row = next(e for e in result['runs'][1]['employees'] if e['employee'] == employee)
        self.assertEqual([(b['available_unique_train'], b['available_unique_val']) for b in row['learning_boundaries']],
                         [(2, 1), (2, 2), (2, 2), (3, 2)])
        self.assertFalse(row['learning_boundaries'][0]['eligible'])
        self.assertTrue(row['learning_boundaries'][-1]['eligible_without_recorded_update'])
        self.assertEqual([(v['version'], v['sessions']) for v in row['versions']], [(0, 2), (1, 2)])
        self.assertEqual(row['versions'][1]['available_from_day'], 8)
        self.assertEqual(row['regimes'][3]['sessions'], 1)

    def test_day17_uses_reversal_feedback_and_adoption_has_day18_and19_exposure(self):
        campaign, record, employee = summary_fixture()
        state = record['checkpoint']['runner']
        for day, split in ((15, 'train'), (16, 'val')):
            state['experiences'].append({'id': f'reversal-observation-{day}', 'employee': employee,
                'source_session': f'reversal-obligation-{day}', 'split': split,
                'available_day': day + 1, 'feedback_available_day': day + 1})
        log = next(row for row in state['learning_eligibility'] if row['employee'] == employee and row['day'] == 17)
        log.update(available_unique_train=4, available_unique_val=3)
        state['updates'].append({'employee': employee, 'day': 17, 'accepted': True, 'parent_version': 1,
            'deployed_version': 2, 'available_from_day': 18, 'status': 'completed', 'costs': {}})
        for day in (18, 19):
            state['sessions'].append({'id': f'post-reversal-{day}', 'employee': employee, 'day': day,
                'regime': 'reversal', 'task_id': f'future-work-{day}', 'skill_version': 2,
                'success': True, 'semantic_score': 1.0, 'infrastructure_valid': True})
        result = build_scale_summary(campaign, [record])
        row = next(e for e in result['runs'][1]['employees'] if e['employee'] == employee)
        self.assertEqual(result['evidence_issues'], [])
        self.assertEqual(row['learning_boundaries'][-1]['day'], 17)
        self.assertEqual(row['learning_boundaries'][-1]['actual_updates'], 1)
        self.assertEqual(row['learning_boundaries'][-1]['accepted_updates'], 1)
        self.assertEqual(row['versions'][-1]['version'], 2)
        self.assertEqual(row['versions'][-1]['available_from_day'], 18)
        self.assertEqual(row['versions'][-1]['sessions'], 2)
        self.assertEqual(row['versions'][-1]['premature_or_unadopted_sessions'], 0)

    def test_absent_explicit_schedule_preserves_periodic_boundary_derivation(self):
        campaign, record, employee = summary_fixture()
        for slot in campaign['slots']:
            slot['config']['update_days'] = None
        for log in record['checkpoint']['runner']['learning_eligibility']:
            if log['day'] == 17:
                log['day'] = 15
                if log['employee'] == employee:
                    log['available_unique_train'] = 2
        result = build_scale_summary(campaign, [record])
        self.assertEqual(result['runs'][1]['scheduled_boundaries'], [3, 7, 11, 15])
        self.assertEqual(result['evidence_issues'], [])

    def test_incomplete_current_boundary_is_unknown_without_log(self):
        campaign, record, employee = summary_fixture()
        record.pop('report')
        state = record['checkpoint']['runner']
        record['checkpoint']['ecosystem']['day'] = 7
        state['phase'] = 'learn'
        state['sessions'] = [row for row in state['sessions'] if row['day'] <= 7]
        state['updates'] = []
        state['learning_eligibility'] = [row for row in state['learning_eligibility'] if row['day'] == 3]
        result = build_scale_summary(campaign, [record])
        row = next(e for e in result['runs'][1]['employees'] if e['employee'] == employee)
        self.assertEqual(row['learning_boundaries'][1]['observation_status'], 'not_reached')
        self.assertIsNone(row['learning_boundaries'][1]['eligible'])
        self.assertEqual(result['evidence_issues'], [])

    def test_missing_historical_log_and_wrong_count_are_explicit_evidence_issues(self):
        campaign, record, employee = summary_fixture()
        logs = record['checkpoint']['runner']['learning_eligibility']
        logs.pop()
        logs[0]['available_unique_train'] = 99
        result = build_scale_summary(campaign, [record])
        self.assertEqual({row['kind'] for row in result['evidence_issues']},
                         {'missing_eligibility_log', 'eligibility_count_or_treatment_mismatch'})

    def test_unadopted_or_early_version_exposure_is_reported(self):
        campaign, record, employee = summary_fixture()
        record['checkpoint']['runner']['sessions'][1]['skill_version'] = 1
        result = build_scale_summary(campaign, [record])
        self.assertIn('unadopted_or_premature_version_exposure', {row['kind'] for row in result['evidence_issues']})

    def test_unknown_duplicate_records_cross_employee_and_split_conflicts_fail(self):
        campaign, record, employee = summary_fixture()
        with self.assertRaises(ValueError):
            build_scale_summary(campaign, [record, record])
        with self.assertRaises(ValueError):
            build_scale_summary(campaign, [{**record, 'run_id': 'unknown'}])
        altered = deepcopy(record)
        altered['checkpoint']['runner']['sessions'][0]['employee'] = 'unknown'
        with self.assertRaises(ValueError):
            build_scale_summary(campaign, [altered])
        altered = deepcopy(record)
        altered['checkpoint']['runner']['experiences'][-1]['split'] = 'val'
        with self.assertRaises(ValueError):
            build_scale_summary(campaign, [altered])

    def test_summaries_exclude_private_text_and_leave_inputs_unchanged(self):
        campaign, record, employee = summary_fixture()
        before = deepcopy((campaign, record))
        result = build_scale_summary(campaign, [record])
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertEqual((campaign, record), before)


if __name__ == '__main__':
    unittest.main()
