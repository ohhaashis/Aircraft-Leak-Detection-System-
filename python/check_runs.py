"""Check recorded runs in data/raw/ BEFORE training: row counts, time gaps, stuck/zero sensor
columns and missing or wrong JSON labels. Run it after every recording session.

Usage:  python check_runs.py                 (checks data/raw)
        python check_runs.py --dir some/folder --min-seconds 50

FAIL = run is broken (fix or delete it). WARN = usable, but look at it. Exit code 1 if any FAIL.
"""
import argparse, glob, json, os, re, sys
import numpy as np
import pandas as pd
from config import RAW_COLUMNS, WINDOW_ROWS, CLASS_NAMES

DT_MS = 100          # ESP32 sends one row every 100 ms
GAP_MS = 150         # a time step bigger than this means rows were lost
STALE_ROWS = 10      # AE rms identical this many rows in a row = stale (ESP32 repeats AE for up to 1 s)
CLIP_PEAK = 2000     # |x| peak near 2048 counts = AD620/ADC clipping
AE_COLS = [c for c in RAW_COLUMNS if c.startswith("AE")]


def longest_repeat(x):
    """Length of the longest stretch of identical consecutive values."""
    change = np.flatnonzero(np.diff(x) != 0)
    return int(np.diff(np.concatenate([[-1], change, [len(x) - 1]])).max())


def check_csv(path, min_s):
    fail, warn = [], []
    try:
        raw = pd.read_csv(path)
    except Exception as e:
        return [f"cannot read CSV ({e})"], warn, 0.0
    if list(raw.columns) != RAW_COLUMNS:
        return ["header does not match config.RAW_COLUMNS"], warn, 0.0
    df = raw.apply(pd.to_numeric, errors="coerce")
    bad = int(df.isna().any(axis=1).sum())
    if bad:
        warn.append(f"{bad} non-numeric rows (features.py drops them)")
    df = df.dropna()
    secs = len(df) * DT_MS / 1000
    if len(df) < WINDOW_ROWS:
        return fail + [f"only {len(df)} rows (features.py skips runs under {WINDOW_ROWS})"], warn, secs
    if secs < min_s:
        warn.append(f"short run: {secs:.0f} s (expected >= {min_s:.0f} s)")

    # ---- Time: gaps and resets ----
    dt = np.diff(df.t_ms.to_numpy())
    if (dt <= 0).any():
        fail.append(f"t_ms goes backwards/repeats {int((dt <= 0).sum())}x (ESP32 reset during run?)")
    gaps = dt[dt > GAP_MS]
    if len(gaps):
        lost = (gaps - DT_MS).sum() / 1000
        msg = f"{len(gaps)} time gaps, longest {gaps.max():.0f} ms, {lost:.1f} s missing in total"
        (fail if lost > 0.05 * secs else warn).append(msg)

    # ---- Pressure and flow ----
    for c in ("P1", "P2"):
        if df[c].nunique() == 1:
            fail.append(f"{c} constant at {df[c].iloc[0]:g} (sensor or ADS1115 not reading)")
    for c, other in (("Q1", "Q2"), ("Q2", "Q1")):
        if (df[c] == 0).all() and df[other].mean() > 0.2:
            fail.append(f"{c} always 0 while {other} flows (no pulses: wiring/pull-up/mounting?)")

    # ---- Acoustic ----
    ae = df[AE_COLS].to_numpy()
    link_lost = (ae == 0).all(axis=1)
    if link_lost.all():
        fail.append("all AE columns 0 for the whole run (STM32 not sending)")
        return fail, warn, secs
    if link_lost.any():
        pct = link_lost.mean()
        (fail if pct > 0.05 else warn).append(f"AE all-zero in {pct:.0%} of rows (STM32 link dropped)")
    ok = df[~link_lost]
    for i in range(1, 5):
        rms = ok[f"AE{i}_rms"].to_numpy()
        if np.all(rms == rms[0]):
            fail.append(f"AE{i}_rms constant at {rms[0]:g} (channel dead?)")
            continue
        rep = longest_repeat(rms)
        if rep >= STALE_ROWS:
            warn.append(f"AE{i}_rms stuck for {rep} rows ({rep * DT_MS / 1000:.1f} s)")
        clip = (ok[f"AE{i}_peak"] >= CLIP_PEAK).mean()
        if clip > 0.01:
            warn.append(f"AE{i}_peak clipping in {clip:.0%} of rows (gain too high?)")
    return fail, warn, secs


def check_json(path, csv_name):
    if not os.path.exists(path):
        return ["missing JSON label file (features.py skips this run)"], [], None
    try:
        meta = json.load(open(path))
    except Exception as e:
        return [f"cannot read JSON ({e})"], [], None
    fail, warn = [], []
    for k in ("run_id", "label"):
        if k not in meta:
            fail.append(f"JSON has no '{k}'")
    if fail:
        return fail, warn, meta
    if meta["label"] not in CLASS_NAMES:
        fail.append(f"label {meta['label']} is not one of {sorted(CLASS_NAMES)}")
    num = int(re.search(r"run_(\d+)", csv_name).group(1))
    if meta["run_id"] != num:
        warn.append(f"run_id {meta['run_id']} does not match file number {num}")
    lpm = meta.get("leak_lpm", 0.0) or 0.0
    if meta["label"] in (1, 2, 3) and lpm <= 0:
        warn.append("leak run without measured leak_lpm (needed for the leak-rate model)")
    if meta["label"] == 0 and lpm > 0:
        warn.append(f"label 0 (no leak) but leak_lpm = {lpm}")
    return fail, warn, meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="data/raw")
    p.add_argument("--min-seconds", type=float, default=50, help="warn if a run is shorter (plan: 60 s)")
    args = p.parse_args()

    csvs = sorted(glob.glob(os.path.join(args.dir, "run_*.csv")))
    if not csvs:
        raise SystemExit(f"No run_*.csv files in {args.dir}")

    results, ids, simulated = [], {}, 0
    for csv in csvs:
        name = os.path.basename(csv)[:-4]
        f1, w1, meta = check_json(csv[:-4] + ".json", name)
        f2, w2, secs = check_csv(csv, args.min_seconds)
        if meta and "run_id" in meta:
            ids.setdefault(meta["run_id"], []).append(name)
        if meta and "SIMULATED" in str(meta.get("condition", "")):
            simulated += 1
        results.append([name, meta, secs, f1 + f2, w1 + w2])

    for rid, names in ids.items():         # duplicate run_id breaks the train/test split by run
        if len(names) > 1:
            for r in results:
                if r[0] in names:
                    r[3].append(f"run_id {rid} also used by {', '.join(n for n in names if n != r[0])}")

    for name, meta, secs, fail, warn in results:
        label = meta.get("label", "?") if meta else "?"
        status = "FAIL" if fail else "WARN" if warn else "OK"
        msgs = fail + warn
        print(f"{name}  label {label}  {secs:5.1f} s  {status:4}  {msgs[0] if msgs else ''}")
        for m in msgs[1:]:
            print(" " * 34 + m)
    for orphan in sorted(glob.glob(os.path.join(args.dir, "run_*.json"))):
        if not os.path.exists(orphan[:-5] + ".csv"):
            print(f"{os.path.basename(orphan)}: JSON without CSV (ignored)")

    n_fail = sum(1 for r in results if r[3])
    n_warn = sum(1 for r in results if not r[3] and r[4])
    print(f"\n{len(results)} runs: {len(results) - n_fail - n_warn} OK, {n_warn} WARN, {n_fail} FAIL")
    print("Usable runs per class (OK + WARN):")
    for lab, cname in CLASS_NAMES.items():
        good = [r for r in results if not r[3] and r[1] and r[1].get("label") == lab]
        lpm = [r[1].get("leak_lpm", 0) or 0 for r in good]
        extra = f", leak {min(lpm):.2f}-{max(lpm):.2f} L/min" if lab and good else ""
        print(f"  {lab} {cname:26} {len(good):3d} runs, {sum(r[2] for r in good) / 60:5.1f} min{extra}")
    if simulated:
        print(f"\nNOTE: {simulated} runs are SIMULATED. Delete data/raw before recording real data;"
              " never report their scores.")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
