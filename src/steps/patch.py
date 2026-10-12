#!/usr/bin/env python3
"""Step patch: regenerate patched .p files from the raw files.

Reads:  raw .p files, instruments.<name>.patch in the config, the cast table
        from cast_log (expected serials and sensitivities).
Writes: <run_dir>/patch/
          <instrument>/                 one .p per raw file: a patched copy, or a
                                        symlink to the raw file when no edit applies
          edits/<instrument>_NN.yaml    the edit specs passed to rsi-tpw patch-config
          patch_report_<instrument>.csv per-file verification and archive comparison
          patch_report.json, commands.log, step_metadata.json

Files that need identical edits are patched in one `rsi-tpw patch-config`
call. Raw files are never modified (patch-config writes new files). Every
patched file is checked: each edited field must hold the configured value,
the cast table's expected serials and sensitivities must match, and the data
records must be byte identical to the raw file. The non-comment config is
also compared with the shipboard patched file, as information only.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

STEP = "patch"


def p_config(path: Path, log: Path) -> str:
    return common.run_cmd([common.tool("rsi-tpw"), "config", path], log).stdout


def edit_spec(edits: dict, inst: dict, prov: dict) -> dict:
    spec = {"note": f"spice_microstructure patch step; {common.provenance_string(prov)}",
            "author": inst["patch"]["author"],
            "channels": edits["channels"]}
    if edits.get("cruise_info"):
        spec["cruise_info"] = edits["cruise_info"]
    return spec


def verify(f: Path, raw: Path, edits: dict, cast: pd.Series, archive: Path, log: Path) -> dict:
    text = p_config(f, log)
    cfg = common.parse_p_config(text)
    problems = []
    for ch, fields in edits.get("channels", {}).items():
        for key, value in fields.items():
            got = cfg.get(ch, {}).get(key.lower())
            if not common.same_value(got, value):
                problems.append(f"{ch}.{key}={got!r}, expected {value!r}")
    for ch in ("sh1", "sh2", "T1", "T2"):
        for key in ("sn", "sens"):
            col = f"expected_{ch}_{key}"
            if col in cast and pd.notna(cast[col]):
                got = cfg.get(ch, {}).get(key)
                if not common.same_value(got, cast[col]):
                    problems.append(f"{ch}.{key}={got!r}, cast table expects {cast[col]!r}")
    identical = True if f.is_symlink() else common.data_records_identical(raw, f)
    if not identical:
        problems.append("data records differ from raw")

    archive_diff = ""
    if archive.exists():
        a = common.non_comment_lines(p_config(archive, log))
        b = common.non_comment_lines(text)
        only_archive = [x for x in a if x not in b]
        only_new = [x for x in b if x not in a]
        archive_diff = " | ".join([f"archive: {x}" for x in only_archive] +
                                  [f"new: {x}" for x in only_new])
    return {"verified": not problems, "problems": "; ".join(problems),
            "data_identical": identical, "differs_from_archive": archive_diff}


def run(ctx: dict) -> None:
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    cast_dir = ctx["run_dir"] / "cast_log"
    out.mkdir(parents=True, exist_ok=True)
    (out / "edits").mkdir(exist_ok=True)
    log = out / "commands.log"
    log.write_text("")
    prov = common.provenance(ctx["config_hash"])
    report = {}

    for name, inst in common.instruments(config):
        casts = pd.read_csv(cast_dir / f"casts_{name}.csv", dtype=str).set_index("file")
        files = common.raw_files(inst)
        dest = out / name
        if dest.exists():
            shutil.rmtree(dest)     # derived output; regenerated in full each run
        dest.mkdir()

        # Group files by identical edits; one patch-config call per group.
        groups: dict[str, list[Path]] = {}
        edits_of = {}
        for f in files:
            edits_of[f.name] = common.file_edits(inst, files, f)
            if edits_of[f.name]:
                groups.setdefault(json.dumps(edits_of[f.name], sort_keys=True), []).append(f)
        for i, (key, members) in enumerate(groups.items()):
            spec_path = out / "edits" / f"{name}_{i:02d}.yaml"
            spec_path.write_text(yaml.safe_dump(edit_spec(json.loads(key), inst, prov),
                                                sort_keys=False))
            common.run_cmd([common.tool("rsi-tpw"), "patch-config", *members,
                            "--edits", spec_path, "--batch-cal", "--out", dest], log)

        # Files with no edits, or whose values already matched, are not
        # written by patch-config: link them to the raw file.
        rows = []
        for f in files:
            target = dest / f.name
            status = "patched"
            if not target.exists():
                os.symlink(f.resolve(), target)
                status = "linked_to_raw" if not edits_of[f.name] else "already_matched_linked"
            row = {"file": f.name, "status": status,
                   "edited": ", ".join(f"{ch}.{k}" for ch, kv in
                                       edits_of[f.name].get("channels", {}).items() for k in kv)}
            row.update(verify(target, f, edits_of[f.name], casts.loc[f.name],
                              Path(inst["archive_patched"]) / f.name, log))
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(out / f"patch_report_{name}.csv", index=False)
        report[name] = {
            "files": len(df),
            "patched": int((df["status"] == "patched").sum()),
            "linked_to_raw": int((df["status"] != "patched").sum()),
            "edit_groups": len(groups),
            "verification_failures": df.loc[~df["verified"], ["file", "problems"]]
                                     .to_dict("records"),
            "files_differing_from_archive": int((df["differs_from_archive"] != "").sum()),
        }
        print(f"  {name}: {report[name]['patched']} patched, {report[name]['linked_to_raw']} "
              f"linked, {len(report[name]['verification_failures'])} verification failures, "
              f"{report[name]['files_differing_from_archive']} differ from archive")

    common.write_json(out / "patch_report.json", report)
    common.write_step_metadata(out, STEP, ctx)
    failures = sum(len(r["verification_failures"]) for r in report.values())
    if failures:
        raise RuntimeError(f"{failures} patched files failed verification; see {out}")


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
