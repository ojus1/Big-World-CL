import argparse
import json
from pathlib import Path
from scripts.source_world_calibration import read
from .bank import Bank
from .calibration import fit


def main():
    p = argparse.ArgumentParser(description='Task-based employee calibration with frozen native replay plans')
    p.add_argument('command', choices=['fit', 'prepare', 'execute', 'audit'])
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--spec', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--hermes-root', type=Path)
    p.add_argument('--eurobench-package', type=Path)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    if a.command == 'fit':
        value = fit(bank, read(a.spec))
    else:
        from .hermes import Hermes
        from .grading import EuroBenchMechanical
        from .campaign import prepare, execute, audit
        grader = EuroBenchMechanical(a.eurobench_package)
        if a.command == 'audit':
            value = audit(bank, grader, a.out)
        else:
            harness = Hermes(a.hermes_root, a.model, a.base_url)
            value = (prepare(bank, read(a.spec), harness, grader, a.out) if a.command == 'prepare'
                     else execute(bank, harness, grader, a.out))
    print(json.dumps(value, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
