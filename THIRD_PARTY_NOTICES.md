# Third-party notices

This repository builds on MiroFish, https://github.com/666ghj/MiroFish, revision `39d849138ef254f6c737ab4c4705e5545dbe31d4`. The upstream project is copyright its respective authors and licensed under GNU AGPL version 3. `patches/mirofish-local.patch` contains modifications to that source, including local graph, model compatibility, simulation and dependency changes. `local-overrides/backend/` supplies added adapter modules. The full AGPL text is in `LICENSE`; upstream attribution and file notices are retained in the pinned source.

Hermes Agent, https://github.com/NousResearch/hermes-agent, is a separately installed dependency licensed under MIT by Nous Research and contributors. Its source is not vendored here. This repository adapts its native environment interface without modifying the installed Hermes source.

Bubblewrap, https://github.com/containers/bubblewrap, is a separately installed operating-system dependency. Its own upstream license applies. Other MiroFish/OASIS/CAMEL/Python dependencies retain their respective licenses in the pinned dependency manifests.

MatrAIx Persona data is a separate research-only dataset. The source card explicitly distinguishes its data terms from the MIT software license. This code repository does not vendor the persona shard. The Hugging Face PoC contains synthetic source records and derived trajectories under the source research-only restrictions; see `docs/DATASET_TERMS.md`. The software license does not grant commercial rights to those records or their derivatives.

SkillOpt, https://github.com/microsoft/SkillOpt, revision `79124b37e9a6371e13b753f8bcd7adb1e493ade1`, is a separately installed MIT-licensed dependency by Microsoft and contributors. Its source is fetched into an ignored cache rather than vendored. The native Hermes bridge invokes the upstream SkillOpt-Sleep consolidation, reflection and validation gate. See `docs/SKILLOPT_BASELINE.md` for the adapter and its explicitly documented prompt-context augmentation.
