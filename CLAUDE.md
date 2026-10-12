# Salt finger diagnostics from VMP microstructure

This directory holds the processing workflow for estimating double diffusive (salt finger) contributions to mixing from Rockland VMP microstructure data (shear probes, FP07 thermistors, CTD). Read this file fully before writing or running any code.

## Context

* Data come from a 2026 R/V Falkor (too) cruise: VMP250 and VMP6000 casts (plus at least one VMP5500 cast to >1000 m), including a 48 hour process station with repeated casts (15 VMP250, 3 VMP6000) in a region with thermohaline staircases.
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

This repository holds code, config, environment files, and documentation only. Data live outside the repository; the config file gives their paths. GitHub rejects files over 100 MB, and data never go in git.

```
config/       # config.example.yaml (committed); config.yaml (local copy with real paths)
src/          # pipeline driver and one module per step
scripts/      # utilities: checksum manifests, environment snapshots
manifests/    # committed checksum manifests of data directories
docs/         # shipboard_processing.md, decisions.md
```

Outputs (derived data, figures, run logs) are written to a data location set in the config, not into the repository.

Existing pieces:

* `src/run_pipeline.py` is the single entry point. It loads the config, refuses to run while any value is `TODO`, verifies the archive manifests, writes `run_metadata.json` (config hash, git commit, package versions), and dispatches steps in order. Each step is a stub to be replaced by its own module in `src/`.
* `scripts/make_manifest.py` writes and verifies SHA-256 manifests (standard library only; refuses to overwrite an existing manifest).
* `scripts/record_environment.py` snapshots Python and package versions to JSON.
* `config/config.example.yaml` lists every parameter; values marked `TODO` must be filled from `docs/shipboard_processing.md`.

## Archived shipboard processing (read only)

The first round of processing, done at sea, lives in three directories outside this repository:

* `vmp250_raw`: original .P files. These are the true pipeline input.
* `vmp250_patched`: .P files after a patch step done at sea.
* `vmp250_processed`: shipboard processing outputs.

Rules:

* Never modify, move, rename, or delete anything in these directories. Treat all three as an archive.
* Each has a committed checksum manifest in `manifests/`. Verify against it before using the data.
* What the patch step changed, and why, must be documented in `docs/shipboard_processing.md`. In this pipeline, patching is a scripted step that regenerates the patched files from `vmp250_raw`, so the chain starts from truly raw data.
* `docs/shipboard_processing.md` is the record of what was run at sea (commands recovered from shell history, package versions, parameters, problem casts). Read it before writing pipeline code.

## First milestone: reproduce the shipboard results

Before any new analysis, the pipeline must regenerate `vmp250_patched` and `vmp250_processed` from `vmp250_raw` using the shipboard parameters, and the outputs must be compared numerically against the archive. Record the comparison in `docs/decisions.md`. If outputs differ, find out why before continuing. Once reproduction works, that run is the baseline, and every later change (noise floor tests, Kraichnan epsilon, the chi comparison, sensitivity runs) is reported as a difference from it.

## Documentation habits

* Every methods choice and its reason goes in `docs/decisions.md`, dated, newest at the bottom.
* When a run produces results worth keeping, commit the config used and note the commit in `docs/decisions.md`.

## Workflow (order of operations)

1. **Convert and log.** Convert .P files to physical units with the `microstructure-tpw` conversion tool, called from the driver script. Record the package version, probe serial numbers, and calibration coefficients.
2. **Select clean segments.** Keep steady fall speed portions only; drop launch acceleration and bottom approach. Despike shear; flag vibration contamination using accelerometers.
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
