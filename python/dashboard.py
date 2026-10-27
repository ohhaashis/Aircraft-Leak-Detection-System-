"""Real-time leak monitoring dashboard.
Live from ESP32:     streamlit run dashboard.py
Replay a recording:  streamlit run dashboard.py -- --replay data/raw/run_0003.csv
"""
import argparse, collections, os, sys, threading, time
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import (SERIAL_PORT, BAUD, RAW_COLUMNS, WINDOW_ROWS, CLASS_NAMES, LOOP, SENSORS, LEAKS,
                    ALARM_CONSECUTIVE, LEAK_PROB_THRESHOLD)
from features import window_features

ap = argparse.ArgumentParser()
ap.add_argument("--replay", default=None)
ap.add_argument("--port", default=SERIAL_PORT)
args, _ = ap.parse_known_args(sys.argv[1:])

st.set_page_config(page_title="Hydraulic Leak Monitor - Group 32", layout="wide")


class Source:
    """Background thread that fills a ring buffer with raw rows (from serial or a replay file)."""
    def __init__(self, replay, port):
        self.buf = collections.deque(maxlen=600)   # last 60 s
        self.ser = None
        self.status = "starting"
        target = self._replay if replay else self._serial
        threading.Thread(target=target, args=(replay or port,), daemon=True).start()

    def _serial(self, port):
        import serial
        while True:
            try:
                self.ser = serial.Serial(port, BAUD, timeout=1)
                self.status = f"live on {port}"
                while True:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    v = line.split(",")
                    if len(v) == len(RAW_COLUMNS) and not line.startswith(("#", "t_ms")):
                        try:
                            self.buf.append([float(x) for x in v])
                        except ValueError:
                            pass
            except Exception as e:
                self.status = f"serial error: {e} (retrying)"
                time.sleep(2)

    def _replay(self, path):
        df = pd.read_csv(path)[RAW_COLUMNS]
        self.status = f"replaying {os.path.basename(path)}"
        while True:
            for row in df.values:
                self.buf.append(list(row))
                time.sleep(0.1)

    def send(self, cmd):
        if self.ser is not None:
            try:
                self.ser.write((cmd + "\n").encode())
            except Exception:
                pass


@st.cache_resource
def get_source():
    return Source(args.replay, args.port)


@st.cache_resource
def get_models():
    clf = joblib.load("models/leak_model.joblib")
    reg = joblib.load("models/leak_rate_model.joblib") if os.path.exists("models/leak_rate_model.joblib") else None
    return clf, reg


def network_figure(active_leak, probs):
    fig = go.Figure()
    xs, ys = zip(*LOOP)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=10, color="#8a8f98"), hoverinfo="skip"))
    for name, (x, y) in SENSORS.items():
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[name], textposition="top center",
                                 marker=dict(size=14, symbol="square", color="#2b7bba"), hoverinfo="text"))
    for k, (x, y) in LEAKS.items():
        on = (k == active_leak)
        p = probs.get(k, 0)
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[f"L{k} {p:.0%}"],
                                 textposition="bottom center",
                                 marker=dict(size=34 if on else 16, color="#e03131" if on else "#cfd4da",
                                             line=dict(width=2, color="#e03131")), hoverinfo="text"))
    fig.update_layout(showlegend=False, height=380, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False, range=[-0.8, 5.8]),
                      yaxis=dict(visible=False, range=[-0.8, 4.6], scaleanchor="x"))
    return fig


src = get_source()
clf, reg = get_models()
le, feat_cols = clf["label_encoder"], clf["features"]
if "streak" not in st.session_state:
    st.session_state.streak, st.session_state.alarm, st.session_state.events = 0, False, []

st.title("✈️ Aircraft Hydraulic Leak Detection - Live Monitor")
st.caption(f"Group 32, IIT Mandi | model: {clf['name']}")


@st.fragment(run_every=0.5)
def live():
    rows = list(src.buf)
    st.write(f"Source: {src.status} | buffered rows: {len(rows)}")
    if len(rows) < WINDOW_ROWS:
        st.info("Waiting for data...")
        return
    df = pd.DataFrame(rows, columns=RAW_COLUMNS)
    f = window_features(df.iloc[-WINDOW_ROWS:])
    X = pd.DataFrame([f])[feat_cols]
    proba = clf["model"].predict_proba(X)[0]
    classes = le.inverse_transform(np.arange(len(proba)))
    probs = dict(zip(classes, proba))
    p_leak = 1 - probs.get(0, 0)
    best = int(classes[np.argmax(proba)])

    # Alarm logic: require several consecutive leak windows -> rejects transients/taps
    st.session_state.streak = st.session_state.streak + 1 if (p_leak >= LEAK_PROB_THRESHOLD and best > 0) else 0
    alarm = st.session_state.streak >= ALARM_CONSECUTIVE
    rate = float(reg["model"].predict(X)[0]) if (alarm and reg) else max(f["dQ"], 0)
    if alarm and not st.session_state.alarm:
        ev = dict(time=datetime.now().strftime("%H:%M:%S"), location=CLASS_NAMES.get(best, best),
                  confidence=round(p_leak, 3), leak_rate_lpm=round(rate, 3), P1=round(f["P1_mean"], 1),
                  Q1=round(f["Q1_mean"], 3), Q2=round(f["Q2_mean"], 3))
        st.session_state.events.insert(0, ev)
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([ev]).to_csv("data/events.csv", mode="a", index=False, header=not os.path.exists("data/events.csv"))
        src.send("A1")
    if not alarm and st.session_state.alarm:
        src.send("A0")
    st.session_state.alarm = alarm

    if alarm:
        st.error(f"🚨 LEAK DETECTED - {CLASS_NAMES.get(best, best)}  |  confidence {p_leak:.0%}  |  est. leak rate {rate:.2f} L/min")
    else:
        st.success(f"✅ NORMAL OPERATION  |  leak probability {p_leak:.0%}")

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.plotly_chart(network_figure(best if alarm else None, probs), width="stretch")
    with c2:
        m = st.columns(4)
        m[0].metric("P inlet (kPa)", f"{f['P1_mean']:.1f}")
        m[1].metric("P outlet (kPa)", f"{f['P2_mean']:.1f}")
        m[2].metric("Q in (L/min)", f"{f['Q1_mean']:.2f}")
        m[3].metric("ΔQ (L/min)", f"{f['dQ']:.3f}")
        t = (df.t_ms - df.t_ms.iloc[-1]) / 1000
        st.line_chart(pd.DataFrame({"P1": df.P1.values, "P2": df.P2.values}, index=t), height=140)
        st.line_chart(pd.DataFrame({"Q1": df.Q1.values, "Q2": df.Q2.values}, index=t), height=140)
        st.line_chart(pd.DataFrame({f"PZT{i}": df[f"AE{i}_rms"].values for i in range(1, 5)}, index=t), height=140)
    st.subheader("Leak event log")
    st.dataframe(pd.DataFrame(st.session_state.events), width="stretch", hide_index=True)


live()
