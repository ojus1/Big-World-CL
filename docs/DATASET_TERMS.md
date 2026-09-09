# BigWorld PoC dataset terms

The release retains the MatrAIx Persona 1M non-commercial research terms. These data terms are separate from the code license.

Source: https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M/blob/8b1073ab23d0c0ba0928386a041bac55e5365ddc/README.md

The following upstream terms are reproduced for attribution and compliance:


MatrAIx Persona 1M is released for **non-commercial research use only**. Use of
the dataset, any subset of it, or derivatives of it in a commercial product or
paid hosted service is not permitted. The MIT license on the
[MatrAIx-Persona-8B](https://github.com/MatrAIx-ai/MatrAIx-Persona-8B) GitHub
repository covers the software in that repository, not these dataset files.

Subsets inherit these terms: extracting a subset, including the 400,000
full-DAG synthetic records, does not relicense it. Synthetic records carry
categorical attributes from the shared schema plus model-generated
descriptions; text generated with a language model remains subject to the
respective model provider's terms. Several upstream sources carry their own
restrictions, so commercial rights are not ours to grant.

Source licenses and terms continue to apply to the underlying data:

| Source | Rows | Upstream license / terms |
|---|---:|---|
| Wiki extraction | 323,438 | Wikipedia text: CC BY-SA 4.0; attributes are model-extracted derivatives |
| Stack Overflow survey | 113,120 | Annual Developer Survey: ODbL 1.0, contents DbCL 1.0, attribution required |
| Amazon review extraction | 97,915 | [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) (McAuley Lab): research use; Amazon conditions of use apply |
| GSS | 63,532 | NORC General Social Survey terms of use |
| PRISM Alignment | 1,487 | Human-written text: CC BY 4.0; model responses: CC BY-NC 4.0; model provider terms apply |
| Real Human Survey | 355 | Collected with informed consent; responses released under CC BY 4.0; no names, contact details, or account identifiers collected |
| Full-DAG synthetic | 400,000 | Generated in this project; same research-only terms; model provider terms apply to generated text |

Responsible-use expectations, described in the paper
([arXiv:2608.04205](https://arxiv.org/abs/2608.04205), Appendix N), apply to
all use: no impersonation of real individuals, no attribution of the data to
identifiable people, no re-identification attempts, and no targeting of
individuals or protected groups. Attribution: cite the MatrAIx paper and link
this dataset card.

### Versioning and takedown

The dataset is versioned on the Hub and ships with a manifest and per-file
hashes, so every change is visible as a new revision. If records are removed,
for example when a survey participant withdraws consent, the removal will be
documented here; downstream users are expected to move to the latest revision
and delete copies of removed records. Questions and takedown requests: open a
discussion on this dataset or an issue on the GitHub repository.
