#!/usr/bin/env python3
"""Step segments: per-window QC flags for the dissipation windows (CLAUDE.md step 2).

Every perturb dissipation window (16 s, stepped 8 s; epsilon and chi share the
grid) gets QC flags. Flags are always computed and reported. Whether later
steps drop flagged windows is decided by `segments.enabled` and recorded as
`applied` in the outputs.

Window i covers fast samples [i * step, i * step + diss_length) of its profile
(epsilon.anchor: top; verified against perturb's P_mean and speed).

Reads:  <run_dir>/convert/<instrument>/{diss,profiles}_NN/*_prof*.nc,
        <run_dir>/cast_log/casts_<instrument>.csv
Writes: <run_dir>/segments/
          segments_<instrument>.csv     one row per window, flag bits and `keep`
          figures/segments_<instrument>.png
          segments_report.json          windows removed by each criterion
          step_metadata.json

Flag bits (`flags` column; `keep` = no exclusion bit set):
    1  excluded_cast     cast excluded in the config
    2  near_surface      P_mean < drop_top_m
    4  bottom_approach   P_mean > profile max pressure - drop_bottom_m
    8  speed_range       speed outside [min_fall_speed, max_fall_speed]
   16  unsteady_speed    within-window speed std / mean > speed_cv_max (acceleration;
                         a steady fall faster or slower than terminal is not flagged)
   32  vibration         accelerometer rms > vibration_factor x profile median
   64  towyo             tow-yo profile (information only, not an exclusion)
Probe exclusions from the config are separate columns (exclude_sh1, ...).
"""

from __future__ import annotations

import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "segments"
BITS = {"excluded_cast": 1, "near_surface": 2, "bottom_approach": 4, "speed_range": 8,
        "unsteady_speed": 16, "vibration": 32, "towyo": 64}
EXCLUDING = ["excluded_cast", "near_surface", "bottom_approach", "speed_range",
             "unsteady_speed", "vibration"]
PROBES = ["sh1", "sh2", "T1", "T2"]


def read_var(ds, name) -> np.ndarray:
    v = ds[name][...]
    return np.ma.filled(v.astype(float), np.nan) if np.ma.isMaskedArray(v) else np.asarray(v, float)


def profile_windows(diss_file: Path, prof_file: Path, seg: dict) -> pd.DataFrame:
    with netCDF4.Dataset(diss_file) as d:
        length, overlap = int(d.diss_length), int(d.overlap)
        fs = float(d.fs_fast)
        win = pd.DataFrame({"P_mean": read_var(d, "P_mean"), "speed": read_var(d, "speed"),
                            "epsilon": read_var(d, "epsilonMean"),
                            "e_1": read_var(d, "e_1"), "e_2": read_var(d, "e_2")})
    with netCDF4.Dataset(prof_file) as p:
        ax, ay = read_var(p, "Ax"), read_var(p, "Ay")
        speed_fast = read_var(p, "speed_fast")
        p_max = float(np.nanmax(read_var(p, "P")))
    sos = butter(4, seg["vibration_highpass_hz"], "highpass", fs=fs, output="sos")
    ax, ay = sosfiltfilt(sos, np.nan_to_num(ax)), sosfiltfilt(sos, np.nan_to_num(ay))
    step = length - overlap
    starts = np.arange(len(win)) * step
    win["vibration_rms"] = [np.sqrt(np.mean(ax[s:s + length] ** 2 + ay[s:s + length] ** 2))
                            for s in starts]
    win["speed_cv"] = [np.nanstd(speed_fast[s:s + length]) / np.nanmean(speed_fast[s:s + length])
                       for s in starts]
    win["window"] = np.arange(len(win))
    win["P_max_profile"] = p_max
    return win


def text(value) -> str:
    """Cast-table cell as text; empty cells read back as NaN."""
    return "" if pd.isna(value) else str(value).strip()


def flag(win: pd.DataFrame, seg: dict, cast: pd.Series) -> pd.DataFrame:
    deep = win["P_mean"] > seg["terminal_speed_below_m"]
    terminal = win.loc[deep, "speed"].median() if deep.any() else win["speed"].median()
    win["terminal_speed"] = terminal
    win["speed_ratio"] = win["speed"] / terminal
    vib_med = win.loc[win["P_mean"] >= seg["drop_top_m"], "vibration_rms"].median()
    win["vibration_ratio"] = win["vibration_rms"] / vib_med

    tests = {
        "excluded_cast": pd.Series(text(cast.get("excluded")) != "", index=win.index),
        "near_surface": win["P_mean"] < seg["drop_top_m"],
        "bottom_approach": win["P_mean"] > win["P_max_profile"] - seg["drop_bottom_m"],
        "speed_range": (win["speed"] < seg["min_fall_speed_m_s"]) |
                       (win["speed"] > seg["max_fall_speed_m_s"]),
        "unsteady_speed": win["speed_cv"] > seg["speed_cv_max"],
        "vibration": win["vibration_ratio"] > seg["vibration_factor"],
        "towyo": pd.Series(text(cast.get("towyo")).lower() == "true", index=win.index),
    }
    win["flags"] = sum(t.astype(int) * BITS[k] for k, t in tests.items())
    excl_mask = sum(BITS[k] for k in EXCLUDING)
    win["keep"] = (win["flags"] & excl_mask) == 0
    excluded_probes = text(cast.get("excluded_probes")).split(",")
    for probe in PROBES:
        win[f"exclude_{probe}"] = probe in excluded_probes
    return win


def figure(df: pd.DataFrame, name: str, seg: dict, path: Path, foot: str) -> None:
    ps.apply()
    fig, axes = plt.subplots(1, 3, figsize=(11, 6), sharey=True)
    kept, dropped = df[df["keep"]], df[~df["keep"]]
    for ax, col, xlabel, log in [(axes[0], "speed_cv", "within-window speed std / mean", True),
                                 (axes[1], "vibration_ratio", "vibration rms / profile median", True),
                                 (axes[2], "epsilon", r"$\varepsilon$ (W kg$^{-1}$)", True)]:
        ax.scatter(dropped[col], dropped["P_mean"], s=4, color=ps.ORANGE, linewidths=0,
                   label=f"flagged ({len(dropped)})")
        ax.scatter(kept[col], kept["P_mean"], s=4, color=ps.BLUE, linewidths=0,
                   label=f"kept ({len(kept)})")
        if log:
            ax.set_xscale("log")
        ax.set_xlabel(xlabel)
    axes[0].axvline(seg["speed_cv_max"], color=ps.TEXT_2, lw=0.8, ls="--")
    axes[1].axvline(seg["vibration_factor"], color=ps.TEXT_2, lw=0.8, ls="--")
    for ax in axes:
        ax.axhline(seg["drop_top_m"], color=ps.TEXT_2, lw=0.8, ls=":")
    axes[0].invert_yaxis()
    axes[0].set_ylabel("window mean pressure (dbar)")
    axes[2].legend(loc="lower right", markerscale=3)
    fig.suptitle(f"{name.upper()}: segment QC flags per 16 s window (dashed: thresholds; "
                 f"dotted: drop_top_m)", x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    seg = config["segments"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    report = {"applied": bool(seg["enabled"]), "thresholds": seg, "instruments": {}}

    for name, _ in common.instruments(config):
        root = ctx["run_dir"] / "convert" / name
        diss_dir, prof_dir = common.single_dir(root, "diss"), common.single_dir(root, "profiles")
        casts = pd.read_csv(ctx["run_dir"] / "cast_log" / f"casts_{name}.csv")
        casts["stem"] = casts["file"].map(lambda f: Path(f).stem)
        casts = casts.set_index("stem")
        frames = []
        for diss_file in sorted(diss_dir.glob("*_prof*.nc")):
            stem = diss_file.name.split("_prof")[0]
            win = profile_windows(diss_file, prof_dir / diss_file.name, seg)
            win = flag(win, seg, casts.loc[stem])
            win.insert(0, "profile_file", diss_file.name)
            win.insert(0, "file", casts.loc[stem, "file"])
            frames.append(win)
        df = pd.concat(frames, ignore_index=True)
        df["applied"] = bool(seg["enabled"])
        df.to_csv(out / f"segments_{name}.csv", index=False, float_format="%.6g")

        # Windows removed by each criterion on its own, and in sequence (in
        # the order listed) so the counts add up to the total removed.
        alone = {k: int(((df["flags"] & BITS[k]) > 0).sum()) for k in BITS}
        remaining, sequential = np.ones(len(df), bool), {}
        for k in EXCLUDING:
            hit = remaining & ((df["flags"] & BITS[k]) > 0).to_numpy()
            sequential[k] = int(hit.sum())
            remaining &= ~hit
        report["instruments"][name] = {
            "windows": len(df), "profiles": int(df["profile_file"].nunique()),
            "kept": int(df["keep"].sum()), "removed": int((~df["keep"]).sum()),
            "removed_fraction": round(float((~df["keep"]).mean()), 4),
            "flagged_by_criterion": alone, "removed_sequentially": sequential,
            "probe_exclusions_windows": {p: int(df[f"exclude_{p}"].sum()) for p in PROBES},
            "terminal_speed_median_m_s": round(float(df.groupby("profile_file")
                                                     ["terminal_speed"].first().median()), 3),
        }
        figure(df, name, seg, out / "figures" / f"segments_{name}.png",
               f"{common.provenance_string(prov)}; applied={seg['enabled']}")
        r = report["instruments"][name]
        print(f"  {name}: {r['windows']} windows, {r['removed']} flagged for removal "
              f"({r['removed_fraction']:.1%}); sequential {sequential}; applied={seg['enabled']}")

    common.write_json(out / "segments_report.json", report)
    common.write_step_metadata(out, STEP, ctx, applied=bool(seg["enabled"]))


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
