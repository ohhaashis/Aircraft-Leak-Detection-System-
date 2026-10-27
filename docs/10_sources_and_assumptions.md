# 10. Sources and Assumptions

## Sources

| Item | Source |
|---|---|
| HK2016 pressure sensor (range, output formula, accuracy, response) | Manufacturer datasheet (team files) |
| OF06ZAT flow sensor (range, pulse output, F = 1.2·Q, wiring) | Manufacturer datasheet (team files) |
| ESP32 ADC/GPIO behaviour | Espressif, *ESP32 Series Datasheet* |
| ADS1115 resolution and input limits | Texas Instruments, *ADS111x Datasheet* |
| AD620 gain formula and gain–bandwidth | Analog Devices, *AD620 Datasheet* |
| STM32F411 ADC, RAM (128 KB) | STMicroelectronics, *STM32F411xC/xE Datasheet* |
| Orifice equation | Standard fluid mechanics texts (e.g., F. M. White, *Fluid Mechanics*) |
| Random Forest | L. Breiman, "Random forests," *Machine Learning*, 45(1), 2001 |
| XGBoost | T. Chen, C. Guestrin, "XGBoost," *Proc. ACM SIGKDD*, 2016 |
| SVM | C. Cortes, V. Vapnik, "Support-vector networks," *Machine Learning*, 20(3), 1995 |
| Pipeline leak detection review | M. A. Adegboye et al., *Sensors*, 19(11), 2548, 2019 |

## Design choices (starting points, to be tuned)

Window length (1 s, 50 % overlap), alarm rule (4 windows ≥ 60 %), AD620 gain (≈50), filter corners
(≈14 kHz high-pass, ≈100 kHz low-pass), component values, run counts.

## Assumptions to confirm

- Rig positions in `config.py` and the figures are placeholders until measured.
- Pump maximum pressure stays below 1 MPa (read the pump label).
- PWM controller switching frequency (≈13 kHz typical) — verify on an oscilloscope.
- The 40 kHz PZT discs are resonant transducers, not calibrated AE sensors; measured spectra are
  relative, not absolute.

## Simulated data

Everything produced by `python/simulate.py` is invented and must never be reported as results.
