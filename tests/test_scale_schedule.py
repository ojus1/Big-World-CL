"""Offline calendar contract for prospective post-reversal learning."""
import unittest

from lifespan.evaluation.protocol import ExperimentConfig, scenario
from scripts.run_scale import study_config


class LearningCalendarTests(unittest.TestCase):
    def test_actual_last_epoch_observes_reversal_feedback_and_has_future_work(self):
        for seed in (211, 307, 401):
            cfg = study_config(seed, 'skillopt')
            spec = scenario(cfg)
            self.assertEqual(cfg.update_days, (3, 7, 11, 17))
            self.assertGreaterEqual(cfg.update_days[-1] - cfg.feedback_delay, spec['reversal_day'])
            self.assertGreaterEqual(cfg.days - cfg.update_days[-1] - 1, 2)

    def test_calendar_roundtrips_json_form_without_mutable_input_alias(self):
        days = [3, 7, 11, 17]
        cfg = ExperimentConfig(days=20, update_days=days)
        days.append(18)
        self.assertEqual(cfg.update_days, (3, 7, 11, 17))
        self.assertEqual(ExperimentConfig(**cfg.public()), cfg)
        self.assertEqual(cfg.public()['update_days'], [3, 7, 11, 17])

    def test_invalid_or_final_day_calendar_rejected(self):
        for days in ([], [True], [7, 3], [3, 3], [-1], [19], [20], '3,7'):
            with self.subTest(days=days), self.assertRaises(ValueError):
                ExperimentConfig(days=20, update_days=days)


if __name__ == '__main__':
    unittest.main()
