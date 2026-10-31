# CLAUDE.md — Aircraft Hydraulic Leak Detection (Group 32, IIT Mandi, IC-202P22)

## What this project is
Lab-scale rig that detects, sizes and localises leaks in a 12 mm steel/hose loop (ISO VG32 oil,
12 V 60 W diaphragm pump, 0.8 MPa max, PWM speed control). Sensors: 2× HK2016 pressure (0–1 MPa),
2× OF06ZAT oval-gear flow (NPN pulses), 4× 50 mm 40 kHz PZT discs via AD620 (gain ≈ 50).
Maintenance-aid demonstrator, not certified. Team lead for software: Ashish (DSAI).

## Architecture
- ESP32 (`firmware/esp32/leak_daq/leak_daq.ino`, v2.1): pressure via ADS1115 (A0=P1, A1=P2, A2=5 V rail,
  addr 0x48, SDA 21, SCL 22), flow on GPIO25/26 (10k pull-up to 3.3 V, period measurement),
  reads STM32 `$AE,...` line on GPIO16 (RX2, 230400 baud), GPIO17 TX → STM32 PA10, buzzer GPIO27.
  Sends one 43-column CSV row every 100 ms over USB at 115200. Commands: Z tare, K,<ch>,<v> K-factor
  (saved in flash), N null flow mismatch (30 s, pump on, leaks closed), P print settings, A1/A0 buzzer.
- STM32F411 Black Pill (`firmware/stm32/ae_firmware/ae_firmware.ino`, STM32duino): PA1–PA4 at 200 kHz/ch
  (TIM2 → ADC1 scan → circular DMA), 9 features/channel every 100 ms, must match `python/ae_reference.py`.
  Send S → check `dropped=0`; if not, lower FS_CH to 100000. Do not use PA0.
- Laptop (Python, `python/`): logger.py → data/raw/run_XXXX.csv + .json; features.py (1 s windows,
  hop 0.5 s, ≈60 features); train.py (LogReg/SVM/RandomForest/XGBoost, StratifiedGroupKFold by RUN,
  A/B/C fusion experiment, physics 3σ baseline, leak-rate RF regressor); dashboard.py (Streamlit, live or
  `-- --replay file.csv`); simulate.py (FAKE data only — never report its scores).
- Labels: 0 no leak, 1 L1 (centre T ball valve, adjustable), 2 L2 (right steel run, drilled hole + clamp),
  3 L3 (left steel run). Alarm: 4 consecutive windows ≥ 60 % leak probability.

## Environment (Windows laptop)
- Project at C:\Projects\Aircraft-Leak-Detection-System-, venv at python\venv (git-ignored).
  Each session: `cd python` then `venv\Scripts\activate`.
- Windows Smart App Control blocked SciPy 1.18 DLLs → pinned `scipy<1.15` in requirements.txt.
  If another "Application Control policy has blocked this file" error appears, pin that library older.
- Repo is private on GitHub (ohhaashis/Aircraft-Leak-Detection-System-).

## Current status (31 Oct 2026)
- Software: all planned tools built (see below) and pushed to main. Whole pipeline works end to end on
  simulated data only (simulate → check_runs → train → notebook → dashboard). Nothing tested on hardware.
- Data: python/data/raw holds 24 SIMULATED runs made with the new PZT plan; models/ and results/ were
  trained on them. AE fingerprint on this data: L1→PZT1, L2→PZT2, L3→PZT3 (simulated, not evidence).
- Firmware: ESP32 and STM32 compile; NOT yet run on hardware.
  The ESP32 file in the repo is v2, not v2.1: K-factors are NOT saved in flash (flowK resets to 1.2 at
  boot) and there are NO N or P commands (only Z, K, A1/A0). If v2.1 exists on a laptop, commit it;
  until then set flowK[] in leak_daq.ino after calibrate_flow.py and re-flash.
- Rig built but not commissioned: missing clamps, loop not closed, flow sensors mounted flat (label must
  be vertical), L2/L3 not drilled, PZT saddles not made, buck converter not set to 5.0 V.
- `config.py` geometry uses the NEW PZT plan but positions are placeholders (not measured; PZT4 spot on
  the top run was guessed). simulate.py reads PZT/leak positions from config.py, so it follows any edit.
- ipykernel not yet installed in the venv (needed to open analysis.ipynb in VS Code).

## Decisions to respect
- New PZT plan (hose isolates the top tee): PZT1 on metal nipple/tee at L1 valve, PZT2 right run (L2),
  PZT3 left run (L3), PZT4 top run as reference. Update config.py SENSORS/LEAKS when measured.
- Calibration order: Z (pump off) → jug test → K,1,<v> → N (pump on, leaks closed) → P.
- Before pilot: noise characterisation runs (pump off; pump on no leak at each PWM setting).
- Data plan: pilot 10 runs, then ≈45 runs × 60 s (15 normal incl. speed changes/knocks, 8–10 per leak),
  mixed order, every run in the shared lab sheet with measured leak L/min.
- Leak experiments at 100 % PWM duty (PWM ≈13 kHz harmonics fall in the acoustic band).
- Keep config.RAW_COLUMNS identical to the ESP32 header line; retrain after any feature change.
- Delete python/data/raw, models, results (simulated) before recording real data.

## Software built 31 Oct 2026 (tested on simulated data / fake ESP32 only, not on hardware)
- check_runs.py (row counts, time gaps, stuck/zero sensors, JSON labels); its limits are imported by dashboard.py
- calibrate_flow.py (K-factor from jug test, live or from a logged CSV)
- analysis.ipynb (plots per run, leak vs no-leak, AE fingerprint, mass balance; needs `pip install ipykernel`)
- dashboard: sensor-health panel, leak-probability chart, sidebar tare / record / silence alarm.
  Dashboard recording writes the same files as logger.py; only one program can hold the COM port.

## Still to build (software)
- optional: Isolation Forest anomaly detector for untrained leak positions

## Style for answers
Explain simply (student team, ~2 weeks left), give exact commands for Windows PowerShell, one step at a
time, and say clearly what is verified vs untested. Never present simulated results as real.
