"""JobBench source fidelity, weighted conjunction, recovery and offline evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import read, save, sha
from worldlab import jobbench_capabilities as caps
from worldlab.jobbench import JobBenchJudge, SourceRubricJudge, normalize_rubrics, parse_response, output_evidence
from test_worldlab_judge_recovery import Client

TASK = 'jobbench/fixture/task1'
PUBLIC = {'id': TASK, 'source': 'jobbench', 'instruction': 'Write the configuration.',
          'input_formats': ['.conf'], 'language': 'en'}
REVIEW = {'instruction_sha256': hashlib.sha256(PUBLIC['instruction'].encode()).hexdigest(),
          'input_formats': ['.conf']}


class Bank:
    def __init__(self, root, weights=(8, 2)):
        self.root = root
        self.verification = {'manifest_sha256': 'fixture'}
        save(root / 'private/RUBRICS.json', {'rubrics': [
            {'rubric': f'Requirement {i}', 'weight': w, 'criterion': ['First condition', 'Second condition']}
            for i, w in enumerate(weights)]})
        self.by_id = {TASK: {'private_directory': 'private', 'rubric_sha256': sha(root / 'private/RUBRICS.json')}}

    def public(self, task_id): return {**PUBLIC, 'id': task_id}


def response(i, passes=(True, True), *, text=None, status='completed', usage=True):
    value = {'rubric_index': i, 'criteria': {str(j): {'passed': passed,
             'reasoning': 'Brief rationale.', 'evidence': ['output/result.conf']} for j, passed in enumerate(passes)}}
    return SimpleNamespace(status=status, output_text=json.dumps(value) if text is None else text,
        usage=SimpleNamespace(input_tokens=80, output_tokens=20, total_tokens=100) if usage else None)


class Tests(unittest.TestCase):
    def setUp(self):
        self.patch = patch.dict(caps.REVIEWED, {TASK: REVIEW})
        self.patch.start(); self.addCleanup(self.patch.stop)

    def case(self, replies, weights=(8, 2), call_limit=None):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); bank = Bank(root, weights)
        workspace = root / 'workspace'; (workspace / 'output').mkdir(parents=True)
        (workspace / 'source.conf').write_text('Exact source bytes.\r\n')
        (workspace / 'output/result.conf').write_bytes(b'Full output\r\nsecond line\r\n')
        baseline = {'source.conf': sha(workspace / 'source.conf')}
        client = Client(replies)
        judge = JobBenchJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
        out = root / 'judging'
        grade = judge.grade(TASK, workspace, baseline, out, call_limit=call_limit)
        return bank, judge, workspace, baseline, out, grade, client

    def audit(self, case):
        bank, judge, workspace, baseline, out, grade, _ = case
        judge.audit_grade(bank, TASK, workspace, baseline, out, grade)

    def test_original_weighted_conjunction_not_fraction_of_subcriteria(self):
        case = self.case([response(0, (True, False)), response(1)])
        grade = case[-2]
        self.assertTrue(grade['grading_complete']); self.assertFalse(grade['success'])
        self.assertEqual(grade['quality_score'], .2); self.assertEqual(grade['rubric_pass_rate'], .5)
        self.assertEqual([v['score'] for v in grade['criteria']], [0, 2])
        self.assertEqual(grade['usage']['charged_tokens'], 200)
        self.audit(case)

    def test_exact_subcriterion_schema_and_no_generated_character_limits(self):
        case = self.case([response(0), response(1)])
        client = case[-1]
        schema = client.calls[0]['extra_body']['structured_outputs']['json']
        self.assertEqual(schema['properties']['criteria']['required'], ['0', '1'])
        self.assertFalse(schema['properties']['criteria']['additionalProperties'])
        self.assertNotIn('maxLength', json.dumps(schema))
        self.assertEqual(client.calls[0]['max_output_tokens'], 4096)
        self.assertFalse(client.calls[0]['stream']); self.audit(case)

    def test_ninth_call_repairs_eighth_rubric_with_all_usage_retained(self):
        replies = [response(i) for i in range(7)] + [response(7, text='{', status='incomplete'), response(7)]
        case = self.case(replies, weights=(1,) * 8)
        self.assertTrue(case[-2]['grading_complete'])
        self.assertEqual(case[-2]['usage']['physical_model_calls'], 9)
        self.assertEqual(case[-2]['usage']['charged_tokens'], 900)
        self.audit(case)

    def test_twelve_rubrics_keep_their_subcriteria_and_thirteenth_repair(self):
        replies=[response(i) for i in range(11)]+[response(11,text='{',status='incomplete'),response(11)]
        case=self.case(replies,weights=(1,)*12)
        self.assertTrue(case[-2]['grading_complete'])
        self.assertEqual(case[-2]['usage']['physical_model_calls'],13)
        self.assertEqual(case[1].max_model_calls_for(TASK),13)
        self.audit(case)

    def test_known_format_failure_can_repair_but_valid_failure_is_final(self):
        case = self.case([response(0, text='bad'), response(0, (False, False)), response(1)])
        self.assertEqual(case[-2]['quality_score'], .2)
        self.assertEqual(len(case[-1].calls), 3); self.audit(case)

    def test_unknown_usage_transport_and_explicit_lower_budget_do_not_retry(self):
        for bad in [response(0, usage=False), ConnectionError('fixture')]:
            case = self.case([bad, response(0)])
            self.assertFalse(case[-2]['grading_complete']); self.assertEqual(len(case[-1].calls), 1)
            self.assertFalse(case[-2]['usage']['accounting_complete'])
            self.assertEqual(case[-2]['format_recoveries'], [])
        case = self.case([response(0, text='{', status='incomplete'), response(0)], call_limit=1)
        self.assertFalse(case[-2]['grading_complete']); self.assertEqual(len(case[-1].calls), 1)

    def test_missing_duplicate_extra_subcriteria_or_unknown_file_rejected(self):
        rubric = normalize_rubrics({'rubrics': [{'rubric': 'Question', 'weight': 1, 'criterion': ['A', 'B']}]})[0]
        for edit in ['missing', 'extra', 'file', 'bool']:
            value = json.loads(response(0).output_text)
            if edit == 'missing': del value['criteria']['1']
            elif edit == 'extra': value['criteria']['2'] = value['criteria']['1']
            elif edit == 'file': value['criteria']['0']['evidence'] = ['nonexistent.conf']
            else: value['criteria']['0']['passed'] = 1
            with self.assertRaises(ValueError): parse_response({'status': 'completed', 'text': json.dumps(value)}, rubric, ['output/result.conf'])
        text = response(0).output_text.replace('"rubric_index": 0', '"rubric_index": 0, "rubric_index": 0')
        with self.assertRaises(ValueError): parse_response({'status': 'completed', 'text': text}, rubric, ['output/result.conf'])

    def test_complete_config_evidence_root_extras_and_empty_files(self):
        case = self.case([response(0), response(1)])
        _, _, workspace, baseline, out, _, _ = case
        self.assertEqual(read(out / 'EVIDENCE.json')['output_files']['output/result.conf']['text'], 'Full output\r\nsecond line\r\n')
        (workspace / 'extra.rules').write_text('root output')
        (workspace / 'empty').touch()
        (workspace / 'scratch').mkdir(); (workspace / 'scratch/temporary.pdf').write_bytes(b'\xff')
        files = output_evidence(workspace, baseline)
        self.assertEqual(set(files), {'output/result.conf', 'extra.rules', 'empty'})
        self.assertEqual(files['empty']['text'], '')
        (workspace / 'output/nontext.pdf').write_bytes(b'%PDF')
        with self.assertRaisesRegex(ValueError, 'document evidence'): output_evidence(workspace, baseline)
        (workspace / 'output/nontext.pdf').unlink()
        (workspace / 'output/unsafe.rules').symlink_to(workspace / 'source.conf')
        with self.assertRaisesRegex(ValueError, 'Symlink'): output_evidence(workspace, baseline)

    def test_capability_review_is_task_specific_and_tied_to_original_text(self):
        self.assertEqual(caps.unsupported(PUBLIC), [])
        for changed in [dict(PUBLIC, id='jobbench/another/task'), dict(PUBLIC, instruction='Research the live web.'),
                        dict(PUBLIC, input_formats=['.pdf']), dict(PUBLIC, requires_app_state=True)]:
            self.assertTrue(caps.unsupported(changed))
        harness = object.__new__(caps.ReviewedOfflineHermes)
        self.assertEqual(harness.unsupported(PUBLIC), [])
        self.assertTrue(harness.unsupported(dict(PUBLIC, id='jobbench/another/task')))

    def test_audit_rejects_changed_source_evidence_prompt_score_and_feedback(self):
        for change in ['rubric', 'output', 'request', 'score', 'feedback', 'meter']:
            case = self.case([response(0), response(1)])
            bank, _, workspace, _, out, grade, _ = case
            self.audit(case)
            if change == 'rubric': (bank.root / 'private/RUBRICS.json').write_text('{}')
            elif change == 'output': (workspace / 'output/result.conf').write_text('Replaced')
            elif change == 'request': save(out / 'REQUEST-00.json', {'different': True})
            else:
                if change == 'score': grade['quality_score'] = .5
                elif change == 'feedback': grade['feedback'] = 'Unrelated learner advice'
                else: grade['usage']['operations'][0]['request_input_sha256'] = 'wrong'
                save(out / 'GRADE.json', grade)
            with self.assertRaises(ValueError): self.audit(case)

    def test_source_router_uses_jobbench_policy_without_internal_supplements(self):
        case = self.case([response(0), response(1)])
        bank, judge, workspace, baseline, out, grade, _ = case
        router = SourceRubricJudge(bank, 'fixture', Client.base_url)
        router.judges['jobbench'] = judge
        with patch.object(router.judges['internal_eurobench'], 'audit_grade', side_effect=AssertionError('Wrong source')):
            router.audit_grade(bank, TASK, workspace, baseline, out, grade)
        self.assertEqual(router.unsupported(PUBLIC), [])
        self.assertTrue(router.unsupported(dict(PUBLIC, source='unknown')))
        self.assertEqual(router.max_model_calls, 13)
        self.assertEqual(router.max_model_calls_for(TASK),3)

    def test_string_criteria_supported_and_invalid_weights_rejected(self):
        rubric = {'rubric': 'Question', 'weight': 2, 'criterion': 'A'}
        self.assertEqual(normalize_rubrics({'rubrics': [rubric]})[0]['criterion'], ['A'])
        for weight in [True, 0, -1, float('nan')]:
            with self.assertRaises(ValueError): normalize_rubrics({'rubrics': [dict(rubric, weight=weight)]})


if __name__ == '__main__': unittest.main()
