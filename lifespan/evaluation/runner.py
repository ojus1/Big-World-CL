"""Chronological native-actor experiments and isolated SkillOpt candidate trials.

Run with the installed MiroFish Python environment. Private checkpoints and
rubrics remain outside every employee computer. A work score is recorded before
it can enter that employee's later learning pool.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time

from ..computers import HERMES
from ..ecosystem import Ecosystem, WORKFLOWS
from ..ecosystem_run import actor_prompt, native_decision
from ..integrated import EMPLOYEE_PROMPT, employee_view, validate_decision, enact_proposal
from ..mirofish import MiroFishRuntime, ROOT, imports, save
from ..personas import import_cohort
from .protocol import ExperimentConfig, SEED_SKILL, digest, experience_split, regime_at, scenario, select_experiences
from .runtime import execute_case
from .tasks import make_case


class ReportPostprocessingError(RuntimeError):
    """Completed execution is preserved when its derived report cannot finish."""


def source_hashes():
    files = sorted((ROOT / 'lifespan').rglob('*.py'))
    files.append(ROOT / 'scripts/evaluation_report_v2.py')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if '/tests/' not in str(p) and '/artifacts/' not in str(p)}


def dependency_provenance():
    result = {}
    for name, root in [('hermes', HERMES), ('mirofish', ROOT / 'MiroFish'), ('skillopt', ROOT / '.cache/SkillOpt')]:
        try:
            revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
            delta = subprocess.check_output(['git', '-C', str(root), 'diff', 'HEAD', '--', '*.py'])
            result[name] = {'revision': revision, 'tracked_python_diff_sha256': hashlib.sha256(delta).hexdigest()}
        except (OSError, subprocess.CalledProcessError):
            result[name] = {'revision': None}
    return result


def credentials():
    imports()
    from app.config import Config
    return {'model': Config.LLM_MODEL_NAME, 'base_url': Config.LLM_BASE_URL, 'api_key': Config.LLM_API_KEY}


def safe_trajectory(record):
    # Whitelist visible messages/calls; never include native transport state,
    # grader truth, diagnostic.expected_procedure or another employee's context.
    messages = []
    for m in record['result']['native'].get('messages', []):
        if m.get('role') not in ('user', 'assistant', 'tool'):
            continue
        messages.append({k: m[k] for k in ('role', 'content', 'tool_calls', 'tool_call_id', 'name') if k in m})
    return json.dumps({'messages': messages, 'feedback': record['feedback']}, ensure_ascii=False)


class NativeActors:
    def __init__(self, out, eco, spec, *, deadline=None):
        participants = eco.participants()
        cohort_path = out / 'persona_cohort.json'
        cohort = json.loads(cohort_path.read_text()) if cohort_path.exists() else import_cohort(
            ROOT / 'lifespan/data/persona8b', cohort_path, count=len(participants), seed=spec['seed'])
        self.runtime = MiroFishRuntime(out / 'actors')
        if deadline is not None:
            self.runtime.evaluation_deadline = deadline
        if self.runtime.state.get('closed'):
            raise RuntimeError('Native MiroFish state was closed; restarting would reset its actor database')
        if self.runtime.state.get('started'):
            alive = self.runtime.call('/api/simulation/env-status',
                {'simulation_id': self.runtime.state['simulation']['simulation_id']})
            if not alive.get('env_alive'):
                raise RuntimeError('Native MiroFish environment no longer alive; refusing destructive database restart')
        self.runtime.bootstrap({'name': 'Big World CL controlled learning evaluation', 'employees': participants,
            'rules': [], 'project_name': 'Big World CL evaluation',
            'ecosystem_description': 'Two competing service enterprises, one government agency, three consumers, '
                'and six employees. A documented exogenous benchmark workload supplements consumer orders. '
                'The institutions react to their own outcomes and current public conditions.'}, cohort)

    def set_deadline(self, deadline):
        self.runtime.evaluation_deadline = deadline

    def institutional(self, eco, actor, view, key):
        return native_decision(self.runtime, actor, actor_prompt(view), key,
            lambda a: Ecosystem.restore(eco.checkpoint()).apply_decision(actor, a, view))

    def employee(self, eco, task, employee, notes, case, key):
        fid = employee.split('__')[0]
        w = eco.worlds[fid]
        view = employee_view(w, task, {task.owner: notes.get(employee, '')},
                             {task.owner: eco.feedback.get(employee)}, {})
        view['enterprise_objectives'] = deepcopy(eco.firms[fid])
        view['enterprise_objectives'].pop('cash', None)
        view['geopolitical_bulletin'] = deepcopy(eco.geopolitics)
        view['received_colleague_messages'] = deepcopy(getattr(self, 'mailbox', {}).get(employee, []))
        view['colleagues'] = [e for e in w.employees if e != task.owner]
        view['substantive_work'] = case['request']
        prompt = (EMPLOYEE_PROMPT + '\nThis evaluation measures delegated work: delegate must be true. '
            'Set a useful request for your Hermes assistant to perform the substantive work with its real '
            'filesystem. Do not solve or invent the unseen task data. Keep your working notes based on '
            'observed outcomes.\n' + json.dumps(view))
        def check(a):
            validate_decision(a, view)
            if a['delegate'] is not True:
                raise ValueError('This controlled delegation protocol requires delegate=true')
        return native_decision(self.runtime, employee, prompt, key, check), view

    def pause(self):
        # Keep the native environment and its database alive for exact resume.
        self.runtime.client.close()

    def close(self):
        self.runtime.close()


def _new_state(config, spec):
    eco = Ecosystem(config.days + 8, spec['seed'])
    eco.shock_schedule = spec['shock_schedule']
    if any(w.blueprint['settlement_delay'] != spec['settlement_delay'] for w in eco.worlds.values()):
        raise ValueError('Scenario settlement delay differs from economy')
    for c in eco.consumers.values():
        c['budget'] = 10000.0
    for f in eco.firms.values():
        f['daily_capacity'] = 3
    employees = [p['id'] for p in eco.participants() if p['entity_type'] == 'Employee']
    if config.focal_employee is not None and config.focal_employee not in employees:
        raise ValueError('Unknown focal employee')
    state = {'phase': 'advance', 'actor_index': 0, 'work_index': 0, 'update_index': 0,
             'notes': {}, 'skills': {e: SEED_SKILL for e in employees},
             'skill_versions': {e: 0 for e in employees}, 'experiences': [], 'sessions': [],
             'updates': [], 'business_archive': {}, 'message_queue': [], 'mailbox': {}, 'learning_calls': 0, 'learning_tokens': 0,
             'elapsed_seconds': 0.0}
    return eco, state


def run_experiment(out, config, *, actor_factory=NativeActors, executor=execute_case, creds=None,
                   stop_after_sessions=None):
    if stop_after_sessions is not None and (type(stop_after_sessions) is not int or stop_after_sessions < 1):
        raise ValueError('stop_after_sessions must be a positive invocation limit')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    spec = scenario(config)
    creds = creds or credentials()
    started = time.monotonic()
    manifest = {'config': config.public(), 'scenario': spec, 'source_sha256': source_hashes(),
                'target_model': creds['model'], 'model_base_url': creds['base_url'],
                'dependencies': dependency_provenance(),
                'state_contract': 'Fresh private agent state each task; native skill is the learning treatment.',
                'environment_actor_usage': {'tokens': None, 'currency_cost': None,
                    'reason': 'Native MiroFish interview API does not expose complete aggregate usage.'},
                'sampling': 'Hosted model randomness is not controlled by the scenario seed.'}
    saved = out / 'checkpoint.json'
    if (out / 'INFLIGHT.json').exists():
        raise RuntimeError('An interrupted action needs reconciliation; refusing automatic replay')
    if (out / 'REPORT.json').exists() and json.loads((out / 'REPORT.json').read_text()).get('status') == 'completed':
        raise ValueError('Completed experiment exists; choose a new output')
    if saved.exists():
        existing = json.loads((out / 'manifest.json').read_text())
        if existing != manifest:
            raise ValueError('Configuration, provider or source differs from the checkpoint')
        cp = json.loads(saved.read_text()); eco = Ecosystem.restore(cp['ecosystem']); state = cp['runner']
    else:
        eco, state = _new_state(config, spec)
        save(out / 'manifest.json', manifest)
    elapsed_before = state['elapsed_seconds']
    initial_sessions = len(state['sessions'])
    deadline = started + config.max_run_seconds - elapsed_before
    def remaining_seconds():
        return max(0, deadline - time.monotonic())
    def checkpoint():
        state['elapsed_seconds'] = elapsed_before + time.monotonic() - started
        save(saved, {'ecosystem': eco.checkpoint(), 'runner': state})
    def begin(kind, key):
        save(out / 'INFLIGHT.json', {'kind': kind, 'key': key, 'day': eco.day})
    def finish():
        checkpoint(); (out / 'INFLIGHT.json').unlink(missing_ok=True)
    def report(status):
        from .metrics import build_report
        provenance = {k: manifest[k] for k in ('target_model', 'model_base_url', 'dependencies', 'source_sha256')}
        cohort_path = out / 'persona_cohort.json'
        provenance['persona_cohort_sha256'] = (hashlib.sha256(cohort_path.read_bytes()).hexdigest()
            if cohort_path.exists() else 'offline-fixture-no-personas')
        provenance['actor_driver'] = actor_factory.__module__ + '.' + actor_factory.__name__
        provenance['executor'] = executor.__module__ + '.' + executor.__name__
        result = build_report(config.public(), spec, state['sessions'], state['updates'], eco.snapshot(),
                              status=status, provenance=provenance)
        save(out / 'timeline.json', eco.events)
        save(out / 'REPORT.json', result)
        if status == 'completed':
            # Keep the frozen availability-based report for historical auditing;
            # publish the corrected commitment headline for every new full run.
            try:
                from scripts.evaluation_report_v2 import write_report_v2
                write_report_v2(out)
            except Exception as exc:
                try:
                    save(out / 'REPORTING_FAILURE.json', {'type': type(exc).__name__,
                        'message': str(exc), 'execution_report_preserved': True})
                except OSError:
                    pass  # A full disk must not turn completed execution into failure.
                raise ReportPostprocessingError(
                    'Completed REPORT.json and checkpoint preserved; reconcile REPORT.v2.json separately') from exc
        return result
    checkpoint()
    driver = None
    keep_actors_alive = False
    try:
        if remaining_seconds() < 1:
            return report('exhausted_time_budget')
        driver = (actor_factory(out, eco, spec, deadline=deadline) if actor_factory is NativeActors
                  else actor_factory(out, eco, spec))
        if hasattr(driver, 'set_deadline'):
            driver.set_deadline(deadline)
        for employee, skill in state['skills'].items():
            initial = out / 'skills' / employee / 'v000.json'
            if not initial.exists():
                save(initial, {'skill': SEED_SKILL, 'hash': hashlib.sha256(SEED_SKILL.encode()).hexdigest(),
                               'adopted_after_day': -1, 'version': 0})
        employees = sorted(state['skills'])
        while eco.day < config.days:
            if remaining_seconds() < 1:
                checkpoint(); return report('exhausted_time_budget')
            if state['phase'] == 'advance':
                day = eco.day + 1
                if day == config.days:
                    break
                if day > 0:
                    cause = eco.emit('benchmark_demand', 'environment', {'for_day': day, 'orders_per_employee': 1})
                    for fid in eco.firms:
                        for workflow in WORKFLOWS:
                            eco.order('consumer-' + fid[-1], fid, workflow, cause, created=day)
                eco.advance()
                for message in list(state['message_queue']):
                    if message['deliver_day'] == eco.day:
                        state['mailbox'].setdefault(message['recipient'], []).append(deepcopy(message))
                        target_firm, target_employee = message['recipient'].split('__')
                        known = eco.worlds[target_firm].employees[target_employee].known
                        for doc_id in message.get('document_ids', []):
                            if doc_id not in known:
                                known.append(doc_id)
                        eco.emit('employee_message_delivered', message['recipient'], message, [message['cause']])
                        state['message_queue'].remove(message)
                eco.emit('work_specification_published', 'environment', {'regime': regime_at(spec, eco.day)})
                state.update(phase='actors', actor_index=0, work_index=0, update_index=0)
                state['phase_views'] = {a: eco.actor_view(a) for a in ['agency', *eco.firms]}
                checkpoint()
            decision_days = {s['day'] for s in spec['shock_schedule']}
            actors = ['agency', *eco.firms, *eco.consumers] if eco.day % config.decision_every == 0 or eco.day in decision_days else []
            if state['phase'] == 'actors':
                for index in range(state['actor_index'], len(actors)):
                    if remaining_seconds() < 1:
                        checkpoint(); return report('exhausted_time_budget')
                    aid = actors[index]; key = f'd{eco.day:03d}-{aid}'
                    begin('actor', key)
                    view = state['phase_views'].get(aid, eco.actor_view(aid))
                    decision = driver.institutional(eco, aid, view, key)
                    eco.apply_decision(aid, decision, view)
                    save(out / 'actor_decisions' / (key + '.json'), {'view': view, 'decision': decision})
                    state['actor_index'] = index + 1; finish()
                work = []
                for fid, w in eco.worlds.items():
                    for emp in w.employees.values():
                        pending = [t for t in w.tasks.values() if t.owner == emp.id and t.status == 'pending']
                        if pending:
                            order = (lambda t: (-t.value, t.due, t.id)) if eco.firms[fid]['objective'] == 'cost_control' else (lambda t: (t.due, t.id))
                            work.append([fid, min(pending, key=order).id])
                work.sort(key=lambda x: (eco.worlds[x[0]].tasks[x[1]].workflow != eco.firms[x[0]]['priority_workflow'], x))
                state.update(worklist=work, phase='work'); checkpoint()
            if state['phase'] == 'work':
                for index in range(state['work_index'], len(state['worklist'])):
                    if remaining_seconds() < 1:
                        checkpoint(); return report('exhausted_time_budget')
                    if stop_after_sessions is not None and len(state['sessions']) - initial_sessions >= stop_after_sessions:
                        keep_actors_alive = True
                        checkpoint(); return report('paused_invocation_limit')
                    if len(state['sessions']) >= config.max_work_sessions:
                        checkpoint(); return report('exhausted_work_budget')
                    fid, tid = state['worklist'][index]; w = eco.worlds[fid]; task = w.tasks[tid]
                    employee = fid + '__' + task.owner
                    key = f'd{eco.day:03d}-{employee}-{tid}'
                    begin('work', key)
                    case = make_case(task.workflow, spec['seed'], eco.day, tid, regime_at(spec, eco.day),
                        'test' if config.split == 'test' else 'online', exception_window=spec['exception_window'])
                    driver.mailbox = state['mailbox']
                    decision, view = driver.employee(eco, task, employee, state['notes'], case, key)
                    state['notes'][employee] = decision['working_notes']
                    state['mailbox'][employee] = []
                    for msg in decision.get('colleague_messages', []):
                        cause = eco.emit('employee_message_sent', employee, msg)
                        state['message_queue'].append(dict(msg, sender=employee, recipient=fid+'__'+msg['recipient'],
                            deliver_day=eco.day+1, cause=cause))
                    proposal = enact_proposal(w, task, decision, {task.owner: eco.feedback.get(employee)})
                    if proposal:
                        eco.emit('employee_process_proposal', employee, proposal)
                    # Full branch inputs are private; the optimizer gets an allowlisted descriptor.
                    archived = deepcopy(state['business_archive'].get(employee, {})) if config.state_mode == 'full_deployment' else None
                    capsule = {'ecosystem': eco.checkpoint(), 'case': case, 'request': decision['request'],
                               'employee': employee, 'firm': fid, 'task_id': tid,
                               'objectives': deepcopy(eco.firms[fid]), 'business_files': archived}
                    save(out / 'private/cases' / (key + '.json'), capsule)
                    record = executor(root=out / 'work' / key, employee=employee, world=w, task_id=tid,
                        case=case, request=decision['request'], skill=state['skills'][employee], credentials=creds,
                        objectives=eco.firms[fid], max_iterations=config.max_iterations,
                        max_tokens=config.max_output_tokens, max_total_tokens=250000,
                        business_files=archived, timeout_seconds=min(420, remaining_seconds()))
                    record.update(id=key, skill_version=state['skill_versions'][employee])
                    state['sessions'].append(record)
                    if not record['infrastructure_valid']:
                        raise RuntimeError('Native work failed transport or accounting validation: ' + key)
                    eco.record_session(fid, task, key, record['diagnostic'], record['filesystem_delta'])
                    if record['success'] and record.get('artifact'):
                        state['business_archive'].setdefault(employee, {})[tid + '.json'] = json.dumps(
                            json.loads(record['artifact']['content']), sort_keys=True)
                    state['experiences'].append({'id': key, 'employee': employee,
                        'split': experience_split(tid), 'available_day': eco.day + config.feedback_delay,
                        'prompt': case['request'], 'context': json.dumps(case['public_files']),
                        'feedback': record['feedback'], 'source_session': tid,
                        'feedback_available_day': eco.day + config.feedback_delay})
                    save(out / 'employee_decisions' / (key + '.json'), {'decision': decision, 'view': view})
                    state['work_index'] = index + 1; finish()
                    print(f"Day {eco.day}: {employee} success={record['success']} skill={record['skill_version']} calls={record['usage']['api_calls']}", flush=True)
                state['phase'] = 'learn'; checkpoint()
            if state['phase'] == 'learn':
                for index in range(state['update_index'], len(employees)):
                    employee = employees[index]
                    learn = config.algorithm == 'skillopt' and (config.focal_employee is None or employee == config.focal_employee)
                    eligible = select_experiences(state['experiences'], employee, eco.day, config.train_cases, config.val_cases)
                    enough = all(sum(e['split'] == split for e in eligible) >= n
                                 for split, n in [('train', config.train_cases), ('val', config.val_cases)])
                    if learn and enough and eco.day + 1 < config.days and (eco.day + 1) % config.update_every == 0:
                        if remaining_seconds() < 1:
                            checkpoint(); return report('exhausted_time_budget')
                        _learn(out, config, eco, state, employee, eligible, creds, executor, begin, finish,
                               remaining_seconds=remaining_seconds, next_update_index=index + 1)
                    state['update_index'] = index + 1; checkpoint()
                state['phase'] = 'advance'; checkpoint()
        # Outcome horizon: no new work/actors/learning; let existing commitments
        # settle and pending obligations incur their declared delay/abandonment.
        drain = max(w.blueprint['settlement_delay'] for w in eco.worlds.values())
        while eco.day < config.days - 1 + drain:
            eco.advance()
        checkpoint()
        return report('completed')
    except ReportPostprocessingError:
        raise
    except Exception as exc:
        save(out / 'FAILURE.json', {'type': type(exc).__name__, 'message': str(exc), 'day': eco.day,
                                  'accounting_complete': False})
        checkpoint(); report('failed')
        raise
    finally:
        if driver is not None:
            if keep_actors_alive and hasattr(driver, 'pause'):
                driver.pause()
            else:
                driver.close()


def _learn(out, config, eco, state, employee, experiences, creds, executor, begin, finish,
           remaining_seconds=None, next_update_index=None):
    from .optimizer import make_reflector
    from .skillopt import LearningBudget, SkillOptLearner
    recipients = 1 if config.focal_employee else len(state['skills'])
    own = [r['costs'] for r in state['updates'] if r['employee'] == employee]
    remaining_calls = min(config.max_learning_calls - state['learning_calls'],
        config.max_learning_calls // recipients - sum(c['target_model_calls'] + c['optimizer_model_calls'] for c in own))
    remaining_tokens = min(config.max_learning_tokens - state['learning_tokens'],
        config.max_learning_tokens // recipients - sum(c['tokens'] for c in own))
    if remaining_calls < config.max_iterations or remaining_tokens < 100000:
        return
    key = f'd{eco.day:03d}-{employee}'
    begin('learning', key)
    live_hash = digest(eco.checkpoint())
    replay_index = [0]
    def replay(payload, limits):
        capsule = json.loads((out / 'private/cases' / (payload['task']['id'] + '.json')).read_text())
        if capsule['employee'] != employee:
            raise ValueError('Cross-employee replay forbidden')
        fork = Ecosystem.restore(capsule['ecosystem']); w = fork.worlds[capsule['firm']]
        attempt = replay_index[0]; replay_index[0] += 1
        result = executor(root=out / 'learning' / key / f'trial-{attempt:03d}',
            employee=employee, world=w, task_id=capsule['task_id'], case=capsule['case'],
            request=capsule['request'], skill=payload['skill'], credentials=creds,
            objectives=capsule['objectives'], max_iterations=min(config.max_iterations, limits['max_model_calls']),
            max_tokens=config.max_output_tokens, max_total_tokens=limits['max_tokens'],
            business_files=capsule['business_files'], timeout_seconds=limits['timeout_seconds'])
        if digest(eco.checkpoint()) != live_hash:
            raise RuntimeError('Candidate trial mutated the live world')
        return {'status': 'completed' if result['infrastructure_valid'] else 'failed',
            'hard': float(result['success']), 'soft': float(result['semantic_score']) if result['success'] else min(.99, float(result['semantic_score'])),
            'response': safe_trajectory(result), 'feedback': result['feedback'],
            'tokens': result['usage']['total_tokens'], 'model_calls': result['usage']['api_calls'],
            'tool_calls': result['tool_calls'], 'latency_ms': result['elapsed_seconds'] * 1000}
    reflector = make_reflector(creds, augment_training_context=True)
    learner = SkillOptLearner(edit_budget=config.edit_budget, rollouts_k=config.skillopt_rollouts_k)
    result = learner.update(state['skills'][employee], experiences, replay, reflector,
        current_day=eco.day, night=len(state['updates']) + 1,
        budget=LearningBudget(max_target_model_calls=max(1, remaining_calls - 4),
            max_optimizer_model_calls=min(4, remaining_calls), max_tokens=remaining_tokens,
            max_seconds=min(1800, remaining_seconds() if remaining_seconds else config.max_run_seconds), replay_model_calls=config.max_iterations,
            replay_tokens=min(250000, remaining_tokens), replay_seconds=420,
            optimizer_tokens=min(32768, remaining_tokens), optimizer_seconds=120))
    result.update(employee=employee, day=eco.day, available_from_day=eco.day + 1,
                  parent_version=state['skill_versions'][employee],
                  optimizer_transport_audit=getattr(reflector, 'audit_records', []))
    state['learning_calls'] += result['costs']['target_model_calls'] + result['costs']['optimizer_model_calls']
    state['learning_tokens'] += result['costs']['tokens']
    state['updates'].append(result)
    if result['accepted']:
        state['skills'][employee] = result['skill']; state['skill_versions'][employee] += 1
    result['deployed_version'] = state['skill_versions'][employee]
    save(out / 'learning' / key / 'update.json', result)
    if result['accepted']:
        save(out / 'skills' / employee / f"v{state['skill_versions'][employee]:03d}.json",
             {'skill': state['skills'][employee], 'hash': hashlib.sha256(state['skills'][employee].encode()).hexdigest(),
              'adopted_after_day': eco.day, 'version': state['skill_versions'][employee]})
    print(f"Day {eco.day}: SkillOpt {employee} {result['status']} accepted={result['accepted']}", flush=True)
    if result['status'] == 'failed' or not result['costs']['accounting_complete']:
        raise RuntimeError('Learning failed with incomplete evaluation/accounting; run is not a valid pair')
    if next_update_index is not None:
        state['update_index'] = next_update_index
    finish()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True)
    p.add_argument('--config', help='JSON ExperimentConfig; CLI defaults used when omitted')
    p.add_argument('--algorithm', choices=['no_learning', 'skillopt'], default='no_learning')
    p.add_argument('--days', type=int, default=24); p.add_argument('--seed', type=int, default=101)
    p.add_argument('--max-work-sessions', type=int, default=144)
    p.add_argument('--focal-employee')
    p.add_argument('--stop-after-sessions', type=int, help='Pause cleanly after this many additional sessions; resume with same config')
    a = p.parse_args()
    cfg = ExperimentConfig(**json.loads(Path(a.config).read_text())) if a.config else ExperimentConfig(
        algorithm=a.algorithm, days=a.days, seed=a.seed, max_work_sessions=a.max_work_sessions, focal_employee=a.focal_employee)
    result = run_experiment(a.out, cfg, stop_after_sessions=a.stop_after_sessions)
    print(json.dumps({'status': result.get('status'), 'out': str(Path(a.out).resolve())}))


if __name__ == '__main__':
    main()
