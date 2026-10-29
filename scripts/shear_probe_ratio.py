#!/usr/bin/env python3
"""sh1/sh2 epsilon ratio per cast and depth bin, to find a probe going bad.

A probe failing over a pressure window reads high (or low) against the other
probe at those depths only, while the steady offset between two healthy probes
is the same at every depth and cast. Config `shear_probe_check`.

Windows: both probes have an estimate at least floor_factor times their own
noise floor. Uses the raw per-probe estimates (epsilon_sh1, epsilon_sh2) before
the config probe exclusions, so excluded casts can be checked too. Statistic:
median log10(epsilon_sh1 / epsilon_sh2) per cast and depth bin.

Reads:  outputs/<run>/epsilon_shear/epsilon_shear_<instrument>.csv,
        outputs/<run>/cast_log/casts_<instrument>.csv (run =
        products.recommended_run unless --run is given)
Writes: outputs/comparisons/shear_probes/<run>/{shear_probe_ratio_<instrument>.png,
        ratio_<instrument>.csv, summary.json}

Usage:
    python scripts/shear_probe_ratio.py --config config/config.yaml [--run NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

LABEL = {"vmp250": "VMP250", "vmp5500": "VMP5500"}


def ratios(eps: pd.DataFrame, casts: pd.DataFrame, cc: dict) -> pd.DataFrame:
    df = eps.copy()
    ok = ((df["epsilon_sh1"] >= cc["floor_factor"] * df["floor_sh1"])
          & (df["epsilon_sh2"] >= cc["floor_factor"] * df["floor_sh2"]))
    df = df[ok].copy()
    df["stem"] = df["profile_file"].str.split("_prof").str[0]
    df["lr"] = np.log10(df["epsilon_sh1"] / df["epsilon_sh2"])
    df["P_bin"] = (np.floor(df["P_mean"] / cc["depth_bin_m"]) + 0.5) * cc["depth_bin_m"]
    out = (df.groupby(["stem", "P_bin"])["lr"].agg(log10_ratio="median", n="size").reset_index())
    out = out[out["n"] >= cc["min_windows"]]
    serials = casts.assign(stem=casts["file"].str.rsplit(".", n=1).str[0]).set_index("stem")
    out["sh1_sn"] = out["stem"].map(serials["raw_sh1_sn"])
    out["sh2_sn"] = out["stem"].map(serials["raw_sh2_sn"])
    return out


def figure(tab: pd.DataFrame, name: str, dz: float, path: Path, foot: str) -> None:
    stems = sorted(tab["stem"].unique())
    centres = np.arange(tab["P_bin"].min(), tab["P_bin"].max() + dz / 2, dz)
    grid = (tab.pivot(index="P_bin", columns="stem", values="log10_ratio")
            .reindex(index=centres, columns=stems))
    fig, ax = plt.subplots(figsize=(max(6, 0.28 * len(stems) + 2), 5))
    im = ax.pcolormesh(np.arange(len(stems) + 1), np.r_[centres - dz / 2, centres[-1] + dz / 2],
                       grid.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, shading="flat")
    ax.set_xticks(np.arange(len(stems)) + 0.5, stems, rotation=90, fontsize=7)
    ax.invert_yaxis()
    ax.set_ylabel("Pressure (dbar)")
    fig.colorbar(im, ax=ax, label=r"median log$_{10}$($\epsilon_{sh1}/\epsilon_{sh2}$)")
    ax.set_title(f"{LABEL.get(name, name)}: shear probe agreement per cast and depth bin")
    ps.footer(fig, foot)
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--run", help="run to check (default products.recommended_run)")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run = args.run or config["products"]["recommended_run"]
    rcfg, rhash = common.apply_sensitivity(config, config_hash, run) if run != config["run"]["name"] \
        else (config, config_hash)
    run_dir = common.run_dir_of(rcfg)
    cc = config["shear_probe_check"]
    out_dir = common.run_dir_of(config).parent / "comparisons" / "shear_probes" / run
    out_dir.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash)) + f"; epsilon_shear of run {run}"
    ps.apply()
    summary = {"provenance": foot, "run": run, "run_config_hash": rhash, "settings": cc, "instruments": {}}
    for name in cc["instruments"]:
        eps = pd.read_csv(run_dir / "epsilon_shear" / f"epsilon_shear_{name}.csv")
        casts = pd.read_csv(run_dir / "cast_log" / f"casts_{name}.csv")
        tab = ratios(eps, casts, cc)
        tab.to_csv(out_dir / f"ratio_{name}.csv", index=False)
        figure(tab, name, cc["depth_bin_m"], out_dir / f"shear_probe_ratio_{name}.png", foot)
        per_cast = tab.groupby("stem")["log10_ratio"].agg(["median", "min", "max"]).round(2)
        summary["instruments"][name] = {"median_log10_ratio": round(float(tab["log10_ratio"].median()), 3),
                                        "per_cast": per_cast.to_dict(orient="index")}
        print(f"{name}: {tab['stem'].nunique()} casts, median log10(sh1/sh2) {tab['log10_ratio'].median():+.2f}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
