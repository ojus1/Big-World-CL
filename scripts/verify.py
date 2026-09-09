#!/usr/bin/env python3
"""Run upstream tests in their proper roots, then local adapter tests."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
python = str(root / 'MiroFish/backend/.venv/bin/python')
checks = [
    ([python, '-c', "from app.config import Config; Config.GRAPH_BACKEND='zep'; import pytest; raise SystemExit(pytest.main(['tests','-q']))"], root / 'MiroFish/backend'),
    ([python, '-m', 'pytest', 'tests', '-q'], root / 'MiroFish'),
    ([python, '-m', 'pytest', 'tests', '-q'], root),
    (['npm', 'run', 'build'], root / 'MiroFish'),
]
for cmd, cwd in checks:
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode:
        sys.exit(result.returncode)
