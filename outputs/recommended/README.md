# Recommended SPICE microstructure products

Copies of the products of run **`fft2_diss8_mle`**: 2 s FFT / 8 s windows, chi by mle, FP07 single_pole. These are the files to take into other analyses. Built 2026-10-14T19:18:25Z by `scripts/publish_recommended.py` from `outputs/fft2_diss8_mle/products` (exported with spice_microstructure git 7a3bde1b85e06f1cf4c3d67046a8e963eb10d279, config sha256 d015710a2441, microstructure-tpw ebec847c157051d6835ebf2d8ac9553166c01880). Do not edit; rebuild with the script.

`RUN_SUMMARY.md` has the full settings, file list, QC counts and caveats of the run. Variable definitions: `docs/products.md`; methods and reasons: `docs/decisions.md`.

## What to use

* **Vertical diffusivities for nutrient (nitrate) fluxes:** `diffusivity_<instrument>.csv` (or `.nc`). In finger-favourable water use `K_S_g<gamma>` (salt diffusivity; nitrate behaves like salt in fingering, K_N ≈ K_S is an assumption to state). Use `K_T` for heat and, outside finger water, `K_rho` (flag `K_rho_valid`). Take `gradients = finescale` as the primary estimate and report the others as sensitivity; take `method = rollo2022` (tuned staircase labels; `vdb2021` is the published-threshold alternative). Groups: `<instrument> all free fall` for cruise-wide averages, `process_station free fall` / `tow-yo` for the station (never pool tow-yo with free fall). `depth_bin = pooled` for whole-depth values, numeric depth bins for profiles. Use rows with `min_profiles_ok` true; `K_S_applicable` marks where K_S is defined.
* **Finger contribution:** `attribution_<instrument>.csv`. Report the range across `baseline` values, not a single number.
* **Mesoscale comparisons (cast to cast):** `cast_metrics_<instrument>.csv` with `casts_<instrument>.csv` (time, position, flags).
* **Your own averages:** `segments_<instrument>.nc` (one record per window). Average epsilon, chi and gradients over windows and profiles first, then form diffusivities; never per window. Respect the QC flags and `shear_keep`, `chi_keep`, `ts_salinity_invalid`.
* **Profiles:** `binned_<instrument>.nc` (5 m bins per profile).

## Headline values and uncertainty ranges

Finger-favourable water, whole cruise, finescale gradients (m²/s). Processing range = across sensitivity runs (stratification scale 5/10/25 m, 10 m bins, staircase threshold, α/β window). Interface excess E is over the Re_b-matched doubly stable control.

| | K_S (γ 0.65) [95% CI] | K_S for γ 0.7–0.5 | K_S processing range | K_S with double-pole FP07 | K_T | K_GM | interface E, processing range | interface finger fraction across baselines |
|---|---|---|---|---|---|---|---|---|
| vmp250 | 1.4e-05 [1.1e-05, 1.8e-05] | 1.3e-05–1.8e-05 | 1.4e-05–1.4e-05 | ×0.49 | 4.9e-06 | 2.7e-06 | 0.6–2.2 | 0.34–0.65 |
| vmp5500 | 1.6e-05 [1.4e-05, 1.9e-05] | 1.5e-05–2.1e-05 | 1.6e-05–1.7e-05 | ×0.54 | 5.1e-06 | 2.4e-06 | 1.1–2.2 | 0.43–0.77 |

Reading: K_S is robust to processing choices; the FP07 response model (×~0.5 with double-pole) and γ are its main uncertainties. The interface excess and finger fraction depend on the baseline and on the stratification scale; report them as ranges. `sensitivity_summary.csv` / `.png` give every run.

## Caveats

See `RUN_SUMMARY.md` (Caveats).
