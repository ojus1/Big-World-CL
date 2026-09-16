from copy import deepcopy
import unittest
from worldlab.learning_feedback import learning_feedback
from worldlab.validation_context import observed_feedback


class LearningFeedbackTests(unittest.TestCase):
    def test_long_passing_prefix_cannot_hide_the_actual_failure(self):
        grade={'feedback':'Passing check. '*5000+'Missing Python examples.',
            'criteria':[{'index':0,'criteria_results':[{'index':0,'passed':True,'reasoning':'Sorting is correct.','criterion':'PRIVATE_RUBRIC_TEXT'}]},
                        {'index':1,'criteria_results':[{'index':0,'passed':False,'reasoning':'Missing Python examples.','criterion':'PRIVATE_RUBRIC_TEXT'}]}]}
        original=deepcopy(grade);text=learning_feedback(grade)
        self.assertIn('Missing Python examples.',text[:140])
        self.assertNotIn('Sorting is correct.',text[:140])
        self.assertNotIn('PRIVATE_RUBRIC_TEXT',text)
        self.assertTrue(text.endswith(grade['feedback']))
        self.assertEqual(grade,original)
        self.assertEqual(observed_feedback({'grade':grade}),text)

    def test_internal_feedback_and_all_pass_feedback_preserve_source(self):
        grade={'feedback':'A passed; B needs revision.', 'criteria':[
            {'criterion_id':'A','passed':True,'reasoning':'Present.'},
            {'criterion_id':'B','passed':False,'reasoning':'Missing source citation.'}]}
        self.assertIn('B: Missing source citation.',learning_feedback(grade)[:140])
        grade['criteria'][1]['passed']=True
        self.assertEqual(learning_feedback(grade),grade['feedback'])
        self.assertEqual(learning_feedback({'feedback':'Released legacy feedback'}),'Released legacy feedback')


if __name__=='__main__':unittest.main()
