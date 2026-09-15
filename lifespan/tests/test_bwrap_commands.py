"""Real Linux command cleanup, resource and concurrent RPC regression checks."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

from lifespan.bubblewrap import BubblewrapSandbox
from lifespan.computers import Computer


@unittest.skipUnless(shutil.which('bwrap') and Path('/usr/bin/prlimit').is_file(),
                     'Linux bubblewrap and prlimit are required')
class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.computer=Computer(self.temp.name,'worker')
        self.sandbox=BubblewrapSandbox(self.computer.root)

    def tearDown(self):
        self.sandbox.close()
        self.temp.cleanup()

    def test_nested_timeout_group_is_killed_with_its_command_session(self):
        began=time.monotonic()
        result=self.sandbox.execute('timeout 3 sleep 9; echo finished',timeout=.2)
        self.assertLess(time.monotonic()-began,1.5)
        self.assertEqual(result['returncode'],124)
        self.assertNotIn('finished',result['output'])
        self.assertNotIn('timeout',self.sandbox.execute('ps -eo comm')['output'])

    def test_timeout_keeps_an_unrelated_existing_background_job(self):
        self.sandbox.execute('sleep 60 >/tmp/background.log 2>&1 & echo $! > /workspace/background.pid')
        result=self.sandbox.execute('timeout 3 sleep 9; echo finished',timeout=.2)
        self.assertEqual(result['returncode'],124)
        self.assertEqual(self.sandbox.execute('kill -0 $(cat /workspace/background.pid)')['returncode'],0)

    def test_visible_descendant_in_new_session_is_also_stopped(self):
        began=time.monotonic()
        result=self.sandbox.execute("setsid sh -c 'echo $$ > /workspace/child.pid; sleep 3' & wait",timeout=.2)
        self.assertLess(time.monotonic()-began,1.5)
        self.assertEqual(result['returncode'],124)
        # A reparented zombie is dead; an extant running/sleeping process is not.
        state=self.sandbox.execute("ps -o stat= -p $(cat /workspace/child.pid)")['output'].strip()
        self.assertTrue(not state or state.startswith('Z'),state)

    def test_escaped_orphan_pipe_cannot_hold_the_task_open(self):
        code=("import os,time; from pathlib import Path; child=os.fork(); "
              "os._exit(0) if child else None; os.setsid(); time.sleep(8); "
              "Path('/workspace/late').write_text('late')")
        command='python3 -c '+shlex.quote(code)+'; sleep 9'
        began=time.monotonic()
        with self.assertRaises((OSError,ValueError)):
            self.sandbox.execute(command,timeout=.2)
        self.assertNotEqual(self.sandbox.process.wait(timeout=3),0)
        self.assertLess(time.monotonic()-began,3)
        failure=json.loads((self.computer.root/'control/TERMINAL_FAILURE.json').read_text())
        self.assertEqual(failure['error_type'],'CommandCleanupIncomplete')
        self.assertFalse((self.computer.workspace/'late').exists())

    def test_limits_are_applied_before_user_code_and_cannot_be_raised(self):
        code="""import json,resource
limits=[resource.getrlimit(k) for k in (resource.RLIMIT_AS,resource.RLIMIT_FSIZE,resource.RLIMIT_CORE)]
try:
    resource.setrlimit(resource.RLIMIT_AS,(805306369,805306369))
    raised=True
except (OSError,ValueError):
    raised=False
print(json.dumps({'limits':limits,'raised':raised}))
"""
        result=self.sandbox.execute('python3 -c '+shlex.quote(code))
        self.assertEqual(result['returncode'],0)
        self.assertEqual(json.loads(result['output']),{'limits':[[805306368,805306368],[67108864,67108864],[0,0]],'raised':False})

    def test_64_concurrent_clients_preserve_stdin_and_all_results(self):
        barrier=threading.Barrier(64)
        def run(index):
            barrier.wait(timeout=10)
            for repeat in range(2):
                content=f'{index}/{repeat}: résumé — Καλημέρα — नमस्ते\n'*16
                result=self.sandbox.execute('sleep .05; cat',timeout=15,stdin=content)
                if result!={'output':content,'returncode':0}:
                    raise AssertionError((index,repeat,result))
            return index
        with ThreadPoolExecutor(max_workers=64) as executor:
            results=list(executor.map(run,range(64)))
        self.assertEqual(results,list(range(64)))


HERMES_ROOT=Path(os.environ.get('WORLDLAB_HERMES_TEST_ROOT','/nonexistent-hermes-test-root'))


@unittest.skipUnless((HERMES_ROOT/'venv/bin/python').is_file() and shutil.which('bwrap'),
                     'Optional pinned native Hermes environment is unavailable')
class NativeEnvironmentTests(unittest.TestCase):
    def test_lost_sandbox_is_recorded_and_no_later_command_is_dispatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); computer=Computer(root,'worker')
            code="""import json,sys
from lifespan.bubblewrap import install_hermes_backend
env=install_hermes_backend(sys.argv[1])
env.sandbox.close()
result=env.execute('echo should-not-run > /workspace/late')
again=env.execute('echo still-not-run > /workspace/later')
print(json.dumps({'result':result,'again':again,'error':env.execution_error}))
"""
            env={k:os.environ[k] for k in ('PATH','LANG') if k in os.environ}
            env.update(HOME=str(root/'home'),HERMES_HOME=str(root/'hermes'),
                       PYTHONPATH=str(Path(__file__).resolve().parents[2])+':'+str(HERMES_ROOT))
            result=subprocess.run([str(HERMES_ROOT/'venv/bin/python'),'-c',code,str(computer.root)],
                                  env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            record=json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(record['result']['returncode'],125)
            self.assertEqual(record['again']['returncode'],125)
            self.assertEqual(record['error'],'RuntimeError')
            self.assertFalse((computer.workspace/'late').exists())
            self.assertFalse((computer.workspace/'later').exists())


if __name__=='__main__': unittest.main()
