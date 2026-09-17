#!/usr/bin/env python3
"""Read-only override/patch check followed by a local Flask capability GET.

No server is started and no model or simulation is invoked. App import may
initialize its normal log files. Configuration is never written or exported.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PIN='39d849138ef254f6c737ab4c4705e5545dbe31d4'
PREFIX='local-overrides/backend/'
PATCH='patches/mirofish-local.patch'
VERSION='mirofish-installation-check-v1'


class CheckError(ValueError):pass


def require(value,code):
    if not value:raise CheckError(code)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,timeout=10)


def static_check(project_root,installation):
    """Inspect every tracked regular override; do not import installed Python."""
    root,installed=Path(project_root).resolve(),Path(installation).resolve()
    records=git(root,'ls-files','--stage','-z','--','local-overrides/backend').split(b'\0')
    paths=[]
    for raw in filter(None,records):
        metadata,name=raw.decode('utf-8').split('\t',1)
        mode,_,stage=metadata.split()
        require(mode in ('100644','100755') and stage=='0','override_not_tracked_regular_file')
        require(name.startswith(PREFIX) and re.fullmatch(r'[A-Za-z0-9_./-]+',name)
            and '..' not in Path(name).parts,'unsafe_override_path')
        paths.append(name)
    require(paths and len(paths)==len(set(paths)),'missing_or_duplicate_override_inventory')
    rows=[]
    for name in sorted(paths):
        source=root/name;relative=Path(name).relative_to(PREFIX);target=installed/'backend'/relative
        require(source.is_file() and not any(p.is_symlink() for p in [source,*source.parents] if p!=root.parent),
            'override_source_not_regular')
        expected=git(root,'show','HEAD:'+name)
        require(source.read_bytes()==expected,'override_source_differs_from_checked_in_bytes')
        real=target.is_file() and not any(p.is_symlink() for p in [target,*target.parents] if p!=installed.parent)
        actual=digest(target.read_bytes()) if real else None
        status='matched' if actual==digest(expected) else 'mismatched' if actual else 'missing_or_nonregular'
        rows.append({'path':'backend/'+str(relative),'source_sha256':digest(expected),
            'installed_sha256':actual,'status':status})
    patch=root/PATCH
    require(patch.is_file() and not patch.is_symlink(),'missing_checked_in_patch')
    require(patch.read_bytes()==git(root,'show','HEAD:'+PATCH),'patch_differs_from_checked_in_bytes')
    verifier=root/'lifespan/actor_contract.py'
    require(verifier.is_file() and not verifier.is_symlink()
        and verifier.read_bytes()==git(root,'show','HEAD:lifespan/actor_contract.py'),
        'client_verifier_differs_from_checked_in_bytes')
    revision=git(installed,'rev-parse','HEAD').decode().strip()
    require(revision==PIN,'mirofish_revision_mismatch')
    try:git(installed,'apply','--reverse','--check',str(patch))
    except subprocess.CalledProcessError:raise CheckError('tracked_patch_not_applied') from None
    return {'ok':all(row['status']=='matched' for row in rows),'tracked_override_files':rows,
        'mirofish_revision':revision,'tracked_patch_sha256':digest(patch.read_bytes()),
        'client_verifier_sha256':digest(verifier.read_bytes()),
        'patch_check':'pinned_revision_and_reverse_apply_feasibility; not_full_tree_identity'}


ROUTE_CODE=r'''
import contextlib,hashlib,json,os,sys,tempfile,uuid
from pathlib import Path
project,backend=map(Path,sys.argv[1:3]);verifier_hash=sys.argv[3]
os.umask(0o077)
def deny(event,args):
    if event in ('socket.__new__','socket.connect','socket.bind','socket.sendto',
                 'subprocess.Popen','os.system','os.posix_spawn'):
        raise RuntimeError('installation_check_network_or_process_dispatch_forbidden')
sys.addaudithook(deny)
sys.pycache_prefix=str(Path(tempfile.gettempdir())/('bigworld-check-no-bytecode-'+uuid.uuid4().hex))
assert not Path(sys.pycache_prefix).exists()
sys.path[:0]=[str(backend),str(project)]
try:
    with contextlib.redirect_stdout(sys.stderr):
        import app
        assert Path(app.__file__).resolve()==backend/'app/__init__.py'
        from lifespan import actor_contract as verifier
        if Path(verifier.__file__).resolve()!=project/'lifespan/actor_contract.py':raise RuntimeError('client_verifier_import_mismatch')
        if hashlib.sha256(Path(verifier.__file__).read_bytes()).hexdigest()!=verifier_hash:raise RuntimeError('client_verifier_source_changed')
        client=app.create_app().test_client()
        response=client.get('/api/simulation/actor-contract-support')
        if response.status_code!=200:raise RuntimeError('capability_http_status')
        payload=response.get_json(silent=True)
        if type(payload)is not dict or payload.get('success')is not True:raise RuntimeError('capability_response_shape')
        verifier.verify_support(payload['data'])
        support=hashlib.sha256(json.dumps(payload['data'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    result={'ok':True,'http_status':200,'support_sha256':support}
except Exception as exc:
    result={'ok':False,'error_type':type(exc).__name__}
print(json.dumps(result,sort_keys=True,allow_nan=False))
'''


def route_check(project_root,installation,python,timeout_seconds):
    require(type(timeout_seconds) in (int,float) and 0<timeout_seconds<=60,'invalid_check_timeout')
    executable=Path(python).absolute()
    require(executable.is_file(),'missing_backend_python')
    # Anonymous private capture: app/provider exception text never enters the
    # public result or the invoking terminal. No diagnostic file is published.
    with tempfile.TemporaryFile() as stderr:
        try:
            process=subprocess.run([str(executable),'-I','-B','-c',ROUTE_CODE,
                str(Path(project_root).resolve()),str(Path(installation).resolve()/'backend'),
                digest((Path(project_root)/'lifespan/actor_contract.py').read_bytes())],
                cwd=Path(installation)/'backend',stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=stderr,timeout=timeout_seconds,check=True)
        except (OSError,subprocess.SubprocessError) as exc:
            return {'ok':False,'status':'subprocess_failed','error_type':type(exc).__name__}
        require(len(process.stdout)<=65536,'capability_result_too_large')
        try:result=json.loads(process.stdout)
        except (ValueError,UnicodeError):raise CheckError('invalid_capability_result') from None
        require(type(result)is dict and type(result.get('ok'))is bool,'invalid_capability_result')
        if result['ok']:
            require(set(result)=={'ok','http_status','support_sha256'} and type(result['http_status'])is int
                and result['http_status']==200 and type(result['support_sha256'])is str
                and re.fullmatch('[0-9a-f]{64}',result['support_sha256']),'invalid_capability_result')
            return {'ok':True,'status':'verified',**result}
        require(set(result)=={'ok','error_type'} and type(result['error_type'])is str
            and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,79}',result['error_type']),'invalid_capability_result')
        return {'ok':False,'status':'route_failed','error_type':result['error_type']}


def check_installation(installation=None,*,project_root=ROOT,python=None,timeout_seconds=30):
    root=Path(project_root).resolve();installed=Path(installation or root/'MiroFish').resolve()
    output={'schema_version':1,'kind':VERSION,'ok':False,'route':{'status':'not_attempted'},
        'scope':'tracked_override_installation_and_local_capability_GET_only; not_native_worker_or_study_qualification',
        'side_effect_scope':'app_import_may_initialize_logs; configuration_is_not_modified'}
    try:
        before=static_check(root,installed);output['static']=before
        if not before['ok']:return output
        output['route']=route_check(root,installed,python or installed/'backend/.venv/bin/python',timeout_seconds)
        require(static_check(root,installed)==before,'installation_changed_during_route_check')
        output['ok']=output['route']['ok'] is True
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,subprocess.SubprocessError) as exc:
        output['error_type']=type(exc).__name__
        if type(exc)is CheckError:output['error_code']=str(exc)
    return output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation',type=Path,default=ROOT/'MiroFish')
    parser.add_argument('--python',type=Path)
    parser.add_argument('--timeout-seconds',type=float,default=30)
    args=parser.parse_args(argv)
    result=check_installation(args.installation,python=args.python,timeout_seconds=args.timeout_seconds)
    print(json.dumps(result,indent=2,sort_keys=True,allow_nan=False))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
