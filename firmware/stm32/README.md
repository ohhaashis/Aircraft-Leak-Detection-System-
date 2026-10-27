# STM32F411 Acoustic-Emission Firmware — Specification

> **Status: to be implemented.** This document is the contract the firmware must meet.
> `ae_protocol_test/` contains a small sketch that sends *fake* AE lines so the ESP32 merge
> and the whole Python pipeline can be tested before this firmware exists.

## Job

Sample the four PZT channels (outputs of the AD620 front-ends), compute 9 features per channel every
100 ms, and send them to the ESP32 as one text line.

## Hardware

| Item | Value |
|---|---|
| Board | WeAct STM32F411CEU6 "Black Pill" |
| AE inputs | PA1, PA2, PA3, PA4 (ADC1 channels 1–4). **Do not use PA0** (KEY button). |
| UART to ESP32 | USART1: PA9 (TX) → ESP32 GPIO16, PA10 (RX) ← ESP32 GPIO17 |
| Ground | STM32 GND ↔ ESP32 GND ↔ analog GND |
| Input range | 0–3.3 V, idle at ≈1.65 V (≈2048 counts) |

## Sampling

- ADC1 in **scan mode** over channels 1–4, **continuous**, triggered by a timer (TIM2/TIM3 TRGO)
  at 800 kHz total → **200 kHz per channel**.
- **Circular DMA** into a buffer of e.g. 4 × 1024 samples (interleaved ch1,ch2,ch3,ch4,...).
- Sample time: 15 cycles is enough with the 1 nF reservoir capacitor at each input.
- The F411 has a **single ADC**, so channels are sampled a few µs apart. Fine for energy-based
  localisation; not suitable for time-difference-of-arrival (TDOA).

## Memory constraint

100 ms × 200 kHz × 4 channels × 2 bytes = 160 KB, but the F411 has **128 KB RAM**. Therefore:

- Process data **on the fly** in the DMA half-complete and complete callbacks.
- Keep **running accumulators** per channel: Σx, Σx², min, max, max|x|, hit state, hit count,
  samples above threshold.
- Store only the **first 1024 samples** of each channel per block for the FFT.

## Features (must match `python/ae_reference.py`)

With `x = sample − baseline` (baseline captured on tare, pump OFF):

| # | Name | Definition |
|---|---|---|
| 1 | `rms` | √(Σx² / N) |
| 2 | `peak` | max \|x\| |
| 3 | `p2p` | max x − min x |
| 4 | `std` | standard deviation of the block (mean removed) |
| 5 | `energy` | Σx² / fs |
| 6 | `crest` | peak / rms |
| 7 | `hits` | threshold crossings of \|x\|; a new hit only after 1 ms below threshold |
| 8 | `dur` | total time above threshold inside hits (ms) |
| 9 | `fdom` | frequency of the largest bin ≥ 5 kHz in a Hann-windowed 1024-point FFT (CMSIS-DSP `arm_rfft_fast_f32`) |

Validate by logging raw samples once (or using a function generator) and comparing the firmware
output with `ae_features()` from `python/ae_reference.py`.

## Output protocol

USART1 at **230400 baud**, 8N1, one line every 100 ms:

```
$AE,<seq>,<ch1: rms,peak,p2p,std,energy,crest,hits,dur,fdom>,<ch2 ...>,<ch3 ...>,<ch4 ...>\n
```

36 values after the sequence number. Two decimals are enough. The ESP32 keeps the latest line and
appends it to its own row.

## Commands from the ESP32

| Command | Action |
|---|---|
| `Z` | Tare: average 1 s of samples per channel (pump OFF) → new baselines |
| `T,<ch>,<counts>` | Set hit threshold for channel 1–4 (default 150 counts) |

## Suggested tools

STM32CubeIDE + CubeMX (ADC + DMA + TIM + USART configuration generated), CMSIS-DSP for the FFT.
