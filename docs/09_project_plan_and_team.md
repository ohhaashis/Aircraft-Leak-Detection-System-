# 9. Project Plan and Team Roles

## 9.1 Plan (≈5 weeks; stretch if more time is available)

| Week | Phase | Gate before moving on |
|---|---|---|
| 1 | Commission rig with water; test software on the simulator | No drips at full pump speed; simulator → train → dashboard works |
| 1–2 | Pressure and flow electronics (ESP32 + ADS1115), flow calibration | Q1 − Q2 rises clearly when L1 opens |
| 2 | One acoustic channel on the oscilloscope (PZT2 next to L1) | Leak clearly visible vs. valve closed |
| 3 | Four acoustic channels + STM32 firmware + ESP32 merge | 43-column rows with live AE values |
| 4 | Data collection in VG32 oil (≈70 runs) | Every run labelled and logged in the lab sheet |
| 5 | Training, live demo, final report | A/B/C results, confusion matrix, rehearsed demo |

## 9.2 Suggested ownership

| Member | Branch | Ownership |
|---|---|---|
| Nishant Thamman | ME | Rig: leak points L2/L3, PZT saddles, sealing, oil handling |
| Badavath Thirumalesh | EE | AE front-end (AD620 channels), power, grounding |
| Bhoomika | GE | ESP32 wiring, pressure/flow bring-up, calibration |
| Aman Kumar | CSE | STM32 firmware, ESP32 merge, dashboard |
| Ashish Kumar | DSAI | Features, model training, A/B/C analysis, software lead |
| Ananya Sharma | MSE | Data collection lead, lab sheet, report and figures |

## 9.3 Status

| Part | Status |
|---|---|
| Hydraulic loop | Built |
| ESP32 firmware (pressure, flow, AE merge) | Written; hardware testing pending |
| STM32 AE firmware | Specified (`firmware/stm32/README.md`); to be implemented |
| Python logger, features, training, dashboard | Written; tested on simulated data |
| Leak points L2, L3 | To be built |
| Real data collection | Pending |
