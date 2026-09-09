#!/usr/bin/env python3
"""Curate a completed ecosystem run; never copy native profiles or credential stores.

Only an allowlist is read. Publication is a separate explicit command. The
destination must not exist. Any detected credential aborts before it is created.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_release import check_files, known_secrets

ROOT = Path(__file__).resolve().parents[1]
OMIT_KEYS = frozenset({'encrypted_content', 'codex_reasoning_items', 'codex_message_items',
                      '_db_persisted', 'last_reasoning', 'reasoning_content', 'reasoning'})


class Sanitizer:
    def __init__(self, replacements=(), objects=None):
        self.replacements = sorted(replacements, key=lambda p: -len(p[0]))
        self.objects = objects or {}
        self.mapping = {}
        self.blobs = {}
        self.active = set()
        self.omitted = Counter()

    def string(self, value):
        for old, new in self.replacements:
            value = value.replace(old, new)
        return re.sub(r'\b[a-f0-9]{64}\b',
                      lambda m: self.object(m[0])[0] if m[0] in self.objects else m[0], value)

    def clean(self, value):
        if isinstance(value, str):
            return self.string(value)
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, dict):
            result = {}
            for key, v in value.items():
                if key in OMIT_KEYS:
                    self.omitted[key] += 1
                else:
                    result[key] = self.clean(v)
            if value.get('sha256') in self.objects and 'bytes' in value:
                result['sha256'], result['bytes'] = self.object(value['sha256'])
            return result
        return value

    def content(self, data):
        text = data.decode('utf-8')  # Unknown binary content fails closed.
        try:
            original = json.loads(text)
            cleaned = self.clean(original)
            return data if original == cleaned else (json.dumps(cleaned, ensure_ascii=False, indent=2) + '\n').encode()
        except json.JSONDecodeError:
            lines = text.splitlines()
            try:
                rows = [json.loads(line) for line in lines if line.strip()]
            except json.JSONDecodeError:
                return self.string(text).encode()
            clean = [self.clean(row) for row in rows]
            if rows == clean:
                return data
            return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in clean).encode()

    def object(self, sha):
        if sha not in self.mapping:
            if sha in self.active:
                raise ValueError('Cyclic content-hash references')
            self.active.add(sha)
            data = self.objects[sha]
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError('Invalid source filesystem object')
            clean = self.content(data)
            new_sha = hashlib.sha256(clean).hexdigest()
            self.mapping[sha] = (new_sha, len(clean))
            self.blobs[new_sha] = clean
            self.active.remove(sha)
        return self.mapping[sha]


def read_file(path):
    if path.is_symlink():
        raise ValueError('Refusing a release source symlink: ' + str(path))
    return path.read_bytes()


def export_run(source, destination, revision, secrets=()):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError('Choose a new destination outside the source run')
    prefix = 'runs/ecosystem-bwrap/'
    raw = {}
    def take(relative, public=None):
        raw[prefix + (public or relative)] = read_file(source / relative)

    for name in ('RESULTS.json', 'VALIDATION.json', 'manifest.json', 'timeline.json',
                 'actor_decisions.json', 'persona_cohort.json', 'imported_mirofish_profiles.json',
                 'mirofish_source.txt', 'checkpoint.json', 'private/final_world.json'):
        take(name, 'evaluator/' + name)
    for directory in ('actor_sessions', 'employee_sessions', 'daily', 'mirofish_interviews', 'infrastructure_failures'):
        for path in sorted((source / directory).rglob('*.json')):
            relative = path.relative_to(source).as_posix()
            take(relative, 'evaluator/' + relative)
    for path in sorted((source / 'learner').glob('*')):
        if path.suffix in ('.json', '.jsonl'):
            take(path.relative_to(source).as_posix())
    # Workspaces are synthetic employee artifacts; native config/db/logs are not.
    for employee in sorted((source / 'computers').iterdir()):
        if not employee.is_dir() or employee.is_symlink():
            raise ValueError('Invalid employee directory')
        for directory in ('workspace', 'os_home', 'hermes/memories', 'hermes/skills'):
            for path in sorted((employee / directory).rglob('*')):
                if path.is_symlink():
                    raise ValueError('Review employee symlinks before publication')
                if path.is_file():
                    take(path.relative_to(source).as_posix())
        for name in ('computer_state.json', 'instance.json', 'hermes/lifespan_history.json'):
            path = employee / name
            if path.exists():
                rel = path.relative_to(source).as_posix()
                take(rel, 'evaluator/' + rel)

    # Export logical native evidence, not the SQLite container or unused pages.
    with sqlite3.connect((source / 'mirofish_simulation.db').as_uri() + '?mode=ro', uri=True) as db:
        rows = [{'user_id': u, 'created_at': t, 'action': a, 'info': json.loads(info)}
                for u, t, a, info in db.execute('SELECT user_id,created_at,action,info FROM trace ORDER BY rowid')]
    raw[prefix + 'evaluator/mirofish_native_trace.jsonl'] = ''.join(json.dumps(r) + '\n' for r in rows).encode()
    objects = {p.name: read_file(p) for p in sorted((source / 'filesystem_objects').iterdir())}
    originals = list(raw.items()) + [('filesystem_objects/' + k, v) for k, v in objects.items()]
    # Check exact credentials even in omitted fields. Ciphertext may randomly
    # resemble token syntax; pattern matching applies after transport removal.
    exact_findings = [{'path': name, 'rule': 'exact-configured-secret'} for name, data in originals
                      if any(secret in data for secret in secrets)]
    if exact_findings:
        raise ValueError('Credential scan failed: ' + json.dumps(exact_findings))
    original_check = check_files(((name, Sanitizer().content(data)) for name, data in originals), secrets)
    if not original_check['passed']:
        raise ValueError('Credential scan failed: ' + json.dumps(original_check['findings']))
    sanitizer = Sanitizer([(str(source), '/simulation/run'), (str(ROOT), '/simulation/code'),
                           (str(Path.home()), '/runtime/host-home')], objects)
    for sha in objects:
        sanitizer.object(sha)
    output = {name: sanitizer.content(data) for name, data in raw.items()}
    output.update({prefix + 'filesystem_objects/' + sha: data for sha, data in sanitizer.blobs.items()})
    for name in list(output):
        if '/infrastructure_failures/' in name and name.endswith('/recovery.json'):
            history = name.rsplit('/', 1)[0] + '/hermes_history.json'
            recovery = json.loads(output[name])
            recovery['source_history_sha256'] = recovery['history_sha256']
            recovery['history_sha256'] = hashlib.sha256(output[history]).hexdigest()
            output[name] = (json.dumps(recovery, indent=2) + '\n').encode()

    sessions = [json.loads(line) for line in output[prefix + 'learner/sessions.jsonl'].decode().splitlines()]
    events = json.loads(output[prefix + 'evaluator/timeline.json'])
    results = json.loads(output[prefix + 'evaluator/RESULTS.json'])
    assert len(sessions) == results['hermes_sessions']
    assert len(events) == results['timeline_events']
    for s in sessions:
        for field in ('filesystem_before', 'filesystem_after'):
            for entry in s[field].values():
                if 'sha256' in entry:
                    blob = sanitizer.blobs[entry['sha256']]
                    assert hashlib.sha256(blob).hexdigest() == entry['sha256']
                    assert len(blob) == entry['bytes']
    event_ids = set()
    for e in events:
        assert e['id'] not in event_ids and all(c in event_ids for c in e['causes'])
        event_ids.add(e['id'])

    # Flat, stable schemas let the Hub viewer expose heterogeneous trajectories.
    flat_sessions = [{'id': f"d{s['day']:03d}-{s['employee']}-{s['task_id']}",
                      'run_id': 'ecosystem-bwrap', 'day': s['day'], 'employee': s['employee'],
                      'task_id': s['task_id'], 'session_json': json.dumps(s, ensure_ascii=False)} for s in sessions]
    flat_events = [{'run_id': 'ecosystem-bwrap', 'id': e['id'], 'day': e['day'], 'actor': e['actor'],
                    'kind': e['kind'], 'event_json': json.dumps(e, ensure_ascii=False)} for e in events]
    for name, rows in [('data/sessions.jsonl', flat_sessions), ('data/events.jsonl', flat_events)]:
        output[name] = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode()

    card = (ROOT / 'docs/DATASET_CARD.md').read_text().replace('{{CODE_REVISION}}', revision)
    output['README.md'] = card.encode()
    output['LICENSE'] = (ROOT / 'docs/DATASET_TERMS.md').read_bytes()
    walkthrough = (source / 'WALKTHROUGH.md').read_text()
    for directory in ('actor_sessions/', 'employee_sessions/'):
        walkthrough = walkthrough.replace('](' + directory, '](evaluator/' + directory)
    for name in ('VALIDATION.json', 'timeline.json'):
        walkthrough = walkthrough.replace('](' + name, '](evaluator/' + name)
    walkthrough = walkthrough.replace('](REPORT.md)', '](../../README.md)')
    walkthrough = walkthrough.replace('](../../docs/ECOSYSTEM_DESIGN.md)',
        f'](https://github.com/ojus1/Big-World-CL/blob/{revision}/lifespan/docs/ECOSYSTEM_DESIGN.md)')
    walkthrough += '\nPublic export: native credential/configuration stores and transport-only fields are omitted. See the dataset card and release manifest.\n'
    output[prefix + 'WALKTHROUGH.md'] = walkthrough.encode()
    manifest = {
        'schema_version': 1, 'run_id': 'ecosystem-bwrap', 'code_repository': 'https://github.com/ojus1/Big-World-CL',
        'release_code_revision': revision,
        'source_scope': 'Release/export code; live run included earlier adapter revisions. See evaluator/manifest.json.',
        'counts': {'sessions': len(sessions), 'events': len(events), 'filesystem_objects': len(sanitizer.blobs)},
        'normalization': {'host_paths': 'Replaced with /simulation/run, /simulation/code, /runtime/host-home',
                          'omitted_fields': dict(sanitizer.omitted),
                          'changed_objects': {old: {'sha256': new, 'bytes': size} for old, (new, size) in sanitizer.mapping.items() if old != new},
                          'hash_policy': 'Referenced object hashes and sizes are recomputed. Original validation is historical evidence.'},
        'excluded': ['native config and credential stores', 'native SQLite profiles and raw simulation database',
                     'runtime logs, sockets, caches, PID files', 'unspecified files outside the export allowlist'],
        'validation': {'source_credential_scan_passed': True, 'causal_references_passed': True,
                       'session_filesystem_hashes_and_sizes_passed': True},
    }
    # Scan documents and generated records as well; write nothing on failure.
    check = check_files(output.items(), secrets)
    if not check['passed']:
        raise ValueError('Export scan failed: ' + json.dumps(check['findings']))
    manifest['files'] = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                         for name, data in sorted(output.items())}
    output['release_manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    for name, data in output.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {'files': len(output), 'bytes': sum(map(len, output.values())), **manifest['counts']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('destination')
    p.add_argument('--code-revision', required=True)
    p.add_argument('--env-file', action='append', default=[])
    a = p.parse_args()
    if not re.fullmatch('[a-f0-9]{40}', a.code_revision):
        p.error('--code-revision must be a full Git commit')
    print(json.dumps(export_run(a.source, a.destination, a.code_revision, known_secrets(a.env_file)), indent=2))


if __name__ == '__main__':
    main()
