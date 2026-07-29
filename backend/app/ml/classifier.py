"""MODULE 2d — Inference: calibrated prediction + OOD flag + explanation.

Loads the trained bundle lazily; exposes ``classify_ear(ac, bc)`` returning
pattern, calibrated confidence, full probability table, an
out-of-distribution flag, and per-frequency importance weights the frontend
uses to glow the audiogram regions that drove the classification.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import joblib
import numpy as np

from app.ml.features import AC_FREQS, FEATURE_FREQS, build_features
from app.models.schemas import ThresholdValue, ear_to_numeric

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "model_bundle.joblib"

#: Predictions with max calibrated probability below this are flagged for
#: human review regardless of the OOD detector.
CONFIDENCE_FLOOR = 0.6

PATTERN_LABELS = {
    "flat": "Flat",
    "sloping_high_frequency": "Sloping (high-frequency)",
    "ski_slope": "Ski-slope",
    "rising": "Rising (low-frequency)",
    "noise_notch_4k": "Noise notch (4 kHz)",
    "cookie_bite": "Cookie-bite (mid-frequency)",
    "corner_audiogram": "Corner audiogram",
}


@lru_cache(maxsize=1)
def _bundle():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"{MODEL_PATH} missing — run `python -m app.ml.generate_dataset` "
            "then `python -m app.ml.train`"
        )
    return joblib.load(MODEL_PATH)


def model_available() -> bool:
    return MODEL_PATH.exists()


def classify_ear(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
    explain: bool = True,
) -> Optional[dict]:
    """Classify one ear's audiogram configuration. None if no AC data.

    ``explain=False`` skips counterfactual search and case retrieval — used
    by batch screening, where only the label and confidence are shown.
    """
    ac_n = ear_to_numeric(ac)
    if not any(v is not None for v in ac_n.values()):
        return None
    bc_n = ear_to_numeric(bc)

    b = _bundle()
    x = build_features(ac_n, bc_n).reshape(1, -1)

    probs = b["calibrated"].predict_proba(x)[0]
    order = np.argsort(probs)[::-1]
    classes = list(b["calibrated"].classes_)
    top = classes[order[0]]
    confidence = float(probs[order[0]])

    iso_score = float(b["iso"].score_samples(x)[0])
    ood_reasons = []
    if confidence < CONFIDENCE_FLOOR:
        ood_reasons.append(
            f"low classifier confidence ({confidence:.0%} < {CONFIDENCE_FLOOR:.0%})"
        )
    if iso_score < b["iso_threshold"]:
        ood_reasons.append(
            "audiogram shape far from training distribution (isolation forest)"
        )

    return {
        "pattern": top,
        "pattern_label": PATTERN_LABELS.get(top, top),
        "confidence": round(confidence, 4),
        "probabilities": {
            c: round(float(p), 4) for c, p in zip(classes, probs)
        },
        "ood": bool(ood_reasons),
        "ood_reasons": ood_reasons,
        "ood_message": (
            "Atypical audiogram — priority human review" if ood_reasons else None
        ),
        "freq_importance": _freq_importance(b, x[0]),
        "model_accuracy": round(float(b["holdout_accuracy"]), 4),
        **(_explanations(b, ac_n, bc_n, top) if explain
           else {"counterfactuals": [], "counterfactual_note": None,
                 "similar_cases": None}),
    }


def _explanations(b, ac_n, bc_n, top: str) -> dict:
    cfs = _counterfactuals(b, ac_n, bc_n, top)
    note = None
    if not cfs:
        note = (
            f"No single-frequency change of up to {max(_CF_DELTAS)} dB would alter "
            "this classification — the pattern is unambiguous."
        )
    return {
        "counterfactuals": cfs,
        "counterfactual_note": note,
        "similar_cases": _similar_cases(b, build_features(ac_n, bc_n), top),
    }


#: Threshold changes probed when searching for a minimal class-flipping edit.
_CF_DELTAS = [-50, -40, -30, -20, -15, -10, -5, 5, 10, 15, 20, 30, 40, 50]


def _counterfactuals(b, ac_n, bc_n, predicted: str) -> list:
    """Smallest single-frequency change that would flip the classification.

    Answers "what would have to be different for this to be something
    else?" — usually more informative to a clinician than importance
    weights, because it names the threshold and the number of decibels.

    All probes are stacked into one matrix and predicted in a single call;
    the uncalibrated forest is used because only the argmax label matters
    here, and it is five times cheaper than the calibrated ensemble.
    """
    probes, meta = [], []
    for f in AC_FREQS:
        if ac_n.get(f) is None:
            continue
        for delta in sorted(_CF_DELTAS, key=abs):
            value = float(min(120, max(-10, ac_n[f] + delta)))
            if value == ac_n[f]:
                continue
            probe = dict(ac_n)
            probe[f] = value
            probes.append(build_features(probe, bc_n))
            meta.append((f, delta))
    if not probes:
        return []

    preds = b["rf"].predict(np.vstack(probes))

    best_per_freq: Dict[int, dict] = {}
    for (f, delta), pred in zip(meta, preds):
        if pred == predicted or f in best_per_freq:
            continue
        best_per_freq[f] = {
            "freq": f,
            "delta_db": delta,
            "direction": "better" if delta < 0 else "worse",
            "new_pattern": str(pred),
            "new_label": PATTERN_LABELS.get(str(pred), str(pred)),
            "text": (
                f"If {f} Hz were {abs(delta)} dB "
                f"{'better' if delta < 0 else 'worse'}, this would classify as "
                f"{PATTERN_LABELS.get(str(pred), str(pred))}."
            ),
        }
    out = sorted(best_per_freq.values(), key=lambda c: abs(c["delta_db"]))
    return out[:3]


def _similar_cases(b, x: np.ndarray, predicted: str) -> Optional[dict]:
    """Case-based support: nearest reference audiograms and their labels."""
    if "X_ref" not in b:
        return None
    z = (b["X_ref"] - b["global_mean"]) / b["global_std"]
    zq = (x - b["global_mean"]) / b["global_std"]
    dist = np.linalg.norm(z - zq, axis=1)
    k = 12
    idx = np.argsort(dist)[:k]
    labels = [str(b["y_ref"][i]) for i in idx]
    agree = sum(1 for l in labels if l == predicted)
    top_other = None
    others = [l for l in labels if l != predicted]
    if others:
        top_other = max(set(others), key=others.count)
    return {
        "k": k,
        "agree": agree,
        "agreement_pct": round(100 * agree / k, 1),
        "neighbour_labels": labels,
        "dissenting_label": top_other,
        "dissenting_display": PATTERN_LABELS.get(top_other, top_other) if top_other else None,
        "example_thresholds": [
            {str(f): float(b["ref_thresholds"][i][j]) for j, f in enumerate(AC_FREQS)}
            for i in idx[:3]
        ],
        "text": (
            f"{agree} of the {k} most similar reference audiograms carry the same "
            f"label ({PATTERN_LABELS.get(predicted, predicted)})."
        ),
    }


def _freq_importance(b, x: np.ndarray) -> Dict[int, float]:
    """Per-frequency contribution weights for the chart glow overlay.

    Deterministic explanation: each feature's global RandomForest importance
    is scaled by how far this input's feature deviates from the training
    mean (|z-score|), then attributed to the audiogram frequencies that
    feature describes. Normalized so the strongest frequency = 1.0.
    """
    z = np.abs((x - b["global_mean"]) / b["global_std"])
    contrib = b["rf"].feature_importances_ * z
    weights = {f: 0.0 for f in AC_FREQS}
    for c, freqs in zip(contrib, FEATURE_FREQS):
        for f in freqs:
            weights[f] += c / len(freqs)
    peak = max(weights.values()) or 1.0
    return {f: round(w / peak, 3) for f, w in weights.items()}
