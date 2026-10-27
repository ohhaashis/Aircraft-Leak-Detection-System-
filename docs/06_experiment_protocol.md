# 6. Experiment Protocol (Data Collection)

The model only learns what is recorded. Plan **≈70 runs of 90 s**, spread over 3–4 days, in
**ISO VG32 oil**.

## 6.1 Before each session

1. Rig on a drip tray; goggles and gloves on.
2. Reservoir filled above the return ports (prevents air bubbles, which sound like leaks).
3. Inlet valve **fully open**. All leak points closed (L1 valve shut, L2/L3 clamps tight).
4. ESP32 connected; Serial Monitor open; pump **off** → send `Z`; close Serial Monitor.

## 6.2 One run

1. Set the condition (open the chosen leak, or arrange the "normal" disturbance).
2. Set pump speed with the PWM knob (use the taped marks: 50 / 75 / 100 %). Wait ≈10 s.
3. Record:
   ```
   python logger.py --label 1 --valve 50 --leak_lpm 0.8 --cond "L1 half open, pump 100%" --duration 90
   ```
4. Measure the leak rate: leak hose (L1) or catch bottle (L2/L3) into a measuring jug for 30 s →
   L/min. Pass it as `--leak_lpm` (or edit the run's `.json` afterwards).
5. Write the run number, condition and anything unusual in the shared lab sheet.
6. Close the leak; wait for pressures to settle before the next run.

## 6.3 Run plan

| Condition | Label | Variations | Runs |
|---|---|---|---|
| Normal operation | 0 | Pump 50 / 75 / 100 %; pump start/stop; pressure-switch cut-off; knocks on pipe; people walking | ~25 |
| L1 centre valve | 1 | Valve ¼, ½, fully open × 4–5 repeats | 12–15 |
| L2 right hole | 2 | Pump 75 / 100 % × 4–5 repeats | 12–15 |
| L3 left hole | 3 | Pump 75 / 100 % × 4–5 repeats | 12–15 |

## 6.4 Rules

- **One leak open at a time.** Label every run correctly — a wrong label cannot be fixed by any algorithm.
- **Mix the order** across days (don't record all L1 runs in one block), so time of day and oil
  temperature don't become what the model learns.
- **Same mounting:** never move a PZT saddle between runs; if you must, note it and re-record baselines.
- **Keep normal-but-disturbed runs** — they teach the model that a speed change or knock is not a leak.

## 6.5 Lab sheet columns

`run_id · date/time · label · leak point · valve/clamp setting · pump % · leak_lpm · oil temp (if known) · notes`
