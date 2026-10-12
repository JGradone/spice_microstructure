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
