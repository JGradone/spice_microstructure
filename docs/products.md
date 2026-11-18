# Exported products

The `export` step writes the products below to `<output_root>/<run.name>/products/`. These files are the interface to analyses done outside this repository. Everything upstream of them is internal and may change between runs; the products change only with a `products.product_version` bump, recorded in `docs/decisions.md`.

Status: written by the `export` step (product version 0.7, 2026-11-18). Scope: microstructure only; nitrate, productivity and grazing data are combined with these products outside this repository.

## Common to every file

* Format: NetCDF-4, CF-1.13 and ACDD-1.3 metadata (`products` section of the config).
* One set of files per instrument (`vmp250`, `vmp5500`), with the instrument model and serial in global attributes.
* Provenance attributes: `product_version`, `run_name`, `run_notes` (the run's own description; since 0.7, sensitivity runs no longer carry the baseline's), `config_sha256`, `git_commit` (flagged `-dirty` if the tree had uncommitted changes), `microstructure_tpw_version` and `microstructure_tpw_commit`, `python_version`, `date_created`, and the archive manifests verified for the run.
* Time in UTC; position from the Sealog ship track (`lat`, `lon`, with the time gap to the nearest fix).
* Every exclusion and caution from the config (`exclude`, `exclude_probes`, `flag`, `towyo`) is carried as a flag variable or attribute, never as silently missing data.

## 1. Cast table: `casts_<instrument>.csv` (and the same table inside each NetCDF file)

One row per profile: instrument, file, profile number, start and end time, lat, lon, max pressure, station label (`process_station` or none), tow-yo flag, exclusion reason, caution flag, probe serials and sensitivities (sh1, sh2, T1, T2), and matched Sealog notes.

## 2. Dissipation segments: `segments_<instrument>.nc`

One record per dissipation window per profile (dimension `segment`), at native resolution:

* `pressure`, `depth`, `time`, `fall_speed`
* `epsilon_sh1`, `epsilon_sh2`, `epsilon_shear` (combined), figure of merit, fraction of variance resolved, noise-floor flag
* `chi_T1`, `chi_T2`, `chi` (combined), `epsilon_T` (from the Kraichnan fit), fit quality
* Background hydrography at the configured smoothing scale: `SA`, `CT`, `N2`, `T_z`, `S_z`, `alpha`, `beta`, `R_rho`, `turner_angle`
* `T_z2_fine` (since 0.6): mean squared temperature gradient on the 1 m hydrography grid over the window, the finescale gradient choice. With it, K_T = <chi> / (2 <T_z2_fine>) can be formed from averages for any grouping; the diffusivity product's `finescale` records use exactly this.
* `Re_b` (buoyancy Reynolds number), regime label (Turner class), and one staircase label (interface, layer, or none) per detection method (`staircase_vdb2021`, `staircase_rollo2022`, and `staircase_ml` when ML labels are supplied)
* QC bit flags with a `flag_meanings` attribute

No diffusivities at this level. K_T and K_S computed per segment are biased where T_z or S_z approach zero (CLAUDE.md, steps 7 and 8). Users who need their own averages should average epsilon, chi and the gradients here, then form diffusivities from the averages.

## 3. Binned profiles: `binned_<instrument>.nc`

The segment variables averaged into depth bins of `products.depth_bin_m` per profile (dimensions `profile`, `depth`), with the number of segments per bin. Arithmetic means for epsilon and chi; the averaging method is recorded per variable in its `cell_methods` attribute.

## 4. Diffusivities: `diffusivity_<instrument>.nc`

From the `diffusivities` step (`diffusivity_bins.csv`). Bin averages over windows and profiles, never per window. One record per station group (process station, transect, all free fall; tow-yo separate) × staircase method × Turner set (finger-favourable, strong finger, control = finger-favourable outside staircases, all) × staircase label (interface, layer, straddles, none, all) × gradient choice (background 10 m fits, finescale 1 m gradient variance, interface_local for interfaces) × depth bin (`double_diffusion.depth_bin_m`, and pooled). Depth range (since 0.6): depth bins from 20 dbar to the bottom of each instrument's casts (`diffusivities.depth_range_dbar`), so the profiles cover the nitracline and the salinity maximum; `P_top_dbar` and `P_bottom_dbar` give each record's pressure limits (the 20–25 dbar bin is partial). Pooled records cover the double-diffusion test range, 150 dbar to the bottom, as the attribution does. Above the staircases most water is not finger-favourable (all free fall, rollo2022: none above 50 dbar, under 10% at 50–75 dbar, 25–30% at 75–100, 50–60% at 100–125, 80–90% at 125–150): use the `all_turner` records there for K_T and K_rho, and K_S only from the finger-favourable sets.

* `K_T` = <chi> / (2 <T_z^2>) (Osborn and Cox; needs no epsilon)
* `R_rho` = <alpha T_z> / <beta S_z> for the bin
* `K_S_g<gamma>` = R_rho K_T / gamma for each gamma in `diffusivities.gammas` (0.5, 0.65, 0.7), only where finger-favourable and 1 < R_rho <= `k_s_max_r_rho` (`K_S_applicable`). K_S is the diffusivity relevant to nitrate and other low-diffusivity solutes in fingering.
* `K_S_eps_g<gamma>` = <epsilon> (R_rho - 1) / (<N2> (1 - gamma)), the independent finger check
* `K_rho` = 0.2 <epsilon> / <N2>, with `K_rho_valid` false in finger-favourable sets
* `K_GM`, the canonical Garrett-Munk level at the bin's N and latitude (reference only)
* 95% bootstrap intervals over profiles (`*_ci_low`, `*_ci_high`) for K_T, R_rho, K_rho and K_S at the configured gamma; `n_windows`, `n_profiles`, `min_profiles_ok`
* Attributes: epsilon source, gammas, flux coefficient, staircase thresholds, gradient choice

## 4a. Primary diffusivity profiles: `diffusivity_primary_<instrument>.csv` (and `.nc`)

Since 0.7. The starting point for nitrate fluxes: the same values as section 4, with only the primary choices (config `products.primary`: `rollo2022` staircase labels, `finescale` gradients, finger-favourable set `finger_any`, γ = `double_diffusion.flux_ratio_gamma`). One row per group (`all free fall`, `process_station free fall`) and depth bin, from 20 dbar.

* `depth_bin`, `P_top_dbar`, `P_bottom_dbar`, `n_profiles`, `n_windows`, `min_profiles_ok` (all water)
* `finger_fraction`: fraction of the bin's windows that are finger-favourable
* `K_T`, `K_rho` with 95% intervals: all water. `K_rho` is not a valid diffusivity where fingers dominate.
* `K_S` with 95% intervals: finger-favourable water at the primary γ; `K_S_gamma_low` and `K_S_gamma_high` at the largest and smallest γ in `diffusivities.gammas`. Empty where K_S is not defined (R_rho outside 1 to `k_s_max_r_rho`) or the finger water has too few profiles. `R_rho_finger`, `n_profiles_finger`.
* `K_GM`: Garrett–Munk reference.
* `K_nitrate`, its 95% interval, and `K_nitrate_source`: `K_S` where `finger_fraction` ≥ `products.primary.finger_fraction_min` (0.5) and K_S is defined, else `K_T` of all water. This is a suggestion, not a method: it assumes K_N = K_S in fingering and treats a bin as finger-dominated or not, so bins near the threshold can switch between instruments. The underlying columns are all in the file.

## 5. Finger attribution: `attribution_<instrument>.csv`

The finger fraction of the heat-variance budget, f = 1 - 1/E, for finger-favourable water (all, interfaces, layers, non-staircase) against each baseline of the ladder: Gamma = 0.2 theory, the Garrett-Munk level, and the Re_b-matched non-staircase finger water at the same depths (`nonstaircase_control`, interfaces and layers only; a lower bound on the finger fraction, since the control itself is finger-favourable), with 95% intervals. The spread across baselines is the baseline uncertainty and is part of the result (decisions.md 2026-10-14).

## 6. Per-cast finger metrics: `cast_metrics_<instrument>.csv`

One row per profile, for comparison with mesoscale fields: time and position, salinity maximum depth and value, finger-favourable fraction, R_rho median, depth range of finger water, staircase fraction per method, number of interfaces and median interface temperature and salinity jumps and thickness, median layer thickness, K_T in finger water and at interfaces (finescale) and their ratio to K_GM, mean epsilon and chi.

## Caveats carried as metadata

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral finescale gradients could also produce chi.
* The dissipation ratio is a diagnostic, not a mixing efficiency (`docs/decisions.md`).
* Shear epsilon near 1e-10 W/kg is at the noise floor; flagged segments are kept, with the flag set.
