"""Source-bound paragraph-level review of fictitious exam-conflict claims."""
import csv
import io
import re
from .workflow_checks import binding,check_exams

METHOD='registered_exam_prose_sections_v1'
OUTPUT='output/konfliktloesungen.md'
IDS={'md_paragraph14_handling','professional_adequacy'}


def sections(files):
    text=files.get(OUTPUT,{}).get('text','')
    return {f'S{i:03d}':part for i,part in enumerate(
        p for p in re.split(r'(?m)(?=^#{1,6}\s)',text) if p.strip())}


def registered(payload):
    rule=binding(payload)
    return (rule is not None and rule['kind']=='exams'
            and payload['criterion']['id'] in IDS and bool(sections(payload['evidence']['files'])))


def certificate(files):
    """Validate a constructive feasible schedule from actual, pinned source rows.

    No optimizer/search claim is needed. One legal schedule suffices to disprove
    the supplied §14.3 trigger 'without the priority rule no legal plan exists'.
    """
    assignments=[(40,'HS4'),(41,'HS3'),(42,'HS2'),(39,'HS1'),(41,'HS4'),
                 (40,'HS2'),(38,'HS2'),(39,'HS2'),(40,'HS1'),(42,'HS1'),
                 (38,'HS5'),(47,'HS1'),(38,'HS4'),(38,'HS6')]
    source=list(csv.DictReader(io.StringIO(files['input/einschreibungen.csv']['text'])))
    if [r['pruefung_id'] for r in source]!=[f'P{i:02d}' for i in range(1,15)]:
        raise ValueError('The registered feasibility witness requires its original source IDs')
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['pruefung_id','pruefung_name','woche','hoersaal','pruefer','typ'])
    for row,(week,room) in zip(source,assignments):
        writer.writerow([row['pruefung_id'],row['pruefung_name'],week,room,row['pruefer'],row['typ']])
    text=stream.getvalue()
    check_exams({**files,'output/pruefungsplan.csv':{'text':text}},'professional_adequacy')
    return text


def semantic_payload(payload):
    if not registered(payload):return payload
    return {**payload,'independent_feasible_schedule_certificate':certificate(payload['evidence']['files']),
        'candidate_markdown_sections':sections(payload['evidence']['files']),
        'evaluation_scope':(
            'The trusted checker validated the attached independent schedule against every supplied CSV constraint. '
            'The source §14.3 explicitly says the priority rule is activated only if NO legal schedule exists without it. '
            'Thus this pinned instance needs no §14 resolution. Greedy earliest-week choices, invented requests, '
            'or voluntarily exhausting earlier slots do not create a source-mandated conflict. '
            'The witness also disproves claims that P01 must be in week 38 or P04 must be in week 38. '
            'Read each candidate Markdown section separately. Set claims_actual_priority_resolution true if '
            'that section asserts that a §14 priority conflict occurred, was necessary, or was actually resolved '
            'in this task. This includes claims contradicted by other sections; a final disclaimer does not erase '
            'an earlier affirmative claim. Hypothetical explanations explicitly not applied and clear denials '
            'are false. Give a short reason grounded in that section. Do not endorse a claimed exhaustive search '
            'merely because the candidate says it ran one. Separately assess all remaining requirements of the '
            'supplied criterion, including source fidelity, language, completeness and CSV/Markdown correspondence '
            'where that criterion requires them. Return the requested section judgments, evidence, reasoning and '
            'remaining_requirements_satisfied. The host computes the final conjunction.')}


def schema(payload):
    if not registered(payload):return None
    row={'type':'object','properties':{'reasoning':{'type':'string'},
        'claims_actual_priority_resolution':{'type':'boolean'}},
        'required':['reasoning','claims_actual_priority_resolution'],'additionalProperties':False}
    rows={key:row for key in sections(payload['evidence']['files'])}
    props={'criterion_id':{'type':'string','enum':[payload['criterion']['id']]},
        'sections':{'type':'object','properties':rows,'required':list(rows),'additionalProperties':False},
        'evidence':{'type':'string','enum':sorted(payload['evidence']['files'])},
        'reasoning':{'type':'string'},'remaining_requirements_satisfied':{'type':'boolean'}}
    return {'json':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}


def parse(value,criterion,files):
    keys={'criterion_id','sections','evidence','reasoning','remaining_requirements_satisfied'}
    if (not isinstance(value,dict) or set(value)!=keys or value['criterion_id']!=criterion['id']
        or value['evidence'] not in files or not isinstance(value['reasoning'],str)
        or type(value['remaining_requirements_satisfied']) is not bool
        or not isinstance(value['sections'],dict) or set(value['sections'])!=set(sections(files))):
        raise ValueError('Malformed source-bound exam section judgments')
    failures=[]
    for key,row in value['sections'].items():
        if (not isinstance(row,dict) or set(row)!={'reasoning','claims_actual_priority_resolution'}
            or not isinstance(row['reasoning'],str) or type(row['claims_actual_priority_resolution']) is not bool):
            raise ValueError('Malformed exam section claim')
        if row['claims_actual_priority_resolution']:failures.append(key+': '+row['reasoning'])
    return {'criterion_id':criterion['id'],'passed':not failures and value['remaining_requirements_satisfied'],
        'evidence':value['evidence'],'reasoning':'; '.join(failures) if failures else value['reasoning'],
        'section_checks':value['sections'],'remaining_requirements_satisfied':value['remaining_requirements_satisfied']}
