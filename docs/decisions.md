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

## 2026-10-12: Segment QC (step 2) flags; applied in the `segqc` run, not the baseline

* The `segments` step flags every 16 s dissipation window. Epsilon and chi share one window grid, checked on all 177 profiles. Window i covers fast samples [i x 4096, i x 4096 + 8192), checked against perturb's P_mean and speed. The flags are computed in every run. The baseline does not apply them (`segments.enabled: false`), because the shipboard run had no segment QC. Applying them is the `segqc` run, reported as a difference from the baseline.
* Thresholds come from the baseline data and are all sensitivity parameters:
  * `drop_top_m: 10`. Epsilon is 1e-5 to 1e-4 at 5-10 m, speed is still accelerating there, and VMP5500 vibration is about 10x its deep value.
  * `drop_bottom_m: 5`.
  * Speed between 0.2 and 1.5 m/s.
  * Within-window speed std/mean <= 0.05. This is 0.12-0.16 in the top 10 m and has a 99th percentile of about 0.05 below 20 m on both instruments.
  * Accelerometer rms (1 Hz high-pass) <= 3x the profile median.
* A first version flagged deviation from terminal speed (|speed/terminal - 1| > 0.10). It mostly removed VMP250 windows at 20-50 m that fall steadily about 8% fast, which is not a data problem: epsilon accounts for speed and the flow is well above 0.2 m/s. The test was replaced by within-window variability, which measures acceleration. The speed ratio stays in the output as information.
* Result: 4.4% of VMP250 windows (266 of 6002) and 2.3% of VMP5500 windows (157 of 6749) are flagged. Counts by criterion, alone and in sequence, are in `segments_report.json`.
* Open: VMP250 epsilon decays from about 1e-5 at 10 m to background by about 30 m. Ship wake and real mixed-layer turbulence cannot be told apart here. This is above the staircase depths of interest, so `drop_top_m` stays 10 m as a sensitivity parameter.

## 2026-10-12: QC exploration (QC explorer page)

* `scripts/build_qc_explorer.py` builds `outputs/<run>/qc_explorer/qc_explorer.html`, which embeds all 12,751 dissipation windows and recomputes outputs for any combination of segment, spectral, noise-floor, probe and averaging choices. It is published as a private Claude artifact (https://claude.ai/artifact/LhyffJS7JfGYtVfzKbzd58). It does not change the pipeline.
* Findings from the baseline run:
  * **Stratification dominates.** perturb's window-scale N2 for the VMP5500 is about 4.5x too large and its dT/dz about 2.3x too small compared with TEOS-10 from the same CT/SA (SPC_033, 150-250 m). The VMP250 window values agree with TEOS-10. The shipboard archive has identical values, so the at-sea VMP5500 chi ratios inherit the error. VMP5500 TEOS-10 N2 is negative in 34-44% of windows at 150-250 m because its salinity is spiky (likely CT-C response mismatch). The process-station chi ratio changes by an order of magnitude with the stratification choice, far more than with any epsilon QC choice. Decision: the `hydrography` step computes N2, T_z and S_z from CT/SA (with salinity despiking or C/T alignment for the VMP5500), and no ratio is interpreted until it exists.
  * **Instruments agree on epsilon and chi** at 150-250 m at the process station: median epsilon 8.9e-10 and 8.0e-10 W/kg, chi 3.9e-8 and 3.7e-8 K2/s.
  * **Noise floors:** about 3e-10 (VMP250) and 3e-11 W/kg (VMP5500). VMP250 epsilon below 150 m is within about 2x of its floor, so treat it as near an upper bound. Excluding below-floor windows biases means high (VMP5500 +24%). If a floor is applied, values below it are set to the floor and flagged, never dropped.
  * **ATOMIX FM > 1.15** removes 41-77% of windows in every epsilon decade, including high epsilon. The threshold likely does not suit these spectra (4 s FFT, 16 s windows). It is not adopted until spectra are inspected (`epsilon.spectral_qc` stays false).
  * **Segment QC** changes the 150-600 m mean epsilon by under 3%; variance-resolved and probe-pair rules change means by under 1%.

## 2026-10-12: Hydrography step; VMP5500 salinity from the ship CTD T-S relation

* The `hydrography` step computes TEOS-10 CT, SA, N2, T_z, S_z (z positive up), alpha, beta, R_rho and Turner angle on a 1 m grid per profile and at every dissipation window centre. Gradients are linear fits over `gradient_smoothing_m` (baseline 10 m; sensitivity runs at 5 and 25 m). The Turner angle follows Ruddick (1983), atan2(aT_z + bS_z, aT_z - bS_z): fingers 45-90 deg, R_rho = -tan(Tu + 45 deg). perturb's window-scale N2 and dTdz are no longer used.
* Diagnosis of the VMP5500 salinity: its scatter at 1 m scale (0.06 g/kg, 16x the VMP250's) comes from the SBC1 conductivity (0.04-0.08 g/kg), not from temperature (0.008) or from C-T lag or response mismatch, which a grid search over lags and T filters could not reduce. The VMP250's JAC salinity is already aligned (best lag about 0).
* Validation reference: the ship CTD (SBE 911, `paths.ship_ctd`, manifested; 103 casts to 550 m). A cast lies within 15 km and 6 h of 37/38 VMP250 and 42/45 VMP5500 casts, including 10 at the process station.
* Methods compared against the ship CTD at 150-550 m: own salinity, median-despiked salinity, local T-S fit, and SA from the nearest ship CTD T-S relation evaluated at the profiler's CT.
  * VMP250 own salinity agrees with the ship CTD: N2 median ratio 0.99, 83% within 2x at 10 m, 97% at 25 m; R_rho 1.71 vs 1.71.
  * VMP5500 own salinity fails: N2 <= 0 in 35-47% of estimates (ship CTD 0-8%), and R_rho is wrong.
  * Ship-CTD T-S salinity fixes the VMP5500: N2 <= 0 in 7% at 10 m (ship 1%), N2 ratio 1.08, R_rho 1.67 vs 1.58. It is not circular: on the VMP250 it reproduces the instrument's own N2 (median ratio 1.00-1.02) and R_rho (1.71-1.76 vs 1.68-1.75).
* Decision: `salinity_source: own` for the VMP250 and `ship_ctd_ts` for the VMP5500. Below the ship CTD's 550 m reach the VMP5500 has no usable salinity; those windows carry `no_stratification` and are excluded from anything that needs N2.
* Result at the process station: R_rho about 1.5-2 and Turner angle about 70-80 deg from 150 to 550 m, strongly finger favourable.

## 2026-10-12: QC explorer revisited with hydrography stratification

* The explorer now takes stratification from the hydrography step at 5, 10 and 25 m fits. perturb's window values remain only as a comparison. It adds a Turner-angle regime filter and the St. Laurent and Schmitt finger prediction with adjustable gamma. Republished as version 2 of the same artifact.
* Process station, segment QC, 10 m fits, pooled ratio of averages over 150-550 m:
  * VMP5500: 1.5, down from 29 with perturb's N2.
  * VMP250: 3.5, down from 4.3; it covers only the top 270 m, from 15 profiles.
  * In 25 m bins below about 200 m the ratio is 1.3-10, bracketing the finger prediction of about 3-5 (gamma 0.65, R_rho 1.5-2). Above 200 m it is near 1.
  * Fit scale 5-25 m changes the pooled ratio by at most about 35%.
* With stratification fixed, the epsilon choice that moves the ratio most is the ATOMIX FM cut: the VMP250 ratio goes from 3.5 to 6.8 and the VMP5500's from 1.5 to 1.9, with about half the windows removed. Spectra must be inspected before any FM threshold is adopted; this is the next QC question. The noise-floor clamp and segment QC barely move the ratio.
* All of this is preliminary: interface/layer classification, epsilon spectral QC and bootstrap uncertainty are not done.

## 2026-10-12: VMP5500 conductivity: what the data show

* Compared with the ship CTD at the same CT (T-S comparison, insensitive to heave), 150-500 m, 44 profiles:
  * VMP5500 salinity reads +0.15 g/kg high (median). The per-profile offset ranges from +0.04 to +0.51 g/kg.
  * Its 1 m noise is 0.073 g/kg, about 30x the VMP250's 0.0025. 10% of its 1 m bins are more than 0.1 g/kg off their local median, against none for the VMP250.
  * The VMP250 offset is +0.006 g/kg.
* Both noise and offset grow through the cruise: noise about 0.02-0.05 and offset +0.04-0.1 in the first casts (SPC_004 to SPC_018), against 0.06-0.15 and +0.2-0.5 from about SPC_044 (2026-08-24) on. They are barely related to fall speed (r = 0.23).
* Calibration is ruled out as the cause. The setup.cfg coefficients for SBE4 C #4076 (cal 2026-02-19) and SBE3 T #5621 (cal 2026-03-25) match Sea-Bird's .cal files exactly.
* Interpretation: the conductivity measurement degraded during the deployment. Contamination, fouling, damage or poor flushing of the unpumped cell are all consistent. Fouling usually biases salinity fresh, so the salty offset is unusual, and the data cannot separate these causes. Temperature gradients from the SBE3 agree with the ship CTD (T_z ratio 0.999 at 25 m fits). The SBE3's absolute temperature could not be checked independently; it is also the FP07 calibration reference.
* Consequences: the VMP5500 salinity is not used (the hydrography step uses the ship CTD T-S relation). perturb's VMP5500 N2, which uses this conductivity, is not used either.
* Recommended: a post-cruise Sea-Bird calibration of SBE4 #4076, and a visual inspection of the cell, to confirm.

## 2026-10-13: Despiking VMP5500 conductivity does not help

* Tested on 42 VMP5500 casts against the ship CTD (150-550 m). Three treatments were applied to the 64 Hz SBC1 conductivity before computing salinity and the 1 m averages: Hampel filter (0.5 s window, 3 sigma and 2 sigma) and a 0.5 s running median.
* The raw 64 Hz conductivity is very spiky (excess kurtosis of the high-passed signal about 77), and the filters replace 13-18% of samples. The results do not change: 1 m salinity noise 0.0729 -> 0.0727 g/kg, offset +0.153 g/kg, N2 <= 0 in 44.6% (ship CTD 1.5%), N2 ratio to ship 3.05.
* Reason: each 1 m bin already averages about 80 samples, so sample-level spikes average out. The problem lies at metre and longer scales (noise about 0.07 g/kg plus the systematic offset), which point despiking cannot reach. This points to the cell's response in the water rather than electronic glitches.
* Decision: no conductivity despiking. A Lueck and Picklo (1990) thermal-mass correction is the only untested candidate for the metre-scale spikes at interfaces; it would not address the offset. VMP5500 salinity stays sourced from the ship CTD T-S relation.

## 2026-10-13: Thermal-mass correction of VMP5500 conductivity

* Tested the Lueck and Picklo (1990) correction (Sea-Bird celltm recursion, applied at 64 Hz to the aligned SBC1) on 42 casts against the ship CTD, 150-550 m. Parameters: Sea-Bird default (alpha 0.03, tau 7 s); Morison et al. (1994) flow-dependent values for V = 0.81 m/s (alpha 0.046, tau 10.2 s); a small grid; and a wrong-sign control.
* Noise is unchanged: 1 m noise 0.073 g/kg in every case, and N2 <= 0 goes from 44.6% to 43.7-44.4% (ship CTD 1.5%).
* The offset falls by 10-20% (+0.153 to +0.125-0.145 g/kg), and the wrong-sign control raises it (+0.166). Thermal mass is a real but minor part of the bias.
* The noise is about 3x larger at sharp temperature gradients (0.111 vs 0.037 g/kg) and the VMP250 does not show it, so it is a sensor mismatch rather than real structure. Fixed C-T lag, T response matching, despiking and thermal-mass correction all fail to remove it. This is consistent with variable flushing or partial blockage of the unpumped SBE4 cell, which no fixed correction can undo.
* Decision: no thermal-mass correction is applied. Correcting a channel that is not used would add complexity for no benefit. VMP5500 salinity stays sourced from the ship CTD T-S relation.

## 2026-10-13: Sensor depth offsets (VMP5500 CT 1.57 m above the pressure sensor)

* Information from the user: on the VMP5500 the SBE3/SBE4 CT sensors sit 1.57 m above the pressure sensor. Every CT sample was therefore taken 1.57 m shallower than the pressure it is paired with.
* Check from the data: SBT1 records the same temperature structure as the nose FP07s about 3.4 s later at 0.81 m/s, a median separation of 2.76 m (IQR 2.54-2.91 m, 44 casts, lagged correlation about 0.5). This is consistent with the stated 1.57 m if the FP07/shear probe tips are about 1.2 m below the pressure sensor. That offset is not yet confirmed.
* Effects: depth registration of CT-derived temperature, salinity and stratification (1.57 m is about 0.09 K in a 0.06 K/m thermocline, and matters for thin staircase interfaces and for pairing stratification with dissipation windows). The salinity conversion is not affected: the pressure term changes SP by under 0.001 g/kg. The T-S comparisons of the conductivity problem are depth independent and unaffected.
* Decision: add `instruments.<name>.sensor_offsets_m` (sensor depth minus pressure-sensor depth, positive deeper) with `ct` and `microstructure` entries. VMP5500 ct = -1.57. The microstructure offsets for both instruments and the VMP250 JAC CT offset are 0 until confirmed. The hydrography step places CT-derived values at the CT depth and evaluates window values at the probe depth. The diagnostic scripts use the CT depth. perturb itself has no sensor-offset option, so its products remain referenced to the pressure sensor.

## 2026-10-13: VMP5500 Sea-Bird response lag explains the salty offset; noise unexplained

* Geometry from the user: VMP5500 probe tips (shear, FP07) about 0.30 m below the pressure sensor; SBE3/SBE4 1.57 m above it. The FP07-to-CT separation is therefore 1.87 m. `sensor_offsets_m.microstructure` is set to 0.30, and the hydrography windows are re-evaluated (validation unchanged).
* The measured FP07-to-SBE3 delay (about 3.4 s, equivalent to 2.76 m) exceeds the geometric 2.3 s. The extra delay is sensor response: fitted against the geometrically delayed FP07, the SBE3 behaves as a first-order sensor with tau about 2 s (IQR 2-3 s) and no extra pure delay.
* The SBE4, fitted against the ideal conductivity (FP07 temperature at the CT sensor plus the ship CTD T-S relation), behaves as a first-order sensor with tau about 6 s (IQR 4-6 s) and 0.25 s delay (40 casts; SPC_042 and SPC_061 excluded as broken). The lagged model halves the misfit (0.29 -> 0.15 mS/cm) and removes the bias (+0.176 -> +0.006 mS/cm).
* A slow cell on a steady descent through decreasing conductivity reads high, which is the salty offset. With a response-matched temperature, the salinity offset falls from +0.153 to +0.024 g/kg. Its growth late in the cruise matches steeper gradients (rate of change of C 0.009 vs 0.024 mS/cm/s, bias 0.10 vs 0.27 mS/cm, the same lag; per-cast correlation 0.42).
* The metre-scale noise is not explained. Response-matched salinity still gives N2 <= 0 in 41% (10 m fits) and 29% (25 m fits), against 1.5% and 0.1% for the ship CTD. The extra spikes sit at staircase interfaces, where the cell overshoots sharp steps.
* Decision: VMP5500 salinity stays sourced from the ship CTD T-S relation. The response analysis is in `scripts/diagnose_vmp5500_conductivity.py` (figure 6 of the memo). Open question for the instrument experts: why the unpumped SBE3/SBE4 respond so slowly (2 and 6 s, against about 0.07 s pumped), and what causes the overshoot at steps.

## 2026-10-13: Removing the VMP5500 salinity spikes

* After the response-lag correction, the remaining salinity spikes sit at staircase interfaces where the SBE4 overshoots sharp steps. Two remedies were tested on 40 casts against the ship CTD, 150-550 m:
  * A learned linear response: a 12 s FIR filter from ideal to measured conductivity, at 8 Hz, ridge regularised, fitted leave-one-cast-out so no cast is corrected with its own comparison data.
  * A 5 m running median on the corrected 1 m salinity.
* Results:
  * The learned response does not help. Noise is unchanged at 0.069 g/kg, the offset grows to +0.092 g/kg, and N2 <= 0 reaches 46%. The spikes are not a consistent linear response, which is consistent with flushing of the unpumped cell that varies with the flow.
  * The running median removes the spikes visually (1 m scatter 0.069 -> 0.036 g/kg, partly by construction) but not the gradient problem. N2 <= 0 stays at 41% (10 m fits) and 30% (25 m fits), against 1.6% and 0.1% for the ship CTD, and R_rho stays near 1 against the ship's 1.67. A slower salinity wander over 5-20 m, not the spikes, is what corrupts N2.
* Decision: no spike treatment in the pipeline; VMP5500 gradients keep the ship CTD T-S salinity. A running median is acceptable for display only, labelled as such.

* 2026-10-13 follow-up: the display-only 5 m running median was tried in the cast stepper and dropped; it did not make the casts easier to judge. The stepper shows the unsmoothed lag-corrected salinity.

## 2026-10-13: VMP5500 salinity matches the Sea-Bird temperature to the cell, not the FP07

The response-corrected VMP5500 salinity previously used the nose FP07, moved 1.87 m to the CT sensor, as the "true" temperature. That made salinity depend on the FP07 calibration and the sensor geometry. Salinity now uses only the co-located Sea-Bird pair: SBE3 temperature delayed by 0.25 s and passed through a 6 s first-order lag (config `instruments.vmp5500.ct_match`), then `SP_from_C` with the SBE4 conductivity. Temperature (Θ) is the SBE3 itself.

Grid over the extra lag (0–10 s) and delay (0–1 s), 40 casts with a ship CTD match, 150–550 m, 1 m bins:

* Noise does not change with the matching filter (0.065–0.068 g/kg everywhere). The metre-scale scatter is not a T–C response mismatch. For the same reason, minimising noise cannot choose the filter.
* The median offset from the ship CTD T–S relation falls steadily with lag: +0.130 (no match), +0.057 (4 s), +0.020 (6 s, 0.25 s delay), −0.009 (8 s).
* A lead-lag using the FP07-fitted SBE3 τ ≈ 2 s and SBE4 τ ≈ 6 s left +0.063, so the SBE3's response relative to the cell is effectively faster than that 2 s fit.
* 6 s / 0.25 s are the SBE4 response-fit cruise medians. They give the same offset as the FP07 method (+0.022) without using FP07 data.

The constants are cruise-wide, not per cast; the per-cast fits used the FP07 as reference. The pipeline still uses ship CTD T–S salinity for VMP5500 gradients (unchanged).

## 2026-10-13: Source of the VMP5500 salinity noise; the cast's own T–S relation as a fix

Exploratory tests (session scratch scripts, not yet in the pipeline), 42 casts with a ship CTD match, 150–550 m:

* Temperature is not the problem. The 1 m high-pass noise is 0.006 °C for both the SBE3 and the FP07, below the ship CTD's 0.011.
* The salinity noise is in the conductivity. The residual from expected C (FP07 T plus ship T–S) is 0.077 mS/cm at 1 m. It is not coherent with fall speed, tilt or dT/dt.
* At 64 Hz in SPC_031 (280–322 m), the FP07 shows sharp steps and flat layers. Inside those layers, the SBE3 wanders by 0.02–0.04 °C and the conductivity (as a temperature equivalent) by 0.05–0.1 °C, with a 4–5 s rhythm, while fall speed is steady (0.82 ± 0.003 m/s). A sensor lag can only smooth, not add structure, so the CT pair, 1.9 m up the body, is sampling water stirred and carried by the vehicle, with irregular flushing of the unpumped cell.
* No response correction removes the noise:
  * a fixed lag (grid over 0–10 s lag and 0–1 s delay): noise unchanged at 0.066 g/kg;
  * a lag refitted in 10 s windows to minimise spiking: worse (0.081).
* The cast's own T–S relation does work. Fit SA against SBE3 CT from the 6 s matched salinity in 0.5 °C CT bins with a 3-bin running mean (about 1.5 °C), then evaluate it at FP07 CT. Compared with measured C plus SBE3 T:
  * 1 m noise 0.0019 g/kg (was 0.067);
  * offset from ship T–S +0.025 g/kg;
  * N2 <= 0 in 10 m fits 16% (was 39%);
  * median R_rho 1.69 (ship 1.59).
  * Narrower bins stay noisy: 0.1 °C bins give 0.020 g/kg, 0.25 °C bins 0.006 g/kg.
* The remaining 10 m inversions come from FP07 temperature inversions (13% of 10 m fits; VMP250 7% in its casts reaching 400 m), likely real intrusions.
* Caveat: with T–S derived salinity, S_z, R_rho and the Turner angle follow the T–S slope at about 1.5 °C resolution and are not independent measurements. The same is true of the current ship CTD T–S method. Compared with the ship CTD method, the cast's own T–S needs no ship match and also covers depths below 550 m.
* Status: proposed for the hydrography step (`salinity_source: own_ts`); not yet adopted.

## 2026-10-13: own_ts adopted for VMP5500 hydrography; temperature inversions flagged

`salinity_source: own_ts` is now in the hydrography step and set for the VMP5500 (config `hydrography.own_ts`: SBT1/SBC1 fit, FP07 T1, 0.5 °C bins, 3-bin smoothing; `instruments.vmp5500.ct_match` 0.25 s / 6 s). The CT grid is FP07 temperature at the probe tips' depth. The cast stepper now plots this grid. The response-corrected salinity helper in the diagnostics script is removed.

Baseline run, 150–550 m, compared with the matched ship CTD cast at 10 m smoothing:

* Salinity noise at 1 m: 0.002 g/kg (measured C 0.067).
* N2 <= 0: 17% (ship 1%; previous ship_ctd_ts at SBE3 CT 7%). N2 within a factor 2 of the ship: 56% (was 63%). R_rho 1.72 (ship 1.58).
* Where T_z > 0: N2 <= 0 is 6.8%, within factor 2 is 56–60%, and R_rho is 1.75 (ship 1.63–1.68).
* Why there are more inversions:
  * Temperature inversions in 10 m fits: FP07 T1 13.8% and T2 13.8% (the two agree), ship CTD 11.8%, SBE3 only 6.5%. The FP07 inversions are real, and the SBE3 smooths about half of them away.
  * The ship's N2 <= 0 is only 1.8%, so the inversions are mostly density-compensated intrusions, which a T–S relation cannot represent.
  * The previous method's 7% was low only because the SBE3 hid inversions.
* New window flag `ts_salinity_invalid` (T_z <= 0 with a T–S salinity source): 857 of 6749 VMP5500 windows. It is a flag, not an exclusion.
* Accuracy of the own T–S relation, as the median |own_ts − ship T–S| per cast, by CT band. Part of this is real spatial and temporal difference from the ship cast.

  | CT band | Median (g/kg) | Casts > 0.05 |
  |---|---|---|
  | < 10 °C | 0.027 | 25% |
  | 10–13 °C | 0.050 | 45% |
  | 13–16 °C | 0.062 | 52% |
  | > 16 °C | 0.133 | 95% |

  * It is worst in the main thermocline, where the cell's errors across steep gradients bias the bin medians (SPC_031: ~0.8 g/kg too fresh at 18–20 °C).
  * SPC_041 and SPC_045 (and partly SPC_044) have bad conductivity throughout (0.26–0.64 g/kg off).
* Open: a per-cast or per-band QC flag against the ship T–S, or a ship_ctd_ts fallback for bad casts. Not yet decided.

## 2026-10-13: Ship T–S fallback for own_ts

Config `hydrography.own_ts.ship_fallback`:

* For each 0.5 °C T–S bin, the cast's relation is compared with the matched ship cast's relation (same bins and smoothing).
* Bins differing by more than 0.15 g/kg take the ship value. The correction, not the whole relation, ramps over 3 bins, so untouched bins keep their own values.
* If the median difference over bins colder than 13 °C exceeds 0.15 g/kg, the whole profile uses the ship relation and is NaN beyond its temperature range.
* Outputs: `SA_from_ship` (grid and windows), `ts_bad_fraction`, `ts_ship_only`.

Threshold choice: |own − ship| per bin has 90th percentiles of 0.11 (< 10 °C), 0.24 (10–13 °C), 0.22 (13–16 °C) and 0.41 g/kg (> 16 °C). A 0.05 threshold sent 40 of 44 casts to the ship, because real cast-to-cast differences are that large. The first version re-smoothed the whole merged relation, which flattened T–S slopes everywhere (R_rho 1.87); fixed.

Result:

* Whole profiles on the ship relation: SPC_041, SPC_045, SPC_018_prof002 and SPC_049_prof002.
* Windows mostly on ship values: 594 of 6749, mainly the thermocline (> 16 °C).
* Stepper per cast, 150–500 m: median 1 m noise 0.001 g/kg, median offset +0.018 g/kg, 4 of 42 casts above 0.05.
* Against the ship, 150–550 m, T_z > 0:

  | Salinity from | Median R_rho (ship) | S_z ratio to ship |
  |---|---|---|
  | Own T–S bins | 1.80 (1.63) | 0.76 |
  | Ship bins | 1.66 (1.66) | 0.93 |

Remaining issue: the slope of the own T–S relation is noisy from cast to cast. In 9 casts with a VMP250 profile nearby, the 10.5–13 °C slope dSA/dCT was 0.12–0.29 (median 0.158) for the cast's own relation, against 0.14–0.17 (median 0.166) for the ship. The VMP250 median, 0.167, agrees with the ship. R_rho depends directly on this slope, so own-relation R_rho carries roughly ±30% per-cast scatter even where offsets pass the check.

## 2026-10-13: VMP5500 salinity uses its own CT wherever usable; ship T–S only for bad cells

User preference: use the VMP5500 CT data and avoid the ship T–S relation unless the VMP5500 data are not worth using. The per-bin ship replacement is removed.

* Bad-cell check, ship-free (`hydrography.own_ts.bad_cell_check`): each profile's T–S relation is compared with the median of all VMP5500 profiles over 5.5–8 °C.
  * Spread across the cruise there is small (median absolute deviation 0.009–0.024 g/kg).
  * SPC_041 (+0.26 g/kg) and SPC_045 (+0.18 g/kg) exceed the 0.1 threshold; the next largest is SPC_050 (+0.07).
  * Only these two use the matched ship cast's T–S, and they are NaN below its reach. The two 12 m second profiles (SPC_018_prof002, SPC_049_prof002) have no usable data and take the same path.
* Ship check, flag only: `SA_ship_diff` (grid and windows) and the window flag `ts_disagrees_with_ship` (> 0.15 g/kg; 438 of 6749 windows, mostly in the thermocline above about 150 m). Nothing is replaced.
* Tests that did not justify a change. All are scored as R_rho own/ship within ±30% at 10 m, T_z > 0, 150–550 m; the VMP250 baseline is 88%, interquartile range 0.92–1.06.

  | Variant | Within ±30% | Median own/ship |
  |---|---|---|
  | Current (0.5 °C bins × 3) | 54–55% | 1.03 |
  | 1.0 °C × 3 | 62% | 1.09 |
  | 1.0 °C × 5 | 62% | 1.12 |
  | Per-cast dT/dt (lag) regression | 55% | 1.02 |
  | dT/dt regression + 1.0 °C × 3 | 63% | 1.07 |

  * Wider smoothing reduces scatter only by biasing R_rho high.
  * Pooling neighbouring casts was not tried: casts are 20–30 km and about 6 h apart, so pooling would blend the spice variability under study.
* Accepted: VMP5500 R_rho from its own T–S is unbiased (median own/ship 1.01–1.04) but noisier per 10 m window (interquartile range 0.82–1.29). Use averaged R_rho, such as the 25 m and profile averages of the double-diffusion test, rather than single windows for classification.
* Parked here (user, 2026-10-13); next work is the microstructure processing.

## 2026-10-13: epsilon_shear step (baseline)

`src/steps/epsilon_shear.py` post-processes perturb's per-probe shear epsilon (config `shear_qc`). Dissipation and FFT lengths stay at the shipboard 16 s and 4 s for the baseline. An 8 s dissipation window is the planned sensitivity run before the regimes step, because 16 s windows (11–13 m) span the 5–8 m staircase steps.

* **Noise floor, independent of FM.**
  * Method: the noise spectrum is the median frequency spectrum of the quietest 2% of segment-QC-passed windows, per probe. For each window, floor = epsilon × ∫noise / ∫observed over 0 < k ≤ K_max at that window's speed.
  * It is an upper bound on the noise, since the quietest windows hold some signal.
  * Windows with epsilon < 2 × floor are flagged `at_floor` and kept. `epsilon_shear_bounded` = max(epsilon, floor) is the upper-bound value for the double-diffusion test.
  * Median floor below 150 dbar: 2.4e-10 W/kg (VMP250) and 2.3e-11 (VMP5500), consistent with the QC explorer's 3e-10 and 3e-11.
  * At floor below 150 dbar: 13% (VMP250, rising to 20–40% below 250 dbar) and 14% (VMP5500, rising to about 50% near 1000 dbar).
* **VMP5500 vibration comb.**
  * Narrow, evenly spaced peaks at 13–39 Hz (about 10–150 cpm) in about 65% of VMP5500 windows, at all depths and in all casts.
  * Not removed by the Goodman cleaning, but mostly above K_max at low epsilon (integration to about 8 Hz).
  * Replacing peaks with the local median lowers the integrated variance below K_max to 0.81–0.92 of the original, versus 0.85–0.92 on the VMP250, which has no comb. So it has a negligible effect on epsilon.
* **ATOMIX FM.** The spectra gallery (`figures/spectra_gallery_<instrument>.png`) shows that FM > 1.15 and FM > 1.5 spectra follow the Nasmyth curves below K_max about as well as FM < 1.15. On the VMP5500 a high FM mostly reflects the vibration comb entering the fit range. FM stays a flag (`apply: false`).
* **var_resolved < 0.5:** applied; removes 274 (VMP250) and 51 (VMP5500) probe estimates.
* **Probe pairs** (limit 2.77, policy `min`).
  * VMP250 probes agree: median log10(e1/e2) 0.01; 6% of windows disagree.
  * VMP5500: sh2 reads higher, median ratio about 1.5; 18% of windows disagree, 81% of them with sh2 higher.
  * Not calibration: the sh2/sh1 spectral ratio is 1.04–1.06 at 1–4 Hz, which carries most of the low-epsilon variance, and about 1.5 below 1 Hz and above 4 Hz.
  * It varies by cast from 0.3 to 2.2 with the same probes installed. It falls below 1 at SPC_059–061, before sh1 M3461 was replaced by M3456 at SPC_062.
  * So one probe is intermittently noisier, and the smaller estimate is kept on disagreement.
* **Segment QC** follows `segments.enabled` (false in the baseline).
* **Kept:** 5885 of 6002 VMP250 windows and 6728 of 6749 VMP5500 windows; the rest have no usable probe.
* **Outputs:** `outputs/baseline/epsilon_shear/` (window table, noise spectra, report, figures).

## 2026-10-13: Correction — high FM marks a systematic low-wavenumber bias in shear epsilon

`scripts/explain_fm.py` (figures `epsilon_shear/figures/fm_explained_<instrument>.png`) shows ln(observed/Nasmyth) along the fitted range for windows with epsilon 1e-10–1e-9 W/kg. This corrects the previous entry's statement that high-FM spectra fit Nasmyth about as well as low-FM spectra.

* **The misfit is the same shape in every FM bin.**
  * The lowest wavenumbers (k < ~0.15 K_max, about 0.3–1.5 cpm or f < ~1 Hz) are 3–5× above Nasmyth.
  * Across the middle of the range the observed spectrum sits below Nasmyth: by about 1.8× at FM < 1.15, about 2.5× at FM 1.15–1.5, and 3–5× at FM > 1.5.
  * On the VMP5500 the spectrum rises again toward K_max, where the vibration hump begins.
  * Per-window misfit is mostly bias (mean ln ratio −0.2 to −0.7 on the VMP250), not random scatter. FM measures how strong this shape is.
* **Interpretation:** low-frequency energy (vehicle motion or other non-turbulent shear below ~1 Hz; also where VMP5500 sh2 exceeds sh1 by about 1.6×) adds variance to the integral. The fitted Nasmyth is then too high, so epsilon is biased high.
* **Size of the bias:** refitting the stored spectra over 1 Hz to K_max (Nasmyth variance matched over the same range; every third profile, below 150 dbar, epsilon 1e-11–1e-8) gives median eps(refit)/eps(perturb):

  | FM bin | VMP250 | VMP5500 |
  |---|---|---|
  | < 1.15 | 0.73 | 0.78 |
  | 1.15–1.5 | 0.58 | 0.70 |
  | > 1.5 | 0.45 | 0.75 |

* **Consequence:** the QC explorer's FM cut raised the chi ratio (VMP250 3.5 → 6.8) because it removed the most biased windows. Correcting the bias with a low-wavenumber cutoff is preferable to discarding windows. Not yet adopted; it needs a decision and goes into the epsilon_shear step as a config option.

## 2026-10-13: Shear epsilon refit from 1 Hz (adopted); cutoff test

* **Method:** `shear_qc.refit` (enabled, f_min_hz 1.0). Per probe and window, epsilon is re-solved so the Nasmyth variance over f_min/speed ≤ k ≤ K_max (perturb's K_max) equals the observed variance. FM is recomputed over that range with the package's formula. num_ffts (7) and vibration channels (2) are recovered by reproducing perturb's FM. perturb's values are kept as `epsilon_<probe>_perturb` and `FM_<probe>_perturb`. This is the first method change from the shipboard processing.
* **Cutoff test** (`scripts/test_shear_fmin.py`, `epsilon_shear/fmin_test/`), windows below 150 dbar, median refit/perturb:

  | f_min (Hz) | VMP250 | VMP5500 |
  |---|---|---|
  | 0 | 0.96 | 0.96 |
  | 0.5 | 0.87 | 0.87 |
  | 1 | 0.66 | 0.74 |
  | 2 | 0.63 | 0.79 |

  * The 0 Hz control reproduces perturb to within about 4% (perturb's own variance correction).
  * Mean epsilon over 150–550 dbar:

    | f_min | VMP250 (W/kg) | VMP5500 (W/kg) |
    |---|---|---|
    | perturb | 1.93e-9 | 5.57e-10 |
    | 1 Hz | 1.19e-9 | 3.74e-10 |
    | 2 Hz | 1.01e-9 | 3.41e-10 |
  * Most of the change happens between 0.5 and 1 Hz. From 1 to 2 Hz the median changes by under 5% for VMP250 windows with perturb FM < 1.15 and for all VMP5500 bins.
  * VMP250 high-FM windows keep falling with a higher cutoff (FM 1.15–1.5: 0.59 to 0.55; FM > 1.5: 0.45 to 0.40), so their contamination extends above 1 Hz.
  * 1 Hz is chosen as the smallest cutoff past the main drop that keeps the fit range. At 0.7 m/s, 2 Hz is about 3 cpm against a K_max of about 15 cpm at low epsilon.
* **Open issue, the upper end.** Inside the refit range the residual is still not flat for epsilon 1e-10–1e-9: a dip at k/K_max 0.2–0.5, then the spectrum rises above Nasmyth toward K_max (+0.7 VMP250, +1.0 VMP5500 in ln). The spectra are flatter than Nasmyth, as expected when the dissipation range approaches the noise or vibration level (or for low buoyancy Reynolds number turbulence, Re_b ~ 2–20 here). perturb's K_max may therefore include noise, which would still bias epsilon high. With the refit, VMP5500 FM > 1.15 rises to 83% of kept windows, driven by this upper end. Next test: K_max chosen against the noise spectrum.
* **Baseline outputs with refit:**

  | Below 150 dbar | VMP250 | VMP5500 |
  |---|---|---|
  | Median epsilon (W/kg) | 4.6e-10 | 8.2e-11 |
  | Median floor (W/kg) | 1.4e-10 | 1.1e-11 |
  | At floor | 9% | 10% |

  The floor also falls, because the noise spectrum below 1 Hz is excluded.

## 2026-10-13: Upper integration limit (K_max) test — keep perturb's K_max

`scripts/test_shear_kmax.py` (`epsilon_shear/kmax_test/`). With the 1 Hz refit, the spectra rise above Nasmyth toward K_max: about 2× on the VMP250 and 2.7× on the VMP5500 at epsilon 1e-10–1e-9. Is that noise inside the fit range?

* **Quiet-window noise spectrum as the criterion: not usable.** It still holds low-epsilon turbulence at low wavenumbers, so a "spectrum < 2× noise" limit triggers just above 1 Hz. On the VMP250, 56% of windows could not be fitted and the rest kept about 9 points.
* **Flat electronic floor:** median of the quiet-window spectrum over 20–40 Hz (`test_white_band_hz`).

  | Probe | Floor (s⁻²/Hz) |
  |---|---|
  | VMP250 sh1 | 1.5e-7 |
  | VMP250 sh2 | 1.7e-8 |
  | VMP5500 sh1 | 1.6e-8 |
  | VMP5500 sh2 | 4.7e-8 |

  A spectrum-vs-floor limit at 2× or 3× never binds (median epsilon unchanged), and subtracting the floor changes epsilon by under 3%. The excess near K_max is not electronic noise.
* **Not vibration either.** The upper-end excess (mean ln obs/Nasmyth over 0.7–1 K_max) has Spearman correlation −0.13 (VMP250) and −0.21 (VMP5500) with the accelerometer ratio, the opposite sign to contamination. It decreases slowly with epsilon (−0.22, −0.31) and Re_b (median 0.98 at Re_b < 3 to 0.63 at Re_b > 1000, VMP5500), and persists at all Re_b. It is a systematic shape difference from Nasmyth at low epsilon. Possible contributors: perturb's K_max sits at the spectral minimum where the spectrum turns up, and weak, anisotropic turbulence.
* **Sensitivity**, refit with the upper limit at a fraction of K_max:

  | Upper limit | VMP250 median / 150–550 mean | VMP5500 median / 150–550 mean |
  |---|---|---|
  | 0.7 K_max | 0.94 / 0.97 | 0.82 / 0.90 |
  | 0.5 K_max | 0.88 / 1.01 | 0.71 / 0.85 |

* **Decision:** keep perturb's K_max. There is no noise-based criterion for a lower limit, and pulling it in would just fit a different part of a non-Nasmyth shape. Carry it as a structural uncertainty in low-epsilon shear estimates: about 5% (VMP250) and 10–20% (VMP5500), in the direction of lower epsilon.

## 2026-10-13: FFT and dissipation length sensitivity runs (fft2_diss16, fft2_diss8)

* **Mechanism:** `--sensitivity NAME` (`src/run_pipeline.py`, every step) applies a `sensitivity_runs` entry's dotted-key overrides to a copy of the config. Output goes to `outputs/NAME/`, and the hash covers the config file plus the overrides.
* **Runs** (chi windows set to match the epsilon windows; both ran cast_log through epsilon_shear without errors, about 12–15 min each):

  | Run | FFT / diss | FFTs per window | Goodman factor | Window extent |
  |---|---|---|---|---|
  | baseline | 4 s / 16 s | 7 | 1.41 | 11–13 m |
  | `fft2_diss16` | 2 s / 16 s | 15 | 1.16 | 11–13 m |
  | `fft2_diss8` | 2 s / 8 s | 7 | 1.41 | ~6 m |

  `fft2_diss8` has 12206 (VMP250) and 13562 (VMP5500) windows.
* **Comparison** (`scripts/compare_runs.py`; `outputs/comparisons/window_lengths/`). Paired per-profile 25 m bin means, 150–550 dbar, relative to baseline (median [IQR]):

  | | VMP250 epsilon | VMP250 chi | VMP5500 epsilon | VMP5500 chi |
  |---|---|---|---|---|
  | `fft2_diss16` | 1.03 [1.00, 1.07] | 1.01 [0.94, 1.08] | 1.02 [0.95, 1.09] | 1.00 [0.93, 1.10] |
  | `fft2_diss8` | 1.01 [0.96, 1.06] | 1.01 [0.91, 1.13] | 0.97 [0.87, 1.08] | 1.01 [0.86, 1.16] |

  * Averaged epsilon and chi do not depend on these choices once the 1 Hz refit is applied.
  * The refit's effect does depend on them: refit/perturb median 0.66 (VMP250) and 0.74 (VMP5500) with 4 s FFTs, but 0.80–0.91 with 2 s FFTs. perturb's own epsilon depends on the FFT length through the energy below 1 Hz, and the refit removes that dependence.
  * The Goodman correction (1.41 vs 1.16) does not change the averaged result.
* **Other metrics** below 150 dbar:

  | | VMP250 baseline / diss16 / diss8 | VMP5500 baseline / diss16 / diss8 |
  |---|---|---|
  | Median floor (W/kg) | 1.4e-10 / 1.7e-10 / 1.4e-10 | 1.1e-11 / 1.3e-11 / 1.0e-11 |
  | At floor | 9% / 15% / 9% | 10% / 12% / 10% |
  | FM > 1.15 | 13% / 29% / 6% | 63% / 75% / 50% |

  * Probe disagreement is unchanged (VMP250 6–7%, VMP5500 19–21%).
  * FM rates depend strongly on the settings, so an FM threshold does not transfer between settings.
* **Interfaces:** 8 s windows resolve the staircase.
  * SPC_031: chi about 1e-10 in the 301–318 dbar layer against 3e-8 at the 290–297 dbar interface. The 16 s windows give about 1e-9 to 1e-8 for both.
  * data_0133_prof003: chi about 2e-9 in the 222–240 dbar mixed layer at 8 s against 1e-8 to 5e-8 at 16 s, with the interface near 220 dbar at about 1e-7.
* **Recommendation, not yet adopted:** use the 2 s / 8 s settings for the regime classification and the interface/layer double-diffusion test. Report them as a difference from the baseline, which keeps the shipboard 4 s / 16 s.

## 2026-10-13: Analysis settings 2 s FFT / 8 s windows; chi by MLE

* Decision (user): regime classification and the double-diffusion tests use 2 s FFT / 8 s dissipation windows (for epsilon and chi). The baseline keeps the shipboard 4 s / 16 s, and analysis results are reported as differences from it. Reason: averaged epsilon and chi are unchanged (previous entry), and 8 s windows separate staircase interfaces from layers.
* The analysis run `fft2_diss8_mle` also fits chi by maximum likelihood (`perturb.chi.fit_method: mle`, Ruddick et al. 2000), the method in CLAUDE.md step 5 and the first planned change after the baseline. The iterative fit (`fft2_diss8`) is kept for comparison.

## 2026-10-13: thermistor step; T3304 excluded; MLE vs iterative chi; epsilon_T vs shear

* **Step:** `src/steps/thermistor.py` (config `chi_qc`) post-processes perturb's per-probe chi and epsilon_T (Kraichnan fits, `use_epsilon: false`).
  * Per probe: exclusions; K_max/kB ≥ 0.5 (applied); fom outside [1/1.15, 1.15] (flagged only).
  * A noise floor from perturb's FP07 noise spectrum; windows near it are kept and flagged.
  * Probe pair: limit 2.77, policy `min`. Geometric mean of the usable probes.
  * epsilon_T is compared with shear epsilon (shear above its floor) by Turner regime and Re_b, and a spectra gallery is drawn.
  * Chi and epsilon windows are identical (checked).
* **VMP5500 T2 (T3304) excluded for SPC_012–SPC_039.**
  * chi_T1/chi_T2 was 0.4–0.8 per cast from SPC_012 (0.95 on SPC_004). At signal/noise above 100 it is 0.58, so the cause is a gain error, not noise.
  * After the swap, T1 against T3301 gives 0.98 at high signal/noise; T1 (T3303) is the same probe throughout.
  * T3304 flat-lined on SPC_040 and was replaced. Added to `exclude_probes`.
* **Noise and fit-quality results.**
  * Below 150 dbar, few windows are near perturb's FP07 noise floor: 0% (VMP250) and 4% (VMP5500).
  * The temperature-gradient spectra on both instruments carry an unmodelled plateau at about 30–200 cpm, 1–2 decades above `spec_noise`. Floors computed from `spec_noise` are therefore optimistic at high k (docs/package_issues.md #4).
  * perturb's own soft QC found no passing probe in 23% (VMP250) and 15% (VMP5500) of windows.
* **MLE vs iterative**, paired windows below 150 dbar, `fft2_diss8_mle` against `fft2_diss8`:

  | Quantity | VMP250 MLE/iterative | VMP5500 MLE/iterative |
  |---|---|---|
  | chi | 1.07 | 1.08 |
  | epsilon_T | 0.94 | 0.97 |
  | kB | 0.99 | 0.99 |

  The fit method is a minor effect. MLE stays in the analysis run, as specified.
* **epsilon_T vs shear epsilon** (MLE, shear above its floor, below 150 dbar), median epsilon_T/epsilon_shear:

  | Turner angle | VMP250 | VMP5500 |
  |---|---|---|
  | Tu < 45° | 1.86 | 1.80 |
  | 45–72° | 1.33 | 1.86 |
  | 72–90° | 2.05 | 3.25 |

  * The ratio is highest at low Re_b.
  * Within the iterative run, windows whose spectrum at K_max is still well above the high-k floor have 4–9× ratios, mostly in strong-finger water, which is consistent with finger-scale variance read as turbulence.
  * The ~1.8× offset outside finger water is not a fit-method effect. Epsilon_T scales as kB⁴, so a ~16% kB error (for example from the FP07 response correction) would explain it. Test run `fft2_diss8_mle_dp`: double-pole FP07 response with a fixed 3 ms tau (Goto et al. 2016).
* epsilon_T is not used to replace shear epsilon until this offset is understood.

## 2026-10-13: FP07 response model and where epsilon_T can be used

* **Test run `fft2_diss8_mle_dp`:** double-pole FP07 response with a fixed tau of 3 ms (Goto et al. 2016), against perturb's default single-pole with the speed-dependent `lueck` tau (10 ms × U^-0.5, about 11–12 ms here). Paired windows below 150 dbar, double/single:

  | Quantity | VMP250 | VMP5500 |
  |---|---|---|
  | kB | 0.79 | 0.82 |
  | epsilon_T | 0.39 | 0.46 |
  | chi | 0.57 | 0.68 |

  The FP07 response model is a first-order uncertainty in chi (30–45%), much larger than the fit method (7–8%).
* **Agreement with shear depends on how much of the Batchelor roll-off is resolved.** Median epsilon_T/shear, shear ≥ 5× its floor:

  | K_max/kB | VMP250 single / double | VMP5500 single / double |
  |---|---|---|
  | 0.8–1.2 | 4.0 / 1.6 | 6.3 / 2.6 |
  | 1.2–1.6 | 2.1 / 0.85 | 3.4 / 1.5 |
  | > 1.6 | 0.90 / 0.34 | 1.19 / 0.51 |

  * Where the roll-off is resolved, the single-pole model agrees with shear and the double-pole model is 2–3× low. Where it is not, the fit extrapolates kB and epsilon_T is biased high under either model.
  * The earlier "1.8× offset" was a mix of the two.
  * perturb's soft QC limit (K_max/kB ≥ 0.5) is far too permissive for epsilon_T.
* **Decision:**
  * Keep the single-pole response (shipboard and perturb default) in the analysis run.
  * Use epsilon_T only where K_max/kB ≥ 1.6 (`chi_qc.epsilon_T.k_max_ratio_min`, flag `epsilon_T_resolved`). Below 150 dbar that is 38% of VMP250 and 52% of VMP5500 windows.
  * epsilon_T is reported everywhere.
* **Result where resolved** (`fft2_diss8_mle`), median epsilon_T/shear:

  | Turner angle | VMP250 | VMP5500 |
  |---|---|---|
  | < 45° | 0.74 | 0.89 |
  | 45–72° | 0.99 | 1.05 |
  | 72–90° | 1.27 | 1.81 |

  * At Re_b > 10 the two agree within about 1.5×.
  * At Re_b < 3, epsilon_T exceeds shear in every regime, most in strong-finger water. This is consistent with weak turbulence or finger-scale variance not following the Kraichnan shape.
* **Uncertainty carried forward:** chi depends on the FP07 response model by a factor of about 1.4–1.8. It is less where the roll-off is resolved (double/single 0.61–0.72 at K_max/kB > 1.6), but not negligible. Per-thermistor tau calibration (perturb `instruments.<SN>.fp07_tau_scale`, anchored where K_max/kB > 1.2 against shear epsilon) is a possible next refinement. It would tie epsilon_T to shear epsilon in the calibration windows.

## 2026-10-13: perturb's own warnings reviewed; email thread with Pat Welch (Jul–Aug 2026)

The email thread (Pat Welch, Eli Hunter, Joe Gradone; 2026-07-14 to 08-13) prompted a review of the warnings perturb writes to its per-file logs. This pipeline had not been reading them. Analysis run `fft2_diss8_mle`:

* **Chi T1/T2 disagreement** is flagged for exactly SPC_012–SPC_040 (median ratio 0.45–0.79). This independently confirms the T3304 exclusion.
* **Shear disagreement:**
  * VMP5500, nearly every cast: e1/e2 0.3–0.86, so sh2 reads higher (known; `min` policy). SPC_060–061 (sh1 low response) are already excluded.
  * VMP250, new:
    * data_0112 profiles 1–2: e1/e2 0.08 and 0.18 (test casts, sh2 M3463; already a candidate for exclusion in shipboard_processing.md).
    * data_0123 profile 4 and data_0124: 3.3–5.4, sh1 high. The Sealog notes sargassum and very high surface current on data_0124, so sh1 is likely fouled.
    * data_0127–0147: a steady 1.2–1.45, sh1 higher. This is consistent with an uncertain sh2 sensitivity (M2662, calibrated 2023).
    * data_0148–0149: 0.8–0.85.
  * Open: exclude sh2 for data_0112 and sh1 for data_0123–0124 (exclusions are per file; data_0123 profiles 1–3 agree).
* **Chi windows dropped** because the fitted kB > 1.5 K_AA: 2364 windows (fft2_diss8_mle). All are near the surface (VMP250 median 14 m, 99th percentile 44 m; median shear epsilon about 1e-6). None of the VMP250 windows and 3 of the VMP5500 windows are below 150 dbar, so the staircase analysis is unaffected. Near-surface chi is missing exactly where turbulence is strongest.
* **perturb's `Gamma`/`K_rho` use shear epsilon even with `use_epsilon: false`** (warned on every file). This pipeline does not use perturb's mixing outputs.
* **Points from the thread that support existing choices:**
  * Patch the .p files for sensor coefficients, except the FP07s, which are calibrated in situ.
  * Keep the original files untouched.
  * Inspect the spectral fits visually; perturb-diag is the package's tool, and this pipeline has its own galleries.
  * Pat considers epsilon validated against the SCOR160/ATOMIX benchmarks (within 2%). He described chi and the mixing parameters as still under review at the time.
* **Caching:** `perturb run` reuses unchanged stages and supports `--jobs`. The `convert` step's `rmtree` defeats the reuse (docs/package_issues.md #6 retracted).

## 2026-10-13: Probe exclusions from perturb's warnings; perturb cache reuse

* **Exclusions (user approved; `instruments.vmp250.exclude_probes`).** Keys may now name a single profile (`data_0123_prof004`) as well as a whole file. Median shear epsilon at 40–200 dbar against neighbouring casts decided which probe was bad:

  | Exclusion | sh1 (W/kg) | sh2 (W/kg) | Neighbours (W/kg) |
  |---|---|---|---|
  | data_0112 sh2 (whole file; test casts with M3463) | 7–8e-10 (normal) | 3.6–3.9e-9 (5× high) | — |
  | data_0123 profile 4 and data_0124 sh2 | 6.0–6.4e-10 (normal) | 1.3–2.3e-10 (3–5× low) | 4–9e-10 |

  Sargassum was logged for data_0124, so the sh2 response was probably damped. A first version excluded sh1 there and was corrected the same day.
* **Lessons:**
  * The `min` rule on probe disagreement assumes contamination only raises epsilon. A damaged or damped probe reads low, and `min` then picks it. Persistent per-cast disagreements need checking against neighbouring casts, not just the rule.
  * The quietest-windows noise floor is sensitive to a low-reading probe. Before the exclusion, 176 of 232 of sh2's quietest windows came from data_0112, data_0123 and data_0124, and sh2's noise level at 2–5 Hz was 6.5e-7 instead of 2.3e-6.
* **Result** (VMP250, `fft2_diss8_mle`, below 150 dbar):
  * Median floor 1.4e-10 → 2.0e-10 W/kg.
  * Windows near the floor 9% → 39%, consistent with the QC explorer's earlier note that VMP250 epsilon below 150 m sits within about 2× of its floor.
  * Median epsilon 4.4 → 4.5e-10.
  * epsilon_T/shear where resolved: 0.87, 0.94 and 1.21 by Turner regime.
  * VMP5500 unchanged.
* **perturb cache** (email from Pat Welch):
  * `convert` no longer deletes perturb's output tree (`conversion.reuse_cache: true`). After each run it records the stage directories that match the config via perturb's own resolver (`odas_tpw.perturb.resolve.stage_dir`, strict) in `convert/stage_dirs_<instrument>.json`, which `common.single_dir` reads.
  * `patch` reuses its files when the raw files, the edits and the package version are unchanged, so file times do not invalidate perturb's per-file cache.
  * `conversion.jobs: 0` (one worker per core).
  * Test on `fft2_diss8_mle`: diss and chi reused (`diss_00`, `chi_00`). The combo stages moved to `_01`, because cast_log rewrites the GPS track file. A patch-plus-convert rerun took about 3 min.

## 2026-10-14: regimes step; staircase thresholds (published vs tuned)

* **Step:** `src/steps/regimes.py` (config `regimes`), run on the analysis run `fft2_diss8_mle`.
  * **Turner class** from 25 m fits (`turner_smoothing_m`; the 10 m class is kept alongside): not_finger, finger (45–72°), strong_finger (72–90°), diffusive, unstable.
  * **Staircase labels per method** from `thermohalinesteps.classify_staircase` on each profile's 1 dbar grid. A window (P ± speed·diss_sec/2, probe-tip depth) is interface or layer when at least 2/3 of its extent is; straddles when the two together reach 2/3; none otherwise.
  * **Re_b** from bounded shear epsilon and from resolved epsilon_T.
  * **Outputs:** `regimes_<instrument>.csv`, `steps_<instrument>.csv`, figures.
* **Background window:** `av_window` only sets the 200 dbar running mean for α and β, which put the mixed-layer test in density units. The Turner angle that classifies steps uses a 50 dbar mean hardcoded in the package. The 200 dbar window is kept for both instruments; `stair_av100` is the sensitivity run.
* **Thresholds:**
  * With the published `ml_grad` 0.0005 kg m⁻³ dbar⁻¹, most visually evident steps were missed, because the layers keep a weak residual gradient.
  * `scripts/test_staircase_thresholds.py` (`regimes/threshold_test/`). Staircase share of profile depth below 150 dbar, temperature-only test:

    | ml_grad | VMP5500 | VMP250 |
    |---|---|---|
    | 0.0005 | 14% | 7% |
    | 0.001 | 29% | 10% |
    | 0.002 | 37–38% | 14% |

  * `ml_density_difference` (0.005–0.04) has almost no effect.
  * At 0.002 the example profiles (SPC_031, SPC_033) are labelled over most of their visible steps. The VMP250 upper thermocline (data_0133) has step-like structure on a strong background gradient and stays mostly unlabelled, which is appropriate.
* **Decision (user):**
  * `vdb2021` keeps the published values: `ml_grad` 0.0005, and mixed layers must pass the temperature, salinity and density tests.
  * `rollo2022` is tuned: temperature-only, `ml_grad` 0.002.
  * Sensitivity run `stair_mlgrad001` (0.001).
  * Results are reported under both labellings. The ML labels, when available, are an independent check.
  * The published thresholds, and the staircase percentages they produce in other datasets, are a reference, not a benchmark for this dataset.
* **Result below 150 dbar:**

  | | VMP250 | VMP5500 |
  |---|---|---|
  | rollo2022 windows (interface / layer / straddles) | 143 / 385 / 207 | 511 / 1623 / 1295 |
  | Profiles with interfaces (rollo2022) | 72 | 44 |
  | vdb2021 windows (interface / layer / straddles) | 9 / 15 / 5 | 287 / 630 / 441 |
  | Methods agree | 87% | 73% |
  | Median Re_b (shear) | 9.6 | 5.1 |

  Turner classes are mostly finger and strong_finger on both instruments.
* **Bug fixed (hydrography):** the T–S relations (own_ts and ship) stopped at the end bins' median CT. That left salinity NaN for the last ~0.25 °C of each cast, about 100 m at depth, and 1573 VMP5500 windows had no Turner class. Relations now extend linearly to the observed CT range. 465 undefined windows remain, mostly SPC_041 and SPC_045 below the ship's 550 m reach (bad-cell casts on the ship relation).

## 2026-10-14: dd_test step; first result at the process station

* **Step:** `src/steps/dd_test.py` (config `double_diffusion`, `uncertainty`).
  * Per window, chi_exp = 2 (0.2 ε/N²) T_z² with ε = bounded shear epsilon (an upper bound near the floor, so R is a lower bound there).
  * R = ⟨chi_obs⟩/⟨chi_exp⟩ (ratio of averages) per group × staircase method × Turner set × staircase label, in 25 m bins and pooled over 150–550 dbar.
  * 95% bootstrap over profiles (1000 samples).
  * Finger model Γ_finger/0.2 from each bin's R_ρ = ⟨αT_z⟩/⟨βS_z⟩, with γ = 0.65.
  * Everything is repeated with the weakest 10% of N² removed.
  * Windows excluded: VMP5500 temperature inversions (T–S salinity invalid), N² ≤ 0, and windows without kept shear or chi.
  * Groups: station group (`station_groups`, process station only for now) × instrument × free fall or tow-yo, never pooled.
* **Result, analysis run `fft2_diss8_mle`, process station, finger-favourable windows, rollo2022 labels**, pooled over 150–550 dbar, R [95% CI]:

  | Group | All | Interface | Layer | Finger model |
  |---|---|---|---|---|
  | VMP5500 (4 profiles, 378 windows) | 2.5 [2.2, 2.9] | 6.6 [4.8, 11.2] | 1.05 [0.5, 1.8] | ~4.0 (R_ρ 1.8) |
  | VMP250 tow-yo (8 profiles) | 2.8 [2.5, 3.1] | 5.4 [4.5, 6.3] | 0.33 [0.14, 0.63] | — |
  | VMP250 free fall (7 profiles, 150–265 dbar) | 5.5 [2.2, 7.8] | — | — | 3.6 |

  * VMP5500 straddles: 3.3. vdb2021 labels: interface 5.8, layer 0.65.
  * VMP250 tow-yo: 89% of layer windows have shear at its floor, so 0.33 is a lower bound. Shear at floor in 31% (free fall) and 45% (tow-yo) of all windows.
  * VMP250 free fall: no staircase labels. Its pooled value is driven by a single deep bin with fewer than 3 profiles.
  * Removing the weakest 10% of N² changes the pooled ratios by under 0.1, except tow-yo layers (0.33 to 0.22).
  * VMP5500 R rises with R_ρ (about 0.8 at R_ρ 1.1 to about 5 at 2.2) along the finger curve for γ 0.65–0.7.
* **Reading:** chi exceeds the shear-turbulence expectation (Γ = 0.2) by 5–7× at staircase interfaces, at or above the finger model, while layers are consistent with about 1. This is the defensible claim: interface chi is not explainable by shear-driven turbulence with Γ = 0.2. R is a dissipation ratio, not a mixing efficiency.
* **Caveats before interpretation:**
  * The FP07 response model scales chi by 0.57–0.68 (double-pole against single-pole). With double-pole, interfaces would be about 3.5–4.5 and layers about 0.6.
  * Only 4 VMP5500 profiles at the station. Many 25 m interface and layer bins have fewer than 3 profiles (flagged), so use pooled values.
  * There is almost no non-finger water at the station for a control (2 and 10 windows).
  * VMP250 free fall and tow-yo differ (5.5 against 2.8) and are not pooled.
  * Stratification scale (10 m) runs `strat5m` and `strat25m`, the staircase threshold run `stair_mlgrad001`, `epsilon_source: thermistor` and γ are pending sensitivity runs.

## 2026-10-14: dd_test depth range extended; interface-local and finescale gradients

* **Depth range per instrument** (`double_diffusion.depth_range_dbar`): VMP250 150–300 dbar (to the bottom of its casts), VMP5500 150–1000 dbar. The earlier 550 dbar limit was the ship CTD validation depth, not a physical limit.
* **Three gradient choices for chi_expected**, all reported:
  * **background:** 10 m linear fits.
  * **interface_local:** windows labelled interface only. T_z and S_z are the detected interface's CT and SA range over its thickness (median 3 m), and N² is computed from them.
  * **finescale:** every window. T_z² is replaced by the mean squared 1 m temperature gradient over the window; N² stays the background value.
* **Why it matters:** below about 600 dbar the background version gave R ≈ 12–19, and 17 for VMP5500 non-finger windows (114, mostly 800–1000 dbar near the AAIW salinity minimum). That would contradict the shear-turbulence expectation of about 1.
  * Not noise. An empirical FP07 chi floor from the quietest 2% of windows (about 1e-11 K²/s) matches perturb's floor. Deep chi is 15–40× above it, and only 2–10% of deep windows are near it.
  * Instead, the 1 m gradient variance exceeds the background T_z² (median 1.3–1.9×, much more in some windows). The ratio of averages is dominated by those intrusive-finestructure windows, a direct case of the Osborn–Cox caveat (chi produced by gradients the background fit does not represent).
* **Process station, finger-favourable, rollo2022**, R [95% CI]:

  | Group | Gradients | All | Interface | Layer | Non-finger control |
  |---|---|---|---|---|---|
  | VMP5500 | background | 2.9 | 6.8 | 1.7 | 16.9 [6.9, 23] |
  | VMP5500 | interface_local | — | 5.2 [3.9, 8.6] | — | — |
  | VMP5500 | finescale | 1.9 [1.6, 2.1] | 4.1 [3.2, 6.2] | 0.93 [0.69, 1.31] | 1.4 [0.2, 9.9] |
  | VMP250 tow-yo | background | 2.8 | 5.4 | 0.33 | — |
  | VMP250 tow-yo | interface_local | — | 4.6 | — | — |
  | VMP250 tow-yo | finescale | 2.0 | 3.1 [2.7, 3.7] | 0.91 | — |
  | VMP250 free fall | background / finescale | 5.5 / 3.6 | — | — | — |

* **Reading:** under every gradient choice, staircase interfaces exceed the shear-turbulence expectation (R 3–7, near the finger prediction of about 4). Layers are about 1 with finescale gradients. With finescale gradients the non-finger control recovers about 1, which supports the finescale version as the more consistent estimate. Background-gradient ratios overstate R where intrusive finestructure is present, and deep (> 600 dbar) background ratios should not be interpreted. Gradient choice is a key methods decision for the paper; all three are carried.

## 2026-10-14: Whole cruise; control water; R depends on Re_b in all water

* **Whole cruise:** `station_groups` [process_station, transect], plus an "all free fall" pool per instrument (tow-yo stays separate).
  * Finger-favourable water, 1 m (finescale) gradients, with interface-gradient values in brackets:

    | Instrument | Casts / profiles | Interfaces | Layers |
    |---|---|---|---|
    | VMP5500 | 44 casts | 4.3 [3.1, 5.9] (6.7) | 1.1 |
    | VMP250 | 119 profiles | 2.7 (4.4) | 1.2 |

* **First control (−90 < Tu < 30, ≥ 150 dbar):** not usable.
  * VMP250: mostly intrusion water (temperature inversions at the 25 m scale, salt-stabilised), which is double-diffusively active.
  * VMP5500: 91% at 900–1000 dbar near the AAIW salinity minimum, where its T–S-derived Turner angle is unreliable and turbulence is barely active (median Re_b 2.4).
  * It also wrongly included diffusive convection (−90° to −45°).
* **Control now:**
  * −45 < Tu < 30 (doubly stable), T_z > 0 at the window scale (no inversions), from 20 dbar (`control_depth_range_dbar`).
  * Most of it sits above the shallow salinity maximum (median about 105 dbar; S increases downward, so fingers are impossible).
  * Pooled R: VMP250 1.36 [1.13, 1.63] (finescale; 1.96 background), 2474 windows. VMP5500 1.74 [1.19, 2.64] (2.87 background), 1160 windows.
* **R by Re_b (`dd_re_b.csv`, figure `ratio_vs_re_b.png`), all free fall, finescale gradients**, finger-favourable vs control:

  | Re_b | VMP5500 finger | VMP5500 control | VMP250 finger | VMP250 control |
  |---|---|---|---|---|
  | 0–3 | 7.0 | 4.7 | 2.3 | 2.0 |
  | 3–10 | 3.9 | 2.4 | 1.9 | 1.8 |
  | 10–30 | 2.3 | 2.3 | 1.9 | 1.7 |
  | 30–100 | 0.94 | 0.92 | 2.3 | 1.6 |
  | > 100 | 0.7 | 0.8 | 2.0 | 0.8 |

* **Reading:**
  * In all water, R rises as Re_b falls: about 1 at Re_b > 30, and 2–5 at Re_b < 10 even in doubly stable water. At low Re_b the Osborn model with Γ = 0.2 does not hold, or epsilon is underestimated near its floor, or chi has non-turbulent sources.
  * Most of the earlier "R > 1" is this low-Re_b effect, not fingers. Median Re_b is about 5–10 in finger water.
  * The finger-specific signal is the excess over the control at matched Re_b: about 1.5× for the VMP5500 at Re_b < 10, and small or absent for the VMP250 except at Re_b 30–100.
  * The staircase-interface excess must be re-evaluated against the Re_b-matched control before any claim.

## 2026-10-14: Excess over the Re_b-matched control (dd_excess.csv)

* **Method:** the control's ratio in each Re_b bin, R_c(b), calibrates the Γ = 0.2 expectation empirically.
  * For a set of finger-favourable windows, E = Σ chi_obs / Σ (chi_exp × R_c(b_window)), with the control from the instrument's whole-cruise free-fall casts (doubly stable, no inversions, from 20 dbar).
  * E = 1 means indistinguishable from doubly stable water at the same Re_b.
  * 95% bootstrap resamples target and control profiles independently.
* **Result, whole cruise free fall, E [95% CI]** (finescale / background / interface_local gradients):

  | Set | Labels | Finescale | Background | Interface-local | Raw R (finescale) | Median Re_b |
  |---|---|---|---|---|---|---|
  | VMP5500 interfaces | rollo2022 | 1.75 [1.21, 2.62] | 2.37 [1.51, 3.64] | 2.74 [1.89, 3.97] | 4.3 | 3.4 |
  | VMP5500 interfaces | vdb2021 | 1.51 [1.08, 2.13] | 2.21 | 2.75 [1.89, 4.17] | — | — |
  | VMP5500 layers | rollo2022 | 0.62 [0.42, 0.95] | — | — | — | — |
  | VMP5500 layers | vdb2021 | 0.23 | — | — | — | — |
  | VMP5500 all finger water | — | 1.29 [0.94, 1.78] | 1.43 | — | — | — |
  | VMP250 interfaces (119 profiles) | rollo2022 | 1.52 [1.01, 2.10] | 2.45 [1.39, 3.97] | 2.51 [1.56, 3.65] | — | — |
  | VMP250 tow-yo interfaces | rollo2022 | 1.71 [1.41, 2.08] | — | 2.53 | — | — |
  | VMP250 layers | rollo2022 | 0.67–0.73 | — | — | — | — |
  | VMP250 all finger water | — | 1.13–1.26 | — | — | — | — |

  * VMP5500 process station alone (4 profiles): interfaces 1.41 [0.94, 2.36] finescale, 1.84 [1.23, 3.18] interface-local.
* **Reading:**
  * Staircase interfaces carry 1.5–2.8× more temperature variance than doubly stable water at the same Re_b. This holds for both instruments, both staircase labellings and every gradient choice, and the 95% interval excludes 1 everywhere except the VMP250 finescale case (lower bound 1.01) and the 4-profile process station.
  * Layers carry less than the control (well mixed).
  * Finger-favourable water as a whole is not clearly distinguishable from the control. The double-diffusive signal is concentrated at interfaces.
  * The earlier raw interface ratios (4–9) were mostly the low-Re_b effect (interface median Re_b about 3.4); the finger-attributable factor is about 1.5–2.8.
* **Caveats:**
  * The control is mostly 20–150 dbar, above the salinity maximum; the interfaces are 150–1000 dbar. Different depths, water masses and internal-wave environments are matched only in Re_b.
  * Low-Re_b behaviour (Γ, epsilon near its floor) is not understood.
  * The FP07 response model scales chi in both target and control alike (cancels to first order in E).

## 2026-10-14: Garrett–Munk reference level; epsilon_T as a baseline

* **GM reference (user):** `dd_gm.csv` and figure `diffusivity_vs_gm.png`. K_GM = K0 L(f, N), with K0 = 5e-6 m²/s, N0 = 5.24e-3 rad/s and the latitude factor relative to 30° (Gregg 1989; Kunze et al. 2006 form; verify constants before publication). It is set beside bin-averaged K_T = ⟨χ⟩/(2⟨T_z²⟩) (background and finescale) and K_ρ = 0.2⟨ε⟩/⟨N²⟩. It is a reference level for context, not a test.
* **Whole-cruise pooled diffusivities (m²/s):**

  | Quantity | VMP5500 | VMP250 |
  |---|---|---|
  | K_GM | 2.4–3.2e-6 | 2.3–3.0e-6 |
  | Shear-based K_ρ | 1.4e-6 | 2.4e-6 |
  | Control K_T (finescale) | 2.0e-6 | 2.4e-6 |
  | Finger-water K_T (finescale) | 5.1e-6 | 5.0e-6 |
  | Interface K_T (finescale / background) | 6.7e-6 / 1.4e-5 | 7.3e-6 / 1.6e-5 |

  * The measured turbulence and the non-finger water are both at about the GM level.
  * Finger water is 2–3× GM, and interfaces 2.7–6× GM.
* **epsilon_T as a baseline (user question).** Deriving ε from chi through the turbulence relations is circular: it forces R = 1. The Batchelor-fit ε_T is not circular (spectral shape, not magnitude), but in resolved windows:
  * In finger water it gives R about 0.7–1.0 at every Re_b, consistent with finger-scale variance setting kB, so it absorbs the finger signal.
  * In the doubly stable control it reads 5–10× below shear epsilon and raises R.

  So ε_T cannot adjudicate the excess. The low-Re_b control excess is not explained by shear epsilon reading low near its floor. Shear epsilon stays primary; `epsilon_source: thermistor` stays a sensitivity run, expected to bias finger water toward R = 1.
* **Framing:** report a ladder of baselines rather than one number:
  * Γ = 0.2 theory (raw R);
  * GM reference level;
  * doubly stable control at matched Re_b (E);
  * internal contrasts (interfaces vs layers vs non-staircase finger water at matched Re_b).

  The robust conclusion is what holds on every rung: interfaces carry the most chi at a given Re_b, layers the least, interface K_T is several times GM, and R rises with R_ρ as fingers predict. The absolute size of the double-diffusive excess depends on the baseline and is given as a range.

## 2026-10-14: Scope and the diffusivities step

* **Scope (user):** this repository is only the microstructure workflow. Nitrate, productivity and grazing analyses (RO1–RO3) use the exported products elsewhere.
* **What the products are designed around:**
  * **RO2a/b:** diffusivity profiles including K_S, the diffusivity relevant to nitrate in fingering, from 20 dbar through the salinity-maximum cap.
  * **RO2a:** the finger attribution ladder.
  * **RO1:** per-cast finger metrics.
* **Why the excess tests matter:** only for attribution (the finger fraction). Total K_T comes from chi alone. Further refinement of the low-Re_b excess is not pursued; the spread across baselines is reported as uncertainty.
* **Step `src/steps/diffusivities.py`** (config `diffusivities`), built from the dd_test window table:
  * K_T for each gradient choice, R_rho, K_S = R_ρ K_T/γ for γ = 0.5, 0.65 and 0.7, K_S_eps, K_rho (flagged invalid in finger sets) and K_GM.
  * 95% profile bootstrap.
  * K_S only where 1 < R_ρ ≤ 4 (`k_s_max_r_rho`): approaching the AAIW salinity minimum R_ρ reaches 3–17, where fingers are weak and R_ρ K_T/γ would grow regardless.
* **Whole cruise, all free fall, finger-favourable water, finescale gradients** (m²/s):

  | Quantity | VMP5500 | VMP250 |
  |---|---|---|
  | K_T | 5.1e-6 [4.2, 6.0] | 5.0e-6 [3.9, 6.2] |
  | K_S (γ 0.65) | 1.6e-5 [1.4, 1.9] | 1.4e-5 [1.1, 1.8] |
  | K_S_eps | 2.2e-5 | 2.9e-5 |
  | Interface K_S | 1.8e-5 | 1.9e-5 |
  | K_GM | 2.4e-6 | 2.7e-6 |
  | Control K_T | 2.0e-6 | 2.4e-6 |

  K_S_eps agrees with K_S within a factor of 2.
* **Finger fraction** (1 − 1/E, finescale gradients, matched control / GM / Γ = 0.2 theory):

  | Set | Matched control | GM | Γ = 0.2 theory |
  |---|---|---|---|
  | VMP5500 interfaces | 0.43 [0.17, 0.62] | 0.63 | 0.77 |
  | VMP250 interfaces | 0.34 | 0.65 | 0.62 |
  | VMP5500 all finger water | 0.23 (CI includes 0) | 0.52 | 0.63 |

  With interface-local gradients, interfaces are 0.60–0.85.
* **Outputs:** `diffusivity_bins.csv`, `attribution.csv`, `cast_metrics_<instrument>.csv`, figures. The `export` step will write them as products (docs/products.md, sections 4–6).

## 2026-10-14: export and uncertainty steps

* **`src/steps/export.py`** writes `outputs/<run>/products/` (docs/products.md):
  * the cast table;
  * segments NetCDF: one record per window, 86 variables, flag_masks and flag_meanings for the segment, shear and chi QC bits, window times from perturb;
  * binned NetCDF;
  * diffusivity NetCDF and CSV;
  * attribution and cast-metric CSVs;
  * a README listing files, provenance and caveats.

  Global attributes carry product_version, the run name and sensitivity overrides, config sha256, git commit, microstructure-tpw version and commit, Python and creation date. Exclusions (including profile-level ones) and cautions are carried as flags.
* **`products.depth_bin_m` 1 → 5 m.** 8 s windows are about 6 m tall and step about 3 m, so 1 m bins would be mostly empty; 92% of 5 m bins are filled for the VMP5500. Product version stays 0.1 (first written version).
* **Validated:** shear epsilon in the segments product equals the regimes table, no missing window times, and profile-level exclusions appear in the cast table.
* **`src/steps/uncertainty.py`:** the profile bootstrap is computed where each estimate is made (dd_test, diffusivities). This step checks coverage:
  * dd_excess: 119/119 pooled estimates with intervals.
  * diffusivity: 413/413.
  * dd_pooled: 904/984 (the rest have fewer than 2 profiles; flagged).
  * Median pooled interval width 0.24–0.35 decades.

## 2026-10-14: Sensitivity runs on the analysis settings

* **Machinery:**
  * Sensitivity entries can chain (`base`).
  * Runs with unchanged perturb settings link the base run's patched files and perturb output (`reuse_convert_from`). The convert step checks that the generated perturb configs agree except for paths and provenance.
* **Runs:** the analysis run `fft2_diss8_mle` was rerun from cast_log to export with all fixes, followed by:
  * `an_strat5m`, `an_strat25m` (background gradient scale);
  * `an_bin10m`;
  * `an_mlgrad001` (staircase threshold);
  * `an_av100`;
  * `an_epsT` (thermistor epsilon);
  * `fft2_diss8_mle_dp` (double-pole FP07 response).

  Each is exported to `outputs/<run>/products/`. Comparison: `scripts/compare_sensitivity.py` writes `outputs/comparisons/sensitivity/`.
* **Diffusivities are robust to processing choices.** Finger-water K_T and K_S (γ 0.65, finescale) change by under 5% across stratification scale (5/10/25 m), bin size, staircase threshold and α/β window. The exception is VMP250 interface K_S with the 0.001 threshold (2.5e-5 vs 1.9e-5; 35 vs 63 windows).
  * The FP07 response model halves K_T and K_S (×0.48–0.55 with double-pole). It and γ (×1.4 across 0.5–0.7) are the dominant uncertainties in K_S.
* **The interface excess is not robust to the stratification scale.** E over the Re_b-matched control:

  | Scale | VMP5500 | VMP250 |
  |---|---|---|
  | 5 m | 2.2 | 2.2 |
  | 10 m | 1.75 | 1.52 |
  | 25 m | 1.10 | 0.60 |

  * Internal contrasts follow: VMP5500 interface/layer 2.3 / 2.7 / 1.5 [1.0, 2.1], interface/none 1.6 / 1.4 / 1.1 [0.8, 1.6]. VMP250 interface/none 2.0 / 1.4 / 0.86.
  * E is insensitive to the FP07 response model (1.63–1.85, which cancels), bin size, staircase threshold and av_window.
  * The stratification scale sets N² and so Re_b, which is how interfaces are matched to the control and to other water. The 25 m scale smooths over interfaces and layers alike.
  * Consequence: the finger fraction at interfaces against the matched control ranges from about 0 (or below, VMP250) to 0.55 across 5–25 m. The VMP5500 interface excess is > 1 at 5 and 10 m, marginal at 25 m.
* **`an_epsT`** uses thermistor epsilon in chi_expected and keeps only windows with a resolved roll-off (VMP5500 194 interface windows instead of 502, VMP250 13). Its K_T and E describe a different subset (lower-chi windows) and are not comparable as a sensitivity on the same sample. It confirms that ε_T absorbs the finger signal (E 0.2–0.26).
* **Reading for the objectives:**
  * RO2a/b: K_S is well constrained by the processing apart from the FP07 response (factor ~2) and γ (factor 1.4).
  * The finger attribution (finger fraction) remains baseline- and scale-dependent and should be reported as a range. Its 10 m central values are not robust on their own.

## 2026-10-14: Full-chain reproduction from the raw files

* The baseline was run through every step: cast_log to export, including compare_archive and figures.
* Run `repro_baseline` (baseline settings, no overrides, fresh run directory) then rebuilt everything from the raw files:
  * all files re-patched (38 VMP250, 44 VMP5500 plus 1 link to an unedited raw file);
  * perturb processed every file (0 skipped as up to date);
  * no links to other runs.
* `scripts/check_reproduction.py` compared all 51 CSV tables and NetCDF products under the step directories (logs, provenance fields, perturb working trees and patched copies excluded): 0 differ beyond relative tolerance 1e-9, and none missing. Report: `outputs/repro_baseline/reproduction_check.json`.
* The chain from raw .p files to exported products is reproducible with one command (`python src/run_pipeline.py --config config/config.yaml [--sensitivity NAME]`).
