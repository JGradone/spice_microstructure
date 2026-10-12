# SPICE microstructure processing

Reproducible processing of all Rockland VMP microstructure data (VMP-250IR SN 537 and VMP-5500 SN 010; shear, FP07, CTD) from the 2026 R/V Falkor (too) SPICE expedition (FKt260806). The chain runs from raw .p files to exported products (epsilon, chi, hydrography, regime labels, and bin-averaged diffusivities with uncertainty; see `docs/products.md`) for use in other analyses. A central question is whether thermal variance dissipation in thermohaline staircases exceeds what shear driven turbulence can explain, and what the salt finger heat and salt diffusivities are.

This repository holds the code, configuration, environment files and documentation, plus the analysis outputs under `outputs/<run.name>/`. Figures, cast tables and reports are committed. Raw and converted instrument data (.p, NetCDF) are gitignored and stay local; the input archives live outside the repository and are located through the config file.

## Layout

```
CLAUDE.md                 # methods, rules, and workflow (read first)
config/
  config.example.yaml     # committed template; copy to config.yaml and set paths
src/
  run_pipeline.py         # single entry point for the full chain
scripts/
  make_manifest.py        # write or verify checksum manifests of data directories
  record_environment.py   # snapshot Python and package versions
manifests/                # committed checksum manifests
docs/
  shipboard_processing.md # record of what was run at sea
  decisions.md            # dated log of methods decisions
requirements.in           # direct dependencies (unpinned)
requirements.txt          # pinned environment (generate, then commit)
```

## Getting started

Requires Python 3.10 or newer.

1. Create an environment and pin it:

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.in
   pip freeze > requirements.txt
   ```

   To reproduce the pinned environment exactly, install from `requirements.txt` instead, which pins microstructure-tpw to a git commit. The shipboard environment (microstructure-tpw 0.3.1) is recorded in `docs/shipboard_pip_freeze.txt` for reference only.

2. Copy the config template and set data paths:

   ```
   cp config/config.example.yaml config/config.yaml
   ```

   `config/config.yaml` is ignored by git because it holds local paths. Any parameter change that matters for results must also be reflected in `config.example.yaml` or a committed run config.

3. Write checksum manifests for the archived shipboard directories (run once, then commit):

   ```
   python scripts/make_manifest.py write /path/to/vmp250_raw manifests/vmp250_raw.sha256.csv
   python scripts/make_manifest.py write /path/to/vmp250_patched manifests/vmp250_patched.sha256.csv
   python scripts/make_manifest.py write /path/to/vmp250_processed manifests/vmp250_processed.sha256.csv
   python scripts/make_manifest.py write /path/to/vmp6000_raw manifests/vmp6000_raw.sha256.csv
   python scripts/make_manifest.py write /path/to/vmp6000_patched manifests/vmp6000_patched.sha256.csv
   python scripts/make_manifest.py write /path/to/vmp6000_processed manifests/vmp6000_processed.sha256.csv
   python scripts/make_manifest.py write /path/to/SPICE_turbulence/sealog manifests/sealog.sha256.csv
   python scripts/make_manifest.py write /path/to/SPICE_turbulence/SpiceProbeCalSheets manifests/probe_calsheets.sha256.csv
   ```

   Verify at any time:

   ```
   python scripts/make_manifest.py verify /path/to/vmp250_raw manifests/vmp250_raw.sha256.csv
   ```

4. Snapshot the environment and commit the result:

   ```
   python scripts/record_environment.py docs/environment.json
   ```

5. Fill in `docs/shipboard_processing.md` before writing pipeline code.

6. Run the pipeline:

   ```
   python src/run_pipeline.py --config config/config.yaml
   ```

   Steps are stubs until implemented. The first milestone is a baseline run from raw on the pinned package version with the shipboard parameters (see CLAUDE.md).

## License

Code in this repository is released under the MIT License (see `LICENSE`). It covers the code and documentation only; no cruise data are included. The microstructure-tpw dependency is distributed separately under its own license (GPL-3.0-or-later).
