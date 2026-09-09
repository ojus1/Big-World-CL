#!/usr/bin/env python3
"""Save bounded, inspectable quality probes; repetition metrics are diagnostic."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'MiroFish/backend'))
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.utils.locale import set_locale

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--modes', default='fast,thinking')
p.add_argument('--cases', help='Comma-separated case names; omit for all.')
p.add_argument('--thinking-budget', type=int, default=4096)
a = p.parse_args()
set_locale('en')
source = (ROOT / 'tests/fixtures/university.txt').read_text()
generator = object.__new__(OasisProfileGenerator)
long_profile_prompt = generator._build_group_persona_prompt(
    'Maya Chen', 'StudentRepresentative',
    'Maya Chen is a student representative supporting later library access, conditional on safe evening transport.',
    {}, source,
)
profile_prompt = long_profile_prompt.replace('2000字', '600字').replace('200字', '100字')
cases = [
    ('facts', 'Use only the supplied source. Give four numbered answers: Has the proposal been approved? How long is the trial? What does Maya request? What does Daniel request?\n'+source, 256),
    ('summary', 'Summarize the source in 120-180 English words. Distinguish the proposal from an approved decision. Do not invent outcomes, people, survey results, or dates.\n'+source, 512),
    ('profile', profile_prompt, 1536),
    ('profile_long', long_profile_prompt, 3072),
    ('discussion', 'Using the source, write a 350-450-word fictional discussion between Maya, Daniel, and Asha about the library proposal. Give each a distinct concern, let them respond to each other, and end with unresolved questions. Do not repeat sentences or invent a final approval. Clearly label invented dialogue.\n'+source, 1024),
]
if a.cases:
    selected = set(a.cases.split(','))
    assert selected <= {case[0] for case in cases}
    cases = [case for case in cases if case[0] in selected]
results = {'versions': json.loads((ROOT/'results/versions.json').read_text()), 'cases': []}
for mode in a.modes.split(','):
    assert mode in {'fast', 'thinking'}
    thinking = mode == 'thinking'
    for name, prompt, cap in cases:
        payload = {'model': 'minicpm5-2b', 'messages': [{'role': 'user', 'content': prompt}],
                   'temperature': 1.0 if thinking else 0.7, 'top_p': 0.95, 'seed': 12342,
                   'max_tokens': cap + (a.thinking_budget if thinking else 0), 'cache_prompt': False,
                   'chat_template_kwargs': {'enable_thinking': thinking},
                   'reasoning_format': 'deepseek', 'reasoning_budget_tokens': a.thinking_budget if thinking else 0}
        if name.startswith('profile'):
            payload['messages'].insert(0, {'role':'system', 'content':generator._get_system_prompt(False)})
            payload['response_format'] = {'type':'json_object'}
        start = time.monotonic()
        try:
            req = Request('http://127.0.0.1:8080/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=180) as response: body=json.load(response)
            choice=body['choices'][0]
            content=choice['message'].get('content') or ''
            words=re.findall(r"[a-z0-9]+(?:'[a-z]+)?",content.lower())
            grams=Counter(tuple(words[i:i+6]) for i in range(max(0,len(words)-5)))
            sentences=Counter(s.strip().lower() for s in re.split(r'[.!?。！？]+',content) if len(s.strip())>25)
            row={'mode':mode,'case':name,'elapsed_s':time.monotonic()-start,'finish_reason':choice['finish_reason'],
                 'answer':content,'word_count':len(words),'repeated_6gram_fraction':sum(n-1 for n in grams.values())/max(1,sum(grams.values())),
                 'repeated_sentences':{s:n for s,n in sentences.items() if n>1},
                 'reasoning_characters':len(choice['message'].get('reasoning_content') or ''),
                 'request':payload,'usage':body.get('usage'), 'error':None}
        except Exception as e:
            row={'mode':mode,'case':name,'error':str(e),'elapsed_s':time.monotonic()-start,'request':payload}
        results['cases'].append(row)
        Path(a.output).write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({k:v for k,v in row.items() if k not in {'answer','request','repeated_sentences'}},ensure_ascii=False),flush=True)
if any(row['error'] for row in results['cases']): raise SystemExit(1)
