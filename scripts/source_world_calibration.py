#!/usr/bin/env python3
"""Source exact JobBench and calibrated Internal EuroBench task packages.

No inference or rubric rewriting. The resulting private task bank is ignored by
Git. Mount only one public task directory in an employee computer; all grading
definitions, rubrics, provenance and sibling tasks stay on the evaluator host.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

THREAD = '01a08fbe-18ee-7922-86e3-3c68299b98c9'
VERSION = 'jobbench-eurobench-calibration-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def child(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not (root / p).resolve().is_relative_to(root.resolve()):
        raise ValueError('Unsafe task path: ' + str(relative))
    return root / p


def copy_verified(source, target, expected=None):
    if source.is_symlink() or not source.is_file() or (expected and sha(source) != expected):
        raise ValueError('Missing or changed source: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha(source) != sha(target):
        raise ValueError('Task copy changed')


def assign_groups(rows):
    """Union families, translations and shared source templates before splitting."""
    parent = {}
    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    for row in rows:
        keys = row['lineage_keys']
        for key in keys[1:]:
            a, b = find(keys[0]), find(key)
            parent[max(a, b)] = min(a, b)
        find(keys[0])
    for row in rows:
        group = find(row['lineage_keys'][0])
        digest = hashlib.sha256((VERSION + '\n' + group).encode()).hexdigest()
        bucket = int(digest[:8], 16) % 10
        row.update(calibration_group=group, partition=(
            'calibration_train' if bucket < 6 else 'calibration_validation' if bucket < 8
            else 'calibration_holdout'))


def build(harness, jobbench, out):
    harness, jobbench, out = harness.resolve(), jobbench.resolve(), out.resolve()
    if out.exists():
        raise ValueError('Task bank destination must be fresh')
    upstream = harness / 'internal_benchmarks'
    euro = upstream / 'euro_knowledge_workbench'
    calibration = upstream / 'rubric_calibration/2026-09-11'
    lock = read(upstream / 'jobbench/dataset.lock.json')
    # Verify all 398 locked JobBench files before publishing any bank metadata.
    for name, expected in lock['files'].items():
        path = child(jobbench, name.removeprefix('dataset/'))
        if path.is_symlink() or not path.is_file() or path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
            raise ValueError('JobBench lock mismatch: ' + name)
    catalog = read(euro / 'release/catalog.json')
    tasks = [t for t in catalog if t['split'] in ('development', 'calibration')]
    if len(tasks) != 264 or len(list(jobbench.glob('*/*/RUBRICS.json'))) != 65:
        raise ValueError('Unexpected source cohort; review scope before rebuilding')
    rows = []
    out.mkdir(parents=True)
    for t in tasks:
        task_id = t['id']; key = 'internal/' + task_id
        definition_path = child(euro, t['definition'])
        definition = read(definition_path)
        rubric_path = calibration / 'all-r3/internal' / (task_id + '.json')
        rubric = read(rubric_path)
        if sha(definition_path) != t['definition_sha256'] or rubric['source_definition_sha256'] != sha(definition_path):
            raise ValueError('Internal definition/rubric mismatch: ' + task_id)
        bundle = euro / 'datasets/v1/bundles' / task_id
        bundle_manifest = read(bundle / 'manifest.json')
        if bundle_manifest['definition_sha256'] != sha(definition_path):
            raise ValueError('Internal bundle definition mismatch: ' + task_id)
        public = out / 'public' / key; private = out / 'private' / key
        for name, digest in bundle_manifest['files'].items():
            copy_verified(child(bundle, name), child(public, name), digest)
        copy_verified(definition_path, private / 'definition.json')
        copy_verified(rubric_path, private / 'rubric.json')
        copy_verified(bundle / 'manifest.json', private / 'source_bundle_manifest.json')
        task = {k: definition[k] for k in ('id', 'title', 'instruction', 'language', 'workflow', 'app', 'frozen_clock', 'budgets') if k in definition}
        task['source'] = 'internal_eurobench'
        save(public / 'task.json', task)
        rows.append({'id': key, 'source': 'internal_eurobench', 'task_id': task_id,
            'family_id': t['family_id'], 'title': t['title'], 'language': t['language'],
            'workflow': t['workflow'], 'source_split': t['split'],
            'lineage_keys': ['internal:family:' + t['family_id']] +
                ['internal:lineage:' + value for value in t.get('lineage_groups', [])],
            'public_directory': str(public.relative_to(out)), 'private_directory': str(private.relative_to(out)),
            'definition_sha256': sha(definition_path), 'rubric_sha256': sha(rubric_path),
            'rubric_policy': 'frozen_calibrated_r3_exact_bytes',
            'mechanical_check_kinds': sorted({x['kind'] for x in definition.get('checks', [])}),
            'requires_app_state': bool((definition.get('app') or {}).get('records')),
            'input_files': len(bundle_manifest['files']),
            'input_formats': sorted({Path(name).suffix.lower() for name in bundle_manifest['files']}),
            'native_adapter_status': 'source_package_only'})
    for rubric_path in sorted(jobbench.glob('*/*/RUBRICS.json')):
        task_root = rubric_path.parent; task_id = str(task_root.relative_to(jobbench)); key = 'jobbench/' + task_id
        public = out / 'public' / key; private = out / 'private' / key
        files = [p for p in sorted((task_root / 'task_folder').rglob('*')) if p.is_file()]
        for p in files:
            relative = str(p.relative_to(jobbench))
            locked = lock['files'].get('dataset/' + relative)
            if locked is None:
                raise ValueError('Unregistered task-folder file: ' + relative)
            copy_verified(p, public / p.relative_to(task_root / 'task_folder'), locked['sha256'])
        copy_verified(rubric_path, private / 'RUBRICS.json')
        instruction = task_root / 'task_folder/TASK_INSTRUCTIONS.txt'
        profession = task_root.parent.name
        save(public / 'task.json', {'id': key, 'source': 'jobbench', 'profession': profession,
            'instruction_file': 'TASK_INSTRUCTIONS.txt', 'language': 'en',
            'instruction': instruction.read_text(), 'external_research_policy': 'Preserve original JobBench research requirements; no reference answer collections are included.'})
        rows.append({'id': key, 'source': 'jobbench', 'task_id': task_id,
            'family_id': profession, 'title': profession.replace('_', ' ') + ' / ' + task_root.name,
            'language': 'en', 'workflow': profession, 'source_split': 'official_main',
            'lineage_keys': ['jobbench:profession:' + profession],
            'public_directory': str(public.relative_to(out)), 'private_directory': str(private.relative_to(out)),
            'instruction_sha256': sha(instruction), 'rubric_sha256': sha(rubric_path),
            'rubric_policy': 'official_unchanged', 'requires_app_state': False,
            'external_research_policy': 'task_dependent_as_original',
            'input_files': len(files), 'input_formats': sorted({p.suffix.lower() for p in files}),
            'native_adapter_status': 'source_package_only'})
    assign_groups(rows)
    rows.sort(key=lambda r: r['id'])
    with (out / 'TASKS.jsonl').open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n')
    for source, target in ((upstream / 'jobbench/dataset.lock.json', 'jobbench-dataset.lock.json'),
                           (euro / 'release/manifest.json', 'internal-release.json'),
                           (calibration / 'freeze.json', 'internal-rubric-freeze.json'),
                           (calibration / 'calibration-verification.json', 'internal-calibration-verification.json')):
        copy_verified(source, out / 'provenance' / target)
    inventory = {str(p.relative_to(out)): {'sha256': sha(p), 'bytes': p.stat().st_size}
                 for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'FILES.json', inventory)
    manifest = {'version': VERSION, 'source_task': THREAD,
        'harness_repository': 'prem-research/harness-benchmarks',
        'harness_commit': subprocess.check_output(['git', '-C', str(harness), 'rev-parse', 'HEAD'], text=True).strip(),
        'jobbench_dataset_revision': lock['revision'], 'jobbench_dataset_repository': lock['repository'],
        'files_sha256': sha(out / 'FILES.json'), 'catalog_sha256': sha(out / 'TASKS.jsonl'),
        'source_counts': dict(Counter(r['source'] for r in rows)),
        'source_partition_counts': dict(Counter(r['source'] + '/' + r['partition'] for r in rows)),
        'family_counts': {s: len({r['family_id'] for r in rows if r['source'] == s}) for s in ('jobbench', 'internal_eurobench')},
        'connected_lineage_groups': len({r['calibration_group'] for r in rows}),
        'internal_languages': dict(Counter(r['language'] for r in rows if r['source'] == 'internal_eurobench')),
        'split_rule': 'Connected family/source-template groups (JobBench: whole profession) hashed with version; buckets 0-5 train, 6-7 validation, 8-9 calibration holdout. Never split translated variants.',
        'excluded': {'internal_reserved_test_instances': len(catalog) - len(tasks),
                     'jobbench_easy_split': True, 'jobbench_reference_answer_collections': True,
                     'historical_solver_outputs_and_judge_labels': True},
        'interpretation': 'A sourced calibration bank, not executed final-world evidence. Calibration holdout is held out from new adaptive calibration, not claimed unseen historically or during model pretraining. Source tasks and grading rubrics remain unchanged.',
        'execution_requirements': ['Per-task public mount only; private rubrics/gold and other tasks never mounted.',
            'Original multi-file and binary deliverables, research access where required, and native simulated app state.',
            'Original EuroBench mechanical graders plus frozen r3 qualitative criteria; JobBench official rubrics.',
            'Calibrate target time/call budgets and judge validity before freezing the final world. Current three-JSON-workflow runner does not execute these packages.']}
    save(out / 'MANIFEST.json', manifest)
    return verify(out)


def verify(out):
    out = out.resolve(); manifest = read(out / 'MANIFEST.json')
    if sha(out / 'FILES.json') != manifest['files_sha256'] or sha(out / 'TASKS.jsonl') != manifest['catalog_sha256']:
        raise ValueError('Bank metadata changed')
    inventory = read(out / 'FILES.json')
    actual = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()} - {'FILES.json', 'MANIFEST.json', 'VERIFICATION.json'}
    if actual != set(inventory):
        raise ValueError('Bank file inventory changed')
    for name, expected in inventory.items():
        p = child(out, name)
        if p.is_symlink() or sha(p) != expected['sha256'] or p.stat().st_size != expected['bytes']:
            raise ValueError('Bank file changed: ' + name)
    rows = [json.loads(line) for line in (out / 'TASKS.jsonl').read_text().splitlines()]
    partitions = {}
    for row in rows:
        for key in row['lineage_keys']:
            partitions.setdefault(key, set()).add(row['partition'])
        public = child(out, row['public_directory'])
        if any(p.name in ('RUBRICS.json', 'rubric.json', 'definition.json') for p in public.rglob('*')):
            raise ValueError('Private evaluator file in public package')
        if any(k in read(public / 'task.json') for k in ('checks', 'rubric', 'criteria', 'design_notes', 'provenance')):
            raise ValueError('Private evaluator fields in public descriptor')
    if any(len(values) != 1 for values in partitions.values()):
        raise ValueError('Source lineage crosses calibration partitions')
    return {'ok': True, 'tasks': len(rows), 'verified_files': len(inventory),
            'verified_bytes': sum(x['bytes'] for x in inventory.values()),
            'manifest_sha256': sha(out / 'MANIFEST.json'), 'lineage_partition_leaks': 0,
            'source_counts': manifest['source_counts'], 'source_partition_counts': manifest['source_partition_counts']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('build', 'verify')); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--harness', type=Path); p.add_argument('--jobbench', type=Path)
    a = p.parse_args()
    result = build(a.harness, a.jobbench, a.out) if a.command == 'build' else verify(a.out)
    print(json.dumps(result, indent=2))
