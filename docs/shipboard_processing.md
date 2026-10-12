# Shipboard processing record

Record of the processing done at sea on the 2026 R/V Falkor (too) SPICE expedition, before this repository existed. Fill this in before writing pipeline code; it is the reference the reproduction run is checked against.

## Archived directories

| Directory | Contents | Location | Manifest |
|---|---|---|---|
| `vmp250_raw` | Original .P files | TODO | `manifests/vmp250_raw.sha256.csv` |
| `vmp250_patched` | .P files after the patch step | TODO | `manifests/vmp250_patched.sha256.csv` |
| `vmp250_processed` | Shipboard processing outputs | TODO | `manifests/vmp250_processed.sha256.csv` |

VMP6000 and VMP5500 data: TODO (location, whether processed at sea).

## Software environment at sea

* Python version: TODO
* microstructure-tpw version: TODO
* Full `pip freeze` saved to: TODO
* Machine and OS: TODO

## Commands run

Recovered from shell history (`~/.zsh_history` or `~/.bash_history`). Paste the relevant commands in the order they were run, with a note on what each did. A filtered copy of the history file is saved to: TODO

```
TODO
```

## Patch step

* What was patched (headers, configuration strings, calibration values, other): TODO
* Why it was needed: TODO
* How it was done (tool, command, or manual edit): TODO
* Which files were affected: TODO

## Processing parameters used

| Parameter | Value | Notes |
|---|---|---|
| FFT length | 4 s | |
| Dissipation length | 16 s | |
| Fall speed limits | TODO | |
| Despiking settings | TODO | |
| Thermistor spectral model and fit | TODO | |
| Other non default settings | TODO | |

## Casts

* 48 hour process station: TODO (cast IDs; 15 VMP250, 3 VMP6000)
* Other stations: TODO
* Casts excluded or flagged, and why: TODO
* Known probe or instrument issues: TODO

## Early results

* At the process station, comparing observed chi with chi expected from epsilon (Gamma = 0.2) put all but one of the 18 casts in a regime indicative of double diffusion.
* Individual profiles at a station could disagree (for example, four of five agreeing), consistent with intermittent chi.
* Shear epsilon was order 1e-10 W/kg in parts of the profiles, close to the shear probe noise floor; figure of merit was marginal there.
* Other observations: TODO
