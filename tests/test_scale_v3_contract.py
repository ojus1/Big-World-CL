"""Adversarial registration tests using synthetic cohorts and no native calls."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation.protocol import digest
from lifespan.mirofish import save
from scripts import prepare_scale_v3 as preparation
from scripts import scale_v3_contract as contract


def example_policy():
    # Test-only values, not an actual campaign policy or evidence hashes.
    return {'per_world_wall_seconds': 86400, 'workers': 2,
        'mirofish_service_url': 'http://127.0.0.1:5002',
        'wall_budget_rationale': 'Synthetic test evidence; no campaign duration forecast.',
        'scope_limits': deepcopy(contract.SCOPE_LIMITS), 'dispatch_policy': contract.DISPATCH_POLICY,
        'evidence': [{'kind': name, 'artifact_sha256': str(i + 1) * 64,
                      'review_sha256': str(i + 4) * 64} for i, name in enumerate(contract.EVIDENCE_KINDS)]}


def importer(cache, path, *, count, seed):
    cohort = {'personas': [{'persona_id': f'fixture-{seed}-{i}', 'text': 'Synthetic fixture'}
                           for i in range(count)]}
    save(path, cohort)
    return cohort


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.out = self.root / 'lifespan/artifacts/registration'
        self.patch = patch.object(preparation, 'ROOT', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        self.sources = {'fixture_source.py': 'a' * 64}
        self.deps = {name: {'revision': 'b' * 40} for name in ('hermes', 'mirofish', 'skillopt')}
        self.tools = {name: 'c' * 64 for name in contract.REGISTRATION_TOOLS}
        self.manifest = preparation.prepare(self.out, launch_policy=example_policy(),
            target_model='fixture-model', model_base_url='https://example.invalid/v1',
            cohort_importer=importer, sources=self.sources, dependencies=self.deps, registration_tools=self.tools)
        self.reviewed_hash = contract.sha(self.out / 'campaign.json')

    def validate(self, **kwargs):
        return contract.validate(self.out, source_sha256=self.sources, dependencies=self.deps,
                                 registration_tools_sha256=self.tools,
                                 campaign_sha256=kwargs.pop('campaign_sha256', self.reviewed_hash), **kwargs)

    def change(self, fn):
        value = deepcopy(self.manifest); fn(value); save(self.out / 'campaign.json', value)

    def test_complete_design_and_identical_paired_inputs(self):
        m = self.validate(); self.assertEqual(m, self.manifest)
        self.assertEqual(len(m['slots']), 6); self.assertEqual(m['population'], contract.POPULATION)
        for seed in contract.SEEDS:
            arms = [s for s in m['slots'] if s['seed'] == seed]
            self.assertEqual(arms[0]['persona_cohort_sha256'], arms[1]['persona_cohort_sha256'])
            a, b = [dict(s['config']) for s in arms]
            self.assertNotEqual(a.pop('algorithm'), b.pop('algorithm')); self.assertEqual(a, b)
            self.assertEqual(a['days'], 20); self.assertEqual(a['update_days'], [3, 7, 11, 17])
            self.assertEqual(a['train_cases'], 2); self.assertEqual(a['val_cases'], 2)
            self.assertEqual(a['actor_output_contract'], contract.ACTOR_CONTRACT)
            self.assertEqual(a['hermes_transport'], 'nonstreaming')
            self.assertIs(a['hermes_startup_observability'], True)
        self.assertEqual(m['budgets']['max_online_sessions'], 1440)
        self.assertIsNone(m['budgets']['actor_tokens'])
        self.assertIsNone(m['budgets']['actor_physical_model_calls'])
        self.assertEqual(m['budgets']['contracted_interview_physical_requests'], 3972)

    def test_only_observability_changes_scientific_config_from_fixed_v2(self):
        from scripts import scale_v2_contract as old
        p = example_policy()
        old_policy = {k: v for k, v in p.items() if k not in ('scope_limits', 'dispatch_policy')}
        old_policy['evidence'] = p['evidence'][:3]
        for seed, arm in contract.schedule():
            actual = contract.config(seed, arm, p).public()
            actual.pop('hermes_startup_observability')
            self.assertEqual(actual, old.config(seed, arm, old_policy).public())
        self.assertEqual(contract.pair_waves(), [
            ['seed-211-no_learning', 'seed-211-skillopt'],
            ['seed-307-skillopt', 'seed-307-no_learning'],
            ['seed-401-no_learning', 'seed-401-skillopt']])
        self.assertEqual(contract.SCOPE_LIMITS['execution_seconds'], 260310)
        self.assertEqual(contract.SCOPE_LIMITS['runtime_max_seconds'], 260490)

    def test_no_implicit_wall_limit_or_prerequisite_claim(self):
        for key in ('per_world_wall_seconds', 'evidence', 'wall_budget_rationale'):
            p = example_policy(); p.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): contract.policy(p)
        self.assertIn('does not re-audit', self.manifest['design']['prerequisites'])

    def test_boolean_zero_negative_and_noninteger_limits_rejected(self):
        for key in ('per_world_wall_seconds', 'workers'):
            for value in (True, False, 0, -1, 2.0, '6', None):
                p = example_policy(); p[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): contract.policy(p)
        p = example_policy(); p['workers'] = 7
        with self.assertRaises(ValueError): contract.policy(p)

    def test_separate_canonical_service_required(self):
        for url in (None, 'http://127.0.0.1:5001', 'http://localhost:5002/',
                    'http://127.0.0.1:5002/', 'https://example.invalid:5002',
                    'http://user:pass@127.0.0.1:5002'):
            p = example_policy(); p['mirofish_service_url'] = url
            with self.subTest(url=url), self.assertRaises(ValueError): contract.policy(p)

    def test_native_evidence_references_cannot_be_missing_duplicated_or_malformed(self):
        cases = []
        p = example_policy(); p['evidence'].pop(); cases.append(p)
        p = example_policy(); p['evidence'][1] = p['evidence'][0]; cases.append(p)
        p = example_policy(); p['evidence'][0]['artifact_sha256'] = 'not a hash'; cases.append(p)
        p = example_policy(); p['evidence'][0]['provider_body'] = 'not permitted'; cases.append(p)
        for i, p in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(ValueError): contract.policy(p)

    def test_design_or_source_mutations_rejected(self):
        mutations = [lambda m: m.update(days=8), lambda m: m['population'].update(employees=3),
            lambda m: m['budgets'].update(max_learning_epochs=12),
            lambda m: m['design'].update(completion='surviving pairs'),
            lambda m: m['source_sha256'].update(extra='d' * 64),
            lambda m: m['registration_tools_sha256'].clear(),
            lambda m: m['dependencies']['hermes'].update(revision='e' * 40),
            lambda m: m.update(schema_version=True), lambda m: m.update(unreviewed_option=True)]
        for i, mutation in enumerate(mutations):
            self.change(mutation)
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.validate(campaign_sha256=contract.sha(self.out / 'campaign.json'))

    def test_reporter_local_imports_are_pinned_before_outcomes(self):
        """A new reporting dependency must enter the prospective source map."""
        from scripts import report_scale_v3 as reporter
        from lifespan.evaluation.runner import source_hashes
        repository = Path(contract.__file__).resolve().parents[1]
        registered = set(contract.REGISTRATION_TOOLS) | set(source_hashes())
        pending = ['scripts/report_scale_v3.py', *reporter.HELPERS]
        visited = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            module = name.removesuffix('.py').replace('/', '.')
            package = module.rsplit('.', 1)[0]
            for node in ast.walk(ast.parse((repository / name).read_text())):
                candidates = []
                if isinstance(node, ast.Import):
                    candidates = [entry.name for entry in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ''
                    if node.level:
                        base = importlib.util.resolve_name('.' * node.level + base, package)
                    candidates = [base, *[base + '.' + entry.name for entry in node.names]]
                for candidate in candidates:
                    if candidate.split('.')[0] not in ('scripts', 'lifespan'):
                        continue
                    relative = candidate.replace('.', '/') + '.py'
                    if (repository / relative).is_file():
                        pending.append(relative)
        self.assertFalse(visited - registered, sorted(visited - registered))
        self.assertIn('scripts/report_scale_v3.py', self.manifest['registration_tools_sha256'])

    def test_reporter_pin_cannot_be_removed_or_changed_with_a_new_manifest_hash(self):
        for change in ('removed', 'changed'):
            value = deepcopy(self.manifest)
            name = 'scripts/report_scale_v3.py'
            if change == 'removed':
                value['registration_tools_sha256'].pop(name)
            else:
                value['registration_tools_sha256'][name] = 'd' * 64
            save(self.out / 'campaign.json', value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(campaign_sha256=contract.sha(self.out / 'campaign.json'))

    def test_fixed_policy_cannot_change_even_with_new_hash(self):
        for key, value in (('workers', 1), ('workers', 6), ('per_world_wall_seconds', 72000),
                           ('dispatch_policy', 'rolling_refill')):
            p = example_policy(); p[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): contract.policy(p)
        for key, value in contract.SCOPE_LIMITS.items():
            p = example_policy(); p['scope_limits'][key] = value + 1
            with self.subTest(limit=key), self.assertRaises(ValueError): contract.policy(p)


    def test_coherently_rewritten_persona_content_is_not_the_reviewed_registration(self):
        m = deepcopy(self.manifest); cohort = contract.read(self.out / 'cohorts/211.json')
        cohort['personas'][0]['text'] = 'Different fixture content'
        save(self.out / 'cohorts/211.json', cohort)
        for slot in m['slots']:
            if slot['seed'] == 211:
                path = self.out / slot['relative_path'] / 'persona_cohort.json'; save(path, cohort)
                slot['persona_cohort_sha256'] = contract.sha(path)
        save(self.out / 'campaign.json', m)
        with self.assertRaisesRegex(ValueError, 'reviewed_campaign_hash'): self.validate()

    def test_missing_reviewed_hash_is_not_replaced_by_current_hash(self):
        for value in (None, '', '0' * 64, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'reviewed_campaign_hash'):
                self.validate(campaign_sha256=value)

    def test_omitted_duplicated_reordered_or_replaced_slots_rejected(self):
        for mutation in (lambda m: m['slots'].pop(),
                         lambda m: m['slots'].__setitem__(1, m['slots'][0]),
                         lambda m: m['slots'].reverse(),
                         lambda m: m['slots'][0].update(seed=999)):
            self.change(mutation)
            with self.assertRaises(ValueError): self.validate()

    def test_coherent_rehash_does_not_allow_shorter_horizon_or_method_change(self):
        slot = self.manifest['slots'][0]; run = self.out / slot['relative_path']
        for key, value in (('days', 8), ('train_cases', 1), ('hermes_transport', 'streaming'),
                           ('hermes_startup_observability', False), ('max_iterations', True), ('mirofish_service_url', 'http://127.0.0.1:5003')):
            def mutate(m):
                s = m['slots'][0]; s['config'][key] = value
                s['config_sha256'] = digest(s['config']); save(run / 'config.json', s['config'])
            self.change(mutate)
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate()

    def test_changed_cohort_bytes_and_overlapping_personas_rejected(self):
        slot = self.manifest['slots'][0]; path = self.out / slot['relative_path'] / 'persona_cohort.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'cohort_bytes'): self.validate()
        path.write_bytes((self.out / 'cohorts/211.json').read_bytes())
        cohort = contract.read(self.out / 'cohorts/307.json')
        cohort['personas'][0]['persona_id'] = 'fixture-211-0'; save(self.out / 'cohorts/307.json', cohort)
        with self.assertRaisesRegex(ValueError, 'distinct_persona'): self.validate()

    def test_symlink_and_unregistered_worlds_rejected(self):
        extra = self.out / 'runs/unregistered'; extra.mkdir()
        with self.assertRaisesRegex(ValueError, 'unregistered_or_missing_run'): self.validate()
        extra.rmdir()
        path = self.out / self.manifest['slots'][0]['relative_path'] / 'config.json'
        target = self.root / 'outside.json'; target.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'path_escape_or_symlink'): self.validate()

    def test_previous_intent_or_any_native_output_prevents_dispatch_validation(self):
        (self.out / 'EXECUTION.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'intent_already_exists'): self.validate()
        self.validate(require_pristine=False)
        (self.out / 'EXECUTION.json').unlink()
        run = self.out / self.manifest['slots'][0]['relative_path']; (run / 'checkpoint.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'uncertain_work'): self.validate()
        self.validate(require_pristine=False)

    def test_provider_match_and_credential_bearing_urls(self):
        self.validate(target_model='fixture-model', model_base_url='https://example.invalid/v1')
        with self.assertRaisesRegex(ValueError, 'provider_changed'):
            self.validate(target_model='other', model_base_url='https://example.invalid/v1')
        for url in ('https://user:secret@example.invalid', 'https://example.invalid?key=secret',
                    'https://example.invalid#secret', 'https://example.invalid\n'):
            with self.subTest(url=url), self.assertRaises(ValueError): contract.model_metadata('fixture', url)

    def test_existing_output_and_uninstalled_dependencies_fail_before_import(self):
        with self.assertRaises(FileExistsError):
            preparation.prepare(self.out, launch_policy=example_policy(), target_model='fixture',
                model_base_url='https://example.invalid', sources=self.sources, dependencies=self.deps,
                registration_tools=self.tools, cohort_importer=lambda *a, **k: self.fail('import called'))
        fresh = self.root / 'lifespan/artifacts/fresh'
        with self.assertRaisesRegex(ValueError, 'installed_dependency'):
            preparation.prepare(fresh, launch_policy=example_policy(), target_model='fixture',
                model_base_url='https://example.invalid', sources=self.sources, dependencies={},
                registration_tools=self.tools, cohort_importer=lambda *a, **k: self.fail('import called'))
        self.assertFalse(fresh.exists())


if __name__ == '__main__':
    unittest.main()
