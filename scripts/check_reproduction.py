#!/usr/bin/env python3
"""Check that two runs of the same settings produce the same results.

Compares every CSV under the step directories and every NetCDF product of run B
against run A: same files, same columns or variables, same row counts, and
numeric values equal within --rtol (NaN equal to NaN). Provenance fields
(timestamps, git commit, config hash, run name, paths) are expected to differ
and are ignored, as are logs and step metadata. Writes a report and prints a
summary; exit status 1 if anything differs beyond tolerance.

Usage (B is a fresh run of A's settings, e.g. a sensitivity_runs entry with `set: {}`):
    python scripts/check_reproduction.py --a outputs/baseline --b outputs/<fresh run>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SKIP_DIRS = {"convert", "patch", "comparisons"}
IGNORE_COLS = {"time", "created_utc", "git_commit", "config_sha256", "run_name", "overrides", "provenance",
               "control_group", "source", "path"}


def compare_frames(a: pd.DataFrame, b: pd.DataFrame, rtol: float) -> list[str]:
    probs = []
    if list(a.columns) != list(b.columns):
        probs.append(f"columns differ: {sorted(set(a.columns) ^ set(b.columns))}")
    if len(a) != len(b):
        return probs + [f"rows {len(a)} vs {len(b)}"]
    for c in a.columns:
        if c not in b.columns or c in IGNORE_COLS:
            continue
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xv, yv = x.to_numpy(float), y.to_numpy(float)
            bad = ~(np.isclose(xv, yv, rtol=rtol, atol=0, equal_nan=True))
            if bad.any():
                rel = np.nanmax(np.abs(xv[bad] - yv[bad]) / np.maximum(np.abs(xv[bad]), 1e-300))
                probs.append(f"{c}: {int(bad.sum())} values differ (max rel {rel:.2e})")
        elif not (x.fillna("").astype(str) == y.fillna("").astype(str)).all():
            probs.append(f"{c}: {int((x.fillna('').astype(str) != y.fillna('').astype(str)).sum())} entries differ")
    return probs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--rtol", type=float, default=1e-9)
    args = ap.parse_args()
    report = {"a": str(args.a), "b": str(args.b), "rtol": args.rtol, "files": {}}
    files = sorted(p.relative_to(args.a) for p in args.a.rglob("*")
                   if p.is_file() and p.suffix in (".csv", ".nc") and p.relative_to(args.a).parts[0] not in SKIP_DIRS)
    n_bad = 0
    for rel in files:
        pa, pb = args.a / rel, args.b / rel
        if not pb.exists():
            report["files"][str(rel)] = ["missing in B"]
            n_bad += 1
            continue
        if rel.suffix == ".csv":
            probs = compare_frames(pd.read_csv(pa, low_memory=False), pd.read_csv(pb, low_memory=False), args.rtol)
        else:
            da, db = xr.open_dataset(pa), xr.open_dataset(pb)
            probs = []
            if set(da.data_vars) != set(db.data_vars):
                probs.append(f"variables differ: {sorted(set(da.data_vars) ^ set(db.data_vars))}")
            for v in sorted(set(da.data_vars) & set(db.data_vars)):
                if v in IGNORE_COLS:
                    continue
                if da[v].shape != db[v].shape:
                    probs.append(f"{v}: shape {da[v].shape} vs {db[v].shape}")
                elif da[v].dtype.kind in "fiu":
                    bad = ~np.isclose(da[v].values.astype(float), db[v].values.astype(float), rtol=args.rtol, atol=0,
                                      equal_nan=True)
                    if bad.any():
                        probs.append(f"{v}: {int(bad.sum())} values differ")
                elif da[v].dtype.kind in "OUS" and not np.array_equal(da[v].values.astype(str), db[v].values.astype(str)):
                    probs.append(f"{v}: text differs")
        report["files"][str(rel)] = probs or "identical"
        n_bad += bool(probs)
    extra = sorted(str(p.relative_to(args.b)) for p in args.b.rglob("*")
                   if p.is_file() and p.suffix in (".csv", ".nc") and p.relative_to(args.b).parts[0] not in SKIP_DIRS
                   and not (args.a / p.relative_to(args.b)).exists())
    report["only_in_b"] = extra
    report["summary"] = {"files_compared": len(files), "files_differing": n_bad, "only_in_b": len(extra)}
    (args.b / "reproduction_check.json").write_text(json.dumps(report, indent=1, default=str))
    print(f"{len(files)} files compared, {n_bad} differ beyond rtol {args.rtol}, {len(extra)} only in B")
    for f, p in report["files"].items():
        if p != "identical":
            print(f"  {f}: {p}")
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
