#!/usr/bin/env python3
"""Figures of the 2026-10-29 processing changes: record-locked shear interference and sh1 M3461.

Figure 1, VMP5500 record-locked interference (config `processing_figures`):
  a. the shear of example_cast folded on its .p record (512 samples, 1 s), before
     and after microstructure-tpw's record-locked removal, with the same settings
     as perturb (L2 high-pass 0.5 / fft_sec);
  b. fraction of samples despiked per cast at the configured despike settings,
     before and after the removal, against the 5% ATOMIX/Zissou rejection limit;
  c. mean shear frequency spectrum below spectrum_P_min_dbar on spectrum_cast,
     with and without the removal (perturb diss output of both runs);
  d. per cast, the median change in combined shear epsilon between the runs.
Figure 2, the failing sh1 (M3461):
  a. median sh1/sh2 per epsilon_sh2 level, failing casts against the others;
  b. per cast, median sh1/sh2 in quiet and in energetic windows, with probe serials.
Panels 2a-b use the raw per-probe estimates (before probe exclusions).
Figure 3, spectra like rsi-tpw ql's epsilon panel, for the windows in spectra_examples:
  observed wavenumber spectra of both runs, Nasmyth at the fitted (refit) epsilon,
  K_max, the noise floor of each run mapped to wavenumber, the 1 Hz refit limit,
  and reference Nasmyth curves.
Figure 4, figure of merit (shear_qc refit FM) of both runs: distribution, the
  fraction above shear_qc.figure_of_merit.max per cast, and FM against epsilon.

Reads:  outputs/<run>/patch/<instrument>/*.P, outputs/<run>/convert/<instrument>/diss_NN/,
        outputs/<run>/epsilon_shear/, outputs/<run>/cast_log/ (run = products.recommended_run
        and processing_figures.without_run)
Writes: outputs/comparisons/processing_2026-10-29/{record_locked_shear.png,
        failing_sh1.png, spectra_examples.png, figure_of_merit.png, despike_fraction.csv,
        spectra_examples.csv, summary.json}

Usage:
    python scripts/plot_processing_changes.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.signal import butter, filtfilt
from odas_tpw.rsi.p_file import PFile
from odas_tpw.rsi.record_locked import remove_record_locked
from odas_tpw.scor160.despike import despike

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

DESPIKE_LIMIT = 0.05          # ATOMIX despike_shear_fraction_limit (odas_tpw.scor160.l4)


def descent(pf: PFile, fc: dict) -> np.ndarray:
    """Fast-sample mask of the steady descent below min_P_dbar."""
    fs = pf.fs_fast
    P = np.interp(pf.t_fast, np.arange(len(pf.channels["P"])) / pf.fs_slow, pf.channels["P"])
    W = filtfilt(*butter(1, 0.5 / (fs / 2)), np.gradient(P) * fs)
    return (W > fc["min_fall_speed_m_s"]) & (P > fc["min_P_dbar"])


def raw_shear(path: Path, probe: str, fc: dict, eps_cfg: dict) -> dict:
    """One probe's descent: high-passed shear before and after the record-locked removal."""
    pf = PFile(path)
    fs, spr = pf.fs_fast, pf.samples_per_record
    sel = np.flatnonzero(descent(pf, fc))
    i0, i1 = sel[0], sel[-1] + 1          # one contiguous block from the first to the last descent sample
    hp_cut = 0.5 / eps_cfg["fft_sec"]
    x = pf.channels[probe][i0:i1]
    rl = remove_record_locked(x, index0=i0, samples_per_record=spr, fs=fs, hp_cut=hp_cut)
    b, a = butter(1, hp_cut / (fs / 2), "high")
    return {"fs": fs, "spr": spr, "index0": i0, "before": filtfilt(b, a, x),
            "after": filtfilt(b, a, rl.signal), "result": rl}


def folded(x: np.ndarray, index0: int, spr: int) -> np.ndarray:
    k0 = (-index0) % spr
    n = (len(x) - k0) // spr
    return x[k0:k0 + n * spr].reshape(n, spr).mean(axis=0)


def despike_fraction(x: np.ndarray, fs: float, eps_cfg: dict) -> float:
    return despike(x, fs, eps_cfg["despike_thresh"], eps_cfg["despike_smooth"],
                   N=round(eps_cfg["despike_half_width"] * fs)).fraction


def mean_spectrum(run_dir: Path, inst: str, cast: str, fc: dict) -> tuple[np.ndarray, np.ndarray]:
    diss = common.single_dir(run_dir / "convert" / inst, "diss")
    specs, freq = [], None
    for f in sorted(diss.glob(f"{Path(cast).stem}_prof*.nc")):
        with xr.open_dataset(f) as d:
            deep = d["P_mean"].values > fc["spectrum_P_min_dbar"]
            specs.append(d["spec_shear"].values[:, :, deep])
            freq = d["F"].values[:, 0]
    return freq, np.concatenate(specs, axis=2).mean(axis=2)       # (probe, freq)


def figure_record_locked(fc, eps_cfg, inst, run_dir, run_dir_without, casts, path, foot) -> dict:
    patched = run_dir / "patch" / inst
    ex = raw_shear(patched / fc["example_cast"], fc["example_probe"], fc, eps_cfg)
    rows = []
    for f in casts["file"]:
        if not (patched / f).exists():
            continue
        for probe in ("sh1", "sh2"):
            r = raw_shear(patched / f, probe, fc, eps_cfg)
            rows.append({"file": f, "probe": probe,
                         "before": despike_fraction(r["before"], r["fs"], eps_cfg),
                         "after": despike_fraction(r["after"], r["fs"], eps_cfg)})
    frac = pd.DataFrame(rows)

    with_e = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
    without_e = pd.read_csv(run_dir_without / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
    m = with_e.merge(without_e, on=["profile_file", "window"], suffixes=("", "_without"))
    m = m[m["P_mean"] > fc["min_P_dbar"]]
    m["cast"] = m["profile_file"].str.split("_prof").str[0]
    m["dlog"] = np.log10(m["epsilon_shear"] / m["epsilon_shear_without"])
    per_cast = m.groupby("cast")["dlog"].median()

    fig, axs = plt.subplots(2, 2, figsize=(12, 8.5))
    ax = axs[0, 0]
    t_ms = np.arange(ex["spr"]) / ex["fs"] * 1e3
    ax.plot(t_ms, folded(ex["before"], ex["index0"], ex["spr"]), color=ps.ORANGE, lw=1.2, label="before removal")
    ax.plot(t_ms, folded(ex["after"], ex["index0"], ex["spr"]), color=ps.BLUE, lw=1.2, label="after removal")
    ax.set_xlabel("time within .p record (ms)")
    ax.set_ylabel(f"mean high-passed {fc['example_probe']} (raw units)")
    ax.set_title(f"a. {Path(fc['example_cast']).stem} {fc['example_probe']}: record-folded mean, "
                 f"{ex['result'].snr:.0f} s.e. at peak", loc="left")
    ax.legend(frameon=False)

    ax = axs[0, 1]
    stems = [Path(f).stem for f in casts["file"] if (patched / f).exists()]
    x = np.arange(len(stems))
    for probe, off, mk in (("sh1", -0.17, "o"), ("sh2", 0.17, "s")):
        p = frac[frac["probe"] == probe].set_index(frac[frac["probe"] == probe]["file"].map(lambda f: Path(f).stem))
        ax.scatter(x + off, 100 * p.loc[stems, "before"], color=ps.ORANGE, marker=mk, s=14,
                   label=f"{probe} before")
        ax.scatter(x + off, 100 * p.loc[stems, "after"], color=ps.BLUE, marker=mk, s=14, label=f"{probe} after")
    ax.axhline(100 * DESPIKE_LIMIT, color=ps.TEXT_2, ls="--", lw=1, label="ATOMIX / Zissou rejection limit")
    ax.set_xticks(x, stems, rotation=90, fontsize=6)
    ax.set_ylabel(f"despiked (%), half-width {eps_cfg['despike_half_width']} s")
    ax.set_title("b. Fraction despiked per cast", loc="left")
    ax.legend(frameon=False, fontsize=7, ncol=2)

    ax = axs[1, 0]
    f_w, s_w = mean_spectrum(run_dir, inst, fc["spectrum_cast"], fc)
    f_o, s_o = mean_spectrum(run_dir_without, inst, fc["spectrum_cast"], fc)
    for i, probe in enumerate(("sh1", "sh2")):
        ls = "-" if i == 0 else ":"
        ax.loglog(f_o, s_o[i], color=ps.ORANGE, ls=ls, lw=1.1, label=f"{probe} without removal")
        ax.loglog(f_w, s_w[i], color=ps.BLUE, ls=ls, lw=1.1, label=f"{probe} with removal")
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel(r"shear spectrum (s$^{-2}$ Hz$^{-1}$)")
    ax.set_title(f"c. {Path(fc['spectrum_cast']).stem}: mean spectrum below {fc['spectrum_P_min_dbar']} dbar",
                 loc="left")
    ax.legend(frameon=False, fontsize=7)

    ax = axs[1, 1]
    station = set(Path(f).stem for f in casts.loc[casts["station"].astype(str) == "process_station", "file"])
    xs = np.arange(len(per_cast))
    ax.bar(xs, per_cast.values, color=[ps.ORANGE if c in station else ps.BLUE for c in per_cast.index])
    ax.axhline(per_cast.median(), color=ps.TEXT_2, ls="--", lw=1)
    ax.text(0.99, 0.03, f"dashed: median of casts {per_cast.median():+.2f} dex", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, color=ps.TEXT_2)
    ax.set_xticks(xs, per_cast.index, rotation=90, fontsize=6)
    ax.set_ylabel(r"median $\log_{10}(\epsilon_{with}/\epsilon_{without})$")
    ax.set_title("d. Change in shear epsilon per cast (orange: process station)", loc="left")

    fig.suptitle("VMP5500: shear interference locked to the .p record, and its removal", x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)
    return {"despike_fraction": frac, "median_dlog_epsilon_windows": round(float(m["dlog"].median()), 3),
            "example_snr": round(float(ex["result"].snr), 1)}


def figure_failing_probe(fc, inst, run_dir, casts, failing, path, foot) -> dict:
    e = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
    e = e[(e["P_mean"] > fc["min_P_dbar"]) & (e["epsilon_sh1"] > 0) & (e["epsilon_sh2"] > 0)].copy()
    e["cast"] = e["profile_file"].str.split("_prof").str[0]
    e["lr"] = np.log10(e["epsilon_sh1"] / e["epsilon_sh2"])
    e["level"] = pd.cut(np.log10(e["epsilon_sh2"]), fc["level_bins_log10"])
    e["failing"] = e["cast"].isin(failing)
    centres = [(iv.left + iv.right) / 2 for iv in e["level"].cat.categories]

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1, 2]})
    ax = axs[0]
    for flag, color, label in ((False, ps.BLUE, "other casts"), (True, ps.ORANGE, "SPC_041–044, 059–061")):
        g = e[e["failing"] == flag].groupby("level", observed=False)["lr"]
        med, lo, hi = g.median(), g.quantile(0.25), g.quantile(0.75)
        ax.fill_between(centres, lo, hi, color=color, alpha=0.2, lw=0)
        ax.plot(centres, med, color=color, marker="o", label=label)
    ax.axhline(0, color=ps.TEXT_2, lw=0.8)
    ax.set_xlabel(r"$\log_{10}\epsilon_{sh2}$ (W kg$^{-1}$), bin centre")
    ax.set_ylabel(r"$\log_{10}(\epsilon_{sh1}/\epsilon_{sh2})$, median and IQR")
    ax.set_title("a. Probe ratio against turbulence level", loc="left")
    ax.legend(frameon=False)

    ax = axs[1]
    quiet = e[np.log10(e["epsilon_sh2"]) < -10].groupby("cast")["lr"].median()
    loud = e[np.log10(e["epsilon_sh2"]) > -9].groupby("cast")["lr"].median()
    order = sorted(set(quiet.index) | set(loud.index))
    xs = np.arange(len(order))
    ax.plot(xs, quiet.reindex(order), color=ps.BLUE, marker="o", ms=4, lw=1,
            label=r"quiet: $\epsilon_{sh2}$ < 1e-10")
    ax.plot(xs, loud.reindex(order), color=ps.ORANGE, marker="s", ms=4, lw=1,
            label=r"energetic: $\epsilon_{sh2}$ > 1e-9")
    for i, c in enumerate(order):
        if c in failing:
            ax.axvspan(i - 0.5, i + 0.5, color=ps.MUTED, alpha=0.25, lw=0)
    sn = casts.assign(stem=casts["file"].map(lambda f: Path(f).stem)).set_index("stem")["raw_sh1_sn"]
    prev = None
    for i, c in enumerate(order):
        if sn.get(c) != prev:
            ax.axvline(i - 0.5, color=ps.TEXT_2, lw=0.8, ls=":")
            ax.text(i - 0.4, 0.99, f"sh1 {sn.get(c)}", transform=ax.get_xaxis_transform(), fontsize=7,
                    color=ps.TEXT_2, va="top")
            prev = sn.get(c)
    ax.axhline(0, color=ps.TEXT_2, lw=0.8)
    ax.set_xticks(xs, order, rotation=90, fontsize=6)
    ax.set_ylabel(r"median $\log_{10}(\epsilon_{sh1}/\epsilon_{sh2})$")
    ax.set_title("b. Per cast; shaded: sh1 now excluded", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower left")

    fig.suptitle("VMP5500 sh1 (M3461): reads high in quiet water and low in strong turbulence on the shaded casts",
                 x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)
    return {"quiet_median_failing": round(float(quiet.reindex(failing).median()), 2),
            "quiet_median_other": round(float(quiet.drop(failing, errors="ignore").median()), 2),
            "energetic_median_failing": round(float(loud.reindex(failing).median()), 2),
            "energetic_median_other": round(float(loud.drop(failing, errors="ignore").median()), 2)}


def window_spectra(run_dir: Path, inst: str, cast: str, P: float) -> dict:
    """Observed wavenumber spectra of the window nearest P, from the run's perturb diss output."""
    diss = common.single_dir(run_dir / "convert" / inst, "diss")
    best = None
    for f in sorted(diss.glob(f"{Path(cast).stem}_prof*.nc")):
        with xr.open_dataset(f) as d:
            w = int(np.nanargmin(np.abs(d["P_mean"].values - P)))
            dist = abs(float(d["P_mean"].values[w]) - P)
            if best is None or dist < best["dist"]:
                best = {"dist": dist, "profile_file": f.name, "window": w, "K": d["K"].values[:, w],
                        "spec": d["spec_shear"].values[:, :, w], "probes": [str(p) for p in d["probe"].values]}
    return best


def figure_spectra(fc, inst, run_dir, run_dir_without, refit, path, foot) -> list:
    from odas_tpw.scor160.nasmyth import nasmyth
    tabs = {r: pd.read_csv(d / "epsilon_shear" / f"epsilon_shear_{inst}.csv").set_index(["profile_file", "window"])
            for r, d in (("with", run_dir), ("without", run_dir_without))}
    noise = {r: pd.read_csv(d / "epsilon_shear" / f"noise_spectrum_{inst}.csv")
             for r, d in (("with", run_dir), ("without", run_dir_without))}
    style = {"without": (ps.ORANGE, "without removal"), "with": (ps.BLUE, "with removal")}
    ex = fc["spectra_examples"]
    fig, axs = plt.subplots(len(ex), 2, figsize=(11, 3.9 * len(ex)), squeeze=False)
    rows = []
    for i, e in enumerate(ex):
        spec = {"with": window_spectra(run_dir, inst, e["cast"], e["P_dbar"]),
                "without": window_spectra(run_dir_without, inst, e["cast"], e["P_dbar"])}
        key = (spec["with"]["profile_file"], spec["with"]["window"])
        row = tabs["with"].loc[key]
        W, nu = float(row["speed"]), float(row["nu"])
        for j, probe in enumerate(("sh1", "sh2")):
            ax = axs[i, j]
            K = spec["with"]["K"]
            for ref in fc["nasmyth_reference_log10"]:
                nas = nasmyth(10.0 ** ref, nu, K)
                ax.loglog(K, nas, color=ps.GRID, lw=0.8, zorder=0)
                k_lab = 3.0                   # label each reference curve at 3 cpm, inside the axes
                y_lab = nasmyth(10.0 ** ref, nu, np.array([k_lab]))[0]
                if 1e-10 < y_lab < 1e-2:
                    ax.text(k_lab, y_lab, f"{ref}", fontsize=6, color=ps.MUTED, va="bottom", clip_on=True)
            info = {}
            for r in ("without", "with"):
                color, label = style[r]
                s = spec[r]
                k = s["K"]
                obs = s["spec"][s["probes"].index(probe)]
                t = tabs[r].loc[key]
                eps, kmax, fm = float(t[f"epsilon_{probe}"]), float(t[f"K_max_{probe}"]), float(t[f"FM_{probe}"])
                info[r] = (eps, fm)
                ax.loglog(k, obs, color=color, lw=1.1,
                          label=f"{label}: ε {eps:.1e}, FM {fm:.2f}")
                if np.isfinite(eps):
                    ax.loglog(k, nasmyth(eps, nu, k), color=color, lw=0.9, ls="--")
                if np.isfinite(kmax):
                    ki = np.argmin(np.abs(k - kmax))
                    ax.plot(kmax, obs[ki], marker="v", color=color, ms=7, zorder=5)
                nf = noise[r]
                ax.loglog(nf["frequency_hz"] / W, nf[f"noise_{probe}"] * W, color=color, lw=0.8, ls=":")
            ax.axvline(refit["f_min_hz"] / W, color=ps.TEXT_2, lw=0.8, ls="-.")
            ax.set_xlim(0.5, 300)
            ax.set_ylim(1e-10, 1e-2)
            ax.set_xlabel("wavenumber (cpm)")
            ax.set_ylabel("Φ(k) (s$^{-2}$ cpm$^{-1}$)")
            ax.set_title(f"{key[0][:-3]} {probe}, P {row['P_mean']:.0f} dbar, W {W:.2f} m/s\n{e['note']}",
                         loc="left", fontsize=9)
            ax.legend(frameon=False, fontsize=7, loc="upper right")
            rows.append({"profile_file": key[0], "window": key[1], "P_dbar": round(float(row["P_mean"]), 1),
                         "probe": probe, "epsilon_without": info["without"][0], "epsilon_with": info["with"][0],
                         "FM_without": round(info["without"][1], 3), "FM_with": round(info["with"][1], 3)})
    fig.suptitle("VMP5500 shear spectra, as in rsi-tpw ql: solid observed, dashed Nasmyth at the fitted ε, "
                 "▼ K_max, dotted noise floor,\ndash-dot the 1 Hz lower fit limit, gray Nasmyth for log10 ε "
                 "as labelled. Orange without, blue with the record-locked removal.", x=0.01, ha="left",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)
    return rows


def figure_fm(fc, inst, run_dir, run_dir_without, fm_max, path, foot) -> dict:
    a = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
    b = pd.read_csv(run_dir_without / "epsilon_shear" / f"epsilon_shear_{inst}.csv")
    m = a.merge(b, on=["profile_file", "window"], suffixes=("", "_without"))
    m = m[m["P_mean"] > fc["min_P_dbar"]].copy()
    m["cast"] = m["profile_file"].str.split("_prof").str[0]
    long = pd.concat([pd.DataFrame({"cast": m["cast"], "probe": p, "FM": m[f"FM_{p}{s}"],
                                    "eps": m[f"epsilon_{p}{s}"], "run": r})
                      for p in ("sh1", "sh2") for s, r in (("", "with"), ("_without", "without"))])
    long = long[np.isfinite(long["FM"]) & (long["eps"] > 0)]
    color = {"without": ps.ORANGE, "with": ps.BLUE}

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1, 1.6, 1]})
    ax = axs[0]
    bins = np.linspace(0, 4, 81)
    summary = {}
    for r in ("without", "with"):
        x = long.loc[long["run"] == r, "FM"]
        above = float((x > fm_max).mean())
        summary[r] = {"median": round(float(x.median()), 3), "fraction_above_max": round(above, 3)}
        ax.hist(x.clip(upper=bins[-1]), bins=bins, histtype="step", color=color[r], lw=1.4,
                label=f"{r} removal: median {x.median():.2f}, {100 * above:.0f}% > {fm_max}")
    ax.axvline(fm_max, color=ps.TEXT_2, ls="--", lw=1)
    ax.set_xlabel("figure of merit (Lueck 2022), per probe and window")
    ax.set_ylabel("windows")
    ax.set_title("a. FM distribution, both probes", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper right")

    ax = axs[1]
    per = long.assign(high=long["FM"] > fm_max).groupby(["cast", "run"])["high"].mean().unstack()
    xs = np.arange(len(per))
    ax.plot(xs, 100 * per["without"], color=ps.ORANGE, marker="o", ms=4, lw=1, label="without removal")
    ax.plot(xs, 100 * per["with"], color=ps.BLUE, marker="o", ms=4, lw=1, label="with removal")
    ax.set_xticks(xs, per.index, rotation=90, fontsize=6)
    ax.set_ylabel(f"windows with FM > {fm_max} (%)")
    ax.set_title("b. Per cast, both probes", loc="left")
    ax.legend(frameon=False, fontsize=8)

    ax = axs[2]
    long["level"] = pd.cut(np.log10(long["eps"]), fc["fm_level_bins_log10"])
    centres = [(iv.left + iv.right) / 2 for iv in long["level"].cat.categories]
    for r in ("without", "with"):
        g = long[long["run"] == r].groupby("level", observed=False)["FM"]
        ax.fill_between(centres, g.quantile(0.25), g.quantile(0.75), color=color[r], alpha=0.2, lw=0)
        ax.plot(centres, g.median(), color=color[r], marker="o", label=f"{r} removal")
    ax.axhline(fm_max, color=ps.TEXT_2, ls="--", lw=1)
    ax.set_xlabel(r"$\log_{10}\epsilon$ of that probe (W kg$^{-1}$), bin centre")
    ax.set_ylabel("FM, median and IQR")
    ax.set_title("c. FM against turbulence level", loc="left")
    ax.legend(frameon=False, fontsize=8)

    fig.suptitle(f"VMP5500 figure of merit with and without the record-locked removal (below {fc['min_P_dbar']} "
                 "dbar; FM over the 1 Hz–K_max refit range)", x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    fc = config["processing_figures"]
    run = config["products"]["recommended_run"]
    rcfg, _ = common.apply_sensitivity(config, config_hash, run)
    ocfg, _ = common.apply_sensitivity(config, config_hash, fc["without_run"])
    run_dir, run_dir_without = common.run_dir_of(rcfg), common.run_dir_of(ocfg)
    inst = fc["instrument"]
    eps_cfg = rcfg["perturb"]["epsilon"]
    casts = pd.read_csv(run_dir / "cast_log" / f"casts_{inst}.csv")
    casts = casts[casts["excluded"].isna() | (casts["excluded"].astype(str) == "")]
    excl = config["instruments"][inst].get("exclude_probes") or {}
    failing = sorted(Path(f).stem for f, probes in excl.items() if fc["failing_probe"] in probes
                     and (casts.loc[casts["file"] == f, "raw_sh1_sn"] == fc["failing_probe_serial"]).any())

    out = common.run_dir_of(config).parent / "comparisons" / "processing_2026-10-29"
    out.mkdir(parents=True, exist_ok=True)
    foot = (common.provenance_string(common.provenance(config_hash))
            + f"; runs {run} and {fc['without_run']}")
    ps.apply()
    r1 = figure_record_locked(fc, eps_cfg, inst, run_dir, run_dir_without, casts, out / "record_locked_shear.png", foot)
    r1.pop("despike_fraction").round(4).to_csv(out / "despike_fraction.csv", index=False)
    r2 = figure_failing_probe(fc, inst, run_dir, casts, failing, out / "failing_sh1.png", foot)
    r3 = figure_spectra(fc, inst, run_dir, run_dir_without, rcfg["shear_qc"]["refit"], out / "spectra_examples.png",
                        foot)
    pd.DataFrame(r3).to_csv(out / "spectra_examples.csv", index=False)
    r4 = figure_fm(fc, inst, run_dir, run_dir_without, rcfg["shear_qc"]["figure_of_merit"]["max"],
                   out / "figure_of_merit.png", foot)
    common.write_json(out / "summary.json", {"provenance": foot, "settings": fc, "failing_casts": failing,
                                             "record_locked": r1, "failing_probe": r2, "figure_of_merit": r4})
    print(json.dumps({"failing_casts": failing, **r1, **r2, "figure_of_merit": r4}, indent=1))
    print(pd.DataFrame(r3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
