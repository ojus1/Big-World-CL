from copy import deepcopy
import unittest
from worldlab.mechanical_criteria import CRITERION, SOURCE, OUTPUT, evaluate
from worldlab.qualitative import request_verdict


class Tests(unittest.TestCase):
    def payload(self, text):
        return {'criterion': deepcopy(CRITERION), 'evidence': {'files': {
            SOURCE: {'text': 'Fig. 4.7\nfigure 4.7\nFig. 4.7'}, OUTPUT: {'text': text}}}}

    def test_variants_exclude_adjacent_numbers_and_changed_reference(self):
        for text, expected in [
            ('Fig. 5.4\nFIGURE 5.4\nfig. 5.4', True),
            ('Fig. 5.5\nfigure 5.4\nFig. 5.4', False),
            ('Fig. 5.4\nfigure 5.4\nFig. 5.4\nFig. 5.4', False),
            ('Fig. 5.4\nfigure 5.4\nFig. 5.40', False),
            ('Fig. 5.4\nfigure 5.4\nFig. 5.4\nFig. 5.40', True),
            ('', False),
        ]:
            self.assertEqual(evaluate(self.payload(text))['passed'], expected)

    def test_changed_criterion_or_source_does_not_reuse_registered_rule(self):
        value = self.payload('Fig. 5.4')
        value['criterion']['requirement'] = 'Require a different count'
        self.assertIsNone(evaluate(value))
        value = self.payload('Fig. 5.4'); value['evidence']['files'][SOURCE]['text'] = 'Other source'
        self.assertIsNone(evaluate(value))

    def test_count_path_never_dispatches_to_model(self):
        result = request_verdict(None, None, self.payload('Fig. 5.4\nfigure 5.4\nFig. 5.4'), 1)
        self.assertEqual(result.evaluation_method, 'registered_literal_count')


if __name__ == '__main__': unittest.main()
