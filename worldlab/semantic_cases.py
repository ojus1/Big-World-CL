"""Constructed, source-reviewed development controls across three task families.

These labels test particular rubric groups; repeated variants are dependent.
They are neither solver outputs nor evidence of general evaluator accuracy.
"""
from copy import deepcopy
import hashlib
import json
from scripts.source_world_calibration import child, read, sha
from .qualify_semantics import controls as association_controls


PINS = {
    'internal/euw_de_001_v2': {
        'task': 'a91887a1a790cadb49a6afda7b6c6cfd921063915632e23eb6ea78608553e99b',
        'rubric': '63d8fb7e83abbe05de8b1c45cdb60b16476ed653263668204bb2a91ebd5d763c',
        'inputs': {
            'input/jahresabschluss_2025.csv': '3ea8fc8e4a531ffebd484e1aba4637bfd0141bbce29a9efde6a6ffbf737ad7f8',
            'input/offene_forderungen.csv': '86baa1e8e37f11754a07a2d37bdddd98d9d6163a5f97266ffafa52b2c22ec4bc',
        },
    },
    'internal/euw_fr_001': {
        'task': 'e91585476f72951f9cdec1284e0e6be7b42612eff4e61dcabd5cbfddd8db1932',
        'rubric': 'eb88545ec6e2707ad7ec487f9dfc2758f5ab4a4dc48405d6930c9a044c997960',
        'inputs': {
            'input/draft_coordination.md': 'd15ed59cce9e53aa906c264e3f4683ef38ed2cfdefd810a4bd0d209f9ef79843',
            'input/revision_notes.md': '4b4c6036d60af53da9057332008898e0df5c2997624208dd67c295635246f977',
            'input/spec_display.csv': 'c3a9a536b3598ccdf7d9997c866cdf40a122cae0bab9794f29a3e94145a78472',
        },
    },
    'internal/euw_fr_003_en_bridge': {
        'task': 'a126aaf7df7e89f1c55a4ff853bcc891e3a14e2ec1b89bf154481c8b3bcd6422',
        'rubric': 'dd0c5b8e2db09a8bfb3d52211fb866d0910f63207262268350de98c381c3fac6',
        'inputs': {
            'input/fiche_avantages.csv': 'eb9ea96cc76ca7f0b656f217d70d60d8fcd214f635c351bcd13e3e1089b46508',
            'input/notes_reunion.md': 'a21318a63d10eaca3cf3e46b9f4d170d04ffc9797c9d85e7602d7eedcfe34e70',
            'input/reglement_interne.md': 'e7b3eb19d6124852be5b1c60c9bcfefe37aef5660937baa1c9a73a47189ecfe1',
        },
    },
}

RECONCILIATION_CSV = ('summe,bilanzwert,differenz,ergebnis\n'
                      '30651.50,30651.55,-0.05,Abweichung\n')
RECONCILIATION_REPORT = '''# Abgleich der Forderungen

## 1) Summe offene Forderungen
Die offenen und überfälligen Forderungen K-101, K-102, K-104 und K-105
ergeben 30651.50 EUR. Die stornierte Forderung K-103 ist ausgeschlossen.

## 2) Bilanzwert
Der Posten Forderungen aus L+L beträgt 30651.55 EUR.

## 3) Differenz
Summe minus Bilanzwert: -0.05 EUR.

## 4) Ergebnis
Abweichung: Die Forderungssumme liegt 0.05 EUR unter dem Bilanzwert.
'''
LETTER = '''Objet : Demande de vitrine supermarché – 5 étagères

Bonjour WOW Display,

Merci de prévoir une vitrine de 5 étagères, avec 20 sachets par étagère
dans un arrangement 5×4, soit 100 sachets au total. La charge par étagère
est de 10 kg et la hauteur totale de 2000 mm.

Veuillez inclure le coffret cadeau en complément de la vitrine.
Merci de fournir un mockup 3D avec les quatre vues : avant, arrière, gauche, droite.

Cordialement,
Équipe Marketing
'''
FACTS = {
    'display': {'shelves': 5, 'pouches_per_shelf': 20, 'total_pouches': 100,
                'load_per_shelf_kg': 10, 'height_mm': 2000},
    'gift_box': {'included': True},
    'mockup': {'views': 4, 'views_list': ['avant', 'arrière', 'gauche', 'droite']},
}


def source(bank, task):
    row = bank.by_id[task]
    public = child(bank.root, row['public_directory'])
    rubric_path = child(bank.root, row['private_directory']) / 'rubric.json'
    pin = PINS[task]
    if (row['partition'] != 'calibration_train' or sha(public / 'task.json') != pin['task']
            or sha(rubric_path) != pin['rubric']):
        raise ValueError('Semantic controls require the reviewed development source: ' + task)
    files = {}
    for path in sorted(public.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink in semantic source')
        if not path.is_file() or path == public / 'task.json':
            continue
        relative = str(path.relative_to(public))
        if not relative.startswith('input/'):
            raise ValueError('Unreviewed semantic source file: ' + relative)
        # Bank verifies its complete file inventory; bind these original bytes
        # into every prepared case as well as the plan's bank manifest hash.
        files[relative] = path.read_text()
    if {name: sha(public / name) for name in files} != pin['inputs']:
        raise ValueError('Semantic control input bytes differ from the source review: ' + task)
    return read(rubric_path), files


def controls(bank):
    sources = {task: source(bank, task) for task in PINS}
    cases = []
    for case in association_controls(bank):
        cases.append({**case, 'id': 'association-' + case['id'],
                      'task_id': 'internal/euw_fr_003_en_bridge', 'family': 'association'})

    def add(family, task, name, criterion, expected, rationale, outputs):
        rubric, originals = sources[task]
        c = next(c for c in rubric['criteria'] if c['id'] == criterion)
        files = {**originals, **outputs}
        evidence = {'instruction': bank.public(task)['instruction'],
                    'frozen_clock': bank.public(task).get('frozen_clock'),
                    'files': {k: {'text': v, 'sha256': hashlib.sha256(v.encode()).hexdigest()}
                              for k, v in files.items()}}
        cases.append({'id': family + '-' + name, 'task_id': task, 'family': family,
                      'expected': expected, 'label_rationale': rationale,
                      'payload': {'criterion': c, 'ambiguities': rubric.get('ambiguities', []),
                                  'evaluation_guidance': rubric.get('evaluation_guidance', []),
                                  'evidence': evidence}})

    task = 'internal/euw_de_001_v2'
    def de(name, criterion, expected, rationale, csv=RECONCILIATION_CSV, prose=RECONCILIATION_REPORT):
        add('reconciliation', task, name, criterion, expected, rationale,
            {'output/abgleich_forderungen.csv': csv, 'output/abgleich_forderungen.md': prose})

    for criterion in ('Q01', 'Q02', 'Q03', 'Q04'):
        de('valid-' + criterion.lower(), criterion, True,
           'Only K-101/K-102/K-104/K-105 contribute: 12500+8300.50+6750.25+3100.75=30651.50. '
           'The selected balance is 30651.55; the signed difference is -0.05, outside the 0.005 tolerance. '
           'Both prescribed artifacts, ordered fields/sections and two-decimal EUR amounts are present.')
    de('valid-locale-csv', 'Q03', True,
       'Semicolon-separated fields make German decimal commas unambiguous; Q03 expressly permits locale formatting.',
       csv='summe;bilanzwert;differenz;ergebnis\n30651,50;30651,55;-0,05;Abweichung\n')
    de('valid-direction-paraphrase', 'Q02', True,
       'Below the balance expresses the same signed difference; Q02 permits this prose alternative.',
       prose=RECONCILIATION_REPORT.replace('Summe minus Bilanzwert: -0.05 EUR.',
                                         'Die Summe unterschreitet den Bilanzwert um 0.05 EUR.'))
    de('valid-semantic-headings', 'Q04', True,
       'The report keeps the four requested meanings and order; equivalent German section wording is permitted.',
       prose=RECONCILIATION_REPORT.replace('Summe offene Forderungen', 'Gesamtsumme der offenen Forderungen')
                                     .replace('## 2) Bilanzwert', '## 2) Forderungen laut Bilanz'))
    de('cancelled-receivable-included', 'Q01', False,
       'Adding the cancelled K-103 amount of 4200 violates the explicit status filter.',
       csv=RECONCILIATION_CSV.replace('30651.50', '34851.50').replace('-0.05', '4199.95'),
       prose=RECONCILIATION_REPORT.replace('30651.50', '34851.50'))
    de('reversed-difference', 'Q02', False,
       'The requested difference is sum minus balance, so positive 0.05 and an above-balance conclusion reverse its sign.',
       csv=RECONCILIATION_CSV.replace('-0.05', '0.05'),
       prose=RECONCILIATION_REPORT.replace('-0.05', '0.05').replace('unter dem', 'über dem'))
    de('wrong-exact-result', 'Q02', False,
       'The public CSV ergebnis must be Abweichung for this nonzero difference.',
       csv=RECONCILIATION_CSV.replace('Abweichung', 'Stimmt überein'))
    de('contradictory-report', 'Q02', False,
       'A correct CSV does not cure the report claiming agreement despite the measured mismatch.',
       prose=RECONCILIATION_REPORT.replace('Abweichung: Die Forderungssumme liegt 0.05 EUR unter dem Bilanzwert.',
                                         'Die Beträge stimmen vollständig überein; es besteht keine Abweichung.'))
    de('duplicate-data-row', 'Q03', False,
       'The public instruction requires one aggregate row, not two copies.',
       csv=RECONCILIATION_CSV + '30651.50,30651.55,-0.05,Abweichung\n')
    de('missing-currency', 'Q04', False,
       'Q04 and the public report instruction explicitly require EUR labels.',
       prose=RECONCILIATION_REPORT.replace(' EUR', ''))

    task = 'internal/euw_fr_001'
    def fr(name, criterion, expected, rationale, prose=LETTER, facts=None, ensure_ascii=False, extra=None):
        outputs = {'output/coordination_final.md': prose,
                   'output/appendix_facts.json': json.dumps(FACTS if facts is None else facts,
                                                           ensure_ascii=ensure_ascii, indent=2)}
        outputs.update(extra or {})
        add('coordination', task, name, criterion, expected, rationale, outputs)

    for criterion in ('Q01', 'Q02', 'Q03', 'Q04'):
        fr('valid-' + criterion.lower(), criterion, True,
           'Revision notes and specifications require 5 shelves, 20 pouches/shelf, 100 total, 10 kg/shelf, '
           '2000 mm, a gift box and the four ordered views. The French letter and typed JSON preserve these facts.')
    fr('valid-escaped-unicode', 'Q03', True,
       'JSON Unicode escapes decode to the exact required arrière value; serialization is not a language change.',
       ensure_ascii=True)
    fr('valid-arrangement-four', 'Q04', True,
       'The numeral 4 in the 5×4 pouch arrangement is expressly allowed and does not assert four shelves.',
       prose=LETTER.replace('dans un arrangement 5×4', 'dans un arrangement de 5 rangées de 4 sachets'))
    fr('stale-subject', 'Q04', False,
       'The subject still requests four shelves; Q04 expressly checks stale values throughout, including the subject.',
       prose=LETTER.replace('– 5 étagères', '– 4 étagères'))
    fr('stale-load-and-height', 'Q01', False,
       'The draft values 8 kg and 1800 mm contradict higher-priority revision notes.',
       prose=LETTER.replace('10 kg', '8 kg').replace('2000 mm', '1800 mm'))
    fr('missing-gift-box', 'Q02', False,
       'The revised letter must include the gift box; a correct appendix alone does not satisfy this letter criterion.',
       prose=LETTER.replace('Veuillez inclure le coffret cadeau en complément de la vitrine.\n', ''))
    fr('missing-back-view', 'Q02', False,
       'The letter omits the required rear view even though the appendix retains it.',
       prose=LETTER.replace('les quatre vues : avant, arrière, gauche, droite', 'les trois vues : avant, gauche, droite'))
    wrong = deepcopy(FACTS); wrong['display']['shelves'] = '5'
    fr('string-integer', 'Q03', False, 'shelves must be a JSON integer, not the string "5".', facts=wrong)
    wrong = deepcopy(FACTS); wrong['mockup']['views_list'].reverse()
    fr('reversed-view-order', 'Q03', False,
       'The public contract fixes the exact order avant, arrière, gauche, droite.', facts=wrong)
    fr('unsupported-commitment', 'Q04', False,
       'No source supports a contractual promise of free delivery tomorrow; Q04 prohibits unsupported commercial commitments.',
       prose=LETTER.replace('Cordialement,',
                           'Vous avez confirmé votre engagement contractuel à livrer gratuitement demain.\n\nCordialement,'))
    fr('extra-deliverable', 'Q04', False,
       'The public instruction and Q04 require exactly the two named output files.',
       extra={'output/extra_notes.md': 'Résumé supplémentaire.'})
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate semantic control ID')
    return cases
