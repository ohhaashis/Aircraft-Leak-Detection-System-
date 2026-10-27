"""Record one labelled experimental run from the ESP32 into data/raw/.

Examples:
  python logger.py --label 0 --cond "normal, pump full" --duration 90
  python logger.py --label 0 --cond "normal, outlet valve half closed" --duration 90
  python logger.py --label 2 --valve 50 --leak_lpm 0.8 --cond "leak L2 half open" --duration 90

--label     0 = no leak, 1/2/3 = which leak valve is open
--valve     leak valve opening in % (or number of turns) - just for your records
--leak_lpm  measured leak rate (collect leaked oil in a measuring cylinder for 60 s, convert to L/min)
"""
import argparse, json, os, time
from datetime import datetime
import serial
from config import SERIAL_PORT, BAUD, RAW_COLUMNS

p = argparse.ArgumentParser()
p.add_argument("--port", default=SERIAL_PORT)
p.add_argument("--label", type=int, required=True)
p.add_argument("--valve", type=float, default=0)
p.add_argument("--leak_lpm", type=float, default=0.0)
p.add_argument("--cond", default="")
p.add_argument("--duration", type=float, default=90)
p.add_argument("--settle", type=float, default=5, help="seconds to discard at the start")
args = p.parse_args()

os.makedirs("data/raw", exist_ok=True)
existing = [f for f in os.listdir("data/raw") if f.startswith("run_") and f.endswith(".csv")]
run_id = 1 + max([int(f[4:8]) for f in existing], default=0)
base = f"data/raw/run_{run_id:04d}"

meta = dict(run_id=run_id, label=args.label, valve=args.valve, leak_lpm=args.leak_lpm,
            condition=args.cond, start=datetime.now().isoformat(timespec="seconds"))
with open(base + ".json", "w") as f:
    json.dump(meta, f, indent=2)

ser = serial.Serial(args.port, BAUD, timeout=1)
time.sleep(2)
ser.reset_input_buffer()
print(f"Run {run_id}: settling {args.settle}s ...")
t_settle = time.time() + args.settle
t_end = t_settle + args.duration
n = 0
with open(base + ".csv", "w") as out:
    out.write(",".join(RAW_COLUMNS) + "\n")
    while time.time() < t_end:
        line = ser.readline().decode(errors="ignore").strip()
        if not line or line.startswith("#") or line.startswith("t_ms"):
            continue
        if len(line.split(",")) != len(RAW_COLUMNS):
            continue
        if time.time() < t_settle:
            continue
        out.write(line + "\n")
        n += 1
        if n % 50 == 0:
            v = line.split(",")
            print(f"  {n:5d} rows | P1={v[1]} P2={v[2]} kPa | Q1={v[3]} Q2={v[4]} L/min | AE1_rms={v[7]}")
ser.close()
print(f"Saved {n} rows -> {base}.csv  (+ {base}.json)")
