"""Single-use native Hermes rollouts with trusted business and content grading."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from ..computers import Computer, file_delta
from ..environment import SessionEnv
from ..mirofish import save


def install_skill(profile, content):
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 50000:
        raise ValueError('Skill must contain 1..50000 bytes of text')
    path = Path(profile) / 'skills/work-process/SKILL.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '---\nname: work-process\ndescription: Employee work process learned from available experience.\n---\n\n' + content
    path.write_text(text)
    return {'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'native_file_sha256': hashlib.sha256(text.encode()).hexdigest(), 'name': 'work-process'}


def write_public_files(workspace, files):
    root = Path(workspace).resolve()
    for relative, text in files.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or not isinstance(text, str):
            raise ValueError('Unsafe public task path/content')
        target = root / path
        if not target.resolve().is_relative_to(root):
            raise ValueError('Task file leaves workspace')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def native_usage(result):
    keys = ('api_calls', 'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
            'reasoning_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens',
            'estimated_cost_usd', 'cost_status', 'cost_source')
    usage = {k: result.get(k) for k in keys}
    meter = result.get('evaluation_budget', {})
    # Provider Responses input includes cached input. Native Hermes' logical
    # api_calls and uncached input_tokens are retained only as diagnostics.
    usage['native_logical_calls'] = usage['api_calls']
    usage['api_calls'] = meter.get('physical_model_calls')
    usage['charged_tokens'] = meter.get('charged_tokens')
    usage['prompt_tokens'] = meter.get('input_tokens')
    usage['completion_tokens'] = meter.get('output_tokens')
    usage['total_tokens'] = meter.get('total_tokens') if meter.get('accounting_complete') else None
    usage['complete'] = bool(meter.get('accounting_complete')) and all(
        type(usage.get(k)) is int and usage[k] >= 0
        for k in ('api_calls', 'prompt_tokens', 'completion_tokens', 'total_tokens'))
    if usage.get('cost_status') not in ('exact', 'estimated'):
        usage['estimated_cost_usd'] = None
    return usage


def skill_loaded(messages, native_file_sha256=None):
    requested = set()
    for message in messages:
        for call in message.get('tool_calls') or []:
            f = call.get('function', {})
            if f.get('name') != 'skill_view':
                continue
            try:
                args = json.loads(f.get('arguments', '{}'))
            except (ValueError, TypeError):
                continue
            if 'work-process' in args.values():
                requested.add(call.get('id'))
    for m in messages:
        if m.get('role') != 'tool' or m.get('tool_call_id') not in requested:
            continue
        try:
            value = json.loads(m.get('content', '{}'))
        except (ValueError, TypeError):
            continue
        if (isinstance(value, dict) and value.get('success') is True and value.get('name') == 'work-process'
                and isinstance(value.get('content'), str) and not value.get('error')):
            if native_file_sha256 is None or hashlib.sha256(value['content'].encode()).hexdigest() == native_file_sha256:
                return True
    return False


def execute_case(*, root, employee, world, task_id, case, request, skill, credentials,
                 objectives, max_iterations=16, max_tokens=4096, business_files=None,
                 max_total_tokens=None, timeout_seconds=420, hermes_transport='streaming'):
    from .tasks import grade_case
    from .hermes_transport import contract
    transport = contract(hermes_transport)
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('Rollout destination exists; trials must start from a fresh state')
    root.mkdir(parents=True)
    started = time.monotonic()
    computer = Computer(root / 'computers', employee,
        execution={'mode': 'evaluation', 'max_iterations': max_iterations, 'max_tokens': max_tokens,
                   'max_total_tokens': max_total_tokens, 'hermes_transport': hermes_transport},
        artifact_grader=lambda artifact: grade_case(case, artifact))
    task = world.tasks[task_id]
    brief = request + '\n' + case['request']
    env = SessionEnv(world, task, employee_message=brief, shared_inbox=[],
        employee_ask=lambda question: 'Recorded employee brief: ' + brief +
        '\nUse the supplied task files and published company procedures; no additional facts are available.')
    before_world = world.snapshot()
    skill_info = install_skill(computer.profile, skill)
    write_public_files(computer.workspace, case['public_files'])
    if business_files:
        write_public_files(computer.workspace, {'business_archive/' + k: v for k, v in business_files.items()})
    computer.publish(env.observation, objectives, [r.public() for r in world.documents(world.employees[task.owner])])
    before = computer.snapshot()
    save(root / 'INFLIGHT.json', {'employee': employee, 'task_id': task_id, 'skill': skill_info})
    try:
        ready = computer.start(credentials, timeout=min(150, timeout_seconds))
        if ready.get('evaluation_transport') != transport:
            raise RuntimeError('Native worker transport differs from requested contract')
        forbidden = set(ready['tool_names']) & {'memory', 'skill_manage'}
        if forbidden:
            raise RuntimeError('Private learning tools exposed in controlled target: ' + str(forbidden))
        result = computer.run(env, brief + '\nSimulated day ' + str(world.day) +
            '. Load work-process using skill_view and complete the task with actual files and tools.',
            timeout=max(1, timeout_seconds-(time.monotonic()-started)))
        if not env.done:
            env.step({'tool': 'session.end', 'args': {}})
        grade = computer.last_grade or {'success': False, 'score': 0.0, 'checks': {},
                                        'feedback': 'No artifact reached substantive submission.'}
        native = result['native']
        # A returned receipt must survive even when provenance is invalid.
        # Preserve the raw native body and costs, then stop at the existing
        # infrastructure gate instead of losing incurred usage in an exception.
        transport_valid = (native.get('evaluation_transport') == transport
            and all(type(op.get('request_stream')) is bool
                and op['request_stream'] == (hermes_transport == 'streaming')
                for op in native.get('evaluation_budget', {}).get('operations', [])))
        calls = sum(len(m.get('tool_calls') or []) for m in native.get('messages', []))
        usage = native_usage(native)
        loaded = skill_loaded(native.get('messages', []), skill_info['native_file_sha256'])
        after = computer.snapshot()
        # The score requires both substantive correctness and trusted commit.
        success = bool(env.success and grade['success'])
        artifact = None
        if success:
            artifact = deepcopy(computer.committed_artifact)
            if artifact is None:
                raise RuntimeError('Successful work has no committed artifact snapshot')
        record = {'employee': employee, 'day': world.day, 'task_id': task_id,
            'hermes_transport': transport,
            'case_id': case['id'], 'regime': case['regime'], 'skill': skill_info,
            'skill_loaded': loaded, 'success': success, 'semantic_score': grade['score'],
            'feedback': grade['feedback'], 'checks': grade['checks'],
            'artifact': artifact, 'committed_artifact_sha256': computer.committed_hash,
            'last_submitted_artifact_sha256': computer.last_submission_hash,
            'usage': usage, 'tool_calls': calls, 'elapsed_seconds': time.monotonic() - started,
            'timing': {'schema_version': 2, 'timeout_seconds': timeout_seconds,
                'elapsed_seconds_scope': 'runtime_start_through_snapshot_before_session_write_and_cleanup',
                'physical_inference_seconds': None},
            'trace': env.trace, 'result': result, 'diagnostic': env.diagnostic(),
            'filesystem_before': before, 'filesystem_after': after,
            'filesystem_delta': file_delta(before, after),
            'world_before': before_world, 'world_after': world.snapshot(),
            'budget_exhausted': bool(native.get('evaluation_budget', {}).get('exhausted', False)),
            'infrastructure_valid': transport_valid and usage['complete'] and (not native.get('failed', False)
                or native.get('evaluation_budget', {}).get('exhausted', False))
                and not any(op.get('status') == 'provider_budget_overrun'
                    for op in native.get('evaluation_budget', {}).get('operations', []))}
        save(root / 'session.json', record)
        (root / 'INFLIGHT.json').unlink()
        return record
    except Exception as exc:
        save(root / 'FAILURE.json', {'type': type(exc).__name__, 'message': str(exc),
                                    'usage_complete': False, 'elapsed_seconds': time.monotonic() - started})
        raise
    finally:
        computer.close()
