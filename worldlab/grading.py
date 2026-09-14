"""Evaluator-owned adapters. Mechanical diagnostics and full quality are distinct."""
import sys
from pathlib import Path
from scripts.source_world_calibration import sha


class EuroBenchMechanical:
    def __init__(self, package_root):
        self.root = Path(package_root).resolve()
        sys.path.insert(0, str(self.root))
        from eurobench import core
        if Path(core.__file__).resolve() != self.root / 'eurobench/core.py':
            raise ValueError('Unexpected EuroBench grading source')
        self.evaluate = core.evaluate

    def identity(self):
        return {'name': 'original_eurobench_mechanical', 'source_sha256': {
            str(p.relative_to(self.root)): sha(p) for p in sorted((self.root / 'eurobench').glob('*.py'))}}

    def unsupported(self, definition):
        kinds = {x['kind'] for x in definition['checks']}
        return sorted(kinds & {'python_cases', 'app_records'})

    def grade(self, definition, workspace, baseline):
        if self.unsupported(definition):
            raise ValueError('Private executable/app grader is not qualified in this adapter')
        value = self.evaluate(definition, workspace, baseline)
        return {**value, 'quality_score': None, 'quality_judging': 'not_executed',
                'learning_claim_eligible': False,
                'scope': 'Original mechanical checks only. Frozen qualitative rubric remains required for full quality.'}
