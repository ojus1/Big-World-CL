"""Verified source packages with an explicit public projection."""
import json
from pathlib import Path
from scripts.source_world_calibration import child, copy_verified, read, sha, verify


class Bank:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.verification = verify(self.root)
        self.manifest = read(self.root / 'MANIFEST.json')
        self.rows = [json.loads(line) for line in (self.root / 'TASKS.jsonl').read_text().splitlines()]
        self.by_id = {row['id']: row for row in self.rows}
        if len(self.by_id) != len(self.rows):
            raise ValueError('Duplicate task identity')
        self.inventory = read(self.root / 'FILES.json')

    def public(self, task_id):
        row = self.by_id[task_id]
        task = read(child(self.root, row['public_directory']) / 'task.json')
        # No raw row/private paths are passed to a harness.
        return {**task, 'id': task_id, 'input_formats': row['input_formats'],
                'requires_app_state': row['requires_app_state'],
                'source': row['source']}

    def stage(self, task_id, workspace):
        """Copy exact binary bytes; never mount the bank or private definitions."""
        workspace = Path(workspace)
        if workspace.exists():
            raise ValueError('Each attempt requires a fresh workspace')
        row = self.by_id[task_id]
        prefix = row['public_directory'] + '/'
        workspace.mkdir(parents=True)
        baseline = {}
        for name, receipt in sorted(self.inventory.items()):
            if name.startswith(prefix):
                relative = name[len(prefix):]
                # task.json is our public descriptor, not an original benchmark input.
                if relative == 'task.json':
                    continue
                source = child(self.root, name)
                target = child(workspace, relative)
                copy_verified(source, target, receipt['sha256'])
                baseline[relative] = sha(target)
        return baseline

    def private_definition(self, task_id):
        row = self.by_id[task_id]
        if row['source'] != 'internal_eurobench':
            raise ValueError('This source has no EuroBench definition')
        return read(child(self.root, row['private_directory']) / 'definition.json')
