# 7. Step-by-Step Demo Guide

Two paths: **Part A** runs the complete software demo on any laptop with no hardware (about 15
minutes). **Part B** runs the live demo on the real rig.

---

## Part A — Software demo without hardware

### A1. Install

1. Install **Python 3.10 or newer** from python.org. On Windows, tick **"Add Python to PATH"**.
2. Install **Git**, then clone the repository:
   ```
   git clone https://github.com/ohhaashis/Aircraft-Leak-Detection-System-.git
   cd Aircraft-Leak-Detection-System-/python
   ```
3. Install the libraries:
   ```
   pip install -r requirements.txt
   ```

### A2. Generate simulated data

```
python simulate.py --runs 24
```
Creates 24 fake runs in `data/raw/` (6 per class: no leak, L1, L2, L3), each a CSV plus a JSON label file.

> Simulated data uses invented physics. It proves the software works; its scores are **not results**.

### A3. Train and compare the models

```
python train.py
```
Expected: a table of scores for 4 models × 3 feature sets (A/B/C), the physics baseline, the
minimum detectable leak, and "Best model on full fusion: …". Takes 1–5 minutes. Outputs:

- `models/leak_model.joblib`, `models/leak_rate_model.joblib`
- `results/summary.csv`, `confusion_matrix.png`, `fusion_comparison.png`, `feature_importance.png`

### A4. Run the dashboard on a recording

```
streamlit run dashboard.py -- --replay data/raw/run_0002.csv
```
A browser tab opens at `http://localhost:8501`. Expected per run (simulated labels follow run number mod 4):

| File | True condition | Dashboard should show |
|---|---|---|
| `run_0004.csv` | No leak | ✅ NORMAL OPERATION |
| `run_0001.csv` | L1 (centre valve) | 🚨 LEAK @ L1, after ≈2 s |
| `run_0002.csv` | L2 (right hole) | 🚨 LEAK @ L2 |
| `run_0003.csv` | L3 (left hole) | 🚨 LEAK @ L3 |

Stop with `Ctrl + C` in the terminal; restart with another file.

### A5. Check the AE feature definitions (optional)

```
python ae_reference.py
```
Prints the 9 features for a synthetic 40 kHz signal and "Self-test passed."

---

## Part B — Live demo on the rig

### B1. Hardware ready

Wiring as in [03_hardware_and_circuits.md](03_hardware_and_circuits.md); pins in
[`hardware/pin_map.md`](../hardware/pin_map.md). Rig commissioned with water, flow sensors
calibrated, PZT channels checked on an oscilloscope.

### B2. Flash firmware

1. **ESP32:** Arduino IDE → board "ESP32 Dev Module" → install "Adafruit ADS1X15" → open
   `firmware/esp32/leak_daq/leak_daq.ino` → Upload (hold BOOT if it hangs at "Connecting…").
2. **STM32:** flash `firmware/stm32/ae_firmware/ae_firmware.ino` (steps in `firmware/stm32/README.md`).
   To test the ESP32 link alone, `ae_protocol_test` sends fake AE data instead.
3. Serial Monitor at 115200 baud: you should see `# Group32 leak DAQ v2 ready`, the header line and
   rows of numbers. No STM32 data → a warning line and zeros in the AE columns.

### B3. Configure

1. In `python/config.py` set `SERIAL_PORT` (Device Manager → Ports on Windows; `/dev/ttyUSB0` on Linux).
2. Enter measured sensor and leak positions in `SENSORS` and `LEAKS`.
3. Pump **off** → send `Z` in Serial Monitor → **close** Serial Monitor.

### B4. Collect real data and train

1. Delete simulated data: remove `python/data/raw`, `python/models`, `python/results`.
2. Record ≈70 runs following [06_experiment_protocol.md](06_experiment_protocol.md).
3. `python train.py`.

### B5. Live demo

1. Start the pump (PWM knob at 100 %), all leaks closed.
2. `streamlit run dashboard.py` → banner shows **NORMAL OPERATION**.
3. Open L1 (centre valve) → within ≈2 s: **LEAK DETECTED — L1**, estimated leak rate, map marker
   turns red, event logged, buzzer on.
4. Close L1 → returns to normal. Repeat with L2/L3 (loosen clamp, catch bottle ready).
5. Show discrimination: change pump speed or knock the pipe → **no alarm**.
6. Show `data/events.csv` and the `results/` charts.

### Demo checklist

- [ ] Drip tray, catch bottles, towels, goggles
- [ ] Laptop charged; Serial Monitor closed before the dashboard
- [ ] `models/leak_model.joblib` trained on **real** data
- [ ] Reservoir filled; inlet valve open; air bled
- [ ] One rehearsal of the full sequence the day before
