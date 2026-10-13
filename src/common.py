"""Shared helpers for the pipeline driver and step modules.

Covers config loading, provenance (config hash, git commit, package
versions), running the microstructure-tpw command line tools with a logged
record of every invocation, reading the configuration record embedded in a
Rockland .p file, and resolving per-file patch edits from the config.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_PACKAGES = ["microstructure-tpw", "thermohalinesteps", "gsw", "numpy", "scipy",
                "xarray", "pandas", "netCDF4"]


# --------------------------------------------------------------------------
# Config and provenance
# --------------------------------------------------------------------------

def load_config(path: Path) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def apply_sensitivity(config: dict, config_hash: str, name: str) -> tuple[dict, str]:
    """Config of sensitivity run `name`: its `set` overrides (dotted keys, which must
    exist) applied to a copy, run.name = name, and a hash of the file plus overrides."""
    runs = {r["name"]: r for r in config.get("sensitivity_runs", [])}
    if name not in runs:
        sys.exit(f"No sensitivity run {name!r}; defined: {', '.join(runs)}")
    cfg = copy.deepcopy(config)
    for key, value in runs[name]["set"].items():
        node, parts = cfg, key.split(".")
        for p in parts[:-1]:
            if not isinstance(node, dict) or p not in node:
                sys.exit(f"Sensitivity run {name!r}: {key} is not a config key")
            node = node[p]
        if parts[-1] not in node:
            sys.exit(f"Sensitivity run {name!r}: {key} is not a config key")
        node[parts[-1]] = value
    cfg["run"]["name"] = name
    cfg["run"]["sensitivity"] = {"of": config["run"]["name"], "set": runs[name]["set"]}
    digest = hashlib.sha256((config_hash + json.dumps(runs[name]["set"], sort_keys=True)).encode())
    return cfg, digest.hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        # Outputs of the run itself do not make the code "dirty".
        dirty = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--",
                                ".", ":(exclude)outputs"],
                               capture_output=True, text=True, check=True)
        return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def package_commit(name: str) -> str | None:
    """Git commit a package was installed from (PEP 610 direct_url.json), if any."""
    try:
        text = metadata.distribution(name).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not text:
        return None
    return json.loads(text).get("vcs_info", {}).get("commit_id")


def provenance(config_hash: str) -> dict:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_sha256": config_hash,
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "packages": {name: package_version(name) for name in KEY_PACKAGES},
        "microstructure_tpw_commit": package_commit("microstructure-tpw"),
        "thermohalinesteps_commit": package_commit("thermohalinesteps"),
    }


def provenance_string(prov: dict) -> str:
    """One-line provenance for embedding in file headers and NetCDF attributes."""
    return (f"spice_microstructure git {prov['git_commit']}; config sha256 "
            f"{prov['config_sha256'][:12]}; microstructure-tpw "
            f"{prov['packages']['microstructure-tpw']} ({prov['microstructure_tpw_commit']})")


def run_dir_of(config: dict) -> Path:
    """<output_root>/<run.name>; a relative output_root is inside this repository."""
    root = Path(config["paths"]["output_root"])
    return (root if root.is_absolute() else REPO_ROOT / root) / config["run"]["name"]


def instruments(config: dict) -> list[tuple[str, dict]]:
    return [(name, config["instruments"][name]) for name in config["run"]["instruments"]]


def raw_files(inst: dict) -> list[Path]:
    """Raw .p files of an instrument, sorted by name (names are zero padded)."""
    return sorted(Path(inst["archive_raw"]).glob(inst["file_pattern"]))


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def write_step_metadata(step_dir: Path, step: str, ctx: dict, **extra) -> None:
    write_json(step_dir / "step_metadata.json",
               {"step": step, **provenance(ctx["config_hash"]),
                "manifests_verified": ctx.get("manifests_verified", True), **extra})


# --------------------------------------------------------------------------
# Running CLI tools
# --------------------------------------------------------------------------

def tool(name: str) -> str:
    """Path of a console script installed in the running Python environment."""
    path = Path(sys.executable).parent / name
    if not path.exists():
        sys.exit(f"Command line tool not found in this environment: {path}")
    return str(path)


def run_cmd(cmd: list, log_path: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, appending the exact command line and its output to log_path."""
    cmd = [str(c) for c in cmd]
    result = subprocess.run(cmd, capture_output=True, text=True)
    with open(log_path, "a") as log:
        log.write(f"$ {shlex.join(cmd)}\n[exit {result.returncode}]\n")
        if result.stdout:
            log.write(result.stdout if result.stdout.endswith("\n") else result.stdout + "\n")
        if result.stderr:
            log.write("[stderr]\n" + result.stderr)
        log.write("\n")
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {shlex.join(cmd)}\n"
                           f"See {log_path}")
    return result


# --------------------------------------------------------------------------
# .p file configuration records
# --------------------------------------------------------------------------

def parse_p_config(text: str) -> dict:
    """Parse the output of `rsi-tpw config` into {section_or_channel: {key: value}}.

    Comment lines (including patch annotations and the embedded original
    configuration) are ignored. Channel sections are keyed by channel name,
    other sections by section name. Keys are lower case.
    """
    out: dict[str, dict] = {}
    current: dict | None = None
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {"_section": line[1:-1].strip()}
            if current["_section"] != "channel":
                out[current["_section"]] = current
            continue
        if "=" in line and current is not None:
            key, value = (part.strip() for part in line.split("=", 1))
            current[key.lower()] = value
            if key.lower() == "name" and current["_section"] == "channel":
                out[value] = current
    return out


def non_comment_lines(text: str) -> list[str]:
    """Configuration lines with comments and whitespace stripped (for comparisons)."""
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split(";", 1)[0].split())
        if line:
            lines.append(line)
    return lines


def same_value(a, b) -> bool:
    """Compare config values as numbers when both parse as numbers, else as strings."""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def data_records_identical(raw: Path, patched: Path, header_bound: int = 65536) -> bool:
    """True if everything after the config header is byte identical.

    patch-config only rewrites the configuration record, which grows the
    header by a fixed number of bytes; the data records are shifted by that
    amount and must otherwise be unchanged.
    """
    delta = patched.stat().st_size - raw.stat().st_size
    with open(raw, "rb") as fa, open(patched, "rb") as fb:
        fa.seek(header_bound)
        fb.seek(header_bound + delta)
        while True:
            a, b = fa.read(1 << 20), fb.read(1 << 20)
            if a != b:
                return False
            if not a:
                return True


# --------------------------------------------------------------------------
# perturb output trees
# --------------------------------------------------------------------------

def single_dir(root: Path, prefix: str) -> Path:
    """The <prefix>_NN directory perturb wrote under root (convert/<instrument>).

    convert records the stage directories that match the current perturb config in
    convert/stage_dirs_<instrument>.json (perturb keeps older parameter sets in
    other _NN directories); without that record exactly one directory must exist."""
    root = Path(root)
    record = root.parent / f"stage_dirs_{root.name}.json"
    if record.exists():
        dirs = json.loads(record.read_text())
        if prefix in dirs:
            return root / dirs[prefix]
    found = sorted(Path(root).glob(f"{prefix}_[0-9][0-9]"))
    if len(found) != 1:
        raise RuntimeError(f"Expected one {prefix}_NN directory in {root}, found {found}")
    return found[0]


def profile_table(diss_dir: Path):
    """file, profile file name and start time (epoch s) of each per-profile NetCDF."""
    import netCDF4
    import pandas as pd
    rows = []
    for f in sorted(Path(diss_dir).glob("*_prof*.nc")):
        with netCDF4.Dataset(f) as ds:
            rows.append({"profile_file": f.name, "file": f.name.split("_prof")[0],
                         "stime": float(ds["stime"][...])})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Patch edits from the config
# --------------------------------------------------------------------------

def file_edits(inst: dict, files: list[Path], target: Path) -> dict:
    """Edits for one file: cruise_info and per-channel fields, merged over the
    patch ranges in config order (later ranges override earlier ones)."""
    patch = inst.get("patch", {})
    names = [f.name for f in files]
    idx = names.index(target.name)
    edits: dict = {"channels": {}}
    for rng in patch.get("ranges", []):
        if names.index(rng["first"]) <= idx <= names.index(rng["last"]):
            for channel, fields in rng.items():
                if channel in ("first", "last"):
                    continue
                edits["channels"].setdefault(channel, {}).update(
                    {k: str(v) for k, v in fields.items()})
    if edits["channels"] and patch.get("cruise_info"):
        edits["cruise_info"] = {k: str(v) for k, v in patch["cruise_info"].items()}
    return edits if edits["channels"] else {}


# --------------------------------------------------------------------------
# Checks before a run
# --------------------------------------------------------------------------

def find_todos(node, prefix="") -> list[str]:
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found += find_todos(value, f"{prefix}{key}.")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += find_todos(value, f"{prefix}{i}.")
    elif node == "TODO":
        found.append(prefix.rstrip("."))
    return found


def verify_manifests(config: dict) -> None:
    """Verify every archive input against its committed manifest; exit on failure."""
    manifests = config.get("manifests", {})
    if not manifests.get("verify_before_run", False):
        return
    pairs = [(config["paths"]["sealog_dir"], manifests.get("sealog")),
             (config["paths"]["probe_calsheets"], manifests.get("probe_calsheets")),
             (config["paths"]["ship_ctd"], manifests.get("ship_ctd"))]
    for _, inst in instruments(config):
        for kind in ("raw", "patched", "processed"):
            pairs.append((inst[f"archive_{kind}"], inst["manifests"].get(kind)))
    script = REPO_ROOT / "scripts" / "make_manifest.py"
    for data_dir, manifest in pairs:
        if not manifest:
            continue
        manifest_path = REPO_ROOT / manifest
        if not manifest_path.exists():
            sys.exit(f"Manifest not found: {manifest_path}. Write it first (see README).")
        result = subprocess.run([sys.executable, str(script), "verify", data_dir,
                                 str(manifest_path)])
        if result.returncode != 0:
            sys.exit(f"Manifest verification failed for {data_dir}. Stopping.")


# --------------------------------------------------------------------------
# Standalone step entry point
# --------------------------------------------------------------------------

def step_main(step: str, run_fn) -> int:
    """Run one step on its own: python src/steps/<step>.py --config config/config.yaml"""
    parser = argparse.ArgumentParser(description=f"Run the '{step}' step on its own.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip archive manifest verification (recorded in step metadata).")
    parser.add_argument("--sensitivity", metavar="NAME",
                        help="Run as sensitivity run NAME (config sensitivity_runs).")
    args = parser.parse_args()
    config, config_hash = load_config(args.config)
    if args.sensitivity:
        config, config_hash = apply_sensitivity(config, config_hash, args.sensitivity)
    todos = find_todos(config)
    if todos:
        sys.exit("Fill all TODO values in the config before running: " + ", ".join(todos))
    if not args.skip_verify:
        verify_manifests(config)
    ctx = {"config": config, "config_hash": config_hash, "run_dir": run_dir_of(config),
           "manifests_verified": not args.skip_verify}
    ctx["run_dir"].mkdir(parents=True, exist_ok=True)
    run_fn(ctx)
    return 0
