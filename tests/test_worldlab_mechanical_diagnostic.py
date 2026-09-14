import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.source_world_calibration import read, save, sha
from worldlab.mechanical_diagnostic import diagnose, audit, inspect_slot, snapshot


class Bank:
    verification = {'manifest_sha256': 'fixture-bank'}
    by_id = {'task': {'public_directory': 'public/task', 'calibration_group': 'one-family'}}
    inventory = {'public/task/input/source.md': {'sha256': hashlib.sha256(b'source').hexdigest()}}
    def public(self, task_id): return {'instruction': 'Deliver the requested table.'}
    def private_definition(self, task_id): return {'id': task_id}


class Grader:
    def identity(self): return {'name': 'fixture-mechanical'}
    def unsupported(self, definition): return []
    def grade(self, definition, workspace, baseline):
        passed = (workspace / 'output/table.csv').read_text() == 'valid'
        return {'grading_complete': True, 'mechanical_success': passed,
                'checks': [{'id': 'table-structure', 'pass': passed}]}


def attempt(root, qualitative, content):
    workspace = root / 'employee/workspace'
    (workspace / 'input').mkdir(parents=True)
    (workspace / 'output').mkdir()
    (workspace / 'input/source.md').write_text('source')
    (workspace / '.employee_identity').write_text('employee\n')
    (workspace / 'output/table.csv').write_text(content)
    save(root / 'PUBLIC_REQUEST.json', {'employee_id': 'employee', 'instruction': Bank().public('task')['instruction']})
    save(root / 'BASELINE.json', {name: sha(workspace / name) for name in ['input/source.md', '.employee_identity']})
    record = {'task_id': 'task', 'employee_id': 'employee', 'status': 'completed',
              'grade': {'grading_complete': True, 'success': qualitative},
              'artifact_inventory': {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}}
    save(root / 'ATTEMPT.json', record)


class Tests(unittest.TestCase):
    def test_disagreement_is_reported_without_rewriting_historical_grades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt(root / 'sources/a', True, 'invalid')
            attempt(root / 'sources/b', False, 'valid')
            before = {str(p): sha(p) for p in (root / 'sources').rglob('*') if p.is_file()}
            report = diagnose(Bank(), Grader(), [root / 'sources'], root / 'diagnostic')
            self.assertEqual(report['agreement_table']['qualitative_True_mechanical_False'], 1)
            self.assertEqual(report['agreement_table']['qualitative_False_mechanical_True'], 1)
            self.assertEqual(report['distinct_lineage_groups'], 1)
            self.assertEqual(report['model_calls'], 0)
            self.assertEqual(audit(Bank(), Grader(), root / 'diagnostic')['attempts_regraded'], 2)
            self.assertEqual(before, {str(p): sha(p) for p in (root / 'sources').rglob('*') if p.is_file()})

    def test_tampering_and_mutating_grader_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); attempt(root / 'source', True, 'valid')
            slot = snapshot(Bank(), [root / 'source'])[0]
            target = root / 'source/employee/workspace/output/table.csv'
            target.write_text('changed')
            with self.assertRaises(ValueError): inspect_slot(Bank(), Grader(), slot)
            target.write_text('valid')
            class Mutator(Grader):
                def grade(self, definition, workspace, baseline):
                    result = super().grade(definition, workspace, baseline)
                    (workspace / 'output/table.csv').write_text('mutated')
                    return result
            with self.assertRaises(ValueError): inspect_slot(Bank(), Mutator(), slot)

    def test_diagnostic_cannot_pollute_source_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); attempt(root / 'source', True, 'valid')
            with self.assertRaises(ValueError): diagnose(Bank(), Grader(), [root / 'source'], root / 'source/new')


if __name__ == '__main__': unittest.main()
