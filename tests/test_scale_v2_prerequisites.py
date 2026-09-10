"""Gate binding regressions; synthetic references, no native or provider work."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import scale_v2_prerequisites as gate


class GateTests(unittest.TestCase):
    def test_actor_manifest_is_bound_before_importing_its_historical_auditor(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source'; source.mkdir()
            (root / 'manifest.json').write_text('{}')
            (root / 'EVIDENCE.json').write_text('{}')
            summary = {'manifest_sha256': gate.sha(root / 'manifest.json'),
                       'evidence_inventory_sha256': gate.sha(root / 'EVIDENCE.json')}
            (root / 'SUMMARY.json').write_text(json.dumps(summary)); review = root / 'review.json'
            review.write_text('{}')
            campaign = {'launch_policy': {'evidence': [{'kind': 'actor_native_capability',
                'artifact_sha256': gate.sha(root / 'SUMMARY.json'), 'review_sha256': gate.sha(review)}]}}
            for name in ('manifest.json', 'EVIDENCE.json'):
                path = root / name; original = path.read_bytes(); path.write_text('{"mutated": true}')
                with patch.object(gate.subprocess, 'run', side_effect=AssertionError('untrusted auditor executed')) as call:
                    with self.assertRaisesRegex(ValueError, 'actor_reviewed_manifest_or_inventory_changed'):
                        gate.actor_check(campaign, directory=root, source_root=source, review_file=review)
                    call.assert_not_called()
                path.write_bytes(original)

    def test_employee_inventory_must_be_reviewed_and_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = root / 'original'; original.mkdir()
            observation = root / 'observation'; observation.mkdir(); review = root / 'review.json'
            def save(path, value): path.write_text(json.dumps(value, sort_keys=True))
            manifest = {'target_model': 'fixture', 'model_base_url': 'https://example.invalid', 'source_sha256': {}}
            save(original / 'manifest.json', manifest)
            saved = {'manifest_sha256': gate.sha(original / 'manifest.json'), 'ok': True, 'capability_pass': True,
                'original_report_capability_pass': False, 'correction_source_sha256': 'f' * 64,
                'usage': {'physical_model_calls': 1, 'total_tokens': 1}, 'elapsed_seconds': 1}
            save(observation / 'AUDIT.json', saved)
            inventory = {'files': {'manifest.json': gate.sha(original / 'manifest.json')}}
            save(observation / 'original_inventory.json', inventory)
            save(review, {'manifest_sha256': saved['manifest_sha256'], 'private_corrected_audit_sha256': gate.sha(observation/'AUDIT.json'),
                'private_original_inventory_sha256': gate.sha(observation/'original_inventory.json'), 'original_regular_files_hashed': 1})
            campaign = {**manifest, 'launch_policy': {'evidence': [{'kind': 'employee_native_capability',
                'artifact_sha256': gate.sha(observation/'AUDIT.json'), 'review_sha256': gate.sha(review)}]}}
            def check():
                return gate.employee_check(campaign, original_directory=original,
                    observation_directory=observation, review_file=review)
            with patch.object(gate, 'employee_audit', return_value=saved):
                self.assertTrue(check()['verified'])
                save(observation/'original_inventory.json', {'files': {}})
                with self.assertRaisesRegex(ValueError, 'employee_reviewed_manifest_or_inventory_changed'): check()
                save(observation/'original_inventory.json', inventory)
                extra = original/'extra'; extra.write_text('unreviewed')
                with self.assertRaisesRegex(ValueError, 'employee_preflight_original_inventory_not_exact'): check()
                extra.unlink(); extra.symlink_to(review)
                with self.assertRaisesRegex(ValueError, 'employee_preflight_original_inventory_not_exact'): check()

    def test_reviewed_hash_binds_both_artifact_and_independent_review(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/'artifact', Path(temp)/'review'
            a.write_text('synthetic evidence'); b.write_text('synthetic review')
            reference = {'kind': 'fixture', 'artifact_sha256': gate.sha(a), 'review_sha256': gate.sha(b)}
            campaign = {'launch_policy': {'evidence': [reference]}}
            self.assertEqual(gate.reviewed_reference(campaign, 'fixture', a, b), reference)
            for target in (a, b):
                original = target.read_bytes(); target.write_bytes(original + b' changed')
                with self.assertRaises(ValueError): gate.reviewed_reference(campaign, 'fixture', a, b)
                target.write_bytes(original)

    def test_path_inventory_and_all_three_gates_are_required(self):
        paths = {'actor': {'directory': '/fixture/a', 'source_root': '/fixture/b', 'review_file': '/fixture/c'},
            'employee': {'original_directory': '/fixture/d', 'observation_directory': '/fixture/e', 'review_file': '/fixture/f'},
            'horizon': {'directory': '/fixture/g', 'review_file': '/fixture/h'}}
        with patch.object(gate, 'actor_check', return_value={'verified': True}) as actor, patch.object(
            gate, 'employee_check', return_value={'verified': True}) as employee, patch.object(
            gate, 'horizon_check', return_value={'verified': True}) as horizon:
            result = gate.verify_prerequisites({}, paths)
            self.assertTrue(result['verified']); self.assertEqual(len(result['checks']), 3)
            for callback in (actor, employee, horizon): callback.assert_called_once()
            employee.return_value = {'verified': False}
            with self.assertRaises(ValueError): gate.verify_prerequisites({}, paths)
        for mutation in (lambda p: p.pop('horizon'), lambda p: p['actor'].update(directory='relative'),
                         lambda p: p['employee'].update(unreviewed='/fixture')):
            bad = deepcopy(paths); mutation(bad)
            with self.assertRaises(ValueError): gate.verify_prerequisites({}, bad)


if __name__ == '__main__': unittest.main()
