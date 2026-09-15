"""Offline orchestration fixtures; these never establish native capability."""
from copy import deepcopy
import json
import io
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from lifespan.mirofish import save
from scripts import hermes_transport_preflight as preflight
from scripts import hermes_preflight_process as processes


def fixture_executor(**kwargs):
    raise AssertionError('Offline orchestration replaces supervision before execution')


class PreflightPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)/'preflight'
        self.deps = patch.object(preflight, 'dependencies', return_value={'fixture': 'no_installed_services'})
        self.deps.start(); self.addCleanup(self.deps.stop)
        self.creds = {'model': 'fixture-model', 'base_url': 'https://fixture.invalid/v1', 'api_key': 'private-fixture-key'}

    def prepare(self):
        return preflight.prepare(self.out, target_model=self.creds['model'], model_base_url=self.creds['base_url'])

    def test_fixed_six_slots_share_each_workflow_capsule_and_skill(self):
        manifest = self.prepare()
        self.assertEqual(len(manifest['slots']), 6)
        for first, second in zip(manifest['slots'][::2], manifest['slots'][1::2]):
            self.assertEqual(first['capsule_sha256'], second['capsule_sha256'])
            self.assertEqual(first['task_id'], second['task_id'])
            self.assertEqual({first['mode'], second['mode']}, {'streaming', 'nonstreaming'})
        self.assertEqual(preflight.verify_prepared(self.out), manifest)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        self.assertIn('work.commit', preflight.REQUEST)
        self.assertIn('even if rejected', preflight.REQUEST)
        self.assertNotIn(self.creds['api_key'], (self.out/'manifest.json').read_text())

    def test_preparation_never_loads_credentials_or_native_executor(self):
        with patch.dict(os.environ, {}, clear=True):
            self.prepare()
        self.assertFalse((self.out/'EXECUTION.json').exists())

    def test_preparation_refuses_credentials_in_service_url(self):
        for url in ('https://key@fixture.invalid', 'https://fixture.invalid?key=private', 'https://fixture.invalid#key'):
            with self.assertRaises(ValueError):
                preflight.prepare(self.out, target_model='m', model_base_url=url)
        self.assertFalse(self.out.exists())

    def test_mutated_future_private_data_and_source_are_rejected_before_dispatch(self):
        self.prepare()
        path = self.out/'private/cases/onboarding.json'
        capsule = preflight.read(path); capsule['request'] += ' injected future task'; save(path, capsule)
        with self.assertRaisesRegex(ValueError, 'Case differs'):
            preflight.execute(self.out, creds=self.creds, executor=fixture_executor)
        self.assertFalse((self.out/'EXECUTION.json').exists())

    def test_native_requires_committed_sources_and_separately_registered_hash(self):
        manifest = self.prepare()
        manifest['source_commit_verified'] = False; save(self.out/'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'committed sources'):
            preflight.execute(self.out, creds=self.creds, expected_manifest_sha256=preflight.sha(self.out/'manifest.json'))
        with self.assertRaisesRegex(ValueError, 'separately registered hash'):
            preflight.execute(self.out, creds=self.creds, executor=fixture_executor, expected_manifest_sha256='0'*64)
        self.assertFalse((self.out/'EXECUTION.json').exists())

    def test_source_change_refused_before_lock_or_dispatch(self):
        self.prepare()
        altered = {**preflight.execution_sources(), 'lifespan/evaluation/runtime.py': 'f'*64}
        with patch.object(preflight, 'execution_sources', return_value=altered), self.assertRaisesRegex(ValueError, 'provenance'):
            preflight.execute(self.out, creds=self.creds, executor=fixture_executor)
        self.assertFalse((self.out/'EXECUTION.json').exists())

    def test_run_deadline_reserves_full_next_slot_before_dispatch(self):
        self.prepare()
        with patch.object(preflight.time, 'monotonic', side_effect=[0, 2600, 2600]), \
                patch.object(preflight, 'supervise', side_effect=AssertionError('No dispatch after exhausted reservation')):
            report = preflight.execute(self.out, creds=self.creds, executor=fixture_executor)
        self.assertEqual(report['status'], 'halted_budget')
        self.assertEqual(report['attempted_slots'], 0)
        self.assertEqual(report['usage']['charged_or_reserved_model_calls'], 0)

    def fake_supervise(self, executor, kwargs, trial, **limits):
        self.seen.append(kwargs)
        trial.mkdir(parents=True)
        save(trial/'native/session.json', {'usage': {'fixture': True}})
        cleanup = {'schema_version': 1, 'status': 'confirmed'}
        result = {'status': getattr(self, 'supervision_status', 'returned'), 'root_exitcode': 0,
                  'elapsed_seconds': getattr(self, 'primary_seconds', .005) + .005,
                  'execution_elapsed_seconds': getattr(self, 'primary_seconds', .005), 'cleanup': cleanup}
        save(trial/'cleanup.json', cleanup); save(trial/'supervision.json', result)
        return result

    def execute_fixture(self, costs=None, evidence=None):
        self.seen = []
        known = {'accounting_verified': True, 'complete': True, 'api_calls': 3,
                 'charged_tokens': 150, 'total_tokens': 150, 'reported_tokens': 150, 'violations': []}
        with patch.object(preflight, 'supervise', side_effect=self.fake_supervise), \
                patch.object(preflight, 'cost_receipt', side_effect=costs or [deepcopy(known) for _ in range(6)]), \
                patch('scripts.audit_hermes_preflight.native_session', return_value=evidence or {
                    'transport_roundtrip_capable': True, 'semantic_success': False, 'semantic_score': .25,
                    'business_committed': False}), \
                patch('scripts.audit_hermes_preflight.cleanup_check', return_value=True):
            with redirect_stdout(io.StringIO()):
                return preflight.execute(self.out, creds=self.creds, executor=fixture_executor)

    def test_rejected_semantics_keep_six_fixed_slots_but_fixtures_cannot_claim_capability(self):
        self.prepare(); report = self.execute_fixture()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['attempted_slots'], 6)
        self.assertFalse(report['capability_pass'])
        self.assertTrue(report['fixture'])
        self.assertEqual(report['usage']['physical_model_calls'], 18)
        self.assertEqual(report['usage']['total_tokens'], 900)
        self.assertEqual(len({str(k['root']) for k in self.seen}), 6)
        for first, second in zip(self.seen[::2], self.seen[1::2]):
            self.assertEqual(first['world'].snapshot(), second['world'].snapshot())
            self.assertIsNot(first['world'], second['world'])
            self.assertEqual(first['case'], second['case'])
        with self.assertRaisesRegex(ValueError, 'one-shot'):
            preflight.execute(self.out, creds=self.creds, executor=fixture_executor)
        for path in self.out.rglob('*.json'):
            self.assertNotIn(self.creds['api_key'], path.read_text())

    def test_unknown_receipt_halts_without_replacement_and_reserves_entire_missing_slot(self):
        self.prepare()
        missing = preflight.cost_receipt(None)
        report = self.execute_fixture(costs=[missing])
        self.assertEqual(report['status'], 'halted_infrastructure')
        self.assertEqual(report['attempted_slots'], 1)
        self.assertEqual(report['usage']['charged_or_reserved_model_calls'], 16)
        self.assertEqual(report['usage']['charged_or_reserved_tokens'], 250000)
        self.assertIsNone(report['usage']['total_tokens'])
        self.assertEqual(sum(s['status'] == 'not_attempted' for s in report['slots']), 5)

    def test_physical_overrun_is_retained_not_clipped(self):
        self.prepare()
        over = {'accounting_verified': True, 'complete': True, 'api_calls': 17,
                'charged_tokens': 270000, 'total_tokens': 270000, 'reported_tokens': 270000,
                'violations': ['physical_slot_cap']}
        report = self.execute_fixture(costs=[over])
        self.assertEqual(report['status'], 'halted_infrastructure')
        self.assertEqual(report['usage']['physical_model_calls'], 17)
        self.assertEqual(report['usage']['total_tokens'], 270000)
        self.assertEqual(report['usage']['charged_or_reserved_tokens'], 270000)

    def test_known_receipt_survives_post_return_exception(self):
        self.prepare(); self.supervision_status = 'exception'
        report = self.execute_fixture()
        self.assertEqual(report['status'], 'halted_infrastructure')
        self.assertTrue(report['usage']['complete'])
        self.assertEqual(report['usage']['total_tokens'], 150)

    def test_interrupted_return_retains_costs_and_stops_fixed_slots(self):
        self.prepare(); self.supervision_status = 'interrupted'
        previous = signal.getsignal(signal.SIGTERM)
        report = self.execute_fixture()
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(report['slots'][0]['status'], 'interrupted')
        self.assertEqual(report['attempted_slots'], 1)
        self.assertEqual(report['usage']['total_tokens'], 150)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_cleanup_allowance_cannot_extend_primary_execution_deadline(self):
        self.prepare(); self.primary_seconds = 425
        report = self.execute_fixture()
        self.assertEqual(report['status'], 'halted_infrastructure')
        self.assertEqual(report['attempted_slots'], 1)
        self.assertTrue(report['usage']['complete'])

    def test_per_slot_native_caps_and_transport_forwarded(self):
        manifest = self.prepare(); self.execute_fixture()
        for kwargs, slot in zip(self.seen, manifest['slots']):
            self.assertEqual(kwargs['hermes_transport'], slot['mode'])
            self.assertEqual((kwargs['max_iterations'], kwargs['max_tokens'], kwargs['max_total_tokens'], kwargs['timeout_seconds']),
                             (16, 4096, 250000, 420))


def process_fixture(*, root, employee, hang=False, terminate_parent=False):
    """Local process/socket fixture, never Hermes or bubblewrap."""
    root = Path(root); computer = root/'computers'/employee
    control = computer/'control'; control.mkdir(parents=True)
    alias = Path(tempfile.mkdtemp(prefix='lifespan-bwrap-'))
    (alias/'control').symlink_to(control, target_is_directory=True)
    sock = socket.socket(socket.AF_UNIX); sock.bind(str(control/'command.sock'))
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
    save(computer/'instance.json', {'pid': os.getpid(), 'sandbox_pid': child.pid,
                                   'rpc_socket': str(alias/'control/command.sock')})
    try:
        if terminate_parent:
            time.sleep(.35)
            os.kill(os.getppid(), signal.SIGTERM)
        time.sleep(10 if hang else .35)
        record = {'fixture_only': True}; save(root/'session.json', record)
        return record
    finally:
        child.terminate(); child.wait(timeout=2); sock.close()


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.trial = Path(self.temp.name)/'trial'

    def test_normal_fixture_preserves_session_and_removes_owned_stale_socket(self):
        result = processes.supervise(process_fixture, {'root': self.trial/'native', 'employee': 'fixture'}, self.trial,
                                     timeout_seconds=2, cleanup_seconds=2)
        self.assertEqual(result['status'], 'returned')
        self.assertEqual(result['cleanup']['status'], 'confirmed')
        self.assertTrue(result['cleanup']['underlying_control_socket_absent'])
        self.assertTrue(result['cleanup']['underlying_socket_removed_by_supervisor'])
        self.assertEqual(result['cleanup']['root_identity']['sid'], result['cleanup']['root_identity']['pid'])
        self.assertTrue((self.trial/'native/session.json').exists())

    def test_deadline_kills_only_owned_fixture_identities_without_retry(self):
        result = processes.supervise(process_fixture,
            {'root': self.trial/'native', 'employee': 'fixture', 'hang': True}, self.trial,
            timeout_seconds=.5, cleanup_seconds=2)
        self.assertEqual(result['status'], 'timeout')
        self.assertTrue(result['cleanup']['forced'])
        known = {(r['pid'], r['start_ticks']) for r in result['cleanup']['owned_processes']}
        self.assertTrue(all((r['pid'], r['start_ticks']) in known for r in result['cleanup']['signals']))
        self.assertNotIn(os.getpid(), {r['pid'] for r in result['cleanup']['signals']})
        self.assertLess(result['elapsed_seconds'], 3)

    def test_reused_pid_is_not_same_owned_identity(self):
        old = {'pid': 123, 'uid': 5, 'start_ticks': 10, 'boot_id': 'fixture'}
        self.assertFalse(processes.same_identity(old, {**old, 'start_ticks': 11}))
        self.assertFalse(processes.same_identity(old, {**old, 'boot_id': 'another'}))

    def test_parent_sigterm_is_durable_interruption_with_owned_cleanup(self):
        previous = signal.getsignal(signal.SIGTERM)
        result = processes.supervise(process_fixture,
            {'root': self.trial/'native', 'employee': 'fixture', 'hang': True, 'terminate_parent': True}, self.trial,
            timeout_seconds=2, cleanup_seconds=2)
        self.assertEqual(result['status'], 'interrupted')
        self.assertTrue(result['cleanup']['forced'])
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual(preflight.read(self.trial/'supervision.json')['status'], 'interrupted')
        self.assertNotIn(os.getpid(), {r['pid'] for r in result['cleanup']['signals']})

    def test_repeated_sigterm_requests_do_not_raise_or_replace_previous_handler(self):
        previous = signal.getsignal(signal.SIGTERM)
        with processes.interruption_scope() as stop:
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGTERM)
            self.assertTrue(stop['requested'])
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)


if __name__ == '__main__':
    unittest.main()
