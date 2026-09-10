#!/usr/bin/env python3
"""Additive audit correction for the frozen scale-v1 native CLI module alias.

The published launcher uses ``python -m lifespan.evaluation.runner``. Python
therefore records its locally defined NativeActors class as __main__.NativeActors.
This adapter changes exactly that one comparison in an isolated, hash-verified
copy of the frozen auditor. It neither edits source/evidence nor normalizes raw
reports. Exact observed launch commands, executor and cohort are checked first.
The during-execution launch observations are not preregistered evidence.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_evaluation import child, read, require

PUBLISHED_COMMIT = 'b72fdda979dccd9065ec41b4629c58a14848e762'
CAMPAIGN_SHA256 = '6f6bc76c30a642cf2b364b28dc18ca0054398d64aba3a0b08c4b23479480bffa'
LAUNCH_RECEIPTS_SHA256 = 'e9356a3ddc08579697c648593b840db505ff51d8a8191cda86f7b3d99c088ec1'
FROZEN_AUDITOR_SHA256 = '1fa30c25a79eb3919ffa88ce18ca816751a546c4a58e642b0dfdd28bd526b72b'
FROZEN_LAUNCHER_SHA256 = '661ff24937aa06bfd86797d0ef219374411122f1aedde6ed8e5534f9d0f9f18f'
FROZEN_RUNNER_SHA256 = '9033a15681456a3b1411182dec2b353ba17fbb9ad4db72cf685878b5493da577'
ALIAS = '__main__.NativeActors'
CANONICAL = 'lifespan.evaluation.runner.NativeActors'
EXECUTOR = 'lifespan.evaluation.runtime.execute_case'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def isolated_auditor(corrected):
    """Execute frozen local definitions; change only an exact AST comparison."""
    path = ROOT / 'scripts/audit_scale.py'
    require(sha(path) == FROZEN_AUDITOR_SHA256, 'unsupported_frozen_auditor_revision')
    tree = ast.parse(path.read_text(), filename=str(path))
    matches = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
                and isinstance(node.left, ast.Subscript) and isinstance(node.left.value, ast.Name)
                and node.left.value.id == 'provenance' and isinstance(node.left.slice, ast.Constant)
                and node.left.slice.value == 'actor_driver' and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == CANONICAL):
            matches.append(node)
    require(len(matches) == 1, 'unsupported_actor_guard_structure')
    if corrected:
        matches[0].comparators[0].value = ALIAS
    namespace = {'__name__': 'scripts._isolated_frozen_scale_audit', '__file__': str(path)}
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace


def launch_check(root, manifest):
    """Validate a fixed post-launch observation without rereading live processes."""
    require(sha(root / 'campaign.json') == CAMPAIGN_SHA256, 'unsupported_published_campaign')
    require(len(manifest['source_sha256']) == 34
            and manifest['source_sha256']['scripts/audit_scale.py'] == FROZEN_AUDITOR_SHA256
            and manifest['source_sha256']['scripts/run_scale.py'] == FROZEN_LAUNCHER_SHA256
            and manifest['source_sha256']['lifespan/evaluation/runner.py'] == FROZEN_RUNNER_SHA256,
            'unsupported_published_execution_sources')
    path = root / 'CLI_LAUNCH_RECEIPTS.json'
    require(sha(path) == LAUNCH_RECEIPTS_SHA256, 'launch_observation_bytes_changed')
    receipt, execution = read(path), read(root / 'EXECUTION.json')
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1
            and receipt['kind'] == 'observed_native_module_launch'
            and receipt['observation_kind'] == 'during_execution_not_preregistered'
            and receipt['published_commit'] == PUBLISHED_COMMIT
            and receipt['campaign_sha256'] == CAMPAIGN_SHA256
            and receipt['execution_sha256'] == sha(root / 'EXECUTION.json')
            and receipt['source_sha256'] == manifest['source_sha256'], 'launch_observation_provenance_mismatch')
    require(datetime.fromisoformat(receipt['observed_at']) >= datetime.fromisoformat(execution['started_at']),
            'launch_observation_predates_execution')
    parent = receipt['supervisor']; rows = receipt['runs']
    require(type(parent['pid']) is int and parent['pid'] == execution['supervisor_pid']
            and type(parent['start_ticks']) is int and parent['start_ticks'] > 0
            and type(receipt['clock_ticks_per_second']) is int and receipt['clock_ticks_per_second'] > 0
            and isinstance(receipt['boot_id'], str) and bool(receipt['boot_id'])
            and len(rows) == 6 and len({row['pid'] for row in rows}) == 6
            and [row['run_id'] for row in rows] == [slot['run_id'] for slot in manifest['slots']], 'launch_process_identity_mismatch')
    python = ROOT / 'MiroFish/backend/.venv/bin/python'
    for slot, row in zip(manifest['slots'], rows):
        run = child(root, slot['relative_path'])
        expected = [str(python), '-u', '-m', 'lifespan.evaluation.runner', '--out', str(run), '--config', str(run / 'config.json')]
        require(row['argv'] == expected and type(row['pid']) is int and row['pid'] > 0
                and row['parent_pid'] == parent['pid'] and type(row['start_ticks']) is int
                and row['start_ticks'] >= parent['start_ticks'] and row['cwd'] == str(ROOT)
                and row['executable'] == str(python.resolve())
                and all(row[key] == slot[key] for key in ('seed', 'algorithm', 'config_sha256', 'persona_cohort_sha256')),
                'observed_native_module_command_mismatch')
    return receipt


def independent_native_binding(root, manifest):
    """The actor-name correction cannot bypass the neighboring safety guards."""
    for slot in manifest['slots']:
        run = child(root, slot['relative_path'])
        require(sha(run / 'persona_cohort.json') == slot['persona_cohort_sha256']
                == sha(root / 'cohorts' / f"{slot['seed']}.json"), 'cli_paired_cohort_mismatch')
        report_path = run / 'REPORT.json'
        if report_path.exists():
            provenance = read(report_path)['provenance']
            require(provenance['actor_driver'] == ALIAS, 'unexpected_native_cli_actor_name')
            require(provenance['executor'] == EXECUTOR, 'non_native_cli_executor')
            require(provenance['persona_cohort_sha256'] == slot['persona_cohort_sha256'], 'cli_report_cohort_mismatch')
            require(all(provenance[key] == manifest[key] for key in
                        ('source_sha256', 'dependencies', 'target_model', 'model_base_url')), 'cli_report_source_or_provider_mismatch')


def audit_campaign_cli(directory, strict=False):
    root = Path(directory).resolve()
    output = {'schema_version': 1, 'kind': 'multi_seed_campaign_integrity_audit', 'status': 'invalid',
              'ok': False, 'errors': [], 'notes': [], 'runs': [], 'accounting_verified': False,
              'model_quality_score': None}
    try:
        frozen = isolated_auditor(False)
        manifest = frozen['campaign_check'](root)
        receipt = launch_check(root, manifest)
        original = frozen['audit_campaign'](root, strict=strict)
        output['frozen_audit'] = original
        saved_path = root / 'AUDIT.json'
        saved = read(saved_path) if saved_path.exists() else None
        output['correction'] = {'schema_version': 1, 'scope': 'Known native CLI module alias only',
            'campaign_sha256': CAMPAIGN_SHA256, 'launch_receipts_sha256': LAUNCH_RECEIPTS_SHA256,
            'frozen_auditor_sha256': FROZEN_AUDITOR_SHA256, 'corrected_auditor_sha256': sha(__file__),
            'published_commit': PUBLISHED_COMMIT, 'observed_actor_driver': ALIAS,
            'resolved_actor_driver': CANONICAL, 'observation_kind': receipt['observation_kind'],
            'observed_at': receipt['observed_at'], 'matched_ast_guards': 1,
            'original_saved_audit_sha256': sha(saved_path) if saved is not None else None,
            'original_saved_audit_status': saved.get('status') if saved is not None else None,
            'frozen_sources_changed': False, 'raw_reports_rewritten': False}
        independent_native_binding(root, manifest)
        corrected = isolated_auditor(True)['audit_campaign'](root, strict=strict)
        output.update(corrected)
        output['notes'].append('This additive audit resolves the frozen launcher\'s __main__.NativeActors alias only. The original audit result is retained; raw reports and all other validation rules are unchanged.')
    except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
        output['status'], output['ok'] = 'invalid', False
        output['errors'].append({'location': 'native_cli_alias_binding',
                                'code': str(exc) if type(exc) is ValueError else type(exc).__name__})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path); parser.add_argument('--strict', action='store_true')
    args = parser.parse_args(); result = audit_campaign_cli(args.run, args.strict)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
