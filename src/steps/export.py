#!/usr/bin/env python3
"""Step export: the documented products for use outside this repository (docs/products.md).

Writes to <run_dir>/products/, per instrument:
  casts_<instrument>.csv            one row per profile (cast table, flags, probe serials)
  segments_<instrument>.nc          one record per dissipation window (epsilon, chi, hydrography,
                                    regimes, staircase labels, QC flags); no diffusivities
  binned_<instrument>.nc            per profile x depth bin (products.depth_bin_m): window means
                                    of epsilon and chi with counts, and the hydrography grid
  diffusivity_<instrument>.nc/.csv  bin-averaged diffusivities (diffusivities step)
  diffusivity_primary_<instrument>.nc/.csv  the same, primary choices only (products.primary):
                                    one profile per group, with K_nitrate and its source
  attribution_<instrument>.csv      finger fraction per baseline
  cast_metrics_<instrument>.csv     per-profile finger metrics
plus README.md (file list, provenance, caveats).

Every NetCDF file carries CF/ACDD metadata, product_version, run name and the
sensitivity overrides, config sha256, git commit, package versions and the
date. Exclusions and cautions are flag variables, never silently missing data.

Reads:  step outputs of cast_log, segments, hydrography, epsilon_shear, thermistor,
        regimes, dd_test and diffusivities; perturb diss files (window times)
"""

from __future__ import annotations

import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import run_summary  # noqa: E402
import epsilon_shear  # noqa: E402
import segments as segments_step  # noqa: E402
import thermistor  # noqa: E402
from dd_test import finescale_tz2  # noqa: E402

STEP = "export"
CAVEATS = [
    "Osborn and Cox assumes local production of thermal variance balances dissipation; lateral (intrusive) "
    "finescale gradients can also produce chi (finescale gradient variants are provided).",
    "The ratio <chi_obs>/<chi_exp> is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency; "
    "in salt fingering the true buoyancy flux is upgradient.",
    "Shear epsilon near the noise floor is flagged (at_floor) and bounded (epsilon_shear_bounded = max(eps, floor)); "
    "flagged windows are kept.",
    "K_S = R_rho K_T / gamma assumes finger-dominated fluxes; gamma (0.5-0.7) is poorly constrained; K_S is given "
    "only where finger-favourable and 1 < R_rho <= diffusivities.k_s_max_r_rho.",
    "VMP5500 salinity is from each cast's own T-S relation (FP07 temperature); its S_z, R_rho and Turner angle "
    "follow the T-S slope, and windows in temperature inversions are flagged ts_salinity_invalid.",
    "chi depends on the FP07 response model (single pole, speed-dependent tau) by a factor ~1.4-1.8 against a "
    "double-pole model (decisions.md 2026-10-13).",
    "The finger fraction depends on the baseline (Gamma = 0.2 theory, Garrett-Munk, Re_b-matched non-staircase finger water at the "
    "same depths, a lower bound); the spread across baselines is part of the result.",
]


def global_attrs(config, prov, name, inst, title) -> dict:
    p = config["products"]
    run = config["run"]
    return {
        "title": f"SPICE FKt260806 {inst['model']} SN {inst['serial']}: {title}",
        "Conventions": p["conventions"], "product_version": p["product_version"],
        "run_name": run["name"], "run_notes": run.get("notes", ""),
        "sensitivity_overrides": str(run.get("sensitivity", {}).get("set", {})),
        "config_sha256": prov["config_sha256"], "git_commit": str(prov["git_commit"]),
        "microstructure_tpw_version": str(prov.get("packages", {}).get("microstructure-tpw")),
        "microstructure_tpw_commit": str(prov.get("microstructure_tpw_commit")),
        "python_version": str(prov.get("python")), "date_created": prov["created_utc"],
        "instrument": f"Rockland {inst['model']} SN {inst['serial']}", "instrument_key": name,
        "platform": "R/V Falkor (too)", "project": "SPICE", "cruise": "FKt260806",
        "creator_name": p["creator_name"], "creator_email": p["creator_email"], "institution": p["institution"],
        "license": p["license"], "caveats": " | ".join(CAVEATS),
        "references": "docs/products.md and docs/decisions.md in the spice_microstructure repository",
    }


def flag_attrs(bits: dict, long_name: str) -> dict:
    return {"long_name": long_name, "flag_masks": np.array(list(bits.values()), dtype=np.int32),
            "flag_meanings": " ".join(bits.keys())}


def window_times(run_dir: Path, name: str) -> pd.DataFrame:
    rows = []
    for f in sorted(common.single_dir(run_dir / "convert" / name, "diss").glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as d:
            t = np.ma.filled(d["t"][:].astype(float), np.nan)
            units = d["t"].units
        base = pd.Timestamp(units.split("since", 1)[1].strip())
        rows.append(pd.DataFrame({"profile_file": f.name, "window": np.arange(len(t)),
                                  "time": base + pd.to_timedelta(t, unit="s")}))
    return pd.concat(rows, ignore_index=True)


def cast_table(run_dir, name, inst, hyd) -> pd.DataFrame:
    casts = pd.read_csv(run_dir / "cast_log" / f"casts_{name}.csv", dtype=str)
    casts["stem"] = casts["file"].str.rsplit(".", n=1).str[0]
    seg = pd.read_csv(run_dir / "segments" / f"segments_{name}.csv")
    pmax = seg.groupby("profile_file")["P_max_profile"].first()
    prof = pd.DataFrame({"profile_file": hyd["profile_file"].values, "lat": hyd["lat"].values,
                         "lon": hyd["lon"].values,
                         "start_utc": pd.to_datetime(hyd["stime"].values, unit="s", utc=True)})
    prof["profile"] = prof["profile_file"].str.extract(r"_prof(\d+)")[0].astype(int)
    prof["stem"] = prof["profile_file"].str.split("_prof").str[0]
    prof["max_pressure_dbar"] = prof["profile_file"].map(pmax)
    keep = ["stem", "file", "station", "towyo", "excluded", "excluded_probes", "caution", "position_flag",
            "track_gap_s", "sealog_notes"] + [c for c in casts.columns if c.startswith("raw_")]
    out = prof.merge(casts[keep], on="stem", how="left").drop(columns="stem")
    exc = inst.get("exclude_probes") or {}
    out["excluded_probes"] = [",".join(sorted(set(str(e).split(",") if isinstance(e, str) and e else [])
                                              | set(exc.get(pf[:-3], []))))
                              for e, pf in zip(out["excluded_probes"], out["profile_file"])]
    out.insert(0, "instrument", name)
    return out


def segments_product(run_dir, name, hyd: xr.Dataset, diss_sec: float) -> xr.Dataset:
    keys = ["profile_file", "window"]
    reg = pd.read_csv(run_dir / "regimes" / f"regimes_{name}.csv")
    sh = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{name}.csv")
    th = pd.read_csv(run_dir / "thermistor" / f"thermistor_{name}.csv")
    sg = pd.read_csv(run_dir / "segments" / f"segments_{name}.csv")
    sh_cols = [c for c in sh.columns if c.startswith(("epsilon_sh1", "epsilon_sh2", "FM_sh", "var_resolved_sh",
                                                      "floor_sh", "use_sh")) and not c.endswith("_perturb")] + \
        ["n_probes", "flags"]
    have = set(reg.columns)
    sh_cols = [c for c in sh_cols if c not in have or c in ("flags", "n_probes")]
    th_cols = [c for c in th.columns if c.startswith(("chi_T", "epsilon_T_T", "kB_T", "fom_T", "K_max_ratio_T",
                                                      "snr_T", "floor_T", "use_T"))] + \
        ["n_probes", "chi_floor", "K_max_ratio", "kB", "flags", "at_floor"]
    th_cols = [c for c in th_cols if c not in have or c in ("flags", "n_probes", "at_floor")]
    d = reg.merge(sh[keys + sh_cols].rename(columns={"flags": "shear_flags", "n_probes": "n_shear_probes"}), on=keys) \
           .merge(th[keys + th_cols].rename(columns={"flags": "chi_flags", "n_probes": "n_thermistors",
                                                     "at_floor": "chi_at_floor"}), on=keys, how="left") \
           .merge(sg[keys + ["flags", "keep", "vibration_ratio", "speed_cv"]]
                  .rename(columns={"flags": "segment_flags", "keep": "segment_keep"}), on=keys) \
           .merge(window_times(run_dir, name), on=keys, how="left")
    # finescale T_z^2: 1 m grid gradient variance over each window, as in dd_test and diffusivities
    d["T_z2_fine"] = finescale_tz2(d["profile_file"], d["depth"], d["speed"] * diss_sec / 2, hyd)
    rename = {"P_mean": "pressure", "speed": "fall_speed", "Turner": "turner_angle_10m",
              "Turner_smooth": "turner_angle", "R_rho": "R_rho_10m", "N2": "N2_10m", "T_z": "T_z_10m",
              "S_z": "S_z_10m"}
    d = d.rename(columns=rename).drop(columns=["instrument"], errors="ignore")
    for c in d.columns:
        if d[c].dtype == bool:
            d[c] = d[c].astype(np.int8)
        elif d[c].dtype == object and c not in ("profile_file",) and not c.startswith(("staircase_", "turner_class")):
            d[c] = pd.to_numeric(d[c], errors="ignore")
    for c in [c for c in d.columns if d[c].dtype == object]:
        d[c] = d[c].fillna("").astype(str)
    ds = xr.Dataset({c: ("segment", d[c].to_numpy()) for c in d.columns if c != "time"})
    ds["time"] = ("segment", pd.to_datetime(d["time"]).dt.tz_localize(None).to_numpy())
    units = {"pressure": "dbar", "depth": "m", "fall_speed": "m s-1", "nu": "m2 s-1", "CT": "degC", "SA": "g kg-1",
             "N2_10m": "s-2", "T_z_10m": "K m-1", "S_z_10m": "g kg-1 m-1", "alpha": "K-1", "beta": "kg g-1",
             "turner_angle": "degree", "turner_angle_10m": "degree", "epsilon_shear": "W kg-1",
             "epsilon_shear_bounded": "W kg-1", "epsilon_floor": "W kg-1", "chi": "K2 s-1", "chi_bounded": "K2 s-1",
             "chi_floor": "K2 s-1", "epsilon_T": "W kg-1", "kB": "cpm"}
    for k, u in units.items():
        if k in ds:
            ds[k].attrs["units"] = u
    for c in ds.data_vars:
        if c.startswith(("epsilon_sh", "floor_sh", "epsilon_T_T")):
            ds[c].attrs["units"] = "W kg-1"
        if c.startswith(("chi_T", "floor_T")):
            ds[c].attrs["units"] = "K2 s-1"
    ds["shear_flags"].attrs.update(flag_attrs(epsilon_shear.BITS, "shear epsilon QC flags (epsilon_shear step)"))
    ds["chi_flags"].attrs.update(flag_attrs(thermistor.BITS, "chi QC flags (thermistor step)"))
    ds["segment_flags"].attrs.update(flag_attrs(segments_step.BITS, "window QC flags (segments step)"))
    ds["T_z_10m"].attrs["comment"] = ds["S_z_10m"].attrs["comment"] = "z positive upward; linear fits over 10 m"
    ds["T_z2_fine"].attrs.update({"units": "K2 m-2", "comment": "mean squared CT gradient on the 1 m hydrography "
                                  "grid over the window (fall speed x diss_sec); the finescale gradient choice: "
                                  "K_T = <chi> / (2 <T_z2_fine>) from averages only"})
    ds["turner_angle"].attrs["comment"] = "Ruddick (1983), linear fits over regimes.turner_smoothing_m"
    ds["epsilon_shear_bounded"].attrs["comment"] = "max(epsilon_shear, epsilon_floor); upper bound where at floor"
    ds.attrs["comment"] = ("One record per dissipation window. No diffusivities at this level: average epsilon, chi "
                           "and gradients over windows and profiles first (docs/products.md).")
    return ds


def binned_product(seg: xr.Dataset, hyd: xr.Dataset, bin_m: float) -> xr.Dataset:
    d = seg[["profile_file", "depth", "epsilon_shear", "epsilon_shear_bounded", "chi", "epsilon_T",
             "shear_keep", "chi_keep"]].to_dataframe()
    zmax = float(np.nanmax(hyd["depth"].values))
    edges = np.arange(0, zmax + bin_m, bin_m)
    zc = (edges[:-1] + edges[1:]) / 2
    profs = list(hyd["profile_file"].values)
    d["b"] = np.digitize(d["depth"], edges) - 1
    out = {}
    for var, keepc in (("epsilon_shear", "shear_keep"), ("epsilon_shear_bounded", "shear_keep"), ("chi", "chi_keep"),
                       ("epsilon_T", "chi_keep")):
        arr, cnt = np.full((len(profs), len(zc)), np.nan), np.zeros((len(profs), len(zc)), np.int32)
        q = d[(d[keepc] == 1) & np.isfinite(d[var]) & (d["b"] >= 0) & (d["b"] < len(zc))]
        g = q.groupby(["profile_file", "b"])[var].agg(["mean", "size"])
        for (pf, b), r in g.iterrows():
            if pf in profs:
                arr[profs.index(pf), b], cnt[profs.index(pf), b] = r["mean"], r["size"]
        out[var] = (("profile", "depth"), arr, {"cell_methods": "depth: mean (window centres in bin)"})
        out[f"n_{var}"] = (("profile", "depth"), cnt)
    # hydrography grid (1 m) averaged to the product bins
    hz = hyd["depth"].values
    hb = np.digitize(hz, edges) - 1
    for v in ("CT", "SA_used", "N2", "T_z", "S_z", "R_rho", "Turner"):
        a = hyd[v].values
        arr = np.full((len(profs), len(zc)), np.nan)
        for b in range(len(zc)):
            s = hb == b
            if s.any():
                with np.errstate(invalid="ignore"):
                    arr[:, b] = np.nanmean(a[:, s], axis=1) if s.sum() > 1 else a[:, s][:, 0]
        out[v if v != "SA_used" else "SA"] = (("profile", "depth"), arr, {"cell_methods": "depth: mean (1 m grid)"})
    ds = xr.Dataset({k: (v[0], v[1], v[2] if len(v) > 2 else {}) for k, v in out.items()},
                    coords={"depth": ("depth", zc, {"units": "m"}), "profile_file": ("profile", profs)})
    for k in ("lat", "lon", "stime"):
        ds[k] = ("profile", hyd[k].values)
    return ds


def table_to_netcdf(tab: pd.DataFrame) -> xr.Dataset:
    t = tab.copy()
    t["depth_bin"] = pd.to_numeric(t["depth_bin"].replace("pooled", np.nan))
    t.insert(0, "pooled", tab["depth_bin"].astype(str).eq("pooled").astype(np.int8))
    for c in t.columns:
        if t[c].dtype == bool:
            t[c] = t[c].astype(np.int8)
        elif t[c].dtype == object:
            t[c] = t[c].fillna("").astype(str)
    return xr.Dataset({c: ("record", t[c].to_numpy()) for c in t.columns})


def primary_product(di: pd.DataFrame, config: dict, name: str) -> pd.DataFrame:
    """One diffusivity profile per group with only the primary choices (products.primary), for
    nitrate fluxes: K_T and K_rho of all water, K_S of finger-favourable water (with its gamma
    range), the finger-favourable fraction, K_GM, and K_nitrate with its source."""
    pc = config["products"]["primary"]
    g0 = float(config["double_diffusion"]["flux_ratio_gamma"])
    gs = [float(g) for g in config["diffusivities"]["gammas"]]
    ks, ks_lo, ks_hi = f"K_S_g{g0:g}", f"K_S_g{max(gs):g}", f"K_S_g{min(gs):g}"
    rows = []
    for group in pc["groups"]:
        sel = di[(di["instrument_group"] == f"{name} {group}") & (di["method"] == pc["method"])
                 & (di["gradients"] == pc["gradients"]) & (di["staircase"] == "all")
                 & (di["depth_bin"].astype(str) != "pooled")]
        if sel.empty:
            continue
        allw = sel[sel["turner"] == "all_turner"].set_index("depth_bin")
        fing = sel[sel["turner"] == pc["finger_set"]].set_index("depth_bin")
        for b, a in allw.iterrows():
            f = fing.loc[b] if b in fing.index else None
            nf = int(f["n_windows"]) if f is not None else 0
            r = {"group": group, "depth_bin": float(b), "P_top_dbar": a["P_top_dbar"],
                 "P_bottom_dbar": a["P_bottom_dbar"], "n_profiles": int(a["n_profiles"]),
                 "n_windows": int(a["n_windows"]), "min_profiles_ok": bool(a["min_profiles_ok"]),
                 "finger_fraction": nf / a["n_windows"] if a["n_windows"] else np.nan,
                 "K_T": a["K_T"], "K_T_ci_low": a["K_T_ci_low"], "K_T_ci_high": a["K_T_ci_high"],
                 "K_rho": a["K_rho"], "K_rho_ci_low": a["K_rho_ci_low"], "K_rho_ci_high": a["K_rho_ci_high"],
                 "K_GM": a["K_GM"]}
            s_ok = f is not None and bool(f["K_S_applicable"]) and bool(f["min_profiles_ok"])
            r.update({"R_rho_finger": f["R_rho"] if f is not None else np.nan,
                      "n_profiles_finger": int(f["n_profiles"]) if f is not None else 0,
                      "K_S": f[ks] if s_ok else np.nan,
                      "K_S_ci_low": f[f"{ks}_ci_low"] if s_ok else np.nan,
                      "K_S_ci_high": f[f"{ks}_ci_high"] if s_ok else np.nan,
                      "K_S_gamma_low": f[ks_lo] if s_ok else np.nan,
                      "K_S_gamma_high": f[ks_hi] if s_ok else np.nan})
            use_s = s_ok and r["finger_fraction"] >= float(pc["finger_fraction_min"])
            src = "K_S" if use_s else "K_T"
            r.update({"K_nitrate": r[src], "K_nitrate_ci_low": r[f"{src}_ci_low"],
                      "K_nitrate_ci_high": r[f"{src}_ci_high"],
                      "K_nitrate_source": "K_S finger water" if use_s else "K_T all water"})
            rows.append(r)
    return pd.DataFrame(rows)


PRIMARY_UNITS = {"depth_bin": "dbar", "P_top_dbar": "dbar", "P_bottom_dbar": "dbar", "finger_fraction": "1",
                 "R_rho_finger": "1"}
PRIMARY_DESC = {
    "group": "casts averaged: all free fall (whole cruise) or process_station free fall",
    "depth_bin": "bin centre (pressure)", "P_top_dbar": "top of the bin as averaged",
    "P_bottom_dbar": "bottom of the bin as averaged",
    "min_profiles_ok": "at least double_diffusion.min_profiles_per_average profiles; use rows where true",
    "finger_fraction": "fraction of the bin's windows that are finger-favourable (Turner 45-90 deg)",
    "K_T": "<chi>/(2<T_z^2>) over all water, finescale gradients (Osborn and Cox)",
    "K_rho": "0.2<epsilon>/<N2> over all water (Osborn); not a valid diffusivity where fingers dominate",
    "K_GM": "Garrett-Munk reference level at the bin's N and latitude",
    "R_rho_finger": "density ratio of the finger-favourable water",
    "K_S": "salt diffusivity of the finger-favourable water, R_rho K_T/gamma at the primary gamma; "
           "only where 1 < R_rho <= diffusivities.k_s_max_r_rho and enough profiles",
    "K_S_gamma_low": "K_S at the largest gamma (lower end of the gamma range)",
    "K_S_gamma_high": "K_S at the smallest gamma (upper end of the gamma range)",
    "K_nitrate": "suggested vertical diffusivity for nitrate: K_S where the finger-favourable fraction is at least "
                 "products.primary.finger_fraction_min and K_S is defined (assumes K_N = K_S in fingering), "
                 "else K_T of all water",
    "K_nitrate_source": "which estimate K_nitrate is",
}


def run(ctx: dict) -> None:
    config = ctx["config"]
    rd = ctx["run_dir"]
    out = rd / "products"
    out.mkdir(parents=True, exist_ok=True)
    prov = common.provenance(ctx["config_hash"])
    bin_m = float(config["products"]["depth_bin_m"])
    diff = pd.read_csv(rd / "diffusivities" / "diffusivity_bins.csv")
    att = pd.read_csv(rd / "diffusivities" / "attribution.csv")
    report = {}
    enc = {"zlib": True, "complevel": 4}
    for name, inst in common.instruments(config):
        hyd = xr.open_dataset(rd / "hydrography" / f"hydrography_{name}.nc")
        casts = cast_table(rd, name, inst, hyd)
        casts.to_csv(out / f"casts_{name}.csv", index=False)

        seg = segments_product(rd, name, hyd, float(config["perturb"]["epsilon"]["diss_sec"]))
        seg.attrs.update(global_attrs(config, prov, name, inst, "dissipation segments"))
        seg.to_netcdf(out / f"segments_{name}.nc", encoding={v: enc for v in seg.data_vars
                                                            if seg[v].dtype.kind in "fiu"})
        binned = binned_product(seg, hyd, bin_m)
        binned.attrs.update(global_attrs(config, prov, name, inst, f"profiles binned at {bin_m:g} m"))
        binned.to_netcdf(out / f"binned_{name}.nc", encoding={v: enc for v in binned.data_vars
                                                             if binned[v].dtype.kind in "fiu"})

        di = diff[diff["instrument_group"].str.startswith(name)]
        di.to_csv(out / f"diffusivity_{name}.csv", index=False, float_format="%.6g")
        dn = table_to_netcdf(di)
        dn.attrs.update(global_attrs(config, prov, name, inst, "bin-averaged diffusivities"))
        dn.attrs["gammas"] = ",".join(str(g) for g in config["diffusivities"]["gammas"])
        dn.attrs["epsilon_source"] = config["double_diffusion"]["epsilon_source"]
        dn.attrs["flux_coefficient"] = config["double_diffusion"]["flux_coefficient"]
        dn.attrs["bootstrap_samples"] = config["uncertainty"]["bootstrap_samples"]
        dn.attrs["random_seed"] = config["uncertainty"]["random_seed"]
        dn.to_netcdf(out / f"diffusivity_{name}.nc")

        pr = primary_product(di, config, name)
        pr.to_csv(out / f"diffusivity_primary_{name}.csv", index=False, float_format="%.4g")
        pn = xr.Dataset({c: ("record", (pr[c].astype(np.int8) if pr[c].dtype == bool else pr[c]).to_numpy())
                         for c in pr.columns})
        for c in pn.data_vars:
            if c.startswith("K_") and c != "K_nitrate_source":
                pn[c].attrs["units"] = "m2 s-1"
            if c in PRIMARY_UNITS:
                pn[c].attrs["units"] = PRIMARY_UNITS[c]
            key = c.replace("_ci_low", "").replace("_ci_high", "")
            if key in PRIMARY_DESC:
                pn[c].attrs["long_name"] = PRIMARY_DESC[key] + (
                    ", 95% bootstrap over profiles, " + ("low" if c.endswith("low") else "high")
                    if c.endswith(("_ci_low", "_ci_high")) else "")
        pc = config["products"]["primary"]
        pn.attrs.update(global_attrs(config, prov, name, inst, "primary diffusivity profiles"))
        pn.attrs.update({"staircase_method": pc["method"], "gradients": pc["gradients"],
                         "finger_set": pc["finger_set"], "finger_fraction_min": pc["finger_fraction_min"],
                         "gamma": config["double_diffusion"]["flux_ratio_gamma"],
                         "gammas": ",".join(str(g) for g in config["diffusivities"]["gammas"]),
                         "comment": "Primary choices only, from diffusivity_<instrument> (same values). One row per "
                                    "group and depth bin; bin averages over windows and profiles."})
        pn.to_netcdf(out / f"diffusivity_primary_{name}.nc")
        att[att["instrument_group"].str.startswith(name)].to_csv(out / f"attribution_{name}.csv", index=False,
                                                                 float_format="%.4g")
        cm = pd.read_csv(rd / "diffusivities" / f"cast_metrics_{name}.csv")
        cm.to_csv(out / f"cast_metrics_{name}.csv", index=False, float_format="%.6g")
        report[name] = {"profiles": int(len(casts)), "segments": int(seg.sizes["segment"]),
                        "binned_profiles": int(binned.sizes["profile"]), "diffusivity_records": int(len(di))}
        print(f"  {name}: {len(casts)} profiles, {seg.sizes['segment']} segments, {len(di)} diffusivity records")

    run_summary.write_readme(config, prov, rd, out, CAVEATS, common.provenance_string(prov)
                             + f"; exported {prov['created_utc']}")
    common.write_json(out / "export_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
