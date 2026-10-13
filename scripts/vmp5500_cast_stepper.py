#!/usr/bin/env python3
"""Per-cast comparison figures for the VMP5500 salinity problem, and a page to step through them.

For every VMP5500 profile: conservative temperature and absolute salinity
against depth, plus the T-S diagram, compared with the nearest ship CTD cast
(within the hydrography step's match limits) and the nearest VMP250 profile
(within 15 km and 12 h, reaching at least 100 m). VMP5500 temperature and
salinity are the hydrography step's 1 m grid (salinity_source own_ts: FP07
temperature, salinity from the cast's own T-S relation). Writes one PNG per cast, casts.json and a stepper
page built from scripts/vmp5500_cast_stepper_template.html to
<run_dir>/diagnostics/vmp5500_conductivity/casts/.

Reads:  <run_dir>/hydrography/hydrography_vmp5500.nc, convert/ profiles (VMP250, positions)

Usage:
    python scripts/vmp5500_cast_stepper.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import gsw
import numpy as np
import pandas as pd
import xarray as xr
from scipy.signal import lfilter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from hydrography import ShipCTD, bin_profile  # noqa: E402
from diagnose_vmp5500_conductivity import SHIP_COLOR, highpass, read_profile  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

TEMPLATE = REPO / "scripts" / "vmp5500_cast_stepper_template.html"
VMP250_MAX_KM, VMP250_MAX_HOURS = 15.0, 12.0
VMP250_MIN_DEPTH = 100.0        # skip false starts (some files begin with a few-metre profile)
STATS_DEPTHS = (150, 500)


def km(lat1, lon1, lat2, lon2):
    return 111.0 * np.hypot(lat1 - lat2, (lon1 - lon2) * np.cos(np.deg2rad(lat1)))


def nearest_vmp250(p, v250):
    best = None
    for name, q in v250.items():
        if not np.isfinite(q["lat"]) or np.nanmax(q["z"]) < VMP250_MIN_DEPTH:
            continue
        d = km(p["lat"], p["lon"], q["lat"], q["lon"])
        h = abs((q["t0"] - p["t0"]).total_seconds()) / 3600
        if d <= VMP250_MAX_KM and h <= VMP250_MAX_HOURS and (best is None or h < best[2]):
            best = (name, d, h)
    return best


def cast_stats(zc, ct, sa, ship, match):
    m = (zc > STATS_DEPTHS[0]) & (zc < STATS_DEPTHS[1]) & np.isfinite(sa)
    out = {"noise": float(np.nanstd(highpass(sa)[m])) if m.sum() > 20 else None, "offset": None}
    if match and m.sum() > 20:
        out["offset"] = float(np.nanmedian((sa - ship.ts_salinity(match["index"], ct))[m]))
    return {k: v if v is not None and np.isfinite(v) else None for k, v in out.items()}


def figure(name, p, grid, ship, match, near250, v250, path, foot):
    zmax = min(max(np.nanmax(p["z"]), 300), 1050)
    zc, ct_r, sa_r = grid
    fig, axes = plt.subplots(1, 3, figsize=(12, 6.2), gridspec_kw={"width_ratios": [1, 1, 1.1]})
    ts_sel = lambda z: (z > 100) & (z < 550)  # noqa: E731
    lines = []
    if match:
        sa_c, ct_c, _ = ship.profile(match["index"])
        axes[0].plot(ct_c, ship.z, color=SHIP_COLOR, lw=1.6)
        axes[1].plot(sa_c, ship.z, color=SHIP_COLOR, lw=1.6)
        s = ts_sel(ship.z)
        axes[2].plot(sa_c[s], ct_c[s], color=SHIP_COLOR, lw=1.6)
        lines.append((SHIP_COLOR, f"Ship CTD {match['cast']} ({match['hours']:.1f} h, {match['km']:.1f} km)"))
    if near250:
        q = v250[near250[0]]
        qmax = np.nanmax(q["z"])
        e2 = np.arange(0, qmax + 1, 1.0)
        z2 = (e2[:-1] + e2[1:]) / 2
        ct2, sa2 = bin_profile(q["z"], q["CT"], e2), bin_profile(q["z"], q["SA"], e2)
        axes[0].plot(ct2, z2, color=ps.BLUE, lw=1.1)
        axes[1].plot(sa2, z2, color=ps.BLUE, lw=1.1)
        s = ts_sel(z2)
        axes[2].plot(sa2[s], ct2[s], color=ps.BLUE, lw=1.1)
        lines.append((ps.BLUE, f"VMP250 {near250[0][:9]} ({near250[2]:.1f} h, {near250[1]:.1f} km)"))
    # VMP5500: hydrography grid (FP07 temperature, own T-S salinity)
    axes[0].plot(ct_r, zc, color=ps.ORANGE, lw=1.0, zorder=3)
    s = ts_sel(zc)
    axes[1].plot(sa_r, zc, color=ps.ORANGE, lw=1.0, zorder=3)
    axes[2].scatter(sa_r[s], ct_r[s], s=6, color=ps.ORANGE, linewidths=0, zorder=3)
    lines.append((ps.ORANGE, f"VMP5500 {name[:7]} (FP07 T, own T–S salinity)"))
    axes[0].set_xlabel("Θ (°C)")
    axes[1].set_xlabel(r"$S_A$ (g kg$^{-1}$)")
    axes[2].set_xlabel(r"$S_A$ (g kg$^{-1}$), 100–550 m")
    axes[2].set_ylabel("Θ (°C)")
    for ax in axes[:2]:
        ax.set_ylim(zmax, 0)
    axes[0].set_ylabel("depth (m)")
    axes[1].set_xlim(34.8, 37.5)
    axes[2].set_xlim(34.8, 37.5)
    if match and zmax > 560:
        for ax in axes[:2]:
            ax.axhspan(550, zmax, color=ps.GRID, alpha=0.5, lw=0)
        axes[0].text(0.98, 558, "below ship CTD reach (550 m)",
                     transform=axes[0].get_yaxis_transform(), ha="right", va="top", fontsize=7,
                     color=ps.TEXT_2)
    handles = [plt.Line2D([], [], color=c, lw=2, label=l) for c, l in lines]
    axes[2].legend(handles=handles, loc="upper left", fontsize=7.5)
    fig.suptitle(f"{name[:7]}, {p['t0']:%d %b %H:%M} UTC, {p['lat']:.3f}°N {-p['lon']:.3f}°W",
                 x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run_dir = common.run_dir_of(config)
    out = run_dir / "diagnostics" / "vmp5500_conductivity" / "casts"
    out.mkdir(parents=True, exist_ok=True)
    prov = common.provenance(config_hash)
    foot = common.provenance_string(prov)
    ship = ShipCTD(Path(config["paths"]["ship_ctd"]), config["hydrography"]["ship_ctd"])
    ps.apply()

    off = lambda inst: float(config["instruments"][inst].get("sensor_offsets_m", {}).get("ct", 0.0))  # noqa: E731
    load = lambda inst: {f.name[:-3]: read_profile(f, inst, off(inst)) for f in  # noqa: E731
                         sorted(common.single_dir(run_dir / "convert" / inst, "profiles").glob("*_prof*.nc"))}
    v55, v250 = load("vmp5500"), load("vmp250")
    hydro = xr.open_dataset(run_dir / "hydrography" / "hydrography_vmp5500.nc")
    if hydro.attrs.get("salinity_source") != "own_ts":
        raise SystemExit(f"hydrography_vmp5500.nc has salinity_source={hydro.attrs.get('salinity_source')}, expected own_ts")
    row = {f[:-3]: i for i, f in enumerate(hydro["profile_file"].values)}
    zgrid = hydro["depth"].values
    casts55 = pd.read_csv(run_dir / "cast_log" / "casts_vmp5500.csv").set_index("file")

    entries = []
    for name, p in v55.items():
        if not np.isfinite(p["lat"]) or np.nanmax(p["z"]) < 50:
            continue
        cast = casts55.loc[f"{name.split('_prof')[0]}.P"]
        match = ship.match(p["lat"], p["lon"], p["t0"])
        near = nearest_vmp250(p, v250)
        grid = (zgrid, hydro["CT"].values[row[name]], hydro["SA_used"].values[row[name]])
        k = row[name]
        on_ship = hydro["SA_from_ship"].values[k][(zgrid > STATS_DEPTHS[0]) & (zgrid < STATS_DEPTHS[1])]
        ts_source = ("ship T–S throughout (bad conductivity)" if bool(hydro["ts_ship_only"].values[k])
                     else "own T–S (no ship check)" if not np.isfinite(hydro["ts_bad_fraction"].values[k])
                     else f"own T–S; {np.nanmean(on_ship > 0.5):.0%} of 150–500 m on ship values")
        stats_r = cast_stats(*grid, ship, match)
        png = out / f"{name}.png"
        figure(name, p, grid, ship, match, near, v250, png, foot)
        note = "" if pd.isna(cast.get("sealog_notes")) else str(cast["sealog_notes"])
        flag = " ".join(str(cast.get(k)) for k in ("excluded", "caution") if not pd.isna(cast.get(k)))
        entries.append({
            "id": name[:7], "profile": name, "time": f"{p['t0']:%Y-%m-%d %H:%M}",
            "lat": round(p["lat"], 3), "lon": round(p["lon"], 3),
            "maxDepth": round(float(np.nanmax(p["z"]))),
            "station": cast.get("station") == "process_station",
            "ship": match, "vmp250": {"profile": near[0], "km": round(near[1], 1),
                                      "hours": round(near[2], 1)} if near else None,
            "noiseR": None if stats_r["noise"] is None else round(stats_r["noise"], 3),
            "offsetR": None if stats_r["offset"] is None else round(stats_r["offset"], 3),
            "tsSource": ts_source, "notes": note, "flags": flag,
            "img": "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode(),
        })

    meta = {"provenance": foot, "created_utc": prov["created_utc"], "count": len(entries)}
    (out / "casts.json").write_text(json.dumps([{k: v for k, v in e.items() if k != "img"} for e in entries], indent=1))
    html = TEMPLATE.read_text().replace("/*__CASTS__*/null", json.dumps(entries)) \
                               .replace("/*__META__*/null", json.dumps(meta))
    (out / "vmp5500_casts.html").write_text(html)
    size = (out / "vmp5500_casts.html").stat().st_size / 1e6
    print(f"{len(entries)} casts, {sum(e['ship'] is not None for e in entries)} with ship CTD, "
          f"{sum(e['vmp250'] is not None for e in entries)} with a VMP250 cast; page {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
