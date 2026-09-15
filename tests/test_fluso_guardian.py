"""Controller-death cleanup must be independent and confined to one attempt."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from worldlab import fluso_guardian as guardian


def plan_for(pid=123):
    owner = '0123456789abcdef0123'
    return {'solver': f'worldlab-{owner}-solver', 'relay': f'worldlab-{owner}-relay',
        'identity': {'image': 'pinned-image'}, 'guardian': {'owner': owner, 'parent_pid': pid,
            'parent_start_ticks': 456, 'unit': f'worldlab-fluso-{owner}-guardian.service',
            'deadline_monotonic': time.monotonic() + 60, 'settle_seconds': 5, 'cleanup_seconds': 60}}


class GuardianTests(unittest.TestCase):
    def test_refuses_wrong_image_owner_or_container_name(self):
        plan = plan_for()
        original = {'Id': 'immutable-id', 'Name': '/' + plan['solver'], 'Image': 'pinned-image',
            'Config': {'Labels': {guardian.LABEL: plan['guardian']['owner']}}, 'State': {'Running': True}}
        for field in ('owner', 'image', 'name'):
            info = copy.deepcopy(original)
            if field == 'owner': info['Config']['Labels'][guardian.LABEL] = 'someone-else'
            if field == 'image': info['Image'] = 'other-image'
            if field == 'name': info['Name'] = '/unrelated-container'
            calls = []
            def run(argv):
                calls.append(argv)
                return {'returncode': 0, 'stdout': 'immutable-id\n' if argv[1] == 'container' else json.dumps([info])}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'outside this attempt'):
                guardian.owned_container(plan, plan['solver'], run)
            self.assertTrue(all(c[1] in ('container', 'inspect') for c in calls))

    def test_listing_failure_is_not_proof_of_absence(self):
        plan = plan_for()
        with self.assertRaisesRegex(RuntimeError, 'listing failed'):
            guardian.owned_container(plan, plan['solver'], lambda argv: {'returncode': 1})

    def test_late_container_is_removed_by_immutable_id(self):
        plan = plan_for()
        now, count, mutations = [0], [0], []
        def clock(): now[0] += .2; return now[0]
        def inspect(plan, name, run):
            count[0] += 1
            if count[0] == 5:
                return {'Id': 'late-immutable-id', 'State': {'Running': True}}
            return None
        def run(argv): mutations.append(argv); return {'argv': argv, 'returncode': 0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); guardian.save(root / 'PLAN.json', plan)
            with patch.object(guardian.time, 'monotonic', clock), patch.object(guardian.time, 'sleep'), \
                 patch.object(guardian, 'owned_container', inspect):
                self.assertTrue(guardian.cleanup(root, plan, 'controller_exited', run))
            self.assertEqual(mutations, [['docker', 'stop', '--time', '2', 'late-immutable-id'],
                                         ['docker', 'rm', '-f', 'late-immutable-id']])
            self.assertFalse(guardian.read(root / 'GUARDIAN_INTERVENTION.json')['grading_allowed'])

    def test_failed_removal_stays_unverified(self):
        plan = plan_for(); now = [0]
        def clock(): now[0] += 10; return now[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); guardian.save(root / 'PLAN.json', plan)
            with patch.object(guardian.time, 'monotonic', clock), patch.object(guardian.time, 'sleep'), \
                 patch.object(guardian, 'owned_container', side_effect=RuntimeError('Docker unavailable')):
                self.assertFalse(guardian.cleanup(root, plan, 'controller_exited'))

    @unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux pidfd required')
    def test_pidfd_survives_parent_sigkill_in_separate_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            self.addCleanup(lambda: parent.poll() is None and parent.kill())
            plan = plan_for(parent.pid); plan['guardian']['parent_start_ticks'] = guardian.start_ticks(parent.pid)
            guardian.save(root / 'PLAN.json', plan)
            # A read-only empty Docker listing is sufficient to test real pidfd death detection.
            docker = root / 'docker'
            docker.write_text('#!/bin/sh\nif [ "$1" = container ]; then exit 0; fi\nexit 9\n')
            docker.chmod(0o700)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH']}
            watcher = subprocess.Popen([sys.executable, '-m', 'worldlab.fluso_guardian', '--root', str(root)],
                                       env=env, start_new_session=True)
            self.addCleanup(lambda: watcher.poll() is None and watcher.kill())
            deadline = time.monotonic() + 10
            while not (root / 'GUARDIAN_READY.json').exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue((root / 'GUARDIAN_READY.json').exists())
            os.kill(parent.pid, signal.SIGKILL); parent.wait(timeout=5)
            self.assertEqual(watcher.wait(timeout=15), 0)
            result = guardian.read(root / 'GUARDIAN_EXIT.json')
            self.assertEqual((result['status'], result['reason']), ('cleaned_after_interruption', 'controller_exited'))
            self.assertFalse(result['accounting_finalized'])


if __name__ == '__main__': unittest.main()
