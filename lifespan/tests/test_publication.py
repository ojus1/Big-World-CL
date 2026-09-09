"""Publication checks protect credentials and preserve normalized file provenance."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from export_dataset import Sanitizer, read_file
from scan_release import check_files, issues, known_secrets


class PublicationTests(unittest.TestCase):
    def test_known_secret_is_detected_without_appearing_in_report(self):
        secret = b'sensitive' + b'-value-for-test'
        report = check_files([('artifact.json', b'{"value":"' + secret + b'"}')], [secret])
        self.assertFalse(report['passed'])
        self.assertNotIn(secret.decode(), json.dumps(report))

    def test_provider_formats_are_detected(self):
        self.assertIn('provider-token', issues(('hf' + '_' + 'a' * 34).encode()))
        self.assertEqual(issues(b'OPENAI_API_KEY=\n'), [])

    def test_environment_file_values_are_not_echoed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.env'
            p.write_text('OPENAI_API_KEY="fixture-private-value"\nLLM_MODEL_NAME=public-model\n')
            secrets = known_secrets([p])
            self.assertIn(b'fixture-private-value', secrets)
            self.assertNotIn(b'public-model', secrets)

    def test_sanitization_rehashes_nested_objects_and_sizes(self):
        leaf = b'/host/user/notes\n'
        sha = hashlib.sha256(leaf).hexdigest()
        parent = json.dumps({'file': {'sha256': sha, 'bytes': len(leaf)}}).encode()
        parent_sha = hashlib.sha256(parent).hexdigest()
        s = Sanitizer([('/host/user', '/employee')], {sha: leaf, parent_sha: parent})
        clean = s.clean({'sha256': parent_sha, 'bytes': len(parent)})
        blob = s.blobs[clean['sha256']]
        self.assertEqual(hashlib.sha256(blob).hexdigest(), clean['sha256'])
        nested = json.loads(blob)['file']
        self.assertEqual(s.blobs[nested['sha256']], b'/employee/notes\n')
        self.assertEqual(nested['bytes'], len(b'/employee/notes\n'))
        self.assertNotEqual(clean['sha256'], parent_sha)

    def test_transport_fields_removed_but_tools_retained(self):
        record = {'role': 'assistant', 'content': 'done', 'codex_reasoning_items': ['opaque'],
                  'reasoning_content': 'private reasoning', 'tool_calls': [{'id': 'call-1'}]}
        clean = Sanitizer().clean(record)
        self.assertEqual(clean, {'role': 'assistant', 'content': 'done', 'tool_calls': [{'id': 'call-1'}]})

    def test_unchanged_file_retains_original_hash(self):
        data = b'{ "task_id": "a", "work": "done" }\n'
        sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(Sanitizer(objects={sha: data}).object(sha), (sha, len(data)))

    def test_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'target'; target.write_text('private')
            link = Path(d) / 'link'; link.symlink_to(target)
            with self.assertRaises(ValueError):
                read_file(link)


if __name__ == '__main__':
    unittest.main()
