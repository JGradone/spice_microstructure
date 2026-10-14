#!/usr/bin/env python3
"""Publish the recommended final products to one clearly named directory.

Copies the products of products.recommended_run (outputs/<run>/products/) to
outputs/<products.recommended_dir>/, adds the run summary (RUN_SUMMARY.md) and
the sensitivity comparison, and writes a README that says which files and
variables to use and the uncertainty ranges implied by the sensitivity runs:
  * processing choices (stratification scale, bins, staircase threshold,
    alpha/beta window): spread of K_S and of the interface excess;
  * FP07 response model (double-pole run);
  * gamma (K_S at the lowest and highest gamma);
  * the finger-fraction spread across baselines.
The directory is rebuilt from scratch each time (it only ever holds copies).

Usage:
    python scripts/publish_recommended.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402

MARKER = ".recommended_products"


def rng(vals) -> str:
    v = np.array([x for x in vals if np.isfinite(x)], float)
    return f"{v.min():.2g}–{v.max():.2g}" if len(v) else "–"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    p = config["products"]
    run = p["recommended_run"]
    cfg = config if run == config["run"]["name"] else common.apply_sensitivity(config, config_hash, run)[0]
    src = common.run_dir_of(cfg) / "products"
    root = REPO / config["paths"]["output_root"]
    dest = root / p["recommended_dir"]
    if dest.exists():
        if not (dest / MARKER).exists():
            sys.exit(f"{dest} exists but was not created by this script; refusing to replace it")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / MARKER).write_text(f"built from {src}\n")
    for f in sorted(src.iterdir()):
        if f.is_file() and f.suffix in (".nc", ".csv"):
            shutil.copy2(f, dest / f.name)
    shutil.copy2(src / "README.md", dest / "RUN_SUMMARY.md")
    meta = json.loads((src / "step_metadata.json").read_text())

    g = [float(x) for x in cfg["diffusivities"]["gammas"]]
    g0 = float(cfg["double_diffusion"]["flux_ratio_gamma"])
    m = cfg["regimes"]["staircase"]["methods"][-1]
    diff = pd.read_csv(common.run_dir_of(cfg) / "diffusivities" / "diffusivity_bins.csv")
    att = pd.read_csv(common.run_dir_of(cfg) / "diffusivities" / "attribution.csv")
    sens_path = root / "comparisons" / p["recommended_sensitivity_label"] / "sensitivity_summary.csv"
    sens = pd.read_csv(sens_path) if sens_path.exists() else None
    if sens is not None:
        shutil.copy2(sens_path, dest / "sensitivity_summary.csv")
        png = sens_path.with_suffix(".png")
        if png.exists():
            shutil.copy2(png, dest / "sensitivity_summary.png")

    rows = []
    for inst in cfg["run"]["instruments"]:
        d = diff[(diff["instrument_group"] == f"{inst} all free fall") & (diff["method"] == m)
                 & (diff["turner"] == "finger_any") & (diff["staircase"] == "all") & (diff["gradients"] == "finescale")
                 & (diff["depth_bin"].astype(str) == "pooled")].iloc[0]
        r = {"instrument": inst, "K_S": d[f"K_S_g{g0:g}"], "K_S_lo": d[f"K_S_g{g0:g}_ci_low"],
             "K_S_hi": d[f"K_S_g{g0:g}_ci_high"], "K_S_gmin": d[f"K_S_g{max(g):g}"], "K_S_gmax": d[f"K_S_g{min(g):g}"],
             "K_T": d["K_T"], "K_GM": d["K_GM"]}
        if sens is not None:
            s = sens[sens["instrument"] == inst]
            proc = s[~s["run"].isin(["fft2_diss8_mle_dp", "an_epsT"])]
            r["K_S_proc"] = rng(proc["K_S_finger"])
            r["E_proc"] = rng(proc["E_interface"])
            dp = s[s["run"] == "fft2_diss8_mle_dp"]
            r["K_S_dp_ratio"] = float(dp["K_S_finger_rel"].iloc[0]) if len(dp) else np.nan
        a = att[(att["instrument_group"] == f"{inst} all free fall") & (att["staircase"] == "interface")
                & (att["gradients"] == "finescale")]
        r["ff_baselines"] = rng(a["finger_fraction"])
        rows.append(r)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Recommended SPICE microstructure products", "",
        f"Copies of the products of run **`{run}`**: {cfg['perturb']['epsilon']['fft_sec']:g} s FFT / "
        f"{cfg['perturb']['epsilon']['diss_sec']:g} s windows, chi by {cfg['perturb']['chi']['fit_method']}, "
        f"FP07 {cfg['perturb']['chi']['fp07_model']}. These are the files to take into other analyses. "
        f"Built {now} by `scripts/publish_recommended.py` from `{src.relative_to(REPO)}` "
        f"(exported with spice_microstructure git {meta.get('git_commit')}, config sha256 "
        f"{str(meta.get('config_sha256'))[:12]}, microstructure-tpw {meta.get('microstructure_tpw_commit')}). "
        "Do not edit; rebuild with the script.", "",
        "`RUN_SUMMARY.md` has the full settings, file list, QC counts and caveats of the run. Variable definitions: "
        "`docs/products.md`; methods and reasons: `docs/decisions.md`.", "",
        "## What to use", "",
        "* **Vertical diffusivities for nutrient (nitrate) fluxes:** `diffusivity_<instrument>.csv` (or `.nc`). In "
        "finger-favourable water use `K_S_g<gamma>` (salt diffusivity; nitrate behaves like salt in fingering, "
        "K_N ≈ K_S is an assumption to state). Use `K_T` for heat and, outside finger water, `K_rho` (flag "
        "`K_rho_valid`). Take `gradients = finescale` as the primary estimate and report the others as sensitivity; "
        f"take `method = {m}` (tuned staircase labels; `vdb2021` is the published-threshold alternative). "
        "Groups: `<instrument> all free fall` for cruise-wide averages, `process_station free fall` / `tow-yo` for "
        "the station (never pool tow-yo with free fall). `depth_bin = pooled` for whole-depth values, numeric "
        "depth bins for profiles. Use rows with `min_profiles_ok` true; `K_S_applicable` marks where K_S is defined.",
        "* **Finger contribution:** `attribution_<instrument>.csv`. Report the range across `baseline` values, not a "
        "single number.",
        "* **Mesoscale comparisons (cast to cast):** `cast_metrics_<instrument>.csv` with `casts_<instrument>.csv` "
        "(time, position, flags).",
        "* **Your own averages:** `segments_<instrument>.nc` (one record per window). Average epsilon, chi and "
        "gradients over windows and profiles first, then form diffusivities; never per window. Respect the QC flags "
        "and `shear_keep`, `chi_keep`, `ts_salinity_invalid`.",
        "* **Profiles:** `binned_<instrument>.nc` (5 m bins per profile).", "",
        "## Headline values and uncertainty ranges", "",
        f"Finger-favourable water, whole cruise, finescale gradients (m²/s). Processing range = across sensitivity runs "
        f"(stratification scale 5/10/25 m, 10 m bins, staircase threshold, α/β window). Interface excess E is over the "
        f"Re_b-matched doubly stable control.", "",
        f"| | K_S (γ {g0:g}) [95% CI] | K_S for γ {max(g):g}–{min(g):g} | K_S processing range | K_S with double-pole "
        "FP07 | K_T | K_GM | interface E, processing range | interface finger fraction across baselines |",
        "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['instrument']} | {r['K_S']:.2g} [{r['K_S_lo']:.2g}, {r['K_S_hi']:.2g}] | "
                     f"{r['K_S_gmin']:.2g}–{r['K_S_gmax']:.2g} | {r.get('K_S_proc', '–')} | "
                     f"×{r.get('K_S_dp_ratio', np.nan):.2f} | {r['K_T']:.2g} | {r['K_GM']:.2g} | "
                     f"{r.get('E_proc', '–')} | {r['ff_baselines']} |")
    lines += ["",
              "Reading: K_S is robust to processing choices; the FP07 response model (×~0.5 with double-pole) and γ "
              "are its main uncertainties. The interface excess and finger fraction depend on the baseline and on "
              "the stratification scale; report them as ranges. `sensitivity_summary.csv` / `.png` give every run.",
              "", "## Caveats", "", "See `RUN_SUMMARY.md` (Caveats)."]
    (dest / "README.md").write_text("\n".join(lines) + "\n")
    print(f"published {len(list(dest.glob('*.csv')))} CSV and {len(list(dest.glob('*.nc')))} NetCDF files to "
          f"{dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
