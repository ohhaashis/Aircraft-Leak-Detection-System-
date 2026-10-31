"""Flow-sensor K-factor from the jug test (OF06ZAT, ISO VG32 oil).

K is in Hz per L/min, the unit the ESP32 uses (Q = pulse frequency / K). Time cancels out:
    K = pulses / (60 x litres)

Set-up: leaks closed, pump running at the PWM you will use for experiments. Take the return hose
off the tank and let it run into a spare container. Both flow sensors are in series, so one test
calibrates both. Each trial: move the hose into the empty measuring jug and press Enter at the same
moment; about 60 s later move it back out and press Enter again; then type the volume.

Live (ESP32 on USB):   python calibrate_flow.py              (3+ trials recommended)
                       python calibrate_flow.py --send       (also sends K,1 and K,2 to the ESP32)
From a logged CSV:     python calibrate_flow.py --csv data/raw/run_0003.csv --volume 1830
                       (pump started and stopped inside the recording, ALL its oil in the jug)
Volume: mL (1830), or grams with a g (1575g) converted with --density (VG32 about 0.86 g/mL;
check your oil's datasheet). Weighing is more accurate than reading the jug scale.
Results are saved to data/calibration/flow_K_<date>.json.
"""
import argparse, json, os, threading, time
from datetime import datetime
import numpy as np
import pandas as pd
import serial
from config import SERIAL_PORT, BAUD, RAW_COLUMNS

MIN_PULSES = 200     # fewer pulses -> +-1 pulse is more than 0.5 % error: collect longer
MAX_SPREAD = 0.02    # trials should agree within 2 %
IDX = {c: RAW_COLUMNS.index(c) for c in ("t_ms", "Q1", "Q2", "C1", "C2")}


def litres(text, density):
    t = text.strip().lower().replace(" ", "")
    if t.endswith("g"):
        return float(t[:-1]) / density / 1000
    return float(t.removesuffix("ml")) / 1000


def trial_result(start, end, q_esp, vol_l):
    """start/end = dict(t_ms, C1, C2); q_esp = mean ESP32 flow (Q1, Q2) during the trial."""
    secs = (end["t_ms"] - start["t_ms"]) / 1000
    r = dict(seconds=round(secs, 1), volume_l=round(vol_l, 4),
             q_jug_lpm=round(vol_l / (secs / 60), 3) if secs > 0 else None)
    for ch in (1, 2):
        n = int(round(end[f"C{ch}"] - start[f"C{ch}"]))
        r[f"pulses{ch}"] = n
        r[f"K{ch}"] = round(n / (60 * vol_l), 4) if n > 0 else None
        r[f"Q{ch}_esp32_lpm"] = round(float(q_esp[ch - 1]), 3)
    return r


def print_trial(i, r):
    print(f"\nTrial {i}: {r['seconds']} s, {r['volume_l'] * 1000:.0f} mL -> jug flow {r['q_jug_lpm']} L/min")
    for ch in (1, 2):
        if r[f"K{ch}"] is None:
            print(f"  FS{ch}: no pulses (sensor not wired, or not in the jug path?)")
            continue
        print(f"  FS{ch}: {r[f'pulses{ch}']} pulses -> K{ch} = {r[f'K{ch}']:.4f} Hz per L/min"
              f"   (ESP32 showed {r[f'Q{ch}_esp32_lpm']} L/min with the old K)")
        if r[f"pulses{ch}"] < MIN_PULSES:
            print(f"  WARNING: only {r[f'pulses{ch}']} pulses on FS{ch}; collect for longer")


class Reader(threading.Thread):
    """Reads ESP32 rows in the background so Enter presses are timed against the latest row."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, BAUD, timeout=1)
        self.lock = threading.Lock()
        self.latest, self.q, self.msgs = None, [], []

    def run(self):
        while True:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line.startswith("#"):
                self.msgs.append(line)
                continue
            v = line.split(",")
            if len(v) != len(RAW_COLUMNS):
                continue
            try:
                row = {c: float(v[i]) for c, i in IDX.items()}
            except ValueError:
                continue
            with self.lock:
                self.latest = row
                self.q.append((row["Q1"], row["Q2"]))

    def snapshot(self, reset_q=False):
        with self.lock:
            row, q = self.latest, self.q
            if reset_q:
                self.q = []
        return row, np.mean(q, axis=0) if q else (0.0, 0.0)


def from_csv(path, vol_l):
    df = pd.read_csv(path).apply(pd.to_numeric, errors="coerce").dropna()
    moving = np.flatnonzero(np.diff(df.C1.to_numpy()) > 0)   # rows where FS1 counted pulses
    if len(moving) == 0:
        raise SystemExit("C1 never changes in this file: no flow recorded")
    a, b = df.iloc[moving[0]], df.iloc[moving[-1] + 1]
    flowing = df.iloc[moving[0] + 1:moving[-1] + 2]
    q = (flowing.Q1.mean(), flowing.Q2.mean())
    return [trial_result(a, b, q, vol_l)]


def live(port, density):
    rd = Reader(port)
    rd.start()
    t0 = time.time()
    while rd.snapshot()[0] is None:
        if time.time() - t0 > 5:
            raise SystemExit(f"No data rows from the ESP32 on {port} (wrong port? Serial Monitor open?)")
        time.sleep(0.1)
    row, _ = rd.snapshot()
    print(f"ESP32 connected. Now: Q1={row['Q1']:.2f}  Q2={row['Q2']:.2f} L/min (with the current K)")
    trials = []
    while True:
        input(f"\nTrial {len(trials) + 1}: hose into the jug + press Enter ...")
        start, _ = rd.snapshot(reset_q=True)
        input("Collecting. Hose out of the jug + press Enter (after about 60 s) ...")
        end, q = rd.snapshot()
        while True:
            try:
                vol = litres(input("Oil collected (mL, or grams with g): "), density)
                break
            except ValueError:
                print("  type a number, e.g. 1830 or 1575g")
        r = trial_result(start, end, q, vol)
        print_trial(len(trials) + 1, r)
        trials.append(r)
        if input("\nAnother trial? [Y/n]: ").strip().lower().startswith("n"):
            return trials, rd


p = argparse.ArgumentParser()
p.add_argument("--port", default=SERIAL_PORT)
p.add_argument("--csv", help="use a logged run instead of the live ESP32")
p.add_argument("--volume", help="with --csv: oil collected (mL, or grams with g)")
p.add_argument("--density", type=float, default=0.86, help="oil density g/mL for weighed volumes")
p.add_argument("--send", action="store_true", help="send the averaged K to the ESP32")
args = p.parse_args()

rd = None
if args.csv:
    if not args.volume:
        raise SystemExit("--csv needs --volume")
    trials = from_csv(args.csv, litres(args.volume, args.density))
    print_trial(1, trials[0])
else:
    trials, rd = live(args.port, args.density)

print("\n================ RESULT ================")
final = {}
for ch in (1, 2):
    ks = [t[f"K{ch}"] for t in trials if t[f"K{ch}"] and t[f"pulses{ch}"] >= MIN_PULSES]
    if not ks:
        ks = [t[f"K{ch}"] for t in trials if t[f"K{ch}"]]
        if ks:
            print(f"FS{ch}: using trials with < {MIN_PULSES} pulses (less accurate)")
    if not ks:
        print(f"FS{ch}: no usable trial")
        continue
    final[ch] = round(float(np.mean(ks)), 4)
    spread = (max(ks) - min(ks)) / final[ch]
    note = f"  WARNING: trials differ by {spread:.1%}, repeat" if spread > MAX_SPREAD else ""
    print(f"FS{ch}: K = {final[ch]:.4f} Hz per L/min  ({len(ks)} trials, spread {spread:.1%}){note}")
if len(final) == 2:
    print(f"K1/K2 = {final[1] / final[2]:.3f}  (sensors differ by {abs(final[1] / final[2] - 1):.1%})")
cmds = [f"K,{ch},{k:.4f}" for ch, k in final.items()]
print("ESP32 commands:  " + "   ".join(cmds))

os.makedirs("data/calibration", exist_ok=True)
out = f"data/calibration/flow_K_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(out, "w") as f:
    json.dump(dict(date=datetime.now().isoformat(timespec="seconds"), source=args.csv or args.port,
                   density=args.density, K=final, commands=cmds, trials=trials), f, indent=2)
print(f"Saved -> {out}")

if args.send and rd and cmds:
    for c in cmds:
        rd.ser.write((c + "\n").encode())
    time.sleep(1.5)
    ok = [m for m in rd.msgs if m.startswith("# Flow")]
    print("ESP32 replied: " + (" | ".join(ok) if ok else "nothing (check the K, commands by hand)"))
elif args.send and not rd:
    print("--send works only in live mode")
print("Next: check that Q1 and Q2 now match the jug flow, then run N (pump on, leaks closed).")
print("If your ESP32 firmware does not save K in flash, also set flowK[] in leak_daq.ino.")
