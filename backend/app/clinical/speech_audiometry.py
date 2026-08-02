"""Speech audiometry: SDT, SRT and word recognition.

Pure tones measure detection of sound. Speech audiometry measures what the
patient can do with it, and it is the standard internal-consistency check on
thresholds that depend on a voluntary response.

Three measurements, in the order a clinic obtains them:

**SDT — speech detection threshold** (also speech awareness threshold). The
lowest level at which speech is *detected* half the time. It does not require
the patient to understand or repeat anything, which makes it the fallback when
an SRT cannot be obtained: infants, profound loss, or no language in common.
Because detection only needs the most audible part of the spectrum, SDT tracks
the patient's BEST pure-tone threshold rather than the average, and normally
sits 5-10 dB better than the SRT (Chaiklin 1959; ASHA 1988).

**SRT — speech reception threshold.** The lowest level at which half of a
spondee list is repeated correctly. It should agree with the pure-tone average
within about 10 dB. An SRT substantially BETTER than the PTA means the tones
are exaggerated — the classic non-organic picture, and the one that matters
most in compensation and disability certification.

**WRS — word recognition score.** Percentage of monosyllabic words repeated
correctly at a suprathreshold level. Two things are routinely got wrong here
and are handled explicitly:

1. A WORD SCORE IS A SAMPLE, NOT A MEASUREMENT. A 25-word list gives a 95%
   confidence interval tens of percentage points wide, so 88% and 76% on
   25 words are not different results. Every score is reported with its exact
   binomial interval, and comparisons are tested rather than eyeballed
   (Thornton & Raffin 1978).
2. A SCORE IS MEANINGLESS BELOW THE LEVEL THAT PRODUCES IT. Word recognition
   is measured at 30-40 dB above the SRT, near the most comfortable level. A
   poor score obtained near threshold measures the presentation level, not the
   patient, and is flagged rather than interpreted.

Rollover — word recognition that FALLS as level rises — remains the classic
retrocochlear indicator.
"""
from __future__ import annotations

from math import comb
from typing import Dict, List, Optional

from app.models.schemas import PTA_FREQS, ThresholdValue, ear_to_numeric

#: Acceptable |PTA − SRT| agreement, dB.
SRT_AGREEMENT_DB = 10
#: Rollover index above this suggests a retrocochlear site of lesion.
ROLLOVER_THRESHOLD = 0.45
#: SDT normally sits this far BELOW the SRT (detection is easier than
#: recognition). Chaiklin (1959); ASHA (1988) guidelines for determining
#: threshold level for speech.
SDT_SRT_EXPECTED_DB = (5, 10)
#: Interaural attenuation for speech through supra-aural earphones, dB. Below
#: this the opposite cochlea may be responding, so masking is required.
SPEECH_INTERAURAL_ATTENUATION_DB = 45
#: Word recognition is measured this far above the SRT, where PB max is
#: normally reached.
SUPRATHRESHOLD_SL_DB = 30
#: Frequencies that carry speech energy, used for the SDT comparison.
SPEECH_FREQS = [250, 500, 1000, 2000, 4000]

WRS_BANDS = [
    (90, 100, "Excellent — normal word recognition"),
    (76, 90, "Good — slight difficulty with speech"),
    (60, 76, "Fair — moderate difficulty following conversation"),
    (40, 60, "Poor — marked difficulty; limited benefit from amplification alone"),
    (0, 40, "Very poor — amplification alone unlikely to restore understanding"),
]


# --------------------------------------------------------------------------
# the statistics of a word list
# --------------------------------------------------------------------------
def _binomial_tail(n: int, k: int, p: float, upper: bool) -> float:
    """P(X >= k) when ``upper``, else P(X <= k), for X ~ Binomial(n, p)."""
    rng = range(k, n + 1) if upper else range(0, k + 1)
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in rng)


def binomial_ci(correct: int, n: int, confidence: float = 0.95) -> dict:
    """Exact (Clopper-Pearson) confidence interval for a word score.

    Computed by bisection on the exact binomial tail rather than a normal
    approximation, because word lists are short and scores cluster near 100%,
    which is exactly where the approximation is worst.

    This is the number that stops a clinician reading a difference into two
    scores that a 25-word list cannot resolve.
    """
    if n <= 0:
        return {"low": None, "high": None, "width": None, "n": n}
    correct = max(0, min(n, correct))
    alpha = (1 - confidence) / 2

    def solve(upper: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            tail = _binomial_tail(n, correct, mid, upper)
            if upper:
                # P(X >= correct) increases with p; find where it equals alpha.
                lo, hi = (lo, mid) if tail > alpha else (mid, hi)
            else:
                # P(X <= correct) decreases with p.
                lo, hi = (mid, hi) if tail > alpha else (lo, mid)
        return (lo + hi) / 2

    low = 0.0 if correct == 0 else solve(upper=True)
    high = 1.0 if correct == n else solve(upper=False)
    return {
        "low": round(low * 100, 1),
        "high": round(high * 100, 1),
        "width": round((high - low) * 100, 1),
        "n": n,
        "confidence": confidence,
    }


def scores_differ(score_a: float, score_b: float, n: int,
                  confidence: float = 0.95) -> Optional[bool]:
    """Is the difference between two word scores larger than the list can hide?

    Tests whether the second score falls outside the first score's exact
    binomial interval — the practical form of the Thornton & Raffin (1978)
    critical-difference tables. Used for ear-to-ear and aided-versus-unaided
    comparisons, where the temptation to over-read a few percent is strongest.
    """
    if n <= 0:
        return None
    ci = binomial_ci(round(score_a * n / 100), n, confidence)
    if ci["low"] is None:
        return None
    return not (ci["low"] <= score_b <= ci["high"])


# --------------------------------------------------------------------------
# pure-tone comparators
# --------------------------------------------------------------------------
def pta_two_frequency(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """Two-frequency PTA (500/1000 Hz) — the classic SRT comparator.

    For steeply sloping losses the 500/1000 Hz average predicts the SRT
    better than the four-frequency PTA does.
    """
    numeric = ear_to_numeric(ac)
    vals = [numeric[f] for f in (500, 1000) if numeric.get(f) is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def pta_fletcher(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """Fletcher's average: the two BEST of 500, 1000 and 2000 Hz.

    The best predictor of the SRT in a sloping loss, because speech reception
    follows the frequencies the patient still hears rather than the mean of
    the ones they do not.
    """
    numeric = ear_to_numeric(ac)
    vals = sorted(v for f in (500, 1000, 2000)
                  if (v := numeric.get(f)) is not None)
    if not vals:
        return None
    best = vals[:2] if len(vals) >= 2 else vals
    return round(sum(best) / len(best), 1)


def best_speech_threshold(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """The single best threshold across the speech range.

    Detection needs only the most audible frequency, so this — not the average
    — is what an SDT should approximate.
    """
    numeric = ear_to_numeric(ac)
    vals = [numeric[f] for f in SPEECH_FREQS if numeric.get(f) is not None]
    return round(min(vals), 1) if vals else None


# --------------------------------------------------------------------------
# SDT
# --------------------------------------------------------------------------
def sdt_analysis(ac: Dict[int, Optional[ThresholdValue]],
                 sdt: Optional[int],
                 srt: Optional[int] = None) -> Optional[dict]:
    """Speech detection threshold against the best pure tone and the SRT."""
    if sdt is None:
        return None

    best = best_speech_threshold(ac)
    lo, hi = SDT_SRT_EXPECTED_DB
    notes: List[str] = []
    flags: List[str] = []

    tone_difference = None if best is None else round(best - sdt, 1)
    if tone_difference is not None and abs(tone_difference) > 10:
        flags.append("sdt_tone_mismatch")
        notes.append(
            f"SDT ({sdt} dB) differs from the best pure-tone threshold "
            f"({best:g} dB) by {abs(tone_difference):g} dB. Detection should "
            "track the most audible frequency closely; re-check both."
        )

    srt_difference = None
    if srt is not None:
        srt_difference = round(srt - sdt, 1)  # positive = SDT better than SRT
        if srt_difference < 0:
            flags.append("sdt_worse_than_srt")
            notes.append(
                f"SDT ({sdt} dB) is poorer than the SRT ({srt} dB). Detecting "
                "speech cannot be harder than recognising it — one of the two "
                "measurements is wrong."
            )
        elif srt_difference > hi + 5:
            flags.append("sdt_srt_gap_wide")
            notes.append(
                f"SDT is {srt_difference:g} dB better than the SRT, against an "
                f"expected {lo}-{hi} dB. A wide gap is typical of a steeply "
                "sloping loss, where low frequencies allow detection but not "
                "recognition — or of an unreliable SRT."
            )
        else:
            notes.append(
                f"SDT is {srt_difference:g} dB better than the SRT, within the "
                f"expected {lo}-{hi} dB."
            )
    else:
        notes.append(
            "No SRT recorded. The SDT establishes that speech is audible but "
            "says nothing about whether it can be understood — obtain an SRT "
            "if the patient can repeat words."
        )

    return {
        "sdt": sdt,
        "best_pure_tone": best,
        "tone_difference": tone_difference,
        "srt": srt,
        "srt_difference": srt_difference,
        "expected_srt_gap": list(SDT_SRT_EXPECTED_DB),
        "agrees": not flags,
        "flags": flags,
        "notes": notes,
        "criterion": (f"SDT tracks the best pure-tone threshold and sits "
                      f"{lo}-{hi} dB better than the SRT"),
    }


# --------------------------------------------------------------------------
# SRT
# --------------------------------------------------------------------------
def srt_agreement(ac: Dict[int, Optional[ThresholdValue]],
                  srt: Optional[int],
                  masked: bool = False,
                  opposite_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
                  ) -> Optional[dict]:
    """Compare SRT with the pure-tone average and flag disagreement."""
    if srt is None:
        return None
    numeric = ear_to_numeric(ac)
    pta_vals = [numeric[f] for f in PTA_FREQS if numeric.get(f) is not None]
    if not pta_vals:
        return None
    pta = round(sum(pta_vals) / len(pta_vals), 1)
    pta2 = pta_two_frequency(ac)
    fletcher = pta_fletcher(ac)
    comparator = pta2 if pta2 is not None else pta
    diff = round(comparator - srt, 1)  # positive = SRT better than pure tones

    agrees = abs(diff) <= SRT_AGREEMENT_DB
    non_organic = diff > SRT_AGREEMENT_DB  # tones look worse than speech

    # Speech crosses the skull like a tone does. Without masking, a good SRT
    # may belong to the other ear entirely.
    masking_note = None
    if not masked and opposite_ac:
        other = ear_to_numeric(opposite_ac)
        other_best = [v for f in SPEECH_FREQS if (v := other.get(f)) is not None]
        if other_best and srt - min(other_best) >= SPEECH_INTERAURAL_ATTENUATION_DB:
            masking_note = (
                f"SRT of {srt} dB exceeds the opposite ear's best threshold by "
                f"at least {SPEECH_INTERAURAL_ATTENUATION_DB} dB and masking was "
                "not recorded. This may be a shadow response from the better ear."
            )

    return {
        "srt": srt,
        "pta": pta,
        "pta_500_1000": pta2,
        "pta_fletcher": fletcher,
        "comparator": comparator,
        "difference": diff,
        "agrees": agrees,
        "masked": masked,
        "masking_note": masking_note,
        "non_organic_suspected": non_organic,
        "criterion": f"|PTA − SRT| ≤ {SRT_AGREEMENT_DB} dB",
        "message": (
            f"SRT ({srt} dB) is {diff:g} dB better than the pure-tone average "
            f"({comparator:g} dB). Pure-tone thresholds are likely exaggerated — "
            "consider non-organic (functional) hearing loss and repeat with "
            "re-instruction before any disability certification."
        ) if non_organic else (
            f"SRT ({srt} dB) is {abs(diff):g} dB poorer than the pure-tone average — "
            "unusual; check test reliability, speech material and language familiarity."
        ) if not agrees else (
            f"SRT agrees with the pure-tone average within {abs(diff):g} dB — "
            "test is internally consistent."
        ),
    }


# --------------------------------------------------------------------------
# WRS
# --------------------------------------------------------------------------
def wrs_analysis(wrs: List[dict], pta: Optional[float] = None,
                 srt: Optional[int] = None) -> Optional[dict]:
    """Interpret word-recognition scores with their statistical uncertainty.

    Rollover index = (PB max − PB min above the max) / PB max. A value above
    0.45 is the classic retrocochlear indicator.
    """
    points = []
    for p in wrs:
        get = (lambda k, d=None: p.get(k, d)) if isinstance(p, dict) \
            else (lambda k, d=None: getattr(p, k, d))
        n_words = int(get("n_words", 25) or 25)
        score = float(get("score"))
        correct = round(score * n_words / 100)
        points.append({
            "level": get("level"),
            "score": score,
            "n_words": n_words,
            "correct": correct,
            "ci": binomial_ci(correct, n_words),
        })
    if not points:
        return None
    points.sort(key=lambda p: p["level"])

    best = max(points, key=lambda p: p["score"])
    pb_max = best["score"]
    after = [p for p in points if p["level"] > best["level"]]
    pb_min = min((p["score"] for p in after), default=None)

    rollover_index = None
    rollover = False
    rollover_significant = None
    if pb_min is not None and pb_max > 0:
        rollover_index = round((pb_max - pb_min) / pb_max, 3)
        rollover = rollover_index > ROLLOVER_THRESHOLD
        # A drop the word list cannot resolve is not a drop.
        rollover_significant = scores_differ(pb_max, pb_min, best["n_words"])

    band = next((d for lo, hi, d in WRS_BANDS if lo <= pb_max < hi), WRS_BANDS[0][2])
    disproportionate = pta is not None and pta < 50 and pb_max < 60

    # Word recognition is measured 30-40 dB above the SRT. Below that, a poor
    # score measures the presentation level rather than the patient.
    reference = srt if srt is not None else pta
    adequate_level = None
    if reference is not None and best["level"] is not None:
        adequate_level = best["level"] >= reference + SUPRATHRESHOLD_SL_DB

    notes = []
    if rollover:
        notes.append(
            f"Rollover index {rollover_index} exceeds {ROLLOVER_THRESHOLD} — word "
            "recognition worsens at higher levels, which suggests a retrocochlear "
            "site of lesion. Refer for ENT/neuro-otology assessment."
        )
        if rollover_significant is False:
            notes.append(
                f"That drop is within the range a {best['n_words']}-word list "
                "cannot resolve. Repeat with a full list before acting on it."
            )
    if disproportionate:
        notes.append(
            f"Word recognition ({pb_max:g}%) is disproportionately poor for a "
            f"{pta:g} dB HL loss — consider retrocochlear pathology or a "
            "significant cochlear distortion component."
        )
    if adequate_level is False:
        notes.append(
            f"The best score was obtained at {best['level']} dB HL, less than "
            f"{SUPRATHRESHOLD_SL_DB} dB above the {'SRT' if srt is not None else 'PTA'} "
            f"({reference:g} dB). PB max may not have been reached, so this score "
            "understates word recognition."
        )
    ci = best["ci"]
    if ci["width"] and ci["width"] > 25:
        # Advice only makes sense if there is a longer list to reach for. A
        # 50-word score near 50% is genuinely that uncertain, and telling the
        # clinician to run 50 words when they already have is not advice.
        remedy = ("Use a 50-word list before reporting this score as a "
                  "difference from anything."
                  if best["n_words"] < 50 else
                  "Mid-range scores carry this much uncertainty even on a full "
                  "list; treat it as a band rather than a number.")
        notes.append(
            f"A {best['n_words']}-word list gives a 95% confidence interval of "
            f"{ci['low']:g}-{ci['high']:g}%. {remedy}"
        )

    return {
        "points": points,
        "pb_max": pb_max,
        "pb_max_level": best["level"],
        "pb_max_ci": ci,
        "n_words": best["n_words"],
        "pb_min_after_max": pb_min,
        "rollover_index": rollover_index,
        "rollover": rollover,
        "rollover_significant": rollover_significant,
        "interpretation": band,
        "disproportionate": disproportionate,
        "adequate_level": adequate_level,
        "suprathreshold_target": (None if reference is None
                                  else round(reference + SUPRATHRESHOLD_SL_DB, 1)),
        "notes": notes,
    }


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------
def analyze_speech(ear, pta: Optional[float] = None,
                   opposite_ear=None) -> Optional[dict]:
    """Full speech-audiometry review for one ear (EarData)."""
    srt = srt_agreement(ear.ac, ear.srt,
                        masked=getattr(ear, "speech_masked", False),
                        opposite_ac=getattr(opposite_ear, "ac", None))
    sdt = sdt_analysis(ear.ac, getattr(ear, "sdt", None), ear.srt)
    wrs = wrs_analysis(ear.wrs, pta, ear.srt)
    if srt is None and wrs is None and sdt is None:
        return None

    flags = []
    if srt and srt["non_organic_suspected"]:
        flags.append("non_organic")
    if srt and srt["masking_note"]:
        flags.append("speech_masking_required")
    if sdt:
        flags.extend(sdt["flags"])
    if wrs and wrs["rollover"]:
        flags.append("rollover")
    if wrs and wrs["disproportionate"]:
        flags.append("disproportionate_wrs")
    if wrs and wrs["adequate_level"] is False:
        flags.append("wrs_level_too_low")

    return {
        "sdt": sdt,
        "srt": srt,
        "wrs": wrs,
        "flags": flags,
        "retrocochlear_suspicion": bool(
            wrs and (wrs["rollover"] or wrs["disproportionate"])),
    }


def compare_ears(right: Optional[dict], left: Optional[dict]) -> Optional[dict]:
    """Is the word-score difference between the ears real?

    An asymmetry in word recognition is a referral trigger, so it has to be
    tested against what the word list can actually resolve rather than read
    off two percentages.
    """
    r_wrs = (right or {}).get("wrs")
    l_wrs = (left or {}).get("wrs")
    if not r_wrs or not l_wrs:
        return None

    n = min(r_wrs["n_words"], l_wrs["n_words"])
    difference = round(r_wrs["pb_max"] - l_wrs["pb_max"], 1)
    significant = scores_differ(r_wrs["pb_max"], l_wrs["pb_max"], n)

    return {
        "right_pb_max": r_wrs["pb_max"],
        "left_pb_max": l_wrs["pb_max"],
        "difference": difference,
        "n_words": n,
        "significant": significant,
        "message": (
            f"Word recognition differs by {abs(difference):g} points "
            f"({r_wrs['pb_max']:g}% right, {l_wrs['pb_max']:g}% left), which is "
            f"more than a {n}-word list can attribute to chance. Investigate the "
            "poorer ear for retrocochlear pathology."
            if significant else
            f"The {abs(difference):g}-point difference between ears is within the "
            f"range a {n}-word list cannot resolve — not an asymmetry."
        ),
    }
