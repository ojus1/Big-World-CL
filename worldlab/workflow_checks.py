"""Registered source-bound workflow facts; prose remains separately assessed."""
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from scripts.source_world_calibration import read

REGISTRY = Path(__file__).with_name('workflow_registry.json')
COLUMNS = ['paquet','sous_traitant','zone','debut_jour','fin_jour','chevauchement_jours','violation_securite','statut_autorisation_reseau']
DURATIONS = [30,20,15,10,10,14]
TEAMS = [1,1,2,3,1,3]
ZONES = ['A','A','A','A','B','C']
OPTIMAL = [(1,30),(31,50),(51,65),(61,70),(51,60),(71,84)]
FALLBACK = [(1,30),(31,50),(51,65),(69,78),(51,60),(79,92)]
PERMITS = {
 'permis_excavation': {'date_emission':'2025-03-03','validite_jours':60,'date_expiration':'2025-05-01','dernier_paquet':'P5','fin_dernier_paquet':60,'conforme':True},
 'autorisation_reseau': {'date_emission':'2025-03-03','validite_jours':90,'date_expiration':'2025-05-31',
  'scenario_optimal':{'fin_projet':84,'conforme':True},
  'scenario_repli':{'fin_projet':92,'conforme':False,'jours_sans_autorisation':2,'prolongation_necessaire':True,'delai_demande_jours':15,'date_limite_demande':'2025-05-16'}}}

# NBN source §4.2 applies the 0.01 bar floor to every converted uncertainty.
# Decimal compares numerical values: 0.010 and 0.01 are equivalent.
UNCERTAINTIES = {s: {Decimal('0.01')} for s in ('2.1','2.2','3.2','4.1','5.1','6.1')}
UNCERTAINTIES.update({'4.2': {Decimal('0.011')}, '7.1': {Decimal('0.011'), Decimal('0.012')},
                      '5.4': {Decimal('0.020')}, '8.1': {Decimal('0.025')}})
SENSORS = {f'PD-4500-{s}': {Decimal('0.01' if s == 'C2' else '0.015')}
           for s in ('A1','A2','B1','B2','C1','C2')}


def uncertainty_errors(text, markdown=False):
    """Necessary numeric checks only; ambiguous prose stays with the model judge.

    Never auto-pass footnotes, conversion explanations, rounding provenance or
    format requirements merely because an extracted final number is correct.
    """
    records=[]
    if markdown:
        # Stop at the next heading; source-valued footnotes are not final values.
        parts=re.split(r'(?m)^#{1,6}\s+(\d+\.\d+)\b[^\n]*\n', text)
        for section,body in zip(parts[1::2],parts[2::2]):
            body=re.split(r'(?m)^#{1,6}\s|^\[\^[^]]+\]:',body)[0]
            if section in UNCERTAINTIES:records.append((section,body,UNCERTAINTIES[section]))
    else:
        reader=csv.DictReader(io.StringIO(text,newline=''),delimiter=';',strict=True)
        if reader.fieldnames != ['nr','abschnitt','typ','original','angepasst','status','bemerkung']:
            return []  # The independently graded structure obligation owns this.
        for row in reader:
            if None in row or any(v is None for v in row.values()):return []
            section=row['abschnitt'].strip();kind=row['typ'].strip()
            if kind=='unsicherheit' and section in UNCERTAINTIES:
                records.append((section,row['angepasst'],UNCERTAINTIES[section]))
            elif kind=='tabelle':
                ids=re.findall(r'PD-4500-[ABC][12]',row['original']+' '+row['angepasst'])
                if len(set(ids))==1 and ids[0] in SENSORS:
                    records.append((ids[0],row['angepasst'],SENSORS[ids[0]]))
    errors=[]
    for label,value,allowed in records:
        numbers=re.findall(r'±\s*(\d+(?:[.,]\d+)?)\s*bar\b',value)
        if len(numbers)!=1:continue
        number=Decimal(numbers[0].replace(',','.'))
        if number not in allowed:
            errors.append(f'{label}: final uncertainty {number} bar, expected '+
                          ' or '.join(str(v) for v in sorted(allowed))+' bar under the supplied conversion/minimum rule')
    return errors


def identical(a,b):
    if type(a) is not type(b):return False
    if isinstance(b,dict):return set(a)==set(b) and all(identical(a[k],v) for k,v in b.items())
    if isinstance(b,list):return len(a)==len(b) and all(identical(x,y) for x,y in zip(a,b))
    return a==b


def check_plan(text, fallback):
    reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
    if reader.fieldnames != COLUMNS:raise ValueError('Plan CSV must have the eight public columns')
    rows=list(reader)
    if len(rows)!=6 or {r['paquet'] for r in rows}!={f'P{i}' for i in range(1,7)}:
        raise ValueError('Plan must contain exactly P1–P6 once each')
    expected=FALLBACK if fallback else OPTIMAL
    for r in rows:
        if None in r or any(v is None for v in r.values()):raise ValueError('Malformed plan row')
        i=int(r['paquet'][1:])-1
        start,end=int(r['debut_jour']),int(r['fin_jour'])
        if end-start+1 != DURATIONS[i]:
            raise ValueError(f"{r['paquet']} duration is {end-start+1}, expected {DURATIONS[i]} inclusive days")
        if (start,end)!=expected[i]:raise ValueError(f"{r['paquet']} dates are {start}–{end}, expected {expected[i]}")
        if not re.match(r'^ST'+str(TEAMS[i])+r'(?:\s|_|$)',r['sous_traitant']) or r['zone']!=ZONES[i]:
            raise ValueError(f"{r['paquet']} team/zone differs from source")
        overlap=5 if not fallback and i in (2,3) else 0
        status='N/A' if i in (0,1,4) else 'expiré' if fallback and i==5 else 'conforme'
        if int(r['chevauchement_jours'])!=overlap or r['violation_securite']!=('OUI' if overlap else 'NON') or r['statut_autorisation_reseau']!=status:
            raise ValueError(f"{r['paquet']} overlap, safety or permit status is wrong")


def check_exams(files, identifier):
    def rows(path):
        reader=csv.DictReader(io.StringIO(files.get(path,{}).get('text',''),newline=''),strict=True)
        values=list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in values):
            raise ValueError('Malformed CSV: '+path)
        return reader.fieldnames,values
    header,plan=rows('output/pruefungsplan.csv')
    _,source=rows('input/einschreibungen.csv');expected={r['pruefung_id']:r for r in source}
    if header!=['pruefung_id','pruefung_name','woche','hoersaal','pruefer','typ']:
        raise ValueError('Exam plan has incorrect public columns')
    ids=[r['pruefung_id'] for r in plan]
    if len(ids)!=len(expected) or set(ids)!=set(expected):raise ValueError('Every source exam must occur exactly once')
    if identifier=='csv_row_ordering':
        if ids!=sorted(ids):raise ValueError('Exam rows are not sorted by ID')
        return
    for row in plan:
        src=expected[row['pruefung_id']]
        if row['pruefer']!=src['pruefer']:
            raise ValueError(row['pruefung_id']+': altered source examiner')
        if identifier!='constraint_satisfaction' and (row['pruefung_name']!=src['pruefung_name'] or row['typ'].replace('ü','ue')!=src['typ']):
            raise ValueError(row['pruefung_id']+': altered source name or exam type')
        if not 38<=int(row['woche'])<=49:raise ValueError('Week outside the public block')
    if identifier=='csv_structure_and_coverage':return
    _,rooms=rows('input/hoersaale.csv');rooms={r['raum_id']:r for r in rooms}
    _,modules=rows('input/modulmatrix.csv');modules={r['pruefung_id']:r for r in modules}
    _,blocked=rows('input/pruefer_verfuegbarkeit.csv')
    _,maintenance=rows('input/wartungsplan.csv')
    weeks={r['pruefung_id']:int(r['woche']) for r in plan};used_rooms=set();used_examiners=set()
    for row in plan:
        exam=row['pruefung_id'];week=weeks[exam];room=row['hoersaal'];examiner=row['pruefer'];src=expected[exam]
        if week>int(src['deadline_week']):raise ValueError(exam+': deadline exceeded')
        if room not in rooms or int(rooms[room]['kapazitaet'])<int(src['einschreibung']):
            raise ValueError(exam+': unknown room or insufficient capacity')
        if modules[exam]['ausstattung']=='Simulations-PCs' and room!='HS3':raise ValueError(exam+': missing simulation PCs')
        if any(r['raum_id']==room and int(r['woche'])==week for r in maintenance):raise ValueError(exam+': room closed')
        if any(r['pruefer']==examiner and int(r['woche_start'])<=week<=int(r['woche_ende']) for r in blocked):
            raise ValueError(exam+': examiner unavailable')
        prerequisite=modules[exam]['vorbedingung']
        if prerequisite and weeks[prerequisite]>=week:raise ValueError(exam+': prerequisite is not strictly earlier')
        if (room,week) in used_rooms or (examiner,week) in used_examiners:raise ValueError(exam+': room or examiner double booked')
        used_rooms.add((room,week));used_examiners.add((examiner,week))


def binding(payload):
    registry=read(REGISTRY);c=payload.get('criterion',{})
    if c.get('id') not in registry['criterion_ids']:return None
    evidence=payload.get('evidence',{});files=evidence.get('files',{})
    digest=hashlib.sha256(evidence.get('instruction','').encode()).hexdigest()
    matched=None
    for rule in registry['tasks'].values():
        if rule['instruction_sha256']!=digest or c not in rule['criteria']:continue
        if all(isinstance(files.get(p,{}).get('text'),str) and
               hashlib.sha256(files[p]['text'].replace('\r\n','\n').replace('\r','\n').encode()).hexdigest()==h
               for p,h in rule['input_text_sha256'].items()):matched=rule;break
    return matched


def semantic_payload(payload):
    rule=binding(payload)
    if rule is None or rule['kind']!='exams' or payload['criterion']['id']!='professional_adequacy':return payload
    try:check_exams(payload['evidence']['files'],'professional_adequacy')
    except (ValueError,KeyError,TypeError,csv.Error):return payload
    return {**payload,'registered_schedule_verification': {
        'method':'source_bound_csv_parser_and_constraint_predicates',
        'passed':['exact source exam identity and names','examiner and type values (muendlich/mündlich equivalence explicitly accepted)',
                  '14 unique exams','weeks within block','deadlines','strict prerequisites','examiner availability',
                  'one exam per examiner per week','room capacity','simulation equipment','room availability','one exam per room per week'],
        'scope':'These facts were checked independently against actual CSV fields and frozen sources. Do not invent a contradictory CSV clash or repeat the type-spelling penalty. Evaluate the remaining professional coherence, required Markdown, and correspondence of its claims with the submitted schedule. Passing CSV constraints does not certify the Markdown or any claimed search/validation procedure.'}}


def verdict(payload):
    matched=binding(payload)
    if matched is None:return None
    c=payload['criterion'];files=payload.get('evidence',{}).get('files',{})
    identifier=c['id'];path=matched['outputs'][identifier];reason='All registered source-bound workflow facts match.';passed=True
    def output(p):return files.get(p,{}).get('text','')
    try:
        if matched['kind']=='fiber':
            if identifier in ('optimal_plan_correctness','evidence_entailment_schedule'):
                check_plan(output('output/plan_travaux.csv'),False)
            if identifier in ('fallback_plan_correctness','evidence_entailment_schedule'):
                check_plan(output('output/plan_repli.csv'),True)
            if identifier in ('permit_analysis_json','evidence_entailment_schedule'):
                if not identical(json.loads(output('output/analyse_permis.json')),PERMITS):
                    raise ValueError('Permit JSON differs from the public schedule/permit calculation: optimal day 84, fallback day 92, two uncovered days, application deadline 2025-05-16')
        elif matched['kind']=='housing':
            value=json.loads(output(path))
            expected={'allocation_id':'AL-2025-0142','etudiant_id':'ETU-2024-0847','chambre_actuelle':'CH-003',
                      'date_analyse':'2025-03-14','etat_actuel':'PROVISOIRE','jours_en_etat':12,
                      'flags_actifs':['CERTIFICAT_EXPIRE','SEUIL_PROVISOIRE_DEPASSE']}
            if any(not identical(value.get(k),v) for k,v in expected.items()):raise ValueError('Core allocation facts, types or sorted flags differ from the source')
            rooms=value['recherche_alternative']['chambres_rdc_eligibles']
            if rooms not in [['CH-001','CH-004','CH-006'],['CH-004','CH-006']]:
                raise ValueError('CH-004 and CH-006 must remain eligible; CH-001 may be included or transparently held for its source-journal conflict. Extra exclusion reasoning is assessed separately.')
        elif matched['kind']=='uncertainty':
            errors=uncertainty_errors(output(path),markdown=path.endswith('.md'))
            if errors:raise ValueError('; '.join(errors))
            return None  # Numeric correctness does not discharge semantic obligations.
        elif matched['kind']=='exams':
            if identifier=='md_paragraph14_handling':
                if not output('output/konfliktloesungen.md').strip():raise ValueError('Required Markdown is missing')
                return None
            check_exams(files,identifier)
            if identifier=='professional_adequacy':return None
        else:raise RuntimeError('Unknown registered workflow kind')
    except (ValueError,KeyError,TypeError,csv.Error) as exc:passed=False;reason=str(exc)
    return {'criterion_id':identifier,'passed':passed,'evidence':path,'reasoning':reason}
