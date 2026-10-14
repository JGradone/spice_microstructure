# SPICE microstructure products: `an_mlgrad001`

Product version 0.1. spice_microstructure git 12bc442adbe629d2abdc2d83268f8c65b9e56674; config sha256 cfdcbeb5535c; microstructure-tpw 0.4.0 (ebec847c157051d6835ebf2d8ac9553166c01880); exported 2026-10-14T17:23:04+00:00.

(This summary regenerated 2026-10-14T18:34:00Z from the run's existing reports.)

Baseline: all VMP casts from raw on the pinned package version with shipboard parameters.

**Sensitivity run** of `baseline`, based on `fft2_diss8_mle`. Overrides: `perturb.epsilon.fft_sec` = 2.0, `perturb.epsilon.diss_sec` = 8.0, `perturb.epsilon.overlap_sec` = 4.0, `perturb.chi.fft_sec` = 2.0, `perturb.chi.diss_sec` = 8.0, `perturb.chi.overlap_sec` = 4.0, `perturb.chi.fit_method` = mle, `regimes.staircase.rollo2022.ml_grad` = 0.001.

Specification of every variable: `docs/products.md`. Methods and the reasons behind them: `docs/decisions.md`. Rerun: `python src/run_pipeline.py --config config/config.yaml --sensitivity an_mlgrad001`.

## Settings

| Setting | Value |
|---|---|
| FFT / dissipation length | 2 s / 8 s (overlap 4 s) |
| chi fit | mle, kraichnan, FP07 single_pole |
| shear epsilon | refit from 1 Hz |
| noise floors | kept, flagged below 2x floor, bounded value provided |
| segment QC applied | False |
| background gradients | linear fits over 10 m |
| Turner class scale | 25 m |
| staircase thresholds (ml_grad) | vdb2021 0.0005, rollo2022 0.001 |
| epsilon in chi_expected | shear |
| gamma | 0.5, 0.65, 0.7 |
| depth bins (tests / products) | 25 m / 5 m |

## Files

| File | Contents |
|---|---|
| `attribution_vmp250.csv` | finger fraction 1 - 1/E against each baseline (Gamma 0.2 theory, Garrett-Munk, Re_b-matched control) with intervals |
| `attribution_vmp5500.csv` | finger fraction 1 - 1/E against each baseline (Gamma 0.2 theory, Garrett-Munk, Re_b-matched control) with intervals |
| `binned_vmp250.nc` | per profile in depth bins: window means of epsilon and chi with counts, and the hydrography |
| `binned_vmp5500.nc` | per profile in depth bins: window means of epsilon and chi with counts, and the hydrography |
| `cast_metrics_vmp250.csv` | per-profile finger metrics: salinity maximum, R_rho, finger fraction, staircase occurrence and geometry, K_T relative to Garrett-Munk |
| `cast_metrics_vmp5500.csv` | per-profile finger metrics: salinity maximum, R_rho, finger fraction, staircase occurrence and geometry, K_T relative to Garrett-Munk |
| `casts_vmp250.csv` | one row per profile: time, position, station, tow-yo, exclusions (file or profile), cautions, probe serials and sensitivities, Sealog notes |
| `casts_vmp5500.csv` | one row per profile: time, position, station, tow-yo, exclusions (file or profile), cautions, probe serials and sensitivities, Sealog notes |
| `diffusivity_vmp250.csv` | bin averages over windows and profiles by group, regime, staircase label, gradient choice and depth: K_T, R_rho, K_S (each gamma), K_S_eps, K_rho, K_GM, 95% profile-bootstrap intervals |
| `diffusivity_vmp250.nc` | bin averages over windows and profiles by group, regime, staircase label, gradient choice and depth: K_T, R_rho, K_S (each gamma), K_S_eps, K_rho, K_GM, 95% profile-bootstrap intervals |
| `diffusivity_vmp5500.csv` | bin averages over windows and profiles by group, regime, staircase label, gradient choice and depth: K_T, R_rho, K_S (each gamma), K_S_eps, K_rho, K_GM, 95% profile-bootstrap intervals |
| `diffusivity_vmp5500.nc` | bin averages over windows and profiles by group, regime, staircase label, gradient choice and depth: K_T, R_rho, K_S (each gamma), K_S_eps, K_rho, K_GM, 95% profile-bootstrap intervals |
| `segments_vmp250.nc` | one record per dissipation window: epsilon and chi per probe and combined, noise floors and flags, epsilon_T, background hydrography, Turner class, staircase labels per method, Re_b, QC bit flags |
| `segments_vmp5500.nc` | one record per dissipation window: epsilon and chi per probe and combined, noise floors and flags, epsilon_T, background hydrography, Turner class, staircase labels per method, Re_b, QC bit flags |

NetCDF files carry this provenance in their global attributes; `*.nc` stays out of git.

## Processing summary

| | vmp250 | vmp5500 |
|---|---|---|
| profiles | 135 | 46 |
| dissipation windows | 12206 | 13562 |
| segment QC flags (applied: False) | 628 (5.1%): near_surface 316, bottom_approach 157, unsteady_speed 83, vibration 72 | 322 (2.4%): near_surface 111, bottom_approach 29, unsteady_speed 45, vibration 137 |
| probe exclusions (windows) | sh2 592 | sh1 626, T2 6680 |
| shear: probe estimates removed | probe_exclusion 583, var_resolved 563 | probe_exclusion 626, var_resolved 110 |
| shear: probes disagree (smaller kept) | 365 | 2862 |
| shear: windows kept | 11940 of 12206 | 13509 of 13562 |
| shear: at noise floor (below 150 dbar) | 39%, median floor 2.0e-10 W/kg | 10%, median floor 1.0e-11 W/kg |
| shear: median epsilon below 150 dbar | 4.5e-10 W/kg | 7.2e-11 W/kg |
| chi: windows kept | 11610 of 12206 | 13384 of 13562 |
| chi: at noise floor (below 150 dbar) | 0.4% | 3.9% |
| epsilon_T roll-off resolved (below 150 dbar) | 38% | 52% |
| salinity source | own | own_ts |
| N2 vs ship CTD, 150-550 m (median ratio; N2<=0) | 1.01; 1% (ship 2%) | 1.11; 16% (ship 1%) |
| windows with T-S salinity invalid (T inversions) | 0 | 1744 |
| Turner class below 150 dbar | strong_finger 4021, finger 1393, not_finger 127, unstable 27, diffusive 26, undefined 8 | finger 5264, strong_finger 3472, not_finger 1317, unstable 923, undefined 465, diffusive 76 |
| staircase windows below 150 dbar (vdb2021) | none 5573, layer 15, interface 9, straddles 5; 5 profiles with interfaces | none 10159, layer 630, straddles 441, interface 287; 44 profiles with interfaces |
| staircase windows below 150 dbar (rollo2022) | none 5104, layer 282, straddles 110, interface 106; 49 profiles with interfaces | none 8760, layer 1275, straddles 982, interface 500; 44 profiles with interfaces |
| median Re_b below 150 dbar (shear) | 9.6 | 5.0 |

## Headline results

Whole cruise, all free-fall casts, finger-favourable water, finescale gradients, staircase labels rollo2022. K in m²/s; brackets are 95% bootstrap intervals over profiles.

| Group | Set | K_T | K_S (γ 0.65) | K_S_eps | K_GM | profiles |
|---|---|---|---|---|---|---|
| vmp250 all free fall | all | 4.9e-06 [3.9e-06, 6.3e-06] | 1.4e-05 [1.1e-05, 1.8e-05] | 2.9e-05 | 2.7e-06 | 119 |
| vmp250 all free fall | interface | 1e-05 [5.4e-06, 1.5e-05] | 2.5e-05 [1.4e-05, 3.7e-05] | 2.5e-05 | 2.6e-06 | 16 |
| vmp250 all free fall | layer | 1e-05 [3.8e-06, 3e-05] | 2.2e-05 [8.5e-06, 6.4e-05] | 6.3e-05 | 2.2e-06 | 17 |
| vmp5500 all free fall | all | 5.1e-06 [4.3e-06, 6e-06] | 1.6e-05 [1.4e-05, 1.9e-05] | 2.2e-05 | 2.4e-06 | 44 |
| vmp5500 all free fall | interface | 6.4e-06 [4.7e-06, 8.6e-06] | 1.7e-05 [1.3e-05, 2.4e-05] | 1.4e-05 | 2.5e-06 | 44 |
| vmp5500 all free fall | layer | 3e-06 [2.1e-06, 4.2e-06] | 9.7e-06 [7.1e-06, 1.4e-05] | 8.1e-05 | 2.1e-06 | 44 |
| vmp250 all free fall | doubly stable control | 2.4e-06 | – | – | 3e-06 | 120 |
| vmp5500 all free fall | doubly stable control | 2e-06 | – | – | 3.1e-06 | 44 |

Interface finger fraction 1 − 1/E by baseline (finescale gradients). The spread is part of the result; it also depends on the stratification scale (docs/decisions.md).

| Group | Baseline | E | finger fraction |
|---|---|---|---|
| vmp250 all free fall | theory_Gamma0.2 | 3.26 [2.02, 4.14] | 0.69 |
| vmp250 all free fall | garrett_munk | 3.90 [2.05, 5.79] | 0.74 |
| vmp250 all free fall | matched_control | 1.88 [1.15, 2.46] | 0.47 |
| vmp5500 all free fall | theory_Gamma0.2 | 4.17 [2.89, 6.03] | 0.76 |
| vmp5500 all free fall | garrett_munk | 2.57 [1.91, 3.47] | 0.61 |
| vmp5500 all free fall | matched_control | 1.68 [1.15, 2.61] | 0.40 |

## Uncertainty

Bootstrap over profiles, 1000 samples (seed 20260812). dd_pooled: 906/978 pooled estimates with intervals; dd_excess: 119/119 pooled estimates with intervals; diffusivity_bins: 413/413 pooled estimates with intervals. Records with fewer than 3 profiles are flagged.

## Caveats

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral (intrusive) finescale gradients can also produce chi (finescale gradient variants are provided).
* The ratio <chi_obs>/<chi_exp> is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency; in salt fingering the true buoyancy flux is upgradient.
* Shear epsilon near the noise floor is flagged (at_floor) and bounded (epsilon_shear_bounded = max(eps, floor)); flagged windows are kept.
* K_S = R_rho K_T / gamma assumes finger-dominated fluxes; gamma (0.5-0.7) is poorly constrained; K_S is given only where finger-favourable and 1 < R_rho <= diffusivities.k_s_max_r_rho.
* VMP5500 salinity is from each cast's own T-S relation (FP07 temperature); its S_z, R_rho and Turner angle follow the T-S slope, and windows in temperature inversions are flagged ts_salinity_invalid.
* chi depends on the FP07 response model (single pole, speed-dependent tau) by a factor ~1.4-1.8 against a double-pole model (decisions.md 2026-10-13).
* The finger fraction depends on the baseline (Gamma = 0.2 theory, Garrett-Munk, Re_b-matched control); the spread across baselines is part of the result.
