#!/usr/bin/env python3
"""Effect of the fp07-pair per-bead FP07 response correction (config `fp07_pair_check`).

Compares a run without the correction (`reference_run`) with one that applies it
(`corrected_run`), per cast of `instrument`:
  * chi_T2 / chi_T1 (median of ln, windows below min_P_dbar where both probes give
    chi above floor_factor x their own noise floor), before and after;
  * its trend with K_max/kB (spectral resolution): median ln ratio per quartile of the
    mean K_max ratio of the two probes, per bead pair, before and after;
  * whether perturb applied the correction to each file (its per-file guard);
  * the combined chi of the corrected run against the reference, matched window by
    window (median ratio, and ratio of sums), and how many T2 estimates were re-admitted.

Reads:  outputs/<run>/thermistor/thermistor_<instrument>.csv,
        outputs/<run>/cast_log/casts_<instrument>.csv
Writes: outputs/comparisons/fp07_pair/{per_cast.csv, kmax_trend.csv, fp07_pair_check.png, summary.json}

Usage:
    python scripts/fp07_pair_check.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def run_dir(config: dict, config_hash: str, run: str) -> Path:
    cfg = config if run == config["run"]["name"] else common.apply_sensitivity(config, config_hash, run)[0]
    return common.run_dir_of(cfg)


def load(rd: Path, inst: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    th = pd.read_csv(rd / "thermistor" / f"thermistor_{inst}.csv")
    th["stem"] = th["profile_file"].str.split("_prof").str[0]
    if "fp07_response_applied" not in th:
        th["fp07_response_applied"] = -1                # thermistor tables from before the fp07_pair step
    casts = pd.read_csv(rd / "cast_log" / f"casts_{inst}.csv", dtype=str)
    casts["stem"] = casts["file"].str.rsplit(".", n=1).str[0]
    return th, casts


def pair_windows(th: pd.DataFrame, cc: dict) -> pd.DataFrame:
    ok = ((th["P_mean"] > cc["min_P_dbar"]) & (th["chi_T1"] > cc["floor_factor"] * th["floor_T1"])
          & (th["chi_T2"] > cc["floor_factor"] * th["floor_T2"]))
    d = th[ok].copy()
    d["lr"] = np.log(d["chi_T2"] / d["chi_T1"])
    d["kmax"] = np.sqrt(d["K_max_ratio_T1"] * d["K_max_ratio_T2"])
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    cc = config["fp07_pair_check"]
    inst = cc["instrument"]
    out = REPO / config["paths"]["output_root"] / "comparisons" / "fp07_pair"
    out.mkdir(parents=True, exist_ok=True)
    ref_th, casts = load(run_dir(config, config_hash, cc["reference_run"]), inst)
    cor_th, _ = load(run_dir(config, config_hash, cc["corrected_run"]), inst)
    pair = casts.set_index("stem")["expected_T2_sn"]      # patched serials (raw headers miss the swap)

    rows = []
    rp, cp = pair_windows(ref_th, cc), pair_windows(cor_th, cc)
    keys = ["profile_file", "window"]
    m = ref_th[keys + ["stem", "P_mean", "chi", "use_T2"]].merge(
        cor_th[keys + ["chi", "use_T2", "fp07_response_applied"]], on=keys, suffixes=("_ref", "_cor"))
    m = m[(m["P_mean"] > cc["min_P_dbar"]) & (m["chi_ref"] > 0) & (m["chi_cor"] > 0)]
    for stem, g in m.groupby("stem"):
        rows.append({
            "cast": stem, "T2_sn": pair.get(stem, ""),
            "applied": int(g["fp07_response_applied"].iloc[0]),
            "lnT2T1_ref": rp.loc[rp["stem"] == stem, "lr"].median(),
            "lnT2T1_cor": cp.loc[cp["stem"] == stem, "lr"].median(),
            "T2_used_ref": float(g["use_T2_ref"].mean()), "T2_used_cor": float(g["use_T2_cor"].mean()),
            "chi_ratio_median": float(np.exp(np.median(np.log(g["chi_cor"] / g["chi_ref"])))),
            "chi_ratio_sum": float(g["chi_cor"].sum() / g["chi_ref"].sum()), "windows": len(g)})
    per_cast = pd.DataFrame(rows)
    per_cast.to_csv(out / "per_cast.csv", index=False, float_format="%.4g")

    trend = []
    for label, d in (("reference", rp), ("corrected", cp)):
        d = d.assign(T2_sn=d["stem"].map(pair))
        for sn, g in d.groupby("T2_sn"):
            q = pd.qcut(g["kmax"], 4, labels=False, duplicates="drop")
            for k, h in g.groupby(q):
                trend.append({"run": label, "T2_sn": sn, "kmax_quartile": int(k) + 1,
                              "kmax_median": h["kmax"].median(), "lnT2T1": h["lr"].median(), "n": len(h)})
    trend = pd.DataFrame(trend)
    trend.to_csv(out / "kmax_trend.csv", index=False, float_format="%.4g")

    ps.apply()
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.2), gridspec_kw={"width_ratios": [2.2, 1.2, 2.2]})
    x = np.arange(len(per_cast))
    ax = axs[0]
    ax.plot(x, per_cast["lnT2T1_ref"], "o", color="0.55", label="without correction")
    ax.plot(x, per_cast["lnT2T1_cor"], "o", color=ps.ORANGE, label="with fp07-pair correction")
    bad = per_cast["applied"] != 1
    ax.plot(x[bad], per_cast.loc[bad, "lnT2T1_cor"], "x", color="k", ms=9, label="correction not applied (guard)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x, per_cast["cast"].str[4:], rotation=90, fontsize=7)
    ax.set(ylabel="median ln(χ_T2 / χ_T1)", title="(a) FP07 pair agreement per cast (P > %g dbar)" % cc["min_P_dbar"])
    ax.legend(fontsize=8)
    ax = axs[1]
    for (label, sn), g in trend.groupby(["run", "T2_sn"]):
        ax.plot(g["kmax_median"], g["lnT2T1"], "o-" if label == "corrected" else "o--",
                color=ps.ORANGE if label == "corrected" else "0.55", alpha=1 if "3304" in str(sn) else 0.5,
                label=f"{label}, T2 {sn}")
    ax.axhline(0, color="k", lw=0.6)
    ax.set(xlabel="K_max / kB (quartile medians)", ylabel="median ln(χ_T2 / χ_T1)", title="(b) trend with resolution")
    ax.legend(fontsize=7)
    ax = axs[2]
    ax.plot(x, per_cast["chi_ratio_sum"], "s", color=ps.BLUE, label="Σχ ratio (what bin averages see)")
    ax.plot(x, per_cast["chi_ratio_median"], "o", mfc="none", color=ps.BLUE, label="median window ratio")
    ax.axhline(1, color="k", lw=0.6)
    ax.set_xticks(x, per_cast["cast"].str[4:], rotation=90, fontsize=7)
    ax.set(ylabel="combined χ, corrected / reference", title="(c) change in combined χ")
    ax.legend(fontsize=8)
    prov = common.provenance(config_hash)
    fig.text(0.01, 0.005, f"{cc['corrected_run']} vs {cc['reference_run']}, {inst}; "
             + common.provenance_string(prov), fontsize=6, color="0.4")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "fp07_pair_check.png", dpi=130)
    common.write_json(out / "summary.json", {
        "provenance": prov, "settings": cc,
        "per_cast": per_cast.to_dict(orient="records"), "kmax_trend": trend.to_dict(orient="records")})
    print(per_cast.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    print(trend.pivot_table(index=["T2_sn", "kmax_quartile"], columns="run", values="lnT2T1").round(2).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
