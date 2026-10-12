#!/usr/bin/env python3
"""Step cast_log: cast table and ship track from the .p headers and the Sealog export.

Reads:  raw .p files (start time, duration, embedded probe calibration via
        `rsi-tpw info` and `rsi-tpw config`), the Sealog export, the config.
Writes: <run_dir>/cast_log/
          track.csv                  ship track (t epoch s, lat, lon) for perturb gps
          casts_<instrument>.csv     one row per .p file
          sealog_<instrument>.csv    VMP Sealog events with their matched file
          sealog_unassigned.csv      VMP events with no platform
          cast_log_report.json       counts, unmatched events, serial checks
          commands.log, step_metadata.json

Sealog events are matched to files by time, not by the logged file name,
because several logged names and times are wrong. An event matches a file
when it falls between the file start minus the match window and the file
end plus the window; the closest start wins.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

STEP = "cast_log"
PROBE_CHANNELS = ["sh1", "sh2", "T1", "T2"]
SEALOG_SERIAL_COLS = {"sh1": "event_option.s1_serial_#", "sh2": "event_option.s2_serial_#",
                      "T1": "event_option.t1_serial_#", "T2": "event_option.t2_serial_#"}


def read_info(files: list[Path], log: Path) -> pd.DataFrame:
    """Start time, duration and instrument string from `rsi-tpw info`."""
    out = common.run_cmd([common.tool("rsi-tpw"), "info", *files], log).stdout
    rows, cur = [], {}
    for line in out.splitlines():
        if line.startswith("File:"):
            cur = {"file": line.split(":", 1)[1].strip()}
            rows.append(cur)
        elif line.startswith("Instrument:"):
            cur["instrument_header"] = line.split(":", 1)[1].strip()
        elif line.startswith("Start:"):
            cur["start_utc"] = pd.Timestamp(line.split(":", 1)[1].strip()).tz_convert("UTC")
        elif line.startswith("Duration:"):
            cur["duration_s"] = float(line.split(":", 1)[1].split()[0])
    df = pd.DataFrame(rows)
    missing = set(f.name for f in files) - set(df["file"])
    if missing:
        raise RuntimeError(f"rsi-tpw info returned no header for: {sorted(missing)}")
    df["end_utc"] = df["start_utc"] + pd.to_timedelta(df["duration_s"], unit="s")
    return df


def read_raw_probes(files: list[Path], log: Path) -> pd.DataFrame:
    """Probe serials and shear sensitivities embedded in each raw file."""
    rows = []
    for f in files:
        cfg = common.parse_p_config(
            common.run_cmd([common.tool("rsi-tpw"), "config", f], log).stdout)
        row = {"file": f.name}
        for ch in PROBE_CHANNELS:
            row[f"raw_{ch}_sn"] = cfg.get(ch, {}).get("sn")
            if ch.startswith("sh"):
                row[f"raw_{ch}_sens"] = cfg.get(ch, {}).get("sens")
        rows.append(row)
    return pd.DataFrame(rows)


def epoch_seconds(times) -> np.ndarray:
    """UTC datetimes to epoch seconds, independent of the datetime64 resolution."""
    times = pd.to_datetime(pd.Series(times), utc=True)
    return ((times - pd.Timestamp(0, tz="UTC")) / pd.Timedelta(seconds=1)).to_numpy(float)


def build_track(sealog: pd.DataFrame, events: list[str]) -> pd.DataFrame:
    lat, lon = "vesselRealtimeNavData.latitude_value", "vesselRealtimeNavData.longitude_value"
    tr = sealog[sealog["event_value"].isin(events)][["ts", lat, lon]].dropna()
    tr = tr.rename(columns={lat: "lat", lon: "lon"})
    tr["time_utc"] = pd.to_datetime(tr["ts"], utc=True)
    tr = tr.sort_values("time_utc").drop_duplicates("time_utc")
    tr["t"] = epoch_seconds(tr["time_utc"])
    return tr[["t", "lat", "lon", "time_utc"]].reset_index(drop=True)


def interp_track(track: pd.DataFrame, times: pd.Series) -> pd.DataFrame:
    t = epoch_seconds(times)
    gap = np.min(np.abs(track["t"].to_numpy()[None, :] - t[:, None]), axis=1)
    return pd.DataFrame({"lat": np.interp(t, track["t"], track["lat"]),
                         "lon": np.interp(t, track["t"], track["lon"]),
                         "track_gap_s": gap})


def file_number(name) -> int | None:
    digits = re.findall(r"\d+", str(name))
    return int(digits[-1]) if digits else None


def match_events(ev: pd.DataFrame, casts: pd.DataFrame, window_min: float) -> pd.DataFrame:
    w = pd.Timedelta(minutes=window_min)
    matched, dt = [], []
    for ts in ev["time_utc"]:
        ok = casts[(casts["start_utc"] - w <= ts) & (ts <= casts["end_utc"] + w)]
        if ok.empty:
            matched.append(None)
            dt.append(np.nan)
        else:
            d = (ts - ok["start_utc"]).abs()
            best = ok.loc[d.idxmin()]
            matched.append(best["file"])
            dt.append((ts - best["start_utc"]).total_seconds() / 60)
    ev = ev.copy()
    ev["matched_file"] = matched
    ev["minutes_from_start"] = np.round(dt, 1)
    logged = ev["event_option.file_name"]
    ev["logged_name_mismatch"] = [
        bool(isinstance(name, str) and m is not None and file_number(name) != file_number(m))
        for name, m in zip(logged, matched)]
    return ev


def check_serials(ev: pd.DataFrame, casts: pd.DataFrame) -> list[dict]:
    """Compare Sealog probe-serial entries with the expected serials of the
    first file that starts after each entry."""
    problems = []
    for _, e in ev.iterrows():
        logged = {ch: e.get(col) for ch, col in SEALOG_SERIAL_COLS.items()
                  if isinstance(e.get(col), str) and e.get(col).strip()}
        if not logged:
            continue
        after = casts[casts["start_utc"] > e["time_utc"]]
        if after.empty:
            continue
        nxt = after.iloc[0]
        for ch, sn in logged.items():
            expected = nxt[f"expected_{ch}_sn"]
            if not common.same_value(sn, expected):
                problems.append({"sealog_time": str(e["time_utc"]), "next_file": nxt["file"],
                                 "channel": ch, "sealog_sn": sn, "expected_sn": expected})
    return problems


def run(ctx: dict) -> None:
    config = ctx["config"]
    out = ctx["run_dir"] / STEP
    out.mkdir(parents=True, exist_ok=True)
    log = out / "commands.log"
    log.write_text("")
    cl = config["cast_log"]

    sealog_path = Path(config["paths"]["sealog_dir"]) / config["paths"]["sealog_file"]
    sealog = pd.read_csv(sealog_path, low_memory=False)
    sealog["time_utc"] = pd.to_datetime(sealog["ts"], utc=True)
    track = build_track(sealog, cl["track_events"])
    track.to_csv(out / "track.csv", index=False)

    vmp = sealog[sealog["event_value"] == "VMP"]
    keep = ["time_utc", "event_author", "event_free_text", "event_option.event_comment",
            "event_option.file_name", "event_option.platform", "event_option.pre-cast_voltage",
            *SEALOG_SERIAL_COLS.values()]
    keep = [c for c in keep if c in vmp.columns]
    vmp[vmp["event_option.platform"].isna()][keep].to_csv(out / "sealog_unassigned.csv",
                                                          index=False)
    max_gap = config["conversion"]["gps_max_time_diff_s"]
    dt = track["t"].diff()
    gaps = [{"from": str(track["time_utc"][i - 1]), "to": str(track["time_utc"][i]),
             "hours": round(dt[i] / 3600, 2)} for i in track.index[dt > max_gap]]
    report = {"sealog_file": str(sealog_path), "track_points": len(track),
              "track_median_spacing_s": float(dt.median()),
              "track_gaps_longer_than_gps_max_time_diff": gaps, "instruments": {}}

    for name, inst in common.instruments(config):
        files = common.raw_files(inst)
        if not files:
            raise RuntimeError(f"No raw files for {name} in {inst['archive_raw']}")
        casts = read_info(files, log).merge(read_raw_probes(files, log), on="file")
        casts.insert(0, "instrument", name)

        # Expected probe serials and sensitivities after the patch step:
        # embedded raw values overridden by the config's patch ranges.
        for ch in PROBE_CHANNELS:
            casts[f"expected_{ch}_sn"] = casts[f"raw_{ch}_sn"]
            if ch.startswith("sh"):
                casts[f"expected_{ch}_sens"] = casts[f"raw_{ch}_sens"]
        for i, f in enumerate(files):
            for ch, fields in common.file_edits(inst, files, f).get("channels", {}).items():
                for key in ("sn", "sens"):
                    col = f"expected_{ch}_{key}"
                    if key in fields and col in casts.columns:
                        casts.loc[i, col] = fields[key]

        casts = pd.concat([casts, interp_track(track, casts["start_utc"])], axis=1)
        casts["position_flag"] = casts["track_gap_s"] > max_gap
        ps = set(inst.get("process_station_files", []))
        casts["station"] = ["process_station" if f in ps else "" for f in casts["file"]]
        casts["towyo"] = casts["file"].isin(inst.get("towyo", []))
        casts["excluded"] = casts["file"].map(inst.get("exclude", {})).fillna("")
        casts["excluded_probes"] = casts["file"].map(
            lambda f: ",".join(inst.get("exclude_probes", {}).get(f, [])))
        casts["caution"] = casts["file"].map(inst.get("flag", {})).fillna("")

        ev = vmp[vmp["event_option.platform"] == inst["sealog_platform"]][keep]
        ev = match_events(ev.sort_values("time_utc"), casts, cl["match_window_min"])
        ev.to_csv(out / f"sealog_{name}.csv", index=False)
        notes = (ev.dropna(subset=["matched_file"])
                 .assign(text=lambda d: d[["event_free_text", "event_option.event_comment"]]
                         .fillna("").agg(" ".join, axis=1).str.strip())
                 .query("text != ''").groupby("matched_file")["text"].agg(" | ".join))
        casts["sealog_notes"] = casts["file"].map(notes).fillna("")
        casts.to_csv(out / f"casts_{name}.csv", index=False)

        serial_problems = check_serials(ev, casts)
        report["instruments"][name] = {
            "files": len(casts),
            "sealog_events": len(ev),
            "sealog_events_matched": int(ev["matched_file"].notna().sum()),
            "sealog_events_unmatched": ev[ev["matched_file"].isna()][
                ["time_utc", "event_option.file_name", "event_free_text"]
            ].astype(str).to_dict("records"),
            "logged_name_mismatches": ev[ev["logged_name_mismatch"]][
                ["time_utc", "event_option.file_name", "matched_file"]
            ].astype(str).to_dict("records"),
            "files_without_sealog_event": sorted(set(casts["file"]) - set(ev["matched_file"].dropna())),
            "probe_serial_mismatches": serial_problems,
            "position_flagged_files": casts.loc[casts["position_flag"], "file"].tolist(),
            "process_station_files": sorted(ps),
            "excluded": inst.get("exclude", {}),
        }
        print(f"  {name}: {len(casts)} files, {report['instruments'][name]['sealog_events_matched']}"
              f"/{len(ev)} Sealog events matched, {len(serial_problems)} serial mismatches")

    common.write_json(out / "cast_log_report.json", report)
    common.write_step_metadata(out, STEP, ctx, sealog_sha256_manifest=config["manifests"]["sealog"])


if __name__ == "__main__":
    sys.exit(common.step_main(STEP, run))
