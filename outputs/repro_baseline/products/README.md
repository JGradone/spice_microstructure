# SPICE microstructure products (repro_baseline)

Product version 0.1; spice_microstructure git 073d8c927ac297c78efc83f49fdd9cbdfdcd3135; config sha256 b6c42334ac2b; microstructure-tpw 0.4.0 (ebec847c157051d6835ebf2d8ac9553166c01880); created 2026-10-14T18:29:48+00:00.

Run overrides: {}

Specification: docs/products.md. Methods and decisions: docs/decisions.md.

## Files

* `attribution_vmp250.csv`
* `attribution_vmp5500.csv`
* `binned_vmp250.nc`
* `binned_vmp5500.nc`
* `cast_metrics_vmp250.csv`
* `cast_metrics_vmp5500.csv`
* `casts_vmp250.csv`
* `casts_vmp5500.csv`
* `diffusivity_vmp250.csv`
* `diffusivity_vmp250.nc`
* `diffusivity_vmp5500.csv`
* `diffusivity_vmp5500.nc`
* `segments_vmp250.nc`
* `segments_vmp5500.nc`

## Caveats

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral (intrusive) finescale gradients can also produce chi (finescale gradient variants are provided).
* The ratio <chi_obs>/<chi_exp> is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency; in salt fingering the true buoyancy flux is upgradient.
* Shear epsilon near the noise floor is flagged (at_floor) and bounded (epsilon_shear_bounded = max(eps, floor)); flagged windows are kept.
* K_S = R_rho K_T / gamma assumes finger-dominated fluxes; gamma (0.5-0.7) is poorly constrained; K_S is given only where finger-favourable and 1 < R_rho <= diffusivities.k_s_max_r_rho.
* VMP5500 salinity is from each cast's own T-S relation (FP07 temperature); its S_z, R_rho and Turner angle follow the T-S slope, and windows in temperature inversions are flagged ts_salinity_invalid.
* chi depends on the FP07 response model (single pole, speed-dependent tau) by a factor ~1.4-1.8 against a double-pole model (decisions.md 2026-10-13).
* The finger fraction depends on the baseline (Gamma = 0.2 theory, Garrett-Munk, Re_b-matched control); the spread across baselines is part of the result.
