# SPICE VMP microstructure processing

This repository is the main processing workflow for all Rockland VMP microstructure data (shear probes, FP07 thermistors, CTD) from the FKt260806 SPICE cruise, both instruments. It runs from the raw .p files to documented derived products: epsilon, chi, background hydrography, regime labels, and bin-averaged diffusivities with uncertainty. Those products are exported for further analysis elsewhere (see `docs/products.md`). A central science question, and the reason for the double diffusion steps, is the salt finger contribution to mixing. Read this file fully before writing or running any code.

## Outputs are the interface

Scope: this repository is only the microstructure processing workflow. Nitrate, productivity, grazing and other datasets are combined with the exported products elsewhere; they do not enter this repository. The products are designed to serve those analyses: diffusivity profiles including K_S (the diffusivity relevant to nitrate in fingering) from 20 dbar down, the finger attribution ladder, and per-cast finger metrics for mesoscale comparisons (decisions.md 2026-10-14).

* Analyses outside this repository read only the exported products (`export` step, specified in `docs/products.md`), never intermediate step outputs.
* Products carry full provenance (config hash, git commit, package versions, product version) and keep every exclusion and caution as a flag, not as silently missing data.
* Any change to product variables, units, or methods bumps `products.product_version` and gets a dated entry in `docs/decisions.md`.
* Diffusivities are exported only as bin averages (see steps 7 and 8). The segment product carries epsilon, chi and gradients so other users can form their own averages correctly.

## Context

* Data come from a 2026 R/V Falkor (too) cruise (FKt260806): VMP-250IR SN 537 casts and deep casts with VMP-5500 SN 010. "VMP6000" and "VMP5500" are the same deep instrument; its directories are named `vmp6000_*`, and the Sealog calls it VMP5500.
* The 48 hour process station (11.626 N, 50.577 W, 2026-08-19 22:40 to 2026-08-21 ~19:30 UTC) is in a region with thermohaline staircases. VMP250: `data_0132.p` (4 profiles), `data_0133.p` (3) and `data_0134.p` (8), 15 profiles in total. The 8 in `data_0134.p` are tow-yo profiles with the ship under way, not free-fall casts from a stationary ship. VMP5500: `SPC_033.P`, `SPC_034.P`, `SPC_038.P` (31 min, short) and `SPC_039.P`.
* Observed pattern: elevated thermal variance dissipation (chi) at or near staircase interfaces, with low shear derived epsilon (order 1e-10 W/kg in places, near the shear probe noise floor).
* Goal: test whether chi exceeds what shear driven turbulence with a flux coefficient of 0.2 can explain, and if so, estimate salt finger heat and salt diffusivities with defensible uncertainty.
* Initial shear processing used an FFT length of 4 s and a dissipation length of 16 s. Treat these as starting values, not fixed choices.

## Processing toolchain

* Processing is in Python using the `microstructure-tpw` package, which is largely driven through command line tools.
* Before running any of its commands, check the installed version and read each tool's `--help` output rather than assuming argument names or defaults.
* Every CLI invocation used in the workflow must live in a version controlled driver script (shell or Python) that reads its arguments from the config file. Never rely on commands typed interactively in a terminal; if a command was run by hand to test something, add it to the driver script before its output is used.
* Record the `microstructure-tpw` version (and Python version) in the pinned environment and in the metadata of every output file.
* Where the package's defaults matter for results (spectral lengths, fitting choices, despiking, noise handling), set them explicitly in the config rather than inheriting defaults silently.

## Before running anything

* Inspect the raw files present and the folder layout before assuming anything about file names or formats.

## Reproducibility requirements (non negotiable)

* Raw .P files are immutable. Never modify, move, or overwrite them. All outputs go to separate derived directories.
* Every processing parameter lives in a single version controlled config file (YAML or equivalent). No parameter values hard coded in scripts.
* Pin the software environment (environment.yml / requirements.txt with versions, or the MATLAB and ODAS toolbox versions recorded in the config).
* Each step is its own script that reads the previous step's saved output and writes its own, so any step can be rerun independently.
* One command reruns the full chain from raw files to final figures.
* Every output file records the config hash (or git commit) and software versions that produced it.
* Log the number of segments excluded at each QC step.
* Use git. Commit the config alongside results for every reported run.

## Repository and data layout

This repository holds code, config, environment files, documentation, and this analysis's outputs. Input data (archives, Sealog, cal sheets) live outside the repository; the config file gives their paths. GitHub rejects files over 100 MB, and instrument data (.p, NetCDF) never go in git.

```
config/       # config.example.yaml (committed); config.yaml (local copy with real paths)
src/          # run_pipeline.py, common.py, steps/<name>.py
scripts/      # utilities: checksum manifests, environment snapshots
manifests/    # committed checksum manifests of data directories
docs/         # shipboard_processing.md, decisions.md, products.md; private/ (gitignored)
outputs/      # <run.name>/<step>/ results and figures (bulky files gitignored)
```

Everything this analysis produces (derived data, figures, reports, run records) is written inside this repository under `outputs/<run.name>/` (`paths.output_root`). `.gitignore` decides what is committed: figures, cast tables, reports and step metadata are tracked, while patched .p copies, NetCDF, perturb working trees and full command transcripts stay local.

Keep this analysis separate from the earlier work. Never write into the data directories: not the archives, and not the shipboard-era scripts and figures in `SPICE_turbulence/code/`. Those earlier figures came from the shipboard processing and are not inputs to, or outputs of, this pipeline. Read-only inputs (raw files, Sealog export, cal sheets) are the only things read from the data area.

Existing pieces:

* `src/run_pipeline.py` is the single entry point. It loads the config, refuses to run while any value is `TODO`, verifies the archive manifests, writes `run_metadata.json` (config hash, git commit, package versions), and dispatches steps in order. Each step is `src/steps/<name>.py` with `run(ctx)`, and can also run on its own: `python src/steps/<name>.py --config config/config.yaml`. Steps without a module raise `NotImplementedError`.
* `src/common.py` holds shared helpers: provenance, `run_cmd` (every CLI call is appended with its output to the step's `commands.log`), parsing of `rsi-tpw config` output, and per-file patch edits from the config.
* Implemented steps:
  * `cast_log`: cast table, Sealog matching and ship track.
  * `patch`: per-cast `rsi-tpw patch-config`, with every output verified.
  * `convert`: one `perturb run` per instrument. perturb's stage subcommands each run the whole pipeline, so epsilon and chi are computed here, and the `epsilon_shear` and `thermistor` steps post-process perturb's output.
* `scripts/make_manifest.py` writes and verifies SHA-256 manifests (standard library only; refuses to overwrite an existing manifest).
* `scripts/record_environment.py` snapshots Python and package versions to JSON.
* `config/config.example.yaml` lists every parameter; values marked `TODO` must be filled from `docs/shipboard_processing.md`.

## Cruise event log (read only)

`SPICE_turbulence/sealog/FKt260806_sealog_export.csv` is the ship's Sealog export: VMP deployment notes, shear probe and thermistor serial numbers and swaps, operating problems, and 5 minute ship position snapshots (ASNAP). It has a committed manifest (`manifests/sealog.sha256.csv`), and the config gives its path. Treat its times and file names as notes, not ground truth. Match events to casts by the .p header start time; known errors are listed in `docs/shipboard_processing.md`.

## Archived shipboard processing (read only)

The first round of processing, done at sea, lives in three directories per instrument outside this repository (`vmp250_*` for the VMP250, `vmp6000_*` for the VMP5500):

* `*_raw`: original .p/.P files. These are the true pipeline input.
* `*_patched`: files after a patch step done at sea.
* `*_processed`: shipboard processing outputs.

The Rockland cal sheets (`SPICE_turbulence/SpiceProbeCalSheets`) are also read-only inputs.

Rules:

* Never modify, move, rename, or delete anything in these directories. Treat all of them as an archive.
* Each has a committed checksum manifest in `manifests/`. Verify against it before using the data.
* What each patch step changed, and why, must be documented in `docs/shipboard_processing.md`. In this pipeline, patching is a scripted step that regenerates the patched files from the raw files, per instrument and per cast range (`instruments.<name>.patch` in the config), so the chain starts from truly raw data.
* `docs/shipboard_processing.md` is the record of what was run at sea (commands recovered from shell history, package versions, parameters, problem casts). Read it before writing pipeline code.

## First milestone: baseline run on the latest package version

Exact reproduction with the shipboard version (microstructure-tpw 0.3.1, commit `81102fc`) is waived (see `docs/decisions.md`, 2026-10-12). The pipeline uses the latest microstructure-tpw, pinned to an exact git commit in `requirements.txt`.

* The baseline is the first full run from the raw files of both instruments (including the scripted patch step) on the pinned version, using the shipboard parameters recorded in `docs/shipboard_processing.md`. Set every shipboard parameter explicitly in the config, and set any option added since 0.3.1 explicitly as well.
* Compare the baseline outputs against `vmp250_processed` (generation `_01`) and `vmp6000_processed` as a sanity check, not a pass/fail test. Differences mix package changes with pipeline changes and cannot be attributed to either alone. Record the comparison in `docs/decisions.md`.
* If epsilon or chi move a lot, read the microstructure-tpw changelog between 0.3.1 and the pinned commit before assuming the pipeline is wrong.
* The regenerated patched files cannot match `vmp250_patched` byte for byte (the patch header embeds a timestamp and source path). Compare them on the non-comment config lines and the data records.
* Every later change (noise floor tests, Kraichnan epsilon, the chi comparison, sensitivity runs) is reported as a difference from the baseline.
* Upgrading the pinned commit later starts a new baseline. Record why in `docs/decisions.md` and rerun.

## Documentation habits

* Every methods choice and its reason goes in `docs/decisions.md`, dated, newest at the bottom.
* When a run produces results worth keeping, commit the config used and note the commit in `docs/decisions.md`.

## Workflow (order of operations)

0. **Cast log and patch.** Build a cast table from the Sealog export and the .p headers: file, start time, position, probe serials, station, operating notes, and exclusion or tow-yo flags. Build a ship track from the ASNAP snapshots. Then patch each instrument's raw files per cast range from the config (`instruments.<name>.patch.ranges`), not one spec for all files. For the VMP250 that is the shear probe calibration; `data_0112.p` was recorded with sh2 = M3463, before the swap to M2662. For the VMP5500 it is the 11 dbar pressure offset (coef0) and the T2 serial after the 2026-08-22 swap; its shear calibrations are already correct in the raw files. Every probe serial in the cast table must match the serial written into that file's config.
1. **Convert and log.** Run `perturb run` (microstructure-tpw) per instrument on the patched files, with a perturb config generated from the config's `perturb` block. This produces profiles, shear epsilon, FP07 chi and epsilon_T, CTD, and binned and combined files in one pass. Supply positions from the ship track (the shipboard run had none). Record the package version, probe serial numbers, and calibration coefficients.
2. **Select clean segments.** Keep steady fall speed portions only; drop launch acceleration and bottom approach. Despike shear; flag vibration contamination using accelerometers. Analyze tow-yo profiles (`data_0134.p`) separately from free-fall casts, and do not pool them at the process station without first showing they agree. Check casts with logged operating problems (line under the hull, sargassum on the line, twisted rod, poor line angle; see the cast table) before using them.
3. **Background hydrography.** TEOS-10 (gsw): SA, CT, alpha, beta, N2, T_z, S_z, density ratio R_rho = alpha T_z / (beta S_z), Turner angle. The smoothing scale for background gradients is a key sensitivity parameter (see below), not a fixed choice.
4. **Epsilon from shear.** Spectra with Goodman coherent noise removal; integrate to the Kolmogorov cutoff or fit a Nasmyth type spectrum. QC with probe agreement and figure of merit, plus an explicit noise floor test that does not rely on the figure of merit alone.
5. **Chi (and epsilon) from FP07.** Calibrate FP07 against CTD temperature; correct for the fall speed dependent thermistor response; fit Kraichnan (or Batchelor) spectra by maximum likelihood (Ruddick et al., 2000) to obtain chi and an independent epsilon. Where shear epsilon is at or near the noise floor, the thermistor derived epsilon is the candidate replacement, but note it assumes a turbulent spectral shape that may not hold for finger scale variance. Carry both epsilon estimates through. Inspect a sample of spectra visually. Consider a shorter dissipation length in staircase depth ranges to resolve interfaces.
6. **Classify regimes.** By Turner angle (45 to 90 deg finger favorable, strongest at 72 to 90 deg) and by staircase structure: label segments as interface or layer. Do not pool interfaces and layers, since the sign and character of the buoyancy flux may differ between them. Compute buoyancy Reynolds number and, where available, a finescale Richardson number.
7. **Test for double diffusion using a ratio of averages.**
   * Do NOT compute the dissipation ratio N2 chi / (2 epsilon T_z^2) segment by segment. T_z crosses zero in mixed layers and density compensated intrusions, which makes the per segment ratio blow up for mathematical rather than physical reasons and biases it high.
   * Instead compute, per segment, chi_expected = 2 K_rho T_z^2 with K_rho = 0.2 epsilon / N2 (Osborn, 1980). Average chi_observed and chi_expected separately over several profiles within each regime and depth bin, then compare the ratio of averages. This approach is described in Fernández-Castro et al. (2024), doi:10.1029/2023JC020817.
   * Compare that ratio against the shear turbulence expectation (1) and the finger model prediction, which is roughly Gamma_d_finger / 0.2 with Gamma_d_finger = [(R_rho - 1) / R_rho] * [gamma / (1 - gamma)] (St. Laurent and Schmitt, 1999), plotted against R_rho bins.
   * N2 also appears in a denominator and is small in staircase layers; check that conclusions hold when the weakest stratification is excluded.
   * Terminology: the St. Laurent and Schmitt quantity is a diagnostic ("dissipation ratio"), not a true mixing efficiency. It assumes K_T = K_rho a priori. In double diffusive convection the true flux coefficient is negative (potential energy converts to kinetic energy). A value above 0.2 means "not explainable by classic shear driven turbulence", which is the defensible claim. See also doi:10.1029/JC094iC02p02137 (Section 3) on negative flux coefficients.
8. **Diffusivities from bin averages only.** K_T = <chi> / (2 <T_z^2>) (Osborn and Cox, 1972); K_S = R_rho K_T / gamma; independent check K_S = epsilon (R_rho - 1) / [N2 (1 - gamma)]. Compute from bin averaged quantities, never segment by segment, since T_z and S_z can approach zero. Do not apply K_rho = 0.2 epsilon / N2 to finger dominated segments (the density flux is upgradient there).
   * Caveat: Osborn and Cox assumes local vertical production balances dissipation. Lateral finescale gradients could also produce chi. This should be stated, and checked if the data allow.
9. **Flux ratio gamma.** Poorly constrained (roughly 0.5 to 0.7 from lab and DNS work, possibly R_rho dependent). Treat as a sensitivity parameter.
10. **Averaging and uncertainty.** Epsilon and chi are roughly lognormal and intermittent (individual profiles at one station can disagree); average arithmetically over profiles and use bootstrap confidence intervals resampled over profiles.
11. **Export.** Write the products in `docs/products.md` (cast table, segments, binned profiles, diffusivities) per instrument, with provenance and flags. This is the last step and the only output meant for use outside this repository.

## Sensitivity parameters (all in config, each varied in its own run)

* FFT length and dissipation length (start: 4 s and 16 s)
* Background gradient smoothing scale for T_z, S_z, N2
* Shear noise floor threshold
* Epsilon source (shear vs thermistor Kraichnan fit)
* Number of profiles per average and depth bin size
* Flux ratio gamma
* Turner angle and interface/layer classification thresholds

## Key references

* Osborn, T. R. (1980). Estimates of the local rate of vertical diffusion from dissipation measurements. J. Phys. Oceanogr.
* Osborn, T. R., and Cox, C. S. (1972). Oceanic fine structure. Geophys. Fluid Dyn.
* St. Laurent, L., and Schmitt, R. W. (1999). The contribution of salt fingers to vertical mixing in the North Atlantic Tracer Release Experiment. J. Phys. Oceanogr.
* Ruddick, B., Anis, A., and Thompson, K. (2000). Maximum likelihood spectral fitting: the Batchelor spectrum. J. Atmos. Oceanic Technol.
* Winters, K. B., et al. (1995). Available potential energy and mixing in density stratified fluids. J. Fluid Mech.
* Fernández-Castro, B., et al. (2024). doi:10.1029/2023JC020817
* doi:10.1029/JC094iC02p02137 (negative flux coefficient discussion, Section 3)
* Gregg, M. C., et al. (2018). Mixing efficiency in the ocean. Annu. Rev. Mar. Sci.

Verify all citation details against the papers before use in a manuscript.
