# Scale-v3 launch failure

The registered six-world campaign failed during initialization. Both seed-211 worlds exited with status 1 after the isolated MiroFish service returned HTTP 500 for its actor-contract support route. The remaining four worlds were never launched. There is no completed pair, primary endpoint or learning-performance result.

| Planned slot | Recorded outcome |
| --- | --- |
| seed-211-no_learning | Failed before actor initialization; cleanup confirmed |
| seed-211-skillopt | Failed before actor initialization; cleanup confirmed |
| seed-307-skillopt | Unlaunched after first-pair failure |
| seed-307-no_learning | Unlaunched after first-pair failure |
| seed-401-no_learning | Unlaunched after first-pair failure |
| seed-401-skillopt | Unlaunched after first-pair failure |

Two service tracebacks identify the same missing import: app.utils.actor_output_contract. The isolated installation lacked its tracked actor_output_contract.py overlay. A static check also found the tracked actor_contract_transport.json file missing, but the observed traceback did not reach that file. The other two tracked utility overlays, camel_responses.py and local_graph.py, matched their sources. openai_chat_compat.py was present at inspection. The service health/readiness probe had passed; its actor-contract support endpoint exposed this installation omission.

Independent receipt checks verify the service and both world processes' direct parent bindings to the registered supervisor. Both worlds exited naturally with status 1 and confirmed cleanup, taking about 1.066 and 0.948 seconds through cleanup. Service cleanup recorded one TERM signal and exit status 0. The outer scope preserved the caller context and enforced the registered 12 GiB memory, zero swap, 512-task and four-CPU limits. It drained to the held controller, released normally, and recorded actual wait status 1, empty cgroup membership, an absent controller and no forced scope stop or cleanup errors. A read-only check found the original service/world/controller processes and scope cgroup path absent.

These cleanup facts do not make the campaign successful. The strict scope audit rejects the incomplete inner result; the saved full audit is invalid and exposes no primary endpoint. The first-pair checkpoints contain no employee sessions or learning updates, and no actor simulation state was created. The audit's zero known receipt totals are not an all-in zero-cost claim: the failed receipts mark accounting incomplete, all-world reconciliation is false, and environment compute and currency cost remain unknown.

The [allowlisted failure observation](scale-v3-launch-failure.json) binds campaign SHA-256 ca6a3d2b890ebdf1a5142dbccd2d019b60179b5d8e61946725b33b743eb0b229, all 61 terminal campaign files, all 69 registered source files, and the four tracked utility overlays. The private snapshot preserves the two installed-file absences separately from the runtime exception. No raw artifact, registered source, native process or service was changed by this review.

The separately registered [nine-slot Hermes startup qualification](HERMES_STARTUP_SCOPE_V3_OUTCOME.md) remains passed. It did not exercise this fresh MiroFish capability route. This failed six-slot registration is preserved without retries or replacement slots; a corrected installation and future full study need their own evidence and a new complete registration.
