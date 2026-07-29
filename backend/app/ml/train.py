"""MODULE 2c — Train the calibrated pattern classifier + OOD detector.

Artifacts written to backend/data/:
  - model_bundle.joblib   (calibrated classifier, raw RF, IsolationForest,
                           OOD threshold, per-class centroids, global stats)
  - accuracy_report.txt   (hold-out accuracy + per-class report)
  - confusion_matrix.png  (hold-out confusion matrix, for the judges)

Run:  python -m app.ml.train
"""
from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.model_selection import train_test_split

from app.ml.features import FEATURE_NAMES, features_from_dataframe

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def train() -> dict:
    df = pd.read_csv(DATA_DIR / "dataset.csv")
    X = features_from_dataframe(df)
    y = df["pattern"].to_numpy()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Raw forest: used for feature importances (explainability).
    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    rf.fit(X_tr, y_tr)

    # Calibrated forest: predict_proba values become trustworthy confidences.
    calibrated = CalibratedClassifierCV(
        RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1),
        method="sigmoid",
        cv=5,
    )
    calibrated.fit(X_tr, y_tr)

    y_pred = calibrated.predict(X_te)
    acc = accuracy_score(y_te, y_pred)
    report = classification_report(y_te, y_pred)

    # Out-of-distribution detector on the training feature distribution.
    iso = IsolationForest(n_estimators=200, random_state=42)
    iso.fit(X_tr)
    iso_threshold = float(np.percentile(iso.score_samples(X_tr), 1))

    # Per-class centroids + global stats for per-frequency explanations.
    classes = sorted(set(y))
    centroids = {c: X_tr[y_tr == c].mean(axis=0) for c in classes}
    global_mean = X_tr.mean(axis=0)
    global_std = X_tr.std(axis=0) + 1e-9

    # Reference subsample for case-based retrieval ("show me similar
    # audiograms from the training set"). Kept small so the bundle stays light.
    rng = np.random.default_rng(42)
    idx = rng.choice(len(X_tr), size=min(3000, len(X_tr)), replace=False)
    X_ref, y_ref = X_tr[idx], y_tr[idx]
    # Store the raw thresholds of each reference case so the UI can draw them.
    ref_thresholds = X_ref[:, :6]

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(DATA_DIR / "accuracy_report.txt", "w", encoding="utf-8") as fh:
        fh.write("AudioSense AI — Pattern Classifier Accuracy Report\n")
        fh.write("=" * 52 + "\n")
        fh.write(f"Dataset: {len(df)} synthetic audiograms, 7 patterns\n")
        fh.write(f"Model:   RandomForest(300) + sigmoid calibration (cv=5)\n")
        fh.write(f"Hold-out accuracy: {acc:.4f}\n\n")
        fh.write(report)
        fh.write(f"\nOOD detector: IsolationForest, threshold={iso_threshold:.4f} "
                 "(1st percentile of training scores)\n")

    cm = confusion_matrix(y_te, y_pred, labels=classes)
    fig, ax = plt.subplots(figsize=(9, 8))
    ConfusionMatrixDisplay(cm, display_labels=classes).plot(
        ax=ax, cmap="Blues", colorbar=False, xticks_rotation=45
    )
    ax.set_title(f"AudioSense AI — Confusion Matrix (hold-out acc {acc:.1%})")
    fig.tight_layout()
    fig.savefig(DATA_DIR / "confusion_matrix.png", dpi=150)
    plt.close(fig)

    bundle = {
        "calibrated": calibrated,
        "rf": rf,
        "iso": iso,
        "iso_threshold": iso_threshold,
        "classes": classes,
        "centroids": centroids,
        "global_mean": global_mean,
        "global_std": global_std,
        "feature_names": FEATURE_NAMES,
        "holdout_accuracy": acc,
        "X_ref": X_ref,
        "y_ref": y_ref,
        "ref_thresholds": ref_thresholds,
    }
    joblib.dump(bundle, DATA_DIR / "model_bundle.joblib", compress=3)
    return {"accuracy": acc, "n": len(df)}


if __name__ == "__main__":
    result = train()
    print(f"trained on {result['n']} rows — hold-out accuracy {result['accuracy']:.4f}")
    print(f"artifacts in {DATA_DIR}")
