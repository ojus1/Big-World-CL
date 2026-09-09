#!/usr/bin/env python3
"""Download runtime assets once; stack.py uses them with offline mode enabled."""
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'models/tiktoken')
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from transformers import AutoModel, AutoTokenizer
import tiktoken

for name in ['cl100k_base', 'o200k_base']:
    tiktoken.get_encoding(name)
for cls in [AutoTokenizer, AutoModel]:
    cls.from_pretrained('Twitter/twhin-bert-base', revision='82ac392ce81f94560c391311ee2ddd024c5ac1fc',
                        cache_dir=str(root / 'models/embedding-cache'))
print('Runtime assets cached.')
