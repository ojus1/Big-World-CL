"""Rebuild causal workplace state and bind each decision to native evidence."""
from pathlib import Path
from scripts.source_world_calibration import read, sha
from .campaign import SEED_SKILL
from .workplace import Workplace
from .worlds import stable_hash


def require(value, message):
    if not value: raise ValueError(message)


def replay_commands(bank, world, state):
    place = Workplace(world)
    decisions = iter(state['decisions'])
    sessions = {s['id']: s for s in state['sessions']}
    require(len(sessions) == len(state['sessions']), 'Duplicate online session')
    visited = set()
    for command in state['workplace']['commands']:
        op, args = command['operation'], command['arguments']
        if op == 'decide':
            decision = next(decisions, None)
            require(decision is not None and decision['day'] == place.day and
                    decision['employee_id'] == args['employee_id'] and
                    decision['obligation_id'] == args['obligation_id'] and decision['decision'] == args['decision'],
                    'Decision chronology or identity differs from workplace command')
            require(decision['view'] == place.view(args['employee_id'], args['obligation_id'], bank),
                    'Actor view includes different or unreleased information')
            require(decision['session_id'] == (decision['id'] if args['decision']['delegate'] else None),
                    'Deferral/delegation changed')
        elif op == 'start':
            sid = args['session_id']
            require(sid in sessions and sid not in visited, 'Unrecorded or duplicate work start')
            visited.add(sid)
            session = sessions[sid]
            original = place.arrivals[args['obligation_id']]
            require(session['employee_id'] == original['employee_id'] and session['day'] == place.day and
                    session['employee_message'] == decision['decision']['request'] and
                    session['obligation_id'] == original['id'] and
                    all(session[k] == original[k] for k in ('task_id', 'split', 'lineage_group', 'work_budget', 'due_day')) and
                    session['feedback_day'] == place.day + place.delay, 'Work request differs from delegation')
        elif op == 'complete':
            session = sessions[args['session_id']]
            require(session['status'] == 'completed' and session['grade']['grading_complete'] and
                    args['outcome'] == {k: session['grade'][k] for k in ('success', 'quality_score', 'feedback')},
                    'Workplace outcome differs from grading evidence')
        require(op in ('advance', 'decide', 'start', 'complete'), 'Unknown workplace operation')
        getattr(place, op)(**args)
    require(next(decisions, None) is None and visited == set(sessions), 'Untracked decision or online session')
    require(place.state == state['workplace'], 'Persistent workplace differs from causal replay')
    return place


def audit_workplaces(bank, out, study, harness, learner):
    from .audit_worlds import audit_attempt, audit_updates
    from .employees import audit_native_decision
    from .organization_graph import declarations
    require(study['employee_driver']['name'] == 'native_mirofish_persona_employees',
            'Supply an auditor for this employee driver')
    counts = {'online_attempts': 0, 'learning_replays': 0, 'adoptions': 0, 'world_pairs': 0,
              'native_employee_decisions': 0, 'actor_interview_tokens': 0}
    for world in study['worlds']:
        require(world['bank_manifest_sha256'] == bank.verification['manifest_sha256'], 'Bank changed')
        for name in ('no_learning', study['learner']['name']):
            root = Path(out) / 'worlds' / f'seed-{world["seed"]}' / name
            state, report = read(root / 'STATE.json'), read(root / 'REPORT.json')
            require(report['status'] == 'completed' and not (root / 'INFLIGHT.json').exists(), 'World incomplete')
            place = replay_commands(bank, world, state)
            require(place.summary() == report['workplace'], 'Workplace report differs from causal replay')
            require(read(root / 'actors/PERSONAS.json') == world['employee_context'], 'Persona assignment changed')
            seed = read(root / 'actors/NATIVE_GRAPH_SEED.json')
            require(seed['declared'] == declarations(world['workforce']) and seed['model_calls'] == 0 and
                    seed['source_sha256'] == study['employee_driver']['graph_compiler_sha256'],
                    'Native organization graph differs from declared assignments')
            calls, tokens = 0, 0
            cache_keys = set()
            for decision in state['decisions']:
                receipts = audit_native_decision(root / 'actors', study['employee_driver'],
                    decision['view'], decision['decision'], decision['id'])
                calls += len(receipts); tokens += sum(r['total_tokens'] for r in receipts)
                cache_keys.add(decision['id'])
                if len(receipts) == 2: cache_keys.add(decision['id'] + '-repair')
                counts['native_employee_decisions'] += 1
            ledger = read(root / 'actors/evaluation_interview_ledger.json')
            require({r['key'] for r in ledger['requests']} == cache_keys and len(ledger['requests']) == len(cache_keys),
                    'Untracked actor request')
            require({p.stem for p in (root / 'actors/mirofish_interviews').glob('*.json')} == cache_keys,
                    'Untracked actor cache')
            require(report['actor_usage']['model_calls'] == calls and report['actor_usage']['tokens'] == tokens,
                    'Actor accounting differs from verified native receipts')
            counts['actor_interview_tokens'] += tokens
            for session in state['sessions']:
                past = [u for u in state['updates'] if u['employee_id'] == session['employee_id'] and
                        u['day'] < session['day'] and u['result']['accepted']]
                skill = past[-1]['result']['skill'] if past else SEED_SKILL
                record = audit_attempt(bank, root / 'sessions' / session['id'], session['task_id'], skill, harness,
                                       employee_message=session['employee_message'])
                require(record['grade'] == session['grade'] and record['tokens'] == session['tokens'] and
                        sha(root / 'sessions' / session['id'] / 'ATTEMPT.json') == session['attempt_sha256'],
                        'Session receipt changed')
                counts['online_attempts'] += 1
            audit_updates(bank, world, root, state, name, harness, counts, learner, study['learner'])
            require(report['world_schedule_sha256'] == stable_hash(world), 'World identity changed')
            require(report['work_and_judging_tokens'] == sum(s['tokens'] for s in state['sessions']) and
                    report['learning_and_replay_judging_tokens'] == sum(u['result']['costs']['tokens'] for u in state['updates']),
                    'World model costs changed')
            for metric in ('probe_quality_mean', 'probe_accepted_on_time_fraction'):
                require(report[metric] == place.summary()[metric], 'Primary or secondary metric changed')
        counts['world_pairs'] += 1
    return {'ok': True, **counts, 'bootstrap_and_social_tokens': None,
            'scope': 'Causal state, native interviews, skill gate, work and replay audit; no certification of judgment truth or final significance.'}
