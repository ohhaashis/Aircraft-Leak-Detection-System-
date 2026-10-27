# 4. Software and Data

## 4.1 Software stack

| Tool | Used for |
|---|---|
| Arduino IDE 2.x + ESP32 boards package + "Adafruit ADS1X15" library | ESP32 firmware |
| STM32CubeIDE (+ CMSIS-DSP), or Arduino IDE + STM32duino | STM32 firmware |
| Python 3.10+ | Logging, features, training, dashboard |
| numpy, pandas, scikit-learn, xgboost, matplotlib, joblib | Data handling and ML |
| pyserial | Reading the ESP32 over USB |
| Streamlit + Plotly | Live dashboard |
| VS Code, Git/GitHub | Editing and sharing code |

Install Python libraries: `cd python && pip install -r requirements.txt`.

## 4.2 Code map

| File | Runs on | What it does |
|---|---|---|
| `firmware/esp32/leak_daq/leak_daq.ino` | ESP32 | Pressure (ADS1115), flow (interrupts), merges STM32 AE line, sends 43-column row every 100 ms |
| `firmware/stm32/README.md` | — | Specification of the STM32 AE firmware (to be implemented) |
| `firmware/stm32/ae_protocol_test/` | STM32 | Sends fake AE lines to test the ESP32 merge |
| `python/config.py` | Laptop | Serial port, column list, windows, class names, rig geometry, alarm settings |
| `python/logger.py` | Laptop | Records one labelled run → `data/raw/run_XXXX.csv` + `.json` |
| `python/features.py` | Laptop | Raw rows → one feature vector per 1 s window (training **and** live) |
| `python/ae_reference.py` | Laptop | Reference definition of the 9 AE features, to validate the STM32 |
| `python/train.py` | Laptop | Compares 4 models, A/B/C fusion experiment, saves best model + charts |
| `python/dashboard.py` | Laptop | Live monitoring interface (or replay of a recording) |
| `python/simulate.py` | Laptop | Fake runs to test the software without hardware |

## 4.3 Data levels

**Level 1 — raw signals** (inside firmware only): pressure voltages, flow pulses, 200 kHz PZT samples.

**Level 2 — one row every 100 ms** (what reaches the laptop, 43 columns):

| Columns | Meaning | Unit |
|---|---|---|
| `t_ms` | ESP32 time since boot | ms |
| `P1`, `P2` | Inlet / outlet pressure | kPa (gauge) |
| `Q1`, `Q2` | Inlet / outlet flow | L/min |
| `C1`, `C2` | Cumulative pulse counts | count |
| `AE{i}_rms, _peak, _p2p, _std, _energy, _crest, _hits, _dur, _fdom` | 9 AE features × 4 channels | ADC counts / ms / Hz |

**Level 3 — labels**, one `.json` per run:

```json
{ "run_id": 17, "label": 1, "valve": 50, "leak_lpm": 0.8,
  "condition": "L1 half open, pump 100%", "start": "2026-11-05T14:02:11" }
```

Labels: 0 = no leak, 1 = L1 (centre valve), 2 = L2 (right hole), 3 = L3 (left hole).

**Level 4 — features**: each 1 s window (10 rows, sliding by 0.5 s) → ≈60 features (see
[05_machine_learning.md](05_machine_learning.md)). A 90 s run gives ≈170 windows; 70 runs ≈12,000.

**Level 5 — output**: class probabilities + leak rate per window → alarm logic → dashboard.

## 4.4 ESP32 serial commands

| Command | Effect |
|---|---|
| `Z` | Tare pressure (pump OFF); also forwarded to the STM32 to tare AE baselines |
| `K,1,<value>` / `K,2,<value>` | Set flow K-factor (Hz per L/min) |
| `A1` / `A0` | Buzzer on / off (sent by the dashboard) |

K-factors reset at power-off; once calibrated, edit `flowK` in `leak_daq.ino`.

## 4.5 Folders created at run time (not committed)

`data/raw/` recorded runs · `models/` saved models · `results/` scores and charts · `data/events.csv` leak log.
