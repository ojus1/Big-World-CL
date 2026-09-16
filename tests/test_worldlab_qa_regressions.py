from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import read, save, sha
from worldlab import supplier_notes
from worldlab.qualitative import FrozenRubricJudge, request_verdict, verdict_input
from worldlab.artifact_contract import input_changes
from test_worldlab_judge_recovery import Bank, Client, response


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def grade_case(self, mutate):
        workspace = self.root / 'workspace'; (workspace / 'output').mkdir(parents=True)
        (workspace / 'source.md').write_text('Source fact.')
        (workspace / 'output/result.md').write_text('Result.')
        baseline = {'source.md': sha(workspace / 'source.md')}
        bank = Bank(self.root / 'bank')
        mutate(workspace)
        client = Client([response(True)])
        judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
        out = self.root / 'judging'
        grade = judge.grade('fixture', workspace, baseline, out)
        judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)
        return workspace, baseline, bank, judge, out, grade, client

    def test_symlink_is_final_failed_submission_with_zero_judge_cost_and_no_target_read(self):
        outside = self.root / 'outside'; outside.write_text('DO NOT COPY THIS')
        case = self.grade_case(lambda w: (w / 'output/link.md').symlink_to(outside))
        workspace, baseline, bank, judge, out, grade, client = case
        self.assertTrue(grade['grading_complete']); self.assertFalse(grade['success'])
        self.assertEqual(grade['quality_score'], 0.)
        self.assertEqual(grade['usage']['physical_model_calls'], 0)
        self.assertTrue(grade['usage']['accounting_complete']); self.assertFalse(client.calls)
        self.assertIn('output/link.md', grade['feedback'])
        self.assertNotIn('DO NOT COPY THIS', json.dumps(grade))
        outside.write_text('External changes cannot affect this rejection')
        judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)
        (workspace / 'output/link.md').unlink()
        with self.assertRaisesRegex(ValueError, 'not reproducible'):
            judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)

    def test_known_invalid_output_formats_are_scored_without_model_calls(self):
        for filename, content, code in [('binary.png', b'\x89PNG', 'unsupported_format'),
                ('invalid.md', b'\xff', 'invalid_utf8'), ('bad.zip', b'not a zip', 'invalid_duplicate_archive')]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                *_, grade, client = self.grade_case(lambda w: (w / 'output' / filename).write_bytes(content))
                self.assertEqual(grade['artifact_contract']['evidence_violations'][0]['code'], code)
                self.assertFalse(client.calls)

    def test_integrity_zero_includes_the_real_reason_even_when_all_rubric_criteria_pass(self):
        *_, grade, client = self.grade_case(lambda w: (w / 'build_planning.py').write_text('print(1)'))
        self.assertTrue(all(v['passed'] for v in grade['criteria']))
        self.assertEqual(grade['quality_score'], 0.)
        self.assertIn('build_planning.py', grade['feedback'])
        self.assertIn('scratch/', grade['feedback'])
        self.assertEqual(len(client.calls), 1)

    def test_infrastructure_errors_are_not_misreported_as_bad_submissions(self):
        with patch('worldlab.qualitative.workspace_evidence', side_effect=PermissionError('fixture I/O failure')):
            with self.assertRaises(PermissionError): self.grade_case(lambda w: None)

    def test_absent_or_blank_deliverables_are_zero_cost_failures_even_with_source_evidence(self):
        for kind in ['absent', 'empty', 'whitespace', 'scratch_only', 'root_only']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                def mutate(workspace):
                    output = workspace / 'output/result.md'
                    output.unlink()
                    if kind == 'empty': output.touch()
                    if kind == 'whitespace': output.write_text(' \n\t')
                    if kind == 'scratch_only':
                        (workspace / 'scratch').mkdir()
                        (workspace / 'scratch/result.md').write_text('Unsubmitted result.')
                    if kind == 'root_only': (workspace / 'result.md').write_text('Wrong directory.')
                workspace, baseline, bank, judge, out, grade, client = self.grade_case(mutate)
                self.assertTrue(grade['grading_complete'])
                self.assertEqual(grade['quality_score'], 0.)
                self.assertFalse(grade['success']); self.assertFalse(client.calls)
                self.assertEqual(grade['usage']['physical_model_calls'], 0)
                self.assertEqual(grade['artifact_contract']['evidence_violations'][0]['code'], 'missing_deliverable')
                (workspace / 'output/result.md').write_text('A submitted result.')
                with self.assertRaisesRegex(ValueError, 'not reproducible'):
                    judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)

    def test_deliverable_guard_does_not_add_a_length_or_correctness_requirement(self):
        *_, grade, client = self.grade_case(lambda w: (w / 'output/result.md').write_text('0'))
        self.assertTrue(grade['success'])
        self.assertEqual(len(client.calls), 1)

    def test_baseline_output_file_is_not_a_new_candidate_deliverable(self):
        from worldlab.artifact_contract import CandidateEvidenceError, require_deliverable
        files = {'output/template.md': {'text': 'Given template.'}}
        with self.assertRaises(CandidateEvidenceError):
            require_deliverable(files, {'output/template.md': 'original'})
        with self.assertRaises(CandidateEvidenceError):
            require_deliverable({'output/bundle.zip': {'text': 'Archive descriptor.',
                'representation': 'verified_duplicate_text_archive'}}, {})

    def test_invalid_artifact_finalizes_attempt_and_preserves_known_solver_cost(self):
        from test_worldlab_adapters import Harness
        from worldlab.attempts import execute_task
        from worldlab.audit_worlds import audit_attempt
        from worldlab.contracts import Budget
        class StagedBank(Bank):
            def __init__(self, root):
                super().__init__(root)
                self.by_id['fixture']['public_directory'] = 'public'
                self.inventory = {'public/source.md': {'sha256': hashlib.sha256(b'Source fact.').hexdigest()}}
            def public(self, task_id): return {**super().public(task_id), 'language': 'en'}
            def stage(self, task_id, workspace):
                workspace.mkdir(parents=True)
                (workspace / 'source.md').write_text('Source fact.')
                return {'source.md': sha(workspace / 'source.md')}
        class LinkHarness(Harness):
            def run(self, request, artifact_root):
                result = super().run(request, artifact_root)
                (request.workspace / 'output').mkdir()
                (request.workspace / 'output/link.md').symlink_to('/unread/outside')
                return result
            @staticmethod
            def audit_execution(root, request, receipt):
                if (root / 'deployment.txt').read_text() != request['skill']: raise ValueError('Fixture skill drift')
        bank = StagedBank(self.root / 'bank'); client = Client([]); harness = LinkHarness()
        judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
        out = self.root / 'attempt'
        result = execute_task(bank, harness, judge, task_id='fixture', employee_id='fixture-employee',
                              skill='seed', budget=Budget(), out=out)
        self.assertEqual(result['status'], 'completed'); self.assertTrue(result['accounting_complete'])
        self.assertEqual(result['tokens'], result['execution']['charged_tokens'])
        self.assertEqual(result['model_calls'], result['execution']['physical_model_calls'])
        self.assertEqual(read(out / 'ATTEMPT.json'), result)
        audit_attempt(bank, out, 'fixture', 'seed', harness, judge=judge)

    def test_replaced_input_directory_is_detected_without_following_it(self):
        workspace = self.root / 'workspace'; workspace.mkdir()
        outside = self.root / 'outside'; outside.mkdir()
        (outside / 'source.md').write_text('Unchanged bytes but wrong authority')
        (workspace / 'input').symlink_to(outside, target_is_directory=True)
        with patch('worldlab.artifact_contract.sha', side_effect=AssertionError('Must not read target')):
            self.assertEqual(input_changes(workspace, {'input/source.md': 'digest'}), ['input/source.md'])

    def supplier_fixture(self, notes):
        instruction = 'Supplier fixture: five rows and notes at most 200 characters.'
        criterion = {'id': 'R7', 'weight': 2, 'requirement': 'Notes <= 200 chars, German, evidence-based.'}
        source = 'Original evidence.'
        registry = self.root / 'registry.json'
        save(registry, [{'task_id': 'fixture', 'instruction_sha256': hashlib.sha256(instruction.encode()).hexdigest(),
            'source_sha256': {'input/source.md': hashlib.sha256(source.encode()).hexdigest()},
            'criterion': criterion, 'semantic_requirement': 'Notes in German with evidence-based substance.'}])
        stream = io.StringIO(newline=''); writer = csv.writer(stream)
        writer.writerow(supplier_notes.COLUMNS)
        writer.writerows([[f'K{i}', 'Name', 'erfuellt', 'source.md', note] for i, note in enumerate(notes, 1)])
        payload = {'criterion': criterion, 'evidence': {'instruction': instruction, 'files': {
            'input/source.md': {'text': source}, supplier_notes.OUTPUT: {'text': stream.getvalue()}}}}
        patcher = patch.object(supplier_notes, 'REGISTRY', registry); patcher.start(); self.addCleanup(patcher.stop)
        return payload

    def test_csv_counts_quoted_comma_newline_unicode_boundary_without_trim(self):
        payload = self.supplier_fixture(['é'*200, 'a,b\nquoted "field"', '🙂'*200, 'a'*199+' ', ''])
        measured = supplier_notes.check(payload)
        self.assertTrue(measured['passed'])
        self.assertEqual([v['characters'] for v in measured['counts']], [200, 18, 200, 200, 0])
        self.assertIsNone(supplier_notes.veto(payload), 'Length alone never passes semantic R7')
        body = json.loads(verdict_input(payload)[1]['content'])
        self.assertEqual(body['criterion']['requirement'], 'Notes in German with evidence-based substance.')
        self.assertEqual(body['prevalidated_subconditions'], measured)
        # The semantic model still controls language/substance after counts pass.
        client = Client([response(False, text=json.dumps({'criterion_id': 'R7', 'passed': False,
            'evidence': supplier_notes.OUTPUT, 'reasoning': 'Notes have no substantive evidence.'}))])
        result = request_verdict(client, {'model': 'fixture'}, payload, 1)
        self.assertFalse(json.loads(result.output_text)['passed']); self.assertEqual(len(client.calls), 1)

    def test_overlimit_and_malformed_csv_are_not_sent_to_semantic_model(self):
        payload = self.supplier_fixture(['a'*201]*5)
        self.assertFalse(json.loads(request_verdict(None, None, payload, 1).output_text)['passed'])
        for body in ['kriterium_id,anmerkung\nK1,ok\n', '"unterminated', 'a,b,c,d,e\n']:
            value = deepcopy(payload); value['evidence']['files'][supplier_notes.OUTPUT]['text'] = body
            self.assertFalse(supplier_notes.check(value)['passed'])
            self.assertFalse(json.loads(request_verdict(None, None, value, 1).output_text)['passed'])

    def test_evidence_projection_preserves_embedded_crlf_at_the_count_boundary(self):
        from worldlab.qualitative import workspace_evidence
        payload = self.supplier_fixture(['a'*199 + '\r\n', 'ok', 'ok', 'ok', 'ok'])
        workspace = self.root / 'workspace'; (workspace / 'output').mkdir(parents=True)
        (workspace / supplier_notes.OUTPUT).write_bytes(payload['evidence']['files'][supplier_notes.OUTPUT]['text'].encode())
        payload['evidence']['files'][supplier_notes.OUTPUT] = workspace_evidence(workspace)[supplier_notes.OUTPUT]
        check = supplier_notes.check(payload)
        self.assertEqual(check['counts'][0]['characters'], 201)
        self.assertFalse(check['passed'])

    def test_registered_subcondition_does_not_apply_to_changed_source_or_rubric(self):
        payload = self.supplier_fixture(['a'*201]*5)
        for field in ['source', 'instruction', 'criterion']:
            value = deepcopy(payload)
            if field == 'source': value['evidence']['files']['input/source.md']['text'] += ' changed'
            if field == 'instruction': value['evidence']['instruction'] += ' changed'
            if field == 'criterion': value['criterion']['requirement'] += ' changed'
            self.assertIsNone(supplier_notes.check(value))
            self.assertEqual(supplier_notes.semantic_payload(value), value)

    def test_supplier_row_conjunction_cannot_hide_one_factual_error(self):
        payload = self.supplier_fixture(['grounded'] * 5)
        value = {'criterion_id': 'R7', 'rows': {f'K{i}': {'evidence': 'input/source.md',
            'reasoning': 'Supported by the supplied source.', 'language_correct': True,
            'facts_supported': True, 'justification_substantive': True} for i in range(1, 6)}}
        self.assertTrue(supplier_notes.parse_semantic(value, payload['evidence']['files'])['passed'])
        value['rows']['K1'].update(facts_supported=False, reasoning='The note calls a source Major finding Minor.')
        verdict = supplier_notes.parse_semantic(value, payload['evidence']['files'])
        self.assertFalse(verdict['passed']); self.assertIn('Major', verdict['reasoning'])
        self.assertEqual(len(verdict['row_checks']), 5)
        del value['rows']['K5']
        with self.assertRaisesRegex(ValueError, 'row judgments'):
            supplier_notes.parse_semantic(value, payload['evidence']['files'])

    def test_public_matrix_status_check_detects_omitted_original_rubric_condition(self):
        from types import SimpleNamespace
        payload = self.supplier_fixture(['grounded'] * 5)
        bank = SimpleNamespace(public=lambda task: {'instruction': payload['evidence']['instruction']})
        checked = supplier_notes.matrix_status_check(bank, 'fixture', payload['evidence']['files'])
        self.assertFalse(checked['passed'])  # The fixture sets all rows fulfilled.
        self.assertEqual(checked['failure_count'], 2)  # K1 and K3.
        body = payload['evidence']['files'][supplier_notes.OUTPUT]['text']
        body = body.replace('K1,Name,erfuellt', 'K1,Name,nicht_erfuellt').replace('K3,Name,erfuellt', 'K3,Name,teilweise_erfuellt')
        payload['evidence']['files'][supplier_notes.OUTPUT]['text'] = body
        self.assertTrue(supplier_notes.matrix_status_check(bank, 'fixture', payload['evidence']['files'])['passed'])

    def test_row_judgments_bind_physical_schema_and_saved_grade_audit(self):
        payload = self.supplier_fixture(['grounded'] * 5)
        bank = Bank(self.root / 'bank')
        bank.public = lambda task: {'id': task, 'source': 'internal_eurobench', 'input_formats': ['.md'],
                                    'instruction': payload['evidence']['instruction']}
        save(bank.root / 'private/rubric.json', {'criteria': [payload['criterion']]})
        bank.by_id['fixture']['rubric_sha256'] = sha(bank.root / 'private/rubric.json')
        workspace = self.root / 'workspace'; (workspace / 'input').mkdir(parents=True); (workspace / 'output').mkdir()
        for name, value in payload['evidence']['files'].items():
            (workspace / name).write_text(value['text'])
        value = {'criterion_id': 'R7', 'rows': {f'K{i}': {'evidence': 'input/source.md',
            'reasoning': 'Supported source facts.', 'language_correct': True, 'facts_supported': True,
            'justification_substantive': True} for i in range(1, 6)}}
        client = Client([response(text=json.dumps(value))]); out = self.root / 'judge'
        judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
        baseline = {'input/source.md': sha(workspace / 'input/source.md')}
        grade = judge.grade('fixture', workspace, baseline, out)
        self.assertTrue(grade['grading_complete']); self.assertTrue(grade['criteria'][0]['passed'])
        self.assertFalse(grade['success'], 'Public matrix-status errors still prevent a passing submission')
        judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)
        self.assertIn('rows', client.calls[0]['extra_body']['structured_outputs']['json']['properties'])
        grade['criteria'][0]['row_checks'][0]['facts_supported'] = False
        save(out / 'GRADE.json', grade)
        with self.assertRaisesRegex(ValueError, 'verdicts changed'):
            judge.audit_grade(bank, 'fixture', workspace, baseline, out, grade)


if __name__ == '__main__': unittest.main()
