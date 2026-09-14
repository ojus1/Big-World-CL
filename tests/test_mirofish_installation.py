"""Offline installation fixtures; no installed app, actor or provider is run."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import check_mirofish_installation as q


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)/'project'
        self.installed=Path(self.tmp)/'installed';self.installed.mkdir()
        self.files=('app/utils/actor_output_contract.py','app/utils/actor_contract_transport.json',
                    'app/utils/camel_responses.py','app/utils/local_graph.py')
        self.expected={q.PREFIX+n:('fixture-'+n).encode() for n in self.files}
        self.expected[q.PATCH]=b'checked-in patch fixture'
        self.expected['lifespan/actor_contract.py']=b'checked-in verifier fixture'
        for name,data in self.expected.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            if name.startswith(q.PREFIX):
                target=self.installed/'backend'/name.removeprefix(q.PREFIX)
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        self.git=self.enterContext(patch.object(q,'git',side_effect=self.git_fixture))

    def git_fixture(self,root,*args):
        if args[:1]==('ls-files',):
            return b'\0'.join(('100644 '+'a'*40+' 0\t'+n).encode() for n in self.expected if n.startswith(q.PREFIX))+b'\0'
        if args[:1]==('show',):return self.expected[args[1].removeprefix('HEAD:')]
        if args==('rev-parse','HEAD'):return q.PIN.encode()+b'\n'
        self.assertEqual(args,('apply','--reverse','--check',str(self.root/q.PATCH)));return b''

    def check(self):return q.check_installation(self.installed,project_root=self.root)

    def test_all_four_tracked_overrides_and_patch_are_checked_caches_ignored(self):
        cache=self.root/'local-overrides/backend/app/utils/__pycache__/untracked.pyc'
        cache.parent.mkdir();cache.write_bytes(b'generated-cache')
        result=q.static_check(self.root,self.installed)
        self.assertTrue(result['ok']);self.assertEqual(len(result['tracked_override_files']),4)
        self.assertTrue(all(r['status']=='matched' for r in result['tracked_override_files']))
        self.assertIn('not_full_tree_identity',result['patch_check'])

    def test_each_new_contract_file_is_required_before_route_import(self):
        for name in self.files[:2]:
            with self.subTest(name=name):
                path=self.installed/'backend'/name;data=path.read_bytes();path.unlink()
                with patch.object(q,'route_check') as route:
                    result=self.check();self.assertFalse(result['ok']);route.assert_not_called()
                self.assertEqual([r['path'] for r in result['static']['tracked_override_files'] if r['status']!='matched'],['backend/'+name])
                path.write_bytes(data)

    def test_mismatched_and_symlinked_modules_are_not_installed_matches(self):
        path=self.installed/'backend'/self.files[0];path.write_bytes(b'different')
        result=self.check();self.assertFalse(result['ok'])
        path.unlink();path.symlink_to(self.root/(q.PREFIX+self.files[0]))
        self.assertFalse(self.check()['ok'])

    def test_changed_checked_in_source_or_patch_refuses_before_route(self):
        for name in (q.PREFIX+self.files[0],q.PATCH,'lifespan/actor_contract.py'):
            path=self.root/name;before=path.read_bytes();path.write_bytes(before+b' changed')
            with patch.object(q,'route_check') as route:
                result=self.check();self.assertFalse(result['ok']);route.assert_not_called()
            self.assertIn('checked_in_bytes',result['error_code']);path.write_bytes(before)

    def test_wrong_revision_or_unapplied_patch_fails_closed(self):
        original=self.git_fixture
        def wrong(root,*args):return b'f'*40 if args==('rev-parse','HEAD') else original(root,*args)
        self.git.side_effect=wrong;self.assertEqual(self.check()['error_code'],'mirofish_revision_mismatch')
        def unapplied(root,*args):
            if args[:1]==('apply',):raise subprocess.CalledProcessError(1,'PRIVATE_FIXTURE')
            return original(root,*args)
        self.git.side_effect=unapplied;self.assertEqual(self.check()['error_code'],'tracked_patch_not_applied')

    def test_route_success_failure_and_installation_drift_are_reconciled(self):
        for ok in (True,False):
            with patch.object(q,'route_check',return_value={'ok':ok,'status':'fixture'}):
                self.assertEqual(self.check()['ok'],ok)
        def mutate(*args):
            (self.installed/'backend'/self.files[0]).write_bytes(b'changed-after-static')
            return {'ok':True}
        with patch.object(q,'route_check',side_effect=mutate):
            result=self.check();self.assertFalse(result['ok'])
            self.assertEqual(result['error_code'],'installation_changed_during_route_check')


class RouteTests(unittest.TestCase):
    """Actual isolated checker child; app fixture and exact real wire verifier."""
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.installed=Path(self.tmp)
        self.app=self.installed/'backend/app/__init__.py';self.app.parent.mkdir(parents=True)

    def fixture(self,*,status=200,valid=True,extra=''):
        self.app.write_text("from types import SimpleNamespace\nfrom lifespan.actor_contract import wire\n"+extra+
            "\ndef create_app():\n data=wire.capabilities()\n"+
            (" data['version']='wrong-fixture'\n" if not valid else '')+
            " response=SimpleNamespace(status_code="+str(status)+",get_json=lambda **kwargs:{'success':True,'data':data})\n"
            " def get(path):\n  assert path=='/api/simulation/actor-contract-support'\n  return response\n"
            " return SimpleNamespace(test_client=lambda:SimpleNamespace(get=get))\n")

    def invoke(self):return q.route_check(q.ROOT,self.installed,sys.executable,10)

    def test_exact_real_verifier_accepts_matching_support_only(self):
        self.fixture();result=self.invoke();self.assertTrue(result['ok']);self.assertEqual(result['http_status'],200)
        self.fixture(valid=False);result=self.invoke();self.assertFalse(result['ok']);self.assertEqual(result['error_type'],'ContractError')

    def test_endpoint_status_and_import_exception_are_safe(self):
        self.fixture(status=500);self.assertFalse(self.invoke()['ok'])
        self.fixture(extra="raise RuntimeError('PRIVATE_FIXTURE_CREDENTIAL_TEXT')\n")
        result=self.invoke();self.assertFalse(result['ok']);self.assertNotIn('PRIVATE_FIXTURE',json.dumps(result))

    def test_backend_shadow_cannot_replace_project_client_verifier(self):
        self.app.write_text("from types import SimpleNamespace\n"
            "def create_app():\n"
            " response=SimpleNamespace(status_code=200,get_json=lambda **kwargs:{'success':True,'data':{'unverified':True}})\n"
            " return SimpleNamespace(test_client=lambda:SimpleNamespace(get=lambda path:response))\n")
        shadow=self.installed/'backend/lifespan';shadow.mkdir()
        (shadow/'__init__.py').write_text('')
        (shadow/'actor_contract.py').write_text('def verify_support(value):pass\n')
        # Isolate the origin check from the separate expected-byte check: even
        # a supplied digest matching this permissive shadow must not authorize it.
        with patch.object(q,'digest',return_value=q.digest((shadow/'actor_contract.py').read_bytes())):
            result=self.invoke()
        self.assertFalse(result['ok']);self.assertEqual(result['error_type'],'RuntimeError')

    def test_python_network_and_subprocess_dispatch_are_blocked_before_effect(self):
        canary=Path(self.tmp)/'UNEXPECTED_CHILD'
        for code in ("import socket\nsocket.socket()\n",
                     "import subprocess\nsubprocess.run(["+repr(sys.executable)+",'-c',"+repr('from pathlib import Path;Path('+repr(str(canary))+').touch()')+"])\n"):
            self.fixture(extra=code);result=self.invoke()
            self.assertFalse(result['ok']);self.assertEqual(result['error_type'],'RuntimeError')
            self.assertFalse(canary.exists())

    def test_timeout_and_malformed_subprocess_output_do_not_leak_text(self):
        with patch.object(q.subprocess,'run',side_effect=subprocess.TimeoutExpired('PRIVATE_FIXTURE',10,stderr=b'PRIVATE_FIXTURE')) as run:
            result=self.invoke();self.assertFalse(result['ok']);self.assertNotIn('PRIVATE_FIXTURE',json.dumps(result))
            args,kwargs=run.call_args;self.assertEqual(args[0][1:4],['-I','-B','-c'])
            self.assertEqual(kwargs['timeout'],10);self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
        for raw in (b'PRIVATE_FIXTURE',b'{"ok":true,"PRIVATE_FIXTURE":"secret"}'):
            with patch.object(q.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=raw)):
                with self.assertRaises(q.CheckError):self.invoke()

    @unittest.skipUnless(importlib.util.find_spec('flask'),'Optional Flask dependency unavailable; fake-app guard tests still run')
    def test_actual_flask_test_client_capability_route(self):
        self.app.write_text("from flask import Flask\nfrom lifespan.actor_contract import wire\n"
            "def create_app():\n app=Flask(__name__)\n"
            " @app.get('/api/simulation/actor-contract-support')\n"
            " def support():return {'success':True,'data':wire.capabilities()}\n return app\n")
        self.assertTrue(self.invoke()['ok'])

    def test_cli_never_prints_private_failure_text(self):
        with patch.object(q,'check_installation',return_value={'ok':False,'error_type':'RuntimeError'}),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(q.main([]),1)
        self.assertEqual(json.loads(output.getvalue()),{'ok':False,'error_type':'RuntimeError'})


if __name__=='__main__':unittest.main()
