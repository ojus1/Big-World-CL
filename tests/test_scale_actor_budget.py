"""Offline logical-request accounting; no OASIS/model usage is inferred."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lifespan.mirofish import MiroFishRuntime


class ActorBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = MiroFishRuntime.__new__(MiroFishRuntime)
        self.runtime.out = Path(self.tmp.name)
        self.runtime.state = {'simulation': {'simulation_id': 'fixture'}}
        self.runtime.employee_ids = {'employee': 0}
        self.runtime.evaluation_max_interviews = 1
        self.calls = []
        def call(*args, **kwargs):
            self.calls.append((args, kwargs))
            ledger = json.loads((self.runtime.out / 'evaluation_interview_ledger.json').read_text())
            self.assertEqual(ledger['requests'][-1]['status'], 'dispatched')
            return {'result': {'response': 'fixture response'}}
        self.runtime.call = call

    def test_intent_precedes_dispatch_and_completed_cache_is_free(self):
        self.assertEqual(self.runtime.interview('employee', 'prompt', 'one'), 'fixture response')
        self.runtime.interview('employee', 'prompt', 'one')
        self.assertEqual(len(self.calls), 1)
        ledger = json.loads((self.runtime.out / 'evaluation_interview_ledger.json').read_text())
        self.assertEqual(ledger['requests'][0]['status'], 'completed')
        self.assertEqual(ledger['requests'][0]['response_sha256'], hashlib.sha256(b'fixture response').hexdigest())
        self.assertIsNone(ledger['tokens'])
        self.assertIsNone(ledger['physical_model_calls'])

    def test_request_limit_prevents_extra_network_call(self):
        self.runtime.interview('employee', 'prompt', 'one')
        with self.assertRaisesRegex(RuntimeError, 'budget exhausted'):
            self.runtime.interview('employee', 'second prompt', 'two')
        self.assertEqual(len(self.calls), 1)

    def test_uncertain_request_retains_reservation_and_refuses_replay(self):
        def fail(*args, **kwargs):
            self.calls.append('failed')
            raise TimeoutError('fixture')
        self.runtime.call = fail
        with self.assertRaises(TimeoutError):
            self.runtime.interview('employee', 'prompt', 'one')
        with self.assertRaisesRegex(RuntimeError, 'refusing automatic replay'):
            self.runtime.interview('employee', 'prompt', 'one')
        self.assertEqual(len(self.calls), 1)

    def test_budget_change_is_rejected(self):
        self.runtime.interview('employee', 'prompt', 'one')
        self.runtime.evaluation_max_interviews = 2
        with self.assertRaisesRegex(ValueError, 'budget changed'):
            self.runtime.interview('employee', 'prompt', 'two')

    def test_legacy_runtime_has_no_new_ledger(self):
        self.runtime.evaluation_max_interviews = None
        self.runtime.call = lambda *args, **kwargs: {'result': {'response': 'legacy'}}
        self.assertEqual(self.runtime.interview('employee', 'prompt', 'one'), 'legacy')
        self.assertFalse((self.runtime.out / 'evaluation_interview_ledger.json').exists())


if __name__ == '__main__':
    unittest.main()
