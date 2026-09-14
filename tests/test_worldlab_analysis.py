"""Prevent selective-pair analysis and verify exact statistical edge cases."""
from fractions import Fraction
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts/analyze_worldlab.py'
spec = importlib.util.spec_from_file_location('analyze_worldlab', MODULE)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(root):
    study = {'employee_driver': {'name': 'fixture'},
             'analysis': {'scope': 'development', 'primary': 'probe_accepted_on_time_fraction'},
             'source_sha256': {}, 'learner': {'name': 'learner'}, 'seed_skill': 'original',
             'worlds': [{'seed': seed, 'schedule': [{'split': 'probe'}] * 4} for seed in [41, 43]]}
    save(root / 'STUDY.json', study)
    save(root / 'PREPARED.json', {'study_sha256': analysis.digest(root / 'STUDY.json')})
    return study


class Tests(unittest.TestCase):
    def test_exact_sign_flip_known_tails_and_ties(self):
        positive = analysis.paired_statistics([Fraction(1, 4)] * 6)
        self.assertEqual(positive['exact_sign_flip'], {
            'two_sided_p': 2 / 64, 'extreme_assignments': 2, 'all_assignments': 64})
        self.assertEqual(positive['world_pairs'], 6)
        self.assertLessEqual(positive['hoeffding_95_interval']['low'], 0)
        self.assertEqual(analysis.paired_statistics([Fraction()] * 6)['exact_sign_flip']['two_sided_p'], 1)
        self.assertEqual(analysis.paired_statistics([Fraction(1, 3), Fraction(-1, 3)])['exact_sign_flip']['two_sided_p'], 1)
        with self.assertRaises(ValueError): analysis.paired_statistics([Fraction(2)])
        with self.assertRaises(ValueError): analysis.paired_statistics([])
        with self.assertRaises(ValueError): analysis.paired_statistics([float('nan')])

    def test_plan_requires_unexecuted_study_and_fixed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'study', Path(tmp) / 'analysis'
            fixture(root)
            result = analysis.prepare(root, out, Path(tmp))
            self.assertEqual(result['world_pairs'], 2)
            self.assertFalse(result['confirmatory_significance_claim'])
            save(root / 'EXECUTION.json', {'started_unix': 1})
            with self.assertRaisesRegex(ValueError, 'before any study execution'):
                analysis.prepare(root, Path(tmp) / 'another', Path(tmp))
            (out / 'PLAN.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Analysis plan or source changed'):
                analysis.analyze(out, Path(tmp))

    def test_partial_study_never_runs_audit_or_computes_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'study', Path(tmp) / 'analysis'
            fixture(root)
            analysis.prepare(root, out, Path(tmp))
            save(root / 'EXECUTION.json', {'started_unix': analysis.read(out / 'PLAN.json')['prepared_unix'] + 1})
            save(root / 'REPORT.json', {'status': 'incomplete'})
            with patch.object(analysis.subprocess, 'run') as audit:
                with self.assertRaisesRegex(ValueError, 'Entire planned study'):
                    analysis.analyze(out, Path(tmp))
                audit.assert_not_called()
            self.assertFalse((out / 'REPORT.json').exists())

    def test_learner_audit_configuration_and_reproduction_source_are_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'study', Path(tmp) / 'analysis'
            fixture(root)
            config = Path(tmp) / 'learner.json'
            save(config, {'factory': 'example:Factory', 'kwargs': {}})
            analysis.prepare(root, out, Path(tmp), learner_config=config)
            plan = analysis.read(out / 'PLAN.json')
            self.assertEqual(plan['learner_config_sha256'], analysis.digest(config))
            self.assertEqual(analysis.digest(out / 'REPRODUCE.py'), plan['analysis_source_sha256'])
            save(root / 'EXECUTION.json', {'started_unix': plan['prepared_unix'] + 1})
            save(root / 'REPORT.json', {'status': 'completed'})
            config.write_text(config.read_text() + '\n')
            with patch.object(analysis.subprocess, 'run') as audit:
                with self.assertRaisesRegex(ValueError, 'learner configuration changed'):
                    analysis.analyze(out, Path(tmp))
                audit.assert_not_called()

    def test_all_planned_probes_and_equal_world_weights_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            study = fixture(root)
            for w in study['worlds']:
                for name, count in [('no_learning', 1), ('learner', 2)]:
                    arm = root / 'worlds' / f'seed-{w["seed"]}' / name
                    save(arm / 'STATE.json', {'sessions': [{'id': 'one-attempt'}], 'updates': []})
                    save(arm / 'REPORT.json', {'status': 'completed', 'adoptions': 0,
                        'probe_accepted_on_time_fraction': count / 4,
                        'work_and_judging_tokens': 10, 'learning_and_replay_judging_tokens': 0,
                        'actor_usage': {'tokens': 4, 'bootstrap_and_social_tokens': None},
                        'workplace': {'probe_accepted_on_time': count, 'probe_obligations': 4, 'rework_attempts': 0}})
            rows, differences, _ = analysis.observations(root, study)
            self.assertEqual(differences, [Fraction(1, 4), Fraction(1, 4)])
            self.assertEqual(analysis.paired_statistics(differences)['world_pairs'], 2)
            self.assertEqual(rows[0]['planned_probes_per_arm'], 4)
            self.assertEqual(rows[0]['learner']['fraction'], .5)
            arm = root / 'worlds/seed-41/learner'
            save(arm / 'STATE.json', {'sessions': [
                {'employee_id': 'editor', 'day': day, 'skill_content_sha256': hashlib.sha256(skill.encode()).hexdigest()}
                for day, skill in [(3, 'changed'), (5, 'original')]], 'updates': [
                    {'employee_id': 'editor', 'day': day, 'result': {'accepted': True, 'skill': skill,
                        'costs': {'operations': [{'kind': 'reflect', 'reported_usage': {'model_calls': 2}},
                                                 {'kind': 'target', 'reported_usage': {'model_calls': 10}}]}}}
                    for day, skill in [(1, 'changed'), (2, 'changed'), (4, 'original')]]})
            _, _, learning = analysis.observations(root, study)
            self.assertEqual(learning['adoptions'], 3)
            self.assertEqual(learning['nontrivial_adoptions'], 2)
            self.assertEqual(learning['later_sessions_with_adopted_skill'], 1)
            self.assertEqual(learning['optimizer_physical_calls_reported'], 6)
            missing = root / 'worlds/seed-43/learner/REPORT.json'
            missing.unlink()
            with self.assertRaises(FileNotFoundError): analysis.observations(root, study)


if __name__ == '__main__':
    unittest.main()
