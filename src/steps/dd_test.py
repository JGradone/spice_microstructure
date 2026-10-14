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
  * Groups: station groups (cast_log `station`) x instrument x tow-yo / free fall
    (tow-yo profiles are never pooled with free-fall casts).
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
    for tname, tsel in (("all_turner", pd.Series(True, index=df.index)), ("finger_any", tc.isin(FINGER)),
                        ("strong_finger", tc == "strong_finger"), ("not_finger", tc == "not_finger")):
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
    ok = (df["shear_keep"].fillna(False).astype(bool) & df["chi_keep"].fillna(False).astype(bool)
          & (df["N2"] > 0) & np.isfinite(df["T_z"]) & np.isfinite(eps) & np.isfinite(df["chi"])
          & ~df["ts_salinity_invalid"].fillna(False).astype(bool)
          & (df["P_mean"] >= lo) & (df["P_mean"] < hi))
    df = df[ok].copy()
    df["epsilon_used"] = eps[ok]
    df["chi_obs"] = df["chi"]
    df["chi_exp"] = 2 * dd["flux_coefficient"] * df["epsilon_used"] / df["N2"] * df["T_z"] ** 2
    b = dd["depth_bin_m"]
    df["depth_bin"] = np.floor(df["P_mean"] / b) * b + b / 2
    df["group"] = df["station"].where(df["station"] != "", "other") + np.where(df["towyo"], " tow-yo", " free fall")
    df.insert(0, "instrument_group", name + " " + df["group"])

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
    groups = sorted(prep["instrument_group"].unique())
    bins_rows, pooled_rows = [], []
    for g in groups:
        dg = prep[prep["instrument_group"] == g]
        weak = dg["N2"] <= dg["N2"].quantile(dd["exclude_weakest_n2_percent"] / 100)
        for n2f, dsel in (("all", dg), (f"drop_weakest_{dd['exclude_weakest_n2_percent']}pct", dg[~weak])):
            for m in methods:
                for (tname, sname), sel in regime_sets(dsel, m).items():
                    d = dsel[sel]
                    if len(d) == 0:
                        continue
                    variants = [("background", d)]
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
            for r in p.itertuples() if r.turner in ("finger_any", "not_finger", "all_turner")}
        print(f"  {g}:")
        for r in p[(p["turner"] == "finger_any")].itertuples():
            print(f"    {r.method:9s} finger {r.staircase:9s} {r.gradients[:10]:10s} R={r.ratio:6.2f} [{r.ratio_lo:5.2f},{r.ratio_hi:6.2f}]"
                  f"  finger model {r.finger_prediction:4.1f} (R_rho {r.R_rho_bin:.2f})  n={r.n_windows} windows,"
                  f" {r.n_profiles} profiles, at floor {r.at_floor_fraction:.0%}")
    for m in methods:
        depth_figure(bins, pooled, groups, m, out / "figures" / f"ratio_vs_depth_{m}.png", foot)
        rrho_figure(prep, groups, m, dd["flux_ratio_gamma"], out / "figures" / f"ratio_vs_rrho_{m}.png", foot)
    common.write_json(out / "dd_test_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
