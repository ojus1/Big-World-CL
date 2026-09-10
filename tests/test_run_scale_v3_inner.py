"""Supervisor fixtures use threads and local files, never a native/model call."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts import run_scale_v3_inner as launch


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.out = self.root / 'lifespan/artifacts/study'
        self.out.mkdir(parents=True)
        self.events = []; self.cleaned = []
        self.manifest = {'source_sha256': {}, 'registration_tools_sha256': {}, 'dependencies': {},
            'launch_policy': {'workers': 2, 'per_world_wall_seconds': 86400,
                              'mirofish_service_url': 'http://127.0.0.1:5002'},
            'slots': [{'run_id': f'fixture-{i}', 'relative_path': f'runs/fixture-{i}'} for i in range(6)]}
        self.handles = []
        for slot in self.manifest['slots']:
            (self.out / slot['relative_path']).mkdir(parents=True)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        def mock(obj, name, **kwargs):
            return self.stack.enter_context(patch.object(obj, name, **kwargs))
        self.mock = mock
        mock(launch, 'ROOT', new=self.root); mock(launch.process, 'ROOT', new=self.root)
        mock(launch, 'credentials', return_value={'model': 'fixture', 'base_url': 'https://example.invalid'})
        mock(launch, 'source_hashes', return_value={}); mock(launch, 'tooling', return_value={})
        mock(launch, 'dependency_provenance', return_value={})
        mock(launch.contract, 'validate', return_value=self.manifest)
        mock(launch, 'committed_sources', return_value='1' * 40)
        mock(launch, 'verify_prerequisites', return_value={'schema_version': 1, 'verified': True, 'checks': []})
        mock(launch.process, 'validate_installation', return_value={'fixture': True})
        mock(launch.process, 'start_service', side_effect=lambda *a, **k: self.events.append('service-start') or 'service')
        mock(launch.process, 'verify_service', return_value={})
        self.service_cleanup = mock(launch.process, 'cleanup_service', side_effect=self.cleanup_service)
        mock(launch.process, 'spawn_world', side_effect=self.spawn)
        mock(launch.process, 'observe_world', side_effect=self.observe)
        mock(launch.process, 'cleanup_world', side_effect=self.cleanup)
        self.mock(launch, 'LAUNCH_LIMITS', new={**launch.LAUNCH_LIMITS, 'observation_interval_seconds': .005})
        self.gate = self.out / 'scope/GATE.json'; launch.process.save(self.gate, {'fixture': True})
        self.start = time.monotonic()
        self.gate_value = {'execution_started_monotonic': self.start,
            'execution_deadline': self.start + launch.contract.SCOPE_LIMITS['execution_seconds'],
            'scope_gate_sha256': launch.contract.sha(self.gate)}
        self.gate_check = mock(launch, 'validate_worker_gate', return_value=self.gate_value)

    def spawn(self, *, run_dir, receipt_dir):
        self.assertTrue((self.out / 'EXECUTION.json').exists())
        receipt_dir.mkdir()
        launch.process.save(receipt_dir / 'WORLD_START.json', {'fixture': run_dir.name})
        handle = SimpleNamespace(receipt_dir=receipt_dir, started_monotonic=time.monotonic(),
                                 polls=0, name=run_dir.name, observed=0)
        def poll():
            handle.polls += 1
            return 0 if handle.polls >= 3 else None
        handle.poll = poll; self.handles.append(handle); self.events.append('start-' + handle.name)
        return handle

    def observe(self, handle, run, service):
        handle.observed += 1
        return {}

    def cleanup(self, handle, run, service, *, timeout_seconds):
        self.assertEqual(timeout_seconds, launch.LAUNCH_LIMITS['world_cleanup_seconds'])
        self.cleaned.append(handle.name)
        handle.poll = lambda: 0
        value = {'started_monotonic': time.monotonic(), 'ended_monotonic': time.monotonic(), 'status': 'confirmed'}
        launch.process.save(handle.receipt_dir / 'WORLD_CLEANUP.json', value, exclusive=True)
        self.events.append('cleanup-' + handle.name)
        return value

    def cleanup_service(self, service, *, timeout_seconds):
        self.assertEqual(len(self.cleaned), len(self.handles))
        self.events.append('service-cleanup')
        return {'status': 'confirmed'}

    def execute(self):
        return launch.execute(self.out, campaign_sha256='a' * 64, prerequisite_paths={}, scope_gate={'fixture': True})

    def test_six_slots_canonical_order_cleanup_and_exact_receipt_times(self):
        self.assertTrue(self.execute()['inner_completed'])
        rows = launch.contract.read(self.out / 'execution_results.json')['runs']
        self.assertEqual([r['run_id'] for r in rows], [s['run_id'] for s in self.manifest['slots']])
        self.assertEqual(len(self.handles), 6)
        for row, handle in zip(rows, self.handles):
            raw = launch.contract.read(handle.receipt_dir / 'WORLD_CLEANUP.json')
            self.assertEqual(row['elapsed_seconds'], raw['ended_monotonic'] - handle.started_monotonic)
        self.assertEqual(self.events[-1], 'service-cleanup')
        self.assertEqual(result := launch.contract.read(self.out / 'STATUS.json')['slots'],
                         [{'run_id': s['run_id'], 'wave': i//2, 'status': 'terminal'}
                          for i, s in enumerate(self.manifest['slots'])])
        self.assertFalse((self.out / 'AUDIT.json').exists())

    def test_durable_intent_prevents_a_second_launch(self):
        self.execute()
        with self.assertRaises(FileExistsError): self.execute()
        self.assertEqual(len(self.handles), 6)

    def test_failed_prerequisite_prevents_intent_and_service(self):
        with patch.object(launch, 'verify_prerequisites', side_effect=ValueError('fixture_fail')):
            with self.assertRaises(ValueError): self.execute()
        self.assertFalse((self.out / 'EXECUTION.json').exists()); self.assertFalse(self.events)

    def test_failed_service_keeps_intent_and_six_slot_audit(self):
        with patch.object(launch.process, 'start_service', side_effect=ValueError('fixture_fail')):
            self.execute()
        self.assertTrue((self.out / 'EXECUTION.json').exists())
        self.assertTrue((self.out / 'SUPERVISOR_INTERRUPTED.json').exists())
        self.assertFalse(self.handles); self.service_cleanup.assert_not_called()
        self.assertEqual(len(launch.contract.read(self.out / 'STATUS.json')['slots']), 6)

    def test_observation_failure_cleans_active_pair_and_halts_later_slots(self):
        def observe(handle, run, service):
            if handle.name == 'fixture-0': raise ValueError('fixture_observer_failed')
            return self.observe(handle, run, service)
        with patch.object(launch.process, 'observe_world', side_effect=observe): self.execute()
        rows = launch.contract.read(self.out / 'execution_results.json')['runs']
        self.assertLessEqual(len(rows), 2); self.assertEqual(rows[0]['termination_reason'], 'observation_failed')
        self.assertLessEqual(len(self.handles), 2)
        states = launch.contract.read(self.out / 'STATUS.json')['slots']
        self.assertTrue(all(s['status'] == 'unlaunched' for s in states[2:]))

    def test_cleanup_does_not_block_another_worlds_observation(self):
        started = threading.Event(); observed = threading.Event()
        def cleanup(handle, run, service, **kwargs):
            if handle.name == 'fixture-0':
                started.set(); self.assertTrue(observed.wait(1), 'another world was blocked by cleanup')
            return self.cleanup(handle, run, service, **kwargs)
        def observe(handle, run, service):
            if handle.name == 'fixture-0': handle.poll = lambda: 0
            elif started.is_set(): observed.set()
            return self.observe(handle, run, service)
        with patch.object(launch.process, 'cleanup_world', side_effect=cleanup), patch.object(
                launch.process, 'observe_world', side_effect=observe): self.execute()
        self.assertTrue(observed.is_set())

    def test_provenance_change_stops_further_dispatch_and_cleans_live_world(self):
        with patch.object(launch, 'runtime_binding', side_effect=[({}, {}, {}), ({}, {}, {}), ValueError('changed')]):
            self.execute()
        self.assertEqual(len(self.handles), 1); self.assertEqual(len(self.cleaned), 1)
        self.assertTrue((self.out / 'SUPERVISOR_INTERRUPTED.json').exists())

    def test_deadline_has_no_retry_or_budget_renewal(self):
        run = self.out / self.manifest['slots'][0]['relative_path']
        # Standalone monitor with a fixed expired start, no service dispatch.
        folder = self.out / 'monitor'; folder.mkdir()
        launch.process.save(folder / 'WORLD_START.json', {'fixture': True})
        handle = SimpleNamespace(receipt_dir=folder, started_monotonic=time.monotonic()-2,
            name=run.name, observed=0, poll=lambda: None)
        result = launch.monitor_world(handle, run, 'service', stop=threading.Event(), wall_seconds=1)
        self.assertEqual(result['termination_reason'], 'wall_limit')
        self.assertEqual(self.cleaned, [run.name])

    def test_fixed_pair_barrier_waits_for_slow_peer_cleanup(self):
        def cleanup(handle, run, service, **kwargs):
            if handle.name == 'fixture-1': time.sleep(.025)
            return self.cleanup(handle, run, service, **kwargs)
        with patch.object(launch.process, 'cleanup_world', side_effect=cleanup):
            self.assertTrue(self.execute()['inner_completed'])
        for wave in (1, 2):
            new = self.events.index('start-fixture-' + str(wave * 2))
            for prior in (wave*2-2, wave*2-1):
                self.assertLess(self.events.index('cleanup-fixture-' + str(prior)), new)

    def test_gate_refusal_happens_before_credentials_or_service(self):
        with patch.object(launch, 'validate_worker_gate', side_effect=ValueError('gate')), patch.object(
                launch, 'credentials') as creds:
            with self.assertRaisesRegex(ValueError, 'gate'): self.execute()
            creds.assert_not_called()
        self.assertFalse(self.events)

    def test_no_inner_cli_or_optional_gate_fallback(self):
        import ast
        module = ast.parse(Path(launch.__file__).read_text())
        self.assertFalse(any(isinstance(n, ast.FunctionDef) and n.name == 'main' for n in module.body))
        wrapper = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_worker_gate')
        self.assertIn('scripts.run_scale_v3', ast.unparse(wrapper))
        self.assertNotIn('except', ast.unparse(wrapper))

    def test_gate_hash_and_clock_cannot_be_changed(self):
        for changes in ({'scope_gate_sha256': '0'*64}, {'execution_deadline': float('nan')},
                        {'execution_started_monotonic': True},
                        {'execution_deadline': self.gate_value['execution_deadline'] + 1}):
            with self.subTest(changes=changes), patch.object(launch, 'validate_worker_gate',
                    return_value={**self.gate_value, **changes}), patch.object(launch, 'credentials') as creds:
                with self.assertRaises(ValueError): self.execute()
                creds.assert_not_called()

    def test_unconfirmed_world_cleanup_stops_next_pair(self):
        def cleanup(*args, **kwargs):
            value = self.cleanup(*args, **kwargs); value['status'] = 'unconfirmed'; return value
        with patch.object(launch.process, 'cleanup_world', side_effect=cleanup):
            self.assertFalse(self.execute()['inner_completed'])
        self.assertLessEqual(len(self.handles), 2)
        self.assertEqual(len(self.cleaned), len(self.handles))

    def test_nonzero_native_exit_stops_next_pair(self):
        def spawn(**kwargs):
            h = self.spawn(**kwargs); h.poll = lambda: 1; return h
        def cleanup(handle, *args, **kwargs):
            value = self.cleanup(handle, *args, **kwargs); handle.poll = lambda: 1; return value
        with patch.object(launch.process, 'spawn_world', side_effect=spawn), patch.object(
                launch.process, 'cleanup_world', side_effect=cleanup):
            self.assertFalse(self.execute()['inner_completed'])
        self.assertLessEqual(len(self.handles), 2)

    def test_service_cleanup_failure_prevents_inner_success(self):
        with patch.object(launch.process, 'cleanup_service', return_value={'status': 'unconfirmed'}):
            self.assertFalse(self.execute()['inner_completed'])
        self.assertEqual(len(self.handles), 6)
        self.assertTrue((self.out / 'SUPERVISOR_INTERRUPTED.json').exists())

    def test_status_write_failure_does_not_skip_active_or_service_cleanup(self):
        original = launch.process.save
        failed = False
        def save(path, value, **kwargs):
            nonlocal failed
            if Path(path).name == 'STATUS.json' and not failed:
                failed = True; raise OSError('fixture_write')
            return original(path, value, **kwargs)
        with patch.object(launch.process, 'save', side_effect=save):
            result = self.execute()
        self.assertFalse(result['inner_completed'])
        self.assertEqual(len(self.cleaned), len(self.handles))
        self.assertEqual(self.events[-1], 'service-cleanup')
        self.assertLessEqual(len(self.handles), 1)

    def test_final_status_write_latency_cannot_claim_in_time_inner_success(self):
        original = launch.process.save; clock = time.monotonic; late = False
        def save(path, value, **kwargs):
            nonlocal late
            answer = original(path, value, **kwargs)
            if Path(path).name == 'STATUS.json' and value['terminal_worlds'] == 6:
                late = True
            return answer
        def now():
            return self.gate_value['execution_deadline'] + 1 if late else clock()
        with patch.object(launch.process, 'save', side_effect=save), patch.object(
                launch.time, 'monotonic', side_effect=now):
            result = self.execute()
        self.assertFalse(result['inner_completed'])
        self.assertGreater(result['finished_monotonic'], result['execution_deadline'])
        self.assertEqual(result['terminal_worlds'], 6)
        self.assertTrue((self.out / 'SUPERVISOR_INTERRUPTED.json').exists())

    def test_preparation_consumes_absolute_campaign_clock(self):
        late = self.gate_value['execution_deadline'] - 100
        with patch.object(launch.time, 'monotonic', return_value=late):
            result = self.execute()
        self.assertFalse(result['inner_completed']); self.assertFalse(self.handles)
        self.assertNotIn('service-start', self.events)



class CommittedSourceTests(unittest.TestCase):
    def test_tracked_bytes_must_match_recorded_commit_but_unrelated_files_are_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
            git('init', '-q'); path = root / 'source.py'; path.write_text('# fixture\n')
            git('add', 'source.py'); git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                        'commit', '-qm', 'fixture')
            source = {'source.py': launch.contract.sha(path)}
            with patch.object(launch, 'ROOT', root):
                (root / 'unrelated.md').write_text('Unrelated local documentation.\n')
                self.assertEqual(launch.committed_sources(source, {}), git('rev-parse', 'HEAD').decode().strip())
                path.write_text('# changed\n')
                with self.assertRaises(ValueError): launch.committed_sources({'source.py': launch.contract.sha(path)}, {})


if __name__ == '__main__': unittest.main()
