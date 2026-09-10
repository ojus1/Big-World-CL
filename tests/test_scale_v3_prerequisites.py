"""Synthetic raw/source fixtures; never invokes an actor, provider or native worker."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch

from scripts import scale_v3_prerequisites as check


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


class PrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / 'original'
        self.artifact = self.root / 'compatibility.json'
        self.review = self.root / 'review.json'
        old = {name: 'a' * 64 for name in check.CHANGED_LIBRARY_FILES
               if name != 'lifespan/startup_observability.py'}
        old['lifespan/evaluation/tasks.py'] = 'c' * 64
        current = {**old, **{name: 'b' * 64 for name in check.CHANGED_LIBRARY_FILES}}
        self.historical = {'source_sha256': old, 'target_model': 'fixture-model',
                           'model_base_url': 'https://example.invalid/v1'}
        write(self.original / 'manifest.json', self.historical)
        self.campaign = {'source_sha256': current, 'registration_tools_sha256': {},
            'dependencies': {'hermes': {'revision': 'd' * 40}},
            'target_model': 'fixture-model', 'model_base_url': 'https://example.invalid/v1',
            'launch_policy': {'evidence': []}}
        self.compatible = {'schema_version': 1, 'kind': 'employee-startup-source-compatibility',
            'historical_manifest_sha256': check.sha(self.original / 'manifest.json'),
            'historical_library_sha256': old, 'current_library_sha256': current,
            'changes': {name: {'before_sha256': old.get(name), 'after_sha256': current[name]}
                        for name in check.CHANGED_LIBRARY_FILES}}
        self.approval = {'artifact_sha256': None, 'decision': 'compatible_for_prospective_evaluation',
            'new_native_provider_observation': False, 'reviewed_source_changes': sorted(check.CHANGED_LIBRARY_FILES)}
        self.save_compatibility()
        self.startup = self.root / 'startup'
        self.startup_review = self.root / 'startup-review.json'
        self.startup_manifest = {'source_sha256': deepcopy(current),
            'dependencies': deepcopy(self.campaign['dependencies']), 'boot_id': 'fixture-boot',
            'caller_security_context': 'fixture-label'}
        write(self.startup / 'manifest.json', self.startup_manifest)
        write(self.startup / 'REPORT.json', {'fixture_only': True})
        write(self.startup_review, {'manifest_sha256': check.sha(self.startup / 'manifest.json'),
            'report_sha256': check.sha(self.startup / 'REPORT.json'), 'qualification_passed': True})
        self.reference('scope_startup_qualification', self.startup / 'REPORT.json', self.startup_review)
        self.qualified = {'ok': True, 'qualification_passed': True, 'status': 'completed',
                          'slots': [{'qualification_passed': True} for _ in range(9)]}

    def reference(self, kind, artifact, review):
        rows = self.campaign['launch_policy']['evidence']
        rows[:] = [row for row in rows if row['kind'] != kind]
        rows.append({'kind': kind, 'artifact_sha256': check.sha(artifact), 'review_sha256': check.sha(review)})

    def save_compatibility(self):
        write(self.artifact, self.compatible)
        self.approval['artifact_sha256'] = check.sha(self.artifact)
        write(self.review, self.approval)
        self.reference('employee_source_compatibility', self.artifact, self.review)

    def compatibility(self):
        return check.compatibility_check(self.campaign, artifact_file=self.artifact,
            review_file=self.review, original_directory=self.original)

    def startup_check(self, actual=None):
        from scripts import hermes_startup_scope_qualification_v3 as scope
        with patch.object(scope, 'audit_qualification', return_value=actual or self.qualified) as audit:
            answer = check.startup_check(self.campaign, directory=self.startup, review_file=self.startup_review)
            audit.assert_called_once_with(self.startup, manifest_sha256=check.sha(self.startup / 'manifest.json'), strict=True)
            return answer

    def test_exact_source_review_is_historical_not_new_provider_evidence(self):
        result = self.compatibility()
        self.assertTrue(result['verified'])
        self.assertEqual(result['changed_files'], sorted(check.CHANGED_LIBRARY_FILES))
        self.assertIn('not_a_new_provider_observation', result['scope'])
        self.assertEqual(result['historical_manifest_sha256'], check.sha(self.original / 'manifest.json'))

    def test_fixed_review_raw_hash_is_required(self):
        self.review.write_text(self.review.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'reviewed_reference_mismatch'): self.compatibility()

    def test_artifact_raw_hash_and_historical_manifest_are_required(self):
        self.artifact.write_text(self.artifact.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'reviewed_reference_mismatch'): self.compatibility()
        self.save_compatibility()
        write(self.original / 'manifest.json', {**self.historical, 'extra': 'fixture'})
        with self.assertRaisesRegex(ValueError, 'history_mismatch'): self.compatibility()

    def test_same_file_inventory_does_not_allow_an_unreviewed_hash(self):
        self.campaign['source_sha256'] = deepcopy(self.campaign['source_sha256'])
        self.campaign['source_sha256']['lifespan/computers.py'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'library_changed'): self.compatibility()

    def test_added_or_removed_changed_file_cannot_be_coherently_rehashed(self):
        self.compatible['current_library_sha256'] = deepcopy(self.compatible['current_library_sha256'])
        self.compatible['current_library_sha256']['lifespan/evaluation/tasks.py'] = 'f' * 64
        self.campaign['source_sha256'] = deepcopy(self.compatible['current_library_sha256'])
        self.compatible['changes']['lifespan/evaluation/tasks.py'] = {
            'before_sha256': 'c' * 64, 'after_sha256': 'f' * 64}
        self.save_compatibility()
        with self.assertRaisesRegex(ValueError, 'unreviewed_employee_library_change'): self.compatibility()

    def test_missing_new_observer_file_is_not_the_reviewed_delta(self):
        self.compatible['current_library_sha256'] = deepcopy(self.compatible['current_library_sha256'])
        self.compatible['current_library_sha256'].pop('lifespan/startup_observability.py')
        self.campaign['source_sha256'] = deepcopy(self.compatible['current_library_sha256'])
        self.compatible['changes'].pop('lifespan/startup_observability.py'); self.save_compatibility()
        with self.assertRaisesRegex(ValueError, 'unreviewed_employee_library_change'): self.compatibility()

    def test_each_before_and_after_hash_is_reconciled(self):
        for field in ('before_sha256', 'after_sha256'):
            original = deepcopy(self.compatible)
            self.compatible['changes']['lifespan/computers.py'][field] = 'f' * 64; self.save_compatibility()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'delta_changed'): self.compatibility()
            self.compatible = original

    def test_review_cannot_be_pending_or_claim_a_new_provider_run(self):
        for key, value in (('decision', 'pending'), ('new_native_provider_observation', True),
                           ('reviewed_source_changes', []), ('artifact_sha256', 'f' * 64)):
            approval = deepcopy(self.approval); approval[key] = value; write(self.review, approval)
            self.reference('employee_source_compatibility', self.artifact, self.review)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'review_missing'): self.compatibility()

    def test_fresh_complete_nine_slot_qualification_is_required_separately(self):
        result = self.startup_check()
        self.assertTrue(result['verified']); self.assertEqual(result['qualified_slots'], 9)
        self.assertIn('not_provider_or_long_horizon', result['scope'])
        self.compatibility()  # Its pass does not stand in for the next check.
        for key, value in (('ok', False), ('qualification_passed', False), ('status', 'incomplete'),
                           ('slots', self.qualified['slots'][:8]),
                           ('slots', [{'qualification_passed': False}] + self.qualified['slots'][1:])):
            actual = deepcopy(self.qualified); actual[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'qualification_not_complete'):
                self.startup_check(actual)

    def test_qualification_source_and_hermes_revision_cannot_drift(self):
        for changes in ({'source_sha256': {}}, {'dependencies': {'hermes': {'revision': 'f' * 40}}}):
            saved = deepcopy(self.campaign); self.campaign.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.startup_check()
            self.campaign = saved

    def test_qualification_review_is_bound_to_raw_manifest_report_and_pass(self):
        original = check.read(self.startup_review)
        for key, value in (('manifest_sha256', 'f' * 64), ('report_sha256', 'f' * 64),
                           ('qualification_passed', False)):
            value = {**original, key: value}; write(self.startup_review, value)
            self.reference('scope_startup_qualification', self.startup / 'REPORT.json', self.startup_review)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'review_mismatch'): self.startup_check()

    def test_duplicate_reference_fails_instead_of_choosing_a_pass(self):
        self.campaign['launch_policy']['evidence'].append(
            deepcopy(self.campaign['launch_policy']['evidence'][0]))
        with self.assertRaisesRegex(ValueError, 'reviewed_reference_mismatch'): self.compatibility()

    def test_orchestration_has_no_failed_or_missing_qualification_bypass(self):
        paths = {'actor': {'directory': '/fixture/a', 'source_root': '/fixture/source', 'review_file': '/fixture/ar'},
            'employee': {'original_directory': '/fixture/e', 'observation_directory': '/fixture/o', 'review_file': '/fixture/er'},
            'horizon': {'directory': '/fixture/h', 'review_file': '/fixture/hr'},
            'startup': {'directory': '/fixture/s', 'review_file': '/fixture/sr'},
            'compatibility': {'artifact_file': '/fixture/c', 'review_file': '/fixture/cr'}}
        with patch.object(check, 'compatibility_check', return_value={'verified': True}), patch.object(
                check, 'startup_check', side_effect=ValueError('fixture_failed_startup')), patch.object(check, 'actor_check') as actor:
            with self.assertRaisesRegex(ValueError, 'failed_startup'): check.verify_prerequisites(self.campaign, paths)
            actor.assert_not_called()
        paths.pop('startup')
        with self.assertRaisesRegex(ValueError, 'path_inventory'): check.verify_prerequisites(self.campaign, paths)

    def test_all_five_checks_are_mandatory_and_failed_flags_do_not_pass(self):
        paths = {'actor': {'directory': '/fixture/a', 'source_root': '/fixture/source', 'review_file': '/fixture/ar'},
            'employee': {'original_directory': '/fixture/e', 'observation_directory': '/fixture/o', 'review_file': '/fixture/er'},
            'horizon': {'directory': '/fixture/h', 'review_file': '/fixture/hr'},
            'startup': {'directory': '/fixture/s', 'review_file': '/fixture/sr'},
            'compatibility': {'artifact_file': '/fixture/c', 'review_file': '/fixture/cr'}}
        from contextlib import ExitStack
        names = ('compatibility_check', 'startup_check', 'actor_check', 'employee_check', 'horizon_check')
        for failed in (None, *names):
            with self.subTest(failed=failed), ExitStack() as stack:
                mocks = {name: stack.enter_context(patch.object(check, name,
                    return_value={'verified': name != failed, 'fixture_scope': name})) for name in names}
                if failed:
                    with self.assertRaisesRegex(ValueError, 'prerequisites_not_verified'):
                        check.verify_prerequisites(self.campaign, paths)
                else:
                    result = check.verify_prerequisites(self.campaign, paths)
                    self.assertTrue(result['verified']); self.assertEqual(len(result['checks']), 5)
                for mock in mocks.values(): mock.assert_called_once()

    def test_historical_employee_still_requires_exact_raw_provider_audit(self):
        observation = self.root / 'employee-observation'; employee_review = self.root / 'employee-review.json'
        mh = check.sha(self.original / 'manifest.json')
        inventory = {'files': {'manifest.json': mh}}
        write(observation / 'original_inventory.json', inventory)
        expected = {'ok': True, 'capability_pass': True, 'manifest_sha256': mh,
            'original_report_capability_pass': False, 'correction_source_sha256': {'fixture.py': 'a' * 64},
            'usage': {'physical_model_calls': 1, 'total_tokens': 10}, 'elapsed_seconds': 1}
        write(observation / 'AUDIT.json', expected)
        write(employee_review, {'private_corrected_audit_sha256': check.sha(observation / 'AUDIT.json'),
            'manifest_sha256': mh, 'private_original_inventory_sha256': check.sha(observation / 'original_inventory.json'),
            'original_regular_files_hashed': 1})
        self.reference('employee_native_capability', observation / 'AUDIT.json', employee_review)
        def audit(value, compatibility=None):
            with patch.object(check, '_historical_employee_audit', return_value=value):
                return check.employee_check(self.campaign, original_directory=self.original,
                    observation_directory=observation, review_file=employee_review,
                    compatibility=compatibility or {'historical_manifest_sha256': mh, 'verified': True})
        result = audit(expected)
        self.assertTrue(result['capability_pass']); self.assertFalse(result['original_capability_pass'])
        with self.assertRaisesRegex(ValueError, 'corrected_audit_changed_or_failed'):
            audit({**expected, 'capability_pass': False})
        with self.assertRaisesRegex(ValueError, 'compatibility_manifest_mismatch'):
            audit(expected, {'historical_manifest_sha256': 'f' * 64, 'verified': True})
        def change_reviewed_bytes(*args):
            target = observation / 'AUDIT.json'; target.write_text(target.read_text() + '\n')
            return expected
        with patch.object(check, '_historical_employee_audit', side_effect=change_reviewed_bytes):
            with self.assertRaisesRegex(ValueError, 'reviewed_observation_changed_during_audit'):
                check.employee_check(self.campaign, original_directory=self.original,
                    observation_directory=observation, review_file=employee_review,
                    compatibility={'historical_manifest_sha256': mh, 'verified': True})
        write(observation / 'AUDIT.json', expected)
        write(self.original / 'extra.json', {'fixture': True})
        with self.assertRaisesRegex(ValueError, 'inventory_not_exact'): audit(expected)


class HistoricalAuditTests(unittest.TestCase):
    """Fake source packages; real isolated Python bootstrap, never native code."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.historical = self.root / 'historical'; self.current = self.root / 'current'
        self.original = self.historical / 'lifespan/artifacts/fixture'
        self.original.mkdir(parents=True)
        self.current.joinpath('scripts').mkdir(parents=True)
        self.contents = {
            'lifespan/__init__.py': b"MARKER='historical_lifespan'\n",
            'scripts/hermes_transport_preflight.py': b"MARKER='historical_launcher'\n",
            'scripts/audit_hermes_preflight.py': (
                b"def audit():\n"
                b" from scripts import hermes_transport_preflight as launcher\n"
                b" from lifespan import MARKER\n"
                b" return {'ok':True,'capability_pass':True,'markers':[MARKER,launcher.MARKER]}\n")}
        for name, raw in self.contents.items():
            path = self.historical / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        # If the correction's own path wins, these imports fail immediately.
        for name in self.contents:
            path = self.current / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("raise RuntimeError('wrong_current_package')\n")
        self.correction = self.current / 'scripts/audit_hermes_readback_v2.py'
        self.correction.write_text(
            'from pathlib import Path\nimport sys\n'
            'ROOT=Path(__file__).resolve().parents[1]\nsys.path.insert(0,str(ROOT))\n'
            'from scripts.audit_hermes_preflight import audit as original\n'
            'def audit(directory, *, manifest_sha256):\n return original()\n')
        self.manifest = {'source_commit_verified': True, 'repository_commit': 'a' * 40,
            'source_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in self.contents.items()}}
        write(self.original / 'manifest.json', self.manifest)
        self.saved = {'manifest_sha256': check.sha(self.original / 'manifest.json'),
            'correction_source_sha256': check.sha(self.correction)}

    def git(self, argv, **kwargs):
        self.assertEqual(argv[0], 'git')
        if argv[-2:] == ['rev-parse', '--show-toplevel']: return str(self.historical) + '\n'
        self.assertEqual(argv[3], 'show')
        commit, name = argv[4].split(':', 1); self.assertEqual(commit, self.manifest['repository_commit'])
        return self.contents[name]

    def invoke(self, git=None):
        with patch.object(check, '__file__', str(self.current / 'scripts/scale_v3_prerequisites.py')), patch.object(
                check.subprocess, 'check_output', side_effect=git or self.git):
            return check._historical_employee_audit(self.original, self.saved)

    def test_actual_isolated_bootstrap_keeps_both_historical_packages(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.invoke()
        self.assertEqual(result, {'ok': True, 'capability_pass': True,
                                 'markers': ['historical_lifespan', 'historical_launcher']})
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                 for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.original / '.readonly-audit-no-bytecode').exists())

    def test_correction_bytes_are_bound_before_subprocess(self):
        self.correction.write_text(self.correction.read_text() + '\n')
        with patch.object(check.subprocess, 'run') as launch:
            with self.assertRaisesRegex(ValueError, 'reviewed_correction_source_changed'): self.invoke()
            launch.assert_not_called()

    def test_historical_working_and_committed_bytes_are_both_required(self):
        target = self.historical / 'lifespan/__init__.py'; old = target.read_bytes(); target.write_bytes(old + b'\n')
        with patch.object(check.subprocess, 'run') as launch:
            with self.assertRaisesRegex(ValueError, 'source_unavailable_or_changed'): self.invoke()
            launch.assert_not_called()
        target.write_bytes(old)
        def changed_commit(argv, **kwargs):
            value = self.git(argv, **kwargs)
            return value + b'\n' if argv[3] == 'show' else value
        with patch.object(check.subprocess, 'run') as launch:
            with self.assertRaisesRegex(ValueError, 'committed_source_changed'): self.invoke(changed_commit)
            launch.assert_not_called()

    def test_unbound_commit_package_init_and_source_paths_fail_closed(self):
        for change, code in (({'source_commit_verified': False}, 'historical_commit_unbound'),
                             ({'repository_commit': 'not-a-commit'}, 'historical_commit_unbound'),
                             ({'source_sha256': {}}, 'historical_auditor_unbound')):
            write(self.original / 'manifest.json', {**self.manifest, **change})
            with patch.object(check.subprocess, 'run') as launch:
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, code): self.invoke()
                launch.assert_not_called()
        write(self.original / 'manifest.json', self.manifest)
        (self.historical / 'scripts/__init__.py').write_text('raise RuntimeError("unbound")\n')
        with self.assertRaisesRegex(ValueError, 'historical_package_changed'): self.invoke()
        (self.historical / 'scripts/__init__.py').unlink()
        changed = deepcopy(self.manifest); changed['source_sha256']['../escape.py'] = 'b' * 64
        write(self.original / 'manifest.json', changed)
        with self.assertRaisesRegex(ValueError, 'historical_source_path'): self.invoke()

    def test_symlinked_historical_source_and_correction_are_rejected(self):
        source = self.historical / 'lifespan/__init__.py'; other = self.root / 'same-source.py'
        other.write_bytes(source.read_bytes()); source.unlink(); source.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'source_unavailable_or_changed'): self.invoke()
        source.unlink(); source.write_bytes(other.read_bytes())
        replacement = self.root / 'same-correction.py'; replacement.write_bytes(self.correction.read_bytes())
        self.correction.unlink(); self.correction.symlink_to(replacement)
        with self.assertRaisesRegex(ValueError, 'reviewed_correction_source_changed'): self.invoke()

    def test_shadow_package_is_rejected_before_its_canary_runs(self):
        canary = self.root / 'UNBOUND-CANARY'
        shadow = self.historical / 'scripts/audit_hermes_preflight/__init__.py'
        shadow.parent.mkdir(); shadow.write_text(f'from pathlib import Path\nPath({str(canary)!r}).touch()\n')
        with patch.object(check.subprocess, 'run') as launch:
            with self.assertRaisesRegex(ValueError, 'historical_module_shadow'): self.invoke()
            launch.assert_not_called()
        self.assertFalse(canary.exists())

    def test_unregistered_historical_import_cannot_execute(self):
        canary = self.root / 'UNBOUND-CANARY'
        extra = self.historical / 'scripts/unbound_fixture.py'
        extra.write_text(f'from pathlib import Path\nPath({str(canary)!r}).touch()\n')
        self.correction.write_text(self.correction.read_text().replace('return original()',
            'import scripts.unbound_fixture\n return original()'))
        self.saved['correction_source_sha256'] = check.sha(self.correction)
        with self.assertRaisesRegex(ValueError, '^employee_historical_raw_audit_failed$'): self.invoke()
        self.assertFalse(canary.exists())

    def test_subprocess_is_bounded_isolated_and_does_not_expose_stderr(self):
        with patch.object(check.subprocess, 'run', side_effect=subprocess.TimeoutExpired(
                'fixture', 30, stderr='PRIVATE_FIXTURE_TEXT')) as launch:
            with self.assertRaisesRegex(ValueError, '^employee_historical_raw_audit_failed$'): self.invoke()
            args, kwargs = launch.call_args
            self.assertEqual(args[0][1:4], ['-I', '-B', '-c'])
            self.assertEqual(kwargs['timeout'], 30)
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            self.assertTrue(kwargs['check'])

    def test_post_audit_source_drift_and_invalid_output_are_rejected(self):
        def mutate(*args, **kwargs):
            source = self.historical / 'lifespan/__init__.py'; source.write_bytes(source.read_bytes() + b'\n')
            return subprocess.CompletedProcess([], 0, stdout='{}')
        with patch.object(check.subprocess, 'run', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'source_changed_during_audit'): self.invoke()
        (self.historical / 'lifespan/__init__.py').write_bytes(self.contents['lifespan/__init__.py'])
        for output, code in (('[]', 'audit_output_shape'), ('not json', 'historical_raw_audit_failed')):
            with patch.object(check.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=output)):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, code): self.invoke()


if __name__ == '__main__':
    unittest.main()
