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
    'jobbench/technical_writers/task1': {
        'instruction_sha256': '0efcdbd427be6728a11cee7b47bc56d63b33eea053f49ed7567e2399d49a1364',
        'input_formats': ['.csv', '.json', '.md', '.txt'],
        'output_formats': ['.md'],
        'required_references': ['swagger_markdown_example'],
        'research': 'The named azagniotov Markdown API example is required as an external formatting reference.',
        'evidence': 'Four Markdown documents; original task facts and API constraints remain binding.',
    },
    'jobbench/technical_writers/task2': {
        'instruction_sha256': '7d60c0377b8c1f922c8e7292d85241cfcd44f76c9c1e2dc1ede219bd08684b42',
        'input_formats': ['.csv', '.json', '.md', '.txt', '.yaml'],
        'output_formats': ['.csv', '.md'],
        'required_references': ['google_style_highlights', 'microsoft_reference_guidelines'],
        'research': 'Both named documentation style-guide pages must be available for consultation.',
        'evidence': 'Complete Markdown migration/reference documents and CSV impact analysis.',
    },
    'jobbench/technical_writers/task3': {
        'instruction_sha256': 'f6088d1667e9e71c4b91dd36c16534421314abd2889274c0e4414d23037b47e1',
        'input_formats': ['.csv', '.json', '.md', '.txt', '.yaml'],
        'output_formats': ['.csv', '.md', '.html'],
        'research': 'Consult public API guidelines as needed; mandatory task-specific facts are supplied locally.',
        'evidence': 'Complete reconciliation, style guide, API reference, webhook catalog and migration guide. The source-required 1500-word minimum is preserved.',
    },
}


def unsupported(public, *, available_references=(), evidence_only=False):
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
    missing = set(review.get('required_references', [])) - set(available_references)
    if missing and not evidence_only:
        reasons.append('Required external references unavailable: ' + ', '.join(sorted(missing)))
    return reasons


class ReviewedOfflineHermes(Hermes):
    """The native Hermes execution path, with explicit additional task eligibility."""
    def identity(self):
        return {**super().identity(), 'name': 'native_hermes_reviewed_offline_tasks',
                'capability_review_sha256': sha(Path(__file__)),
                'jobbench_dataset_revision': DATASET_REVISION,
                'jobbench_reviewed_tasks': sorted(k for k,v in REVIEWED.items() if not v.get('required_references')),
                'jobbench_scope': 'Static source eligibility; native qualification is recorded separately'}

    def unsupported(self, public):
        if public.get('source') == 'jobbench':
            return unsupported(public)
        return super().unsupported(public)
