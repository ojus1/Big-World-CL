#!/usr/bin/env python3
"""Fetch the reviewed SkillOpt-Sleep source without modifying a Python environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REVISION = "79124b37e9a6371e13b753f8bcd7adb1e493ade1"
URL = "https://github.com/microsoft/SkillOpt.git"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / ".cache" / "SkillOpt"


def verify(destination: Path) -> None:
    revision = subprocess.check_output(
        ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise RuntimeError(f"SkillOpt revision must be {REVISION}, found {revision}")
    status = subprocess.check_output(
        ["git", "-C", str(destination), "status", "--porcelain", "--untracked-files=normal"],
        text=True,
    )
    if status.strip():
        raise RuntimeError("SkillOpt checkout contains local changes; use a clean pinned checkout")
    if not (destination / "skillopt_sleep" / "consolidate.py").is_file():
        raise RuntimeError("SkillOpt-Sleep consolidation module is missing")


def install(destination: Path = DEFAULT_DESTINATION) -> Path:
    destination = destination.resolve()
    if destination.exists():
        verify(destination)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".skillopt-install-", dir=destination.parent))
    checkout = temporary / "source"
    try:
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", URL, str(checkout)],
            check=True, timeout=180,
        )
        subprocess.run(
            ["git", "-C", str(checkout), "checkout", "--detach", REVISION],
            check=True, timeout=180,
        )
        verify(checkout)
        checkout.rename(destination)
    finally:
        shutil.rmtree(temporary)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    destination = install(args.destination)
    print(json.dumps({"path": str(destination), "revision": REVISION, "pip_install_required": False}))


if __name__ == "__main__":
    main()
