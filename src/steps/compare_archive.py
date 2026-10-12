#!/usr/bin/env python3
"""Step compare_archive: sanity check of this run against the shipboard outputs.

This is not a pass/fail test (CLAUDE.md, First milestone). Differences mix
package changes (0.3.1 -> pinned commit) with pipeline changes; large shifts
call for reading the microstructure-tpw changelog before assuming an error.

Reads:  <run_dir>/convert/<instrument>/{diss,chi}_binned_NN/binned.nc and
        per-profile diss_NN/*.nc; the archive's equivalents in the generation
        given by instruments.<name>.archive_generation.
Writes: <run_dir>/compare_archive/
          compare_summary_<instrument>.csv   per-variable statistics
          compare_profiles_<instrument>.csv  per-profile median ratios
          figures/compare_<instrument>.png   new vs archive and ratio vs depth
          compare_report.json, step_metadata.json

Profiles are matched by start time (stime) and values compared in the common
1 m depth bins, so a shift in dissipation-window placement does not break the
pairing. Ratios are new / archive.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

STEP = "compare_archive"
# T_mean (viscosity reference temperature), nu and speed are compared because
# they explain most epsilon differences between versions.
VARIABLES = {"diss": ["epsilonMean", "e_1", "e_2", "T_mean", "nu", "speed", "N2", "dTdz"],
             "chi": ["chiMean", "chi_1", "chi_2"]}
POSITIVE = {"epsilonMean", "e_1", "e_2", "chiMean", "chi_1", "chi_2"}


def load(root: Path, kind: str) -> tuple[xr.Dataset, pd.DataFrame]:
    ds = xr.open_dataset(common.single_dir(root, f"{kind}_binned") / "binned.nc")
    table = common.profile_table(common.single_dir(root, "diss"))
    return ds, table


def match_profiles(a: xr.Dataset, b: xr.Dataset, tol_s: float = 1.0) -> list[tuple[int, int]]:
    tb = b["stime"].values
    pairs = []
    for i, t in enumerate(a["stime"].values):
        j = int(np.nanargmin(np.abs(tb - t)))
        if abs(tb[j] - t) <= tol_s:
            pairs.append((i, j))
    return pairs


def label_profiles(ds: xr.Dataset, table: pd.DataFrame) -> list[str]:
    names = []
    for t in ds["stime"].values:
        d = (table["stime"] - t).abs()
        names.append(table.loc[d.idxmin(), "profile_file"] if d.min() <= 1.0 else "")
    return names


def compare(new: xr.Dataset, arc: xr.Dataset, pairs, var: str):
    bins = np.intersect1d(new["bin"].values, arc["bin"].values)
    ia, ib = zip(*pairs)
    a = new[var].sel(bin=bins).isel(profile=list(ia)).values
    b = arc[var].sel(bin=bins).isel(profile=list(ib)).values
    return bins, a, b


def stats(a: np.ndarray, b: np.ndarray, var: str) -> dict:
    both = np.isfinite(a) & np.isfinite(b)
    only_new = int((np.isfinite(a) & ~np.isfinite(b)).sum())
    # Dissipation windows land in single 1 m bins; a shifted window grid
    # (e.g. epsilon.anchor) shows as values in only one of the two runs.
    out = {"variable": var, "bins_both": int(both.sum()), "only_new": only_new,
           "only_archive": int((~np.isfinite(a) & np.isfinite(b)).sum()),
           "aligned_fraction": round(both.sum() / max(both.sum() + only_new, 1), 3)}
    if var in POSITIVE:
        ok = both & (a > 0) & (b > 0)
        r = np.log10(a[ok] / b[ok])
        if r.size:
            out.update({"median_ratio": 10 ** np.median(r),
                        "ratio_p05": 10 ** np.percentile(r, 5),
                        "ratio_p95": 10 ** np.percentile(r, 95),
                        "frac_within_10pct": float(np.mean(np.abs(r) <= np.log10(1.1))),
                        "frac_within_factor2": float(np.mean(np.abs(r) <= np.log10(2)))})
    else:
        d = a[both] - b[both]
        if d.size:
            out.update({"median_diff": float(np.median(d)),
                        "diff_p05": float(np.percentile(d, 5)),
                        "diff_p95": float(np.percentile(d, 95)),
                        "frac_within_rel_1e-3": float(np.mean(np.isclose(a[both], b[both],
                                                                         rtol=1e-3, atol=0)))})
    return out


def figure(name: str, data: dict, path: Path, foot: str) -> None:
    ps.apply()
    fig, axes = plt.subplots(2, 2, figsize=(8.5, 7.5))
    for col, (var, label, cmap) in enumerate([("epsilonMean", r"$\varepsilon$ (W kg$^{-1}$)",
                                               ps.SEQ_EPSILON),
                                              ("chiMean", r"$\chi$ (K$^2$ s$^{-1}$)", ps.SEQ_CHI)]):
        bins, a, b = data[var]
        ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
        la, lb = np.log10(a[ok]), np.log10(b[ok])
        ax = axes[0, col]
        lo, hi = np.percentile(np.r_[la, lb], [0.5, 99.5])
        h = ax.hist2d(lb, la, bins=80, range=[[lo, hi], [lo, hi]], cmap=cmap, cmin=1,
                      norm=plt.matplotlib.colors.LogNorm())
        ax.plot([lo, hi], [lo, hi], color=ps.TEXT_2, lw=0.8, ls="--")
        ax.set_xlabel(f"archive log$_{{10}}$ {label}")
        ax.set_ylabel(f"this run log$_{{10}}$ {label}")
        ax.set_title(f"{var}: new vs archive (1 m bins)")
        fig.colorbar(h[3], ax=ax, label="bins", shrink=0.8)

        ax = axes[1, col]
        # Ratios grouped into 10 m bands: only part of the 1 m bins hold a
        # value in both runs, so single bins are too sparse at depth.
        r = np.where(ok, np.log10(np.where(ok, a, 1) / np.where(ok, b, 1)), np.nan)
        band = np.floor(bins / 10) * 10 + 5
        df = pd.DataFrame(r, index=band).stack().rename("r").reset_index(level=0)
        g = df.groupby("level_0")["r"]
        prof = pd.DataFrame({"med": g.median(), "p05": g.quantile(0.05),
                             "p95": g.quantile(0.95), "n": g.size()})
        prof = prof[prof["n"] >= 5]
        fill, line = (ps.BLUE_RAMP[1], ps.BLUE) if var == "epsilonMean" else (ps.ORANGE_RAMP[1], ps.ORANGE)
        ax.fill_betweenx(prof.index, prof["p05"], prof["p95"], color=fill, lw=0,
                         label="5–95 % (10 m bands)")
        ax.plot(prof["med"], prof.index, color=line, lw=1.2, label="median")
        ax.axvline(0, color=ps.TEXT_2, lw=0.8, ls="--")
        ax.invert_yaxis()
        ax.set_xlabel(f"log$_{{10}}$ new / archive, {var}")
        ax.set_ylabel("depth (m)")
        ax.legend(loc="lower left")
    fig.suptitle(f"{name}: this run vs shipboard archive (sanity check, not pass/fail)",
                 x=0.01, ha="left")
    fig.tight_layout()
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


def run(ctx: dict) -> None:
    warnings.filterwarnings("ignore", message="All-NaN slice encountered")
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    report = {}

    for name, inst in common.instruments(config):
        new_root = ctx["run_dir"] / "convert" / name
        gen = str(inst["archive_generation"])
        arc_root = Path(inst["archive_processed"])
        summaries, fig_data, per_profile = [], {}, None
        for kind, variables in VARIABLES.items():
            new, new_tab = load(new_root, kind)
            arc = xr.open_dataset(arc_root / f"{kind}_binned_{gen}" / "binned.nc")
            pairs = match_profiles(new, arc)
            names = label_profiles(new, new_tab)
            for var in variables:
                bins, a, b = compare(new, arc, pairs, var)
                summaries.append({"kind": kind, "profiles_new": new.sizes["profile"],
                                  "profiles_archive": arc.sizes["profile"],
                                  "profiles_matched": len(pairs), **stats(a, b, var)})
                if var in ("epsilonMean", "chiMean"):
                    fig_data[var] = (bins, a, b)
                if var in POSITIVE:
                    ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
                    r = np.where(ok, np.log10(np.where(ok, a, 1) / np.where(ok, b, 1)), np.nan)
                    col = pd.Series(10 ** np.nanmedian(r, axis=0),
                                    index=[names[i] for i, _ in pairs], name=f"{var}_median_ratio")
                    per_profile = col.to_frame() if per_profile is None else per_profile.join(col)
        summary = pd.DataFrame(summaries)
        summary.to_csv(out / f"compare_summary_{name}.csv", index=False)
        per_profile.index.name = "profile_file"
        per_profile.to_csv(out / f"compare_profiles_{name}.csv")
        figure(name, fig_data, out / "figures" / f"compare_{name}.png",
               f"{common.provenance_string(prov)}; archive {arc_root.name} generation _{gen}")

        # Known, expected difference: data_0112.p sh2 sensitivity 0.1134 -> 0.1079
        # gives e_2 x (0.1134/0.1079)^2 = 1.105 (epsilon goes as sens^-2).
        checks = {}
        if name == "vmp250":
            rows = per_profile[per_profile.index.str.startswith("data_0112_")]
            checks["data_0112_e_2_expected_ratio"] = round((0.1134 / 0.1079) ** 2, 4)
            checks["data_0112_e_2_observed_median_ratios"] = rows["e_2_median_ratio"].round(4).tolist()
            checks["data_0112_e_1_observed_median_ratios"] = rows["e_1_median_ratio"].round(4).tolist()
        report[name] = {"archive": str(arc_root), "archive_generation": gen,
                        "summary": summary.to_dict("records"), "checks": checks}
        eps = summary.set_index("variable").loc["epsilonMean"]
        chi = summary.set_index("variable").loc["chiMean"]
        print(f"  {name}: epsilon median ratio {eps['median_ratio']:.3f} "
              f"({eps['frac_within_10pct']:.0%} within 10%), chi median ratio "
              f"{chi['median_ratio']:.3f} ({chi['frac_within_10pct']:.0%} within 10%)")

    common.write_json(out / "compare_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
