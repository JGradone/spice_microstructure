#!/usr/bin/env python3
"""Single entry point for the processing chain.

Usage:
    python src/run_pipeline.py --config config/config.yaml
    python src/run_pipeline.py --config config/config.yaml --steps convert segments
    python src/run_pipeline.py --config config/config.yaml --dry-run

Each step reads the previous step's saved output and writes its own under
<output_root>/<run.name>/<step>/, so any step can be rerun on its own. Every
run writes run_metadata.json with the config hash, git commit, and package
versions. Steps are stubs until implemented; see CLAUDE.md for the methods.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ordered list of steps, matching the workflow in CLAUDE.md.
STEPS = [
    "patch",          # regenerate patched .P files from raw
    "convert",        # 1. convert to physical units
    "segments",       # 2. select clean segments
    "hydrography",    # 3. background hydrography
    "epsilon_shear",  # 4. epsilon from shear
    "thermistor",     # 5. chi and epsilon from FP07
    "regimes",        # 6. classify regimes
    "dd_test",        # 7. ratio of averages test
    "diffusivities",  # 8. bin averaged diffusivities
    "uncertainty",    # 10. bootstrap over profiles
    "compare_archive",  # milestone check against shipboard outputs
]


def load_config(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    config = yaml.safe_load(raw)
    return config, hashlib.sha256(raw).hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def find_todos(node, prefix="") -> list[str]:
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found += find_todos(value, f"{prefix}{key}.")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += find_todos(value, f"{prefix}{i}.")
    elif node == "TODO":
        found.append(prefix.rstrip("."))
    return found


def verify_manifests(config: dict) -> None:
    manifests = config.get("manifests", {})
    if not manifests.get("verify_before_run", False):
        return
    pairs = [
        (config["paths"]["archive_raw"], manifests.get("raw")),
        (config["paths"]["archive_patched"], manifests.get("patched")),
        (config["paths"]["archive_processed"], manifests.get("processed")),
    ]
    script = REPO_ROOT / "scripts" / "make_manifest.py"
    for data_dir, manifest in pairs:
        if not manifest:
            continue
        manifest_path = REPO_ROOT / manifest
        if not manifest_path.exists():
            sys.exit(f"Manifest not found: {manifest_path}. Write it first (see README).")
        result = subprocess.run(
            [sys.executable, str(script), "verify", data_dir, str(manifest_path)]
        )
        if result.returncode != 0:
            sys.exit(f"Manifest verification failed for {data_dir}. Stopping.")


def run_step(name: str, config: dict, run_dir: Path) -> None:
    """Dispatch to a step implementation. Replace the stub as steps are written."""
    raise NotImplementedError(
        f"Step '{name}' is not implemented yet. Implement it as its own module "
        f"in src/, reading from and writing to {run_dir}."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the processing chain.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Check config and print the plan without running steps.")
    args = parser.parse_args()

    config, config_hash = load_config(args.config)
    todos = find_todos(config)
    run_name = config["run"]["name"]
    run_dir = Path(config["paths"]["output_root"]) / run_name

    print(f"Run: {run_name}")
    print(f"Config: {args.config} (sha256 {config_hash[:12]})")
    print(f"Output: {run_dir}")
    print("Steps: " + ", ".join(args.steps))
    if todos:
        print("Unfilled TODO values: " + ", ".join(todos))

    if args.dry_run:
        return 0
    if todos:
        sys.exit("Fill all TODO values in the config before running.")

    verify_manifests(config)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_metadata = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_path": str(args.config),
        "config_sha256": config_hash,
        "git_commit": git_commit(),
        "python": sys.version,
        "packages": {name: package_version(name) for name in
                     ["microstructure-tpw", "gsw", "numpy", "scipy", "xarray"]},
        "steps": args.steps,
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(run_metadata, indent=2) + "\n")

    for name in STEPS:
        if name in args.steps:
            print(f"--- {name}")
            run_step(name, config, run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
