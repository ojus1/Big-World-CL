#!/usr/bin/env python3
"""Small paid API check of the configured Luna model, with four concurrent requests."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'MiroFish/backend'))
from app.config import Config
from app.utils.llm_client import LLMClient
from app.utils.openai_chat_compat import create_chat_completion

assert Config.LLM_MODEL_NAME == 'gpt-5.6-luna'
assert Config.LLM_REASONING_EFFORT == 'low'
assert Config.LLM_BASE_URL == 'https://api.openai.com/v1'
assert Config.GRAPH_BACKEND == 'local'

cases = [
    ('arithmetic', 'What is 17 times 23? Give the number and one short verification.', '391'),
    ('source_facts', 'Source: A library trial runs for two weeks. Maya requests safe evening transport. Leo requests a cost review. In two sentences, summarize only these facts.', 'Maya'),
    ('uncertainty', 'A fictional university is considering later library hours. No survey has been conducted. What percentage of students support it? Answer in two short sentences without inventing data.', None),
    ('discussion', 'Write a concise four-turn dialogue between Maya, who supports later library hours with safe transport, and Leo, who wants a cost review. Each turn should add a new point. End with a concrete next step, without claiming a real decision was made.', 'Maya'),
]


def check(case):
    name, prompt, expected = case
    start = time.monotonic()
    response = create_chat_completion(
        LLMClient().client, model=Config.LLM_MODEL_NAME,
        messages=[{'role': 'user', 'content': prompt}], max_tokens=1024,
    )
    choice = response.choices[0]
    answer = choice.message.content or ''
    assert choice.finish_reason == 'stop' and answer.strip(), name
    if expected:
        assert expected in answer, name
    words = re.findall(r'\b\w+\b', answer.lower())
    grams = Counter(tuple(words[i:i + 6]) for i in range(max(0, len(words) - 5)))
    return {'case': name, 'prompt': prompt, 'answer': answer,
            'elapsed_s': round(time.monotonic() - start, 2),
            'finish_reason': choice.finish_reason,
            'duplicate_sixgrams': sum(v - 1 for v in grams.values()),
            'usage': response.usage.model_dump()}


start = time.monotonic()
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(check, cases))
output = {'model': Config.LLM_MODEL_NAME, 'reasoning_effort': Config.LLM_REASONING_EFFORT,
          'concurrency': 4, 'elapsed_s': round(time.monotonic() - start, 2), 'results': results}
(ROOT / 'results/luna-quality.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output, indent=2))
