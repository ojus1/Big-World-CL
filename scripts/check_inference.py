#!/usr/bin/env python3
"""Verify the OpenAI features MiroFish/OASIS use against the real GPU server."""
import argparse
import json
from pathlib import Path
import time
from openai import OpenAI
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.utils.llm_client import LLMClient
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.utils.locale import set_locale

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='results/inference-compatibility.json')
args = parser.parse_args()
client = OpenAI(base_url='http://127.0.0.1:8080/v1', api_key='local-llama', timeout=120)
results = {}
start = time.time()
plain = client.chat.completions.create(model='minicpm5-2b', messages=[{'role':'user', 'content':'Reply with exactly READY.'}], temperature=0, max_tokens=64)
assert 'READY' in plain.choices[0].message.content
results['plain'] = plain.model_dump()
structured = client.chat.completions.create(model='minicpm5-2b', messages=[{'role':'user','content':'Return a JSON object with status equal to ready and count equal to 3.'}],
                                           response_format={'type':'json_object'}, temperature=0, max_tokens=128)
assert LLMClient._parse_json_response(structured) == {'status':'ready','count':3}
results['json'] = structured.model_dump()
results['json_note'] = 'Bare json_object may be fenced; local MiroFish now enforces a nonempty JSON schema.'
results['schema_json'] = LLMClient().chat_json([{'role':'user', 'content':'Return a JSON object with status equal to ready and count equal to 3.'}], temperature=0, max_tokens=128)
assert results['schema_json'] == {'status':'ready','count':3}
tools = [{'type':'function','function':{'name':'create_post','description':'Create a post in this fictional simulation.',
          'parameters':{'type':'object','properties':{'content':{'type':'string'}},'required':['content'],'additionalProperties':False}}}]
messages = [{'role':'user','content':'Use create_post to post exactly: The library trial starts tomorrow.'}]
tool = client.chat.completions.create(model='minicpm5-2b', messages=messages, tools=tools, tool_choice='required', temperature=0, max_tokens=160)
calls = tool.choices[0].message.tool_calls
assert calls and calls[0].function.name == 'create_post'
assert 'library' in json.loads(calls[0].function.arguments)['content']
results['tool_call'] = tool.model_dump()
messages += [tool.choices[0].message.model_dump(exclude_none=True), {'role':'tool','tool_call_id':calls[0].id,'content':'{"post_id":1,"success":true}'}]
follow = client.chat.completions.create(model='minicpm5-2b', messages=messages, tools=tools, tool_choice='none', temperature=0, max_tokens=128)
assert follow.choices[0].message.content
results['tool_followup'] = follow.model_dump()
set_locale('en')
profile = OasisProfileGenerator()._generate_profile_with_llm(
    'Maya Chen', 'StudentRepresentative',
    'Maya Chen is a student representative who supports later library access but asks for safe evening transport.',
    {}, (Path(__file__).resolve().parents[1] / 'tests/fixtures/university.txt').read_text(),
)
assert 0 < len(profile['bio']) <= 360 and 80 <= len(profile['persona']) <= 2400
assert 'Maya' in profile['bio'] + profile['persona']
results['local_profile'] = profile
results['elapsed_s'] = time.time() - start
results['versions'] = json.loads((Path(__file__).resolve().parents[1] / 'results/versions.json').read_text())
Path(args.output).write_text(json.dumps(results, indent=2))
print('PASS: plain chat, JSON, XML tool-call parsing, tool-result follow-up, and bounded local profile', flush=True)
