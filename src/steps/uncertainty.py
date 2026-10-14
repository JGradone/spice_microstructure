#!/usr/bin/env python3
"""Step uncertainty: check and summarise the bootstrap intervals (CLAUDE.md step 10).

The bootstrap over profiles is computed where each estimate is made (dd_test:
ratios and excess; diffusivities: K_T, R_rho, K_rho, K_S), with
uncertainty.bootstrap_samples and uncertainty.random_seed. This step checks
that every reported pooled estimate has an interval, counts bins below
double_diffusion.min_profiles_per_average, and summarises interval widths.

Reads:  <run_dir>/dd_test/{dd_pooled,dd_excess}.csv, <run_dir>/diffusivities/diffusivity_bins.csv
Writes: <run_dir>/uncertainty/uncertainty_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

STEP = "uncertainty"


def run(ctx: dict) -> None:
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    out.mkdir(parents=True, exist_ok=True)
    rd = ctx["run_dir"]
    minp = config["double_diffusion"]["min_profiles_per_average"]
    report = {"bootstrap_samples": config["uncertainty"]["bootstrap_samples"],
              "random_seed": config["uncertainty"]["random_seed"], "resampling_unit": "profile", "tables": {}}
    for label, path, est, lo, hi in (("dd_pooled", rd / "dd_test" / "dd_pooled.csv", "ratio", "ratio_lo", "ratio_hi"),
                                     ("dd_excess", rd / "dd_test" / "dd_excess.csv", "excess", "excess_lo", "excess_hi"),
                                     ("diffusivity_bins", rd / "diffusivities" / "diffusivity_bins.csv", "K_T",
                                      "K_T_ci_low", "K_T_ci_high")):
        t = pd.read_csv(path)
        pooled = t[t["depth_bin"].astype(str) == "pooled"] if "depth_bin" in t else t
        has = np.isfinite(pooled[lo]) & np.isfinite(pooled[hi])
        width = np.log10(pooled.loc[has, hi] / pooled.loc[has, lo])
        report["tables"][label] = {
            "records": int(len(t)), "pooled_records": int(len(pooled)),
            "pooled_with_interval": int(has.sum()),
            "pooled_without_interval_reason": "fewer than 2 profiles" if (~has).any() else None,
            "records_below_min_profiles": int((t["n_profiles"] < minp).sum()),
            "pooled_interval_width_log10_median": float(width.median()) if len(width) else None,
            "estimate_outside_interval": int(((pooled[est] < pooled[lo]) | (pooled[est] > pooled[hi]))[has].sum())}
        r = report["tables"][label]
        print(f"  {label}: {r['pooled_with_interval']}/{r['pooled_records']} pooled estimates with intervals, "
              f"{r['records_below_min_profiles']} records below {minp} profiles, "
              f"median width {r['pooled_interval_width_log10_median']:.2f} decades")
    common.write_json(out / "uncertainty_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
