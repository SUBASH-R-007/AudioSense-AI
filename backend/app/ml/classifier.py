"""MODULE 2d — Inference: calibrated prediction + OOD flag + explanation.

Loads the trained bundle lazily; exposes ``classify_ear(ac, bc)`` returning
pattern, calibrated confidence, full probability table, an
out-of-distribution flag, and per-frequency importance weights the frontend
uses to glow the audiogram regions that drove the classification.

The forest only knows seven loss configurations and names one for any
input. Rule gates around it (``app.ml.features``) decide what is shown:
too few frequencies -> no pattern; thresholds within normal limits ->
"normal"; otherwise the model's label, with ``reliable`` saying whether it
may drive etiology text and advice. The raw model output is always kept in
the ``model_*`` fields.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np

from app.ml.features import (
    AC_FREQS,
    FEATURE_FREQS,
    NORMAL_FREQ_LIMIT,
    NORMAL_PTA_LIMIT,
    build_features,
    coverage,
    isolated_outliers,
    label_shape_caveat,
    normal_average_caveat,
    notch_retest_note,
    outlier_blocks,
    plausibility_reasons,
    pta4,
    steep_improvements,
    steep_worsenings,
    within_normal_limits,
)
from app.models.schemas import ThresholdValue, ear_to_numeric

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "model_bundle.joblib"

#: Predictions with max calibrated probability below this are flagged for
#: human review regardless of the OOD detector.
CONFIDENCE_FLOOR = 0.6

#: A label is reliable — fit to drive etiology wording, hearing-protection
#: advice or a verdict headline — only at or above this calibrated
#: probability. Between the floor and this value the label is shown as
#: provisional. The calibration is on synthetic data (see /api/validate), so
#: the bar is set well above the review floor.
RELIABLE_CONFIDENCE = 0.8

PATTERN_LABELS = {
    "flat": "Flat",
    "sloping_high_frequency": "Sloping (high-frequency)",
    "ski_slope": "Ski-slope",
    "rising": "Rising (low-frequency)",
    "noise_notch_4k": "Noise notch (4 kHz)",
    "cookie_bite": "Cookie-bite (mid-frequency)",
    "corner_audiogram": "Corner audiogram",
    # Rule-gated, never predicted by the model: the training set has no
    # normal class, so without the gate every normal ear became a loss.
    "normal": "Within normal limits",
}

#: Shown in place of a pattern when too few frequencies were tested.
NOT_CLASSIFIED_LABEL = "Not classified — insufficient frequencies"


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

    Every result carries ``reliable`` and ``reliability_note``. ``reliable``
    is True only for a model label (not "normal", not unclassified) with
    calibrated confidence >= RELIABLE_CONFIDENCE, all six frequencies
    measured (nothing imputed), no out-of-distribution or plausibility
    flag, and — when the four-frequency average is normal — abnormal
    thresholds that form the shape named (``normal_average_caveat``).
    Downstream wording (etiology, advice, cohort statistics) must not act on
    a label that is not reliable.
    """
    # Only the six model frequencies describe the shape; any other key would
    # be silently dropped by the feature builder anyway.
    ac_n = {f: v for f, v in ear_to_numeric(ac).items() if f in AC_FREQS}
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
    model_ood_reasons = []
    if confidence < CONFIDENCE_FLOOR:
        model_ood_reasons.append(
            f"low classifier confidence ({confidence:.0%} < {CONFIDENCE_FLOOR:.0%})"
        )
    if iso_score < b["iso_threshold"]:
        model_ood_reasons.append(
            "audiogram shape far from training distribution (isolation forest)"
        )

    cov = coverage(ac_n)
    raw = {
        "model_pattern": top,
        "model_pattern_label": PATTERN_LABELS.get(top, top),
        "model_confidence": round(confidence, 4),
        "model_ood_reasons": model_ood_reasons,
        "probabilities": {
            c: round(float(p), 4) for c, p in zip(classes, probs)
        },
        "frequencies_tested": cov["tested"],
        "frequencies_imputed": cov["untested"],
        "model_accuracy": round(float(b["holdout_accuracy"]), 4),
    }

    # ---- gate 1: too little of the audiogram to describe a shape ---------
    if not cov["adequate"]:
        return {
            **raw,
            **_gated(None, NOT_CLASSIFIED_LABEL, "insufficient_frequencies",
                     confidence=0.0, note=cov["note"]),
            "outliers": [],
            "outlier_blocks": [],
            "steep_improvements": [],
            "steep_worsenings": [],
            "counterfactual_note": (
                "Not classified: " + cov["note"] + "." if explain else None),
        }

    # ---- gate 2: nothing to classify — hearing within normal limits ------
    if within_normal_limits(ac_n):
        note = (
            f"Thresholds within normal limits: PTA {round(pta4(ac_n), 1):g} dB HL "
            f"(< {NORMAL_PTA_LIMIT:g}, WHO 2021) and no tested threshold above "
            f"{NORMAL_FREQ_LIMIT:g} dB HL — there is no loss configuration to "
            "classify"
            + (f"; {_fmt(cov['untested'])} not tested" if cov["untested"] else "")
        )
        # The normal call is a definition applied to measured thresholds, not
        # an estimate, so it carries full confidence; it is still not
        # "reliable" because there is no configuration to act on.
        return {
            **raw,
            **_gated("normal", PATTERN_LABELS["normal"], "normal_gate",
                     confidence=1.0, note=note),
            "outliers": [],
            "outlier_blocks": [],
            "steep_improvements": [],
            "steep_worsenings": [],
            "counterfactual_note": (
                "No configuration is classified for an ear whose thresholds "
                "are within normal limits." if explain else None),
        }

    # ---- model label, with its reliability --------------------------------
    # The label is passed so that a deep 4 kHz noise notch does not withdraw
    # the noise-notch label it is evidence for; it still asks for a retest.
    plausibility = plausibility_reasons(ac_n, top)
    retest = notch_retest_note(ac_n, top)
    ood_reasons = model_ood_reasons + plausibility
    caveats: List[str] = list(ood_reasons)
    if CONFIDENCE_FLOOR <= confidence < RELIABLE_CONFIDENCE:
        caveats.append(
            f"classifier confidence {confidence:.0%} is below the "
            f"{RELIABLE_CONFIDENCE:.0%} needed to act on a configuration label")
    # An ear graded Normal hearing by its average (WHO 2021) with a threshold
    # or two above 20 dB HL is not a loss configuration unless those
    # thresholds form the shape named; the forest, never having seen such
    # ears, otherwise calls one raised 250 Hz threshold a flat loss.
    shape = normal_average_caveat(ac_n, top)
    if shape:
        caveats.append(shape)
    mismatch = label_shape_caveat(ac_n, top)
    if mismatch:
        caveats.append(mismatch)
    if cov["untested"]:
        caveats.append(
            f"{_fmt(cov['untested'])} not tested — estimated from neighbouring "
            "thresholds, so the shape there is assumed, not measured")
    reliable = not caveats
    if reliable:
        note = (f"All six frequencies measured, {confidence:.0%} calibrated "
                "confidence, within the trained distribution")
    else:
        note = "; ".join(caveats)
        note = note[0].upper() + note[1:]
    if retest:
        note = f"{note}; {retest}"

    return {
        **raw,
        "pattern": top,
        "pattern_label": PATTERN_LABELS.get(top, top),
        "pattern_source": "model",
        "confidence": round(confidence, 4),
        "ood": bool(ood_reasons),
        "ood_reasons": ood_reasons,
        "ood_message": (
            "Atypical audiogram — priority human review" if ood_reasons else None
        ),
        "reliable": reliable,
        "reliability_note": note,
        "retest_note": retest,
        "outliers": isolated_outliers(ac_n),
        "outlier_blocks": outlier_blocks(ac_n),
        "steep_improvements": steep_improvements(ac_n),
        "steep_worsenings": steep_worsenings(ac_n),
        "freq_importance": _freq_importance(b, x[0]),
        **(_explanations(b, ac_n, bc_n, top) if explain
           else {"counterfactuals": [], "counterfactual_note": None,
                 "similar_cases": None}),
    }


def _fmt(freqs: List[int]) -> str:
    return ", ".join(f"{f} Hz" for f in freqs)


def _gated(pattern: Optional[str], label: str, source: str,
           confidence: float, note: str) -> dict:
    """Fields shared by every rule-gated (non-model) result.

    ``confidence`` stays numeric because consumers compare it with floors;
    for an unclassified ear it is 0.0 so any such comparison routes the case
    to a human. The glow overlay and counterfactuals are emptied because no
    model decision is being shown.
    """
    return {
        "pattern": pattern,
        "pattern_label": label,
        "pattern_source": source,
        "confidence": confidence,
        "ood": False,
        "ood_reasons": [],
        "ood_message": None,
        "reliable": False,
        "reliability_note": note,
        "retest_note": None,
        "freq_importance": {f: 0.0 for f in AC_FREQS},
        "counterfactuals": [],
        "similar_cases": None,
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
