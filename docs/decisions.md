# Methods decisions log

Dated record of methods choices and why they were made. Newest entries at the bottom. When a run's results are worth keeping, note the git commit and config used.

## 2026-10-12: Repository setup

* Processing moved to a dedicated repository, separate from the shipboard working directories. Shipboard directories (`vmp250_raw`, `vmp250_patched`, `vmp250_processed`) are archived read only with committed checksum manifests.
* Data stay outside git; the config gives their paths.
* First milestone is reproducing the shipboard outputs from raw with the shipboard parameters, before any new analysis.

## 2026-10-12: Test for double diffusion with a ratio of averages

* Decision: do not compute the dissipation ratio N2 chi / (2 epsilon T_z^2) per segment. Instead compute chi_expected = 2 (0.2 epsilon / N2) T_z^2 per segment, average chi_observed and chi_expected separately over several profiles, and compare the ratio of averages.
* Reason: T_z crosses zero in staircase mixed layers and density compensated intrusions, so the per segment ratio becomes large for mathematical rather than physical reasons. Moving T_z^2 to the numerator before averaging removes this. Approach follows Fernández-Castro et al. (2024), doi:10.1029/2023JC020817.
* Related: K_T and K_S are computed from bin averaged quantities only.

## 2026-10-12: Terminology for the dissipation ratio

* Decision: call N2 chi / (2 epsilon T_z^2) the "dissipation ratio", not a mixing efficiency.
* Reason: it assumes K_T = K_rho a priori. In double diffusive convection the true flux coefficient is negative. A value above 0.2 means the observations are not explainable by shear driven turbulence with Gamma = 0.2, which is the defensible claim.

## 2026-10-12: Epsilon near the noise floor

* Decision: add an explicit shear noise floor test independent of the figure of merit, and carry thermistor (Kraichnan fit) epsilon alongside shear epsilon.
* Reason: shear epsilon is order 1e-10 W/kg in parts of the profiles, near the noise floor, and the figure of merit may not flag it. Thermistor epsilon assumes a turbulent spectral shape that may not hold at finger scales, so neither source is assumed correct; results are reported for both.

## 2026-10-12: Interfaces and layers analyzed separately

* Decision: classify segments as staircase interface or layer and do not pool them.
* Reason: the buoyancy flux may be upgradient at interfaces and down gradient in layers. With a 16 s dissipation length, estimates may span both, so a shorter dissipation length in staircase depth ranges will be tested.

## 2026-10-12: Open caveat on Osborn and Cox

* Osborn and Cox assumes local vertical production of thermal variance balances dissipation. Lateral finescale gradients could also produce chi. To be stated in any results and checked if the data allow.

## 2026-10-12: Use the latest microstructure-tpw; exact shipboard reproduction waived

* Shipboard version (recorded in `docs/shipboard_processing.md`): microstructure-tpw 0.3.1, git commit `81102fc242c18edf3acfdee37c0f40150e8ec8c1`, Python 3.14.6, perturb engine fingerprint `ce19d219eac8822274e72622fbf58649c801260c638afc67d43a405764f73866`. Every patched .p header (2026-08-18 to 2026-09-30) and both output generations in `vmp250_processed` were produced with it.
* Decision: the pipeline uses the latest microstructure-tpw, installed from `git+https://github.com/mousebrains/turbulence.git` and pinned in `requirements.txt` to commit `ebec847c157051d6835ebf2d8ac9553166c01880` (reports version 0.4.0; Python 3.12.15, conda env `spice_microstructure`). The pin is a commit, not `0.4.0`, because the version string does not identify a unique build. 58 commits separate the two versions.
* Exact reproduction with 0.3.1 was skipped on purpose. This supersedes the "First milestone" in the 2026-10-12 repository setup entry above. The new baseline is the first full run from `vmp250_raw` on the pinned version with the shipboard parameters.
* Consequence: any difference between the baseline and `vmp250_processed` mixes package changes (0.3.1 to `ebec847`) with changes in this pipeline, and cannot be attributed to either alone. The archive comparison is therefore a sanity check, not a pass/fail test. If epsilon or chi move a lot, check the package changelog between the two versions before assuming the pipeline is wrong.
* Checks on the new version (2026-10-12):
  * `--help` for `rsi-tpw` (top level, `patch-config`, `patch-template`, `config`, `info`, `nc`, `prof`, `eps`, `chi`) and `perturb` (top level, `run`, `init`, `trim`, `profiles`, `diss`, `chi`, `ctd`, `bin`, `combo`): argument names and defaults unchanged; differences are help formatting only.
  * `perturb init` templates: no existing default changed. New keys: `bottom.{method, height, fallrate_fraction, fallrate_smooth_s, proximity_bins}`, `chi.mixing_use_qc_fallback`, `epsilon.{anchor, spectral_qc, FM_max, var_resolved_min, pair_policy, pair_limit, bbl_diss_sec, bbl_extent_sec, bbl_overlap_sec}`, `fp07.{min_corr, reference_interval}`, `hotel.{max_gap, extrapolate}`. Set these explicitly in the config. Use values that mimic 0.3.1 behavior where the option allows (for example `epsilon.spectral_qc: false`, `epsilon.pair_policy: keep_both`). `epsilon.anchor` and `fp07.min_corr` have no "off" setting and may shift window positions or FP07 calibration.
  * Changelog entries likely to move results: FP07 calibration fixes (`ln(R_T/R_0)` defaults, recorded tau multipliers), chi stage fixes, and the new epsilon spectral QC and probe-pair options.

## 2026-10-12: Sealog export, probe cal sheets, and per-cast patching

* New read-only inputs, each with a committed manifest and a config path: the Sealog export (`SPICE_turbulence/sealog/FKt260806_sealog_export.csv`, moved there from the repository root; an identical copy is in `SPICE_ctd/`) and the Rockland cal sheets (`SPICE_turbulence/SpiceProbeCalSheets`).
* "VMP6000" and "VMP5500" are the same instrument (VMP-5500 SN 010). CLAUDE.md and the shipboard record are updated to match.
* Decision: patch shear probe calibrations per cast range from a probe history in the config (`patch.probes`), not one spec for all files. Reason: the Sealog shows `data_0112.p` was recorded with sh2 = M3463 (sens 0.1079), but the shipboard patch applied M2662 (0.1134) to every file. The calibration error alone is about 9% in sh2 epsilon. It does not explain the cast's 0.09 to 1.5 probe ratios, so `data_0112.p` (test casts) is a candidate for exclusion via `cast_log.exclude`. Decide that after inspecting it.
* Decision: add a `cast_log` step before `patch`. It builds the cast table and the ship track and matches Sealog events to files by .p header start time, because several logged file names and times are wrong.
* Decision: supply positions from the Sealog ASNAP ship track (5 min cadence, no gaps over 15 min). The shipboard run had none.
* Decision: treat `data_0134.p` (tow-yo lines, ship under way) separately from free-fall casts. It holds 8 of the 15 process-station VMP250 profiles, so process-station results must be shown with and without it.
* Caveat: sh2 probe M2662 was last calibrated 2023-04-12. A sensitivity drift of a few percent gives twice that in sh2 epsilon. Keep this in mind when reading sh1/sh2 disagreement, and consider it in the epsilon uncertainty.

## 2026-10-12: Scope is all cruise VMP data; products are the interface

* Decision: this repository is the main processing workflow for all FKt260806 VMP microstructure data, both instruments (VMP-250IR SN 537 and VMP-5500 SN 010). It ends in exported products (`docs/products.md`) that other analyses use; the salt finger diagnostics are one part of it.
* Consequences: the config is organized by instrument (`instruments.vmp250`, `instruments.vmp5500`), each with its archive paths, manifests, process-station files, exclusions, flags, and patch ranges. A final `export` step writes versioned products with provenance. Diffusivities are exported only as bin averages; the segment product carries epsilon, chi and gradients for users who need their own averages.
* VMP5500 archive (`vmp6000_*`) manifested and its shipboard patch checked against the Sealog probe history and the cal sheets (details in `docs/shipboard_processing.md`). Shear serials and sensitivities are correct in the raw files. The shipboard patch fixed an 11 dbar pressure offset (checked against on-deck pressure; about 1 dbar of drift remains over the cruise). The T2 serial was never updated after the 2026-08-22 swap (metadata only), so the pipeline patch corrects it.
* VMP5500 exclusions and flags: SPC_003 excluded (bench test); T2 excluded on SPC_040 (flat-lined); sh1 excluded on SPC_060 and SPC_061 (low response); SPC_004 to SPC_015 flagged for ballast-tuning noise and differing fall speeds; SPC_038 flagged as short. Segment fall-speed limits may need per-instrument values.

## 2026-10-12: Config filled for the baseline

* All perturb options are now explicit in a `perturb` block. Checked field by field against the shipboard `.params_sha256_*` files: every shipboard value matches for both instruments. The VMP5500 overrides use its Sea-Bird CT (`SBT1`, `SBC1`) in place of the VMP250's JAC CT. Options added after 0.3.1 are set to 0.3.1 behaviour (`epsilon.spectral_qc: false`, `pair_policy: keep_both`, `chi.mixing_use_qc_fallback: false`); `epsilon.anchor: top` and `fp07.min_corr: 0.5` have no off setting. `diss_sec` 16 s and `overlap_sec` 8 s are written out (shipboard `null` resolves to the same values).
* Correction: the template said `thermistor.fit_method: mle`, but the shipboard run used `iterative`. The baseline uses `iterative`; MLE (Ruddick et al. 2000) is the first planned change after the baseline, as is the explicit shear noise floor test (`shear_qc.noise_floor_w_kg`, null in the baseline).
* Staircase interface/layer labelling: two published detectors run side by side and are compared, van der Boog et al. (2021, doi:10.5194/essd-13-43-2021) and Rollo et al. (2022, doi:10.5194/gi-11-359-2022). There is also a slot for labels from an external ML classifier (intern project; `regimes.staircase.ml`). van der Boog values are from the paper text. Rollo values are as printed, with garbled units, and are flagged `verified_against_code: false` until checked against the Zenodo code (doi:10.5281/zenodo.5541659). van der Boog's 200 dbar background window and 100 dbar end trims do not fit VMP250 casts (about 180 to 270 m). Use the VMP5500 profiles or a co-located deep background there.
* Averaging: by station group, with at least 3 profiles per bin. The depth bin is 25 m in the baseline, with a `bin10m` sensitivity run to compare against. The weakest-stratification check repeats the averages with the lowest N2 decile removed.
* Products: creator Joe Gradone (joe@gradone.com), data license CC-BY-4.0 (code MIT), 1 m binned profiles to match the shipboard binning.

## 2026-10-12: Rollo classifier checked against its code and pinned

* Rollo's classifier (`thermohalinesteps`, github.com/callumrollo/thermohaline-steps, GPL-3.0) is pinned in `requirements.txt` at commit `976a4febdf85192aab1d247f7fc32abd3aeab83f`. Config keys now match the arguments of `classify_staircase`.
* Checked in the code: `ml_grad` is in kg m-3 dbar-1, `ml_density_difference` in kg m-3, and `av_window` and `interface_max_height` in dbar. The defaults (0.0005, 0.005, 200, 30, `layer_height_ratio` 1) equal the van der Boog et al. (2021) values. The paper's 0.001 and 0.01 were settings for its glider data, and "kg m-4" was a typo. The input must be evenly spaced in pressure.
* As a result, rollo2022 with default settings and vdb2021 differ only in implementation details (temperature-only flagging, flexible grid), so a comparison at defaults mostly tests the implementations. Comparing at settings tuned for this dataset is more informative; record any tuning here.

## 2026-10-12: First steps implemented (cast_log, patch, convert)

* Step modules live in `src/steps/` with shared helpers in `src/common.py`. Each step writes its own directory under `<output_root>/<run.name>/`, with a `commands.log` holding every CLI call and its output and a `step_metadata.json` holding provenance.
* `convert` runs `perturb run` once per instrument. perturb's `profiles`, `diss` and `chi` subcommands each call the full pipeline (checked in `odas_tpw/perturb/cli.py`), so there is no way to run conversion, epsilon and chi as separate package stages. The `epsilon_shear` and `thermistor` steps will therefore post-process perturb's outputs (noise floor test, MLE refits) rather than recompute them.
* `cast_log` matches Sealog events to files by time, using the .p start minus 15 min to the .p end plus 15 min. The config's probe history agrees with every Sealog probe-serial entry for both instruments (0 mismatches). Ship track gaps longer than `gps_max_time_diff_s` are reported, and casts whose start is farther than that from a fix are flagged (`SPC_003`, `SPC_004`; a 4.4 h nav gap on 2026-08-10).
* `patch` verifies every output file: each edited field holds its configured value, the cast table's expected serials and sensitivities match, and the data records are byte identical to raw. Differences from the shipboard patched files are all intended. VMP250: thermistor serials now recorded, ISO cal dates, and M3463 on `data_0112.p` sh2. VMP5500: T2 = T3301 from SPC_041 on, and `SPC_003` (excluded bench test) is left unpatched.
* pandas 3 stores datetimes at microsecond resolution, so epoch seconds are computed by timedelta division, never `astype("int64") / 1e9`.

## 2026-10-12: Outputs live in the repository, separate from the earlier work

* All outputs of this analysis (derived data, figures, reports, run records) are written inside the repository under `outputs/<run.name>/`. `paths.output_root` is now relative to the repository root. `.gitignore` decides what is committed: figures, cast tables, reports and step metadata are tracked; patched .p copies, NetCDF, perturb working trees and `commands.log` transcripts stay local.
* Reason: keep this analysis self-contained and never mix it with the earlier shipboard-era work in `SPICE_turbulence/` (its `code/` scripts and `code/figures/`). The data area is only read from: raw archives, the Sealog export, and the cal sheets.
* The first partial run, which had been writing to `SPICE_turbulence/spice_microstructure_outputs/`, was stopped and that directory deleted; it was regenerable. The local shell-history copy moved to `docs/private/` (gitignored).

## 2026-10-12: compare_archive finding: VMP5500 FP07 left uncalibrated by the new version

* The first `compare_archive` run showed VMP250 epsilon and chi identical to the archive where 1 m bins align (median ratio 1.000). The only expected exception is `data_0112.p` e_2: observed ratio 1.107, versus 1.105 expected from the M3463 sensitivity correction.
* VMP5500 epsilon came out 5.7% low (5-95%: 0.93-0.97) on both probes. The cause was the viscosity reference temperature, 3.0 degC warmer than in the archive. The new `fp07.min_corr` gate (default 0.5, added after 0.3.1) rejected every VMP5500 profile ("no profile reached the lag correlation gate"), so the FP07s kept their nominal coefficients. The Rockland production reports say these probes are factory uncalibrated, and they read about +3 degC (T1) and +3.7 degC (T2) against the Sea-Bird SBT1. The archive's reference temperature matched SBT1 to 0.04 degC.
* Decision: set `fp07.min_corr: 0`, which disables the gate as in 0.3.1, for the baseline. Also set the VMP5500 `fp07.reference_interval` to 1/64 s (SBT1 is a native 64 Hz channel), which silences the "interval unknown" warning. Tested on SPC_033: T1 - SBT1 = -0.02 degC median (5-95%: -0.32 to +0.10). Setting the interval alone did not help, because the correlation is genuinely below 0.5 on these deep casts. Why the lag correlation is low on the VMP5500 is worth understanding before relying on the FP07 calibration in later runs.
* This corrects the earlier note that `fp07.min_corr` has no off switch.
* Also found: only about 65% of 1 m bins hold a value in both runs, with equal counts new-only and archive-only. This is consistent with dissipation windows shifted by the new `epsilon.anchor`; values agree where windows align. Ratio-versus-depth plots therefore use 10 m bands.
