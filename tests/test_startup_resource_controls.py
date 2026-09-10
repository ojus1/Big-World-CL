"""Offline fixtures only: never invoke systemd, providers or native workers."""
import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import startup_resource_controls as probe


NAME = probe.PREFIX + 'a' * 32 + '.service'
UID = 1000
GROUP = f'/user.slice/user-{UID}.slice/user@{UID}.service/app.slice/{NAME}'


def fixture():
    kernel = {'memory.max': '67108864', 'memory.swap.max': '0',
              'pids.max': '32', 'cpu.max': '100000 100000', 'io.weight': None}
    worker = {'pid': 4242, 'uid': UID, 'start_ticks': 77, 'boot_id': 'fixture-boot',
              'cgroup': GROUP, 'kernel': deepcopy(kernel)}
    current = {key: value for key, value in worker.items() if key != 'kernel'}
    current['state'] = 'S'
    unit = {'Id': NAME, 'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
            'MainPID': '4242', 'ControlGroup': GROUP, 'InvocationID': 'b' * 32}
    return worker, unit, current, kernel


def absent_unit():
    return {'Id': NAME, 'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
            'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}


class ObservationTests(unittest.TestCase):
    def validate(self, values):
        return probe.validate_observation(NAME, *values, uid=UID)

    def test_four_kernel_controls_and_unavailable_io(self):
        result = self.validate(fixture())
        self.assertTrue(result['verified'])
        self.assertEqual(result['cpu_quota_cores'], 1)
        self.assertEqual(result['io'], {'requested': False, 'qualified': False,
            'status': 'unavailable', 'kernel_file_present': False, 'readback_sha256': None})

    def test_present_io_is_observed_without_effectiveness_claim(self):
        values = fixture()
        values[0]['kernel']['io.weight'] = values[3]['io.weight'] = 'default 100'
        result = self.validate(values)['io']
        self.assertEqual(result['status'], 'observed_unrequested')
        self.assertFalse(result['qualified'])
        self.assertFalse(result['requested'])
        self.assertNotIn('default', json.dumps(result))

    def test_limit_failures_and_independent_readback_disagreement(self):
        for key, wrong in [('memory.max', 'max'), ('memory.swap.max', '1'),
                           ('pids.max', 'max'), ('cpu.max', 'max 100000'),
                           ('cpu.max', '200000 100000'), ('cpu.max', '0 0')]:
            with self.subTest(key=key, wrong=wrong):
                values = fixture()
                values[0]['kernel'][key] = values[3][key] = wrong
                with self.assertRaises(ValueError):
                    self.validate(values)
        values = fixture(); values[3]['memory.max'] = '1'
        with self.assertRaisesRegex(ValueError, 'readback_mismatch'):
            self.validate(values)

    def test_independent_pid_uid_boot_start_and_cgroup_binding(self):
        for key, wrong in [('pid', 999), ('uid', 0), ('start_ticks', 78),
                           ('boot_id', 'another-boot'), ('state', 'Z'), ('cgroup', '/foreign')]:
            with self.subTest(key=key):
                values = fixture(); values[2][key] = wrong
                with self.assertRaises(ValueError):
                    self.validate(values)
        values = fixture(); values[0]['pid'] = True
        with self.assertRaisesRegex(ValueError, 'invalid_probe_identity'):
            self.validate(values)

    def test_unit_identity_and_foreign_cgroup_rejected(self):
        for key, wrong in [('Id', 'existing.service'), ('MainPID', '999'),
                           ('ControlGroup', '/foreign'), ('InvocationID', ''),
                           ('ActiveState', 'inactive')]:
            with self.subTest(key=key):
                values = fixture(); values[1][key] = wrong
                with self.assertRaises(ValueError):
                    self.validate(values)
        for group in [GROUP.replace('user-1000', 'user-0'), '/system.slice/' + NAME,
                      GROUP.replace('/app.slice/', '/app.slice/../'), GROUP + '/child']:
            values = fixture(); values[0]['cgroup'] = values[1]['ControlGroup'] = values[2]['cgroup'] = group
            with self.assertRaisesRegex(ValueError, 'foreign_probe_cgroup'):
                self.validate(values)

    def test_kernel_files_read_under_only_owned_cgroup(self):
        with tempfile.TemporaryDirectory() as root, patch.object(probe, 'CGROUP_ROOT', Path(root)):
            base = Path(root) / GROUP.lstrip('/'); base.mkdir(parents=True)
            for key, value in fixture()[3].items():
                if value is not None:
                    (base / key).write_text(value + '\n')
            self.assertEqual(probe.kernel_readback(GROUP, UID, NAME), fixture()[3])
            for group in [None, '/system.slice/' + NAME, GROUP.replace('app.slice', '..')]:
                with self.assertRaises(ValueError):
                    probe.kernel_readback(group, UID, NAME)

    def test_literal_payload_readback_with_mocked_kernel(self):
        worker, _, _, kernel = fixture()
        fields = ['S'] + ['0'] * 18 + [str(worker['start_ticks'])]
        data = {'/proc/self/stat': '4242 (fixture python) ' + ' '.join(fields),
                '/proc/self/cgroup': '0::' + GROUP + '\n',
                '/proc/sys/kernel/random/boot_id': worker['boot_id']}
        data.update({'/sys/fs/cgroup' + GROUP + '/' + key: value
                     for key, value in kernel.items() if value is not None})
        def read(path, *args, **kwargs):
            if str(path) not in data:
                raise FileNotFoundError
            return data[str(path)]
        output = io.StringIO()
        with patch.object(Path, 'read_text', read), patch.object(os, 'getpid', return_value=4242), \
             patch.object(os, 'getuid', return_value=UID), patch('sys.stdin', io.StringIO('\n')), \
             contextlib.redirect_stdout(output):
            exec(compile(probe.PAYLOAD, '<fixed-probe-fixture>', 'exec'), {})
        self.assertEqual(json.loads(output.getvalue()), worker)


class CleanupTests(unittest.TestCase):
    def test_collected_unit_and_original_pid_absent(self):
        worker, unit, _, _ = fixture()
        self.assertTrue(probe.cleanup_evidence(NAME, absent_unit(), worker, None, 0, unit)['confirmed'])

    def test_terminal_loaded_unit_must_have_same_invocation_and_zero_pid(self):
        worker, original, _, _ = fixture()
        terminal = dict(original, ActiveState='inactive', SubState='dead', MainPID='0')
        self.assertTrue(probe.cleanup_evidence(NAME, terminal, worker, None, 0, original)['confirmed'])
        for key, value in [('InvocationID', 'c' * 32), ('MainPID', '1234'), ('ControlGroup', '/foreign')]:
            with self.subTest(key=key):
                changed = dict(terminal, **{key: value})
                self.assertFalse(probe.cleanup_evidence(NAME, changed, worker, None, 0, original)['confirmed'])

    def test_absent_unit_is_insufficient_for_live_or_unbound_process(self):
        worker, unit, current, _ = fixture()
        for owned, state in [(worker, current), (None, None)]:
            self.assertFalse(probe.cleanup_evidence(NAME, absent_unit(), owned, state, 0, unit)['confirmed'])
        replaced = dict(current, start_ticks=78)
        result = probe.cleanup_evidence(NAME, absent_unit(), worker, replaced, 0, unit)
        self.assertTrue(result['confirmed'])
        self.assertEqual(result['original_process_state'], 'identity_replaced')
        self.assertFalse(result['unit_stop_or_kill_issued'])

    def test_active_or_foreign_unit_cannot_be_confirmed(self):
        worker, unit, _, _ = fixture()
        self.assertFalse(probe.cleanup_evidence(NAME, unit, worker, None, 0, unit)['confirmed'])
        with self.assertRaisesRegex(ValueError, 'cleanup_foreign_unit'):
            probe.cleanup_evidence(NAME, dict(absent_unit(), Id='other.service'), worker, None, 0)


class RunTests(unittest.TestCase):
    def run_fixture(self, out, *, mutate=None, timeout=False, reused=False, kill_race=False):
        worker, unit, current, kernel = fixture()
        if mutate:
            mutate(worker, unit, current, kernel)
        client = dict(current, pid=31337, cgroup='/fixture-parent', start_ticks=66)
        process = Mock(pid=31337, returncode=0)
        process.communicate.return_value = (b'', b'PRIVATE_SENTINEL')
        process.poll.return_value = 0
        identities = [client, current]
        if timeout:
            process.communicate.side_effect = subprocess.TimeoutExpired('PRIVATE_SENTINEL', 1)
            process.poll.side_effect = [None, -9]
            identities.append(dict(client, start_ticks=100) if reused else client)
            if kill_race:
                process.kill.side_effect = ProcessLookupError('PRIVATE_SENTINEL')
        identities.append(None)
        with patch.object(probe, 'unit_name', return_value=NAME), \
             patch.object(probe.os, 'getuid', return_value=UID), \
             patch.object(probe, 'show_unit', side_effect=[absent_unit(), unit, absent_unit()]) as show, \
             patch.object(probe.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(probe, 'identity', side_effect=identities), \
             patch.object(probe, 'first_line', return_value=probe.canonical(worker) + b'\n'), \
             patch.object(probe, 'kernel_readback', return_value=kernel):
            result = probe.run_probe(out)
        return result, process, popen, show

    def test_fixed_command_complete_receipts_permissions_and_privacy(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'new'
            result, process, popen, _ = self.run_fixture(out)
            self.assertTrue(result['ok'])
            command = popen.call_args.args[0]
            for value in probe.PROPERTIES:
                self.assertIn('--property=' + value, command)
            self.assertNotIn('IOWeight', ' '.join(command))
            self.assertEqual(command[-5:], ['-I', '-S', '-B', '-c', probe.PAYLOAD])
            self.assertIn('--unit=' + NAME, command)
            self.assertEqual(popen.call_args.kwargs['cwd'], '/')
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            process.communicate.assert_called_once()
            self.assertEqual(process.communicate.call_args.kwargs['input'], b'\n')
            process.kill.assert_not_called()
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            for file in out.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('PRIVATE_SENTINEL', file.read_text())
            for name, digest in result['receipt_sha256'].items():
                self.assertEqual(probe.sha((out / name).read_bytes()), digest)
            self.assertEqual(result['native_or_model_calls'], 0)
            self.assertFalse(result['existing_workload_controls_changed'])

    def test_timeout_kills_only_matching_direct_client_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as root:
            result, process, _, _ = self.run_fixture(Path(root) / 'new', timeout=True)
            self.assertFalse(result['ok'])
            process.kill.assert_called_once_with()
            cleanup = json.loads((Path(root) / 'new/CLEANUP.json').read_text())
            self.assertTrue(cleanup['own_client_forced_termination'])
            self.assertFalse(cleanup['streams_complete'])
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_reused_direct_client_identity_is_never_signaled(self):
        with tempfile.TemporaryDirectory() as root:
            result, process, _, _ = self.run_fixture(Path(root) / 'new', timeout=True, reused=True)
            self.assertFalse(result['ok'])
            process.kill.assert_not_called()

    def test_client_exit_race_still_writes_failed_cleanup_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            result, _, _, _ = self.run_fixture(Path(root) / 'new', timeout=True, kill_race=True)
            self.assertFalse(result['ok'])
            self.assertTrue((Path(root) / 'new/CLEANUP.json').is_file())
            self.assertIn('client_identity_cleanup', [row['stage'] for row in result['errors']])

    def test_kernel_failure_is_not_qualification(self):
        def wrong(worker, unit, current, kernel):
            worker['kernel']['pids.max'] = kernel['pids.max'] = 'max'
        with tempfile.TemporaryDirectory() as root:
            result, process, _, _ = self.run_fixture(Path(root) / 'new', mutate=wrong)
            self.assertFalse(result['ok'])
            self.assertFalse(result['cleanup']['confirmed'])
            self.assertIsNone(result['controls'])
            process.kill.assert_not_called()

    def test_existing_unit_never_spawns_or_controls(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(probe, 'unit_name', return_value=NAME), \
             patch.object(probe, 'show_unit', return_value=fixture()[1]), \
             patch.object(probe.subprocess, 'Popen') as spawn:
            result = probe.run_probe(Path(root) / 'new')
            spawn.assert_not_called()
            self.assertFalse(result['ok'])
            self.assertEqual(result['errors'][0]['code'], 'probe_unit_name_already_exists')

    def test_existing_output_or_symlink_parent_rejected_before_systemd(self):
        with tempfile.TemporaryDirectory() as root, patch.object(probe, 'show_unit') as show:
            base = Path(root)
            with self.assertRaisesRegex(ValueError, 'already_exists'):
                probe.run_probe(base)
            (base / 'link').symlink_to(base, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'real_directory'):
                probe.run_probe(base / 'link/new')
            show.assert_not_called()


class WireTests(unittest.TestCase):
    def test_generated_names_unique_and_external_names_refused(self):
        names = {probe.unit_name() for _ in range(100)}
        self.assertEqual(len(names), 100)
        for name in names:
            self.assertEqual(probe.checked_name(name), name)
        for name in ['sshd.service', NAME + ';anything', '../' + NAME, '--user', None]:
            with self.assertRaises(ValueError):
                probe.checked_name(name)

    def test_show_only_allowlisted_fields_without_stderr_leak(self):
        unit = fixture()[1]
        stdout = '\n'.join(f'{key}={value}' for key, value in unit.items()).encode()
        with patch.object(probe.subprocess, 'run', return_value=SimpleNamespace(
                stdout=stdout, stderr=b'PRIVATE_SENTINEL', returncode=0)) as run:
            self.assertEqual(probe.show_unit(NAME), unit)
            command = run.call_args.args[0]
            self.assertEqual(command[:4], ['systemctl', '--user', 'show', NAME])
            self.assertEqual(set(command[4:]), {'--property=' + k for k in probe.SHOW_KEYS})
        with patch.object(probe.subprocess, 'run', return_value=SimpleNamespace(
                stdout=stdout + b'\nEnvironment=PRIVATE_SENTINEL', returncode=0)):
            with self.assertRaisesRegex(ValueError, 'invalid_unit_observation'):
                probe.show_unit(NAME)

    def read_pipe(self, data):
        read, write = os.pipe()
        try:
            os.write(write, data); os.close(write); write = None
            with os.fdopen(read, 'rb') as stream:
                return probe.first_line(SimpleNamespace(stdout=stream), .5)
        finally:
            if write is not None:
                os.close(write)

    def test_readback_one_line_and_early_eof(self):
        self.assertEqual(self.read_pipe(b'{"fixture":true}\n'), b'{"fixture":true}\n')
        for data, error in [(b'', 'closed_before_readback'), (b'{}\n{}\n', 'unexpected_probe_output')]:
            with self.assertRaisesRegex(ValueError, error):
                self.read_pipe(data)

    def test_readback_length_bound(self):
        process = SimpleNamespace(stdout=Mock())
        selector = Mock()
        selector.__enter__ = Mock(return_value=selector)
        selector.__exit__ = Mock(return_value=False)
        selector.select.return_value = [True]
        with patch.object(probe.selectors, 'DefaultSelector', return_value=selector), \
             patch.object(probe.os, 'read', return_value=b'x' * 16385):
            with self.assertRaisesRegex(ValueError, 'readback_too_large'):
                probe.first_line(process, .5)


if __name__ == '__main__':
    unittest.main()
