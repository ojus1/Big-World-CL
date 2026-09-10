"""Preflight launch/repair/isolation contracts with no native or model startup."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import preflight_actor_contract as p
PROVIDER = p.wire.provider_contract('model', 'https://fixture.invalid/v1')


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
                 patch.object(p, 'credentials', return_value={'model': 'model', 'base_url': PROVIDER['base_url'], 'api_key': 'private-fixture-value'}), \
                 patch.object(p, 'provider', return_value=PROVIDER), \
                 patch.object(p, 'sources', return_value={'script': 'hash'}), \
                 patch.object(p, 'committed_sources', return_value='a' * 40), \
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
            manifest = {'claims_excluded': [], 'accounting_scope': 'interviews', 'provider_contract': PROVIDER}
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
            with patch.object(p, 'ROOT', checkout), patch.object(p, 'verify', return_value={'claims_excluded': [], 'accounting_scope': 'interviews', 'provider_contract': PROVIDER}), \
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


# These are artificial complete raw records, with fake provider HTTP and
# explicitly stubbed installation/commit provenance. Never native evidence.
import asyncio
from copy import deepcopy
import sqlite3
import httpx
import pytest
from tests import test_actor_output_contract as fixtures


@pytest.fixture(autouse=True)
def block_real_http_transports(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Offline fixture attempted real HTTP')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', blocked)


@pytest.fixture
def completed_raw(tmp_path, monkeypatch):
    from lifespan.evaluation.runner import source_hashes
    root = tmp_path / 'checkout'; out = root / 'preflight'; out.mkdir(parents=True)
    native = root / 'MiroFish/backend/uploads/simulations/sim_fixture'; native.mkdir(parents=True)
    p.save(native / 'simulation_config.json', {'agent_configs': [
        {'agent_id': i, 'entity_type': p.TYPES[role]} for i, role in enumerate(p.ROLES)]})
    p.save(native / 'reddit_profiles.json', [{'username': row['id']} for row in p.participants()])
    with sqlite3.connect(native / 'reddit_simulation.db') as database:
        database.execute('CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT, created_at TEXT)')
    def respond(request):
        value = json.loads(request.content)
        role = value['text']['format']['name'][len('actor_'):-len('_v1')]
        return httpx.Response(200, json=fixtures.profile_response(json.dumps(p.expected(role))))
    instance = fixtures.profile_model(respond, monkeypatch)
    monkeypatch.setattr(fixtures, 'CONFIG', p.CONTRACT)
    runtime = p.MiroFishRuntime(out / 'actors')
    runtime.actor_output_contract = p.CONTRACT
    runtime.actor_roles = {row['id']: role for row, role in zip(p.participants(), p.ROLES)}
    runtime.employee_ids = {row['id']: i for i, row in enumerate(p.participants())}
    runtime.evaluation_max_interviews = 8
    runtime.state = {'simulation': {'simulation_id': native.name}}
    p.save(runtime.state_path, runtime.state)
    for i, role in enumerate(p.ROLES):
        key = 'wire-' + role
        record = asyncio.run(fixtures.native_fixture(native, instance, agent_id=i, role=role,
            request_key=p.wire.text_hash(key)))
        monkeypatch.setattr(runtime, 'call', lambda *a, _record=record, **kw: _record['native_result'])
        runtime.interview('preflight-' + role, 'fixture', key)
    provider = p.wire.configured_provider_contract()
    sources = source_hashes()
    monkeypatch.setattr(p, 'ROOT', root)
    monkeypatch.setattr(p, 'sources', lambda: deepcopy(sources))
    monkeypatch.setattr(p, 'dependencies', lambda: {'fixture_only': True})
    monkeypatch.setattr(p, 'installation', lambda **kw: {'fixture_only': True})
    monkeypatch.setattr(p, 'committed_sources', lambda values, revision=None: 'a' * 40)
    monkeypatch.setattr(p.wire, 'require_transport_support', lambda _: None)
    p.save(out / 'persona_cohort.json', {'revision': 'fixture', 'personas': []})
    manifest = {'schema_version': 1, 'kind': 'native_actor_wire_capability_preflight',
        'config': p.config(provider), 'provider_contract': provider, 'limits': p.LIMITS,
        'roles': list(p.ROLES), 'participants': p.participants(), 'server_url': p.URL,
        'source_sha256': sources, 'dependencies': p.dependencies(), 'installation': p.installation(),
        'repository_commit': 'a' * 40, 'source_commit_verified': True,
        'target_model': provider['model'], 'model_base_url': provider['base_url'],
        'actor_output_contract_provenance': p.provenance(p.CONTRACT, expected_provider=provider),
        'cohort_sha256': p.sha(out / 'persona_cohort.json'),
        'fixture_sha256': p.wire.digest({role: p.expected(role) for role in p.ROLES})}
    p.save(out / 'manifest.json', manifest)
    measured = p.audit_interviews(out, manifest, p.participants(), completed=True)
    roles = [{'role': role, 'exact_fixture_match': True} for role in p.ROLES]
    p.save(out / 'ROLE_RESULTS.json', roles)
    p.save(out / 'WIRE_RESULT.json', {'status': 'completed', 'roles': roles, 'actor_interviews': measured})
    manifest_hash = p.sha(out / 'manifest.json')
    p.save(out / 'EXECUTION.json', {'manifest_sha256': manifest_hash, 'started_monotonic': 1.,
        'deadline_monotonic': 901., 'supervisor_pid': 100})
    p.save(out / 'SERVER.json', {'pid': 101, 'start_ticks': '123', 'url': p.URL})
    p.save(out / 'WORKER.json', {'pid': 102, 'start_ticks': '124'})
    p.save(out / 'NATIVE_PROCESS.json', {'status': 'observed_live', 'pid': 103,
        'start_ticks': '125', 'cwd': str(native), 'simulation_id': native.name})
    summary = {'status': 'completed', 'manifest_sha256': manifest_hash, 'provider_contract': provider,
        'worker_exit_code': 0, 'roles': roles, 'actor_interviews': measured,
        'execution_started_monotonic': 1., 'cleanup_started_monotonic': 9., 'finished_monotonic': 11.,
        'execution_elapsed_seconds': 8., 'cleanup_elapsed_seconds': 2., 'elapsed_seconds': 10.,
        'worker_cleanup': {'status': 'exited', 'exit_code': 0}, 'server_cleanup': {'status': 'exited', 'exit_code': -15},
        'actor_cleanup': {'status': 'closed', 'simulation_id': native.name}, 'native_process_cleanup': {'status': 'exited'}}
    p.save(out / 'SUMMARY.json', summary)
    def rebind():
        inventory = p.evidence_inventory(out); p.save(out / 'EVIDENCE.json', inventory)
        value = p.read(out / 'SUMMARY.json')
        value.update(evidence_inventory_sha256=p.sha(out / 'EVIDENCE.json'),
                     evidence_files={key: len(rows) for key, rows in inventory['files'].items()})
        p.save(out / 'SUMMARY.json', value)
    rebind()
    runtime.client.close()
    return out, native, manifest_hash, rebind


def test_raw_preflight_audit_joins_four_role_claims_receipts_and_database_without_environment(completed_raw, monkeypatch):
    out, _, manifest_hash, _ = completed_raw
    for name in ('BIGWORLD_PROVIDER_PROFILE', 'LLM_MODEL_NAME', 'LLM_BASE_URL'): monkeypatch.delenv(name)
    monkeypatch.setattr(p, 'credentials', lambda: pytest.fail('Offline audit must not load credentials'))
    before = dict(os.environ)
    result = p.audit(out, manifest_sha256=manifest_hash, strict=True)
    assert result['ok'] and result['verified'] and result['status'] == 'completed'
    assert result['roles'] == list(p.ROLES)
    assert result['actor_interviews']['logical_requests'] == 4
    assert result['actor_interviews']['measured_tokens'] == 240
    assert dict(os.environ) == before


@pytest.mark.parametrize('mode,code', [
    ('claim', 'native_receipt_or_claim'), ('db', 'native_trace_mismatch'),
    ('extra', 'unreconciled_native_requests'), ('roles', 'fixed_role_results'),
    ('cost', 'summary_usage'), ('cleanup', 'cleanup_unconfirmed'),
    ('deadline', 'deadline_or_timing'), ('process', 'process_identity_evidence'),
    ('inventory', 'raw_inventory_changed'), ('execution', 'execution_binding')])
def test_raw_preflight_audit_rejects_rebound_tampered_evidence(completed_raw, mode, code):
    out, native, manifest_hash, rebind = completed_raw
    if mode == 'claim':
        path = next((native / 'actor_contract_claims').glob('*.json'))
        value = p.read(path); value['request_id'] = '0' * 64; p.save(path, value)
    elif mode == 'db':
        with sqlite3.connect(native / 'reddit_simulation.db') as database:
            info = json.loads(database.execute('SELECT info FROM trace WHERE rowid=1').fetchone()[0])
            info['response'] = 'changed'; database.execute('UPDATE trace SET info=? WHERE rowid=1', (json.dumps(info),))
    elif mode == 'extra': p.save(native / 'actor_contract_receipts/extra.json', {})
    elif mode == 'process': (out / 'NATIVE_PROCESS.json').unlink()
    elif mode == 'inventory': (out / 'ROLE_RESULTS.json').write_text('[]')
    elif mode == 'execution':
        value = p.read(out / 'EXECUTION.json'); value['deadline_monotonic'] += 1; p.save(out / 'EXECUTION.json', value)
    else:
        value = p.read(out / 'SUMMARY.json')
        if mode == 'roles': value['roles'].pop()
        if mode == 'cost': value['actor_interviews']['measured_tokens'] += 1
        if mode == 'cleanup': value['native_process_cleanup']['status'] = 'cleanup_unconfirmed'
        if mode == 'deadline': value['execution_elapsed_seconds'] = 901
        p.save(out / 'SUMMARY.json', value)
    if mode != 'inventory': rebind()
    result = p.audit(out, manifest_sha256=manifest_hash, strict=True)
    assert result['ok'] is False and result['status'] == 'invalid'
    if mode == 'process': assert result['errors'] == ['FileNotFoundError']
    else: assert any(code in item for item in result['errors'])


def test_full_tracked_overlay_installation_is_required(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'; backend = root / 'MiroFish/backend'
    (backend / 'app').mkdir(parents=True); (backend / 'app/config.py').write_text('# fixture')
    names = ['local-overrides/backend/app/utils/' + name for name in (
        'actor_output_contract.py', 'actor_contract_transport.json', 'camel_responses.py', 'local_graph.py')]
    monkeypatch.setattr(p, 'ROOT', root)
    monkeypatch.setattr(p.subprocess, 'check_output', lambda *a, **kw: '\n'.join(names))
    for name in names:
        source = root / name; source.parent.mkdir(parents=True, exist_ok=True); source.write_text(name)
        installed = backend / Path(name).relative_to('local-overrides/backend')
        installed.parent.mkdir(parents=True, exist_ok=True); installed.write_bytes(source.read_bytes())
    assert len(p.installation(current=False)['overlay_sha256']) == 4
    (backend / 'app/utils/actor_contract_transport.json').unlink()
    with pytest.raises(ValueError, match='overlay_missing'): p.installation(current=False)


def test_source_commit_binding_rejects_worktree_only_bytes(monkeypatch):
    monkeypatch.setattr(p.subprocess, 'check_output', lambda *a, **kw: b'committed')
    with pytest.raises(ValueError, match='source_not_committed'):
        p.committed_sources({'scripts/example.py': '0' * 64}, 'a' * 40)


def test_current_preflight_verify_requires_same_runtime_provider(completed_raw, monkeypatch):
    out, _, manifest_hash, _ = completed_raw
    monkeypatch.setattr(p, 'credentials', lambda: {'model': 'other', 'base_url': fixtures.PROFILE_BASE,
        'provider_profile': 'responses-no-thinking-v1', 'api_key': 'offline-fixture-key'})
    with pytest.raises(ValueError, match='explicit_provider_contract_required'):
        p.verify(out, manifest_hash)


def test_failed_preflight_retains_known_prefix_and_unknown_reservation(completed_raw):
    out, _, manifest_hash, rebind = completed_raw
    ledger = p.read(out / 'actors/evaluation_interview_ledger.json')
    ledger['requests'].append({'key': 'wire-employee-repair', 'actor': 'preflight-employee',
        'output_contract': {**p.CONTRACT, 'role': 'employee'}, 'status': 'dispatched',
        'accounting_complete': False, 'reserved_output_tokens': 4096})
    p.save(out / 'actors/evaluation_interview_ledger.json', ledger)
    summary = p.read(out / 'SUMMARY.json'); summary['status'] = 'failed'; p.save(out / 'SUMMARY.json', summary)
    rebind()
    result = p.audit(out, manifest_sha256=manifest_hash, strict=True)
    assert result['ok'] is False and result['status'] == 'invalid'
    assert result['actor_interviews']['measured_physical_requests'] == 4
    assert result['actor_interviews']['measured_tokens'] == 240
    assert result['actor_interviews']['unknown_requests'] == 1
    assert result['actor_interviews']['reserved_output_tokens'] == 4096


def test_inventory_raw_bytes_are_rechecked_after_audit(completed_raw, monkeypatch):
    out, _, manifest_hash, _ = completed_raw
    original = p.evidence_inventory
    seen = []
    def changed(directory):
        seen.append(1)
        if len(seen) == 2:
            path = out / 'EVIDENCE.json'; path.write_bytes(path.read_bytes() + b'\n')
        return original(directory)
    monkeypatch.setattr(p, 'evidence_inventory', changed)
    result = p.audit(out, manifest_sha256=manifest_hash, strict=True)
    assert result['ok'] is False
    assert result['errors'] == ['preflight_evidence_changed_during_audit']


@pytest.mark.parametrize('mode', ['manifest_limit', 'manifest_schema', 'native_receipt', 'summary_cost'])
def test_coherent_hash_boolean_counts_cannot_pass_as_integers(completed_raw, mode):
    out, native, manifest_hash, rebind = completed_raw
    if mode.startswith('manifest'):
        manifest = p.read(out / 'manifest.json')
        if mode == 'manifest_limit': manifest['limits']['max_repairs_per_actor'] = True
        else: manifest['schema_version'] = True
        p.save(out / 'manifest.json', manifest); manifest_hash = p.sha(out / 'manifest.json')
        for name in ('SUMMARY.json', 'EXECUTION.json'):
            value = p.read(out / name); value['manifest_sha256'] = manifest_hash; p.save(out / name, value)
    elif mode == 'native_receipt':
        path = next((native / 'actor_contract_receipts').glob('*.json'))
        value = p.read(path); value['physical_requests_dispatched'] = True; p.save(path, value)
    else:
        value = p.read(out / 'SUMMARY.json'); value['actor_interviews']['unknown_requests'] = False
        p.save(out / 'SUMMARY.json', value)
    rebind()
    result = p.audit(out, manifest_sha256=manifest_hash, strict=True)
    assert result['ok'] is False and result['status'] == 'invalid'
