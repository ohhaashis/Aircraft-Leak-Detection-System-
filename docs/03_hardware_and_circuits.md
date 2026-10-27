# 3. Hardware and Circuits

Full parts list: [`hardware/BOM.csv`](../hardware/BOM.csv). Pin summary: [`hardware/pin_map.md`](../hardware/pin_map.md).

## 3.1 Sensors and key parameters

| Sensor | Model | Range / output | Accuracy | Response | Read by |
|---|---|---|---|---|---|
| Pressure ×2 | HK2016 | 0–1 MPa → 0.5–4.5 V at 5 V supply | ±1 %FS | ≤ 2 ms | ADS1115 (16-bit) |
| Flow ×2 | DIJIANG OF06ZAT (oval gear, Hall) | 30–3000 L/h, NPN pulses, F = 1.2·Q (water) | ±1 % (water) | pulse-based | ESP32 interrupts |
| Acoustic ×4 | 50 × 2.6 mm PZT disc, 40 kHz | mV-level AC | uncalibrated, resonant | — | AD620 → STM32 ADC |

Sampling: pressure ≈ 158 Hz per channel (ADS1115, 3 channels round-robin), flow by pulse period,
acoustics 200 kHz per channel, all summarised to **10 rows per second**.

## 3.2 Pressure sensor circuit (×2)

```
Sensor OUT ──┬── 10k ──┬── 1k ──┬── ADS1115 A0 (A1 for sensor 2)
             │         │        │
            (TVS       20k     100 nF (2.2 nF also works)
           optional)   │        │
                      GND      GND
Sensor red → +5 V, black → GND.   5 V rail → its own 10k/20k divider → ADS1115 A2.
```

- **Divider (10k/20k):** scales 0.5–4.5 V to 0.33–3.0 V. A failed sensor at 5 V gives only 3.33 V.
- **1k + capacitor:** noise filter (≈200 Hz with 100 nF); the capacitor also steadies the ADS1115 input.
- **A2 (rail monitor):** the sensor output is ratiometric (Vout = Vcc·(0.8·P + 0.1)); the firmware
  corrects for supply drift.
- **TVS diode:** optional on a bench rig; if used, choose a 5 V type (SMAJ5.0A, PESD5V0).
- Conversion: P [MPa] = (Vout/Vcc − 0.1) / 0.8.

**ADS1115 → ESP32:** VDD → **3.3 V** (not 5 V, the SDA/SCL pull-ups go to VDD), GND → GND,
SCL → GPIO22, SDA → GPIO21, ADDR → GND (address 0x48), ALRT unused.

## 3.3 Flow sensor circuit (×2)

```
+12 V (or 5 V) → sensor red        sensor black → GND
sensor yellow (OUT) ──┬── 1k ──┬── ESP32 GPIO25 (GPIO26 for sensor 2)
                      │        │
                10k to 3.3 V  100 nF (10 nF gives sharper edges)
                               │
                              GND
```

- **Check first:** with the sensor powered and nothing on the yellow wire, measure it while blowing
  through the sensor. Near 0 V / floating = open collector (safe). Near 12 V = internal pull-up: do
  **not** connect as drawn; use a divider.
- The 12 V supply's GND **must** join the ESP32 GND.
- Mount sensors with the label **vertical** (sensor on its side) and the arrow in the flow direction.
- **Calibrate K with oil:** pump into a jug for 60 s, K = (pulses ÷ litres) ÷ 60, send `K,1,<K>`.

## 3.4 PZT acoustic channel (×4)

Signal path: PZT → protection → AD620 (gain ≈ 50) → AC coupling + 1.65 V bias → anti-alias filter + clamp → STM32 ADC.

| Ref | Part | Connection | Purpose |
|---|---|---|---|
| R1, R2 | 1 kΩ | in series with PZT + and − leads | Limit spike current |
| R3, R4 | 1 MΩ | S+ to GND, S− to GND | DC bias path for AD620 inputs |
| D1–D4 | 1N4148 | back-to-back pairs, S+ to GND and S− to GND | Clamp inputs to ±0.7 V |
| U1 | AD620 module | S+, S−, VCC 5 V (100 nF + 10 µF), GND, OUT | Differential amplifier, gain ≈ 50 |
| C1 | 2.2 nF C0G | in series from OUT | Block DC offset |
| R5, R6 | 10 kΩ each | 3.3 V → bias node → GND | Centre signal at 1.65 V; with C1 a ≈14 kHz high-pass |
| R7 | 1 kΩ | bias node → ADC pin | With C2: anti-alias low-pass (≈100 kHz) |
| C2 | 1 nF | ADC pin → GND | Anti-alias + charge reservoir for ADC sampling |
| D5 | BAT54S | pin 1 → GND, pin 2 → 3.3 V, pin 3 → ADC pin | Clamp ADC input to 0–3.3 V |
| — | STM32 | PA1, PA2, PA3, PA4 | ADC inputs (avoid PA0) |

**Why gain ≈ 50, not 1000:** AD620 bandwidth falls with gain (≈120 kHz at G = 100, ≈12 kHz at
G = 1000, AD620 datasheet). G = 1 + 49.4 kΩ/RG → RG ≈ 1 kΩ for G ≈ 50. Set it with a function
generator (40 kHz, 10 mV in → ≈0.5 Vpp out).

**Signal levels:** leak ≈ ±5 mV → AD620 ≈ ±250 mV → ADC sees 1.40–1.90 V (≈1740–2360 counts).

**Grounding:** all GNDs joined; shielded cable from each disc, shield grounded at the board end only;
the pipe connects to GND at one point (the disc's − face touches the steel saddle).

All values are starting points; confirm with a one-channel oscilloscope test (leak valve closed vs
open) before building four channels.

## 3.5 PZT mounting (steel saddle)

| Item | Specification |
|---|---|
| Material | Mild steel (aluminium acceptable) |
| Size | 70 mm (along pipe) × 50 mm × 10 mm |
| Groove | 12 mm wide half-round, 5 mm deep, along the length |
| Disc bonding | Thin epoxy (Araldite), pressed flat |
| Pipe contact | Thin grease in the groove; two hose clamps over the block ends, never over the disc |

Make all four mounts identical: localisation compares loudness between discs. The disc is a resonant
40 kHz transducer, so measured spectra reflect leak noise filtered by pipe, mount and sensor; the
system relies on relative changes, not absolute frequencies.

## 3.6 Pump and PWM speed controller

| Controller terminal | Connects to |
|---|---|
| Power + | 12 V supply + through a 10 A fuse |
| Power − | 12 V supply − (also the star ground for all electronics) |
| Motor + | Pump red wire |
| Motor − | Pump black wire — **never** connect to electronics ground |

- Supply: 12 V, ≥ 8 A (pump ≈ 5 A at full power, more at start). Wire ≥ 1 mm².
- Knob sets duty cycle (average voltage = duty × 12 V). Mark 50/75/100 % positions with tape.
- PWM switching (typically ≈13 kHz; verify on a scope) and its harmonics fall in the acoustic band.
  Run leak experiments at **100 %** when possible, twist pump wires, add a ferrite, keep them away
  from sensor cables.
- Check the pump's printed maximum pressure stays below 1 MPa (sensor limit).

## 3.7 Power and grounding summary

- 12 V supply → PWM controller → pump; 12 V → flow sensors (or 5 V).
- 5 V for pressure sensors and AD620 modules: ESP32 5V/VIN on USB for testing, LM2596 buck later.
- 3.3 V for ADS1115, flow pull-ups, AE bias dividers.
- **Single star ground** at the 12 V supply's − terminal; ESP32, STM32, sensors, buck converter
  grounds all join there.
