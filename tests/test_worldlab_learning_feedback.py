from copy import deepcopy
import json
import unittest
from worldlab.learning_feedback import learning_feedback
from worldlab.validation_context import observed_feedback
from worldlab.audit_worlds import audit_learning_context, audit_replay_response
from worldlab.attempts import task_instruction


class LearningFeedbackTests(unittest.TestCase):
    def test_rejected_artifact_preserves_zero_grade_and_feedback_with_null_supplement(self):
        from worldlab.artifact_contract import rejected_grade
        record = {'passed': False, 'input_changes': [], 'unauthorized_files': [],
                  'evidence_violations': [{'path': 'output/', 'reason': 'No deliverable submitted'}]}
        grade = rejected_grade(record, 'rubric', 'evidence')
        original = deepcopy(grade)
        self.assertIsNone(grade['public_requirements'])
        self.assertEqual(learning_feedback(grade), grade['feedback'])
        self.assertEqual(observed_feedback({'grade': grade}), grade['feedback'])
        self.assertEqual(grade, original)
        self.assertEqual(grade['quality_score'], 0)

    def test_saved_trajectory_allows_json_key_order_but_rejects_content_changes(self):
        trajectory=[{'role':'assistant','content':'Read source','tool_calls':[{'id':'1','args':{'path':'input.md'}}]},
                    {'role':'tool','content':'source text'}]
        response=json.dumps({'messages':trajectory},ensure_ascii=False)
        saved=json.loads(json.dumps(trajectory,sort_keys=True))
        audit_replay_response(response,saved)
        for bad in [response.replace('source text','fabricated text'),
                    json.dumps({'messages':list(reversed(trajectory))}),
                    response.replace('"role": "assistant"','"role": "user", "role": "assistant"'),
                    'null','not json']:
            with self.subTest(value=bad),self.assertRaises(ValueError):audit_replay_response(bad,saved)

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

    def test_optimizer_context_rejects_changed_prompt_feedback_and_trajectory(self):
        class Bank:
            def public(self, task):
                return {'instruction': 'Write the source-grounded report.'}
        bank=Bank()
        selected=[{'id':'s1','split':'train','day':0,'feedback_day':1,'lineage_group':'f1',
                   'task_id':'t1','grade':{'feedback':'Missing source citation.'}}]
        task={'id':'s1','split':'train','available_day':0,'feedback_available_day':1,
              'source_session':'f1','prompt':task_instruction(bank.public('t1')['instruction'],None),
              'context':'','feedback':'Missing source citation.'}
        replay={'id':'s1','split':'train','attempt_index':0,'sample_id':0,'phase':'train_initial',
                'response':'Native transcript','feedback':'Native released feedback'}
        entry={'task':task,**{k:replay[k] for k in ('attempt_index','sample_id','phase','response','feedback')}}
        update={'current_day':2,'replay_evidence':[replay],
                'optimizer_inputs':[{'current_day':2,'train_experiences':[entry]}]}
        audit_learning_context(bank,selected,update)
        for target,key in [('task','prompt'),('task','feedback'),('entry','response'),('entry','feedback')]:
            changed=deepcopy(update);record=changed['optimizer_inputs'][0]['train_experiences'][0]
            (record['task'] if target=='task' else record)[key]='Injected unreleased context'
            with self.subTest(target=target,key=key),self.assertRaises(ValueError):
                audit_learning_context(bank,selected,changed)

    def test_failed_public_check_is_visible_when_all_rubric_checks_pass(self):
        grade={'feedback':'Rubric passed. Public requirement checks: total needs revision.',
               'criteria':[{'criterion_id':'prose','passed':True,'reasoning':'Clear.'}],
               'public_requirements':{'checks':[
                   {'id':'public_total','passed':False,'requirement':'Recompute the total.',
                    'evidence':['Total differs from source rows.']}]}}
        original=deepcopy(grade);feedback=learning_feedback(grade)
        self.assertIn('public_total: Recompute the total.',feedback[:140])
        self.assertIn('Total differs from source rows.',feedback)
        self.assertTrue(feedback.endswith(grade['feedback']))
        self.assertEqual(grade,original)
        grade['public_requirements']['checks'][0]['passed']=True
        self.assertEqual(learning_feedback(grade),grade['feedback'])


if __name__=='__main__':unittest.main()
