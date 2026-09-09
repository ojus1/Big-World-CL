import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.config import Config
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.utils.openai_chat_compat import create_chat_completion


@pytest.mark.parametrize(('backend','url','adapted'), [
    ('local','http://127.0.0.1:8080/v1',True),
    ('local','https://example.com/v1',False),
    ('zep','http://127.0.0.1:8080/v1',False),
])
def test_uncapped_json_is_bounded_only_for_local_runtime(monkeypatch,backend,url,adapted):
    monkeypatch.setattr(Config,'GRAPH_BACKEND',backend)
    calls=[]
    client=SimpleNamespace(base_url=url,chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:calls.append(kw))))
    create_chat_completion(client,model='minicpm5-2b',messages=[],response_format={'type':'json_object'})
    assert calls[0]['response_format']['type']==('json_schema' if adapted else 'json_object')
    assert calls[0].get('max_tokens')==(8192 if adapted else None)


def test_local_profile_retries_truncation_without_repairing_partial_content(monkeypatch):
    monkeypatch.setattr(Config,'GRAPH_BACKEND','local')
    monkeypatch.setattr('time.sleep',lambda seconds:None)
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        content={'bio':'partial' if len(calls)==1 else 'complete','persona':'Maya is a student representative. She supports later library access. She requests safe evening transport.'}
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='length' if len(calls)==1 else 'stop',message=SimpleNamespace(content=json.dumps(content)))])
    generator=object.__new__(OasisProfileGenerator)
    generator.client=SimpleNamespace(base_url='http://127.0.0.1:8080/v1',chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    generator.model_name='minicpm5-2b'
    profile=generator._generate_profile_with_llm('Maya Chen','StudentRepresentative','Student representative.',{},'')
    assert profile['bio']=='complete'
    assert len(calls)==2
    assert all(c['max_tokens']==4096 for c in calls)
    assert calls[0]['response_format']['json_schema']['schema']['properties']['persona']['maxLength']==2400
