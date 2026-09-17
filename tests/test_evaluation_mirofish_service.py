"""Offline service-routing fixtures; no MiroFish startup or provider calls.

NativeActors and MiroFishRuntime are real. Only HTTP, bootstrap and delegated
work are substituted, so these are routing/evidence tests, not native evidence.
"""
from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation import runner
from lifespan.evaluation.protocol import ExperimentConfig, digest, scenario
from lifespan.mirofish import MiroFishRuntime, SERVICE_BINDING_FILE, save, service_binding
from scripts.audit_evaluation import mirofish_service_check, sha


class FakeClient:
    instances = []

    def __init__(self, *, base_url, **kwargs):
        self.base_url = base_url.rstrip('/') + '/'
        self.trust_env = kwargs.get('trust_env', True)
        self.follow_redirects = kwargs.get('follow_redirects', False)
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    def get(self, path, **kwargs):
        self.calls.append((self.base_url, path, kwargs))
        from lifespan.actor_contract import wire
        data = wire.capabilities() if path.endswith('actor-contract-support') else {'fixture': True}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'success': True, 'data': data})

    def close(self):
        self.closed = True


@contextmanager
def fake_http():
    FakeClient.instances.clear()
    with patch.dict(sys.modules, {'httpx': SimpleNamespace(Client=FakeClient, Timeout=lambda *a, **k: None)}):
        yield


class ServiceConfigTests(unittest.TestCase):
    def test_historical_default_fingerprints_and_omission(self):
        # Exact defaults from pre-change commit 131dea4.
        config = ExperimentConfig()
        self.assertEqual(config.fingerprint, '463e2da17efe0e25d05d8f61bb3782370f0c3346721d507f84d14ecef41436a1')
        self.assertEqual(digest(scenario(config)), 'ae37cbd3f6232dae15c63e066c7d500fccf87044d413cf3afef5b28fb5d60d0d')
        self.assertNotIn('mirofish_service_url', config.public())
        self.assertNotIn('mirofish_service_url', scenario(config))

    def test_canonical_loopback_origins_and_json_roundtrip(self):
        for value, expected in [('http://localhost:5002/', 'http://127.0.0.1:5002'),
                                ('HTTP://127.0.0.1:05002/', 'http://127.0.0.1:5002'),
                                ('http://127.0.0.2:1', 'http://127.0.0.2:1'),
                                ('http://[0:0:0:0:0:0:0:1]:65535', 'http://[::1]:65535')]:
            with self.subTest(value=value):
                config = ExperimentConfig(mirofish_service_url=value)
                self.assertEqual(config.mirofish_service_url, expected)
                self.assertEqual(config.public()['mirofish_service_url'], expected)
                self.assertEqual(scenario(config)['mirofish_service_url'], expected)
                self.assertEqual(ExperimentConfig(**json.loads(json.dumps(config.public()))), config)

    def test_unsafe_or_ambiguous_urls_fail_before_work(self):
        for value in [True, 5002, {}, '', 'localhost:5002', 'http://127.0.0.1',
                      'https://127.0.0.1:5002', 'http://127.0.0.1:0', 'http://127.0.0.1:65536',
                      'http://127.0.0.1:-1', 'http://127.0.0.1:abc', 'http://example.com:5002',
                      'http://10.0.0.1:5002', 'http://0.0.0.0:5002', 'http://[::]:5002',
                      'http://localhost.example.com:5002', 'http://127.1:5002',
                      'http://user:pass@127.0.0.1:5002', 'http://@127.0.0.1:5002',
                      'http://127.0.0.1:5002/api', 'http://127.0.0.1:5002?', 'http://127.0.0.1:5002#',
                      'http://[::1%lo]:5002', 'http://127.0.0.1:5002\n', ' http://127.0.0.1:5002']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExperimentConfig(mirofish_service_url=value)


class NativeServiceTests(unittest.TestCase):
    def test_actual_native_constructor_routes_and_binds_before_bootstrap(self):
        for url in (None, 'http://localhost:5002/'):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as tmp, fake_http():
                out = Path(tmp); save(out / 'persona_cohort.json', {'personas': []})
                cfg = ExperimentConfig(days=8, mirofish_service_url=url)
                def bootstrap(runtime, blueprint, cohort):
                    if url is not None:
                        self.assertEqual(json.loads((runtime.out / SERVICE_BINDING_FILE).read_text()), service_binding(cfg.mirofish_service_url))
                    self.assertEqual(len(blueprint['employees']), len(Ecosystem(16, 101).participants()))
                with patch.object(MiroFishRuntime, 'bootstrap', bootstrap):
                    actors = runner.NativeActors(out, Ecosystem(16, 101), scenario(cfg), deadline=12345)
                self.assertIsInstance(actors.runtime, MiroFishRuntime)
                client = actors.runtime.client
                expected = cfg.mirofish_service_url or 'http://127.0.0.1:5001'
                self.assertEqual(client.base_url, expected + '/')
                self.assertEqual(client.trust_env, url is None)
                self.assertEqual(actors.runtime.evaluation_deadline, 12345)
                if url is None:
                    self.assertFalse((out / 'actors' / SERVICE_BINDING_FILE).exists())
                actors.pause()

    def test_contract_handshake_occurs_after_client_binding(self):
        contract = {'version': 'actor-json-v1', 'max_output_tokens': 4096, 'timeout_seconds': 120}
        with tempfile.TemporaryDirectory() as tmp, fake_http():
            runtime = MiroFishRuntime(tmp, base_url='http://127.0.0.1:5002',
                evaluation_service_url='http://127.0.0.1:5002', actor_output_contract=contract)
            self.assertEqual(len(runtime.client.calls), 1)
            self.assertEqual(runtime.client.calls[0][0], 'http://127.0.0.1:5002/')
            self.assertEqual(json.loads((Path(tmp) / SERVICE_BINDING_FILE).read_text()), service_binding('http://127.0.0.1:5002'))
            self.assertEqual(runtime.actor_output_contract, contract)
            runtime.client.close()

    def test_client_url_and_routing_mutation_block_dispatch(self):
        for key, value in [('base_url', 'http://127.0.0.1:5003/'), ('trust_env', True), ('follow_redirects', True)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp, fake_http():
                runtime = MiroFishRuntime(tmp, base_url='http://127.0.0.1:5002', evaluation_service_url='http://127.0.0.1:5002')
                setattr(runtime.client, key, value)
                with self.assertRaisesRegex(ValueError, 'routing settings changed'):
                    runtime.call('/api/simulation/start', {'fixture': True})
                self.assertFalse(runtime.client.calls)
                runtime.client.close()

    def test_failed_contract_handshake_closes_allocated_client(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as tmp, fake_http(), \
                 patch.object(FakeClient, 'get', side_effect=TimeoutError('offline handshake failure')) as request:
                url = 'http://127.0.0.1:5002'
                contract = {'version': 'actor-json-v1', 'max_output_tokens': 4096, 'timeout_seconds': 120}
                with self.assertRaises(TimeoutError):
                    MiroFishRuntime(tmp, actor_output_contract=contract,
                        **({'base_url': url, 'evaluation_service_url': url} if explicit else {}))
                self.assertTrue(FakeClient.instances[-1].closed)
                request.assert_called_once()

    def test_explicit_url_and_base_url_cannot_disagree(self):
        with tempfile.TemporaryDirectory() as tmp, fake_http():
            out = Path(tmp) / 'fresh'
            with self.assertRaisesRegex(ValueError, 'differs from native client'):
                MiroFishRuntime(out, evaluation_service_url='http://127.0.0.1:5002')
            self.assertFalse(out.exists())
            self.assertFalse(FakeClient.instances)

    def test_binding_cannot_move_or_downgrade_existing_state(self):
        for action in ('changed_url', 'disabled', 'missing_binding'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp, fake_http():
                out = Path(tmp); url = 'http://127.0.0.1:5002'
                first = MiroFishRuntime(out, base_url=url, evaluation_service_url=url); first.client.close()
                save(out / 'mirofish_state.json', {'fixture': 'existing native state'})
                if action == 'changed_url': url = 'http://127.0.0.1:5003'
                if action == 'missing_binding': (out / SERVICE_BINDING_FILE).unlink()
                with self.assertRaises(ValueError):
                    MiroFishRuntime(out, **({} if action == 'disabled' else {'base_url': url, 'evaluation_service_url': url}))
                self.assertTrue(FakeClient.instances[-1].closed)
                self.assertFalse(FakeClient.instances[-1].calls)

    def test_same_binding_can_reopen_client_without_restarting_native(self):
        with tempfile.TemporaryDirectory() as tmp, fake_http():
            url = 'http://127.0.0.1:5002'; out = Path(tmp)
            first = MiroFishRuntime(out, base_url=url, evaluation_service_url=url); first.client.close()
            save(out / 'mirofish_state.json', {'fixture': 'existing native state'})
            before = (out / SERVICE_BINDING_FILE).read_bytes()
            second = MiroFishRuntime(out, base_url=url, evaluation_service_url=url)
            self.assertEqual(second.state, {'fixture': 'existing native state'})
            self.assertEqual((out / SERVICE_BINDING_FILE).read_bytes(), before)
            self.assertFalse(second.client.calls)
            second.client.close()


class ServiceEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        url = 'http://127.0.0.1:5002';config = ExperimentConfig(mirofish_service_url=url)
        save(root / 'actors' / SERVICE_BINDING_FILE, service_binding(url))
        manifest = {'config': config.public(), 'scenario': scenario(config), 'mirofish_service_url': url,
                    'source_sha256': runner.source_hashes()}
        report = {'config': config.public(), 'scenario': scenario(config), 'provenance': {
            'mirofish_service_url': url, 'mirofish_service_binding_sha256': sha((root / 'actors' / SERVICE_BINDING_FILE).read_bytes())}}
        return manifest, report

    def test_exact_native_and_report_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); manifest, report = self.fixture(root)
            self.assertEqual(mirofish_service_check(root, manifest, report)['service_url'], 'http://127.0.0.1:5002')

    def test_metadata_native_and_source_tampering_rejected(self):
        for location in ('config', 'scenario', 'manifest', 'report_config', 'report_scenario', 'provenance', 'native', 'hash', 'source'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); m, r = self.fixture(root)
                places = {'config': m['config'], 'scenario': m['scenario'], 'manifest': m,
                          'report_config': r['config'], 'report_scenario': r['scenario'], 'provenance': r['provenance']}
                if location in places: places[location]['mirofish_service_url'] = 'http://127.0.0.1:5003'
                elif location == 'native': save(root / 'actors' / SERVICE_BINDING_FILE, service_binding('http://127.0.0.1:5003'))
                elif location == 'hash': r['provenance']['mirofish_service_binding_sha256'] = '0' * 64
                else: m['source_sha256']['lifespan/mirofish.py'] = '0' * 64
                with self.assertRaises(ValueError): mirofish_service_check(root, m, r)

    def test_stripped_options_and_provenance_leave_detectable_client_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); m, r = self.fixture(root)
            for data in (m, m['config'], m['scenario'], r['config'], r['scenario'], r['provenance']): data.pop('mirofish_service_url')
            r['provenance'].pop('mirofish_service_binding_sha256')
            with self.assertRaisesRegex(ValueError, 'marker_downgrade'): mirofish_service_check(root, m, r)

    def test_legacy_absence_stays_valid_and_missing_explicit_binding_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(mirofish_service_check(root, {'config': {}, 'scenario': {}}, {'config': {}, 'scenario': {}, 'provenance': {}}))
            m, r = self.fixture(root); (root / 'actors' / SERVICE_BINDING_FILE).unlink()
            with self.assertRaisesRegex(ValueError, 'native_client_binding'): mirofish_service_check(root, m, r)

    def test_paired_reports_reject_different_service_contracts(self):
        from lifespan.evaluation.metrics import paired_report
        from lifespan.tests.test_evaluation_metrics import report as fixture_report
        for location in ('config', 'scenario', 'provenance'):
            with self.subTest(location=location):
                a, b = fixture_report(algorithm='no_learning'), fixture_report(algorithm='skillopt')
                a[location]['mirofish_service_url'] = 'http://127.0.0.1:5002'
                b[location]['mirofish_service_url'] = 'http://127.0.0.1:5003'
                result = paired_report([a, b])
                self.assertEqual(result['eligible_pairs'], [])
                self.assertEqual(len(result['rejected_pairs']), 1)

    def test_real_runner_native_actor_metadata_uses_actual_client(self):
        from lifespan.tests.test_evaluation_runner import CREDS, _offline_execute
        for url in (None, 'http://127.0.0.1:5002'):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as tmp, fake_http():
                out = Path(tmp);save(out / 'persona_cohort.json', {'personas': []})
                def institution(actors, eco, actor, view, key):
                    common = {'notes': '', 'reason': 'Offline routing fixture.', 'evidence_ids': []}
                    if actor == 'agency': return {**common, 'policy': 'keep', 'duration': 2}
                    if actor in eco.firms:
                        own = view['own_state']
                        return {**common, **{k: own[k] for k in ('objective','price','target_market','priority_workflow')}, 'procedure': 'keep'}
                    return {**common, 'action': 'wait'}
                def employee(actors, eco, task, worker, notes, case, key):
                    return {'delegate': True, 'request': 'Use the published fixture inputs.', 'working_notes': ''}, {'fixture': True}
                cfg = ExperimentConfig(days=8, mirofish_service_url=url)
                with patch.object(MiroFishRuntime, 'bootstrap'), patch.object(runner.NativeActors, 'institutional', institution), \
                     patch.object(runner.NativeActors, 'employee', employee), patch.object(runner, 'dependency_provenance', return_value={}), \
                     redirect_stdout(io.StringIO()):
                    report = runner.run_experiment(out, cfg, executor=_offline_execute, creds=CREDS, stop_after_sessions=1)
                self.assertEqual(report['status'], 'paused_invocation_limit')
                self.assertEqual(report['provenance']['actor_driver'], 'lifespan.evaluation.runner.NativeActors')
                manifest = json.loads((out / 'manifest.json').read_text())
                if url is None:
                    self.assertNotIn('mirofish_service_url', manifest)
                    self.assertNotIn('mirofish_service_url', report['provenance'])
                    self.assertNotIn('mirofish_service_binding_sha256', report['provenance'])
                else:
                    self.assertEqual(manifest['mirofish_service_url'], url)
                    self.assertEqual(report['provenance']['mirofish_service_url'], url)
                self.assertEqual(mirofish_service_check(out, manifest, report) is not None, url is not None)


if __name__ == '__main__':
    unittest.main()
