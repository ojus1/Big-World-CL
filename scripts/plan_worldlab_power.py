"""Outcome-free sample-size sensitivity for independent workplace world pairs.

This planner makes no model calls and never reads execution outcomes. Its
paired-t calculation is a normal-theory planning model, not the power of the
existing exact sign-flip diagnostic and not a selected confirmatory design.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy
import scipy
from scipy.stats import nct, t


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value < 1


def validate(config):
    require(set(config) == {'schema_version', 'unit', 'primary', 'alpha', 'target_power',
            'max_world_pairs', 'minimum_effects', 'paired_difference_standard_deviations',
            'assumption_source'}, 'Expected only the documented outcome-free scenario fields')
    require(type(config['schema_version']) is int and config['schema_version'] == 1
            and config['unit'] == 'world_pair'
            and config['primary'] == 'probe_accepted_on_time_fraction', 'Unsupported planning contract')
    require(probability(config['alpha']) and probability(config['target_power'])
            and config['target_power'] > config['alpha'], 'Invalid alpha or target power')
    require(type(config['max_world_pairs']) is int and config['max_world_pairs'] >= 2,
            'Maximum sample size must be an integer count of at least two world pairs')
    for key in ('minimum_effects', 'paired_difference_standard_deviations'):
        values = config[key]
        require(isinstance(values, list) and values and all(probability(v) for v in values)
                and len(values) == len(set(values)), 'Expected distinct positive fractions below one: ' + key)
    require(isinstance(config['assumption_source'], str) and config['assumption_source'].strip(),
            'Record where the planning assumptions came from')
    # A bounded difference D in [-1,1] cannot have Var(D) > 1-E(D)^2.
    require(all(sd * sd + effect * effect <= 1 for effect in config['minimum_effects']
                for sd in config['paired_difference_standard_deviations']),
            'Mean and SD are incompatible with bounded world differences')


def paired_t_power(n, effect, sd, alpha):
    require(type(n) is int and n >= 2 and probability(effect) and probability(sd)
            and probability(alpha), 'Invalid paired-t planning inputs')
    critical = float(t.isf(alpha / 2, n - 1))
    noncentrality = math.sqrt(n) * effect / sd
    positive = float(nct.sf(critical, n - 1, noncentrality))
    # Reflection gives the same lower tail and avoids SciPy's cancellation
    # path for cdf(negative threshold, large positive noncentrality).
    negative = float(nct.sf(critical, n - 1, -noncentrality))
    require(all(math.isfinite(v) and 0 <= v <= 1 for v in (positive, negative)),
            'Numerical power calculation failed; no sample size is substituted')
    return {'positive_rejection_probability': positive,
            'negative_rejection_probability': negative,
            'two_sided_rejection_probability': min(1., positive + negative)}


def first_sufficient(evaluate, target, maximum):
    """Smallest integer meeting a monotone power function within the given bound."""
    if evaluate(maximum) < target:
        return None
    low, high = 2, maximum
    while low < high:
        midpoint = (low + high) // 2
        if evaluate(midpoint) >= target:
            high = midpoint
        else:
            low = midpoint + 1
    require(evaluate(low) >= target and (low == 2 or evaluate(low - 1) < target),
            'Sample-size threshold failed adjacent integer verification')
    return low


def hoeffding_positive_ci_power_bound(n, effect, alpha):
    """Lower bound for P(two-sided bounded-mean CI has lower endpoint > 0).

    For independent D_i in [-1,1] with average expectation >= effect,
    r=sqrt(2 log(2/alpha)/n) and P(mean <= r) <= exp(-n(effect-r)^2/2)
    whenever effect > r. This needs no assumed variance or normality.
    """
    require(type(n) is int and n >= 2 and probability(effect) and probability(alpha),
            'Invalid bounded-mean planning inputs')
    radius = math.sqrt(2 * math.log(2 / alpha) / n)
    return 0. if effect <= radius else -math.expm1(-n * (effect - radius) ** 2 / 2)


def scenarios(config):
    validate(config)
    alpha, target, maximum = config['alpha'], config['target_power'], config['max_world_pairs']
    rows = []
    for effect in config['minimum_effects']:
        bound = lambda n: hoeffding_positive_ci_power_bound(n, effect, alpha)
        sufficient = first_sufficient(bound, target, maximum)
        bounded = {'sufficient_world_pairs': sufficient,
                   'power_lower_bound_at_sufficient_n': bound(sufficient) if sufficient else None,
                   'power_lower_bound_at_previous_n': bound(sufficient - 1) if sufficient and sufficient > 2 else None,
                   'target_attained_within_planning_limit': sufficient is not None,
                   'power_lower_bound_at_planning_limit': bound(maximum)}
        for sd in config['paired_difference_standard_deviations']:
            power = lambda n: paired_t_power(n, effect, sd, alpha)['positive_rejection_probability']
            n = first_sufficient(power, target, maximum)
            rows.append({'minimum_effect': effect, 'paired_difference_standard_deviation': sd,
                         'standardized_effect': effect / sd,
                         'paired_t_normal_theory': {
                             'minimum_world_pairs': n,
                             'power_at_minimum_n': paired_t_power(n, effect, sd, alpha) if n else None,
                             'positive_power_at_previous_n': power(n - 1) if n and n > 2 else None,
                             'target_attained_within_planning_limit': n is not None,
                             'positive_power_at_planning_limit': power(maximum)},
                         'hoeffding_positive_ci': bounded})
    return rows


def plan(config_path, out):
    config_path, out = Path(config_path).resolve(), Path(out).resolve()
    require(not out.exists(), 'Use a fresh planning directory')
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    rows = scenarios(config)
    contract = {
        'schema_version': 1, 'kind': 'outcome_free_world_pair_power_sensitivity',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'configuration_sha256': hashlib.sha256(config_bytes).hexdigest(),
        'planner_sha256': digest(__file__),
        'runtime': {'python': platform.python_version(), 'numpy': numpy.__version__, 'scipy': scipy.__version__},
        'unit': 'independent world pair', 'primary': config['primary'],
        'effect': 'Absolute learner-minus-control difference in planned probe on-time acceptance fraction',
        'useful_effect_interpretation': 'Power to detect a positive effect against zero when the true mean equals minimum_effect; not power to prove the effect exceeds minimum_effect',
        'paired_t': 'Two-sided alpha critical value, df=n-1, noncentrality=sqrt(n)*effect/SD. Sample size targets positive-direction rejection only.',
        'paired_t_assumptions': 'Independent identically distributed normal world differences. Bounded workplace differences are not exactly normal; this is a sensitivity model requiring validation before any final design.',
        'bounded_mean': 'Power lower bound for a positive lower endpoint of the two-sided Hoeffding interval for independent differences bounded in [-1,1]. No normality or variance assumption.',
        'scope': 'Conditional on the eventual world population, task bank, harness, learner and evaluator. Repeated sessions, employees, task translations and grading criteria do not add independent pairs.',
        'limitations': 'Does not compute power of the frozen sign-flip diagnostic, estimate variance from outcomes, select a final method or N, certify world independence, qualify scoring, or dispatch a study. A changed final bank or protocol can change variability.',
        'references': [
            'https://www.statsmodels.org/stable/generated/statsmodels.stats.power.TTestPower.power.html',
            'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html',
            'https://doi.org/10.1080/01621459.1963.10500830'],
        'model_calls': 0, 'execution_outcomes_read': False,
        'final_sample_size_selected': False, 'confirmatory_readiness_established': False}
    out.mkdir(parents=True)
    (out / 'CONFIG.json').write_bytes(config_bytes)
    (out / 'REPRODUCE.py').write_bytes(Path(__file__).read_bytes())
    write_new(out / 'PLAN.json', contract)
    write_new(out / 'REPORT.json', {'plan_sha256': digest(out / 'PLAN.json'), 'scenarios': rows,
                                  'final_sample_size_selected': False})
    write_new(out / 'MANIFEST.json', {name: digest(out / name) for name in
              ('CONFIG.json', 'REPRODUCE.py', 'PLAN.json', 'REPORT.json')})
    return {'out': str(out), 'scenarios': len(rows), 'report_sha256': digest(out / 'REPORT.json'),
            'model_calls': 0, 'execution_outcomes_read': False, 'final_sample_size_selected': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(plan(args.config, args.out), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
