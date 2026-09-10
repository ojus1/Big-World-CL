"""Pure boundary/fake-computer tests. No native startup, service or network use."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hermes_startup_probe as probe
from lifespan.evaluation.hermes_transport import contract


def fixture():
    expected = {'uid': 1000, 'boot_id': 'fixture-boot',
                'host_net_namespace': 'net:[10]', 'host_user_namespace': 'user:[11]',
                'unit': probe.UNIT_PREFIX + 'a' * 32 + '.service', 'invocation_id': 'b' * 32}
    current = {'uid': 1000, 'boot_id': 'fixture-boot', 'net_namespace': 'net:[20]',
               'user_namespace': 'user:[21]', 'interfaces': [{'name': 'lo', 'up': False}],
               'cgroup': '/user.slice/user-1000.slice/user@1000.service/app.slice/' + expected['unit'],
               'invocation_id': expected['invocation_id'], 'kernel': dict(probe.KERNEL_LIMITS)}
    return expected, current


class BoundaryTests(unittest.TestCase):
    def test_exact_owned_isolated_boundary(self):
        result = probe.verify_boundary(*fixture())
        self.assertTrue(result['verified'])
        self.assertFalse(result['io_isolation_qualified'])

    def test_host_namespaces_and_interface_changes_refused(self):
        expected, original = fixture()
        edits = [('net_namespace', expected['host_net_namespace']),
                 ('user_namespace', expected['host_user_namespace']),
                 ('net_namespace', None),
                 ('interfaces', [{'name': 'lo', 'up': True}]),
                 ('interfaces', [{'name': 'lo', 'up': False}, {'name': 'eth0', 'up': False}])]
        for key, value in edits:
            with self.subTest(key=key, value=value):
                current = deepcopy(original); current[key] = value
                with self.assertRaises(ValueError): probe.verify_boundary(expected, current)

    def test_uid_boot_invocation_and_foreign_cgroup_refused(self):
        expected, original = fixture()
        for key, value in [('uid', 0), ('boot_id', 'other'), ('invocation_id', 'c' * 32),
                           ('cgroup', '/user.slice/foreign.service')]:
            with self.subTest(key=key):
                current = deepcopy(original); current[key] = value
                with self.assertRaises(ValueError): probe.verify_boundary(expected, current)

    def test_each_kernel_control_is_required(self):
        expected, original = fixture()
        for key in probe.KERNEL_LIMITS:
            current = deepcopy(original); current['kernel'][key] = 'max'
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.verify_boundary(expected, current)

    def test_parent_contract_cannot_add_credentials_or_use_foreign_unit(self):
        expected, current = fixture()
        for changed in [dict(expected, api_key='SECRET_CANARY'), dict(expected, unit='other.service')]:
            with self.assertRaises(ValueError): probe.verify_boundary(changed, current)


class NativeBodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.out = Path(self.temp) / 'new-slot'
        self.expected, self.current = fixture()
        self.calls = []
        outer = self

        class FakeComputer:
            def __init__(self, root, employee, **kwargs):
                self.profile = root / employee / 'hermes'
                outer.calls.append(('init', kwargs))

            def start(self, credentials, timeout):
                outer.calls.append(('start', {'credentials': credentials, 'timeout': timeout}))
                return {'kind': 'ready', 'backend': 'bubblewrap', 'tool_names': ['terminal', 'skill_view'],
                        'evaluation_transport': contract('nonstreaming')}

            def run(self, *args, **kwargs):
                raise AssertionError('Never send work from a startup qualification')

            def close(self):
                outer.calls.append(('close', {}))

        self.fake = FakeComputer

    def run_fake(self, **kwargs):
        return probe.native_startup(self.out, self.expected, computer_factory=self.fake,
                                    boundary_reader=lambda: deepcopy(self.current), **kwargs)

    def test_start_once_close_once_no_work_or_cleanup_upgrade(self):
        result = self.run_fake()
        self.assertEqual([name for name, _ in self.calls], ['init', 'start', 'close'])
        self.assertLessEqual(self.calls[1][1]['timeout'], 150)
        self.assertGreater(self.calls[1][1]['timeout'], 0)
        self.assertEqual(self.calls[1][1]['credentials'], probe.CREDENTIALS)
        self.assertEqual(self.calls[0][1]['execution'], probe.EXECUTION)
        self.assertTrue(result['ready_observed'])
        self.assertEqual(result['work_requests_sent'], 0)
        self.assertFalse(result['complete_qualification'])
        self.assertFalse(result['independent_cleanup_confirmed'])
        self.assertNotIn('tokens', result)

    def test_refuses_host_before_factory_or_output_creation(self):
        self.current['net_namespace'] = self.expected['host_net_namespace']
        with self.assertRaises(ValueError): self.run_fake()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.out.exists())

    def test_existing_output_cannot_be_resumed(self):
        self.out.mkdir()
        with self.assertRaises(ValueError): self.run_fake()
        self.assertEqual(self.calls, [])

    def test_startup_failure_closes_and_retains_class_only(self):
        with patch.object(self.fake, 'start', side_effect=RuntimeError('SECRET_CANARY_PRIVATE')):
            result = self.run_fake()
        self.assertEqual(result['error_type'], 'RuntimeError')
        self.assertFalse(result['ready_observed'])
        self.assertEqual(self.calls[-1][0], 'close')
        self.assertNotIn('SECRET_CANARY_PRIVATE', (self.out / 'CHILD_RESULT.json').read_text())

    def test_close_failure_does_not_certify_cleanup(self):
        with patch.object(self.fake, 'close', side_effect=OSError('SECRET_CANARY_PRIVATE')):
            result = self.run_fake()
        self.assertEqual(result['close_error_type'], 'OSError')
        self.assertFalse(result['close_returned_within_allowance'])

    def test_boundary_drift_preserves_initial_evidence_without_terminal_result(self):
        after = deepcopy(self.current); after['boot_id'] = 'changed'
        with self.assertRaises(ValueError):
            probe.native_startup(self.out, self.expected, computer_factory=self.fake,
                                boundary_reader=iter([self.current, after]).__next__)
        self.assertTrue((self.out / 'BOUNDARY_BEFORE.json').exists())
        self.assertFalse((self.out / 'CHILD_RESULT.json').exists())

    def test_late_start_or_cleanup_is_not_accepted(self):
        for name, startup, cleanup in [('startup', 151, 1), ('cleanup', 1, 31)]:
            self.out = Path(self.temp) / name
            now = [100]
            original_start, original_close = self.fake.start, self.fake.close
            def start(computer, *args, **kwargs):
                value = original_start(computer, *args, **kwargs); now[0] += startup; return value
            def close(computer):
                original_close(computer); now[0] += cleanup
            with self.subTest(name=name), patch.object(probe.time, 'monotonic', side_effect=lambda: now[0]):
                with patch.object(self.fake, 'start', start), patch.object(self.fake, 'close', close):
                    result = self.run_fake()
            if name == 'startup':
                self.assertEqual(result['error_type'], 'ValueError')
            else:
                self.assertFalse(result['close_returned_within_allowance'])

    def test_parent_deadline_is_not_refreshed(self):
        with patch.object(probe.time, 'monotonic', return_value=100):
            result = self.run_fake(startup_deadline=120)
        self.assertEqual(self.calls[1][1]['timeout'], 20)
        self.assertEqual(result['startup_deadline'], 120)
        self.assertTrue((self.out / 'STARTUP_FINISHED.json').is_file())
        self.assertTrue((self.out / 'CLOSE_STARTED.json').is_file())

    def test_expired_or_extended_parent_deadline_refused_before_factory(self):
        for deadline in (99, 251, float('inf')):
            with self.subTest(deadline=deadline), patch.object(probe.time, 'monotonic', return_value=100):
                with self.assertRaises(ValueError): self.run_fake(startup_deadline=deadline)
        self.assertEqual(self.calls, [])

    def test_setup_overhead_prevents_late_native_launch(self):
        now = [100]
        original = self.fake.__init__
        def slow_setup(computer, *args, **kwargs):
            original(computer, *args, **kwargs); now[0] += 151
        with patch.object(probe.time, 'monotonic', side_effect=lambda: now[0]):
            with patch.object(self.fake, '__init__', slow_setup): result = self.run_fake()
        self.assertEqual([name for name, _ in self.calls], ['init', 'close'])
        self.assertFalse(result['ready_observed'])

    def test_capture_gate_observes_phase_receipts_before_close(self):
        def gate(directory, ready, deadline):
            self.assertTrue((directory / 'STARTUP_FINISHED.json').exists())
            self.assertTrue((directory / 'CLOSE_STARTED.json').exists())
            self.assertEqual(ready['kind'], 'ready')
            self.assertEqual(deadline, 130)
            self.assertNotIn('close', [name for name, _ in self.calls])
            self.calls.append(('gate', {}))
        with patch.object(probe.time, 'monotonic', return_value=100):
            result = self.run_fake(before_close=gate)
        self.assertEqual([name for name, _ in self.calls], ['init', 'start', 'gate', 'close'])
        self.assertIsNone(result['pre_close_error_type'])

    def test_capture_gate_errors_do_not_prevent_owned_close(self):
        def gate(*_): raise TimeoutError('SECRET_CANARY_PRIVATE')
        result = self.run_fake(before_close=gate)
        self.assertEqual(result['pre_close_error_type'], 'TimeoutError')
        self.assertEqual(self.calls[-1][0], 'close')
        self.assertNotIn('SECRET_CANARY_PRIVATE', (self.out / 'CHILD_RESULT.json').read_text())

    def test_capture_gate_wait_consumes_cleanup_allowance(self):
        now = [100]
        def gate(*_): now[0] += 31
        with patch.object(probe.time, 'monotonic', side_effect=lambda: now[0]):
            result = self.run_fake(before_close=gate)
        self.assertFalse(result['close_returned_within_allowance'])
        self.assertEqual(result['close_elapsed_seconds'], 31)


if __name__ == '__main__':
    unittest.main()
