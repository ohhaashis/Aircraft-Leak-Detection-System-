# 8. Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `pip` or `python` not found | Python not on PATH | Reinstall with "Add Python to PATH" ticked; reopen terminal |
| "Access denied" / port busy | Serial Monitor or another script holds the port | Close Serial Monitor, then run the Python script |
| No COM port appears | Missing USB driver or charge-only cable | Install CP210x / CH340 driver; try another cable |
| Upload hangs at "Connecting…" | ESP32 not in boot mode | Hold the BOOT button until upload starts |
| `# ERROR: ADS1115 not found` | I²C wiring or address | SDA→21, SCL→22, ADDR→GND, VDD→3.3 V; run the i2c_scanner example (expect 0x48) |
| Pressure negative or jumping | Not tared, divider wrong, missing common ground | Send `Z` with pump off; divider output ≈0.33 V at 0 bar; join all GNDs |
| Flow stays 0 | Wrong pin, no pull-up, 12 V GND not joined, sensor mounted flat | GPIO25/26 + 10k to 3.3 V; join grounds; label vertical |
| Flow lower than jug measurement | K-factor still the water value | Recalibrate K with oil |
| `# WARNING: no AE data from STM32` | UART wiring or STM32 not running | PA9→GPIO16, common GND, 230400 baud; test with `ae_protocol_test` |
| AE channel flat or saturated | AD620 gain wrong, bias missing | Scope check; gain ≈ 50; check 10k/10k bias at 1.65 V |
| AE channels noisy even with no leak | PWM switching noise, ground loop | Pump at 100 %; twist pump wires, ferrite; star ground; shield grounded at board end only |
| False "leaks" with bubbles | Return lines above oil level, air in loop | Fill reservoir above return ports; bleed air at full pump speed |
| Training scores ≈100 % on real data | Train/test leakage or too-easy data | Confirm split is by run; add more varied normal runs |
| Leaks detected but locations confused | PZT placement, unequal mounting, too few runs | Identical saddles; check placement; more runs per leak |
| Dashboard "Waiting for data…" | Wrong port in `config.py` | Set `SERIAL_PORT`; confirm rows in Serial Monitor first |
| `models/leak_model.joblib` not found | Training not run | `python train.py` |
| Column-count mismatch after firmware change | Firmware and `config.py` disagree | Keep `RAW_COLUMNS` identical to the ESP32 header line; retrain |
