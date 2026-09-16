import csv
from copy import deepcopy
import hashlib
import io,json
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts.source_world_calibration import save
from worldlab import workflow_checks as w
from worldlab.qualitative import request_verdict


def plan(fallback=False):
    intervals=[(1,30),(31,50),(51,65),(69,78),(51,60),(79,92)] if fallback else [(1,30),(31,50),(51,65),(61,70),(51,60),(71,84)]
    rows=[]
    for i,(start,end) in enumerate(intervals):
        overlap=5 if not fallback and i in (2,3) else 0
        rows.append(dict(zip(w.COLUMNS,[f'P{i+1}', ['ST1','ST1','ST2','ST3','ST1','ST3'][i], ['A','A','A','A','B','C'][i],start,end,overlap,'OUI' if overlap else 'NON','N/A' if i in (0,1,4) else 'expiré' if fallback and i==5 else 'conforme'])))
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=w.COLUMNS);writer.writeheader();writer.writerows(rows)
    return stream.getvalue()


class WorkflowTests(unittest.TestCase):
    def rule(self,kind,criteria,outputs):
        return {'criterion_ids':[c['id'] for c in criteria],'tasks':{'fixture':{'kind':kind,'criteria':criteria,'outputs':outputs,
            'instruction_sha256':hashlib.sha256(b'Workflow').hexdigest(), 'input_text_sha256':{'input/source.md':hashlib.sha256(b'Source').hexdigest()}}}}

    def test_inclusive_duration_and_fallback_mutation_are_consistent_across_criteria(self):
        identifiers=['optimal_plan_correctness','fallback_plan_correctness','permit_analysis_json','evidence_entailment_schedule']
        criteria=[{'id':i,'requirement':i,'weight':1} for i in identifiers]
        outputs=dict(zip(identifiers,['output/plan_travaux.csv','output/plan_repli.csv','output/analyse_permis.json','output/analyse_permis.json']))
        files={'input/source.md':{'text':'Source'},'output/plan_travaux.csv':{'text':plan()},'output/plan_repli.csv':{'text':plan(True)},'output/analyse_permis.json':{'text':json.dumps(w.PERMITS)}}
        with tempfile.TemporaryDirectory() as tmp:
            registry=Path(tmp)/'registry.json';save(registry,self.rule('fiber',criteria,outputs))
            with patch.object(w,'REGISTRY',registry):
                for c in criteria:
                    p={'criterion':c,'evidence':{'instruction':'Workflow','files':files}}
                    self.assertTrue(w.verdict(p)['passed'])
                    self.assertEqual(request_verdict(None,None,p,1).evaluation_method,'registered_workflow_source_predicate')
                bad=deepcopy(files);bad['output/plan_repli.csv']['text']=bad['output/plan_repli.csv']['text'].replace(',79,92,',',79,91,')
                for c in [criteria[1],criteria[3]]:
                    result=w.verdict({'criterion':c,'evidence':{'instruction':'Workflow','files':bad}})
                    self.assertFalse(result['passed']);self.assertIn('13',result['reasoning'])
                bad=deepcopy(files);permit=deepcopy(w.PERMITS);permit['autorisation_reseau']['scenario_repli']['jours_sans_autorisation']=1
                bad['output/analyse_permis.json']['text']=json.dumps(permit)
                for c in [criteria[2],criteria[3]]:self.assertFalse(w.verdict({'criterion':c,'evidence':{'instruction':'Workflow','files':bad}})['passed'])
                for field in ['source','instruction','criterion']:
                    p={'criterion':deepcopy(criteria[0]),'evidence':{'instruction':'Workflow','files':deepcopy(files)}}
                    if field=='source':p['evidence']['files']['input/source.md']['text']+='!'
                    if field=='instruction':p['evidence']['instruction']+='!'
                    if field=='criterion':p['criterion']['weight']=2
                    self.assertIsNone(w.verdict(p))

    def test_housing_accepted_alternative_preserves_uncontested_rooms_and_types(self):
        c={'id':'core_json_facts','requirement':'Registered facts','weight':3};path='output/decision_workflow.json'
        value={'allocation_id':'AL-2025-0142','etudiant_id':'ETU-2024-0847','chambre_actuelle':'CH-003','date_analyse':'2025-03-14','etat_actuel':'PROVISOIRE','jours_en_etat':12,'flags_actifs':['CERTIFICAT_EXPIRE','SEUIL_PROVISOIRE_DEPASSE'],'recherche_alternative':{}}
        with tempfile.TemporaryDirectory() as tmp:
            registry=Path(tmp)/'registry.json';save(registry,self.rule('housing',[c],{c['id']:path}))
            with patch.object(w,'REGISTRY',registry):
                for rooms,passed in [(['CH-001','CH-004','CH-006'],True),(['CH-004','CH-006'],True),([],False),(['CH-004'],False),(['CH-004','CH-005','CH-006'],False)]:
                    value['recherche_alternative']['chambres_rdc_eligibles']=rooms
                    p={'criterion':c,'evidence':{'instruction':'Workflow','files':{'input/source.md':{'text':'Source'},path:{'text':json.dumps(value)}}}}
                    self.assertEqual(w.verdict(p)['passed'],passed)
                value['recherche_alternative']['chambres_rdc_eligibles']=['CH-004','CH-006'];value['jours_en_etat']='12'
                p['evidence']['files'][path]['text']=json.dumps(value)
                self.assertFalse(w.verdict(p)['passed'])

    def test_uncertainty_veto_rejects_false_full_pass_without_accepting_prose(self):
        header='nr;abschnitt;typ;original;angepasst;status;bemerkung\n'
        c={'id':'csv_conversion_values','requirement':'Source minimum','weight':3}
        path='output/adaptationsprotokoll.csv'
        with tempfile.TemporaryDirectory() as tmp:
            registry=Path(tmp)/'registry.json';save(registry,self.rule('uncertainty',[c],{c['id']:path}))
            with patch.object(w,'REGISTRY',registry):
                for value,failed in [('0,006',True),('0.01',False),('0,010',False)]:
                    text=header+f'1;2.1;unsicherheit;±0,008 bar;±{value} bar;UNS_KONVERTIERT;Source §4.2\n'
                    payload={'criterion':c,'evidence':{'instruction':'Workflow','files':{'input/source.md':{'text':'Source'},path:{'text':text}}}}
                    result=w.verdict(payload)
                    if failed:
                        self.assertFalse(result['passed'])
                        self.assertEqual(request_verdict(None,None,payload,1).evaluation_method,'registered_workflow_source_predicate')
                    else:self.assertIsNone(result)
                payload['evidence']['instruction']='Changed';self.assertIsNone(w.verdict(payload))
        for section,wrong,right in [('4.2','0.015','0.011'),('7.1','0.006','0.012'),('5.4','0.01','0.020')]:
            self.assertTrue(w.uncertainty_errors(f'### {section} Topic\nU = ±{wrong} bar.\n',markdown=True))
            self.assertFalse(w.uncertainty_errors(f'### {section} Topic\nU = ±{right} bar.\n\n[^1]: Original U = ±{wrong} bar.\n',markdown=True))
        self.assertFalse(w.uncertainty_errors('### 7.1 Topic\nU = ±0,011 bar.\n',markdown=True))
        for sensor,number,failed in [('A1','0,01',True),('C2','0,010',False),('C2','0,00',True)]:
            text=header+f'1;7.3;tabelle;PD-4500-{sensor} ±0,02 bar;PD-4500-{sensor} ±{number} bar;UNS_TABELLE;Source\n'
            self.assertEqual(bool(w.uncertainty_errors(text)),failed)

    def test_exam_constraint_mutations_are_independent_of_model_judgments(self):
        files={
            'input/einschreibungen.csv':{'text':'pruefung_id,pruefung_name,pruefer,einschreibung,deadline_week,typ\nP01,A,One,40,41,schriftlich\nP02,B,One,20,43,muendlich\nP03,C,Two,20,43,schriftlich\n'},
            'input/modulmatrix.csv':{'text':'pruefung_id,ausstattung,vorbedingung\nP01,Standard,\nP02,Simulations-PCs,P01\nP03,Standard,\n'},
            'input/hoersaale.csv':{'text':'raum_id,kapazitaet\nHS1,80\nHS2,30\nHS3,60\n'},
            'input/pruefer_verfuegbarkeit.csv':{'text':'pruefer,woche_start,woche_ende\nOne,39,39\n'},
            'input/wartungsplan.csv':{'text':'raum_id,woche\nHS3,42\n'},
        }
        valid='pruefung_id,pruefung_name,woche,hoersaal,pruefer,typ\nP01,A,38,HS1,One,schriftlich\nP02,B,40,HS3,One,mündlich\nP03,C,38,HS2,Two,schriftlich\n'
        files['output/pruefungsplan.csv']={'text':valid}
        for identifier in ('csv_row_ordering','csv_structure_and_coverage','constraint_satisfaction'):
            w.check_exams(files,identifier)
        for old,new,reason in [('P01,A,38,HS1','P01,A,38,HS2','capacity'),('P02,B,40','P02,B,39','unavailable'),
                               ('P02,B,40','P02,B,42','closed'),('P02,B,40','P02,B,38','prerequisite'),
                               ('P02,B,40','P02,B,44','deadline'),('P03,C,38,HS2','P03,C,38,HS1','double booked'),
                               ('P02,B,40,HS3','P02,B,40,HS1','PCs')]:
            files['output/pruefungsplan.csv']['text']=valid.replace(old,new)
            with self.assertRaisesRegex(ValueError,reason):w.check_exams(files,'constraint_satisfaction')


if __name__=='__main__':unittest.main()
