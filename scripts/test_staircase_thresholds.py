#!/usr/bin/env python3
"""Sensitivity of staircase detection to the mixed-layer thresholds.

Runs thermohalinesteps.classify_staircase (rollo2022 settings, temperature-only
mixed-layer test) on every profile's hydrography grid for each combination of
ml_grad and ml_density_difference in regimes.staircase.test_grid, and reports:
  * profiles with at least one interface, interfaces and mixed-layer metres
    below 150 dbar, per instrument;
  * the example profiles (regimes.examples) with detected layers and
    interfaces drawn for each setting, to judge against the FP07 temperature.

Reads:  <run_dir>/hydrography/hydrography_<instrument>.nc
Writes: <run_dir>/regimes/threshold_test/threshold_test.csv, threshold_examples.png

Usage:
    python scripts/test_staircase_thresholds.py --config config/config.yaml --sensitivity fft2_diss8_mle
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import gsw
import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from regimes import LABEL_COLOR, profile_staircase  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--sensitivity", metavar="NAME")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    if args.sensitivity:
        config, config_hash = common.apply_sensitivity(config, config_hash, args.sensitivity)
    run_dir = common.run_dir_of(config)
    out = run_dir / "regimes" / "threshold_test"
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    st = config["regimes"]["staircase"]
    base = st["rollo2022"]
    grid = st["test_grid"]
    settings = [(g, d) for g in grid["ml_grad"] for d in grid["ml_density_difference"]]
    rows, cache = [], {}
    for name, _ in common.instruments(config):
        hyd = xr.open_dataset(run_dir / "hydrography" / f"hydrography_{name}.nc")
        zc = hyd["depth"].values
        for i, pf in enumerate(hyd["profile_file"].values):
            lat = float(hyd["lat"].values[i]) if np.isfinite(hyd["lat"].values[i]) else 12.0
            for g, d in settings:
                cfg = {**base, "ml_grad": g, "ml_density_difference": d}
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    pg, masks, steps = profile_staircase(zc, hyd["CT"].values[i], hyd["SA_used"].values[i], lat, cfg)
                deep = pg > 150 if len(pg) else np.array([], bool)
                n_if = int(((steps["kind"] == "interface") & (steps["p"] > 150)).sum()) if len(steps) else 0
                rows.append({"instrument": name, "profile_file": pf, "ml_grad": g, "ml_density_difference": d,
                             "interfaces_below_150": n_if,
                             "layer_m_below_150": float(masks["layer"][deep].sum()) if len(pg) else 0.0,
                             "interface_m_below_150": float(masks["interface"][deep].sum()) if len(pg) else 0.0,
                             "profile_m_below_150": float(deep.sum()) if len(pg) else 0.0})
                cache[(name, pf, g, d)] = (pg, steps, lat)
    df = pd.DataFrame(rows)
    df.to_csv(out / "threshold_test.csv", index=False)
    summ = df.groupby(["instrument", "ml_grad", "ml_density_difference"]).agg(
        profiles=("profile_file", "nunique"),
        with_interfaces=("interfaces_below_150", lambda x: int((x > 0).sum())),
        interfaces=("interfaces_below_150", "sum"),
        staircase_fraction=("layer_m_below_150", "sum"))
    tot = df.groupby(["instrument", "ml_grad", "ml_density_difference"])
    summ["staircase_fraction"] = ((tot["layer_m_below_150"].sum() + tot["interface_m_below_150"].sum())
                                  / tot["profile_m_below_150"].sum()).round(3)
    print(summ.to_string())

    ex = config["regimes"]["examples"]
    fig, axes = plt.subplots(len(ex), len(settings), figsize=(2.6 * len(settings), 4.2 * len(ex)), squeeze=False)
    for r, (inst, prof, p0, p1) in enumerate(ex):
        hyd = xr.open_dataset(run_dir / "hydrography" / f"hydrography_{inst}.nc")
        i = list(hyd["profile_file"].values).index(f"{prof}.nc")
        for c, (g, d) in enumerate(settings):
            ax = axes[r, c]
            pg, steps, lat = cache[(inst, f"{prof}.nc", g, d)]
            pz = gsw.p_from_z(-hyd["depth"].values, lat)
            ct = hyd["CT"].values[i]
            ax.plot(ct, pz, color="k", lw=0.8)
            inr = (pz >= p0) & (pz <= p1) & np.isfinite(ct)
            pad = 0.05 * (ct[inr].max() - ct[inr].min())
            ax.set_xlim(ct[inr].min() - pad, ct[inr].max() + pad)
            for _, s in (steps.iterrows() if len(steps) else []):
                ax.axhspan(s["p_start"], s["p_end"], color=LABEL_COLOR[s["kind"]], alpha=0.3, lw=0)
            ax.set_ylim(p1, p0)
            n = int(((steps["kind"] == "interface") & (steps["p"] >= p0) & (steps["p"] <= p1)).sum()) if len(steps) else 0
            ax.set_title(f"{prof[:9]}\nml_grad {g:g}, Δρ {d:g}: {n} if", fontsize=8)
            if c:
                ax.set_yticklabels([])
            ax.tick_params(labelsize=7)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "threshold_examples.png", dpi=90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
