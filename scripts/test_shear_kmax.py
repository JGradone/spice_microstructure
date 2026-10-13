#!/usr/bin/env python3
"""Test the upper integration limit of the shear epsilon refit against the noise spectrum.

With the low-wavenumber cutoff from shear_qc.refit.f_min_hz, epsilon is refit
with these upper limits (per probe and window):
  perturb    perturb's K_max (the epsilon_shear step as configured)
  r=<x>      min(K_max, first k above the cutoff where the observed spectrum,
             smoothed over 3 bins, falls below x times the noise spectrum);
             x from shear_qc.refit.test_noise_ratio
  subtract   perturb's K_max, noise subtracted first (lower bracket)
Two noise models: `quiet` is the epsilon_shear step's noise spectrum
(noise_spectrum_<instrument>.csv; median of the quietest windows, which still
holds low-epsilon turbulence at low wavenumbers), and `white` is its flat
high-frequency plateau (median over shear_qc.refit.test_white_band_hz) taken as
constant in frequency.
Reported for windows below 150 dbar: median ratio to `perturb` by epsilon
decade, residual ln(observed/Nasmyth) along k/K_used for epsilon 1e-10-1e-9,
median points in the fit, unfit fraction, mean epsilon over 150-550 dbar.

Reads:  <run_dir>/convert/<instrument>/diss_NN, <run_dir>/epsilon_shear/noise_spectrum_<instrument>.csv
Writes: <run_dir>/epsilon_shear/kmax_test/kmax_test.json, kmax_test.png

Usage:
    python scripts/test_shear_kmax.py --config config/config.yaml [--sensitivity NAME]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from epsilon_shear import load, nasmyth_grid, refit, vibration_channels  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

XB = np.linspace(0, 1, 11)
DECADES = [-12, -10, -9.5, -9, -8, -4]


def noise_limit(data, noise, ratio, f_min):
    """Per probe: first k >= f_min/speed where the 3-bin smoothed spectrum < ratio x noise."""
    df, K = data["df"], data["K"]
    u = df["speed"].to_numpy()
    out = {}
    for i, p in enumerate(data["probes"]):
        sm = uniform_filter1d(data["spec"][:, i, :], 3, axis=1)
        nk = noise[p][None, :] * u[:, None]
        below = (sm < ratio * nk) & (K >= f_min / u[:, None]) & (K > 0)
        first = np.where(below.any(axis=1), np.argmax(below, axis=1), -1)
        out[p] = np.where(first >= 0, K[np.arange(len(K)), np.maximum(first, 0)], np.inf)
    return out


def residual(data, res, f_min, sel):
    df, K = data["df"], data["K"]
    p = data["probes"][0]
    eps, kmax = res[p]["epsilon"], res[p]["K_max"]
    xs, ys, npts = [], [], []
    for w in np.flatnonzero(sel & np.isfinite(eps)):
        k = K[w]
        m = (k > 0) & (k >= f_min / df["speed"].iloc[w]) & (k <= kmax[w])
        xs.append(k[m] / kmax[w])
        ys.append(np.log(data["spec"][w, 0, m] / nasmyth_grid(eps[w], df["nu"].iloc[w], k[m])))
        npts.append(m.sum())
    x, y = np.concatenate(xs), np.concatenate(ys)
    idx = np.digitize(x, XB) - 1
    q = np.array([np.nanpercentile(y[idx == b], [25, 50, 75]) if (idx == b).sum() > 30 else [np.nan] * 3
                  for b in range(len(XB) - 1)])
    return q, float(np.median(npts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--sensitivity", metavar="NAME")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    if args.sensitivity:
        config, config_hash = common.apply_sensitivity(config, config_hash, args.sensitivity)
    run_dir = common.run_dir_of(config)
    rc = config["shear_qc"]["refit"]
    f_min = float(rc["f_min_hz"])
    out = run_dir / "epsilon_shear" / "kmax_test"
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    names = [n for n, _ in common.instruments(config)]
    fig, axes = plt.subplots(1, len(names), figsize=(6.8 * len(names), 4.8), squeeze=False)
    colors = [ps.MUTED, ps.BLUE_RAMP[2], ps.BLUE_RAMP[4], ps.BLUE_RAMP[6], ps.ORANGE, ps.RED, ps.ORANGE_RAMP[6]]
    summary = {"f_min_hz": f_min}
    mids = (XB[:-1] + XB[1:]) / 2
    for j, name in enumerate(names):
        data = load(common.single_dir(run_dir / "convert" / name, "diss"))
        n_v = vibration_channels(data)
        nz = pd.read_csv(run_dir / "epsilon_shear" / f"noise_spectrum_{name}.csv")
        lo, hi = rc["test_white_band_hz"]
        fb = (nz["frequency_hz"] >= lo) & (nz["frequency_hz"] < hi)
        models = {"quiet": {p: nz[f"noise_{p}"].to_numpy() for p in data["probes"]},
                  "white": {p: np.full(len(nz), float(nz.loc[fb, f"noise_{p}"].median())) for p in data["probes"]}}
        df = data["df"]
        deep = (df["P_mean"] > 150).to_numpy()
        band = deep & (df["P_mean"] < 550).to_numpy()
        variants = {"perturb": refit(data, f_min, rc["min_points"], n_v)}
        for mname, noise in models.items():
            for r in rc["test_noise_ratio"]:
                variants[f"{mname} r={r:g}"] = refit(data, f_min, rc["min_points"], n_v,
                                                     k_upper=noise_limit(data, noise, float(r), f_min))
            variants[f"{mname} subtract"] = refit(data, f_min, rc["min_points"], n_v, subtract=noise)
        s_noise = {p: float(v[0]) for p, v in models["white"].items()}
        base = variants["perturb"]
        s = summary[name] = {"white_noise_level_s-2_per_Hz": s_noise}
        p0 = data["probes"][0]
        sel = deep & (base[p0]["epsilon"] >= 1e-10) & (base[p0]["epsilon"] < 1e-9)
        for c, (lab, res) in zip(colors, variants.items()):
            if lab.startswith("quiet r"):
                continue
            ratios, e_band = [], []
            for p in data["probes"]:
                e0, e1 = base[p]["epsilon"], res[p]["epsilon"]
                ok = deep & np.isfinite(e0)
                ratios.append(pd.DataFrame({"r": e1[ok] / e0[ok], "e0": e0[ok]}))
                e_band.append(np.where(np.isfinite(e1[band & np.isfinite(e0)]), e1[band & np.isfinite(e0)], np.nan))
            R = pd.concat(ratios)
            q, npts = residual(data, res, f_min, sel)
            s[lab] = {"median_ratio_to_perturb_Kmax": round(float(R["r"].median()), 3),
                      "ratio_by_decade": R.groupby(pd.cut(np.log10(R["e0"]), DECADES), observed=True)["r"]
                      .median().round(3).rename(lambda b: str(b)).to_dict(),
                      "unfit_fraction": round(float(R["r"].isna().mean()), 4),
                      "mean_epsilon_150_550": float(np.nanmean(np.concatenate(e_band))),
                      "median_points_in_fit_1e-10_1e-9": npts,
                      "residual_median_by_k_over_Kused": [None if not np.isfinite(v) else round(float(v), 3)
                                                          for v in q[:, 1]],
                      "residual_spread_of_medians": round(float(np.nanmax(q[:, 1]) - np.nanmin(q[:, 1])), 3)}
            ax = axes[0, j]
            ax.fill_between(mids, q[:, 0], q[:, 2], color=c, alpha=0.12, lw=0)
            ax.plot(mids, q[:, 1], color=c, lw=2, label=f"{lab}: ε×{s[lab]['median_ratio_to_perturb_Kmax']:.2f}, "
                                                        f"{npts:.0f} pts")
            print(f"{name} {lab}: ratio {s[lab]['median_ratio_to_perturb_Kmax']} by decade {s[lab]['ratio_by_decade']}, "
                  f"unfit {s[lab]['unfit_fraction']}, pts {npts:.0f}, residual range "
                  f"{s[lab]['residual_spread_of_medians']}, mean 150-550 {s[lab]['mean_epsilon_150_550']:.2e}")
        ax = axes[0, j]
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylim(-2, 2)
        ax.set_xlim(0, 1)
        ax.set_xlabel(r"$k / K_{used}$")
        ax.set_ylabel("ln(observed / Nasmyth at fitted ε), sh1")
        ax.set_title(f"{name}: upper limit test, f_min {f_min:g} Hz (ε 1e-10–1e-9, >150 dbar)", fontsize=10)
        ax.legend(fontsize=7.5)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "kmax_test.png", dpi=100)
    common.write_json(out / "kmax_test.json", {"provenance": foot, **summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
