"""Train + compare models, run the A/B/C sensor-fusion experiment, save the best model.
Usage:  python train.py
Outputs: models/leak_model.joblib, models/leak_rate_model.joblib, results/*.png, results/summary.csv"""
import os, warnings
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import StratifiedGroupKFold, GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (accuracy_score, f1_score, recall_score, precision_score,
                             confusion_matrix, ConfusionMatrixDisplay, mean_absolute_error)
from features import build_dataset, FEATURE_SETS
from config import CLASS_NAMES

warnings.filterwarnings("ignore")
os.makedirs("models", exist_ok=True)
os.makedirs("results", exist_ok=True)

X_all, y, groups, leak_lpm, data = build_dataset()
le = LabelEncoder().fit(y)
y_enc = le.transform(y)
print(f"Dataset: {len(X_all)} windows from {groups.nunique()} runs | class counts: {y.value_counts().sort_index().to_dict()}")


def models():
    m = {
        "LogReg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
        "SVM-RBF": make_pipeline(StandardScaler(), SVC(C=10, gamma="scale", probability=True, class_weight="balanced")),
        "RandomForest": RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced",
                                               n_jobs=-1, random_state=0),
    }
    try:
        from xgboost import XGBClassifier
        m["XGBoost"] = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08, subsample=0.9,
                                     colsample_bytree=0.8, eval_metric="mlogloss", random_state=0)
    except ImportError:
        print("(xgboost not installed - skipping)")
    return m


# Split by RUN, never by window (windows from the same run are near-duplicates)
cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
rows, preds_store = [], {}
for set_name, cols in FEATURE_SETS.items():
    X = X_all if cols is None else X_all[cols]
    for name, model in models().items():
        pred = cross_val_predict(model, X, y_enc, groups=groups, cv=cv)
        pred_lab = le.inverse_transform(pred)
        true_leak, pred_leak = (y > 0).astype(int), (pred_lab > 0).astype(int)
        rows.append(dict(features=set_name, model=name,
                         accuracy=accuracy_score(y, pred_lab),
                         macro_F1=f1_score(y, pred_lab, average="macro"),
                         leak_recall=recall_score(true_leak, pred_leak),
                         leak_precision=precision_score(true_leak, pred_leak, zero_division=0)))
        preds_store[(set_name, name)] = pred_lab
        print(f"  {set_name:16s} {name:12s} acc={rows[-1]['accuracy']:.3f}  F1={rows[-1]['macro_F1']:.3f}  "
              f"leak recall={rows[-1]['leak_recall']:.3f}")

summary = pd.DataFrame(rows)
summary.to_csv("results/summary.csv", index=False)

# --- Physics baseline (no ML): leak if flow imbalance exceeds 3 sigma of normal runs ---
normal = X_all[y == 0]["dQ"]
thr = normal.mean() + 3 * normal.std()
base_pred = (X_all["dQ"] > thr).astype(int)
print(f"\nPhysics baseline (dQ > {thr:.3f} L/min): leak recall={recall_score((y > 0).astype(int), base_pred):.3f}, "
      f"precision={precision_score((y > 0).astype(int), base_pred, zero_division=0):.3f}")
print(f"=> Minimum detectable leak rate (3-sigma of flow imbalance) ~ {3 * normal.std():.3f} L/min")

# --- Pick best full-fusion model by macro F1 (tie-break on leak recall) ---
full = summary[summary.features == "C_full_fusion"].sort_values(["macro_F1", "leak_recall"], ascending=False)
best_name = full.iloc[0]["model"]
print(f"\nBest model on full fusion: {best_name}")

labels_present = sorted(y.unique())
disp_names = [CLASS_NAMES.get(l, str(l)) for l in labels_present]
cm = confusion_matrix(y, preds_store[("C_full_fusion", best_name)], labels=labels_present)
ConfusionMatrixDisplay(cm, display_labels=disp_names).plot(cmap="Blues", xticks_rotation=30)
plt.title(f"{best_name} - full fusion (cross-validated by run)")
plt.tight_layout(); plt.savefig("results/confusion_matrix.png", dpi=150); plt.close()

pivot = summary.pivot(index="model", columns="features", values="macro_F1")
pivot.plot(kind="bar", figsize=(8, 4), ylim=(0, 1.05))
plt.ylabel("Macro F1 (CV by run)"); plt.title("Sensor fusion comparison A / B / C")
plt.tight_layout(); plt.savefig("results/fusion_comparison.png", dpi=150); plt.close()

# --- Fit final classifier on ALL data and save ---
final = models()[best_name].fit(X_all, y_enc)
joblib.dump(dict(model=final, features=list(X_all.columns), label_encoder=le, name=best_name), "models/leak_model.joblib")

rf = final if hasattr(final, "feature_importances_") else RandomForestClassifier(n_estimators=300, random_state=0).fit(X_all, y_enc)
imp = pd.Series(rf.feature_importances_, index=X_all.columns).sort_values()[-15:]
imp.plot(kind="barh", figsize=(7, 5)); plt.title("Top 15 features"); plt.tight_layout()
plt.savefig("results/feature_importance.png", dpi=150); plt.close()

# --- Leak RATE regression (only windows with a measured leak) ---
mask = (y > 0) & (leak_lpm > 0)
if mask.sum() > 20 and groups[mask].nunique() >= 3:
    Xr, yr, gr = X_all[mask], leak_lpm[mask], groups[mask]
    reg = RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=0, n_jobs=-1)
    pr = cross_val_predict(reg, Xr, yr, groups=gr, cv=GroupKFold(n_splits=min(5, gr.nunique())))
    print(f"\nLeak-rate model MAE = {mean_absolute_error(yr, pr):.3f} L/min   "
          f"(physics dQ only: {mean_absolute_error(yr, Xr['dQ'].clip(0)):.3f} L/min)")
    joblib.dump(dict(model=reg.fit(Xr, yr), features=list(X_all.columns)), "models/leak_rate_model.joblib")
else:
    print("\nNot enough leak runs with measured leak_lpm to train the leak-rate model yet.")

print("\nSaved: models/leak_model.joblib, results/summary.csv, results/*.png")
