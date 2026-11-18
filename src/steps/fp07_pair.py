#!/usr/bin/env python3
"""Step fp07_pair: per-bead FP07 response corrections (microstructure-tpw `fp07-pair fit`).

Two FP07 beads on one probe head see the same temperature microstructure, so
the ratio of their gradient spectra measures their relative response with no
turbulence model. `fp07-pair fit` turns that ratio into a correction per bead
pair and time segment; convert passes the corrections to perturb
(instruments.<key>.fp07_response), which equalizes each bead's spectra before
chi is computed, and checks each file against its correction (files that
disagree run uncorrected and say so in their attributes).

The corrections are fitted on the chi products of `fp07_pair.source_run` (a
run with the same perturb settings and no correction), so the run that applies
them depends on that run's convert output. Disabled (the default), the step
only records that.

Reads:  <output_root>/<source_run>/convert/<instrument>/chi_NN/*_prof*.nc
Writes: <run_dir>/fp07_pair/<instrument>/fp07pair_*.nc and fp07pair_report.txt,
        corrections_<instrument>.json (files and fit summary, read by convert),
        commands.log, step_metadata.json
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

STEP = "fp07_pair"
LINE = re.compile(r"^\s+SN\S+ (?P<pair>T1_\S+ T2_\S+) \[(?P<span>[^\]]+)\]: (?P<files>\d+) files, (?P<windows>\d+) "
                  r"windows; band (?P<band>[\d.]+-[\d.]+) Hz; ln G (?P<lnG>[-+\d.]+) .*?ln R' at 20 Hz "
                  r"(?P<lnR20>[-+\d.]+); per-file mid-band spread (?P<spread>[\d.]+); flags (?P<flags>\S+)")


def corrections_path(run_dir: Path, name: str) -> Path:
    return run_dir / STEP / f"corrections_{name}.json"


def run(ctx: dict) -> None:
    config = ctx["config"]
    fc = config["fp07_pair"]
    out = ctx["run_dir"] / STEP
    out.mkdir(parents=True, exist_ok=True)
    log = out / "commands.log"
    log.write_text("")
    if not fc["enabled"]:
        common.write_step_metadata(out, STEP, ctx, enabled=False)
        print("  fp07_pair disabled")
        return
    root = Path(config["paths"]["output_root"])
    src = (root if root.is_absolute() else common.REPO_ROOT / root) / fc["source_run"] / "convert"
    report = {}
    for name in fc["instruments"]:
        chi_dir = common.single_dir(src / name, "chi")
        dest = out / name
        if dest.exists():
            shutil.rmtree(dest)
        cmd = ["fp07-pair", "fit", str(chi_dir / "*_prof*.nc"), "-o", dest, "--anchor", fc["anchor"],
               "--min-files", fc["min_files"]]
        if not fc["segment"]:
            cmd.append("--no-segment")
        if fc["allow_amplitude"]:
            cmd.append("--allow-amplitude")
        common.run_cmd(cmd, log)
        files = sorted(dest.glob("fp07pair_*.nc"))
        if not files:
            raise RuntimeError(f"fp07-pair fit wrote no corrections for {name}; see {log}")
        text = (dest / "fp07pair_report.txt").read_text()
        fits = [m.groupdict() for m in map(LINE.match, text.splitlines()) if m]
        report[name] = {"source_chi": common.portable_path(chi_dir), "anchor": fc["anchor"],
                        "files": [common.portable_path(f) for f in files], "fits": fits}
        common.write_json(corrections_path(ctx["run_dir"], name), report[name])
        for f in fits:
            print(f"  {name} {f['pair']}: {f['files']} files, ln G {f['lnG']}, ln R'(20 Hz) {f['lnR20']}, "
                  f"spread {f['spread']}, flags {f['flags']}")
    common.write_step_metadata(out, STEP, ctx, enabled=True, source_run=fc["source_run"], report=report)


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
