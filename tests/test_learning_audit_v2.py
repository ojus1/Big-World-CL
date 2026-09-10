"""Fabricated filesystem/provider receipts exercise auditing, not native quality."""
from copy import deepcopy
import json
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.evaluation import skillopt
from scripts.audit_evaluation import ROOT, audit_run, sha
from tests import test_evaluation_audit as fixtures


class LegacyStopAuditTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.ArtifactAuditTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        return fixture

    def test_v1_target_missing_score_remains_rejected(self):
        fixture = self.fixture(); update, directory = fixture.add_update()
        update['status'] = 'budget_exhausted'
        update['replay_evidence'].pop()
        fixtures.save(directory / 'update.json', update); fixture.flush()
        result = audit_run(fixture.root, strict=True)
        self.assertFalse(result['ok'])
        self.assertIn('missing_replay_evidence', [r['code'] for r in result['errors']])

    def test_v1_optimizer_timing_status_keeps_historical_behavior(self):
        fixture = self.fixture(); update, directory = fixture.add_update()
        update['status'] = 'budget_exhausted'
        update['costs']['operations'][-1].update(status='budget_exceeded', latency_ms=2000.,
                                               wall_seconds=2.)
        fixtures.save(directory / 'update.json', update); fixture.flush()
        self.assertTrue(audit_run(fixture.root, strict=True)['ok'])


@unittest.skipUnless((skillopt.DEFAULT_SOURCE / 'skillopt_sleep/consolidate.py').exists(),
                     'Pinned upstream not installed')
class NativeFileStopAuditTests(unittest.TestCase):
    def fixture(self, kind):
        f = fixtures.ArtifactAuditTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.use_modern_streaming_transport()
        directory = f.root / ('learning/d002-' + f.employee)
        public = [{k: v for k, v in e.items() if k != 'employee'} for e in f.state['experiences']]
        artifacts, transports, clock = [], [], [0.]
        def target(payload, limits):
            identifier = payload['task']['id']; attempt = len(artifacts)
            trial = directory / f'trial-{attempt:03d}'
            shutil.copytree(f.root / 'work' / identifier, trial)
            record = json.loads((trial / 'session.json').read_text())
            if kind == 'optimizer':
                record.update(success=False, artifact=None, committed_artifact_sha256=None,
                    last_submitted_artifact_sha256=None, semantic_score=0., checks={},
                    feedback='No artifact reached substantive submission.')
            record['timing'] = {'schema_version': 2, 'timeout_seconds': limits['timeout_seconds'],
                'elapsed_seconds_scope': 'runtime_start_through_snapshot_before_session_write_and_cleanup',
                'physical_inference_seconds': None}
            fixtures.save(trial / 'session.json', record)
            case_path = 'private/cases/' + identifier + '.json'
            artifacts.append({'capsule_path': case_path, 'capsule_sha256': sha((f.root / case_path).read_bytes()),
                'session_path': str((trial / 'session.json').relative_to(f.root)),
                'session_sha256': sha((trial / 'session.json').read_bytes()), 'attempt_index': attempt,
                'experience_id': identifier, 'source_task_id': record['task_id'], 'employee': f.employee,
                'phase': payload['phase'], 'sample_id': payload['sample_id'],
                'skill_sha256': record['skill']['content_sha256'], 'limits': limits, 'dispatch_status': 'returned',
                'usage_known': True, 'usage': {key: record['usage'].get(key) for key in
                    ('api_calls', 'total_tokens', 'charged_tokens', 'input_tokens', 'output_tokens', 'complete')},
                **{key: record[key] for key in ('success', 'semantic_score', 'infrastructure_valid', 'skill_loaded')}})
            clock[0] += record['elapsed_seconds']
            if kind == 'target':
                clock[0] += 2.  # Synthetic callback overhead; no sleep or model.
            return {'status': 'completed', 'model_calls': 1, 'tokens': 5,
                'tool_calls': record['tool_calls'], 'latency_ms': record['elapsed_seconds'] * 1000,
                'hard': float(record['success']), 'soft': record['semantic_score'],
                'response': 'offline file fixture', 'feedback': record['feedback']}
        def optimizer(payload, limits):
            clock[0] += 2.
            receipt = {'status': 'completed', 'tokens': 3, 'model_calls': 1, 'tool_calls': 0,
                'latency_ms': 0., 'input_tokens': 2, 'output_tokens': 1, 'accounting_complete': True,
                'optimizer_prompt': payload['prompt'], 'optimizer_prompt_sha256': sha(payload['prompt'].encode()),
                'max_output_tokens': 1024, 'response': '[]'}
            transports.append(deepcopy(receipt))
            return receipt
        with patch.object(skillopt, 'time', SimpleNamespace(monotonic=lambda: clock[0])):
            update = skillopt.SkillOptLearner(rollouts_k=2).update(f.skill, public, target, optimizer,
                current_day=2, budget=skillopt.LearningBudget(max_seconds=100, replay_seconds=1, optimizer_seconds=1))
        update.update(employee=f.employee, day=2, available_from_day=3, parent_version=0, deployed_version=0,
                      replay_artifacts=artifacts, optimizer_transport_audit=transports)
        f.state.update(updates=[update], learning_calls=update['costs']['target_model_calls'] +
            update['costs']['optimizer_model_calls'], learning_tokens=update['costs']['tokens'])
        f.manifest['learning_evidence_version'] = 2
        for name in ('lifespan/evaluation/skillopt.py', 'lifespan/evaluation/runtime.py',
                     'lifespan/evaluation/runner.py', 'scripts/audit_learning_v2.py', 'scripts/audit_evaluation.py'):
            f.manifest['source_sha256'][name] = sha((ROOT / name).read_bytes())
        def flush():
            fixtures.save(directory / 'update.json', update); f.flush()
        flush()
        return f, update, flush

    def test_fully_accounted_target_and_optimizer_stops_pass_raw_binding_without_adoption(self):
        for kind in ('target', 'optimizer'):
            with self.subTest(kind=kind):
                fixture, update, flush = self.fixture(kind)
                result = audit_run(fixture.root, strict=True)
                self.assertTrue(result['ok'], result)
                self.assertFalse(update['accepted'])
                self.assertEqual(len(update['unscored_replay_evidence']), int(kind == 'target'))

    def test_terminal_capsule_hash_session_hash_and_tool_receipt_are_bound(self):
        mutations = [
            lambda u: u['replay_artifacts'][-1].update(capsule_sha256='0' * 64),
            lambda u: u['replay_artifacts'][-1].update(session_sha256='0' * 64),
            lambda u: u['replay_artifacts'][-1].update(source_task_id='wrong-task'),
            lambda u: u['replay_artifacts'].append(deepcopy(u['replay_artifacts'][-1])),
        ]
        for mutate in mutations:
            f, update, flush = self.fixture('target'); mutate(update); flush()
            self.assertFalse(audit_run(f.root, strict=True)['ok'])
        f, update, flush = self.fixture('target')
        update['costs']['operations'][0]['tool_calls'] += 1
        update['costs']['operations'][0]['reported_usage']['tool_calls'] += 1
        flush()
        self.assertFalse(audit_run(f.root, strict=True)['ok'])

    def test_missing_native_receipt_and_version_downgrade_cannot_hide_terminal_operation(self):
        f, update, flush = self.fixture('target')
        path = f.root / update['replay_artifacts'][0]['session_path']
        path.unlink()
        self.assertFalse(audit_run(f.root, strict=True)['ok'])
        f, update, flush = self.fixture('optimizer')
        update.pop('learning_evidence_version'); flush()
        result = audit_run(f.root, strict=True)
        self.assertFalse(result['ok'])
        self.assertIn('learning_evidence_manifest_version', [r['code'] for r in result['errors']])
        f.manifest.pop('learning_evidence_version'); flush()
        result = audit_run(f.root, strict=True)
        self.assertFalse(result['ok'])
        self.assertIn('learning_evidence_source_version', [r['code'] for r in result['errors']])

    def test_optimizer_failed_or_physical_overrun_receipt_is_rejected(self):
        for mode in ('failed', 'output_tokens', 'tool_calls'):
            f, update, flush = self.fixture('optimizer')
            receipt = update['optimizer_transport_audit'][0]
            if mode == 'failed':
                receipt['status'] = update['costs']['operations'][-1]['callback_status'] = 'failed'
            elif mode == 'output_tokens':
                receipt['max_output_tokens'] = 0
            else:
                receipt['tool_calls'] = 4
            flush()
            self.assertFalse(audit_run(f.root, strict=True)['ok'])


if __name__ == '__main__':
    unittest.main()
