#!/usr/bin/env python3
"""Compare VMP250 and VMP5500 epsilon and chi in the upper ocean, where both sample.

Two comparisons (config `instrument_comparison`):
  * station: every usable profile of each instrument at one cast_log station
    (the process station), mean profiles with bootstrap 95% intervals;
  * pairs: casts outside that station matched in time and space. VMP250 and
    VMP5500 profiles within max_hours and max_km of each other are linked, and
    each connected set of linked profiles is one pair group. Within a group the
    two instruments' depth-bin means are compared (scatter and log10 ratio).

Averaging: kept windows only (segment_keep and shear_keep / chi_keep), using
epsilon_shear_bounded and chi_bounded as the averages do. Each profile gives an
arithmetic mean per depth bin; profiles are then averaged arithmetically with
equal weight, and intervals come from resampling profiles.

Reads:  outputs/<run>/products/{segments,casts}_<instrument>.csv/.nc (run =
        products.recommended_run unless --run is given)
Writes: outputs/comparisons/instruments/{compare_instruments.png,
        station_profiles.csv, pair_bins.csv, pair_groups.csv, comparison.json}

Usage:
    python scripts/compare_instruments.py --config config/config.yaml [--run NAME]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

INSTRUMENTS = ("vmp250", "vmp5500")
MIN_GROUPS_CI = 5            # bootstrap over pair groups only with at least this many groups
LABEL = {"vmp250": "VMP250", "vmp5500": "VMP5500"}
QUANTITIES = (("epsilon", "epsilon_shear_bounded", "shear_keep", r"$\epsilon_{shear}$ (W kg$^{-1}$)"),
              ("chi", "chi_bounded", "chi_keep", r"$\chi$ (K$^2$ s$^{-1}$)"))
FLOOR = {"epsilon": "epsilon_floor", "chi": "chi_floor"}   # per-window noise floors, drawn for reference


def load(run_dir: Path, inst: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    prod = run_dir / "products"
    casts = pd.read_csv(prod / f"casts_{inst}.csv", parse_dates=["start_utc"])
    casts = casts[casts["excluded"].isna()]
    with xr.open_dataset(prod / f"segments_{inst}.nc") as d:
        seg = d[["profile_file", "depth", "segment_keep"]
                + [c for _, v, k, _ in QUANTITIES for c in (v, k)] + list(FLOOR.values())].to_dataframe()
    seg = seg[seg["profile_file"].isin(casts["profile_file"]) & (seg["segment_keep"] == 1)]
    return casts, seg


def profile_bins(seg: pd.DataFrame, edges: np.ndarray) -> pd.DataFrame:
    """Arithmetic mean of each quantity per profile and depth bin (kept windows)."""
    seg = seg.assign(bin=pd.cut(seg["depth"], edges, labels=(edges[:-1] + edges[1:]) / 2))
    seg = seg.dropna(subset=["bin"])
    out = []
    for q, var, keep, _ in QUANTITIES:
        s = seg[(seg[keep] == 1) & np.isfinite(seg[var])]
        out.append(s.groupby(["profile_file", "bin"], observed=True)[var].mean().rename(q))
        out.append(s.groupby(["profile_file", "bin"], observed=True)[FLOOR[q]].median().rename(f"{q}_floor"))
    return pd.concat(out, axis=1).reset_index().astype({"bin": float})


def mean_ci(table: pd.DataFrame, q: str, min_prof: int, rng, n_boot: int) -> pd.DataFrame:
    """Mean over profiles per bin with a bootstrap 95% interval (resampling profiles)."""
    rows = []
    for b, g in table.dropna(subset=[q]).groupby("bin"):
        x = g[q].to_numpy()
        if len(x) < min_prof:
            continue
        boot = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
        rows.append({"bin": b, "n_profiles": len(x), "mean": x.mean(),
                     "lo": np.percentile(boot, 2.5), "hi": np.percentile(boot, 97.5)})
    return pd.DataFrame(rows, columns=["bin", "n_profiles", "mean", "lo", "hi"])


def pair_groups(casts: dict, station: str, max_hours: float, max_km: float) -> pd.DataFrame:
    """Connected sets of VMP250 and VMP5500 profiles within max_hours and max_km (outside the station)."""
    a = casts["vmp250"][casts["vmp250"]["station"] != station].reset_index(drop=True)
    b = casts["vmp5500"][casts["vmp5500"]["station"] != station].reset_index(drop=True)
    nodes = [("vmp250", f) for f in a["profile_file"]] + [("vmp5500", f) for f in b["profile_file"]]
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    linked = set()
    for i, r in a.iterrows():
        dt = (b["start_utc"] - r["start_utc"]).abs().dt.total_seconds() / 3600
        dkm = np.hypot((b["lat"] - r["lat"]) * 111.2, (b["lon"] - r["lon"]) * 111.2 * np.cos(np.radians(r["lat"])))
        for j in np.flatnonzero((dt <= max_hours) & (dkm <= max_km)):
            parent[find(i)] = find(len(a) + j)
            linked |= {i, len(a) + j}
    rows = [{"instrument": nodes[i][0], "profile_file": nodes[i][1], "root": find(i)} for i in sorted(linked)]
    df = pd.DataFrame(rows, columns=["instrument", "profile_file", "root"])
    df["group"] = df["root"].rank(method="dense").astype(int) if len(df) else []
    return df.drop(columns="root")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--run", help="run whose products are compared (default products.recommended_run)")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run = args.run or config["products"]["recommended_run"]
    rcfg, rhash = common.apply_sensitivity(config, config_hash, run) if run != config["run"]["name"] \
        else (config, config_hash)
    run_dir = common.run_dir_of(rcfg)
    cc = config["instrument_comparison"]
    uc = config["uncertainty"]
    rng = np.random.default_rng(uc["random_seed"])
    z0, z1 = cc["depth_range_dbar"]
    edges = np.arange(z0, z1 + cc["depth_bin_m"] / 2, cc["depth_bin_m"])
    out = REPO / config["paths"]["output_root"] / "comparisons" / "instruments"
    out.mkdir(parents=True, exist_ok=True)
    meta = common.provenance(config_hash)
    foot = common.provenance_string(meta) + f"; products of run {run}"
    ps.apply()

    casts, bins = {}, {}
    for inst in INSTRUMENTS:
        casts[inst], seg = load(run_dir, inst)
        bins[inst] = profile_bins(seg, edges)
    summary = {"provenance": foot, "run": run, "run_config_hash": rhash, "settings": cc, "station": {}, "pairs": {}}

    # Station: all profiles of each instrument at the station.
    station = cc["station"]
    st_rows = []
    for inst in INSTRUMENTS:
        prof = casts[inst].loc[casts[inst]["station"] == station, "profile_file"]
        t = bins[inst][bins[inst]["profile_file"].isin(prof)]
        summary["station"][inst] = {"n_profiles": int(t["profile_file"].nunique())}
        for q, *_ in QUANTITIES:
            m = mean_ci(t, q, cc["min_profiles"], rng, uc["bootstrap_samples"])
            fl = t.groupby("bin")[f"{q}_floor"].median().rename("floor_median")
            st_rows.append(m.join(fl, on="bin").assign(instrument=inst, quantity=q))
    st = pd.concat(st_rows, ignore_index=True)
    st.to_csv(out / "station_profiles.csv", index=False)
    for q, *_ in QUANTITIES:
        w = st[st["quantity"] == q].pivot(index="bin", columns="instrument", values="mean").dropna()
        r = np.log10(w["vmp5500"] / w["vmp250"])
        summary["station"][f"{q}_log10_ratio_5500_over_250"] = {
            "n_bins": int(len(r)), "median": round(float(r.median()), 2) if len(r) else None,
            "ratio_of_depth_means": round(float(w["vmp5500"].mean() / w["vmp250"].mean()), 2) if len(r) else None}

    # Pairs: matched casts outside the station, one mean per instrument, group and bin.
    pair_rows = []
    for key, pc in (("main", cc["pairing"]), ("alt", cc["pairing"]["alt"])):
        groups = pair_groups(casts, station, pc["max_hours"], pc["max_km"])
        rows = []
        for gid, g in groups.groupby("group"):
            per = {}
            for inst in INSTRUMENTS:
                t = bins[inst][bins[inst]["profile_file"].isin(g.loc[g["instrument"] == inst, "profile_file"])]
                per[inst] = t.groupby("bin").agg(**{f"{q}": (q, "mean") for q, *_ in QUANTITIES},
                                                 n=("profile_file", "nunique"))
            j = per["vmp250"].join(per["vmp5500"], lsuffix="_250", rsuffix="_5500", how="inner")
            rows.append(j.reset_index().assign(group=gid))
        pb = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        s = summary["pairs"][key] = {
            "max_hours": pc["max_hours"], "max_km": pc["max_km"], "n_groups": int(groups["group"].nunique()),
            "n_profiles": {i: int((groups["instrument"] == i).sum()) for i in INSTRUMENTS}}
        for q, *_ in QUANTITIES:
            if pb.empty:
                continue
            r = np.log10(pb[f"{q}_5500"] / pb[f"{q}_250"]).dropna()
            # Interval on the median log ratio: resample pair groups, not bins.
            gids = pb["group"].unique()
            boot = [np.nanmedian(np.concatenate([np.log10(pb.loc[pb["group"] == g, f"{q}_5500"]
                                                          / pb.loc[pb["group"] == g, f"{q}_250"]).to_numpy()
                                                 for g in rng.choice(gids, len(gids))]))
                    for _ in range(uc["bootstrap_samples"])]
            ci = ([round(float(np.percentile(boot, 2.5)), 2), round(float(np.percentile(boot, 97.5)), 2)]
                  if len(gids) >= MIN_GROUPS_CI else None)
            s[f"{q}_log10_ratio_5500_over_250"] = {
                "n_bins": int(len(r)), "median": round(float(r.median()), 2), "ci95_groups": ci,
                "spearman_r": round(float(pb[[f"{q}_250", f"{q}_5500"]].corr("spearman").iloc[0, 1]), 2)}
        if key == "main":
            groups.to_csv(out / "pair_groups.csv", index=False)
            pb.to_csv(out / "pair_bins.csv", index=False)
            pair_rows = pb

    # Figure: station mean profiles (top), matched pairs scatter (bottom).
    fig, axes = plt.subplots(2, 2, figsize=(10, 10))
    for k, (q, _, _, xlabel) in enumerate(QUANTITIES):
        ax = axes[0, k]
        for inst in INSTRUMENTS:
            m = st[(st["instrument"] == inst) & (st["quantity"] == q)]
            c = ps.INSTRUMENT_COLOR[inst]
            ax.fill_betweenx(m["bin"], m["lo"], m["hi"], color=c, alpha=0.25, lw=0)
            ax.plot(m["mean"], m["bin"], color=c, lw=1.6,
                    label=f"{LABEL[inst]} ({summary['station'][inst]['n_profiles']} profiles)")
            ax.plot(m["floor_median"], m["bin"], color=c, lw=0.9, ls=":")
        ax.plot([], [], color=ps.MUTED, lw=0.9, ls=":", label="median noise floor")
        ax.set_xscale("log")
        ax.set_ylim(z1, z0)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("depth (m)")
        rs = summary["station"][f"{q}_log10_ratio_5500_over_250"]
        ax.set_title(f"{station.replace('_', ' ')}: mean over profiles, 95% bootstrap\n"
                     f"median log10(VMP5500/VMP250) per bin = {rs['median']:+.2f}", fontsize=9)
        ax.legend(fontsize=8, loc="lower right")

        ax = axes[1, k]
        sp = summary["pairs"]["main"]
        if len(pair_rows):
            x, y = pair_rows[f"{q}_250"], pair_rows[f"{q}_5500"]
            sc = ax.scatter(x, y, c=pair_rows["bin"], cmap=ps.SEQ_EPSILON if q == "epsilon" else ps.SEQ_CHI,
                            s=16, vmin=z0, vmax=z1, edgecolor="none")
            lim = [np.nanmin([x.min(), y.min()]) / 2, np.nanmax([x.max(), y.max()]) * 2]
            ax.plot(lim, lim, color=ps.MUTED, lw=0.8, ls="--")
            ax.set_xlim(lim)
            ax.set_ylim(lim)
            fig.colorbar(sc, ax=ax, label="depth (m)", shrink=0.8)
            rr = sp[f"{q}_log10_ratio_5500_over_250"]
            ax.set_title(f"matched casts (≤{sp['max_hours']:g} h, ≤{sp['max_km']:g} km): {sp['n_groups']} groups, "
                         f"{sp['n_profiles']['vmp250']} + {sp['n_profiles']['vmp5500']} profiles\n"
                         f"median log10 ratio {rr['median']:+.2f}"
                         + (f" [{rr['ci95_groups'][0]:+.2f}, {rr['ci95_groups'][1]:+.2f}]" if rr["ci95_groups"]
                            else " (too few groups for an interval)")
                         + f", Spearman {rr['spearman_r']:.2f}", fontsize=9)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(f"VMP250 {xlabel}")
        ax.set_ylabel(f"VMP5500 {xlabel}")
    fig.suptitle(f"VMP250 vs VMP5500, {z0}–{z1} dbar, {cc['depth_bin_m']:g} m bins (kept windows)", fontsize=11)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(out / "compare_instruments.png", dpi=110)
    plt.close(fig)
    common.write_json(out / "comparison.json", summary)
    print(f"wrote {common.portable_path(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
