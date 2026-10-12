#!/usr/bin/env python3
"""Snapshot the Python environment to a JSON file.

Records the Python version, platform, git commit (if available), and the
installed version of every package, with key packages listed separately.

Usage:
    python scripts/record_environment.py OUTPUT.json
"""

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

KEY_PACKAGES = ["microstructure-tpw", "gsw", "numpy", "scipy", "xarray", "netCDF4", "pyyaml"]


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        commit = out.stdout.strip()
        return commit + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def installed_packages() -> dict:
    packages = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            packages[name] = dist.version
    return dict(sorted(packages.items(), key=lambda item: item[0].lower()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    packages = installed_packages()
    lower = {name.lower(): version for name, version in packages.items()}
    snapshot = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version,
        "platform": platform.platform(),
        "git_commit": git_commit(),
        "key_packages": {name: lower.get(name.lower()) for name in KEY_PACKAGES},
        "all_packages": packages,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n")
    missing = [name for name, version in snapshot["key_packages"].items() if version is None]
    print(f"Wrote environment snapshot to {args.output}")
    if missing:
        print("Not installed: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
