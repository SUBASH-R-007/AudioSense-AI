"""Acoustic reflexes, and the battery-level view of the middle ear.

Pure-tone audiometry says *how much* hearing is lost. Immittance says *where
the problem is*, independently of the patient's voluntary response, which is
why it is the standard cross-check on a conductive finding.

Tympanogram typing itself lives in ``tympanometry.py``, which implements the
full eight-type classification from the clinical reference. This module keeps
the reflex analysis and the per-ear bundle used by the analysis pipeline.

Acoustic reflex thresholds normally appear 70-100 dB above the pure-tone
threshold. Their presence or absence, ipsilateral versus contralateral,
localises the lesion along the reflex arc.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.clinical.tympanometry import (
    COMPLIANCE_NORMAL_ADULT as COMPLIANCE_NORMAL,
    ECV_NORMAL_ADULT as ECV_NORMAL,
    PRESSURE_NORMAL,
    classify,
)

#: Acoustic reflex thresholds are normally 70-100 dB SL above threshold.
REFLEX_SL_NORMAL = (70, 100)


def classify_tympanogram(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    age_years: Optional[float] = None,
) -> Optional[dict]:
    """Type a tympanogram from its summary values.

    Delegates to ``tympanometry.classify`` so there is exactly one place that
    decides what a tympanogram is. This used to hold a second, five-type copy
    of the rules, which meant the battery on the dashboard and the instrument
    page could disagree about the same ear.
    """
    return classify(peak_pressure, compliance, ecv, age_years=age_years)


def analyze_reflexes(
    reflexes: Dict[str, Optional[float]],
    pta: Optional[float] = None,
) -> Optional[dict]:
    """Interpret ipsi/contra acoustic reflex thresholds for one ear.

    ``reflexes``: {"ipsi": dB HL or None, "contra": dB HL or None}, where
    None means "absent at maximum output" rather than "not tested" — the
    caller passes an empty dict when the test was not done.
    """
    if not reflexes:
        return None
    ipsi, contra = reflexes.get("ipsi"), reflexes.get("contra")
    present = {"ipsi": ipsi is not None, "contra": contra is not None}

    sensation_level = None
    elevated = False
    if ipsi is not None and pta is not None:
        sensation_level = round(ipsi - pta, 1)
        elevated = sensation_level > REFLEX_SL_NORMAL[1]

    if not present["ipsi"] and not present["contra"]:
        pattern = "absent"
        note = ("Reflexes absent bilaterally in this ear — consistent with a "
                "conductive block, severe cochlear loss, or a retrocochlear/"
                "neural lesion depending on the rest of the battery.")
    elif present["ipsi"] and present["contra"]:
        pattern = "present"
        note = ("Reflexes present — the middle ear transmits sound and the "
                "reflex arc is intact.")
    else:
        pattern = "partial"
        note = ("Reflexes present on one side only — asymmetric findings warrant "
                "a full reflex pattern (ipsi and contra, both ears) to localise "
                "the lesion.")

    return {
        "ipsi": ipsi, "contra": contra, "present": present, "pattern": pattern,
        "sensation_level": sensation_level, "elevated": elevated,
        "note": note,
        "normal_sl_range": REFLEX_SL_NORMAL,
    }


def analyze_immittance(ear, pta: Optional[float] = None) -> Optional[dict]:
    """Full immittance review for one ear (EarData)."""
    tymp = classify_tympanogram(ear.tymp_pressure, ear.tymp_compliance, ear.tymp_ecv)
    reflexes = analyze_reflexes(ear.reflexes or {}, pta)
    if tymp is None and reflexes is None:
        return None
    return {"tympanogram": tymp, "reflexes": reflexes}
