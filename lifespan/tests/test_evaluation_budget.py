"""Offline transport tests: no API keys, HTTP requests or model inference."""
from types import SimpleNamespace as NS
import unittest

from lifespan.evaluation.budget import NativeBudgetExceeded, ResponsesBudget, install_native_budget


def usage_response(input_tokens=10, output_tokens=5):
    return NS(usage=NS(input_tokens=input_tokens, output_tokens=output_tokens,
                       total_tokens=input_tokens + output_tokens,
                       input_tokens_details=NS(cached_tokens=3),
                       output_tokens_details=NS(reasoning_tokens=2)))


class Stream:
    def __init__(self, events, close_error=None):
        self.events = iter(events)
        self.closed = False
        self.close_error = close_error

    def __iter__(self):
        return self

    def __next__(self):
        value = next(self.events)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self):
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class Client:
    def __init__(self, responses):
        self.max_retries = 2
        self.calls = []
        self.results = iter(responses)
        self.responses = NS(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class BudgetTests(unittest.TestCase):
    def meter(self, **kwargs):
        return ResponsesBudget(max_model_calls=kwargs.pop('max_model_calls', 4),
                               max_output_tokens=64, max_total_tokens=kwargs.pop('max_total_tokens', 100000),
                               **kwargs)

    def test_output_cap_clamps_actual_request_and_disables_sdk_retries(self):
        client = Client([usage_response()])
        budget = self.meter()
        budget.wrap_client(client).responses.create(input='text', max_output_tokens=32768)
        self.assertEqual(client.calls[0]['max_output_tokens'], 64)
        self.assertEqual(client.max_retries, 0)
        self.assertEqual(budget.report()['charged_tokens'], 15)
        self.assertTrue(budget.report()['accounting_complete'])

    def test_completed_stream_reconciles_actual_usage_once(self):
        response = usage_response()
        stream = Stream([NS(type='response.output_text.delta', delta='text'),
                         NS(type='response.completed', response=response)])
        client = Client([stream])
        budget = self.meter()
        wrapped = budget.wrap_client(client).responses.create(input='text', stream=True)
        self.assertEqual(len(list(wrapped)), 2)
        wrapped.close()
        result = budget.report()
        self.assertTrue(stream.closed)
        self.assertEqual(result['physical_model_calls'], 1)
        self.assertEqual(result['reported_tokens'], 15)
        self.assertEqual(result['charged_tokens'], 15)
        self.assertEqual(result['operations'][0]['cache_read_tokens'], 3)
        self.assertEqual(result['operations'][0]['reasoning_tokens'], 2)
        self.assertTrue(result['accounting_complete'])
        row = result['operations'][0]
        self.assertEqual(row['status'], 'response.completed')
        self.assertTrue(row['stream_ended'])
        self.assertEqual(row['stream_close_status'], 'completed')
        self.assertEqual(row['stream_close_attempts'], 1)

    def test_stream_retry_is_another_dispatch_and_missing_receipt_keeps_reservation(self):
        client = Client([Stream([ConnectionError('private provider detail')]),
                         Stream([NS(type='response.completed', response=usage_response())])])
        budget = self.meter()
        budget.wrap_client(client)
        with self.assertRaises(ConnectionError):
            list(client.responses.create(input='text', stream=True))
        list(client.responses.create(input='text', stream=True))
        result = budget.report()
        self.assertEqual(result['physical_model_calls'], 2)
        self.assertEqual(result['reported_tokens'], 15)
        self.assertGreater(result['charged_tokens'], result['reported_tokens'])
        self.assertFalse(result['accounting_complete'])
        self.assertNotIn('private provider detail', str(result))
        self.assertEqual(result['operations'][0]['error_type'], 'ConnectionError')

    def test_call_limit_blocks_hidden_retry_before_dispatch(self):
        client = Client([ConnectionError('lost request')])
        budget = self.meter(max_model_calls=1)
        budget.wrap_client(client)
        with self.assertRaises(ConnectionError):
            client.responses.create(input='text')
        with self.assertRaises(NativeBudgetExceeded):
            client.responses.create(input='text')
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(budget.report()['physical_model_calls'], 1)

    def test_token_reservation_blocks_before_any_api_request(self):
        client = Client([])
        budget = self.meter(max_total_tokens=50)
        budget.wrap_client(client)
        with self.assertRaises(NativeBudgetExceeded):
            client.responses.create(input='text')
        self.assertEqual(client.calls, [])
        self.assertEqual(budget.report()['charged_tokens'], 0)

    def test_nonstream_missing_or_invalid_receipt_is_never_measured_zero(self):
        for response in (NS(), NS(usage=NS(input_tokens=10, output_tokens=5, total_tokens=999)),
                         NS(usage=NS(input_tokens=True, output_tokens=5, total_tokens=6))):
            client = Client([response])
            budget = self.meter()
            budget.wrap_client(client).responses.create(input='text')
            result = budget.report()
            self.assertFalse(result['accounting_complete'])
            self.assertGreater(result['charged_tokens'], 0)
            self.assertEqual(result['operations'][0]['accounting'], 'reservation')

    def test_empty_and_closed_stream_keep_unknown_usage_reservation(self):
        for consume in (True, False):
            stream = Stream([])
            client = Client([stream])
            budget = self.meter()
            wrapped = budget.wrap_client(client).responses.create(input='text', stream=True)
            if consume:
                list(wrapped)
            wrapped.close()
            self.assertFalse(budget.report()['accounting_complete'])
            self.assertGreater(budget.report()['charged_tokens'], 0)
            row = budget.report()['operations'][0]
            self.assertEqual(row['status'], 'stream_ended_without_receipt' if consume
                             else 'stream_closed_without_receipt')
            self.assertEqual(row.get('stream_ended', False), consume)
            self.assertEqual(row['stream_close_status'], 'completed')

    def test_read_error_survives_end_and_close_without_recovering_unknown_usage(self):
        class ReadError(Exception):
            pass  # Fake transport exception; this test never imports or calls a provider.

        budget = self.meter()
        wrapped = budget.wrap_client(Client([Stream([ReadError('private body')])])).responses.create(
            input='text', stream=True)
        reserved = budget.report()['charged_tokens']
        with self.assertRaises(ReadError):
            next(wrapped)
        with self.assertRaises(StopIteration):
            next(wrapped)
        wrapped.close()
        report = budget.report()
        row = report['operations'][0]
        self.assertEqual((row['status'], row['error_type']), ('stream_error', 'ReadError'))
        self.assertTrue(row['stream_ended'])
        self.assertEqual(row['stream_close_status'], 'completed')
        self.assertEqual(report['charged_tokens'], reserved)
        self.assertEqual(report['reported_tokens'], 0)
        self.assertFalse(report['accounting_complete'])
        self.assertTrue(all(row[key] is None for key in ('input_tokens', 'output_tokens', 'total_tokens')))
        self.assertNotIn('private body', str(report))

    def test_close_error_is_separate_and_cannot_erase_prior_stream_error_or_receipt(self):
        for initial in ('unconsumed', 'read_error', 'receipt'):
            with self.subTest(initial=initial):
                events = [ConnectionError('private read body')] if initial == 'read_error' else (
                    [NS(type='response.completed', response=usage_response())] if initial == 'receipt' else [])
                raw = Stream(events, close_error=OSError('private close body'))
                budget = self.meter()
                wrapped = budget.wrap_client(Client([raw])).responses.create(input='text', stream=True)
                if initial == 'read_error':
                    with self.assertRaises(ConnectionError):
                        next(wrapped)
                elif initial == 'receipt':
                    list(wrapped)
                before = budget.report()
                with self.assertRaises(OSError):
                    wrapped.close()
                # Repeated cleanup can succeed, but cannot conceal the earlier failure.
                raw.close_error = None
                wrapped.close()
                report = budget.report()
                row = report['operations'][0]
                self.assertEqual(row['status'], {'unconsumed': 'stream_close_error',
                    'read_error': 'stream_error', 'receipt': 'response.completed'}[initial])
                self.assertEqual(row.get('error_type'), {'unconsumed': 'OSError',
                    'read_error': 'ConnectionError', 'receipt': None}[initial])
                self.assertEqual(row['stream_close_status'], 'failed')
                self.assertEqual(row['stream_close_error_type'], 'OSError')
                self.assertEqual(row['stream_close_attempts'], 2)
                for key in ('charged_tokens', 'reported_tokens', 'physical_model_calls', 'accounting_complete'):
                    self.assertEqual(report[key], before[key])
                self.assertNotIn('private', str(report))

    def test_invalid_terminal_usage_diagnosis_survives_close(self):
        budget = self.meter()
        wrapped = budget.wrap_client(Client([Stream([NS(type='response.completed', response=NS())])
            ])).responses.create(input='text', stream=True)
        list(wrapped)
        wrapped.close()
        report = budget.report()
        self.assertEqual(report['operations'][0]['status'], 'missing_or_invalid_usage')
        self.assertFalse(report['accounting_complete'])

    def test_dispatch_error_keeps_unknown_reservation_and_class_only(self):
        budget = self.meter()
        with self.assertRaises(ConnectionError):
            budget.wrap_client(Client([ConnectionError('private body')])).responses.create(input='text', stream=True)
        report = budget.report()
        row = report['operations'][0]
        self.assertEqual((row['status'], row['error_type']), ('dispatch_error', 'ConnectionError'))
        self.assertEqual(row['charged_tokens'], row['reserved_tokens'])
        self.assertNotIn('stream_close_status', row)
        self.assertNotIn('private body', str(report))

    def test_additive_stream_evidence_preserves_existing_audit_eligibility(self):
        from copy import deepcopy
        from lifespan.evaluation.runtime import native_usage
        from scripts.audit_evaluation import meter_check

        for outcome in ('receipt', 'receipt_close_error', 'unknown', 'physical_overrun'):
            with self.subTest(outcome=outcome):
                event = ConnectionError('private body') if outcome == 'unknown' else NS(
                    type='response.completed', response=usage_response(output_tokens=100 if outcome == 'physical_overrun' else 5))
                budget = self.meter()
                raw = Stream([event], close_error=OSError('private close body')
                             if outcome == 'receipt_close_error' else None)
                wrapped = budget.wrap_client(Client([raw])).responses.create(input='text', stream=True)
                if outcome == 'unknown':
                    with self.assertRaises(ConnectionError):
                        list(wrapped)
                else:
                    list(wrapped)
                if outcome == 'receipt_close_error':
                    with self.assertRaises(OSError):
                        wrapped.close()
                else:
                    wrapped.close()
                native = {'evaluation_budget': budget.report()}
                valid = outcome.startswith('receipt')
                record = {'result': {'native': native}, 'usage': native_usage(native),
                          'infrastructure_valid': valid}
                for legacy in (False, True):
                    candidate = deepcopy(record)
                    if legacy:
                        row = candidate['result']['native']['evaluation_budget']['operations'][0]
                        for key in ('stream_ended', 'stream_close_status', 'stream_close_attempts',
                                    'stream_close_error_type'):
                            row.pop(key, None)
                        if outcome == 'unknown':
                            row['status'] = 'stream_closed_without_receipt'
                    if valid:
                        meter_check(candidate)
                    else:
                        with self.assertRaisesRegex(ValueError, 'trial_infrastructure_or_accounting_invalid'
                            if outcome == 'unknown' else 'provider_budget_overrun'):
                            meter_check(candidate)
                if outcome == 'unknown':
                    self.assertIsNone(record['usage']['total_tokens'])
                    self.assertFalse(record['usage']['complete'])

    def test_incomplete_response_with_real_usage_still_charges_actual_tokens(self):
        client = Client([Stream([{'type': 'response.incomplete',
                                  'response': {'usage': {'input_tokens': 20, 'output_tokens': 64, 'total_tokens': 84}}}])])
        budget = self.meter()
        list(budget.wrap_client(client).responses.create(input='text', stream=True))
        self.assertEqual(budget.report()['charged_tokens'], 84)
        self.assertEqual(budget.report()['operations'][0]['status'], 'response.incomplete')
        self.assertTrue(budget.report()['accounting_complete'])

    def test_provider_overrun_retains_actual_cost_and_blocks_further_work(self):
        client = Client([usage_response(10, 100)])
        budget = self.meter()
        budget.wrap_client(client).responses.create(input='text')
        self.assertEqual(budget.report()['charged_tokens'], 110)
        self.assertTrue(budget.report()['exhausted'])
        with self.assertRaises(NativeBudgetExceeded):
            client.responses.create(input='text')
        self.assertEqual(len(client.calls), 1)

    def test_same_client_is_wrapped_once_and_cannot_cross_budgets(self):
        client = Client([usage_response()])
        budget = self.meter()
        budget.wrap_client(client)
        budget.wrap_client(client).responses.create(input='text')
        self.assertEqual(budget.report()['physical_model_calls'], 1)
        with self.assertRaises(ValueError):
            self.meter().wrap_client(client)

    def test_install_covers_primary_factory_and_request_factory(self):
        primary = Client([usage_response()])
        request = Client([usage_response()])
        agent = NS(api_mode='codex_responses', client=primary,
                   _ensure_primary_openai_client=lambda **kwargs: primary,
                   _create_request_openai_client=lambda **kwargs: request,
                   interrupt=lambda *args, **kwargs: None,
                   context_compressor=NS(_micro_compact_enabled=True, _call_summary_llm=lambda: None))
        budget = install_native_budget(agent, max_model_calls=3, max_output_tokens=64)
        agent._ensure_primary_openai_client(reason='summary').responses.create(input='primary')
        agent._create_request_openai_client(reason='retry').responses.create(input='request')
        self.assertEqual(budget.report()['physical_model_calls'], 2)
        self.assertEqual((primary.max_retries, request.max_retries), (0, 0))
        self.assertFalse(agent.context_compressor._micro_compact_enabled)
        self.assertIn('no additional', agent._handle_max_iterations([], 3))
        self.assertEqual(budget.report()['physical_model_calls'], 2)
        with self.assertRaises(NativeBudgetExceeded):
            agent._compress_context([], '')
        with self.assertRaises(NativeBudgetExceeded):
            agent.context_compressor._call_summary_llm()
        self.assertEqual(budget.report()['physical_model_calls'], 2)

    def test_invalid_limits_and_unsupported_provider_fail_closed(self):
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                ResponsesBudget(max_model_calls=value, max_output_tokens=64)
        with self.assertRaises(ValueError):
            install_native_budget(NS(api_mode='chat_completions'), max_model_calls=3, max_output_tokens=64)


if __name__ == '__main__':
    unittest.main()
