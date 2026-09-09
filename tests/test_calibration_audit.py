"""Fabricated offline receipts exercise auditing, never model-quality claims."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts.audit_calibration import ROOT, audit_calibration, digest, sha
from scripts.calibration_bank import build_bank, aggregate_repeats
from lifespan.evaluation.protocol import ExperimentConfig, SEED_SKILL, scenario
from lifespan.evaluation.runtime import install_skill

# Reuse the tiny raw-object/native-receipt fixture without depending on the test
# discovery import path. Its own tests are not inherited or run by this class.
spec = importlib.util.spec_from_file_location('_calibration_source_fixture', ROOT / 'tests/test_evaluation_audit.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


class CalibrationAuditTests(unittest.TestCase):
    def setUp(self):
        source_fixture = fixture_module.ArtifactAuditTests()
        source_fixture.setUp()
        self.addCleanup(source_fixture.doCleanups)
        self.source = source_fixture.root
        source_fixture.manifest['config'] = ExperimentConfig(algorithm='no_learning', days=8).public()
        source_fixture.manifest['scenario'] = scenario(ExperimentConfig(algorithm='no_learning', days=8))
        source_fixture.manifest['dependencies'] = {'fixture': {'revision': 'fabricated-offline-source'}}
        source_fixture.provenance['dependencies'] = source_fixture.manifest['dependencies']
        employee = source_fixture.employee
        source_fixture.state['skills'][employee] = SEED_SKILL
        save(self.source / f'skills/{employee}/v000.json', {'version': 0, 'skill': SEED_SKILL,
             'hash': hashlib.sha256(SEED_SKILL.encode()).hexdigest(), 'adopted_after_day': -1})
        for record in source_fixture.state['sessions']:
            directory = self.source / 'work' / record['id']
            record['skill'] = install_skill(directory / f'computers/{employee}/hermes', SEED_SKILL)
            skill_text = (directory / f'computers/{employee}/hermes/skills/work-process/SKILL.md').read_text()
            record['result']['native']['messages'][-1]['content'] = json.dumps({'success': True, 'name': 'work-process', 'content': skill_text})
            record['budget_exhausted'] = False
            source_fixture.sync_session(record)
            path = self.source / f"private/cases/{record['id']}.json"
            capsule = json.loads(path.read_text())
            eco = source_fixture.eco.checkpoint()
            eco['day'] = record['day']
            for world in eco['worlds'].values():
                world['day'] = record['day']
            task = eco['worlds']['firm-0']['tasks'][record['task_id']]
            task.update(status='pending', completed=None)
            capsule.update(ecosystem=eco, firm='firm-0')
            save(path, capsule)
        source_fixture.flush()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.bank = build_bank(self.source)
        self.assertEqual(self.bank['selected_cell_count'], 1)
        self.config = {'repeats': 2, 'max_rollouts': 2, 'max_model_calls': 32, 'max_charged_tokens': 500000,
                       'max_run_seconds': 3600, 'max_iterations': 16, 'max_output_tokens': 4096,
                       'max_rollout_tokens': 250000, 'max_rollout_seconds': 420, 'order_seed': 104729}
        identifier = self.bank['selections'][0]['selection_id']
        self.slots = [{'selection_id': identifier, 'repeat_index': index, 'rollout_id': identifier + '-r' + str(index)} for index in range(2)]
        names = ('lifespan/evaluation/tasks.py', 'lifespan/evaluation/runtime.py', 'lifespan/evaluation/budget.py',
                 'lifespan/evaluation/protocol.py', 'lifespan/computers.py', 'lifespan/ecosystem.py', 'lifespan/world.py',
                 'scripts/run_calibration.py', 'scripts/calibration_bank.py', 'scripts/audit_evaluation.py')
        self.manifest = {'kind': 'native_historical_replay_calibration', 'source_directory': str(self.source),
                         'config': self.config, 'bank_sha256': digest(self.bank), 'slots': self.slots,
                         'source_sha256': {name: sha(ROOT / name) for name in names},
                         'target_model': source_fixture.manifest['target_model'], 'model_base_url': source_fixture.manifest['model_base_url'],
                         'skill_sha256': source_fixture.state['sessions'][0]['skill']['content_sha256']}
        results = []
        for slot in self.slots:
            directory = self.out / 'replays' / slot['rollout_id']
            shutil.copytree(self.source / 'work' / identifier, directory)
            record = json.loads((directory / 'session.json').read_text())
            fields = ('success', 'semantic_score', 'infrastructure_valid', 'budget_exhausted', 'usage', 'diagnostic', 'elapsed_seconds', 'skill_loaded')
            results.append({**slot, 'status': 'completed', **{key: record[key] for key in fields},
                            'session_path': str((directory / 'session.json').relative_to(self.out)), 'session_sha256': sha(directory / 'session.json')})
        self.state = {'status': 'completed', 'next_slot': 2, 'results': results,
                      'charged_tokens': 10, 'model_calls': 2, 'elapsed_seconds': 1.}
        self.flush()

    def flush(self):
        save(self.out / 'manifest.json', self.manifest)
        save(self.out / 'bank.json', self.bank)
        save(self.out / 'state.json', self.state)
        report = aggregate_repeats(self.bank, self.state['results'])
        report.update(status=self.state['status'], config=self.config, manifest_sha256=sha(self.out / 'manifest.json'),
                      actual_execution_elapsed_seconds=self.state['elapsed_seconds'], charged_or_reserved_tokens=self.state['charged_tokens'],
                      charged_or_reserved_calls=self.state['model_calls'])
        save(self.out / 'REPORT.json', report)

    def invalid(self, code):
        result = audit_calibration(self.out, strict=True)
        self.assertFalse(result['ok'], result)
        self.assertIn(code, result['errors'], result)

    def test_complete_two_repeat_fixture(self):
        result = audit_calibration(self.out, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['checked_slots'], 2)
        self.assertIsNone(result['model_quality_score'])

    def test_receipt_and_budget_checkpoint_tampering(self):
        self.state['charged_tokens'] = 0
        self.flush()
        self.invalid('campaign_cost_totals')
        self.state['charged_tokens'] = 10
        self.state['results'][0]['success'] = False
        self.flush()
        self.invalid('receipt_native_session_mismatch')

    def test_slot_order_and_source_provenance_tampering(self):
        self.manifest['slots'].reverse()
        self.flush()
        self.invalid('planned_slot_order_mismatch')
        self.manifest['slots'].reverse()
        self.manifest['source_sha256']['lifespan/evaluation/runtime.py'] = '0' * 64
        self.flush()
        self.invalid('campaign_source_revision_mismatch')

    def test_raw_session_and_committed_object_tampering(self):
        result = self.state['results'][0]
        path = self.out / result['session_path']
        with path.open('a') as stream:
            stream.write('\n')
        self.invalid('native_session_hash_or_path_mismatch')
        result['session_sha256'] = sha(path)
        record = json.loads(path.read_text())
        (path.parent / 'filesystem_objects' / record['committed_artifact_sha256']).write_text('{}')
        self.flush()
        self.invalid('committed_artifact_hash_or_content')

    def test_aggregate_report_tamper(self):
        path = self.out / 'REPORT.json'
        report = json.loads(path.read_text())
        report['outcomes']['mean_semantic_score_completed_receipts'] = .9
        save(path, report)
        self.invalid('calibration_report_mismatch')

    def test_partial_is_explicit_and_strict_cli_fails(self):
        self.state.update(status='paused_invocation_limit', next_slot=1, results=self.state['results'][:1], charged_tokens=5, model_calls=1)
        shutil.rmtree(self.out / 'replays' / self.slots[1]['rollout_id'])
        self.flush()
        result = audit_calibration(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/audit_calibration.py'), str(self.out), '--strict'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout)

    def test_unknown_failure_retains_reservation_and_missing_future_slot(self):
        first = {**self.slots[0], 'status': 'infrastructure_error', 'infrastructure_valid': False,
                 'success': None, 'semantic_score': None, 'usage': {'complete': False, 'api_calls': None, 'total_tokens': None, 'charged_tokens': 250000}}
        self.state.update(status='infrastructure_error', next_slot=0, results=[first], charged_tokens=250000, model_calls=16)
        shutil.rmtree(self.out / 'replays')
        save(self.out / 'INFLIGHT.json', {**self.slots[0], 'reserved_tokens': 250000, 'reserved_calls': 16})
        save(self.out / 'FAILURE.json', {'type': 'FabricatedOfflineFailure'})
        self.flush()
        result = audit_calibration(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['charged_or_reserved_tokens'], 250000)
        self.state['status'] = 'running'
        self.flush()
        self.invalid('continued_after_infrastructure_failure')

    def test_checkpointed_inflight_slot_remains_reconcilable_incomplete(self):
        self.state['status'] = 'running'
        save(self.out / 'INFLIGHT.json', {**self.slots[-1], 'reserved_tokens': 250000, 'reserved_calls': 16})
        self.flush()
        result = audit_calibration(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('INFLIGHT.json', result['pending_artifacts'])

    def test_orphan_native_directory_cannot_be_hidden_in_partial_run(self):
        self.state['status'] = 'paused_invocation_limit'
        (self.out / 'replays/unknown-call').mkdir()
        self.flush()
        self.invalid('unaccounted_replay_directory')

    def test_elapsed_budget_cannot_rewind_below_saved_native_elapsed(self):
        self.state['elapsed_seconds'] = 0
        self.flush()
        self.invalid('checkpoint_elapsed_below_recorded_rollouts')


if __name__ == '__main__':
    unittest.main()
