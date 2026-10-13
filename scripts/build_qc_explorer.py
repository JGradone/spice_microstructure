#!/usr/bin/env python3
"""Build the QC explorer: an interactive page for trying QC choices.

Collects every dissipation window of a run (epsilon and chi share one window
grid) with the inputs each QC choice needs, embeds them in
scripts/qc_explorer_template.html, and writes
<run_dir>/qc_explorer/qc_explorer.html plus the data as JSON. The page
recomputes everything in the browser, so no QC choice made there changes the
pipeline; it is a tool for choosing config values.

Usage:
    python scripts/build_qc_explorer.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import gsw
import netCDF4
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402

TEMPLATE = REPO / "scripts" / "qc_explorer_template.html"
STRAT_SCALES_M = [5, 10, 25]


def stratification(P: np.ndarray, CT: np.ndarray, SA: np.ndarray, lat: float,
                   centres: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray]:
    """N2 and dT/dz (K/m, positive down) at each window centre from a linear fit of
    CT and SA against pressure over +-scale/2 dbar, with TEOS-10 alpha and beta.

    Independent of perturb's window-scale values, which are wrong for the VMP5500
    (decisions.md 2026-10-12). Pressure in dbar is used as depth in m (<1% error)."""
    ok = np.isfinite(P) & np.isfinite(CT) & np.isfinite(SA)
    P, CT, SA = P[ok], CT[ok], SA[ok]
    n2, tz = np.full(len(centres), np.nan), np.full(len(centres), np.nan)
    for i, pc in enumerate(centres):
        m = np.abs(P - pc) <= scale / 2
        if m.sum() < 10 or np.ptp(P[m]) < 0.5 * scale:
            continue
        dct = np.polyfit(P[m], CT[m], 1)[0]          # K per dbar, down
        dsa = np.polyfit(P[m], SA[m], 1)[0]
        ct0, sa0 = CT[m].mean(), SA[m].mean()
        alpha = gsw.alpha(sa0, ct0, pc)
        beta = gsw.beta(sa0, ct0, pc)
        g = gsw.grav(lat, pc)
        n2[i] = g * (beta * dsa - alpha * dct)        # z up: -d/dp
        tz[i] = dct
    return n2, tz


def var(ds, name) -> np.ndarray:
    v = ds[name][...]
    return np.ma.filled(v.astype(float), np.nan) if np.ma.isMaskedArray(v) else np.asarray(v, float)


def sig(x: np.ndarray, digits: int = 4) -> list:
    """Round to significant digits; NaN becomes None (JSON null)."""
    out = []
    for v in np.asarray(x, float):
        out.append(None if not np.isfinite(v) else float(f"{v:.{digits}g}"))
    return out


def collect(run_dir: Path, config: dict) -> dict:
    profiles, cols = [], {k: [] for k in [
        "pi", "w", "P", "spd", "scv", "vib", "e1", "e2", "fm1", "fm2", "vr1", "vr2",
        "c1", "c2", "cvr1", "cvr2", "eT1", "eT2", "N2", "Tz"]
        + [f"{q}_{s}" for s in STRAT_SCALES_M for q in ("N2", "Tz")]}
    for inst_idx, (name, inst) in enumerate(common.instruments(config)):
        root = run_dir / "convert" / name
        diss_dir, chi_dir = common.single_dir(root, "diss"), common.single_dir(root, "chi")
        prof_dir = common.single_dir(root, "profiles")
        seg = pd.read_csv(run_dir / "segments" / f"segments_{name}.csv")
        casts = pd.read_csv(run_dir / "cast_log" / f"casts_{name}.csv").set_index("file")
        for prof_file, s in seg.groupby("profile_file", sort=True):
            cast = casts.loc[s["file"].iloc[0]]
            with netCDF4.Dataset(diss_dir / prof_file) as d:
                fm, vr = var(d, "FM"), var(d, "var_resolved")
                e1, e2 = var(d, "e_1"), var(d, "e_2")
                n2, tz = var(d, "N2"), var(d, "dTdz")
                t0 = float(d["stime"][...])
            with netCDF4.Dataset(chi_dir / prof_file) as c:
                c1, c2 = var(c, "chi_1"), var(c, "chi_2")
                cvr, eT = var(c, "var_resolved"), var(c, "epsilon_T")
            with netCDF4.Dataset(prof_dir / prof_file) as pr:
                Pp, CTp, SAp = var(pr, "P"), var(pr, "CT"), var(pr, "SA")
                lat = float(pr["lat"][...]) if np.isfinite(pr["lat"][...]) else 12.0
            for scale in STRAT_SCALES_M:
                n2s, tzs = stratification(Pp, CTp, SAp, lat, s["P_mean"].to_numpy(), scale)
                cols[f"N2_{scale}"] += sig(n2s)
                cols[f"Tz_{scale}"] += sig(tzs)
            n = len(s)
            assert n == len(e1) == len(c1), prof_file
            pi = len(profiles)
            excl = "" if pd.isna(cast.get("excluded")) else str(cast["excluded"])
            probes = "" if pd.isna(cast.get("excluded_probes")) else str(cast["excluded_probes"])
            profiles.append({
                "inst": inst_idx, "file": s["file"].iloc[0], "prof": prof_file[:-3],
                "station": cast.get("station") == "process_station",
                "towyo": str(cast.get("towyo")).lower() == "true",
                "excluded": excl, "exclProbes": [p for p in probes.split(",") if p],
                "t0": pd.to_datetime(t0, unit="s", utc=True).strftime("%Y-%m-%d %H:%M"),
                "pmax": round(float(s["P_max_profile"].iloc[0]), 1)})
            cols["pi"] += [pi] * n
            cols["w"] += list(range(n))
            for key, arr in [("P", s["P_mean"]), ("spd", s["speed"]), ("scv", s["speed_cv"]),
                             ("vib", s["vibration_ratio"]), ("e1", e1), ("e2", e2),
                             ("fm1", fm[0]), ("fm2", fm[1]), ("vr1", vr[0]), ("vr2", vr[1]),
                             ("c1", c1), ("c2", c2), ("cvr1", cvr[0]), ("cvr2", cvr[1]),
                             ("eT1", eT[0]), ("eT2", eT[1]), ("N2", n2), ("Tz", tz)]:
                cols[key] += sig(np.asarray(arr, float))
    return {"instruments": [n for n, _ in common.instruments(config)],
            "stratScales": STRAT_SCALES_M,
            "profiles": profiles, "windows": cols,
            "defaults": {"segments": config["segments"],
                         "atomix": {"FM_max": config["perturb"]["epsilon"]["FM_max"],
                                    "var_resolved_min": config["perturb"]["epsilon"]["var_resolved_min"],
                                    "pair_limit": config["perturb"]["epsilon"]["pair_limit"]}}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run_dir = common.run_dir_of(config)
    out = run_dir / "qc_explorer"
    out.mkdir(parents=True, exist_ok=True)
    data = collect(run_dir, config)
    prov = common.provenance(config_hash)
    data["provenance"] = {"run": config["run"]["name"], "text": common.provenance_string(prov),
                          "created_utc": prov["created_utc"]}
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
    (out / "qc_explorer_data.json").write_text(payload)
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", payload)
    (out / "qc_explorer.html").write_text(html)
    n = len(data["windows"]["P"])
    print(f"{n} windows, {len(data['profiles'])} profiles; "
          f"{len(payload) / 1e6:.1f} MB of data -> {out / 'qc_explorer.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
