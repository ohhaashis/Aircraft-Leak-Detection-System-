# 2. System Architecture

![System architecture](images/architecture.png)

## Three layers

| Layer | Components | Job |
|---|---|---|
| Sensing | 2 × HK2016 pressure, 2 × OF06ZAT flow, 4 × PZT discs on steel saddles | Turn leak effects into electrical signals |
| Acquisition | ESP32 + ADS1115 (pressure, flow); STM32F411 + 4 × AD620 (acoustics) | Digitise signals, compute acoustic features, merge into one data row |
| Processing | Laptop running Python | Log labelled runs, train ML models, run the live dashboard |

## Why two microcontrollers

Pressure and flow change slowly: about 150 samples/s per channel is plenty. The PZT signal sits around
40 kHz and must be sampled at about 200 kHz per channel. Doing both on one microcontroller would cause
timing conflicts, so:

- **ESP32** handles the slow signals deterministically and is the single link to the laptop.
- **STM32F411** samples the four acoustic channels with ADC + DMA, reduces each 100 ms of raw data
  to 9 numbers per channel, and sends them to the ESP32 over UART.

The laptop replaces the Raspberry Pi described in the mid-semester report: it receives the ESP32's
rows over USB, runs the trained model and displays the dashboard.

## Data flow

1. Sensors → ESP32 / STM32.
2. STM32 → ESP32: one `$AE,...` line (36 values) every 100 ms over UART at 230400 baud.
3. ESP32 → laptop: one 43-column CSV row every 100 ms over USB at 115200 baud.
4. Laptop: `logger.py` saves rows with a label (training) **or** `dashboard.py` predicts live.

## Test rig

![Rig layout](images/rig_layout.png)

- Oil flows reservoir → inlet valve → pump → PT1/FS1 → right edge → top edge → left edge →
  FS2/PT2 → reservoir.
- **L1** is the ball valve on the centre T joint; opening it releases oil to the reservoir through a
  hose, like an adjustable leak.
- **L2** and **L3** are drilled holes, sealed by a rubber strip and hose clamp; loosening the clamp
  creates a fixed-size leak.
- One PZT per steel segment. Hose couplings partly isolate segments acoustically, so the disc nearest
  the leak hears it loudest.
- The inlet valve stays **fully open** during runs; flow is changed with the pump's PWM controller.

Positions in the figure are placeholders: measure the rig and update `python/config.py`.
