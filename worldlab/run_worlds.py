"""Prepare and execute native task worlds without hard-coding a learning loop."""
import argparse
import json
from pathlib import Path
from scripts.source_world_calibration import read
from .bank import Bank
from .calibration import attach_examples
from .hermes import Hermes
from .learning import SkillOpt
from .qualitative import FrozenRubricJudge
from .worlds import prepare_study, execute_study
from .workforce import expand_workforce


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'execute'])
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--spec', type=Path)
    p.add_argument('--employee-examples', type=Path)
    p.add_argument('--seeds', type=int, nargs='+', default=[211])
    p.add_argument('--hermes-root', type=Path, required=True)
    p.add_argument('--skillopt-root', type=Path, required=True)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    harness = Hermes(a.hermes_root, a.model, a.base_url)
    judge = FrozenRubricJudge(bank, a.model, a.base_url)
    learner = SkillOpt(a.skillopt_root, a.model, a.base_url)
    if a.command == 'prepare':
        spec = expand_workforce(read(a.spec))
        if a.employee_examples: spec = attach_examples(spec, read(a.employee_examples))
        value = prepare_study(bank, spec, a.seeds, harness, judge, learner, a.out)
    else:
        value = execute_study(bank, harness, judge, learner, a.out)
    print(json.dumps(value, indent=2))


if __name__ == '__main__': main()
