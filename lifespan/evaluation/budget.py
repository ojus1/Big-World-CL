"""Meter pinned Hermes Responses transport attempts before SDK dispatch.

The worker must use a dedicated AIAgent and SDK clients. This adapter covers the
pinned ``codex_responses`` path, including its internal stream retry. It is not
a provider-independent network billing meter. Lost usage receipts retain a
conservative reservation and are explicitly marked incomplete.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import threading
import time


class NativeBudgetExceeded(RuntimeError):
    pass


class NativeProviderStopped(InterruptedError):
    """A terminal profiled transport failure; native Hermes must not retry."""


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _integer(value):
    return type(value) is int and value >= 0


def _error_type(exc):
    name = type(exc).__name__
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', name) else 'Exception'


def availability_classification(error_type, http_status=None):
    if error_type in ('APITimeoutError', 'TimeoutError', 'TimeoutException', 'ConnectTimeout',
                      'ReadTimeout', 'WriteTimeout', 'PoolTimeout'):
        return 'timeout'
    if error_type in ('APIConnectionError', 'ConnectionError', 'ConnectError', 'ReadError',
                      'WriteError', 'RemoteProtocolError', 'NetworkError'):
        return 'connection_error'
    if type(http_status) is int and 500 <= http_status <= 599:
        return 'server_unavailable'
    return 'other_terminal_failure'


class ResponsesBudget:
    def __init__(self, *, max_model_calls, max_output_tokens, max_total_tokens=None,
                 on_block=None, framing_reserve=2048, provider_contract=None, on_failure=None):
        for name, value in (("max_model_calls", max_model_calls),
                            ("max_output_tokens", max_output_tokens),
                            ("framing_reserve", framing_reserve)):
            if not _integer(value) or value < 1:
                raise ValueError(name + " must be a positive integer")
        if max_total_tokens is not None and (not _integer(max_total_tokens) or max_total_tokens < 1):
            raise ValueError("max_total_tokens must be a positive integer or None")
        self.max_model_calls = max_model_calls
        self.max_output_tokens = max_output_tokens
        self.max_total_tokens = max_total_tokens
        self.framing_reserve = framing_reserve
        self.on_block = on_block
        self.on_failure = on_failure
        if provider_contract is not None:
            from .provider import validate_contract
            provider_contract = validate_contract(provider_contract)
        self.provider_contract = provider_contract
        self.rows = []
        self.charged_tokens = 0
        self.exhausted = False
        self.stopped = False
        self.terminal_failure = None
        self.blocked_calls = 0
        self.disabled_auxiliary_calls = []
        self._lock = threading.RLock()
        # Dedicated synchronous Hermes request clients can be recreated by its
        # retry loop. Serialize the profiled physical seam across all of them,
        # so a waiting request cannot pass a check made before the first error.
        self._dispatch_lock = threading.RLock()

    def ensure_running(self):
        with self._lock:
            if self.stopped:
                self.blocked_calls += 1
                raise NativeProviderStopped('Profiled provider transport is terminally stopped')

    def _fail(self, row, reason):
        """Latch before notifying/cancelling; neither callback can enable retry."""
        if self.provider_contract is None:
            return
        with self._lock:
            first = not self.stopped
            if first:
                self.stopped = True
                self.terminal_failure = {'reason': reason, 'dispatch': row['dispatch'],
                    'operation_status': row['status'], 'error_type': row.get('error_type'),
                    'accounting': row['accounting'],
                    'provider_response_status': row.get('provider_response_status'),
                    'http_status': row.get('http_status'),
                    'availability_classification': availability_classification(
                        row.get('error_type'), row.get('http_status')),
                    'observed_monotonic': time.monotonic()}
        if first:
            # Publish before native cancellation (which may wait on a native
            # lock). Preserve safe callback failures without masking costs or
            # clearing the latch if the host filesystem/cancel hook fails.
            for callback, key, argument in ((self.on_failure, 'notification_error_type', self.report()),
                    (self.on_block, 'cancellation_error_type', 'Profiled provider transport stopped')):
                if callback:
                    try:
                        callback(argument)
                    except Exception as exc:
                        with self._lock:
                            self.terminal_failure[key] = _error_type(exc)
        raise NativeProviderStopped('Profiled provider transport stopped: ' + reason) from None

    def block(self, reason):
        with self._lock:
            self.ensure_running()
            self.exhausted = True
            self.blocked_calls += 1
        if self.on_block:
            self.on_block(reason)
        raise NativeBudgetExceeded(reason)

    def _reserve(self, kwargs):
        # Current text-only task requests: UTF-8 bytes conservatively bound
        # byte-token text, with explicit framing allowance. Clamp the actual
        # wire output cap, including Hermes length-continuation increases.
        request = dict(kwargs)
        proposed = request.get("max_output_tokens", self.max_output_tokens)
        if not _integer(proposed) or proposed < 1:
            self.block("Invalid Responses output token cap")
        request["max_output_tokens"] = min(proposed, self.max_output_tokens)
        reserve = (len(json.dumps(request, ensure_ascii=False, default=str).encode())
                   + request["max_output_tokens"] + self.framing_reserve)
        with self._lock:
            self.ensure_running()
            if len(self.rows) >= self.max_model_calls:
                self.block("Declared physical model-call budget exhausted")
            if self.max_total_tokens is not None and self.charged_tokens + reserve > self.max_total_tokens:
                self.block("Declared token budget cannot fit the next request reservation")
            row = {"dispatch": len(self.rows) + 1, "reserved_tokens": reserve,
                   "charged_tokens": reserve, "accounting": "reservation",
                   "status": "dispatched", "input_tokens": None, "output_tokens": None,
                   "total_tokens": None, "cache_read_tokens": None, "reasoning_tokens": None,
                   "output_cap": request["max_output_tokens"],
                   "request_stream": request.get("stream", False)}
            self.rows.append(row)
            self.charged_tokens += reserve
        return request, row

    def _receipt(self, row, response, status):
        usage = _get(response, "usage")
        values = {key: _get(usage, key) for key in ("input_tokens", "output_tokens", "total_tokens")}
        valid = all(_integer(x) for x in values.values())
        valid = valid and values["total_tokens"] == values["input_tokens"] + values["output_tokens"]
        with self._lock:
            if row["accounting"] == "reported":
                return
            if not valid:
                row["status"] = "missing_or_invalid_usage"
                if self.provider_contract is not None:
                    # These are independently observed dimensions, not a valid
                    # total. Keep the original reservation/main audit equation;
                    # never relabel inconsistent or partial usage as measured.
                    row['observed_usage'] = {key: value if _integer(value) else None
                                             for key, value in values.items()}
                return
            self.charged_tokens += values["total_tokens"] - row["charged_tokens"]
            row.update(values, charged_tokens=values["total_tokens"], accounting="reported", status=status)
            for key, parent, child in (("cache_read_tokens", "input_tokens_details", "cached_tokens"),
                                       ("reasoning_tokens", "output_tokens_details", "reasoning_tokens")):
                value = _get(_get(usage, parent), child)
                row[key] = value if _integer(value) else None
            if values["total_tokens"] > row["reserved_tokens"] or values["output_tokens"] > row["output_cap"]:
                # A provider contract/accounting overrun invalidates the bound;
                # retain actual usage and prevent any subsequent dispatch.
                row["status"] = "provider_budget_overrun"
                self.exhausted = True

    def wrap_client(self, client):
        """Wrap a dedicated synchronous OpenAI SDK client in place, once."""
        if getattr(client, "_big_world_budget", None) is self:
            return client
        if getattr(client, "_big_world_budget", None) is not None:
            raise ValueError("Client already belongs to another evaluation budget")
        # SDK retry loops run below responses.create and cannot yield a receipt
        # per attempt here. Disable them; Hermes retries call our wrapper again.
        client.max_retries = 0
        original = client.responses.create

        def dispatch(kwargs):
            self.ensure_running()
            if self.exhausted:
                self.block("Evaluation transport already stopped at its declared bound")
            readbacks = self._provider_readbacks(client, kwargs)
            request, row = self._reserve(kwargs)
            row.update(readbacks)
            started = time.monotonic()
            try:
                response = original(**request)
                if request.get("stream"):
                    return _MeteredStream(self, row, response, started)
                provider_status = _get(response, "status")
                row["provider_response_status"] = (provider_status if type(provider_status) is str
                    and provider_status in ("completed", "incomplete", "failed", "cancelled", "queued", "in_progress")
                    else None)
                self._receipt(row, response, "completed")
                row["wall_seconds"] = time.monotonic() - started
            except Exception as exc:
                row.update(status="dispatch_error", error_type=_error_type(exc),
                           wall_seconds=time.monotonic() - started)
                if self.provider_contract is not None:
                    code = getattr(exc, 'status_code', None)
                    row['http_status'] = code if type(code) is int and 100 <= code <= 599 else None
                self._fail(row, 'dispatch_error')
                raise
            if row['status'] in ('missing_or_invalid_usage', 'provider_budget_overrun'):
                self._fail(row, row['status'])
            if self.provider_contract is not None and provider_status not in ('completed', 'incomplete'):
                self._fail(row, 'provider_response_not_completed')
            return response

        def create(**kwargs):
            if self.provider_contract is None:
                return dispatch(kwargs)
            with self._dispatch_lock:
                return dispatch(kwargs)

        client.responses.create = create
        client._big_world_budget = self
        return client

    def _provider_readbacks(self, client, request):
        """Bind the actual SDK boundary without recording credentials or inputs."""
        if self.provider_contract is None:
            return {}
        from .provider import validate_contract
        policy = validate_contract(self.provider_contract)
        extra = request.get('extra_body')
        template = extra.get('chat_template_kwargs') if type(extra) is dict else None
        base_url = str(getattr(client, 'base_url', '')).rstrip('/')
        if not (base_url == policy['base_url'] and request.get('model') == policy['model']
                and client.max_retries == 0 and request.get('stream') is False and request.get('store') is False
                and type(extra) is dict and set(extra) == {'chat_template_kwargs'}
                and type(template) is dict and set(template) == {'enable_thinking'}
                and template['enable_thinking'] is False and request.get('reasoning') in (None, {})):
            raise ValueError('Physical Responses request differs from the registered provider contract')
        return {'provider_contract': policy, 'request_api_mode': 'responses',
                'request_model': request['model'], 'request_base_url': base_url,
                'request_store': False, 'request_chat_template_kwargs': deepcopy(template)}

    def report(self):
        with self._lock:
            rows = [deepcopy(row) for row in self.rows]
            totals = {key: sum(row[key] or 0 for row in rows)
                      for key in ("input_tokens", "output_tokens", "total_tokens")}
            return {"physical_model_calls": len(rows), "charged_tokens": self.charged_tokens,
                    "reported_tokens": totals["total_tokens"], **totals,
                    "accounting_complete": all(row["accounting"] == "reported" for row in rows),
                    "exhausted": self.exhausted, "blocked_calls": self.blocked_calls,
                    "disabled_auxiliary_calls": list(self.disabled_auxiliary_calls),
                    "operations": rows,
                    **({'provider_contract': deepcopy(self.provider_contract), 'stopped': self.stopped,
                        'terminal_failure': deepcopy(self.terminal_failure)}
                       if self.provider_contract is not None else {})}


class _MeteredStream:
    def __init__(self, budget, row, stream, started):
        self._budget, self._row, self._stream = budget, row, stream
        self._iterator = iter(stream)
        self._started = started

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self._iterator)
            kind = _get(event, "type", "")
            if kind in ("response.completed", "response.incomplete", "response.failed"):
                self._budget._receipt(self._row, _get(event, "response"), kind)
            return event
        except StopIteration:
            self._row["stream_ended"] = True
            self._finish("stream_ended_without_receipt")
            raise
        except Exception as exc:
            self._finish("stream_error")
            self._row.setdefault("error_type", type(exc).__name__)
            raise

    def _finish(self, status):
        self._row["wall_seconds"] = time.monotonic() - self._started
        # Cleanup must not erase the first terminal receipt/error diagnosis.
        # In particular, a read failure followed by close still has unknown
        # usage, but its cause is stream_error rather than an ordinary close.
        if self._row["accounting"] != "reported" and self._row["status"] == "dispatched":
            self._row["status"] = status

    def close(self):
        status = "stream_closed_without_receipt"
        self._row["stream_close_attempts"] = self._row.get("stream_close_attempts", 0) + 1
        try:
            result = self._stream.close()
        except Exception as exc:
            status = "stream_close_error"
            self._row["stream_close_status"] = "failed"
            self._row.setdefault("stream_close_error_type", type(exc).__name__)
            if self._row["status"] == "dispatched":
                self._row.setdefault("error_type", type(exc).__name__)
            raise
        else:
            # A later successful close must not hide an earlier close failure.
            self._row.setdefault("stream_close_status", "completed")
            return result
        finally:
            self._finish(status)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_native_budget(agent, *, max_model_calls, max_output_tokens, max_total_tokens=None,
                          provider_contract=None, on_failure=None):
    """Install on one pinned native Hermes ``codex_responses`` agent.

    Return a meter whose report is authoritative for transport attempts. Disable
    auxiliary summarization/compaction inference rather than allowing it to use
    a separate unmetered client. Main task trials remain normal native Hermes.
    """
    if getattr(agent, "api_mode", None) != "codex_responses":
        raise ValueError("Evaluation transport meter requires codex_responses")
    if getattr(agent, "_big_world_budget", None) is not None:
        raise ValueError("Agent already has an evaluation transport budget")

    def stop(reason):
        agent.interrupt(reason, hard_cancel=True)

    budget = ResponsesBudget(max_model_calls=max_model_calls, max_output_tokens=max_output_tokens,
                             max_total_tokens=max_total_tokens, on_block=stop,
                             provider_contract=provider_contract, on_failure=on_failure)
    for name in ("_ensure_primary_openai_client", "_create_request_openai_client"):
        original = getattr(agent, name)

        def factory(*args, _original=original, **kwargs):
            budget.ensure_running()
            return budget.wrap_client(_original(*args, **kwargs))

        setattr(agent, name, factory)
    budget.wrap_client(agent.client)

    def no_summary(*args, **kwargs):
        budget.disabled_auxiliary_calls.append("iteration_summary")
        return "Evaluation iteration budget reached; no additional summary model call was made."

    def no_compression(*args, **kwargs):
        budget.disabled_auxiliary_calls.append("context_compression")
        budget.block("Context compaction inference is disabled in the controlled evaluation")

    agent._handle_max_iterations = no_summary
    agent._compress_context = no_compression
    compressor = getattr(agent, "context_compressor", None)
    if compressor is not None:
        compressor._micro_compact_enabled = False
        # Defense against a direct compressor call that bypasses the AIAgent
        # seam. These methods contain all summary inference in this revision.
        for name in ("_generate_summary", "_build_chunk_digests", "_micro_summarize_one",
                     "_call_summary_llm", "_micro_compact", "compress"):
            if callable(getattr(compressor, name, None)):
                setattr(compressor, name, no_compression)
    agent._big_world_budget = budget
    return budget
