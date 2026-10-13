#!/usr/bin/env python3
"""Test the low-wavenumber cutoff of the shear epsilon refit (epsilon_shear step).

For each f_min in shear_qc.refit.test_f_min_hz, epsilon is re-solved over
f_min/speed <= k <= K_max (f_min 0 must reproduce perturb). Reported for
windows below 150 dbar, by instrument:
  * median refit/perturb ratio, overall, by perturb FM bin and by epsilon decade;
  * the residual ln(observed / Nasmyth) along k / K_max for epsilon 1e-10 to
    1e-9 (the cutoff is right when the residual inside the refit range is flat);
  * the arithmetic mean epsilon over 150-550 dbar (what the averages use).

Reads:  <run_dir>/convert/<instrument>/diss_NN/*_prof*.nc
Writes: <run_dir>/epsilon_shear/fmin_test/fmin_test.json, fmin_test.png

Usage:
    python scripts/test_shear_fmin.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from epsilon_shear import load, nasmyth_grid, refit, vibration_channels  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

XB = np.linspace(0, 1, 11)
FM_BINS = [0, 1.15, 1.5, np.inf]


def residual_profile(data, eps, probe_i, sel, f_min):
    """Median and IQR of ln(obs/Nasmyth(eps)) against k/K_max over the refit range."""
    df, K = data["df"], data["K"]
    p = data["probes"][probe_i]
    xs, ys = [], []
    for w in np.flatnonzero(sel & np.isfinite(eps)):
        k = K[w]
        km = df[f"K_max_{p}"].iloc[w]
        m = (k > 0) & (k >= f_min / df["speed"].iloc[w]) & (k <= km)
        if m.sum() < 3:
            continue
        xs.append(k[m] / km)
        ys.append(np.log(data["spec"][w, probe_i, m] / nasmyth_grid(eps[w], df["nu"].iloc[w], k[m])))
    x, y = np.concatenate(xs), np.concatenate(ys)
    idx = np.digitize(x, XB) - 1
    return np.array([np.nanpercentile(y[idx == b], [25, 50, 75]) if (idx == b).sum() > 30 else [np.nan] * 3
                     for b in range(len(XB) - 1)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run_dir = common.run_dir_of(config)
    rc = config["shear_qc"]["refit"]
    out = run_dir / "epsilon_shear" / "fmin_test"
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    fmins = [float(f) for f in rc["test_f_min_hz"]]
    names = [n for n, _ in common.instruments(config)]
    fig, axes = plt.subplots(2, len(names), figsize=(6.5 * len(names), 9), squeeze=False)
    colors = [ps.MUTED, ps.BLUE, ps.AQUA, ps.ORANGE, ps.RED]
    summary = {}
    for j, name in enumerate(names):
        data = load(common.single_dir(run_dir / "convert" / name, "diss"))
        n_v = vibration_channels(data)
        df = data["df"]
        deep = (df["P_mean"] > 150).to_numpy()
        band = deep & (df["P_mean"] < 550).to_numpy()
        res = {f: refit(data, f, rc["min_points"], n_v) for f in fmins}
        s = summary[name] = {"n_vibration_channels": n_v, "num_ffts": data["num_ffts"], "f_min": {}}
        mids = (XB[:-1] + XB[1:]) / 2
        for c, f in zip(colors, fmins):
            r = {}
            ratios, e_all, e_pert = [], [], []
            for i, p in enumerate(data["probes"]):
                e0, e1 = df[f"epsilon_{p}"].to_numpy(), res[f][p]["epsilon"]
                ok = deep & np.isfinite(e0) & np.isfinite(e1)
                ratios.append(pd.DataFrame({"r": e1[ok] / e0[ok], "FM": df[f"FM_{p}"].to_numpy()[ok],
                                            "e0": e0[ok], "FMr": res[f][p]["FM"][ok]}))
                bb = band & np.isfinite(e0) & np.isfinite(e1)
                e_all.append(e1[bb]); e_pert.append(e0[bb])
            R = pd.concat(ratios)
            r["median_ratio"] = round(float(R["r"].median()), 3)
            r["ratio_by_perturb_FM"] = R.groupby(pd.cut(R["FM"], FM_BINS), observed=True)["r"].median().round(3) \
                .rename(lambda b: str(b)).to_dict()
            r["ratio_by_decade"] = R.groupby(pd.cut(np.log10(R["e0"]), [-12, -10, -9.5, -9, -8, -4]), observed=True)["r"] \
                .median().round(3).rename(lambda b: str(b)).to_dict()
            r["FM_refit_fraction_over_1.15"] = round(float((R["FMr"] > 1.15).mean()), 3)
            r["FM_perturb_fraction_over_1.15"] = round(float((R["FM"] > 1.15).mean()), 3)
            r["mean_epsilon_150_550"] = float(np.mean(np.concatenate(e_all)))
            r["mean_epsilon_150_550_perturb"] = float(np.mean(np.concatenate(e_pert)))
            e0 = df[f"epsilon_{data['probes'][0]}"].to_numpy()
            sel = deep & (e0 >= 1e-10) & (e0 < 1e-9)
            q = residual_profile(data, res[f][data["probes"][0]]["epsilon"], 0, sel, f)
            r["residual_median_by_k_over_Kmax"] = [None if not np.isfinite(v) else round(float(v), 3) for v in q[:, 1]]
            s["f_min"][str(f)] = r
            ax = axes[0, j]
            ax.fill_between(mids, q[:, 0], q[:, 2], color=c, alpha=0.15, lw=0)
            ax.plot(mids, q[:, 1], color=c, lw=2, label=f"f_min {f:g} Hz" + (" (≈ perturb)" if f == 0 else ""))
            print(f"{name} f_min {f:g}: ratio {r['median_ratio']}, by FM {r['ratio_by_perturb_FM']}, "
                  f"FM>1.15 {r['FM_perturb_fraction_over_1.15']} -> {r['FM_refit_fraction_over_1.15']}, "
                  f"mean eps 150-550 {r['mean_epsilon_150_550']:.2e} (perturb {r['mean_epsilon_150_550_perturb']:.2e})")
        ax = axes[0, j]
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylim(-2, 2)
        ax.set_xlim(0, 1)
        ax.set_xlabel(r"$k/K_{max}$")
        ax.set_ylabel("ln(observed / Nasmyth at refit ε), sh1")
        ax.set_title(f"{name}: residual inside the refit range (ε 1e-10–1e-9, >150 dbar)", fontsize=10)
        ax.legend(fontsize=8)
        ax = axes[1, j]
        x = np.arange(len(fmins))
        for k, (lab, key) in enumerate([("FM < 1.15", "(0.0, 1.15]"), ("FM 1.15–1.5", "(1.15, 1.5]"),
                                        ("FM > 1.5", "(1.5, inf]")]):
            ax.plot(x, [s["f_min"][str(f)]["ratio_by_perturb_FM"].get(key, np.nan) for f in fmins], "o-",
                    color=[ps.BLUE, ps.AQUA, ps.ORANGE][k], label=f"perturb {lab}")
        ax.set_xticks(x, [f"{f:g}" for f in fmins])
        ax.set_xlabel("f_min (Hz)")
        ax.set_ylabel("median ε refit / ε perturb")
        ax.set_ylim(0, 1.2)
        ax.axhline(1, color="k", lw=0.8)
        ax.legend(fontsize=8)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "fmin_test.png", dpi=100)
    common.write_json(out / "fmin_test.json", {"provenance": foot, **summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
