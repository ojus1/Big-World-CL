"""Profile preflight fixtures; no native executor, service, credentials or HTTP."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lifespan.evaluation.provider import PROFILE, provider_contract
from lifespan.evaluation.hermes_transport import contract
from lifespan.evaluation.runner import source_hashes
from scripts import hermes_transport_preflight as preflight
from scripts import audit_hermes_preflight as audit
from scripts import audit_hermes_readback_v2 as readback
from tests import test_hermes_transport_preflight as launch_fixtures
from tests import test_hermes_preflight_audit as audit_fixtures


class ProfilePlanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = launch_fixtures.PreflightPlanTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.out = self.fixture.out
        self.fixture.creds['provider_profile'] = PROFILE

    def prepare(self):
        return preflight.prepare(self.out, target_model=self.fixture.creds['model'],
            model_base_url=self.fixture.creds['base_url'], provider_profile=PROFILE)

    def test_fixed_three_nonstreaming_workflows_and_unchanged_caps(self):
        manifest = self.prepare(); config = manifest['config']
        self.assertEqual((config['fixed_slots'], config['max_model_calls'], config['max_charged_tokens'], config['max_run_seconds']),
                         (3, 48, 750000, 1350))
        self.assertEqual(set(manifest['transports']), {'nonstreaming'})
        self.assertEqual([s['workflow'] for s in manifest['slots']], list(preflight.WORKFLOWS))
        self.assertTrue(all(s['mode'] == 'nonstreaming' for s in manifest['slots']))
        self.assertEqual(manifest['kind'], preflight.PROFILE_VERSION)
        self.assertEqual(manifest['provider_contract'], provider_contract(self.fixture.creds['model'], self.fixture.creds['base_url']))
        self.assertIn('scripts/audit_hermes_readback_v2.py', manifest['source_sha256'])
        self.assertEqual(preflight.verify_prepared(self.out), manifest)
        self.assertFalse((self.out / 'EXECUTION.json').exists())

    def test_profile_forwarded_to_every_fresh_task_without_gain_gate(self):
        self.prepare(); report = self.fixture.execute_fixture()
        self.assertEqual(report['status'], 'completed'); self.assertEqual(report['fixed_slots'], 3)
        self.assertEqual(len(self.fixture.seen), 3); self.assertFalse(report['capability_pass'])
        self.assertTrue(report['fixture'])
        for kwargs in self.fixture.seen:
            self.assertEqual(kwargs['provider_profile'], PROFILE); self.assertEqual(kwargs['hermes_transport'], 'nonstreaming')
            self.assertEqual((kwargs['max_iterations'], kwargs['max_tokens'], kwargs['max_total_tokens'], kwargs['timeout_seconds']),
                             (16, 4096, 250000, 420))
        with self.assertRaisesRegex(ValueError, 'one-shot'): self.fixture.execute_fixture()
        for path in self.out.rglob('*.json'):
            self.assertNotIn(self.fixture.creds['api_key'], path.read_text())

    def test_no_profile_creds_cannot_silently_execute_profile_registration(self):
        self.prepare(); self.fixture.creds.pop('provider_profile')
        with self.assertRaisesRegex(ValueError, 'provider policy'): self.fixture.execute_fixture()
        self.assertFalse((self.out / 'EXECUTION.json').exists())

    def test_mutated_mode_policy_or_slot_denominator_refused(self):
        manifest = self.prepare()
        for field in ('profile', 'thinking', 'mode', 'slots', 'readback'):
            changed = deepcopy(manifest)
            if field == 'profile': changed['config'].pop('provider_profile')
            elif field == 'thinking': changed['provider_contract']['chat_template_kwargs']['enable_thinking'] = True
            elif field == 'mode': changed['slots'][0]['mode'] = 'streaming'
            elif field == 'slots': changed['config']['fixed_slots'] = 1
            else: changed['readback_contract'] = 'unknown'
            preflight.save(self.out / 'manifest.json', changed)
            with self.subTest(field=field), self.assertRaises(ValueError): preflight.verify_prepared(self.out)
        self.assertFalse((self.out / 'EXECUTION.json').exists())

    def test_unknown_receipt_halts_preserving_three_slots_and_reservation(self):
        self.prepare(); report = self.fixture.execute_fixture(costs=[preflight.cost_receipt(None)])
        self.assertEqual(report['attempted_slots'], 1); self.assertEqual(len(report['slots']), 3)
        self.assertEqual(report['usage']['charged_or_reserved_model_calls'], 16)
        self.assertEqual(report['usage']['charged_or_reserved_tokens'], 250000)
        self.assertIsNone(report['usage']['total_tokens'])
        self.assertEqual(sum(s['status'] == 'not_attempted' for s in report['slots']), 2)

    def test_profile_total_deadline_keeps_full_next_slot_reservation(self):
        self.prepare()
        with patch.object(preflight.time, 'monotonic', side_effect=[0, 1000, 1000]), \
                patch.object(preflight, 'supervise', side_effect=AssertionError('No late dispatch')):
            report = preflight.execute(self.out, creds=self.fixture.creds, executor=launch_fixtures.fixture_executor)
        self.assertEqual(report['status'], 'halted_budget'); self.assertEqual(report['attempted_slots'], 0)


class ProfileNativeAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = audit_fixtures.PreflightEvidenceTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture; self.policy = provider_contract('offline-fixture', 'https://example.invalid')
        f.slot['mode'] = 'nonstreaming'
        f.manifest.update(provider_contract=self.policy, target_model=self.policy['model'], model_base_url=self.policy['base_url'],
            config={'provider_profile': PROFILE}, readback_contract=readback.VERSION,
            transports={'nonstreaming': contract('nonstreaming')}, source_sha256=source_hashes())
        f.record['provider_contract'] = self.policy
        native = f.record['result']['native']; native['provider_contract'] = self.policy
        f.record['hermes_transport'] = native['evaluation_transport'] = contract('nonstreaming')
        native['evaluation_budget']['provider_contract'] = self.policy
        native['evaluation_budget']['operations'][0].update(provider_contract=self.policy, request_api_mode='responses',
            request_model=self.policy['model'], request_base_url=self.policy['base_url'], request_stream=False,
            request_store=False, request_chat_template_kwargs={'enable_thinking': False})
        names = {'load': 'skill_view', 'commit': 'enterprise_action', 'readback': 'read_file'}
        for message in native['messages']:
            if message.get('role') == 'tool': message['name'] = names[message['tool_call_id']]

    def test_cleanup_ready_instance_must_bind_exact_provider_contract(self):
        f = self.fixture; trial, cleanup = f.cleanup_fixture()
        path = Path(cleanup['instance']['instance_path']); value = preflight.read(path)
        with self.assertRaises(ValueError):
            audit.cleanup_check(trial, f.slot, cleanup, provider_contract=self.policy)
        value['provider_contract'] = self.policy; preflight.save(path, value)
        cleanup['instance']['instance_sha256'] = preflight.sha(path)
        self.assertTrue(audit.cleanup_check(trial, f.slot, cleanup, provider_contract=self.policy))
        with self.assertRaisesRegex(ValueError, 'native_instance_provider_contract'):
            audit.cleanup_check(trial, f.slot, cleanup)
        value['provider_contract'] = deepcopy(self.policy); value['provider_contract']['store'] = 0
        preflight.save(path, value); cleanup['instance']['instance_sha256'] = preflight.sha(path)
        with self.assertRaises(ValueError): audit.cleanup_check(trial, f.slot, cleanup, provider_contract=self.policy)
        value['provider_contract'] = {**self.policy, 'model': 'wrong-model'}; preflight.save(path, value)
        cleanup['instance']['instance_sha256'] = preflight.sha(path)
        with self.assertRaisesRegex(ValueError, 'native_instance_provider_contract'):
            audit.cleanup_check(trial, f.slot, cleanup, provider_contract=self.policy)

    def test_profile_raw_session_policy_reconstructs_native_readback(self):
        self.assertTrue(self.fixture.inspect()['transport_roundtrip_capable'])
        self.fixture.record['result']['native']['evaluation_budget']['operations'][0]['request_chat_template_kwargs'] = {'enable_thinking': True}
        with self.assertRaisesRegex(ValueError, 'provider_physical'): self.fixture.inspect()

    def test_exact_native_warning_count_is_supported_but_arbitrary_suffix_is_not(self):
        f = self.fixture; messages = f.record['result']['native']['messages']
        # One matching read before commit, then native identical-result warning.
        before = deepcopy(messages[4:6]); before[0]['tool_calls'][0]['id'] = 'first-read'
        before[1]['tool_call_id'] = 'first-read'
        messages[2:2] = before; f.record['tool_calls'] += 1
        result = messages[7]; original = result['content']; result['content'] += readback.warning(2)
        self.assertTrue(f.inspect()['transport_roundtrip_capable'])
        result['content'] = original + ' arbitrary suffix'
        self.assertFalse(f.inspect()['transport_roundtrip_capable'])
        result['content'] = original + readback.warning(3)
        with self.assertRaisesRegex(ValueError, 'repeat_count_unproven'): f.inspect()

    def test_warning_compatibility_never_weakens_immutable_artifact_or_json_type(self):
        f = self.fixture; result = f.record['result']['native']['messages'][5]
        artifact = deepcopy(f.record['artifact']); artifact['redact'] = int(artifact['redact'])
        result['content'] = json.dumps({'content': json.dumps(artifact)})
        self.assertFalse(f.inspect()['transport_roundtrip_capable'])
        path = f.directory / 'filesystem_objects' / f.record['last_submitted_artifact_sha256']
        path.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'committed_artifact_hash_or_content'): f.inspect()


class ProfileCampaignAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = audit_fixtures.PreflightCampaignTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # This explicit outer-audit fixture mocks native evidence, never a live proof.
        f = self.fixture; f.root = f.root.parent / 'profile'
        f.manifest = preflight.prepare(f.root, target_model='offline-fixture', model_base_url='https://example.invalid',
                                      provider_profile=PROFILE)

    def flush(self):
        self.fixture.flush()
        path = self.fixture.root / 'REPORT.json'; report = preflight.read(path)
        report['fixed_slots'] = 3; preflight.save(path, report)

    def test_complete_profile_requires_all_three_fixed_slots_and_bound_registration(self):
        f = self.fixture; f.begin()
        for _ in range(3): f.add_receipt()
        self.flush(); result = audit.audit_preflight(f.root, strict=True, expected_manifest_sha256=preflight.sha(f.root / 'manifest.json'))
        self.assertTrue(result['ok'], result); self.assertEqual(len(result['slots']), 3)
        self.assertFalse(any(s['native_evidence']['semantic_success'] for s in result['slots']))
        self.assertFalse(audit.audit_preflight(f.root, strict=True, expected_manifest_sha256='0'*64)['ok'])

    def test_subset_cannot_be_completed_profile_proof(self):
        f = self.fixture; f.begin(); f.add_receipt(); self.flush()
        result = audit.audit_preflight(f.root, strict=True)
        self.assertFalse(result['ok']); self.assertEqual(len(result['slots']), 3)
        self.assertFalse(result['capability_pass'])


if __name__ == '__main__':
    unittest.main()
