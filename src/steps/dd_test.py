#!/usr/bin/env python3
"""Step dd_test: is chi larger than shear-driven turbulence can explain? (CLAUDE.md step 7)

Ratio of averages (Fernandez-Castro et al. 2024): per window
    chi_expected = 2 K_rho T_z^2,   K_rho = flux_coefficient * epsilon / N2  (Osborn 1980)
then chi_observed and chi_expected are averaged SEPARATELY over all windows of a
group, regime and depth bin, and R = <chi_observed> / <chi_expected>. The
per-window dissipation ratio is never formed (T_z and N2 approach zero).

  * epsilon: double_diffusion.epsilon_source. `shear` uses epsilon_shear_bounded
    (max of epsilon and its noise floor), so chi_expected is an upper bound and R
    a lower bound where shear is at its floor. `thermistor` uses epsilon_T where
    the Batchelor roll-off is resolved.
  * Windows used: shear and chi kept, N2 > 0, finite T_z, inside depth_range_dbar,
    not ts_salinity_invalid (T-S salinity in a temperature inversion).
  * Groups: station groups (cast_log `station`; casts outside a station are
    `transect`) x instrument x tow-yo / free fall (tow-yo profiles are never
    pooled with free-fall casts). With pool_free_fall, all free-fall casts of an
    instrument in the selected groups are also tested together ("all free fall").
  * Control: doubly stable water, -45 < Tu < control_max_turner_deg (25 m Turner
    angle, away from the 45 deg finger boundary and excluding diffusive
    convection), T_z > 0 at the window scale (no temperature inversion, which
    marks intrusions), taken over control_depth_range_dbar (which reaches above
    the shallow salinity maximum). Finger and other regime sets use
    depth_range_dbar.
  * Excess over the Re_b-matched control (dd_excess.csv): the control's ratio in
    each Re_b bin, R_c(b), calibrates the Gamma = 0.2 expectation empirically;
    for a target set E = sum(chi_obs) / sum(chi_exp * R_c(b_window)). E = 1 means
    indistinguishable from doubly stable water at the same Re_b. The control is
    the instrument's "all free fall" control (excess_control_group); windows in
    Re_b bins with fewer than excess_min_control_windows control windows are
    left out (counted). 95% bootstrap resamples target and control profiles
    independently.
  * Garrett-Munk reference level (dd_gm.csv; Gregg 1989, Kunze et al. 2006):
    K_GM = K0 L(f, N), L = f arccosh(N/f) / (f30 arccosh(N0/f30)), the canonical
    internal-wave diapycnal diffusivity at the bin's N and latitude (Gamma 0.2
    implied in K0). Compared with bin-averaged K_T = <chi> / (2 <T_z^2>)
    (Osborn and Cox; background and finescale T_z^2) and K_rho = 0.2 <eps>/<N2>,
    per group x regime x staircase label x depth bin. A reference level for
    context, not a test: GM is climatological, and finescale (strain-based)
    versions are invalid inside staircases.
  * Re_b: R is also computed in buoyancy Reynolds number bins (re_b_bins) for
    finger-favourable windows and for the control, so the two are compared at
    matched turbulence intensity (Gamma = 0.2 is an active-turbulence value).
  * Regimes: Turner class (from the regimes step) x staircase label, one set per
    staircase method; interfaces and layers are never pooled.
  * Uncertainty: bootstrap over profiles (uncertainty.bootstrap_samples, seed).
  * Finger model (St. Laurent and Schmitt 1999): R_finger = Gamma_finger / 0.2,
    Gamma_finger = [(R_rho - 1) / R_rho] [gamma / (1 - gamma)], with the bin's
    R_rho = <alpha T_z> / <beta S_z> and gamma = flux_ratio_gamma.
    R is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency;
    R > 1 means "not explainable by shear-driven turbulence with Gamma = 0.2".
  * Robustness: everything repeated with the weakest exclude_weakest_n2_percent
    of N2 (per group) removed.
  * Gradients: chi_expected uses the hydrography step's background gradients
    (linear fits over hydrography.gradient_smoothing_m), which at a thin
    interface average the interface with the layers around it. For windows
    labelled interface, a second estimate uses the interface's own gradients
    from the regimes step table: T_z = CT range / thickness, S_z = SA range /
    thickness (signs of the background), N2 = g (alpha T_z - beta S_z), from
    the detected interface overlapping the window most. Reported as
    gradients = interface_local next to gradients = background.
    A third estimate, gradients = finescale, applies to every window: T_z^2 is
    replaced by the mean squared temperature gradient on the hydrography 1 m
    grid over the window's extent (N2 stays the background value). Intrusive
    finestructure makes the 1 m gradient variance much larger than the
    background T_z^2 in some windows, and the ratio of averages is dominated by
    them (decisions.md 2026-10-14).
  * Depth range per instrument: double_diffusion.depth_range_dbar.

Reads:  <run_dir>/regimes/{regimes,steps}_<instrument>.csv, <run_dir>/cast_log/casts_<instrument>.csv
Writes: <run_dir>/dd_test/
          dd_bins.csv        group x method x regime x depth bin
          dd_pooled.csv      group x method x regime over the whole depth range
          figures/*.png, dd_test_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import gsw
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "dd_test"
FINGER = ("finger", "strong_finger")
LABEL_COLOR = {"interface": ps.ORANGE, "layer": ps.BLUE, "straddles": ps.AQUA, "none": ps.MUTED, "all": "k"}


def regime_sets(df: pd.DataFrame, method: str) -> dict[str, pd.Series]:
    """Named boolean selections: Turner group x staircase label for one method."""
    lab = df[f"staircase_{method}"]
    tc = df["turner_class"]
    out = {}
    tu = df["Turner_smooth"]
    t = df["in_test"]
    control = (tu > -45) & (tu < df.attrs.get("control_max", 30)) & (df["T_z"] > 0) & df["in_control_range"]
    for tname, tsel in (("all_turner", t), ("finger_any", t & tc.isin(FINGER)),
                        ("strong_finger", t & (tc == "strong_finger")), ("not_finger", t & (tc == "not_finger")),
                        ("control", control)):
        for sname in ("all", "interface", "layer", "straddles", "none"):
            ssel = pd.Series(True, index=df.index) if sname == "all" else (lab == sname)
            out[(tname, sname)] = tsel & ssel
    return out


def ratio_stats(d: pd.DataFrame, gamma: float, n_boot: int, rng) -> dict:
    """Ratio of averages with a bootstrap over profiles, plus the finger prediction."""
    obs, exp = d["chi_obs"].to_numpy(), d["chi_exp"].to_numpy()
    r = {"n_windows": len(d), "n_profiles": d["profile_file"].nunique(),
         "chi_obs_mean": float(obs.mean()), "chi_exp_mean": float(exp.mean()),
         "ratio": float(obs.mean() / exp.mean()) if exp.mean() > 0 else np.nan,
         "at_floor_fraction": float(d["shear_at_floor"].mean())}
    at, bs = (d["alpha"] * d["T_z"]).mean(), (d["beta"] * d["S_z"]).mean()
    rr = at / bs if bs > 0 else np.nan
    r["R_rho_bin"] = float(rr)
    r["finger_prediction"] = float(((rr - 1) / rr) * (gamma / (1 - gamma)) / 0.2) if rr > 1 else np.nan
    profs = d["profile_file"].unique()
    if len(profs) >= 2 and n_boot > 0:
        g = d.groupby("profile_file")[["chi_obs", "chi_exp"]].agg(["sum", "count"])
        so, se, n = g[("chi_obs", "sum")].to_numpy(), g[("chi_exp", "sum")].to_numpy(), g[("chi_obs", "count")].to_numpy()
        idx = rng.integers(0, len(profs), size=(n_boot, len(profs)))
        nb = n[idx].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            boot = (so[idx].sum(axis=1) / nb) / (se[idx].sum(axis=1) / nb)
        r["ratio_lo"], r["ratio_hi"] = (float(np.nanpercentile(boot, 2.5)), float(np.nanpercentile(boot, 97.5)))
    else:
        r["ratio_lo"] = r["ratio_hi"] = np.nan
    return r


def excess_stats(target: pd.DataFrame, control: pd.DataFrame, edges, min_ctrl: int, n_boot: int, rng) -> dict:
    """Excess of target chi over the Re_b-matched control expectation, with a two-sample profile bootstrap."""
    tb = np.digitize(target["Re_b_shear"].to_numpy(), edges) - 1
    cb = np.digitize(control["Re_b_shear"].to_numpy(), edges) - 1
    nb = len(edges) - 1

    def calib(c_obs, c_exp, c_bin):
        so = np.bincount(c_bin[(c_bin >= 0) & (c_bin < nb)], weights=c_obs[(c_bin >= 0) & (c_bin < nb)], minlength=nb)
        se = np.bincount(c_bin[(c_bin >= 0) & (c_bin < nb)], weights=c_exp[(c_bin >= 0) & (c_bin < nb)], minlength=nb)
        n = np.bincount(c_bin[(c_bin >= 0) & (c_bin < nb)], minlength=nb)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = so / se
        r[n < min_ctrl] = np.nan
        return r

    def excess(t_obs, t_exp, t_bin, rc):
        f = rc[np.clip(t_bin, 0, nb - 1)]
        f[(t_bin < 0) | (t_bin >= nb)] = np.nan
        ok = np.isfinite(f)
        return (t_obs[ok].sum() / (t_exp[ok] * f[ok]).sum()) if ok.any() else np.nan, ok

    rc = calib(control["chi_obs"].to_numpy(), control["chi_exp"].to_numpy(), cb)
    e, ok = excess(target["chi_obs"].to_numpy(), target["chi_exp"].to_numpy(), tb, rc)
    out = {"excess": float(e), "n_windows": len(target), "n_windows_matched": int(ok.sum()),
           "n_profiles": target["profile_file"].nunique(), "n_control_windows": len(control),
           "ratio_raw": float(target["chi_obs"].sum() / target["chi_exp"].sum()),
           "Re_b_median": float(np.nanmedian(target["Re_b_shear"]))}
    tp, cp = target["profile_file"].to_numpy(), control["profile_file"].to_numpy()
    tu, cu = np.unique(tp), np.unique(cp)
    if len(tu) >= 2 and len(cu) >= 2 and n_boot > 0:
        t_idx = {p: np.flatnonzero(tp == p) for p in tu}
        c_idx = {p: np.flatnonzero(cp == p) for p in cu}
        boot = []
        for _ in range(n_boot):
            ti = np.concatenate([t_idx[p] for p in rng.choice(tu, len(tu))])
            ci = np.concatenate([c_idx[p] for p in rng.choice(cu, len(cu))])
            rcb = calib(control["chi_obs"].to_numpy()[ci], control["chi_exp"].to_numpy()[ci], cb[ci])
            boot.append(excess(target["chi_obs"].to_numpy()[ti], target["chi_exp"].to_numpy()[ti], tb[ti], rcb)[0])
        out["excess_lo"], out["excess_hi"] = float(np.nanpercentile(boot, 2.5)), float(np.nanpercentile(boot, 97.5))
    else:
        out["excess_lo"] = out["excess_hi"] = np.nan
    return out


def k_gm(n2, lat, gm: dict) -> np.ndarray:
    """Canonical GM diapycnal diffusivity at buoyancy frequency sqrt(n2) and latitude lat."""
    om = 7.2921e-5
    f = np.abs(2 * om * np.sin(np.deg2rad(lat)))
    f30 = 2 * om * np.sin(np.deg2rad(gm["f_ref_lat_deg"]))
    n = np.sqrt(np.clip(n2, 0, None))
    with np.errstate(invalid="ignore", divide="ignore"):
        lfn = f * np.arccosh(np.maximum(n / f, 1)) / (f30 * np.arccosh(gm["N0_rad_s"] / f30))
    return gm["K0_m2_s"] * lfn


def gm_stats(d: pd.DataFrame, gm: dict) -> dict:
    n2 = d["N2"].mean()
    return {"n_windows": len(d), "n_profiles": d["profile_file"].nunique(), "N2_mean": float(n2),
            "K_T_background": float(d["chi_obs"].mean() / (2 * (d["T_z"] ** 2).mean())),
            "K_T_finescale": float(d["chi_obs"].mean() / (2 * d["T_z2_fine"].mean())),
            "K_rho_measured": float(0.2 * d["epsilon_used"].mean() / n2),
            "K_GM": float(k_gm(n2, d["lat"].mean(), gm))}


def prepare(ctx, name, config) -> pd.DataFrame:
    dd = config["double_diffusion"]
    rd = ctx["run_dir"]
    df = pd.read_csv(rd / "regimes" / f"regimes_{name}.csv")
    casts = pd.read_csv(rd / "cast_log" / f"casts_{name}.csv", dtype=str)
    casts["stem"] = casts["file"].str.rsplit(".", n=1).str[0]
    stem = df["profile_file"].str.split("_prof").str[0]
    df["station"] = stem.map(casts.set_index("stem")["station"]).fillna("")
    df["towyo"] = stem.map(casts.set_index("stem")["towyo"]).fillna("False") == "True"
    if dd["epsilon_source"] == "shear":
        eps = df["epsilon_shear_bounded"]
    elif dd["epsilon_source"] == "thermistor":
        eps = df["epsilon_T"].where(df["epsilon_T_resolved"].fillna(False).astype(bool))
    else:
        raise ValueError(f"Unknown double_diffusion.epsilon_source {dd['epsilon_source']!r}")
    lo, hi = dd["depth_range_dbar"][name]
    clo, chi_ = dd["control_depth_range_dbar"][name]
    ok = (df["shear_keep"].fillna(False).astype(bool) & df["chi_keep"].fillna(False).astype(bool)
          & (df["N2"] > 0) & np.isfinite(df["T_z"]) & np.isfinite(eps) & np.isfinite(df["chi"])
          & ~df["ts_salinity_invalid"].fillna(False).astype(bool)
          & (df["P_mean"] >= min(lo, clo)) & (df["P_mean"] < max(hi, chi_)))
    df = df[ok].copy()
    df["epsilon_used"] = eps[ok]
    df["in_test"] = (df["P_mean"] >= lo) & (df["P_mean"] < hi)
    df["in_control_range"] = (df["P_mean"] >= clo) & (df["P_mean"] < chi_)
    df["chi_obs"] = df["chi"]
    df["chi_exp"] = 2 * dd["flux_coefficient"] * df["epsilon_used"] / df["N2"] * df["T_z"] ** 2
    b = dd["depth_bin_m"]
    df["depth_bin"] = np.floor(df["P_mean"] / b) * b + b / 2
    df["station"] = df["station"].where(df["station"] != "", "transect")
    df["group"] = df["station"] + np.where(df["towyo"], " tow-yo", " free fall")
    df.insert(0, "instrument_group", name + " " + df["group"])

    # Finescale (1 m grid) temperature-gradient variance over each window
    hyd = xr.open_dataset(rd / "hydrography" / f"hydrography_{name}.nc")
    zc = hyd["depth"].values
    row = {f: k for k, f in enumerate(hyd["profile_file"].values)}
    hw = df["speed"] * float(config["perturb"]["epsilon"]["diss_sec"]) / 2
    fine = np.full(len(df), np.nan)
    grads = {}
    for k, (pf, dep, h) in enumerate(zip(df["profile_file"], df["depth"], hw)):
        if pf not in grads:
            grads[pf] = -np.gradient(hyd["CT"].values[row[pf]], zc)        # z up
        sel = (zc >= dep - h) & (zc <= dep + h)
        if sel.any():
            fine[k] = np.nanmean(grads[pf][sel] ** 2)
    df["T_z2_fine"] = fine
    lat = hyd["lat"].values
    df["lat"] = df["profile_file"].map({f: (float(lat[k]) if np.isfinite(lat[k]) else 12.0) for f, k in row.items()})
    df["chi_exp_fine"] = 2 * dd["flux_coefficient"] * df["epsilon_used"] / df["N2"] * df["T_z2_fine"]

    # Interface-local gradients for windows labelled interface, per staircase method
    steps = pd.read_csv(rd / "regimes" / f"steps_{name}.csv")
    half = df["speed"] * float(config["perturb"]["epsilon"]["diss_sec"]) / 2
    pc = gsw.p_from_z(-df["depth"].to_numpy(), 12.0)
    for m in config["regimes"]["staircase"]["methods"]:
        ifc = steps[(steps["method"] == m) & (steps["kind"] == "interface")]
        by_prof = {k: g for k, g in ifc.groupby("profile_file")}
        tz, sz = np.full(len(df), np.nan), np.full(len(df), np.nan)
        lab = df[f"staircase_{m}"].to_numpy()
        for k, (pf, p, h, tzb, szb) in enumerate(zip(df["profile_file"], pc, half, df["T_z"], df["S_z"])):
            if lab[k] != "interface" or pf not in by_prof:
                continue
            g = by_prof[pf]
            ov = (np.minimum(g["p_end"], p + h) - np.maximum(g["p_start"], p - h)).to_numpy()
            if not (ov > 0).any():
                continue
            r = g.iloc[int(np.argmax(ov))]
            hgt = max(float(r["layer_height"]), float(config["regimes"]["staircase"][m]["grid_dbar"]))
            tz[k] = np.sign(tzb) * r["ct_range"] / hgt
            sz[k] = np.sign(szb) * r["sa_range"] / hgt
        n2 = 9.81 * (df["alpha"] * tz - df["beta"] * sz)
        df[f"T_z_iface_{m}"], df[f"S_z_iface_{m}"], df[f"N2_iface_{m}"] = tz, sz, n2
        with np.errstate(invalid="ignore", divide="ignore"):
            df[f"chi_exp_iface_{m}"] = np.where(n2 > 0, 2 * dd["flux_coefficient"] * df["epsilon_used"] / n2 * tz ** 2,
                                                np.nan)
    return df


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def depth_figure(bins, pooled, groups, method, path, foot):
    fig, axes = plt.subplots(1, len(groups), figsize=(5.4 * len(groups), 7), squeeze=False)
    for ax, g in zip(axes[0], groups):
        b_all = bins[(bins["instrument_group"] == g) & (bins["method"] == method) & (bins["turner"] == "finger_any")
                     & (bins["n2_filter"] == "all")]
        b = b_all[b_all["gradients"] == "background"]
        loc = b_all[(b_all["gradients"] == "interface_local")].sort_values("depth_bin")
        if len(loc):
            ax.scatter(loc["ratio"], loc["depth_bin"] - 2, marker="D", s=22, facecolors="none",
                       edgecolors=ps.ORANGE, label="interface, local gradients", zorder=3)
        for lab in ("all", "interface", "layer", "straddles"):
            s = b[b["staircase"] == lab].sort_values("depth_bin")
            if not len(s):
                continue
            off = {"all": 0, "interface": -2, "layer": 2, "straddles": 4}[lab]
            ok = s["n_profiles"] >= s["min_profiles"]
            ax.errorbar(s["ratio"], s["depth_bin"] + off,
                        xerr=[s["ratio"] - s["ratio_lo"], s["ratio_hi"] - s["ratio"]],
                        fmt="o-" if lab == "all" else "o", color=LABEL_COLOR[lab], ms=4, lw=1, capsize=2,
                        label=lab, alpha=1.0)
            ax.scatter(s.loc[~ok, "ratio"], s.loc[~ok, "depth_bin"] + off, s=40, facecolors="none",
                       edgecolors="r", linewidths=1)
        fs = b_all[(b_all["gradients"] == "finescale") & (b_all["staircase"] == "all")].sort_values("depth_bin")
        if len(fs):
            ax.plot(fs["ratio"], fs["depth_bin"], color="k", lw=1, ls=":", marker="s", ms=3,
                    label="all, finescale gradients")
        a = b[b["staircase"] == "all"].sort_values("depth_bin")
        ax.plot(a["finger_prediction"], a["depth_bin"], color=ps.RED, lw=1.5, ls="--", label="finger model (γ)")
        ax.axvline(1, color="k", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlim(0.05, 300)
        ax.invert_yaxis()
        ax.set_xlabel(r"$\langle\chi_{obs}\rangle / \langle\chi_{exp}\rangle$ (95% bootstrap)")
        ax.set_ylabel("pressure (dbar)")
        p = pooled[(pooled["instrument_group"] == g) & (pooled["method"] == method)
                   & (pooled["turner"] == "finger_any") & (pooled["staircase"] == "all") & (pooled["n2_filter"] == "all")
                   & (pooled["gradients"] == "background")]
        txt = f"pooled {p['ratio'].iloc[0]:.1f} [{p['ratio_lo'].iloc[0]:.1f}, {p['ratio_hi'].iloc[0]:.1f}]" if len(p) else ""
        ax.set_title(f"{g}\nfinger-favourable, {method}\n{txt}", fontsize=9)
        ax.legend(fontsize=7.5, loc="lower right")
    fig.tight_layout()
    ps.footer(fig, foot + "; red circles: fewer profiles than min_profiles_per_average")
    fig.savefig(path, dpi=100)
    plt.close(fig)


def rrho_figure(prep, groups, method, gamma, path, foot):
    fig, axes = plt.subplots(1, len(groups), figsize=(5.4 * len(groups), 5), squeeze=False)
    rr = np.linspace(1.01, 4, 200)
    for ax, g in zip(axes[0], groups):
        d = prep[prep["instrument_group"] == g]
        d = d[d["R_rho"].between(1, 10)]
        edges = np.array([1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 10])
        for lab in ("interface", "layer", "all"):
            s = d if lab == "all" else d[d[f"staircase_{method}"] == lab]
            x, y, n = [], [], []
            for lo, hi in zip(edges[:-1], edges[1:]):
                q = s[(s["R_rho"] >= lo) & (s["R_rho"] < hi)]
                if len(q) >= 10 and q["profile_file"].nunique() >= 2:
                    x.append(q["R_rho"].median())
                    y.append(q["chi_obs"].mean() / q["chi_exp"].mean())
                    n.append(len(q))
            ax.plot(x, y, "o-" if lab == "all" else "o", color=LABEL_COLOR[lab], label=lab, ms=5)
        for gm, ls in ((0.5, ":"), (gamma, "--"), (0.7, "-.")):
            ax.plot(rr, ((rr - 1) / rr) * (gm / (1 - gm)) / 0.2, color=ps.RED, ls=ls, lw=1, label=f"finger γ={gm:g}")
        ax.axhline(1, color="k", lw=0.8)
        ax.set_yscale("log")
        ax.set_ylim(0.1, 300)
        ax.set_xlim(1, 4)
        ax.set_xlabel(r"$R_\rho$ (window, 10 m fits)")
        ax.set_ylabel(r"$\langle\chi_{obs}\rangle / \langle\chi_{exp}\rangle$")
        ax.set_title(f"{g} ({method})", fontsize=9)
        ax.legend(fontsize=7)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def gm_figure(gmt, groups, path, foot):
    gs = [g for g in groups if "all free fall" in g] or groups
    fig, axes = plt.subplots(1, len(gs), figsize=(5.2 * len(gs), 7), squeeze=False)
    for ax, g in zip(axes[0], gs):
        b = gmt[(gmt["instrument_group"] == g) & (gmt["depth_bin"] != "pooled")].copy()
        b["z"] = b["depth_bin"].astype(float)
        for (tname, sname), c, lab in ((("finger_any", "interface"), ps.ORANGE, "K_T interfaces"),
                                       (("finger_any", "layer"), ps.BLUE, "K_T layers"),
                                       (("finger_any", "none"), ps.AQUA, "K_T finger, no staircase"),
                                       (("control", "all"), ps.MUTED, "K_T control")):
            s = b[(b["turner"] == tname) & (b["staircase"] == sname)].sort_values("z")
            ax.plot(s["K_T_finescale"], s["z"], "o-", color=c, ms=3, lw=1, label=lab + " (finescale)")
        a = b[(b["turner"] == "all_turner") & (b["staircase"] == "all")].sort_values("z")
        ax.plot(a["K_rho_measured"], a["z"], color="k", lw=1, ls=":", label="K_rho = 0.2<ε>/<N²>")
        c_ = b[(b["turner"] == "control") & (b["staircase"] == "all")].sort_values("z")
        allz = pd.concat([a, c_]).drop_duplicates("z").sort_values("z")
        ax.plot(allz["K_GM"], allz["z"], color=ps.RED, lw=2, label="Garrett–Munk K_GM")
        ax.axvline(1.4e-7, color="k", lw=0.6, ls="--", label="molecular κ_T")
        ax.set_xscale("log")
        ax.set_xlim(1e-8, 1e-2)
        ax.invert_yaxis()
        ax.set_xlabel("diffusivity (m² s⁻¹), bin averages")
        ax.set_ylabel("pressure (dbar)")
        ax.set_title(g, fontsize=9)
        ax.legend(fontsize=6.5, loc="lower right")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def reb_figure(reb, groups, path, foot):
    gs = [g for g in groups if g in set(reb["instrument_group"])]
    if not gs:
        return
    fig, axes = plt.subplots(1, len(gs), figsize=(4.6 * len(gs), 4.6), squeeze=False)
    for ax, g in zip(axes[0], gs):
        for (tname, grad), c, ls in ((("finger_any", "finescale"), ps.ORANGE, "-"), (("control", "finescale"), ps.BLUE, "-"),
                                     (("finger_any", "background"), ps.ORANGE, ":"), (("control", "background"), ps.BLUE, ":")):
            s = reb[(reb["instrument_group"] == g) & (reb["turner"] == tname) & (reb["gradients"] == grad)]
            if not len(s):
                continue
            x = np.sqrt(s["Re_b_lo"].clip(lower=0.3) * s["Re_b_hi"].clip(upper=3000))
            ax.errorbar(x, s["ratio"], yerr=[s["ratio"] - s["ratio_lo"], s["ratio_hi"] - s["ratio"]], color=c, ls=ls,
                        marker="o", ms=4, capsize=2, label=f"{'finger' if tname == 'finger_any' else 'control'}, {grad}")
        ax.axhline(1, color="k", lw=0.8)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.05, 300)
        ax.set_xlabel("Re_b (shear, bounded)")
        ax.set_ylabel(r"$\langle\chi_{obs}\rangle / \langle\chi_{exp}\rangle$")
        ax.set_title(g, fontsize=9)
        ax.legend(fontsize=6.5)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    dd = config["double_diffusion"]
    unc = config["uncertainty"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ps.apply()
    rng = np.random.default_rng(unc["random_seed"])
    methods = config["regimes"]["staircase"]["methods"]
    preps = [prepare(ctx, name, config) for name, _ in common.instruments(config)]
    prep = pd.concat(preps, ignore_index=True)
    prep = prep[prep["station"].isin(dd["station_groups"])]
    if dd.get("pool_free_fall"):
        ff = prep[~prep["towyo"]].copy()
        ff["instrument_group"] = ff["instrument_group"].str.split(" ").str[0] + " all free fall"
        prep = pd.concat([prep, ff], ignore_index=True)
    prep.attrs["control_max"] = dd["control_max_turner_deg"]
    groups = sorted(prep["instrument_group"].unique())
    bins_rows, pooled_rows = [], []
    for g in groups:
        dg = prep[prep["instrument_group"] == g]
        dg.attrs["control_max"] = dd["control_max_turner_deg"]
        weak = dg["N2"] <= dg["N2"].quantile(dd["exclude_weakest_n2_percent"] / 100)
        for n2f, dsel in (("all", dg), (f"drop_weakest_{dd['exclude_weakest_n2_percent']}pct", dg[~weak])):
            for m in methods:
                dsel.attrs["control_max"] = dd["control_max_turner_deg"]
                for (tname, sname), sel in regime_sets(dsel, m).items():
                    d = dsel[sel]
                    if len(d) == 0:
                        continue
                    variants = [("background", d),
                                ("finescale", d.assign(chi_exp=d["chi_exp_fine"])[np.isfinite(d["chi_exp_fine"])])]
                    if sname == "interface":
                        dl = d.assign(chi_exp=d[f"chi_exp_iface_{m}"], T_z=d[f"T_z_iface_{m}"], S_z=d[f"S_z_iface_{m}"])
                        variants.append(("interface_local", dl[np.isfinite(dl["chi_exp"])]))
                    for grad, dv in variants:
                        if not len(dv):
                            continue
                        base = {"instrument_group": g, "method": m, "turner": tname, "staircase": sname,
                                "gradients": grad, "n2_filter": n2f, "min_profiles": dd["min_profiles_per_average"]}
                        pooled_rows.append({**base, **ratio_stats(dv, dd["flux_ratio_gamma"], unc["bootstrap_samples"], rng)})
                        for zb, db in dv.groupby("depth_bin"):
                            bins_rows.append({**base, "depth_bin": zb,
                                              **ratio_stats(db, dd["flux_ratio_gamma"], unc["bootstrap_samples"], rng)})
    # Ratio in Re_b bins: finger-favourable windows vs control, matched turbulence intensity
    reb_rows = []
    edges = dd["re_b_bins"]
    for g in groups:
        dg = prep[prep["instrument_group"] == g]
        dg.attrs["control_max"] = dd["control_max_turner_deg"]
        sets = regime_sets(dg, methods[-1])
        for tname in ("finger_any", "control"):
            d = dg[sets[(tname, "all")]]
            for lo_b, hi_b in zip(edges[:-1], edges[1:]):
                db = d[(d["Re_b_shear"] >= lo_b) & (d["Re_b_shear"] < hi_b)]
                for grad, dv in (("background", db), ("finescale", db.assign(chi_exp=db["chi_exp_fine"])
                                                         [np.isfinite(db["chi_exp_fine"])])):
                    if len(dv) >= 5:
                        reb_rows.append({"instrument_group": g, "turner": tname, "gradients": grad,
                                         "Re_b_lo": lo_b, "Re_b_hi": hi_b,
                                         **ratio_stats(dv, dd["flux_ratio_gamma"], unc["bootstrap_samples"], rng)})
    reb = pd.DataFrame(reb_rows)

    # Excess over the Re_b-matched control, per group x method x staircase label x gradients
    ex_rows = []
    for g in groups:
        inst = g.split(" ")[0]
        cg = prep[prep["instrument_group"] == f"{inst} {dd['excess_control_group']}"]
        cg.attrs["control_max"] = dd["control_max_turner_deg"]
        dg = prep[prep["instrument_group"] == g]
        dg.attrs["control_max"] = dd["control_max_turner_deg"]
        for m in methods:
            ctrl_sel = regime_sets(cg, m)[("control", "all")]
            sets = regime_sets(dg, m)
            for sname in ("all", "interface", "layer", "straddles", "none"):
                d = dg[sets[("finger_any", sname)]]
                if len(d) < 5:
                    continue
                grads = [("background", d, cg[ctrl_sel]),
                         ("finescale", d.assign(chi_exp=d["chi_exp_fine"])[np.isfinite(d["chi_exp_fine"])],
                          cg[ctrl_sel].assign(chi_exp=cg.loc[ctrl_sel, "chi_exp_fine"])
                          [np.isfinite(cg.loc[ctrl_sel, "chi_exp_fine"])])]
                if sname == "interface":
                    # interface windows with their own gradients; the control keeps finescale gradients
                    dl = d.assign(chi_exp=d[f"chi_exp_iface_{m}"])[np.isfinite(d[f"chi_exp_iface_{m}"])]
                    grads.append(("interface_local", dl, grads[1][2]))
                for grad, dt, dc in grads:
                    if len(dt) < 5 or len(dc) < 10:
                        continue
                    ex_rows.append({"instrument_group": g, "method": m, "staircase": sname, "gradients": grad,
                                    "control_group": f"{inst} {dd['excess_control_group']}",
                                    **excess_stats(dt, dc, dd["re_b_bins"], dd["excess_min_control_windows"],
                                                   unc["bootstrap_samples"], rng)})
    ex = pd.DataFrame(ex_rows)

    # Garrett-Munk reference level, by group x regime x staircase label (pooled and per depth bin)
    gm_rows = []
    for g in groups:
        dg = prep[prep["instrument_group"] == g]
        dg.attrs["control_max"] = dd["control_max_turner_deg"]
        sets = regime_sets(dg, methods[-1])
        for (tname, sname) in [("finger_any", "all"), ("finger_any", "interface"), ("finger_any", "layer"),
                               ("finger_any", "none"), ("control", "all"), ("all_turner", "all")]:
            d = dg[sets[(tname, sname)]]
            if len(d) < 5:
                continue
            base = {"instrument_group": g, "method": methods[-1], "turner": tname, "staircase": sname}
            gm_rows.append({**base, "depth_bin": "pooled", **gm_stats(d, dd["gm"])})
            for zb, db in d.groupby("depth_bin"):
                if len(db) >= 5:
                    gm_rows.append({**base, "depth_bin": zb, **gm_stats(db, dd["gm"])})
    gmt = pd.DataFrame(gm_rows)
    gmt.to_csv(out / "dd_gm.csv", index=False, float_format="%.6g")
    gm_figure(gmt, groups, out / "figures" / "diffusivity_vs_gm.png", foot)
    ex.to_csv(out / "dd_excess.csv", index=False, float_format="%.6g")
    reb.to_csv(out / "dd_re_b.csv", index=False, float_format="%.6g")
    reb_figure(reb, groups, out / "figures" / "ratio_vs_re_b.png", foot)

    bins = pd.DataFrame(bins_rows)
    pooled = pd.DataFrame(pooled_rows)
    for t in (bins, pooled):
        t["below_min_profiles"] = t["n_profiles"] < t["min_profiles"]
        t["epsilon_source"] = dd["epsilon_source"]
        t["flux_coefficient"] = dd["flux_coefficient"]
        t["flux_ratio_gamma"] = dd["flux_ratio_gamma"]
    bins.to_csv(out / "dd_bins.csv", index=False, float_format="%.6g")
    pooled.to_csv(out / "dd_pooled.csv", index=False, float_format="%.6g")
    prep.to_csv(out / "dd_windows.csv", index=False, float_format="%.6g")

    report = {"double_diffusion": dd, "groups": {}}
    for g in groups:
        p = pooled[(pooled["instrument_group"] == g) & (pooled["n2_filter"] == "all")]
        report["groups"][g] = {
            f"{r.method} {r.turner} {r.staircase} {r.gradients}": {"ratio": round(r.ratio, 2),
                                                    "ci95": [round(r.ratio_lo, 2), round(r.ratio_hi, 2)],
                                                    "finger_prediction": round(r.finger_prediction, 2),
                                                    "R_rho": round(r.R_rho_bin, 2), "n_windows": int(r.n_windows),
                                                    "n_profiles": int(r.n_profiles),
                                                    "at_floor_fraction": round(r.at_floor_fraction, 2)}
            for r in p.itertuples() if r.turner in ("finger_any", "not_finger", "all_turner", "control")}
        print(f"  {g}:")
        for r in p[p["turner"].isin(["finger_any", "control"]) & p["staircase"].isin(["all", "interface", "layer"])
                   & (p["method"] == methods[-1])].itertuples():
            print(f"    {r.method:9s} {r.turner[:7]:7s} {r.staircase:9s} {r.gradients[:10]:10s} R={r.ratio:6.2f} [{r.ratio_lo:5.2f},{r.ratio_hi:6.2f}]"
                  f"  finger model {r.finger_prediction:4.1f} (R_rho {r.R_rho_bin:.2f})  n={r.n_windows} windows,"
                  f" {r.n_profiles} profiles, at floor {r.at_floor_fraction:.0%}")
    for m in methods:
        depth_figure(bins, pooled, groups, m, out / "figures" / f"ratio_vs_depth_{m}.png", foot)
        rrho_figure(prep, groups, m, dd["flux_ratio_gamma"], out / "figures" / f"ratio_vs_rrho_{m}.png", foot)
    common.write_json(out / "dd_test_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
