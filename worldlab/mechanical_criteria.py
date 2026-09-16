"""Narrow executable predicates for exactly registered frozen rubric criteria.

Unknown or changed criteria always return None and retain ordinary judging.
These are narrow source checks, not a model judgment or general semantic oracle.
"""
import hashlib
import html
import re
from .supplier_notes import veto as supplier_note_veto, check as supplier_note_check, source_matrix_verdict
from .memo_counts import verdict as memo_count_verdict
from .source_coverage import count_verdict as restored_count_verdict

SOURCE = 'input/manual_v23_section4.md'
OUTPUT = 'output/texte_restructure_v3.md'
CRITERION = {
    'acceptable_alternatives': ['Case variation (Fig./fig./Figure) is acceptable if count is exactly 3.'],
    'evidence_anchors': ['input/guide_style_v2.md', 'input/index_renvoyes.csv', 'input/liste_figures_v3.csv',
                         SOURCE, 'input/note_edition.md', 'output/arbitrages_terminologiques.csv', OUTPUT],
    'failure_examples': [], 'id': 'fig54_exact_count',
    'requirement': "Exactly 3 occurrences of 'Fig. 5.4' (or 'figure 5.4') in the restructured text, corresponding to the 3 original Fig. 4.7 references.",
    'weight': 2,
}

HEADING_OUTPUT = 'output/synthese_avantages.md'
HEADING_INSTRUCTION_SHA256 = '29c6acfd0cf8514d9fb44e86649088b2888c41cf32393c954dae00e286f5f14f'
# Text hashes use the same universal-newline projection as Path.read_text.
# The calibration bank separately binds the original file bytes.
HEADING_SOURCES = {
    'input/fiche_avantages.csv': 'a64445de81aab8c6de2519d8314cfa998199c040e87bef14b77912bdbafdf05d',
    'input/notes_reunion.md': 'a21318a63d10eaca3cf3e46b9f4d170d04ffc9797c9d85e7602d7eedcfe34e70',
    'input/reglement_interne.md': 'e7b3eb19d6124852be5b1c60c9bcfefe37aef5660937baa1c9a73a47189ecfe1',
}
HEADING_CRITERION = {
    'acceptable_alternatives': ['Source-faithful paraphrasing is acceptable; the required headings remain literal even where they differ from the prose language.'],
    'evidence_anchors': [*HEADING_SOURCES, HEADING_OUTPUT, 'output/annexe_faits.json'],
    'failure_examples': ['A bullet dump without explanatory synthesis, missing a topical section, or replacing the explicitly instructed headings ## Fiscal, ## Administrative, ## Network.'],
    'id': 'Q01',
    'requirement': 'The two required deliverables are output/synthese_avantages.md and output/annexe_faits.json. The synthesis is coherent English prose with three exact section headings ## Fiscal, ## Administrative, ## Network, organizing the source benefits appropriately into fiscal, administrative and network topics.',
    'weight': 1,
}


# Source-reviewed exact deliverable set; only violations are decided here.
DELIVERABLE_CRITERION = {'acceptable_alternatives': ['A different greeting, closing or prose structure is acceptable.',
                             '5×4 is the retained pouch arrangement, not a stale 4-shelf value.'],
 'evidence_anchors': ['output/coordination_final.md', 'output/appendix_facts.json'],
 'failure_examples': ['A change log replaces the revised letter or an unchanged subject still requests four '
                      'shelves.'],
 'id': 'Q04',
 'requirement': 'Exactly output/coordination_final.md and output/appendix_facts.json are supplied; the '
                'Markdown is a coherent revised coordination letter in French that retains the request to '
                'WOW Display and avoids stale draft values throughout, including any subject line, without '
                'introducing unsupported commercial commitments.',
 'weight': 1}
DELIVERABLE_INSTRUCTION_SHA256 = 'ed9e515d23796e0777ad96c929ed107b2ea84f638738851a431bfdff71fc7865'
DELIVERABLE_SOURCES = {'input/draft_coordination.md': 'd15ed59cce9e53aa906c264e3f4683ef38ed2cfdefd810a4bd0d209f9ef79843',
 'input/revision_notes.md': '4b4c6036d60af53da9057332008898e0df5c2997624208dd67c295635246f977',
 'input/spec_display.csv': '3792709909bd72b3d944da053aa1822e5db18d37eb1140d33d804e8b36fcc22c'}
DELIVERABLE_OUTPUTS = {'output/coordination_final.md', 'output/appendix_facts.json'}


def deliverable_set_veto(payload):
    evidence = payload.get('evidence', {})
    instruction = evidence.get('instruction')
    if (payload.get('criterion') != DELIVERABLE_CRITERION or not isinstance(instruction, str)
            or hashlib.sha256(instruction.encode()).hexdigest() != DELIVERABLE_INSTRUCTION_SHA256):
        return None
    files = evidence.get('files', {})
    for name, expected in DELIVERABLE_SOURCES.items():
        text = files.get(name, {}).get('text')
        if not isinstance(text, str):
            return None
        if hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest() != expected:
            return None
    actual = {name for name in files if name.startswith('output/')}
    if actual == DELIVERABLE_OUTPUTS:
        return None
    return {'criterion_id': DELIVERABLE_CRITERION['id'], 'passed': False,
            'evidence': 'Output file inventory: ' + ', '.join(sorted(actual)) +
                        '; missing: ' + ', '.join(sorted(DELIVERABLE_OUTPUTS - actual)) +
                        '; extra: ' + ', '.join(sorted(actual - DELIVERABLE_OUTPUTS)) + '.',
            'reasoning': 'The reviewed public instruction and Q04 require exactly the two named deliverables. '
                         'The actual file set violates that condition. Letter quality still needs judgment '
                         'when the file set matches.'}


def missing_heading_veto(payload):
    evidence = payload.get('evidence', {})
    instruction = evidence.get('instruction')
    if (payload.get('criterion') != HEADING_CRITERION or not isinstance(instruction, str)
            or hashlib.sha256(instruction.encode()).hexdigest() != HEADING_INSTRUCTION_SHA256):
        return None
    files = evidence.get('files', {})
    for name, expected in HEADING_SOURCES.items():
        source = files.get(name, {}).get('text')
        if not isinstance(source, str):
            return None
        source = source.replace('\r\n', '\n').replace('\r', '\n')
        if hashlib.sha256(source.encode()).hexdigest() != expected:
            return None
    text = files.get(HEADING_OUTPUT, {}).get('text', '')
    if not isinstance(text, str):
        return None
    text = html.unescape(text)
    # A permissive presence test supplies only a necessary condition. It is
    # deliberately not a Markdown parser or an automatic positive verdict:
    # quoted headings, extra sections and prose quality still need judgment.
    missing = [title for title in ('Fiscal', 'Administrative', 'Network')
               if re.search(r'##[ \t]+' + title + r'(?=$|[ \t#\r\n])', text) is None]
    if not missing:
        return None
    return {'criterion_id': 'Q01', 'passed': False,
            'evidence': HEADING_OUTPUT + ': absent required heading text: ' + ', '.join('## ' + t for t in missing) + '.',
            'reasoning': 'The reviewed public instruction and Q01 explicitly require these exact section headings. '
                         'Their absence violates a binding requirement; other quality conditions are not waived.'}


def evaluation_method(payload):
    """Call only after evaluate returns a registered verdict."""
    from .workflow_checks import verdict as workflow_verdict
    if workflow_verdict(payload) is not None:
        return 'registered_workflow_source_predicate'
    from .calendar_checks import verdict as calendar_verdict
    if calendar_verdict(payload) is not None:
        return 'registered_calendar_source_predicate'
    if restored_count_verdict(payload) is not None:
        from .source_coverage import count_measure
        if count_measure(payload)['unit'] == 'characters':
            return 'registered_source_character_count'
        return 'registered_source_report_word_count'
    if source_matrix_verdict(payload) is not None:
        return 'registered_supplier_matrix_source_predicate'
    if memo_count_verdict(payload) is not None:
        return 'registered_memo_body_word_count'
    if supplier_note_check(payload) is not None:
        return 'registered_supplier_note_csv_length_veto'
    if payload.get('criterion') == DELIVERABLE_CRITERION:
        return 'registered_deliverable_set_veto'
    return 'registered_missing_heading_veto' if payload.get('criterion') == HEADING_CRITERION else 'registered_literal_count'


def matches(text, number):
    return list(re.finditer(r'\b(?:fig\.|figure)\s*' + re.escape(number) + r'(?!\d)', text, re.IGNORECASE))


def evaluate(payload):
    from .workflow_checks import verdict as workflow_verdict
    workflow = workflow_verdict(payload)
    if workflow is not None:
        return workflow
    from .calendar_checks import verdict as calendar_verdict
    calendar = calendar_verdict(payload)
    if calendar is not None:
        return calendar
    counted = restored_count_verdict(payload)
    if counted is not None:
        return counted
    matrix_verdict = source_matrix_verdict(payload)
    if matrix_verdict is not None:
        return matrix_verdict
    memo_verdict = memo_count_verdict(payload)
    if memo_verdict is not None:
        return memo_verdict
    note_verdict = supplier_note_veto(payload)
    if note_verdict is not None:
        return note_verdict
    if payload.get('criterion') == DELIVERABLE_CRITERION:
        return deliverable_set_veto(payload)
    if payload.get('criterion') == HEADING_CRITERION:
        return missing_heading_veto(payload)
    if payload.get('criterion') != CRITERION:
        return None
    files = payload['evidence']['files']
    original = files.get(SOURCE, {}).get('text')
    # This registration is scoped to the source package with three original
    # references. A different source does not silently inherit this predicate.
    if not isinstance(original, str) or len(matches(original, '4.7')) != 3:
        return None
    text = files.get(OUTPUT, {}).get('text', '')
    found = matches(text, '5.4')
    positions = ', '.join(str(m.start()) for m in found[:8]) or 'none'
    return {'criterion_id': CRITERION['id'], 'evidence':
            f'{OUTPUT}: {len(found)} target references; character offsets {positions}. {SOURCE}: 3 original references.',
            'reasoning': f'The frozen criterion requires exactly 3 references to Fig. 5.4 or figure 5.4. The literal count is {len(found)}.',
            'passed': len(found) == 3}
