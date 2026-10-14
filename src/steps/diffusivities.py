#!/usr/bin/env python3
"""Step diffusivities: bin-averaged diffusivities, finger attribution, per-cast finger metrics (CLAUDE.md step 8).

Built from the dd_test window table (same window selection, groups, regimes,
gradient choices), always from averages over windows and profiles, never per
window (T_z and S_z approach zero):

  K_T      = <chi> / (2 <T_z^2>)                 Osborn and Cox (1972); needs no epsilon
             for gradients = background (10 m fits), finescale (1 m gradient
             variance), interface_local (detected interface's own gradients)
  R_rho    = <alpha T_z> / <beta S_z>            bin density ratio (same gradients)
  K_S      = R_rho K_T / gamma                   finger-favourable sets only, 1 < R_rho <=
                                                 k_s_max_r_rho, for each gamma in diffusivities.gammas
  K_S_eps  = <eps> (R_rho - 1) / (<N2> (1 - gamma))  independent finger check
  K_rho    = 0.2 <eps> / <N2>                    Osborn (1980); not valid where finger
                                                 dominated (finger_set flag)
  K_GM     = canonical Garrett-Munk level at the bin's N and latitude (reference)

with 95% bootstrap intervals over profiles (uncertainty.bootstrap_samples).
Nitrate behaves like salt in fingering (low molecular diffusivity), so K_S is the
diffusivity relevant to nutrient fluxes computed outside this repository.

Attribution (finger fraction of the heat-variance budget, f = 1 - 1/E) against
each baseline of the ladder (decisions.md 2026-10-14): Gamma = 0.2 theory
(E = R from dd_pooled), the GM level (E = K_T / K_GM), and the Re_b-matched
doubly stable control (E from dd_excess). The spread is the baseline uncertainty.

Per-cast metrics (one row per profile) for mesoscale comparisons: salinity
maximum depth, finger-favourable fraction and R_rho over the test range,
staircase occurrence and geometry per method, interface and finger-water K_T
relative to K_GM, mean epsilon and chi.

Reads:  <run_dir>/dd_test/{dd_windows,dd_pooled,dd_gm,dd_excess}.csv
        <run_dir>/regimes/steps_<instrument>.csv, <run_dir>/hydrography/hydrography_<instrument>.nc
Writes: <run_dir>/diffusivities/
          diffusivity_bins.csv     group x regime x staircase x gradients x depth bin (and pooled)
          attribution.csv          finger fraction per baseline
          cast_metrics_<instrument>.csv
          figures/*.png, diffusivities_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from dd_test import k_gm, regime_sets  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "diffusivities"
FINGER_SETS = ("finger_any", "strong_finger")


def gradient_frame(d: pd.DataFrame, grad: str, method: str) -> pd.DataFrame:
    """Columns tz2, atz, bsz for the chosen gradients (NaN rows dropped)."""
    if grad == "background":
        out = d.assign(tz2=d["T_z"] ** 2, atz=d["alpha"] * d["T_z"], bsz=d["beta"] * d["S_z"])
    elif grad == "finescale":
        # finescale changes T_z^2 only; R_rho stays the background value
        out = d.assign(tz2=d["T_z2_fine"], atz=d["alpha"] * d["T_z"], bsz=d["beta"] * d["S_z"])
    elif grad == "interface_local":
        tz, sz = d[f"T_z_iface_{method}"], d[f"S_z_iface_{method}"]
        out = d.assign(tz2=tz ** 2, atz=d["alpha"] * tz, bsz=d["beta"] * sz)
    else:
        raise ValueError(grad)
    return out[np.isfinite(out["tz2"]) & np.isfinite(out["atz"]) & np.isfinite(out["bsz"])]


def estimates(sums: np.ndarray, gammas, n2_lat) -> dict:
    """Diffusivities from summed per-window quantities (chi, tz2, atz, bsz, eps, N2, n)."""
    chi, tz2, atz, bsz, eps, n2, n = sums
    kt = chi / (2 * tz2)
    rr = atz / bsz if bsz > 0 else np.nan
    out = {"K_T": kt, "R_rho": rr, "K_rho": 0.2 * eps / n2, "eps_mean": eps / n, "N2_mean": n2 / n,
           "chi_mean": chi / n}
    for g in gammas:
        out[f"K_S_g{g:g}"] = rr * kt / g if rr > 1 else np.nan
        out[f"K_S_eps_g{g:g}"] = (eps / n) * (rr - 1) / ((n2 / n) * (1 - g)) if rr > 1 else np.nan
    return out


def bin_estimates(d: pd.DataFrame, gammas, gm_cfg, n_boot, rng, ci_keys) -> dict:
    cols = ["chi_obs", "tz2", "atz", "bsz", "epsilon_used", "N2"]
    per = d.groupby("profile_file")[cols].sum()
    per["n"] = d.groupby("profile_file").size()
    tot = per.sum().to_numpy()
    r = {"n_windows": len(d), "n_profiles": len(per), **estimates(tot, gammas, None)}
    r["K_GM"] = float(k_gm(r["N2_mean"], d["lat"].mean(), gm_cfg))
    if len(per) >= 2 and n_boot > 0:
        arr = per.to_numpy()
        idx = rng.integers(0, len(per), size=(n_boot, len(per)))
        boot = {k: [] for k in ci_keys}
        for row in idx:
            e = estimates(arr[row].sum(axis=0), gammas, None)
            for k in ci_keys:
                boot[k].append(e[k])
        for k in ci_keys:
            v = np.array(boot[k], float)
            r[f"{k}_ci_low"], r[f"{k}_ci_high"] = (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))) \
                if np.isfinite(v).any() else (np.nan, np.nan)
    return r


def cast_metrics(w: pd.DataFrame, steps: pd.DataFrame, hyd: xr.Dataset, methods, gm_cfg) -> pd.DataFrame:
    zc = hyd["depth"].values
    rows = []
    for i, pf in enumerate(hyd["profile_file"].values):
        d = w[w["profile_file"] == pf]
        sa = hyd["SA_used"].values[i]
        shallow = (zc > 20) & (zc < 250) & np.isfinite(sa)
        r = {"profile_file": pf, "lat": float(hyd["lat"].values[i]), "lon": float(hyd["lon"].values[i]),
             "stime": float(hyd["stime"].values[i]),
             "SA_max_depth_m": float(zc[shallow][np.nanargmax(sa[shallow])]) if shallow.sum() > 20 else np.nan,
             "SA_max": float(np.nanmax(sa[shallow])) if shallow.sum() > 20 else np.nan}
        t = d[d["in_test"]] if len(d) else d
        r["windows_test_range"] = len(t)
        if len(t):
            fing = t["turner_class"].isin(["finger", "strong_finger"])
            r["finger_fraction"] = float(fing.mean())
            r["strong_finger_fraction"] = float((t["turner_class"] == "strong_finger").mean())
            r["R_rho_median"] = float(np.nanmedian(t["R_rho"]))
            r["finger_depth_top_m"] = float(t.loc[fing, "depth"].min()) if fing.any() else np.nan
            r["finger_depth_bottom_m"] = float(t.loc[fing, "depth"].max()) if fing.any() else np.nan
            r["epsilon_mean"] = float(t["epsilon_used"].mean())
            r["chi_mean"] = float(t["chi_obs"].mean())
            f = t[fing]
            if len(f):
                n2 = f["N2"].mean()
                kgm = float(k_gm(n2, f["lat"].mean(), gm_cfg))
                r["K_T_finger_finescale"] = float(f["chi_obs"].sum() / (2 * f["T_z2_fine"].sum()))
                r["K_T_finger_over_GM"] = r["K_T_finger_finescale"] / kgm
            for m in methods:
                lab = t[f"staircase_{m}"]
                r[f"staircase_fraction_{m}"] = float(lab.isin(["interface", "layer", "straddles"]).mean())
                fi = f[f[f"staircase_{m}"] == "interface"] if len(f) else f
                if len(fi):
                    kgm_i = float(k_gm(fi["N2"].mean(), fi["lat"].mean(), gm_cfg))
                    r[f"K_T_interface_finescale_{m}"] = float(fi["chi_obs"].sum() / (2 * fi["T_z2_fine"].sum()))
                    r[f"K_T_interface_over_GM_{m}"] = r[f"K_T_interface_finescale_{m}"] / kgm_i
        for m in methods:
            s = steps[(steps["profile_file"] == pf) & (steps["method"] == m) & (steps["p"] > 150)] if len(steps) else steps
            ifc = s[s["kind"] == "interface"] if len(s) else s
            lay = s[s["kind"] == "layer"] if len(s) else s
            r[f"n_interfaces_{m}"] = int(len(ifc))
            r[f"interface_dCT_median_{m}"] = float(ifc["ct_range"].median()) if len(ifc) else np.nan
            r[f"interface_dSA_median_{m}"] = float(ifc["sa_range"].median()) if len(ifc) else np.nan
            r[f"interface_thickness_median_m_{m}"] = float(ifc["layer_height"].median()) if len(ifc) else np.nan
            r[f"layer_thickness_median_m_{m}"] = float(lay["layer_height"].median()) if len(lay) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def profile_figure(tab, groups, gammas, path, foot):
    gs = [g for g in groups if "all free fall" in g] or groups
    fig, axes = plt.subplots(1, len(gs), figsize=(5.4 * len(gs), 7), squeeze=False)
    g0 = gammas[len(gammas) // 2]
    for ax, g in zip(axes[0], gs):
        b = tab[(tab["instrument_group"] == g) & (tab["depth_bin"] != "pooled")].copy()
        b["z"] = b["depth_bin"].astype(float)
        f = b[(b["turner"] == "finger_any") & (b["staircase"] == "all") & (b["gradients"] == "finescale")].sort_values("z")
        ax.fill_betweenx(f["z"], f[f"K_S_g{max(gammas):g}"], f[f"K_S_g{min(gammas):g}"], color=ps.ORANGE, alpha=0.2, lw=0,
                         label=f"K_S finger water, γ {min(gammas):g}–{max(gammas):g}")
        ax.plot(f[f"K_S_g{g0:g}"], f["z"], color=ps.ORANGE, lw=1.6, label=f"K_S (γ={g0:g})")
        ax.plot(f["K_T"], f["z"], color=ps.RED, lw=1.2, label="K_T finger water")
        c = b[(b["turner"] == "control") & (b["staircase"] == "all") & (b["gradients"] == "finescale")].sort_values("z")
        ax.plot(c["K_T"], c["z"], color=ps.BLUE, lw=1.2, marker="o", ms=2, label="K_T doubly stable (control)")
        a = b[(b["turner"] == "all_turner") & (b["staircase"] == "all") & (b["gradients"] == "background")].sort_values("z")
        allz = pd.concat([a, c]).sort_values("z").drop_duplicates("z")
        ax.plot(allz["K_GM"], allz["z"], color="k", lw=1.5, ls="--", label="Garrett–Munk")
        ax.plot(a["K_rho"], a["z"], color=ps.MUTED, lw=1, ls=":", label="K_ρ = 0.2⟨ε⟩/⟨N²⟩")
        ax.set_xscale("log")
        ax.set_xlim(1e-7, 1e-3)
        ax.invert_yaxis()
        ax.set_xlabel("diffusivity (m² s⁻¹), bin averages (finescale gradients)")
        ax.set_ylabel("pressure (dbar)")
        ax.set_title(g, fontsize=9)
        ax.legend(fontsize=6.5, loc="lower right")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def cast_map_figure(cm: dict, methods, path, foot):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    for ax, (col, lab) in zip(axes, ((f"staircase_fraction_{methods[-1]}", "staircase fraction (150 dbar+)"),
                                     ("K_T_finger_over_GM", "K_T finger water / K_GM"))):
        vals = pd.concat([v.assign(inst=k) for k, v in cm.items()])
        v = vals[np.isfinite(vals.get(col, np.nan))] if col in vals else vals.iloc[0:0]
        for inst, mk in (("vmp250", "o"), ("vmp5500", "s")):
            s = v[v["inst"] == inst]
            sc = ax.scatter(s["lon"], s["lat"], c=s[col], s=26 if inst == "vmp5500" else 12, marker=mk,
                            cmap=ps.SEQ_CHI, edgecolors="k", linewidths=0.3, label=inst,
                            norm=None if "fraction" in col else plt.matplotlib.colors.LogNorm(0.3, 30))
        plt.colorbar(sc, ax=ax, label=lab)
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.legend(fontsize=8)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    dd, dc = config["double_diffusion"], config["diffusivities"]
    unc = config["uncertainty"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ps.apply()
    rng = np.random.default_rng(unc["random_seed"])
    methods = config["regimes"]["staircase"]["methods"]
    gammas = [float(g) for g in dc["gammas"]]
    g0 = float(dd["flux_ratio_gamma"])
    ci_keys = ["K_T", "R_rho", "K_rho", f"K_S_g{g0:g}", f"K_S_eps_g{g0:g}"]
    w = pd.read_csv(ctx["run_dir"] / "dd_test" / "dd_windows.csv", low_memory=False)
    groups = sorted(w["instrument_group"].unique())

    rows = []
    for g in groups:
        dg = w[w["instrument_group"] == g]
        dg.attrs["control_max"] = dd["control_max_turner_deg"]
        for m in methods:
            for (tname, sname), sel in regime_sets(dg, m).items():
                if tname == "not_finger":
                    continue
                d0 = dg[sel]
                grads = ["background", "finescale"] + (["interface_local"] if sname == "interface" else [])
                for grad in grads:
                    d = gradient_frame(d0, grad, m)
                    if len(d) < dc["min_windows"]:
                        continue
                    base = {"instrument_group": g, "method": m, "turner": tname, "staircase": sname, "gradients": grad,
                            "finger_set": tname in FINGER_SETS}
                    rows.append({**base, "depth_bin": "pooled", **bin_estimates(d, gammas, dd["gm"], unc["bootstrap_samples"],
                                                                                rng, ci_keys)})
                    for zb, db in d.groupby("depth_bin"):
                        if len(db) >= dc["min_windows"]:
                            rows.append({**base, "depth_bin": zb,
                                         **bin_estimates(db, gammas, dd["gm"], unc["bootstrap_samples"], rng, ci_keys)})
    tab = pd.DataFrame(rows)
    # K_S applies only to finger-favourable sets with R_rho <= k_s_max_r_rho (fingers weaken at high
    # R_rho and the finger formula would grow with R_rho regardless); K_rho is not valid in finger sets
    tab["K_S_applicable"] = tab["finger_set"] & (tab["R_rho"] > 1) & (tab["R_rho"] <= dc["k_s_max_r_rho"])
    for g in gammas:
        cols = [c for c in tab.columns if c.startswith((f"K_S_g{g:g}", f"K_S_eps_g{g:g}"))]
        tab.loc[~tab["K_S_applicable"], cols] = np.nan
    tab["K_rho_valid"] = ~tab["finger_set"]
    tab["min_profiles_ok"] = tab["n_profiles"] >= dd["min_profiles_per_average"]
    tab["gammas"] = ",".join(f"{g:g}" for g in gammas)
    tab["epsilon_source"] = dd["epsilon_source"]
    tab.to_csv(out / "diffusivity_bins.csv", index=False, float_format="%.6g")

    # Attribution ladder (pooled, finger-favourable, last staircase method)
    pooled = pd.read_csv(ctx["run_dir"] / "dd_test" / "dd_pooled.csv")
    gmt = pd.read_csv(ctx["run_dir"] / "dd_test" / "dd_gm.csv")
    exc = pd.read_csv(ctx["run_dir"] / "dd_test" / "dd_excess.csv")
    m = methods[-1]
    att = []
    for g in groups:
        for sname in ("all", "interface", "layer", "none"):
            for grad in ("background", "finescale", "interface_local"):
                e = {}
                p = pooled[(pooled["instrument_group"] == g) & (pooled["method"] == m) & (pooled["turner"] == "finger_any")
                           & (pooled["staircase"] == sname) & (pooled["gradients"] == grad) & (pooled["n2_filter"] == "all")]
                if len(p):
                    e["theory_Gamma0.2"] = (p["ratio"].iloc[0], p["ratio_lo"].iloc[0], p["ratio_hi"].iloc[0])
                k = tab[(tab["instrument_group"] == g) & (tab["method"] == m) & (tab["turner"] == "finger_any")
                        & (tab["staircase"] == sname) & (tab["gradients"] == grad) & (tab["depth_bin"] == "pooled")]
                if len(k):
                    kk = k.iloc[0]
                    e["garrett_munk"] = (kk["K_T"] / kk["K_GM"], kk.get("K_T_ci_low", np.nan) / kk["K_GM"],
                                         kk.get("K_T_ci_high", np.nan) / kk["K_GM"])
                x = exc[(exc["instrument_group"] == g) & (exc["method"] == m) & (exc["staircase"] == sname)
                        & (exc["gradients"] == grad)]
                if len(x):
                    e["matched_control"] = (x["excess"].iloc[0], x["excess_lo"].iloc[0], x["excess_hi"].iloc[0])
                for base, (val, lo, hi) in e.items():
                    att.append({"instrument_group": g, "method": m, "staircase": sname, "gradients": grad,
                                "baseline": base, "E": val, "E_ci_low": lo, "E_ci_high": hi,
                                "finger_fraction": 1 - 1 / val if val > 0 else np.nan,
                                "finger_fraction_ci_low": 1 - 1 / lo if lo > 0 else np.nan,
                                "finger_fraction_ci_high": 1 - 1 / hi if hi > 0 else np.nan})
    att = pd.DataFrame(att)
    att.to_csv(out / "attribution.csv", index=False, float_format="%.4g")

    # Per-cast metrics
    cms = {}
    for name, _ in common.instruments(config):
        hyd = xr.open_dataset(ctx["run_dir"] / "hydrography" / f"hydrography_{name}.nc")
        steps = pd.read_csv(ctx["run_dir"] / "regimes" / f"steps_{name}.csv")
        wi = w[w["instrument_group"].str.startswith(name) & ~w["instrument_group"].str.contains("all free fall")]
        cm = cast_metrics(wi, steps, hyd, methods, dd["gm"])
        cm.insert(0, "instrument", name)
        cm.to_csv(out / f"cast_metrics_{name}.csv", index=False, float_format="%.6g")
        cms[name] = cm

    profile_figure(tab, groups, gammas, out / "figures" / "diffusivity_profiles.png", foot)
    cast_map_figure(cms, methods, out / "figures" / "cast_metrics_map.png", foot)
    report = {"gammas": gammas, "groups": {}}
    for g in groups:
        k = tab[(tab["instrument_group"] == g) & (tab["depth_bin"] == "pooled") & (tab["method"] == m)
                & (tab["turner"] == "finger_any") & (tab["gradients"] == "finescale")]
        report["groups"][g] = {row["staircase"]: {"K_T": row["K_T"], f"K_S_g{g0:g}": row[f"K_S_g{g0:g}"],
                                                  "K_GM": row["K_GM"], "n_profiles": int(row["n_profiles"])}
                               for _, row in k.iterrows()}
    common.write_json(out / "diffusivities_report.json", report)
    common.write_step_metadata(out, STEP, ctx)
    show = tab[(tab["depth_bin"] == "pooled") & (tab["method"] == m) & (tab["turner"].isin(["finger_any", "control"]))
               & (tab["staircase"].isin(["all", "interface", "layer"])) & (tab["gradients"] == "finescale")
               & tab["instrument_group"].str.contains("all free fall")]
    for _, d in show.iterrows():
        print(f"  {d['instrument_group']:22s} {d['turner']:10s} {d['staircase']:9s} K_T {d['K_T']:.2e} "
              f"[{d.get('K_T_ci_low', np.nan):.1e},{d.get('K_T_ci_high', np.nan):.1e}]  K_S(γ={g0:g}) "
              f"{d[f'K_S_g{g0:g}']:.2e} [{d.get(f'K_S_g{g0:g}_ci_low', np.nan):.1e},{d.get(f'K_S_g{g0:g}_ci_high', np.nan):.1e}]"
              f"  K_S_eps {d[f'K_S_eps_g{g0:g}']:.2e}  K_rho {d['K_rho']:.2e}  K_GM {d['K_GM']:.2e}  R_rho {d['R_rho']:.2f}")


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
