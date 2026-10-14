#!/usr/bin/env python3
"""Regenerate the run summary README.md of existing export products, without re-exporting.

Uses the run's step reports and result tables and the provenance recorded by
its export step (products/step_metadata.json). Useful when a run's perturb
output has been deleted (export needs it) or the summary format changes.

Usage:
    python scripts/write_run_summaries.py --config config/config.yaml --runs baseline fft2_diss8_mle ...
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import run_summary  # noqa: E402
from export import CAVEATS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--runs", nargs="+", required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    for run in args.runs:
        cfg = config if run == config["run"]["name"] else common.apply_sensitivity(config, config_hash, run)[0]
        rd = common.run_dir_of(cfg)
        out = rd / "products"
        meta = json.loads((out / "step_metadata.json").read_text())
        line = (f"spice_microstructure git {meta.get('git_commit')}; config sha256 {str(meta.get('config_sha256'))[:12]}; "
                f"microstructure-tpw {meta.get('packages', {}).get('microstructure-tpw')} "
                f"({meta.get('microstructure_tpw_commit')}); exported {meta.get('created_utc')}")
        p = run_summary.write_readme(cfg, meta, rd, out, CAVEATS, line,
                                     regenerated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"  {run}: {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
