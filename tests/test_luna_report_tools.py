from pathlib import Path
import sys
from types import SimpleNamespace

from openai.types.chat import ChatCompletion

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.services.report_agent import ReportAgent, ReportOutline, ReportSection


class NativeModel:
    def __init__(self, tool_rounds):
        self.model_config_dict = {}
        self.requests = []
        self.tool_rounds = tool_rounds

    def run(self, messages, tools):
        self.requests.append((messages, tools, dict(self.model_config_dict)))
        index = len(self.requests)
        call = index <= self.tool_rounds
        return ChatCompletion(id=f'resp_{index}', object='chat.completion', created=1, model='gpt-5.6-luna', choices=[{
            'index': 0, 'finish_reason': 'tool_calls' if call else 'stop',
            'message': {'role': 'assistant', 'content': None if call else 'Final Answer: Maya supports later access with safe transport.',
                        'tool_calls': [{'id': f'call_{index}', 'type': 'function', 'function': {
                            'name': 'quick_search', 'arguments': '{"query":"Maya transport"}'}}] if call else None}}])


def agent(monkeypatch, rounds):
    native = NativeModel(rounds)
    monkeypatch.setattr('app.utils.camel_responses.create_simulation_model', lambda *args: native)
    llm = SimpleNamespace(model='gpt-5.6-luna', api_key='test-key', base_url='https://api.openai.com/v1')
    report = ReportAgent('g', 's', 'Review the fictional discussion.', llm_client=llm, zep_tools=SimpleNamespace())
    calls = []
    def execute(name, parameters, **kwargs):
        calls.append((name, parameters))
        return 'Retrieved source: Maya supports later access with safe transport.'
    monkeypatch.setattr(report, '_execute_tool', execute)
    return report, native, calls


def test_luna_section_retrieves_evidence_with_native_tool_results(monkeypatch):
    report, native, calls = agent(monkeypatch, 3)
    section = ReportSection(title='Findings', content='')
    outline = ReportOutline(title='Trial', summary='Fictional study', sections=[section])
    text = report._generate_section_react(section, outline, [])
    assert 'Maya supports' in text and len(calls) == 3
    assert [request[2]['tool_choice'] for request in native.requests] == ['required'] * 3 + ['auto']
    assert [m['tool_call_id'] for m in native.requests[-1][0] if m['role'] == 'tool'] == ['call_1', 'call_2', 'call_3']
    assert native.requests[0][1][0]['function']['parameters']['properties']['query']['type'] == 'string'


def test_luna_report_chat_uses_native_retrieval_and_returns_sources(monkeypatch):
    report, native, calls = agent(monkeypatch, 1)
    monkeypatch.setattr('app.services.report_agent.ReportManager.get_report_by_simulation', lambda sid: None)
    result = report.chat('Find Maya’s position in the graph.')
    assert len(calls) == 1
    assert result['sources'] == ['Maya transport']
    assert 'Maya supports' in result['response']
    assert native.requests[-1][0][-1]['role'] == 'tool'
