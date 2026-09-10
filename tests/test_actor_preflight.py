"""Preflight launch/repair/isolation contracts with no native or model startup."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import preflight_actor_contract as p


class ActorPreflightTests(unittest.TestCase):
    def test_four_role_wire_fixtures_preserve_escaped_witness(self):
        self.assertEqual(len(p.participants()), 4)
        for role in p.ROLES:
            raw = json.dumps(p.expected(role), ensure_ascii=False)
            self.assertTrue(p.wire.shape_valid(raw, role))
            self.assertIn(p.MARKER, json.loads(raw).values())

    def test_prepare_binds_source_and_cohort_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'new'
            def cohort(cache, target, **kw):
                self.assertEqual(kw, {'count': 4, 'seed': 907})
                p.save(target, {'revision': 'fixture', 'personas': []})
                return p.read(target)
            with patch.object(p, 'import_cohort', side_effect=cohort), \
                 patch.object(p, 'ROOT', Path(tmp)), \
                 patch.object(p, 'credentials', return_value={'model': 'model', 'base_url': 'url', 'api_key': 'private-fixture-value'}), \
                 patch.object(p, 'sources', return_value={'script': 'hash'}), \
                 patch.object(p, 'installation', return_value={}), \
                 patch.object(p, 'dependency_provenance', return_value={}):
                result = p.prepare(out)
                self.assertEqual(result['manifest_sha256'], p.sha(out / 'manifest.json'))
                self.assertNotIn('private-fixture-value', (out / 'manifest.json').read_text())
                self.assertEqual(p.read(out / 'manifest.json')['roles'], list(p.ROLES))
                with self.assertRaises(FileExistsError):
                    p.prepare(out)

    def test_bad_manifest_cannot_start_service(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p.subprocess, 'Popen') as start, \
             patch.object(p, 'ROOT', Path(tmp)):
            out = Path(tmp)
            p.save(out / 'manifest.json', {})
            with self.assertRaisesRegex(ValueError, 'manifest_hash'):
                p.execute(out, 'wrong')
            start.assert_not_called()

    def test_used_execution_intent_cannot_start_service(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'verify', return_value={}), \
             patch.object(p.socket, 'socket'), patch.object(p.subprocess, 'Popen') as start, \
             patch.object(p, 'ROOT', Path(tmp) / 'checkout'):
            out = Path(tmp) / 'out'; out.mkdir()
            (out / 'EXECUTION.json').write_text('{}')
            with self.assertRaises(FileExistsError):
                p.execute(out, 'hash')
            start.assert_not_called()

    def test_nonempty_backend_is_never_attached(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'verify', return_value={}), \
             patch.object(p.socket, 'socket'), patch.object(p.subprocess, 'Popen') as start, \
             patch.object(p, 'ROOT', Path(tmp) / 'checkout'):
            uploads = p.ROOT / 'MiroFish/backend/uploads'; uploads.mkdir(parents=True)
            (uploads / 'existing-world').mkdir()
            with self.assertRaisesRegex(ValueError, 'fresh_backend'):
                p.execute(Path(tmp), 'hash')
            start.assert_not_called()

    def test_worker_uses_native_single_repair_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p.save(out / 'persona_cohort.json', {})
            runtime = MagicMock()
            raw = [json.dumps(p.expected(role)) for role in p.ROLES]
            runtime.interview.side_effect = ['{broken', *raw]
            with patch.object(p, 'verify', return_value={}), \
                 patch.object(p, 'verify_worker_parent', return_value=12345.0), \
                 patch.object(p, 'MiroFishRuntime', return_value=runtime), \
                 patch.object(p, 'audit_interviews', return_value={'measured_physical_requests': 5}):
                p.worker(out, 'hash')
            keys = [call.args[2] for call in runtime.interview.call_args_list]
            self.assertEqual(keys, ['wire-employee', 'wire-employee-repair', 'wire-enterprise', 'wire-government', 'wire-consumer'])
            self.assertEqual(p.read(out / 'WIRE_RESULT.json')['status'], 'completed')
            self.assertEqual(runtime.evaluation_max_interviews, 8)
            self.assertEqual(runtime.evaluation_deadline, 12345.0)
            runtime.client.close.assert_called_once()

    def test_second_malformed_response_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p.save(out / 'persona_cohort.json', {})
            runtime = MagicMock(); runtime.interview.side_effect = ['{broken', '{still broken']
            with patch.object(p, 'verify', return_value={}), \
                 patch.object(p, 'verify_worker_parent'), \
                 patch.object(p, 'MiroFishRuntime', return_value=runtime):
                with self.assertRaises(ValueError):
                    p.worker(out, 'hash')
            self.assertEqual(runtime.interview.call_count, 2)
            self.assertTrue((out / 'WORKER_FAILURE.json').exists())
            self.assertFalse((out / 'WIRE_RESULT.json').exists())

    def test_unknown_receipt_failure_cannot_be_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p.save(out / 'persona_cohort.json', {})
            runtime = MagicMock(); runtime.interview.side_effect = RuntimeError('private provider diagnostic')
            with patch.object(p, 'verify', return_value={}), \
                 patch.object(p, 'verify_worker_parent'), \
                 patch.object(p, 'MiroFishRuntime', return_value=runtime):
                with self.assertRaises(RuntimeError):
                    p.worker(out, 'hash')
            self.assertEqual(runtime.interview.call_count, 1)
            self.assertEqual(p.read(out / 'WORKER_FAILURE.json'), {'error_class': 'RuntimeError'})

    def test_worker_requires_original_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p.save(out / 'EXECUTION.json', {'manifest_sha256': 'hash', 'supervisor_pid': -1})
            p.save(out / 'SERVER.json', {'pid': 0, 'start_ticks': '0'})
            with self.assertRaisesRegex(ValueError, 'live_supervisor'):
                p.verify_worker_parent(out, 'hash')

    def test_cleanup_never_addresses_unrecorded_simulation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'request') as request:
            self.assertEqual(p.cleanup_actor(Path(tmp)), {'status': 'no_recorded_environment'})
            request.assert_not_called()

    def test_cleanup_confirms_liveness_and_forces_only_recorded_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p.save(out / 'actors/mirofish_state.json', {'simulation': {'simulation_id': 'sim_fixture'}})
            replies = [{}, {'success': True, 'data': {'env_alive': True}}, {},
                       {'success': True, 'data': {'env_alive': False}}]
            with patch.object(p, 'request', side_effect=replies) as request:
                result = p.cleanup_actor(out)
            self.assertEqual(result['status'], 'closed')
            self.assertTrue(result['forced_stop_requested'])
            self.assertTrue(all(c.args[1]['simulation_id'] == 'sim_fixture' for c in request.call_args_list))

    def test_terminate_tolerates_exit_between_poll_and_signal(self):
        process = MagicMock(); process.poll.return_value = None; process.returncode = 0
        with patch.object(p.os, 'killpg', side_effect=ProcessLookupError):
            self.assertEqual(p.terminate(process), {'status': 'exited', 'exit_code': 0})
        process.wait.assert_called_once_with(timeout=10)

    def test_cleanup_exception_does_not_skip_remaining_stages_or_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'; out.mkdir()
            checkout = Path(tmp) / 'checkout'
            backend = checkout / 'MiroFish/backend'; backend.mkdir(parents=True)
            p.save(out / 'WIRE_RESULT.json', {'status': 'completed'})
            process = MagicMock(); process.pid = os.getpid(); process.poll.return_value = None
            process.wait.return_value = 0; process.returncode = 0
            manifest = {'claims_excluded': [], 'accounting_scope': 'interviews'}
            with patch.object(p, 'ROOT', checkout), patch.object(p, 'verify', return_value=manifest), \
                 patch.object(p.socket, 'socket'), patch.object(p, 'request', return_value={}), \
                 patch.object(p.subprocess, 'Popen', return_value=process), \
                 patch.object(p, 'terminate', side_effect=[ProcessLookupError(), {'status': 'exited'}]) as terminate, \
                 patch.object(p, 'cleanup_actor', return_value={'status': 'closed'}) as cleanup:
                result = p.execute(out, 'hash')
            self.assertEqual(terminate.call_count, 2)
            cleanup.assert_called_once()
            self.assertEqual(result['status'], 'cleanup_unconfirmed')
            self.assertEqual(p.read(out / 'SUMMARY.json'), result)
            self.assertEqual(result['evidence_inventory_sha256'], p.sha(out / 'EVIDENCE.json'))

    def test_false_env_status_cannot_hide_surviving_native_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'; out.mkdir()
            checkout = Path(tmp) / 'checkout'; (checkout / 'MiroFish/backend').mkdir(parents=True)
            p.save(out / 'WIRE_RESULT.json', {'status': 'completed'})
            process = MagicMock(); process.pid = os.getpid(); process.poll.return_value = None
            process.wait.return_value = 0; process.returncode = -9
            with patch.object(p, 'ROOT', checkout), patch.object(p, 'verify', return_value={'claims_excluded': [], 'accounting_scope': 'interviews'}), \
                 patch.object(p.socket, 'socket'), patch.object(p, 'request', return_value={}), \
                 patch.object(p.subprocess, 'Popen', return_value=process), \
                 patch.object(p, 'terminate', return_value={'status': 'exited', 'exit_code': -9}), \
                 patch.object(p, 'cleanup_actor', return_value={'status': 'closed'}), \
                 patch.object(p, 'observe_native', return_value={'status': 'observed_live'}), \
                 patch.object(p, 'finish_native', return_value={'status': 'cleanup_unconfirmed'}):
                result = p.execute(out, 'hash')
            self.assertEqual(result['status'], 'cleanup_unconfirmed')

    def test_unknown_native_identity_is_never_signalled(self):
        with patch.object(p.os, 'killpg') as kill:
            self.assertEqual(p.finish_native({'status': 'unknown_native_identity'})['status'], 'cleanup_unconfirmed')
            kill.assert_not_called()

    def test_reused_or_exited_native_identity_is_never_signalled(self):
        with patch.object(p, 'native_gone', return_value=True), patch.object(p.os, 'killpg') as kill:
            self.assertEqual(p.finish_native({'status': 'observed_live', 'pid': 123, 'start_ticks': 'old'})['status'], 'exited')
            kill.assert_not_called()

    def test_output_outside_checkout_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'ROOT', Path(tmp) / 'checkout'):
            out = Path(tmp) / 'outside'
            with self.assertRaisesRegex(ValueError, 'isolated_checkout'):
                p.prepare(out)
            self.assertFalse(out.exists())

    def test_native_identity_resolves_actual_pinned_launch_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'ROOT', Path(tmp) / 'checkout'), \
             patch.object(p.os, 'getpgid', return_value=410):
            out = p.ROOT / 'out'
            backend = p.ROOT / 'MiroFish/backend'
            directory = backend / 'uploads/simulations/sim_fixture'
            p.save(out / 'actors/mirofish_state.json', {'simulation': {'simulation_id': 'sim_fixture'}})
            p.save(directory / 'run_state.json', {'process_pid': 410})
            fake_proc = Path(tmp) / 'proc'; proc = fake_proc / '410'; proc.mkdir(parents=True)
            (proc / 'cwd').symlink_to(directory, target_is_directory=True)
            (proc / 'stat').write_text(' '.join(['410', '(python)', 'S'] + ['0'] * 18 + ['12345']))
            argv = ['python', str(backend / 'app/services/../../scripts/run_reddit_simulation.py'),
                    '--config', str(backend / 'app/services/../../uploads/simulations/sim_fixture/simulation_config.json')]
            (proc / 'cmdline').write_bytes(b'\0'.join(v.encode() for v in argv) + b'\0')
            observed = p.observe_native(out, proc_root=fake_proc)
            self.assertEqual(observed['status'], 'observed_live')
            self.assertEqual(observed['start_ticks'], '12345')
            argv[3] = str(Path(tmp) / 'another-simulation.json')
            (proc / 'cmdline').write_bytes(b'\0'.join(v.encode() for v in argv) + b'\0')
            self.assertEqual(p.observe_native(out, proc_root=fake_proc)['status'], 'unknown_native_identity')

    def test_inventory_binds_nested_receipts_claims_and_database(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'ROOT', Path(tmp) / 'checkout'):
            out = Path(tmp) / 'out'
            receipt = out / 'actors/mirofish_interviews/wire.json'; p.save(receipt, {'known': 1})
            native = p.ROOT / 'MiroFish/backend/uploads/simulations/sim_fixture'
            p.save(native / 'actor_contract_receipts/claim.json', {'claimed': True})
            (native / 'reddit_simulation.db').write_bytes(b'fixture database')
            first = p.evidence_inventory(out)
            self.assertEqual(len(first['files']['preflight']), 1)
            self.assertEqual(len(first['files']['native_uploads']), 2)
            p.save(receipt, {'known': 2})
            self.assertNotEqual(first, p.evidence_inventory(out))


if __name__ == '__main__':
    unittest.main()
