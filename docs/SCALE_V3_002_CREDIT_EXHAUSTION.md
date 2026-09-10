# Scale-v3-002 stopped after API credit exhaustion

The scaled comparison stopped on September 10, 2026 at 12:01:52 UTC, during day-7 employee work. The API returned HTTP 429 with the message “You have no credits remaining.” The no-learning world exited with status 1; the supervisor stopped its paired SkillOpt world and left the four later worlds unlaunched. No world completed, no learning epoch ran, and no primary endpoint or learning gain is available.

| Planned slot | Returned session records | Learning updates | Terminal outcome |
| --- | ---: | ---: | --- |
| seed-211-no_learning | 88 | 0 | Provider credit exhaustion; exit 1; cleanup confirmed |
| seed-211-skillopt | 87 | 0 | Stopped after peer failure; exit -15; cleanup confirmed |
| seed-307-skillopt | — | — | Unlaunched |
| seed-307-no_learning | — | — | Unlaunched |
| seed-401-no_learning | — | — | Unlaunched |
| seed-401-skillopt | — | — | Unlaunched |

The 175 returned records include the no-learning attempt that exposed the provider failure. Its infrastructure/accounting check failed. The other 174 records report valid infrastructure; these flags alone are not a scientific outcome audit. One additional SkillOpt work attempt was interrupted before writing its session record. Neither world reached the end-of-day-7 learning boundary. The earlier [day-3 eligibility and startup observations](SCALE_V3_002_PROGRESS.md) remain valid dated observations, not evidence that the study completed.

The failed attempt records four completed physical calls with 34,276 reported tokens, followed by three RateLimitError dispatches. Those errors retain conservative reservations of 66,651 tokens each because their usage is unknown. The provider message identifies account credit exhaustion; it does not establish which workload consumed the account balance. The registered per-attempt budget was not exhausted, and this observation does not show a recurrence of the earlier Hermes startup failures.

Across the two launched worlds, employee receipts record 1,777 physical dispatches and 18,908,796 reported tokens. Including unresolved reservations gives 1,793 calls and 19,358,749 charged-or-reserved tokens. There are two unresolved work records: the partial no-learning receipt and the interrupted SkillOpt work attempt without a session receipt, which reserves 16 calls and 250,000 tokens. Separately, contracted actor interviews reconcile 254 requests and 813,568 tokens. Bootstrap/social usage and currency cost remain unknown. Reservations are accounting bounds, not measured usage or an API invoice.

Independent lifecycle validation confirms both world cleanups and service cleanup. The outer scope drained and released normally, recorded actual wait status 1, and ended with no remaining members, an absent controller, no forced scope stop and no terminal cleanup errors. The strict outer audit rejects the unsuccessful inner result; that rejection is not a cleanup-failure finding. The full campaign audit is invalid and provides no comparison.

The [allowlisted terminal observation](scale-v3-002-credit-exhaustion.json) binds the registered campaign SHA-256 `72b19a41eb00f90761302df0d55e5051ec166d7240215b2302a68ae294b1c6ce` to a private, stable copy of all 8,740 terminal campaign files and all 69 registered source files. Raw prompts, personas, skills, provider identifiers and credentials are not published. No native requests, source changes or process mutations were made by this observation.

Further native evaluation requires replenished API credits or an authorized funded endpoint. This registration is terminal and is preserved without resumption, retries or replacement worlds. Any future complete comparison needs a fresh registration with all six slots; the failed prefix cannot stand in for the planned endpoint.
