#!/usr/bin/env python3
"""Diagnostic figures for the VMP5500 conductivity (SBE4 #4076) problem.

Compares VMP5500 salinity with the VMP250 and the ship CTD (SBE 911) and writes
figures, a numbers file, and a shareable HTML page built from
scripts/vmp5500_conductivity_template.html to
<run_dir>/diagnostics/vmp5500_conductivity/.

Reads the convert outputs (per-profile NetCDF), the cast tables and the ship
CTD named in the config. Reuses the hydrography step's ship CTD matching,
T-S salinity and gradient code, so the numbers match the pipeline.

Usage:
    python scripts/diagnose_vmp5500_conductivity.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import gsw
import netCDF4
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter
from scipy.signal import lfilter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src" / "steps"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from hydrography import ShipCTD, bin_profile, stratification  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

TEMPLATE = REPO / "scripts" / "vmp5500_conductivity_template.html"
SENSORS = {"vmp5500": ("SBT1", "SBC1"), "vmp250": ("JAC_T", "JAC_C")}
DEPTHS = (150, 500)             # comparison depth range (m)
DEGRADED_FROM = "SPC_044"       # first cast of the later, noisier period
SHIP_COLOR = "#3d4a52"


def read_profile(path: Path, inst: str, ct_offset_m: float = 0.0) -> dict:
    """Slow CT channels of one profile; z is the CT sensor's depth (pressure-sensor
    depth plus ct_offset_m, which is negative when the CT sits above the pressure port)."""
    T, C = SENSORS[inst]
    with netCDF4.Dataset(path) as d:
        g = lambda n: np.ma.filled(d[n][:].astype(float), np.nan)  # noqa: E731
        out = {"P": g("P"), "CT": g("CT"), "SA": g("SA"), "T": g(T), "C": g(C), "W": g("W_slow"),
               "T1": g("T1"),
               "lat": float(np.ma.filled(d["lat"][...], np.nan)),
               "lon": float(np.ma.filled(d["lon"][...], np.nan)),
               "t0": pd.Timestamp(float(d["stime"][...]), unit="s", tz="UTC")}
    lat = out["lat"] if np.isfinite(out["lat"]) else 12.0
    out["z"] = -gsw.z_from_p(out["P"], lat) + ct_offset_m
    return out


def binned(p: dict, key: str, edges: np.ndarray) -> np.ndarray:
    return bin_profile(p["z"], p[key], edges)


def highpass(x: np.ndarray, width: int = 9) -> np.ndarray:
    filled = np.nan_to_num(x, nan=np.nanmedian(x))
    return x - median_filter(filled, width)


def profile_stats(p: dict, ship: ShipCTD) -> dict | None:
    if not np.isfinite(p["lat"]) or np.nanmax(p["z"]) < 200:
        return None
    edges = np.arange(0, np.nanmax(p["z"]) + 1, 1.0)
    zc = (edges[:-1] + edges[1:]) / 2
    sa, ct = binned(p, "SA", edges), binned(p, "CT", edges)
    m = (zc > DEPTHS[0]) & (zc < DEPTHS[1]) & np.isfinite(sa)
    hp = highpass(sa)
    raw = (p["z"] > DEPTHS[0]) & (p["z"] < DEPTHS[1])
    out = {"t0": p["t0"], "noise": float(np.nanstd(hp[m])),
           "spike_fraction": float(np.mean(np.abs(hp[m]) > 0.1)),
           "speed": float(np.nanmedian(p["W"][raw])),
           # fraction of 64 Hz samples equal to the previous one (sensor update rate)
           "T_repeat": float(np.mean(np.diff(p["T"][raw]) == 0)),
           "C_repeat": float(np.mean(np.diff(p["C"][raw]) == 0))}
    match = ship.match(p["lat"], p["lon"], p["t0"])
    if match:
        sa_ship = ship.ts_salinity(match["index"], ct)
        out["offset"] = float(np.nanmedian((sa - sa_ship)[m]))
        out["ship_cast"] = match["cast"]
    return out


def spikiness_vs_lag(p: dict, lags) -> list[float]:
    """1 m salinity noise (150-500 m) with conductivity shifted by `lag` samples."""
    edges = np.arange(DEPTHS[0], DEPTHS[1] + 1, 1.0)
    out = []
    for lag in lags:
        C = np.roll(p["C"], lag)
        sl = slice(max(lag, 0) + 320, len(C) + min(lag, 0) - 1)
        sp = gsw.SP_from_C(C[sl], p["T"][sl], p["P"][sl])
        sb = bin_profile(p["z"][sl], sp, edges)
        out.append(float(np.nanstd(highpass(sb))))
    return out


def noise_split(p: dict) -> tuple[float, float]:
    """Salinity-unit contributions of T and C to the 1 m noise, 150-500 m."""
    edges = np.arange(DEPTHS[0], DEPTHS[1] + 1, 1.0)
    m = (p["z"] > DEPTHS[0]) & (p["z"] < DEPTHS[1]) & np.isfinite(p["C"]) & np.isfinite(p["T"])
    sp = gsw.SP_from_C(p["C"][m], p["T"][m], p["P"][m])
    dSdT = np.nanmedian((gsw.SP_from_C(p["C"][m], p["T"][m] + 0.01, p["P"][m]) - sp) / 0.01)
    dSdC = np.nanmedian((gsw.SP_from_C(p["C"][m] + 0.01, p["T"][m], p["P"][m]) - sp) / 0.01)
    hT = np.nanstd(highpass(bin_profile(p["z"], p["T"], edges)))
    hC = np.nanstd(highpass(bin_profile(p["z"], p["C"], edges)))
    return float(abs(dSdT) * hT), float(abs(dSdC) * hC)


def n2_against_ship(p: dict, ship: ShipCTD, scale: float, cfg: dict) -> pd.DataFrame | None:
    match = ship.match(p["lat"], p["lon"], p["t0"])
    if not match or np.nanmax(p["z"]) < 200:
        return None
    edges = np.arange(0, min(np.nanmax(p["z"]), 560) + 1, 1.0)
    zc = (edges[:-1] + edges[1:]) / 2
    ct, sa_own = binned(p, "CT", edges), binned(p, "SA", edges)
    pres = gsw.p_from_z(-zc, p["lat"])
    own = stratification(zc, ct, sa_own, pres, scale, 1.0, cfg["min_fit_fraction"])
    sa_ts = ship.ts_salinity(match["index"], ct)
    ts = stratification(zc, ct, sa_ts, pres, scale, 1.0, cfg["min_fit_fraction"])
    sa_c, ct_c, p_c = ship.profile(match["index"])
    ref = stratification(ship.z, ct_c, sa_c, p_c, scale, 1.0, cfg["min_fit_fraction"])
    rows = []
    for zv in np.arange(DEPTHS[0], 551, 10.0):
        a, b = np.argmin(np.abs(zc - zv)), np.argmin(np.abs(ship.z - zv))
        rows.append({"depth": zv, "own": own["N2"][a], "ts": ts["N2"][a], "ship": ref["N2"][b]})
    return pd.DataFrame(rows)


FS_SLOW = 64.0
SBE3_TAUS = [0.5, 1, 1.5, 2, 3, 4, 6, 8]
SBE4_DELAYS = np.arange(0, 4.01, 0.25)
SBE4_TAUS = [0, 0.5, 1, 2, 3, 4, 6, 8, 10]


def lowpass(x: np.ndarray, tau: float) -> np.ndarray:
    """First-order sensor response with time constant tau (s) at the slow rate."""
    if tau <= 0:
        return x
    a = np.exp(-1 / (FS_SLOW * tau))
    return lfilter([1 - a], [1, -a], x - x[0]) + x[0]


def delay(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 0:
        return x.copy()
    out = np.empty_like(x)
    out[:n], out[n:] = x[0], x[:-n]
    return out


def fill(x: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    out = x.copy()
    out[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), x[ok])
    return out


def response_analysis(p: dict, ship: ShipCTD, separation_m: float, ct_offset_m: float):
    """Fit the SBE3 and SBE4 responses against the nose FP07 temperature.

    The FP07 (fast, at the probe tips) is delayed by the probe-to-CT separation
    to give the true temperature at the CT sensor. The ideal conductivity there
    follows from that temperature and the ship CTD's T-S relation. Each Sea-Bird
    channel is then modelled as a pure delay plus a first-order low-pass of its
    ideal signal. Returns per-cast numbers and series for plotting, or None."""
    m = (p["P"] > 100) & (p["P"] < 500)
    if m.sum() < 5000 or not np.isfinite(p["lat"]):
        return None
    match = ship.match(p["lat"], p["lon"], p["t0"])
    if not match:
        return None
    T1, SB, C = fill(p["T1"]), fill(p["T"]), fill(p["C"])
    i0, i1 = np.flatnonzero(m)[[0, -1]]
    v = float(np.nanmedian(p["W"][m]))
    t_true = delay(T1, int(round(separation_m / v * FS_SLOW)))
    p_ct = p["P"] + ct_offset_m
    sbe3_tau = min(SBE3_TAUS, key=lambda t: np.nanstd((SB - lowpass(t_true, t))[i0:i1]))
    sa_guess = gsw.SA_from_SP(np.full_like(p_ct, 35.5), p_ct, p["lon"], p["lat"])
    ct_true = gsw.CT_from_t(sa_guess, t_true, p_ct)
    sa_ideal = ship.ts_salinity(match["index"], ct_true)
    c_ideal = fill(gsw.C_from_SP(gsw.SP_from_SA(sa_ideal, p_ct, p["lon"], p["lat"]), t_true, p_ct))
    best = None
    for d_s in SBE4_DELAYS:
        x = delay(c_ideal, int(round(d_s * FS_SLOW)))
        for tau in SBE4_TAUS:
            r = (C - lowpass(x, tau))[i0:i1]
            rms = float(np.sqrt(np.mean((r - np.median(r)) ** 2)))
            if best is None or rms < best["rms"]:
                best = {"rms": rms, "delay": float(d_s), "tau": float(tau), "bias": float(np.median(r))}
    r0 = (C - c_ideal)[i0:i1]
    c_lagged = lowpass(delay(c_ideal, int(round(best["delay"] * FS_SLOW))), best["tau"])
    # Salinity from the measured C with a temperature matched to the cell's response
    t_matched = lowpass(delay(t_true, int(round(best["delay"] * FS_SLOW))), best["tau"])
    sa_matched = gsw.SA_from_SP(gsw.SP_from_C(C, t_matched, p_ct), p_ct, p["lon"], p["lat"])
    ct_ok = gsw.CT_from_t(sa_matched, t_true, p_ct)
    edges = np.arange(DEPTHS[0], DEPTHS[1] + 1, 1.0)
    sab, ctb = bin_profile(p["z"], sa_matched, edges), bin_profile(p["z"], ct_ok, edges)
    off_matched = float(np.nanmedian(sab - ship.ts_salinity(match["index"], ctb)))
    rate = float(np.median(-np.gradient(lowpass(c_ideal, 1.0))[i0:i1] * FS_SLOW))
    return {"sbe3_tau": float(sbe3_tau), "sbe4_delay": best["delay"], "sbe4_tau": best["tau"],
            "misfit_ideal": float(np.sqrt(np.mean((r0 - np.median(r0)) ** 2))), "misfit_lagged": best["rms"],
            "bias_ideal": float(np.median(r0)), "bias_lagged": best["bias"], "dCdt": rate,
            "offset_matched": off_matched, "z": p["z"], "C": C, "c_ideal": c_ideal, "c_lagged": c_lagged,
            "t0": p["t0"]}


def save(fig, path: Path, foot: str) -> None:
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run_dir = common.run_dir_of(config)
    out = run_dir / "diagnostics" / "vmp5500_conductivity"
    out.mkdir(parents=True, exist_ok=True)
    prov = common.provenance(config_hash)
    foot = common.provenance_string(prov)
    hc = config["hydrography"]
    ship = ShipCTD(Path(config["paths"]["ship_ctd"]), hc["ship_ctd"])
    ps.apply()

    profs = {}
    for inst in SENSORS:
        d = common.single_dir(run_dir / "convert" / inst, "profiles")
        off = float(config["instruments"][inst].get("sensor_offsets_m", {}).get("ct", 0.0))
        profs[inst] = {f.name[:-3]: read_profile(f, inst, off) for f in sorted(d.glob("*_prof*.nc"))}

    # ---- per-profile statistics through the cruise
    stats = {inst: pd.DataFrame({k: v for k, v in
                                 ((name, profile_stats(p, ship)) for name, p in ps_.items()) if v}).T
             for inst, ps_ in profs.items()}
    for inst, df in stats.items():
        df["t0"] = pd.to_datetime(df["t0"], utc=True)
        for c in ("noise", "spike_fraction", "offset", "speed", "T_repeat", "C_repeat"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    v55, v250 = stats["vmp5500"], stats["vmp250"]
    early = v55[v55.index < f"{DEGRADED_FROM}_prof001"]
    late = v55[v55.index >= f"{DEGRADED_FROM}_prof001"]

    # ---- Figure 1: matched profiles at the process station
    a55, a250 = profs["vmp5500"]["SPC_033_prof001"], profs["vmp250"]["data_0133_prof001"]
    m = ship.match(a55["lat"], a55["lon"], a55["t0"])
    sa_c, ct_c, _ = ship.profile(m["index"])
    fig, axes = plt.subplots(1, 2, figsize=(9, 6.2), sharey=True)
    edges = np.arange(0, 560, 1.0)
    zc = (edges[:-1] + edges[1:]) / 2
    for ax, key, ship_val, label in [(axes[0], "CT", ct_c, "Θ (°C)"), (axes[1], "SA", sa_c, r"$S_A$ (g kg$^{-1}$)")]:
        ax.plot(ship_val, ship.z, color=SHIP_COLOR, lw=1.6, label=f"Ship CTD cast {m['cast']}")
        ax.plot(binned(a250, key, edges), zc, color=ps.BLUE, lw=1.1, label="VMP250 data_0133 (JAC CT)")
        ax.plot(binned(a55, key, edges), zc, color=ps.ORANGE, lw=0.9, label="VMP5500 SPC_033 (SBE3/SBE4)")
        ax.set_xlabel(label)
    axes[1].set_xlim(34.9, 37.4)
    axes[0].set_ylim(550, 0)
    axes[0].set_ylabel("depth (m)")
    axes[1].legend(loc="lower right", fontsize=7.5)
    fig.suptitle(f"Process station, 2026-08-20: same water, three instruments (1 m bins; ship cast "
                 f"{m['hours']:.1f} h from SPC_033)", x=0.01, ha="left")
    save(fig, out / "fig1_profiles.png", foot)

    # ---- Figure 2: T-S, early vs late VMP5500 cast
    pick = [("SPC_014_prof001", "Early cruise"), ("SPC_045_prof001", "Late cruise")]
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 5), sharey=True)
    ts_rows = []
    for ax, (name, label) in zip(axes, pick):
        p = profs["vmp5500"][name]
        mm = ship.match(p["lat"], p["lon"], p["t0"])
        sa_c, ct_c, _ = ship.profile(mm["index"])
        sel = (ship.z > 100) & (ship.z < 550)
        ax.plot(sa_c[sel], ct_c[sel], color=SHIP_COLOR, lw=1.6, label=f"Ship CTD {mm['cast']}")
        e = np.arange(100, 551, 1.0)
        sa, ct = bin_profile(p["z"], p["SA"], e), bin_profile(p["z"], p["CT"], e)
        ax.scatter(sa, ct, s=5, color=ps.ORANGE, linewidths=0, label=f"VMP5500 {name[:7]}")
        off = v55.loc[name, "offset"]
        ts_rows.append((name, off))
        ax.set_title(f"{label}: {name[:7]} ({p['t0']:%d %b}); median offset {off:+.2f} g/kg",
                     loc="left", fontsize=9)
        ax.set_xlabel(r"$S_A$ (g kg$^{-1}$)")
        ax.legend(loc="lower right", fontsize=7.5)
        ax.set_xlim(34.9, 37.4)
    axes[0].set_ylabel("Θ (°C)")
    fig.suptitle("T–S, 100–550 m: VMP5500 salinity sits salty of the ship CTD and scatters more as "
                 "the cruise goes on", x=0.01, ha="left")
    save(fig, out / "fig2_ts.png", foot)

    # ---- Figure 3: noise and offset through the cruise
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 6), sharex=True)
    for ax, col, label, log in [(axes[0], "noise", "1 m salinity noise (g kg$^{-1}$)", True),
                                (axes[1], "offset", "offset from ship CTD at same Θ (g kg$^{-1}$)", False)]:
        ax.scatter(v250["t0"], v250[col], s=14, color=ps.BLUE, linewidths=0, label="VMP250 (JAC CT)")
        ax.scatter(v55["t0"], v55[col], s=22, color=ps.ORANGE, edgecolors=ps.SURFACE, linewidths=0.8,
                   label="VMP5500 (SBE4 #4076)")
        ax.set_ylabel(label)
        if log:
            ax.set_yscale("log")
        ax.axvline(late["t0"].min(), color=ps.TEXT_2, lw=0.8, ls="--")
    axes[1].axhline(0, color=ps.TEXT_2, lw=0.8)
    axes[0].text(late["t0"].min(), axes[0].get_ylim()[1] * 0.8, f"  {DEGRADED_FROM}, 24 Aug",
                 fontsize=7.5, color=ps.TEXT_2, va="top")
    axes[0].legend(loc="lower left", fontsize=7.5)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.suptitle("Per cast, 150–500 m: VMP5500 noise and salty offset grow through the cruise",
                 x=0.01, ha="left")
    save(fig, out / "fig3_timeseries.png", foot)

    # ---- Figure 4: not a lag problem; conductivity dominates
    lags = list(range(-24, 25, 2))
    lag_sets = {"vmp5500": ["SPC_033_prof001", "SPC_039_prof001", "SPC_050_prof001"],
                "vmp250": ["data_0133_prof001", "data_0140_prof001", "data_0145_prof001"]}
    lag_curves = {inst: np.mean([spikiness_vs_lag(profs[inst][n], lags) for n in names], axis=0)
                  for inst, names in lag_sets.items()}
    split = pd.DataFrame([(n, *noise_split(p)) for n, p in profs["vmp5500"].items()
                          if np.nanmax(p["z"]) > 300], columns=["profile", "T", "C"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    ax = axes[0]
    for inst, color in (("vmp250", ps.BLUE), ("vmp5500", ps.ORANGE)):
        ax.plot(np.array(lags) / 64, lag_curves[inst], color=color, lw=1.8, marker="o", ms=3,
                label=inst.upper())
    ax.set_yscale("log")
    ax.set_xlabel("conductivity shifted relative to temperature (s)")
    ax.set_ylabel("1 m salinity noise (g kg$^{-1}$)")
    ax.set_title("Shifting C against T: VMP250 has a clear best lag; VMP5500 is flat", loc="left",
                 fontsize=9)
    ax.legend(loc="center right", fontsize=7.5)
    ax = axes[1]
    order = np.arange(len(split))
    ax.scatter(order, split["C"], s=16, color=ps.ORANGE, linewidths=0, label="from conductivity (SBE4)")
    ax.scatter(order, split["T"], s=16, color=SHIP_COLOR, linewidths=0, label="from temperature (SBE3)")
    ax.set_yscale("log")
    ax.set_xlabel("VMP5500 cast, in cruise order")
    ax.set_ylabel("salinity noise contribution (g kg$^{-1}$)")
    ax.set_title("Where VMP5500 salinity noise comes from", loc="left", fontsize=9)
    ax.legend(loc="lower right", fontsize=7.5)
    fig.suptitle("The noise is in the conductivity channel, and it is not a C-T timing mismatch",
                 x=0.01, ha="left")
    save(fig, out / "fig4_attribution.png", foot)

    # ---- Figure 5: consequence for N2
    scale = hc["gradient_smoothing_m"]
    frames = [f for f in (n2_against_ship(p, ship, scale, hc) for p in profs["vmp5500"].values())
              if f is not None]
    n2 = pd.concat(frames, ignore_index=True)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.6), sharey=True)
    lims = (-6.5, -3.5)
    for ax, col, title in [(axes[0], "own", "VMP5500 own salinity"),
                           (axes[1], "ts", "VMP5500 Θ with ship CTD T–S salinity")]:
        neg = float((n2[col] <= 0).mean())
        ok = (n2[col] > 0) & (n2["ship"] > 0)
        ax.scatter(np.log10(n2.loc[ok, "ship"]), np.log10(n2.loc[ok, col]), s=6, color=ps.ORANGE,
                   alpha=0.6, linewidths=0)
        ax.plot(lims, lims, color=ps.TEXT_2, lw=0.8, ls="--")
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_title(f"{title}: {neg:.0%} of N² ≤ 0 (not plotted)", loc="left", fontsize=9)
        ax.set_xlabel("ship CTD log$_{10}$ N² (s$^{-2}$)")
        ax.set_aspect("equal")
    axes[0].set_ylabel("VMP5500 log$_{10}$ N² (s$^{-2}$)")
    ship_neg = float((n2["ship"] <= 0).mean())
    fig.suptitle(f"Consequence: N² over {scale:g} m at 150–550 m vs the nearest ship CTD "
                 f"(ship N² ≤ 0 in {ship_neg:.0%})", x=0.01, ha="left")
    save(fig, out / "fig5_n2.png", foot)

    # ---- Figure 6: slow sensor response explains the salty offset
    offsets = config["instruments"]["vmp5500"].get("sensor_offsets_m", {})
    ct_off, ms_off = float(offsets.get("ct", 0.0)), float(offsets.get("microstructure", 0.0))
    resp = {n: r for n, r in ((n, response_analysis(p, ship, ms_off - ct_off, ct_off))
                              for n, p in profs["vmp5500"].items()) if r is not None}
    resp_df = pd.DataFrame({n: {k: v for k, v in r.items() if np.isscalar(v)} for n, r in resp.items()}).T
    for c in resp_df.columns:
        if c != "t0":
            resp_df[c] = pd.to_numeric(resp_df[c])
    broken = resp_df.index[np.abs(resp_df["bias_ideal"]) > 1.0].tolist()   # e.g. SPC_061
    rd = resp_df.drop(index=broken)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5), gridspec_kw={"width_ratios": [1, 1.2]})
    ex = resp["SPC_033_prof001"]
    sel = (ex["z"] > 150) & (ex["z"] < 300)
    ax = axes[0]
    ax.plot(ex["c_ideal"][sel], ex["z"][sel], color=SHIP_COLOR, lw=1.2, label="ideal (FP07 T + ship T–S)")
    ax.plot(ex["C"][sel], ex["z"][sel], color=ps.ORANGE, lw=0.7, label="measured SBC1")
    ax.plot(ex["c_lagged"][sel], ex["z"][sel], color=ps.AQUA, lw=1.4, ls="--",
            label=f"ideal, lagged (τ {resp_df.loc['SPC_033_prof001', 'sbe4_tau']:.0f} s)")
    ax.set_ylim(300, 150)
    ax.set_xlabel("conductivity (mS cm$^{-1}$)")
    ax.set_ylabel("CT sensor depth (m)")
    ax.set_title("SPC_033: the cell reads like a slowed version of the ideal signal", loc="left", fontsize=9)
    ax.legend(loc="lower right", fontsize=7.5)
    ax = axes[1]
    early_r = rd[rd.index < f"{DEGRADED_FROM}_prof001"]
    late_r = rd[rd.index >= f"{DEGRADED_FROM}_prof001"]
    for g, color, lab in ((early_r, ps.BLUE, "SPC_004–043"), (late_r, ps.AQUA, f"{DEGRADED_FROM}–SPC_063")):
        ax.scatter(g["dCdt"], g["bias_ideal"], s=24, color=color, edgecolors=ps.SURFACE, linewidths=0.8, label=lab)
    ax.axhline(0, color=ps.TEXT_2, lw=0.8)
    ax.set_xlabel("rate of change of ideal conductivity on descent (mS cm$^{-1}$ s$^{-1}$)")
    ax.set_ylabel("measured − ideal conductivity (mS cm$^{-1}$)")
    ax.set_title("Per cast: bias grows with how fast conductivity is changing", loc="left", fontsize=9)
    ax.legend(loc="upper left", fontsize=7.5)
    fig.suptitle("A slow conductivity response explains the salty offset", x=0.01, ha="left")
    save(fig, out / "fig6_response.png", foot)

    # ---- numbers and page
    numbers = {
        "provenance": foot, "created_utc": prov["created_utc"],
        "profiles": {"vmp5500": int(len(v55)), "vmp250": int(len(v250))},
        "noise_median": {"vmp5500": round(float(v55["noise"].median()), 4),
                         "vmp250": round(float(v250["noise"].median()), 4)},
        "noise_ratio": int(round(float(v55["noise"].median() / v250["noise"].median()))),
        "spike_fraction_median": {"vmp5500": round(float(v55["spike_fraction"].median()), 3),
                                  "vmp250": round(float(v250["spike_fraction"].median()), 3)},
        "offset_median": {"vmp5500": round(float(v55["offset"].median()), 3),
                          "vmp250": round(float(v250["offset"].median()), 4)},
        "offset_range_vmp5500": [round(float(v55["offset"].min()), 2), round(float(v55["offset"].max()), 2)],
        "early": {"casts": f"{early.index.min()[:7]}–{early.index.max()[:7]}",
                  "noise_median": round(float(early["noise"].median()), 3),
                  "offset_median": round(float(early["offset"].median()), 2)},
        "late": {"casts": f"{late.index.min()[:7]}–{late.index.max()[:7]}",
                 "noise_median": round(float(late["noise"].median()), 3),
                 "offset_median": round(float(late["offset"].median()), 2)},
        "split_median": {"T": round(float(split["T"].median()), 4), "C": round(float(split["C"].median()), 4)},
        "lag_curve_range": {k: [round(float(min(v)), 4), round(float(max(v)), 4)] for k, v in lag_curves.items()},
        "n2_nonpositive": {"own": round(float((n2["own"] <= 0).mean()), 3),
                           "ts": round(float((n2["ts"] <= 0).mean()), 3),
                           "ship": round(ship_neg, 3)},
        "gradient_scale_m": scale,
        "n2_nonpositive_pct": {k: f"{100 * v:.0f}%" for k, v in
                               {"own": float((n2["own"] <= 0).mean()), "ts": float((n2["ts"] <= 0).mean()),
                                "ship": ship_neg}.items()},
        "noise_speed_corr": round(float(np.corrcoef(v55["noise"], v55["speed"])[0, 1]), 2),
        "T_repeat_range": [round(float(v55["T_repeat"].min()), 2), round(float(v55["T_repeat"].max()), 2)],
        "C_repeat_first_last": [round(float(v55["C_repeat"].iloc[:5].median()), 2),
                                round(float(v55["C_repeat"].iloc[-5:].median()), 2)],
        "ts_cast_offsets": {n[:7]: round(float(o), 2) for n, o in ts_rows},
        "fig1_ship_hours": float(m["hours"]),
        "sbe4": {"serial": "4076", "cal_date": "2026-02-19"},
        "response": {
            "casts": int(len(rd)), "excluded": " and ".join(b[:7] for b in broken) or "none",
            "separation_m": round(ms_off - ct_off, 2),
            "sbe3_tau_median": float(rd["sbe3_tau"].median()),
            "sbe3_tau_iqr": [float(rd["sbe3_tau"].quantile(.25)), float(rd["sbe3_tau"].quantile(.75))],
            "sbe4_tau_median": float(rd["sbe4_tau"].median()),
            "sbe4_tau_iqr": [float(rd["sbe4_tau"].quantile(.25)), float(rd["sbe4_tau"].quantile(.75))],
            "sbe4_delay_median": float(rd["sbe4_delay"].median()),
            "misfit": [round(float(rd["misfit_ideal"].median()), 2), round(float(rd["misfit_lagged"].median()), 2)],
            "bias": [round(float(rd["bias_ideal"].median()), 3), round(float(rd["bias_lagged"].median()), 3)],
            "offset_matched_median": round(float(rd["offset_matched"].median()), 3),
            "early": {"dCdt": round(float(early_r["dCdt"].median()), 4), "bias": round(float(early_r["bias_ideal"].median()), 2)},
            "late": {"dCdt": round(float(late_r["dCdt"].median()), 4), "bias": round(float(late_r["bias_ideal"].median()), 2)},
            "corr_bias_rate": round(float(np.corrcoef(rd["bias_ideal"], rd["dCdt"])[0, 1]), 2),
        },
        "sbe3": {"serial": "5621", "cal_date": "2026-03-25"},
    }
    (out / "numbers.json").write_text(json.dumps(numbers, indent=2))
    html = TEMPLATE.read_text()
    for i, name in enumerate(["fig1_profiles", "fig2_ts", "fig3_timeseries", "fig4_attribution", "fig5_n2",
                              "fig6_response"], 1):
        b64 = base64.b64encode((out / f"{name}.png").read_bytes()).decode()
        html = html.replace(f"{{{{FIG{i}}}}}", f"data:image/png;base64,{b64}")
    html = html.replace("{{NUMBERS}}", json.dumps(numbers))

    def lookup(path: str):
        v = numbers
        for part in path.split("."):
            v = v[int(part)] if isinstance(v, list) else v[part]
        return v

    import re
    html = re.sub(r"\{\{n:([A-Za-z0-9_.]+)\}\}", lambda mt: str(lookup(mt.group(1))), html)
    left = re.findall(r"\{\{[^}]+\}\}", html)
    if left:
        raise RuntimeError(f"Unfilled placeholders in template: {sorted(set(left))}")
    (out / "vmp5500_conductivity.html").write_text(html)
    print(json.dumps(numbers, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
