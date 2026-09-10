"""Meter pinned Hermes Responses transport attempts before SDK dispatch.

The worker must use a dedicated AIAgent and SDK clients. This adapter covers the
pinned ``codex_responses`` path, including its internal stream retry. It is not
a provider-independent network billing meter. Lost usage receipts retain a
conservative reservation and are explicitly marked incomplete.
"""
from __future__ import annotations

import json
import threading
import time


class NativeBudgetExceeded(RuntimeError):
    pass


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _integer(value):
    return type(value) is int and value >= 0


class ResponsesBudget:
    def __init__(self, *, max_model_calls, max_output_tokens, max_total_tokens=None,
                 on_block=None, framing_reserve=2048):
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
        self.rows = []
        self.charged_tokens = 0
        self.exhausted = False
        self.blocked_calls = 0
        self.disabled_auxiliary_calls = []
        self._lock = threading.RLock()

    def block(self, reason):
        with self._lock:
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
            if len(self.rows) >= self.max_model_calls:
                self.block("Declared physical model-call budget exhausted")
            if self.max_total_tokens is not None and self.charged_tokens + reserve > self.max_total_tokens:
                self.block("Declared token budget cannot fit the next request reservation")
            row = {"dispatch": len(self.rows) + 1, "reserved_tokens": reserve,
                   "charged_tokens": reserve, "accounting": "reservation",
                   "status": "dispatched", "input_tokens": None, "output_tokens": None,
                   "total_tokens": None, "cache_read_tokens": None, "reasoning_tokens": None,
                   "output_cap": request["max_output_tokens"]}
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

        def create(**kwargs):
            if self.exhausted:
                self.block("Evaluation transport already stopped at its declared bound")
            request, row = self._reserve(kwargs)
            started = time.monotonic()
            try:
                response = original(**request)
                if request.get("stream"):
                    return _MeteredStream(self, row, response, started)
                self._receipt(row, response, "completed")
                row["wall_seconds"] = time.monotonic() - started
                return response
            except Exception as exc:
                row.update(status="dispatch_error", error_type=type(exc).__name__,
                           wall_seconds=time.monotonic() - started)
                raise

        client.responses.create = create
        client._big_world_budget = self
        return client

    def report(self):
        with self._lock:
            rows = [dict(row) for row in self.rows]
            totals = {key: sum(row[key] or 0 for row in rows)
                      for key in ("input_tokens", "output_tokens", "total_tokens")}
            return {"physical_model_calls": len(rows), "charged_tokens": self.charged_tokens,
                    "reported_tokens": totals["total_tokens"], **totals,
                    "accounting_complete": all(row["accounting"] == "reported" for row in rows),
                    "exhausted": self.exhausted, "blocked_calls": self.blocked_calls,
                    "disabled_auxiliary_calls": list(self.disabled_auxiliary_calls),
                    "operations": rows}


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


def install_native_budget(agent, *, max_model_calls, max_output_tokens, max_total_tokens=None):
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
                             max_total_tokens=max_total_tokens, on_block=stop)
    for name in ("_ensure_primary_openai_client", "_create_request_openai_client"):
        original = getattr(agent, name)

        def factory(*args, _original=original, **kwargs):
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
