"""Check independent power constructions, planning boundaries and saved inputs."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
    from scipy.integrate import quad
    from scipy.stats import chi2, norm, t
except ModuleNotFoundError:
    np = None

MODULE = Path(__file__).resolve().parents[1] / 'scripts/plan_worldlab_power.py'
CONFIG = MODULE.parents[1] / 'configs/worldlab/power_scenarios_v1.json'
if np is not None:
    spec = importlib.util.spec_from_file_location('plan_worldlab_power', MODULE)
    power = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(power)


@unittest.skipIf(np is None, 'Install optional requirements-worldlab-planning.txt')
class Tests(unittest.TestCase):
    def config(self):
        return json.loads(CONFIG.read_text())

    def test_noncentral_t_matches_independent_chi_square_mixture_integral(self):
        for n, effect, sd in [(8, .025, .1), (34, .05, .1), (12, .1, .2)]:
            df, noncentrality = n - 1, math.sqrt(n) * effect / sd
            critical = t.isf(.025, df)
            positive = quad(lambda v: norm.sf(critical * math.sqrt(v / df) - noncentrality)
                            * chi2.pdf(v, df), 0, math.inf, epsabs=1e-10)[0]
            negative = quad(lambda v: norm.cdf(-critical * math.sqrt(v / df) - noncentrality)
                            * chi2.pdf(v, df), 0, math.inf, epsabs=1e-10)[0]
            actual = power.paired_t_power(n, effect, sd, .05)
            self.assertAlmostEqual(actual['positive_rejection_probability'], positive, places=8)
            self.assertAlmostEqual(actual['negative_rejection_probability'], negative, places=8)
            self.assertAlmostEqual(actual['two_sided_rejection_probability'], positive + negative, places=8)

    def test_planned_threshold_has_monte_carlo_power_under_declared_normal_model(self):
        # Independently construct entire samples and their sample-SD t statistics.
        config = self.config()
        config['minimum_effects'], config['paired_difference_standard_deviations'] = [.05], [.1]
        row = power.scenarios(config)[0]['paired_t_normal_theory']
        self.assertEqual(row['minimum_world_pairs'], 34)
        draws = np.random.default_rng(87123).normal(.05, .1, size=(50_000, 34))
        statistic = draws.mean(axis=1) / (draws.std(axis=1, ddof=1) / math.sqrt(34))
        measured = float((statistic > t.isf(.025, 33)).mean())
        self.assertLess(abs(measured - row['power_at_minimum_n']['positive_rejection_probability']), .008)
        self.assertLess(row['positive_power_at_previous_n'], .8)
        self.assertGreaterEqual(row['power_at_minimum_n']['positive_rejection_probability'], .8)

    def test_direction_and_unit_are_not_inflated(self):
        got = power.paired_t_power(6, 1e-9, .2, .05)
        self.assertAlmostEqual(got['positive_rejection_probability'], .025, places=7)
        self.assertAlmostEqual(got['two_sided_rejection_probability'], .05, places=7)
        config = self.config()
        for field, value in [('unit', 'employee'), ('unit', 'session'), ('primary', 'rubric_pass_fraction')]:
            invalid = dict(config, **{field: value})
            with self.assertRaises(ValueError): power.scenarios(invalid)
        with self.assertRaises(ValueError): power.scenarios(dict(config, observed_differences=[.1] * 20))

    def test_large_noncentrality_uses_finite_reflected_tail(self):
        # The direct nct.cdf lower-tail path returned NaN for these inputs.
        for n in [626, 5001]:
            got = power.paired_t_power(n, .05, .1, .05)
            self.assertTrue(all(math.isfinite(v) and 0 <= v <= 1 for v in got.values()))
            self.assertGreater(got['positive_rejection_probability'], .999)

    def test_sensitivity_and_unsatisfied_limits_are_explicit(self):
        rows = power.scenarios(self.config())
        sizes = {(r['minimum_effect'], r['paired_difference_standard_deviation']):
                 r['paired_t_normal_theory']['minimum_world_pairs'] for r in rows}
        self.assertGreater(sizes[.025, .1], sizes[.05, .1])
        self.assertGreater(sizes[.05, .2], sizes[.05, .1])
        small = self.config()
        small['max_world_pairs'] = 6
        for row in power.scenarios(small):
            value = row['paired_t_normal_theory']
            if value['minimum_world_pairs'] is None:
                self.assertFalse(value['target_attained_within_planning_limit'])
                self.assertLess(value['positive_power_at_planning_limit'], .8)
        self.assertIsNone(power.first_sufficient(lambda n: .2, .8, 50))
        self.assertEqual(power.first_sufficient(lambda n: .9, .8, 50), 2)

    def test_hoeffding_power_bound_matches_closed_form_sample_size(self):
        for effect in [.025, .05, .1]:
            alpha, target = .05, .8
            closed = math.ceil(2 * (math.sqrt(math.log(2 / alpha)) +
                                   math.sqrt(math.log(1 / (1 - target)))) ** 2 / effect ** 2)
            actual = power.first_sufficient(
                lambda n: power.hoeffding_positive_ci_power_bound(n, effect, alpha), target, 100_000)
            self.assertEqual(actual, closed)
            self.assertGreaterEqual(power.hoeffding_positive_ci_power_bound(actual, effect, alpha), target)
            self.assertLess(power.hoeffding_positive_ci_power_bound(actual - 1, effect, alpha), target)
        self.assertEqual(power.hoeffding_positive_ci_power_bound(6, .1, .05), 0)

    def test_rejects_invalid_assumptions_without_creating_artifacts(self):
        for key, value in [('alpha', True), ('target_power', 1), ('max_world_pairs', 6.0),
                           ('minimum_effects', [float('nan')]), ('minimum_effects', [.1, .1]),
                           ('paired_difference_standard_deviations', [0]),
                           ('assumption_source', ''), ('schema_version', True)]:
            with self.subTest(key=key, value=value):
                config = dict(self.config(), **{key: value})
                with self.assertRaises(ValueError): power.scenarios(config)
        invalid = dict(self.config(), minimum_effects=[.9], paired_difference_standard_deviations=[.9])
        with tempfile.TemporaryDirectory() as tmp:
            config, out = Path(tmp) / 'config.json', Path(tmp) / 'out'
            config.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, 'incompatible'): power.plan(config, out)
            self.assertFalse(out.exists())

    def test_saved_report_binds_exact_configuration_source_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            result = power.plan(CONFIG, out)
            self.assertEqual(result['scenarios'], 9)
            self.assertEqual(result['model_calls'], 0)
            self.assertFalse(result['execution_outcomes_read'])
            self.assertFalse(result['final_sample_size_selected'])
            saved = power.read(out / 'PLAN.json')
            self.assertEqual(saved['runtime']['numpy'], np.__version__)
            self.assertEqual((out / 'CONFIG.json').read_bytes(), CONFIG.read_bytes())
            self.assertEqual((out / 'REPRODUCE.py').read_bytes(), MODULE.read_bytes())
            before = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                      for name in power.read(out / 'MANIFEST.json')}
            self.assertEqual(before, power.read(out / 'MANIFEST.json'))
            self.assertEqual(saved['configuration_sha256'], before['CONFIG.json'])
            self.assertEqual(saved['planner_sha256'], before['REPRODUCE.py'])
            self.assertEqual(power.read(out / 'REPORT.json')['plan_sha256'], before['PLAN.json'])
            with self.assertRaisesRegex(ValueError, 'fresh'): power.plan(CONFIG, out)
            self.assertEqual(before, {name: power.digest(out / name) for name in before})


if __name__ == '__main__':
    unittest.main()
