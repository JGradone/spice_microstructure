# Recommended SPICE microstructure products

Copies of the products of run **`fft2_diss8_mle`**: 2 s FFT / 8 s windows, chi by mle, FP07 single_pole. These are the files to take into other analyses. Built 2026-11-18T14:42:42Z by `scripts/publish_recommended.py` from `outputs/fft2_diss8_mle/products` (exported with spice_microstructure git 6eeb239115fdccebc550a4b7914f896937eff3f0, config sha256 8cf6ba0c97bb, microstructure-tpw c90ff7fefa4c4ab6bd3020ac1b2671e80d9276c4). Do not edit; rebuild with the script.

`RUN_SUMMARY.md` has the full settings, file list, QC counts and caveats of the run. Variable definitions: `docs/products.md`; methods and reasons: `docs/decisions.md`.

## What to use

* **Start here for nitrate fluxes:** `diffusivity_primary_<instrument>.csv` (or `.nc`). One diffusivity profile per group (`all free fall` = whole cruise, `process_station free fall`), 25 m bins from 20 dbar, primary choices only (rollo2022 staircase labels, finescale gradients, γ 0.65): `K_T` and `K_rho` of all water, `K_S` of the finger-favourable water with its 95% interval and γ range (`K_S_gamma_low`/`_high`), the finger-favourable fraction, `K_GM`, and `K_nitrate` with `K_nitrate_source`. `K_nitrate` is `K_S` where at least 0.5 of the bin is finger-favourable and K_S is defined, else `K_T` of all water; K_N ≈ K_S in fingering is an assumption to state. Use rows with `min_profiles_ok` true. The values are the same as in the full table below.
* **Fine-scale finger fluxes in single profiles:** `finger_profiles_<instrument>.nc`. One record per dissipation window (about 6 m tall, 3 m apart) in each profile, from 20 dbar: `K_S` (all of chi finger-driven) and `K_S_finger` (after removing the shear-turbulence part) in finger-favourable windows, with `K_T`, `K_rho`, the ingredients and `finger_flags`. Pair with a nitrate gradient over the same window. Single windows vary by about ×3 from one to the next (patchy mixing); to average, average chi, `T_z2_fine`, epsilon and N2 first, never the per-window K (`docs/products.md` 4b).
* **All variants of the diffusivities:** `diffusivity_<instrument>.csv` (or `.nc`). In finger-favourable water use `K_S_g<gamma>` (salt diffusivity; nitrate behaves like salt in fingering, K_N ≈ K_S is an assumption to state). Use `K_T` for heat and, outside finger water, `K_rho` (flag `K_rho_valid`). Take `gradients = finescale` as the primary estimate and report the others as sensitivity; take `method = rollo2022` (tuned staircase labels; `vdb2021` is the published-threshold alternative). Groups: `<instrument> all free fall` for cruise-wide averages, `process_station free fall` for the station (a `tow-yo` group appears only for casts in config `towyo`, none at present; never pool it with free fall). `depth_bin = pooled` for whole-depth values, numeric depth bins for profiles. Use rows with `min_profiles_ok` true; `K_S_applicable` marks where K_S is defined.
* **Finger contribution:** `attribution_<instrument>.csv`. Report the range across `baseline` values, not a single number.
* **Mesoscale comparisons (cast to cast):** `cast_metrics_<instrument>.csv` with `casts_<instrument>.csv` (time, position, flags).
* **Your own averages:** `segments_<instrument>.nc` (one record per window). Average epsilon, chi and gradients over windows and profiles first, then form diffusivities; never per window. Respect the QC flags and `shear_keep`, `chi_keep`, `ts_salinity_invalid`.
* **Profiles:** `binned_<instrument>.nc` (5 m bins per profile).

## Headline values and uncertainty ranges

Finger-favourable water, whole cruise, finescale gradients (m²/s). Processing range = across sensitivity runs (stratification scale 5/10/25 m, 10 m bins, staircase threshold, α/β window). Interface excess E is over the Re_b-matched non-staircase finger water at the same depths.

| | K_S (γ 0.65) [95% CI] | K_S for γ 0.7–0.5 | K_S processing range | K_S with double-pole FP07 | K_T | K_GM | interface E, processing range | interface finger fraction across baselines |
|---|---|---|---|---|---|---|---|---|
| vmp250 | 1.4e-05 [1.1e-05, 1.7e-05] | 1.3e-05–1.8e-05 | 1.4e-05–1.4e-05 | ×0.53 | 4.9e-06 | 2.7e-06 | 0.88–1.9 | 0.33–0.64 |
| vmp5500 | 1.6e-05 [1.4e-05, 1.9e-05] | 1.5e-05–2.1e-05 | 1.6e-05–1.7e-05 | ×0.56 | 5.1e-06 | 2.4e-06 | 1.1–1.6 | 0.27–0.79 |

Reading: K_S is robust to processing choices; the FP07 response model (×~0.5 with double-pole) and γ are its main uncertainties. The interface excess and finger fraction depend on the baseline and on the stratification scale; report them as ranges. `sensitivity_summary.csv` / `.png` give every run.

## Caveats

See `RUN_SUMMARY.md` (Caveats).
