"""MODULE 1 — Deterministic clinical rules engine.

Every function here is pure, unit-tested, and cites the guideline it
implements. "NR" (No Response) thresholds are computed as 120 dB HL
(audiometer maximum) and the result carries an ``nr_used`` caveat — with two
deliberate exceptions, each set by its own standard:

- the RPwD disability percentage, where the Gazette of India fixes a
  no-response air-conduction threshold at 95 dB (``RPWD_NR_DB``);
- the air-bone gap, where a bone-conduction no-response is beyond the bone
  vibrator's output limit and the gap there is indeterminate, so that
  frequency is excluded rather than computed against 120 dB.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from app.models.schemas import (
    NR_DB,
    PTA_FREQS,
    ThresholdValue,
    ear_to_numeric,
)

# ---------------------------------------------------------------------------
# Pure-tone average
# ---------------------------------------------------------------------------


def _raw(thresholds: Dict[int, Optional[ThresholdValue]]) -> Dict[int, Optional[ThresholdValue]]:
    """Thresholds keyed by int frequency, so "NR" lookups never miss on a str key."""
    return {int(f): v for f, v in (thresholds or {}).items()}


def pta(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[dict]:
    """Four-frequency pure-tone average (PTA4).

    PTA = mean of air-conduction thresholds at 500, 1000, 2000 and 4000 Hz,
    per the WHO World Report on Hearing (2021), which grades hearing loss on
    the better-ear 4-frequency average.

    Untested frequencies are excluded from the mean (flagged in
    ``missing_freqs``); "NR" counts as 120 dB HL (flagged in ``nr_freqs``).
    Returns None if none of the four frequencies were tested.
    """
    raw = _raw(ac)
    numeric = ear_to_numeric(raw)
    used, missing, nr_freqs = [], [], []
    for f in PTA_FREQS:
        v = numeric.get(f)
        if v is None:
            missing.append(f)
        else:
            used.append(v)
            if raw.get(f) == "NR":
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
    (80, 95, "Profound hearing loss", "Extreme difficulty even with amplification; may benefit from cochlear implant"),
    # WHO World Report on Hearing (2021), grades table: 95 dB HL or greater
    # is its own grade, "Complete or total hearing loss/deafness" — not the
    # top of "Profound". It is the grade at which a cochlear implant is the
    # route to speech, so it is not folded into the band below.
    (95, float("inf"), "Complete or total hearing loss",
     "Cannot hear speech or most environmental sounds, even shouted; cochlear implant candidacy assessment"),
]

#: Air-conduction PTA from which an ear is no longer within normal limits.
#: Derived from the WHO table above (20 dB HL grades as Mild), so the type
#: rules and the grade can never disagree about the same number.
HEARING_LOSS_FROM_DB: float = WHO_GRADES[0][1]


def who_grade(pta_value: float) -> dict:
    """WHO 2021 (World Report on Hearing) grade for a PTA4 value.

    Grades: Normal <20, Mild 20-<35, Moderate 35-<50, Moderately Severe
    50-<65, Severe 65-<80, Profound 80-<95, Complete or total >=95 dB HL.
    Lower bound is inclusive: a PTA of exactly 20.0 grades as Mild, exactly
    35.0 as Moderate, exactly 95.0 as Complete or total, etc.
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

#: An air-bone gap must EXCEED this to be clinically significant.
ABG_SIGNIFICANT_DB = 10

#: Bone-conduction PTA at or below which the cochlea is taken as within normal
#: limits for typing. BSA Recommended Procedure, Pure-tone audiometry (2018),
#: section 9 describes 21-40 dB HL as mild, i.e. normal runs up to and
#: including 20 dB HL. The WHO grades describe hearing (air conduction) and do
#: not set this edge.
BC_NORMAL_MAX_DB = 20

#: The same BSA (2018) edge for a single air-conduction threshold — the
#: per-frequency normal limit safety.NORMAL_LIMIT_DB applies.
AC_NORMAL_MAX_DB = BC_NORMAL_MAX_DB


def _ac_all_within_normal_limits(ac: Dict[int, Optional[ThresholdValue]]) -> bool:
    """Every tested air-conduction threshold, at any frequency, is a measured
    value within AC_NORMAL_MAX_DB (a no-response never is)."""
    raw = {f: v for f, v in _raw(ac).items() if v is not None}
    return bool(raw) and all(v != "NR" and float(v) <= AC_NORMAL_MAX_DB
                             for v in raw.values())


def _bc_no_response(bc: Dict[int, Optional[ThresholdValue]]) -> List[int]:
    raw = _raw(bc)
    return [f for f in PTA_FREQS if raw.get(f) == "NR"]


def air_bone_gap(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
) -> Optional[dict]:
    """Average air-bone gap (ABG) over 500/1k/2k/4k Hz.

    ABG = AC threshold - BC threshold, averaged across the PTA frequencies
    at which BOTH conductions were tested. An ABG > 10 dB is considered
    clinically significant (standard audiological convention; e.g. ASHA
    guidelines for manual pure-tone audiometry).

    A bone-conduction "No Response" says only that the cochlear threshold lies
    beyond the bone vibrator's output limit, which sits far below the air
    maximum. The gap at that frequency is indeterminate, so it is excluded
    (listed in ``bc_nr_excluded``). Computing it as AC - 120 would produce a
    negative gap that cancels the real gaps beside it and turns a mixed loss
    into a sensorineural one.
    """
    ac_n, bc_n = ear_to_numeric(_raw(ac)), ear_to_numeric(_raw(bc))
    bc_nr = _bc_no_response(bc)
    gaps, freqs, excluded = [], [], []
    for f in PTA_FREQS:
        a, b = ac_n.get(f), bc_n.get(f)
        if a is None or b is None:
            continue
        if f in bc_nr:
            excluded.append(f)
            continue
        gaps.append(a - b)
        freqs.append(f)
    if not gaps:
        return None
    return {"value": round(sum(gaps) / len(gaps), 2), "freqs_used": freqs,
            "bc_nr_excluded": excluded}


def hearing_type(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
) -> dict:
    """Classify conductive / sensorineural / mixed / normal for one ear.

    Standard audiological criteria (ASHA; British Society of Audiology
    recommended procedure):

    - Normal:        AC PTA < 20 dB HL (WHO 2021 normal), with or without a gap
    - Conductive:    AC PTA >= 20, ABG > 10 dB and BC PTA <= 20 (cochlea normal)
    - Mixed:         AC PTA >= 20, ABG > 10 dB and BC PTA > 20
    - Sensorineural: AC PTA >= 20 and ABG <= 10 dB

    An ABG of exactly 10 dB is NOT significant (must exceed 10). An AC PTA of
    exactly 20 dB HL is a loss: WHO grades it Mild, and the type follows the
    grade.

    Hearing within normal limits is typed Normal even when bone conduction is
    better than air by more than 10 dB: a type names a hearing LOSS, and there
    is none. The gap is still a finding — it can be the first sign of a
    middle-ear problem, or a bone-vibrator placement or masking artefact — so
    it is reported in ``air_bone_gap_note`` and ``significant_air_bone_gap``
    rather than dropped.

    Missing-BC handling (QUALITY BAR requirement): if BC was not tested at
    any PTA frequency, the ABG is unknowable, so the ear is classified from
    AC alone and flagged ``provisional`` with the message
    "type provisional — BC not tested". Partially tested BC also flags
    provisional, as does a BC "No Response" that leaves the gap indeterminate
    at a PTA frequency. The exception is an ear whose every tested air
    threshold is within normal limits: it is Normal whatever bone conduction
    shows, so it is not provisional, and a caveat says a gap behind normal
    hearing is not excluded.
    """
    ac_pta = pta(ac)
    abg = air_bone_gap(ac, bc)
    bc_pta = pta(bc)
    bc_nr = _bc_no_response(bc)

    caveats: List[str] = []
    provisional = False
    significant_gap = False
    gap_note: Optional[str] = None

    if ac_pta is None:
        return {
            "type": "Indeterminate",
            "provisional": True,
            "caveats": ["no AC thresholds at PTA frequencies"],
            "ac_pta": None,
            "bc_pta": None,
            "abg": None,
            "significant_air_bone_gap": False,
            "air_bone_gap_note": None,
            "bc_nr_freqs": bc_nr,
        }

    ac_loss = ac_pta["value"] >= HEARING_LOSS_FROM_DB

    if abg is None and not bc_nr and not ac_loss and _ac_all_within_normal_limits(ac):
        # Bone conduction not tested, the average graded normal (a PTA of
        # exactly 20 dB HL is Mild, a loss, even with every threshold at the
        # 20 dB HL limit) and every air threshold within normal limits. The
        # type is Normal whatever bone conduction would show — an
        # ear graded normal is typed Normal with or without a gap (above), and
        # a bone threshold cannot reveal a cochlear loss air conduction does
        # not — so it is not provisional. Holding it provisional would route
        # every normal-hearing ear of an air-only screening camp to review.
        # The one thing not excluded, a gap behind normal hearing, is said.
        t = "Normal"
        caveats.append(
            "BC not tested — not needed to type this ear: every air-conduction "
            f"threshold is within normal limits (≤ {AC_NORMAL_MAX_DB:g} dB HL); an "
            "air-bone gap behind normal hearing is not excluded")
    elif abg is None:
        # No determinate AC/BC pair at all -> AC-only provisional classification.
        provisional = True
        if bc_nr:
            caveats.append(
                f"type provisional — air-bone gap indeterminate: BC 'No Response' "
                f"at {bc_nr} Hz is beyond the bone vibrator's output limit, so a "
                "conductive component cannot be excluded")
        else:
            caveats.append("type provisional — BC not tested")
        t = "Sensorineural (provisional)" if ac_loss else "Normal"
    else:
        bc_raw = _raw(bc)
        bc_tested = [f for f in PTA_FREQS if bc_raw.get(f) is not None]
        if len(abg["freqs_used"]) < len(PTA_FREQS):
            provisional = True
            if len(bc_tested) < len(PTA_FREQS):
                caveats.append(
                    "type provisional — BC incomplete (tested at "
                    f"{len(bc_tested)}/{len(PTA_FREQS)} PTA frequencies)"
                )
            if bc_nr:
                caveats.append(
                    f"type provisional — BC 'No Response' at {bc_nr} Hz is beyond "
                    "the bone vibrator's output limit; the air-bone gap there is "
                    "indeterminate and excluded from the average, never counted "
                    "as a negative gap")
            if len(bc_tested) == len(PTA_FREQS) and not bc_nr:
                caveats.append(
                    "type provisional — air-bone gap determined at "
                    f"{len(abg['freqs_used'])}/{len(PTA_FREQS)} PTA frequencies")
        significant_gap = abg["value"] > ABG_SIGNIFICANT_DB
        bc_val = bc_pta["value"] if bc_pta else None
        if not ac_loss:
            t = "Normal"
            if significant_gap:
                gap_note = (
                    f"Hearing within normal limits (AC PTA {ac_pta['value']:g} dB HL) "
                    f"with a {abg['value']:g} dB air-bone gap. Typed Normal because "
                    "there is no loss to type; the gap is a finding — check "
                    "bone-vibrator placement and masking, and consider "
                    "tympanometry and otoscopy for a middle-ear cause.")
        elif significant_gap and bc_val is not None and bc_val <= BC_NORMAL_MAX_DB:
            t = "Conductive"
        elif significant_gap and bc_val is not None:
            t = "Mixed"
        else:
            t = "Sensorineural"

    if ac_pta["missing_freqs"]:
        caveats.append(
            f"AC PTA averaged over {len(ac_pta['freqs_used'])}/{len(PTA_FREQS)} "
            f"frequencies — {ac_pta['missing_freqs']} Hz untested; the WHO grade "
            "and the RPwD percentage are defined on all four")
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
        "significant_air_bone_gap": significant_gap,
        "air_bone_gap_note": gap_note,
        "bc_nr_freqs": bc_nr,
    }


# ---------------------------------------------------------------------------
# India RPwD Act 2016 disability percentage
# ---------------------------------------------------------------------------

#: Source of every number in this section: Gazette of India, Extraordinary,
#: Part II Sec. 3(ii), S.O. 76(E), 4 January 2018 — Guidelines for assessing
#: the extent of specified disability under the RPwD Act 2016, Annexure II,
#: III-A (Hearing impairment), paras 20.2.2 and 20.2.3.
#: S.O. 1338(E), 12 March 2024, supersedes those guidelines. Secondary sources
#: built from it reproduce this same method (95 dB for no response, this ready
#: reckoner, the 5:1 binaural weighting), but its primary text could not be
#: retrieved to confirm it: the DEPwD notification page links it as
#: https://divyangjan.depwd.gov.in/upload/uploadfiles/assessment_guidelines.pdf,
#: which did not serve the document. Re-verify against S.O. 1338(E) before
#: relying on these figures for certification.
RPWD_SOURCE = "Gazette of India S.O. 76(E), 4 Jan 2018, paras 20.2.2–20.2.3"

#: The caveat above, in the words every disability payload carries
#: (``guideline_note``) and the certifiable note repeats. The figure reaches a
#: government certificate, so the supersession is stated wherever it is shown,
#: not only here.
RPWD_GUIDELINE_NOTE = (
    "S.O. 76(E) (2018) has been superseded by S.O. 1338(E) of 12 March 2024. "
    "Published summaries of the 2024 guidelines describe this same method (no "
    "response counted as 95 dB, the same ready reckoner, the 5:1 binaural "
    "weighting), but it has not been checked against the 2024 Gazette text "
    "itself — confirm it against the guidelines in force before certifying.")

#: Para 20.2.2(a)(i): "whenever there is no response at any frequency ACT is
#: to be considered as 95dB". This substitution belongs to the disability
#: computation ONLY; the PTA, grade and type keep NR at the audiometer
#: maximum (``NR_DB``).
#:
#: The paragraph substitutes 95 dB for a no-response only. It does not cap a
#: MEASURED threshold, so a measured 100 or 110 dB HL enters the mean at its
#: measured value. Read literally, as here, an ear with no response can
#: compute LOWER than an ear with measured thresholds above 95 dB, although
#: its hearing is no better: {90, 90, NR, NR} is (90 + 90 + 95 + 95) / 4 =
#: 92.5 -> 93 dB -> 96.43%, while {90, 90, 100, 100} is 95 dB -> 100%. The
#: certificate figure is the Gazette's, so neither value is adjusted here; the
#: formula string prints "95 [NR]" against each substituted frequency so the
#: certifying authority can see where it applied.
RPWD_NR_DB = 95

#: Para 20.2.2(a)(ii), the monaural ready reckoner, transcribed entry by entry
#: (monaural PTA in whole dB -> % of hearing disability). The Gazette prints
#: 0 to 25 dB as one row (0%) and ends at 95 dB = 100%. The jump from 27% at
#: 59 dB to 40% at 60 dB is in the Gazette; it is what places the 40%
#: benchmark exactly at a 60 dB better ear. Values are strings so the
#: arithmetic is exact decimal, as printed.
RPWD_READY_RECKONER: Dict[int, str] = {
    26: "1", 27: "1", 28: "1", 29: "1", 30: "1", 31: "1", 32: "1", 33: "1",
    34: "2", 35: "3", 36: "4", 37: "5", 38: "6", 39: "7", 40: "8", 41: "9",
    42: "10", 43: "11", 44: "12", 45: "13", 46: "14", 47: "15", 48: "16",
    49: "17", 50: "18", 51: "19", 52: "20", 53: "21", 54: "22", 55: "23",
    56: "24", 57: "25", 58: "26", 59: "27", 60: "40",
    61: "41.71", 62: "43.42", 63: "45.13", 64: "46.84", 65: "48.55",
    66: "50.26", 67: "51.97", 68: "53.68", 69: "55.39", 70: "57.1",
    71: "58.81", 72: "60.52", 73: "62.23", 74: "63.94", 75: "65.65",
    76: "67.36", 77: "69.07", 78: "70.78", 79: "72.49", 80: "74.2",
    81: "75.91", 82: "77.62", 83: "79.33", 84: "81.04", 85: "82.75",
    86: "84.46", 87: "86.17", 88: "87.88", 89: "89.59", 90: "91.3",
    91: "93.01", 92: "94.72", 93: "96.43", 94: "98.14", 95: "100",
}
#: Highest PTA the Gazette prints as 0%.
RPWD_ZERO_UPTO_DB = 25
#: The ready reckoner's last row. A PTA above it can only come from measured
#: thresholds above 95 dB HL (see ``RPWD_NR_DB``), and is held at that row's
#: 100%: the Gazette prints no row beyond it and no percentage exceeds 100.
RPWD_FULL_FROM_DB = 95

#: The ready reckoner is indexed by whole dB, but a four-frequency mean moves
#: in 0.25 dB steps and the Gazette does not say how to enter the table with
#: a fraction. This module rounds to the nearest whole dB, halves upward
#: (52.5 -> 53): ordinary arithmetic rounding, never lower than truncation.
#: The rounded value is printed in every formula, so an authority applying a
#: different convention can see exactly where its figure would differ.
RPWD_ROUNDING_RULE = ("PTA rounded to the nearest whole dB (halves rounded up) "
                      "before entering the ready reckoner")

RPWD_BENCHMARK_PCT = Decimal(40)


def _half_up(value: Decimal, places: str = "1") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _num(value: Decimal) -> str:
    return f"{float(value):g}"


def rpwd_monaural_pct(pta_value: float) -> Tuple[int, Decimal]:
    """(whole-dB PTA used, monaural %) from the para 20.2.2(a)(ii) ready reckoner."""
    whole = int(_half_up(Decimal(str(pta_value))))
    if whole <= RPWD_ZERO_UPTO_DB:
        return whole, Decimal(0)
    if whole >= RPWD_FULL_FROM_DB:
        return whole, Decimal(100)
    return whole, Decimal(RPWD_READY_RECKONER[whole])


def _reckoner_step(mean: Decimal, whole: int, pct: Decimal) -> str:
    step = ""
    if mean != whole:
        step += f" → {whole} dB (nearest whole dB, halves up)"
    if whole <= RPWD_ZERO_UPTO_DB:
        step += f" → ready reckoner 0–{RPWD_ZERO_UPTO_DB} dB = 0%"
    elif whole >= RPWD_FULL_FROM_DB:
        step += f" → ready reckoner ≥ {RPWD_FULL_FROM_DB} dB = 100%"
    else:
        step += f" → ready reckoner {whole} dB = {_num(pct)}%"
    return step


def rpwd_pta(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[dict]:
    """The Gazette PTA for one ear: mean ACT at 500/1000/2000/4000 Hz, NR = 95 dB.

    Para 20.2.2(a)(i) requires all four frequencies; an untested one is listed
    in ``missing_freqs`` and the mean is taken over the rest, so the figure is
    an estimate that cannot be certified. Returns None when none of the four
    were tested. ``value`` is an exact Decimal, so the ready-reckoner lookup
    and its rounding never see binary floating-point error.
    """
    raw = _raw(ac)
    terms: List[str] = []
    values: List[Decimal] = []
    used, missing, nr = [], [], []
    for f in PTA_FREQS:
        v = raw.get(f)
        if v is None:
            missing.append(f)
            continue
        used.append(f)
        if v == "NR":
            nr.append(f)
            values.append(Decimal(RPWD_NR_DB))
            terms.append(f"{RPWD_NR_DB} [NR]")
        else:
            values.append(Decimal(str(v)))
            terms.append(f"{float(v):g}")
    if not values:
        return None
    mean = sum(values) / len(values)
    return {"value": mean, "freqs_used": used, "missing_freqs": missing,
            "nr_freqs": nr, "terms": terms}


def _monaural_from_gazette_pta(p: dict) -> dict:
    mean: Decimal = p["value"]
    whole, pct = rpwd_monaural_pct(mean)
    freqs = "/".join(str(f) for f in p["freqs_used"])
    formula = (f"PTA ({freqs} Hz) = ({' + '.join(p['terms'])}) / "
               f"{len(p['freqs_used'])} = {_num(mean)} dB")
    if p["missing_freqs"]:
        formula += (f" [{', '.join(str(f) for f in p['missing_freqs'])} Hz untested "
                    "— the Gazette requires all four; not certifiable]")
    formula += _reckoner_step(mean, whole, pct)
    return {
        "pta": round(float(mean), 2),
        "pta_rounded": whole,
        "pct": float(pct),
        "freqs_used": p["freqs_used"],
        "missing_freqs": p["missing_freqs"],
        "nr_freqs": p["nr_freqs"],
        "formula": formula,
        "_pct": pct,
    }


def _monaural_from_value(p: float) -> dict:
    mean = Decimal(str(p))
    whole, pct = rpwd_monaural_pct(p)
    return {
        "pta": round(p, 2),
        "pta_rounded": whole,
        "pct": float(pct),
        "formula": f"PTA {_num(mean)} dB" + _reckoner_step(mean, whole, pct),
        "_pct": pct,
    }


def _binaural(right: dict, left: dict, certifiable: bool,
              certification_note: str) -> dict:
    # Para 20.2.3: (better-ear % x 5 + poorer-ear %) / 6. "Better" is the ear
    # with the lower disability %; equal percentages fall back to the lower
    # PTA, then to the right ear, only to name the ears.
    r_key = (right["_pct"], right["pta"])
    l_key = (left["_pct"], left["pta"])
    better_ear = "right" if r_key <= l_key else "left"
    worse_ear = "left" if better_ear == "right" else "right"
    better = right if better_ear == "right" else left
    worse = left if better_ear == "right" else right
    exact = (5 * better["_pct"] + worse["_pct"]) / 6
    shown = _half_up(exact, "0.01")
    for ear in (right, left):
        ear.pop("_pct", None)

    return {
        "right": right,
        "left": left,
        "better_ear": better_ear,
        "worse_ear": worse_ear,
        "binaural_pct": float(shown),
        "binaural_formula": (
            f"(5 × {better['pct']:g} [better: {better_ear}] + "
            f"{worse['pct']:g} [poorer: {worse_ear}]) / 6 = {float(shown):g}%"
        ),
        # Compared on the exact value, never the rounded display. On this
        # ready reckoner the benchmark is met exactly when the better ear's
        # whole-dB PTA is 60 dB or more.
        "benchmark_disability": exact >= RPWD_BENCHMARK_PCT,
        "benchmark_note": ("Benchmark disability under RPwD Act 2016 = ≥ 40% "
                           "(reached when the better ear's PTA is 60 dB or more)"),
        "certifiable": certifiable,
        "certification_note": certification_note,
        "guideline_note": RPWD_GUIDELINE_NOTE,
        "method": RPWD_SOURCE,
        "rounding_rule": RPWD_ROUNDING_RULE,
        "nr_value_db": RPWD_NR_DB,
    }


def rpwd_disability_from_thresholds(
    right_ac: Dict[int, Optional[ThresholdValue]],
    left_ac: Dict[int, Optional[ThresholdValue]],
) -> Optional[dict]:
    """Hearing disability percentage under India's RPwD Act 2016, from thresholds.

    Gazette of India S.O. 76(E), 4 Jan 2018, Annexure II, III-A:

    - 20.2.2(a)(i)  PTA of ACT at 500, 1000, 2000 and 4000 Hz per ear; a
      no-response is taken as 95 dB.
    - 20.2.2(a)(ii) Monaural % from the ready reckoner (``RPWD_READY_RECKONER``),
      entered at the PTA rounded per ``RPWD_ROUNDING_RULE``.
    - 20.2.3        Binaural % = (5 x better-ear % + poorer-ear %) / 6.
    - "Benchmark disability" under the Act = 40% or more.

    ``certifiable`` is False whenever any of the four frequencies is untested
    in either ear: the percentage is then a provisional estimate from the
    tested frequencies, and ``certification_note`` says which are missing.
    Returns None when either ear has none of the four frequencies.

    Every intermediate step is returned for transparent UI display.
    """
    r, l = rpwd_pta(right_ac), rpwd_pta(left_ac)
    if r is None or l is None:
        return None
    gaps = {side: p["missing_freqs"] for side, p in (("right", r), ("left", l))
            if p["missing_freqs"]}
    if gaps:
        where = "; ".join(f"{side}: {', '.join(str(f) for f in freqs)} Hz"
                          for side, freqs in gaps.items())
        note = ("Not certifiable: the Gazette (S.O. 76(E) 2018, para 20.2.2) "
                "computes the PTA from all four of 500, 1000, 2000 and 4000 Hz, "
                f"and these were not tested — {where}. This percentage is a "
                "provisional estimate from the tested frequencies only; test the "
                "missing frequencies before any certification.")
    else:
        note = ("All four frequencies (500, 1000, 2000, 4000 Hz) tested in both "
                f"ears; computed per {RPWD_SOURCE}. {RPWD_GUIDELINE_NOTE} "
                "Certification remains the decision of the notified medical "
                "authority.")
    return _binaural(_monaural_from_gazette_pta(r), _monaural_from_gazette_pta(l),
                     certifiable=not gaps, certification_note=note)


def rpwd_disability(pta_right: Optional[float], pta_left: Optional[float]) -> Optional[dict]:
    """RPwD disability percentage from two PTA VALUES alone.

    Same ready reckoner and binaural weighting as
    ``rpwd_disability_from_thresholds``, for callers that hold only a PTA
    (e.g. a projected one). A bare PTA cannot show whether all four
    frequencies were tested or how a no-response was counted (para 20.2.2
    fixes it at 95 dB; the rest of this module uses 120), so the result is
    never ``certifiable``. Anything with per-frequency thresholds must use
    ``rpwd_disability_from_thresholds``.
    """
    if pta_right is None or pta_left is None:
        return None
    return _binaural(
        _monaural_from_value(pta_right), _monaural_from_value(pta_left),
        certifiable=False,
        certification_note=(
            "Estimate from PTA values alone: four-frequency completeness and the "
            "95 dB no-response rule of S.O. 76(E) para 20.2.2 cannot be verified, "
            "so this figure is not certifiable."),
    )


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
    return {
        "right": right,
        "left": left,
        "disability": rpwd_disability_from_thresholds(right_ac, left_ac),
    }
