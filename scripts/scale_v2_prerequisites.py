"""Read-only, source-bound native evidence checks before six-world dispatch.

These component and timing observations do not guarantee study completion.
They bind the reviewed inputs used to choose a prospective launch policy.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from lifespan.actor_contract import provenance
from scripts.audit_hermes_readback_v2 import audit as employee_audit
from scripts.scale_v2_contract import ACTOR_CONTRACT, EVIDENCE_KINDS, read, require, same, sha


ACTOR_AUDIT_CODE = r'''
import json, sys
from pathlib import Path
source, directory = map(Path, sys.argv[1:])
sys.path.insert(0, str(source))
from scripts import preflight_actor_contract as pre
manifest = pre.read(directory / 'manifest.json')
summary = pre.read(directory / 'SUMMARY.json')
assert pre.sources() == manifest['source_sha256']
assert pre.dependency_provenance() == manifest['dependencies']
assert pre.evidence_inventory(directory) == pre.read(directory / 'EVIDENCE.json')
assert pre.sha(directory / 'EVIDENCE.json') == summary['evidence_inventory_sha256']
assert pre.sha(directory / 'manifest.json') == summary['manifest_sha256']
wire = pre.audit_interviews(directory, manifest, pre.participants(), completed=True)
assert wire == summary['actor_interviews']
ledger = pre.read(directory / 'actors/evaluation_interview_ledger.json')['requests']
for role in pre.ROLES:
    rows = [row for row in ledger if row['actor'] == 'preflight-' + role]
    assert rows
    final = pre.read(directory / 'actors/mirofish_interviews' / (rows[-1]['key'] + '.json'))
    assert json.loads(final['response']) == pre.expected(role)
assert summary['status'] == 'completed' and summary['worker_exit_code'] == 0
assert summary['roles'] == [{'role': role, 'exact_fixture_match': True} for role in pre.ROLES]
assert summary['worker_cleanup'] == {'status': 'exited', 'exit_code': 0}
assert summary['server_cleanup'] == {'status': 'exited', 'exit_code': 0}
assert summary['actor_cleanup']['status'] == 'closed'
assert summary['native_process_cleanup']['status'] == 'exited'
assert 0 <= summary['elapsed_seconds'] <= manifest['limits']['wall_seconds'] + manifest['limits']['cleanup_seconds']
print(json.dumps({'verified': True, 'actor_interviews': wire,
    'manifest_sha256': pre.sha(directory / 'manifest.json'),
    'summary_sha256': pre.sha(directory / 'SUMMARY.json'),
    'evidence_inventory_sha256': pre.sha(directory / 'EVIDENCE.json')}))
'''


def reviewed_reference(campaign, kind, artifact, review):
    rows = [row for row in campaign['launch_policy']['evidence'] if row['kind'] == kind]
    require(len(rows) == 1 and sha(artifact) == rows[0]['artifact_sha256'] and
            sha(review) == rows[0]['review_sha256'], 'prerequisite_reviewed_reference_mismatch')
    return dict(rows[0])


def actor_check(campaign, *, directory, source_root, review_file):
    directory, source_root = Path(directory).resolve(), Path(source_root).resolve()
    reference = reviewed_reference(campaign, 'actor_native_capability', directory / 'SUMMARY.json', review_file)
    summary = read(directory / 'SUMMARY.json')
    # Establish trust in the historical manifest and source before importing
    # its auditor. The reviewed summary commits both raw inventories.
    require(sha(directory / 'manifest.json') == summary['manifest_sha256'] and
            sha(directory / 'EVIDENCE.json') == summary['evidence_inventory_sha256'],
            'actor_reviewed_manifest_or_inventory_changed')
    manifest = read(directory / 'manifest.json')
    require(manifest['kind'] == 'native_actor_wire_capability_preflight', 'actor_preflight_kind')
    require(manifest['actor_output_contract_provenance'] == provenance(ACTOR_CONTRACT),
            'actor_preflight_transport_descriptor_changed')
    require(manifest['dependencies'] == campaign['dependencies'] and
            (manifest['target_model'], manifest['model_base_url']) ==
            (campaign['target_model'], campaign['model_base_url']), 'actor_preflight_dependency_or_provider_changed')
    # Audit the historical native observation at its own exact source revision.
    # Do not rewrite its broad client source hashes to claim it ran newer code.
    require(all(not Path(name).is_absolute() and '..' not in Path(name).parts and
                (source_root / name).resolve().is_relative_to(source_root) and
                sha(source_root / name) == value for name, value in manifest['source_sha256'].items()),
            'actor_preflight_source_unavailable_or_changed')
    require('scripts/preflight_actor_contract.py' in manifest['source_sha256'], 'actor_preflight_auditor_unbound')
    try:
        process = subprocess.run([sys.executable, '-I', '-B', '-c', ACTOR_AUDIT_CODE, str(source_root), str(directory)],
            cwd=source_root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30, check=True)
        result = json.loads(process.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError('actor_preflight_raw_audit_failed') from None
    require(result.get('verified') is True and result['summary_sha256'] == reference['artifact_sha256'],
            'actor_preflight_raw_audit_binding')
    return {'reference': reference, **result,
        'compatibility_scope': 'unchanged_actor_wire_descriptor_and_installed_dependencies; '
                               'historical_client_evidence_audited_at_its_original_source; '
                               'new_client_routing_requires_current_source_and_per_world_binding'}


def employee_check(campaign, *, original_directory, observation_directory, review_file):
    original, observation = Path(original_directory).resolve(), Path(observation_directory).resolve()
    reference = reviewed_reference(campaign, 'employee_native_capability', observation / 'AUDIT.json', review_file)
    saved = read(observation / 'AUDIT.json'); manifest = read(original / 'manifest.json')
    review = read(review_file)
    require(review['private_corrected_audit_sha256'] == reference['artifact_sha256'] and
            review['manifest_sha256'] == sha(original / 'manifest.json') and
            review['private_original_inventory_sha256'] == sha(observation / 'original_inventory.json'),
            'employee_reviewed_manifest_or_inventory_changed')
    require((manifest['target_model'], manifest['model_base_url']) ==
            (campaign['target_model'], campaign['model_base_url']), 'employee_preflight_provider_changed')
    actual = employee_audit(original, manifest_sha256=saved['manifest_sha256'])
    require(same(actual, saved) and actual['ok'] is True and actual['capability_pass'] is True,
            'employee_preflight_corrected_audit_changed_or_failed')
    # This also binds the current integrated client/library source to the
    # reviewed native employee preflight. The actor wire descriptor is checked
    # separately; a component pass is not proof of a full new world lifecycle.
    require(all(campaign['source_sha256'].get(name) == value for name, value in
                manifest['source_sha256'].items() if name.startswith('lifespan/')),
            'current_library_differs_from_native_employee_preflight')
    inventory = read(observation / 'original_inventory.json')
    actual_paths = list(original.rglob('*'))
    require(not any(path.is_symlink() for path in actual_paths) and
            {str(path.relative_to(original)) for path in actual_paths if path.is_file()} == set(inventory['files']) and
            len(inventory['files']) == review['original_regular_files_hashed'],
            'employee_preflight_original_inventory_not_exact')
    require(all(not Path(name).is_absolute() and '..' not in Path(name).parts and
                (original / name).resolve().is_relative_to(original) and sha(original / name) == value
                for name, value in inventory['files'].items()), 'employee_preflight_original_evidence_changed')
    return {'reference': reference, 'verified': True, 'capability_pass': True,
            'original_manifest_sha256': saved['manifest_sha256'],
            'original_capability_pass': saved['original_report_capability_pass'],
            'correction_source_sha256': saved['correction_source_sha256'],
            'physical_model_calls': saved['usage']['physical_model_calls'],
            'measured_tokens': saved['usage']['total_tokens'], 'elapsed_seconds': saved['elapsed_seconds']}


def horizon_check(campaign, *, directory, review_file):
    from scripts.scale_horizon_observations import verify_snapshot
    directory = Path(directory).resolve()
    reference = reviewed_reference(campaign, 'horizon_feasibility', directory / 'REPORT.json', review_file)
    report = read(directory / 'REPORT.json')
    verified = verify_snapshot(directory, expected_report_sha256=reference['artifact_sha256'],
        expected_capture_sha256=report['provenance']['capture_sha256'])
    require(verified['ok'] is True and verified['summary_reproduced'] is True and
            verified['world_slots'] == 6, 'horizon_raw_snapshot_invalid')
    require(report['forecast_seconds'] is None and report['nonstreaming_long_horizon_claim'] is False,
            'horizon_observation_scope_changed')
    return {'reference': reference, 'verified': True, 'raw_snapshot': verified,
            'scope': 'observed_streaming_development_durations; no_nonstreaming_completion_forecast'}


def verify_prerequisites(campaign, paths):
    """Reproduce the exact gate from private paths without native execution."""
    expected = {'actor': {'directory', 'source_root', 'review_file'},
                'employee': {'original_directory', 'observation_directory', 'review_file'},
                'horizon': {'directory', 'review_file'}}
    require(type(paths) is dict and set(paths) == set(expected), 'prerequisite_path_inventory')
    for kind, fields in expected.items():
        require(type(paths[kind]) is dict and set(paths[kind]) == fields and all(
            type(value) is str and Path(value).is_absolute() for value in paths[kind].values()),
            'prerequisite_explicit_absolute_paths_required')
    checks = [actor_check(campaign, **paths['actor']), employee_check(campaign, **paths['employee']),
              horizon_check(campaign, **paths['horizon'])]
    require(all(check.get('verified') is True for check in checks), 'native_prerequisites_not_verified')
    return {'schema_version': 1, 'verified': True, 'checks': checks}
