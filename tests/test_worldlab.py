"""Information boundaries, fixed exposure denominators, and failed execution safety."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import save
from worldlab.calibration import fit, slots
from worldlab.contracts import Feedback, released_training
from worldlab.campaign import prepare, execute, summarize


class FakeBank:
    def __init__(self):
        self.rows = [{'id': str(i), 'partition': 'calibration_train' if i < 3 else 'calibration_holdout',
                     'title': 'Reconcile invoice costs', 'workflow': 'finance', 'language': 'en',
                     'source': 'internal_eurobench', 'calibration_group': str(i)} for i in range(4)]
        self.by_id = {r['id']: r for r in self.rows}
        self.verification = {'manifest_sha256': 'bank'}

    def public(self, ident):
        if ident == '3':
            raise AssertionError('Holdout brief leaked to calibration')
        return {'source': 'internal_eurobench', 'instruction': 'Reconcile invoice costs ' + ident,
                'language': 'en', 'budgets': {'time_seconds': 120}}

    def stage(self, ident, ws):
        ws.mkdir(parents=True)
        return {}

    def private_definition(self, ident):
        return {'secret': ident}


SPEC = {'schema_version': 1, 'repeats': 2, 'employees': [
    {'id': 'analyst', 'role': 'Finance analyst', 'language': 'en', 'representative_tasks': [
        {'prompt': 'reconcile invoices and costs', 'matches': 2}]}]}


class FakeGrader:
    def identity(self): return {'name': 'fake'}
    def unsupported(self, public): return []
    def grade(self, definition, workspace, baseline):
        return {'grading_complete': True, 'mechanical_success': False}


class FakeHarness:
    def identity(self): return {'name': 'fake'}
    def unsupported(self, public): return []
    def run(self, request, root):
        if 'secret' in request.instruction:
            raise AssertionError('Private definition leaked')
        return {'status': 'completed', 'accounting_complete': True,
                'physical_model_calls': 1, 'charged_tokens': 20}


class Tests(unittest.TestCase):
    def test_holdout_never_read_and_explicit_holdout_rejected(self):
        bank = FakeBank()
        result = fit(bank, SPEC)
        self.assertEqual(len(result['anchors'][0]['matches']), 2)
        spec = copy.deepcopy(SPEC)
        spec['employees'][0]['representative_tasks'][0]['selector'] = {'task_ids': ['3']}
        with self.assertRaises(ValueError): fit(bank, spec)

    def test_same_family_and_translations_do_not_inflate_selection(self):
        bank = FakeBank()
        bank.rows[1]['calibration_group'] = '0'
        result = fit(bank, SPEC)
        groups = [x['lineage_group'] for x in result['anchors'][0]['matches']]
        self.assertEqual(groups, ['0', '2'])
        schedule = slots(bank, result, SPEC)
        self.assertEqual(len(schedule), 4)
        self.assertEqual(schedule, slots(bank, result, SPEC))
        self.assertEqual([s['repeat'] for s in schedule], [0, 0, 1, 1])

    def test_unmatched_prompts_remain_uncovered(self):
        spec = copy.deepcopy(SPEC)
        spec['employees'][0]['representative_tasks'][0]['prompt'] = 'astronomy telescope nebula'
        result = fit(FakeBank(), spec)
        self.assertEqual(result['weighted_retrieval_coverage'], 0)
        self.assertEqual(result['anchors'][0]['unfilled_matches'], 2)

    def test_future_and_validation_never_reach_training(self):
        def e(task, observed, released, partition='train'):
            return Feedback(task, task, observed, released, partition, 'request', [], 0, 'feedback')
        observations = [e('a', 1, 2), e('a', 2, 3), e('b', 2, 2, 'validation'), e('c', 3, 5)]
        self.assertEqual(released_training(observations, 2), (observations[0],))
        self.assertEqual(released_training(observations, 3), (observations[1],))
        with self.assertRaises(ValueError): released_training(list(reversed(observations)), 3)

    def test_failures_remain_in_full_schedule_and_no_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            bank, harness, grader = FakeBank(), FakeHarness(), FakeGrader()
            prepare(bank, SPEC, harness, grader, out)
            report = execute(bank, harness, grader, out)
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(report['completed_native_attempts'], 4)
            self.assertEqual(report['mechanical_successes'], 0)
            self.assertEqual(report['charged_or_reserved_tokens'], 80)
            with self.assertRaises(FileExistsError): execute(bank, harness, grader, out)

    def test_ambiguous_attempt_stops_without_replacing_or_dropping_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            bank, harness, grader = FakeBank(), FakeHarness(), FakeGrader()
            prepare(bank, SPEC, harness, grader, out)
            with patch.object(harness, 'run', return_value={'status': 'infrastructure_ambiguous',
                    'charged_tokens': 500000, 'accounting_complete': False}):
                report = execute(bank, harness, grader, out)
            self.assertEqual(report['recorded_slots'], 1)
            self.assertEqual(len(report['missing_slots']), 3)
            self.assertTrue((out / 'INFLIGHT.json').exists())
            self.assertEqual(report['status'], 'incomplete')

    def test_grader_exception_does_not_reuse_previous_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            bank, harness, grader = FakeBank(), FakeHarness(), FakeGrader()
            prepare(bank, SPEC, harness, grader, out)
            first = {'status': 'completed', 'accounting_complete': True, 'physical_model_calls': 1, 'charged_tokens': 20}
            with patch.object(harness, 'run', side_effect=[first, RuntimeError()]):
                report = execute(bank, harness, grader, out)
            self.assertEqual(report['charged_or_reserved_tokens'], 500020)
            self.assertEqual(report['unknown_call_count_attempts'], 1)

    def test_plan_mutation_and_duplicate_results_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            bank, harness, grader = FakeBank(), FakeHarness(), FakeGrader()
            prepare(bank, SPEC, harness, grader, out)
            with (out / 'PLAN.json').open('a') as f: f.write(' ')
            with self.assertRaises(ValueError): execute(bank, harness, grader, out)
        with self.assertRaises(ValueError):
            summarize({'slots': [{'id': 'a'}]}, [{'id': 'a'}, {'id': 'a'}])


if __name__ == '__main__': unittest.main()
