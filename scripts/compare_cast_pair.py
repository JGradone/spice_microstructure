#!/usr/bin/env python3
"""Window-by-window epsilon and chi for one VMP250 and one VMP5500 profile, plus shear figure of merit.

Panels (shared depth axis): FP07 temperature (CT); shear epsilon per probe;
chi per thermistor; figure of merit per
shear probe for each profile given with --fm. One solid line per channel
(dark shade channel 1, light shade channel 2), drawn where that channel is used
(use_<probe>); windows are not filtered by segment QC. The grey FM band is
shear_qc.figure_of_merit.max (a flag, not applied).

Reads:  outputs/<run>/products/segments_<instrument>.nc, or with --source perturb
        outputs/<run>/convert/<instrument>/{diss,chi}_NN/<profile>.nc (perturb's own
        per-probe epsilon, chi and Lueck FM, no pipeline QC); run =
        products.recommended_run unless --run is given
Writes: outputs/comparisons/cast_pairs/<profile>_vs_<profile>[_<max-depth>m][_perturb].png

Usage:
    python scripts/compare_cast_pair.py --config config/config.yaml \
        --profiles vmp250:data_0127_prof001 vmp5500:SPC_026_prof001 --fm vmp5500 [--max-depth 400] [--source perturb]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import common  # noqa: E402
import plotstyle as ps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

LABEL = {"vmp250": "VMP250", "vmp5500": "VMP5500"}


def load(run_dir: Path, inst: str, prof: str):
    with xr.open_dataset(run_dir / "products" / f"segments_{inst}.nc") as d:
        df = d.to_dataframe()
    df = df[df["profile_file"] == f"{prof}.nc"].sort_values("depth")
    if df.empty:
        raise SystemExit(f"no windows for {prof} in segments_{inst}.nc")
    return df


def load_perturb(run_dir: Path, inst: str, prof: str):
    """perturb's own per-probe output (convert step): no pipeline QC, refit or probe exclusions.

    Same columns as load(); `depth` is the window-mean pressure (dbar, at the
    pressure sensor), `CT` the window-mean temperature, and every channel is drawn.
    """
    import netCDF4
    import pandas as pd
    root = run_dir / "convert" / inst
    with netCDF4.Dataset(common.single_dir(root, "diss") / f"{prof}.nc") as d, \
            netCDF4.Dataset(common.single_dir(root, "chi") / f"{prof}.nc") as c:
        get = lambda ds, k: np.ma.filled(ds[k][:].astype(float), np.nan)
        t0 = pd.Timestamp(float(d["stime"][:]), unit="s", tz="UTC")
        df = pd.DataFrame({"depth": get(d, "P_mean"), "CT": get(d, "T_mean"),
                           "time": t0 + pd.to_timedelta(get(d, "t") - get(d, "t")[0], unit="s")})
        for i, probe in enumerate(d["probe"][:]):
            df[f"epsilon_{probe}"] = get(d, "epsilon")[i]
            df[f"FM_{probe}"] = get(d, "FM")[i]
            df[f"use_{probe}"] = 1
        # chi windows can differ from the shear windows: interpolate onto the shear window pressures
        pc = get(c, "P_mean")
        for i, probe in enumerate(c["probe"][:]):
            name = str(probe).split("_")[0]                                   # "T1_dT1" -> "T1"
            chi = get(c, "chi")[i]
            ok = np.isfinite(pc) & np.isfinite(chi)
            df[f"chi_{name}"] = np.interp(df["depth"], pc[ok], chi[ok], left=np.nan, right=np.nan) \
                if (len(pc) != len(df) or not np.allclose(pc, df["depth"], equal_nan=True)) else chi
            df[f"use_{name}"] = 1
    return df.sort_values("depth")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--profiles", nargs=2, required=True, metavar="INSTRUMENT:PROFILE")
    ap.add_argument("--fm", nargs="*", default=[], metavar="INSTRUMENT", help="instruments whose FM is drawn")
    ap.add_argument("--max-depth", type=float,
                    help="bottom of the depth axis (m); default 10 m below the shallower profile")
    ap.add_argument("--source", choices=["products", "perturb"], default="products",
                    help="products: exported segments (pipeline QC); perturb: raw per-probe convert output")
    ap.add_argument("--run", help="run whose products are used (default products.recommended_run)")
    args = ap.parse_args()
    config, config_hash = common.load_config(args.config)
    run = args.run or config["products"]["recommended_run"]
    rcfg, _ = common.apply_sensitivity(config, config_hash, run) if run != config["run"]["name"] \
        else (config, config_hash)
    run_dir = common.run_dir_of(rcfg)
    fm_max = config["shear_qc"]["figure_of_merit"]["max"]
    out = REPO / config["paths"]["output_root"] / "comparisons" / "cast_pairs"
    out.mkdir(parents=True, exist_ok=True)
    foot = common.provenance_string(common.provenance(config_hash)) + f"; {args.source} output of run {run}"
    ps.apply()

    data = []
    for spec in args.profiles:
        inst, prof = spec.split(":")
        data.append((inst, prof, (load_perturb if args.source == "perturb" else load)(run_dir, inst, prof)))
    z_max = args.max_depth or min(df["depth"].max() for *_, df in data) + 10   # default: range both sample

    fig, axes = plt.subplots(1, 4, figsize=(14, 7.5), sharey=True,
                             gridspec_kw={"width_ratios": [0.7, 1.2, 1.2, 0.9]})
    axT, axE, axC, axF = axes
    # One solid line per channel: dark shade = channel 1 (sh1, T1), light shade = channel 2 (sh2, T2).
    shade = {"vmp250": {1: ps.BLUE_RAMP[5], 2: ps.BLUE_RAMP[2]},
             "vmp5500": {1: ps.ORANGE_RAMP[5], 2: ps.ORANGE_RAMP[2]}}
    for inst, prof, df in data:
        c = ps.INSTRUMENT_COLOR[inst]
        z = df["depth"].to_numpy()
        name = f"{LABEL[inst]} {prof.replace('_prof001', '')} ({df['time'].min():%m-%d %H:%M} UTC)"
        axT.plot(df["CT"], z, color=c, lw=1.2, label=name)

        def probe_line(ax, var, p, label):
            use = df[f"use_{p}"].to_numpy() == 1
            col = shade[inst][int(p[-1])]
            if not use.any():                      # probe excluded on this cast
                ax.plot([], [], color=col, lw=1.2, label=f"{label} (excluded)")
                return
            ax.plot(np.where(use, df[var], np.nan), z, color=col, lw=1.2, label=label)

        for p in ("sh1", "sh2"):
            probe_line(axE, f"epsilon_{p}", p, f"{LABEL[inst]} {p}")
        for p in ("T1", "T2"):
            probe_line(axC, f"chi_{p}", p, f"{LABEL[inst]} {p}")

        if inst in args.fm:
            for p in ("sh1", "sh2"):
                fm = df[f"FM_{p}"][z <= z_max]
                probe_line(axF, f"FM_{p}", p, f"{LABEL[inst]} {p} (median {np.nanmedian(fm):.2f}, "
                                               f">{fm_max:g}: {np.mean(fm > fm_max):.0%})")

    raw = args.source == "perturb"
    # x limits from windows below the top 10 m (launch and surface windows reach 1e-2 W/kg)
    for ax, prefix in ((axE, "epsilon_sh"), (axC, "chi_T")):
        v = np.concatenate([df.loc[(df["depth"] > 10) & (df["depth"] <= z_max), [k for k in df if k.startswith(prefix)]]
                            .to_numpy().ravel() for *_, df in data])
        v = v[np.isfinite(v) & (v > 0)]
        ax.set_xlim(np.min(v) / 2, np.max(v) * 2)
    axT.set_xlabel("window-mean T (°C)" if raw else "CT (°C, FP07)")
    axT.set_ylabel("pressure (dbar)" if raw else "depth (m)")
    axT.set_ylim(z_max, 0)
    axT.legend(fontsize=7, loc="lower right")
    for ax, xlabel, title in ((axE, r"$\epsilon_{shear}$ (W kg$^{-1}$)", "shear probes sh1, sh2"),
                              (axC, r"$\chi$ (K$^2$ s$^{-1}$)", "thermistors T1, T2")):
        ax.set_xscale("log")
        ax.set_xlabel(xlabel)
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=7, loc="lower right")
    axF.axvspan(1 / fm_max, fm_max, color=ps.MID_GRAY, lw=0, zorder=0)
    axF.set_xlabel("shear figure of merit")
    axF.set_title(f"shear FM (grey band: within {fm_max:g}, flag only)", fontsize=9)
    axF.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    path = out / (f"{data[0][1]}_vs_{data[1][1]}" + (f"_{args.max_depth:g}m" if args.max_depth else "")
                  + ("_perturb" if raw else "") + ".png")
    fig.savefig(path, dpi=110, metadata={"Description": foot})   # provenance in the PNG metadata, not drawn
    plt.close(fig)
    print(f"wrote {common.portable_path(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
