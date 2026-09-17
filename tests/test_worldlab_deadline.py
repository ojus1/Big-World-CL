"""Durable dispatch reservations and deadline settlement without model access."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from lifespan.evaluation.budget import ResponsesBudget, NativeBudgetExceeded
from lifespan.evaluation.provider import provider_contract
from lifespan.tests.test_evaluation_budget import Client, usage_response
from worldlab.contracts import Budget
from worldlab.hermes_deadline import TaskDeadline, clock_contract, validate_clock, checkpoint_costs, audit_deadline, save


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provider = provider_contract('fixture', 'http://127.0.0.1:9999/v1')
        self.clock = clock_contract(10)
        self.budget = Budget(model_calls=3, output_tokens=64, total_tokens=10000, seconds=10)

    def meter(self, callback=None, clock=None):
        return ResponsesBudget(max_model_calls=3, max_output_tokens=64, max_total_tokens=10000,
            provider_contract=self.provider, deadline_monotonic=(clock or self.clock)['deadline_monotonic'],
            on_checkpoint=callback or (lambda report: save(self.root / 'METER_CHECKPOINT.json', report)))

    def wire(self):
        return {'model': 'fixture', 'input': 'Fixture request', 'max_output_tokens': 64,
                'stream': False, 'store': False, 'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}

    def client(self, responses):
        client = Client(responses); client.base_url = self.provider['base_url']
        return client

    def response(self):
        response = usage_response(); response.status = 'completed'; return response

    def test_reservation_is_durable_before_physical_dispatch(self):
        meter = self.meter(); observed = []
        def dispatch(**kwargs):
            observed.append(json.loads((self.root / 'METER_CHECKPOINT.json').read_bytes()))
            return self.response()
        client = self.client([]); client.responses.create = dispatch
        meter.wrap_client(client).responses.create(**self.wire())
        self.assertEqual(observed[0]['physical_model_calls'], 1)
        self.assertEqual(observed[0]['operations'][0]['accounting'], 'reservation')
        final = json.loads((self.root / 'METER_CHECKPOINT.json').read_bytes())
        self.assertEqual(final, meter.report())
        self.assertEqual((final['charged_tokens'], final['reported_tokens']), (15, 15))

    def test_failed_checkpoint_prevents_request(self):
        def broken(report):
            if report['physical_model_calls']: raise OSError('controlled storage failure')
        meter = self.meter(broken); client = self.client([self.response()]); meter.wrap_client(client)
        with self.assertRaises(OSError): client.responses.create(**self.wire())
        self.assertEqual(client.calls, [])

    def test_deadline_stops_tools_but_settles_accepted_response(self):
        clock = clock_contract(1, time.monotonic() - .7)
        meter = self.meter(clock=clock)
        tool = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
        def cleanup():
            if tool.poll() is None: tool.terminate(); tool.wait(timeout=5)
        self.addCleanup(cleanup)
        sandbox = NS(sandbox=NS(process=tool), cleanup=cleanup)
        save(self.root / 'READY.json', {'sandbox_pid': tool.pid})
        deadline = TaskDeadline(self.root, clock, meter, sandbox)
        entered, release, errors = threading.Event(), threading.Event(), []
        def dispatch(**kwargs):
            entered.set()
            if not release.wait(5): raise RuntimeError('fixture settlement not released')
            return self.response()
        client = self.client([]); client.responses.create = dispatch; meter.wrap_client(client)
        def request():
            try: client.responses.create(**self.wire())
            except Exception as exc: errors.append(exc)
        worker = threading.Thread(target=request); worker.start(); self.assertTrue(entered.wait(2))
        deadline.start()
        tool.wait(timeout=3)
        self.assertTrue(worker.is_alive(), 'Accepted inference should still be settling')
        self.assertTrue(meter.report()['exhausted'])
        self.assertFalse(meter.report()['accounting_complete'])
        release.set(); worker.join(timeout=3); deadline.finish()
        self.assertEqual(errors, [])
        self.assertTrue(meter.report()['accounting_complete'])
        self.assertEqual(meter.report()['charged_tokens'], 15)
        with self.assertRaises(NativeBudgetExceeded): client.responses.create(**self.wire())
        audit_deadline(self.root, clock, {'evaluation_budget': meter.report()})
        self.assertEqual(meter.report()['physical_model_calls'], 1)

    def test_worker_crash_retains_pre_dispatch_reservation(self):
        save(self.root / 'FIXTURE.json', {'provider': self.provider, 'clock': self.clock, 'wire': self.wire()})
        script = '''import json,os,sys
from pathlib import Path
from types import SimpleNamespace as NS
from lifespan.evaluation.budget import ResponsesBudget
from worldlab.hermes_deadline import save
root=Path(sys.argv[1]); spec=json.loads((root/'FIXTURE.json').read_bytes())
def dispatch(**kwargs): os._exit(23)
client=NS(base_url=spec['provider']['base_url'],max_retries=0,responses=NS(create=dispatch))
meter=ResponsesBudget(max_model_calls=3,max_output_tokens=64,max_total_tokens=10000,
 provider_contract=spec['provider'],deadline_monotonic=spec['clock']['deadline_monotonic'],
 on_checkpoint=lambda report:save(root/'METER_CHECKPOINT.json',report))
meter.wrap_client(client).responses.create(**spec['wire'])
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.root)], timeout=5)
        self.assertEqual(result.returncode, 23)
        costs = checkpoint_costs(self.root / 'METER_CHECKPOINT.json', self.provider, self.clock, self.budget)
        self.assertEqual(costs['physical_model_calls'], 1)
        self.assertGreater(costs['charged_tokens'], 64)
        self.assertFalse(costs['accounting_complete'])
        self.assertEqual(costs['reported_tokens'], 0)

    def test_missing_final_execution_does_not_become_complete_from_checkpoint(self):
        meter = self.meter(); client = self.client([self.response()]); meter.wrap_client(client)
        client.responses.create(**self.wire())
        costs = checkpoint_costs(self.root / 'METER_CHECKPOINT.json', self.provider, self.clock, self.budget)
        self.assertTrue(costs['checkpoint_accounting_complete'])
        self.assertFalse(costs['accounting_complete'])
        self.assertEqual(costs['charged_tokens'], 15)

    def test_deadline_notice_cannot_claim_an_early_stop(self):
        clock = clock_contract(1, time.monotonic() - 2); meter = self.meter(clock=clock)
        sandbox = NS(sandbox=NS(process=NS(pid=100, poll=lambda: -15)), cleanup=lambda: None)
        save(self.root / 'READY.json', {'sandbox_pid': 100})
        deadline = TaskDeadline(self.root, clock, meter, sandbox)
        deadline.expire()
        native = {'evaluation_budget': meter.report()}; audit_deadline(self.root, clock, native)
        p = self.root / 'DEADLINE_INTENT.json'; value = json.loads(p.read_bytes())
        value['observed_monotonic'] = clock['deadline_monotonic'] - 1; save(p, value)
        with self.assertRaisesRegex(ValueError, 'did not freeze'): audit_deadline(self.root, clock, native)

    def test_finalization_cannot_cancel_due_cleanup_before_timer_runs(self):
        clock = clock_contract(1, time.monotonic() - 2); meter = self.meter(clock=clock); cleaned = []
        sandbox = NS(sandbox=NS(process=NS(pid=100, poll=lambda: -15)), cleanup=lambda: cleaned.append(True))
        save(self.root / 'READY.json', {'sandbox_pid': 100})
        deadline = TaskDeadline(self.root, clock, meter, sandbox)
        deadline.timer = NS(cancel=lambda: None, join=lambda: None)
        deadline.finish(); deadline.expire()
        self.assertEqual(cleaned, [True])
        audit_deadline(self.root, clock, {'evaluation_budget': meter.report()})

    def test_changed_clock_and_costs_are_rejected(self):
        for changes in ({'settlement_seconds': 9999}, {'deadline_monotonic': 0}, {'active_seconds': 100}):
            with self.assertRaises(ValueError): validate_clock({**self.clock, **changes}, 10)
        meter = self.meter(); client = self.client([self.response()]); meter.wrap_client(client)
        client.responses.create(**self.wire()); value = meter.report(); value['charged_tokens'] = 0
        save(self.root / 'METER_CHECKPOINT.json', value)
        with self.assertRaises(ValueError):
            checkpoint_costs(self.root / 'METER_CHECKPOINT.json', self.provider, self.clock, self.budget)


if __name__ == '__main__': unittest.main()
