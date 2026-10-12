# Exported products

The `export` step writes the products below to `<output_root>/<run.name>/products/`. These files are the interface to analyses done outside this repository. Everything upstream of them is internal and may change between runs; the products change only with a `products.product_version` bump, recorded in `docs/decisions.md`.

Status: specification. Nothing is written yet; refine this as the steps are implemented.

## Common to every file

* Format: NetCDF-4, CF-1.13 and ACDD-1.3 metadata (`products` section of the config).
* One set of files per instrument (`vmp250`, `vmp5500`), with the instrument model and serial in global attributes.
* Provenance attributes: `product_version`, `run_name`, `config_sha256`, `git_commit` (flagged `-dirty` if the tree had uncommitted changes), `microstructure_tpw_version` and `microstructure_tpw_commit`, `python_version`, `date_created`, and the archive manifests verified for the run.
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
* `Re_b` (buoyancy Reynolds number), regime label (Turner class), and one staircase label (interface, layer, or none) per detection method (`staircase_vdb2021`, `staircase_rollo2022`, and `staircase_ml` when ML labels are supplied)
* QC bit flags with a `flag_meanings` attribute

No diffusivities at this level. K_T and K_S computed per segment are biased where T_z or S_z approach zero (CLAUDE.md, steps 7 and 8). Users who need their own averages should average epsilon, chi and the gradients here, then form diffusivities from the averages.

## 3. Binned profiles: `binned_<instrument>.nc`

The segment variables averaged into depth bins of `products.depth_bin_m` per profile (dimensions `profile`, `depth`), with the number of segments per bin. Arithmetic means for epsilon and chi; the averaging method is recorded per variable in its `cell_methods` attribute.

## 4. Diffusivities: `diffusivity_<instrument>.nc`

Bin-averaged over profiles, by regime (Turner class x interface or layer), depth bin, and station group:

* `chi_observed`, `chi_expected` (2 K_rho T_z^2 with K_rho = 0.2 epsilon / N2) and their ratio of averages
* `K_T` = <chi> / (2 <T_z^2>)
* `K_S` = R_rho K_T / gamma, and the independent check `K_S_eps` = epsilon (R_rho - 1) / [N2 (1 - gamma)]
* `K_rho` = 0.2 <epsilon> / <N2>, provided only where the regime is not finger dominated
* Each with bootstrap confidence intervals over profiles (`*_ci_low`, `*_ci_high`, `bootstrap_samples`, `random_seed`) and the number of profiles and segments in the average
* The epsilon source (shear or thermistor), gamma, and the regime and staircase thresholds used, as attributes

Sensitivity runs (different gamma, smoothing scale, epsilon source, and so on) write the same files under their own `run.name`, so downstream code can compare runs by swapping one directory.

## Caveats carried as metadata

* Osborn and Cox assumes local production of thermal variance balances dissipation; lateral finescale gradients could also produce chi.
* The dissipation ratio is a diagnostic, not a mixing efficiency (`docs/decisions.md`).
* Shear epsilon near 1e-10 W/kg is at the noise floor; flagged segments are kept, with the flag set.
