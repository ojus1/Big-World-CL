import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from zep_cloud import BatchAddItem, NotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.utils.local_graph import LocalGraphClient
from app.utils.zep_paging import fetch_all_nodes, fetch_all_edges
from app.config import Config
from app.utils.llm_client import LLMClient


@pytest.mark.parametrize('allow_remote', [False, True])
def test_remote_extraction_requires_explicit_configuration(tmp_path, monkeypatch, allow_remote):
    monkeypatch.setattr(Config, 'LLM_BASE_URL', 'https://api.openai.com/v1')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'test-key')
    monkeypatch.setattr(Config, 'LOCAL_GRAPH_ALLOW_REMOTE_LLM', allow_remote)
    calls = []
    def extract_empty(*args, **kwargs):
        calls.append(kwargs)
        return {'nodes': []}
    monkeypatch.setattr(LLMClient, 'chat_json', extract_empty)
    client = LocalGraphClient(str(tmp_path / 'graph.db'))
    client.graph.create('g')
    if allow_remote:
        assert client.graph.add('g', 'No named entities.').processed
        assert len(calls) == 1
    else:
        with pytest.raises(ValueError, match='LOCAL_GRAPH_ALLOW_REMOTE_LLM'):
            client.graph.add('g', 'No named entities.')
        assert not calls


def extract(text, ontology):
    return {
        'nodes': [
            {'name': 'Alice', 'type': 'Person', 'summary': 'Alice is a student.'},
            {'name': 'University', 'type': 'Organization', 'summary': 'A university.'},
        ],
        'edges': [{'source': 'Alice', 'target': 'University', 'name': 'STUDIES_AT',
                   'fact': 'Alice studies at University. 学生讨论大学政策。'}],
    }


def test_persistence_concurrent_ingestion_search_and_delete(tmp_path):
    path = str(tmp_path / 'graph.db')
    client = LocalGraphClient(path, extract)
    client.graph.create('g')
    with ThreadPoolExecutor(max_workers=8) as pool:
        episodes = list(pool.map(lambda i: client.graph.add('g', f'item {i}'), range(12)))
    reopened = LocalGraphClient(path, extract)
    assert len(fetch_all_nodes(reopened, 'g', page_size=1)) == 2
    edges = fetch_all_edges(reopened, 'g', page_size=1)
    assert len(edges) == 1 and len(edges[0].episodes) == 12
    assert all(reopened.graph.episode.get(e.uuid_).processed for e in episodes)
    assert len(reopened.graph.search('g', 'Alice', scope='edges').edges) == 1
    assert len(reopened.graph.search('g', '大学政策', scope='edges').edges) == 1
    assert reopened.graph.search('g', 'unrelatedxyz', scope='nodes').nodes == []
    assert len(reopened.graph.node.get_edges(edges[0].target_node_uuid)) == 1
    reopened.graph.delete('g')
    with pytest.raises(NotFoundError):
        reopened.graph.get('g')
    with pytest.raises(NotFoundError):
        reopened.graph.episode.get(episodes[0].uuid_)


def test_batch_failure_is_durable_and_never_reported_as_success(tmp_path):
    def failing(text, ontology):
        if text == 'bad':
            raise RuntimeError('model unavailable')
        return extract(text, ontology)
    client = LocalGraphClient(str(tmp_path / 'graph.db'), failing)
    client.graph.create('g')
    batch = client.batch.create({'graph_id': 'g'})
    client.batch.add(batch.batch_id, [BatchAddItem(type='graph_episode', graph_id='g', data=s, data_type='text') for s in ['good', 'bad']])
    result = client.batch.process(batch.batch_id)
    assert result.status == 'failed'
    assert result.progress.succeeded_items == 1
    page = client.batch.list_items(batch.batch_id, limit=1)
    second = client.batch.list_items(batch.batch_id, cursor=page.next_cursor)
    item = second.items[0]
    assert item.error == 'model unavailable'
    episode = client.graph.episode.get(item.episode_uuid)
    assert not episode.processed and episode.data == 'bad'
    with pytest.raises(ValueError, match='already been submitted'):
        client.batch.process(batch.batch_id)


def test_malformed_extraction_does_not_partially_write_nodes(tmp_path):
    def malformed(text, ontology):
        data = extract(text, ontology)
        data['edges'][0]['source'] = 'Missing'
        return data
    client = LocalGraphClient(str(tmp_path / 'graph.db'), malformed)
    client.graph.create('g')
    with pytest.raises(ValueError, match='missing node'):
        client.graph.add('g', 'source')
    assert fetch_all_nodes(client, 'g') == []
    assert fetch_all_edges(client, 'g') == []
