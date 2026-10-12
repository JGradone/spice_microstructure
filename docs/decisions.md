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
