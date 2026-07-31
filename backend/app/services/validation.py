"""Validation against expert-labelled audiograms.

THE LIMITATION THIS MODULE EXISTS TO ADDRESS
--------------------------------------------
The classifier's reported 99.9% hold-out accuracy is measured on data
produced by the same generator that produced its training set. That number
says the model learned the generator; it does NOT say the model agrees
with an audiologist. Quoting it as clinical accuracy would be misleading.

Real validation needs audiograms labelled by a qualified audiologist. This
module is the harness for exactly that: hand it a CSV of real cases with
expert labels and it reports agreement the way a clinical validation study
would — accuracy AND Cohen's kappa (which corrects for the agreement you
would get by chance alone), with a full confusion matrix.

The rules engine is treated separately and deliberately: degree, type and
disability are deterministic implementations of published guidelines, so
disagreement there is either a data-entry difference or a genuine bug, not
a modelling error. Kappa on those columns is a conformance check.

CSV columns: the same threshold columns as batch upload, plus any of
  expert_pattern, expert_grade, expert_type, expert_disability
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

from app.clinical import rules
from app.ml import classifier
from app.models.schemas import AC_FREQS, BC_FREQS

#: Free-text expert labels are normalized before comparison so that
#: "noise notch", "Noise Notch (4 kHz)" and "noise_notch_4k" all match.
PATTERN_ALIASES = {
    "flat": "flat",
    "sloping": "sloping_high_frequency",
    "sloping high frequency": "sloping_high_frequency",
    "high frequency": "sloping_high_frequency",
    "ski slope": "ski_slope",
    "skislope": "ski_slope",
    "precipitous": "ski_slope",
    "rising": "rising",
    "low frequency": "rising",
    "noise notch": "noise_notch_4k",
    "notch": "noise_notch_4k",
    "4k notch": "noise_notch_4k",
    "cookie bite": "cookie_bite",
    "mid frequency": "cookie_bite",
    "corner": "corner_audiogram",
    "corner audiogram": "corner_audiogram",
}


def normalize_pattern(value: str) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if not key:
        return None
    if key.replace(" ", "_") in classifier.PATTERN_LABELS:
        return key.replace(" ", "_")
    for alias, canonical in PATTERN_ALIASES.items():
        if alias in key:
            return canonical
    return key.replace(" ", "_")


def normalize_grade(value: str) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower()
    for grade in ("profound", "moderately severe", "severe", "moderate", "mild", "normal"):
        if grade in key:
            return {
                "normal": "Normal hearing",
                "mild": "Mild hearing loss",
                "moderate": "Moderate hearing loss",
                "moderately severe": "Moderately severe hearing loss",
                "severe": "Severe hearing loss",
                "profound": "Profound hearing loss",
            }[grade]
    return str(value).strip()


def normalize_type(value: str) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower()
    for word, canonical in (("mixed", "Mixed"), ("conduct", "Conductive"),
                            ("sensor", "Sensorineural"), ("normal", "Normal")):
        if word in key:
            return canonical
    return str(value).strip()


def _agreement(expert: List[str], predicted: List[str], name: str) -> Optional[dict]:
    """Accuracy, Cohen's kappa and the confusion matrix for one label set."""
    pairs = [(e, p) for e, p in zip(expert, predicted) if e is not None and p is not None]
    if len(pairs) < 2:
        return None
    e_vals = [p[0] for p in pairs]
    p_vals = [p[1] for p in pairs]
    labels = sorted(set(e_vals) | set(p_vals))
    correct = sum(1 for e, p in pairs if e == p)
    kappa = float(cohen_kappa_score(e_vals, p_vals, labels=labels))
    cm = confusion_matrix(e_vals, p_vals, labels=labels).tolist()

    return {
        "field": name,
        "n": len(pairs),
        "agreement": round(100 * correct / len(pairs), 1),
        "cohens_kappa": round(kappa, 3),
        "kappa_interpretation": _kappa_word(kappa),
        "labels": labels,
        "confusion_matrix": cm,
        "disagreements": [
            {"expert": e, "predicted": p} for e, p in pairs if e != p
        ][:20],
    }


def _kappa_word(k: float) -> str:
    """Landis & Koch (1977) benchmarks for kappa."""
    if k < 0:
        return "worse than chance"
    if k < 0.21:
        return "slight"
    if k < 0.41:
        return "fair"
    if k < 0.61:
        return "moderate"
    if k < 0.81:
        return "substantial"
    return "almost perfect"


def _cell(row, col):
    if col not in row or pd.isna(row[col]) or str(row[col]).strip() == "":
        return None
    v = str(row[col]).strip().upper()
    if v == "NR":
        return "NR"
    try:
        return int(float(v))
    except ValueError:
        return None


def _thresholds(row, prefix, freqs):
    out = {}
    for f in freqs:
        v = _cell(row, f"{prefix}_{f}")
        if v is not None:
            out[f] = v
    return out


def validate_csv(raw: bytes) -> dict:
    """Run the full pipeline over labelled cases and report agreement."""
    df = pd.read_csv(io.BytesIO(raw), dtype=str)

    # Refuse anything that is not actually an audiogram table, rather than
    # silently reporting metrics computed over nothing.
    threshold_cols = [c for c in df.columns
                      if c.startswith(("r_ac_", "l_ac_", "r_bc_", "l_bc_"))]
    if not threshold_cols:
        raise ValueError(
            "no threshold columns found — expected r_ac_250 … l_bc_4000 as in "
            "samples/validation_labelled.csv")
    if df.empty:
        raise ValueError("the file contains no data rows")

    expert_pattern, pred_pattern = [], []
    expert_grade, pred_grade = [], []
    expert_type, pred_type = [], []
    disability_errors: List[float] = []
    rows: List[dict] = []

    for i, row in df.iterrows():
        r_ac = _thresholds(row, "r_ac", AC_FREQS)
        r_bc = _thresholds(row, "r_bc", BC_FREQS)
        l_ac = _thresholds(row, "l_ac", AC_FREQS)
        l_bc = _thresholds(row, "l_bc", BC_FREQS)
        rr = rules.analyze_test(r_ac, r_bc, l_ac, l_bc)

        pattern = None
        try:
            m = classifier.classify_ear(r_ac, r_bc, explain=False)
            pattern = m["pattern"] if m else None
        except FileNotFoundError:
            pattern = None

        ear = rr["right"]
        grade = (ear.get("who_grade") or {}).get("grade")
        ear_type = (ear.get("type") or "").replace(" (provisional)", "") or None
        disability = (rr.get("disability") or {}).get("binaural_pct")

        ep = normalize_pattern(row.get("expert_pattern"))
        eg = normalize_grade(row.get("expert_grade"))
        et = normalize_type(row.get("expert_type"))

        expert_pattern.append(ep); pred_pattern.append(pattern)
        expert_grade.append(eg); pred_grade.append(grade)
        expert_type.append(et); pred_type.append(ear_type)

        ed = row.get("expert_disability")
        if ed is not None and str(ed).strip() != "" and disability is not None:
            try:
                disability_errors.append(abs(float(ed) - disability))
            except ValueError:
                pass

        rows.append({
            "row": int(i) + 1,
            "name": str(row.get("name", f"Row {i+1}")),
            "expert": {"pattern": ep, "grade": eg, "type": et},
            "predicted": {"pattern": pattern, "grade": grade, "type": ear_type},
            "match": {
                "pattern": ep is not None and ep == pattern,
                "grade": eg is not None and eg == grade,
                "type": et is not None and et == ear_type,
            },
        })

    metrics = {
        "pattern": _agreement(expert_pattern, pred_pattern, "Audiogram pattern (ML)"),
        "grade": _agreement(expert_grade, pred_grade, "Degree of loss (rules)"),
        "type": _agreement(expert_type, pred_type, "Type of loss (rules)"),
    }
    if disability_errors:
        metrics["disability"] = {
            "field": "Disability percentage (rules)",
            "n": len(disability_errors),
            "mean_absolute_error_pct": round(
                sum(disability_errors) / len(disability_errors), 2),
            "max_absolute_error_pct": round(max(disability_errors), 2),
            "within_1_pct": round(
                100 * sum(1 for e in disability_errors if e <= 1) / len(disability_errors), 1),
        }

    graded = [m for m in metrics.values() if m and "cohens_kappa" in m]
    return {
        "cases": len(df),
        "metrics": {k: v for k, v in metrics.items() if v},
        "rows": rows,
        "summary": (
            "Validated against " + str(len(df)) + " expert-labelled case(s): "
            + "; ".join(f"{m['field']} {m['agreement']}% agreement "
                        f"(κ={m['cohens_kappa']}, {m['kappa_interpretation']})"
                        for m in graded)
            if graded else
            "No expert labels found. Add expert_pattern, expert_grade, expert_type "
            "or expert_disability columns to measure agreement."
        ),
        "caveat": (
            "The classifier's headline 99.9% figure is hold-out accuracy on synthetic "
            "data and measures only that it learned its own generator. Clinical "
            "accuracy is whatever this harness reports on real, expert-labelled "
            "audiograms — which is the number that should be quoted."
        ),
    }
