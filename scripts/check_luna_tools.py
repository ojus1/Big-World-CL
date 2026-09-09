#!/usr/bin/env python3
"""Exercise concurrent CAMEL function calls and tool results on Luna low."""
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'MiroFish/backend'))
from app.config import Config
from app.utils.camel_responses import create_simulation_model

model = create_simulation_model(Config.LLM_MODEL_NAME, Config.LLM_API_KEY, Config.LLM_BASE_URL)
tools = [{'type': 'function', 'function': {
    'name': 'create_post', 'description': 'Create a post in a fictional simulation.',
    'parameters': {'type': 'object', 'properties': {'content': {'type': 'string'}},
                   'required': ['content'], 'additionalProperties': False}}}]


async def run(index):
    started = time.monotonic()
    text = f'Library trial update {index}.'
    messages = [{'role': 'user', 'content': f'Call create_post exactly once. Set content to this exact JSON string: {json.dumps(text)}. After the tool succeeds, confirm the post ID in a short sentence without any more calls.'}]
    first = await model.arun(messages, tools=tools)
    calls = first.choices[0].message.tool_calls
    assert calls and len(calls) == 1
    assert calls[0].function.name == 'create_post'
    assert json.loads(calls[0].function.arguments)['content'] == text, calls[0].function.arguments
    messages += [first.choices[0].message.model_dump(exclude_none=True),
                 {'role': 'tool', 'tool_call_id': calls[0].id,
                  'content': json.dumps({'success': True, 'post_id': 101 + index})}]
    final = await model.arun(messages, tools=tools)
    assert final.choices[0].finish_reason == 'stop'
    answer = final.choices[0].message.content or ''
    assert str(101 + index) in answer
    return {'index': index, 'function': calls[0].function.model_dump(), 'answer': answer,
            'elapsed_s': round(time.monotonic() - started, 2),
            'initial_usage': first.usage.model_dump(), 'followup_usage': final.usage.model_dump()}


async def main():
    started = time.monotonic()
    results = await asyncio.gather(*(run(i) for i in range(4)))
    report = {'model': Config.LLM_MODEL_NAME, 'reasoning_effort': Config.LLM_REASONING_EFFORT,
              'api': 'Responses', 'store': False, 'concurrency': 4,
              'elapsed_s': round(time.monotonic() - started, 2), 'results': results}
    (ROOT / 'results/luna-tools.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


asyncio.run(main())
