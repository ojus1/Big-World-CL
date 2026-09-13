"""Explicit provider registration and no-network startup fixtures; no model calls."""
from copy import deepcopy
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation.provider import PROFILE, provider_contract
from lifespan.mirofish import save
from scripts import prepare_scale_v3 as prepare
from scripts import scale_v3_contract as contract
from scripts import scale_v3_prerequisites as prerequisites
from scripts import hermes_startup_probe as probe
from tests import test_scale_v3_contract as legacy
from tests import test_hermes_startup_probe as probe_tests
from tests import test_hermes_startup_scope_qualification_v3 as scope_tests
from scripts import hermes_startup_scope_qualification_v3 as scope


def profiled_policy():
    value = legacy.example_policy()
    value['provider_profile'] = PROFILE
    for row, kind in zip(value['evidence'], contract.PROFILE_EVIDENCE_KINDS):
        row['kind'] = kind
    return value


class ProviderRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        self.enterContext(patch.object(prepare, 'ROOT', self.root))
        self.out = self.root / 'lifespan/artifacts/profiled'
        self.sources = {'fixture.py': 'a' * 64}
        self.tools = {'fixture_tool.py': 'b' * 64}
        self.deps = {n: {'revision': 'c' * 40} for n in ('hermes', 'mirofish', 'skillopt')}

    def prepare(self, **kwargs):
        return prepare.prepare(self.out, launch_policy=profiled_policy(), target_model='fixture-qwen',
            model_base_url='https://example.invalid/v1', cohort_importer=legacy.importer,
            sources=self.sources, dependencies=self.deps, registration_tools=self.tools, **kwargs)

    def validate(self):
        return contract.validate(self.out, source_sha256=self.sources, dependencies=self.deps,
            registration_tools_sha256=self.tools, campaign_sha256=contract.sha(self.out / 'campaign.json'))

    def test_profile_adds_only_declared_provider_config_to_same_six_world_science(self):
        manifest = self.prepare(provider_profile=PROFILE)
        self.assertEqual(self.validate(), manifest)
        self.assertEqual(manifest['provider_contract'], provider_contract('fixture-qwen', 'https://example.invalid/v1'))
        for slot in manifest['slots']:
            actual = dict(slot['config']); self.assertEqual(actual.pop('provider_profile'), PROFILE)
            self.assertEqual(actual, contract.config(slot['seed'], slot['algorithm'], legacy.example_policy()).public())
        self.assertEqual(manifest['budgets'], contract.budgets(legacy.example_policy()))
        self.assertEqual(len(manifest['slots']), 6)
        self.assertEqual(contract.pair_waves()[1], ['seed-307-skillopt', 'seed-307-no_learning'])

    def test_legacy_profile_and_format_stay_absent(self):
        for seed, arm in contract.schedule():
            self.assertNotIn('provider_profile', contract.config(seed, arm, legacy.example_policy()).public())
        self.assertNotIn('provider_profile', contract.policy(legacy.example_policy()))

    def test_installed_overlays_and_native_gate_implementations_are_registered(self):
        repository = Path(contract.__file__).resolve().parents[1]
        overlays = subprocess.check_output(['git', '-C', str(repository), 'ls-files', '-z', '--',
            'local-overrides/backend'], timeout=10).decode().split('\0')
        required = {name for name in overlays if name} | {
            'patches/mirofish-local.patch', 'scripts/check_mirofish_installation.py',
            'scripts/preflight_actor_contract.py', 'scripts/preflight_optimizer.py',
            'scripts/hermes_transport_preflight.py', 'scripts/audit_hermes_preflight.py',
            'scripts/hermes_preflight_process.py', 'scripts/audit_hermes_readback_v2.py'}
        self.assertEqual(len([name for name in overlays if name]), 4)
        self.assertLessEqual(required, set(contract.REGISTRATION_TOOLS))

    def test_wrong_profile_or_old_compatibility_evidence_refused_before_prepare(self):
        with self.assertRaises(ValueError): self.prepare(provider_profile='unsupported')
        self.assertFalse(self.out.exists())
        p = legacy.example_policy(); p['provider_profile'] = PROFILE
        with self.assertRaises(ValueError): contract.policy(p)
        for value in (None, True, '', 'other'):
            p = profiled_policy(); p['provider_profile'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): contract.policy(p)

    def test_profile_descriptor_downgrades_and_policy_changes_rejected_with_new_raw_hash(self):
        original = self.prepare()
        for change in ('descriptor_missing', 'policy_missing', 'thinking_true', 'thinking_zero',
                       'model', 'url', 'profile', 'secret_field', 'one_slot_downgrade'):
            m = deepcopy(original)
            if change == 'descriptor_missing': m.pop('provider_contract')
            elif change == 'policy_missing': m['launch_policy'].pop('provider_profile')
            elif change.startswith('thinking_'): m['provider_contract']['chat_template_kwargs']['enable_thinking'] = True if change.endswith('true') else 0
            elif change == 'model': m['provider_contract']['model'] = 'different-model'
            elif change == 'url': m['provider_contract']['base_url'] = 'https://elsewhere.invalid/v1'
            elif change == 'profile': m['provider_contract']['profile'] = 'other'
            elif change == 'secret_field': m['provider_contract']['api_key'] = 'CANARY_NOT_CREDENTIAL'
            else:
                slot = m['slots'][0]; slot['config'].pop('provider_profile')
                slot['config_sha256'] = contract.digest(slot['config'])
                save(self.out / slot['relative_path'] / 'config.json', slot['config'])
            save(self.out / 'campaign.json', m)
            with self.subTest(change=change), self.assertRaises(ValueError): self.validate()

    def test_fresh_profile_never_enters_old_provider_compatibility_path(self):
        manifest = self.prepare()
        with patch.object(prerequisites, 'compatibility_check') as old:
            with self.assertRaisesRegex(ValueError, 'v3_prerequisite_path_inventory'):
                prerequisites.verify_prerequisites(manifest, {})
        old.assert_not_called()


class ProviderStartupTests(unittest.TestCase):
    def test_parameters_never_accept_endpoint_key_or_execution_overrides(self):
        config = {'model': 'fixture-qwen', 'provider_profile': PROFILE}
        execution, creds = probe.startup_settings(config)
        self.assertEqual(creds['base_url'], probe.CREDENTIALS['base_url'])
        self.assertEqual(creds['api_key'], probe.CREDENTIALS['api_key'])
        self.assertEqual(creds['model'], config['model'])
        self.assertEqual(execution['provider_contract'], provider_contract(config['model'], creds['base_url']))
        self.assertEqual(probe.startup_settings(), (probe.EXECUTION, probe.CREDENTIALS))
        for key in ('api_key', 'base_url', 'max_iterations'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.startup_settings({**config, key: 'CANARY_NOT_CREDENTIAL'})

    def test_actual_fake_computer_receives_profile_and_ready_policy_must_match(self):
        config = {'model': 'fixture-qwen', 'provider_profile': PROFILE}
        for changed in ('valid', 'omitted', 'model', 'thinking_zero'):
            case = probe_tests.NativeBodyTests('test_start_once_close_once_no_work_or_cleanup_upgrade')
            case.setUp()
            try:
                base = case.fake
                class ProfileComputer(base):
                    def start(self, credentials, timeout):
                        result = super().start(credentials, timeout)
                        descriptor = provider_contract(credentials['model'], credentials['base_url'])
                        if changed == 'model': descriptor['model'] = 'different'
                        elif changed == 'thinking_zero': descriptor['chat_template_kwargs']['enable_thinking'] = 0
                        if changed != 'omitted': result['provider_contract'] = descriptor
                        return result
                case.fake = ProfileComputer
                result = case.run_fake(startup_configuration=config)
                self.assertEqual(result['ready_observed'], changed == 'valid')
                self.assertEqual([n for n, _ in case.calls], ['init', 'start', 'close'])
                self.assertEqual(case.calls[0][1]['execution']['provider_contract'],
                    provider_contract('fixture-qwen', probe.CREDENTIALS['base_url']))
                self.assertEqual(case.calls[1][1]['credentials']['provider_profile'], PROFILE)
                receipt = json.loads((case.out / 'STARTUP_INTENT.json').read_bytes())
                self.assertEqual(receipt['execution'], case.calls[0][1]['execution'])
            finally:
                case.doCleanups()


class ProviderScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.out = Path(self.tmp) / 'startup'
        self.enterContext(scope_tests.guards())

    def test_prepare_binds_model_policy_and_keeps_nine_slot_caps(self):
        result = scope.prepare(self.out, model='fixture-qwen', provider_profile=PROFILE)
        m = scope.validate_manifest(self.out, result['manifest_sha256'])
        self.assertEqual(m['startup_configuration'], {'model': 'fixture-qwen', 'provider_profile': PROFILE})
        self.assertEqual(m['child_execution']['provider_contract'],
            provider_contract('fixture-qwen', probe.CREDENTIALS['base_url']))
        self.assertEqual([x['batch'] for x in m['slots']], [0, 1, 2, 3, 3, 4, 4, 5, 5])
        self.assertEqual((m['config']['startup_seconds'], m['config']['cleanup_seconds']), (150, 30))
        for change in ('missing', 'model', 'profile', 'endpoint', 'thinking_zero'):
            value = deepcopy(m)
            if change == 'missing': value.pop('startup_configuration')
            elif change in ('model', 'profile'):
                value['startup_configuration']['model' if change == 'model' else 'provider_profile'] = 'different'
            elif change == 'endpoint': value['startup_configuration']['base_url'] = 'https://example.invalid/v1'
            else: value['child_execution']['provider_contract']['chat_template_kwargs']['enable_thinking'] = 0
            scope_tests.write(self.out / 'manifest.json', value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                scope.validate_manifest(self.out, scope.load(self.out / 'manifest.json')[1])

    def test_half_selected_configuration_is_rejected_without_directory_creation(self):
        for kwargs in ({'model': 'fixture-qwen'}, {'provider_profile': PROFILE}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): scope.prepare(self.out, **kwargs)
            self.assertFalse(self.out.exists())

    def test_profiled_worker_passes_manifest_selection_after_gate_without_real_native_start(self):
        m, old_hash = scope_tests.fixture(self.out)
        selection = {'model': 'fixture-qwen', 'provider_profile': PROFILE}
        m.update(startup_configuration=selection, child_execution=probe.startup_settings(selection)[0])
        scope_tests.write(self.out / 'manifest.json', m)
        digest = scope.load(self.out / 'manifest.json')[1]
        execution = scope.load(self.out / 'EXECUTION.json')[0]
        execution['registered_manifest_sha256'] = digest
        scope_tests.write(self.out / 'EXECUTION.json', execution)
        slot = m['slots'][0]; trial = self.out / 'slots' / slot['slot_id']
        for name in ('INTENT.json', 'GATE.json', 'RELEASE.json'):
            path = trial / name; value = scope.load(path)[0]
            self.assertEqual(value['manifest_sha256'], old_hash)
            value['manifest_sha256'] = digest; scope_tests.write(path, value)
        for name in ('HELLO.json', 'CONTROLLER_EXIT.json'): (trial / name).unlink()
        gate = scope.load(trial / 'GATE.json')[0]
        env = {**m['controller_environment'], 'INVOCATION_ID': gate['unit_binding']['invocation_id']}
        def fake_native(*args, **kwargs):
            self.assertEqual(kwargs, {'startup_configuration': selection})
            self.assertEqual(args[3], digest)
            return {'cleanup_deadline': 180.}
        with patch.dict(os.environ, env, clear=True), patch.object(scope, 'identity', return_value=gate['unit_binding']['main_identity']), \
                patch.object(scope.time, 'monotonic', return_value=102.), patch.object(scope, '_native_startup', side_effect=fake_native) as called:
            scope._worker(self.out, slot['slot_id'])
        called.assert_called_once()


if __name__ == '__main__':
    unittest.main()
