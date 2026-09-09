"""Import actual Persona 8B public-cohort records with pinned provenance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import random
import urllib.request

REPO = "MatrAIx2026/MatrAIx_Persona_1M"
REVISION = "8b1073ab23d0c0ba0928386a041bac55e5365ddc"
SHARD = "data/persona-1m-0006.parquet"
SHARD_SHA = "602cfb8baf198ca9cef778f5508340695e963dfcdb5e97fd2f0fc277cff39b83"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch(cache, relative):
    target = Path(cache) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{relative}"
        request = urllib.request.Request(url, headers={"User-Agent": "EnterpriseLifespans-research/0.2"})
        with urllib.request.urlopen(request, timeout=60) as response, target.with_suffix(".part").open("wb") as f:
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
        target.with_suffix(".part").replace(target)
    return target


def decode(attributes, null_bitmap, columns, overrides=None):
    result = {}
    for i, column in enumerate(columns):
        if null_bitmap is not None and null_bitmap[i // 8] & (1 << (i % 8)):
            continue
        code = (attributes[i // 2] >> (4 * (i % 2))) & 15
        if code < len(column["values"]):
            result[column["id"]] = column["values"][code]
    if isinstance(overrides, str):
        overrides = json.loads(overrides)
    if overrides:
        result.update(dict(overrides))
    return result


def import_cohort(cache, out, count=6, seed=7):
    import pyarrow.parquet as pq
    cache, out = Path(cache), Path(out)
    paths = {name: fetch(cache, name) for name in ["manifest.json", "persona_codes.schema.json", "README.md", SHARD]}
    if sha256(paths[SHARD]) != SHARD_SHA:
        raise ValueError("Persona shard SHA-256 mismatch; refusing unverified data")
    schema = json.loads(paths["persona_codes.schema.json"].read_text())
    columns = schema["columns"]
    table = pq.read_table(paths[SHARD])
    rng = random.Random(seed)
    indices = list(range(table.num_rows))
    rng.shuffle(indices)
    selected = []
    for index in indices:
        row = table.slice(index, 1).to_pylist()[0]
        if row["source"] != "synthetic":
            continue
        attrs = decode(row["attributes"], row.get("null_bitmap"), columns, row.get("attribute_overrides"))
        # The organization assigns jobs; sampled persona traits do not imply
        # that a real individual holds this job. Keep demographics out of policy.
        keys = ("tech_savviness", "risk_tolerance", "decision_style", "trust_level", "learning_style",
                "big5_trust", "lstyle_work_schedule", "lstyle_planning_horizon", "cog_detail_orientation",
                "cog_feedback_receptiveness", "cog_ambiguity_tolerance", "cog_learning_pace",
                "cog_decision_speed", "cog_big_picture_vs_detail", "trait_love_of_learning", "trait_teamwork")
        work = {k: attrs[k] for k in keys if k in attrs}
        selected.append({"persona_id": f"persona8b:synthetic:{row['source_row_index']}",
                         "source": "synthetic", "source_row_index": row.get("source_row_index"),
                         "shard_row_index": index, "dataset": REPO, "revision": REVISION,
                         "shard": SHARD, "attributes": attrs,
                         "work_attributes": dict(list(work.items())[:36])})
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError("Insufficient synthetic personas")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {"dataset": REPO, "revision": REVISION, "shard": SHARD,
              "shard_sha256": SHARD_SHA, "selection_seed": seed,
              "selection": "Seeded sample of synthetic rows in one full-release shard; organization roles are assigned separately",
              "license": "MatrAIx non-commercial research only, including subsets and derivatives",
              "source_file_sha256": {name: sha256(path) for name, path in paths.items()},
              "personas": selected}
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cache", default="lifespan/data/persona8b")
    p.add_argument("--out", default="lifespan/data/cohort.json")
    args = p.parse_args()
    result = import_cohort(args.cache, args.out)
    print(json.dumps({"count": len(result["personas"]), "revision": result["revision"],
                      "fields": list(result["personas"][0]["work_attributes"]), "out": args.out}, indent=2))
