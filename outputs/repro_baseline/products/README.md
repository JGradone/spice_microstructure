# SPICE microstructure products: `repro_baseline`

Product version 0.1. spice_microstructure git 073d8c927ac297c78efc83f49fdd9cbdfdcd3135; config sha256 b6c42334ac2b; microstructure-tpw 0.4.0 (ebec847c157051d6835ebf2d8ac9553166c01880); exported 2026-10-14T18:29:50+00:00.

(This summary regenerated 2026-10-14T18:34:00Z from the run's existing reports.)

Baseline: all VMP casts from raw on the pinned package version with shipboard parameters.

**Sensitivity run** of `baseline`. Overrides: .

Specification of every variable: `docs/products.md`. Methods and the reasons behind them: `docs/decisions.md`. Rerun: `python src/run_pipeline.py --config config/config.yaml --sensitivity repro_baseline`.

## Settings

| Setting | Value |
|---|---|
| FFT / dissipation length | 4 s / 16 s (overlap 8 s) |
| chi fit | iterative, kraichnan, FP07 single_pole |
| shear epsilon | refit from 1 Hz |
| noise floors | kept, flagged below 2x floor, bounded value provided |
| segment QC applied | False |
| background gradients | linear fits over 10 m |
| Turner class scale | 25 m |
| staircase thresholds (ml_grad) | vdb2021 0.0005, rollo2022 0.002 |
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
| profiles | 131 | 46 |
| dissipation windows | 6002 | 6749 |
| segment QC flags (applied: False) | 266 (4.4%): near_surface 127, bottom_approach 12, unsteady_speed 94, vibration 33 | 157 (2.3%): near_surface 45, bottom_approach 1, unsteady_speed 44, vibration 67 |
| probe exclusions (windows) | sh2 291 | sh1 312, T2 3324 |
| shear: probe estimates removed | probe_exclusion 286, var_resolved 272 | probe_exclusion 312, var_resolved 51 |
| shear: probes disagree (smaller kept) | 150 | 1331 |
| shear: windows kept | 5877 of 6002 | 6728 of 6749 |
| shear: at noise floor (below 150 dbar) | 40%, median floor 2.1e-10 W/kg | 10%, median floor 1.1e-11 W/kg |
| shear: median epsilon below 150 dbar | 4.6e-10 W/kg | 8.2e-11 W/kg |
| chi: windows kept | 5715 of 6002 | 6675 of 6749 |
| chi: at noise floor (below 150 dbar) | 0.1% | 2.8% |
| epsilon_T roll-off resolved (below 150 dbar) | 53% | 68% |
| salinity source | own | own_ts |
| N2 vs ship CTD, 150-550 m (median ratio; N2<=0) | 1.01; 1% (ship 2%) | 1.11; 16% (ship 1%) |
| windows with T-S salinity invalid (T inversions) | 0 | 856 |
| Turner class below 150 dbar | strong_finger 1964, finger 685, not_finger 62, diffusive 12, unstable 11 | finger 2631, strong_finger 1728, not_finger 648, unstable 469, undefined 219, diffusive 43 |
| staircase windows below 150 dbar (vdb2021) | none 2722, layer 5, straddles 4, interface 3; 5 profiles with interfaces | none 5123, straddles 301, layer 243, interface 71; 44 profiles with interfaces |
| staircase windows below 150 dbar (rollo2022) | none 2400, layer 148, straddles 145, interface 41; 72 profiles with interfaces | none 4120, straddles 829, layer 687, interface 102; 44 profiles with interfaces |
| median Re_b below 150 dbar (shear) | 9.8 | 5.6 |

## Headline results

Whole cruise, all free-fall casts, finger-favourable water, finescale gradients, staircase labels rollo2022. K in m²/s; brackets are 95% bootstrap intervals over profiles.

| Group | Set | K_T | K_S (γ 0.65) | K_S_eps | K_GM | profiles |
|---|---|---|---|---|---|---|
| vmp250 all free fall | all | 4.5e-06 [3.4e-06, 5.8e-06] | 1.3e-05 [9.7e-06, 1.6e-05] | 2.9e-05 | 2.7e-06 | 119 |
| vmp250 all free fall | interface | 5.5e-06 [3.7e-06, 7.2e-06] | 1.4e-05 [9.7e-06, 1.8e-05] | 3.1e-05 | 2.6e-06 | 15 |
| vmp250 all free fall | layer | 9.4e-06 [9.2e-07, 1.6e-05] | 2.1e-05 [2.1e-06, 3.6e-05] | 0.00012 | 2.2e-06 | 14 |
| vmp5500 all free fall | all | 4.5e-06 [3.6e-06, 5.3e-06] | 1.4e-05 [1.2e-05, 1.7e-05] | 2.3e-05 | 2.4e-06 | 44 |
| vmp5500 all free fall | interface | 5.5e-06 [3.9e-06, 7.1e-06] | 1.5e-05 [1.1e-05, 1.9e-05] | 1.3e-05 | 2.5e-06 | 38 |
| vmp5500 all free fall | layer | 7.3e-06 [4.4e-06, 1.1e-05] | 2.2e-05 [1.4e-05, 3.3e-05] | 5.5e-05 | 2.1e-06 | 44 |
| vmp250 all free fall | doubly stable control | 2.1e-06 | – | – | 3e-06 | 120 |
| vmp5500 all free fall | doubly stable control | 1.7e-06 | – | – | 3.2e-06 | 44 |

Interface finger fraction 1 − 1/E by baseline (finescale gradients). The spread is part of the result; it also depends on the stratification scale (docs/decisions.md).

| Group | Baseline | E | finger fraction |
|---|---|---|---|
| vmp250 all free fall | theory_Gamma0.2 | 1.72 [1.34, 2.50] | 0.42 |
| vmp250 all free fall | garrett_munk | 2.13 [1.43, 2.78] | 0.53 |
| vmp250 all free fall | matched_control | 1.29 [0.96, 1.92] | 0.22 |
| vmp5500 all free fall | theory_Gamma0.2 | 3.50 [2.29, 5.58] | 0.71 |
| vmp5500 all free fall | garrett_munk | 2.24 [1.60, 2.87] | 0.55 |
| vmp5500 all free fall | matched_control | 2.25 [1.37, 3.44] | 0.56 |

## Reproduction check

Rebuilt from the raw files and compared with `outputs/baseline`: 51 files compared, 0 differ beyond relative tolerance 1e-09.

## Uncertainty

Bootstrap over profiles, 1000 samples (seed 20260812). dd_pooled: 892/916 pooled estimates with intervals; dd_excess: 117/117 pooled estimates with intervals; diffusivity_bins: 407/407 pooled estimates with intervals. Records with fewer than 3 profiles are flagged.

## Caveats

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral (intrusive) finescale gradients can also produce chi (finescale gradient variants are provided).
* The ratio <chi_obs>/<chi_exp> is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency; in salt fingering the true buoyancy flux is upgradient.
* Shear epsilon near the noise floor is flagged (at_floor) and bounded (epsilon_shear_bounded = max(eps, floor)); flagged windows are kept.
* K_S = R_rho K_T / gamma assumes finger-dominated fluxes; gamma (0.5-0.7) is poorly constrained; K_S is given only where finger-favourable and 1 < R_rho <= diffusivities.k_s_max_r_rho.
* VMP5500 salinity is from each cast's own T-S relation (FP07 temperature); its S_z, R_rho and Turner angle follow the T-S slope, and windows in temperature inversions are flagged ts_salinity_invalid.
* chi depends on the FP07 response model (single pole, speed-dependent tau) by a factor ~1.4-1.8 against a double-pole model (decisions.md 2026-10-13).
* The finger fraction depends on the baseline (Gamma = 0.2 theory, Garrett-Munk, Re_b-matched control); the spread across baselines is part of the result.
