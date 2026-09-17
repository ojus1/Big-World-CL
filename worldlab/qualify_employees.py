"""Qualify new role assignments and native employee decisions on day-zero views.

No solver, synthetic feedback, learning or future task view is introduced.
The native environments are new and their interview receipts remain auditable.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from scripts.source_world_calibration import read, save, sha
from .bank import Bank
from .campaign import source_identity
from .employees import MiroFishEmployees, audit_native_decision, audit_social_usage
from .hermes import Hermes
from .qualitative import FrozenRubricJudge
from .workforce import expand_workforce
from .workplace import Workplace
from .worlds import compile_world
from .validation_context import employee_world


def qualify(bank, spec, harness, judge, factory, out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    world = compile_world(bank, expand_workforce(spec), 307, harness, judge)
    context = factory.prepare(employee_world(world))
    save(out / 'PLAN.json', {'source_sha256': source_identity(), 'world': world, 'employee_context': context,
        'employee_driver': factory.identity(), 'scope': 'Native bootstrap and one released day-zero decision per employee only.'})
    place = Workplace(world); place.advance(0)
    save(out / 'INFLIGHT.json', {'kind': 'bootstrap'})
    driver = factory.open(employee_world(world), context, out / 'actors')
    rows = []
    try:
        for employee in sorted(place.profiles):
            oid = place.available(employee)[0]
            key = 'day-zero-' + employee
            view = place.view(employee, oid, bank)
            save(out / 'INFLIGHT.json', {'kind': 'employee_decision', 'id': key})
            decision = driver.decide(view, key, lambda d: deepcopy(place).decide(employee, oid, d))
            place.decide(employee, oid, decision)
            receipts = audit_native_decision(out / 'actors', factory.identity(), view, decision, key)
            rows.append({'id': key, 'view': view, 'decision': decision, 'native_receipts_verified': len(receipts)})
            save(out / 'PROGRESS.json', {'rows': rows, 'usage': driver.usage()})
        (out / 'INFLIGHT.json').unlink()
        result = {'ok': len(rows) == len(place.profiles), 'employee_decisions': len(rows), 'usage': driver.usage(),
                  'plan_sha256': sha(out / 'PLAN.json'), 'scope': 'Native role/view/decision contract qualification only.'}
    finally:
        save(out / 'WORKPLACE.json', place.state)
        try:
            save(out / 'USAGE.json', driver.usage())
        finally:
            driver.close()
    result['social_usage_audit'] = audit_social_usage(out / 'actors', factory.identity(), result['usage'])
    save(out / 'QUALIFICATION.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('bank', 'spec', 'out', 'hermes-root', 'mirofish-backend', 'persona-cache'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--mirofish-service-url', default='http://127.0.0.1:5001')
    p.add_argument('--meter-social-calls', action='store_true')
    p.add_argument('--model', default='Qwen/Qwen3.8-Flash-Next-FP8')
    p.add_argument('--base-url', default='http://127.0.0.1:8011/v1')
    a = p.parse_args()
    bank = Bank(a.bank)
    factory = MiroFishEmployees(a.mirofish_backend, a.persona_cache, a.mirofish_service_url, a.model, a.base_url,
                               meter_social_calls=a.meter_social_calls)
    print(json.dumps(qualify(bank, read(a.spec), Hermes(a.hermes_root, a.model, a.base_url),
                            FrozenRubricJudge(bank, a.model, a.base_url), factory, a.out), indent=2))
