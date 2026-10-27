# Pin Map

## ESP32

| ESP32 pin | Connects to |
|---|---|
| 3.3V | ADS1115 VDD, flow pull-ups (10k ×2) |
| GND | Star ground: ADS1115, sensors, STM32, 12 V supply −, buck − |
| GPIO21 | ADS1115 SDA |
| GPIO22 | ADS1115 SCL |
| GPIO25 | Flow sensor 1 (inlet) via 1k + capacitor |
| GPIO26 | Flow sensor 2 (outlet) via 1k + capacitor |
| GPIO16 (RX2) | STM32 PA9 (TX) |
| GPIO17 (TX2) | STM32 PA10 (RX), optional |
| GPIO27 | Buzzer via NPN transistor (optional) |
| 5V / VIN | Pressure sensors + AD620 modules while on USB power (testing only) |
| USB | Laptop (115200 baud) |

## ADS1115

| Pin | Connects to |
|---|---|
| VDD | ESP32 3.3 V |
| GND | GND |
| SCL / SDA | GPIO22 / GPIO21 |
| ADDR | GND (address 0x48) |
| A0 | Pressure sensor 1 via 10k/20k divider + 1k + cap |
| A1 | Pressure sensor 2 (same circuit) |
| A2 | 5 V rail via 10k/20k divider |
| A3 | Spare |

## STM32F411 Black Pill

| Pin | Connects to |
|---|---|
| PA1 – PA4 | AE channels 1–4 (after AD620 front-end) |
| PA9 (TX) | ESP32 GPIO16 |
| PA10 (RX) | ESP32 GPIO17 (optional) |
| GND | Star ground |
| 3.3V | AE bias dividers (10k/10k) and BAT54S upper clamp |
| PA0 | Do not use (KEY button) |

## Sensors

| Sensor | Red | Black | Signal |
|---|---|---|---|
| HK2016 pressure | +5 V | GND | Blue/yellow → divider |
| OF06ZAT flow | +12 V (or 5 V) | GND | Yellow → pull-up + 1k |

## Pump / PWM controller

Power+ ← 12 V via 10 A fuse · Power− ← 12 V − · Motor+ → pump red · Motor− → pump black (**not ground**).
