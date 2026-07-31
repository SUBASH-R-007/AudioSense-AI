"""MODULE 1 — Deterministic clinical rules engine.

Every function here is pure, unit-tested, and cites the guideline it
implements. "NR" (No Response) thresholds are computed as 120 dB HL
(audiometer maximum) and the result carries an ``nr_used`` caveat.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import (
    NR_DB,
    PTA_FREQS,
    ThresholdValue,
    ear_to_numeric,
)

# ---------------------------------------------------------------------------
# Pure-tone average
# ---------------------------------------------------------------------------


def pta(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[dict]:
    """Four-frequency pure-tone average (PTA4).

    PTA = mean of air-conduction thresholds at 500, 1000, 2000 and 4000 Hz,
    per the WHO World Report on Hearing (2021), which grades hearing loss on
    the better-ear 4-frequency average.

    Untested frequencies are excluded from the mean (flagged in
    ``missing_freqs``); "NR" counts as 120 dB HL (flagged in ``nr_freqs``).
    Returns None if none of the four frequencies were tested.
    """
    numeric = ear_to_numeric(ac)
    used, missing, nr_freqs = [], [], []
    for f in PTA_FREQS:
        v = numeric.get(f)
        if v is None:
            missing.append(f)
        else:
            used.append(v)
            if ac.get(f) == "NR":
                nr_freqs.append(f)
    if not used:
        return None
    return {
        "value": round(sum(used) / len(used), 2),
        "freqs_used": [f for f in PTA_FREQS if f not in missing],
        "missing_freqs": missing,
        "nr_freqs": nr_freqs,
    }


# ---------------------------------------------------------------------------
# WHO 2021 degree of hearing loss
# ---------------------------------------------------------------------------

WHO_GRADES = [
    # (lower bound inclusive, upper bound exclusive, grade, functional note)
    (-float("inf"), 20, "Normal hearing", "No problem hearing sounds"),
    (20, 35, "Mild hearing loss", "May have trouble with soft speech or speech in noise"),
    (35, 50, "Moderate hearing loss", "Difficulty hearing conversational speech"),
    (50, 65, "Moderately severe hearing loss", "Difficulty with raised speech; hearing aids usually needed"),
    (65, 80, "Severe hearing loss", "Hears only shouted speech; hearing aids essential"),
    (80, float("inf"), "Profound hearing loss", "Extreme difficulty even with amplification; may benefit from cochlear implant"),
]


def who_grade(pta_value: float) -> dict:
    """WHO 2021 (World Report on Hearing) grade for a PTA4 value.

    Grades: Normal <20, Mild 20-<35, Moderate 35-<50, Moderately Severe
    50-<65, Severe 65-<80, Profound >=80 dB HL. Lower bound is inclusive:
    a PTA of exactly 20.0 grades as Mild, exactly 35.0 as Moderate, etc.
    """
    for lo, hi, grade, note in WHO_GRADES:
        if lo <= pta_value < hi:
            return {
                "grade": grade,
                "range": _range_label(lo, hi),
                "functional_note": note,
                "pta": round(pta_value, 2),
            }
    raise ValueError(f"unreachable PTA {pta_value}")  # pragma: no cover


def _range_label(lo: float, hi: float) -> str:
    if lo == -float("inf"):
        return f"< {hi:g} dB HL"
    if hi == float("inf"):
        return f"≥ {lo:g} dB HL"
    return f"{lo:g} – < {hi:g} dB HL"


# ---------------------------------------------------------------------------
# Type of hearing loss via air-bone gap
# ---------------------------------------------------------------------------


def air_bone_gap(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
) -> Optional[dict]:
    """Average air-bone gap (ABG) over 500/1k/2k/4k Hz.

    ABG = AC threshold - BC threshold, averaged across the PTA frequencies
    at which BOTH conductions were tested. An ABG > 10 dB is considered
    clinically significant (standard audiological convention; e.g. ASHA
    guidelines for manual pure-tone audiometry).
    """
    ac_n, bc_n = ear_to_numeric(ac), ear_to_numeric(bc)
    gaps, freqs = [], []
    for f in PTA_FREQS:
        a, b = ac_n.get(f), bc_n.get(f)
        if a is not None and b is not None:
            gaps.append(a - b)
            freqs.append(f)
    if not gaps:
        return None
    return {"value": round(sum(gaps) / len(gaps), 2), "freqs_used": freqs}


def hearing_type(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
) -> dict:
    """Classify conductive / sensorineural / mixed / normal for one ear.

    Standard audiological criteria (ASHA; British Society of Audiology
    recommended procedure):

    - Conductive:    ABG > 10 dB and BC PTA <= 20 dB HL (cochlea normal)
    - Sensorineural: ABG <= 10 dB and AC PTA > 20 dB HL
    - Mixed:         ABG > 10 dB and BC PTA > 20 dB HL
    - Normal:        otherwise (AC PTA <= 20 with no significant gap)

    An ABG of exactly 10 dB is NOT significant (must exceed 10).

    Missing-BC handling (QUALITY BAR requirement): if BC was not tested at
    any PTA frequency, the ABG is unknowable, so the ear is classified from
    AC alone and flagged ``provisional`` with the message
    "type provisional — BC not tested". Partially tested BC also flags
    provisional.
    """
    ac_pta = pta(ac)
    abg = air_bone_gap(ac, bc)
    bc_pta = pta(bc)

    caveats: List[str] = []
    provisional = False

    if ac_pta is None:
        return {
            "type": "Indeterminate",
            "provisional": True,
            "caveats": ["no AC thresholds at PTA frequencies"],
            "ac_pta": None,
            "bc_pta": None,
            "abg": None,
        }

    if abg is None:
        # No overlapping AC/BC at all -> AC-only provisional classification.
        provisional = True
        caveats.append("type provisional — BC not tested")
        t = "Sensorineural (provisional)" if ac_pta["value"] > 20 else "Normal"
    else:
        if len(abg["freqs_used"]) < len(PTA_FREQS):
            provisional = True
            caveats.append(
                "type provisional — BC incomplete (tested at "
                f"{len(abg['freqs_used'])}/{len(PTA_FREQS)} PTA frequencies)"
            )
        significant_gap = abg["value"] > 10
        bc_val = bc_pta["value"] if bc_pta else None
        if significant_gap and bc_val is not None and bc_val <= 20:
            t = "Conductive"
        elif significant_gap and bc_val is not None and bc_val > 20:
            t = "Mixed"
        elif not significant_gap and ac_pta["value"] > 20:
            t = "Sensorineural"
        else:
            t = "Normal"

    if ac_pta["nr_freqs"]:
        caveats.append(
            f"AC 'No Response' at {ac_pta['nr_freqs']} computed as {NR_DB} dB HL"
        )

    return {
        "type": t,
        "provisional": provisional,
        "caveats": caveats,
        "ac_pta": ac_pta,
        "bc_pta": bc_pta,
        "abg": abg,
    }


# ---------------------------------------------------------------------------
# India RPwD Act 2016 disability percentage
# ---------------------------------------------------------------------------


def rpwd_disability(pta_right: Optional[float], pta_left: Optional[float]) -> Optional[dict]:
    """Hearing disability percentage under India's RPwD Act 2016.

    Per the Gazette of India notification (4 Jan 2018) guidelines for
    assessment of hearing disability:

    - Monaural %  = 1.5 x (PTA - 25), clamped to [0, 100]
    - Binaural %  = (5 x better-ear % + 1 x worse-ear %) / 6
    - "Benchmark disability" under the Act = 40% or more.

    Every intermediate step is returned for transparent UI display.
    """
    if pta_right is None or pta_left is None:
        return None

    def monaural(p: float) -> dict:
        raw = 1.5 * (p - 25)
        clamped = min(100.0, max(0.0, raw))
        return {
            "pta": round(p, 2),
            "raw": round(raw, 2),
            "pct": round(clamped, 2),
            "formula": f"1.5 × ({p:g} − 25) = {raw:g} → clamp [0,100] = {clamped:g}%",
        }

    right = monaural(pta_right)
    left = monaural(pta_left)
    better_ear = "right" if pta_right <= pta_left else "left"
    worse_ear = "left" if better_ear == "right" else "right"
    better = right if better_ear == "right" else left
    worse = left if better_ear == "right" else right
    binaural = (5 * better["pct"] + worse["pct"]) / 6

    return {
        "right": right,
        "left": left,
        "better_ear": better_ear,
        "worse_ear": worse_ear,
        "binaural_pct": round(binaural, 2),
        "binaural_formula": (
            f"(5 × {better['pct']:g} [better: {better_ear}] + "
            f"{worse['pct']:g} [worse: {worse_ear}]) / 6 = {round(binaural, 2):g}%"
        ),
        "benchmark_disability": binaural >= 40.0,
        "benchmark_note": "Benchmark disability under RPwD Act 2016 = ≥ 40%",
    }


# ---------------------------------------------------------------------------
# Full single-test analysis
# ---------------------------------------------------------------------------


def analyze_ear(ac, bc) -> dict:
    """Complete rules-engine analysis for one ear."""
    t = hearing_type(ac, bc)
    grade = who_grade(t["ac_pta"]["value"]) if t["ac_pta"] else None
    return {**t, "who_grade": grade}


def analyze_test(right_ac, right_bc, left_ac, left_bc) -> dict:
    """Complete rules-engine analysis for a full test (both ears)."""
    right = analyze_ear(right_ac, right_bc)
    left = analyze_ear(left_ac, left_bc)
    r_pta = right["ac_pta"]["value"] if right["ac_pta"] else None
    l_pta = left["ac_pta"]["value"] if left["ac_pta"] else None
    return {
        "right": right,
        "left": left,
        "disability": rpwd_disability(r_pta, l_pta),
    }
