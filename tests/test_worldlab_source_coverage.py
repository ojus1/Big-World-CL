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
from worldlab.qualitative import FrozenRubricJudge
from test_worldlab_judge_recovery import Bank, Client, response


class CoverageTests(unittest.TestCase):
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
