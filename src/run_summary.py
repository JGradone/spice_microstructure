"""Human-readable run summary (README.md) for an exported products directory.

Assembled from the step reports and result tables of one run, so the JSON
reports never need to be opened: run settings and their difference from the
baseline, the product files, QC counts per instrument, headline results, the
caveats, and the reproduction check when one exists. Called by the export step
and by scripts/write_run_summaries.py (to regenerate it for existing products).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FILES = {
    "casts": "one row per profile: time, position, station, tow-yo, exclusions (file or profile), cautions, probe "
             "serials and sensitivities, Sealog notes",
    "segments": "one record per dissipation window: epsilon and chi per probe and combined, noise floors and flags, "
                "epsilon_T, background hydrography, Turner class, staircase labels per method, Re_b, QC bit flags",
    "binned": "per profile in depth bins: window means of epsilon and chi with counts, and the hydrography",
    "diffusivity": "bin averages over windows and profiles by group, regime, staircase label, gradient choice and "
                   "depth: K_T, R_rho, K_S (each gamma), K_S_eps, K_rho, K_GM, 95% profile-bootstrap intervals",
    "attribution": "finger fraction 1 - 1/E against each baseline (Gamma 0.2 theory, Garrett-Munk, Re_b-matched "
                   "control) with intervals",
    "cast_metrics": "per-profile finger metrics: salinity maximum, R_rho, finger fraction, staircase occurrence and "
                    "geometry, K_T relative to Garrett-Munk",
}


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _csv(path: Path):
    try:
        return pd.read_csv(path, low_memory=False)
    except (OSError, ValueError):
        return None


def _fmt(v, nd=2, sci=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    if sci:
        return f"{v:.2g}"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def _settings(config) -> list[str]:
    pe, pc = config["perturb"]["epsilon"], config["perturb"]["chi"]
    sq, rc, dd = config["shear_qc"], config["regimes"], config["double_diffusion"]
    rows = [
        ("FFT / dissipation length", f"{pe['fft_sec']:g} s / {pe['diss_sec']:g} s (overlap {pe['overlap_sec']:g} s)"),
        ("chi fit", f"{pc['fit_method']}, {pc['spectrum_model']}, FP07 {pc['fp07_model']}"),
        ("shear epsilon", f"refit from {sq['refit']['f_min_hz']:g} Hz" if sq["refit"]["enabled"] else "perturb's values"),
        ("noise floors", f"kept, flagged below {sq['noise_floor']['factor']:g}x floor, bounded value provided"),
        ("segment QC applied", str(config["segments"]["enabled"])),
        ("background gradients", f"linear fits over {config['hydrography']['gradient_smoothing_m']:g} m"),
        ("Turner class scale", f"{rc['turner_smoothing_m']:g} m"),
        ("staircase thresholds (ml_grad)", ", ".join(f"{m} {rc['staircase'][m]['ml_grad']:g}"
                                                      for m in rc["staircase"]["methods"])),
        ("epsilon in chi_expected", dd["epsilon_source"]),
        ("gamma", ", ".join(f"{g:g}" for g in config["diffusivities"]["gammas"])),
        ("depth bins (tests / products)", f"{dd['depth_bin_m']:g} m / {config['products']['depth_bin_m']:g} m"),
    ]
    return ["| Setting | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]


def _qc_table(run_dir: Path, names) -> list[str]:
    seg = _load(run_dir / "segments" / "segments_report.json") or {}
    sh = _load(run_dir / "epsilon_shear" / "epsilon_shear_report.json") or {}
    th = _load(run_dir / "thermistor" / "thermistor_report.json") or {}
    hy = _load(run_dir / "hydrography" / "hydrography_report.json") or {}
    rg = _load(run_dir / "regimes" / "regimes_report.json") or {}
    rows = []

    def add(label, fn):
        vals = []
        for n in names:
            try:
                vals.append(fn(n))
            except (KeyError, TypeError, ZeroDivisionError):
                vals.append("–")
        rows.append(f"| {label} | " + " | ".join(vals) + " |")

    i = lambda r, n: r["instruments"][n]  # noqa: E731
    add("profiles", lambda n: str(i(seg, n)["profiles"]))
    add("dissipation windows", lambda n: str(i(seg, n)["windows"]))
    add(f"segment QC flags (applied: {seg.get('applied')})",
        lambda n: f"{i(seg, n)['removed']} ({i(seg, n)['removed_fraction']:.1%}): "
                  + ", ".join(f"{k} {v}" for k, v in i(seg, n)["removed_sequentially"].items() if v))
    add("probe exclusions (windows)", lambda n: ", ".join(f"{k} {v}" for k, v in
                                                          i(seg, n)["probe_exclusions_windows"].items() if v) or "none")
    add("shear: probe estimates removed", lambda n: ", ".join(f"{k} {v}" for k, v in
                                                              i(sh, n)["probe_estimates_removed"].items() if v) or "none")
    add("shear: probes disagree (smaller kept)", lambda n: str(i(sh, n)["probe_disagree"]))
    add("shear: windows kept", lambda n: f"{i(sh, n)['kept']} of {i(sh, n)['windows']}")
    add("shear: at noise floor (below 150 dbar)", lambda n: f"{i(sh, n)['at_floor_fraction_below_150dbar']:.0%}, "
                                                            f"median floor {i(sh, n)['floor_median_below_150dbar_w_kg']:.1e} W/kg")
    add("shear: median epsilon below 150 dbar", lambda n: f"{i(sh, n)['epsilon_median_below_150dbar_w_kg']:.1e} W/kg")
    add("chi: windows kept", lambda n: f"{i(th, n)['kept']} of {i(th, n)['windows']}")
    add("chi: at noise floor (below 150 dbar)", lambda n: f"{i(th, n)['at_floor_fraction_below_150']:.1%}")
    add("epsilon_T roll-off resolved (below 150 dbar)", lambda n: f"{i(th, n)['epsilon_T_resolved_fraction_below_150']:.0%}")
    add("salinity source", lambda n: i(hy, n)["salinity_source"])
    add("N2 vs ship CTD, 150-550 m (median ratio; N2<=0)",
        lambda n: f"{i(hy, n)['validation_150_550m']['N2_median_ratio']:.2f}; "
                  f"{i(hy, n)['validation_150_550m']['N2_nonpositive_fraction']:.0%} "
                  f"(ship {i(hy, n)['validation_150_550m']['ship_N2_nonpositive_fraction']:.0%})")
    add("windows with T-S salinity invalid (T inversions)", lambda n: str(i(hy, n)["windows_ts_salinity_invalid"]))
    add("Turner class below 150 dbar", lambda n: ", ".join(f"{k} {v}" for k, v in i(rg, n)["turner_class_below_150"].items()))
    for m in (rg.get("regimes", {}).get("staircase", {}).get("methods") or []):
        add(f"staircase windows below 150 dbar ({m})",
            lambda n, m=m: ", ".join(f"{k} {v}" for k, v in i(rg, n)[f"staircase_{m}_below_150"].items())
            + f"; {i(rg, n)[f'profiles_with_interfaces_{m}']} profiles with interfaces")
    add("median Re_b below 150 dbar (shear)", lambda n: f"{i(rg, n)['Re_b_shear_median_below_150']:.1f}")
    return [f"| | {' | '.join(names)} |", "|---|" + "---|" * len(names)] + rows


def _headlines(run_dir: Path, config) -> list[str]:
    diff = _csv(run_dir / "diffusivities" / "diffusivity_bins.csv")
    att = _csv(run_dir / "diffusivities" / "attribution.csv")
    if diff is None:
        return ["Diffusivity results not available for this run."]
    g0 = float(config["double_diffusion"]["flux_ratio_gamma"])
    m = config["regimes"]["staircase"]["methods"][-1]
    out = [f"Whole cruise, all free-fall casts, finger-favourable water, finescale gradients, staircase labels {m}. "
           f"K in m²/s; brackets are 95% bootstrap intervals over profiles.", "",
           f"| Group | Set | K_T | K_S (γ {g0:g}) | K_S_eps | K_GM | profiles |", "|---|---|---|---|---|---|---|"]
    sel = diff[(diff["depth_bin"].astype(str) == "pooled") & (diff["method"] == m) & (diff["gradients"] == "finescale")
               & diff["instrument_group"].str.contains("all free fall")]
    for _, r in sel[(sel["turner"] == "finger_any") & sel["staircase"].isin(["all", "interface", "layer"])].iterrows():
        out.append(f"| {r['instrument_group']} | {r['staircase']} | {_fmt(r['K_T'], sci=True)} "
                   f"[{_fmt(r.get('K_T_ci_low'), sci=True)}, {_fmt(r.get('K_T_ci_high'), sci=True)}] | "
                   f"{_fmt(r.get(f'K_S_g{g0:g}'), sci=True)} [{_fmt(r.get(f'K_S_g{g0:g}_ci_low'), sci=True)}, "
                   f"{_fmt(r.get(f'K_S_g{g0:g}_ci_high'), sci=True)}] | {_fmt(r.get(f'K_S_eps_g{g0:g}'), sci=True)} | "
                   f"{_fmt(r['K_GM'], sci=True)} | {int(r['n_profiles'])} |")
    for _, r in sel[(sel["turner"] == "control") & (sel["staircase"] == "all")].iterrows():
        out.append(f"| {r['instrument_group']} | doubly stable control | {_fmt(r['K_T'], sci=True)} | – | – | "
                   f"{_fmt(r['K_GM'], sci=True)} | {int(r['n_profiles'])} |")
    if att is not None and len(att):
        a = att[att["instrument_group"].str.contains("all free fall") & (att["staircase"] == "interface")
                & (att["gradients"] == "finescale")]
        out += ["", "Interface finger fraction 1 − 1/E by baseline (finescale gradients). The spread is part of the "
                "result; it also depends on the stratification scale (docs/decisions.md).", "",
                "| Group | Baseline | E | finger fraction |", "|---|---|---|---|"]
        for _, r in a.iterrows():
            out.append(f"| {r['instrument_group']} | {r['baseline']} | {_fmt(r['E'])} "
                       f"[{_fmt(r['E_ci_low'])}, {_fmt(r['E_ci_high'])}] | {_fmt(r['finger_fraction'])} |")
    return out


def write_readme(config: dict, prov: dict, run_dir: Path, out_dir: Path, caveats: list[str],
                 provenance_line: str, regenerated: str | None = None) -> Path:
    run = config["run"]
    names = list(config["run"]["instruments"])
    sens = run.get("sensitivity", {})
    lines = [f"# SPICE microstructure products: `{run['name']}`", "",
             f"Product version {config['products']['product_version']}. {provenance_line}.", ""]
    if regenerated:
        lines += [f"(This summary regenerated {regenerated} from the run's existing reports.)", ""]
    lines += [run.get("notes", "").strip(), "",
              ("**Baseline run** (shipboard settings)." if not sens else
               f"**Sensitivity run** of `{sens.get('of')}`" + (f", based on `{sens['base']}`" if sens.get("base") else "")
               + ". Overrides: " + ", ".join(f"`{k}` = {v}" for k, v in sens.get("set", {}).items()) + "."), "",
              "Specification of every variable: `docs/products.md`. Methods and the reasons behind them: "
              "`docs/decisions.md`. Rerun: `python src/run_pipeline.py --config config/config.yaml"
              + (f" --sensitivity {run['name']}" if sens else "") + "`.", "",
              "## Settings", ""] + _settings(config)
    files = sorted(p.name for p in out_dir.iterdir() if p.is_file() and p.suffix in (".nc", ".csv"))
    lines += ["", "## Files", "", "| File | Contents |", "|---|---|"]
    for f in files:
        key = next((k for k in FILES if f.startswith(k + "_")), None)
        lines.append(f"| `{f}` | {FILES.get(key, '')} |")
    lines += ["", "NetCDF files carry this provenance in their global attributes; `*.nc` stays out of git.", "",
              "## Processing summary", ""] + _qc_table(run_dir, names)
    lines += ["", "## Headline results", ""] + _headlines(run_dir, config)
    rep = _load(run_dir / "reproduction_check.json")
    if rep:
        s = rep["summary"]
        lines += ["", "## Reproduction check", "",
                  f"Rebuilt from the raw files and compared with `{rep['a']}`: {s['files_compared']} files compared, "
                  f"{s['files_differing']} differ beyond relative tolerance {rep['rtol']:g}."]
    unc = _load(run_dir / "uncertainty" / "uncertainty_report.json")
    if unc:
        t = unc["tables"]
        lines += ["", "## Uncertainty", "",
                  f"Bootstrap over profiles, {unc['bootstrap_samples']} samples (seed {unc['random_seed']}). "
                  + "; ".join(f"{k}: {v['pooled_with_interval']}/{v['pooled_records']} pooled estimates with intervals"
                              for k, v in t.items()) + ". Records with fewer than "
                  f"{config['double_diffusion']['min_profiles_per_average']} profiles are flagged."]
    lines += ["", "## Caveats", ""] + [f"* {c}" for c in caveats]
    path = out_dir / "README.md"
    path.write_text("\n".join(lines) + "\n")
    return path
