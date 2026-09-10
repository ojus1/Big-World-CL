# Preserve stream failure evidence during cleanup

This change applies to future executions. It improves diagnostics for the pinned
Hermes Responses transport; it does not recover a lost provider usage receipt or
make an incomplete run eligible for comparison. Existing campaign artifacts are
unchanged.

Previously, a stream read exception recorded `status=stream_error` and its
exception class, but subsequent cleanup replaced the status with
`stream_closed_without_receipt`. Stream exhaustion and close now preserve an
already recorded receipt, error or missing-usage status. A `ReadError` followed by
close therefore retains `status=stream_error` and `error_type=ReadError`.
Exception messages, response bodies and endpoint details are not added to the
meter.

The operation records cleanup separately:

| Field | Meaning |
|---|---|
| `stream_ended` | The iterator raised `StopIteration`; this alone is not a provider receipt. |
| `stream_close_attempts` | Number of explicit close calls, not model requests. |
| `stream_close_status` | `completed` or `failed`; a failure remains visible after a later successful close. |
| `stream_close_error_type` | First exception class raised by close, when present. |

A close failure before any terminal event records `status=stream_close_error`
and its exception class. If a receipt or earlier failure is already recorded,
the close failure leaves that status intact and appears in the separate cleanup
fields. Exceptions still propagate. An ordinary no-receipt iterator end remains
`stream_ended_without_receipt` after close; an unconsumed stream closed normally
remains `stream_closed_without_receipt`.

Accounting, dispatch limits, retries, deadlines and eligibility are unchanged.
A reported receipt retains its measured input/output tokens even if cleanup
fails. A missing receipt retains its conservative reservation and unknown token
total. A successful later Hermes retry does not supply usage for the earlier
failed request. Physical cap violations and incomplete accounting remain invalid.
The existing `wall_seconds` scope continues through stream cleanup; the new
fields do not estimate physical inference time.

The fields are additive diagnostics, not a new accounting policy or learning
evidence version. Existing native usage and independent meter checks accept
complete within-cap receipt fixtures with or without these fields, and reject
unknown reservations and physical overruns in both formats. Historical receipts
are not rewritten or reinterpreted. Source hashes distinguish future execution
bytes from prior campaign code.

Offline fake-stream regressions cover read failure followed by end/close,
reported receipt followed by close, ordinary no-receipt termination, close
failure before/after a receipt or prior error, repeated cleanup, invalid usage,
dispatch failure and unchanged independent-audit eligibility. These tests make
no provider requests and provide no evidence about model quality or provider
reliability.
