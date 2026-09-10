"""Plot a hash-bound, completed report_scale_v3 public SUMMARY.json.

This independent postprocessor checks the public report's completion markers and
fixed-demand arithmetic. It does not re-audit private native evidence. Matplotlib
is optional and imported only after validation. No campaign files are accessed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import re
import sys

VERSION = "scale-v3-figures-1.0"
SEEDS = (211, 307, 401)
ARMS = ("no_learning", "skillopt")
DENOMINATOR = 240
METRIC = "fixed_demand_fulfillment_rate"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "invalid_sha256")
    return value


def count(value, expected=None):
    require(type(value) is int and value >= 0, "invalid_count")
    require(expected is None or value == expected, "unexpected_count")
    return value


def number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    require(valid, "invalid_number")
    return value


def close(actual, expected):
    require(math.isclose(number(actual), expected, rel_tol=0, abs_tol=1e-12),
            "fixed_demand_arithmetic_mismatch")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def validate_summary(summary, *, synthetic_fixture=False):
    """Return only plotting data; never propagate unrecognized report fields."""
    require(type(summary) is dict, "summary_object_required")
    require(summary.get("fixture_only", False) is synthetic_fixture,
            "synthetic_fixture_flag_mismatch")
    require(summary["schema_version"] == 1 and type(summary["schema_version"]) is int
            and summary["report_version"] == "scale-publication-v3.0"
            and summary["kind"] == "completed_scale_v3_development_publication_draft",
            "unsupported_report_shape")
    require(summary["complete"] is True, "completed_report_required")
    for key, value in (("planned_worlds", 6), ("completed_worlds", 6),
                       ("world_pairs", 3), ("work_days", 20), ("settlement_only_days", 2)):
        count(summary[key], value)
    provenance = summary["provenance"]
    require(provenance["hash_encoding"] == "sha256_raw_file_bytes", "raw_hash_provenance_required")
    campaign_hash = digest(provenance["campaign_raw_sha256"])
    require(digest(provenance["published_preregistration_raw_sha256"]) == campaign_hash,
            "preregistration_campaign_hash_mismatch")
    processor = provenance["postprocessor"]
    require(processor["path"] == "scripts/report_scale_v3.py"
            and processor["version"] == summary["report_version"], "wrong_reporter")
    digest(processor["sha256"])
    audit = provenance["strict_audit"]
    require(audit["status"] == "valid_completed" and audit["primary_endpoint_available"] is True
            and audit["owned_scope_passed"] is True, "completed_audit_marker_required")
    for key, value in (("completed_runs", 6), ("complete_pairs", 3), ("stable_completed_audits", 2)):
        count(audit[key], value)
    digest(audit["audit_result_sha256"])
    scope = summary["outer_scope"]
    require(all(scope[key] is True for key in ("ok", "scope_passed", "scope_complete",
            "inner_completed", "inner_supervisor_identity_bound")), "completed_scope_marker_required")
    count(scope["native_wait_exit_code"], 0)
    count(scope["inner_result_exit_code"], 0)
    lifecycle = summary["lifecycle"]
    require(lifecycle["service"]["cleanup_confirmed"] is True, "service_cleanup_required")
    require(type(lifecycle["service"]["root_exitcode"]) is int, "service_exit_required")
    require(count(lifecycle["peak_parallel_worlds"]) <= 2, "registered_parallelism_exceeded")
    lifecycle_worlds = lifecycle["worlds"]
    require(type(lifecycle_worlds) is list and len(lifecycle_worlds) == 6,
            "all_six_world_cleanup_records_required")
    planned_ids = {f"seed-{seed}-{arm}" for seed in SEEDS for arm in ARMS}
    require({row["run_id"] for row in lifecycle_worlds} == planned_ids,
            "world_cleanup_inventory_mismatch")
    for row in lifecycle_worlds:
        require(row["cleanup_confirmed"] is True, "world_cleanup_required")
        count(row["root_exitcode"], 0)
    barriers = lifecycle["pair_barriers"]
    count(barriers["planned_pair_batches"], 3)
    count(barriers["observed_following_pair_barriers"], 2)
    require(barriers["prior_pair_requires_normal_exit_and_confirmed_cleanup"] is True,
            "completed_pair_barriers_required")
    endpoint = summary["primary_endpoint"]
    require(endpoint["metric"] == METRIC and endpoint["direction"] == "skillopt minus no_learning"
            and endpoint["weighting"] == "equal world pair", "wrong_primary_endpoint")
    count(endpoint["denominator_per_world"], DENOMINATOR)
    worlds = summary["worlds"]
    require(type(worlds) is list and len(worlds) == 6, "all_six_worlds_required")
    by_key = {}
    for world in worlds:
        seed, arm = world["seed"], world["algorithm"]
        require(type(seed) is int and seed in SEEDS and arm in ARMS, "unplanned_world")
        require((seed, arm) not in by_key, "duplicate_world")
        require(world["status"] == "completed" and world["run_id"] == f"seed-{seed}-{arm}",
                "incomplete_or_mismatched_world")
        fixed = world["primary_fixed_demand"]
        count(fixed["accepted_before_work_horizon"], DENOMINATOR)
        fulfilled = count(fixed["fulfilled_before_work_horizon"])
        require(fulfilled <= DENOMINATOR, "fulfilled_count_exceeds_denominator")
        count(fixed["unfulfilled_at_work_horizon"], DENOMINATOR - fulfilled)
        count(fixed["missing_task_evidence"], 0)
        close(fixed["fulfillment_rate"], fulfilled / DENOMINATOR)
        by_key[seed, arm] = fulfilled
    require(set(by_key) == {(seed, arm) for seed in SEEDS for arm in ARMS}, "missing_world")
    comparison = summary["comparison"]
    require(comparison["direction"] == "skillopt minus no_learning"
            and comparison["inference_unit"] == "world pair"
            and comparison["confidence_interval"] is None, "descriptive_pair_comparison_required")
    pairs = comparison["pairs"]
    require(type(pairs) is list and len(pairs) == 3, "all_three_pairs_required")
    observed = set()
    deltas = {seed: (by_key[seed, "skillopt"] - by_key[seed, "no_learning"]) / DENOMINATOR
              for seed in SEEDS}
    for pair in pairs:
        seed = pair["seed"]
        require(type(seed) is int and seed in SEEDS and seed not in observed, "duplicate_or_unplanned_pair")
        observed.add(seed)
        close(pair["deltas"][METRIC], deltas[seed])
    mean = sum(deltas.values()) / len(SEEDS)
    close(comparison["equal_world_mean_deltas"][METRIC], mean)
    close(endpoint["value"], mean)
    return {"synthetic_fixture": synthetic_fixture, "campaign_raw_sha256": campaign_hash,
            "denominator_per_world": DENOMINATOR,
            "pairs": [{"seed": seed, "fulfilled": {arm: by_key[seed, arm] for arm in ARMS},
                       "delta_percentage_points": deltas[seed] * 100} for seed in SEEDS],
            "equal_world_mean_percent": {arm: sum(by_key[s, arm] for s in SEEDS) / 3 / DENOMINATOR * 100
                                         for arm in ARMS},
            "equal_world_mean_delta_percentage_points": mean * 100}


def load_summary(path, expected_sha256, *, synthetic_fixture=False):
    expected_sha256 = digest(expected_sha256)
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular_summary_file_required")
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == expected_sha256, "summary_raw_sha256_mismatch")
    summary = json.loads(raw, object_pairs_hook=_unique_object,
                         parse_constant=lambda _: require(False, "nonfinite_json"))
    return validate_summary(summary, synthetic_fixture=synthetic_fixture)


def render(data):
    """Return SVG/PNG bytes using a noninteractive backend; no GUI or network."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ValueError("matplotlib_missing_use_separate_plotting_environment") from exc
    style = {"font.family": "DejaVu Sans", "font.size": 11, "svg.fonttype": "none",
             "svg.hashsalt": VERSION, "axes.spines.top": False, "axes.spines.right": False}
    with plt.rc_context(style):
        fig, (left, right) = plt.subplots(1, 2, figsize=(12, 6), gridspec_kw={"width_ratios": [1.2, 1]})
        colors = {"no_learning": "#176B96", "skillopt": "#B34D00"}
        labels = {"no_learning": "No-learning Hermes", "skillopt": "SkillOpt"}
        y = [3, 2, 1, -.4]
        names = [f"Seed {p['seed']}" for p in data["pairs"]] + ["Equal-world mean"]
        for i, row in enumerate(data["pairs"]):
            rates = [row["fulfilled"][arm] / DENOMINATOR * 100 for arm in ARMS]
            left.plot(rates, [y[i] + .11, y[i] - .11], color="#b2b9bf", linewidth=2, zorder=1)
        for arm, offset, marker in (("no_learning", .11, "o"), ("skillopt", -.11, "s")):
            rates = [row["fulfilled"][arm] / DENOMINATOR * 100 for row in data["pairs"]]
            left.scatter(rates, [p + offset for p in y[:3]], label=labels[arm], color=colors[arm],
                         marker=marker, s=58, zorder=3)
            for i, row in enumerate(data["pairs"]):
                left.annotate(f"{row['fulfilled'][arm]}/240", (rates[i], y[i] + offset),
                              xytext=(0, 9 if offset > 0 else -16), textcoords="offset points",
                              ha="center", color=colors[arm], fontsize=9)
            rate = data["equal_world_mean_percent"][arm]
            left.scatter([rate], [y[-1] + offset], color=colors[arm], marker="D", s=54, zorder=3)
            left.annotate(f"{rate:.1f}%", (rate, y[-1] + offset),
                          xytext=(0, 9 if offset > 0 else -16), textcoords="offset points",
                          ha="center", color=colors[arm], fontsize=9)
        deltas = [p["delta_percentage_points"] for p in data["pairs"]]
        deltas.append(data["equal_world_mean_delta_percentage_points"])
        span = max(5, max(abs(x) for x in deltas) * 1.3 + 1)
        right.axvline(0, color="#747c83", linewidth=1)
        for i, delta in enumerate(deltas):
            right.plot([0, delta], [y[i], y[i]], color="#667585", linewidth=2)
            right.scatter([delta], [y[i]], color="#243949", marker="D" if i == 3 else "o", s=58, zorder=3)
            right.annotate(f"{delta:+.2f} pp", (delta, y[i]), xytext=(0, 11),
                           textcoords="offset points", ha="center", fontsize=10)
        left.set(xlim=(-5, 105), xlabel="Fulfilled before work horizon (%)", title="Fixed-demand fulfillment")
        right.set(xlim=(-span, span), xlabel="SkillOpt − no-learning (percentage points)", title="Within-seed paired difference")
        left.set_xticks([0, 25, 50, 75, 100])
        for axis in (left, right):
            axis.set(yticks=y, yticklabels=names, ylim=(-1.05, 3.65))
            axis.axhline(.3, color="#d0d5da", linestyle="--", linewidth=.8)
            axis.grid(axis="x", alpha=.18)
            axis.set_axisbelow(True)
            axis.tick_params(axis="y", length=0)
        left.legend(loc="upper center", bbox_to_anchor=(.5, -.16), ncol=2, frameon=False, fontsize=10)
        fixture = "SYNTHETIC FIXTURE — NOT STUDY RESULTS\n" if data["synthetic_fixture"] else ""
        fig.suptitle(fixture + "Descriptive development results · 3 world pairs / 6 worlds", fontsize=14, y=.98)
        fig.text(.5, .045, "Planned denominator: 240 commitments per world · 20 work days\n"
                 "All three pairs shown; equal-world weighting. No confidence interval or causal learning claim.",
                 ha="center", va="center", fontsize=10, color="#46515c")
        fig.subplots_adjust(left=.13, right=.97, bottom=.24, top=.8 if data["synthetic_fixture"] else .84, wspace=.53)
        outputs = {}
        for fmt in ("svg", "png"):
            stream = io.BytesIO()
            metadata = {"Creator": VERSION, "Date": None} if fmt == "svg" else {"Software": VERSION}
            fig.savefig(stream, format=fmt, dpi=180, metadata=metadata)
            outputs[f"fixed-demand-pairs.{fmt}"] = stream.getvalue()
        plt.close(fig)
    return outputs, matplotlib.__version__


def plot_summary(path, out, *, expected_sha256, synthetic_fixture=False):
    path, out = Path(path), Path(out)
    data = load_summary(path, expected_sha256, synthetic_fixture=synthetic_fixture)
    require(not out.exists() and not out.is_symlink(), "new_output_directory_required")
    source_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    outputs, matplotlib_version = render(data)
    require(not path.is_symlink() and sha256(path.read_bytes()).hexdigest() == expected_sha256,
            "summary_changed_during_plotting")
    require(sha256(Path(__file__).read_bytes()).hexdigest() == source_sha, "plotter_changed_during_plotting")
    manifest = {"schema_version": 1, "kind": "scale_v3_descriptive_figures", "version": VERSION,
                "summary_raw_sha256": expected_sha256, "plotter_raw_sha256": source_sha,
                "matplotlib_version": matplotlib_version, "hash_encoding": "sha256_raw_file_bytes",
                "validation_scope": "public_summary_shape_and_arithmetic_only_not_native_reaudit",
                "data": data, "outputs": {name: sha256(raw).hexdigest() for name, raw in outputs.items()}}
    outputs["FIGURES.json"] = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in outputs.items():
        with (out / name).open("xb") as handle:
            handle.write(raw)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--summary-sha256", required=True, help="Separately reviewed SHA-256 of exact SUMMARY.json bytes")
    parser.add_argument("--out", required=True, type=Path, help="New output directory; never overwrite existing figures")
    parser.add_argument("--synthetic-fixture", action="store_true", help="Require fixture_only=true and label every figure as synthetic")
    args = parser.parse_args(argv)
    try:
        result = plot_summary(args.summary, args.out, expected_sha256=args.summary_sha256,
                              synthetic_fixture=args.synthetic_fixture)
    except (ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        code = str(exc) if type(exc) is ValueError and re.fullmatch(r"[a-z0-9_]+", str(exc)) else type(exc).__name__
        print(json.dumps({"ok": False, "error": code}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "summary_raw_sha256": result["summary_raw_sha256"],
                      "synthetic_fixture": result["data"]["synthetic_fixture"],
                      "outputs": [*result["outputs"], "FIGURES.json"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
