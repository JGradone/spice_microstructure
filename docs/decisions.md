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
