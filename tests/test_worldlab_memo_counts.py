from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from worldlab import memo_counts
from worldlab.mechanical_criteria import evaluate
from worldlab.qualitative import request_verdict, verdict_input


class MemoCountsTests(unittest.TestCase):
    def payload(self, n, criterion='memo_word_count'):
        c = {'id': criterion, 'requirement': 'Fixture requirement', 'weight': 1}
        rule = {'instruction_sha256': hashlib.sha256(b'Memo.').hexdigest(), 'criteria': [c],
                'source_sha256': {'input/source.md': hashlib.sha256(b'Source.').hexdigest()}}
        return rule, {'criterion': c, 'evidence': {'instruction': 'Memo.', 'files': {
            'input/source.md': {'text': 'Source.'}, memo_counts.OUTPUT: {'text': '# Title\n\n' + ' '.join(['word'] * n)}}}}

    def test_boundaries_and_no_provider_dispatch(self):
        for count, expected in [(144, False), (145, True), (155, True), (156, False)]:
            rule, payload = self.payload(count)
            with patch.object(memo_counts.json, 'loads', return_value=[rule]):
                value = evaluate(payload)
                self.assertEqual(value['passed'], expected)
                result = request_verdict(None, None, payload, 1)
                self.assertEqual(result.evaluation_method, 'registered_memo_body_word_count')

    def test_unicode_punctuation_and_title_are_counted_explicitly(self):
        self.assertEqual(memo_counts.body_count('\ufeff\nTitre\n=====\n\nl’école quarante-huit 中文 : ;'), 3)

    def test_length_does_not_automatically_pass_semantic_format(self):
        rule, payload = self.payload(150, 'memo_format_quality')
        with patch.object(memo_counts, 'registration', return_value=rule):
            self.assertIsNone(memo_counts.verdict(payload))
            value = memo_counts.semantic_payload(payload)
            self.assertIn('Do not estimate or recount', value['evaluation_scope'])
            self.assertEqual(value['separately_evaluated_word_count']['body_words'], 150)

    def test_changed_contract_or_source_cannot_inherit_count_policy(self):
        rule, payload = self.payload(150)
        for kind in ['criterion', 'instruction', 'source']:
            changed = deepcopy(payload)
            if kind == 'criterion': changed['criterion']['weight'] = 2
            if kind == 'instruction': changed['evidence']['instruction'] += '!'
            if kind == 'source': changed['evidence']['files']['input/source.md']['text'] += '!'
            with patch.object(memo_counts.json, 'loads', return_value=[rule]):
                self.assertIsNone(memo_counts.measure(changed))


if __name__ == '__main__': unittest.main()
