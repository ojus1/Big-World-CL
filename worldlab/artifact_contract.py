"""Candidate violations are scored outcomes; unexpected I/O failures are not."""
from pathlib import Path
from scripts.source_world_calibration import sha


class CandidateEvidenceError(ValueError):
    def __init__(self, path, code, message):
        super().__init__(message)
        self.violation = {'path': path, 'code': code, 'reason': message}


def input_changes(workspace, baseline):
    """Never read a baseline file through an inserted directory/file symlink."""
    workspace = Path(workspace)
    changed = []
    for name, expected in baseline.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid trusted baseline path')
        path = workspace / relative
        ancestors = [workspace.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]
        if any(p.is_symlink() for p in ancestors) or not path.is_file() or sha(path) != expected:
            changed.append(name)
    return sorted(changed)


def contract(workspace, baseline, files, *, violation=None):
    changed = input_changes(workspace, baseline)
    unauthorized = sorted(name for name in files if name not in baseline and not name.startswith('output/'))
    violations = [violation] if violation else []
    return {'policy': 'preserve_inputs_output_or_scratch_v1', 'passed': not (changed or unauthorized or violations),
            'input_changes': changed, 'unauthorized_files': unauthorized, 'evidence_violations': violations}


def feedback(record):
    if record['passed']:
        return 'Artifact contract: satisfied.'
    reasons = []
    if record['input_changes']:
        reasons.append('Restore unchanged original inputs: ' + ', '.join(record['input_changes']))
    if record['unauthorized_files']:
        reasons.append('Move helper files into scratch/; deliverables belong in output/: ' + ', '.join(record['unauthorized_files']))
    reasons += [v['path'] + ': ' + v['reason'] for v in record['evidence_violations']]
    return 'Artifact contract failed; submission score is zero. ' + '; '.join(reasons) + '.'


def rejected_grade(record, rubric_sha256, evidence_sha256):
    return {'status': 'completed', 'grading_complete': True, 'quality_score': 0.0, 'success': False,
            'criteria': [], 'error_type': None, 'evaluation_method': 'invalid_candidate_artifact',
            'usage': {'physical_model_calls': 0, 'charged_tokens': 0, 'accounting_complete': True, 'operations': []},
            'format_recoveries': [], 'public_requirements': None, 'rubric_sha256': rubric_sha256,
            'artifact_contract': record, 'evidence_sha256': evidence_sha256,
            'input_changes': record['input_changes'], 'unauthorized_files': record['unauthorized_files'],
            'feedback': feedback(record),
            'scope': 'Candidate artifact-contract failure. Semantic criteria were not judged; no model calls were made.'}
