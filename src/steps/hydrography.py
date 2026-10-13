#!/usr/bin/env python3
"""Step hydrography: background stratification for every profile (CLAUDE.md step 3).

TEOS-10 on a 1 m grid per profile: CT, SA, sigma0, alpha, beta, N2, T_z, S_z,
density ratio R_rho = alpha T_z / (beta S_z) and Turner angle, with gradients
from linear fits over hydrography.gradient_smoothing_m. Gradients use z
positive upward (T_z > 0 when warmer above), so salt fingers have
T_z > 0, S_z > 0, R_rho > 1 and Turner angle between 45 and 90 degrees.

Sensor offsets (instruments.<name>.sensor_offsets_m, sensor depth minus
pressure-sensor depth): CT-derived values are placed at the CT sensor's depth
and window values are evaluated at the microstructure probes' depth.

Salinity source per instrument (instruments.<name>.salinity_source):
  own          the profiler's CT-sensor salinity (VMP250: agrees with the ship CTD)
  ship_ctd_ts  SA from the nearest ship CTD cast's T-S relation, evaluated at
               the profiler's own CT. Used for the VMP5500, whose conductivity
               is too noisy for gradients; undefined below the ship CTD's
               deepest (coldest) data, about 550 m, where values are NaN and
               flagged.
  own_ts       SA from the profile's own T-S relation, evaluated at the FP07
               temperature on the microstructure probes' depth grid. The
               relation is fitted to salinity from the Sea-Bird conductivity
               with the co-located SBE3 temperature matched to the cell
               (instruments.<name>.ct_match), as the median SA in CT bins of
               hydrography.own_ts.bin_degC smoothed over smooth_bins bins.
               The CT pair samples water disturbed by the vehicle (decisions.md
               2026-10-13), so measured salinity is too noisy for gradients;
               the T-S relation averages that out while the FP07 keeps the
               native vertical resolution. S_z, R_rho and Turner then follow
               the T-S slope and are not independent of T_z.
               Ship fallback (hydrography.own_ts.ship_fallback): where a ship
               CTD cast is matched, each T-S bin is compared with the ship's
               relation (same bins and smoothing); bins differing by more than
               max_diff_g_kg take the ship value and the merged relation is
               smoothed again. If more than cast_fail_fraction of the bins
               fail, the whole profile uses the ship relation and is NaN
               outside its temperature range. SA_from_ship records the
               fraction of each 1 m bin on ship values.
With a T-S derived salinity (ship_ctd_ts, own_ts), windows with T_z <= 0 are
flagged ts_salinity_invalid: temperature inversions are mostly intrusions whose
salinity compensates in density, which a T-S relation cannot represent, so N2,
R_rho and Turner there are not reliable (decisions.md 2026-10-13).
perturb's window-scale N2 and dTdz are not used (wrong for the VMP5500).

Reads:  <run_dir>/convert/<instrument>/profiles_NN/*.nc (P, CT, SA, lat, lon;
          own_ts also the Sea-Bird T and C, the FP07 and t_slow),
        <run_dir>/segments/segments_<instrument>.csv (window centres),
        paths.ship_ctd
Writes: <run_dir>/hydrography/
          hydrography_<instrument>.nc   profile x depth grid
          windows_<instrument>.csv      values at each dissipation window centre
          figures/*.png, hydrography_report.json, step_metadata.json

Each run validates against the ship CTD: N2, T_z, S_z and R_rho of every
profile with a matched cast, at the same scale, over 150-550 m.
"""

from __future__ import annotations

import sys
from pathlib import Path

import gsw
import netCDF4
import numpy as np
import pandas as pd
import xarray as xr
from scipy.signal import lfilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

STEP = "hydrography"
VALID_DEPTHS = (150, 550)


# --------------------------------------------------------------------------
# Gradients
# --------------------------------------------------------------------------

def moving_slope(z: np.ndarray, x: np.ndarray, half: int, min_n: int) -> np.ndarray:
    """Least-squares slope dx/dz over a centred window of 2*half+1 grid points."""
    ok = np.isfinite(x) & np.isfinite(z)
    k = np.ones(2 * half + 1)
    zz, xx = np.where(ok, z, 0.0), np.where(ok, x, 0.0)
    conv = lambda a: np.convolve(a, k, mode="same")  # noqa: E731
    n, sz, sx = conv(ok.astype(float)), conv(zz), conv(xx)
    szz, szx = conv(zz * zz), conv(zz * xx)
    den = n * szz - sz * sz
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = (n * szx - sz * sx) / den
    slope[(n < min_n) | (den <= 0)] = np.nan
    return slope


def stratification(z, ct, sa, p, scale, bin_m, min_frac):
    """N2, T_z, S_z (z positive up), alpha, beta, R_rho, Turner on the grid z (depth, m)."""
    half = int(round(scale / bin_m / 2))
    min_n = int(np.ceil(min_frac * (2 * half + 1)))
    dct_dd = moving_slope(z, ct, half, min_n)          # per metre of depth (down)
    dsa_dd = moving_slope(z, sa, half, min_n)
    t_z, s_z = -dct_dd, -dsa_dd                        # z positive up
    alpha, beta = gsw.alpha(sa, ct, p), gsw.beta(sa, ct, p)
    g = 9.81
    at, bs = alpha * t_z, beta * s_z
    with np.errstate(invalid="ignore", divide="ignore"):
        r_rho = at / bs
    return {"N2": g * (at - bs), "T_z": t_z, "S_z": s_z, "alpha": alpha, "beta": beta,
            # Ruddick (1983): Tu = atan2(aT_z + bS_z, aT_z - bS_z), z up; fingers 45-90 deg,
            # diffusive -90 to -45, |Tu| > 90 statically unstable; R_rho = -tan(Tu + 45 deg)
            "R_rho": r_rho, "Turner": np.degrees(np.arctan2(at + bs, at - bs))}


def bin_profile(depth, x, edges):
    idx = np.digitize(depth, edges) - 1
    ok = np.isfinite(x) & (idx >= 0) & (idx < len(edges) - 1)
    s = np.bincount(idx[ok], weights=x[ok], minlength=len(edges) - 1)
    n = np.bincount(idx[ok], minlength=len(edges) - 1)
    with np.errstate(invalid="ignore"):
        return np.where(n > 0, s / np.maximum(n, 1), np.nan)


# --------------------------------------------------------------------------
# Salinity from the profile's own T-S relation (salinity_source own_ts)
# --------------------------------------------------------------------------

def fill(x: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    out = x.copy()
    if ok.sum() < 2:
        return out
    out[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), x[ok])
    return out


def match_to_cell(t: np.ndarray, fs: float, delay_s: float, tau_s: float) -> np.ndarray:
    """Temperature delayed by delay_s and passed through a first-order lag tau_s."""
    n = int(round(delay_s * fs))
    out = np.r_[np.full(n, t[0]), t[:len(t) - n]] if n > 0 else t.copy()
    if tau_s > 0:
        a = np.exp(-1.0 / (fs * tau_s))
        out = lfilter([1 - a], [1, -a], out - out[0]) + out[0]
    return out


def ts_relation(ct: np.ndarray, sa: np.ndarray, bin_degc: float, smooth_bins: int):
    """(CT, SA) nodes: median SA in CT bins, then a running mean over smooth_bins bins."""
    ok = np.isfinite(ct) & np.isfinite(sa)
    tab = pd.DataFrame({"b": np.floor(ct[ok] / bin_degc), "ct": ct[ok], "sa": sa[ok]}) \
        .groupby("b").median().rolling(smooth_bins, center=True, min_periods=1).mean()
    return tab["ct"].to_numpy(), tab["sa"].to_numpy()


def own_ts_profile(d, lat: float, lon: float, ct_off: float, ms_off: float,
                   inst: dict, cfg: dict) -> dict:
    """The profile's own T-S relation (CT, SA nodes) and the FP07 inputs to evaluate it."""
    g = lambda n: np.ma.filled(d[n][:].astype(float), np.nan)  # noqa: E731
    t_s = g("t_slow")
    fs = 1.0 / float(np.nanmedian(np.diff(t_s)))
    P = g("P")
    t_sbe, c_sbe, t_fp = fill(g(cfg["sbe_temperature"])), fill(g(cfg["sbe_conductivity"])), fill(g(cfg["fp07"]))
    m = inst["ct_match"]
    p_ct, p_tip = P + ct_off, P + ms_off
    t_cell = match_to_cell(t_sbe, fs, float(m["delay_s"]), float(m["tau_s"]))
    sa_m = gsw.SA_from_SP(gsw.SP_from_C(c_sbe, t_cell, p_ct), p_ct, lon, lat)
    nodes = ts_relation(gsw.CT_from_t(sa_m, t_sbe, p_ct), sa_m, cfg["bin_degC"], cfg["smooth_bins"])
    usable = len(nodes[0]) >= 2 and bool(np.isfinite(t_fp).any())
    return {"P_tip": p_tip, "t_fp": t_fp, "nodes": nodes if usable else None,
            "sa_ref": float(np.nanmedian(sa_m)) if usable else np.nan}


def ship_fallback(nodes, ship_nodes, cfg: dict) -> dict:
    """Merge own T-S nodes with the ship's where they differ by more than max_diff_g_kg."""
    fb = cfg["ship_fallback"]
    if nodes is None:
        return {"nodes": ship_nodes, "bad_nodes": None, "failed": True, "bad_fraction": 1.0}
    ct, sa = nodes
    ship_sa = np.interp(ct, *ship_nodes, left=np.nan, right=np.nan)
    diff = sa - ship_sa
    checked = np.isfinite(diff)
    bad = checked & (np.abs(diff) > fb["max_diff_g_kg"])
    frac = float(bad.sum() / checked.sum()) if checked.any() else 0.0
    if frac > fb["cast_fail_fraction"]:
        return {"nodes": ship_nodes, "bad_nodes": None, "failed": True, "bad_fraction": frac}
    merged = pd.Series(np.where(bad, ship_sa, sa)).rolling(
        cfg["smooth_bins"], center=True, min_periods=1).mean().to_numpy()
    return {"nodes": (ct, merged), "bad_nodes": (ct, bad.astype(float)), "failed": False,
            "bad_fraction": frac}


def evaluate_ts(own: dict, nodes, bad_nodes, sa_ref: float) -> dict:
    """Native-rate FP07 CT and SA from T-S nodes, plus the fraction from ship values."""
    n = len(own["t_fp"])
    if nodes is None or len(nodes[0]) < 2:
        return {"CT": np.full(n, np.nan), "SA": np.full(n, np.nan), "from_ship": np.full(n, np.nan)}
    interp = lambda ct: np.interp(ct, *nodes, left=np.nan, right=np.nan)  # noqa: E731
    t_fp, p_tip = own["t_fp"], own["P_tip"]
    ct = gsw.CT_from_t(sa_ref, t_fp, p_tip)
    for _ in range(2):                                # SA depends weakly on CT_from_t's SA
        sa = interp(ct)
        ct = gsw.CT_from_t(np.where(np.isfinite(sa), sa, sa_ref), t_fp, p_tip)
    sa = interp(ct)
    from_ship = (np.interp(ct, *bad_nodes) if bad_nodes is not None else np.ones(n))
    return {"CT": ct, "SA": sa, "from_ship": np.where(np.isfinite(sa), from_ship, np.nan)}


# --------------------------------------------------------------------------
# Ship CTD
# --------------------------------------------------------------------------

class ShipCTD:
    def __init__(self, path: Path, cfg: dict):
        ds = xr.open_dataset(path)
        k = cfg["sensor"]
        self.time = pd.to_datetime(ds["time"].values, utc=True)
        self.lat, self.lon = ds["latitude"].values, ds["longitude"].values
        self.cast = [c.decode() if isinstance(c, bytes) else str(c) for c in ds["ctd_no"].values]
        self.z = ds["depth"].values.astype(float)
        self.SP, self.t = ds[f"salt{k}"].values, ds[f"temp{k}"].values   # (z, cast)
        self.cfg = cfg
        self._cache = {}

    def match(self, lat, lon, t0):
        if not np.isfinite(lat):
            return None
        dist = 111.0 * np.hypot(self.lat - lat, (self.lon - lon) * np.cos(np.deg2rad(lat)))
        dt = np.abs((self.time - t0).total_seconds().to_numpy()) / 3600.0
        ok = (dist <= self.cfg["match_max_km"]) & (dt <= self.cfg["match_max_hours"])
        if not ok.any():
            return None
        j = int(np.argmin(np.where(ok, dt, np.inf)))
        return {"index": j, "cast": self.cast[j], "km": round(float(dist[j]), 2),
                "hours": round(float(dt[j]), 2)}

    def profile(self, j):
        """SA, CT and pressure of cast j on its depth grid."""
        if j not in self._cache:
            lat, lon = self.lat[j], self.lon[j]
            p = gsw.p_from_z(-self.z, lat)
            sa = gsw.SA_from_SP(self.SP[:, j], p, lon, lat)
            ct = gsw.CT_from_t(sa, self.t[:, j], p)
            self._cache[j] = (sa, ct, p)
        return self._cache[j]

    def ts_salinity(self, j, ct_query):
        """SA at ct_query from cast j's T-S relation (median SA in CT bins); NaN outside it."""
        sa, ct, _ = self.profile(j)
        ok = np.isfinite(sa) & np.isfinite(ct)
        w = self.cfg["ts_bin_degC"]
        b = np.floor(ct[ok] / w)
        tab = pd.DataFrame({"b": b, "ct": ct[ok], "sa": sa[ok]}).groupby("b").median()
        return np.interp(ct_query, tab["ct"].to_numpy(), tab["sa"].to_numpy(),
                         left=np.nan, right=np.nan)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def validation_figure(val: pd.DataFrame, path: Path, scale: float, foot: str) -> None:
    ps.apply()
    names = list(val["instrument"].unique())
    fig, axes = plt.subplots(2, len(names), figsize=(4.4 * len(names), 8.4), squeeze=False)
    for col, name in enumerate(names):
        v = val[val["instrument"] == name]
        ok = (v["N2"] > 0) & (v["N2_ctd"] > 0)
        ax = axes[0, col]
        lx, ly = np.log10(v.loc[ok, "N2_ctd"]), np.log10(v.loc[ok, "N2"])
        lo, hi = np.percentile(np.r_[lx, ly], [1, 99])
        h = ax.hist2d(lx, ly, bins=50, range=[[lo, hi], [lo, hi]], cmap=ps.SEQ_EPSILON, cmin=1,
                      norm=LogNorm())
        ax.plot([lo, hi], [lo, hi], color=ps.TEXT_2, lw=0.8, ls="--")
        neg = (v["N2"] <= 0).mean()
        ax.set_title(f"{name.upper()}: N² vs ship CTD ({neg:.0%} of profiler N² ≤ 0)", loc="left")
        ax.set_xlabel("ship CTD log$_{10}$ N² (s$^{-2}$)")
        ax.set_ylabel("profiler log$_{10}$ N² (s$^{-2}$)")
        ax.set_aspect("equal")
        fig.colorbar(h[3], ax=ax, label="estimates", shrink=0.75)
        ax = axes[1, col]
        bins = np.linspace(0, 4, 41)
        ax.hist(v["R_rho_ctd"].clip(0, 4), bins=bins, color=ps.MUTED, label="ship CTD")
        ax.hist(v["R_rho"].clip(0, 4), bins=bins, histtype="step", lw=1.5,
                color=ps.INSTRUMENT_COLOR.get(name, ps.BLUE), label=name.upper())
        ax.set_xlabel(r"density ratio $R_\rho$ (clipped to 0–4)")
        ax.set_ylabel("estimates")
        ax.legend(loc="upper right")
    fig.suptitle(f"Stratification vs nearest ship CTD, 150–550 m, {scale:g} m fits",
                 x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


def station_figure(grids: dict, station_profiles: dict, path: Path, foot: str) -> None:
    ps.apply()
    fig, axes = plt.subplots(1, 4, figsize=(11, 6.5), sharey=True)
    panels = [("SA_used", r"$S_A$ used (g kg$^{-1}$)", False), ("N2", r"N² (s$^{-2}$)", True),
              ("R_rho", r"$R_\rho$", False), ("Turner", "Turner angle (°)", False)]
    for name, ds in grids.items():
        sel = np.isin(ds["profile_file"].values, station_profiles.get(name, []))
        color = ps.INSTRUMENT_COLOR.get(name, ps.BLUE)
        for i in np.flatnonzero(sel):
            for ax, (var, _, log) in zip(axes, panels):
                x = ds[var].isel(profile=i).values
                if var == "R_rho":
                    x = np.where((x > 0) & (x < 10), x, np.nan)
                if log:
                    x = np.where(x > 0, x, np.nan)
                ax.plot(x, ds["depth"].values, color=color, lw=0.7, alpha=0.7)
    for ax, (_, label, log) in zip(axes, panels):
        if log:
            ax.set_xscale("log")
        ax.set_xlabel(label)
    axes[3].axvspan(45, 90, color=ps.ORANGE_RAMP[0], zorder=0, lw=0)
    axes[3].text(67, 20, "salt fingers", ha="center", fontsize=7, color=ps.TEXT_2)
    axes[2].axvline(1, color=ps.TEXT_2, lw=0.8, ls="--")
    axes[0].invert_yaxis()
    axes[0].set_ylabel("depth (m)")
    handles = [plt.Line2D([], [], color=ps.INSTRUMENT_COLOR.get(n, ps.BLUE), lw=2,
                          label=f"{n.upper()} ({len(station_profiles.get(n, []))} profiles)")
               for n in grids]
    axes[0].legend(handles=handles, loc="lower left", fontsize=7)
    fig.suptitle("Process station stratification (VMP5500 salinity from the ship CTD T–S; "
                 "blank below its 550 m reach)", x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


# --------------------------------------------------------------------------
# Step
# --------------------------------------------------------------------------

def run(ctx: dict) -> None:
    config = ctx["config"]
    hc = config["hydrography"]
    scale, bin_m, min_frac = hc["gradient_smoothing_m"], hc["bin_m"], hc["min_fit_fraction"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ship = ShipCTD(Path(config["paths"]["ship_ctd"]), hc["ship_ctd"])
    report = {"gradient_smoothing_m": scale, "instruments": {}}
    grids, val_rows, station_profiles = {}, [], {}

    for name, inst in common.instruments(config):
        source = inst["salinity_source"]
        offsets = inst.get("sensor_offsets_m", {})
        ct_off, ms_off = float(offsets.get("ct", 0.0)), float(offsets.get("microstructure", 0.0))
        prof_dir = common.single_dir(ctx["run_dir"] / "convert" / name, "profiles")
        seg = pd.read_csv(ctx["run_dir"] / "segments" / f"segments_{name}.csv")
        casts = pd.read_csv(ctx["run_dir"] / "cast_log" / f"casts_{name}.csv")
        casts["stem"] = casts["file"].map(lambda f: Path(f).stem)
        station = set(casts.loc[casts["station"] == "process_station", "stem"])
        files = sorted(prof_dir.glob("*_prof*.nc"))
        zmax = 0.0
        raw = []
        for f in files:
            with netCDF4.Dataset(f) as d:
                g = lambda n: np.ma.filled(d[n][:].astype(float), np.nan)  # noqa: E731
                P, CT, SA = g("P"), g("CT"), g("SA")
                lat, lon = float(np.ma.filled(d["lat"][...], np.nan)), float(np.ma.filled(d["lon"][...], np.nan))
                t0 = pd.Timestamp(float(d["stime"][...]), unit="s", tz="UTC")
                latu = lat if np.isfinite(lat) else 12.0
                own = (own_ts_profile(d, latu, lon if np.isfinite(lon) else -50.0, ct_off, ms_off,
                                      inst, hc["own_ts"]) if source == "own_ts" else None)
            depth = -gsw.z_from_p(P, latu) + ct_off      # depth of the CT sensor
            zmax = max(zmax, float(np.nanmax(depth)) + max(ms_off - ct_off, 0.0))
            raw.append((f, P, CT, SA, depth, lat, lon, latu, t0, own))

        edges = np.arange(0.0, np.ceil(zmax) + bin_m, bin_m)
        zc = (edges[:-1] + edges[1:]) / 2
        nz, npf = len(zc), len(raw)
        fields = ["CT", "SA_own", "SA_used", "SA_from_ship", "sigma0", "N2", "T_z", "S_z",
                  "alpha", "beta", "R_rho", "Turner"]
        arr = {k: np.full((npf, nz), np.nan) for k in fields}
        meta = {"profile_file": [], "ship_cast": [], "ship_km": [], "ship_hours": [],
                "lat": [], "lon": [], "stime": [], "ts_bad_fraction": [], "ts_ship_only": []}
        win_frames = []
        for i, (f, P, CT, SA, depth, lat, lon, latu, t0, own) in enumerate(raw):
            ct = bin_profile(depth, CT, edges)
            sa_own = bin_profile(depth, SA, edges)
            p = gsw.p_from_z(-zc, latu)
            m = ship.match(lat, lon, t0)
            if source == "own":
                sa = sa_own
            elif source == "ship_ctd_ts":
                sa = ship.ts_salinity(m["index"], ct) if m else np.full(nz, np.nan)
            elif source == "own_ts":                     # FP07 CT on the probe-tip depth grid
                oc = hc["own_ts"]
                if m and oc["ship_fallback"]["enabled"]:
                    sa_c, ct_c, _ = ship.profile(m["index"])
                    fbk = ship_fallback(own["nodes"], ts_relation(ct_c, sa_c, oc["bin_degC"],
                                                                  oc["smooth_bins"]), oc)
                else:
                    fbk = {"nodes": own["nodes"], "bad_nodes": None, "failed": False,
                           "bad_fraction": np.nan}
                bad = fbk["bad_nodes"]
                if bad is None and not fbk["failed"] and own["nodes"] is not None:
                    bad = (own["nodes"][0], np.zeros(len(own["nodes"][0])))
                sa_ref = own["sa_ref"] if np.isfinite(own["sa_ref"]) else 35.0
                ev = evaluate_ts(own, fbk["nodes"], bad, sa_ref)
                tip = -gsw.z_from_p(own["P_tip"], latu)
                ct, sa = bin_profile(tip, ev["CT"], edges), bin_profile(tip, ev["SA"], edges)
                arr["SA_from_ship"][i] = bin_profile(tip, ev["from_ship"], edges)
                meta["ts_bad_fraction"].append(fbk["bad_fraction"])
                meta["ts_ship_only"].append(fbk["failed"])
            else:
                raise ValueError(f"Unknown salinity_source {source!r} for {name}")
            st = stratification(zc, ct, sa, p, scale, bin_m, min_frac)
            arr["CT"][i], arr["SA_own"][i], arr["SA_used"][i] = ct, sa_own, sa
            arr["sigma0"][i] = gsw.sigma0(sa, ct)
            for k in ("N2", "T_z", "S_z", "alpha", "beta", "R_rho", "Turner"):
                arr[k][i] = st[k]
            meta["profile_file"].append(f.name)
            meta["ship_cast"].append(m["cast"] if m else "")
            meta["ship_km"].append(m["km"] if m else np.nan)
            meta["ship_hours"].append(m["hours"] if m else np.nan)
            meta["lat"].append(lat), meta["lon"].append(lon)
            meta["stime"].append(t0.timestamp())

            # Values at the dissipation window centres (P_mean converted to depth)
            w = seg[seg["profile_file"] == f.name][["profile_file", "window", "P_mean"]].copy()
            wd = -gsw.z_from_p(w["P_mean"].to_numpy(), latu) + ms_off   # probe-tip depth
            w["depth"] = wd
            for k in ("N2", "T_z", "S_z", "alpha", "beta", "R_rho", "Turner"):
                w[k] = np.interp(wd, zc, st[k], left=np.nan, right=np.nan)
            w["CT"] = np.interp(wd, zc, ct, left=np.nan, right=np.nan)
            w["SA"] = np.interp(wd, zc, sa, left=np.nan, right=np.nan)
            if source == "own_ts":
                w["SA_from_ship"] = np.interp(wd, zc, arr["SA_from_ship"][i], left=np.nan, right=np.nan)
            win_frames.append(w)

            # Validation against the matched ship CTD cast, same scale and grid
            if m:
                sa_c, ct_c, p_c = ship.profile(m["index"])
                zs = ship.z
                ref = stratification(zs, ct_c, sa_c, p_c, scale, 1.0, min_frac)
                for zv in np.arange(VALID_DEPTHS[0], VALID_DEPTHS[1] + 1, 10.0):
                    a, b = np.argmin(np.abs(zc - zv)), np.argmin(np.abs(zs - zv))
                    val_rows.append({"instrument": name, "profile_file": f.name, "depth": zv,
                                     "N2": st["N2"][a], "N2_ctd": ref["N2"][b],
                                     "T_z": st["T_z"][a], "T_z_ctd": ref["T_z"][b],
                                     "S_z": st["S_z"][a], "S_z_ctd": ref["S_z"][b],
                                     "R_rho": st["R_rho"][a], "R_rho_ctd": ref["R_rho"][b]})

        ds = xr.Dataset({k: (("profile", "depth"), v) for k, v in arr.items()},
                        coords={"depth": zc, "profile_file": ("profile", meta["profile_file"])})
        for k in ("ship_cast", "ship_km", "ship_hours", "lat", "lon", "stime"):
            ds[k] = ("profile", np.asarray(meta[k]))
        if source == "own_ts":
            ds["ts_bad_fraction"] = ("profile", np.asarray(meta["ts_bad_fraction"], float))
            ds["ts_ship_only"] = ("profile", np.asarray(meta["ts_ship_only"], bool))
            ds["ts_bad_fraction"].attrs["comment"] = "fraction of own T-S bins failing the ship check (NaN: no ship cast)"
            ds["ts_ship_only"].attrs["comment"] = "whole profile on the ship T-S relation"
        else:
            ds = ds.drop_vars("SA_from_ship")
        units = {"CT": "degC", "SA_own": "g/kg", "SA_used": "g/kg", "SA_from_ship": "1", "sigma0": "kg m-3",
                 "N2": "s-2", "T_z": "K m-1", "S_z": "g kg-1 m-1", "alpha": "K-1",
                 "beta": "kg g-1", "R_rho": "1", "Turner": "degree", "depth": "m"}
        for k, u in ((k, u) for k, u in units.items() if k in ds):
            ds[k].attrs["units"] = u
        ds["T_z"].attrs["comment"] = ds["S_z"].attrs["comment"] = "z positive upward"
        ds["SA_used"].attrs["comment"] = f"salinity_source={source}"
        ds["SA_own"].attrs["comment"] = "profiler CT-sensor salinity (perturb), at the CT sensor's depth"
        if source == "own_ts":
            ds["CT"].attrs["comment"] = f"FP07 {hc['own_ts']['fp07']} at the probe tips' depth"
            ds.attrs.update({f"own_ts_{k}": str(v) for k, v in hc["own_ts"].items()})
            ds.attrs.update({f"ct_match_{k}": v for k, v in inst["ct_match"].items()})
        ds.attrs.update({"instrument": name, "gradient_smoothing_m": scale,
                         "ct_offset_m": ct_off, "microstructure_offset_m": ms_off,
                         "salinity_source": source, "provenance": foot})
        ds.to_netcdf(out / f"hydrography_{name}.nc")
        grids[name] = ds

        wins = pd.concat(win_frames, ignore_index=True)
        wins["no_stratification"] = ~np.isfinite(wins["N2"])
        wins["N2_nonpositive"] = wins["N2"] <= 0
        wins["ts_salinity_invalid"] = (source in ("ship_ctd_ts", "own_ts")) & ~(wins["T_z"] > 0)
        wins.to_csv(out / f"windows_{name}.csv", index=False, float_format="%.6g")
        station_profiles[name] = [f for f in meta["profile_file"] if f.split("_prof")[0] in station]

        v = pd.DataFrame([r for r in val_rows if r["instrument"] == name])
        ok = (v["N2"] > 0) & (v["N2_ctd"] > 0)
        r = np.log10(v.loc[ok, "N2"] / v.loc[ok, "N2_ctd"])
        matched = sum(1 for c in meta["ship_cast"] if c)
        report["instruments"][name] = {
            "salinity_source": source, "profiles": npf, "profiles_with_ship_ctd": matched,
            "sensor_offsets_m": {"ct": ct_off, "microstructure": ms_off},
            "windows": len(wins),
            "windows_without_stratification": int(wins["no_stratification"].sum()),
            "windows_N2_nonpositive": int(wins["N2_nonpositive"].sum()),
            "windows_ts_salinity_invalid": int(wins["ts_salinity_invalid"].sum()),
            **({"profiles_ts_ship_only": int(np.sum(meta["ts_ship_only"])),
                "profiles_ts_ship_only_files": [f for f, x in zip(meta["profile_file"], meta["ts_ship_only"]) if x],
                "ts_bad_fraction_median": round(float(np.nanmedian(meta["ts_bad_fraction"])), 3),
                "windows_SA_mostly_from_ship": int((wins["SA_from_ship"] > 0.5).sum())}
               if source == "own_ts" else {}),
            "validation_150_550m": {
                "estimates": int(len(v)),
                "N2_nonpositive_fraction": round(float((v["N2"] <= 0).mean()), 3),
                "ship_N2_nonpositive_fraction": round(float((v["N2_ctd"] <= 0).mean()), 3),
                "N2_median_ratio": round(float(10 ** np.median(r)), 3),
                "N2_within_factor2": round(float(np.mean(np.abs(r) < np.log10(2))), 3),
                "T_z_median_ratio": round(float(np.nanmedian(v["T_z"] / v["T_z_ctd"])), 3),
                "S_z_median_ratio": round(float(np.nanmedian(v["S_z"] / v["S_z_ctd"])), 3),
                "R_rho_median": round(float(np.nanmedian(v["R_rho"])), 3),
                "R_rho_ship_median": round(float(np.nanmedian(v["R_rho_ctd"])), 3)},
        }
        rv = report["instruments"][name]["validation_150_550m"]
        print(f"  {name}: {npf} profiles ({matched} with ship CTD), salinity={source}; vs ship "
              f"CTD 150-550 m: N2 ratio {rv['N2_median_ratio']}, within x2 "
              f"{rv['N2_within_factor2']:.0%}, N2<=0 {rv['N2_nonpositive_fraction']:.0%} "
              f"(ship {rv['ship_N2_nonpositive_fraction']:.0%}), R_rho {rv['R_rho_median']} "
              f"(ship {rv['R_rho_ship_median']})")

    val = pd.DataFrame(val_rows)
    val.to_csv(out / "validation_ship_ctd.csv", index=False, float_format="%.6g")
    validation_figure(val, out / "figures" / "validation_ship_ctd.png", scale, foot)
    station_figure(grids, station_profiles, out / "figures" / "process_station_stratification.png",
                   foot)
    common.write_json(out / "hydrography_report.json", report)
    common.write_step_metadata(out, STEP, ctx, gradient_smoothing_m=scale)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
