#!/usr/bin/env python3
"""Figures explaining the Lueck (2022) figure of merit (FM) for the shear spectra.

FM (microstructure-tpw, scor160/l4.py) = mean |ln(observed / Nasmyth)| over the
fitted wavenumbers (0 < k <= K_max), divided by T_M * sigma_ln, the misfit
expected from spectral statistics alone (sigma_ln from the effective number of
FFTs after Goodman cleaning, T_M from the number of wavenumber points).

For each instrument, windows kept by the epsilon_shear step with epsilon in
1e-10 to 1e-9 W/kg (the staircase depths) are grouped by FM bin:
  row 1  median and interquartile range of ln(observed / Nasmyth) against
         k / K_max: where along the fitted range the misfit sits;
  row 2  per-window bias (mean ln ratio) against scatter (mean |ln ratio|):
         a systematic shape difference vs random scatter;
  row 3  one example per FM bin (spectrum, Nasmyth, residual).

Reads:  <run_dir>/epsilon_shear/epsilon_shear_<instrument>.csv,
        <run_dir>/convert/<instrument>/diss_NN/*_prof*.nc
Writes: <run_dir>/epsilon_shear/figures/fm_explained_<instrument>.png

Usage:
    python scripts/explain_fm.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

FM_BINS = [(0.0, 1.15), (1.15, 1.5), (1.5, np.inf)]
EPS_RANGE = (1e-10, 1e-9)
XBINS = np.linspace(0, 1, 11)
COLORS = [ps.BLUE, ps.AQUA, ps.ORANGE]


def label(lo, hi):
    return f"FM {lo:g}–{hi:g}" if np.isfinite(hi) else f"FM > {lo:g}"


def collect(run_dir: Path, name: str) -> pd.DataFrame:
    tab = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{name}.csv")
    tab = tab[tab["keep"]].set_index(["profile_file", "window"])
    rows = []
    for f in sorted(common.single_dir(run_dir / "convert" / name, "diss").glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as d:
            g = lambda n: np.ma.filled(d[n][:].astype(float), np.nan)  # noqa: E731
            s, n, K = g("spec_shear"), g("spec_nasmyth"), g("K")
            eps, fm, kmax = g("epsilon"), g("FM"), g("K_max")
            probes = [str(p) for p in d["probe"][:]]
        for w in range(s.shape[2]):
            if (f.name, w) not in tab.index:
                continue
            t = tab.loc[(f.name, w)]
            for i, p in enumerate(probes):
                if not t[f"use_{p}"] or not (EPS_RANGE[0] <= eps[i, w] < EPS_RANGE[1]):
                    continue
                m = (K[:, w] > 0) & (K[:, w] <= kmax[i, w])
                lr = np.log(s[i, m, w] / n[i, m, w])
                rows.append({"profile_file": f.name, "window": w, "probe": p, "FM": fm[i, w],
                             "epsilon": eps[i, w], "P": t["P_mean"], "x": K[m, w] / kmax[i, w],
                             "lr": lr, "K": K[:, w], "spec": s[i, :, w], "nas": n[i, :, w],
                             "kmax": kmax[i, w], "bias": float(np.mean(lr)),
                             "scatter": float(np.mean(np.abs(lr))), "npts": int(m.sum())})
    return pd.DataFrame(rows)


def figure(name: str, df: pd.DataFrame, path: Path, foot: str) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(14, 12.5))
    for j, ((lo, hi), c) in enumerate(zip(FM_BINS, COLORS)):
        sub = df[(df["FM"] >= lo) & (df["FM"] < hi)]
        # Row 1: residual against k / K_max
        ax = axes[0, j]
        x = np.concatenate(sub["x"].to_list()) if len(sub) else np.array([])
        y = np.concatenate(sub["lr"].to_list()) if len(sub) else np.array([])
        idx = np.digitize(x, XBINS) - 1
        mids = (XBINS[:-1] + XBINS[1:]) / 2
        q = np.array([np.nanpercentile(y[idx == b], [25, 50, 75]) if (idx == b).sum() > 20
                      else [np.nan] * 3 for b in range(len(mids))])
        ax.fill_between(mids, q[:, 0], q[:, 2], color=c, alpha=0.25, lw=0)
        ax.plot(mids, q[:, 1], color=c, lw=2)
        ax.axhline(0, color="k", lw=0.8)
        for v in (np.log(2), -np.log(2)):
            ax.axhline(v, color=ps.MUTED, lw=0.8, ls="--")
        ax.set_ylim(-2.5, 2.5)
        ax.set_xlim(0, 1)
        ax.set_title(f"{label(lo, hi)}: {len(sub)} probe-windows ({len(sub) / max(len(df), 1):.0%})", fontsize=10)
        ax.set_xlabel(r"$k / K_{max}$ (fitted range)")
        if j == 0:
            ax.set_ylabel("ln(observed / Nasmyth)\nmedian and IQR (dashed: factor 2)")
        # Row 2: bias vs scatter per window
        ax = axes[1, j]
        ax.scatter(df["bias"], df["scatter"], s=3, color=ps.GRID, linewidths=0)
        ax.scatter(sub["bias"], sub["scatter"], s=4, color=c, alpha=0.5, linewidths=0)
        ax.plot([0, 2], [0, 2], color=ps.MUTED, lw=0.8)
        ax.plot([0, -2], [0, 2], color=ps.MUTED, lw=0.8)
        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(0, 1.6)
        ax.set_xlabel("bias: mean ln(obs/Nasmyth)")
        if j == 0:
            ax.set_ylabel("scatter: mean |ln(obs/Nasmyth)|")
        if len(sub):
            ax.text(0.03, 0.95, f"median bias {sub['bias'].median():+.2f}\nmedian scatter "
                    f"{sub['scatter'].median():.2f}\nmedian points {sub['npts'].median():.0f}\n"
                    f"median depth {sub['P'].median():.0f} dbar",
                    transform=ax.transAxes, va="top", fontsize=8)
        # Row 3: example closest to the bin's median scatter
        ax = axes[2, j]
        if len(sub):
            ex = sub.iloc[int(np.argmin(np.abs(sub["scatter"] - sub["scatter"].median())))]
            K = ex["K"]
            ax.loglog(K[1:], ex["spec"][1:], color=c, lw=1, label="observed")
            ax.loglog(K[1:], ex["nas"][1:], color="k", lw=1, ls=":", label="Nasmyth at fitted ε")
            ax.axvline(ex["kmax"], color=ps.MUTED, lw=1, label=r"$K_{max}$")
            ax.axvspan(K[1], ex["kmax"], color=c, alpha=0.08, lw=0)
            ax.set_xlim(0.2, 300)
            ax.set_ylim(1e-9, 1e-3)
            ax.set_title(f"{ex['profile_file'][:11]} w{ex['window']} {ex['probe']}: "
                         f"ε {ex['epsilon']:.1e}, FM {ex['FM']:.2f}, {ex['P']:.0f} dbar", fontsize=9)
            ax.legend(fontsize=7.5, loc="lower left")
        ax.set_xlabel("k (cpm)")
        if j == 0:
            ax.set_ylabel(r"Φ (s$^{-2}$ cpm$^{-1}$)")
    fig.suptitle(f"{name}: what the figure of merit measures (windows with ε {EPS_RANGE[0]:.0e}–"
                 f"{EPS_RANGE[1]:.0e} W/kg)", x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run_dir = common.run_dir_of(config)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    for name, _ in common.instruments(config):
        df = collect(run_dir, name)
        figure(name, df, run_dir / "epsilon_shear" / "figures" / f"fm_explained_{name}.png", foot)
        for (lo, hi) in FM_BINS:
            sub = df[(df["FM"] >= lo) & (df["FM"] < hi)]
            print(f"{name} {label(lo, hi)}: n={len(sub)}, bias {sub['bias'].median():+.2f}, "
                  f"scatter {sub['scatter'].median():.2f}, points {sub['npts'].median():.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
