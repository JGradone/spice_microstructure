#!/usr/bin/env python3
"""Step thermistor: QC and combination of FP07 chi and epsilon_T (CLAUDE.md step 5).

perturb (convert step) calibrated the FP07s in situ against the CT temperature,
corrected their speed-dependent response (perturb.chi.fp07_model) and fitted a
Kraichnan spectrum to each probe's temperature-gradient spectrum
(perturb.chi.fit_method, `use_epsilon: false`), giving chi and epsilon_T per
probe on the same windows as shear epsilon. This step decides which probe
estimates to use and how close each window is to the FP07 noise.

Per probe and window:
  * Probe exclusions: instruments.<name>.exclude_probes.
  * K_max / kB < chi_qc.k_max_ratio.min: chi mostly extrapolated beyond the
    resolved band; flagged, dropped if `apply`.
  * fom (observed / model variance over the fit band) outside
    [1/fom.band, fom.band]: flagged, dropped if `apply`. This is perturb's
    variance ratio, not the Lueck (2022) MAD statistic.
  * Noise: perturb's FP07 electronics noise spectrum (spec_noise) against the
    observed spectrum over the fit band (0 < k <= K_max_T):
        floor = chi * integral(noise) / integral(observed).
Per window:
  * Probe pair: |ln(chi1/chi2)| > ln(chi_qc.probe_pair.limit) -> disagree;
    policy `min` keeps the smaller estimate.
  * chi, epsilon_T: geometric (or arithmetic) mean of the usable probes; the
    floor is combined the same way over the same probes.
  * at_floor: chi < factor x floor; kept and flagged, chi_bounded =
    max(chi, floor) (policy clamp).

epsilon_T assumes the Kraichnan (turbulent) spectral shape, which may not hold
for finger-scale variance. The report compares it with shear epsilon where the
shear estimate is above its floor, by Turner-angle regime and buoyancy
Reynolds number; both estimates are carried forward.

Window flag bits (`flags`):
    1  no_usable_probe     no probe passed QC (chi NaN)
    2  probe_disagree      probes disagree beyond probe_pair.limit
    4  at_floor            chi < factor x floor (upper bound)
    8  fom_out_of_band     a probe's fom is outside the band
   16  low_k_max_ratio     a probe has K_max/kB below the minimum
   32  segment_flagged     segment QC flagged the window (dropped only if segments.enabled)

Reads:  <run_dir>/convert/<instrument>/chi_NN/*_prof*.nc
        <run_dir>/segments/segments_<instrument>.csv
        <run_dir>/epsilon_shear/epsilon_shear_<instrument>.csv
        <run_dir>/hydrography/windows_<instrument>.csv
Writes: <run_dir>/thermistor/
          thermistor_<instrument>.csv     one row per window
          figures/*.png, thermistor_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "thermistor"
BITS = {"no_usable_probe": 1, "probe_disagree": 2, "at_floor": 4, "fom_out_of_band": 8,
        "low_k_max_ratio": 16, "segment_flagged": 32}
CHI_DECADES = [(1e-11, 1e-9), (1e-9, 1e-8), (1e-8, 1e-7), (1e-7, 1e-3)]
FOM_BINS = [(0.0, 1 / 1.15), (1 / 1.15, 1.15), (1.15, np.inf)]
REGIMES = [("Tu < 45 (not finger)", -90, 45), ("Tu 45-72", 45, 72), ("Tu 72-90", 72, 90)]
GALLERY_COLORS = [ps.BLUE, ps.ORANGE, ps.AQUA, ps.RED, ps.BLUE_RAMP[5]]


def read_var(ds, name) -> np.ndarray:
    return np.ma.filled(ds[name][...].astype(float), np.nan)


def load(chi_dir: Path) -> dict:
    rows, obs, model, noise, kgrid = [], [], [], [], []
    probes = None
    for f in sorted(chi_dir.glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as d:
            probes = [str(p) for p in d["probe"][:]]
            chi, epsT, kB, kmax, fom, kr = (read_var(d, k) for k in
                                            ("chi", "epsilon_T", "kB", "K_max_T", "fom", "K_max_ratio"))
            s, m, n, K = (read_var(d, k) for k in ("spec_gradT", "spec_batch", "spec_noise", "K"))
            u, nu, P = read_var(d, "speed"), read_var(d, "nu"), read_var(d, "P_mean")
        for w in range(chi.shape[1]):
            row = {"profile_file": f.name, "window": w, "P_mean": P[w], "speed": u[w], "nu": nu[w]}
            for i, p in enumerate(probes):
                row.update({f"chi_{p}": chi[i, w], f"epsilon_T_{p}": epsT[i, w], f"kB_{p}": kB[i, w],
                            f"K_max_T_{p}": kmax[i, w], f"fom_{p}": fom[i, w], f"K_max_ratio_{p}": kr[i, w]})
            rows.append(row)
            obs.append(s[:, :, w])
            model.append(m[:, :, w])
            noise.append(n[:, :, w])
            kgrid.append(K[:, w])
    return {"df": pd.DataFrame(rows), "probes": probes, "obs": np.array(obs), "model": np.array(model),
            "noise": np.array(noise), "K": np.array(kgrid)}


def floors(data: dict) -> dict:
    """floor = chi x integral(noise) / integral(observed) over 0 < k <= K_max_T, per probe."""
    df, K, out = data["df"], data["K"], {}
    for i, p in enumerate(data["probes"]):
        m = (K > 0) & (K <= df[f"K_max_T_{p}"].to_numpy()[:, None])
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = (np.trapezoid(np.where(m, data["noise"][:, i, :], 0.0), K, axis=1)
                    / np.trapezoid(np.where(m, data["obs"][:, i, :], 0.0), K, axis=1))
        out[p] = df[f"chi_{p}"].to_numpy() * frac
        data["df"][f"snr_{p}"] = 1.0 / frac
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
            raise ValueError(f"Unknown chi_qc.combine {how!r}")
    return np.where(n > 0, out, np.nan)


def qc(data: dict, seg: pd.DataFrame, cfg: dict, seg_enabled: bool, exclude: dict) -> tuple[pd.DataFrame, dict]:
    df = data["df"].merge(seg[["profile_file", "window", "keep"]].rename(columns={"keep": "segment_keep"}),
                          on=["profile_file", "window"], how="left", validate="one_to_one")
    if df["segment_keep"].isna().any():
        raise ValueError("chi windows missing from the segments table")
    probes = data["probes"]
    stem = df["profile_file"].str.split("_prof").str[0]
    seg_keep = df["segment_keep"].to_numpy(bool)
    base = seg_keep if seg_enabled else np.ones(len(df), bool)
    fl = floors(data)
    kc, fc, pair = cfg["k_max_ratio"], cfg["fom"], cfg["probe_pair"]
    counts = {"windows": len(df), "after_segment_qc": int(base.sum())}
    stage = {"probe_exclusion": 0, "k_max_ratio": 0, "fom": 0}
    use, fom_bad_any, kr_bad_any = {}, np.zeros(len(df), bool), np.zeros(len(df), bool)
    for p in probes:
        chi = df[f"chi_{p}"].to_numpy()
        ok = base & np.isfinite(chi)
        excl = stem.map(lambda s, p=p: p in exclude.get(f"{s}.P", exclude.get(f"{s}.p", []))).to_numpy(bool)
        stage["probe_exclusion"] += int((ok & excl).sum())
        ok &= ~excl
        kr_bad = df[f"K_max_ratio_{p}"].to_numpy() < kc["min"]
        kr_bad_any |= ok & kr_bad
        if kc["apply"]:
            stage["k_max_ratio"] += int((ok & kr_bad).sum())
            ok &= ~kr_bad
        fom = df[f"fom_{p}"].to_numpy()
        fom_bad = (fom > fc["band"]) | (fom < 1 / fc["band"])
        fom_bad_any |= ok & fom_bad
        if fc["apply"]:
            stage["fom"] += int((ok & fom_bad).sum())
            ok &= ~fom_bad
        use[p] = ok
        df[f"floor_{p}"] = fl[p]
    counts["probe_estimates_removed"] = stage

    c = np.column_stack([df[f"chi_{p}"].to_numpy() for p in probes])
    u = np.column_stack([use[p] for p in probes])
    disagree = np.zeros(len(df), bool)
    if len(probes) == 2:
        with np.errstate(invalid="ignore", divide="ignore"):
            lr = np.abs(np.log(c[:, 0] / c[:, 1]))
        disagree = u.all(axis=1) & (lr > np.log(pair["limit"]))
        df["probe_ratio"] = c[:, 0] / c[:, 1]
        if pair["policy"] == "min":
            larger = np.argmax(np.nan_to_num(c, nan=-np.inf), axis=1)
            u[disagree, larger[disagree]] = False
        elif pair["policy"] != "keep_both":
            raise ValueError(f"Unknown chi_qc.probe_pair.policy {pair['policy']!r}")
    for i, p in enumerate(probes):
        df[f"use_{p}"] = u[:, i]
    df["n_probes"] = u.sum(axis=1)
    df["chi"] = combine(c, u, cfg["combine"])
    df["chi_floor"] = combine(np.column_stack([fl[p] for p in probes]), u, cfg["combine"])
    df["epsilon_T"] = combine(np.column_stack([df[f"epsilon_T_{p}"].to_numpy() for p in probes]), u, cfg["combine"])
    df["kB"] = combine(np.column_stack([df[f"kB_{p}"].to_numpy() for p in probes]), u, cfg["combine"])
    nf = cfg["noise_floor"]
    at_floor = (np.isfinite(df["chi"]) & (df["chi"] < nf["factor"] * df["chi_floor"])).to_numpy()
    if nf["policy"] == "clamp":
        df["chi_bounded"] = np.fmax(df["chi"], df["chi_floor"])
    elif nf["policy"] == "none":
        df["chi_bounded"] = df["chi"]
    else:
        raise ValueError(f"Unknown chi_qc.noise_floor.policy {nf['policy']!r}")
    df.loc[~np.isfinite(df["chi"]), "chi_bounded"] = np.nan
    flags = np.zeros(len(df), int)
    for name, hit in [("no_usable_probe", ~np.isfinite(df["chi"].to_numpy())), ("probe_disagree", disagree),
                      ("at_floor", at_floor), ("fom_out_of_band", fom_bad_any),
                      ("low_k_max_ratio", kr_bad_any), ("segment_flagged", ~seg_keep)]:
        flags |= np.where(hit, BITS[name], 0)
    df["flags"] = flags
    df["at_floor"] = at_floor
    df["keep"] = np.isfinite(df["chi"]) & base
    k = df["keep"]
    counts.update({"no_usable_probe": int((base & ~np.isfinite(df["chi"])).sum()),
                   "probe_disagree": int(disagree.sum()), "kept": int(k.sum()),
                   "kept_at_floor_fraction": round(float((k & at_floor).sum() / max(k.sum(), 1)), 4),
                   "kept_fom_out_of_band_fraction": round(float((k & fom_bad_any).sum() / max(k.sum(), 1)), 4)})
    return df, counts


def agreement(df: pd.DataFrame, shear: pd.DataFrame, hyd: pd.DataFrame) -> pd.DataFrame:
    """epsilon_T vs shear epsilon where both are kept and shear is above its floor."""
    m = df[["profile_file", "window", "P_mean", "nu", "epsilon_T", "chi", "keep", "at_floor"]].merge(
        shear[["profile_file", "window", "epsilon_shear", "at_floor", "keep"]].rename(
            columns={"at_floor": "shear_at_floor", "keep": "shear_keep"}), on=["profile_file", "window"]).merge(
        hyd[["profile_file", "window", "N2", "Turner"]], on=["profile_file", "window"], how="left")
    m = m[m["keep"] & m["shear_keep"] & ~m["shear_at_floor"] & np.isfinite(m["epsilon_T"])
          & np.isfinite(m["epsilon_shear"])].copy()
    m["log_ratio"] = np.log10(m["epsilon_T"] / m["epsilon_shear"])
    with np.errstate(invalid="ignore", divide="ignore"):
        m["Re_b"] = np.where(m["N2"] > 0, m["epsilon_shear"] / (m["nu"] * m["N2"]), np.nan)
    return m


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def agreement_figure(results: dict, path: Path, foot: str) -> None:
    fig, axes = plt.subplots(2, len(results), figsize=(6.4 * len(results), 10.5), squeeze=False)
    for j, (name, r) in enumerate(results.items()):
        m = r["agree"]
        deep = m[m["P_mean"] > 150]
        ax = axes[0, j]
        for (lab, lo, hi), c in zip(REGIMES, (ps.MUTED, ps.BLUE, ps.ORANGE)):
            s = deep[(deep["Turner"] > lo) & (deep["Turner"] <= hi)]
            ax.scatter(s["epsilon_shear"], s["epsilon_T"], s=3, color=c, alpha=0.35, linewidths=0,
                       label=f"{lab}: n={len(s)}, median ratio {10 ** s['log_ratio'].median():.2f}")
        lim = [1e-12, 1e-5]
        ax.plot(lim, lim, color="k", lw=0.8)
        for f in (3, 1 / 3):
            ax.plot(lim, [v * f for v in lim], color="k", lw=0.5, ls="--")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel(r"$\epsilon_{shear}$ (above floor, W kg$^{-1}$)")
        ax.set_ylabel(r"$\epsilon_T$ (Kraichnan fit, W kg$^{-1}$)")
        ax.set_title(f"{name}: windows below 150 dbar", fontsize=10)
        ax.legend(fontsize=7.5, loc="upper left", markerscale=4)
        ax = axes[1, j]
        bins = [-1, 0.5, 1, 1.5, 2, 3, 7]
        for (lab, lo, hi), c in zip(REGIMES, (ps.MUTED, ps.BLUE, ps.ORANGE)):
            s = deep[(deep["Turner"] > lo) & (deep["Turner"] <= hi)]
            g = s.groupby(pd.cut(np.log10(s["Re_b"]), bins), observed=True)["log_ratio"]
            mid = [b.mid for b in g.median().index]
            ax.plot(mid, g.median(), "o-", color=c, label=lab)
            ax.fill_between(mid, g.quantile(0.25), g.quantile(0.75), color=c, alpha=0.15, lw=0)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xlabel(r"log$_{10}$ Re$_b$ = $\epsilon_{shear}$ / ($\nu N^2$)")
        ax.set_ylabel(r"log$_{10}$($\epsilon_T$ / $\epsilon_{shear}$), median and IQR")
        ax.legend(fontsize=8)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=105)
    plt.close(fig)


def gallery_figure(name: str, data: dict, df: pd.DataFrame, gal: dict, path: Path, foot: str) -> None:
    """Sample temperature-gradient spectra by chi decade (rows) and fom bin (columns)."""
    rng = np.random.default_rng(gal["seed"])
    fig, axes = plt.subplots(len(CHI_DECADES), len(FOM_BINS), figsize=(13, 13), sharex=True, squeeze=False)
    for i, (lo, hi) in enumerate(CHI_DECADES):
        for j, (flo, fhi) in enumerate(FOM_BINS):
            ax = axes[i, j]
            cand = []
            for pi, p in enumerate(data["probes"]):
                c, fom = df[f"chi_{p}"].to_numpy(), df[f"fom_{p}"].to_numpy()
                hit = (df["keep"] & df[f"use_{p}"] & (df["P_mean"] > 150)).to_numpy() & (c >= lo) & (c < hi) \
                    & (fom >= flo) & (fom < fhi)
                cand += [(w, pi) for w in np.flatnonzero(hit)]
            pick = [cand[k] for k in rng.choice(len(cand), min(gal["per_panel"], len(cand)), replace=False)] \
                if cand else []
            for col, (w, pi) in zip(GALLERY_COLORS, pick):
                p = data["probes"][pi]
                K = data["K"][w]
                ax.loglog(K[1:], data["obs"][w, pi, 1:], color=col, lw=0.9)
                ax.loglog(K[1:], data["model"][w, pi, 1:], color=col, lw=0.8, ls=":")
                ax.loglog(K[1:], data["noise"][w, pi, 1:], color=col, lw=0.6, ls="--", alpha=0.7)
                ax.axvline(df[f"K_max_T_{p}"].iloc[w], color=col, lw=0.6, alpha=0.6)
            ax.set_xlim(0.3, 400)
            ax.set_ylim(1e-9, 1e-1)
            ax.text(0.03, 0.04, f"n={len(cand)}", transform=ax.transAxes, fontsize=8)
            if i == 0:
                ax.set_title(f"fom {flo:.2f}–{fhi:.2f}" if np.isfinite(fhi) else f"fom > {flo:.2f}", fontsize=10)
            if j == 0:
                ax.set_ylabel(f"χ {lo:.0e}–{hi:.0e}\n" + r"Φ$_{T_z}$ (K$^2$ m$^{-2}$ cpm$^{-1}$)", fontsize=9)
            if i == len(CHI_DECADES) - 1:
                ax.set_xlabel("k (cpm)")
    fig.suptitle(f"{name}: temperature-gradient spectra (solid), fitted Kraichnan model (dotted), FP07 noise "
                 "(dashed), K_max (vertical); below 150 dbar", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    cfg = config["chi_qc"]
    seg_enabled = bool(config["segments"]["enabled"])
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ps.apply()
    report = {"segments_applied": seg_enabled, "chi_qc": cfg,
              "fit_method": config["perturb"]["chi"]["fit_method"], "instruments": {}}
    results = {}
    for name, inst in common.instruments(config):
        data = load(common.single_dir(ctx["run_dir"] / "convert" / name, "chi"))
        seg = pd.read_csv(ctx["run_dir"] / "segments" / f"segments_{name}.csv")
        df, counts = qc(data, seg, cfg, seg_enabled, inst.get("exclude_probes") or {})
        df.insert(0, "instrument", name)
        df.to_csv(out / f"thermistor_{name}.csv", index=False, float_format="%.6g")
        shear = pd.read_csv(ctx["run_dir"] / "epsilon_shear" / f"epsilon_shear_{name}.csv")
        hyd = pd.read_csv(ctx["run_dir"] / "hydrography" / f"windows_{name}.csv")
        agree = agreement(df, shear, hyd)
        deep = df[df["keep"] & (df["P_mean"] > 150)]
        ad = agree[agree["P_mean"] > 150]
        counts["chi_median_below_150"] = float(deep["chi"].median())
        counts["chi_floor_median_below_150"] = float(deep["chi_floor"].median())
        counts["at_floor_fraction_below_150"] = round(float(deep["at_floor"].mean()), 4)
        counts["snr_median_below_150"] = {p: float(deep[f"snr_{p}"].median()) for p in data["probes"]}
        counts["probe_ratio_median_below_150"] = float(np.nanmedian(deep.loc[deep["n_probes"] == 2, "probe_ratio"])) \
            if "probe_ratio" in deep else None
        counts["epsilon_T_vs_shear_below_150"] = {
            lab: {"n": int(((ad["Turner"] > lo) & (ad["Turner"] <= hi)).sum()),
                  "median_ratio": float(10 ** ad.loc[(ad["Turner"] > lo) & (ad["Turner"] <= hi), "log_ratio"].median()),
                  "iqr_log10": [float(ad.loc[(ad["Turner"] > lo) & (ad["Turner"] <= hi), "log_ratio"].quantile(q))
                                for q in (0.25, 0.75)]}
            for lab, lo, hi in REGIMES}
        report["instruments"][name] = counts
        results[name] = {"df": df, "agree": agree, "data": data}
        er = counts["epsilon_T_vs_shear_below_150"]
        print(f"  {name}: {counts['windows']} windows, kept {counts['kept']}; probe estimates removed "
              f"{counts['probe_estimates_removed']}; probes disagree {counts['probe_disagree']}; "
              f"below 150 dbar: chi median {counts['chi_median_below_150']:.1e}, at floor "
              f"{counts['at_floor_fraction_below_150']:.0%}; epsilon_T/shear "
              + ", ".join(f"{k} {v['median_ratio']:.2f} (n={v['n']})" for k, v in er.items()))
    agreement_figure(results, out / "figures" / "epsilon_T_vs_shear.png", foot)
    for name, r in results.items():
        gallery_figure(name, r["data"], r["df"], cfg["gallery"], out / "figures" / f"spectra_gallery_{name}.png", foot)
    common.write_json(out / "thermistor_report.json", report)
    common.write_step_metadata(out, STEP, ctx, segments_applied=seg_enabled)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
