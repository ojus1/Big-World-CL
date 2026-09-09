"""Lightweight persistent employee namespaces; no Docker dependency.

Only trusted Hermes transport lives on the host. Every terminal/file operation
runs inside the employee's bubblewrap supervisor. Disk identity survives restart;
namespace identity and background processes survive across turns within a run.
"""
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import time


def rpc(path,request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(request.get('timeout',15)+5)
        client.connect(str(path))
        stream=client.makefile('rwb')
        stream.write((json.dumps(request)+'\n').encode());stream.flush()
        return json.loads(stream.readline())


class BubblewrapSandbox:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.control=self.root/'control'
        self.home=self.root/'os_home'
        for p in (self.control,self.home):p.mkdir(parents=True,exist_ok=True)
        self.control.chmod(0o700)
        self.socket=self.control/'command.sock'
        # Short path avoids Linux's 108-byte Unix socket pathname limit. It
        # aliases only this employee's control socket, not a shared filesystem.
        import tempfile
        self.alias=Path(tempfile.mkdtemp(prefix='lifespan-bwrap-'))
        (self.alias/'control').symlink_to(self.control,target_is_directory=True)
        self.rpc_socket=self.alias/'control/command.sock'
        server=Path(__file__).with_name('bwrap_server.py')
        passwd=self.control/'passwd'
        passwd.write_text(f'employee:x:{os.getuid()}:{os.getgid()}::/home/employee:/bin/bash\n')
        group=self.control/'group';group.write_text(f'employee:x:{os.getgid()}:\n')
        self.command=['bwrap','--unshare-all','--new-session','--die-with-parent','--cap-drop','ALL',
            '--clearenv','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
            '--symlink','usr/lib64','/lib64','--symlink','usr/sbin','/sbin','--proc','/proc','--dev','/dev',
            '--tmpfs','/tmp','--dir','/etc','--ro-bind',str(passwd),'/etc/passwd',
            '--ro-bind',str(group),'/etc/group','--bind',str(self.root/'workspace'),'/workspace',
            '--bind',str(self.home),'/home/employee','--bind',str(self.control),'/run/control',
            '--ro-bind',str(server),'/sandbox_server.py',
            '--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/home/employee',
            '--setenv','LANG','C.UTF-8','--chdir','/workspace','/usr/bin/python3','-u','/sandbox_server.py']
        self.log=(self.root/'bubblewrap.log').open('a')
        self.process=subprocess.Popen(self.command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                      stderr=self.log,text=True)
        with selectors.DefaultSelector() as sel:
            sel.register(self.process.stdout,selectors.EVENT_READ)
            if not sel.select(10) or self.process.stdout.readline().strip()!='BWRAP_READY':
                self.close()
                raise RuntimeError('Bubblewrap startup failed; inspect bubblewrap.log')
        self.initial=self.inspect()
        if self.initial['workspace_identity'] != self.root.name:
            self.close();raise RuntimeError('Wrong employee filesystem mounted in bubblewrap')
        host_ns={n:os.readlink('/proc/self/ns/'+n) for n in ('mnt','pid','net','user')}
        if any(self.initial['namespaces'][n]==host_ns[n] for n in host_ns):
            self.close();raise RuntimeError('Bubblewrap namespace isolation probe failed')

    def execute(self,command,timeout=30,stdin=None,login=False):
        if self.process.poll() is not None:
            raise RuntimeError('Employee bubblewrap sandbox exited; refusing host execution')
        return rpc(self.rpc_socket,{'command':command,'timeout':timeout,'stdin':stdin,'login':login})

    def inspect(self):
        return rpc(self.rpc_socket,{'kind':'inspect'})

    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        if getattr(self,'process',None) and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        if getattr(self,'process',None) and self.process.stdout:
            self.process.stdout.close()
        if hasattr(self,'log'):self.log.close()
        if hasattr(self,'alias'):
            (self.alias/'control').unlink(missing_ok=True)
            self.alias.rmdir()


def install_hermes_backend(root):
    """Adapt Hermes' native BaseEnvironment without modifying its source tree.

    Populate both its shared and explicit task cache, and replace this worker's
    factory with a fail-closed factory for this single Bubblewrap environment.
    The native file layer detects BaseEnvironment (not LocalEnvironment) and
    uses shell-backed file operations inside the namespace.
    """
    from tools.environments.base import BaseEnvironment,_ThreadedProcessHandle
    from tools import terminal_tool as terminal
    class Environment(BaseEnvironment):
        def __init__(self):
            super().__init__('/workspace',30)
            self._persistent=True
            self.sandbox=BubblewrapSandbox(root)
            self.init_session()
        def _run_bash(self,cmd_string,*,login=False,timeout=120,stdin_data=None):
            def execute():
                r=self.sandbox.execute(cmd_string,timeout,stdin_data,login)
                return r['output'],r['returncode']
            return _ThreadedProcessHandle(execute)
        def cleanup(self):
            self.sandbox.close()
    env=Environment()
    terminal._active_environments['default']=env
    terminal._create_environment=lambda *a,**kw: env
    return env
