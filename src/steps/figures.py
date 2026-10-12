#!/usr/bin/env python3
"""Step figures: first-look figures of this run.

Until the export step exists, figures read the perturb output of the convert
step (binned and combined NetCDF) and the cast table. These are values before
this pipeline's own QC (noise floor test, probe exclusions, MLE refits), and
every figure says so. Once products exist, figures should read only them.

Reads:  <run_dir>/cast_log/{casts_<instrument>.csv, track.csv}
        <run_dir>/convert/<instrument>/{diss,chi}_binned_NN, combo_NN
Writes: <run_dir>/figures/
          cruise_map.png
          process_station_profiles.png
          sections_<instrument>.png
          probe_agreement.png
          captions.md, step_metadata.json
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm, Normalize  # noqa: E402

STEP = "figures"
PRE_QC = "perturb output before this pipeline's QC"


def epoch(values) -> np.ndarray:
    v = np.asarray(values)
    if np.issubdtype(v.dtype, np.datetime64):
        return v.astype("datetime64[ns]").astype("int64") / 1e9
    return v.astype(float)


class RunData:
    """Binned and combined perturb output for one instrument, profiles labelled by file."""

    def __init__(self, run_dir: Path, name: str):
        root = run_dir / "convert" / name
        self.name = name
        self.diss = xr.open_dataset(common.single_dir(root, "diss_binned") / "binned.nc")
        self.chi = xr.open_dataset(common.single_dir(root, "chi_binned") / "binned.nc")
        self.combo = xr.open_dataset(common.single_dir(root, "combo") / "combo.nc")
        table = common.profile_table(common.single_dir(root, "diss"))
        self.casts = pd.read_csv(run_dir / "cast_log" / f"casts_{name}.csv")
        # perturb names profiles by file stem (data_0132_prof001.nc); match on stems
        self.casts["stem"] = self.casts["file"].map(lambda f: Path(f).stem)
        for ds in (self.diss, self.chi, self.combo):
            t = epoch(ds["stime"].values)
            files = []
            for ti in t:
                d = (table["stime"] - ti).abs()
                files.append(table.loc[d.idxmin(), "file"] if d.min() <= 2.0 else "")
            ds.coords["file"] = ("profile", files)
            ds.coords["t0"] = ("profile", t)


def caption_footer(fig, prov: dict) -> None:
    ps.footer(fig, f"{common.provenance_string(prov)}; {PRE_QC}")


def cruise_map(track: pd.DataFrame, runs: dict, path: Path, prov: dict) -> str:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(track["lon"], track["lat"], color=ps.MUTED, lw=0.6, zorder=1, label="ship track")
    for name, run in runs.items():
        c = run.casts[run.casts["excluded"].isna()]
        ax.scatter(c["lon"], c["lat"], s=28, color=ps.INSTRUMENT_COLOR[name], zorder=3,
                   edgecolor=ps.SURFACE, linewidth=1.0, label=f"{name.upper()} casts ({len(c)})")
    ps_cfg = runs[next(iter(runs))].process_station
    ax.scatter([ps_cfg["center_lon"]], [ps_cfg["center_lat"]], s=260, facecolor="none",
               edgecolor=ps.TEXT, lw=1.0, zorder=4)
    ax.annotate("48 h process station", (ps_cfg["center_lon"], ps_cfg["center_lat"]),
                xytext=(12, 12), textcoords="offset points", fontsize=8, color=ps.TEXT)
    lat0 = np.nanmean(track["lat"])
    ax.set_aspect(1 / np.cos(np.deg2rad(lat0)))
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.legend(loc="lower left")
    ax.set_title("FKt260806 SPICE: VMP casts on the ship track", loc="left")
    caption_footer(fig, prov)
    fig.savefig(path)
    plt.close(fig)
    return ("Ship track (Sealog 5 min snapshots) with VMP250 and VMP5500 cast start "
            "positions; excluded casts omitted. Circle: 48 h process station.")


def station_groups(runs: dict) -> list[tuple[str, RunData, list[str]]]:
    groups = []
    v250 = runs.get("vmp250")
    if v250 is not None:
        st = v250.casts[(v250.casts["station"] == "process_station") & v250.casts["excluded"].isna()]
        groups.append(("VMP250 free fall", v250, st.loc[~st["towyo"], "stem"].tolist()))
        groups.append(("VMP250 tow-yo", v250, st.loc[st["towyo"], "stem"].tolist()))
    v55 = runs.get("vmp5500")
    if v55 is not None:
        st = v55.casts[(v55.casts["station"] == "process_station") & v55.casts["excluded"].isna()]
        groups.append(("VMP5500", v55, st["stem"].tolist()))
    return groups


def process_station(runs: dict, path: Path, prov: dict) -> str:
    panels = [("combo", "CT", "Θ (°C)", False), ("combo", "SA", r"$S_A$ (g kg$^{-1}$)", False),
              ("diss", "epsilonMean", r"$\varepsilon$ (W kg$^{-1}$)", True),
              ("chi", "chiMean", r"$\chi$ (K$^2$ s$^{-1}$)", True)]
    fig, axes = plt.subplots(1, 4, figsize=(11, 6.5), sharey=True)
    counts = {}
    for label, run, files in station_groups(runs):
        color = ps.GROUP_COLOR[label]
        counts[label] = 0
        for ax, (src, var, xlabel, log) in zip(axes, panels):
            ds = getattr(run, src)
            for i in np.flatnonzero(np.isin(ds["file"].values, files)):
                prof = ds[var].isel(profile=i).to_series().dropna()
                if log:
                    prof = prof[prof > 0]
                ax.plot(prof.values, prof.index.values, color=color, lw=0.7, alpha=0.75)
                if src == "diss":
                    counts[label] += 1
    for ax, (_, var, xlabel, log) in zip(axes, panels):
        if log:
            ax.set_xscale("log")
        else:
            # Robust limits: a single bad surface bin (e.g. conductivity cell
            # breaking the surface) must not squash the axis.
            vals = np.concatenate([l.get_xdata() for l in ax.get_lines()])
            lo, hi = np.nanpercentile(vals, [0.5, 99.5])
            pad = 0.05 * (hi - lo)
            ax.set_xlim(lo - pad, hi + pad)
        ax.set_xlabel(xlabel)
    axes[0].invert_yaxis()
    axes[0].set_ylabel("depth (m)")
    handles = [plt.Line2D([], [], color=ps.GROUP_COLOR[k], lw=2, label=f"{k} ({n} profiles)")
               for k, n in counts.items()]
    axes[0].legend(handles=handles, loc="lower left", fontsize=7)
    fig.suptitle("48 h process station (11.626 N, 50.577 W): individual profiles", x=0.01,
                 ha="left")
    fig.tight_layout()
    caption_footer(fig, prov)
    fig.savefig(path)
    plt.close(fig)
    return ("Process station profiles of conservative temperature, absolute salinity, "
            "shear epsilon (geometric mean of probes) and FP07 chi, by group: VMP250 "
            "free fall, VMP250 tow-yo (ship under way), VMP5500. 1 m bins; epsilon and "
            "chi are 16 s windows, so each profile has values every few metres.")


def sections(run: RunData, path: Path, prov: dict) -> str:
    excluded = set(run.casts.loc[run.casts["excluded"].notna(), "stem"])
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)
    for ax, ds, var, cmap, label in [
            (axes[0], run.diss, "epsilonMean", ps.SEQ_EPSILON, r"log$_{10}$ $\varepsilon$ (W kg$^{-1}$)"),
            (axes[1], run.chi, "chiMean", ps.SEQ_CHI, r"log$_{10}$ $\chi$ (K$^2$ s$^{-1}$)")]:
        keep = ~np.isin(ds["file"].values, list(excluded))
        order = np.argsort(ds["t0"].values[keep])
        sub = ds[var].isel(profile=np.flatnonzero(keep)[order])
        v = sub.values
        ok = np.isfinite(v) & (v > 0)
        jj, ii = np.nonzero(ok.T)          # profile index, bin index
        vals = np.log10(v[ii, jj])
        lo, hi = np.percentile(vals, [2, 98])
        sc = ax.scatter(jj, ds["bin"].values[ii], c=vals, s=5, marker="s", cmap=cmap,
                        norm=Normalize(lo, hi), linewidths=0)
        fig.colorbar(sc, ax=ax, label=label, pad=0.01)
        ax.invert_yaxis()
        ax.set_ylabel("depth (m)")
        ax.grid(False)
        files = sub["file"].values
        starts = [k for k in range(len(files)) if k == 0 or files[k] != files[k - 1]]
        for k in starts:
            ax.axvline(k - 0.5, color=ps.GRID, lw=0.5, zorder=0)
    days = pd.to_datetime(sub["t0"].values, unit="s", utc=True)
    ticks = [k for k in range(len(days)) if k == 0 or days[k].date() != days[k - 1].date()]
    axes[1].set_xticks(ticks[::2])
    axes[1].set_xticklabels([days[k].strftime("%m-%d") for k in ticks[::2]], rotation=0)
    axes[1].set_xlabel("profile (ordered by start time; ticks mark UTC dates; gray lines separate files)")
    axes[0].set_title(f"{run.name.upper()}: shear epsilon and FP07 chi, all profiles", loc="left")
    fig.tight_layout()
    caption_footer(fig, prov)
    fig.savefig(path)
    plt.close(fig)
    return (f"{run.name.upper()} epsilon (top) and chi (bottom) for every profile in time "
            "order, excluded casts omitted; each square is one 16 s window in its 1 m bin. "
            "Color limits are the 2nd to 98th percentiles.")


def probe_agreement(runs: dict, path: Path, prov: dict) -> str:
    fig, axes = plt.subplots(2, len(runs), figsize=(4.2 * len(runs), 8), squeeze=False)
    for col, (name, run) in enumerate(runs.items()):
        for row, (ds, a, b, cmap, label) in enumerate([
                (run.diss, "e_1", "e_2", ps.SEQ_EPSILON, r"$\varepsilon$"),
                (run.chi, "chi_1", "chi_2", ps.SEQ_CHI, r"$\chi$")]):
            x, y = ds[a].values.ravel(), ds[b].values.ravel()
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
            lx, ly = np.log10(x[ok]), np.log10(y[ok])
            lo, hi = np.percentile(np.r_[lx, ly], [0.5, 99.5])
            ax = axes[row, col]
            h = ax.hist2d(lx, ly, bins=70, range=[[lo, hi], [lo, hi]], cmap=cmap, cmin=1,
                          norm=LogNorm())
            for off, style in [(0, "--"), (np.log10(2), ":"), (-np.log10(2), ":")]:
                ax.plot([lo, hi], [lo + off, hi + off], color=ps.TEXT_2, lw=0.8, ls=style)
            med = 10 ** np.median(ly - lx)
            ax.set_title(f"{name.upper()} {label}: probe 2 / probe 1 median {med:.2f}", loc="left")
            ax.set_xlabel(f"log$_{{10}}$ {a}")
            ax.set_ylabel(f"log$_{{10}}$ {b}")
            ax.set_aspect("equal")
            fig.colorbar(h[3], ax=ax, label="windows", shrink=0.75)
    fig.tight_layout()
    caption_footer(fig, prov)
    fig.savefig(path)
    plt.close(fig)
    return ("Agreement between the two shear probes (top) and the two FP07 thermistors "
            "(bottom) per instrument, all windows. Dashed: 1:1; dotted: factor of 2. Excluded "
            "probes (e.g. VMP5500 sh1 on SPC_060-061) are not yet removed.")


def run(ctx: dict) -> None:
    warnings.filterwarnings("ignore", message="All-NaN slice encountered")
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    out.mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    ps.apply()

    runs = {}
    for name, _ in common.instruments(config):
        runs[name] = RunData(ctx["run_dir"], name)
        runs[name].process_station = config["cast_log"]["process_station"]
    track = pd.read_csv(ctx["run_dir"] / "cast_log" / "track.csv")

    captions = {"cruise_map.png": cruise_map(track, runs, out / "cruise_map.png", prov),
                "process_station_profiles.png": process_station(
                    runs, out / "process_station_profiles.png", prov)}
    for name, r in runs.items():
        captions[f"sections_{name}.png"] = sections(r, out / f"sections_{name}.png", prov)
    captions["probe_agreement.png"] = probe_agreement(runs, out / "probe_agreement.png", prov)

    lines = [f"# Figures: run `{config['run']['name']}`", "",
             f"Provenance: {common.provenance_string(prov)}.", "",
             f"All figures show {PRE_QC}.", ""]
    for fname, cap in captions.items():
        lines += [f"## {fname}", "", f"![{fname}]({fname})", "", cap, ""]
    (out / "captions.md").write_text("\n".join(lines))
    common.write_step_metadata(out, STEP, ctx, figures=list(captions))
    print(f"  wrote {len(captions)} figures to {out}")


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
