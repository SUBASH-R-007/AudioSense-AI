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
spondee list is repeated correctly. It should agree within about 10 dB with
the 500/1000/2000 Hz average — or, in a sloping or rising loss, with
Fletcher's average of the best two (ASHA 1988; Fletcher 1950). An SRT
substantially BETTER than both means the tones are exaggerated — the classic
non-organic picture, and the one that matters most in compensation and
disability certification. Holding an honest sloping or reverse-slope loss to
the three-frequency mean alone makes it look non-organic.

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

from math import comb, isclose
from typing import Dict, List, Optional

from app.models.schemas import PTA_FREQS, ThresholdValue, ear_to_numeric

#: Acceptable SRT–pure-tone agreement, dB.
SRT_AGREEMENT_DB = 10
#: The frequencies the SRT is compared against. ASHA (1988) recognises two
#: averages of them: the three-frequency PTA (Fletcher 1929), with which "for
#: most clinical cases there will be good agreement", and the average of the
#: best two (Fletcher 1950), with which agreement "may be better" in a
#: sloping loss. The SRT agrees when it is within SRT_AGREEMENT_DB of EITHER;
#: the best-two average can never exceed the three-frequency one, so an SRT is
#: called better than the tones only when it beats both. 4000 Hz carries
#: little of what a spondee needs.
SRT_PTA_FREQS = (500, 1000, 2000)
#: An adjacent-octave step (500→1000 or 1000→2000 Hz) larger than this marks
#: a steep configuration: Guthrie & Mackersie (2009, J Am Acad Audiol
#: 20(6):381) note that the best-two average "is often used in lieu of the
#: pure-tone average when there is a greater than 20 dB difference between
#: two adjacent frequencies". In a "really precipitous" configuration the SRT
#: can follow the single best threshold (Schoepflin 2012, AudiologyOnline,
#: "Back to Basics: Speech Audiometry"). No published cut-off for precipitous
#: could be confirmed, so above this step an SRT that beats both averages but
#: sits within SRT_AGREEMENT_DB of the best single threshold is reported as
#: indeterminate — neither agreement nor non-organic loss.
STEEP_STEP_DB = 20
#: The SRT rule as reported with every result and by the reference endpoint.
SRT_CRITERION = (
    f"SRT within {SRT_AGREEMENT_DB} dB of the 500/1000/2000 Hz average or of "
    f"Fletcher's best-two average; more than {SRT_AGREEMENT_DB} dB better than "
    "both suggests exaggerated tones, unless an adjacent-octave step exceeds "
    f"{STEEP_STEP_DB} dB and the SRT is within {SRT_AGREEMENT_DB} dB of the "
    "best single threshold (indeterminate). ASHA 1988; Fletcher 1929, 1950; "
    "Schoepflin 2012"
)
#: Rollover is called when the index EXCEEDS this value. 0.45 separated
#: cochlear from eighth-nerve ears on PAL PB-50 lists in Jerger & Jerger
#: (1971) and again in Dirks et al. (1977); the criterion is applied as
#: "ratios > 0.45" (Qian et al. 2023, Ear Hear 44(6):1540). Schlauch & Carney
#: (2018, JSLHR 61:936) quote Dirks' PB-50 pass/fail value as 0.46 — the same
#: rule for an index given to two decimals. On the exact ratio an index
#: strictly between the two (40/88 = 0.4545) is called rollover, the referral
#: direction, with a borderline note. The criterion is list-specific: Meyer &
#: Mishler (1985) found > 0.35 the separating value for Auditec NU-6 lists, so
#: an index between 0.35 and 0.45 is reported as a caveat.
ROLLOVER_THRESHOLD = 0.45
#: Dirks et al.'s PB-50 criterion as quoted by Schlauch & Carney (2018); an
#: index above ROLLOVER_THRESHOLD but below this is flagged with a note.
ROLLOVER_THRESHOLD_DIRKS = 0.46
#: Rollover criterion reported for NU-6 word lists (Meyer & Mishler 1985,
#: J Speech Hear Disord 50:356) — used only to caveat, never to flag, because
#: the word list is not recorded.
ROLLOVER_THRESHOLD_NU6 = 0.35
#: SDT normally sits this far BELOW the SRT (detection is easier than
#: recognition). Chaiklin (1959); ASHA (1988) guidelines for determining
#: threshold level for speech, which give the mean gap as 8-9 dB.
SDT_SRT_EXPECTED_DB = (5, 10)
#: Clinical thresholds move in 5 dB steps, so a gap one step outside the
#: expected range is reported as atypical rather than flagged.
THRESHOLD_STEP_DB = 5
#: Interaural attenuation for speech through supra-aural earphones, dB. Below
#: this the opposite cochlea may be responding, so masking is required.
SPEECH_INTERAURAL_ATTENUATION_DB = 45
#: Word recognition is measured this far above the SRT, where PB max is
#: normally reached.
SUPRATHRESHOLD_SL_DB = 30
#: Frequencies that carry speech energy, used for the SDT comparison.
SPEECH_FREQS = [250, 500, 1000, 2000, 4000]

#: Word-recognition categories after Goetzinger (1978), "Word discrimination
#: testing", in Katz (ed.) Handbook of Clinical Audiology, 2nd ed.:
#: 90-100% excellent / within normal limits, 78-88% good / slight difficulty,
#: 66-76% fair / moderate difficulty, 54-64% poor / great difficulty, below
#: 52% very poor. The published bands are written in the 2% steps of a
#: 50-word list and leave gaps between them (e.g. 52%, or 77% on a 30-word
#: list); a score in a gap takes the POORER category, so a band never
#: overstates recognition. Each band is (low inclusive, high exclusive).
WRS_BANDS = [
    (90, 100, "Excellent — within normal limits"),
    (78, 90, "Good — slight difficulty"),
    (66, 78, "Fair — moderate difficulty"),
    (54, 66, "Poor — great difficulty"),
    (0, 54, "Very poor"),
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

    Both scores must come from a list of ``n`` words. Where they do not, use
    ``scores_differ_unequal`` — passing one score's list length for a
    comparison against a score measured on a different list understates the
    uncertainty of whichever list was shorter.
    """
    if n <= 0:
        return None
    ci = binomial_ci(round(score_a * n / 100), n, confidence)
    if ci["low"] is None:
        return None
    return not (ci["low"] <= score_b <= ci["high"])


def scores_differ_unequal(score_a: float, n_a: int, score_b: float, n_b: int,
                          confidence: float = 0.95) -> Optional[bool]:
    """``scores_differ`` for two scores measured on lists of different lengths.

    There is no single Thornton & Raffin table row for a comparison between a
    50-word score and a 25-word one: the table is indexed by list length, and
    the two scores carry different precision. Testing with only one of the two
    lengths — whichever the caller happened to pass — makes a difference the
    shorter list cannot resolve look resolvable.

    So the difference counts only when NEITHER score falls inside the other's
    interval. That is symmetric, uses each score's own list length, and is the
    conservative direction: it can refuse to call a real difference real, and
    it cannot manufacture one. Which is the right way round, because the
    caller that matters here turns a difference into a referral for imaging.

    With equal list lengths this reduces to ``scores_differ``, since the two
    one-sided tests agree whenever the intervals are symmetric about their
    own scores.
    """
    if n_a <= 0 or n_b <= 0:
        return None
    a_outside = scores_differ(score_a, score_b, n_a, confidence)
    b_outside = scores_differ(score_b, score_a, n_b, confidence)
    if a_outside is None or b_outside is None:
        return None
    return a_outside and b_outside


# --------------------------------------------------------------------------
# pure-tone comparators
# --------------------------------------------------------------------------
def pta_three_frequency(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """Three-frequency PTA (500/1000/2000 Hz) — the conventional SRT comparator.

    Fletcher (1929); ASHA (1988) guidelines for determining threshold level
    for speech. Averages whichever of the three were tested; the caller
    decides whether an incomplete average is good enough.
    """
    numeric = ear_to_numeric(ac)
    vals = [numeric[f] for f in SRT_PTA_FREQS if numeric.get(f) is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def pta_two_frequency(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """Two-frequency PTA (500/1000 Hz).

    Reported for reference only. For a high-frequency slope it approximates
    Fletcher's average; for a rising loss it is the two WORST of the speech
    frequencies, so it is never used as the comparator on its own.
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


def best_comparator_threshold(ac: Dict[int, Optional[ThresholdValue]]
                              ) -> Optional[tuple]:
    """The best single threshold of 500/1000/2000 Hz, as (dB, Hz).

    The SRT comparator of last resort in a precipitous configuration
    (Schoepflin 2012: "the best frequency in the PTA"). The lower frequency
    wins a tie.
    """
    numeric = ear_to_numeric(ac)
    vals = [(v, f) for f in SRT_PTA_FREQS if (v := numeric.get(f)) is not None]
    return min(vals) if vals else None


def speech_configuration(ac: Dict[int, Optional[ThresholdValue]]) -> dict:
    """Shape of the 500-2000 Hz audiogram, as far as the SRT check cares.

    ``gradual`` (flat, or sloping/rising by no more than ``STEEP_STEP_DB`` per
    octave) unless an adjacent-octave step (500→1000 or 1000→2000 Hz) exceeds
    ``STEEP_STEP_DB``. A large step is ``sloping`` when the thresholds worsen
    with frequency, ``rising`` (reverse slope) when they improve, and
    ``irregular`` when both happen. ``incomplete`` when any of the three
    frequencies is untested, because the shape cannot be judged.
    """
    numeric = ear_to_numeric(ac)
    vals = {f: numeric.get(f) for f in SRT_PTA_FREQS}
    missing = [f for f, v in vals.items() if v is None]
    if missing:
        return {"shape": "incomplete", "missing": missing, "steps": [],
                "steep": None}
    steps = [vals[1000] - vals[500], vals[2000] - vals[1000]]
    large = [s for s in steps if abs(s) > STEEP_STEP_DB]
    if not large:
        shape = "gradual"
    elif all(s > 0 for s in large):
        shape = "sloping"
    elif all(s < 0 for s in large):
        shape = "rising"
    else:
        shape = "irregular"
    return {"shape": shape, "missing": [], "steps": steps, "steep": bool(large)}


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
        elif srt_difference > hi + THRESHOLD_STEP_DB:
            flags.append("sdt_srt_gap_wide")
            notes.append(
                f"SDT is {srt_difference:g} dB better than the SRT, against an "
                f"expected {lo}-{hi} dB. A wide gap is typical of a steeply "
                "sloping loss, where low frequencies allow detection but not "
                "recognition — or of an unreliable SRT."
            )
        elif srt_difference > hi:
            notes.append(
                f"SDT is {srt_difference:g} dB better than the SRT — wider than "
                f"the expected {lo}-{hi} dB, but within one "
                f"{THRESHOLD_STEP_DB} dB step of it. A sloping loss widens the "
                "gap; not by itself an inconsistency."
            )
        elif srt_difference < lo:
            gap = ("SDT equals the SRT" if srt_difference == 0 else
                   f"SDT is only {srt_difference:g} dB better than the SRT")
            notes.append(
                f"{gap} — narrower than the expected {lo}-{hi} dB. Detection "
                "normally needs less level than recognition, so either the SDT "
                "was set too high or the SRT was scored leniently. Within one "
                f"{THRESHOLD_STEP_DB} dB step of the expected gap, so re-check "
                "rather than reject either."
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
    """Compare the SRT with the conventional pure-tone averages.

    The SRT is checked against both averages ASHA (1988) recognises — the
    500/1000/2000 Hz mean (Fletcher 1929) and the best two of those
    frequencies (Fletcher 1950) — and agrees when it is within
    ``SRT_AGREEMENT_DB`` of either. Speech reception follows the frequencies
    the patient still hears, so in a sloping OR rising loss the
    three-frequency mean is dragged towards the frequency that contributes
    least, and an honest SRT looks "too good" against it alone.

    Non-organic loss is suspected only when the SRT is better than BOTH
    averages by more than the tolerance. In a steep configuration (an
    adjacent-octave step over ``STEEP_STEP_DB``) the SRT can follow the best
    single threshold, so an SRT within tolerance of that threshold leaves the
    check indeterminate rather than calling the tones exaggerated. With any
    of 500/1000/2000 Hz untested the configuration — and so the right average
    — cannot be established, and the check is indeterminate as well.

    ``comparator`` is the average the verdict rests on: the one nearest the
    SRT (a tie goes to the three-frequency average), the tested frequencies
    when incomplete, or the best single threshold when indeterminate in a
    steep configuration. ``difference`` is comparator − SRT; positive means
    the SRT is better than the tones.
    """
    if srt is None:
        return None
    tol = SRT_AGREEMENT_DB
    numeric = ear_to_numeric(ac)
    pta_vals = [numeric[f] for f in PTA_FREQS if numeric.get(f) is not None]
    pta = round(sum(pta_vals) / len(pta_vals), 1) if pta_vals else None
    pta2 = pta_two_frequency(ac)
    pta3 = pta_three_frequency(ac)
    fletcher = pta_fletcher(ac)
    best = best_comparator_threshold(ac)
    config = speech_configuration(ac)
    shape, missing = config["shape"], config["missing"]

    labels = {
        "three_frequency": "three-frequency average (500/1000/2000 Hz)",
        "fletcher": "Fletcher average (best two of 500/1000/2000 Hz)",
    }
    agrees: Optional[bool] = None
    non_organic = False
    indeterminate: Optional[str] = None
    comparator = basis = None
    d3 = df = None  # average − SRT; positive = SRT better than the tones

    if pta3 is None:
        indeterminate = "no_speech_frequencies"
    elif missing:
        # The configuration decides which average applies, and one of the
        # frequencies that defines it is missing.
        indeterminate = "incomplete"
        tested = [str(f) for f in SRT_PTA_FREQS if f not in missing]
        comparator, basis = pta3, "tested_frequencies"
        labels[basis] = (f"average of {'/'.join(tested)} Hz" if len(tested) > 1
                         else f"threshold at {tested[0]} Hz")
    else:
        d3, df = round(pta3 - srt, 1), round(fletcher - srt, 1)
        if abs(d3) <= abs(df):
            comparator, basis = pta3, "three_frequency"
        else:
            comparator, basis = fletcher, "fletcher"
        if abs(d3) <= tol or abs(df) <= tol:
            agrees = True
        elif df > tol:
            best_db, best_hz = best
            if config["steep"] and best_db - srt <= tol:
                indeterminate = "steep_configuration"
                comparator, basis = best_db, "best_threshold"
                labels[basis] = f"best single threshold ({best_hz} Hz)"
            else:
                agrees, non_organic = False, True
        else:
            agrees = False
    label = labels.get(basis)
    diff = None if comparator is None else round(comparator - srt, 1)

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

    # Every message names the averages it used, because the non-organic call
    # can reach a disability certificate.
    if indeterminate == "no_speech_frequencies":
        message = (
            f"SRT ({srt} dB) cannot be checked against the pure tones: none of "
            "500/1000/2000 Hz was tested. Obtain those thresholds before using "
            "the SRT as a validity check."
        )
    elif indeterminate == "incomplete":
        relation = ("equals" if diff == 0 else
                    f"is {abs(diff):g} dB {'better' if diff > 0 else 'poorer'} than")
        message = (
            f"SRT ({srt} dB) {relation} the {label}, {comparator:g} dB, but "
            f"{'/'.join(str(f) for f in missing)} Hz was not tested. Which "
            "average the SRT should match depends on the configuration across "
            "500/1000/2000 Hz, so agreement cannot be judged — complete those "
            "thresholds before using the SRT as a validity check or certifying "
            "disability."
        )
    elif indeterminate == "steep_configuration":
        near_best = (f"within {abs(diff):g} dB of" if abs(diff) <= tol else
                     "between that average and")
        message = (
            f"SRT ({srt} dB) is {df:g} dB better than Fletcher's best-two "
            f"average ({fletcher:g} dB) and {d3:g} dB better than the "
            f"three-frequency average ({pta3:g} dB), but {near_best} the best "
            f"single threshold ({comparator:g} dB at "
            f"{best[1]} Hz). In a precipitous configuration the SRT can follow "
            f"the best single threshold, and this {shape} configuration has an "
            f"adjacent-octave step over {STEEP_STEP_DB} dB — so the SRT can "
            "neither confirm nor refute the pure tones. Confirm the thresholds "
            "with an objective measure (e.g. ABR or ASSR) before any disability "
            "certification."
        )
    elif non_organic:
        if fletcher == pta3:
            against = (f"{d3:g} dB better than the three-frequency average "
                       f"(500/1000/2000 Hz), {pta3:g} dB, which here equals "
                       "Fletcher's best-two average")
        else:
            against = (f"better than both conventional averages — {df:g} dB "
                       f"better than Fletcher's best-two average ({fletcher:g} dB) "
                       f"and {d3:g} dB better than the three-frequency average "
                       f"({pta3:g} dB)")
        message = (
            f"SRT ({srt} dB) is {against}. Pure-tone thresholds are likely "
            "exaggerated — consider non-organic (functional) hearing loss and "
            "repeat with re-instruction before any disability certification."
        )
        if config["steep"]:
            message += (
                f" It is also {best[0] - srt:g} dB better than the best single "
                f"threshold ({best[0]:g} dB at {best[1]} Hz), so even a "
                "precipitous configuration does not explain it."
            )
    elif agrees:
        closeness = "exactly" if diff == 0 else f"within {abs(diff):g} dB"
        message = (
            f"SRT ({srt} dB) agrees with the {label}, {comparator:g} dB, "
            f"{closeness} — test is internally consistent."
        )
        if abs(d3) > tol:
            message += (
                f" Against the three-frequency average ({pta3:g} dB) alone it "
                f"would look {d3:g} dB too good: in a sloping or rising loss the "
                "SRT follows the frequencies the patient hears best (ASHA 1988; "
                "Fletcher 1950)."
            )
    elif d3 < -tol:
        message = (
            f"SRT ({srt} dB) is {abs(d3):g} dB poorer than the three-frequency "
            f"average (500/1000/2000 Hz), {pta3:g} dB"
            + (f", and {abs(df):g} dB poorer than Fletcher's best-two average "
               f"({fletcher:g} dB)" if fletcher != pta3 else "")
            + " — unusual; check test reliability, speech material and "
            "language familiarity."
        )
    else:
        # Only possible when the poorest frequency sits far above the other
        # two (a gap of more than 2 x tolerance between the averages).
        message = (
            f"SRT ({srt} dB) lies between Fletcher's best-two average "
            f"({fletcher:g} dB) and the three-frequency average ({pta3:g} dB), "
            f"within {tol} dB of neither — {abs(df):g} dB poorer than the "
            "frequencies the patient hears best. Not the pattern of exaggerated "
            "tones, but unusual; check test reliability, speech material and "
            "language familiarity."
        )

    return {
        "srt": srt,
        # Four-frequency PTA (500-4000 Hz), for reference — not a comparator.
        "pta": pta,
        "pta_500_1000": pta2,
        "pta_500_1000_2000": pta3,
        "pta_fletcher": fletcher,
        "best_threshold": None if best is None else best[0],
        "best_threshold_freq": None if best is None else best[1],
        "configuration": shape,
        "comparator": comparator,
        "comparator_basis": basis,
        "comparator_label": label,
        "difference": diff,
        "agrees": agrees,
        "indeterminate_reason": indeterminate,
        "masked": masked,
        "masking_note": masking_note,
        "non_organic_suspected": non_organic,
        "criterion": SRT_CRITERION,
        "message": message,
    }


# --------------------------------------------------------------------------
# WRS
# --------------------------------------------------------------------------
def wrs_analysis(wrs: List[dict], pta: Optional[float] = None,
                 srt: Optional[int] = None) -> Optional[dict]:
    """Interpret word-recognition scores with their statistical uncertainty.

    Rollover index = (PB max − PB min above the max) / PB max (Jerger &
    Jerger 1971). An index EXCEEDING 0.45 is the classic retrocochlear
    indicator; an index of exactly 0.45 meets but does not exceed it and is
    reported as borderline, not as rollover.
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
    # The POINT, not just its score. The level is the most useful single fact
    # about a rollover — "recognition fell at 95 dB" is actionable where a bare
    # percentage is not — and the list length is needed to test the drop
    # against the right amount of uncertainty.
    worst = min(after, key=lambda p: p["score"]) if after else None
    pb_min = worst["score"] if worst else None

    rollover_index = None
    rollover = False
    rollover_significant = None
    rollover_ratio = None
    rollover_provisional = False
    if worst is not None and pb_max > 0:
        # The criterion is applied to the exact ratio; the rounded index is
        # for display only.
        rollover_ratio = (pb_max - pb_min) / pb_max
        rollover_index = round(rollover_ratio, 3)
        exceeds = (rollover_ratio > ROLLOVER_THRESHOLD
                   and not isclose(rollover_ratio, ROLLOVER_THRESHOLD))
        # A drop the word lists cannot resolve is not a drop. Each score is
        # tested with its OWN list length: PB max on 50 words against a
        # minimum on 25 used to be judged entirely on the 50-word interval,
        # which treats the shorter list as more precise than it is.
        rollover_significant = scores_differ_unequal(
            pb_max, best["n_words"], pb_min, worst["n_words"])

        # THE INDEX ALONE IS NOT ENOUGH, and this is the correction that
        # matters. The index is a RATIO, so at a low PB max a difference of a
        # few words swings it past the criterion: 6 words correct falling to 3
        # on a 25-word list is an index of 0.50 and a drop of three words.
        # Acting on that produced an urgent referral for imaging — the whole
        # point of carrying binomial intervals through this module is to stop
        # exactly that, and the flag ignored them.
        #
        # So a confirmed rollover now needs both the criterion AND a drop the
        # lists can resolve. Where the index exceeds the criterion but the
        # drop does not survive the test, the finding is kept and reported as
        # PROVISIONAL with a repeat instruction — it is not discarded, and it
        # does not become a referral on its own.
        #
        # An untestable drop (no usable interval) leaves the criterion to
        # decide, which fails toward referral rather than away from it.
        rollover = exceeds and rollover_significant is not False
        rollover_provisional = exceeds and rollover_significant is False

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
            f"recognition falls from {pb_max:g}% at {best['level']} dB HL to "
            f"{pb_min:g}% at {worst['level']} dB HL, which suggests a "
            "retrocochlear site of lesion. Refer for ENT/neuro-otology assessment."
        )
        if rollover_ratio < ROLLOVER_THRESHOLD_DIRKS and not isclose(
                rollover_ratio, ROLLOVER_THRESHOLD_DIRKS):
            notes.append(
                f"The index exceeds {ROLLOVER_THRESHOLD} but not "
                f"{ROLLOVER_THRESHOLD_DIRKS}, the form in which Dirks et al.'s "
                "PB-50 criterion is also quoted (Schlauch & Carney 2018). "
                "Borderline — repeat the performance-intensity function with "
                "full lists; the referral stands until it is repeated."
            )
        if rollover_significant is None:
            notes.append(
                "The drop could not be tested against the word lists' own "
                "uncertainty, so the criterion alone decides it here."
            )
    elif rollover_provisional:
        # Reported, not discarded — and not a referral. The index is a ratio,
        # and a ratio over a low PB max moves by whole words.
        lists = (f"a {best['n_words']}-word list"
                 if best["n_words"] == worst["n_words"]
                 else f"{best['n_words']}- and {worst['n_words']}-word lists")
        notes.append(
            f"Possible rollover: index {rollover_index} exceeds "
            f"{ROLLOVER_THRESHOLD}, but the fall from {pb_max:g}% at "
            f"{best['level']} dB HL to {pb_min:g}% at {worst['level']} dB HL is "
            f"within what {lists} cannot resolve — "
            f"{best['correct']} words correct against {worst['correct']}. The "
            "index is a ratio, so at a low PB max a difference of a few words "
            "clears the criterion on its own. Repeat the performance-intensity "
            "function with full lists before reading this as retrocochlear; it "
            "is not a referral on these numbers."
        )
    elif rollover_ratio is not None and isclose(rollover_ratio, ROLLOVER_THRESHOLD):
        notes.append(
            f"Rollover index {rollover_index} meets but does not exceed the "
            f"criterion (index > {ROLLOVER_THRESHOLD}). Borderline — repeat the "
            "performance-intensity function with full lists before ruling "
            "rollover in or out."
        )
    elif (rollover_ratio is not None
          and rollover_ratio > ROLLOVER_THRESHOLD_NU6
          and not isclose(rollover_ratio, ROLLOVER_THRESHOLD_NU6)):
        notes.append(
            f"Rollover index {rollover_index} is below the {ROLLOVER_THRESHOLD} "
            "criterion derived on PAL PB-50 lists, but above the "
            f"{ROLLOVER_THRESHOLD_NU6} reported for NU-6 lists (Meyer & Mishler "
            "1985). The criterion depends on the word list; if this list has no "
            f"validated {ROLLOVER_THRESHOLD} criterion, rollover cannot be "
            "excluded — repeat the performance-intensity function."
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
        #: Where the minimum was measured, and on what list. Without these the
        #: reader cannot tell a two-word wobble from a collapse, and the
        #: significance test cannot use the right amount of uncertainty.
        "pb_min_level": worst["level"] if worst else None,
        "pb_min_n_words": worst["n_words"] if worst else None,
        "pb_min_ci": worst["ci"] if worst else None,
        "rollover_index": rollover_index,
        "rollover": rollover,
        "rollover_criterion": (f"index > {ROLLOVER_THRESHOLD} AND a drop the word "
                               "lists can resolve (PAL PB-50; Jerger & Jerger "
                               "1971, Dirks et al. 1977; Thornton & Raffin 1978)"),
        "rollover_significant": rollover_significant,
        #: Index over the criterion, drop inside what the lists can hide. A
        #: finding to repeat, never a referral on its own.
        "rollover_provisional": rollover_provisional,
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
    if srt and srt["agrees"] is None:
        # The SRT could not be used as a validity check (see its message):
        # not evidence for the tones, and not evidence against them.
        flags.append("srt_indeterminate")
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
    # Each ear tested on its own list length rather than both on the shorter
    # one. Same reasoning as the rollover drop: the ears are often scored on
    # different lists, and this comparison escalates to an urgent alert
    # recommending imaging of the poorer ear, so it must not inherit a
    # precision neither measurement has.
    significant = scores_differ_unequal(
        r_wrs["pb_max"], r_wrs["n_words"], l_wrs["pb_max"], l_wrs["n_words"])

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
