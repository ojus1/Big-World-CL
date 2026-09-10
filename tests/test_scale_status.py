"""Offline status fixtures only; no world, provider, process launch, or audit."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import scale_status as q


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp) / 'source'; self.root.mkdir()
        self.campaign = Path(self.tmp) / 'campaign'; self.campaign.mkdir()
        self.sources = {}
        for name in (q.HELPER, q.RUNNER, *(f'scripts/fixture_{i}.py' for i in range(67))):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture source\n'); self.sources[name] = q.sha(path.read_bytes())
        slots = []
        for seed, arm in q.SCHEDULE:
            name = f'seed-{seed}-{arm}'; cfg = {'max_run_seconds': 1000, 'seed': seed, 'algorithm': arm}
            slot = {'seed': seed, 'algorithm': arm, 'run_id': name, 'relative_path': 'runs/' + name,
                    'config': cfg, 'config_sha256': q.sha(q.canonical(cfg))}
            slots.append(slot); self.save(self.campaign / slot['relative_path'] / 'config.json', cfg)
        self.registration = {'schema_version': 3, 'kind': 'scale-v3-six-world-registration', 'slots': slots,
                             'source_sha256': {q.RUNNER: self.sources[q.RUNNER]},
                             'registration_tools_sha256': {k: v for k, v in self.sources.items() if k != q.RUNNER},
                             'model_base_url': 'PRIVATE_PROVIDER', 'target_model': 'PRIVATE_MODEL'}
        self.save(self.campaign / 'campaign.json', self.registration)
        self.campaign_hash = q.sha((self.campaign / 'campaign.json').read_bytes())
        self.processes = {}

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + '\n')
        return q.sha(path.read_bytes())

    def read(self, **kwargs):
        return q.read_status(self.campaign, campaign_sha256=self.campaign_hash, source_root=self.root,
                             boot_id=kwargs.pop('boot_id', 'fixture-boot'), monotonic=kwargs.pop('monotonic', 150),
                             now=kwargs.pop('now', 2000000000), identity_reader=self.processes.get, **kwargs)

    def run_dir(self, index=0):
        return self.campaign / self.registration['slots'][index]['relative_path']

    def launch(self, index=0):
        run = self.run_dir(index); slot = self.registration['slots'][index]
        command = ['/fixture/python', '-u', '-m', 'lifespan.evaluation.runner', '--out', str(run), '--config', str(run / 'config.json')]
        identity = {'pid': 90000 + index, 'start_ticks': 500, 'uid': os.getuid(), 'boot_id': 'fixture-boot',
                    'pgid': 90000 + index, 'sid': 90000 + index}
        intent = {'schema_version': 1, 'kind': 'WORLD', 'helper_sha256': self.sources[q.HELPER],
                  'started_monotonic': 100, 'cwd': str(self.root), 'command': command,
                  'binding': {'run_directory': str(run), 'config_sha256': q.sha((run / 'config.json').read_bytes()),
                              'runner_sha256': self.sources[q.RUNNER]}}
        intent_hash = self.save(run / 'lifecycle/WORLD_INTENT.json', intent)
        start = {**intent, 'intent_sha256': intent_hash, 'root_identity': identity}
        self.save(run / 'lifecycle/WORLD_START.json', start)
        self.processes[identity['pid']] = {**identity, 'state': 'S', 'cwd': str(self.root), 'command': command}
        return start

    def checkpoint(self, index=0):
        self.save(self.run_dir(index) / 'checkpoint.json', {'ecosystem': {'day': 4, 'PRIVATE_TASK': 'PRIVATE_TEXT'},
            'runner': {'phase': 'work', 'sessions': [{'private': 'PRIVATE_CONTENT'}] * 3,
                       'updates': [{'accepted': True, 'score': 99}, {'accepted': False, 'secret': 'PRIVATE'}]}})

    def terminal(self, index=0):
        run = self.run_dir(index); start = run / 'lifecycle/WORLD_START.json'
        cleanup = {'schema_version': 1, 'helper_sha256': self.sources[q.HELPER], 'start_sha256': q.sha(start.read_bytes()),
                   'status': 'confirmed', 'root_exitcode': 0}
        cleanup_hash = self.save(run / 'lifecycle/WORLD_CLEANUP.json', cleanup)
        self.save(self.campaign / 'execution_results.json', {'campaign_sha256': self.campaign_hash,
            'runs': [{'run_id': run.name, 'exit_code': 0, 'cleanup_confirmed': True,
                      'lifecycle': {'start_sha256': q.sha(start.read_bytes()), 'cleanup_sha256': cleanup_hash}}]})
        self.processes.clear()

    def test_prepared_keeps_all_six_unlaunched_and_unknown_counts(self):
        value = self.read()
        self.assertEqual(value['planned_slots'], 6)
        self.assertEqual(value['state_counts'], {'unlaunched': 6})
        self.assertTrue(all(r['returned_sessions'] is None and r['recorded_adoptions'] is None for r in value['slots']))
        self.assertEqual(value['registered_sources']['matched_files'], 69)

    def test_two_owned_worlds_without_first_checkpoint_and_four_unlaunched(self):
        self.launch(0); self.launch(1)
        rows = self.read()['slots']
        self.assertEqual([r['state'] for r in rows], ['running', 'running', 'unlaunched', 'unlaunched', 'unlaunched', 'unlaunched'])
        self.assertEqual(rows[0]['elapsed_seconds'], 50); self.assertEqual(rows[0]['remaining_seconds'], 950)
        self.assertIsNone(rows[0]['returned_sessions']); self.assertIsNone(rows[0]['phase'])

    def test_checkpoint_counts_only_returned_rows_and_allowlisted_phase(self):
        self.launch(); self.checkpoint()
        self.save(self.run_dir() / 'INFLIGHT.json', {'kind': 'learning', 'key': 'PRIVATE_EMPLOYEE', 'day': 5})
        row = self.read()['slots'][0]
        self.assertEqual((row['returned_sessions'], row['recorded_updates'], row['recorded_adoptions']), (3, 2, 1))
        self.assertEqual((row['phase'], row['day'], row['inflight_kind']), ('work', 4, 'learning'))
        self.assertGreater(row['checkpoint_age_seconds'], 0)

    def test_partial_writes_remain_unknown_without_false_failure_or_zero(self):
        self.launch(); self.checkpoint()
        for path in ('checkpoint.json', 'INFLIGHT.json', 'REPORT.json'):
            (self.run_dir() / path).write_text('{"partially-written":')
        row = self.read()['slots'][0]
        self.assertEqual(row['state'], 'running')
        self.assertEqual(row['records']['checkpoint'], 'updating_unknown')
        self.assertIsNone(row['returned_sessions']); self.assertIsNone(row['runner_report_status'])
        (self.run_dir() / 'lifecycle/WORLD_START.json').write_text('{')
        self.assertEqual(self.read()['slots'][0]['state'], 'updating_unknown')

    def test_old_boot_replaced_pid_zombie_and_command_mismatch_never_gain_clock(self):
        start = self.launch(); original = dict(self.processes[start['root_identity']['pid']])
        self.checkpoint()
        self.assertIsNone(self.read(boot_id='new-boot')['slots'][0]['elapsed_seconds'])
        for field, value in (('start_ticks', 501), ('uid', os.getuid() + 1), ('state', 'Z'), ('command', ['different']), ('cwd', '/wrong')):
            with self.subTest(field=field):
                self.processes[original['pid']] = {**original, field: value}
                row = self.read()['slots'][0]
                self.assertEqual(row['state'], 'updating_unknown'); self.assertIsNone(row['remaining_seconds'])
                self.assertEqual(row['returned_sessions'], 3)
        self.processes.clear()
        self.assertEqual(self.read()['slots'][0]['state'], 'updating_unknown')

    def test_start_intent_config_and_source_bindings_are_required(self):
        self.launch()
        for filename in ('lifecycle/WORLD_INTENT.json', 'config.json'):
            path = self.run_dir() / filename; original = path.read_bytes(); path.write_bytes(original + b' ')
            self.assertIsNone(self.read()['slots'][0]['elapsed_seconds']); path.write_bytes(original)
        source = self.root / q.RUNNER; source.write_text('# changed\n')
        self.assertEqual(self.read()['registered_sources']['state'], 'drift')

    def test_terminal_receipt_hashes_and_report_status_are_separate_from_audit(self):
        self.launch(); self.checkpoint(); self.terminal()
        self.save(self.run_dir() / 'REPORT.json', {'status': 'completed', 'scores': 'PRIVATE_SCORE'})
        row = self.read()['slots'][0]
        self.assertEqual(row['state'], 'terminal_recorded'); self.assertEqual(row['runner_report_status'], 'completed')
        self.assertEqual(row['terminal_evidence'], {'exit_code': 0, 'cleanup_reported_confirmed': True})
        self.assertIsNone(row['elapsed_seconds'])
        path = self.run_dir() / 'lifecycle/WORLD_CLEANUP.json'; path.write_bytes(path.read_bytes() + b' ')
        row = self.read()['slots'][0]
        self.assertEqual(row['state'], 'updating_unknown'); self.assertIsNone(row['terminal_evidence'])
        self.assertEqual(row['runner_report_status'], 'completed')

    def test_nonfinite_and_nonboolean_counts_remain_unknown(self):
        self.launch()
        self.save(self.run_dir() / 'checkpoint.json', {'ecosystem': {'day': True}, 'runner': {
            'phase': 'PRIVATE_PROMPT', 'sessions': None, 'updates': [{'accepted': 1}]}})
        row = self.read(now=float('nan'), monotonic=float('nan'))['slots'][0]
        for key in ('day', 'phase', 'returned_sessions', 'recorded_adoptions', 'checkpoint_age_seconds', 'elapsed_seconds'):
            self.assertIsNone(row[key], key)
        (self.run_dir() / 'checkpoint.json').write_text('{"runner":{"elapsed_seconds":NaN}}')
        self.assertEqual(self.read()['slots'][0]['records']['checkpoint'], 'updating_unknown')

    def test_malformed_terminal_receipts_cannot_claim_terminal_even_with_matching_hashes(self):
        self.launch(); self.terminal()
        cleanup_path = self.run_dir() / 'lifecycle/WORLD_CLEANUP.json'
        start_path = self.run_dir() / 'lifecycle/WORLD_START.json'
        result_path = self.campaign / 'execution_results.json'
        originals = {p: p.read_bytes() for p in (cleanup_path, start_path, result_path)}
        for change in ('boolean_exit', 'array_start', 'missing_intent_link'):
            with self.subTest(change=change):
                for p, raw in originals.items(): p.write_bytes(raw)
                clean = json.loads(cleanup_path.read_bytes()); result = json.loads(result_path.read_bytes())
                if change == 'boolean_exit': clean['root_exitcode'] = False
                else:
                    start = [] if change == 'array_start' else json.loads(start_path.read_bytes())
                    if type(start) is dict: start.pop('intent_sha256')
                    self.save(start_path, start)
                clean['start_sha256'] = q.sha(start_path.read_bytes()); self.save(cleanup_path, clean)
                result['runs'][0]['lifecycle'] = {'start_sha256': q.sha(start_path.read_bytes()),
                    'cleanup_sha256': q.sha(cleanup_path.read_bytes())}
                self.save(result_path, result)
                row = self.read()['slots'][0]
                self.assertEqual(row['state'], 'updating_unknown'); self.assertIsNone(row['terminal_evidence'])

    def test_composite_process_observation_rechecks_start_identity_after_command_read(self):
        proc = Path(self.tmp) / 'proc'; directory = proc / '123'; directory.mkdir(parents=True)
        (directory / 'cwd').symlink_to(self.root)
        (directory / 'cmdline').write_bytes(b'/fixture/python\0-u\0')
        boot = proc / 'sys/kernel/random/boot_id'; boot.parent.mkdir(parents=True); boot.write_text('fixture-boot')
        fields = ['S', '1', '123', '123', *(['0'] * 15), '500']
        stat_path = directory / 'stat'; original = '123 (fixture) ' + ' '.join(fields)
        stat_path.write_text(original)
        self.assertEqual(q.process_identity(123, proc_root=proc)['start_ticks'], 500)
        native_read = Path.read_bytes
        def replace_during_command(path):
            if path == directory / 'cmdline':
                fields[19] = '501'; stat_path.write_text('123 (fixture) ' + ' '.join(fields))
            return native_read(path)
        with patch.object(Path, 'read_bytes', replace_during_command):
            self.assertIsNone(q.process_identity(123, proc_root=proc))

    def test_json_exponent_overflow_is_unknown_without_losing_other_five_slots(self):
        self.launch()
        intent_path = self.run_dir() / 'lifecycle/WORLD_INTENT.json'
        start_path = self.run_dir() / 'lifecycle/WORLD_START.json'
        intent = json.loads(intent_path.read_bytes()); intent['started_monotonic'] = float('inf')
        intent_path.write_text(json.dumps(intent).replace('Infinity', '1e999'))
        start = json.loads(start_path.read_bytes()); start['started_monotonic'] = float('inf')
        start['intent_sha256'] = q.sha(intent_path.read_bytes())
        start_path.write_text(json.dumps(start).replace('Infinity', '1e999'))
        self.terminal()
        value = self.read()
        self.assertEqual(len(value['slots']), 6)
        self.assertEqual(value['slots'][0]['state'], 'updating_unknown')
        self.assertEqual(value['slots'][0]['records']['start'], 'updating_unknown')
        self.assertTrue(all(r['state'] == 'unlaunched' for r in value['slots'][1:]))

    def test_symlink_or_size_bound_refuses_record_without_reading_target(self):
        self.launch(); self.checkpoint(); path = self.run_dir() / 'checkpoint.json'
        data = path.read_bytes(); path.unlink()
        target = self.campaign / 'PRIVATE_TARGET'; target.write_bytes(data); path.symlink_to(target)
        self.assertEqual(self.read()['slots'][0]['records']['checkpoint'], 'updating_unknown')
        path.unlink(); path.write_bytes(data)
        self.assertEqual(q.safe_read(path, limit=4)['state'], 'updating_unknown')

    def test_wrong_campaign_hash_subset_and_registration_mutation_refuse(self):
        with self.assertRaises(q.StatusError):
            q.read_status(self.campaign, campaign_sha256='0' * 64, source_root=self.root)
        value = dict(self.registration); value['slots'] = value['slots'][:2]
        self.save(self.campaign / 'campaign.json', value)
        self.campaign_hash = q.sha((self.campaign / 'campaign.json').read_bytes())
        with self.assertRaises(q.StatusError): self.read()

    def test_fixed_path_bounded_snapshot_does_not_walk_worktrees_or_export_content(self):
        self.launch(); self.checkpoint()
        self.save(self.run_dir() / 'REPORT.json', {'status': 'PRIVATE_EXCEPTION', 'message': '/private/key'})
        self.save(self.campaign / 'STATUS.json', {'slots': ['PRIVATE_PROVIDER_ID']})
        with patch.object(Path, 'glob', side_effect=AssertionError('no scan')), \
             patch.object(Path, 'rglob', side_effect=AssertionError('no scan')):
            value = self.read()
        exported = json.dumps(value) + q.table(value)
        for forbidden in ('PRIVATE', self.tmp, 'score', 'model_base_url', '90000', 'fixture-boot'):
            self.assertNotIn(forbidden, exported)
        self.assertIn('6 planned slots', exported)

    def test_cli_unknown_is_not_failure_and_bad_registration_is_safe(self):
        with patch.object(q, 'read_status', return_value=self.read()), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(q.main([str(self.campaign), '--campaign-sha256', self.campaign_hash]), 0)
        self.assertEqual(json.loads(output.getvalue())['planned_slots'], 6)
        with patch.object(q, 'read_status', side_effect=OSError('PRIVATE_EXCEPTION')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(q.main([str(self.campaign), '--campaign-sha256', self.campaign_hash]), 2)
        self.assertNotIn('PRIVATE', output.getvalue())


if __name__ == '__main__':
    unittest.main()
