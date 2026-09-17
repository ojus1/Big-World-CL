import argparse
import json
from pathlib import Path
from scripts.source_world_calibration import read
from .bank import Bank
from .calibration import fit, attach_examples
from .workforce import expand_workforce


def main():
    p = argparse.ArgumentParser(description='Task-based employee calibration with frozen native replay plans')
    p.add_argument('command', choices=['fit', 'prepare', 'execute', 'audit'])
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--spec', type=Path)
    p.add_argument('--employee-examples', type=Path,
                   help='Optional {employee_id: [tasks]} overlay; --spec supplies the generated workforce')
    p.add_argument('--out', type=Path)
    p.add_argument('--hermes-root', type=Path)
    p.add_argument('--eurobench-package', type=Path)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8011/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    specification = expand_workforce(read(a.spec)) if a.spec else None
    if a.employee_examples:
        specification = attach_examples(specification, read(a.employee_examples))
    if a.command == 'fit':
        value = fit(bank, specification)
    else:
        from .hermes import Hermes
        from .grading import EuroBenchMechanical
        from .campaign import prepare, execute, audit
        grader = EuroBenchMechanical(a.eurobench_package)
        if a.command == 'audit':
            value = audit(bank, grader, a.out)
        else:
            harness = Hermes(a.hermes_root, a.model, a.base_url)
            value = (prepare(bank, specification, harness, grader, a.out) if a.command == 'prepare'
                     else execute(bank, harness, grader, a.out))
    print(json.dumps(value, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
