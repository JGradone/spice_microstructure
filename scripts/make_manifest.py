#!/usr/bin/env python3
"""Write or verify a SHA-256 checksum manifest for a data directory.

Standard library only, so it runs before the project environment exists.

Usage:
    python scripts/make_manifest.py write  DATA_DIR_OR_FILE MANIFEST.csv
    python scripts/make_manifest.py verify DATA_DIR_OR_FILE MANIFEST.csv

The manifest is a CSV with columns: relative_path, size_bytes, sha256.
Paths are relative to DATA_DIR and sorted, so the file is stable across runs
and machines. Verify exits with status 1 if any file is missing, added, or
changed.
"""

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

CHUNK = 1024 * 1024
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def scan(data_dir: Path) -> dict:
    if data_dir.is_file():
        # A single file is its own manifest entry, keyed by its name.
        return {data_dir.name: (data_dir.stat().st_size, sha256_of(data_dir))}
    entries = {}
    for root, dirs, files in os.walk(data_dir):
        dirs.sort()
        for name in sorted(files):
            if name in IGNORED_NAMES:
                continue
            full = Path(root) / name
            rel = full.relative_to(data_dir).as_posix()
            entries[rel] = (full.stat().st_size, sha256_of(full))
    return entries


def write_manifest(data_dir: Path, manifest: Path) -> int:
    entries = scan(data_dir)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relative_path", "size_bytes", "sha256"])
        for rel in sorted(entries):
            size, digest = entries[rel]
            writer.writerow([rel, size, digest])
    print(f"Wrote {len(entries)} entries to {manifest}")
    return 0


def read_manifest(manifest: Path) -> dict:
    with manifest.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return {
            row["relative_path"]: (int(row["size_bytes"]), row["sha256"])
            for row in reader
        }


def verify_manifest(data_dir: Path, manifest: Path) -> int:
    expected = read_manifest(manifest)
    actual = scan(data_dir)
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    changed = sorted(
        rel for rel in set(expected) & set(actual) if expected[rel] != actual[rel]
    )
    for label, items in (("MISSING", missing), ("ADDED", added), ("CHANGED", changed)):
        for rel in items:
            print(f"{label}: {rel}")
    if missing or added or changed:
        print(
            f"FAILED: {len(missing)} missing, {len(added)} added, "
            f"{len(changed)} changed (of {len(expected)} expected)"
        )
        return 1
    print(f"OK: {len(expected)} files match {manifest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["write", "verify"])
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"Not found: {args.data_dir}", file=sys.stderr)
        return 2
    if args.action == "write":
        if args.manifest.exists():
            print(
                f"Refusing to overwrite existing manifest {args.manifest}. "
                "Delete it deliberately if a new manifest is intended.",
                file=sys.stderr,
            )
            return 2
        return write_manifest(args.data_dir, args.manifest)
    return verify_manifest(args.data_dir, args.manifest)


if __name__ == "__main__":
    sys.exit(main())
