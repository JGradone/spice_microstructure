# Shipboard processing record

Record of the processing done at sea on the 2026 R/V Falkor (too) SPICE expedition, before this repository existed. Compiled 2026-10-12 from the archive directories, the run logs and parameter files inside `vmp250_processed`, the embedded configuration of the .p files, and shell history.

Exact reproduction of these outputs with the shipboard software version has been waived (see `docs/decisions.md`, 2026-10-12). This record documents what was run so that differences between the new baseline and the archive can be interpreted.

## Archived directories

All three live under `SPICE_turbulence/` in the local data area (paths are set in `config/config.yaml`). At sea they were at `~/Desktop/SPICE_turbulence/` and were moved to SynologyDrive by 2026-09-30. Paths embedded in the at-sea outputs and patched files still point at the Desktop location.

| Directory | Contents | Files (manifest entries) | Size | Manifest |
|---|---|---|---|---|
| `vmp250_raw` | 38 original .p files plus 2 YAML files | 40 | 920 MB | `manifests/vmp250_raw.sha256.csv` |
| `vmp250_patched` | 38 patched .p files plus 1 YAML file | 39 | 920 MB | `manifests/vmp250_patched.sha256.csv` |
| `vmp250_processed` | perturb outputs from two output generations, logs, trim cache | 1451 | 2.0 GB | `manifests/vmp250_processed.sha256.csv` |

Manifests skip `.DS_Store`. All three verified OK on 2026-10-12. The VMP5500 (`vmp6000_*`) directories have their own manifests; see that section below.

### vmp250_raw

* `data_0112.p` to `data_0149.p`: 38 consecutive files, none missing, 2.6 MB (`data_0115.p`) to 76 MB (`data_0134.p`). Rockland .p format, VMP250-IR SN537. File dates 2026-08-10 to 2026-08-31.
* `edits.yaml`: the `rsi-tpw patch-config` edit spec, generated from `data_0129.p` on 2026-08-18 (see Patch step).
* `perturb_config.yaml`: an early perturb config (2026-08-14) pointing at `vmp250_raw` with `chi.use_epsilon: true`. It is **stale**: it did not produce the archived outputs (see Processing parameters).
* Note: the two YAML files were written into the raw directory at sea. The .p files themselves were never modified there (patching writes new files elsewhere).

### vmp250_patched

* `data_0112.p` to `data_0149.p`: the same 38 names as raw. Each is 10 903 bytes larger than its raw file (10 937 for 0146 to 0149; see Patch step).
* `perturb_config.yaml`: the config used for processing, last edited 2026-09-30. Its only differences from the raw copy are `p_file_root` and `output_root` (moved to SynologyDrive paths) and `chi.use_epsilon: false`.

### vmp250_processed

perturb appends a `_NN` suffix per output directory whenever the parameter hash changes. The hash includes the file paths, so moving the data created a second generation:

| Generation | Written | Casts | profiles | diss | chi | ctd | binned / combo |
|---|---|---|---|---|---|---|---|
| `_00` | at sea, last run 2026-08-30 08:48 | 33 with profiles (0112 to 0145; 34 files) | 125 nc | 119 nc | 119 nc | 34 nc | 1 nc each |
| `_01` | post cruise, 2026-09-30 11:04 | 37 with profiles (0112 to 0149; 38 files) | 137 nc | 131 nc | 131 nc | 38 nc | 1 nc each |

* Subdirectories per generation: `profiles_NN`, `diss_NN`, `chi_NN`, `ctd_NN`, `profiles_binned_NN`, `diss_binned_NN`, `chi_binned_NN`, `diss_combo_NN`, `chi_combo_NN`, `ctd_combo_NN`, `combo_NN`. Each holds per-cast `.log` files, NetCDF outputs (`data_XXXX_profNNN.nc`, `binned.nc`, `combo.nc`) and a hidden `.params_sha256_<hash>` JSON with the full resolved parameter set.
* `logs/`: three run logs: `run_20260828T183133Z.log` (31 files), `run_20260830T124822Z.log` (34 files), `run_20260930T150103Z.log` (38 files).
* `.cache/trim/`: 38 JSON trim records (patched files referenced in place, not copied).
* Profiles per cast (identical in `_00` and `_01` for shared casts): 0112:3, 0113:3, 0114:6, **0115:0**, 0116:2, 0117:1, 0118:4, 0119:3, 0120:3, 0121:4, 0122:6, 0123:4, 0124:3, 0125:5, 0126:5, 0127:1, 0128:3, 0129:5, 0130:3, 0131:5, 0132:4, 0133:3, 0134:8, 0135:3 to 0140:3 each, 0141:4, 0142:4, 0143:3 to 0149:3 each.
* `_00` is the at-sea result. `_01` uses the same parameters on the same software and adds 0146 to 0149. Use `_01` for the sanity comparison of shared casts and check that `_00` agrees with it.

### VMP6000 / VMP5500 data

* "VMP6000" and "VMP5500" are the same instrument: every `SPC_*.P` header reads `vmp-5500 SN 010`, and the Sealog calls it VMP5500 throughout. There is no separate VMP6000 dataset.
* Location: `SPICE_turbulence/vmp6000_raw` (45 `SPC_*.P` files, SPC_003 to SPC_063 with gaps, plus `SETUP.CFG`, `SETUP_OG_041326.CFG`, `edits.yaml`, `perturb_config.yaml`, `spice_config.yaml`, `bench/`, `results/`), `vmp6000_patched` (45 .P plus `perturb_config.yaml`) and `vmp6000_processed` (one `_00` generation, last written 2026-08-28).
* Processed at sea: yes. Early runs used `rsi-tpw pipeline ../vmp6000_raw/*.P -o ../vmp6000_processed/`, then patched with `rsi-tpw patch-config` and processed with `perturb run --config perturb_config.yaml` in `vmp6000_patched`, in the same way as the VMP250.
* Manifests (all verified 2026-10-12): `manifests/vmp6000_raw.sha256.csv` (54 entries, 1.4 GB, including `bench/` and `results/logs/`), `manifests/vmp6000_patched.sha256.csv` (46, 1.4 GB), `manifests/vmp6000_processed.sha256.csv` (608, 1.2 GB).
* Patch content, checked 2026-10-12 against the Sealog probe history and the cal sheets. Each raw and patched pair was compared with `rsi-tpw config`; the data records are identical in all 45 pairs.
  * **What the patch changed:** pressure `coef0` 29.48 -> 18.48 (an 11 dbar offset; the note "Edited P coef0 to -11" means *by* -11) and `cruise_info` (operator APL -> Rutgers, project, ship). Applied to all 45 files with one spec (`vmp6000_raw/edits.yaml`, author "Joe Gradoner"). Patch timestamps run from 2026-08-20 08:18 (SPC_003 to SPC_033 in one batch) to 2026-08-30 08:38.
  * **Pressure fix checked:** median on-deck pressure in the first and last 30 s is 11 to 12 dbar raw and 0.4 to 1.3 dbar patched (SPC_020, SPC_040, SPC_062). The patched minimum drifts from +0.4 dbar (SPC_020) to -0.4 dbar (SPC_062), so a residual offset of about 1 dbar remains over the cruise.
  * **Shear probes need no patch.** The raw `setup.cfg` was updated aboard at every swap, and serials and sensitivities match the Sealog and the cal sheets in every file: sh1 M3461 (0.1207) to SPC_061 and M3456 (0.1301) from SPC_062; sh2 M3462 (0.1174) in SPC_004, M3244 (0.1031) in SPC_012 to SPC_019, and M3459 (0.1038) from SPC_020. SPC_003 (bench test) has placeholders (M, 0.07).
  * **T2 serial is wrong from SPC_041 on.** The config still says T3304, but the Sealog says T3301 was installed on 2026-08-22 at 14:50 (SPC_041 starts 16:03). This is metadata only: the FP07 coefficients in `setup.cfg` are nominal (beta_1 3143.55, t_0 289.301), identical in every file, and replaced by the in-situ calibration. The pipeline corrects the serial in its patch.
  * **Data problems that the configuration cannot fix:** T2 flat-lined on SPC_040, and sh1 (M3461) showed low response on SPC_060 and SPC_061. These probes are excluded for those files in the config (`exclude_probes`).
  * Shear `cal_date` is empty in every file (cosmetic).
* Patch banner timestamps (both instruments) are laptop local time (UTC-4), not UTC. For example, SPC_040 is stamped 10:09 but started at 10:24 UTC.

## Software environment at sea

* Python version: 3.14.6 (miniforge conda env `turbulence`, created with `conda create -n turbulence python=3.14`).
* microstructure-tpw version: **0.3.1**, installed with `pip install git+https://github.com/mousebrains/turbulence.git`, git commit `81102fc242c18edf3acfdee37c0f40150e8ec8c1`. The import name is `odas_tpw`; the CLIs are `rsi-tpw`, `perturb`, `perturb-diag`, `perturb-plot`.
* perturb engine fingerprint (in every `.params_sha256_*` file, both generations): `ce19d219eac8822274e72622fbf58649c801260c638afc67d43a405764f73866`.
* Evidence that the env is unchanged since the cruise: every patched .p header, from 2026-08-18 to 2026-09-30, is stamped `rsi-tpw patch-config 0.3.1`, and `_00` and `_01` share one engine fingerprint. The freeze below was captured on 2026-10-12 from the env as it is now.
* Key packages: numpy 2.5.1, scipy 1.18.0, xarray 2026.7.0, gsw 3.6.23, netCDF4 1.7.4.
* Full `pip freeze` saved to: `docs/shipboard_pip_freeze.txt`.
* Machine and OS: the author's Mac laptop, macOS (Darwin 25.6.0 as of 2026-10-12).

## Commands run

Recovered from `~/.zsh_history`, which has no timestamps; dates come from the patch headers and run logs. There is no `~/.bash_history`. A filtered copy, keeping original line numbers, is kept locally at `docs/private/shipboard_shell_history.txt`, which is gitignored because it contains unrelated personal command history. Lines 60 to 304 of the history also contain earlier MicroRider glider work that is not part of SPICE.

```
# Environment (history lines 60-72, 178)
conda create -n turbulence python=3.14
conda activate turbulence
pip install git+https://github.com/mousebrains/turbulence.git

# Early perturb runs on the unpatched raw files (lines 443-445, 475), cwd vmp250_raw
perturb run --config perturb_config.yaml

# Build the patch spec (2026-08-18; lines 520-523), cwd vmp250_raw
rsi-tpw config data_0129.p                      # print embedded config
rsi-tpw patch-template data_0129.p -o edits.yaml
#   ...edits.yaml edited by hand (see Patch step)...

# First patch, all files present at the time: data_0112-0129 (line 532)
rsi-tpw patch-config *.p --edits edits.yaml --batch-cal --out ../vmp250_patched/

# Process the patched files (line 537 onward), cwd vmp250_patched
perturb run --config perturb_config.yaml

# Then for each new cast, patch it and rerun perturb (perturb caches finished casts):
rsi-tpw patch-config data_0130.p --edits edits.yaml --out ../vmp250_patched/   # 08-19
rsi-tpw patch-config data_0131.p --edits edits.yaml --out ../vmp250_patched/   # 08-19
rsi-tpw patch-config data_0132.p ... data_0133.p                               # 08-20
rsi-tpw patch-config data_0134.p ...                                           # 08-20
rsi-tpw patch-config data_0135.p ...                                           # 08-22
rsi-tpw patch-config data_0136.p ... data_0137.p                               # 08-23
rsi-tpw patch-config data_0138.p ... ; data_0139.p                             # 08-24
rsi-tpw patch-config data_014* --edits edits.yaml --batch-cal --out ../vmp250_patched/  # 0140-0142, 08-28
rsi-tpw patch-config data_0143.p|0144|0145 --edits edits.yaml --batch-cal --out ../vmp250_patched/  # 08-30
perturb run --config perturb_config.yaml        # last at-sea run, 2026-08-30 08:48 (_00)

# Post cruise, data relocated to SynologyDrive (2026-09-30; lines 997-1011)
rsi-tpw patch-config data_0146.p|0147|0148|0149 --edits edits.yaml --batch-cal --out ../vmp250_patched/
perturb run --config perturb_config.yaml        # in vmp250_raw (line 1005): no log in vmp250_processed; probably failed on the stale Desktop paths
perturb run --config perturb_config.yaml        # in vmp250_patched, repeated 4x; final run 11:01-11:04 (_01)
```

Interactive inspection used throughout (does not produce outputs): `rsi-tpw ql`, `rsi-tpw dl`, `rsi-tpw ml` on individual casts (for example 0113 to 0117, 0129, 0133, 0138, 0139, 0145).

## Patch step

* What was patched: only the shear probe calibration fields in the embedded `setup.cfg` configuration record.

  | Channel | Field | Raw | Patched |
  |---|---|---|---|
  | sh1 | sens | 0.0700 | 0.1215 |
  | sh1 | SN | M | M3464 |
  | sh1 | cal_date | (empty) | 2026/04/07 |
  | sh2 | sens | 0.0700 | 0.1134 |
  | sh2 | SN | M | M2662 |
  | sh2 | cal_date | (empty) | 2023-04-12 |

  `edits.yaml` also lists `instrument_info.vehicle: "VMP"`, but the raw files already had `vehicle = VMP`, so that field was not changed. `diff_gain`, `adc_fs` and `adc_bits` in the spec match the raw values. Verified on all 38 files: the non-comment config differs only in these six lines, and every byte after the config header (the data records) is identical between raw and patched.
* Why it was needed: the instrument's `setup.cfg` carried placeholder shear probe sensitivities (0.0700) and serial numbers. Epsilon scales as sens^-2, so processing raw files would overestimate epsilon by (0.1215/0.07)^2 = 3.0 for sh1 and (0.1134/0.07)^2 = 2.6 for sh2.
* How it was done: `rsi-tpw patch-config <files> --edits edits.yaml [--batch-cal] --out ../vmp250_patched/` (microstructure-tpw 0.3.1). The tool writes new files and never modifies the originals. Each patched header gets a banner (timestamp, author, tool version, absolute source path, note), a `[PATCH ...]` comment above each changed line, and the full original configuration as comments.
* Which files were affected: all 38. Patch timestamps: 0112 to 0129 on 2026-08-18 09:52:21; 0130 and 0131 on 08-19; 0132 and 0133 on 08-20 05:18; 0134 on 08-20 15:02; 0135 on 08-22; 0136 and 0137 on 08-23; 0138 and 0139 on 08-24; 0140 to 0142 on 08-28; 0143 to 0145 on 08-30; 0146 to 0149 on 2026-09-30.
* Reproducibility note: the patched files **cannot be regenerated byte for byte**, because the header embeds the patch timestamp and the absolute source path. That longer SynologyDrive path is why 0146 to 0149 are 34 bytes larger. Compare regenerated patched files on (a) the non-comment config lines and (b) the data records, not on whole-file checksums.
* **Error in the shipboard patch for `data_0112.p`.** The Sealog shows sh2 was probe **M3463** for this cast; it was swapped for M2662 at 04:03 UTC on 2026-08-11, after the test deployments in `data_0112.p` (start 02:08). The shipboard patch wrote M2662 and its sensitivity (0.1134) into every file, so `data_0112.p` sh2 epsilon in the archive uses the wrong sensitivity. That is consistent with this cast's inter-probe ratios being far from 1 and varying (0.086, 0.14, 1.51 across its three profiles), The log gives no reason for removing M3463 after the test casts, so the probe itself may also have been faulty. The pipeline patches per cast range (`patch.probes` in the config), using M3463 sens = 0.1079 (cal 2026-04-07) for `data_0112.p`. With 0.1134 applied instead, the archived sh2 epsilon for that cast is low by (0.1079/0.1134)^2 = 0.91, about 9%. That is far too small to explain ratios of 0.09 to 1.5, so M3463 or the test setup itself was probably faulty, and `data_0112.p` is a candidate for exclusion.
* Checked against the Rockland cal sheets (`SPICE_turbulence/SpiceProbeCalSheets`, manifest `manifests/probe_calsheets.sha256.csv`): M3464 0.1215 (2026-04-07) and M2662 0.1134 (2023-04-12) match the patch. M2662 is a borrowed probe (sheet in `Chant_probe_calsheets/`). Its calibration is 3.5 years old, older than Rockland's recommended annual recalibration, so sh2 sensitivity is less certain than sh1's. Epsilon goes as sens^-2, so a 5% sens error is a 10% epsilon error. Persistent sh1/sh2 offsets should be read with this in mind.

## Processing parameters used

Source of truth: the `.params_sha256_*` JSON files in `vmp250_processed`, which record the resolved parameters for each stage. Both generations are identical apart from paths. Neither `perturb_config.yaml` in the archive is exactly the config of the at-sea run. The raw copy is stale. The patched copy was edited 2026-09-30 (paths), but its `use_epsilon: false` matches the `_00` parameters.

| Parameter | Value | Notes |
|---|---|---|
| FFT length | 4 s | `epsilon.fft_sec`, `chi.fft_sec` |
| Dissipation length | 16 s | `diss_sec: null` resolves to 4 x fft_sec; overlap null resolves to half the window |
| Fall speed limits | `W_min` auto = 0.3 dbar/s (free-fall VMP), `P_min` 0.5 dbar, `min_duration` 7 s, direction down | speed from smoothed dP/dt (`speed.method: pressure`, default tau 1.5 s, `speed_cutout` 0.05 m/s) |
| Launch / bottom trimming | none: `top_trim.enable: false`, `bottom.enable: false` | profiles begin at P > 0.5 dbar once W > 0.3 dbar/s |
| Despiking settings | `despike_thresh` 8, `despike_smooth` 0.5 Hz | |
| Shear spectra | Goodman on, `f_AA` 98 Hz, `f_limit` null (= f_AA), `fit_order` 3, `epsilon_minimum` 1e-13 | |
| Epsilon QC | **`epsilon.fom_max: null` (no spectral fit QC on epsilon)**, no qc drop rules | probe-consistency warnings are logged only |
| Thermistor spectral model and fit | Kraichnan, **Method 2** (`use_epsilon: false`, fits epsilon_T and chi from FP07 spectra), `fit_method: iterative` (not MLE), `fp07_model: single_pole`, Goodman on, `chi.spectral_qc: true`, `chi.fom_max: null`, `chi_minimum` 1e-13 | |
| FP07 calibration | against `JAC_T`, Steinhart-Hart order 2, `max_lag_seconds` 10, lag must be negative | CT alignment on (`JAC_T`, `JAC_C`) |
| Seawater properties | viscosity salinity fixed 35 (`salinity: null`); reference T auto (first plausible of T1, T2, JAC_T) | |
| Stratification | N2 and dT/dz with salinity from conductivity (TEOS-10), 2 dbar window for the profile product; diss uses its dissipation window | |
| Binning | depth, 1 m, mean | |
| GPS / hotel | none (`gps.source: nan`, hotel disabled) | outputs carry no lat/lon |
| Other non default settings | Compared with the 0.3.1 `perturb init` template, only these differ: `epsilon.fft_sec` and `chi.fft_sec` 4 (default 1.0), `chi.enable: true` (default false), `chi.use_epsilon: false` (default true). `chi.spectral_qc: true` is not in the template but is the package default. | |

## Casts

Cast information below comes from the Sealog export (`SPICE_turbulence/sealog/FKt260806_sealog_export.csv`, 95 VMP events) matched to .p header start times (`rsi-tpw info`).

* 48 hour process station, 11.626 N, 50.577 W, 2026-08-19 22:40 to about 2026-08-21 19:30 UTC:
  * VMP250: `data_0132.p` (08-19 22:40, 4 profiles), `data_0133.p` (08-20 01:55, 3 profiles), `data_0134.p` (08-20 13:31 to 16:03, 8 profiles). That makes 15 profiles, matching the 15 VMP250 casts reported. **`data_0134.p` is entirely "Tow-yo line #1" and "#2" (EK80 off), with the ship under way, not free-fall casts from a stationary ship.**
  * VMP5500: `SPC_033.P` (08-20 09:22), `SPC_034.P` (08-20 22:51), `SPC_038.P` (08-21 13:51, only 31 min long), `SPC_039.P` (08-21 18:10). That is four files against the "3 VMP6000" casts reported earlier; `SPC_038.P` may be the incomplete one. TODO: confirm.
  * The "all but one of the 18 casts" result in Early results presumably counts these profiles; recheck which ones were included.
* Second repeated station, 12.857 N, 55.354 W, 2026-08-27 to 08-28: VMP5500 `SPC_055.P` to `SPC_060.P` (six casts in about 20 h); VMP250 `data_0141.p` and `data_0142.p`.
* Other stations: the remaining VMP250 files are one station each along the cruise track (positions in the Sealog; to go in the cast table).

Probe history (Sealog EQUIPMENT and VMP entries):

| Instrument | From (UTC) | sh1 | sh2 | T1 | T2 | Note |
|---|---|---|---|---|---|---|
| VMP250 | 2026-08-11 00:27 | M3464 (0.1215) | M3463 (0.1079) | T3306 | T3308 | T1 dummy probe cable recovered and bench tested; covers `data_0112.p` (test casts) |
| VMP250 | 2026-08-11 04:03 | M3464 (0.1215) | M2662 (0.1134) | T3306 | T3308 | M3463 swapped for M2662 after the test deployments; `data_0113.p` onward, no later changes logged |
| VMP5500 | 2026-08-10 14:40 | M3461 | M3462 | T3303 | T3304 | before the first 500 m test dive (`SPC_004.P`) |
| VMP5500 | 2026-08-11 04:13 | M3461 | M3244 | T3303 | T3304 | M3462 removed, suspected epoxy issue |
| VMP5500 | 2026-08-14 19:38 | M3461 | M3459 | T3303 | T3304 | sh2 slightly noisier than sh1 |
| VMP5500 | 2026-08-22 14:50 | M3461 | M3459 | T3303 | T3301 | T2 flat-lined on `SPC_040.P`; T3304 replaced |
| VMP5500 | 2026-08-28 22:58 | M3456 | M3459 | T3303 | T3301 | sh1 low response on `SPC_060.P` and `SPC_061.P`; M3461 replaced |

Shear probe sensitivities from the Rockland cal sheets (`SPICE_turbulence/SpiceProbeCalSheets`; all calibrated 2026-04-07 unless noted): M3456 0.1301, M3457 0.1100, M3458 0.1092, M3459 0.1038, M3461 0.1207, M3462 0.1174, M3463 0.1079, M3464 0.1215, M3244 0.1031 (2025-04-29), M2662 0.1134 (2023-04-12). M3457 and M3458 do not appear in the Sealog (spares). The FP07 sheets (T3298, T3299, T3301 to T3304, T3306, T3308; production reports dated 2026-03-13) state the thermistors are **uncalibrated**: calibrate them in situ against the JAC CT, as the shipboard run did (`fp07.calibrate`, reference `JAC_T`).

VMP5500 pre-cast battery voltages (15.9 to 16.3 V) are also logged for many casts.

`SPICE_turbulence/VMP5500_VITO_CHANGElog.xlsx` (sha256 `90c8a45f...85f5c9`) records ballast tuning on the first VMP5500 casts:

| Cast | File | Notes |
|---|---|---|
| none | `SPC_003.P` | bench test with test probes; clock set incorrectly |
| 1 | `SPC_004.P` | shallow 500 m; 1 drag element, 1 weight, 0.4 m/s; spiking |
| 2 | `SPC_008.P` | 1000 m; 1 drag element, 1 weight, 0.4 m/s; vibration noise (file not in `vmp6000_raw`) |
| 3 | `SPC_012.P` | 1000 m; 1 drag element, 2 weights, 1.0 m/s; vibration noise |
| 4 | `SPC_014.P` | 1000 m; 2 drag elements, 2 weights, 0.85 m/s; vibration noise |
| 5 | `SPC_015.P` | 1000 m; 2 drag elements, 2 weights, 2 foam, 0.81 m/s; vibration noise |
| 6 | `SPC_016.P` | set for 1000 m, released early at 600 m; release cable taped up; reduced noise |

So VMP5500 casts up to `SPC_015.P` carry vibration noise from the ballast and release setup, and their fall speeds differ (0.4 to 1.0 m/s).

Operating notes per VMP250 cast (Sealog):

| File | Note |
|---|---|
| `data_0112.p` | test casts; sh2 = M3463 (see Patch step) |
| `data_0113.p` | first deployment after the shear probe replacement |
| `data_0114.p` | 6 casts |
| `data_0116.p` | strong upper-layer shear put the line and profiler under the hull; difficult recovery |
| `data_0117.p` | ship at 1.5 kn with 750 ft of line out to keep the line off the hull; heavy sargassum on the line, further casts aborted |
| `data_0118.p` | big swells, sargassum, strong surface current; reached 180 m |
| `data_0119.p` | heavy sargassum, strong winds, good casts, depth limited to 180 m (logged under `data_0118.p`) |
| `data_0120.p` | 4 good casts; rod twisted on its post in a big swell, at a bad angle |
| `data_0121.p` | 4 casts, maximum depth 250 m |
| `data_0122.p` | ship repositioned after the first 3 dives for a better line angle; later drops cleaner |
| `data_0124.p` | low sargassum, very high surface current |
| `data_0125.p` | 5 good casts; magnet screw broken and extracted |
| `data_0126.p` | smooth operations |
| `data_0127.p` | co-located with VMP5500 `SPC_026.P` |
| `data_0128.p` | 3 casts; "forgot to turn on for the first 3", so earlier casts at this station were not recorded |
| `data_0129.p` | second cast reached 269.4 m |
| `data_0131.p` | calm; higher surface salinity, no salinity barrier layer |
| `data_0134.p` | tow-yo lines 1 and 2, EK80 off |
| `data_0140.p` | second deepest casts |

Sealog cross check: VMP250 Sealog entries mostly fall within 0 to 5 min of the .p start time. Known problems:

* Wrong file names: `data_116.p` (= 0116), `dat_0136.p`, `data_0137` (no extension), `data_147.p`. The 2026-08-14 00:35 entry says `data_0118.p` but matches `data_0119.p`.
* Wrong or late times: the `data_0141.p` entry (08-27 04:53) is 4 h after the file start (00:51); that looks like local time (UTC-4) entered as UTC. The `data_0121.p` entry was logged at the end of the casts (+58 min). The 08-15 03:11 and 08-28 06:08 entries say to ignore them.
* No VMP250 entry for `data_0115.p` (5 min file, no profiles) or `data_0130.p`. Entries without file names (08-16 23:45, 08-17 16:01, 08-19 22:43, 08-22 00:25, 08-24 21:07) match `data_0125`, `0127`, `0132`, `0135` and `0139` by time.
* Casts excluded or flagged, and why:
  * `data_0115.p` (2.6 MB) produced no profiles in either run (none passed the profile detection criteria).
  * `data_0117.p`: one profile; FP07 calibration warned that the in-situ temperature range (4.1 degC) is under 8 degC, so the order-2 Steinhart-Hart fit may be poorly constrained.
  * 611 Method-2 chi windows dropped in the 2026-09-30 run because the fitted Batchelor wavenumber exceeded 1.5 x the anti-alias wavenumber (under-resolved, biased low).
  * The logs also warn (repeatedly) that `chi.use_epsilon: false` still uses shear `epsilonMean` for the package's own Gamma and K_rho mixing variables, and that Gamma > 5 and K_rho > 10 m^2/s values were masked. Those package-computed mixing variables are not used in this analysis (see CLAUDE.md, steps 7 and 8).
* Known probe or instrument issues (persistent inter-probe disagreement warnings, 2026-09-30 run):
  * Shear sh1/sh2 median ratio far from 1: 0112 (prof001 0.086, prof002 0.14, prof003 1.51), 0123 prof004 (2.68), 0124 (1.88 to 2.67). Smaller offsets (0.75 to 1.41) on 0116, 0119, 0120, 0123, 0128, 0129, 0130, 0132, 0133, 0141, 0144, 0147, 0148, 0149.
  * FP07 T1/T2 chi ratio: 0129 prof003 (0.378), 0132 prof002, 0137 prof002 and prof003, 0140 prof002 and prof003 (0.76 to 1.54).
  * Cast 0112 should be inspected before use: the shear ratio changes by more than 10x between its profiles.

## Early results

* At the process station, comparing observed chi with chi expected from epsilon (Gamma = 0.2) put all but one of the 18 casts in a regime indicative of double diffusion.
* Individual profiles at a station could disagree (for example, four of five agreeing), consistent with intermittent chi.
* Shear epsilon was order 1e-10 W/kg in parts of the profiles, close to the shear probe noise floor; figure of merit was marginal there.
* Note that these results came from Method 2 chi (iterative Kraichnan fit) with no epsilon spectral QC, so they predate the noise floor test and the MLE fit called for in CLAUDE.md.
* Other observations: TODO
