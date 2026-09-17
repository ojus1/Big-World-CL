"""Exercise reference tools through the pinned native Hermes registry, without inference."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('WORLDLAB_HERMES_TEST_ROOT'), 'Requires the pinned native Hermes runtime')
class Tests(unittest.TestCase):
    def test_native_registration_schemas_and_complete_dispatch_payloads(self):
        hermes = Path(os.environ['WORLDLAB_HERMES_TEST_ROOT'])
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: os.environ[k] for k in ('PATH', 'LANG') if k in os.environ}
            env.update(HOME=tmp, HERMES_HOME=tmp + '/profile', HERMES_AGENT_ROOT=str(hermes),
                       PYTHONPATH=str(repo) + ':' + str(repo / 'tests') + ':' + str(hermes))
            script = '''
from pathlib import Path
import json, os
from test_worldlab_references import library
from worldlab.references import install_native_tools, audit_accesses
from scripts.source_world_calibration import save
from tools.registry import registry
root=Path(os.environ['HOME']); attempt=root/'attempt'; attempt.mkdir()
content='# Native guide\\nComplete café evidence.\\n' * 2000
lib=library(root/'library',content)
toolset=install_native_tools(lib,attempt)
names=set(registry.get_tool_names_for_toolset(toolset))
assert names=={'list_references','read_reference'}
schemas=registry.get_definitions(names,quiet=True)
assert {s['function']['name'] for s in schemas}==names
messages=[]
for i,(name,args) in enumerate([('list_references',{}),('read_reference',{'reference_id':'style_guide'})]):
    result=registry.dispatch(name,args)
    assert json.loads(result)==lib.response(name,args)
    messages.extend([{'role':'assistant','tool_calls':[{'id':str(i),'function':{'name':name,'arguments':json.dumps(args)}}]},
                     {'role':'tool','tool_call_id':str(i),'content':result}])
save(attempt/'NATIVE.json',{'reference_library':lib.identity(),'messages':messages})
assert audit_accesses(attempt,lib)==['style_guide']
print(json.dumps({'ok':True,'complete_content_bytes':len(content.encode()),'tools':sorted(names)}))
'''
            result = subprocess.run([str(hermes / 'venv/bin/python'), '-c', script], env=env,
                                    cwd=tmp, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout.splitlines()[-1])['ok'])


if __name__ == '__main__': unittest.main()
