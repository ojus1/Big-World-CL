"""Offline cleanup ownership and process supervision fixtures; no native calls."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from lifespan.mirofish import save
from scripts import run_scale as runner


class ActorCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.run = Path(self.temp) / 'run'
        self.state_path = self.run / 'actors/mirofish_state.json'
        self.identifier = 'sim_owned_fixture_123'
        save(self.state_path, {'simulation': {'simulation_id': self.identifier}})
        self.requests = []
        self.alive = False
        self.success = True
        self.close_response = {'success': True, 'data': {'message': 'Close acknowledged; may still be closing.'}}
        self.net = self.enterContext(patch.object(runner, 'urlopen', side_effect=self.request))

    def request(self, request, timeout):
        body = json.loads(request.data)
        self.requests.append((request.full_url, body, timeout))
        self.assertEqual(body['simulation_id'], self.identifier)
        self.assertEqual(request.get_method(), 'POST')
        self.assertNotIn('Authorization', request.headers)
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 35)
        if request.full_url.endswith('/close-env'):
            self.assertEqual(body, {'simulation_id': self.identifier, 'timeout': 15})
            self.assertEqual(timeout, 35)
            intent = json.loads((self.run / 'SUPERVISOR_ACTOR_CLEANUP.json').read_bytes())
            self.assertEqual(intent['simulation_id'], self.identifier)
            payload = self.close_response
        else:
            self.assertEqual(request.full_url, 'http://127.0.0.1:5001/api/simulation/env-status')
            self.assertEqual(body, {'simulation_id': self.identifier})
            self.assertEqual(timeout, 10)
            payload = {'success': self.success, 'data': {'env_alive': self.alive}}
        return io.BytesIO(json.dumps(payload).encode())

    def test_close_intent_precedes_scoped_request_and_liveness_confirmation(self):
        result = runner.close_actor_environment(self.run)
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result, json.loads((self.run / 'SUPERVISOR_ACTOR_CLEANUP.json').read_bytes()))
        self.assertEqual(json.loads(self.state_path.read_bytes()), {'simulation': {'simulation_id': self.identifier}})

    def test_close_acknowledgement_does_not_prove_environment_closed(self):
        for alive in (True, None, 0, 'false'):
            with self.subTest(alive=alive):
                self.alive = alive
                result = runner.close_actor_environment(self.run)
                self.assertEqual(result['status'], 'close_unconfirmed')

    def test_unsuccessful_status_response_cannot_confirm_closure(self):
        self.success = False
        self.assertEqual(runner.close_actor_environment(self.run)['status'], 'close_unconfirmed')

    def test_prior_close_response_still_requires_liveness_verification(self):
        save(self.state_path, {'simulation': {'simulation_id': self.identifier},
                              'closed': {'success': True, 'message': 'May still be closing.'}})
        self.alive = True
        self.assertEqual(runner.close_actor_environment(self.run)['status'], 'close_unconfirmed')
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.requests[0][0].endswith('/env-status'))
        self.alive = False
        self.assertEqual(runner.close_actor_environment(self.run)['status'], 'closed')

    def test_missing_environment_never_sends_network_request(self):
        self.state_path.unlink()
        self.assertEqual(runner.close_actor_environment(self.run)['status'], 'no_recorded_environment')
        save(self.state_path, {})
        self.assertEqual(runner.close_actor_environment(self.run)['status'], 'no_recorded_environment')
        self.assertEqual(self.requests, [])

    def test_malformed_state_is_contained_and_does_not_break_other_cleanup(self):
        for text in ('{', '[]', '{"simulation":[]}'):
            with self.subTest(text=text):
                self.state_path.write_text(text)
                result = runner.close_actor_environment(self.run)
                self.assertEqual(result['status'], 'close_unconfirmed')
                self.assertIn('error_class', result)
        self.assertEqual(self.requests, [])

    def test_network_exception_text_is_never_persisted(self):
        secret_fixture = 'PRIVATE_TRANSPORT_EXCEPTION_FIXTURE'
        self.net.side_effect = TimeoutError(secret_fixture)
        result = runner.close_actor_environment(self.run)
        self.assertEqual(result['status'], 'close_unconfirmed')
        self.assertEqual(result['error_class'], 'TimeoutError')
        self.assertNotIn(secret_fixture, json.dumps(result))
        self.assertNotIn(secret_fixture, (self.run / 'SUPERVISOR_ACTOR_CLEANUP.json').read_text())

    def test_failed_record_write_is_contained(self):
        with patch.object(runner, 'save', side_effect=OSError('fixture disk full')):
            result = runner.close_actor_environment(self.run)
        self.assertEqual(result['status'], 'close_unconfirmed')
        self.assertEqual(result['error_class'], 'OSError')
        self.assertTrue(result['record_write_failed'])


class SupervisorOwnershipTests(unittest.TestCase):
    def test_interrupt_kills_and_closes_only_started_worlds(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            out = Path(directory)
            save(out / 'campaign.json', {'fixture': 'not-native-execution-evidence'})
            slots = [{'run_id': 'fixture-' + str(index), 'relative_path': 'runs/fixture-' + str(index)}
                     for index in range(3)]
            for slot in slots:
                (out / slot['relative_path']).mkdir(parents=True)
            children = [Mock(pid=41001), Mock(pid=41002)]
            for child in children:
                child.poll.return_value = None
            children[0].wait.side_effect = [subprocess.TimeoutExpired('offline-child', 30), 0]
            children[1].wait.return_value = 0
            stack.enter_context(patch.object(runner, 'credentials', return_value={'fixture': True}))
            stack.enter_context(patch.object(runner, 'validate_prepared', return_value={'slots': slots}))
            popen = stack.enter_context(patch.object(runner.subprocess, 'Popen', side_effect=children))
            kill = stack.enter_context(patch.object(runner.os, 'killpg'))
            cleanup = stack.enter_context(patch.object(runner, 'close_actor_environment', return_value={'status': 'closed'}))
            stack.enter_context(patch.object(runner, 'status', side_effect=KeyboardInterrupt))
            stack.enter_context(patch.object(runner.time, 'monotonic', return_value=100.0))
            signals = stack.enter_context(patch.object(runner.signal, 'signal', return_value='original-handler'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            with self.assertRaises(KeyboardInterrupt):
                runner.execute(out, workers=2, python=Path('/offline/not-launched'),
                               campaign_sha256=runner.sha(out / 'campaign.json'))
            self.assertEqual(popen.call_count, 2)
            self.assertTrue(all(call.kwargs['start_new_session'] for call in popen.call_args_list))
            self.assertEqual([call.args for call in kill.call_args_list],
                             [(41001, signal.SIGTERM), (41002, signal.SIGTERM), (41001, signal.SIGKILL)])
            self.assertEqual([call.args[0] for call in cleanup.call_args_list],
                             [out / slots[0]['relative_path'], out / slots[1]['relative_path']])
            interrupted = json.loads((out / 'SUPERVISOR_INTERRUPTED.json').read_bytes())
            self.assertEqual(interrupted['running_slots'], ['fixture-0', 'fixture-1'])
            self.assertEqual(interrupted['pending_slots'], ['fixture-2'])
            self.assertEqual(signals.call_args.args, (signal.SIGTERM, 'original-handler'))
            self.assertTrue((out / 'EXECUTION.json').exists())


if __name__ == '__main__':
    unittest.main()
