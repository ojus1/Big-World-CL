"""Fresh-provider gate fixtures; all native auditors are replaced offline."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation.provider import PROFILE, provider_contract
from lifespan.mirofish import save
from scripts import scale_v3_prerequisites as check
from scripts import preflight_actor_contract as actor
from scripts import audit_hermes_preflight as employee
from scripts import preflight_optimizer as optimizer
from scripts import hermes_startup_scope_qualification_v3 as startup
from scripts import hermes_startup_probe as probe
from tests.test_scale_v3_provider_registration import profiled_policy


class FreshProviderPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(check, 'ROOT', self.root))
        self.source = self.root / 'lifespan/fixture.py'
        self.source.parent.mkdir(); self.source.write_text('# fixture source only\n')
        self.tool = self.root / 'scripts/component.py'
        self.tool.parent.mkdir(); self.tool.write_text('# fixture component only\n')
        self.policy = provider_contract('fixture-qwen', 'https://example.invalid/v1')
        self.campaign = {'provider_contract': self.policy, 'target_model': self.policy['model'],
            'model_base_url': self.policy['base_url'], 'launch_policy': profiled_policy(),
            'source_sha256': {'lifespan/fixture.py': check.sha(self.source)},
            'registration_tools_sha256': {'scripts/component.py': check.sha(self.tool)},
            'dependencies': {'hermes': {'revision': 'd' * 40}, 'mirofish': {'revision': 'e' * 40}}}
        self.out = self.root / 'component'; self.review = self.root / 'review.json'

    def fixture(self, component):
        kind, artifact = {
            'actor': ('native_actor_wire_capability_preflight', 'SUMMARY.json'),
            'employee': ('hermes-transport-capability-provider-v1', 'REPORT.json'),
            'optimizer': ('native_optimizer_provider_capability_v1', 'REPORT.json')}[component]
        self.component, self.artifact = component, artifact
        self.manifest = {'kind': kind, 'provider_contract': deepcopy(self.policy),
            'target_model': self.policy['model'], 'model_base_url': self.policy['base_url'],
            'source_sha256': {**self.campaign['source_sha256'], **self.campaign['registration_tools_sha256']},
            'dependencies': deepcopy(self.campaign['dependencies'])}
        if component == 'actor':
            self.manifest['dependencies'] = {'repositories': self.manifest['dependencies'],
                'python': {'fixture_only': True}, 'packages': {'fixture_only': True}}
        save(self.out / 'manifest.json', self.manifest)
        save(self.out / artifact, {'fixture_component': component})
        self.bind()
        result = {'ok': True, 'status': 'completed', 'manifest_sha256': check.sha(self.out / 'manifest.json'),
            'provider_contract': deepcopy(self.policy), 'evidence_inventory_sha256': 'f' * 64}
        if component == 'actor':
            result.update(verified=True, roles=list(actor.ROLES),
                summary_sha256=check.sha(self.out / artifact), actor_interviews={'fixture_only': True})
        elif component == 'employee':
            result.update(status='valid_completed', capability_pass=True, accounting_verified=True,
                report_sha256=check.sha(self.out / artifact), usage={'complete': True},
                slots=[{'workflow': workflow, 'mode': 'nonstreaming', 'capability_pass': True,
                        'cleanup_confirmed': True} for workflow in ('onboarding', 'renewal', 'incident')])
        else:
            result.update(capability_pass=True, physical_model_calls=1, tokens=37,
                parsed_edit_count=0, native_learning_or_adoption=False)
        return result

    def bind(self):
        save(self.out / 'manifest.json', self.manifest)
        save(self.review, {'artifact_sha256': check.sha(self.out / self.artifact),
            'manifest_sha256': check.sha(self.out / 'manifest.json'),
            'decision': 'approved_for_prospective_evaluation'})
        for row in self.campaign['launch_policy']['evidence']:
            if row['kind'] == self.component + '_native_capability':
                row.update(artifact_sha256=check.sha(self.out / self.artifact), review_sha256=check.sha(self.review))

    def call(self, result, side_effect=None):
        module, name = {'actor': (actor, 'audit'), 'employee': (employee, 'audit_preflight'),
                        'optimizer': (optimizer, 'audit_preflight')}[self.component]
        kwargs = {'directory': self.out, 'review_file': self.review}
        if self.component == 'actor': kwargs['source_root'] = self.root
        with patch.object(module, name, return_value=result, side_effect=side_effect) as audited:
            value = getattr(check, 'fresh_' + self.component + '_check')(self.campaign, **kwargs)
            self.assertEqual(audited.call_args.kwargs['strict'], True)
            key = 'expected_manifest_sha256' if self.component == 'employee' else 'manifest_sha256'
            self.assertEqual(audited.call_args.kwargs[key], check.sha(self.out / 'manifest.json'))
            return value

    def test_each_fresh_component_calls_real_api_with_strict_external_manifest_binding(self):
        for component in ('actor', 'employee', 'optimizer'):
            with self.subTest(component=component):
                value = self.call(self.fixture(component))
                self.assertIs(value['verified'], True)
                self.assertNotIn('compatibility', value)
        self.assertEqual(value['parsed_edit_count'], 0)  # Valid [] is not a gain gate.

    def test_failed_or_unknown_component_never_passes_reviewed_success_label(self):
        for component in ('actor', 'employee', 'optimizer'):
            result = self.fixture(component)
            changes = [('ok', False), ('status', 'incomplete'), ('manifest_sha256', '0' * 64),
                       ('provider_contract', {**self.policy, 'model': 'old-model'})]
            if component == 'actor': changes += [('verified', False), ('roles', list(actor.ROLES)[:3])]
            elif component == 'employee':
                changes += [('capability_pass', False), ('accounting_verified', False),
                    ('slots', result['slots'][:2]), ('usage', {'complete': False}),
                    ('slots', [{**result['slots'][0], 'cleanup_confirmed': False}, *result['slots'][1:]]),
                    ('slots', [{**result['slots'][0], 'mode': 'streaming'}, *result['slots'][1:]]),
                    ('slots', [result['slots'][0]] * 3)]
            else: changes += [('physical_model_calls', True), ('physical_model_calls', 2),
                              ('capability_pass', False), ('native_learning_or_adoption', True)]
            for key, value in changes:
                with self.subTest(component=component, key=key), self.assertRaises(ValueError):
                    self.call({**result, key: value})

    def test_old_provider_and_missing_profile_refused_before_native_auditor(self):
        for component in ('actor', 'employee', 'optimizer'):
            for change in ('old_model', 'missing_profile', 'thinking_zero', 'different_url'):
                result = self.fixture(component)
                if change == 'old_model': self.manifest['provider_contract']['model'] = 'old-model'
                elif change == 'missing_profile': self.manifest.pop('provider_contract')
                elif change == 'thinking_zero': self.manifest['provider_contract']['chat_template_kwargs']['enable_thinking'] = 0
                else: self.manifest['model_base_url'] = 'https://elsewhere.invalid/v1'
                self.bind()
                with self.subTest(component=component, change=change), self.assertRaises(ValueError):
                    self.call(result, side_effect=AssertionError('audit must not run'))

    def test_missing_unregistered_or_changed_source_cannot_be_coherently_rebound(self):
        for change in ('missing_core', 'unregistered_tool', 'changed_current', 'symlink'):
            result = self.fixture('employee')
            if change == 'missing_core': self.manifest['source_sha256'].pop('lifespan/fixture.py')
            elif change == 'unregistered_tool': self.manifest['source_sha256']['scripts/foreign.py'] = 'a' * 64
            elif change == 'changed_current': self.tool.write_text('# changed after preflight\n')
            else:
                self.tool.unlink(); self.tool.symlink_to(self.source)
                self.manifest['source_sha256']['scripts/component.py'] = check.sha(self.source)
                self.campaign['registration_tools_sha256']['scripts/component.py'] = check.sha(self.source)
            self.bind()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call(result, side_effect=AssertionError('audit must not run'))
            if self.tool.is_symlink(): self.tool.unlink()
            self.tool.write_text('# fixture component only\n')
            self.campaign['registration_tools_sha256']['scripts/component.py'] = check.sha(self.tool)

    def test_source_and_reviewed_raw_bytes_rechecked_after_component_audit(self):
        for target in ('source', 'manifest', 'artifact', 'review'):
            result = self.fixture('actor')
            path = {'source': self.source, 'manifest': self.out / 'manifest.json',
                    'artifact': self.out / self.artifact, 'review': self.review}[target]
            original = path.read_bytes()
            def mutate(*args, **kwargs):
                path.write_bytes(original + b'\n'); return result
            with self.subTest(target=target), self.assertRaises(ValueError): self.call(result, side_effect=mutate)
            path.write_bytes(original)

    def test_legacy_paths_and_compatibility_cannot_replace_fresh_optimizer(self):
        paths = {name: {'directory': str(self.root / name), 'review_file': str(self.review)}
                 for name in ('actor', 'employee', 'horizon', 'startup', 'optimizer')}
        paths['actor']['source_root'] = str(self.root)
        with patch.object(check, 'compatibility_check', side_effect=AssertionError('historical shortcut')):
            for changes in ('missing_optimizer', 'compatibility_extra', 'old_employee'):
                value = deepcopy(paths)
                if changes == 'missing_optimizer': value.pop('optimizer')
                elif changes == 'compatibility_extra': value['compatibility'] = {'artifact_file': '/fixture'}
                else: value['employee'] = {'original_directory': '/fixture', 'observation_directory': '/fixture', 'review_file': '/fixture'}
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'v3_prerequisite_'):
                    check.verify_prerequisites(self.campaign, value)
            from contextlib import ExitStack
            with ExitStack() as stack:
                names = ('fresh_actor_check', 'fresh_employee_check', 'horizon_check', 'startup_check', 'fresh_optimizer_check')
                mocked = [stack.enter_context(patch.object(check, name, return_value={'verified': True})) for name in names]
                result = check.verify_prerequisites(self.campaign, paths)
                self.assertEqual(result['provider_contract'], self.policy)
                self.assertEqual(len(result['checks']), 5)
                for mock in mocked: mock.assert_called_once()

    def test_current_model_nine_slot_startup_with_fixed_dummy_endpoint_is_required(self):
        directory = self.root / 'startup'; review = self.root / 'startup-review.json'
        selection = {'model': self.policy['model'], 'provider_profile': PROFILE}
        manifest = {'startup_configuration': selection, 'child_execution': probe.startup_settings(selection)[0],
            'source_sha256': self.campaign['source_sha256'], 'dependencies': self.campaign['dependencies'],
            'boot_id': 'fixture-boot', 'caller_security_context': 'fixture-context'}
        save(directory / 'REPORT.json', {'fixture_only': True})
        for change in ('valid', 'old_model', 'missing', 'real_endpoint', 'only_eight', 'one_failed'):
            value = deepcopy(manifest)
            actual = {'ok': True, 'status': 'completed', 'qualification_passed': True,
                      'slots': [{'qualification_passed': True} for _ in range(9)]}
            if change == 'old_model': value['startup_configuration']['model'] = 'old-model'
            elif change == 'missing': value.pop('startup_configuration')
            elif change == 'real_endpoint': value['child_execution']['provider_contract'] = self.policy
            elif change == 'only_eight': actual['slots'].pop()
            elif change == 'one_failed': actual['slots'][0]['qualification_passed'] = False
            save(directory / 'manifest.json', value)
            save(review, {'manifest_sha256': check.sha(directory / 'manifest.json'),
                'report_sha256': check.sha(directory / 'REPORT.json'), 'qualification_passed': True})
            row = next(r for r in self.campaign['launch_policy']['evidence'] if r['kind'] == 'scope_startup_qualification')
            row.update(artifact_sha256=check.sha(directory / 'REPORT.json'), review_sha256=check.sha(review))
            with patch.object(startup, 'audit_qualification', return_value=actual):
                if change == 'valid': self.assertTrue(check.startup_check(self.campaign, directory=directory, review_file=review)['verified'])
                else:
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        check.startup_check(self.campaign, directory=directory, review_file=review)

    def test_startup_raw_references_and_current_sources_cannot_change_during_audit(self):
        selection = {'model': self.policy['model'], 'provider_profile': PROFILE}
        directory = self.root / 'startup'; review = self.root / 'startup-review.json'
        manifest = {'startup_configuration': selection, 'child_execution': probe.startup_settings(selection)[0],
            'source_sha256': self.campaign['source_sha256'], 'dependencies': self.campaign['dependencies'],
            'boot_id': 'fixture-boot', 'caller_security_context': 'fixture-context'}
        save(directory / 'manifest.json', manifest); save(directory / 'REPORT.json', {'fixture_only': True})
        save(review, {'manifest_sha256': check.sha(directory / 'manifest.json'),
            'report_sha256': check.sha(directory / 'REPORT.json'), 'qualification_passed': True})
        row = next(r for r in self.campaign['launch_policy']['evidence'] if r['kind'] == 'scope_startup_qualification')
        row.update(artifact_sha256=check.sha(directory / 'REPORT.json'), review_sha256=check.sha(review))
        result = {'ok': True, 'status': 'completed', 'qualification_passed': True,
                  'slots': [{'qualification_passed': True} for _ in range(9)]}
        for path in (directory / 'manifest.json', directory / 'REPORT.json', review, self.source):
            original = path.read_bytes()
            def mutate(*args, **kwargs):
                path.write_bytes(original + b'\n'); return result
            with patch.object(startup, 'audit_qualification', side_effect=mutate), self.subTest(path=path.name), \
                    self.assertRaises(ValueError):
                check.startup_check(self.campaign, directory=directory, review_file=review)
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
