"""Shared settings for logger, feature extraction, training and dashboard.
Edit SERIAL_PORT and the geometry section to match your rig."""

SERIAL_PORT = "COM5"          # Windows: "COM5" ; Linux: "/dev/ttyUSB0" ; Mac: "/dev/cu.usbserial-xxxx"
BAUD = 115200

# ---------------------------------------------------------------------------
# Raw row format sent by the ESP32 every 100 ms (43 columns)
#   t_ms           ESP32 time since boot (ms)
#   P1, P2         inlet / outlet pressure (kPa, gauge)
#   Q1, Q2         inlet / outlet flow (L/min)
#   C1, C2         cumulative flow pulse counts
#   AE{i}_*        9 acoustic features per PZT channel i = 1..4, computed by the STM32
# ---------------------------------------------------------------------------
AE_FEATURES = ["rms", "peak", "p2p", "std", "energy", "crest", "hits", "dur", "fdom"]
RAW_COLUMNS = ["t_ms", "P1", "P2", "Q1", "Q2", "C1", "C2"] + [
    f"AE{i}_{f}" for i in range(1, 5) for f in AE_FEATURES
]

# Analysis window: 10 rows/s -> 10 rows = 1 s window, hop 5 rows = 0.5 s
WINDOW_ROWS = 10
HOP_ROWS = 5

# Class labels. 0 = no leak (including normal operational changes), 1..3 = leak at that point
CLASS_NAMES = {0: "NO LEAK", 1: "LEAK @ L1 (centre valve)", 2: "LEAK @ L2 (right)", 3: "LEAK @ L3 (left)"}

# ---------- Rig geometry (feet) for the dashboard map. EDIT with measured positions ----------
# Rectangle 5 ft x 4 ft, origin = bottom-left corner. Pump feeds the right edge.
LOOP = [(0, 0), (0, 4), (5, 4), (5, 0)]  # open rectangle: left edge, top edge, right edge
SENSORS = {
    "PT1/FS1 (inlet)":  (5, 0.4),
    "PT2/FS2 (outlet)": (0, 0.4),
    "PZT1": (5, 1.4), "PZT2": (3.8, 4), "PZT3": (1.2, 4), "PZT4": (0, 1.4),
}
LEAKS = {1: (2.5, 4), 2: (5, 2.6), 3: (0, 2.6)}  # L1 = centre T valve, L2/L3 = drilled holes

# Alarm logic: consecutive leak windows (0.5 s each) before raising the alarm
ALARM_CONSECUTIVE = 4
LEAK_PROB_THRESHOLD = 0.6
