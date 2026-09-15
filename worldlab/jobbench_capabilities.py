"""Source-reviewed capabilities, independent of private rubric answers.

Register exact public tasks only after reviewing their complete requirements.
Input suffixes alone cannot establish research, app or output-tool requirements.
Native qualification receipts are separate from these static eligibility reviews.
"""
import hashlib
from pathlib import Path
from scripts.source_world_calibration import sha
from .hermes import Hermes

DATASET_REVISION = '7ff2673ac78f42e492b204f5fffe0b8ccc11bf7d'
REVIEWED = {
    'jobbench/web_administrators/task1': {
        'instruction_sha256': 'd95f32d725bdcda152d5ab1e8c3d6849b088224476e53ec1f33bd6057b7ff091',
        'input_formats': ['.conf', '.csv', '.html', '.json', '.rules', '.txt'],
        'output_formats': ['.conf', '.csv', '.html', '.rules'],
        'research': 'The wordpress-nginx reference may be useful; it is optional. Required incident facts are supplied locally.',
        'execution': 'Produce replacement configuration files; do not apply them to real services.',
        'evidence': 'CSV records, configuration semantics and populated HTML report tables; no visual appearance criterion.',
    },
}


def unsupported(public):
    review = REVIEWED.get(public.get('id'))
    if public.get('source') != 'jobbench' or review is None:
        return ['JobBench task requires a source review of research, execution and complete evidence capabilities']
    reasons = []
    if hashlib.sha256(public['instruction'].encode()).hexdigest() != review['instruction_sha256']:
        reasons.append('Reviewed JobBench instruction bytes changed')
    if sorted(public['input_formats']) != review['input_formats']:
        reasons.append('Reviewed JobBench input formats changed')
    if public.get('requires_app_state') or public.get('budgets', {}).get('user_turns', 0):
        reasons.append('Reviewed offline JobBench task cannot require app state or employee interaction')
    return reasons


class ReviewedOfflineHermes(Hermes):
    """The native Hermes execution path, with explicit additional task eligibility."""
    def identity(self):
        return {**super().identity(), 'name': 'native_hermes_reviewed_offline_tasks',
                'capability_review_sha256': sha(Path(__file__)),
                'jobbench_dataset_revision': DATASET_REVISION,
                'jobbench_reviewed_tasks': sorted(REVIEWED),
                'jobbench_scope': 'Static source eligibility; native qualification is recorded separately'}

    def unsupported(self, public):
        if public.get('source') == 'jobbench':
            return unsupported(public)
        return super().unsupported(public)
