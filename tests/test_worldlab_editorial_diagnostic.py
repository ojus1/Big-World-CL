from copy import deepcopy
from datetime import date, timedelta
import csv
import io
import unittest

from worldlab.editorial_diagnostic import working_days, boundary_controls, arithmetic_checks, HOLIDAYS, summarize


def text(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


class Tests(unittest.TestCase):
    def test_hand_calculated_calendar_boundaries(self):
        self.assertTrue(boundary_controls()['ok'])
        self.assertEqual(len(boundary_controls()['cases']), 8)

    def test_constant_time_calendar_matches_independent_date_enumeration(self):
        for offset in range(365):
            start = date(2025, 1, 1) + timedelta(days=offset)
            for span in (-7, 0, 1, 6, 7, 8, 14, 31):
                end = start + timedelta(days=span - 1)
                dates = [start + timedelta(days=i) for i in range(max(0, span))]
                expected = span - sum(d.weekday() == 6 for d in dates) - sum(d in HOLIDAYS for d in dates)
                self.assertEqual(working_days(start, end), expected)

    def rows(self):
        return [{'scenario': 'dates_fixes', 'titre': 'Fixture', 'langue': 'FR',
                 'date_livraison_manuscrit': '2025-01-06', 'date_relecture': '2025-01-16',
                 'fenetre_jours_ouvrables': '10', 'sous_seuil_10j': 'non'}]

    def test_wrong_calendar_and_boundary_are_separate_defects(self):
        rows = self.rows()
        self.assertTrue(all(c['passed'] for c in arithmetic_checks(text(rows))['checks']))
        wrong = deepcopy(rows); wrong[0]['fenetre_jours_ouvrables'] = '9'
        self.assertEqual([c['passed'] for c in arithmetic_checks(text(wrong))['checks']], [False, True])
        wrong[0]['sous_seuil_10j'] = 'oui'
        self.assertEqual([c['passed'] for c in arithmetic_checks(text(wrong))['checks']], [False, False])
        rows[0]['fenetre_jours_ouvrables'] = '10.0'
        self.assertTrue(all(c['passed'] for c in arithmetic_checks(text(rows))['checks']))

    def test_missing_malformed_or_nonfinite_values_cannot_pass(self):
        for value in ('', 'NaN', 'Infinity', 'not-a-number'):
            rows = self.rows(); rows[0]['fenetre_jours_ouvrables'] = value
            self.assertFalse(all(c['passed'] for c in arithmetic_checks(text(rows))['checks']))
        self.assertFalse(all(c['passed'] for c in arithmetic_checks('')['checks']))
        rows = self.rows(); rows[0]['date_relecture'] = '2025-99-99'
        self.assertFalse(all(c['passed'] for c in arithmetic_checks(text(rows))['checks']))

    def test_summary_does_not_relabel_historical_outcomes_or_claim_accuracy(self):
        positive = {**arithmetic_checks(text(self.rows())), 'qualitative_success': False}
        wrong = self.rows(); wrong[0]['fenetre_jours_ouvrables'] = '0'
        negative = {**arithmetic_checks(text(wrong)), 'qualitative_success': True}
        result = summarize([positive, negative])
        self.assertEqual(result['arithmetic_failures'], 1)
        self.assertEqual(result['historically_successful_with_arithmetic_failure'], 1)
        self.assertFalse(result['historical_grades_changed'])
        self.assertEqual(result['distinct_task_families'], 1)


if __name__ == '__main__': unittest.main()
