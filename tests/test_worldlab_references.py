"""Complete source projection, isolation and native reference-read provenance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import read, save, sha
from worldlab.references import ReferenceLibrary, extract, audit_accesses, payload_hash
from worldlab.reference_hermes import ReferenceHermes
from worldlab.hermes import Hermes
from worldlab import jobbench_capabilities as caps


def library(root, content='# Guide\nUse active voice.\n'):
    root.mkdir()
    (root / 'raw.txt').write_bytes(content.encode())
    (root / 'content.txt').write_bytes(content.encode())
    save(root / 'MANIFEST.json', {'version': 1, 'references': [{
        'id': 'style_guide', 'title': 'Public style guide', 'source_url': 'https://example.org/style',
        'fetched_at': '2026-09-15T00:00:00Z', 'raw_path': 'raw.txt', 'content_path': 'content.txt',
        'extractor': {'kind': 'identity'}, 'raw_sha256': sha(root / 'raw.txt'),
        'content_sha256': sha(root / 'content.txt')}]})
    return ReferenceLibrary(root)


class Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_exact_nested_html_projection_preserves_links_code_and_unicode(self):
        fragment='<div class="other article-body"><h1>Résumé</h1><div><code>a &lt; b</code></div><a href="/guide">Next</a></div>'
        raw=('<html>navigation' + fragment + '<footer>footer</footer></html>').encode()
        rule={'kind':'html_element','tag':'div','attribute':'class','value':'article-body'}
        self.assertEqual(extract(raw,rule),fragment)
        for bad in [b'<div>wrong</div>', (fragment+fragment).encode(), fragment[:-6].encode()]:
            with self.assertRaises(ValueError): extract(bad,rule)

    def test_gist_rejects_truncated_reference_and_keeps_original_markdown(self):
        value={'files':{'guide.md':{'truncated':False,'content':'# Exact\n```json\n{}\n```\n'}}}
        rule={'kind':'github_gist','file':'guide.md'}
        self.assertEqual(extract(json.dumps(value).encode(),rule),value['files']['guide.md']['content'])
        value['files']['guide.md']['truncated']=True
        with self.assertRaises(ValueError): extract(json.dumps(value).encode(),rule)

    def test_complete_large_source_has_no_character_quota_or_summary(self):
        content='résumé — use `code` and [links](https://example.org)\n'*10000
        lib=library(self.root/'library',content)
        result=lib.response('read_reference',{'reference_id':'style_guide'})
        self.assertEqual(result['content'],content)
        self.assertEqual(result['content_sha256'],sha(lib.root/'content.txt'))
        self.assertNotIn('maxLength',json.dumps(lib.schemas()))
        self.assertEqual(lib.schemas()[1]['parameters']['properties']['reference_id']['enum'],['style_guide'])

    def test_changes_to_content_raw_source_and_projection_are_rejected(self):
        for name in ['raw.txt','content.txt']:
            root=self.root/name;lib=library(root)
            (root/name).write_text('Replaced')
            with self.assertRaises(ValueError):lib.content('style_guide')
        root=self.root/'mismatch';lib=library(root)
        (root/'content.txt').write_text('Forged projection')
        manifest=read(root/'MANIFEST.json');manifest['references'][0]['content_sha256']=sha(root/'content.txt')
        save(root/'MANIFEST.json',manifest)
        with self.assertRaisesRegex(ValueError,'projection'):ReferenceLibrary(root)

    def test_reference_paths_cannot_escape_library_or_follow_symlinks(self):
        for kind in ['parent','link']:
            root=self.root/kind;lib=library(root)
            outside=self.root/(kind+'-private.txt');outside.write_text('Evaluator-only fixture')
            manifest=read(root/'MANIFEST.json')
            if kind=='parent':manifest['references'][0]['content_path']='../'+outside.name
            else:
                (root/'content.txt').unlink();(root/'content.txt').symlink_to(outside)
            save(root/'MANIFEST.json',manifest)
            with self.assertRaises(ValueError):ReferenceLibrary(root)

    def native_case(self):
        lib=library(self.root/'library');root=self.root/'attempt';root.mkdir()
        args={'reference_id':'style_guide'};result=lib.response('read_reference',args)
        native={'reference_library':lib.identity(),'messages':[
            {'role':'assistant','tool_calls':[{'id':'read-1','function':{'name':'read_reference','arguments':json.dumps(args)}}]},
            {'role':'tool','tool_call_id':'read-1','name':'read_reference','content':json.dumps(result)}]}
        row={'tool':'read_reference','arguments':args,'response_sha256':payload_hash(result)}
        save(root/'NATIVE.json',native)
        (root/'REFERENCE_ACCESSES.jsonl').write_text(json.dumps(row)+'\n')
        return lib,root,native,row

    def test_audit_binds_native_calls_full_returned_content_and_access_ledger(self):
        lib,root,native,row=self.native_case()
        self.assertEqual(audit_accesses(root,lib),['style_guide'])
        result=json.loads(native['messages'][1]['content']);result['content']='Altered source'
        native['messages'][1]['content']=json.dumps(result)
        save(root/'NATIVE.json',native)
        row['response_sha256']=payload_hash(result)
        (root/'REFERENCE_ACCESSES.jsonl').write_text(json.dumps(row)+'\n')
        with self.assertRaisesRegex(ValueError,'response changed'):audit_accesses(root,lib)

    def test_audit_rejects_fabricated_or_missing_access(self):
        lib,root,native,row=self.native_case()
        (root/'REFERENCE_ACCESSES.jsonl').write_text('')
        with self.assertRaisesRegex(ValueError,'ledger'):audit_accesses(root,lib)
        (root/'REFERENCE_ACCESSES.jsonl').write_text(json.dumps(row)+'\n')
        native['messages'].pop();save(root/'NATIVE.json',native)
        with self.assertRaisesRegex(ValueError,'ledger'):audit_accesses(root,lib)

    def test_invalid_reference_cannot_read_arbitrary_host_file(self):
        lib=library(self.root/'library')
        for args in [{'reference_id':'/etc/passwd'}, {'reference_id':['style_guide']},
                     {'reference_id':'style_guide','path':'/etc/passwd'}, []]:
            self.assertIn('error',lib.response('read_reference',args))

    def test_required_references_gate_execution_but_not_original_rubric_evidence(self):
        public={'source':'jobbench','id':'fixture','instruction':'Consult the style guide.', 'input_formats':['.md']}
        import hashlib
        review={'instruction_sha256':hashlib.sha256(public['instruction'].encode()).hexdigest(),
                'input_formats':['.md'],'required_references':['style_guide']}
        with patch.dict(caps.REVIEWED,{'fixture':review}):
            self.assertTrue(caps.unsupported(public))
            self.assertEqual(caps.unsupported(public,evidence_only=True),[])
            harness=object.__new__(ReferenceHermes);harness.references=library(self.root/'library')
            self.assertEqual(harness.unsupported(public),[])
            self.assertEqual(harness.worker_options()['public_references']['identity'],harness.references.identity())
        self.assertEqual(object.__new__(Hermes).worker_options(),{})


if __name__=='__main__':unittest.main()
