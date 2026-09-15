"""Bind native Fluso assistant turns and a skill read to metered wire evidence.

Call the matching budget-meter auditor separately. This does not audit every
tool's effects, the complete runtime event history, isolation or task scoring.
"""
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def response_message(raw, streaming):
    if not streaming:
        values = [json.loads(raw)]
        choice = values[0]['choices'][0]
        message = choice['message']
        return values[0]['id'], {'text': message.get('content') or '', 'tools': [
            {'id': c['id'], 'name': c['function']['name'], 'arguments': json.loads(c['function']['arguments'])}
            for c in message.get('tool_calls', [])]}, choice['finish_reason']
    ids, calls, text, finish = set(), {}, '', None
    for line in raw.decode().splitlines():
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if data == '[DONE]':
            continue
        value = json.loads(data)
        if value.get('id'):
            ids.add(value['id'])
        for choice in value.get('choices', []):
            require(choice['index'] == 0, 'Unexpected choice in native response')
            delta = choice.get('delta', {})
            text += delta.get('content') or ''
            for part in delta.get('tool_calls', []):
                call = calls.setdefault(part['index'], {'id': '', 'name': '', 'arguments': ''})
                call['id'] += part.get('id') or ''
                for key in ('name', 'arguments'):
                    call[key] += part.get('function', {}).get(key) or ''
            finish = choice.get('finish_reason') or finish
    require(len(ids) == 1 and finish is not None, 'Incomplete or conflicting native response identity')
    return ids.pop(), {'text': text, 'tools': [{**calls[k], 'arguments': json.loads(calls[k]['arguments'])}
                                              for k in sorted(calls)]}, finish


def text_parts(content):
    if isinstance(content, str):
        return content
    require(isinstance(content, list) and all(p.get('type') == 'text' for p in content),
            'Unqualified nontext tool evidence')
    return ''.join(p['text'] for p in content)


def assistant_parts(message):
    parts = message['content']
    require(isinstance(parts, list) and all(p.get('type') in ('text', 'toolCall') for p in parts),
            'Unqualified native assistant content')
    return {'text': ''.join(p['text'] for p in parts if p['type'] == 'text'),
            'tools': [{k: p[k] for k in ('id', 'name', 'arguments')} for p in parts if p['type'] == 'toolCall']}


def audit_skill_and_responses(trace, meter_root, *, model, skill_path, skill_text):
    """Verify all primary assistant responses plus read-and-consume skill proof.

    Auxiliary requests are included in the meter but need not have a primary
    session row. Report them separately; never infer full cost from native rows.
    """
    trace, meter_root = Path(trace), Path(meter_root)
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    messages = [r['message'] for r in rows if r.get('type') == 'message']
    meter = json.loads((meter_root / 'METER.json').read_text())
    replies = {}
    for operation in meter['operations']:
        if operation['status'] != 'completed':
            continue
        root = meter_root / operation['path']
        wire = json.loads((root / 'WIRE_REQUEST.json').read_text())
        response_id, value, finish = response_message((root / 'RESPONSE.bin').read_bytes(), wire['stream'])
        require(response_id not in replies, 'Repeated provider response identity')
        replies[response_id] = (value, finish, operation, wire)
    primary, normalized, reads, consumed = [], [], {}, []
    known_calls, pending = {}, set()
    for index, message in enumerate(messages):
        role = message['role']
        if role == 'assistant':
            require(not pending, 'Native assistant continued before pending tool results')
            require(message.get('api') == 'openai-completions' and message.get('provider') == 'pcci'
                    and message.get('model') == model, 'Native assistant provider changed')
            response_id = message['responseId']
            require(response_id in replies and response_id not in primary, 'Unmetered or repeated native assistant response')
            value, finish, operation, wire = replies[response_id]
            require(value == assistant_parts(message), 'Native assistant differs from provider bytes')
            require(message['stopReason'] == {'stop': 'stop', 'tool_calls': 'toolUse'}.get(finish),
                    'Native assistant has no qualified terminal reason')
            usage, observed = message['usage'], operation['usage']
            require(usage['input'] + usage.get('cacheRead', 0) + usage.get('cacheWrite', 0) == observed['prompt_tokens']
                    and usage['output'] == observed['completion_tokens'] and usage['totalTokens'] == observed['total_tokens'],
                    'Native primary usage differs from metered provider usage')
            for read_id, read_index in reads.items():
                if any(m.get('role') == 'tool' and m.get('tool_call_id') == read_id
                       and text_parts(m['content']) == skill_text for m in wire['messages']):
                    consumed.append({'tool_call_id': read_id, 'read_index': read_index,
                                     'consuming_response_id': response_id, 'dispatch': operation['dispatch']})
            primary.append(response_id)
            tool_calls = []
            for call in value['tools']:
                require(call['id'] not in known_calls, 'Duplicate native tool call identity')
                known_calls[call['id']] = call
                pending.add(call['id'])
                tool_calls.append({'id': call['id'], 'type': 'function',
                                   'function': {'name': call['name'], 'arguments': json.dumps(call['arguments'], ensure_ascii=False)}})
            normalized.append({'role': 'assistant', 'content': value['text'], 'tool_calls': tool_calls})
        elif role == 'toolResult':
            call = known_calls.get(message['toolCallId'])
            require(call is not None and call['name'] == message['toolName'] and message['toolCallId'] in pending,
                    'Unlinked or repeated native tool result')
            pending.remove(message['toolCallId'])
            content = text_parts(message['content'])
            if call['name'] == 'read' and call['arguments'].get('path') == skill_path:
                require(message.get('isError') is False and content == skill_text, 'Native skill read did not return installed bytes')
                require(not call['arguments'].get('offset') and not call['arguments'].get('limit'), 'Partial skill read is unqualified')
                reads[call['id']] = index
            normalized.append({'role': 'tool', 'tool_call_id': message['toolCallId'],
                               'name': message['toolName'], 'content': content})
        elif role == 'user':
            normalized.append({'role': 'user', 'content': text_parts(message['content'])})
        else:
            raise ValueError('Unqualified native message role')
    require(primary and consumed and messages[-1]['role'] == 'assistant'
            and messages[-1]['stopReason'] == 'stop', 'Missing consumed skill or completed native assistant turn')
    return {'ok': True, 'trace_sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
            'skill_sha256': hashlib.sha256(skill_text.encode()).hexdigest(),
            'primary_model_calls': len(primary), 'other_metered_calls': meter['physical_model_calls'] - len(primary),
            'skill_loaded': True, 'skill_consumption': consumed, 'trajectory': normalized,
            'scope': 'Native primary assistant response bytes and usage, linked full skill read and later wire consumption. '
                     'Excludes other tool effects, complete runtime-event audit, isolation and task grading.'}
