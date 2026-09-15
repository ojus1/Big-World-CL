"""Format recovery cannot become outcome selection or hide physical costs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from scripts.source_world_calibration import read, save, sha
from worldlab.qualitative import FrozenRubricJudge, REPAIR_RULES


def response(passed=False, *, status='completed', text=None, usage=True):
    return SimpleNamespace(status=status, output_text=text if text is not None else json.dumps({
        'criterion_id': 'q', 'passed': passed, 'evidence': 'output/result.md', 'reasoning': 'Final decision.'}),
        usage=SimpleNamespace(input_tokens=50, output_tokens=10, total_tokens=60) if usage else None)


class Bank:
    def __init__(self, root):
        self.root = root
        self.verification = {'manifest_sha256': 'fixture'}
        save(root / 'private/rubric.json', {'criteria': [{'id': 'q', 'weight': 1, 'requirement': 'Use the source.'}]})
        self.by_id = {'fixture': {'private_directory': 'private', 'rubric_sha256': sha(root / 'private/rubric.json')}}

    def public(self, task_id):
        return {'id': task_id, 'source': 'internal_eurobench', 'instruction': 'Use the source.', 'input_formats': ['.md']}

    def private_definition(self, task_id): return {'checks': []}


class Client:
    base_url = 'http://127.0.0.1:8011/v1'
    max_retries = 0
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)
    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        result = next(self.replies)
        if isinstance(result, Exception): raise result
        return result
    def close(self): pass


class Tests(unittest.TestCase):
    def run_case(self, replies, *, call_limit=8):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root = Path(tmp.name);bank = Bank(root)
        workspace = root / 'workspace';(workspace / 'output').mkdir(parents=True)
        (workspace / 'source.md').write_text('Source fact.');(workspace / 'output/result.md').write_text('Result.')
        baseline = {'source.md': sha(workspace / 'source.md')}
        client = Client(replies)
        judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
        out = root / 'judging'
        grade = judge.grade('fixture', workspace, baseline, out, call_limit=call_limit)
        return bank, judge, workspace, baseline, out, grade, client

    def audit(self, case):
        bank, judge, workspace, baseline, out, grade, _ = case
        judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)

    def test_valid_failing_verdict_is_final_without_retry(self):
        case = self.run_case([response(False), response(True)])
        *_, out, grade, client = case
        self.assertTrue(grade['grading_complete']);self.assertFalse(grade['success'])
        self.assertEqual(len(client.calls), 1);self.assertEqual(grade['format_recoveries'], [])
        self.assertFalse(list(out.glob('REPAIR-*')))
        self.audit(case)

    def test_returned_incomplete_response_recovers_and_charges_both_calls(self):
        case = self.run_case([response(status='incomplete', text='{'), response(False)])
        *_, out, grade, client = case
        self.assertTrue(grade['grading_complete']);self.assertFalse(grade['success'])
        self.assertEqual(grade['usage']['physical_model_calls'], 2)
        self.assertEqual(grade['usage']['charged_tokens'], 120)
        self.assertEqual(read(out / 'RESPONSE-00.json')['status'], 'incomplete')
        self.assertEqual(read(out / 'REQUEST-00.json'), read(out / 'REPAIR-REQUEST-00.json'))
        self.assertNotIn(REPAIR_RULES, client.calls[0]['input'][0]['content'])
        self.assertIn(REPAIR_RULES, client.calls[1]['input'][0]['content'])
        self.audit(case)

    def test_malformed_returned_json_can_recover(self):
        case = self.run_case([response(text='not json'), response(True)])
        self.assertTrue(case[-2]['grading_complete']);self.assertTrue(case[-2]['success'])
        self.assertEqual(case[-2]['format_recoveries'][0]['reason'], 'invalid_verdict')
        self.audit(case)

    def test_repeated_format_failure_does_not_dispatch_a_third_call(self):
        case = self.run_case([response(status='incomplete'), response(text='bad'), response(True)])
        grade, client = case[-2:]
        self.assertFalse(grade['grading_complete']);self.assertEqual(len(client.calls), 2)
        self.assertEqual(grade['usage']['charged_tokens'], 120)
        self.assertEqual(len(grade['format_recoveries']), 1)

    def test_unknown_transport_or_usage_is_never_retried(self):
        for bad in [ConnectionError('fixture'), response(usage=False)]:
            with self.subTest(bad=type(bad).__name__):
                case = self.run_case([bad, response(True)])
                grade, client = case[-2:]
                self.assertFalse(grade['grading_complete']);self.assertFalse(grade['usage']['accounting_complete'])
                self.assertEqual(len(client.calls), 1);self.assertEqual(grade['format_recoveries'], [])

    def test_format_recovery_still_respects_original_call_allocation(self):
        case = self.run_case([response(status='incomplete'), response(True)], call_limit=1)
        grade, client = case[-2:]
        self.assertFalse(grade['grading_complete']);self.assertEqual(len(client.calls), 1)
        self.assertEqual(grade['usage']['physical_model_calls'], 1)
        self.assertEqual(grade['usage']['charged_tokens'], 60)

    def test_eighth_criterion_can_use_declared_ninth_call_without_retrying_valid_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bank = Bank(root)
            criteria = [{'id': f'q{i}', 'weight': 1, 'requirement': 'Use the source.'} for i in range(8)]
            save(root / 'private/rubric.json', {'criteria': criteria})
            bank.by_id['fixture']['rubric_sha256'] = sha(root / 'private/rubric.json')
            workspace = root / 'workspace'; (workspace / 'output').mkdir(parents=True)
            (workspace / 'source.md').write_text('Source fact.')
            (workspace / 'output/result.md').write_text('Candidate result.')
            def verdict(index):
                value = json.loads(response(False).output_text); value['criterion_id'] = f'q{index}'
                return response(text=json.dumps(value))
            client = Client([*(verdict(i) for i in range(7)), response(status='incomplete', text='{'), verdict(7)])
            judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
            baseline = {'source.md': sha(workspace / 'source.md')}; out = root / 'judging'
            grade = judge.grade('fixture', workspace, baseline, out, call_limit=judge.max_model_calls)
            self.assertTrue(grade['grading_complete']); self.assertFalse(grade['success'])
            self.assertEqual(grade['usage']['physical_model_calls'], 9)
            self.assertEqual(grade['usage']['charged_tokens'], 540)
            self.assertEqual(grade['format_recoveries'], [{'criterion_index': 7, 'criterion_id': 'q7', 'reason': 'incomplete'}])
            self.assertEqual(len(list(out.glob('REPAIR-RESPONSE-*'))), 1)
            judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)

    def test_auditor_rejects_outcome_selection_or_changed_repair_context(self):
        for tamper in ['valid_initial', 'changed_evidence', 'changed_prompt_receipt']:
            with self.subTest(tamper=tamper):
                case = self.run_case([response(status='incomplete', text='{'), response(True)])
                *_, out, grade, _ = case
                self.audit(case)
                if tamper == 'valid_initial':
                    save(out / 'RESPONSE-00.json', {'status': 'completed', 'text': response(False).output_text, 'evaluation_method': 'model'})
                elif tamper == 'changed_evidence':
                    payload = read(out / 'REPAIR-REQUEST-00.json');payload['evidence']['instruction'] = 'Different task.'
                    save(out / 'REPAIR-REQUEST-00.json', payload)
                else:
                    grade['usage']['operations'][1]['request_input_sha256'] = 'wrong'
                    save(out / 'GRADE.json', grade)
                with self.assertRaises(ValueError):self.audit(case)


if __name__ == '__main__': unittest.main()
