"""Real-time leak monitoring dashboard.
Live from ESP32:     streamlit run dashboard.py
Replay a recording:  streamlit run dashboard.py -- --replay data/raw/run_0003.csv

Sidebar: tare (Z), start/stop recording a labelled run (same files as logger.py), silence the buzzer.
Close logger.py and the Arduino Serial Monitor first: only one program can use the COM port.
"""
import argparse, collections, json, os, sys, threading, time
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import (SERIAL_PORT, BAUD, RAW_COLUMNS, WINDOW_ROWS, CLASS_NAMES, LOOP, SENSORS, LEAKS,
                    ALARM_CONSECUTIVE, LEAK_PROB_THRESHOLD)
from features import window_features
from check_runs import GAP_MS, STALE_ROWS, CLIP_PEAK, longest_repeat

ap = argparse.ArgumentParser()
ap.add_argument("--replay", default=None)
ap.add_argument("--port", default=SERIAL_PORT)
args, _ = ap.parse_known_args(sys.argv[1:])
LIVE = args.replay is None

st.set_page_config(page_title="Hydraulic Leak Monitor - Group 32", layout="wide")

HEALTH_ROWS = 50     # sensor health is judged on the last 5 s
P_RANGE = (-20, 1000)  # kPa; HK2016 is 0-1 MPa, a reading outside this means wiring/supply trouble
ICON = {"ok": "🟢", "warn": "🟡", "fail": "🔴"}


class Source:
    """Background thread that fills a ring buffer with raw rows (from serial or a replay file)
    and, while recording, writes every row to data/raw/run_XXXX.csv exactly like logger.py."""
    def __init__(self, replay, port):
        self.buf = collections.deque(maxlen=600)   # last 60 s
        self.msgs = collections.deque(maxlen=8)    # '#' lines from the ESP32 (replies, warnings)
        self.ser = None
        self.status = "starting"
        self.last_rx = 0.0
        self.lock = threading.Lock()
        self.rec = None
        target = self._replay if replay else self._serial
        threading.Thread(target=target, args=(replay or port,), daemon=True).start()

    def _add(self, values, line):
        self.buf.append(values)
        self.last_rx = time.time()
        with self.lock:
            if self.rec:
                self.rec["file"].write(line + "\n")
                self.rec["rows"] += 1

    def _serial(self, port):
        import serial
        while True:
            try:
                self.ser = serial.Serial(port, BAUD, timeout=1)
                self.status = f"live on {port}"
                while True:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if line.startswith("#"):
                        self.msgs.append(f"{datetime.now():%H:%M:%S} {line[1:].strip()}")
                        continue
                    v = line.split(",")
                    if len(v) == len(RAW_COLUMNS) and not line.startswith("t_ms"):
                        try:
                            self._add([float(x) for x in v], line)
                        except ValueError:
                            pass
            except Exception as e:
                self.ser = None
                self.status = f"serial error: {e} (retrying)"
                time.sleep(2)

    def _replay(self, path):
        df = pd.read_csv(path)[RAW_COLUMNS]
        self.status = f"replaying {os.path.basename(path)}"
        while True:
            for row in df.values:
                self.buf.append(list(row))
                self.last_rx = time.time()
                time.sleep(0.1)

    def send(self, cmd):
        if self.ser is not None:
            try:
                self.ser.write((cmd + "\n").encode())
                return True
            except Exception:
                pass
        return False

    def start_recording(self, label, leak_lpm, valve, condition):
        os.makedirs("data/raw", exist_ok=True)
        existing = [f for f in os.listdir("data/raw") if f.startswith("run_") and f.endswith(".csv")]
        run_id = 1 + max([int(f[4:8]) for f in existing], default=0)
        base = f"data/raw/run_{run_id:04d}"
        meta = dict(run_id=run_id, label=label, valve=valve, leak_lpm=leak_lpm,
                    condition=condition, start=datetime.now().isoformat(timespec="seconds"))
        with open(base + ".json", "w") as f:
            json.dump(meta, f, indent=2)
        out = open(base + ".csv", "w")
        out.write(",".join(RAW_COLUMNS) + "\n")
        with self.lock:
            self.rec = dict(file=out, base=base, meta=meta, rows=0, t0=time.time())

    def stop_recording(self, leak_lpm):
        with self.lock:
            rec, self.rec = self.rec, None
        if not rec:
            return None
        rec["file"].close()
        rec["meta"]["leak_lpm"] = leak_lpm        # the jug result is often only known at the end
        with open(rec["base"] + ".json", "w") as f:
            json.dump(rec["meta"], f, indent=2)
        return rec


@st.cache_resource
def get_source():
    return Source(args.replay, args.port)


@st.cache_resource
def get_models():
    clf = joblib.load("models/leak_model.joblib")
    reg = joblib.load("models/leak_rate_model.joblib") if os.path.exists("models/leak_rate_model.joblib") else None
    return clf, reg


def sensor_health(df, age_s):
    """[(name, status, message)] from the last 5 s of rows. status: ok / warn / fail."""
    w = df.iloc[-HEALTH_ROWS:]
    out = []
    dt = np.diff(w.t_ms.to_numpy())
    gaps = int((dt > GAP_MS).sum())
    if age_s > 1:
        out.append(("ESP32", "fail", f"no data for {age_s:.0f} s"))
    elif gaps:
        out.append(("ESP32", "warn", f"{gaps} gaps in last 5 s"))
    else:
        out.append(("ESP32", "ok", "10 rows/s"))

    ae = w[[c for c in RAW_COLUMNS if c.startswith("AE")]].to_numpy()
    lost = (ae == 0).all(axis=1)
    if lost[-1]:
        out.append(("STM32", "fail", "no AE data: check PA9 → GPIO16, GND"))
    elif lost.any():
        out.append(("STM32", "warn", f"AE dropped in {lost.sum()} rows"))
    else:
        out.append(("STM32", "ok", "AE data arriving"))

    for c in ("P1", "P2"):
        v = w[c]
        if not P_RANGE[0] <= v.iloc[-1] <= P_RANGE[1]:
            out.append((c, "fail", f"{v.iloc[-1]:.0f} kPa out of range: wiring/5 V?"))
        elif v.nunique() == 1:
            out.append((c, "fail", f"stuck at {v.iloc[-1]:.1f} kPa"))
        else:
            out.append((c, "ok", f"{v.mean():.0f} kPa"))

    q1, q2 = w.Q1.mean(), w.Q2.mean()
    for c, q, other in (("Q1", q1, q2), ("Q2", q2, q1)):
        if q == 0 and other > 0.2:
            out.append((c, "fail", "no pulses while the other flows"))
        elif q == 0:
            out.append((c, "warn", "no flow (pump off?)"))
        else:
            out.append((c, "ok", f"{q:.2f} L/min"))

    ok_rows = w[~lost]
    for i in range(1, 5):
        if lost[-1] or ok_rows.empty:
            out.append((f"PZT{i}", "fail", "no AE data (STM32)"))
            continue
        rms, peak = ok_rows[f"AE{i}_rms"].to_numpy(), ok_rows[f"AE{i}_peak"].to_numpy()
        if len(rms) >= STALE_ROWS and np.all(rms == rms[0]):
            out.append((f"PZT{i}", "fail", f"stuck at {rms[0]:g} (channel dead?)"))
        elif len(rms) >= STALE_ROWS and longest_repeat(rms) >= STALE_ROWS:
            out.append((f"PZT{i}", "warn", "stale values"))
        elif (peak >= CLIP_PEAK).mean() > 0.01:
            out.append((f"PZT{i}", "warn", "clipping: gain too high?"))
        else:
            out.append((f"PZT{i}", "ok", f"rms {rms.mean():.0f}"))
    return out


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


def probability_figure(hist):
    """Leak probability over the last 60 s, alarm threshold line and alarm periods shaded."""
    now = time.time()
    x = [h[0] - now for h in hist]
    y = [h[1] for h in hist]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#2a78d6", width=2),
                               hovertemplate="%{x:.1f} s: %{y:.0%}<extra>leak probability</extra>"))
    start = None
    for (t, _, alarm), nxt in zip(hist, list(hist)[1:] + [None]):
        if alarm and start is None:
            start = t
        if start is not None and (nxt is None or not nxt[2]):
            fig.add_vrect(x0=start - now, x1=t - now, fillcolor="#d03b3b", opacity=0.12, line_width=0,
                          annotation_text="alarm", annotation_position="top left")
            start = None
    fig.add_hline(y=LEAK_PROB_THRESHOLD, line=dict(color="#898781", width=1, dash="dash"),
                  annotation_text=f"threshold {LEAK_PROB_THRESHOLD:.0%}", annotation_position="bottom left")
    fig.update_layout(height=230, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                      title=dict(text="Leak probability (last 60 s)", font=dict(size=14)),
                      xaxis=dict(range=[-60, 0], title="seconds ago"),
                      yaxis=dict(range=[0, 1.02], tickformat=".0%"))
    return fig


src = get_source()
clf, reg = get_models()
le, feat_cols = clf["label_encoder"], clf["features"]
if "streak" not in st.session_state:
    st.session_state.streak, st.session_state.alarm, st.session_state.events = 0, False, []
    st.session_state.silenced, st.session_state.last_t = False, None
    st.session_state.hist = collections.deque(maxlen=120)   # (wall time, p_leak, alarm), 2 per s

# ---------------- Controls (sidebar, outside the auto-refresh) ----------------
with st.sidebar:
    st.header("Controls")
    if not LIVE:
        st.caption("Replay mode: tare and recording need the live ESP32.")

    if st.button("Tare pressure (Z)", disabled=not LIVE, width="stretch",
                 help="Pump must be OFF. Zeroes P1/P2 and the STM32 AE baseline."):
        st.toast("Tare sent (Z)" if src.send("Z") else "ESP32 not connected")

    if st.button("🔕 Silence alarm", width="stretch",
                 help="Stops the buzzer until this alarm clears. The alarm stays on screen."):
        st.session_state.silenced = True
        src.send("A0")

    st.subheader("Recording")
    recording = src.rec is not None
    label = st.selectbox("Label", list(CLASS_NAMES), format_func=lambda k: f"{k} · {CLASS_NAMES[k]}",
                         disabled=recording)
    valve = st.number_input("Valve opening (%)", 0.0, 100.0, 0.0, 5.0, disabled=recording)
    cond = st.text_input("Condition", placeholder="e.g. L2 open, pump 100 %", disabled=recording)
    leak_lpm = st.number_input("Measured leak (L/min)", 0.0, 10.0, 0.0, 0.01, format="%.3f",
                               help="Can be entered while recording: it is saved when you press Stop.")
    if not recording:
        if st.button("⏺ Start recording", type="primary", disabled=not LIVE, width="stretch"):
            src.start_recording(label, leak_lpm, valve, cond)
            st.rerun()
    else:
        if st.button("⏹ Stop recording", type="primary", width="stretch"):
            rec = src.stop_recording(leak_lpm)
            st.session_state.saved = f"Saved {rec['rows']} rows → {rec['base']}.csv"
            if rec["meta"]["label"] and not leak_lpm:
                st.session_state.saved += "  ⚠️ leak run without measured L/min: edit the JSON"
            st.rerun()
    if st.session_state.get("saved"):
        st.success(st.session_state.saved)
        st.caption("Run `python check_runs.py` after the session.")

    if src.msgs:
        st.subheader("ESP32 messages")
        st.code("\n".join(src.msgs), language=None)

st.title("✈️ Aircraft Hydraulic Leak Detection - Live Monitor")
st.caption(f"Group 32, IIT Mandi | model: {clf['name']}")


@st.fragment(run_every=0.5)
def live():
    rows = list(src.buf)
    rec = src.rec
    line = f"Source: {src.status} | buffered rows: {len(rows)}"
    if rec:
        line += f" | 🔴 REC {os.path.basename(rec['base'])}: {rec['rows']} rows ({time.time() - rec['t0']:.0f} s)"
    st.write(line)
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

    # Alarm logic: require several consecutive leak windows -> rejects transients/taps.
    # Count only windows with new data, so a stalled link cannot raise or hold an alarm.
    new_data = df.t_ms.iloc[-1] != st.session_state.last_t
    st.session_state.last_t = df.t_ms.iloc[-1]
    if new_data:
        st.session_state.streak = st.session_state.streak + 1 if (p_leak >= LEAK_PROB_THRESHOLD and best > 0) else 0
    alarm = st.session_state.streak >= ALARM_CONSECUTIVE
    if new_data:
        st.session_state.hist.append((time.time(), p_leak, alarm))
    rate = float(reg["model"].predict(X)[0]) if (alarm and reg) else max(f["dQ"], 0)
    if alarm and not st.session_state.alarm:
        ev = dict(time=datetime.now().strftime("%H:%M:%S"), location=CLASS_NAMES.get(best, best),
                  confidence=round(p_leak, 3), leak_rate_lpm=round(rate, 3), P1=round(f["P1_mean"], 1),
                  Q1=round(f["Q1_mean"], 3), Q2=round(f["Q2_mean"], 3))
        st.session_state.events.insert(0, ev)
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([ev]).to_csv("data/events.csv", mode="a", index=False, header=not os.path.exists("data/events.csv"))
        st.session_state.silenced = False
        src.send("A1")
    if not alarm and st.session_state.alarm:
        st.session_state.silenced = False
        src.send("A0")
    st.session_state.alarm = alarm

    if alarm:
        muted = "  |  🔕 buzzer silenced" if st.session_state.silenced else "  |  silence the buzzer in the sidebar"
        st.error(f"🚨 LEAK DETECTED - {CLASS_NAMES.get(best, best)}  |  confidence {p_leak:.0%}  |  est. leak rate {rate:.2f} L/min{muted}")
    else:
        st.success(f"✅ NORMAL OPERATION  |  leak probability {p_leak:.0%}")

    health = sensor_health(df, time.time() - src.last_rx)
    worst = "fail" if any(h[1] == "fail" for h in health) else "warn" if any(h[1] == "warn" for h in health) else "ok"
    with st.expander(f"{ICON[worst]} Sensor health", expanded=worst != "ok"):
        cols = st.columns(5)
        for k, (name, status, msg) in enumerate(health):
            cols[k % 5].markdown(f"{ICON[status]} **{name}** · {status.upper()}  \n{msg}")
        if worst != "ok":
            st.caption("Predictions are unreliable while a sensor shows FAIL.")

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.plotly_chart(network_figure(best if alarm else None, probs), width="stretch")
    with c2:
        st.plotly_chart(probability_figure(st.session_state.hist), width="stretch")
        m = st.columns(4)
        m[0].metric("P inlet (kPa)", f"{f['P1_mean']:.1f}")
        m[1].metric("P outlet (kPa)", f"{f['P2_mean']:.1f}")
        m[2].metric("Q in (L/min)", f"{f['Q1_mean']:.2f}")
        m[3].metric("ΔQ (L/min)", f"{f['dQ']:.3f}")
    t = (df.t_ms - df.t_ms.iloc[-1]) / 1000
    s = st.columns(3)
    s[0].line_chart(pd.DataFrame({"P1": df.P1.values, "P2": df.P2.values}, index=t), height=160)
    s[1].line_chart(pd.DataFrame({"Q1": df.Q1.values, "Q2": df.Q2.values}, index=t), height=160)
    s[2].line_chart(pd.DataFrame({f"PZT{i}": df[f"AE{i}_rms"].values for i in range(1, 5)}, index=t), height=160)
    st.subheader("Leak event log")
    st.dataframe(pd.DataFrame(st.session_state.events), width="stretch", hide_index=True)


live()
