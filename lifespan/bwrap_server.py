"""Runs INSIDE one employee's persistent bubblewrap namespace."""
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import threading


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
            def limits():
                resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
                resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
                resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            args=['/bin/bash','-lc' if request.get('login') else '-c',request['command']]
            with subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,start_new_session=True,preexec_fn=limits) as p:
                try:
                    output,_=p.communicate(request.get('stdin'),timeout=min(request.get('timeout',30),120))
                    result={'output':output,'returncode':p.returncode}
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL)
                    output,_=p.communicate()
                    result={'output':output+'\nCommand timed out','returncode':124}
        stream.write((json.dumps(result)+'\n').encode());stream.flush()


def main():
    path='/run/control/command.sock'
    if Path(path).exists():Path(path).unlink()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(path);os.chmod(path,0o600);server.listen(16)
        print('BWRAP_READY',flush=True)
        while True:
            conn,_=server.accept()
            threading.Thread(target=serve,args=(conn,),daemon=True).start()

if __name__=='__main__':main()
