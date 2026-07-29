"""MODULE 1.5 — Progression analysis between two dated tests.

Implements OSHA Standard Threshold Shift and ASHA ototoxicity-monitoring
criteria on per-ear air-conduction deltas. Positive delta = hearing got
worse (threshold increased).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, ThresholdValue, ear_to_numeric

#: Frequencies used for the OSHA STS average. OSHA 29 CFR 1910.95(g)(10)
#: defines STS over 2000/3000/4000 Hz; 3000 Hz is not collected in this
#: data model, so 2000/4000 Hz serve as the documented proxy.
OSHA_FREQS = [2000, 4000]


def ear_deltas(
    baseline: Dict[int, Optional[ThresholdValue]],
    current: Dict[int, Optional[ThresholdValue]],
) -> Dict[int, Optional[float]]:
    """Per-frequency threshold shift (current - baseline), dB. NR -> 120."""
    b, c = ear_to_numeric(baseline), ear_to_numeric(current)
    out: Dict[int, Optional[float]] = {}
    for f in AC_FREQS:
        if b.get(f) is not None and c.get(f) is not None:
            out[f] = round(c[f] - b[f], 1)
        else:
            out[f] = None
    return out


def osha_sts(deltas: Dict[int, Optional[float]]) -> dict:
    """OSHA Standard Threshold Shift check.

    OSHA 29 CFR 1910.95(g)(10)(i): an STS is an average shift of 10 dB or
    more at 2000, 3000 and 4000 Hz relative to the baseline audiogram.
    3000 Hz is not part of this data model, so the average is taken over
    2000/4000 Hz (documented proxy). An average shift of exactly 10 dB
    flags positive (criterion is ">= 10").
    """
    shifts = [deltas[f] for f in OSHA_FREQS if deltas.get(f) is not None]
    if not shifts:
        return {"flag": False, "avg_shift": None, "freqs": OSHA_FREQS,
                "note": "insufficient data at 2k/4k Hz"}
    avg = round(sum(shifts) / len(shifts), 2)
    return {
        "flag": avg >= 10.0,
        "avg_shift": avg,
        "freqs": OSHA_FREQS,
        "criterion": "average shift ≥ 10 dB at 2000/4000 Hz (proxy for OSHA 2k/3k/4k)",
    }


def asha_ototoxicity(
    deltas: Dict[int, Optional[float]],
    baseline: Dict[int, Optional[ThresholdValue]] | None = None,
    current: Dict[int, Optional[ThresholdValue]] | None = None,
) -> dict:
    """ASHA (1994) ototoxicity-monitoring significant-change criteria.

    A significant ototoxic change is any of:
      (a) >= 20 dB shift at any single test frequency;
      (b) >= 10 dB shift at two ADJACENT test frequencies;
      (c) loss of response ("NR") at three consecutive frequencies where
          responses were previously obtained.
    """
    triggers: List[str] = []

    for f, d in deltas.items():
        if d is not None and d >= 20:
            triggers.append(f"≥20 dB shift at {f} Hz ({d:+g} dB)")

    ordered = [f for f in AC_FREQS if deltas.get(f) is not None]
    for f1, f2 in zip(ordered, ordered[1:]):
        if AC_FREQS.index(f2) - AC_FREQS.index(f1) == 1:  # truly adjacent
            if deltas[f1] >= 10 and deltas[f2] >= 10:
                triggers.append(
                    f"≥10 dB shift at adjacent frequencies {f1}/{f2} Hz "
                    f"({deltas[f1]:+g}/{deltas[f2]:+g} dB)"
                )

    if baseline is not None and current is not None:
        run = 0
        for f in AC_FREQS:
            had_response = baseline.get(f) is not None and baseline.get(f) != "NR"
            lost = current.get(f) == "NR"
            run = run + 1 if (had_response and lost) else 0
            if run == 3:
                triggers.append("loss of response at three consecutive frequencies")
                break

    return {"flag": bool(triggers), "triggers": triggers,
            "criteria": "ASHA 1994 ototoxicity monitoring"}


def compare_ears(baseline_ac, current_ac) -> dict:
    """Full progression analysis for one ear (AC thresholds)."""
    deltas = ear_deltas(baseline_ac, current_ac)
    return {
        "deltas": deltas,
        "osha_sts": osha_sts(deltas),
        "asha_ototoxicity": asha_ototoxicity(deltas, baseline_ac, current_ac),
        "max_shift": max((d for d in deltas.values() if d is not None), default=None),
    }


def compare_tests(baseline: dict, current: dict) -> dict:
    """Progression for both ears.

    ``baseline``/``current`` are dicts with 'right'/'left' -> {'ac': {...}}.
    """
    return {
        "right": compare_ears(baseline["right"]["ac"], current["right"]["ac"]),
        "left": compare_ears(baseline["left"]["ac"], current["left"]["ac"]),
    }
