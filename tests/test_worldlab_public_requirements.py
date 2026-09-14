from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.source_world_calibration import save
from worldlab import public_requirements as checks
from worldlab.bank import Bank
from worldlab.qualify_public_requirements import controls, qualify
from worldlab.qualitative import FrozenRubricJudge

BANK = Path(__file__).resolve().parents[2] / 'Big-World-CL/lifespan/artifacts/final-world-calibration-v1'


class BindingTests(unittest.TestCase):
    def test_modified_public_contract_or_source_cannot_reuse_registered_predicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'public').mkdir()
            task = root / 'public/task.json'; task.write_text('{}')
            source = root / 'public/input.csv'; source.write_text('original')
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            registry = root / 'registry.json'
            save(registry, {'tasks': {'task': {'checker': 'editorial_calendar_v1',
                'public_descriptor_sha256': digest(task), 'input_sha256': {'input.csv': digest(source)}}}})
            bank = SimpleNamespace(root=root, by_id={'task': {'public_directory': 'public'}})
            with patch.object(checks, 'REGISTRY', registry):
                task.write_text('{"changed":true}')
                with self.assertRaisesRegex(ValueError, 'contract changed'): checks.evaluate(bank, 'task', {})
                task.write_text('{}'); source.write_text('changed')
                with self.assertRaisesRegex(ValueError, 'input changed'): checks.evaluate(bank, 'task', {})


@unittest.skipUnless(BANK.is_dir(), 'Frozen source bank required for component integration')
class SourceIntegrationTests(unittest.TestCase):
    def test_all_source_grounded_controls_and_fixed_denominators(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = qualify(Bank(BANK), Path(tmp) / 'qualification')
            self.assertTrue(result['ok']); self.assertEqual(result['cases'], 16)

    def test_public_numeric_failure_prevents_perfect_grade_despite_all_semantic_passes(self):
        bank = Bank(BANK)
        case = next(c for c in controls(bank) if c['id'] == 'negative-mri-report-total')
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            criterion = json.loads(kwargs['input'][1]['content'])['criterion']
            return SimpleNamespace(status='completed', output_text=json.dumps({
                'criterion_id': criterion['id'], 'evidence': 'Synthetic passing semantic response.',
                'reasoning': 'Fixture only; does not evaluate quality.', 'passed': True}),
                usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))
        client = SimpleNamespace(base_url='http://127.0.0.1:8000/v1', max_retries=0,
                                 responses=SimpleNamespace(create=create), close=lambda: None)
        judge = FrozenRubricJudge(bank, 'fixture', str(client.base_url), client_factory=lambda: client)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); workspace = root / 'workspace'; baseline = bank.stage(case['task_id'], workspace)
            for name, text in case['outputs'].items():
                path = workspace / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
            result = judge.grade(case['task_id'], workspace, baseline, root / 'judging')
            self.assertTrue(result['grading_complete'])
            self.assertTrue(all(v['passed'] for v in result['criteria']))
            self.assertFalse(result['success']); self.assertLess(result['quality_score'], 1)
            self.assertEqual(len(calls), len(result['criteria']))
            self.assertEqual(result['usage']['charged_tokens'], 15 * len(calls))
            self.assertEqual([c['id'] for c in result['public_requirements']['checks'] if not c['passed']],
                             ['public_mri_weighted_scores'])


if __name__ == '__main__': unittest.main()
