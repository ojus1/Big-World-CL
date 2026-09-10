# Four-role native actor capability preflight

This preflight checks whether the hosted model, patched MiroFish/OASIS path and
client receipt verifier can carry strict JSON for an employee, enterprise,
government agency and consumer. It is outside the learning study. Its fixed
fixtures test escaped quotes, braces, a backslash, Unicode and a newline, plus
all four role schemas. It does not test business decisions, learning gain or
long-horizon reliability.

Use a **fresh isolated checkout and MiroFish installation**, applying the pinned
patch and complete overrides from [SETUP.md](SETUP.md). Dependency and downloaded
model/Persona caches may be reused without installing or changing packages.
All mutable graph, simulation and output state must remain in the new checkout.
Create a private configuration with the selected provider credentials; never
commit it. Port 5002 must be free. No frontend is needed.

```bash
PYTHONDONTWRITEBYTECODE=1 MiroFish/backend/.venv/bin/python \
  scripts/preflight_actor_contract.py prepare --out lifespan/artifacts/actor-preflight-v1

# Review and retain the generated manifest, including its exact SHA-256.
PYTHONDONTWRITEBYTECODE=1 MiroFish/backend/.venv/bin/python \
  scripts/preflight_actor_contract.py execute --out lifespan/artifacts/actor-preflight-v1 \
  --manifest-sha256 REVIEWED_MANIFEST_SHA256
```

Preparation imports four pinned synthetic Persona records (seed 907), records
the exact cohort hash and fixed fixture hash, and binds source, transport,
dependency, provider, port and mutable-state paths. It makes no model calls;
missing Persona cache files can be downloaded by the existing importer. Native
execution requires the manifest hash and unchanged sources. Exclusive execution
intent prohibits retrying an uncertain preflight in place.

The supervisor starts only the new checkout's backend on loopback port 5002.
Before bootstrap, the worker verifies its parent, server PID and start time,
working directory, listening socket, imported config module and mutable paths.
The native client also performs the actor-contract capability handshake. Four
original interviews and at most one repair per role permit at most eight
contracted logical requests, with one physical dispatch each. Every request has
a 4,096 output-token cap and 120-second contract window. Shape/fixture failures
can use the existing repair; infrastructure or uncertain-usage failures stop.

The parent execution cap is 900 seconds including server startup; the worker
inherits that original monotonic deadline rather than starting a new clock. It
refuses interviews whose full contract window cannot fit. Execution is followed by
separately bounded cleanup (up to 120 seconds of process/network waits). The
supervisor closes the recorded simulation, checks native liveness and, if
necessary, requests a forced stop of that same simulation. Unconfirmed cleanup
cannot pass. It terminates its own worker/server process groups and separately
verifies the recorded OASIS PID and start identity: the native status file can
say stopped before the process finishes. After a brief grace period, only that
verified native process group may be terminated. An unknown or still-running
identity cannot pass. Do not
remove execution intent or caches to restart the same test.

Private outputs retain the cohort, prompts, native responses, logical request
ledger, returned receipts and logs. After cleanup, `EVIDENCE.json` inventories
all private output and native upload files by relative path and raw hash,
including native claims, receipts and SQLite traces. `SUMMARY.json` binds this
inventory and contains safe counts, role results, error classes and cleanup
status. A successful result requires
every role to match its declared fixture and all completed interview receipts to
pass the client/ledger/source audit. Graph generation, bootstrap/social calls
and currency remain unmetered; the eight-request and token caps cover contracted
interviews only. This is not a whole-run physical-cost ceiling.

Run the offline harness and transport checks without starting native services:

```bash
PYTHONDONTWRITEBYTECODE=1 MiroFish/backend/.venv/bin/python -m pytest \
  tests/test_actor_preflight.py tests/test_actor_output_contract.py -q
```

Native use requires independent review of the prepared code and exact manifest.
Any provider failure remains evidence. A correction needs new sources and a new
preflight registration; passing a later attempt does not erase earlier failures.
