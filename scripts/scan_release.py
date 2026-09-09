#!/usr/bin/env python3
"""Fail closed on known credentials and common token formats, without printing values.

Use alongside a maintained scanner such as Gitleaks. Environment files are read
only for exact comparisons; their contents and hashes never enter the report.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

PATTERNS = {
    'provider-token': rb'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'aws-access-key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'bearer-token': rb'(?i)bearer\s+[A-Za-z0-9_.~+/=-]{24,}',
    'credential-url': rb'https?://[^\s/:"\x27]+:[^\s/@"\x27]{8,}@',
}


def known_secrets(env_files=()):
    values = dict(os.environ)
    for path in env_files:
        for line in Path(path).read_text().splitlines():
            line = line.strip().removeprefix('export ')
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\x27')
    found = set()
    for key, value in values.items():
        if re.search(r'(?:API_KEY|TOKEN|PASSWORD|SECRET|PRIVATE_KEY)$', key) and len(value) >= 12:
            found.update((value.encode(), quote(value, safe='').encode(), base64.b64encode(value.encode())))
    return found


def issues(data, secrets=()):
    result = [name for name, pattern in PATTERNS.items() if re.search(pattern, data)]
    if any(secret in data for secret in secrets):
        result.append('exact-configured-secret')
    return result


def check_files(files, secrets=()):
    findings = []
    count = 0
    for name, data in files:
        count += 1
        for rule in issues(data, secrets):
            findings.append({'path': name, 'rule': rule})
    return {'passed': not findings, 'files_scanned': count, 'findings': findings}


def directory_files(root):
    root = Path(root)
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('Release contains a symlink: ' + str(p.relative_to(root)))
        if p.is_file():
            yield str(p.relative_to(root)), p.read_bytes()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', nargs='?')
    p.add_argument('--git-index', action='store_true')
    p.add_argument('--env-file', action='append', default=[])
    args = p.parse_args()
    if args.git_index:
        names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
        files = ((n, subprocess.check_output(['git', 'show', ':' + n])) for n in names if n)
    elif args.directory:
        files = directory_files(args.directory)
    else:
        p.error('provide a directory or --git-index')
    result = check_files(files, known_secrets(args.env_file))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
