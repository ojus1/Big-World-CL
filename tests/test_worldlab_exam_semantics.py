from copy import deepcopy
import unittest
from worldlab.exam_semantics import sections,parse


class ExamSemanticTests(unittest.TestCase):
    def test_final_disclaimer_cannot_erase_an_earlier_claim(self):
        files={'output/konfliktloesungen.md':{'text':'# Conflict\nP07 won under paragraph 14.\n## Conclusion\nNo conflict occurred.\n'}}
        criterion={'id':'md_paragraph14_handling'}
        self.assertEqual(list(sections(files)),['S000','S001'])
        value={'criterion_id':criterion['id'],'evidence':'output/konfliktloesungen.md','reasoning':'Final denial.',
            'remaining_requirements_satisfied':True,'sections':{
                'S000':{'reasoning':'Claims an actual resolution.','claims_actual_priority_resolution':True},
                'S001':{'reasoning':'Denies a conflict.','claims_actual_priority_resolution':False}}}
        self.assertFalse(parse(value,criterion,files)['passed'])
        # Omitting the inconvenient paragraph is an invalid structured response.
        incomplete=deepcopy(value);del incomplete['sections']['S000']
        with self.assertRaises(ValueError):parse(incomplete,criterion,files)
        value['sections']['S000']['claims_actual_priority_resolution']=False
        self.assertTrue(parse(value,criterion,files)['passed'])
        value['remaining_requirements_satisfied']=False
        self.assertFalse(parse(value,criterion,files)['passed'])

    def test_unknown_sections_and_truthy_strings_are_rejected(self):
        files={'output/konfliktloesungen.md':{'text':'No priority resolution was required.'}}
        criterion={'id':'professional_adequacy'}
        value={'criterion_id':criterion['id'],'evidence':'output/konfliktloesungen.md','reasoning':'Coherent.',
            'remaining_requirements_satisfied':True,'sections':{'S000':{'reasoning':'Denial.','claims_actual_priority_resolution':False}}}
        self.assertTrue(parse(value,criterion,files)['passed'])
        bad=deepcopy(value);bad['sections']['S001']=bad['sections']['S000']
        with self.assertRaises(ValueError):parse(bad,criterion,files)
        bad=deepcopy(value);bad['sections']['S000']['claims_actual_priority_resolution']='false'
        with self.assertRaises(ValueError):parse(bad,criterion,files)


if __name__=='__main__':unittest.main()
