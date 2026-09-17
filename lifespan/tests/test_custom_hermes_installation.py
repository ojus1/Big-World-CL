"""A worker must resolve the same explicit Hermes installation as its parent."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lifespan import computers


class CustomHermesInstallationTests(unittest.TestCase):
    def test_sanitized_worker_can_resolve_custom_installation(self):
        real_popen = subprocess.Popen
        observed = {}
        class StopBeforeNativeLaunch(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            selected = root / 'dedicated-hermes'
            selected.mkdir()
            computer = computers.Computer(root / 'computers', 'employee')
            def capture(command, **kwargs):
                env = kwargs['env']
                # Import in a fresh process, just as the native worker does.
                with real_popen([sys.executable, '-c',
                    'import json; from lifespan.computers import HERMES; '
                    'print(json.dumps(str(HERMES)))'], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
                    stdout, stderr = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, stderr)
                observed['root'] = json.loads(stdout)
                self.assertNotIn('PERSONAL_TOKEN_CANARY', env)
                self.assertEqual(env['HERMES_HOME'], str(computer.profile))
                raise StopBeforeNativeLaunch
            try:
                # Config serialization is incidental to this environment test;
                # keep it independent of native Hermes' optional dependencies.
                with patch.dict(sys.modules, yaml=SimpleNamespace(safe_dump=json.dumps)), \
                     patch.object(computers, 'HERMES', selected), \
                     patch.dict(os.environ, {'PERSONAL_TOKEN_CANARY': 'must-not-inherit'}), \
                     patch.object(computers.subprocess, 'Popen', side_effect=capture), \
                     self.assertRaises(StopBeforeNativeLaunch):
                    computer.start({'model': 'fixture', 'base_url': 'http://127.0.0.1:9/v1',
                                    'api_key': 'fixture'}, timeout=10)
            finally:
                log = getattr(computer, 'log', None)
                if log is not None:
                    log.close()
            self.assertEqual(observed['root'], str(selected))
