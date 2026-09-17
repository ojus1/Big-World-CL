"""Runs INSIDE one employee's persistent bubblewrap namespace."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading


def process_identity(pid):
    # comm may contain spaces or parentheses; the fields after its last ')' are
    # state, parent, group, session, ... and start ticks at offset 19.
    fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
    return {'parent':int(fields[1]),'session':int(fields[3]),'start':int(fields[19])}


def kill_command(process):
    """Kill this command's session and visible descendants, using pinned PIDs.

    GNU timeout creates a separate process group in the same session. Killing
    only the outer shell's group leaves it holding the output pipe open.
    Unrelated commands in this persistent sandbox have distinct sessions.
    """
    identities={}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try: identities[int(path.name)]=process_identity(int(path.name))
            except (FileNotFoundError,ProcessLookupError): pass
    owned={process.pid}|{pid for pid,item in identities.items() if item['session']==process.pid}
    while True:
        expanded=owned|{pid for pid,item in identities.items() if item['parent'] in owned}
        if expanded==owned: break
        owned=expanded
    handles=[]
    try:
        for pid in sorted(owned):
            if pid not in identities: continue
            try:
                fd=os.pidfd_open(pid)
                try:
                    if process_identity(pid)['start']!=identities[pid]['start']:
                        os.close(fd);continue
                except BaseException:
                    os.close(fd);raise
                handles.append(fd)
            except (FileNotFoundError,ProcessLookupError): pass
        for fd in handles:
            try: signal.pidfd_send_signal(fd,signal.SIGKILL)
            except ProcessLookupError: pass
    finally:
        for fd in handles: os.close(fd)


def execute(request):
    # Set limits in an external executable, after exec. Python preexec_fn in
    # this threaded server can deadlock before Popen returns, outside its timer.
    args=['/usr/bin/prlimit','--as=805306368:805306368',
          '--fsize=67108864:67108864','--core=0:0','--',
          '/bin/bash','-lc' if request.get('login') else '-c',request['command']]
    with subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='backslashreplace',start_new_session=True) as process:
        # Shell previews (e.g. cut/head) can split a UTF-8 sequence, and commands
        # may emit binary bytes. Escape undecodable bytes in terminal display;
        # do not turn ordinary stdout into a fatal RPC error. Workspace files
        # retain their exact bytes for later tools and complete grading evidence.
        try:
            output,_=process.communicate(request.get('stdin'),timeout=min(request.get('timeout',30),120))
            return {'output':output,'returncode':process.returncode}
        except subprocess.TimeoutExpired:
            kill_command(process)
            try:
                output,_=process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                # A detached orphan can escape both the session and current
                # ancestry. Do not wait indefinitely or claim cleanup. Exiting
                # the namespace supervisor stops the entire task sandbox.
                failure={'error_type':'CommandCleanupIncomplete','command_pid':process.pid,
                         'scope':'Task sandbox terminated; command pipe did not close after owned process cleanup.'}
                try:
                    fd=os.open('/run/control/TERMINAL_FAILURE.json',
                               os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w') as stream: stream.write(json.dumps(failure)+'\n')
                finally:
                    os._exit(70)
            return {'output':output+'\nCommand timed out','returncode':124}


def serve(connection):
    with connection:
        stream=connection.makefile('rwb')
        request=json.loads(stream.readline())
        if request.get('kind')=='inspect':
            result={'pid':os.getpid(),'namespaces':{n:os.readlink('/proc/self/ns/'+n) for n in ('mnt','pid','net','user')},
                'processes':[{'pid':int(p.name),'comm':(p/'comm').read_text().strip()} for p in Path('/proc').iterdir()
                             if p.name.isdigit() and (p/'comm').exists()],
                'network_interfaces':os.listdir('/sys/class/net') if Path('/sys/class/net').exists() else [],
                'workspace_identity':Path('/workspace/.employee_identity').read_text().strip()}
        else:
            result=execute(request)
        stream.write((json.dumps(result)+'\n').encode());stream.flush()


def main():
    if not (Path('/usr/bin/prlimit').is_file() and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal')):
        raise RuntimeError('Sandbox requires prlimit and Linux pidfd signaling')
    path='/run/control/command.sock'
    if Path(path).exists():Path(path).unlink()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        # Admit a full 64-client tool burst plus control/inspection connections.
        # A full Unix-domain queue can fail connect with EAGAIN before dispatch.
        server.bind(path);os.chmod(path,0o600);server.listen(128)
        print('BWRAP_READY',flush=True)
        while True:
            conn,_=server.accept()
            threading.Thread(target=serve,args=(conn,),daemon=True).start()

if __name__=='__main__':main()
