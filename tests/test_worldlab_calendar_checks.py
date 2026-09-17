import csv
from copy import deepcopy
from datetime import date
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import save
from worldlab import calendar_checks as cal
from worldlab.qualitative import request_verdict


def csv_text(columns, rows):
    stream = io.StringIO(); w = csv.DictWriter(stream, fieldnames=columns)
    w.writeheader(); w.writerows(rows)
    return stream.getvalue()


class CalendarChecksTests(unittest.TestCase):
    def fixture(self):
        agenda = []; output = []
        for title in ['A', 'B', 'C', 'D']:
            for language in ['DE', 'EN', 'FR']:
                row = dict(titre=title, langue=language, date_livraison_manuscrit='2025-01-06',
                           date_relecture='2025-01-27', date_parution='2025-02-03')
                agenda.append(row)
                for scenario in sorted(cal.SCENARIOS):
                    actual = dict(row, scenario=scenario, fenetre_jours_calendaires='22',
                                  fenetre_jours_ouvrables='19', sous_seuil_10j='non', statut='OK')
                    if scenario == 'compression':
                        actual.update(date_livraison_manuscrit='2025-01-20', fenetre_jours_calendaires='8',
                                      fenetre_jours_ouvrables='7', sous_seuil_10j='oui')
                    if scenario == 'glissement' and language != 'FR':
                        actual.update(date_livraison_manuscrit='2025-01-20', date_relecture='2025-02-10', date_parution='2025-02-17')
                    output.append(actual)
        output.sort(key=lambda r: (r['scenario'], r['titre'], r['langue']))
        source = csv_text(list(agenda[0]), agenda)
        files = {cal.SOURCE: {'text': source}, cal.OUTPUT: {'text': csv_text(cal.COLUMNS, output)}}
        ids = ['csv_sort_order', 'csv_schema_completeness', 'dates_fixes_fidelity', 'window_arithmetic',
               'compression_shift', 'glissement_logic', 'sous_seuil_flag']
        criteria = [{'id': x, 'requirement': x, 'weight': 1} for x in ids]
        rule = {'criterion_ids': ids, 'tasks': {'fixture': {'instruction_sha256': hashlib.sha256(b'Calendar').hexdigest(),
                'input_text_sha256': {cal.SOURCE: hashlib.sha256(source.replace('\r\n', '\n').encode()).hexdigest()}, 'criteria': criteria}}}
        return rule, files, output, criteria

    def test_all_checks_positive_and_targeted_mutations_no_provider(self):
        rule, files, output, criteria = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / 'registry.json'; save(registry, rule)
            with patch.object(cal, 'REGISTRY', registry):
                for c in criteria:
                    payload = {'criterion': c, 'evidence': {'instruction': 'Calendar', 'files': files}}
                    self.assertTrue(cal.verdict(payload)['passed'], c['id'])
                    self.assertEqual(request_verdict(None, None, payload, 1).evaluation_method, 'registered_calendar_source_predicate')
                    changed = deepcopy(output); identifier = c['id']
                    if identifier == 'csv_sort_order': changed.reverse()
                    elif identifier == 'csv_schema_completeness': changed[-1] = changed[0]
                    elif identifier == 'window_arithmetic': changed[0]['fenetre_jours_ouvrables'] = '8'
                    elif identifier == 'sous_seuil_flag': changed[0]['sous_seuil_10j'] = 'non'
                    else:
                        scenario = {'dates_fixes_fidelity': 'dates_fixes', 'compression_shift': 'compression', 'glissement_logic': 'glissement'}[identifier]
                        row = next(r for r in changed if r['scenario'] == scenario and r['langue'] == 'FR')
                        row['date_livraison_manuscrit'] = '2025-01-21'
                    mutated = deepcopy(payload)
                    mutated['evidence']['files'][cal.OUTPUT]['text'] = csv_text(cal.COLUMNS, changed)
                    self.assertFalse(cal.verdict(mutated)['passed'], identifier)
                for field in ['instruction', 'source', 'criterion']:
                    changed = deepcopy(payload)
                    if field == 'instruction': changed['evidence']['instruction'] += '!'
                    if field == 'source': changed['evidence']['files'][cal.SOURCE]['text'] += '!'
                    if field == 'criterion': changed['criterion']['weight'] = 2
                    self.assertIsNone(cal.verdict(changed))

    def test_inclusive_sundays_holidays_negative_and_leap_boundaries(self):
        self.assertEqual(cal.window(date(2025, 1, 6), date(2025, 1, 13)), (8, 7))
        self.assertEqual(cal.window(date(2025, 1, 20), date(2025, 1, 13)), (-6, -6))
        self.assertEqual(cal.window(date(2025, 4, 18), date(2025, 4, 20)), (3, 1))
        self.assertEqual(cal.window(date(2024, 2, 28), date(2024, 3, 1)), (3, 3))


if __name__ == '__main__': unittest.main()
