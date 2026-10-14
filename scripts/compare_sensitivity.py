#!/usr/bin/env python3
"""Compare the headline numbers of sensitivity runs against a reference run.

For each run and instrument ("<instrument> all free fall", finger-favourable
water, the last staircase method, finescale gradients unless noted), pooled:
  K_T and K_S (gamma = double_diffusion.flux_ratio_gamma) for all finger water
  and for interfaces; the interface excess E over the Re_b-matched control and
  its finger fraction; the raw interface ratio <chi_obs>/<chi_exp>; the number
  of interface windows. Each value is also given relative to the reference run.

Reads:  outputs/<run>/{diffusivities/diffusivity_bins.csv, dd_test/dd_excess.csv, dd_test/dd_pooled.csv}
Writes: outputs/comparisons/<label>/sensitivity_summary.csv, sensitivity_summary.png

Usage:
    python scripts/compare_sensitivity.py --config config/config.yaml --label sensitivity \\
        --reference fft2_diss8_mle --runs an_strat5m an_strat25m ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

METRICS = ["K_S_finger", "K_S_interface", "K_T_finger", "K_T_interface", "E_interface", "finger_fraction_interface",
           "R_interface_raw", "n_interface_windows"]


def run_metrics(config, config_hash, run, ref_name) -> pd.DataFrame:
    cfg, _ = (config, config_hash) if run == ref_name and run == config["run"]["name"] else \
        common.apply_sensitivity(config, config_hash, run)
    rd = common.run_dir_of(cfg)
    g0 = float(cfg["double_diffusion"]["flux_ratio_gamma"])
    m = cfg["regimes"]["staircase"]["methods"][-1]
    diff = pd.read_csv(rd / "diffusivities" / "diffusivity_bins.csv")
    exc = pd.read_csv(rd / "dd_test" / "dd_excess.csv")
    pooled = pd.read_csv(rd / "dd_test" / "dd_pooled.csv")
    rows = []
    for inst in [n for n, _ in common.instruments(cfg)]:
        g = f"{inst} all free fall"
        d = diff[(diff["instrument_group"] == g) & (diff["method"] == m) & (diff["turner"] == "finger_any")
                 & (diff["gradients"] == "finescale") & (diff["depth_bin"].astype(str) == "pooled")]
        e = exc[(exc["instrument_group"] == g) & (exc["method"] == m) & (exc["staircase"] == "interface")
                & (exc["gradients"] == "finescale")]
        p = pooled[(pooled["instrument_group"] == g) & (pooled["method"] == m) & (pooled["turner"] == "finger_any")
                   & (pooled["staircase"] == "interface") & (pooled["gradients"] == "finescale")
                   & (pooled["n2_filter"] == "all")]
        get = lambda t, s, c: float(t.loc[t["staircase"] == s, c].iloc[0]) if (t["staircase"] == s).any() else np.nan  # noqa: E731
        ev = float(e["excess"].iloc[0]) if len(e) else np.nan
        rows.append({"run": run, "instrument": inst,
                     "K_S_finger": get(d, "all", f"K_S_g{g0:g}"), "K_S_interface": get(d, "interface", f"K_S_g{g0:g}"),
                     "K_T_finger": get(d, "all", "K_T"), "K_T_interface": get(d, "interface", "K_T"),
                     "E_interface": ev, "E_interface_lo": float(e["excess_lo"].iloc[0]) if len(e) else np.nan,
                     "E_interface_hi": float(e["excess_hi"].iloc[0]) if len(e) else np.nan,
                     "finger_fraction_interface": 1 - 1 / ev if ev > 0 else np.nan,
                     "R_interface_raw": float(p["ratio"].iloc[0]) if len(p) else np.nan,
                     "n_interface_windows": int(p["n_windows"].iloc[0]) if len(p) else 0,
                     "overrides": str(cfg["run"].get("sensitivity", {}).get("set", {}))})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--runs", nargs="+", required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    out = REPO / config["paths"]["output_root"] / "comparisons" / args.label
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    tab = pd.concat([run_metrics(config, config_hash, r, args.reference) for r in [args.reference] + args.runs],
                    ignore_index=True)
    ref = tab[tab["run"] == args.reference].set_index("instrument")
    for mtr in METRICS:
        tab[f"{mtr}_rel"] = [row[mtr] / ref.loc[row["instrument"], mtr] if ref.loc[row["instrument"], mtr] else np.nan
                             for _, row in tab.iterrows()]
    tab.to_csv(out / "sensitivity_summary.csv", index=False, float_format="%.4g")

    show = ["K_S_finger", "K_S_interface", "E_interface", "R_interface_raw", "n_interface_windows"]
    insts = sorted(tab["instrument"].unique())
    fig, axes = plt.subplots(1, len(show), figsize=(3.3 * len(show), 0.42 * len(tab["run"].unique()) + 2),
                             sharey=True, squeeze=False)
    runs = list(dict.fromkeys(tab["run"]))
    for ax, mtr in zip(axes[0], show):
        for k, (inst, c) in enumerate(zip(insts, (ps.BLUE, ps.ORANGE))):
            s = tab[tab["instrument"] == inst].set_index("run").reindex(runs)
            y = np.arange(len(runs)) + (k - 0.5) * 0.25
            ax.scatter(s[f"{mtr}_rel"], y, color=c, s=24, label=inst, zorder=3)
            if mtr == "E_interface":
                ref_e = ref.loc[inst, "E_interface"]
                ax.hlines(y, s["E_interface_lo"] / ref_e, s["E_interface_hi"] / ref_e, color=c, lw=1)
        ax.axvline(1, color="k", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlim(0.25, 4)
        ax.set_title(f"{mtr}\n(relative to {args.reference})", fontsize=8.5)
    axes[0, 0].set_yticks(range(len(runs)), runs, fontsize=8)
    axes[0, 0].invert_yaxis()
    axes[0, 0].legend(fontsize=7)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "sensitivity_summary.png", dpi=100)
    cols = ["run", "instrument"] + METRICS
    print(tab[cols].to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
