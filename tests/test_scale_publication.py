"""Offline publication fixtures with a stub audit: NOT native benchmark evidence.

No agents, provider clients, model calls, or current campaign artifacts are used.
The real strict auditor has its own independent native-evidence tests.
"""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation.metrics import _execution_costs, _learning_costs
from scripts.audit_scale import expected_config
from scripts import report_scale as publication


PRIVATE = 'PRIVATE_PROMPT_CASE_ANSWER_SKILL_PROFILE_SECRET'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def commitment(accepted, fulfilled):
    pending = accepted - fulfilled
    result = {key: 0 for key in publication.COMMITMENT_FIELDS}
    result.update(accepted_before_work_horizon=accepted, actionable_before_work_horizon=accepted,
        fulfilled_before_work_horizon=fulfilled, fulfilled_at_observation=fulfilled,
        unfulfilled_at_work_horizon=pending, available_but_unfinished_at_work_horizon=pending,
        materialized_at_observation=accepted,
        unfulfilled_at_observation=pending, pending_at_observation=pending,
        settled_at_observation=fulfilled, right_censored_unfulfilled=pending,
        fulfillment_rate=fulfilled / accepted if accepted else None, private=PRIVATE)
    return result


def fixture(root):
    """Small artificial records satisfying publication contracts, with stub validation."""
    campaign = {'kind': 'OFFLINE_FIXTURE_NOT_NATIVE_EVIDENCE', 'slots': [],
        'source_sha256': {'lifespan/evaluation/tasks.py': publication.sha((publication.ROOT / 'lifespan/evaluation/tasks.py').read_bytes())}, 'private': PRIVATE}
    for seed in (211, 307, 401):
        for algorithm in ('no_learning', 'skillopt'):
            identifier = f'seed-{seed}-{algorithm}'
            slot = {'run_id': identifier, 'relative_path': 'runs/' + identifier, 'seed': seed,
                'algorithm': algorithm, 'config': expected_config(seed, algorithm)}
            campaign['slots'].append(slot)
            learned = algorithm == 'skillopt'
            employee = 'firm-0__incident-regulated'
            experiences = [{'id': f'experience-{i}', 'source_session': f'obligation-{i}', 'employee': employee,
                'split': 'train' if i < 2 else 'val', 'available_day': i + 1, 'feedback_available_day': i + 1,
                'prompt': PRIVATE, 'context': PRIVATE, 'feedback': PRIVATE} for i in range(4)]
            sessions = [{'id': f'session-{day}', 'employee': employee, 'day': day, 'regime': regime,
                'task_id': f'obligation-{day}', 'skill_version': int(learned and day > 7),
                'success': day != 7 or learned, 'semantic_score': 1. if day != 7 or learned else .5,
                'infrastructure_valid': True, 'skill_loaded': True, 'budget_exhausted': day == 7 and not learned,
                'usage': {'total_tokens': 100, 'prompt_tokens': 80, 'completion_tokens': 20,
                          'api_calls': 2, 'charged_tokens': 120, 'cost_status': 'unknown', 'private': PRIVATE},
                'elapsed_seconds': 2.5, 'diagnostic': {'cost': 1, 'human_minutes': 0, 'private': PRIVATE},
                'artifact': PRIVATE, 'result': PRIVATE, 'skill': PRIVATE}
                for day, regime in ((1, 'base'), (7, 'changed'), (11, 'exception'), (18, 'reversal'))]
            logs = []
            for firm in range(4):
                for workflow in ('onboarding', 'renewal', 'incident'):
                    owner = f'firm-{firm}__{workflow}-regulated'
                    for day in (3, 7, 11, 17):
                        train, val = (2, 1 if day == 3 else 2) if owner == employee else (0, 0)
                        logs.append({'employee': owner, 'day': day, 'available_unique_train': train,
                            'available_unique_val': val, 'eligible': train >= 2 and val >= 2,
                            'treatment_enabled': learned, 'selected_ids': [PRIVATE], 'reason': PRIVATE})
            updates = []
            if learned:
                for day in (7, 11, 17):
                    gate = {'applied_edits': [{'content': PRIVATE}] if day == 7 else [],
                        'rejected_edits': [{'content': PRIVATE}, {'content': PRIVATE}] if day == 17 else [],
                        'unmatched_edits': [{'content': PRIVATE}], 'gate_trials': [
                            {'target': 'skill', 'accepted': day == 7, 'task_deltas': PRIVATE},
                            {'target': 'final', 'accepted': day == 7, 'task_deltas': PRIVATE}], 'new_skill': PRIVATE}
                    if day == 11:
                        gate = {'accepted': False, 'gate_action': 'reject_incomplete', 'private': PRIVATE}
                    updates.append({'employee': employee, 'day': day, 'status': 'budget_exhausted' if day == 11 else 'completed',
                        'accepted': day == 7, 'parent_version': 0 if day == 7 else 1, 'deployed_version': 1,
                        'available_from_day': day + 1, 'optimizer_inputs': [{'prompt': PRIVATE}],
                        'gate_evidence': gate, 'skill': PRIVATE, 'replay_evidence': PRIVATE,
                        'costs': {'tokens': 1000, 'target_model_calls': 10, 'optimizer_model_calls': 1,
                            'replays': 4, 'wall_seconds': 5., 'accounting_complete': True, 'operations': PRIVATE}})
            cp = {'ecosystem': {'day': 21, 'private': PRIVATE}, 'runner': {'phase': 'advance',
                'sessions': sessions, 'updates': updates, 'experiences': experiences, 'learning_eligibility': logs,
                'skills': PRIVATE, 'private': PRIVATE}}
            v1 = {'status': 'completed', 'algorithm': algorithm, 'private': PRIVATE,
                'business': {'realized_utility': 105. if learned else 100., 'settled_entries': 3,
                    'unsettled_entries': 1, 'reward_censored_obligations': 1, 'private': PRIVATE},
                'costs': {'execution': _execution_costs(sessions), 'learning': _learning_costs(updates)},
                'prospective': {'attempts': 4, 'strict_successes': 4 if learned else 3,
                    'distinct_obligations_attempted': 4, 'retry_attempts': 0, 'strict_success_rate': 1. if learned else .75,
                    'mean_semantic_score': 1. if learned else .875, 'budget_exhausted_attempts': 0 if learned else 1}}
            fixed_fulfilled = 192 if learned else 180
            native_n, native_f = (3, 2) if learned else (2, 1)
            v2 = {'status': 'completed', 'algorithm': algorithm, 'metric_schema_version': 2,
                'correction_audit': {'eligible_for_paired_inference': True, 'issues': []},
                'commitments': commitment(240 + native_n, fixed_fulfilled + native_f),
                'source_breakdown': {'initial': commitment(12, 12), 'benchmark': commitment(228, fixed_fulfilled - 12),
                    'fixed_initial_and_benchmark': commitment(240, fixed_fulfilled), 'native_consumer': commitment(native_n, native_f),
                    'unknown': commitment(0, 0)}, 'private': PRIVATE, 'commitment_records': [PRIVATE]}
            run = root / slot['relative_path']
            for name, value in (('manifest.json', {'private': PRIVATE}), ('checkpoint.json', cp), ('REPORT.json', v1),
                                ('persona_cohort.json', {'private': PRIVATE})):
                write(run / name, value)
            v2['source_hashes'] = {'checkpoint_sha256': publication.sha((run / 'checkpoint.json').read_bytes()),
                'v1_report_sha256': publication.sha((run / 'REPORT.json').read_bytes())}
            write(run / 'REPORT.v2.json', v2)
    write(root / 'campaign.json', campaign)
    for name in ('CLI_LAUNCH_RECEIPTS.json', 'EXECUTION.json', 'execution_results.json'):
        write(root / name, {'kind': 'OFFLINE_FIXTURE_NOT_NATIVE_EVIDENCE', 'private': PRIVATE})
    return campaign


def stub_audit(root, strict=False):
    """Explicit offline substitute. It does NOT validate native artifacts."""
    assert strict is True
    campaign = json.loads((root / 'campaign.json').read_text())
    runs, calls, tokens = [], 0, 0
    for slot in campaign['slots']:
        run = root / slot['relative_path']
        cp = json.loads((run / 'checkpoint.json').read_text())
        state = cp['runner']
        calls += sum(row['usage']['api_calls'] for row in state['sessions']) + sum(row['costs']['target_model_calls'] + row['costs']['optimizer_model_calls'] for row in state['updates'])
        tokens += sum(row['usage']['total_tokens'] for row in state['sessions']) + sum(row['costs']['tokens'] for row in state['updates'])
        runs.append({'run_id': slot['run_id'], 'completed': True, 'status': 'completed',
            'evidence_sha256': {name: publication.sha((run / name).read_bytes()) for name in publication.RUN_FILES},
            'private': PRIVATE})
    return {'ok': True, 'status': 'valid_completed', 'errors': [], 'completed_runs': 6, 'complete_pairs': 3,
        'accounting_verified': True, 'runs': runs, 'accounting': {'learner_physical_calls': calls,
        'learner_measured_tokens': tokens, 'environment': {'logical_interview_requests': 60, 'private': PRIVATE}}, 'private': PRIVATE,
        'frozen_audit': {'ok': False, 'status': 'invalid', 'errors': [
            {'run_id': row['run_id'], 'code': 'non_native_or_wrong_cohort_execution', 'private': PRIVATE} for row in runs], 'private': PRIVATE},
        'correction': {'scope': 'Known native CLI module alias only',
            'campaign_sha256': publication.sha((root / 'campaign.json').read_bytes()),
            'launch_receipts_sha256': publication.sha((root / 'CLI_LAUNCH_RECEIPTS.json').read_bytes()),
            'corrected_auditor_sha256': publication.sha(Path(publication.audit_scale_cli.__file__).read_bytes()),
            'frozen_auditor_sha256': publication.sha((publication.ROOT / 'scripts/audit_scale.py').read_bytes()),
            'observation_kind': 'during_execution_not_preregistered', 'observed_actor_driver': '__main__.NativeActors',
            'resolved_actor_driver': 'lifespan.evaluation.runner.NativeActors', 'frozen_sources_changed': False,
            'raw_reports_rewritten': False, 'matched_ast_guards': 1, 'published_commit': 'b' * 40,
            'original_saved_audit_sha256': None, 'original_saved_audit_status': None, 'private': PRIVATE}}


class ScalePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw, self.out = self.base / 'raw', self.base / 'public-draft'
        self.campaign = fixture(self.raw)
        self.prereg = self.base / 'published-preregistration.json'
        self.prereg.write_bytes((self.raw / 'campaign.json').read_bytes())
        self.auditor = patch.object(publication, 'audit_campaign', side_effect=stub_audit).start()
        self.addCleanup(patch.stopall)

    def generate(self):
        return publication.report_scale(self.raw, self.out, preregistration_path=self.prereg)

    def mutate(self, run_index, name, edit, *, rebind=True):
        run = self.raw / self.campaign['slots'][run_index]['relative_path']
        data = json.loads((run / name).read_text())
        edit(data)
        write(run / name, data)
        if rebind and name in ('checkpoint.json', 'REPORT.json'):
            v2 = json.loads((run / 'REPORT.v2.json').read_text())
            field = 'checkpoint_sha256' if name == 'checkpoint.json' else 'v1_report_sha256'
            v2['source_hashes'][field] = publication.sha((run / name).read_bytes())
            write(run / 'REPORT.v2.json', v2)

    def test_complete_fixture_retains_all_worlds_employees_regimes_and_boundaries(self):
        result = self.generate()
        self.assertEqual((result['completed_worlds'], result['world_pairs']), (6, 3))
        self.assertEqual(len(result['worlds']), 6)
        exposure = result['learning_exposure']
        self.assertEqual((exposure['planned_employee_world_instances'], exposure['planned_learning_boundaries']), (72, 288))
        self.assertEqual(exposure['observed_learning_boundaries'], 288)
        self.assertEqual(exposure['recorded_updates'], 9)
        self.assertEqual(exposure['accepted_updates'], 3)
        self.assertTrue(exposure['complete'])
        self.assertEqual(exposure['hash_encoding'], 'canonical_json')
        own = next(row for row in exposure['runs'][1]['employees'] if row['employee'] == 'firm-0__incident-regulated')
        self.assertEqual([row['regime'] for row in own['regimes']], ['base', 'changed', 'exception', 'reversal'])
        self.assertEqual([(row['version'], row['sessions']) for row in own['versions']], [(0, 2), (1, 2)])
        self.assertEqual(set(p.name for p in self.out.iterdir()), {'SUMMARY.json', 'REPORT.md'})

    def test_primary_fixed_demand_is_distinct_from_endogenous_denominator(self):
        result = self.generate()
        base, learned = result['worlds'][:2]
        self.assertEqual(base['primary_fixed_demand']['accepted_before_work_horizon'], 240)
        self.assertEqual(base['all_commitments']['accepted_before_work_horizon'], 242)
        self.assertEqual(learned['all_commitments']['accepted_before_work_horizon'], 243)
        self.assertAlmostEqual(result['comparison']['equal_world_mean_deltas']['fixed_demand_fulfillment_rate'], .05)
        self.assertEqual(len(result['comparison']['pairs']), 3)
        self.assertIsNone(result['comparison']['confidence_interval'])

    def test_gate_proposals_edits_trials_unknown_bookkeeping_and_adoption_differ(self):
        opt = self.generate()['worlds'][1]['optimizer']
        self.assertEqual((opt['epochs'], opt['accepted_epochs'], opt['gate_recorded_epochs'], opt['gate_unreported_epochs']), (3, 1, 2, 1))
        self.assertEqual(opt['recorded_totals']['recorded_edit_proposals'], 5)
        self.assertEqual(opt['recorded_totals']['applied_edits'], 1)
        self.assertEqual(opt['recorded_totals']['rejected_edits'], 2)
        self.assertEqual(opt['recorded_totals']['unmatched_edits'], 2)
        self.assertEqual(opt['recorded_totals']['scored_candidate_trials'], 2)
        self.assertEqual(opt['recorded_totals']['final_gate_rechecks'], 2)
        self.assertIsNone(opt['updates'][1]['recorded_edit_proposals'])
        self.assertEqual(opt['recorded_totals']['optimizer_physical_calls'], 3)

    def test_costs_separate_measured_charged_learning_online_and_unknown_currency(self):
        costs = self.generate()['costs']
        self.assertEqual(costs['online']['tokens']['total'], 2400)
        self.assertEqual(costs['online']['charged_tokens']['total'], 2880)
        self.assertEqual(costs['learning']['tokens']['total'], 9000)
        self.assertEqual(costs['employee_and_optimizer']['measured_physical_calls'], 147)
        self.assertEqual(costs['employee_and_optimizer']['measured_tokens'], 11400)
        self.assertEqual(costs['employee_and_optimizer']['charged_or_reserved_tokens'], 11880)
        self.assertIsNone(costs['employee_and_optimizer']['estimated_usd'])
        self.assertIsNone(costs['all_in_estimated_usd'])
        self.assertIsNone(costs['environment']['tokens'])
        self.assertEqual(costs['environment']['logical_interview_requests'], 60)

    def test_privacy_allowlists_exclude_all_nested_text_absolute_paths_and_audit_payload(self):
        result = self.generate()
        for path in self.out.iterdir():
            text = path.read_text()
            self.assertNotIn(PRIVATE, text)
            self.assertNotIn(str(self.base), text)
            self.assertNotIn('commitment_records', text)
            self.assertNotIn('optimizer_inputs', text)
        provenance = result['provenance']
        self.assertEqual(provenance['hash_encoding'], 'sha256_raw_file_bytes')
        self.assertEqual(provenance['campaign_raw_sha256'], publication.sha(self.prereg.read_bytes()))
        self.assertEqual(provenance['postprocessor']['sha256'], publication.sha(Path(publication.__file__).read_bytes()))
        self.assertEqual(len(provenance['raw_input_sha256']), 34)
        self.assertEqual(provenance['audit']['frozen_status'], 'invalid')
        self.assertEqual(len(provenance['audit']['frozen_errors']), 6)
        self.assertEqual(provenance['audit']['corrected_status'], 'valid_completed')
        self.assertFalse(provenance['audit']['correction']['raw_reports_rewritten'])

    def test_rejects_unexplained_original_failure_or_unbound_alias_correction(self):
        for field, value in (('raw_reports_rewritten', True), ('observation_kind', 'preregistered'),
                             ('corrected_auditor_sha256', '0' * 64), ('launch_receipts_sha256', '0' * 64)):
            good = stub_audit(self.raw, True)
            good['correction'][field] = value
            self.auditor.side_effect = None
            self.auditor.return_value = good
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.generate()
        good = stub_audit(self.raw, True)
        good['frozen_audit']['errors'][0]['code'] = PRIVATE
        self.auditor.return_value = good
        with self.assertRaisesRegex(ValueError, 'unexplained_frozen'):
            self.generate()
        self.assertFalse(self.out.exists())

    def test_deterministic_outputs_and_source_bytes_preserved(self):
        before = {str(path.relative_to(self.raw)): path.read_bytes() for path in self.raw.rglob('*.json')}
        self.generate()
        second = self.base / 'second-draft'
        publication.report_scale(self.raw, second, preregistration_path=self.prereg)
        self.assertEqual((self.out / 'SUMMARY.json').read_bytes(), (second / 'SUMMARY.json').read_bytes())
        self.assertEqual((self.out / 'REPORT.md').read_bytes(), (second / 'REPORT.md').read_bytes())
        self.assertEqual(before, {str(path.relative_to(self.raw)): path.read_bytes() for path in self.raw.rglob('*.json')})

    def test_refuses_overwrite_and_output_inside_raw_campaign(self):
        self.out.mkdir()
        (self.out / 'keep').write_text('unchanged')
        with self.assertRaisesRegex(ValueError, 'already_exists'):
            self.generate()
        self.assertEqual((self.out / 'keep').read_text(), 'unchanged')
        with self.assertRaisesRegex(ValueError, 'separate_from_raw'):
            publication.report_scale(self.raw, self.raw / 'draft', preregistration_path=self.prereg)
        self.auditor.assert_not_called()

    def test_preregistration_requires_exact_published_bytes_not_semantic_equality(self):
        self.prereg.write_text(json.dumps(self.campaign))
        with self.assertRaisesRegex(ValueError, 'raw_hash_mismatch'):
            self.generate()
        self.auditor.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_rejects_incomplete_invalid_or_unverified_audit_by_default(self):
        good = stub_audit(self.raw, True)
        for edit in ({'status': 'incomplete'}, {'complete_pairs': 2}, {'completed_runs': 5},
                     {'ok': False}, {'accounting_verified': False}, {'errors': [PRIVATE]}):
            with self.subTest(edit=edit):
                self.auditor.side_effect = None
                self.auditor.return_value = {**good, **edit}
                with self.assertRaisesRegex(ValueError, 'strict_completed'):
                    self.generate()
                self.assertFalse(self.out.exists())

    def test_rejects_raw_receipt_hash_tampering_and_corrected_report_binding(self):
        receipt = stub_audit(self.raw, True)
        receipt['runs'][0]['evidence_sha256']['checkpoint.json'] = '0' * 64
        self.auditor.side_effect = None
        self.auditor.return_value = receipt
        with self.assertRaisesRegex(ValueError, 'changed_since_audit'):
            self.generate()
        self.auditor.side_effect = stub_audit
        self.mutate(0, 'REPORT.v2.json', lambda data: data['source_hashes'].update(checkpoint_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'corrected_report_raw_binding'):
            self.generate()

    def test_rejects_private_text_in_allowed_identity_field(self):
        self.mutate(1, 'checkpoint.json', lambda data: data['runner']['updates'][0].update(employee=PRIVATE))
        with self.assertRaises(ValueError):
            self.generate()
        self.assertFalse(self.out.exists())

    def test_rejects_wrong_commitment_counts_or_rates(self):
        self.mutate(0, 'REPORT.v2.json', lambda data: data['source_breakdown']['fixed_initial_and_benchmark'].update(fulfillment_rate=.99))
        with self.assertRaisesRegex(ValueError, 'commitment_rate_mismatch'):
            self.generate()
        self.assertFalse(self.out.exists())

    def test_corrected_endpoint_uses_work_horizon_not_later_observation(self):
        raw = commitment(5, 2)
        raw.update(fulfilled_at_observation=3, unfulfilled_at_observation=2)
        safe = publication._commitments(raw)
        self.assertEqual(safe['fulfillment_rate'], .4)
        self.assertEqual(safe['fulfilled_at_observation'], 3)

    def test_rejects_boolean_as_numeric_and_cost_disagreement(self):
        self.mutate(0, 'REPORT.json', lambda data: data['business'].update(realized_utility=True))
        with self.assertRaisesRegex(ValueError, 'numeric_evidence'):
            self.generate()
        self.mutate(0, 'REPORT.json', lambda data: data['business'].update(realized_utility=100.))
        self.mutate(0, 'REPORT.json', lambda data: data['costs']['execution']['tokens'].update(total=4000, recorded_total=4000))
        with self.assertRaisesRegex(ValueError, 'cost_mismatch'):
            self.generate()

    def test_rejects_missing_eligibility_and_infrastructure_failures(self):
        self.mutate(0, 'checkpoint.json', lambda data: data['runner']['learning_eligibility'].pop())
        with self.assertRaisesRegex(ValueError, 'incomplete_learning_exposure'):
            self.generate()
        self.mutate(0, 'checkpoint.json', lambda data: data['runner']['sessions'][0].update(infrastructure_valid=False))
        with self.assertRaisesRegex(ValueError, 'invalid_online_outcome'):
            self.generate()

    def test_rejects_source_mutation_during_reporting_before_output(self):
        real = publication.build_scale_summary
        def mutate_after_summary(campaign, records):
            result = real(campaign, records)
            (self.raw / 'campaign.json').write_bytes((self.raw / 'campaign.json').read_bytes() + b' ')
            return result
        with patch.object(publication, 'build_scale_summary', side_effect=mutate_after_summary):
            with self.assertRaisesRegex(ValueError, 'changed_during_reporting'):
                self.generate()
        self.assertFalse(self.out.exists())

    def test_final_source_recheck_catches_execution_revision_mismatch(self):
        campaign = json.loads((self.raw / 'campaign.json').read_text())
        campaign['source_sha256']['lifespan/evaluation/tasks.py'] = '0' * 64
        write(self.raw / 'campaign.json', campaign)
        self.prereg.write_bytes((self.raw / 'campaign.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'changed_during_reporting'):
            self.generate()
        self.assertFalse(self.out.exists())

    def test_cli_rejects_invalid_without_echoing_private_exception_payload(self):
        self.auditor.side_effect = ValueError(PRIVATE + str(self.base))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = publication.main([str(self.raw), '--out', str(self.out), '--preregistration', str(self.prereg)])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue()), {'ok': False, 'error': 'ValueError'})
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
