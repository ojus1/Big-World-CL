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
from .adapters import load_adapter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'execute'])
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--spec', type=Path)
    p.add_argument('--employee-examples', type=Path)
    p.add_argument('--seeds', type=int, nargs='+', default=[211])
    p.add_argument('--hermes-root', type=Path)
    p.add_argument('--skillopt-root', type=Path)
    p.add_argument('--harness-config', type=Path)
    p.add_argument('--learner-config', type=Path)
    p.add_argument('--judge-config', type=Path)
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    p.add_argument('--mirofish-backend', type=Path)
    p.add_argument('--persona-cache', type=Path)
    p.add_argument('--mirofish-service-url')
    p.add_argument('--meter-social-calls', action='store_true',
                   help='Opt in to simulation-bound native Responses usage receipts; requires a fresh updated backend')
    a = p.parse_args()
    if bool(a.hermes_root) == bool(a.harness_config):
        p.error('Supply exactly one of --hermes-root and --harness-config')
    if bool(a.skillopt_root) == bool(a.learner_config):
        p.error('Supply exactly one of --skillopt-root and --learner-config')
    bank = Bank(a.bank)
    harness = load_adapter(a.harness_config, 'harness') if a.harness_config else Hermes(a.hermes_root, a.model, a.base_url)
    judge = load_adapter(a.judge_config, 'judge') if a.judge_config else FrozenRubricJudge(bank, a.model, a.base_url)
    learner = load_adapter(a.learner_config, 'learner') if a.learner_config else SkillOpt(a.skillopt_root, a.model, a.base_url)
    employee_factory = None
    actor_options = [a.mirofish_backend, a.persona_cache, a.mirofish_service_url]
    if a.meter_social_calls and not all(actor_options):
        p.error('--meter-social-calls requires native employees')
    if any(actor_options):
        if not all(actor_options): p.error('Native employees require backend, persona cache and service URL')
        from .employees import MiroFishEmployees
        employee_factory = MiroFishEmployees(*actor_options, a.model, a.base_url,
                                            meter_social_calls=a.meter_social_calls)
    if a.command == 'prepare':
        spec = expand_workforce(read(a.spec))
        if a.employee_examples: spec = attach_examples(spec, read(a.employee_examples))
        value = prepare_study(bank, spec, a.seeds, harness, judge, learner, a.out, employee_factory)
    else:
        value = execute_study(bank, harness, judge, learner, a.out, employee_factory)
    print(json.dumps(value, indent=2))


if __name__ == '__main__': main()
