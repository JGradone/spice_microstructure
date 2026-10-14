#!/usr/bin/env python3
"""Figures illustrating the possible microstructure-tpw issues in docs/package_issues.md.

  1. epsilon_T / shear epsilon against K_max/kB (roll-off resolution), for the
     single-pole and double-pole FP07 response runs (items 5 and 8).
  2. Thorpe-sorting bias: perturb's sorted dT/dz and N2 in SPC_033 with the
     measured salinity and with its 35 PSU default, against a linear fit (item 2).
  3. FP07 temperature from the header (factory) coefficients against the in-situ
     calibrated temperature and SBT1 (item 4 context: the uncalibrated offset).

Reads existing run outputs and converts one patched file to NetCDF in a
temporary directory (rsi-tpw nc); writes only PNGs to --out.

Usage:
    python scripts/diagnose_package_issues.py --config config/config.yaml --out docs/private/figures_for_pat
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import gsw
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from odas_tpw.processing.mixing import profile_stratification  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402

RUNS = {"single_pole": "fft2_diss8_mle", "double_pole": "fft2_diss8_mle_dp"}
CAST = "SPC_033"
P_RANGE = (150.0, 250.0)
EDGES = np.array([0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0])


def run_dir(config, config_hash, name):
    return common.run_dir_of(common.apply_sensitivity(config, config_hash, name)[0])


def fig_epsilon_ratio(config, config_hash, out):
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, inst in zip(axs, config["run"]["instruments"]):
        sh = pd.read_csv(run_dir(config, config_hash, RUNS["single_pole"]) / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
        sh = sh[sh["keep"] & (sh["P_mean"] > 150) & (sh["epsilon_shear"] >= 5 * sh["epsilon_floor"])]
        for (model, run), c in zip(RUNS.items(), ["C0", "C3"]):
            th = pd.read_csv(run_dir(config, config_hash, run) / "thermistor" / f"thermistor_{inst}.csv")
            th = th[th["use_T1"].astype(bool)]
            m = th.merge(sh[["profile_file", "window", "epsilon_shear"]], on=["profile_file", "window"])
            x = m["K_max_ratio_T1"].to_numpy(float)
            r = np.log10(m["epsilon_T_T1"] / m["epsilon_shear"]).to_numpy(float)
            ok = np.isfinite(x) & np.isfinite(r)
            ax.scatter(x[ok], r[ok], s=2, alpha=0.08, color=c, rasterized=True)
            idx = np.digitize(x[ok], EDGES)
            mid, med, q1, q3 = [], [], [], []
            for i in range(1, len(EDGES)):
                v = r[ok][idx == i]
                if len(v) >= 20:
                    mid.append(0.5 * (EDGES[i - 1] + EDGES[i]))
                    med.append(np.median(v)), q1.append(np.percentile(v, 25)), q3.append(np.percentile(v, 75))
            ax.errorbar(mid, med, yerr=[np.subtract(med, q1), np.subtract(q3, med)], color=c, marker="o", lw=2,
                        capsize=3, label=f"{model} (median, IQR)")
        ax.axhline(0, color="k", lw=0.8)
        ax.axvline(1.6, color="0.4", ls="--", lw=0.8)
        ax.text(1.65, 1.6, "resolved\n(K_max/kB ≥ 1.6)", fontsize=8, color="0.3", va="top")
        ax.set(xlim=(0.4, 4), ylim=(-2, 2), xlabel="K_max / kB (T1)", title=f"{inst}: shear ε ≥ 5× floor, P > 150 dbar")
        ax.legend(loc="lower left", fontsize=8)
    axs[0].set_ylabel("log10( ε_T / ε_shear )")
    fig.suptitle("Thermistor ε (Kraichnan MLE) against shear ε: biased high when the roll-off is unresolved; "
                 "level depends on FP07 model", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "1_epsilon_T_vs_kmax_ratio.png", dpi=150)
    plt.close(fig)


def fig_thorpe(config, out):
    base = common.run_dir_of(config) / "convert" / "vmp5500"
    p = xr.open_dataset(next(base.glob(f"profiles_*/{CAST}_prof001.nc")))
    P, T, C = p["P"].values, p["SBT1"].values, p["SBC1"].values
    lat, lon = float(np.nanmean(p["lat"].values)), float(np.nanmean(p["lon"].values))
    sp = gsw.SP_from_C(C, T, P)
    sel = (P >= P_RANGE[0] - 5) & (P <= P_RANGE[1] + 5) & np.isfinite(T) & np.isfinite(sp)
    P, T, sp = P[sel], T[sel], sp[sel]
    z = -gsw.z_from_p(P, lat)
    sa = gsw.SA_from_SP(sp, P, lon, lat)
    ct = gsw.CT_from_t(sa, T, P)
    in_r = (P >= P_RANGE[0]) & (P <= P_RANGE[1])
    slope_t = np.polyfit(z[in_r], T[in_r], 1)[0]
    slope_ct = np.polyfit(z[in_r], ct[in_r], 1)[0]
    slope_sa = np.polyfit(z[in_r], sa[in_r], 1)[0]
    pm = P[in_r].mean()
    alpha, beta = gsw.alpha(sa[in_r].mean(), ct[in_r].mean(), pm), gsw.beta(sa[in_r].mean(), ct[in_r].mean(), pm)
    n2_fit = 9.81 * (-alpha * slope_ct + beta * slope_sa)  # z is depth (positive down)
    res = {"measured S": profile_stratification(P, T, S=sp, lat=lat, lon=lon, window=2.0),
           "S = 35 PSU (default)": profile_stratification(P, T, S=None, lat=lat, lon=lon, window=2.0)}
    fig, axs = plt.subplots(1, 3, figsize=(12, 5.5), sharey=True)
    axs[0].plot(T, P, "k", lw=0.6, label="SBT1")
    axs[0].plot(ct, P, "C1", lw=0.6, label="CT")
    axs[0].set(xlabel="°C", ylabel="pressure [dbar]", title=f"{CAST}")
    axs[0].legend(fontsize=8)
    for (lab, (tp, n2, dtdz)), c in zip(res.items(), ["C0", "C3"]):
        k = (tp >= P_RANGE[0]) & (tp <= P_RANGE[1])
        axs[1].plot(dtdz[k], tp[k], ".-", color=c, ms=3, lw=0.6,
                    label=f"{lab}: median {np.nanmedian(dtdz[k]):.3f}")
        axs[2].semilogx(np.where(n2[k] > 0, n2[k], np.nan), tp[k], ".-", color=c, ms=3, lw=0.6,
                        label=f"{lab}: median {np.nanmedian(n2[k]):.1e}")
    axs[1].axvline(slope_t, color="k", ls="--", label=f"linear fit, 150–250 dbar: {slope_t:.3f}")
    axs[2].axvline(n2_fit, color="k", ls="--", label=f"linear fit (T and S): {n2_fit:.1e}")
    axs[2].axvline(-9.81 * alpha * slope_ct, color="k", ls=":", label=f"linear fit, T only: {-9.81 * alpha * slope_ct:.1e}")
    axs[1].set(xlabel="dT/dz [K/m, z = depth]", title="sorted 2 dbar dT/dz")
    axs[2].set(xlabel="N² [s⁻²]", title="sorted 2 dbar N²")
    for a in axs[1:]:
        a.legend(fontsize=7, loc="lower left")
    axs[0].set_ylim(P_RANGE[1], P_RANGE[0])
    fig.suptitle("Thorpe sorting (2 dbar) in a staircase: with the measured (noisy, unpumped) S, sorted dT/dz is biased "
                 "low and N² high against the linear fit;\nwith the S = 35 default, dT/dz is close but N² is the "
                 "temperature-only value (salt compensation ignored)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "2_thorpe_sorting_SPC_033.png", dpi=150)
    plt.close(fig)


def fig_fp07_cal(config, out):
    base = common.run_dir_of(config)
    patched = base / "patch" / "vmp5500" / f"{CAST}.P"
    prof = xr.open_dataset(next((base / "convert" / "vmp5500").glob(f"profiles_*/{CAST}_prof001.nc")))
    tmp = Path(tempfile.mkdtemp())
    try:
        nc = tmp / f"{CAST}.nc"
        subprocess.run([shutil.which("rsi-tpw") or "rsi-tpw", "nc", str(patched), "-o", str(nc)], check=True,
                       capture_output=True)
        raw = xr.open_dataset(nc, group="L1_converted")
        traw = pd.Series(raw["TEMP"].isel(N_TEMP_SENSORS=0).values, index=raw["TIME"].values)
        traw = traw.resample("1s").mean()
        raw.close()
    finally:
        shutil.rmtree(tmp)
    tp = pd.to_datetime(prof["t_slow"].values, unit="s") if np.issubdtype(prof["t_slow"].dtype, np.number) \
        else pd.to_datetime(prof["t_slow"].values)
    sbt = pd.Series(prof["SBT1"].values, index=tp).resample("1s").mean()
    pres = pd.Series(prof["P"].values, index=tp).resample("1s").mean()
    tcal = pd.Series(prof["T1"].values, index=tp).resample("1s").mean()
    df = pd.concat({"P": pres, "SBT1": sbt, "T1_cal": tcal, "T1_header": traw}, axis=1, sort=True).dropna()
    fig, axs = plt.subplots(1, 2, figsize=(10, 5.5))
    for col, c in [("SBT1", "k"), ("T1_cal", "C0"), ("T1_header", "C3")]:
        axs[0].plot(df[col], df["P"], color=c, lw=0.8, label=col)
    axs[0].invert_yaxis()
    axs[0].set(xlabel="°C", ylabel="pressure [dbar]", title=f"{CAST} T1, 1 s means")
    axs[0].legend(fontsize=8)
    for col, c in [("T1_cal", "C0"), ("T1_header", "C3")]:
        d = df[col] - df["SBT1"]
        axs[1].plot(d, df["P"], color=c, lw=0.8, label=f"{col} − SBT1 (median {d.median():+.2f} °C)")
    axs[1].invert_yaxis()
    axs[1].axvline(0, color="k", lw=0.6)
    axs[1].set(xlabel="°C", title="difference from SBT1")
    axs[1].legend(fontsize=8)
    fig.suptitle("FP07 T1 with the header (factory nominal) coefficients vs in-situ calibration against SBT1",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "3_fp07_header_vs_calibrated.png", dpi=150)
    plt.close(fig)
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    fig_epsilon_ratio(config, config_hash, args.out)
    fig_thorpe(config, args.out)
    fig_fp07_cal(config, args.out)
    print(f"wrote figures to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
