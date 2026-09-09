"""Tiny fabricated receipts test the auditor; they are never native/model evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.audit_evaluation import ROOT, audit_run, reports_equal, sha
from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.metrics import build_report
from lifespan.evaluation.runtime import install_skill, native_usage
from lifespan.evaluation.tasks import grade_case, make_case
from lifespan.world import Task


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


class ArtifactAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.employee = 'firm-0__onboarding-regulated'
        self.eco = Ecosystem(16, 101)
        self.eco.day = 9
        for world in self.eco.worlds.values():
            world.day, world.tasks, world.ledger = 9, {}, []
        self.skill = 'Offline fixture: read current task inputs and published procedures.'
        save(self.root / f'skills/{self.employee}/v000.json',
             {'version': 0, 'skill': self.skill, 'hash': sha(self.skill.encode()), 'adopted_after_day': -1})
        self.state = {'sessions': [], 'experiences': [], 'updates': [], 'skills': {self.employee: self.skill},
                      'skill_versions': {self.employee: 0}, 'learning_calls': 0, 'learning_tokens': 0}
        self.manifest = {'config': {'algorithm': 'skillopt', 'days': 8, 'feedback_delay': 1},
            'scenario': {'settlement_delay': 2}, 'target_model': 'offline-fabricated-evidence',
            'model_base_url': 'https://example.invalid', 'dependencies': {},
            'source_sha256': {name: sha((ROOT / name).read_bytes()) for name in
                ('lifespan/evaluation/tasks.py', 'lifespan/evaluation/metrics.py', 'lifespan/ecosystem.py', 'lifespan/world.py')}}
        self.provenance = {key: self.manifest[key] for key in
                           ('target_model', 'model_base_url', 'dependencies', 'source_sha256')}
        self.provenance.update(persona_cohort_sha256='offline-fixture-no-personas', actor_driver='offline-fixture', executor='offline-fixture')
        for day, split in enumerate(('train', 'val')):
            identifier, task_id = 'session-' + split, 'task-' + split
            case = make_case('onboarding', 101, day, task_id)
            artifact = {'task_id': task_id, 'channel': 'fixture-channel', 'redact': False,
                        'endpoint': 'fixture-endpoint', 'content': json.dumps(case['private']['expected'])}
            grade = grade_case(case, artifact)
            directory = self.root / 'work' / identifier
            info = install_skill(directory / f'computers/{self.employee}/hermes', self.skill)
            raw = json.dumps(artifact, indent=3).encode()  # Deliberately not canonical JSON.
            (directory / 'filesystem_objects').mkdir()
            (directory / 'filesystem_objects' / sha(raw)).write_bytes(raw)
            native_text = (directory / f'computers/{self.employee}/hermes/skills/work-process/SKILL.md').read_text()
            row = {'dispatch': 1, 'reserved_tokens': 10000, 'charged_tokens': 5, 'accounting': 'reported',
                   'status': 'response.completed', 'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5, 'output_cap': 32}
            native = {'evaluation_budget': {'physical_model_calls': 1, 'charged_tokens': 5, 'reported_tokens': 5,
                       'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5, 'accounting_complete': True,
                       'exhausted': False, 'operations': [row]},
                      'messages': [{'role': 'assistant', 'tool_calls': [{'id': 'load', 'function':
                          {'name': 'skill_view', 'arguments': '{"name":"work-process"}'}}]},
                          {'role': 'tool', 'tool_call_id': 'load', 'content': json.dumps(
                              {'success': True, 'name': 'work-process', 'content': native_text})}]}
            record = {'employee': self.employee, 'day': day, 'task_id': task_id, 'case_id': task_id,
                      'regime': 'base', 'skill': info, 'skill_loaded': True, 'success': True,
                      'semantic_score': grade['score'], 'checks': grade['checks'], 'feedback': grade['feedback'],
                      'artifact': artifact, 'committed_artifact_sha256': sha(raw), 'result': {'native': native},
                      'usage': native_usage(native), 'infrastructure_valid': True, 'elapsed_seconds': .01,
                      'tool_calls': 3, 'diagnostic': {'cost': 0, 'human_minutes': 0},
                      'filesystem_before': {name: {'sha256': sha(text.encode())} for name, text in case['public_files'].items()}}
            save(directory / 'session.json', record)
            record.update(id=identifier, skill_version=0)
            self.state['sessions'].append(record)
            self.state['experiences'].append({'id': identifier, 'employee': self.employee, 'split': split,
                'available_day': day + 1, 'feedback_available_day': day + 1, 'source_session': task_id,
                'prompt': case['request'], 'context': json.dumps(case['public_files']), 'feedback': grade['feedback']})
            save(self.root / f'private/cases/{identifier}.json', {'employee': self.employee, 'task_id': task_id,
                 'case': case, 'ecosystem': {'day': day}})
            world = self.eco.worlds['firm-0']
            world.tasks[task_id] = Task(task_id, 'onboarding', 'regulated', 'onboarding-regulated',
                                       'consumer-0', day, day + 3, 10, status='completed', completed=day)
            world.ledger.append({'task_id': task_id, 'owner': 'onboarding-regulated', 'settles': day + 2,
                                 'settled': True, 'amount': 10, 'session_id': identifier})
        self.flush()

    def flush(self, status='completed'):
        save(self.root / 'manifest.json', self.manifest)
        save(self.root / 'checkpoint.json', {'ecosystem': self.eco.checkpoint(), 'runner': self.state})
        save(self.root / 'REPORT.json', build_report(self.manifest['config'], self.manifest['scenario'],
             self.state['sessions'], self.state['updates'], self.eco.snapshot(), status=status, provenance=self.provenance))

    def add_update(self):
        directory = self.root / f'learning/d002-{self.employee}'
        evidence, rows = [], []
        for index, record in enumerate(self.state['sessions']):
            import shutil
            shutil.copytree(self.root / 'work' / record['id'], directory / f'trial-{index:03d}')
            rows.append({'kind': 'target', 'task_id': record['id'], 'phase': 'initial', 'tokens': 5,
                         'model_calls': 1, 'tool_calls': 3, 'accounting': 'reported', 'status': 'completed',
                         'limits': {'max_tokens': 10000, 'max_model_calls': 2}})
            evidence.append({'id': record['id'], 'skill_sha256': sha(self.skill.encode()), 'hard': 1., 'soft': 1.})
        rows.append({'kind': 'optimizer', 'phase': 'reflect', 'tokens': 3, 'model_calls': 1, 'tool_calls': 0,
                     'accounting': 'reported', 'status': 'completed', 'limits': {'max_tokens': 10000, 'max_model_calls': 1}})
        public = {key: value for key, value in self.state['experiences'][0].items() if key != 'employee'}
        update = {'employee': self.employee, 'day': 2, 'current_day': 2, 'available_from_day': 3,
                  'train_ids': ['session-train'], 'validation_ids': ['session-val'], 'accepted': False,
                  'skill': self.skill, 'skill_before_sha256': sha(self.skill.encode()), 'skill_after_sha256': sha(self.skill.encode()),
                  'parent_version': 0, 'deployed_version': 0, 'status': 'completed',
                  'optimizer_inputs': [{'current_day': 2, 'train_experiences': [{'task': public}]}],
                  'costs': {'tokens': 13, 'target_model_calls': 2, 'optimizer_model_calls': 1, 'replays': 2,
                            'wall_seconds': .1, 'accounting_complete': True, 'operations': rows},
                  'replay_evidence': evidence, 'optimizer_transport_audit': [{'accounting_complete': True,
                      'tokens': 3, 'input_tokens': 2, 'output_tokens': 1, 'model_calls': 1,
                      'optimizer_prompt': 'offline fixture', 'optimizer_prompt_sha256': sha(b'offline fixture')}]}
        self.state.update(updates=[update], learning_calls=3, learning_tokens=13)
        save(directory / 'update.json', update)
        self.flush()
        return update, directory

    def assertInvalid(self, code):
        result = audit_run(self.root, strict=True)
        self.assertFalse(result['ok'], result)
        self.assertIn(code, [row['code'] for row in result['errors']], result)

    def test_completed_raw_hash_fixture_and_learning_receipts(self):
        self.add_update()
        result = audit_run(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'valid_completed')
        self.assertIsNone(result['model_quality_score'])

    def test_checkpoint_disk_tamper(self):
        self.state['sessions'][0]['skill_loaded'] = False
        self.flush()
        self.assertInvalid('checkpoint_session_mismatch')

    def test_raw_object_tamper_and_missing_object(self):
        record = self.state['sessions'][0]
        path = self.root / 'work' / record['id'] / 'filesystem_objects' / record['committed_artifact_sha256']
        path.write_text('{}')
        self.assertInvalid('committed_artifact_hash_or_content')
        path.unlink()
        self.assertInvalid('missing_immutable_committed_bytes')

    def test_mutated_skill_file(self):
        path = self.root / f'work/session-train/computers/{self.employee}/hermes/skills/work-process/SKILL.md'
        path.write_text('different skill')
        self.assertInvalid('deployed_native_skill_hash')

    def test_fake_load_and_physical_receipt_tamper(self):
        record = self.state['sessions'][0]
        record['result']['native']['messages'][-1]['content'] = '{}'
        self.sync_session(record)
        self.assertInvalid('native_skill_load_provenance')
        record['skill_loaded'] = False
        record['result']['native']['evaluation_budget']['operations'][0]['total_tokens'] = 50
        self.sync_session(record)
        self.assertInvalid('physical_token_equation')

    def sync_session(self, record):
        save(self.root / 'work' / record['id'] / 'session.json',
             {key: value for key, value in record.items() if key not in ('id', 'skill_version')})
        self.flush()

    def test_regrade_tampered_score_even_if_report_agrees(self):
        record = self.state['sessions'][0]
        record['checks'] = {'fabricated': 1.}
        self.sync_session(record)
        self.assertInvalid('independent_committed_artifact_grade')

    def make_failed_record(self):
        record = self.state['sessions'][0]
        record.update(success=False, artifact=None, committed_artifact_sha256=None)
        world = self.eco.worlds['firm-0']
        world.tasks[record['task_id']].status = 'pending'
        world.tasks[record['task_id']].completed = None
        world.ledger = [entry for entry in world.ledger if entry['task_id'] != record['task_id']]
        return record

    def test_failed_submission_regraded_from_immutable_bytes_after_file_deletion(self):
        record = self.make_failed_record()
        directory = self.root / 'work' / record['id']
        capsule = json.loads((self.root / f"private/cases/{record['id']}.json").read_text())
        artifact = {'task_id': record['task_id'], 'channel': 'fixture-channel', 'redact': False,
                    'endpoint': 'fixture-endpoint', 'content': '{}'}
        raw = json.dumps(artifact, indent=3).encode()
        record['last_submitted_artifact_sha256'] = sha(raw)
        object_path = directory / 'filesystem_objects' / sha(raw)
        object_path.write_bytes(raw)  # No mutable workspace submission file remains.
        grade = grade_case(capsule['case'], artifact)
        record.update(semantic_score=grade['score'], checks=grade['checks'], feedback=grade['feedback'])
        self.sync_session(record)
        result = audit_run(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        self.assertFalse(any('partial scores' in note for note in result['notes']), result)
        record['semantic_score'] = .25
        self.sync_session(record)
        self.assertInvalid('independent_last_submission_grade')
        record['semantic_score'] = grade['score']
        self.sync_session(record)
        object_path.write_text('{}')
        self.assertInvalid('submitted_artifact_hash')
        object_path.unlink()
        self.assertInvalid('missing_immutable_submitted_bytes')

    def test_null_submission_requires_default_ungraded_result(self):
        record = self.make_failed_record()
        record.update(last_submitted_artifact_sha256=None, semantic_score=0., checks={},
                      feedback='No artifact reached substantive submission.')
        self.sync_session(record)
        result = audit_run(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        record['feedback'] = 'Fabricated substantive feedback'
        self.sync_session(record)
        self.assertInvalid('independent_last_submission_grade')

    def test_future_and_cross_employee_update_experience(self):
        self.add_update()
        self.state['experiences'][0]['available_day'] = 0
        self.flush()
        self.assertInvalid('future_update_experience')
        self.state['experiences'][0]['available_day'] = 3
        self.flush()
        self.assertInvalid('future_update_experience')
        self.state['experiences'][0].update(available_day=1, employee='firm-1__other')
        self.flush()
        self.assertInvalid('cross_employee_or_split_experience')

    def test_replay_and_optimizer_cost_tamper(self):
        update, directory = self.add_update()
        update['costs']['operations'][0]['tokens'] += 1
        update['costs']['tokens'] += 1
        self.state['learning_tokens'] += 1
        save(directory / 'update.json', update)
        self.flush()
        self.assertInvalid('replay_physical_evidence_mismatch')

    def test_report_tamper_and_ledger_ineligibility(self):
        path = self.root / 'REPORT.json'
        report = json.loads(path.read_text())
        report['business']['realized_utility'] += 10
        save(path, report)
        self.assertInvalid('persisted_report_mismatch')
        self.eco.worlds['firm-0'].ledger.pop()
        self.flush()
        self.assertInvalid('completed_report_ineligible')

    def test_report_roundoff_accepted_but_meaningful_score_change_rejected(self):
        path = self.root / 'REPORT.json'
        report = json.loads(path.read_text())
        report['prospective']['mean_semantic_score'] -= 2e-16
        save(path, report)
        result = audit_run(self.root, strict=True)
        self.assertTrue(result['ok'], result)
        report['prospective']['mean_semantic_score'] -= 1e-6
        save(path, report)
        self.assertInvalid('persisted_report_mismatch')

    def test_report_comparison_preserves_exact_types_counts_and_structure(self):
        self.assertTrue(reports_equal({'nested': [425.50000000000006, .9925925555555557]},
                                      {'nested': [425.5, .9925925555555555]}))
        for left, right in ((1, True), (1, 1.), (10**15, 10**15 + 1), ('1', 1),
                            ({'count': 1}, {'count': 1, 'extra': None}), ([1], [1, 2]),
                            (float('nan'), float('nan')), (float('inf'), float('inf'))):
            with self.subTest(left=left, right=right):
                self.assertFalse(reports_equal(left, right))

    def test_incomplete_label_and_strict_cli(self):
        self.flush('paused_invocation_limit')
        save(self.root / 'INFLIGHT.json', {'kind': 'work'})
        result = audit_run(self.root)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(audit_run(self.root, strict=True)['ok'])
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/audit_evaluation.py'), str(self.root), '--strict'],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)['status'], 'incomplete')

    def test_completed_run_cannot_hide_orphan_or_failure(self):
        save(self.root / 'learning/orphan/FAILURE.json', {'type': 'offline-fixture-failure'})
        self.assertInvalid('completed_run_has_unreconciled_artifacts')

    def test_uncheckpointed_learning_and_extra_replay_fail(self):
        update, directory = self.add_update()
        save(directory / 'trial-999/session.json', {'fixture': 'unaccounted call'})
        self.assertInvalid('unreconciled_replay_sessions')
        (directory / 'trial-999/session.json').unlink()
        (self.root / 'learning/unrecorded-update').mkdir()
        self.assertInvalid('completed_run_has_unreconciled_artifacts')


if __name__ == '__main__':
    unittest.main()
