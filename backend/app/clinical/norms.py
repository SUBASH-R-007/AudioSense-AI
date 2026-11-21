"""Age- and sex-matched hearing norms (ISO 7029:2000).

"PTA 30 dB HL" means nothing to a patient and little to a non-specialist.
"Your ears are performing like a typical 61-year-old's" lands immediately,
and it is the same fact.

EDITION. This module follows ISO 7029:2000 (second edition), which models
the median age-related threshold shift in an otologically normal population
as a quadratic in age:

    H_median(age, freq, sex) = a(freq, sex) x (age - 18)^2      18 <= age <= 70

with the reference at 18 years. The 2000 edition covers ages 18 to 70 at
every frequency. ISO 7029:2017 (third edition) replaced it with new data and
modified formulae, extending the range to 80 years at 2000 Hz and below
only; those formulae are not implemented here. Outside 18-70 this module
therefore EXTRAPOLATES the 2000 curve: ages 71-80 follow the same quadratic,
ages above 80 are clamped to the 80-year value, and ages below 18 are compared
with the 18-year reference. Every such comparison — and every hearing age
above 70 — is flagged as extrapolated in the payload.

SEX. The standard is sex-specific. When sex is not recorded as male or
female, the mean of the male and female coefficients is used and the payload
says so, rather than silently assuming either.

Two things fall out of the median curve:

  PERCENTILE   where this person sits among peers of the same age and sex
  HEARING AGE  the age at which the median person would have this threshold

Hearing age is the honest headline: it depends only on the median curve,
which is the well-established part of the standard.

LIMITS OF THE PERCENTILE FIGURE
ISO 7029 describes an asymmetric distribution around the median with a
spread that widens as thresholds worsen. This module approximates that
spread with a normal distribution whose standard deviation grows with the
median shift (documented below). Percentiles are therefore indicative, not
a substitute for the tabulated statistics, and the payload says so. The
median curve, hearing age, and the direction of every comparison are not
affected by that approximation.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, ThresholdValue, ear_to_numeric

#: ISO 7029:2000 median coefficients a(freq, sex), applied to (age - 18)^2.
#: Hearing deteriorates faster with age at high frequencies, and faster in
#: men than women — both visible directly in these numbers.
A_MALE = {250: 0.0030, 500: 0.0035, 1000: 0.0040,
          2000: 0.0070, 4000: 0.0160, 8000: 0.0220}
A_FEMALE = {250: 0.0030, 500: 0.0035, 1000: 0.0040,
            2000: 0.0060, 4000: 0.0090, 8000: 0.0150}
#: Sex not recorded: the mean of the two curves, never a silent default to
#: either. At 4 kHz the sexes differ by 7 dB at age 60, so a guess matters.
A_UNSPECIFIED = {f: round((A_MALE[f] + A_FEMALE[f]) / 2, 5) for f in A_MALE}

STANDARD = "ISO 7029:2000"
REFERENCE_AGE = 18
#: Upper age of ISO 7029:2000 at every frequency.
STANDARD_MAX_AGE = 70
#: Ages above the standard follow the same quadratic up to here, then clamp.
MAX_MODELLED_AGE = 80

#: Approximation of the ISO 7029 spread, widening as the median shift grows.
#:
#: The floor deliberately exceeds the standard's own spread at the reference
#: age for two reasons. Pure-tone audiometry has a test-retest variability
#: of about ±5 dB before any biological variation is considered, and ISO 7029
#: describes *otologically screened* populations — people with no noise
#: history, no ear disease and no ototoxic exposure. Comparing an unscreened
#: clinic patient against that reference with a tight spread produces alarming
#: percentiles for thresholds that are clinically normal. A 9 dB floor keeps
#: the comparison informative without overstating it.
SD_FLOOR_DB = 9.0
SD_GROWTH = 0.20

#: Upper edge of clinically normal thresholds: WHO (2021) World Report on
#: Hearing grades 20 dB HL as the start of mild loss, so a threshold is
#: within normal limits only BELOW 20 dB HL. The same edge decides hearing-aid
#: candidacy (prescription.NORMAL_LIMIT_DB) and the rules engine's normal
#: grade, so one payload never calls 20 dB HL both normal and a loss.
NORMAL_BELOW_DB = 20.0


def sex_basis(sex: Optional[str]) -> str:
    """Which ISO 7029 curve applies: "male", "female" or "unspecified"."""
    s = str(sex or "").strip().lower()
    if s in ("f", "female", "woman", "girl") or s.startswith("fem"):
        return "female"
    if s in ("m", "male", "man", "boy") or s.startswith("mal"):
        return "male"
    return "unspecified"


def _coefficients(sex: Optional[str]) -> Dict[int, float]:
    return {"female": A_FEMALE, "male": A_MALE}.get(sex_basis(sex), A_UNSPECIFIED)


def age_within_standard(age: float) -> bool:
    """Whether ISO 7029:2000 covers this age directly (18-70 years)."""
    return REFERENCE_AGE <= float(age) <= STANDARD_MAX_AGE


def median_threshold(age: float, freq: int, sex: str = "unspecified") -> Optional[float]:
    """Expected threshold for an otologically normal person of this age.

    Ages 71-80 extrapolate the ISO 7029:2000 quadratic beyond its 70-year
    limit, ages above 80 clamp to the 80-year value and ages below 18 take
    the 18-year reference; callers flag those with ``age_within_standard``.
    """
    a = _coefficients(sex).get(freq)
    if a is None:
        return None
    effective_age = max(REFERENCE_AGE, min(float(age), MAX_MODELLED_AGE))
    return round(a * (effective_age - REFERENCE_AGE) ** 2, 1)


def _sd(median: float) -> float:
    return SD_FLOOR_DB + SD_GROWTH * max(0.0, median)


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def percentile(threshold: float, age: float, freq: int,
               sex: str = "unspecified") -> Optional[dict]:
    """Where this threshold sits among age- and sex-matched peers.

    Reported as "better than N% of peers": hearing better than the median
    gives a percentile above 50. Because lower dB HL is better hearing, the
    comparison is deliberately inverted here rather than at the call site.
    """
    median = median_threshold(age, freq, sex)
    if median is None:
        return None
    sd = _sd(median)
    z = (threshold - median) / sd
    worse_than_peers = _normal_cdf(z)  # proportion of peers who hear better
    better_than_pct = round(100 * (1 - worse_than_peers), 1)
    return {
        "freq": freq,
        "threshold": threshold,
        "expected_for_age": median,
        "difference": round(threshold - median, 1),
        "better_than_pct": better_than_pct,
        "worse_than_pct": round(100 - better_than_pct, 1),
        "within_normal_variation": abs(threshold - median) <= sd,
        "age_extrapolated": not age_within_standard(age),
    }


def hearing_age(threshold: float, freq: int, sex: str = "unspecified") -> Optional[float]:
    """The age whose median threshold equals this one — invert the curve.

    Returns None below the reference age (a threshold better than the
    18-year-old median simply means "at least as good as a young adult").
    """
    a = _coefficients(sex).get(freq)
    if a is None or threshold <= 0:
        return None
    years = math.sqrt(max(0.0, threshold) / a)
    return round(REFERENCE_AGE + years, 1)


def _extrapolation_note(age: float, overall_age: Optional[float]) -> Optional[str]:
    """Plain statement of where the comparison leaves ISO 7029:2000's range."""
    a = float(age)
    if a > MAX_MODELLED_AGE:
        return (f"{STANDARD} covers ages {REFERENCE_AGE}-{STANDARD_MAX_AGE}; at age "
                f"{a:.0f} the expected thresholds are extrapolated and held at the "
                f"{MAX_MODELLED_AGE}-year value, so treat the comparison as "
                "approximate.")
    if a > STANDARD_MAX_AGE:
        return (f"{STANDARD} covers ages {REFERENCE_AGE}-{STANDARD_MAX_AGE}; at age "
                f"{a:.0f} the expected thresholds are extrapolated along its curve, "
                "so treat the comparison as approximate.")
    if a < REFERENCE_AGE:
        return (f"{STANDARD} starts at {REFERENCE_AGE} years; this ear is compared "
                "with the young-adult reference, which is not a paediatric norm.")
    if overall_age is not None and overall_age > STANDARD_MAX_AGE:
        return (f"A hearing age above {STANDARD_MAX_AGE} lies beyond the range "
                f"{STANDARD} covers and is extrapolated from its curve.")
    return None


def ear_norms(
    ac: Dict[int, Optional[ThresholdValue]],
    age: float,
    sex: str = "unspecified",
) -> Optional[dict]:
    """Full age-matched comparison for one ear."""
    numeric = ear_to_numeric(ac)
    if not any(v is not None for v in numeric.values()):
        return None

    per_freq: List[dict] = []
    hearing_ages: List[float] = []
    for f in AC_FREQS:
        value = numeric.get(f)
        if value is None:
            continue
        p = percentile(value, age, f, sex)
        if not p:
            continue
        ha = hearing_age(value, f, sex)
        p["hearing_age"] = ha
        p["hearing_age_extrapolated"] = ha is not None and ha > STANDARD_MAX_AGE
        per_freq.append(p)
        if ha is not None:
            hearing_ages.append(ha)

    if not per_freq:
        return None

    # The overall hearing age is driven by the frequencies where age-related
    # change actually shows, which is where noise damage also shows.
    high_ages = [p["hearing_age"] for p in per_freq
                 if p["freq"] >= 2000 and p["hearing_age"] is not None]
    overall_age = round(sum(high_ages) / len(high_ages), 0) if high_ages else None

    worst = min(per_freq, key=lambda p: p["better_than_pct"])
    mean_gap = round(sum(p["difference"] for p in per_freq) / len(per_freq), 1)
    # Whether the thresholds themselves are still inside clinical normal
    # limits changes what a raised hearing age means.
    clinically_normal = all(p["threshold"] < NORMAL_BELOW_DB for p in per_freq)

    basis = sex_basis(sex)
    extrapolation = _extrapolation_note(age, overall_age)
    summary = _summary(overall_age, age, worst, mean_gap, clinically_normal, basis)
    if extrapolation and overall_age is not None:
        summary = f"{summary} {extrapolation}"

    return {
        "age": age,
        "sex": sex,
        "sex_basis": basis,
        "per_frequency": per_freq,
        "hearing_age": overall_age,
        "age_gap": None if overall_age is None else round(overall_age - float(age), 0),
        "mean_difference_db": mean_gap,
        "worst_frequency": worst,
        "clinically_normal": clinically_normal,
        "age_in_standard_range": age_within_standard(age),
        "hearing_age_extrapolated": overall_age is not None and overall_age > STANDARD_MAX_AGE,
        "extrapolated": extrapolation is not None,
        "extrapolation_note": extrapolation,
        "summary": summary,
        "standard": STANDARD,
        "method": f"{STANDARD} median age-related threshold curves",
        "sex_note": (None if basis != "unspecified" else
                     "Sex not recorded as male or female: expected thresholds use the "
                     "mean of the ISO 7029 male and female curves."),
        "caveat": ("ISO 7029 describes otologically screened populations, so it is a "
                   "demanding reference; percentiles use a normal approximation to its "
                   "spread and are indicative. Hearing age comes from the median curve "
                   "directly. A high hearing age with thresholds still inside normal "
                   "limits means early change, not a diagnosis of hearing loss."),
    }


def _summary(overall_age, actual_age, worst, mean_gap, clinically_normal=False,
             basis: str = "male") -> str:
    actual = float(actual_age)
    if overall_age is None:
        return "Age-matched comparison unavailable."

    peers = ("for its age and sex" if basis != "unspecified" else
             "for its age (sex not recorded; male and female norms averaged)")
    at_freq = (f"At {worst['freq']} Hz this ear sits in the bottom "
               f"{worst['better_than_pct']:g}% {peers}.")

    if overall_age <= actual + 3:
        return ("Hearing is what would be expected at this age. " + at_freq
                if worst["better_than_pct"] < 25 else
                "Hearing is what would be expected at this age, or better.")

    gap = overall_age - actual
    if gap >= 20:
        lead = (f"These ears are performing like a typical {overall_age:.0f}-year-old's "
                f"— about {gap:.0f} years older than the patient.")
    else:
        lead = (f"Hearing is roughly {gap:.0f} years ahead of this patient's age "
                f"(comparable to a typical {overall_age:.0f}-year-old).")

    if clinically_normal:
        return (f"{lead} Thresholds are still within normal limits, so this is early "
                f"change rather than hearing loss — but it is the point at which it "
                f"can still be stopped. {at_freq}")
    return f"{lead} {at_freq}"


def analyze_norms(right_ac, left_ac, age: float, sex: str = "unspecified") -> Optional[dict]:
    """Age-matched norms for both ears."""
    if age is None:
        return None
    right = ear_norms(right_ac, age, sex)
    left = ear_norms(left_ac, age, sex)
    if not right and not left:
        return None

    ages = [e["hearing_age"] for e in (right, left)
            if e and e["hearing_age"] is not None]
    worse_age = max(ages) if ages else None
    extrapolation = _extrapolation_note(age, worse_age)
    headline = (
        f"Hearing age {worse_age:.0f} versus an actual age of {float(age):.0f}."
        if worse_age is not None and worse_age > float(age) + 3 else
        "Hearing is age-appropriate."
    )
    if extrapolation:
        headline += f" (Extrapolated beyond {STANDARD}'s {REFERENCE_AGE}–{STANDARD_MAX_AGE}-year range.)"
    return {
        "right": right,
        "left": left,
        "hearing_age": worse_age,
        "age_gap": None if worse_age is None else round(worse_age - float(age), 0),
        "headline": headline,
        "extrapolated": extrapolation is not None,
        "extrapolation_note": extrapolation,
        "sex_basis": sex_basis(sex),
        "standard": STANDARD,
        "method": STANDARD,
    }
