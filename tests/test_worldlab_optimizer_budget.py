import unittest
from lifespan.evaluation.optimizer import make_reflector

CREDS={'api_key':'fixture-secret-value','model':'Qwen/Qwen3.8-Flash-Next-FP8',
       'base_url':'http://localhost:8011/v1','provider_profile':'responses-no-thinking-v1'}
PAYLOAD={'prompt':'Propose concise procedures.','current_day':2,'train_experiences':[],'max_output_tokens':1024}
LIMITS={'max_model_calls':1,'max_tokens':32000,'timeout_seconds':120}


class OptimizerBudgetTests(unittest.TestCase):
    def test_configured_output_allowance_is_sent_and_metered(self):
        requests=[]
        def send(request,**kwargs):
            requests.append(request)
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'[]'}]}],
                    'usage':{'input_tokens':12,'output_tokens':2,'total_tokens':14}}
        reflector=make_reflector(CREDS,transport=send,output_tokens=4096)
        result=reflector(PAYLOAD,LIMITS)
        self.assertEqual(requests[0]['max_output_tokens'],4096)
        self.assertEqual(result['upstream_requested_output_tokens'],1024)
        self.assertEqual(result['configured_output_tokens'],4096)
        self.assertEqual(result['tokens'],14)
        self.assertLessEqual(result['input_token_reservation']+result['max_output_tokens'],32000)

    def test_incomplete_proposal_is_preserved_redacted_and_not_accepted(self):
        def send(request,**kwargs):
            return {'status':'incomplete','output':[{'type':'message','content':[{'type':'output_text','text':'[{"content":"fixture-secret-value'}]}],
                    'usage':{'input_tokens':12,'output_tokens':4096,'total_tokens':4108}}
        result=make_reflector(CREDS,transport=send,output_tokens=4096)(PAYLOAD,LIMITS)
        self.assertEqual(result['status'],'incomplete_response')
        self.assertEqual(result['response'],'')
        self.assertIn('[REDACTED]',result['partial_response'])
        self.assertNotIn(CREDS['api_key'],result['partial_response'])
        self.assertTrue(result['accounting_complete']);self.assertEqual(result['tokens'],4108)


if __name__=='__main__':unittest.main()
