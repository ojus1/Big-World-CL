"""Freeze and run a development analysis of complete, audited workplace pairs.

The plan is separate from the experiment checkout, so it can be frozen before
dispatch without editing its source or workload. No model calls are made.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_study(root):
    study = read(root / 'STUDY.json')
    require(digest(root / 'STUDY.json') == read(root / 'PREPARED.json')['study_sha256'],
            'Prepared study bytes changed')
    require(study.get('employee_driver') and study['analysis']['scope'] == 'development' and
            study['analysis']['primary'] == 'probe_accepted_on_time_fraction',
            'This analysis supports the declared development workplace primary metric')
    seeds = [w['seed'] for w in study['worlds']]
    require(seeds and all(type(s) is int for s in seeds) and len(seeds) == len(set(seeds)),
            'World seeds must be unique integers')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', study['learner']['name']) and
            study['learner']['name'] != 'no_learning', 'Invalid learner arm')
    return study


def prepare(study_root, out, frozen_source, python=sys.executable, harness_config=None, learner_config=None, judge_config=None):
    root, out, frozen_source = map(lambda p: Path(p).resolve(), (study_root, out, frozen_source))
    study = verified_study(root)
    require(not (root / 'EXECUTION.json').exists() and not (root / 'worlds').exists(),
            'Freeze this analysis before any study execution, including cancelled dispatch')
    require(not out.exists() and out != root and root not in out.parents,
            'Use a fresh analysis directory outside the study')
    sources = study['source_sha256']
    require(all(not Path(name).is_absolute() and '..' not in Path(name).parts and
                (frozen_source / name).is_file() and digest(frozen_source / name) == sha
                for name, sha in sources.items()), 'Frozen audit source differs from prepared study')
    config = Path(harness_config).resolve() if harness_config else None
    learner = Path(learner_config).resolve() if learner_config else None
    judge = Path(judge_config).resolve() if judge_config else None
    frozen_judge_factory = study.get('judge', {}).get('operator_factory')
    if frozen_judge_factory is not None:
        require(judge is not None and digest(judge) == frozen_judge_factory.get('configuration_sha256'),
                'Freeze the exact configured judge before study execution')
    else:
        require(judge is None, 'Judge configuration does not match the prepared built-in judge')
    plan = {'schema_version': 1, 'kind': 'prospective_development_workplace_analysis',
            'prepared_unix': time.time(), 'study_root': str(root),
            'study_sha256': digest(root / 'STUDY.json'),
            'seeds': [w['seed'] for w in study['worlds']], 'learner_arm': study['learner']['name'],
            'unit': 'world_pair', 'primary': 'probe_accepted_on_time_fraction',
            'effect': 'learner minus no_learning, equal weight per world pair',
            'denominator': 'all planned probe obligations, including deferred and unattempted work',
            'missing_pair_policy': 'No inference unless every planned pair completes and passes the frozen audit',
            'test': {'method': 'exact_two_sided_paired_sign_flip_of_mean',
                     'max_pairs': 20, 'alpha': 0.05,
                     'assumption': 'Independent world differences whose signs are exchangeable under the null; counterbalanced order alone does not establish this',
                     'interpretation': 'Exploratory sensitivity diagnostic; not a design-justified randomization test'},
            'interval': {'method': 'two_sided_Hoeffding_bounded_mean', 'level': 0.95,
                         'difference_bounds': [-1, 1],
                         'assumption': 'Independent world differences; conditional on the fixed source bank, simulator and grading contract',
                         'interpretation': 'Conservative concentration interval; may cover the full feasible range in small studies'},
            'confirmatory_significance_claim': False,
            'analysis_source_sha256': digest(__file__),
            'audit_source': str(frozen_source), 'audit_python': str(Path(python).resolve()),
            'harness_config': str(config) if config else None,
            'harness_config_sha256': digest(config) if config else None,
            'learner_config': str(learner) if learner else None,
            'learner_config_sha256': digest(learner) if learner else None,
            'judge_config': str(judge) if judge else None,
            'judge_config_sha256': digest(judge) if judge else None}
    require(len(plan['seeds']) <= plan['test']['max_pairs'],
            'This exact small-study analysis supports at most 20 pairs; choose another prospective protocol for larger studies')
    out.mkdir(parents=True)
    write_new(out / 'PLAN.json', plan)
    write_new(out / 'PREPARED.json', {'plan_sha256': digest(out / 'PLAN.json')})
    with (out / 'REPRODUCE.py').open('xb') as stream:
        stream.write(Path(__file__).read_bytes())
    return {'status': 'prepared', 'plan_sha256': digest(out / 'PLAN.json'), 'world_pairs': len(plan['seeds']),
            'model_calls': 0, 'confirmatory_significance_claim': False}


def paired_statistics(differences):
    """Use exact rational arithmetic so ties in the permutation tail stay ties."""
    require(1 <= len(differences) <= 20 and all(isinstance(d, Fraction) and -1 <= d <= 1 for d in differences),
            'Expected 1 to 20 bounded rational world-pair differences')
    n = len(differences)
    total = sum(differences, Fraction())
    null = Counter({Fraction(): 1})
    for d in differences:
        next_null = Counter()
        for value, count in null.items():
            next_null[value + d] += count
            next_null[value - d] += count
        null = next_null
    extreme = sum(count for value, count in null.items() if abs(value) >= abs(total))
    permutations = 2 ** n
    mean = float(total / n)
    sd = statistics.stdev(float(d) for d in differences) if n > 1 else None
    # Hoeffding: P(|mean - E(mean)| >= e) <= 2 exp(-n e^2/2),
    # since each independent paired difference lies in [-1, 1].
    radius = math.sqrt(2 * math.log(2 / 0.05) / n)
    return {'world_pairs': n, 'mean_difference': mean,
            'world_difference_standard_deviation': sd,
            'standard_error_world_mean': sd / math.sqrt(n) if sd is not None else None,
            'positive_pairs': sum(d > 0 for d in differences),
            'zero_pairs': sum(d == 0 for d in differences), 'negative_pairs': sum(d < 0 for d in differences),
            'exact_sign_flip': {'two_sided_p': extreme / permutations,
                                'extreme_assignments': extreme, 'all_assignments': permutations},
            'hoeffding_95_interval': {'low': max(-1., mean - radius), 'high': min(1., mean + radius),
                                      'unclipped_radius': radius}}


def observations(root, study):
    """Only arm reports validated by the frozen auditor may reach this function."""
    rows, differences = [], []
    learning = Counter({key: 0 for key in ('updates', 'adoptions', 'nontrivial_adoptions',
        'optimizer_physical_calls_reported', 'optimizer_operations_with_unknown_calls',
        'later_sessions_with_adopted_skill')})
    for world in study['worlds']:
        planned = sum(s['split'] == 'probe' for s in world['schedule'])
        require(planned > 0, 'No planned probe obligations')
        row = {'seed': world['seed'], 'planned_probes_per_arm': planned}
        scores = []
        for name in ('no_learning', study['learner']['name']):
            arm = root / 'worlds' / f'seed-{world["seed"]}' / name
            report, state = read(arm / 'REPORT.json'), read(arm / 'STATE.json')
            require(report['status'] == 'completed' and not (arm / 'INFLIGHT.json').exists(), 'Incomplete arm')
            workplace = report['workplace']
            numerator = workplace['probe_accepted_on_time']
            require(workplace['probe_obligations'] == planned and type(numerator) is int and 0 <= numerator <= planned,
                    'Probe denominator or accepted count changed')
            score = Fraction(numerator, planned)
            require(report['probe_accepted_on_time_fraction'] == float(score), 'Primary metric differs from counts')
            scores.append(score)
            row[name] = {'accepted_on_time': numerator, 'fraction': float(score),
                         'work_sessions': len(state['sessions']), 'adoptions': report['adoptions'],
                         'rework_attempts': workplace['rework_attempts'],
                         'work_and_judging_tokens': report['work_and_judging_tokens'],
                         'learning_and_replay_judging_tokens': report['learning_and_replay_judging_tokens'],
                         'actor_usage': report['actor_usage']}
            if name != 'no_learning':
                deployed = {}
                for update in state['updates']:
                    value = update['result']
                    learning['updates'] += 1
                    learning['adoptions'] += int(value['accepted'])
                    for operation in value['costs']['operations']:
                        if operation['kind'] == 'target':
                            continue
                        calls = operation.get('reported_usage', {}).get('model_calls')
                        if type(calls) is int and calls >= 0:
                            learning['optimizer_physical_calls_reported'] += calls
                        else:
                            learning['optimizer_operations_with_unknown_calls'] += 1
                    if value['accepted']:
                        prior = deployed.get(update['employee_id'], study['seed_skill'])
                        learning['nontrivial_adoptions'] += int(value['skill'] != prior)
                        deployed[update['employee_id']] = value['skill']
                for session in state['sessions']:
                    past = [u for u in state['updates'] if u['employee_id'] == session['employee_id'] and
                            u['day'] < session['day'] and u['result']['accepted']]
                    if past:
                        value = past[-1]['result']['skill']
                        learning['later_sessions_with_adopted_skill'] += int(value != study['seed_skill'] and
                            session['skill_content_sha256'] == hashlib.sha256(value.encode()).hexdigest())
        difference = scores[1] - scores[0]
        differences.append(difference)
        row['difference'] = float(difference)
        row['difference_exact'] = str(difference)
        rows.append(row)
    return rows, differences, dict(learning)


def analyze(out, bank):
    out, bank = Path(out).resolve(), Path(bank).resolve()
    plan = read(out / 'PLAN.json')
    require(digest(out / 'PLAN.json') == read(out / 'PREPARED.json')['plan_sha256'] and
            digest(__file__) == plan['analysis_source_sha256'], 'Analysis plan or source changed')
    require(not (out / 'REPORT.json').exists() and not (out / 'AUDIT.json').exists(), 'Analysis already recorded')
    root = Path(plan['study_root'])
    study = verified_study(root)
    require(digest(root / 'STUDY.json') == plan['study_sha256'] and
            [w['seed'] for w in study['worlds']] == plan['seeds'], 'Planned study changed')
    require(read(root / 'EXECUTION.json')['started_unix'] >= plan['prepared_unix'], 'Study started before analysis preparation')
    require(read(root / 'REPORT.json')['status'] == 'completed', 'Entire planned study must complete before analysis')
    command = [plan['audit_python'], '-m', 'worldlab.audit_worlds', '--bank', str(bank), '--out', str(root)]
    for kind in ('harness', 'learner', 'judge'):
        config = plan.get(kind + '_config')
        if config:
            require(digest(config) == plan[kind + '_config_sha256'], kind + ' configuration changed')
            command += ['--' + kind + '-config', config]
    before = {str(p.relative_to(root)): digest(p) for p in root.rglob('*.json') if p.is_file()}
    result = subprocess.run(command, cwd=plan['audit_source'], capture_output=True, text=True, timeout=3600, check=True)
    audit = json.loads(result.stdout)
    require(audit['ok'] is True and audit['world_pairs'] == len(plan['seeds']), 'Frozen audit did not accept all pairs')
    rows, differences, learning = observations(root, study)
    after = {str(p.relative_to(root)): digest(p) for p in root.rglob('*.json') if p.is_file()}
    require(before == after, 'Study evidence changed during audit/analysis')
    report = {'status': 'completed', 'plan_sha256': digest(out / 'PLAN.json'),
              'study_sha256': plan['study_sha256'], 'analyzed_unix': time.time(),
              'world_pairs': rows, 'primary': paired_statistics(differences), 'learning': learning,
              'analysis_contract': {k: plan[k] for k in ('unit', 'effect', 'denominator', 'missing_pair_policy', 'test', 'interval')},
              'confirmatory_significance_claim': False, 'whole_model_accounting_complete': False,
              'scope': 'Development outcomes conditional on this simulator, bank and grader. Partial scoring coverage, same-model judgments and unknown bootstrap/social usage remain limitations.'}
    write_new(out / 'AUDIT.json', {'command': command, 'cwd': plan['audit_source'], 'result': audit,
                                  'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                                  'study_json_sha256': before})
    write_new(out / 'REPORT.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare', 'analyze'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--study', type=Path)
    p.add_argument('--frozen-source', type=Path)
    p.add_argument('--python', default=sys.executable)
    p.add_argument('--harness-config', type=Path)
    p.add_argument('--learner-config', type=Path)
    p.add_argument('--judge-config', type=Path)
    p.add_argument('--bank', type=Path)
    a = p.parse_args()
    if a.command == 'prepare':
        if not a.study or not a.frozen_source: p.error('Preparation needs --study and --frozen-source')
        value = prepare(a.study, a.out, a.frozen_source, a.python, a.harness_config, a.learner_config, a.judge_config)
    else:
        if not a.bank: p.error('Analysis needs --bank')
        value = analyze(a.out, a.bank)
    print(json.dumps(value, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
