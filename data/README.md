# Data

Recorded runs live in `python/data/raw/` (created by `logger.py`) and are **not committed** by default
(see `.gitignore`). To share a final dataset, copy it here (e.g. `data/final_dataset/`) and commit it
deliberately.

Each run = two files:

- `run_XXXX.csv` — 43 columns, 10 rows per second (format in `docs/04_software_and_data.md`)
- `run_XXXX.json` — label and metadata:

```json
{ "run_id": 17, "label": 1, "valve": 50, "leak_lpm": 0.8,
  "condition": "L1 half open, pump 100%", "start": "2026-11-05T14:02:11" }
```

Labels: 0 = no leak, 1 = L1 (centre valve), 2 = L2 (right hole), 3 = L3 (left hole).
