#!/usr/bin/env python3
"""Step convert: run microstructure-tpw's perturb pipeline on the patched files.

perturb's stage subcommands (profiles, diss, chi) each run the whole
pipeline, so the package cannot be split into separate conversion, epsilon
and chi steps. This step runs `perturb run` once per instrument; the later
epsilon_shear and thermistor steps post-process its outputs.

Reads:  <run_dir>/patch/<instrument>/*.p, <run_dir>/cast_log/track.csv,
        the `perturb`, `conversion` and `products` sections of the config.
Writes: <run_dir>/convert/
          perturb_config_<instrument>.yaml   the exact config passed to perturb
          <instrument>/                      perturb output tree (profiles_NN,
                                             diss_NN, chi_NN, ctd_NN, *_binned_NN,
                                             *_combo_NN, logs/)
          convert_report.json, commands.log, step_metadata.json

The generated perturb config sets every option explicitly (the shared
`perturb` block merged with instruments.<name>.perturb_overrides) and embeds
the provenance string in the NetCDF `comment` attribute.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

STEP = "convert"


def merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def perturb_config(config: dict, name: str, inst: dict, patched: Path, output: Path,
                   track: Path, prov: dict) -> dict:
    conv, prod = config["conversion"], config["products"]
    pc = merge(config["perturb"], inst.get("perturb_overrides", {}))
    pc["files"] = {"p_file_root": str(patched), "p_file_pattern": inst["file_pattern"],
                   "output_root": str(output), "force_trim": False, "merge": False}
    pc["gps"] = {"source": conv["gps_source"], "lat": None, "lon": None, "file": str(track),
                 "time_col": "t", "lat_col": "lat", "lon_col": "lon",
                 "max_time_diff": conv["gps_max_time_diff_s"]}
    pc["hotel"] = {"enable": False}
    pc["parallel"] = {"jobs": conv["jobs"]}
    pc["instruments"] = {}
    pc["netcdf"] = {
        "title": f"SPICE FKt260806 {inst['model']} SN {inst['serial']} microstructure",
        "institution": prod["institution"], "creator_name": prod["creator_name"],
        "creator_email": prod["creator_email"], "license": prod["license"],
        "project": "SPICE", "platform": "R/V Falkor (too)",
        "instrument": f"Rockland {inst['model']} SN {inst['serial']}",
        "comment": common.provenance_string(prov),
    }
    return pc


def inventory(output: Path) -> dict:
    counts = {}
    for d in sorted(p for p in output.iterdir() if p.is_dir()):
        counts[d.name] = len(list(d.glob("*.nc")))
    return counts


def run(ctx: dict) -> None:
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    out.mkdir(parents=True, exist_ok=True)
    log = out / "commands.log"
    log.write_text("")
    prov = common.provenance(ctx["config_hash"])
    track = ctx["run_dir"] / "cast_log" / "track.csv"
    report = {}

    for name, inst in common.instruments(config):
        patched = ctx["run_dir"] / "patch" / name
        files = sorted(patched.glob(inst["file_pattern"]))
        if not files:
            raise RuntimeError(f"No patched files for {name} in {patched}; run the patch step")
        output = out / name
        output.mkdir(exist_ok=True)
        cfg_path = out / f"perturb_config_{name}.yaml"
        cfg_path.write_text(yaml.safe_dump(
            perturb_config(config, name, inst, patched, output, track, prov), sort_keys=False))

        result = common.run_cmd([common.tool("perturb"), "run", "--config", cfg_path,
                                 "--output", output, *files], log, check=False)
        summary = result.stderr.strip()
        logs = sorted((output / "logs").glob("run_*.log"))
        run_log = logs[-1] if logs else None
        warnings = 0
        if run_log:
            warnings = sum(1 for line in run_log.read_text().splitlines()
                           if re.search(r"\bWARNING\b", line))
        report[name] = {"files": len(files), "exit_code": result.returncode,
                        "perturb_summary": summary, "perturb_log": str(run_log),
                        "warnings_in_log": warnings, "outputs": inventory(output)}
        print(f"  {name}: exit {result.returncode}; {summary.splitlines()[0] if summary else ''}")
        if result.returncode != 0:
            common.write_json(out / "convert_report.json", report)
            raise RuntimeError(f"perturb run failed for {name}; see {run_log}")

    common.write_json(out / "convert_report.json", report)
    common.write_step_metadata(out, STEP, ctx)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
