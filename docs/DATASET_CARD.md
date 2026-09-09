---
pretty_name: BigWorld PoC — Persistent Enterprise Lifespans
license: other
license_name: matraix-research-only
license_link: LICENSE
language:
- en
task_categories:
- text-generation
tags:
- synthetic
- agents
- continual-learning
- reinforcement-learning
- mirofish
- hermes
- persona8b
- simulation
size_categories:
- n<1K
configs:
- config_name: sessions
  default: true
  data_files:
  - split: train
    path: data/sessions.jsonl
- config_name: events
  data_files:
  - split: train
    path: data/events.jsonl
---

# BigWorld PoC

One persistent, 16-day synthetic workplace ecosystem with **two competing enterprises, one government agency, three consumers, six employees and six dedicated native Hermes/bubblewrap computers**. Twelve distinct pinned synthetic Persona 8B records condition actual MiroFish/OASIS actors. Companies change goals and offers in response to competition, outcomes, policy and fictional geopolitical changes. Employee files, conversations and commitments persist between sessions.

[Code and research design](https://github.com/ojus1/Big-World-CL) · [Release code revision](https://github.com/ojus1/Big-World-CL/tree/{{CODE_REVISION}}) · [Causal walkthrough](runs/ecosystem-bwrap/WALKTHROUGH.md)

## Recorded run

| Measure | Count |
|---|---:|
| Simulated days | 16 |
| Institutional / consumer decisions | 30 |
| Reconciled Hermes sessions | 14 |
| Native Hermes model calls | 132 |
| Shared causal events | 163 |
| Completed / pending work items | 10 / 0 |
| Persistent unchanged file links between sessions | 18 |
| Synthetic business utility | 108.23 |

Four of the reconciled sessions left work pending before retry. One additional infrastructure-interrupted attempt is retained in evaluator evidence and excluded from the reconciled session and utility totals; its partial compute/work costs are not included. Native model: `gpt-5.6-luna`, low reasoning. Utility is not API spend.

The day-4 corridor disruption and day-11 reopening are exogenous fictional shocks. Institutional and consumer responses are model decisions. Temporary jurisdiction review becomes effective on day 5 and expires on day 9. Employees must adapt actual deliverables and procedures; successful work produces delayed business consequences.

**No RL training, online weight updates, controlled baseline advantage, representative economic behavior or benchmark novelty is claimed.** This is integration evidence. The run includes early adapter revisions; the release commit describes the current implementation/exporter, not an immutable revision used for every recorded step. Read the historical `evaluator/manifest.json` and private rule snapshots when interpreting the trajectory.

## Loading and boundaries

```python
from datasets import load_dataset
import json

rows = load_dataset("ojus1/BigWorld-PoC", "sessions", split="train")
session = json.loads(rows[0]["session_json"])
print(session["employee"], session["day"], len(session["native_hermes"]["messages"]))
```

The sessions configuration contains 14 rows with `id`, `run_id`, `day`, `employee`, `task_id` and `session_json`. The events configuration contains 163 rows with `run_id`, `id`, `day`, `actor`, `kind` and `event_json`. JSON strings retain heterogeneous nested schemas without flattening away tool detail.

`train` is a packaging label for a single experience, not an evaluation split. Native conversations accumulate and may repeat earlier messages. Preserve temporal order and employee identity. Do not treat these rows as independent episodes or claim generalization from random session splits.

- `runs/ecosystem-bwrap/learner/`: employee tool observations, native conversations, file manifests, RPC traces and time-indexed rewards.
- `runs/ecosystem-bwrap/evaluator/`: global events, complete world/checkpoint state, actor observations and decisions, private success diagnostics, imported personas, native evidence and interruption history. **Privileged audit material, not learner observations.** The `events` viewer configuration is also privileged.
- `runs/ecosystem-bwrap/filesystem_objects/`: content-addressed employee file versions. Access must be limited to hashes authorized for the employee at that time.
- `runs/ecosystem-bwrap/computers/`: final workspace/home and memory/skill files when present. These are terminal snapshots, not initial learner state.

Do not expose future events, end-state memory, private diagnostics or other employees' files to a learner. Delayed reward tables are labels available at their recorded times. Training against this environment would require a separate SFT/RL loop, causal re-simulation of reacting institutions, held-out change mechanisms, and an explicit information/budget contract.

## Export transformations

Native configuration, credentials, raw profile databases, runtime logs, sockets and caches are excluded. Native OASIS trace rows are exported as JSONL rather than a raw SQLite file. Host paths are replaced with `/simulation/run`, `/simulation/code` and `/runtime/host-home`. Transport-only provider fields, encrypted payloads and reasoning-only fields are omitted; ordinary user/assistant/tool messages and calls remain.

Sanitized file objects are rehashed, and referenced hashes and byte sizes are updated. `release_manifest.json` records transformations, changed hashes, source-scope limitations and checksums for every other file. Original `VALIDATION.json` is historical raw-run evidence; export checks independently validate counts, causal references and normalized session file hashes. Credential checks include known configured secret values and common formats; publication additionally uses Gitleaks.

The export is suitable for inspection and prospective training research. It is not a drop-in native Hermes/MiroFish restart image because private runtime stores and transport state are excluded. Reconstruct authorized files from session manifests for an offline analysis; use the code to generate a new live world.

## Provenance and terms

- [MiroFish](https://github.com/666ghj/MiroFish): `39d849138ef254f6c737ab4c4705e5545dbe31d4`, with the published local patches.
- [Hermes Agent](https://github.com/NousResearch/hermes-agent): `2c8a2b65aa148ceb178d2251c54a523af12092c9`.
- [MatrAIx Persona 1M](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M): `8b1073ab23d0c0ba0928386a041bac55e5365ddc`; shard `data/persona-1m-0006.parquet`; SHA-256 `602cfb8baf198ca9cef778f5508340695e963dfcdb5e97fd2f0fc277cff39b83`; selection seed 7. All 12 selected records have `source=synthetic`; roles are assigned separately. The public release contains 999,847 records, not eight billion downloaded profiles. [Persona 8B paper](https://arxiv.org/abs/2608.04205).
- Bubblewrap 0.9.0; Linux namespace isolation with a shared host kernel.

**Non-commercial research only.** Persona source terms apply to subsets and derivatives, including synthetic records; the source software's MIT license does not relicense the data. Model-provider terms also apply to generated text. See [LICENSE](LICENSE), cite the MatrAIx paper and link its dataset card when reusing this release. Do not impersonate or re-identify real people or target individuals/protected groups. These are fictional roles and organizations; the personas are not a representative sample of a population.

For corrections or takedown requests, open a discussion on this dataset or an issue on the code repository. Follow upstream record-removal notices and update affected copies if necessary.
