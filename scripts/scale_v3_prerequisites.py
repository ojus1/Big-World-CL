"""V3 gates: exact reviewed native capability and fresh startup.

Historical provider observations are never relabeled as current-source native
runs. An exact source review and the current native startup qualification are
separate prerequisites; no failed prefix or missing usage becomes a pass.
Explicit provider profiles instead require fresh actor, employee and optimizer
receipts from the current source and provider, with no compatibility shortcut.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from scripts.scale_v2_prerequisites import (actor_check, horizon_check, reviewed_reference,
    read, require, same, sha)

CHANGED_LIBRARY_FILES = {
    'lifespan/computers.py', 'lifespan/evaluation/protocol.py',
    'lifespan/evaluation/runner.py', 'lifespan/evaluation/runtime.py',
    'lifespan/hermes_worker.py', 'lifespan/startup_observability.py'}
ROOT = Path(__file__).resolve().parents[1]


EMPLOYEE_AUDIT_CODE = r'''
import hashlib, importlib.util, json, sys, types
from pathlib import Path
historical, correction, directory = map(Path, sys.argv[1:4])
manifest_hash, correction_hash = sys.argv[4:6]
assert hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest() == manifest_hash
assert hashlib.sha256(correction.read_bytes()).hexdigest() == correction_hash
sources = json.loads((directory / 'manifest.json').read_bytes())['source_sha256']
# Read source rather than an unbound pre-existing bytecode cache, and -B keeps
# this nonexistent cache path absent throughout the read-only audit.
sys.pycache_prefix = str(directory / '.readonly-audit-no-bytecode')
assert not Path(sys.pycache_prefix).exists()
sys.path.insert(0, str(historical))
# scripts is a namespace package. Pin its search path before the unchanged
# correction module prepends its own checkout to sys.path. All nested original
# auditor/launcher imports must continue to use the historical package.
scripts = types.ModuleType('scripts')
scripts.__path__ = [str(historical / 'scripts')]
scripts.__package__ = 'scripts'
sys.modules['scripts'] = scripts
class HistoricalSources:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in ('lifespan', 'scripts'):
            return None
        base = fullname.replace('.', '/')
        candidates = [name for name in (base + '.py', base + '/__init__.py') if name in sources]
        if len(candidates) != 1:
            raise ImportError('unbound_historical_python_module')
        name = candidates[0]
        source = historical / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != sources[name]:
            raise ImportError('historical_python_source_changed')
        options = {'submodule_search_locations': [str(source.parent)]} if name.endswith('/__init__.py') else {}
        return importlib.util.spec_from_file_location(fullname, source, **options)
sys.meta_path.insert(0, HistoricalSources())
import lifespan
assert Path(lifespan.__file__).resolve() == historical / 'lifespan/__init__.py'
assert list(lifespan.__path__) == [str(historical / 'lifespan')]
spec = importlib.util.spec_from_file_location('_reviewed_employee_readback', correction)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.audit(directory, manifest_sha256=manifest_hash)
print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
'''


def _historical_employee_audit(original, saved):
    """Run exact reviewed correction bytes with the original source imports.

    The caller first binds the manifest and complete raw inventory to the
    reviewed observation. Nothing is copied into or changed in that checkout.
    This is a historical audit, never a new native/provider invocation.
    """
    manifest = read(original / 'manifest.json')
    correction = Path(__file__).with_name('audit_hermes_readback_v2.py')
    require(type(saved.get('correction_source_sha256')) is str and
        re.fullmatch('[0-9a-f]{64}', saved['correction_source_sha256']) and
        not correction.is_symlink() and sha(correction) == saved['correction_source_sha256'],
        'employee_reviewed_correction_source_changed')
    require(manifest.get('source_commit_verified') is True and
        type(manifest.get('repository_commit')) is str and
        re.fullmatch('[0-9a-f]{40}', manifest['repository_commit']),
        'employee_historical_commit_unbound')
    sources = manifest.get('source_sha256')
    require(type(sources) is dict and bool(sources) and
        {'lifespan/__init__.py', 'scripts/audit_hermes_preflight.py',
         'scripts/hermes_transport_preflight.py'} <= set(sources),
        'employee_historical_auditor_unbound')
    try:
        historical = Path(subprocess.check_output(['git', '-C', str(original),
            'rev-parse', '--show-toplevel'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()).resolve()
        require(original.is_relative_to(historical) and
            not (historical / 'scripts/__init__.py').exists() and
            not (historical / 'scripts/__init__.py').is_symlink(), 'employee_historical_package_changed')
        for name, expected in sources.items():
            require(type(name) is str, 'employee_historical_source_path')
            path = Path(name)
            require(not path.is_absolute() and '..' not in path.parts and bool(path.parts) and
                path.parts[0] in ('scripts', 'lifespan') and path.suffix == '.py' and
                type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected),
                'employee_historical_source_path')
            actual = historical / path
            require(not any(p.is_symlink() for p in (actual, *actual.parents) if p != historical.parent)
                and actual.resolve().is_relative_to(historical) and sha(actual) == expected,
                'employee_historical_source_unavailable_or_changed')
            if path.name != '__init__.py':
                shadow = actual.with_suffix('') / '__init__.py'
                require(not shadow.exists() and not shadow.is_symlink(), 'employee_historical_module_shadow')
            committed = subprocess.check_output(['git', '-C', str(historical), 'show',
                manifest['repository_commit'] + ':' + name], stderr=subprocess.DEVNULL, timeout=10)
            require(hashlib.sha256(committed).hexdigest() == expected, 'employee_historical_committed_source_changed')
        process = subprocess.run([sys.executable, '-I', '-B', '-c', EMPLOYEE_AUDIT_CODE,
            str(historical), str(correction), str(original), saved['manifest_sha256'],
            saved['correction_source_sha256']], cwd=historical, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=True)
        require(len(process.stdout) <= 2_000_000, 'employee_historical_audit_output_too_large')
        result = json.loads(process.stdout)
        require(type(result) is dict, 'employee_historical_audit_output_shape')
        require(all(sha(historical / name) == expected for name, expected in sources.items()) and
            sha(correction) == saved['correction_source_sha256'], 'employee_historical_source_changed_during_audit')
        return result
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        raise ValueError('employee_historical_raw_audit_failed') from None


def compatibility_check(campaign, *, artifact_file, review_file, original_directory):
    reference = reviewed_reference(campaign, 'employee_source_compatibility', artifact_file, review_file)
    artifact, review = read(artifact_file), read(review_file)
    historical = Path(original_directory) / 'manifest.json'
    require(artifact['schema_version'] == 1 and artifact['kind'] == 'employee-startup-source-compatibility'
        and artifact['historical_manifest_sha256'] == sha(historical), 'source_compatibility_history_mismatch')
    old = {k:v for k,v in read(historical)['source_sha256'].items() if k.startswith('lifespan/')}
    current = {k:v for k,v in campaign['source_sha256'].items() if k.startswith('lifespan/')}
    require(artifact['historical_library_sha256'] == old and artifact['current_library_sha256'] == current,
            'source_compatibility_library_changed')
    changed = {k for k in set(old)|set(current) if old.get(k) != current.get(k)}
    require(changed == CHANGED_LIBRARY_FILES and set(artifact['changes']) == changed,
            'unreviewed_employee_library_change')
    for name in changed:
        require(artifact['changes'][name]['before_sha256'] == old.get(name)
            and artifact['changes'][name]['after_sha256'] == current.get(name), 'source_compatibility_delta_changed')
    require(review['artifact_sha256'] == reference['artifact_sha256']
        and review['decision'] == 'compatible_for_prospective_evaluation'
        and review['new_native_provider_observation'] is False
        and review['reviewed_source_changes'] == sorted(changed), 'source_compatibility_review_missing')
    return {'verified': True, 'reference': reference,
        'historical_manifest_sha256': sha(historical), 'changed_files': sorted(changed),
        'scope': 'source_compatibility_review_not_a_new_provider_observation'}


def startup_check(campaign, *, directory, review_file):
    from scripts.hermes_startup_scope_qualification_v3 import audit_qualification
    directory = Path(directory)
    reference = reviewed_reference(campaign, 'scope_startup_qualification', directory / 'REPORT.json', review_file)
    manifest = read(directory / 'manifest.json'); review = read(review_file)
    manifest_sha = sha(directory / 'manifest.json')
    if 'provider_contract' in campaign:
        from lifespan.evaluation.provider import validate_contract, provider_contract
        from scripts.hermes_startup_probe import CREDENTIALS
        policy = validate_contract(campaign['provider_contract'])
        require(manifest.get('startup_configuration') == {'model': policy['model'], 'provider_profile': policy['profile']}
            and same(manifest['child_execution'].get('provider_contract'),
                     provider_contract(policy['model'], CREDENTIALS['base_url'], policy['profile'])),
            'startup_provider_configuration_mismatch')
    else:
        require('startup_configuration' not in manifest and
                'provider_contract' not in manifest.get('child_execution', {}), 'startup_provider_configuration_unexpected')
    require(review['manifest_sha256'] == manifest_sha
        and review['report_sha256'] == reference['artifact_sha256']
        and review['qualification_passed'] is True, 'startup_qualification_review_mismatch')
    actual = audit_qualification(directory, manifest_sha256=review['manifest_sha256'], strict=True)
    require(actual['ok'] is True and actual['qualification_passed'] is True
        and actual['status'] == 'completed' and len(actual['slots']) == 9
        and all(row['qualification_passed'] is True for row in actual['slots']), 'startup_qualification_not_complete')
    combined = {**campaign['source_sha256'], **campaign['registration_tools_sha256']}
    require(all(combined.get(k) == v for k,v in manifest['source_sha256'].items()),
            'current_sources_differ_from_qualified_startup')
    require(manifest['dependencies']['hermes']['revision'] == campaign['dependencies']['hermes']['revision'],
            'qualified_hermes_revision_changed')
    require(sha(directory / 'manifest.json') == manifest_sha and
        sha(directory / 'REPORT.json') == reference['artifact_sha256'] and
        sha(review_file) == reference['review_sha256'], 'startup_evidence_changed_during_audit')
    if 'provider_contract' in campaign:
        _fresh_sources(campaign, manifest, require_all_execution=False)
    return {'verified': True, 'reference': reference, 'planned_slots': 9, 'qualified_slots': 9,
        'manifest_sha256': manifest_sha, 'boot_id': manifest['boot_id'],
        'caller_security_context': manifest['caller_security_context'],
        'scope': 'startup_component_only_not_provider_or_long_horizon_reliability'}


def employee_check(campaign, *, original_directory, observation_directory, review_file, compatibility):
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
    require(compatibility['historical_manifest_sha256'] == saved['manifest_sha256']
            and compatibility['verified'] is True, 'employee_compatibility_manifest_mismatch')
    inventory = read(observation / 'original_inventory.json')
    actual_paths = list(original.rglob('*'))
    require(not any(path.is_symlink() for path in actual_paths) and
            {str(path.relative_to(original)) for path in actual_paths if path.is_file()} == set(inventory['files']) and
            len(inventory['files']) == review['original_regular_files_hashed'],
            'employee_preflight_original_inventory_not_exact')
    require(all(not Path(name).is_absolute() and '..' not in Path(name).parts and
                (original / name).resolve().is_relative_to(original) and sha(original / name) == value
                for name, value in inventory['files'].items()), 'employee_preflight_original_evidence_changed')
    actual = _historical_employee_audit(original, saved)
    require(same(actual, saved) and actual['ok'] is True and actual['capability_pass'] is True,
            'employee_preflight_corrected_audit_changed_or_failed')
    final_paths = list(original.rglob('*'))
    require(not any(path.is_symlink() for path in final_paths) and
        {str(path.relative_to(original)) for path in final_paths if path.is_file()} == set(inventory['files']) and
        all(sha(original / name) == value for name, value in inventory['files'].items()),
        'employee_preflight_original_evidence_changed_during_audit')
    require(sha(observation / 'AUDIT.json') == reference['artifact_sha256'] and
        sha(review_file) == reference['review_sha256'] and
        sha(observation / 'original_inventory.json') == review['private_original_inventory_sha256'],
        'employee_reviewed_observation_changed_during_audit')
    return {'reference': reference, 'verified': True, 'capability_pass': True,
            'original_manifest_sha256': saved['manifest_sha256'],
            'original_capability_pass': saved['original_report_capability_pass'],
            'correction_source_sha256': saved['correction_source_sha256'],
            'compatibility_scope': 'historical_provider_capability_plus_explicit_current_source_review_and_fresh_startup_qualification',
            'physical_model_calls': saved['usage']['physical_model_calls'],
            'measured_tokens': saved['usage']['total_tokens'], 'elapsed_seconds': saved['elapsed_seconds']}


def _fresh_sources(campaign, manifest, *, require_all_execution=True):
    declared = manifest.get('source_sha256')
    combined = {**campaign['source_sha256'], **campaign['registration_tools_sha256']}
    require(type(declared) is dict and bool(declared) and (not require_all_execution or
        all(declared.get(k) == v for k, v in campaign['source_sha256'].items())),
        'fresh_preflight_missing_current_execution_sources')
    for name, expected in declared.items():
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts
            and type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected)
            and combined.get(name) == expected, 'fresh_preflight_source_not_registered')
        path = ROOT / name
        require(path.resolve().is_relative_to(ROOT.resolve()) and
            not any(p.is_symlink() for p in (path, *path.parents) if p != ROOT.parent)
            and sha(path) == expected, 'fresh_preflight_source_changed')


def _fresh_context(campaign, directory, review_file, kind, artifact_name):
    from lifespan.evaluation.provider import validate_contract, provider_contract
    directory = Path(directory).resolve()
    reference = reviewed_reference(campaign, kind, directory / artifact_name, review_file)
    manifest_sha = sha(directory / 'manifest.json')
    manifest, review = read(directory / 'manifest.json'), read(review_file)
    policy = validate_contract(campaign.get('provider_contract'))
    require(campaign['launch_policy'].get('provider_profile') == policy['profile'] and
        same(policy, provider_contract(campaign['target_model'], campaign['model_base_url'], policy['profile'])),
        'fresh_campaign_provider_binding')
    require(same(validate_contract(manifest.get('provider_contract')), policy) and
        (manifest.get('target_model'), manifest.get('model_base_url')) ==
        (campaign['target_model'], campaign['model_base_url']), 'fresh_preflight_provider_changed')
    require(review.get('manifest_sha256') == manifest_sha and
        review.get('artifact_sha256') == reference['artifact_sha256'] and
        review.get('decision') == 'approved_for_prospective_evaluation', 'fresh_preflight_review_mismatch')
    _fresh_sources(campaign, manifest)
    return directory, manifest, manifest_sha, reference


def _fresh_finish(campaign, directory, manifest, manifest_sha, reference, artifact_name, review_file):
    require(sha(directory / 'manifest.json') == manifest_sha and
        sha(directory / artifact_name) == reference['artifact_sha256'] and
        sha(review_file) == reference['review_sha256'], 'fresh_preflight_changed_during_audit')
    _fresh_sources(campaign, manifest)


def fresh_actor_check(campaign, *, directory, source_root, review_file):
    from scripts import preflight_actor_contract as actor
    require(Path(source_root).resolve() == ROOT.resolve(), 'fresh_actor_requires_current_source_root')
    directory, manifest, manifest_sha, reference = _fresh_context(
        campaign, directory, review_file, 'actor_native_capability', 'SUMMARY.json')
    require(manifest.get('kind') == 'native_actor_wire_capability_preflight' and
        same(manifest.get('dependencies', {}).get('repositories'), campaign['dependencies']),
        'fresh_actor_dependency_or_kind_changed')
    actual = actor.audit(directory, manifest_sha256=manifest_sha, strict=True)
    require(actual.get('ok') is True and actual.get('verified') is True and actual.get('status') == 'completed'
        and actual.get('manifest_sha256') == manifest_sha
        and actual.get('summary_sha256') == reference['artifact_sha256']
        and actual.get('roles') == list(actor.ROLES)
        and same(actual.get('provider_contract'), campaign['provider_contract']), 'fresh_actor_raw_audit_failed')
    _fresh_finish(campaign, directory, manifest, manifest_sha, reference, 'SUMMARY.json', review_file)
    return {'verified': True, 'reference': reference, 'manifest_sha256': manifest_sha,
        'summary_sha256': actual['summary_sha256'], 'evidence_inventory_sha256': actual['evidence_inventory_sha256'],
        'actor_interviews': actual['actor_interviews'], 'qualified_roles': 4,
        'scope': 'current_provider_contracted_interviews_only; bootstrap_social_and_all_in_usage_unknown'}


def fresh_employee_check(campaign, *, directory, review_file):
    from scripts import audit_hermes_preflight as employee
    directory, manifest, manifest_sha, reference = _fresh_context(
        campaign, directory, review_file, 'employee_native_capability', 'REPORT.json')
    require(manifest.get('kind') == 'hermes-transport-capability-provider-v1' and
        manifest['dependencies']['hermes']['revision'] == campaign['dependencies']['hermes']['revision'],
        'fresh_employee_dependency_or_kind_changed')
    actual = employee.audit_preflight(directory, strict=True, expected_manifest_sha256=manifest_sha)
    require(actual.get('ok') is True and actual.get('capability_pass') is True
        and actual.get('accounting_verified') is True and actual.get('status') == 'valid_completed'
        and actual.get('manifest_sha256') == manifest_sha and actual.get('report_sha256') == reference['artifact_sha256']
        and same(actual.get('provider_contract'), campaign['provider_contract'])
        and len(actual.get('slots', [])) == 3
        and {s.get('workflow') for s in actual['slots']} == {'onboarding', 'renewal', 'incident'}
        and all(s.get('mode') == 'nonstreaming' and s.get('capability_pass') is True
                and s.get('cleanup_confirmed') is True for s in actual['slots'])
        and actual.get('usage', {}).get('complete') is True, 'fresh_employee_raw_audit_failed')
    _fresh_finish(campaign, directory, manifest, manifest_sha, reference, 'REPORT.json', review_file)
    return {'verified': True, 'reference': reference, 'manifest_sha256': manifest_sha,
        'report_sha256': actual['report_sha256'], 'qualified_slots': 3, 'usage': actual['usage'],
        'scope': 'current_provider_native_tool_file_submission_readback_component; no_learning_or_long_horizon_claim'}


def fresh_optimizer_check(campaign, *, directory, review_file):
    from scripts import preflight_optimizer as optimizer
    directory, manifest, manifest_sha, reference = _fresh_context(
        campaign, directory, review_file, 'optimizer_native_capability', 'REPORT.json')
    require(manifest.get('kind') == 'native_optimizer_provider_capability_v1' and
        same(manifest.get('dependencies'), campaign['dependencies']), 'fresh_optimizer_dependency_or_kind_changed')
    actual = optimizer.audit_preflight(directory, manifest_sha256=manifest_sha, strict=True)
    require(actual.get('ok') is True and actual.get('capability_pass') is True and actual.get('status') == 'completed'
        and actual.get('manifest_sha256') == manifest_sha
        and same(actual.get('provider_contract'), campaign['provider_contract'])
        and type(actual.get('physical_model_calls')) is int and actual['physical_model_calls'] == 1
        and actual.get('native_learning_or_adoption') is False, 'fresh_optimizer_raw_audit_failed')
    _fresh_finish(campaign, directory, manifest, manifest_sha, reference, 'REPORT.json', review_file)
    return {'verified': True, 'reference': reference, 'manifest_sha256': manifest_sha,
        'report_sha256': reference['artifact_sha256'], 'evidence_inventory_sha256': actual['evidence_inventory_sha256'],
        'physical_model_calls': 1, 'measured_tokens': actual['tokens'], 'parsed_edit_count': actual['parsed_edit_count'],
        'scope': 'current_provider_synthetic_train_reflector_transport_and_parse; no_target_or_adoption'}


def verify_prerequisites(campaign, paths):
    if 'provider_contract' in campaign or 'provider_profile' in campaign['launch_policy']:
        from scripts.scale_v3_contract import policy
        policy(campaign['launch_policy'])
        expected = {'actor': {'directory', 'source_root', 'review_file'},
            'employee': {'directory', 'review_file'}, 'optimizer': {'directory', 'review_file'},
            'horizon': {'directory', 'review_file'}, 'startup': {'directory', 'review_file'}}
        _paths(paths, expected)
        checks = [fresh_actor_check(campaign, **paths['actor']), fresh_employee_check(campaign, **paths['employee']),
            horizon_check(campaign, **paths['horizon']), startup_check(campaign, **paths['startup']),
            fresh_optimizer_check(campaign, **paths['optimizer'])]
        require(all(row['verified'] is True for row in checks), 'v3_prerequisites_not_verified')
        return {'schema_version': 3, 'verified': True, 'provider_contract': campaign['provider_contract'], 'checks': checks}
    expected = {'actor': {'directory', 'source_root', 'review_file'},
        'employee': {'original_directory', 'observation_directory', 'review_file'},
        'horizon': {'directory', 'review_file'}, 'startup': {'directory', 'review_file'},
        'compatibility': {'artifact_file', 'review_file'}}
    _paths(paths, expected)
    compatible = compatibility_check(campaign, **paths['compatibility'],
        original_directory=paths['employee']['original_directory'])
    startup = startup_check(campaign, **paths['startup'])
    checks = [actor_check(campaign, **paths['actor']),
        employee_check(campaign, **paths['employee'], compatibility=compatible),
        horizon_check(campaign, **paths['horizon']), startup, compatible]
    require(all(row['verified'] is True for row in checks), 'v3_prerequisites_not_verified')
    return {'schema_version': 3, 'verified': True, 'checks': checks}


def _paths(paths, expected):
    require(type(paths) is dict and set(paths) == set(expected), 'v3_prerequisite_path_inventory')
    for name, fields in expected.items():
        require(type(paths[name]) is dict and set(paths[name]) == fields and all(
            type(value) is str and Path(value).is_absolute() for value in paths[name].values()),
            'v3_prerequisite_absolute_paths_required')
