#!/usr/bin/env python3
"""Validate and compare completed Big World evaluation reports by world pair."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifespan.evaluation.metrics import paired_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args=parser.parse_args()
    result=paired_report([json.loads(path.read_text()) for path in args.reports])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__=='__main__':
    main()
