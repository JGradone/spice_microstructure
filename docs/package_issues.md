# microstructure-tpw: possible problems to report

Running log of anything in microstructure-tpw (`odas_tpw`, CLIs `rsi-tpw` and `perturb`) that looks wrong, fragile, or worth raising with Pat Welch. Pinned version: commit `ebec847` (`requirements.txt`). Each entry gives a status, the evidence, how to reproduce it from this repository, and the related `docs/decisions.md` entry.

Status values:

* **Confirmed**: verified in the code or with a minimal test.
* **Likely**: strong evidence in our data, not yet traced to a line of code.
* **Question**: behaviour that may be intended, but the outcome surprised us or depends on settings in ways users may not expect.
* **Request**: a missing feature that we had to work around.

Before sending, recheck each Likely or Question entry against the current upstream code. Newest entries at the bottom.

---

## 1. `fp07.min_corr` gate falls back silently to nominal FP07 coefficients (Likely)

* Added after 0.3.1, default 0.5. On our VMP-5500 deep casts, no profile reached the lag-correlation gate ("no profile reached the lag correlation gate"), so every profile kept the nominal FP07 coefficients.
* The Rockland production reports state these thermistors are uncalibrated. They read about +3.0 °C (T1) and +3.7 °C (T2) against SBT1.
* Downstream effect: the viscosity uses the wrong temperature, so epsilon came out 5.7% low on both shear probes (5–95%: 0.93–0.97). Chi and the FP07 temperature were also wrong. The run completed without an error.
* Suggestion: when calibration is enabled and fails, either stop or flag it prominently in the output metadata (per profile). Also consider why the T/reference lag correlation is below 0.5 on these casts; SBT1 is a native 64 Hz channel, so `reference_interval` is not the cause.
* Reproduce: `perturb.fp07.min_corr: 0.5` in `config/config.yaml`, run `convert`, compare `T1` with `SBT1` on any VMP-5500 profile, for example SPC_033.
* decisions.md: 2026-10-12, "compare_archive finding: VMP5500 FP07 left uncalibrated by the new version".

## 2. perturb window-scale N2 and dTdz disagree with TEOS-10 on the VMP-5500 (Likely, cause not traced)

* For SPC_033 at 150–250 m, perturb's per-window `N2` is about 4.5× and `dTdz` about 0.43× the values from TEOS-10 on the same profile's CT and SA. The VMP-250 values agree with TEOS-10. The shipboard archive (0.3.1) has identical values.
* The N2 error could come from the VMP-5500's noisy salinity (an instrument problem). The dTdz error cannot: it uses temperature only, so it points at the stratification calculation, its channel choice or its units for this instrument.
* Settings: `perturb.stratification: {enable: true, window: 2.0}`; VMP-5500 CT channels `SBT1`/`SBC1` via `perturb_overrides`.
* Reproduce: compare `N2` and `dTdz` in `outputs/baseline/convert/vmp5500/diss_00/SPC_033_prof001.nc` with `outputs/baseline/hydrography/windows_vmp5500.csv`.
* decisions.md: 2026-10-12, "QC exploration (QC explorer page)".

## 3. Shear epsilon integrates from the lowest wavenumber; result depends on FFT length (Question)

* The variance method integrates the shear spectrum from the first nonzero wavenumber to K_max. In our spectra, the bins below about 1 Hz sit 3–5× above Nasmyth (vehicle motion or other non-turbulent shear). The fitted Nasmyth is then too high through the middle of the range, and FM is high where this is strongest.
* Refitting over 1 Hz to K_max lowers epsilon (median refit/perturb, below 150 dbar):

  | FFT length | VMP-250 | VMP-5500 |
  |---|---|---|
  | 4 s | 0.66 | 0.74 |
  | 2 s | 0.80–0.91 | 0.80–0.91 |

  So perturb's own epsilon depends on the FFT length through this low-frequency energy. After the refit, all three FFT/diss settings agree within 3% in 25 m bin means.
* Suggestion: an optional lower integration limit (`f_min` or `K_min`) for the variance and ISR methods, and a note in the docs that FM thresholds and FM rates depend strongly on the FFT and diss lengths. We saw FM > 1.15 in 13%, 29% and 6% of VMP-250 windows at 4/16 s, 2/16 s and 2/8 s.
* Reproduce: `scripts/explain_fm.py`, `scripts/test_shear_fmin.py`, `scripts/compare_runs.py`.
* decisions.md: 2026-10-13 entries on the FM correction, the 1 Hz refit and the window-length runs.

## 4. FP07 noise model sits well below the observed high-wavenumber floor (Question)

* On both instruments the temperature-gradient spectra have a plateau at about 30–200 cpm: about 5e-7 K² m⁻² cpm⁻¹ (VMP-250) and about 1e-6 (VMP-5500).
* That is 1–2 decades above `spec_noise` at 50 cpm, and it has a different shape: flat, whereas the model rises toward high k.
* For low-chi windows, `K_max_T` often falls inside this plateau. Chi floors computed from `spec_noise` therefore look far safer than they are.
* Possible causes to check: noise-model parameters for these FP07 circuits, the speed-dependent response correction (`fp07_model: single_pole`, tau model `lueck`) amplifying high frequencies, or vibration pickup.
* Reproduce: `outputs/fft2_diss8/thermistor/figures/spectra_gallery_<instrument>.png` (observed against `spec_noise`).
* decisions.md: 2026-10-13, thermistor step (pending).

## 5. epsilon_T from the iterative Kraichnan fit about 1.6–1.8× shear epsilon (Question, pending MLE comparison)

* With `chi.use_epsilon: false` and `fit_method: iterative`, epsilon_T exceeds shear epsilon (shear above its noise floor, below 150 dbar) by a median 1.6–1.8×. That holds even where the fit ends at the noise floor, and outside finger-favourable water (Turner < 45°: 2.0 VMP-250, 1.9 VMP-5500).
* The larger excesses (up to 4–9×) are in finger-favourable windows and may be physical (finger-scale variance). The baseline offset is the part to check against the MLE fit (`fit_method: mle`) before raising it.
* Reproduce: `python src/steps/thermistor.py --config config/config.yaml --sensitivity fft2_diss8`.
* decisions.md: 2026-10-13, thermistor step (pending).

## 6. `perturb` stage subcommands each run the whole pipeline (Request)

* `perturb profiles`, `diss` and `chi` each call the full pipeline (`odas_tpw/perturb/cli.py`), so a stage cannot be rerun on its own from saved output (for example, chi with a different fit method without recomputing profiles and epsilon). Every chi or epsilon variant needs a full `perturb run`.
* decisions.md: 2026-10-12, convert step.

## 7. Minor and documentation

* **Probe naming differs between products:** shear probes are `sh1`/`sh2` in the dissipation files, but thermistors are `T1_dT1`/`T2_dT2` in the chi files.
* **No sensor vertical offsets:** a CT pair 1.57 m above the pressure port on the VMP-5500, and probe tips about 0.3 m below it. Every CT-derived quantity is placed at the pressure-sensor depth (Request).
* **SBE4 conversion omits the CTcor/CPcor term** (`odas_tpw/rsi/channels.py`). It is negligible here, but worth a comment in the code.
