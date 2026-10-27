"""Generate FAKE runs (same format as logger.py) to test features/training/dashboard
before the rig exists. The physics is rough and invented: never report these results.
Delete data/raw/ before recording real runs.      Usage:  python simulate.py --runs 24"""
import argparse, json, os
import numpy as np
from config import RAW_COLUMNS

rng = np.random.default_rng(0)
# Positions measured along the pipe from the pump outlet (feet), matching config.py
PZT_S = np.array([1.4, 5.2, 7.8, 11.6])
LEAK_S = {1: 6.5, 2: 2.6, 3: 10.4}


def make_run(label, valve, speed, transient, seconds=90):
    n = seconds * 10
    t = np.arange(n) * 100
    q_pump = 4.0 * speed                                 # L/min
    p1 = 250 * speed ** 2                                # kPa
    q_leak = 0.0
    if label == 1:
        q_leak = 0.012 * valve * np.sqrt(p1 / 250)       # adjustable centre valve
    elif label in (2, 3):
        q_leak = 0.5 * np.sqrt(p1 / 250)                 # fixed drilled hole
    P1 = p1 - 25 * q_leak + rng.normal(0, 2.5, n)
    P2 = 0.35 * p1 - 40 * q_leak + rng.normal(0, 2.5, n)
    Q1 = q_pump + rng.normal(0, 0.04, n)
    Q2 = q_pump - q_leak + rng.normal(0, 0.04, n)
    if transient == "valve":                              # normal change: outlet partly restricted
        P1 += 30; P2 -= 20; Q1 -= 0.4; Q2 -= 0.4
    if transient == "speed_step":                         # pump speed change half-way through
        P1[n // 2:] *= 0.8; P2[n // 2:] *= 0.8; Q1[n // 2:] *= 0.9; Q2[n // 2:] *= 0.9
    rows = np.zeros((n, len(RAW_COLUMNS)))
    rows[:, 0:5] = np.column_stack([t, P1, P2, Q1, Q2])
    rows[:, 5] = np.cumsum(Q1 * 1.2 * 0.1)
    rows[:, 6] = np.cumsum(Q2 * 1.2 * 0.1)
    for i in range(4):
        pump_noise = 40 * speed * np.exp(-PZT_S[i] / 6)
        leak_noise, near = 0.0, False
        if label:
            d = abs(PZT_S[i] - LEAK_S[label])
            leak_noise = 260 * q_leak ** 0.8 * np.exp(-d / 1.8)
            near = d < 2
        rms = pump_noise + leak_noise + rng.normal(0, 6, n).clip(-15, 15) + 5
        if transient == "tap":                            # someone knocks the pipe: short bursts
            rms = rms + (rng.random(n) < 0.02) * rng.uniform(100, 400, n)
        rms = rms.clip(1)
        peak = rms * rng.uniform(2.0, 3.0, n)
        hits = rng.poisson(rms / 40)
        fdom = rng.normal(36000 if near else 40000, 1500, n)
        c = 7 + 9 * i
        rows[:, c:c + 9] = np.column_stack([
            rms, peak, 1.8 * peak, 0.95 * rms, rms ** 2, peak / rms, hits,
            hits * rng.uniform(0.2, 1.0, n), fdom])
    return rows, q_leak


p = argparse.ArgumentParser()
p.add_argument("--runs", type=int, default=24)
args = p.parse_args()
os.makedirs("data/raw", exist_ok=True)
for r in range(1, args.runs + 1):
    label = r % 4
    valve = float(rng.choice([25, 50, 100])) if label == 1 else (100.0 if label else 0.0)
    speed = rng.uniform(0.7, 1.0)
    transient = rng.choice(["none", "valve", "speed_step", "tap"]) if label == 0 else rng.choice(["none", "none", "tap"])
    rows, q_leak = make_run(label, valve, speed, transient)
    base = f"data/raw/run_{r:04d}"
    np.savetxt(base + ".csv", rows, delimiter=",", header=",".join(RAW_COLUMNS), comments="", fmt="%.3f")
    json.dump(dict(run_id=r, label=int(label), valve=valve, leak_lpm=round(float(q_leak), 3),
                   condition=f"SIMULATED speed={speed:.2f} transient={transient}"),
              open(base + ".json", "w"), indent=2)
print(f"Wrote {args.runs} simulated runs to data/raw/")
