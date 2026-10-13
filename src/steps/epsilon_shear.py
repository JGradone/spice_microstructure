#!/usr/bin/env python3
"""Step epsilon_shear: QC, noise floor and combination of shear epsilon (CLAUDE.md step 4).

perturb (convert step) already computed epsilon per shear probe on 16 s windows
with Goodman coherent-noise removal and Nasmyth fitting. This step decides
which probe estimates to use and how close each window is to the noise floor.

Per probe and window:
  * Low-wavenumber refit (shear_qc.refit): perturb integrates the spectrum from
    the lowest wavenumber to K_max. Energy below ~1 Hz (vehicle motion or other
    non-turbulent shear) sits 3-5x above Nasmyth and biases epsilon high
    (decisions.md 2026-10-13). With refit enabled, epsilon is re-solved so the
    Nasmyth variance between k_min = f_min_hz / speed and perturb's K_max
    equals the observed variance over the same range, and FM is recomputed
    over that range with the package's formula (Lueck 2022; num_ffts and the
    number of vibration channels recovered by reproducing perturb's FM).
    perturb's values are kept as epsilon_<probe>_perturb and FM_<probe>_perturb.
  * Probe exclusions from the config and, if segments.enabled, the segment QC.
  * var_resolved < shear_qc.var_resolved.min    flagged; dropped if `apply`.
  * Lueck (2022) FM > shear_qc.figure_of_merit.max  flagged; dropped if `apply`.
  * Noise floor, independent of the figure of merit: the noise spectrum is the
    median frequency spectrum of the quietest `quantile` of windows (per
    instrument and probe). For each window it is mapped to wavenumber at that
    window's speed and compared with the observed spectrum over the same
    integration range (0 < k <= K_max):
        floor = epsilon * integral(noise) / integral(observed).
    Because the quietest windows contain some real signal, this floor is an
    upper bound on the instrument noise, so at_floor is conservative.
Per window:
  * Probe pair: if both probes are usable and |ln(e1/e2)| > ln(limit), the
    probes disagree; policy `min` keeps the smaller estimate.
  * epsilon_shear: geometric (or arithmetic) mean of the usable probes; the
    floor is combined the same way over the same probes.
  * at_floor: epsilon_shear < factor x floor. Such windows are kept and flagged;
    epsilon_shear_bounded = max(epsilon_shear, floor) is the upper-bound value
    for the double diffusion test (policy clamp). Nothing is dropped for being
    near the floor: dropping biases means high (decisions.md 2026-10-12).

Window flag bits (`flags`):
    1  no_usable_probe      no probe passed QC (epsilon_shear NaN)
    2  probe_disagree       probes disagree beyond probe_pair.limit
    4  at_floor             epsilon_shear < factor x floor (upper bound)
    8  fm_high              a usable probe has FM > figure_of_merit.max
   16  low_var_resolved     a probe has var_resolved < var_resolved.min
   32  segment_flagged      segment QC flagged the window (dropped only if segments.enabled)
`keep`: epsilon_shear is finite and the window passes segment QC when applied.

Reads:  <run_dir>/convert/<instrument>/diss_NN/*_prof*.nc
        <run_dir>/segments/segments_<instrument>.csv
Writes: <run_dir>/epsilon_shear/
          epsilon_shear_<instrument>.csv     one row per window
          noise_spectrum_<instrument>.csv    noise frequency spectra per probe
          figures/*.png, epsilon_shear_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
from odas_tpw.scor160.nasmyth import nasmyth_grid
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "epsilon_shear"
BITS = {"no_usable_probe": 1, "probe_disagree": 2, "at_floor": 4, "fm_high": 8,
        "low_var_resolved": 16, "segment_flagged": 32}
EPS_DECADES = [(1e-11, 1e-10), (1e-10, 1e-9), (1e-9, 1e-8), (1e-8, 1e-5)]
FM_BINS = [(0.0, 1.15), (1.15, 1.5), (1.5, np.inf)]
GALLERY_COLORS = [ps.BLUE, ps.ORANGE, ps.AQUA, ps.RED, ps.BLUE_RAMP[5]]


def read_var(ds, name) -> np.ndarray:
    return np.ma.filled(ds[name][...].astype(float), np.nan)


def load(diss_dir: Path) -> dict:
    """All windows of one instrument: per-probe scalars, spectra (wavenumber) and grids."""
    rows, spec, nasm, kgrid = [], [], [], []
    freq, num_ffts = None, None
    for f in sorted(diss_dir.glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as d:
            probes = [str(p) for p in d["probe"][:]]
            eps, fm, vr, kmax = (read_var(d, k) for k in ("epsilon", "FM", "var_resolved", "K_max"))
            s, n, K, F = (read_var(d, k) for k in ("spec_shear", "spec_nasmyth", "K", "F"))
            u, nu, P = read_var(d, "speed"), read_var(d, "nu"), read_var(d, "P_mean")
            nf = 2 * (int(d.diss_length) // int(d.fft_length)) - 1     # as in perturb's pipeline
        if num_ffts is None:
            num_ffts = nf
        if nf != num_ffts:
            raise ValueError(f"{f.name}: FFT count differs from the instrument's first file")
        if freq is None:
            freq = F[:, 0]
        if not np.allclose(F, freq[:, None], equal_nan=True):
            raise ValueError(f"{f.name}: frequency grid differs from the instrument's first file")
        for w in range(eps.shape[1]):
            row = {"profile_file": f.name, "window": w, "P_mean": P[w], "speed": u[w], "nu": nu[w]}
            for i, p in enumerate(probes):
                row.update({f"epsilon_{p}": eps[i, w], f"FM_{p}": fm[i, w],
                            f"var_resolved_{p}": vr[i, w], f"K_max_{p}": kmax[i, w]})
            rows.append(row)
            spec.append(s[:, :, w])
            nasm.append(n[:, :, w])
            kgrid.append(K[:, w])
    return {"df": pd.DataFrame(rows), "probes": probes, "spec": np.array(spec),
            "nasmyth": np.array(nasm), "K": np.array(kgrid), "F": freq, "num_ffts": num_ffts}


def lueck_fm(obs: np.ndarray, nas: np.ndarray, num_ffts: int, n_v: int) -> float:
    """Lueck (2022) figure of merit, as in microstructure-tpw scor160/l4.py."""
    r = obs / nas
    r = r[r > 0]
    if len(r) == 0:
        return np.nan
    sigma_ln = np.sqrt(1.25 * max(num_ffts - n_v, 1) ** (-7 / 9))
    t_m = 0.8 + np.sqrt(1.56 / len(r))
    return float(np.mean(np.abs(np.log(r))) / (t_m * sigma_ln))


def vibration_channels(data: dict, probe: int = 0, n_check: int = 200) -> int:
    """Number of Goodman vibration channels that reproduces perturb's FM (range 0 < k <= K_max)."""
    df, K, p = data["df"], data["K"], data["probes"][probe]
    eps, kmax, fm = (df[f"{v}_{p}"].to_numpy() for v in ("epsilon", "K_max", "FM"))
    idx = np.flatnonzero(np.isfinite(eps) & np.isfinite(fm) & (eps < 1e-7))[:n_check]
    for n_v in range(0, 5):
        ours = []
        for w in idx:
            m = (K[w] > 0) & (K[w] <= kmax[w])
            ours.append(lueck_fm(data["spec"][w, probe, m], data["nasmyth"][w, probe, m],
                                 data["num_ffts"], n_v))
        if np.nanmedian(np.abs(np.array(ours) / fm[idx] - 1)) < 0.02:
            return n_v
    raise ValueError("Could not reproduce perturb's FM; check the FM formula against the package")


def refit(data: dict, f_min_hz: float, min_points: int, n_v: int,
          k_upper: dict | None = None, subtract: dict | None = None) -> dict:
    """Epsilon re-solved over f_min_hz/speed <= k <= K_max by matching Nasmyth variance; FM over that range.

    k_upper[probe]: optional per-window upper limit (cpm) replacing K_max where smaller.
    subtract[probe]: optional noise frequency spectrum subtracted before the fit."""
    df, K = data["df"], data["K"]
    u, nu = df["speed"].to_numpy(), df["nu"].to_numpy()
    out = {}
    for i, p in enumerate(data["probes"]):
        kmax, e0 = df[f"K_max_{p}"].to_numpy(), df[f"epsilon_{p}"].to_numpy()
        eps, fm = np.full(len(df), np.nan), np.full(len(df), np.nan)
        if k_upper is not None:
            kmax = np.fmin(kmax, k_upper[p])
        for w in np.flatnonzero(np.isfinite(e0) & np.isfinite(kmax)):
            k = K[w]
            m = (k > 0) & (k >= f_min_hz / u[w]) & (k <= kmax[w])
            if m.sum() < min_points:
                continue
            obs = data["spec"][w, i, m]
            if subtract is not None:
                obs = np.maximum(obs - subtract[p][m] * u[w], 0.0)
                if not obs.any():
                    continue
            target = np.log(np.trapezoid(obs, k[m]))
            f = lambda le: np.log(np.trapezoid(nasmyth_grid(10 ** le, nu[w], k[m]), k[m])) - target  # noqa: E731
            lo, hi = np.log10(e0[w]) - 3, np.log10(e0[w]) + 1
            if f(lo) * f(hi) > 0:
                continue
            eps[w] = 10 ** brentq(f, lo, hi, xtol=1e-4)
            fm[w] = lueck_fm(obs, nasmyth_grid(eps[w], nu[w], k[m]), data["num_ffts"], n_v)
        out[p] = {"epsilon": eps, "FM": fm, "K_max": kmax}
    return out


def apply_refit(data: dict, cfg: dict) -> dict:
    """Replace per-probe epsilon and FM by the refit (originals kept with suffix _perturb)."""
    rc = cfg["refit"]
    df = data["df"]
    info = {"enabled": bool(rc["enabled"]), "num_ffts": data["num_ffts"]}
    data["k_min_hz"] = 0.0
    for p in data["probes"]:
        df[f"epsilon_{p}_perturb"], df[f"FM_{p}_perturb"] = df[f"epsilon_{p}"], df[f"FM_{p}"]
    if not rc["enabled"]:
        return info
    n_v = vibration_channels(data)
    res = refit(data, rc["f_min_hz"], rc["min_points"], n_v)
    for p in data["probes"]:
        df[f"epsilon_{p}"], df[f"FM_{p}"] = res[p]["epsilon"], res[p]["FM"]
    data["k_min_hz"] = rc["f_min_hz"]
    info.update({"n_vibration_channels": n_v, "f_min_hz": rc["f_min_hz"],
                 "unfit": {p: int((np.isfinite(df[f"epsilon_{p}_perturb"]) & ~np.isfinite(df[f"epsilon_{p}"])).sum())
                           for p in data["probes"]},
                 "median_ratio_refit_perturb": {p: float(np.nanmedian(df[f"epsilon_{p}"] / df[f"epsilon_{p}_perturb"]))
                                                for p in data["probes"]}})
    return info


def noise_spectra(data: dict, base_ok: np.ndarray, cfg: dict) -> dict:
    """Median frequency spectrum of the quietest windows, per probe."""
    df, out = data["df"], {}
    for i, p in enumerate(data["probes"]):
        eps = df[f"epsilon_{p}"].to_numpy()
        ok = base_ok & np.isfinite(eps)
        quiet = ok & (eps <= np.nanquantile(eps[ok], cfg["quantile"]))
        out[p] = {"spectrum": np.nanmedian(data["spec"][quiet, i, :] / df["speed"].to_numpy()[quiet, None], axis=0),
                  "windows": int(quiet.sum()), "epsilon_max": float(eps[quiet].max())}
    return out


def window_floor(data: dict, noise: dict) -> dict:
    """floor = epsilon x integral(noise) / integral(observed) over 0 < k <= K_max, per probe."""
    df, K = data["df"], data["K"]
    u = df["speed"].to_numpy()
    out = {}
    for i, p in enumerate(data["probes"]):
        kmax = df[f"K_max_{p}"].to_numpy()
        m = (K > 0) & (K <= kmax[:, None]) & (K >= data.get("k_min_hz", 0.0) / u[:, None])
        obs = np.where(m, data["spec"][:, i, :], 0.0)
        nk = np.where(m, noise[p]["spectrum"][None, :] * u[:, None], 0.0)   # noise on each window's k grid
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.trapezoid(nk, K, axis=1) / np.trapezoid(obs, K, axis=1)
        out[p] = df[f"epsilon_{p}"].to_numpy() * frac
    return out


def combine(values: np.ndarray, use: np.ndarray, how: str) -> np.ndarray:
    v = np.where(use, values, np.nan)
    n = use.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        if how == "geometric":
            out = np.exp(np.nansum(np.log(v), axis=1) / n)
        elif how == "arithmetic":
            out = np.nansum(v, axis=1) / n
        else:
            raise ValueError(f"Unknown shear_qc.combine {how!r}")
    return np.where(n > 0, out, np.nan)


def qc(data: dict, seg: pd.DataFrame, cfg: dict, seg_enabled: bool) -> tuple[pd.DataFrame, dict, dict]:
    df = data["df"].merge(seg[["profile_file", "window", "keep", "flags"]]
                          .rename(columns={"keep": "segment_keep", "flags": "segment_flags"}),
                          on=["profile_file", "window"], how="left", validate="one_to_one")
    if df["segment_keep"].isna().any():
        raise ValueError("Dissipation windows missing from the segments table")
    probes = data["probes"]
    excl = {p: seg.set_index(["profile_file", "window"])[f"exclude_{p}"]
            .reindex(pd.MultiIndex.from_frame(df[["profile_file", "window"]])).to_numpy(bool)
            for p in probes}
    seg_keep = df["segment_keep"].to_numpy(bool)
    fmc, vrc, pair = cfg["figure_of_merit"], cfg["var_resolved"], cfg["probe_pair"]

    # Noise floor from the quietest segment-QC-passed windows (always, so surface junk never sets it)
    noise = noise_spectra(data, seg_keep & ~np.any([excl[p] for p in probes], axis=0), cfg["noise_floor"])
    floors = window_floor(data, noise)

    counts = {"windows": len(df)}
    base = seg_keep if seg_enabled else np.ones(len(df), bool)
    counts["after_segment_qc"] = int(base.sum())
    use, fm_high, low_vr = {}, np.zeros(len(df), bool), np.zeros(len(df), bool)
    stage = {"probe_exclusion": 0, "var_resolved": 0, "figure_of_merit": 0}
    for p in probes:
        eps = df[f"epsilon_{p}"].to_numpy()
        ok = base & np.isfinite(eps)
        stage["probe_exclusion"] += int((ok & excl[p]).sum())
        ok &= ~excl[p]
        vr_bad = df[f"var_resolved_{p}"].to_numpy() < vrc["min"]
        low_vr |= vr_bad & np.isfinite(eps)
        if vrc["apply"]:
            stage["var_resolved"] += int((ok & vr_bad).sum())
            ok &= ~vr_bad
        fm_bad = df[f"FM_{p}"].to_numpy() > fmc["max"]
        fm_high |= ok & fm_bad
        if fmc["apply"]:
            stage["figure_of_merit"] += int((ok & fm_bad).sum())
            ok &= ~fm_bad
        use[p] = ok
        df[f"floor_{p}"] = floors[p]
    counts["probe_estimates_removed"] = stage

    # Probe pair agreement
    e = np.column_stack([df[f"epsilon_{p}"].to_numpy() for p in probes])
    u = np.column_stack([use[p] for p in probes])
    disagree = np.zeros(len(df), bool)
    if len(probes) == 2:
        both = u.all(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            lr = np.abs(np.log(e[:, 0] / e[:, 1]))
        disagree = both & (lr > np.log(pair["limit"]))
        df["probe_ratio"] = e[:, 0] / e[:, 1]
        if pair["policy"] == "min":
            larger = np.argmax(np.nan_to_num(e, nan=-np.inf), axis=1)
            u[disagree, larger[disagree]] = False
        elif pair["policy"] != "keep_both":
            raise ValueError(f"Unknown shear_qc.probe_pair.policy {pair['policy']!r}")
    for i, p in enumerate(probes):
        df[f"use_{p}"] = u[:, i]
    fl = np.column_stack([floors[p] for p in probes])
    df["n_probes"] = u.sum(axis=1)
    df["epsilon_shear"] = combine(e, u, cfg["combine"])
    df["epsilon_floor"] = combine(fl, u, cfg["combine"])
    nf = cfg["noise_floor"]
    at_floor = np.isfinite(df["epsilon_shear"]) & (df["epsilon_shear"] < nf["factor"] * df["epsilon_floor"])
    if nf["policy"] == "clamp":
        df["epsilon_shear_bounded"] = np.fmax(df["epsilon_shear"], df["epsilon_floor"])
    elif nf["policy"] == "none":
        df["epsilon_shear_bounded"] = df["epsilon_shear"]
    else:
        raise ValueError(f"Unknown shear_qc.noise_floor.policy {nf['policy']!r}")
    df.loc[~np.isfinite(df["epsilon_shear"]), "epsilon_shear_bounded"] = np.nan

    flags = np.zeros(len(df), int)
    for name, hit in [("no_usable_probe", ~np.isfinite(df["epsilon_shear"].to_numpy())),
                      ("probe_disagree", disagree), ("at_floor", at_floor.to_numpy()),
                      ("fm_high", fm_high), ("low_var_resolved", low_vr), ("segment_flagged", ~seg_keep)]:
        flags |= np.where(hit, BITS[name], 0)
    df["flags"] = flags
    df["at_floor"] = at_floor
    df["keep"] = np.isfinite(df["epsilon_shear"]) & base
    counts["no_usable_probe"] = int((base & ~np.isfinite(df["epsilon_shear"])).sum())
    counts["probe_disagree"] = int(disagree.sum())
    counts["kept"] = int(df["keep"].sum())
    k = df["keep"]
    counts["kept_at_floor"] = int((k & at_floor).sum())
    counts["kept_at_floor_fraction"] = round(float((k & at_floor).sum() / max(k.sum(), 1)), 4)
    counts["kept_fm_high_fraction"] = round(float((k & (fm_high)).sum() / max(k.sum(), 1)), 4)
    return df, noise, counts


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def noise_figure(results: dict, path: Path, foot: str) -> None:
    fig, axes = plt.subplots(1, len(results), figsize=(6.2 * len(results), 4.6), squeeze=False)
    for ax, (name, r) in zip(axes[0], results.items()):
        F, df, data = r["F"], r["df"], r["data"]
        k = df["keep"].to_numpy()
        allspec = np.nanmedian(data["spec"][k, 0, :] / df["speed"].to_numpy()[k, None], axis=0)
        ax.loglog(F[1:], allspec[1:], color=ps.MUTED, lw=1.2, label="median of all kept windows (sh1)")
        for (p, nz), c in zip(r["noise"].items(), (ps.BLUE, ps.ORANGE)):
            ax.loglog(F[1:], nz["spectrum"][1:], color=c, lw=1.1,
                      label=f"noise {p}: quietest {nz['windows']} windows (eps <= {nz['epsilon_max']:.1e})")
        ax.set_xlabel("frequency (Hz)")
        ax.set_ylabel(r"shear spectrum (s$^{-2}$ Hz$^{-1}$)")
        ax.set_title(name)
        ax.legend(fontsize=7.5, loc="lower left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def depth_figure(results: dict, path: Path, foot: str) -> None:
    fig, axes = plt.subplots(1, 2 * len(results), figsize=(5.2 * len(results) * 1.4, 6.2),
                             gridspec_kw={"width_ratios": [3, 1] * len(results)}, squeeze=False)
    for j, (name, r) in enumerate(results.items()):
        df = r["df"][r["df"]["keep"]]
        ax, ax2 = axes[0, 2 * j], axes[0, 2 * j + 1]
        z = df["P_mean"]
        ax.scatter(df.loc[~df["at_floor"], "epsilon_shear"], z[~df["at_floor"]], s=2, color=ps.BLUE,
                   alpha=0.35, linewidths=0, label="above floor")
        ax.scatter(df.loc[df["at_floor"], "epsilon_shear"], z[df["at_floor"]], s=2, color=ps.ORANGE,
                   alpha=0.5, linewidths=0, label="at floor (upper bound)")
        bins = np.arange(0, z.max() + 25, 25)
        g = df.groupby(pd.cut(z, bins), observed=True)
        zc = [b.mid for b in g.size().index]
        ax.plot(g["epsilon_floor"].median(), zc, color="k", lw=1.3, label="median floor")
        ax.set_xscale("log")
        ax.set_xlim(1e-12, 1e-5)
        ax.set_ylim(z.max() + 10, 0)
        ax.set_xlabel(r"$\epsilon_{shear}$ (W kg$^{-1}$)")
        ax.set_ylabel("pressure (dbar)")
        ax.set_title(f"{name}: {len(df)} kept windows")
        ax.legend(fontsize=7.5, loc="lower right", markerscale=4)
        ax2.plot(g["at_floor"].mean(), zc, color=ps.ORANGE, lw=1.5)
        ax2.set_xlim(0, 1)
        ax2.set_ylim(z.max() + 10, 0)
        ax2.set_xlabel("fraction at floor")
        ax2.set_yticklabels([])
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def gallery_figure(name: str, r: dict, gal: dict, path: Path, foot: str) -> None:
    """Sample spectra by epsilon decade (rows) and FM bin (columns), probe sh1 and sh2 pooled."""
    df, data = r["df"], r["data"]
    rng = np.random.default_rng(gal["seed"])
    fig, axes = plt.subplots(len(EPS_DECADES), len(FM_BINS), figsize=(13, 13), sharex=True, squeeze=False)
    u = df["speed"].to_numpy()
    for i, (elo, ehi) in enumerate(EPS_DECADES):
        for j, (flo, fhi) in enumerate(FM_BINS):
            ax = axes[i, j]
            cand = []
            for pi, p in enumerate(data["probes"]):
                e, fm = df[f"epsilon_{p}"].to_numpy(), df[f"FM_{p}"].to_numpy()
                hit = df["keep"].to_numpy() & df[f"use_{p}"].to_numpy() & (e >= elo) & (e < ehi) & (fm >= flo) & (fm < fhi)
                cand += [(w, pi) for w in np.flatnonzero(hit)]
            total = len(cand)
            pick = [cand[c] for c in rng.choice(total, min(gal["per_panel"], total), replace=False)] if total else []
            for c, (w, pi) in zip(GALLERY_COLORS, pick):
                p = data["probes"][pi]
                K, s = data["K"][w], data["spec"][w, pi]
                n = nasmyth_grid(df[f"epsilon_{p}"].iloc[w], df["nu"].iloc[w], K)
                ax.loglog(K[1:], s[1:], color=c, lw=0.9)
                ax.loglog(K[1:], n[1:], color=c, lw=0.8, ls=":")
                ax.loglog(K[1:], (r["noise"][p]["spectrum"] * u[w])[1:], color=c, lw=0.6, ls="--", alpha=0.7)
                ax.axvline(df[f"K_max_{p}"].iloc[w], color=c, lw=0.6, alpha=0.6)
            ax.set_xlim(0.2, 300)
            ax.set_ylim(1e-9, 1e-1)
            ax.text(0.03, 0.04, f"n={total}", transform=ax.transAxes, fontsize=8)
            if i == 0:
                ax.set_title(f"FM {flo:g}–{fhi:g}" if np.isfinite(fhi) else f"FM > {flo:g}", fontsize=10)
            if j == 0:
                ax.set_ylabel(f"ε {elo:.0e}–{ehi:.0e}\n" + r"Φ (s$^{-2}$ cpm$^{-1}$)", fontsize=9)
            if i == len(EPS_DECADES) - 1:
                ax.set_xlabel("k (cpm)")
    fig.suptitle(f"{name}: sample shear spectra (solid), Nasmyth fit (dotted), noise spectrum (dashed), "
                 "K_max (vertical)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    cfg = config["shear_qc"]
    seg_enabled = bool(config["segments"]["enabled"])
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ps.apply()
    report = {"segments_applied": seg_enabled, "shear_qc": cfg, "instruments": {}}
    results = {}
    for name, _inst in common.instruments(config):
        data = load(common.single_dir(ctx["run_dir"] / "convert" / name, "diss"))
        refit_info = apply_refit(data, cfg)
        seg = pd.read_csv(ctx["run_dir"] / "segments" / f"segments_{name}.csv")
        df, noise, counts = qc(data, seg, cfg, seg_enabled)
        df.insert(0, "instrument", name)
        df.to_csv(out / f"epsilon_shear_{name}.csv", index=False, float_format="%.6g")
        pd.DataFrame({"frequency_hz": data["F"], **{f"noise_{p}": v["spectrum"] for p, v in noise.items()}}) \
            .to_csv(out / f"noise_spectrum_{name}.csv", index=False, float_format="%.6g")
        k = df["keep"]
        deep = k & (df["P_mean"] > 150)
        counts["refit"] = refit_info
        counts["noise_windows"] = {p: v["windows"] for p, v in noise.items()}
        counts["noise_window_epsilon_max"] = {p: v["epsilon_max"] for p, v in noise.items()}
        counts["floor_median_w_kg"] = float(df.loc[k, "epsilon_floor"].median())
        counts["floor_median_below_150dbar_w_kg"] = float(df.loc[deep, "epsilon_floor"].median())
        counts["at_floor_fraction_below_150dbar"] = round(float(df.loc[deep, "at_floor"].mean()), 4)
        counts["epsilon_median_below_150dbar_w_kg"] = float(df.loc[deep, "epsilon_shear"].median())
        report["instruments"][name] = counts
        results[name] = {"df": df, "noise": noise, "F": data["F"], "data": data}
        print(f"  {name}: {counts['windows']} windows, kept {counts['kept']}; probe estimates removed "
              f"{counts['probe_estimates_removed']}; probes disagree {counts['probe_disagree']}; "
              f"at floor {counts['kept_at_floor_fraction']:.0%} (below 150 dbar "
              f"{counts['at_floor_fraction_below_150dbar']:.0%}, median floor "
              f"{counts['floor_median_below_150dbar_w_kg']:.1e}, median epsilon "
              f"{counts['epsilon_median_below_150dbar_w_kg']:.1e})")

    noise_figure(results, out / "figures" / "noise_spectra.png", foot)
    depth_figure(results, out / "figures" / "epsilon_vs_floor.png", foot)
    for name, r in results.items():
        gallery_figure(name, r, cfg["gallery"], out / "figures" / f"spectra_gallery_{name}.png", foot)
    common.write_json(out / "epsilon_shear_report.json", report)
    common.write_step_metadata(out, STEP, ctx, segments_applied=seg_enabled)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
