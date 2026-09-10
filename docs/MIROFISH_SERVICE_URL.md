# Isolated MiroFish service for new evaluations

Set `mirofish_service_url` in the JSON `ExperimentConfig` when a new evaluation
must use a separately installed local MiroFish service, for example:

```json
{"mirofish_service_url": "http://127.0.0.1:5002"}
```

Merge this option into the complete registered configuration and pass that file
to `python -m lifespan.evaluation.runner --config CONFIG.json --out NEW_RUN`.
The setting selects a service; it does not start, install or isolate that service.
The launcher must verify that the intended fresh installation owns its port and
uses separate mutable graph and simulation directories. Existing campaigns and
their service on port 5001 must retain their original configuration and sources.

The option accepts HTTP on a loopback IP with an explicit port from 1 through
65535. `localhost` becomes `127.0.0.1`; IPv6 loopback is supported. An optional
root slash is removed. Credentials, other hostnames, nonloopback addresses,
paths, queries, fragments and whitespace are rejected. The canonical URL appears
in the config, scenario, run manifest and report provenance. Omitting the option
preserves the historical `http://127.0.0.1:5001` default and adds no URL fields to
those historical public objects.

`NativeActors` supplies the URL to the actual `MiroFishRuntime` HTTP client.
Explicit runs disable environment proxies and redirects for that client, then
record its actual URL and routing settings in `actors/evaluation_service.json`
before any capability handshake or bootstrap. Every later native request checks
these settings again. A different URL, a removed binding, or preexisting native
state without a binding is rejected. Reopening a matching client does not grant
permission to recreate a closed OASIS environment; existing liveness guards stay
in force.

The raw audit checks the config, scenario, manifest, recorded client settings,
execution sources and report's raw binding-file hash. Removing configuration
and provenance fields while leaving the client binding fails the audit. Paired
reports must match the URL and binding in addition to the existing model,
population and workload contracts. This local record supports provenance; it
does not authenticate a server or prove native/model execution by itself.

The focused offline tests use the real runner and native actor/client classes
with HTTP and bootstrap fixtures, plus actual filesystem task dispatch. They
test configuration, routing, persistence, metadata tampering and pairing without
contacting a service:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_evaluation_mirofish_service -v
```
