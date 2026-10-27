# 5. Machine Learning

![ML pipeline](images/ml_pipeline.png)

## 5.1 Problem formulation

Two supervised tasks on the same input (one feature vector per 1 s window):

| Task | Output | Trained on |
|---|---|---|
| Classification | No leak / L1 / L2 / L3 (detection + localisation in one answer) | Run labels |
| Regression | Leak rate (L/min) | Leak volume measured with a jug each run |

## 5.2 Physics behind the features

**Flow — mass conservation.** Oil is practically incompressible:
`Q_leak = Q_in − Q_out = Q1 − Q2`. Direct leak signal and leak rate; no location information.

**Pressure — orifice flow.** `Q = Cd · A · √(2ΔP/ρ)` (Cd ≈ 0.6 for a sharp hole). A leak lowers
pressure downstream; P1, P2 and P1 − P2 shift. Weak location information.

**Acoustics — jet noise.** Oil forced through a hole forms a turbulent jet producing broadband
high-frequency noise. It attenuates with distance and at hose joints, so the nearest PZT hears it
loudest; the loudness *pattern* across four discs points to the leak.

| Sensor | Detect | Quantify | Localise | Weakness |
|---|---|---|---|---|
| Flow | Strong | Strong | None | No location |
| Pressure | Medium | Weak | Weak | Also changes with pump speed |
| Acoustic | Medium | Weak | Strong | Pump and bench noise |

## 5.3 Features (≈60 per window)

| Group | Features |
|---|---|
| Pressure (6) | P1_mean, P2_mean, dP = P1 − P2, P1_std, P2_std, P1_slope |
| Flow (6) | Q1_mean, Q2_mean, dQ = Q1 − Q2, dQ_rel = dQ/Q1, Q1_std, dP_per_Q2 = dP/Q1² |
| Acoustic per channel (10 × 4) | rms, peak, p2p, std, energy, crest, hits, dur, fdom, rms_var |
| Acoustic cross-channel (8) | AE_total, AEi_ratio = rms_i / Σrms (4), log-ratios of neighbours (3) |

Ratios (dQ_rel, AEi_ratio) stay stable when the pump runs faster or slower, which helps the model
generalise across days and speeds.

## 5.4 Models compared

| Model | How it works | Role |
|---|---|---|
| Logistic Regression | Linear boundaries | Baseline: shows whether non-linearity is needed |
| SVM (RBF kernel) | Curved maximum-margin boundary | Classic strong small-data method |
| **Random Forest** | 300 decision trees on random resamples and feature subsets; majority vote (bagging) | **Main model**: robust, no scaling, vote fraction = confidence, feature importance |
| XGBoost | Trees built sequentially, each correcting previous errors (gradient boosting), regularised | Main challenger |

Deep learning is not used: ≈70 runs is too little data, the features already encode the physics, and
tree models are easier to explain.

Leak rate: Random Forest Regressor, compared with the pure physics estimate (dQ).

## 5.5 Honest validation

- **Split by run, never by window.** Windows from one run are near-identical; mixing them between
  train and test inflates scores. `StratifiedGroupKFold` (5 folds) keeps each run wholly in one side.
- **A/B/C fusion experiment:** A = pressure only, B = pressure + flow, C = all features. Proves what
  each sensor type adds.
- **Physics baseline:** "leak if dQ > mean + 3σ of normal runs" — the ML must beat this.

## 5.6 Metrics

| Metric | Meaning |
|---|---|
| Accuracy | Fraction of windows classified correctly |
| Precision | Of windows flagged as leaks, fraction that were real |
| **Leak recall** | Of real leaks, fraction caught — most important for safety |
| Macro F1 | Average F1 over all four classes |
| Confusion matrix | Which leak is mistaken for which |
| MAE | Average leak-rate error (L/min) |
| Minimum detectable leak | 3σ of dQ during no-leak runs |

## 5.7 From prediction to alarm

Alarm only after **4 consecutive windows (2 s)** with leak probability ≥ 60 % (`config.py`).
Trade-off: 2 s delay versus far fewer false alarms from knocks and valve transients. Together with
"normal but disturbed" training runs, this meets the discrimination objective.

## 5.8 Outputs of `train.py`

`results/summary.csv` (all scores), `confusion_matrix.png`, `fusion_comparison.png`,
`feature_importance.png`, and `models/leak_model.joblib`, `models/leak_rate_model.joblib`.

## 5.9 Scope

The system localises leaks to **trained** positions (L1, L2, L3). It cannot pinpoint a leak at a
position never seen in training — the normal scope of a supervised, lab-scale demonstrator.
