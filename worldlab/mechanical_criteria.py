"""Narrow executable predicates for exactly registered frozen rubric criteria.

Unknown or changed criteria always return None and retain ordinary judging.
This is a literal-count check, not a model judgment or general semantic oracle.
"""
import re

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


def matches(text, number):
    return list(re.finditer(r'\b(?:fig\.|figure)\s*' + re.escape(number) + r'(?!\d)', text, re.IGNORECASE))


def evaluate(payload):
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
