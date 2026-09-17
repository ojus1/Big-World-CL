from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch
from worldlab import mechanical_criteria as rules
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

    def test_deliverable_veto_checks_exact_set_and_never_assumes_semantic_success(self):
        instruction, source = 'Exactly the two named deliverables.', 'Original source.\n'
        payload = {'criterion': deepcopy(rules.DELIVERABLE_CRITERION), 'evidence': {
            'instruction': instruction, 'files': {'input/source.md': {'text': source},
                **{name: {'text': 'Nonsense contents.'} for name in rules.DELIVERABLE_OUTPUTS}}}}
        with patch.object(rules, 'DELIVERABLE_INSTRUCTION_SHA256', hashlib.sha256(instruction.encode()).hexdigest()), \
             patch.object(rules, 'DELIVERABLE_SOURCES', {'input/source.md': hashlib.sha256(source.encode()).hexdigest()}):
            self.assertIsNone(evaluate(payload), 'Correct filenames alone do not satisfy letter quality')
            for change in ['extra', 'missing', 'replacement']:
                bad = deepcopy(payload)
                if change != 'extra': bad['evidence']['files'].pop('output/coordination_final.md')
                if change != 'missing': bad['evidence']['files']['output/extra.md'] = {'text': 'Extra'}
                self.assertFalse(evaluate(bad)['passed'])
                self.assertEqual(request_verdict(None, None, bad, 1).evaluation_method, 'registered_deliverable_set_veto')
                for drift in ['instruction', 'criterion', 'source']:
                    changed = deepcopy(bad)
                    if drift == 'instruction': changed['evidence']['instruction'] += ' Changed.'
                    if drift == 'criterion': changed['criterion']['requirement'] += ' Changed.'
                    if drift == 'source': changed['evidence']['files']['input/source.md']['text'] += ' Changed.'
                    self.assertIsNone(evaluate(changed))

    def test_missing_heading_veto_cannot_pass_content_or_leak_to_unregistered_sources(self):
        instruction = 'The reviewed fixture requires ## Fiscal, ## Administrative and ## Network.'
        text = 'Fixture source.\n'
        payload = {'criterion': deepcopy(rules.HEADING_CRITERION), 'evidence': {'instruction': instruction,
                   'files': {'input/source.md': {'text': text}, rules.HEADING_OUTPUT: {'text': '## Fiscal\n## Administrative\nGallery contacts'}}}}
        with patch.object(rules, 'HEADING_INSTRUCTION_SHA256', hashlib.sha256(instruction.encode()).hexdigest()), \
             patch.object(rules, 'HEADING_SOURCES', {'input/source.md': hashlib.sha256(text.encode()).hexdigest()}):
            self.assertFalse(evaluate(payload)['passed'])
            windows = deepcopy(payload)
            windows['evidence']['files']['input/source.md']['text'] = text.replace('\n', '\r\n')
            self.assertFalse(evaluate(windows)['passed'])
            result = request_verdict(None, None, payload, 1)
            self.assertEqual(result.evaluation_method, 'registered_missing_heading_veto')
            for body in ('## Fiscal\n## Administrative\n## Network\nUnrelated unsupported nonsense.',
                         '##  Fiscal\n##\tAdministrative\n## Netw&#111;rk',
                         '```\n## Fiscal\n## Administrative\n## Network\n```'):
                present = deepcopy(payload); present['evidence']['files'][rules.HEADING_OUTPUT]['text'] = body
                self.assertIsNone(evaluate(present), 'Heading presence cannot establish the full prose criterion')
            for change in ('instruction', 'source', 'criterion'):
                modified = deepcopy(payload)
                if change == 'instruction': modified['evidence']['instruction'] += ' Changed rule.'
                if change == 'source': modified['evidence']['files']['input/source.md']['text'] += ' Changed source.'
                if change == 'criterion': modified['criterion']['requirement'] += ' Changed criterion.'
                self.assertIsNone(evaluate(modified))


if __name__ == '__main__': unittest.main()
