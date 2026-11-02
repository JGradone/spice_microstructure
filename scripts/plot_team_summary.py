#!/usr/bin/env python3
"""Slide figures summarising the recommended run's results for a general audience (config `team_summary`).

Reads only the exported products in outputs/<products.recommended_dir>/, like any
analysis outside this repository, so the figures show exactly what is published.
Each figure carries a one-line takeaway computed from the products and a plain
"how to read this" note.

  1. overview.png: profile positions by instrument (process station marked), and
     K_T in finger-favourable water relative to Garrett-Munk per profile.
  1b. maps.png: per-profile metrics on a map: salinity maximum (both instruments), and
     for map_instrument the median R_rho, staircase coverage and mean epsilon below 150 m.
  2. dissipation_profiles.png: epsilon (shear, bounded at the noise floor) and chi
     against depth, arithmetic mean over profiles in depth_bin_m bins with the
     interquartile range across profiles; the median shear noise floor.
  3. double_diffusion.png: (a) the dissipation ratio E = <chi_obs>/<chi_exp> for
     staircase interfaces and layers against each baseline of the ladder; (b) pooled
     K_T and K_S (gamma_mid) for interfaces, layers and non-staircase finger water,
     with Garrett-Munk; 95% bootstrap intervals over profiles.
  4. diffusivity_profiles.png: K_T and K_S (gamma range) in finger-favourable water,
     Garrett-Munk and K_rho = 0.2 eps/N2, per instrument.

Reads:  outputs/<recommended_dir>/{casts,cast_metrics,attribution,diffusivity}_<inst>.csv,
        outputs/<recommended_dir>/{binned,segments}_<inst>.nc
Writes: outputs/comparisons/<team_summary.out_dir>/{overview,maps,dissipation_profiles,
        double_diffusion,diffusivity_profiles}.png, summary.json

Usage:
    python scripts/plot_team_summary.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import LogNorm
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

INSTRUMENTS = ("vmp250", "vmp5500")
LABEL = {"vmp250": "VMP-250 (upper ocean)", "vmp5500": "VMP-5500 (deep)"}
SHORT = {"vmp250": "VMP-250", "vmp5500": "VMP-5500"}
BASELINE_LABEL = {"theory_Gamma0.2": "standard\nturbulence theory",
                  "garrett_munk": "typical internal-wave\nmixing (Garrett–Munk)",
                  "nonstaircase_control": "nearby finger water\nwithout staircases"}
SET_LABEL = {"interface": "staircase interfaces", "layer": "staircase layers", "none": "no staircase"}
SET_MARKER = {"interface": "o", "layer": "s", "none": "D"}


def slide_style() -> None:
    ps.apply()
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 13, "axes.labelsize": 12,
                         "legend.fontsize": 10.5, "xtick.labelsize": 11, "ytick.labelsize": 11,
                         "lines.linewidth": 1.8})


def headline(fig, text: str, note: str) -> None:
    fig.suptitle(text.replace("; ", ";\n"), x=0.01, ha="left", fontsize=16, fontweight="bold")
    fig.text(0.01, 0.005, note, fontsize=10.5, color=ps.TEXT_2, ha="left", va="bottom")


def finish(fig, path: Path, foot: str, bottom: float = 0.04) -> None:
    fig.tight_layout(rect=(0, bottom, 1, 0.97))
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


def plain_log_axis(axis, ticks) -> None:
    axis.set_major_locator(FixedLocator(ticks))
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    axis.set_minor_formatter(NullFormatter())


def load(prod: Path, inst: str, name: str) -> pd.DataFrame:
    return pd.read_csv(prod / f"{name}_{inst}.csv")


def pick(df: pd.DataFrame, ts: dict, **kw) -> pd.DataFrame:
    sel = (df["instrument_group"].str.endswith(ts["group"])) & (df["method"] == ts["staircase_method"]) \
        & (df["gradients"] == ts["gradients"])
    for k, v in kw.items():
        sel &= df[k] == v
    return df[sel]


def figure_overview(prod: Path, ts: dict, path: Path, foot: str) -> dict:
    fig, axs = plt.subplots(1, 2, figsize=(14, 6.4), sharex=True, sharey=True)
    ax = axs[0]
    info = {}
    for inst in INSTRUMENTS:
        with xr.open_dataset(prod / f"segments_{inst}.nc") as s:
            used = set(np.unique(s["profile_file"].values))
        c = load(prod, inst, "casts")
        c = c[c["excluded"].isna() & c["profile_file"].isin(used)]
        ax.scatter(c["lon"], c["lat"], s=26 if inst == "vmp5500" else 12, color=ps.INSTRUMENT_COLOR[inst],
                   label=f"{LABEL[inst]}: {len(c)} profiles", zorder=3 if inst == "vmp5500" else 2,
                   edgecolor="white" if inst == "vmp5500" else "none", linewidth=0.5)
        info[inst] = {"profiles": len(c), "station_profiles": int((c["station"] == ts["station"]).sum())}
    lon0, lat0 = ts["station_lonlat"]
    ax.scatter([lon0], [lat0], s=450, facecolor="none", edgecolor=ps.TEXT, lw=1.4, zorder=4)
    ax.annotate("48 h process station\n(thermohaline staircases)", (lon0, lat0), xytext=(-150, 60),
                textcoords="offset points", fontsize=11, ha="center", color=ps.TEXT,
                bbox={"boxstyle": "round,pad=0.3", "fc": ps.SURFACE, "ec": ps.MUTED, "lw": 0.6},
                arrowprops={"arrowstyle": "-", "color": ps.TEXT_2, "lw": 0.8})
    ax.set_title("a. Where we measured", loc="left")
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.legend(loc="upper right")

    ax = axs[1]
    m = pd.concat([load(prod, inst, "cast_metrics") for inst in INSTRUMENTS], ignore_index=True)
    m = m[np.isfinite(m["K_T_finger_over_GM"]) & (m["K_T_finger_over_GM"] > 0)]
    lo, hi = ts["k_over_gm_range"]
    for inst, mk in (("vmp250", "o"), ("vmp5500", "s")):
        s = m[m["instrument"] == inst]
        sc = ax.scatter(s["lon"], s["lat"], c=s["K_T_finger_over_GM"], cmap=ps.SEQ_CHI,
                        norm=LogNorm(lo, hi), marker=mk, s=32 if inst == "vmp5500" else 18,
                        edgecolor=ps.TEXT_2, linewidth=0.3, label=SHORT[inst])
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    plain_log_axis(cb.ax.yaxis, ts["k_over_gm_ticks"])
    cb.set_label("heat mixing ÷ typical internal-wave mixing")
    ax.set_title("b. Heat mixing in finger-favourable water, per profile", loc="left")
    ax.set_xlabel("longitude (°E)")
    ax.legend(loc="upper right")
    med = float(m["K_T_finger_over_GM"].median())
    frac = float((m["K_T_finger_over_GM"] > 1).mean())
    info["K_T_finger_over_GM"] = {"median": round(med, 2), "fraction_above_1": round(frac, 2)}
    headline(fig, f"{info['vmp250']['profiles'] + info['vmp5500']['profiles']} turbulence profiles across "
             f"the western tropical Atlantic; heat mixing exceeds the typical background in "
             f"{frac:.0%} of them (median {med:.1f}×)",
             "Each dot is one free-falling profile. In (b), 1 means the mixing expected from internal waves "
             "alone (Garrett–Munk); darker = more mixing.")
    finish(fig, path, foot)
    return info


def figure_maps(prod: Path, ts: dict, path: Path, foot: str) -> dict:
    m = {inst: load(prod, inst, "cast_metrics") for inst in INSTRUMENTS}
    deep = m[ts["map_instrument"]]
    fig, axs = plt.subplots(2, 2, figsize=(14, 10.5), sharex=True, sharey=True)
    lon0, lat0 = ts["station_lonlat"]

    def panel(ax, df, col, cmap, norm, label, title, ticks=None, marker="s", size=46):
        d = df[np.isfinite(df[col])]
        sc = ax.scatter(d["lon"], d["lat"], c=d[col], cmap=cmap, norm=norm, marker=marker, s=size,
                        edgecolor=ps.TEXT_2, linewidth=0.3, zorder=3)
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        if ticks is not None:
            plain_log_axis(cb.ax.yaxis, ticks)
        cb.set_label(label)
        ax.scatter([lon0], [lat0], s=380, facecolor="none", edgecolor=ps.TEXT, lw=1.2, zorder=4)
        ax.set_title(title, loc="left")

    ax = axs[0, 0]
    sa = pd.concat([m[inst]["SA_max"] for inst in INSTRUMENTS])
    norm = plt.Normalize(*np.nanpercentile(sa, [2, 98]))
    v = m["vmp250"]
    ax.scatter(v["lon"], v["lat"], c=v["SA_max"], cmap=ps.SEQ_CHI, norm=norm, marker="o", s=22,
               edgecolor=ps.TEXT_2, linewidth=0.3, zorder=2)
    panel(ax, m["vmp5500"], "SA_max", ps.SEQ_CHI, norm, "salinity maximum (g kg⁻¹)",
          "a. Salt-rich subtropical water (both instruments)")
    ax.legend(handles=[plt.Line2D([], [], marker="o", ls="none", color=ps.MUTED, label=SHORT["vmp250"]),
                       plt.Line2D([], [], marker="s", ls="none", color=ps.MUTED, label=SHORT["vmp5500"])],
              loc="upper right")
    lo, hi = ts["r_rho_range"]
    panel(axs[0, 1], deep, "R_rho_median", ps.SEQ_EPSILON.reversed(), plt.Normalize(lo, hi),
          "density ratio Rρ (lower = stronger fingering)", "b. How strongly the water favours salt fingers")
    panel(axs[1, 0], deep.assign(pct=100 * deep["staircase_fraction_rollo2022"]), "pct", ps.SEQ_EPSILON,
          plt.Normalize(0, ts["staircase_pct_max"]), "% of the profile in staircases",
          "c. How much of the water column is staircased")
    lo, hi = ts["epsilon_map_range"]
    panel(axs[1, 1], deep, "epsilon_mean", ps.SEQ_CHI, LogNorm(lo, hi), r"turbulence $\varepsilon$ (W kg$^{-1}$)",
          "d. Turbulence level")
    for ax in axs[1]:
        ax.set_xlabel("longitude (°E)")
    for ax in axs[:, 0]:
        ax.set_ylabel("latitude (°N)")
    axs[0, 0].annotate("process station", (lon0, lat0), xytext=(-20, 30), textcoords="offset points",
                       ha="right", fontsize=10, arrowprops={"arrowstyle": "-", "color": ps.TEXT_2, "lw": 0.8})
    cov = 100 * deep["staircase_fraction_rollo2022"]
    info = {"staircase_pct_median": round(float(cov.median()), 1), "staircase_pct_range":
            [round(float(cov.min()), 1), round(float(cov.max()), 1)],
            "R_rho_median_range": [round(float(deep["R_rho_median"].min()), 2),
                                   round(float(deep["R_rho_median"].max()), 2)],
            "profiles_with_interfaces": int((deep["n_interfaces_rollo2022"] > 0).sum()), "profiles": len(deep)}
    headline(fig, f"Staircases are everywhere we looked: every deep profile has them, "
             f"covering {cov.min():.0f}–{cov.max():.0f}% of the water column below 150 m",
             f"Panels b–d: {SHORT[ts['map_instrument']]} profiles, 150 m to bottom (the VMP-250 reaches only "
             "~290 m). Circle: 48 h process station.")
    finish(fig, path, foot)
    return info


def binned_profile(prod: Path, inst: str, var: str, bin_m: float) -> pd.DataFrame:
    with xr.open_dataset(prod / f"binned_{inst}.nc") as b:
        x = b[var].to_pandas()                     # profile x depth
    edges = np.floor(x.columns.to_numpy() / bin_m) * bin_m + bin_m / 2
    per_prof = x.T.groupby(edges).mean().T         # mean of the 5 m bins within each coarse bin, per profile
    return pd.DataFrame({"depth": per_prof.columns, "mean": per_prof.mean(axis=0).to_numpy(),
                         "q25": per_prof.quantile(0.25).to_numpy(), "q75": per_prof.quantile(0.75).to_numpy(),
                         "n": per_prof.notna().sum(axis=0).to_numpy()})


def floor_profile(prod: Path, inst: str, bin_m: float) -> pd.Series:
    with xr.open_dataset(prod / f"segments_{inst}.nc") as s:
        d = pd.DataFrame({"depth": s["depth"].values, "floor": s["epsilon_floor"].values})
    d["bin"] = np.floor(d["depth"] / bin_m) * bin_m + bin_m / 2
    return d.groupby("bin")["floor"].median()


def figure_dissipation(prod: Path, ts: dict, path: Path, foot: str) -> dict:
    fig, axs = plt.subplots(1, 2, figsize=(13, 7), sharey=True)
    bin_m, n_min = ts["depth_bin_m"], ts["min_profiles"]
    info = {}
    for inst in INSTRUMENTS:
        col = ps.INSTRUMENT_COLOR[inst]
        for ax, var in ((axs[0], "epsilon_shear_bounded"), (axs[1], "chi")):
            p = binned_profile(prod, inst, var, bin_m)
            p = p[(p["n"] >= n_min) & (p["depth"] >= ts["min_depth_m"])]
            ax.fill_betweenx(p["depth"], p["q25"], p["q75"], color=col, alpha=0.18, lw=0)
            ax.plot(p["mean"], p["depth"], color=col, label=LABEL[inst])
            info.setdefault(inst, {})[var] = {
                "upper": float(f"{p.loc[p['depth'] < ts['deep_m'], 'mean'].mean():.2g}"),
                "deep": float(f"{p.loc[p['depth'] > ts['deep_m'], 'mean'].mean():.2g}")}
        f = floor_profile(prod, inst, bin_m)
        f = f[(f.index >= ts["min_depth_m"]) & (f.index <= p["depth"].max())]
        axs[0].plot(f.values, f.index, color=col, ls=":", lw=1.4, label=f"{SHORT[inst]} detection limit")
    axs[0].set_xlabel(r"turbulence, $\varepsilon$ (W kg$^{-1}$)")
    axs[1].set_xlabel(r"temperature mixing, $\chi$ (K$^2$ s$^{-1}$)")
    axs[0].set_ylabel("depth (m)")
    axs[0].invert_yaxis()
    axs[0].set_title("a. How turbulent the water is", loc="left")
    axs[1].set_title("b. How fast temperature fluctuations are smoothed out", loc="left")
    for ax in axs:
        ax.set_xscale("log")
    axs[0].legend(loc="lower left", fontsize=10)
    e5 = info["vmp5500"]["epsilon_shear_bounded"]
    headline(fig, f"Turbulence fades with depth (about {e5['upper'] / e5['deep']:.0f}× weaker below "
             f"{ts['deep_m']} m), but temperature mixing stays strong through the staircase depths",
             f"Lines: average over all profiles in {bin_m:.0f} m depth bins; shading: middle half of profiles. "
             "Dotted: the smallest turbulence each instrument can detect.")
    finish(fig, path, foot)
    return info


def figure_dd(prod: Path, ts: dict, path: Path, foot: str) -> dict:
    fig, axs = plt.subplots(1, 2, figsize=(15, 6.8), gridspec_kw={"width_ratios": [1.2, 1]})
    baselines = list(BASELINE_LABEL)
    sets = ts["dd_sets"]
    ax = axs[0]
    n = len(sets) * len(INSTRUMENTS)
    width = 0.7 / n
    info = {}
    for i, inst in enumerate(INSTRUMENTS):
        a = pick(load(prod, inst, "attribution"), ts)
        for j, st in enumerate(sets):
            off = (j * len(INSTRUMENTS) + i - (n - 1) / 2) * width
            for k, base in enumerate(baselines):
                r = a[(a["staircase"] == st) & (a["baseline"] == base)]
                if r.empty:
                    continue
                r = r.iloc[0]
                ax.errorbar(k + off, r["E"], yerr=[[r["E"] - r["E_ci_low"]], [r["E_ci_high"] - r["E"]]],
                            fmt=SET_MARKER[st], color=ps.INSTRUMENT_COLOR[inst], mfc="white" if st == "layer"
                            else ps.INSTRUMENT_COLOR[inst], mew=1.6, ms=9, capsize=3,
                            label=f"{SHORT[inst]}, {SET_LABEL[st]}" if k == 0 else None)
                info[f"E {inst} {st} {base}"] = [round(r["E"], 2), round(r["E_ci_low"], 2), round(r["E_ci_high"], 2)]
    ax.axhline(1, color=ps.TEXT, lw=1.2)
    ax.text(0.01, 0.02, "above the line: more heat mixing than the baseline explains", fontsize=10,
            color=ps.TEXT_2, va="bottom", transform=ax.transAxes)
    ax.set_yscale("log")
    plain_log_axis(ax.yaxis, ts["e_ticks"])
    ax.set_xticks(range(len(baselines)), [BASELINE_LABEL[b] for b in baselines])
    ax.set_xlim(-0.5, len(baselines) - 0.5)
    ax.set_ylabel("observed ÷ expected temperature mixing")
    ax.set_title("a. Heat mixing compared with three baselines", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, fontsize=10)

    ax = axs[1]
    g = f"g{ts['gamma_mid']}"
    centers = []
    for gi, st in enumerate(ts["k_sets"]):
        centers.append(gi)
        for i, inst in enumerate(INSTRUMENTS):
            r = pick(load(prod, inst, "diffusivity"), ts, turner="finger_any", staircase=st, depth_bin="pooled")
            if r.empty:
                continue
            r = r.iloc[0]
            col = ps.INSTRUMENT_COLOR[inst]
            x = gi + (i - 0.5) * 0.36
            ax.errorbar(x - 0.07, r["K_T"], yerr=[[r["K_T"] - r["K_T_ci_low"]], [r["K_T_ci_high"] - r["K_T"]]],
                        fmt="o", color=col, ms=9, capsize=3)
            ax.errorbar(x + 0.07, r[f"K_S_{g}"], yerr=[[r[f"K_S_{g}"] - r[f"K_S_{g}_ci_low"]],
                                                       [r[f"K_S_{g}_ci_high"] - r[f"K_S_{g}"]]],
                        fmt="^", color=col, mfc="white", ms=10, capsize=3, mew=1.8)
            ax.plot([x - 0.14, x + 0.14], [r["K_GM"]] * 2, color=ps.TEXT_2, lw=2)
            info[f"K {inst} {st}"] = {"K_T": float(f"{r['K_T']:.2g}"), "K_S": float(f"{r[f'K_S_{g}']:.2g}"),
                                      "K_GM": float(f"{r['K_GM']:.2g}")}
    ax.set_xticks(centers, [SET_LABEL[s] for s in ts["k_sets"]])
    ax.set_xlim(-0.5, len(centers) - 0.5)
    ax.set_yscale("log")
    ax.set_ylabel(r"diffusivity (m$^2$ s$^{-1}$), 150 m to bottom")
    ax.set_title("b. How fast heat and salt mix", loc="left")
    h = [plt.Line2D([], [], marker="o", ls="none", color=ps.TEXT_2, ms=9, label="heat"),
         plt.Line2D([], [], marker="^", ls="none", color=ps.TEXT_2, mfc="white", ms=10, mew=1.8,
                    label=f"salt (and nitrate), γ = {ts['gamma_mid']}"),
         plt.Line2D([], [], color=ps.TEXT_2, lw=2, label="typical internal-wave mixing"),
         plt.Line2D([], [], marker="s", ls="none", color=ps.INSTRUMENT_COLOR["vmp250"], label=SHORT["vmp250"]),
         plt.Line2D([], [], marker="s", ls="none", color=ps.INSTRUMENT_COLOR["vmp5500"], label=SHORT["vmp5500"])]
    ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=10)
    e250 = info["E vmp250 interface nonstaircase_control"][0]
    e5500 = info["E vmp5500 interface nonstaircase_control"][0]
    ks = np.mean([info[f"K {i} interface"]["K_S"] / info[f"K {i} interface"]["K_T"] for i in INSTRUMENTS])
    headline(fig, f"Staircase interfaces mix heat {min(e250, e5500):.1f}–{max(e250, e5500):.1f}× more than "
             f"nearby water without staircases; if salt fingers carry the fluxes, salt (and nitrate) "
             f"mixes about {ks:.1f}× faster than heat",
             "Bars: 95% ranges from resampling profiles. All free-fall casts; staircases labelled by "
             f"{ts['staircase_method']}; local (finescale) gradients.")
    finish(fig, path, foot)
    return info


def figure_diffusivity(prod: Path, ts: dict, dd_bin: float, path: Path, foot: str) -> dict:
    fig, axs = plt.subplots(1, 2, figsize=(13, 7))
    g = f"g{ts['gamma_mid']}"
    info = {}
    for ax, inst in zip(axs, INSTRUMENTS):
        d = load(prod, inst, "diffusivity")
        f = pick(d, ts, turner="finger_any", staircase="all")
        f = f[(f["depth_bin"] != "pooled") & f["min_profiles_ok"]].assign(z=lambda x: x["depth_bin"].astype(float))
        f = f.sort_values("z")
        ks = f[[f"K_S_g{x}" for x in ts["gammas"]]]
        ax.fill_betweenx(f["z"], ks.min(axis=1), ks.max(axis=1), color=ps.ORANGE, alpha=0.2, lw=0,
                         label=f"salt (and nitrate), γ {min(ts['gammas'])}–{max(ts['gammas'])}")
        ax.plot(f[f"K_S_{g}"], f["z"], color=ps.ORANGE)
        ax.fill_betweenx(f["z"], f["K_T_ci_low"], f["K_T_ci_high"], color=ps.BLUE, alpha=0.18, lw=0)
        ax.plot(f["K_T"], f["z"], color=ps.BLUE, label="heat")
        ax.plot(f["K_GM"], f["z"], color=ps.TEXT, ls="-.", lw=1.3, label="typical internal-wave mixing")
        ax.plot(f["K_rho"], f["z"], color=ps.MUTED, ls=":", lw=1.6,
                label="what shear turbulence alone would give")
        ax.set_xscale("log")
        ax.set_xlim(*ts["k_range"])
        ax.invert_yaxis()
        ax.set_title(f"{'ab'[INSTRUMENTS.index(inst)]}. {LABEL[inst]}", loc="left")
        ax.set_xlabel(r"diffusivity (m$^2$ s$^{-1}$)")
        info[inst] = {"K_T_over_K_rho_median": round(float((f["K_T"] / f["K_rho"]).median()), 1)}
    axs[0].set_ylabel("depth (m)")
    fig.legend(*axs[1].get_legend_handles_labels(), loc="lower center", bbox_to_anchor=(0.5, 0.04),
               ncol=4, fontsize=10.5)
    r = np.mean([v["K_T_over_K_rho_median"] for v in info.values()])
    headline(fig, f"In finger-favourable water heat mixes about {r:.0f}× faster than shear turbulence alone "
             "would give; under the salt-finger model, salt (and nitrate) mixes faster still",
             f"Averages over all profiles in {dd_bin:.0f} m bins, from 150 m down. Blue shading: 95% range for heat; "
             "orange shading: range of the salt-to-heat flux ratio γ.")
    finish(fig, path, foot, bottom=0.1)
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    ts = config["team_summary"]
    pc = config["products"]
    root = common.run_dir_of(config).parent
    prod = root / pc["recommended_dir"]
    out = root / "comparisons" / ts["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    with xr.open_dataset(prod / "segments_vmp5500.nc") as s:
        a = s.attrs
    foot = (f"products {a['product_version']}, run {a['run_name']}; spice_microstructure git "
            f"{a['git_commit'][:7]}; microstructure-tpw {a['microstructure_tpw_commit'][:7]}")
    slide_style()
    summary = {"products": foot, "settings": ts,
               "overview": figure_overview(prod, ts, out / "overview.png", foot),
               "maps": figure_maps(prod, ts, out / "maps.png", foot),
               "dissipation": figure_dissipation(prod, ts, out / "dissipation_profiles.png", foot),
               "double_diffusion": figure_dd(prod, ts, out / "double_diffusion.png", foot),
               "diffusivity": figure_diffusivity(prod, ts, config["double_diffusion"]["depth_bin_m"],
                                                 out / "diffusivity_profiles.png", foot)}
    common.write_json(out / "summary.json", summary)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
