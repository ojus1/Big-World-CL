#!/usr/bin/env python3
"""Explicitly publish a scanned, manifest-verified export using HF_TOKEN in memory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from scan_release import check_files, directory_files, known_secrets


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory')
    p.add_argument('--repo', default='ojus1/BigWorld-PoC')
    a = p.parse_args()
    root = Path(a.directory)
    files = dict(directory_files(root))
    report = check_files(files.items(), known_secrets())
    if not report['passed']:
        raise SystemExit(json.dumps(report))
    manifest = json.loads(files['release_manifest.json'])
    assert set(files) == set(manifest['files']) | {'release_manifest.json'}, 'Unmanifested release content'
    for name, entry in manifest['files'].items():
        assert len(files[name]) == entry['bytes']
        assert hashlib.sha256(files[name]).hexdigest() == entry['sha256'], name
    from huggingface_hub import HfApi
    token = os.environ['HF_TOKEN']
    api = HfApi(token=token)
    api.create_repo(a.repo, repo_type='dataset', exist_ok=True, private=False)
    result = api.upload_folder(repo_id=a.repo, repo_type='dataset', folder_path=root,
                               commit_message='Publish audited 16-day MiroFish, Persona 8B and Hermes PoC')
    info = api.repo_info(a.repo, repo_type='dataset')
    remote = set(api.list_repo_files(a.repo, repo_type='dataset', revision=info.sha))
    assert set(files).issubset(remote), 'Remote upload missing files'
    print(json.dumps({'repo': a.repo, 'commit': info.sha, 'url': result.commit_url,
                      'published_files': len(files), 'credential_scan_passed': True}))


if __name__ == '__main__':
    main()
