#!/usr/bin/env python3
"""Step regimes: label every dissipation window by regime (CLAUDE.md step 6).

Per window:
  * Turner class from the Turner angle of linear fits over
    regimes.turner_smoothing_m (Ruddick 1983, z up):
        not_finger    -45 < Tu <  45
        finger         45 <= Tu < turner_finger_strong_deg
        strong_finger  turner_finger_strong_deg <= Tu <= 90
        diffusive     -90 <= Tu <= -45
        unstable       |Tu| > 90
    The hydrography step's 10 m values are kept alongside. VMP5500 windows in a
    temperature inversion keep their ts_salinity_invalid flag (T-S salinity
    cannot represent compensated intrusions).
  * Staircase position, one label per method in regimes.staircase.methods.
    Each method runs Rollo's classify_staircase on the profile's 1 dbar grid
    (hydrography CT and SA, interpolated to even pressure) and marks each
    pressure bin as mixed layer or interface. A window covers
    P_centre +/- speed * diss_sec / 2 (probe-tip depth); with f the fraction of
    regimes.window_label_fraction:
        interface   interface share >= f
        layer       mixed-layer share >= f
        straddles   interface + layer share >= f, neither alone
        none        otherwise
    plus the step type (salt finger / diffusive convection) of the interfaces it
    touches. Methods are compared, never merged.
  * Buoyancy Reynolds number Re_b = epsilon / (nu N2), from the bounded shear
    epsilon and, where the Batchelor roll-off is resolved, from epsilon_T.

Reads:  <run_dir>/hydrography/{hydrography,windows}_<instrument>.{nc,csv}
        <run_dir>/epsilon_shear/epsilon_shear_<instrument>.csv
        <run_dir>/thermistor/thermistor_<instrument>.csv
Writes: <run_dir>/regimes/
          regimes_<instrument>.csv       one row per window
          steps_<instrument>.csv         detected mixed layers and interfaces per profile and method
          figures/*.png, regimes_report.json, step_metadata.json
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import gsw
import numpy as np
import pandas as pd
import xarray as xr
from thermohalinesteps.detect_staircases import classify_staircase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
from hydrography import stratification  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "regimes"
TURNER_CLASSES = ["not_finger", "finger", "strong_finger", "diffusive", "unstable"]
LABELS = ["interface", "layer", "straddles", "none"]
CLASSIFY_ARGS = ("ml_grad", "ml_density_difference", "av_window", "interface_max_height",
                 "layer_height_ratio", "temp_flag_only")
LABEL_COLOR = {"interface": ps.ORANGE, "layer": ps.BLUE, "straddles": ps.AQUA, "none": ps.MUTED}


def turner_class(tu: np.ndarray, strong: float, fmin: float) -> np.ndarray:
    out = np.full(len(tu), "", dtype=object)
    out[(tu > -fmin) & (tu < fmin)] = "not_finger"
    out[(tu >= fmin) & (tu < strong)] = "finger"
    out[(tu >= strong) & (tu <= 90)] = "strong_finger"
    out[(tu >= -90) & (tu <= -fmin)] = "diffusive"
    out[np.abs(tu) > 90] = "unstable"
    out[~np.isfinite(tu)] = ""
    return out


def profile_staircase(depth, ct, sa, lat, cfg) -> tuple[np.ndarray, dict, pd.DataFrame]:
    """(pressure grid, {mask name: bool array}, steps table) for one profile and method."""
    ok = np.isfinite(ct) & np.isfinite(sa)
    if ok.sum() < 20:
        return np.array([]), {}, pd.DataFrame()
    p = gsw.p_from_z(-depth[ok], lat)
    step = cfg["grid_dbar"]
    pg = np.arange(np.ceil(p.min()), np.floor(p.max()) + step / 2, step)
    ctg, sag = np.interp(pg, p, ct[ok]), np.interp(pg, p, sa[ok])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df, ml, gl = classify_staircase(pg, ctg, sag, **{k: cfg[k] for k in CLASSIFY_ARGS})
    # Final masks are True where a bin is NOT a (qualifying) layer; returned df drops the end points
    masks = {"layer": np.zeros(len(pg), bool), "interface": np.zeros(len(pg), bool),
             "salt_finger": np.zeros(len(pg), bool)}
    idx = np.searchsorted(pg, df["p"].to_numpy())
    masks["layer"][idx] = ~df["mixed_layer_final_mask"].to_numpy(bool)
    masks["interface"][idx] = ~df["gradient_layer_final_mask"].to_numpy(bool)
    if "mixed_layer_salt_finger_mask" in df:
        masks["salt_finger"][idx] = ~df["mixed_layer_salt_finger_mask"].to_numpy(bool)
    steps = []
    for kind, tab in (("layer", ml), ("interface", gl)):
        if tab is None or not len(tab):
            continue
        keep = ~tab.get("bad_mixed_layer", tab.get("bad_grad_layer", pd.Series(False, index=tab.index))).astype(bool)
        t = tab[keep].copy()
        t.insert(0, "kind", kind)
        steps.append(t)
    steps = pd.concat(steps, ignore_index=True) if steps else pd.DataFrame()
    if len(steps):
        # Interfaces carry their own salt_finger flag; mark finger-type interface bins
        for _, r in steps[steps["kind"] == "interface"].iterrows():
            if bool(r.get("salt_finger", False)):
                masks["salt_finger"][(pg >= r["p_start"]) & (pg <= r["p_end"])] = True
    return pg, masks, steps


def window_labels(pg, masks, p0, p1, frac) -> tuple[str, float, float, bool]:
    if not len(pg):
        return "none", np.nan, np.nan, False
    sel = (pg >= p0) & (pg <= p1)
    if sel.sum() == 0:
        return "none", np.nan, np.nan, False
    fi, fl = masks["interface"][sel].mean(), masks["layer"][sel].mean()
    sf = bool(masks["salt_finger"][sel & masks["interface"]].any())
    if fi >= frac:
        lab = "interface"
    elif fl >= frac:
        lab = "layer"
    elif fi + fl >= frac:
        lab = "straddles"
    else:
        lab = "none"
    return lab, float(fi), float(fl), sf


def run_instrument(ctx, name, inst, config):
    rc = config["regimes"]
    rd = ctx["run_dir"]
    hyd = xr.open_dataset(rd / "hydrography" / f"hydrography_{name}.nc")
    win = pd.read_csv(rd / "hydrography" / f"windows_{name}.csv")
    sh = pd.read_csv(rd / "epsilon_shear" / f"epsilon_shear_{name}.csv")
    th = pd.read_csv(rd / "thermistor" / f"thermistor_{name}.csv")
    keys = ["profile_file", "window"]
    df = win.merge(sh[keys + ["speed", "nu", "epsilon_shear", "epsilon_shear_bounded", "epsilon_floor", "at_floor",
                              "keep"]].rename(columns={"at_floor": "shear_at_floor", "keep": "shear_keep"}), on=keys) \
            .merge(th[keys + ["chi", "chi_bounded", "epsilon_T", "epsilon_T_resolved", "keep"]]
                   .rename(columns={"keep": "chi_keep"}), on=keys, how="left")
    half = df["speed"] * float(config["perturb"]["epsilon"]["diss_sec"]) / 2      # m ~ dbar

    # Turner angle at the classification scale, from the hydrography grid
    hc = config["hydrography"]
    zc = hyd["depth"].values
    tu_s = {}
    lat_of = {}
    for i, pf in enumerate(hyd["profile_file"].values):
        lat = float(hyd["lat"].values[i]) if np.isfinite(hyd["lat"].values[i]) else 12.0
        lat_of[pf] = lat
        st = stratification(zc, hyd["CT"].values[i], hyd["SA_used"].values[i], gsw.p_from_z(-zc, lat),
                            rc["turner_smoothing_m"], hc["bin_m"], hc["min_fit_fraction"])
        tu_s[pf] = st["Turner"]
    df["Turner_class_m"] = rc["turner_smoothing_m"]
    df["Turner_smooth"] = [np.interp(d, zc, tu_s[pf], left=np.nan, right=np.nan)
                           for pf, d in zip(df["profile_file"], df["depth"])]
    df["turner_class"] = turner_class(df["Turner_smooth"].to_numpy(), rc["turner_finger_strong_deg"],
                                      rc["turner_finger_min_deg"])
    df["turner_class_10m"] = turner_class(df["Turner"].to_numpy(), rc["turner_finger_strong_deg"],
                                          rc["turner_finger_min_deg"])

    # Buoyancy Reynolds number
    with np.errstate(invalid="ignore", divide="ignore"):
        n2 = df["N2"].where(df["N2"] > 0)
        df["Re_b_shear"] = df["epsilon_shear_bounded"] / (df["nu"] * n2)
        df["Re_b_T"] = (df["epsilon_T"] / (df["nu"] * n2)).where(df["epsilon_T_resolved"].fillna(False).astype(bool))

    # Staircases, per method
    steps_all = []
    frac = rc["window_label_fraction"]
    st_cfg = rc["staircase"]
    for method in st_cfg["methods"]:
        mcfg = st_cfg[method]
        cache = {}
        for i, pf in enumerate(hyd["profile_file"].values):
            pg, masks, steps = profile_staircase(zc, hyd["CT"].values[i], hyd["SA_used"].values[i], lat_of[pf], mcfg)
            cache[pf] = (pg, masks)
            if len(steps):
                steps.insert(0, "method", method)
                steps.insert(0, "profile_file", pf)
                steps_all.append(steps)
        out = []
        for pf, d, h in zip(df["profile_file"], df["depth"], half):
            pg, masks = cache.get(pf, (np.array([]), {}))
            pc = float(gsw.p_from_z(-d, lat_of.get(pf, 12.0))) if np.isfinite(d) else np.nan
            out.append(window_labels(pg, masks, pc - h, pc + h, frac) if np.isfinite(pc) else ("none", np.nan, np.nan, False))
        df[f"staircase_{method}"] = [o[0] for o in out]
        df[f"interface_fraction_{method}"] = [o[1] for o in out]
        df[f"layer_fraction_{method}"] = [o[2] for o in out]
        df[f"salt_finger_interface_{method}"] = [o[3] for o in out]
    m = st_cfg["methods"]
    if len(m) >= 2:
        df["staircase_methods_agree"] = df[f"staircase_{m[0]}"] == df[f"staircase_{m[1]}"]
    steps = pd.concat(steps_all, ignore_index=True) if steps_all else pd.DataFrame()
    return df, steps


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def examples_figure(ctx, config, results, path, foot):
    ex = [e for e in config["regimes"]["examples"] if e[0] in results]
    methods = config["regimes"]["staircase"]["methods"]
    if not ex:
        return
    fig, axes = plt.subplots(1, 3 * len(ex), figsize=(4.6 * len(ex) * 1.6, 7.5),
                             gridspec_kw={"width_ratios": [1.2, 0.9, 0.9] * len(ex)}, squeeze=False)
    for e, (inst, prof, p0, p1) in enumerate(ex):
        df, steps = results[inst]
        hyd = xr.open_dataset(ctx["run_dir"] / "hydrography" / f"hydrography_{inst}.nc")
        i = list(hyd["profile_file"].values).index(f"{prof}.nc")
        lat = float(hyd["lat"].values[i]) if np.isfinite(hyd["lat"].values[i]) else 12.0
        pz = gsw.p_from_z(-hyd["depth"].values, lat)
        axT = axes[0, 3 * e]
        axT.plot(hyd["CT"].values[i], pz, color="k", lw=0.9)
        s = steps[(steps["profile_file"] == f"{prof}.nc") & (steps["method"] == methods[-1])] if len(steps) else steps
        for _, r in s.iterrows():
            axT.axhspan(r["p_start"], r["p_end"], color=LABEL_COLOR["layer" if r["kind"] == "layer" else "interface"],
                        alpha=0.25, lw=0)
        axT.set_ylim(p1, p0)
        axT.set_xlabel("Θ (°C)")
        axT.set_ylabel("pressure (dbar)")
        axT.set_title(f"{inst} {prof}\nsteps: {methods[-1]}", fontsize=9)
        w = df[(df["profile_file"] == f"{prof}.nc") & (df["window"] % 2 == 0)]
        for ax, col, lab in ((axes[0, 3 * e + 1], "chi", "χ (K² s⁻¹)"), (axes[0, 3 * e + 2], "epsilon_shear", "ε (W kg⁻¹)")):
            for _, r in w.iterrows():
                pc = float(gsw.p_from_z(-r["depth"], lat))
                h = r["speed"] * float(config["perturb"]["epsilon"]["diss_sec"]) / 2
                if p0 <= pc <= p1 and np.isfinite(r[col]):
                    ax.plot([r[col], r[col]], [pc - h, pc + h], color=LABEL_COLOR[r[f"staircase_{methods[-1]}"]], lw=2)
            ax.set_xscale("log")
            ax.set_ylim(p1, p0)
            ax.set_yticklabels([])
            ax.set_xlabel(lab)
        handles = [plt.Line2D([], [], color=c, lw=3, label=k) for k, c in LABEL_COLOR.items()]
        axes[0, 3 * e + 1].legend(handles=handles, fontsize=7, loc="lower right")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def occurrence_figure(results, methods, path, foot):
    fig, axes = plt.subplots(1, len(results), figsize=(7.5 * len(results), 6), squeeze=False)
    for ax, (inst, (df, _)) in zip(axes[0], results.items()):
        files = sorted(df["profile_file"].unique())
        x = df["profile_file"].map({f: k for k, f in enumerate(files)})
        p = df["P_mean"]
        lab = df[f"staircase_{methods[-1]}"]
        for k in ("none", "straddles", "layer", "interface"):
            sel = lab == k
            ax.scatter(x[sel], p[sel], s=3 if k == "none" else 5, color=LABEL_COLOR[k], linewidths=0,
                       alpha=0.25 if k == "none" else 0.9, label=k)
        ax.invert_yaxis()
        ax.set_xlabel("profile (chronological)")
        ax.set_ylabel("pressure (dbar)")
        ax.set_title(f"{inst}: staircase labels ({methods[-1]})", fontsize=10)
        ax.legend(fontsize=8, markerscale=3, loc="lower left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def distributions_figure(results, methods, path, foot):
    fig, axes = plt.subplots(2, len(results), figsize=(7 * len(results), 9), squeeze=False)
    for j, (inst, (df, _)) in enumerate(results.items()):
        d = df[(df["P_mean"] > 150) & df["chi_keep"].fillna(False).astype(bool)]
        for i, (col, lab) in enumerate((("chi", "χ (K² s⁻¹)"), ("epsilon_shear_bounded", "ε shear, bounded (W kg⁻¹)"))):
            ax = axes[i, j]
            groups, names = [], []
            for tc in ("not_finger", "finger", "strong_finger"):
                for st in ("layer", "straddles", "interface"):
                    v = d.loc[(d["turner_class"] == tc) & (d[f"staircase_{methods[-1]}"] == st), col]
                    v = np.log10(v[v > 0])
                    groups.append(v)
                    names.append(f"{tc.replace('_', ' ')}\n{st} ({len(v)})")
            bp = ax.boxplot([g if len(g) else [np.nan] for g in groups], showfliers=False, patch_artist=True)
            for patch, nm in zip(bp["boxes"], names):
                patch.set_facecolor(LABEL_COLOR[nm.split("\n")[1].split(" ")[0]])
                patch.set_alpha(0.6)
            ax.set_xticks(range(1, len(names) + 1), names, fontsize=6.5, rotation=90)
            ax.set_ylabel(f"log10 {lab}")
            ax.set_title(f"{inst}, below 150 dbar ({methods[-1]})", fontsize=10)
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def run(ctx: dict) -> None:
    config = ctx["config"]
    rc = config["regimes"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    foot = common.provenance_string(prov)
    ps.apply()
    methods = rc["staircase"]["methods"]
    report = {"regimes": rc, "instruments": {}}
    results = {}
    for name, inst in common.instruments(config):
        df, steps = run_instrument(ctx, name, inst, config)
        df.insert(0, "instrument", name)
        df.to_csv(out / f"regimes_{name}.csv", index=False, float_format="%.6g")
        steps.to_csv(out / f"steps_{name}.csv", index=False, float_format="%.6g")
        results[name] = (df, steps)
        deep = df[df["P_mean"] > 150]
        r = {"windows": len(df), "windows_below_150": len(deep),
             "turner_class_below_150": deep["turner_class"].replace("", "undefined").value_counts().to_dict(),
             "turner_class_10m_vs_smooth_agree_below_150":
                 round(float((deep["turner_class"] == deep["turner_class_10m"]).mean()), 3)}
        for mth in methods:
            r[f"staircase_{mth}_below_150"] = deep[f"staircase_{mth}"].value_counts().to_dict()
            prof_with = steps[(steps["method"] == mth) & (steps["kind"] == "interface")]["profile_file"].nunique() \
                if len(steps) else 0
            r[f"profiles_with_interfaces_{mth}"] = int(prof_with)
        if len(methods) >= 2:
            r["methods_agree_below_150"] = round(float(deep["staircase_methods_agree"].mean()), 3)
            r["methods_confusion_below_150"] = pd.crosstab(deep[f"staircase_{methods[0]}"],
                                                           deep[f"staircase_{methods[1]}"]).to_dict()
        r["Re_b_shear_median_below_150"] = float(deep["Re_b_shear"].median())
        report["instruments"][name] = r
        print(f"  {name}: {len(df)} windows; below 150 dbar Turner {r['turner_class_below_150']}; "
              + "; ".join(f"{mth} {r[f'staircase_{mth}_below_150']} ({r[f'profiles_with_interfaces_{mth}']} profiles "
                          f"with interfaces)" for mth in methods)
              + (f"; methods agree {r['methods_agree_below_150']:.0%}" if len(methods) >= 2 else ""))
    examples_figure(ctx, config, results, out / "figures" / "staircase_examples.png", foot)
    occurrence_figure(results, methods, out / "figures" / "staircase_occurrence.png", foot)
    distributions_figure(results, methods, out / "figures" / "regime_distributions.png", foot)
    common.write_json(out / "regimes_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
