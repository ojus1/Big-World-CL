from copy import deepcopy
import json
from pathlib import Path
import unittest
from worldlab.bank import Bank
from worldlab.procurement_checks import match,verdict,semantic_payload,grading_rules,readable_evidence,METHOD
from worldlab.qualitative import request_verdict,verdict_input
from worldlab.qualify_public_requirements import controls
from scripts.source_world_calibration import read,child
from worldlab.procurement_checks import REGISTRY

BANK=Path(__file__).resolve().parents[2]/'Big-World-CL/lifespan/artifacts/final-world-calibration-v1'


@unittest.skipUnless(BANK.is_dir(),'Frozen source bank required for procurement integration')
class ProcurementTests(unittest.TestCase):
    def payloads(self):
        b=Bank(BANK)
        csv=next(c['outputs']['output/tabla_puntuacion.csv'] for c in controls(b) if c['id']=='mri-component-positive')
        for rule in read(REGISTRY)['tasks']:
            directory=child(b.root,b.by_id[rule['task_id']]['public_directory'])
            files={name:{'text':(directory/name).read_text()} for name in rule['input_text_sha256']}
            files['output/tabla_puntuacion.csv']={'text':csv.replace('EXCLUDED',rule['excluded_marker'])}
            yield rule,{'criterion':rule['criteria']['csv_structure_and_values'],
                        'evidence':{'instruction':b.public(rule['task_id'])['instruction'],'files':files}}

    def test_all_registered_language_variants_veto_ineligible_supplier_scores(self):
        for rule,p in self.payloads():
            with self.subTest(task=rule['task_id']):
                self.assertIsNotNone(match(p));self.assertIsNone(verdict(p))
                bad=deepcopy(p);f=bad['evidence']['files']['output/tabla_puntuacion.csv']
                f['text']=f['text'].replace(rule['excluded_marker'],'9.8',1)
                r=request_verdict(None,None,bad,1)
                self.assertEqual(r.evaluation_method,METHOD)
                self.assertFalse(json.loads(r.output_text)['passed'])
                self.assertIn('public_mri_exclusions',r.output_text)
                bad['evidence']['files']['input/parametros_tecnicos.csv']['text']+='changed source'
                self.assertIsNone(verdict(bad))

    def test_malformed_or_wrong_arithmetic_never_passes_and_valid_csv_stays_semantic(self):
        for rule,p in self.payloads():
            for old,new in [('9.20','9.15'),('9.2,','9.0,'),('TOTAL,100','TOTAL,100,extra')]:
                bad=deepcopy(p);f=bad['evidence']['files']['output/tabla_puntuacion.csv'];f['text']=f['text'].replace(old,new)
                with self.subTest(task=rule['task_id'],change=old):self.assertFalse(verdict(bad)['passed'])
            self.assertIsNone(verdict(p))
            changed=deepcopy(p);changed['criterion']['requirement']+=' changed'
            self.assertIsNone(match(changed))

    def test_prose_judge_gets_source_sums_and_mandatory_exclusions(self):
        for rule,p in self.payloads():
            p['criterion']=rule['criteria']['professional_adequacy']
            projected=semantic_payload(p);facts=projected['registered_procurement_facts']
            self.assertEqual(facts['seven_year_csv_sums'],{'a':'955306','b':'875758','c':'1115141'})
            self.assertEqual(set(facts['excluded_suppliers']),{'B','C'})
            self.assertIn('does not authorize',facts['policy_precedence'])
            self.assertNotIn('registered_procurement_facts',p)
            self.assertIsNone(verdict(p))
            self.assertIn('registered_procurement_facts',verdict_input(p)[1]['content'])
            rendered=readable_evidence(projected)
            for name,value in p['evidence']['files'].items():
                self.assertIn(value['text'],rendered)
                self.assertIn(name,rendered)
            self.assertIn('BEGIN FILE',rendered)
            self.assertIn('overrides the general TCO',verdict_input(p)[0]['content'])
            changed=deepcopy(p);changed['evidence']['instruction']+=' changed'
            self.assertEqual(grading_rules(changed),'')


if __name__=='__main__':unittest.main()
