# SPICE microstructure: salt finger diagnostics

Reproducible processing of Rockland VMP microstructure data (shear, FP07, CTD) from the 2026 R/V Falkor (too) SPICE expedition, aimed at testing whether thermal variance dissipation in thermohaline staircases exceeds what shear driven turbulence can explain, and estimating salt finger heat and salt diffusivities.

This repository holds code, configuration, environment files, and documentation only. Data live outside the repository and are located through the config file.

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
