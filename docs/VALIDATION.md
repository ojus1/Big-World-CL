# Initial publication validation

Checked on 2026-09-09 against the installed pinned MiroFish/Hermes stack:

| Check | Result |
|---|---|
| `python3 -m unittest discover -s lifespan/tests -q` | 52 passed |
| Patched MiroFish backend tests | 131 passed |
| MiroFish root tests | 28 passed |
| Local graph / Responses / report / profile adapter tests | 18 passed |
| MiroFish frontend production build | Passed; existing chunk-size and import warnings |
| Actual native Hermes sandbox check | File writes worked; host-private read blocked; terminal cwd persisted |
| Patch application to a clean archive of pinned MiroFish | Passed |
| Accepted run's offline audit | 14 sessions, 132 native model calls, 163 causal events; all rewards reconciled |
| Public export manifest | All published file sizes and hashes verified |
| Export session filesystem manifests | Normalized object hashes and byte sizes verified |
| Dataset card / walkthrough | Card parsed; relative artifact links resolved |
| Credential checks | Gitleaks 8.30.1 and configured-secret/common-format scans passed for prepared code and dataset |

The prepared data export has 279 files, including a manifest, with 85 content-addressed file versions. Four file versions require host-path normalization and receive new hashes. Native profiles, runtime logs and credential stores are excluded rather than copied wholesale. Ciphertext provider metadata is omitted before pattern scanning; exact configured credential values are also checked against raw allowlisted input.

No extra live model run or training job was launched for publication. These checks establish integration and export integrity within the documented PoC scope; they do not validate realism, generalization or a lifelong-learning improvement.
