from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import csv
import io
import hashlib

from scripts.source_world_calibration import read, save
from worldlab.source_coverage import rubric
from worldlab import source_coverage
from worldlab.qualitative import FrozenRubricJudge
from test_worldlab_judge_recovery import Bank, Client, response


class CoverageTests(unittest.TestCase):
    def test_existing_r3_correction_is_exactly_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bank = Bank(root / 'bank'); bank.private_definition = lambda _: {'rubric': []}
            original = rubric(bank, 'fixture')['criteria'][0]
            registry = root / 'registry.json'
            save(registry, {'tasks': {'fixture': {
                'definition_sha256': bank.by_id['fixture'].get('definition_sha256'),
                'instruction_sha256': hashlib.sha256(bank.public('fixture')['instruction'].encode()).hexdigest(),
                'corrections': {original['id']: {'original_requirement': original['requirement'],
                                                 'requirement': 'Reviewed public source requirement.'}}}}})
            with patch.object(source_coverage, 'REGISTRY', registry):
                result = rubric(bank, 'fixture')
                self.assertEqual(result['criteria'][0]['requirement'], 'Reviewed public source requirement.')
                self.assertEqual(result['criteria'][0]['weight'], original['weight'])
                self.assertEqual(result['source_coverage']['restored_ids'], [])

    def test_mixed_length_veto_does_not_automatically_pass_semantics(self):
        from worldlab.qualitative import request_verdict, verdict_input
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / 'registry.json'
            criterion = {'id': 'R7', 'requirement': '800 characters and correct French.', 'weight': 1}
            rule = {'instruction_sha256': hashlib.sha256(b'Notes').hexdigest(), 'input_text_sha256': {},
                'counts': {'R7': {'criterion': criterion, 'minimum': 800, 'maximum': None, 'unit': 'characters',
                                  'mode': 'veto', 'path': 'output/notes.md', 'exclude_title': False}}}
            save(registry, {'tasks': {'fixture': rule}})
            with patch.object(source_coverage, 'REGISTRY', registry):
                payload = {'criterion': criterion, 'evidence': {'instruction': 'Notes',
                    'files': {'output/notes.md': {'text': 'é' * 799}}}}
                self.assertFalse(source_coverage.count_verdict(payload)['passed'])
                self.assertEqual(request_verdict(None, None, payload, 1).evaluation_method, 'registered_source_character_count')
                payload['evidence']['files']['output/notes.md']['text'] += 'é'
                self.assertIsNone(source_coverage.count_verdict(payload))
                self.assertTrue(source_coverage.count_measure(payload)['passed'])
                self.assertIn('Do not estimate or recount', verdict_input(payload)[1]['content'])
                payload['evidence']['files']['output/notes.md']['text'] += 'é' * 3000
                self.assertTrue(source_coverage.count_measure(payload)['passed'])

    def test_reviewed_translation_is_applied_only_to_bound_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bank = Bank(root / 'bank')
            original = {'id': 'R8', 'verification': 'mechanical', 'weight': 1,
                        'requirement': 'German recommendation Ablehnung.'}
            bank.private_definition = lambda _: {'rubric': [original]}
            correction = {'original_requirement': original['requirement'],
                          'requirement': 'English recommendation Rejection.'}
            registry = root / 'registry.json'
            save(registry, {'tasks': {'fixture': {
                'definition_sha256': bank.by_id['fixture'].get('definition_sha256'),
                'instruction_sha256': hashlib.sha256(bank.public('fixture')['instruction'].encode()).hexdigest(),
                'corrections': {'R8': correction}}}})
            with patch.object(source_coverage, 'REGISTRY', registry):
                value = rubric(bank, 'fixture')
                self.assertEqual(value['criteria'][-1]['requirement'], correction['requirement'])
                self.assertEqual(value['source_coverage']['corrected_ids'], ['R8'])
                original['requirement'] += ' Changed.'
                with self.assertRaisesRegex(ValueError, 'reviewed original'):
                    rubric(bank, 'fixture')
                bank.by_id['fixture']['definition_sha256'] = 'changed'
                with self.assertRaisesRegex(ValueError, 'requalification'):
                    rubric(bank, 'fixture')

    def test_report_count_boundaries_and_source_binding_without_inference(self):
        from worldlab.qualitative import request_verdict
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / 'registry.json'
            criterion = {'id': 'report_word_count', 'requirement': '1200–1800 words.', 'weight': 1}
            rule = {'instruction_sha256': hashlib.sha256(b'Report').hexdigest(),
                    'input_text_sha256': {'input/source.md': hashlib.sha256(b'Source\n').hexdigest()},
                    'counts': {'report_word_count': {'criterion': criterion, 'minimum': 1200,
                        'maximum': 1800, 'path': 'output/report.md', 'exclude_title': False}}}
            save(registry, {'tasks': {'fixture': rule}})
            with patch.object(source_coverage, 'REGISTRY', registry):
                for count, expected in [(1199, False), (1200, True), (1800, True), (1801, False)]:
                    payload = {'criterion': criterion, 'evidence': {'instruction': 'Report', 'files': {
                        'input/source.md': {'text': 'Source\r\n'},
                        'output/report.md': {'text': '中文 l’école quarante-huit : ; ' + ' '.join(['word'] * (count - 3))}}}}
                    self.assertEqual(source_coverage.count_verdict(payload)['passed'], expected)
                    result = request_verdict(None, None, payload, 1)
                    self.assertEqual(result.evaluation_method, 'registered_source_report_word_count')
                for field in ['source', 'instruction', 'criterion']:
                    changed = deepcopy(payload)
                    if field == 'source': changed['evidence']['files']['input/source.md']['text'] += '!'
                    if field == 'instruction': changed['evidence']['instruction'] += '!'
                    if field == 'criterion': changed['criterion']['weight'] = 2
                    self.assertIsNone(source_coverage.count_verdict(changed))

    def test_supplier_predicates_bind_each_language_and_detect_status_mutation(self):
        from worldlab import supplier_notes
        rules = read(supplier_notes.REGISTRY)
        for rule in rules:
            # Distinct instruction hashes disambiguate identical R1-R5 rubrics.
            text = rule['task_id']; sources = {'input/source.md': {'text': 'Source'}}
            variant = deepcopy(rule); variant['instruction_sha256'] = hashlib.sha256(text.encode()).hexdigest()
            variant['source_sha256'] = {'input/source.md': hashlib.sha256(b'Source').hexdigest()}
            all_rules = [r if r['task_id'] != rule['task_id'] else variant for r in rules]
            stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(supplier_notes.COLUMNS)
            for i, status in enumerate(['nicht_erfuellt', 'erfuellt', 'teilweise_erfuellt', 'erfuellt', 'erfuellt'], 1):
                writer.writerow([f'K{i}', 'Translated label', status, 'Source', 'Note'])
            sources[supplier_notes.OUTPUT] = {'text': stream.getvalue()}
            with patch.object(supplier_notes.json, 'loads', return_value=all_rules):
                for criterion in variant['matrix_criteria']:
                    payload = {'criterion': criterion, 'evidence': {'instruction': text, 'files': sources}}
                    self.assertTrue(supplier_notes.source_matrix_verdict(payload)['passed'])
                sources[supplier_notes.OUTPUT]['text'] = stream.getvalue().replace('nicht_erfuellt', 'erfuellt')
                payload['criterion'] = next(c for c in variant['matrix_criteria'] if c['id'] == 'R2')
                self.assertFalse(supplier_notes.source_matrix_verdict(payload)['passed'])

    def test_missing_obligations_are_scored_audited_and_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bank = Bank(root / 'bank')
            definition = {'checks': [], 'rubric': [
                {'id': 'q', 'verification': 'mechanical', 'weight': 99, 'requirement': 'Already represented.'},
                {'id': 'missing_math', 'verification': 'mechanical', 'weight': 3, 'requirement': 'The arithmetic is correct.'}]}
            bank.private_definition = lambda _: deepcopy(definition)
            merged = rubric(bank, 'fixture')
            self.assertEqual([c['id'] for c in merged['criteria']], ['q', 'missing_math'])
            self.assertEqual(merged['criteria'][0]['weight'], 1)
            workspace = root / 'workspace'; (workspace / 'output').mkdir(parents=True)
            (workspace / 'output/result.md').write_text('Wrong arithmetic.')
            bad = response(False); bad.output_text = bad.output_text.replace('"q"', '"missing_math"')
            client = Client([response(True), bad])
            judge = FrozenRubricJudge(bank, 'fixture', client.base_url, client_factory=lambda: client)
            self.assertEqual(judge.max_model_calls_for('fixture'), 3)
            out = root / 'judging'; grade = judge.grade('fixture', workspace, {}, out)
            self.assertFalse(grade['success']); self.assertEqual(grade['quality_score'], .25)
            self.assertEqual(grade['usage']['physical_model_calls'], 2)
            self.assertEqual(grade['source_coverage']['restored_ids'], ['missing_math'])
            judge.audit_grade(bank, 'fixture', workspace, {}, out, grade)
            definition['rubric'][1]['requirement'] = 'Changed source obligation.'
            with self.assertRaisesRegex(ValueError, 'coverage changed'):
                judge.audit_grade(bank, 'fixture', workspace, {}, out, grade)


if __name__ == '__main__': unittest.main()
