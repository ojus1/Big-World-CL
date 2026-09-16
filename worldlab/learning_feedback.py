"""Prioritize released failures without changing grades or exposing private rubrics."""

POLICY = 'released_failures_first_v2'


def learning_feedback(grade):
    original=grade.get('feedback','')
    failures=[];passed=[]
    for rubric in grade.get('criteria',[]):
        if 'criteria_results' in rubric:
            rows=[(f"Rubric {rubric['index']}, subcriterion {row['index']}",row)
                  for row in rubric['criteria_results']]
        else:rows=[(rubric.get('criterion_id',''),rubric)]
        for label,row in rows:
            if not label or type(row.get('passed')) is not bool or not isinstance(row.get('reasoning'),str):continue
            if row['passed']:passed.append(label)
            else:failures.append(label+': '+row['reasoning'])
    for row in grade.get('public_requirements', {}).get('checks', []):
        if not row.get('id') or type(row.get('passed')) is not bool:continue
        if row['passed']:continue
        # The grader already releases this exact requirement and evidence in
        # its original feedback. Include its failure alongside rubric failures.
        failures.append(row['id']+': '+row['requirement']+' '+' '.join(row['evidence']))
    if not failures:return original
    # Use only IDs and rationales already present in released feedback. Never
    # attach the private criterion text or hidden source definition here.
    return ('Released evaluator failures (fallible; verify against task sources):\n- '+
            '\n- '.join(failures)+'\nReported passing checks: '+', '.join(passed)+
            '\n\nComplete original released feedback:\n'+original)
