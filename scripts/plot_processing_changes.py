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

Reads:  outputs/<run>/patch/<instrument>/*.P, outputs/<run>/convert/<instrument>/diss_NN/,
        outputs/<run>/epsilon_shear/, outputs/<run>/cast_log/ (run = products.recommended_run
        and processing_figures.without_run)
Writes: outputs/comparisons/processing_2026-10-29/{record_locked_shear.png,
        failing_sh1.png, despike_fraction.csv, summary.json}

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
    common.write_json(out / "summary.json", {"provenance": foot, "settings": fc, "failing_casts": failing,
                                             "record_locked": r1, "failing_probe": r2})
    print(json.dumps({"failing_casts": failing, **r1, **r2}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
