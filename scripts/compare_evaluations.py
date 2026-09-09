#!/usr/bin/env python3
"""Validate and compare completed Big World evaluation reports by world pair."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifespan.evaluation.metrics import paired_report
from scripts.evaluation_report_v2 import compare_reports_v2, load_verified_report_v2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--legacy-actionable', action='store_true',
                        help='Explicit historical v1 comparison; availability-conditioned rate is not the business fulfillment headline')
    args=parser.parse_args()
    if args.legacy_actionable:
        reports = [json.loads(path.read_text()) for path in args.reports]
        if any(report.get('metric_schema_version') == 2 for report in reports):
            parser.error('--legacy-actionable accepts REPORT.json v1 only')
        result=paired_report(reports)
        result['warning']='Historical actionable-work comparison; canonical business fulfillment uses REPORT.v2.json.'
    else:
        if any(json.loads(path.read_text()).get('metric_schema_version') != 2 for path in args.reports):
            parser.error('Use canonical REPORT.v2.json files; generate historical corrections with scripts/evaluation_report_v2.py, or explicitly request --legacy-actionable.')
        result=compare_reports_v2([load_verified_report_v2(path) for path in args.reports])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__=='__main__':
    main()
