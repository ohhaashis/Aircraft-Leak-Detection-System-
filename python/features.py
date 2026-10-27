"""Turn raw 10 Hz rows into one feature vector per 1-second window.
The same function is used for training AND live inference, so features always match."""
import glob, json, os
import numpy as np
import pandas as pd
from config import WINDOW_ROWS, HOP_ROWS

EPS = 1e-6


def window_features(w: pd.DataFrame) -> dict:
    f = {}
    # ---------------- Pressure ----------------
    f["P1_mean"] = w.P1.mean()
    f["P2_mean"] = w.P2.mean()
    f["dP"] = f["P1_mean"] - f["P2_mean"]                 # pressure drop across the loop
    f["P1_std"] = w.P1.std()
    f["P2_std"] = w.P2.std()
    f["P1_slope"] = w.P1.iloc[-1] - w.P1.iloc[0]         # sudden drop when a leak opens
    # ---------------- Flow ----------------
    f["Q1_mean"] = w.Q1.mean()
    f["Q2_mean"] = w.Q2.mean()
    f["dQ"] = f["Q1_mean"] - f["Q2_mean"]                 # mass balance: leak rate estimate
    f["dQ_rel"] = f["dQ"] / (f["Q1_mean"] + EPS)          # normalised: insensitive to pump speed
    f["Q1_std"] = w.Q1.std()
    f["dP_per_Q2"] = f["dP"] / (f["Q1_mean"] ** 2 + EPS)  # hydraulic resistance (dP ~ Q^2)
    # ---------------- Acoustic (4 PZT channels, 9 STM32 features each) ----------------
    rms = []
    for i in range(1, 5):
        p = f"AE{i}_"
        f[p + "rms"] = w[p + "rms"].mean()
        f[p + "peak"] = w[p + "peak"].max()
        f[p + "p2p"] = w[p + "p2p"].max()
        f[p + "std"] = w[p + "std"].mean()
        f[p + "energy"] = w[p + "energy"].mean()
        f[p + "crest"] = w[p + "crest"].mean()
        f[p + "hits"] = w[p + "hits"].sum()
        f[p + "dur"] = w[p + "dur"].sum()
        f[p + "fdom"] = w[p + "fdom"].median()
        f[p + "rms_var"] = w[p + "rms"].std()             # how much loudness fluctuates
        rms.append(f[p + "rms"])
    total = sum(rms) + EPS
    f["AE_total"] = total
    for i in range(4):
        f[f"AE{i+1}_ratio"] = rms[i] / total                # WHERE the sound is (localisation)
    for i in range(3):
        f[f"AE{i+1}{i+2}_logratio"] = np.log((rms[i] + 1) / (rms[i + 1] + 1))
    return f


PRESSURE = ["P1_mean", "P2_mean", "dP", "P1_std", "P2_std", "P1_slope"]
FLOW = ["Q1_mean", "Q2_mean", "dQ", "dQ_rel", "Q1_std", "dP_per_Q2"]
FEATURE_SETS = {
    "A_pressure": PRESSURE,
    "B_pressure_flow": PRESSURE + FLOW,
    "C_full_fusion": None,  # None = all features
}


def windows_from_df(df: pd.DataFrame):
    rows = []
    for s in range(0, len(df) - WINDOW_ROWS + 1, HOP_ROWS):
        rows.append(window_features(df.iloc[s:s + WINDOW_ROWS]))
    return pd.DataFrame(rows)


def build_dataset(raw_dir="data/raw"):
    """Returns features X, labels y, run ids (groups), leak rate per window, and the full table."""
    parts = []
    for csv in sorted(glob.glob(os.path.join(raw_dir, "run_*.csv"))):
        meta_path = csv.replace(".csv", ".json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        df = pd.read_csv(csv).apply(pd.to_numeric, errors="coerce").dropna()
        if len(df) < WINDOW_ROWS:
            continue
        W = windows_from_df(df)
        W["label"] = meta["label"]
        W["run_id"] = meta["run_id"]
        W["leak_lpm"] = meta.get("leak_lpm", 0.0)
        W["condition"] = meta.get("condition", "")
        parts.append(W)
    if not parts:
        raise SystemExit(f"No runs found in {raw_dir}. Record data with logger.py (or run simulate.py).")
    data = pd.concat(parts, ignore_index=True)
    meta_cols = ["label", "run_id", "leak_lpm", "condition"]
    X = data.drop(columns=meta_cols)
    return X, data["label"], data["run_id"], data["leak_lpm"], data
