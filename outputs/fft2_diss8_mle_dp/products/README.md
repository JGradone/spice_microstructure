# SPICE microstructure products: `fft2_diss8_mle_dp`

Product version 0.5. spice_microstructure git 1625108a14e820888b7f649d284e718fe8457df8-dirty; config sha256 8ebfacd3d409; microstructure-tpw 0.4.0 (c90ff7fefa4c4ab6bd3020ac1b2671e80d9276c4); exported 2026-10-29T16:54:47+00:00.

**Sensitivity run** of `baseline`, based on `fft2_diss8_mle`. Overrides: `perturb.epsilon.fft_sec` = 2.0, `perturb.epsilon.diss_sec` = 8.0, `perturb.epsilon.overlap_sec` = 4.0, `perturb.chi.fft_sec` = 2.0, `perturb.chi.diss_sec` = 8.0, `perturb.chi.overlap_sec` = 4.0, `perturb.chi.fit_method` = mle, `perturb.epsilon.record_locked_shear` = True, `perturb.chi.fp07_model` = double_pole.

Specification of every variable: `docs/products.md`. Methods and the reasons behind them: `docs/decisions.md`. Rerun: `python src/run_pipeline.py --config config/config.yaml --sensitivity fft2_diss8_mle_dp`.

## Settings

| Setting | Value |
|---|---|
| FFT / dissipation length | 2 s / 8 s (overlap 4 s) |
| chi fit | mle, kraichnan, FP07 double_pole |
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
| `attribution_vmp250.csv` | finger fraction 1 - 1/E against each baseline (Gamma 0.2 theory, Garrett-Munk, Re_b-matched non-staircase finger water at the same depths) with intervals |
| `attribution_vmp5500.csv` | finger fraction 1 - 1/E against each baseline (Gamma 0.2 theory, Garrett-Munk, Re_b-matched non-staircase finger water at the same depths) with intervals |
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
| profiles | 135 | 44 |
| dissipation windows | 12206 | 13554 |
| segment QC flags (applied: False) | 628 (5.1%): near_surface 316, bottom_approach 157, unsteady_speed 83, vibration 72 | 314 (2.3%): near_surface 105, bottom_approach 27, unsteady_speed 45, vibration 137 |
| probe exclusions (windows) | sh2 592 | sh1 2189, T2 6676 |
| shear: probe estimates removed | probe_exclusion 583, var_resolved 563 | probe_exclusion 2189, var_resolved 108 |
| shear: probes disagree (smaller kept) | 365 | 1081 |
| shear: windows kept | 11940 of 12206 | 13509 of 13554 |
| shear: at noise floor (below 150 dbar) | 39%, median floor 2.0e-10 W/kg | 13%, median floor 8.3e-12 W/kg |
| shear: median epsilon below 150 dbar | 4.5e-10 W/kg | 4.3e-11 W/kg |
| chi: windows kept | 11806 of 12206 | 13466 of 13554 |
| chi: at noise floor (below 150 dbar) | 0.4% | 3.9% |
| epsilon_T roll-off resolved (below 150 dbar) | 73% | 88% |
| salinity source | own | own_ts |
| N2 vs ship CTD, 150-550 m (median ratio; N2<=0) | 1.01; 1% (ship 2%) | 1.11; 16% (ship 2%) |
| windows with T-S salinity invalid (T inversions) | 0 | 1744 |
| Turner class below 150 dbar | strong_finger 4021, finger 1393, not_finger 127, unstable 27, diffusive 26, undefined 8 | finger 5263, strong_finger 3471, not_finger 1318, unstable 924, undefined 465, diffusive 76 |
| staircase windows below 150 dbar (vdb2021) | none 5573, layer 15, interface 9, straddles 5; 5 profiles with interfaces | none 10159, layer 630, straddles 440, interface 288; 44 profiles with interfaces |
| staircase windows below 150 dbar (rollo2022) | none 4867, layer 385, straddles 207, interface 143; 72 profiles with interfaces | none 8088, layer 1624, straddles 1291, interface 514; 44 profiles with interfaces |
| median Re_b below 150 dbar (shear) | 9.6 | 3.2 |

## Headline results

Whole cruise, all free-fall casts, finger-favourable water, finescale gradients, staircase labels rollo2022. K in m²/s; brackets are 95% bootstrap intervals over profiles.

| Group | Set | K_T | K_S (γ 0.65) | K_S_eps | K_GM | profiles |
|---|---|---|---|---|---|---|
| vmp250 all free fall | all | 2.6e-06 [2.1e-06, 3.2e-06] | 7.2e-06 [6e-06, 8.9e-06] | 2.9e-05 | 2.7e-06 | 127 |
| vmp250 all free fall | interface | 3.3e-06 [2.4e-06, 4.6e-06] | 8.3e-06 [6.1e-06, 1.1e-05] | 2.1e-05 | 2.6e-06 | 32 |
| vmp250 all free fall | layer | 4.3e-06 [2.6e-06, 7.7e-06] | 9.4e-06 [5.9e-06, 1.7e-05] | 5.8e-05 | 2.2e-06 | 40 |
| vmp5500 all free fall | all | 2.8e-06 [2.4e-06, 3.3e-06] | 9.1e-06 [7.7e-06, 1.1e-05] | 1.8e-05 | 2.4e-06 | 44 |
| vmp5500 all free fall | interface | 3.7e-06 [2.8e-06, 4.6e-06] | 9.8e-06 [7.5e-06, 1.2e-05] | 1.1e-05 | 2.5e-06 | 44 |
| vmp5500 all free fall | layer | 2.7e-06 [2.2e-06, 3.2e-06] | 8.4e-06 [6.8e-06, 1e-05] | 3.9e-05 | 2.1e-06 | 44 |
| vmp250 all free fall | finger water, no staircase (control) | 2.4e-06 | – | – | 2.7e-06 | 127 |
| vmp5500 all free fall | finger water, no staircase (control) | 2.4e-06 | – | – | 2.5e-06 | 44 |

Interface finger fraction 1 − 1/E by baseline (finescale gradients). The spread is part of the result; it also depends on the stratification scale (docs/decisions.md).

| Group | Baseline | E | finger fraction |
|---|---|---|---|
| vmp250 all free fall | theory_Gamma0.2 | 1.50 [1.17, 1.87] | 0.33 |
| vmp250 all free fall | garrett_munk | 1.30 [0.95, 1.78] | 0.23 |
| vmp250 all free fall | nonstaircase_control | 1.48 [1.13, 1.90] | 0.33 |
| vmp5500 all free fall | theory_Gamma0.2 | 2.62 [2.01, 3.35] | 0.62 |
| vmp5500 all free fall | garrett_munk | 1.47 [1.13, 1.86] | 0.32 |
| vmp5500 all free fall | nonstaircase_control | 1.32 [1.00, 1.71] | 0.24 |

## Uncertainty

Bootstrap over profiles, 1000 samples (seed 20260812). dd_pooled: 812/856 pooled estimates with intervals; dd_excess: 63/63 pooled estimates with intervals; diffusivity_bins: 357/357 pooled estimates with intervals. Records with fewer than 3 profiles are flagged.

## Caveats

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral (intrusive) finescale gradients can also produce chi (finescale gradient variants are provided).
* The ratio <chi_obs>/<chi_exp> is a dissipation ratio relative to Gamma = 0.2, not a mixing efficiency; in salt fingering the true buoyancy flux is upgradient.
* Shear epsilon near the noise floor is flagged (at_floor) and bounded (epsilon_shear_bounded = max(eps, floor)); flagged windows are kept.
* K_S = R_rho K_T / gamma assumes finger-dominated fluxes; gamma (0.5-0.7) is poorly constrained; K_S is given only where finger-favourable and 1 < R_rho <= diffusivities.k_s_max_r_rho.
* VMP5500 salinity is from each cast's own T-S relation (FP07 temperature); its S_z, R_rho and Turner angle follow the T-S slope, and windows in temperature inversions are flagged ts_salinity_invalid.
* chi depends on the FP07 response model (single pole, speed-dependent tau) by a factor ~1.4-1.8 against a double-pole model (decisions.md 2026-10-13).
* The finger fraction depends on the baseline (Gamma = 0.2 theory, Garrett-Munk, Re_b-matched non-staircase finger water at the same depths, a lower bound); the spread across baselines is part of the result.
