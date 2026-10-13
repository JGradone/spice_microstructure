#!/usr/bin/env python3
"""Compare shear epsilon (and perturb chi) between runs, e.g. FFT/dissipation length runs.

For each run and instrument (epsilon_shear outputs, kept windows):
  * metrics below 150 dbar: median epsilon, median floor, fraction at floor,
    probe disagreement, refit/perturb ratio (effect of the low-wavenumber
    cutoff), FM > 1.15 fraction; arithmetic mean epsilon over 150-550 dbar;
  * paired depth-bin means: per profile, arithmetic mean epsilon and chi in
    bins of double_diffusion.depth_bin_m over 150-550 dbar, ratio to the
    first run for the same profile and bin (what the averaged tests see);
  * example profiles through the staircase: FP07 temperature with epsilon and
    chi drawn over each window's vertical extent (every other window, so the
    50%-overlapping windows do not overlap on the plot), one colour per run.

Reads:  outputs/<run>/epsilon_shear/epsilon_shear_<instrument>.csv,
        outputs/<run>/convert/<instrument>/{profiles,chi}_NN/
Writes: outputs/comparisons/<label>/comparison.json, comparison_bins.png, examples.png

Usage:
    python scripts/compare_runs.py --config config/config.yaml --label window_lengths \
        --runs baseline fft2_diss16 fft2_diss8 \
        --examples vmp5500:SPC_031_prof001:250:340 vmp250:data_0132_prof001:150:260
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

BAND = (150, 550)
COLORS = [ps.MUTED, ps.BLUE, ps.ORANGE, ps.AQUA, ps.RED]


def run_config(config, config_hash, run):
    if run == config["run"]["name"]:
        return config, config_hash
    return common.apply_sensitivity(config, config_hash, run)


def chi_table(run_dir: Path, inst: str) -> pd.DataFrame:
    rows = []
    for f in sorted(common.single_dir(run_dir / "convert" / inst, "chi").glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as d:
            chi = np.ma.filled(d["chiMean"][:].astype(float), np.nan)
        rows.append(pd.DataFrame({"profile_file": f.name, "window": np.arange(len(chi)), "chi": chi}))
    return pd.concat(rows, ignore_index=True)


def metrics(df: pd.DataFrame, probes: list[str]) -> dict:
    k = df[df["keep"]]
    deep = k[k["P_mean"] > BAND[0]]
    band = k[(k["P_mean"] > BAND[0]) & (k["P_mean"] < BAND[1])]
    ratio = pd.concat([deep[f"epsilon_{p}"] / deep[f"epsilon_{p}_perturb"] for p in probes])
    fm = pd.concat([deep[f"FM_{p}"] for p in probes])
    return {"windows_kept": int(len(k)),
            "median_epsilon_below_150": float(deep["epsilon_shear"].median()),
            "mean_epsilon_150_550": float(band["epsilon_shear"].mean()),
            "mean_epsilon_bounded_150_550": float(band["epsilon_shear_bounded"].mean()),
            "median_floor_below_150": float(deep["epsilon_floor"].median()),
            "at_floor_fraction_below_150": round(float(deep["at_floor"].mean()), 3),
            "probe_disagree_fraction": round(float(((k["flags"] & 2) > 0).mean()), 3),
            "refit_over_perturb_median": round(float(ratio.median()), 3),
            "FM_over_1.15_fraction": round(float((fm > 1.15).mean()), 3)}


def binned(df: pd.DataFrame, chi: pd.DataFrame, bin_m: float) -> pd.DataFrame:
    k = df[df["keep"] & (df["P_mean"] > BAND[0]) & (df["P_mean"] < BAND[1])].merge(
        chi, on=["profile_file", "window"], how="left")
    k["bin"] = (np.floor(k["P_mean"] / bin_m) * bin_m + bin_m / 2)
    return k.groupby(["profile_file", "bin"]).agg(eps=("epsilon_shear", "mean"),
                                                  eps_b=("epsilon_shear_bounded", "mean"),
                                                  chi=("chi", "mean"), n=("epsilon_shear", "size"))


def examples_figure(examples, runs, cfgs, path, foot):
    fig, axes = plt.subplots(1, 3 * len(examples), figsize=(5.2 * len(examples) * 1.35, 7.5),
                             gridspec_kw={"width_ratios": [1.1, 1, 1] * len(examples)}, squeeze=False)
    for e, (inst, prof, z0, z1) in enumerate(examples):
        axT, axE, axC = axes[0, 3 * e:3 * e + 3]
        for c, run in zip(COLORS, runs):
            rd = common.run_dir_of(cfgs[run][0])
            df = pd.read_csv(rd / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
            df = df[df["profile_file"] == f"{prof}.nc"]
            chi = chi_table(rd, inst)
            df = df.merge(chi[chi["profile_file"] == f"{prof}.nc"], on=["profile_file", "window"], how="left")
            pe = cfgs[run][0]["perturb"]["epsilon"]
            half = pe["diss_sec"] * df["speed"] / 2                        # window half extent (m ~ dbar)
            for ax, col in ((axE, "epsilon_shear"), (axC, "chi")):
                for _, r in df[df["window"] % 2 == 0].iterrows():     # every other window: no overlap
                    if z0 - 10 <= r["P_mean"] <= z1 + 10 and np.isfinite(r[col]):
                        h = half.loc[_]
                        ax.plot([r[col], r[col]], [r["P_mean"] - h, r["P_mean"] + h], color=c, lw=1.6)
                ax.plot([], [], color=c, lw=2, label=f"{run} ({pe['fft_sec']:g} s / {pe['diss_sec']:g} s)")
            if run == runs[0]:
                prof_file = common.single_dir(rd / "convert" / inst, "profiles") / f"{prof}.nc"
                with netCDF4.Dataset(prof_file) as d:
                    P = np.ma.filled(d["P"][:].astype(float), np.nan)
                    T = np.ma.filled(d["T1"][:].astype(float), np.nan)
                m = (P > z0) & (P < z1)
                axT.plot(T[m], P[m], color="k", lw=0.8)
        axT.set_ylabel("pressure (dbar)")
        axT.set_xlabel("FP07 T1 (°C)")
        axT.set_title(f"{inst} {prof}", fontsize=10)
        axE.set_xscale("log")
        axE.set_xlabel(r"$\epsilon_{shear}$ (W kg$^{-1}$)")
        axC.set_xscale("log")
        axC.set_xlabel(r"$\chi$ (K$^2$ s$^{-1}$, perturb)")
        axE.legend(fontsize=7, loc="lower right")
        for ax in (axT, axE, axC):
            ax.set_ylim(z1, z0)
        for ax in (axE, axC):
            ax.set_yticklabels([])
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=105)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", nargs="+", required=True, help="first run is the reference")
    ap.add_argument("--examples", nargs="*", default=[], help="instrument:profile:p0:p1")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    cfgs = {r: run_config(config, config_hash, r) for r in args.runs}
    out = REPO / config["paths"]["output_root"] / "comparisons" / args.label
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash))
    ps.apply()
    bin_m = config["double_diffusion"]["depth_bin_m"]
    names = [n for n, _ in common.instruments(config)]
    summary = {"runs": {r: cfgs[r][0]["run"] for r in args.runs}, "depth_bin_m": bin_m, "instruments": {}}
    fig, axes = plt.subplots(2, len(names), figsize=(6.5 * len(names), 9), squeeze=False)
    for j, inst in enumerate(names):
        s = summary["instruments"][inst] = {}
        bins = {}
        for run in args.runs:
            rd = common.run_dir_of(cfgs[run][0])
            df = pd.read_csv(rd / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
            probes = [c[len("use_"):] for c in df.columns if c.startswith("use_")]
            s[run] = metrics(df, probes)
            bins[run] = binned(df, chi_table(rd, inst), bin_m)
        ref = bins[args.runs[0]]
        for c, run in zip(COLORS, args.runs):
            b = ref.join(bins[run], rsuffix="_r", how="inner")
            ok = (b["n"] >= 1) & (b["n_r"] >= 1)
            re = np.log10(b.loc[ok, "eps_r"] / b.loc[ok, "eps"])
            rc = np.log10(b.loc[ok, "chi_r"] / b.loc[ok, "chi"])
            s[run]["paired_bins"] = int(ok.sum())
            s[run]["paired_bin_eps_ratio_median"] = round(float(10 ** re.median()), 3)
            s[run]["paired_bin_eps_ratio_iqr"] = [round(float(10 ** re.quantile(q)), 3) for q in (0.25, 0.75)]
            s[run]["paired_bin_chi_ratio_median"] = round(float(10 ** rc.median()), 3)
            s[run]["paired_bin_chi_ratio_iqr"] = [round(float(10 ** rc.quantile(q)), 3) for q in (0.25, 0.75)]
            prof = bins[run].groupby(level="bin").agg(eps=("eps", "mean"), chi=("chi", "mean"))
            axes[0, j].plot(prof["eps"], prof.index, color=c, lw=1.8, marker="o", ms=3, label=run)
            axes[1, j].plot(prof["chi"], prof.index, color=c, lw=1.8, marker="o", ms=3, label=run)
            print(f"{inst} {run}: " + ", ".join(f"{k} {v}" for k, v in s[run].items()))
        for ax, lab in ((axes[0, j], r"mean $\epsilon_{shear}$ (W kg$^{-1}$)"), (axes[1, j], r"mean $\chi$ (K$^2$ s$^{-1}$)")):
            ax.set_xscale("log")
            ax.set_ylim(BAND[1], BAND[0])
            ax.set_xlabel(lab)
            ax.set_ylabel("pressure (dbar)")
            ax.legend(fontsize=8)
        axes[0, j].set_title(f"{inst}: mean over profiles, {bin_m:g} m bins", fontsize=10)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "comparison_bins.png", dpi=100)
    plt.close(fig)
    if args.examples:
        ex = [(e.split(":")[0], e.split(":")[1], float(e.split(":")[2]), float(e.split(":")[3])) for e in args.examples]
        examples_figure(ex, args.runs, cfgs, out / "examples.png", foot)
    common.write_json(out / "comparison.json", {"provenance": foot, **summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
