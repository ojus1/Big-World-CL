"""Full enlarged timeline with offline public-input oracle, not native evidence."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from lifespan.evaluation.runner import run_experiment
from lifespan.evaluation.protocol import select_experiences
from lifespan.tests.test_evaluation_runner import FakeActors, offline_dependencies, offline_executor, CREDS
from scripts.run_scale import study_config


class ScaledTimelineTests(unittest.TestCase):
    def test_twenty_day_population_demand_and_feedback_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            config = study_config(211, 'no_learning')
            with offline_dependencies():
                report = run_experiment(out, config, actor_factory=FakeActors,
                                        executor=offline_executor, creds=CREDS)
            cp = json.loads((out / 'checkpoint.json').read_text())
            state = cp['runner']
            corrected = json.loads((out / 'REPORT.v2.json').read_text())
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(len(state['skills']), 12)
            self.assertEqual(cp['ecosystem']['day'], 21)
            self.assertLessEqual(len(state['sessions']), 240)
            self.assertEqual(corrected['source_breakdown']['fixed_initial_and_benchmark']['accepted_before_work_horizon'], 240)
            self.assertTrue(corrected['correction_audit']['eligible_for_paired_inference'])
            logs = state['learning_eligibility']
            self.assertEqual(len(logs), 48)
            self.assertEqual(Counter(row['day'] for row in logs), {3: 12, 7: 12, 11: 12, 17: 12})
            for row in logs:
                pool = select_experiences(state['experiences'], row['employee'], row['day'], 100000, 100000)
                self.assertEqual(row['available_unique_train'], sum(e['split'] == 'train' for e in pool))
                self.assertEqual(row['available_unique_val'], sum(e['split'] == 'val' for e in pool))
                self.assertFalse(row['treatment_enabled'])
                if row['day'] == 3:
                    self.assertFalse(row['eligible'])
            self.assertEqual(state['updates'], [])
            for employee in state['skills']:
                regimes = {row['regime'] for row in state['sessions'] if row['employee'] == employee}
                self.assertEqual(regimes, {'base', 'changed', 'exception', 'reversal'})


if __name__ == '__main__':
    unittest.main()
