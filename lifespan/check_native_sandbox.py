"""Run with Hermes' Python: verifies native Hermes file tools use bubblewrap."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)/'employee';profile=root/'hermes';workspace=root/'workspace'
        profile.mkdir(parents=True);workspace.mkdir()
        (workspace/'.employee_identity').write_text('employee\n')
        (profile/'config.yaml').write_text('terminal:\n  backend: local\n  cwd: /workspace\n')
        os.environ['HERMES_HOME']=str(profile)
        os.environ['TERMINAL_ENV']='local'
        outside=Path(tmp)/'simulator-private.txt';outside.write_text('unreadable sentinel')
        from lifespan.bubblewrap import install_hermes_backend
        from tools.file_tools import write_file_tool,read_file_tool
        from tools.terminal_tool import terminal_tool,is_persistent_env
        env=install_hermes_backend(root)
        try:
            assert is_persistent_env('employee-session')
            wr=json.loads(write_file_tool('/workspace/native-file.txt','Hermes wrote this'))
            assert (workspace/'native-file.txt').read_text()=='Hermes wrote this',wr
            rr=read_file_tool(str(outside))
            assert 'unreadable sentinel' not in rr,rr
            tt=json.loads(terminal_tool('cd /home/employee; echo persistent > native-note.txt'))
            assert tt['exit_code']==0,tt
            tt=json.loads(terminal_tool('pwd; cat native-note.txt'))
            assert '/home/employee' in tt['output'] and 'persistent' in tt['output'],tt
            assert (root/'os_home/native-note.txt').read_text().strip()=='persistent'
            print(json.dumps({'native_file_write':True,'host_private_file_blocked':True,
                              'native_terminal_cwd_persistent':True,'backend':'bubblewrap'}))
        finally:env.cleanup()

if __name__=='__main__':main()
