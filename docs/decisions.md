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
