#!/usr/bin/env python3
"""Exercise the README workflow using clearly labelled, small demo adaptations."""
import argparse
import json
from pathlib import Path
import re
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('scenario', choices=['university', 'red_chamber'])
p.add_argument('--rounds', type=int, default=2)
p.add_argument('--output-dir', type=Path, help='Separate evidence directory for a fresh model run; existing state resumes.')
p.add_argument('--keep-env', action='store_true', help='Keep the completed simulation workers alive for additional live interviews.')
a = p.parse_args()
out = a.output_dir or ROOT / 'results' / ('tutorial-' + a.scenario)
out.mkdir(exist_ok=True)
client = httpx.Client(base_url='http://127.0.0.1:5001', timeout=900, headers={'Accept-Language': 'en', 'X-Language': 'en'})
state_path = out / 'state.json'
state = json.loads(state_path.read_text()) if state_path.exists() else {}
versions = json.loads((ROOT / 'results/versions.json').read_text())
if state and 'versions' not in state:
    raise SystemExit('Existing state has no model provenance; choose a fresh --output-dir.')
def model_identity(manifest):
    return (manifest.get('api_model'), manifest.get('reasoning_effort'),
            manifest.get('simulation_api'), manifest.get('model_sha256'))


if state and model_identity(state['versions']) != model_identity(versions):
    raise SystemExit('This output directory belongs to another model; choose a fresh --output-dir.')
state.setdefault('versions', versions)


def save(key, value):
    state[key] = value
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(key, json.dumps(value, ensure_ascii=False)[:350], flush=True)
    return value


def call(path, payload=None, **kwargs):
    response = client.post(path, json=payload, **kwargs) if payload is not None or kwargs else client.get(path)
    body = response.json()
    if response.is_error or not body.get('success', True):
        raise RuntimeError(f'{path}: HTTP {response.status_code}: {json.dumps(body, ensure_ascii=False)}')
    return body.get('data', body)


def wait(path, payload=None, key='status', ready=('completed', 'ready'), timeout=1800):
    deadline = time.time() + timeout
    previous = None
    while time.time() < deadline:
        data = call(path, payload)
        status = data.get(key)
        marker = (status, data.get('progress'), data.get('current_round'))
        if marker != previous:
            print(path, marker, str(data.get('message', ''))[:160], flush=True)
            previous = marker
        if status in ready:
            return data
        if status in {'failed', 'error', 'stopped'}:
            raise RuntimeError(json.dumps(data, ensure_ascii=False))
        time.sleep(3)
    raise TimeoutError(path)


started = time.time()
try:
    if 'ontology' not in state:
        text = (ROOT / 'tests/fixtures' / (a.scenario + '.txt')).read_bytes()
        requirement = ('Simulate the named participants discussing the proposal in the source on Twitter and Reddit. '
                       'Run a small two-round fictional test. Assess possible agreement and disagreement, and distinguish speculation from source facts. '
                       'Keep the simulation, profiles and final report concise and in English.')
        response = client.post('/api/graph/ontology/generate', files={'files': (a.scenario + '.txt', text, 'text/plain')},
                               data={'simulation_requirement': requirement,
                                     'project_name': f"Tutorial smoke: {a.scenario} ({versions.get('api_model') or versions.get('model_file')})"})
        response.raise_for_status()
        body = response.json()
        if not body['success']:
            raise RuntimeError(str(body))
        save('ontology', body['data'])
    project = state['ontology']['project_id']
    if 'build' not in state:
        save('build', call('/api/graph/build', {'project_id': project, 'chunk_size': 3000, 'chunk_overlap': 0}))
    if 'graph' not in state:
        save('build_result', wait('/api/graph/task/' + state['build']['task_id']))
        proj = call('/api/graph/project/' + project)
        save('graph', call('/api/graph/data/' + proj['graph_id']))
        assert state['graph']['node_count'] >= 3 and state['graph']['edge_count'] > 0
    graph_id = state['graph']['graph_id']
    if 'simulation' not in state:
        save('simulation', call('/api/simulation/create', {'project_id': project, 'enable_twitter': True, 'enable_reddit': True}))
    sim = state['simulation']['simulation_id']
    if 'prepare' not in state:
        save('prepare', call('/api/simulation/prepare', {'simulation_id': sim, 'use_llm_for_profiles': True, 'parallel_profile_count': 8}))
    if 'prepared' not in state:
        save('prepared', wait('/api/simulation/prepare/status', {'simulation_id': sim, 'task_id': state['prepare'].get('task_id')}))
    if 'start' not in state:
        # The generated schedule may have no active agents at midnight. Force
        # activity only in this smoke fixture so rounds exercise real LLMAction.
        config_path = ROOT / 'MiroFish/backend/uploads/simulations' / sim / 'simulation_config.json'
        original_config = json.loads(config_path.read_text())
        if not (out / 'generated-config.json').exists():
            (out / 'generated-config.json').write_text(json.dumps(original_config, indent=2, ensure_ascii=False))
        config = json.loads(json.dumps(original_config))
        count = len(config['agent_configs'])
        config['time_config'].update(agents_per_hour_min=count, agents_per_hour_max=count,
                                    peak_activity_multiplier=1, off_peak_activity_multiplier=1)
        for agent in config['agent_configs']:
            agent.update(active_hours=list(range(24)), activity_level=1)
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        save('smoke_schedule', {'active_agents': count, 'active_hours': 'all', 'reason': 'exercise LLM actions in two rounds'})
        save('start', call('/api/simulation/start', {'simulation_id': sim, 'platform': 'parallel', 'max_rounds': a.rounds, 'enable_graph_memory_update': True, 'force': True}))
    if 'run' not in state:
        save('run', wait(f'/api/simulation/{sim}/run-status', key='runner_status', ready=('completed',)))
    if 'run_validated' not in state:
        assert state['run']['twitter_actions_count'] > 0 and state['run']['reddit_actions_count'] > 0
        worker_log = (ROOT / 'MiroFish/backend/uploads/simulations' / sim / 'simulation.log').read_text(errors='replace')
        assert not re.search(r'Model error:|Error processing with model:|Traceback \(most recent call last\)', worker_log), 'Simulation worker logged an inference error'
        for platform in ['twitter', 'reddit']:
            log = ROOT / 'MiroFish/backend/uploads/simulations' / sim / platform / 'actions.jsonl'
            actions = [json.loads(line) for line in log.read_text().splitlines()]
            seeds = {row.get('action_args', {}).get('content') for row in actions if row.get('round') == 0}
            assert any(row.get('round', 0) > 0 and row.get('success') and (
                row.get('action_type') not in {None, 'CREATE_POST', 'DO_NOTHING'} or
                (row.get('action_type') == 'CREATE_POST' and row.get('action_args', {}).get('content') not in seeds)
            ) for row in actions), f'No successful new LLM action on {platform}; seeded posts do not count'
        save('run_validated', {'no_model_errors': True, 'new_actions_beyond_seeds': True})
    if 'graph_after_simulation' not in state:
        save('graph_after_simulation', call('/api/graph/data/' + graph_id))
    if 'interview' not in state:
        save('interview', call('/api/simulation/interview', {'simulation_id': sim, 'agent_id': 0, 'platform': 'twitter',
                                                           'prompt': 'What do you think about the proposal after the discussion? Answer briefly.', 'timeout': 180}))
    if 'report_start' not in state:
        save('report_start', call('/api/report/generate', {'simulation_id': sim}))
    if 'report_done' not in state:
        save('report_done', wait('/api/report/generate/status', {'simulation_id': sim, 'task_id': state['report_start'].get('task_id')}))
    if 'report' not in state:
        save('report', call('/api/report/by-simulation/' + sim))
        report_id = state['report']['report_id']
        response = client.get(f'/api/report/{report_id}/download')
        response.raise_for_status()
        (out / 'report.md').write_text(response.text)
    if 'report_validated' not in state:
        report_id = state['report']['report_id']
        events = [json.loads(line) for line in (ROOT / 'MiroFish/backend/uploads/reports' / report_id / 'agent_log.jsonl').read_text().splitlines()]
        sections = [event for event in events if event['action'] == 'section_content']
        assert sections and all(event['details'].get('tool_calls_count', 0) >= 3 for event in sections), 'Every report section must retrieve simulation evidence'
        assert any(event['action'] == 'tool_result' and event['details'].get('result') for event in events), 'Report has no recorded retrieval results'
        save('report_validated', {'sections': len(sections), 'tool_calls': sum(event['action'] == 'tool_call' for event in events)})
    if 'report_chat' not in state:
        save('report_chat', call('/api/report/chat', {'simulation_id': sim, 'message': 'Give two short observations supported by this simulation and one limitation.'}))
    if not a.keep_env:
        call('/api/simulation/close-env', {'simulation_id': sim, 'timeout': 30}, timeout=40)
        closed = wait('/api/simulation/env-status', {'simulation_id': sim},
                      key='env_alive', ready=(False,), timeout=45)
        save('environment_closed', closed)
    state.pop('last_error', None)
    if state.get('result', {}).get('status') != 'passed':
        save('result', {'status': 'passed', 'elapsed_this_run_s': time.time() - started, 'rounds': a.rounds,
                        'scope': 'README five-stage workflow with reconstructed small demo inputs, not original video assets'})
    else:
        print('PASS: saved workflow results verified; no model calls repeated.', flush=True)
except Exception as error:
    save('last_error', {'message': str(error), 'elapsed_this_run_s': time.time() - started})
    raise
