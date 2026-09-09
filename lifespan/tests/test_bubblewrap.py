"""Real OS boundary tests, no model/API calls and no Docker requirement."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from lifespan.bubblewrap import BubblewrapSandbox
from lifespan.computers import Computer


@unittest.skipUnless(shutil.which('bwrap'),'bubblewrap is not installed')
class BubblewrapTests(unittest.TestCase):
    def test_namespaces_files_secrets_and_network_are_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Computer(root,'a'),Computer(root,'b')
            (a.workspace/'private.txt').write_text('employee-a')
            (b.workspace/'private.txt').write_text('employee-b')
            secret=Path(root)/'simulator-private.txt';secret.write_text('hidden-evaluator')
            with unittest.mock.patch.dict(os.environ,{'LIFESPAN_TEST_SECRET':'do-not-forward'}):
                aa,bb=BubblewrapSandbox(a.root),BubblewrapSandbox(b.root)
            try:
                self.assertEqual(aa.execute('cat /workspace/private.txt')['output'],'employee-a')
                self.assertEqual(bb.execute('cat /workspace/private.txt')['output'],'employee-b')
                self.assertNotEqual(aa.inspect()['namespaces']['pid'],bb.inspect()['namespaces']['pid'])
                self.assertNotEqual(aa.inspect()['namespaces']['net'],bb.inspect()['namespaces']['net'])
                result=aa.execute('test ! -e '+str(secret)+' && test -z "$LIFESPAN_TEST_SECRET" && test ! -S /var/run/docker.sock')
                self.assertEqual(result['returncode'],0)
                # Loopback exists but no externally routed interface is present.
                result=aa.execute("python3 -c \"import socket; print(socket.if_nameindex())\"")
                self.assertIn('lo',result['output'])
                self.assertNotIn('eth',result['output'])
            finally:aa.close();bb.close()

    def test_background_process_cwd_and_files_survive_commands(self):
        with tempfile.TemporaryDirectory() as root:
            c=Computer(root,'a');sandbox=BubblewrapSandbox(c.root)
            try:
                sandbox.execute('sleep 60 >/tmp/background.log 2>&1 & echo $! > /workspace/pid')
                self.assertEqual(sandbox.execute('kill -0 $(cat /workspace/pid)')['returncode'],0)
                sandbox.execute('echo remembered > /home/employee/process.txt')
                sandbox.execute('echo temporary > /tmp/restart_marker')
                ns=sandbox.inspect()['namespaces']
                self.assertEqual(sandbox.inspect()['namespaces'],ns)
            finally:sandbox.close()
            fresh=BubblewrapSandbox(c.root)
            try:
                self.assertEqual(fresh.execute('cat /home/employee/process.txt')['output'].strip(),'remembered')
                # Kernel namespace inode numbers can be recycled after exit.
                self.assertEqual(fresh.execute('test ! -e /tmp/restart_marker')['returncode'],0)
            finally:fresh.close()

    def test_host_path_symlink_cannot_escape_guest_filesystem(self):
        with tempfile.TemporaryDirectory() as root:
            c=Computer(root,'a');outside=Path(root)/'outside';outside.write_text('unchanged')
            (c.workspace/'link').symlink_to(outside)
            sandbox=BubblewrapSandbox(c.root)
            try:
                self.assertNotEqual(sandbox.execute('cat /workspace/link')['returncode'],0)
                self.assertNotEqual(sandbox.execute('echo changed > /workspace/link')['returncode'],0)
                self.assertEqual(outside.read_text(),'unchanged')
            finally:sandbox.close()

import unittest.mock
if __name__=='__main__':unittest.main()
