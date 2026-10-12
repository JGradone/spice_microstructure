#!/usr/bin/env python3
"""Single entry point for the processing chain.

Usage:
    python src/run_pipeline.py --config config/config.yaml
    python src/run_pipeline.py --config config/config.yaml --steps convert segments
    python src/run_pipeline.py --config config/config.yaml --dry-run

Each step reads the previous step's saved output and writes its own under
<output_root>/<run.name>/<step>/, so any step can be rerun on its own. Every
run writes run_metadata.json with the config hash, git commit, and package
versions. Each step processes every instrument listed in run.instruments.
Implemented steps live in src/steps/; the rest are stubs (see CLAUDE.md).
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

import common

# Ordered list of steps, matching the workflow in CLAUDE.md. Implemented
# steps live in src/steps/<name>.py and expose run(ctx).
STEPS = [
    "cast_log",       # 0. cast table and ship track from the Sealog export
    "patch",          # 0. regenerate patched .p files from raw (per-cast edits)
    "convert",        # 1. perturb run: profiles, epsilon, chi, CTD, binning
    "segments",       # 2. select clean segments
    "hydrography",    # 3. background hydrography
    "epsilon_shear",  # 4. epsilon from shear (QC and noise floor on perturb output)
    "thermistor",     # 5. chi and epsilon from FP07 (refits on perturb output)
    "regimes",        # 6. classify regimes
    "dd_test",        # 7. ratio of averages test
    "diffusivities",  # 8. bin averaged diffusivities
    "uncertainty",    # 10. bootstrap over profiles
    "compare_archive",  # sanity check against shipboard outputs
    "figures",        # first-look figures (convert output until export exists)
    "export",         # documented products for use outside this repository
]


def run_step(name: str, ctx: dict) -> None:
    try:
        module = importlib.import_module(f"steps.{name}")
    except ModuleNotFoundError:
        raise NotImplementedError(
            f"Step '{name}' is not implemented yet. Implement it as src/steps/{name}.py "
            f"with run(ctx), reading from and writing to {ctx['run_dir']}.")
    module.run(ctx)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the processing chain.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Check config and print the plan without running steps.")
    args = parser.parse_args()

    config, config_hash = common.load_config(args.config)
    todos = common.find_todos(config)
    run_name = config["run"]["name"]
    run_dir = common.run_dir_of(config)

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

    common.verify_manifests(config)
    run_dir.mkdir(parents=True, exist_ok=True)
    common.write_json(run_dir / "run_metadata.json", {
        **common.provenance(config_hash), "config_path": str(args.config),
        "steps": args.steps, "manifests_verified": True})

    ctx = {"config": config, "config_hash": config_hash, "run_dir": run_dir}
    for name in STEPS:
        if name in args.steps:
            print(f"--- {name}")
            run_step(name, ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
