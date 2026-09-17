"""Compile declared roles and departments into a fresh native local graph.

These are simulator assignments, not facts inferred about real people. The
compiler never receives task content, future events, feedback or grading data.
"""
from copy import deepcopy
import json
from pathlib import Path
import uuid
from scripts.source_world_calibration import save, sha

ONTOLOGY = {'entity_types': [
    {'name': 'Employee', 'description': 'An assigned employee in the fictional workforce.', 'attributes': [], 'examples': []},
    {'name': 'Department', 'description': 'An explicitly assigned workplace department.', 'attributes': [], 'examples': []}],
    'edge_types': [{'name': 'WORKS_IN', 'description': 'Declared department assignment.',
                    'source_targets': [{'source': 'Employee', 'target': 'Department'}], 'attributes': []}],
    'analysis_summary': 'Compiled from declared simulation roles; no model inference.'}


def declarations(employees):
    rows = [{'id': e['id'], 'role': e['role'], 'department': e.get('department', e['role']), 'language': e['language']}
            for e in employees]
    nodes = [{'name': e['id'], 'type': 'Employee',
              'summary': f"Assigned role: {e['role']}. Working language: {e['language']}.",
              'attributes': {'employee_id': e['id']}} for e in rows]
    departments = sorted({e['department'] for e in rows})
    nodes += [{'name': 'Department: ' + d, 'type': 'Department', 'summary': 'Assigned department: ' + d,
               'attributes': {}} for d in departments]
    if len({n['name'].casefold() for n in nodes}) != len(nodes):
        raise ValueError('Declared organization graph requires distinct case-insensitive names')
    edges = [{'source': e['id'], 'target': 'Department: ' + e['department'], 'name': 'WORKS_IN',
              'fact': e['id'] + ' is assigned to department ' + e['department'] + '.'} for e in rows]
    return {'assignments': rows, 'nodes': nodes, 'edges': edges}


def seed_native(runtime, employees):
    from app.config import Config
    from app.models.project import ProjectManager, ProjectStatus
    from app.services.graph_builder import GraphBuilderService
    from app.utils.local_graph import LocalGraphClient
    if Config.GRAPH_BACKEND != 'local' or runtime.state:
        raise ValueError('Declared graph bootstrap requires a fresh runtime and the local graph backend')
    declared = declarations(employees)
    project = ProjectManager.create_project('Big World declared workplace')
    graph_id = 'worldlab_' + uuid.uuid4().hex
    save(runtime.out / 'GRAPH_SEED_INTENT.json', {'project_id': project.project_id, 'graph_id': graph_id,
                                               'declared': declared, 'ontology': ONTOLOGY})
    # LocalGraphClient's public extractor injection supplies an exact compiled
    # graph. Graph.add still performs its native validation, episode persistence,
    # node/edge UUID construction and indexing in the shared local store.
    client = LocalGraphClient(Config.LOCAL_GRAPH_DB, extractor=lambda text, ontology: deepcopy(declared))
    client.graph.create(graph_id, name='Declared workplace', description='Explicit fictional role assignments')
    builder = GraphBuilderService()
    builder.set_ontology(graph_id, deepcopy(ONTOLOGY))
    source = json.dumps(declared['assignments'], ensure_ascii=False, sort_keys=True)
    episode = client.graph.add(graph_id, source, source_description='Declared simulation workforce',
                               metadata={'compiler_source_sha256': sha(Path(__file__)), 'model_calls': 0})
    ProjectManager.save_extracted_text(project.project_id, source)
    project.graph_id = graph_id
    project.ontology = deepcopy(ONTOLOGY)
    project.analysis_summary = ONTOLOGY['analysis_summary']
    project.total_text_length = len(source)
    project.simulation_requirement = 'Persistent employees in the declared fictional workplace.'
    project.status = ProjectStatus.GRAPH_COMPLETED
    ProjectManager.save_project(project)
    actual = runtime.call('/api/graph/data/' + graph_id)
    save(runtime.out / 'NATIVE_GRAPH_SEED.json', {'project_id': project.project_id, 'graph_id': graph_id,
        'episode_id': episode.uuid_, 'declared': declared, 'ontology': ONTOLOGY,
        'model_calls': 0, 'source_sha256': sha(Path(__file__)), 'native_graph_readback': actual})
    runtime.put('ontology', {'project_id': project.project_id, 'method': 'declared_organization_graph'})
    runtime.put('build', {'method': 'declared_organization_graph', 'episode_id': episode.uuid_})
    runtime.put('graph', actual)
