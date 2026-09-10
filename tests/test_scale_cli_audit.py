"""Offline alias/launch tamper fixtures; no native calls or performance evidence."""
from copy import deepcopy
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lifespan.evaluation.protocol import ExperimentConfig, scenario
from lifespan.evaluation.runner import _new_state
from lifespan.mirofish import save
from scripts import audit_scale_cli as cli, run_scale


class CliAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp)
        sources = {'scripts/audit_scale.py': cli.FROZEN_AUDITOR_SHA256,
                   'scripts/run_scale.py': cli.FROZEN_LAUNCHER_SHA256,
                   'lifespan/evaluation/runner.py': cli.FROZEN_RUNNER_SHA256,
                   **{f'offline-fixture-{i}.py': '0' * 64 for i in range(31)}}
        self.manifest = {'slots': [], 'source_sha256': sources, 'dependencies': {'fixture': 'offline'},
                         'target_model': 'offline-model', 'model_base_url': 'https://offline.example.invalid'}
        self.receipt = {'schema_version': 1, 'kind': 'observed_native_module_launch',
            'observation_kind': 'during_execution_not_preregistered', 'observed_at': '2030-01-01T00:01:00+00:00',
            'published_commit': cli.PUBLISHED_COMMIT, 'source_sha256': sources, 'boot_id': 'offline-fixture-boot',
            'clock_ticks_per_second': 100, 'supervisor': {'pid': 100, 'start_ticks': 1000}, 'runs': []}
        for seed in (211, 307, 401):
            save(self.root / 'cohorts' / f'{seed}.json', {'fixture': 'private-synthetic-persona-' + str(seed)})
            for arm in ('no_learning', 'skillopt'):
                run_id = f'seed-{seed}-{arm}'; run = self.root / 'runs' / run_id
                save(run / 'persona_cohort.json', json.loads((self.root / 'cohorts' / f'{seed}.json').read_text()))
                cfg = run_scale.study_config(seed, arm).public(); save(run / 'config.json', cfg)
                slot = {'seed': seed, 'algorithm': arm, 'run_id': run_id, 'relative_path': 'runs/' + run_id,
                        'config': cfg, 'config_sha256': 'offline-config-hash',
                        'persona_cohort_sha256': cli.sha(run / 'persona_cohort.json')}
                self.manifest['slots'].append(slot)
                python = cli.ROOT / 'MiroFish/backend/.venv/bin/python'
                row = {key: slot[key] for key in ('seed', 'algorithm', 'run_id', 'config_sha256', 'persona_cohort_sha256')}
                row.update(pid=200 + len(self.receipt['runs']), parent_pid=100, start_ticks=2000,
                    executable=str(python.resolve()), cwd=str(cli.ROOT),
                    argv=[str(python), '-u', '-m', 'lifespan.evaluation.runner', '--out', str(run), '--config', str(run / 'config.json')])
                self.receipt['runs'].append(row)
                provenance = {key: self.manifest[key] for key in ('source_sha256', 'dependencies', 'target_model', 'model_base_url')}
                provenance.update(actor_driver=cli.ALIAS, executor=cli.EXECUTOR, persona_cohort_sha256=slot['persona_cohort_sha256'])
                save(run / 'REPORT.json', {'status': 'completed', 'provenance': provenance})
        save(self.root / 'campaign.json', self.manifest)
        self.campaign_sha = cli.sha(self.root / 'campaign.json')
        save(self.root / 'EXECUTION.json', {'supervisor_pid': 100, 'started_at': '2030-01-01T00:00:00+00:00'})
        self.receipt.update(campaign_sha256=self.campaign_sha, execution_sha256=cli.sha(self.root / 'EXECUTION.json'))
        save(self.root / 'CLI_LAUNCH_RECEIPTS.json', self.receipt)
        self.enterContext(patch.object(cli, 'CAMPAIGN_SHA256', self.campaign_sha))
        self.receipt_patch = self.enterContext(patch.object(cli, 'LAUNCH_RECEIPTS_SHA256', cli.sha(self.root / 'CLI_LAUNCH_RECEIPTS.json')))

    def test_launch_observation_semantics_accept_exact_commands(self):
        self.assertEqual(cli.launch_check(self.root, self.manifest), self.receipt)
        cli.independent_native_binding(self.root, self.manifest)

    def test_launch_receipt_raw_tamper_is_rejected(self):
        receipt = deepcopy(self.receipt); receipt['runs'][0]['pid'] += 50
        save(self.root / 'CLI_LAUNCH_RECEIPTS.json', receipt)
        with self.assertRaisesRegex(ValueError, 'bytes_changed'):
            cli.launch_check(self.root, self.manifest)

    def test_even_rehashed_wrong_argv_parent_identity_or_preregistration_is_rejected(self):
        mutations = [lambda r: r['runs'][0]['argv'].__setitem__(3, 'other.module'),
            lambda r: r['runs'][0].update(parent_pid=999), lambda r: r['runs'][0].update(start_ticks=10),
            lambda r: r['runs'][1].update(pid=r['runs'][0]['pid']),
            lambda r: r.update(observation_kind='preregistered'),
            lambda r: r.update(observed_at='2029-12-01T00:00:00+00:00'),
            lambda r: r['source_sha256'].update({'scripts/run_scale.py': '0' * 64})]
        for mutate in mutations:
            receipt = deepcopy(self.receipt); mutate(receipt)
            save(self.root / 'CLI_LAUNCH_RECEIPTS.json', receipt)
            with patch.object(cli, 'LAUNCH_RECEIPTS_SHA256', cli.sha(self.root / 'CLI_LAUNCH_RECEIPTS.json')):
                with self.assertRaises(ValueError):
                    cli.launch_check(self.root, self.manifest)

    def test_wrong_actor_executor_and_cohort_cannot_use_alias_exception(self):
        path = self.root / self.manifest['slots'][0]['relative_path'] / 'REPORT.json'
        original = json.loads(path.read_text())
        for key, value in [('actor_driver', 'fixture.NativeActors'), ('actor_driver', cli.CANONICAL),
                           ('executor', 'fixture.execute_case'), ('persona_cohort_sha256', '0' * 64),
                           ('target_model', 'other-model')]:
            altered = deepcopy(original); altered['provenance'][key] = value; save(path, altered)
            with self.assertRaises(ValueError):
                cli.independent_native_binding(self.root, self.manifest)

    def test_pair_cohort_file_tamper_is_rejected_independently(self):
        path = self.root / self.manifest['slots'][0]['relative_path'] / 'persona_cohort.json'
        save(path, {'fixture': 'different-persona'})
        with self.assertRaisesRegex(ValueError, 'paired_cohort'):
            cli.independent_native_binding(self.root, self.manifest)

    def stubbed_completed_run(self, namespace):
        """Stub the separately tested native checks to reach the actual guard."""
        slot = self.manifest['slots'][0]; run = self.root / slot['relative_path']
        cfg = ExperimentConfig(**slot['config']); spec = scenario(cfg); eco, state = _new_state(cfg, spec)
        cp = {'ecosystem': eco.checkpoint(), 'runner': state}; cp['ecosystem']['day'] = 21
        save(run / 'checkpoint.json', cp)
        save(run / 'manifest.json', {'config': cfg.public(), 'scenario': spec,
                                    **{k: self.manifest[k] for k in ('source_sha256', 'dependencies', 'target_model', 'model_base_url')}})
        save(run / 'REPORT.v2.json', {'fixture': 'not-a-real-report'})
        namespace['audit_run'] = lambda *a, **k: {'ok': True}
        namespace['actor_check'] = lambda *a, **k: {'logical_requests': 0}
        namespace['build_scale_summary'] = lambda *a, **k: {'complete': True, 'evidence_issues': [], 'observed_learning_boundaries': 48}
        namespace['eligibility_check'] = lambda *a, **k: None
        namespace['load_verified_report_v2'] = lambda *a: {'correction_audit': {'eligible_for_paired_inference': True},
            'source_breakdown': {'fixed_initial_and_benchmark': {'accepted_before_work_horizon': 240}}}
        return namespace['run_check'](self.root, self.manifest, slot)

    def test_exact_frozen_ast_corrects_only_actor_guard_and_retains_siblings(self):
        with self.assertRaisesRegex(ValueError, 'non_native_or_wrong_cohort_execution'):
            self.stubbed_completed_run(cli.isolated_auditor(False))
        self.assertTrue(self.stubbed_completed_run(cli.isolated_auditor(True))[0]['completed'])
        path = self.root / self.manifest['slots'][0]['relative_path'] / 'REPORT.json'; original = json.loads(path.read_text())
        for key in ('executor', 'persona_cohort_sha256'):
            report = deepcopy(original); report['provenance'][key] = 'tampered'; save(path, report)
            with self.assertRaisesRegex(ValueError, 'non_native_or_wrong_cohort_execution'):
                self.stubbed_completed_run(cli.isolated_auditor(True))

    def test_unsupported_frozen_auditor_hash_refuses_adapter(self):
        with patch.object(cli, 'FROZEN_AUDITOR_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'unsupported_frozen_auditor_revision'):
                cli.isolated_auditor(True)

    def test_multiple_matching_actor_guards_refuse_correction(self):
        tree = ast.parse((cli.ROOT / 'scripts/audit_scale.py').read_text())
        tree.body.append(ast.Expr(value=ast.Compare(
            left=ast.Subscript(value=ast.Name(id='provenance', ctx=ast.Load()),
                               slice=ast.Constant(value='actor_driver'), ctx=ast.Load()),
            ops=[ast.Eq()], comparators=[ast.Constant(value=cli.CANONICAL)])))
        with patch.object(cli.ast, 'parse', return_value=tree):
            with self.assertRaisesRegex(ValueError, 'unsupported_actor_guard_structure'):
                cli.isolated_auditor(True)

    def test_original_audit_is_retained_and_raw_bytes_never_rewritten(self):
        original = {'status': 'invalid', 'ok': False, 'errors': [{'code': 'non_native_or_wrong_cohort_execution'}]}
        save(self.root / 'AUDIT.json', original)
        before = {str(path): path.read_bytes() for path in self.root.rglob('*.json')}
        corrected = {'schema_version': 1, 'status': 'valid_completed', 'ok': True, 'errors': [], 'notes': [],
                     'runs': [], 'accounting_verified': True, 'accounting': {'learner_physical_calls': 123}}
        frozen = {'campaign_check': lambda p: self.manifest, 'audit_campaign': lambda *a, **k: deepcopy(original)}
        adapted = {'audit_campaign': lambda *a, **k: deepcopy(corrected)}
        with patch.object(cli, 'isolated_auditor', side_effect=[frozen, adapted]):
            result = cli.audit_campaign_cli(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['frozen_audit'], original)
        self.assertEqual(result['accounting']['learner_physical_calls'], 123)
        self.assertEqual(result['correction']['original_saved_audit_sha256'], cli.sha(self.root / 'AUDIT.json'))
        self.assertFalse(result['correction']['raw_reports_rewritten'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*.json')})

    def test_campaign_binding_error_never_returns_completed(self):
        frozen = {'campaign_check': lambda p: self.manifest}
        with patch.object(cli, 'isolated_auditor', return_value=frozen), patch.object(cli, 'CAMPAIGN_SHA256', '0' * 64):
            result = cli.audit_campaign_cli(self.root, strict=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'invalid')
        self.assertFalse(result['accounting_verified'])


if __name__ == '__main__':
    unittest.main()
