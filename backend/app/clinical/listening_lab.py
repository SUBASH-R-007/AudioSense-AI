"""Three functional listening measures the pure-tone audiogram cannot give.

An audiogram says how loud a tone must be before it is detected. It says
almost nothing about the three complaints that actually bring people to a
clinic:

  "I can't tell where sounds come from"   -> spatial localization
  "I can't follow speech in a crowd"      -> speech reception in noise
  "There is a ringing that never stops"   -> tinnitus

Each is measured here by a procedure with a real clinical counterpart, and
each is scored against published normative expectations rather than a
threshold in decibels.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from app.models.schemas import PTA_FREQS, ThresholdValue, ear_to_numeric

# ---------------------------------------------------------------------------
# 1. Spatial localization
# ---------------------------------------------------------------------------
#
# Horizontal localization depends on comparing the two ears: interaural
# level differences carry high frequencies, interaural time differences
# carry low ones. Both require the ears to be roughly matched, which is why
# asymmetric loss destroys localization even when the better ear hears well.
#
# Normative root-mean-square error for horizontal localization in normally
# hearing listeners is on the order of 5-10 degrees; unilateral or strongly
# asymmetric loss typically degrades it to 25-40 degrees.

NORMAL_RMS_DEGREES = 10.0
IMPAIRED_RMS_DEGREES = 25.0


def _pta(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    numeric = ear_to_numeric(ac)
    vals = [numeric[f] for f in PTA_FREQS if numeric.get(f) is not None]
    return sum(vals) / len(vals) if vals else None


def predict_localization(right_ac, left_ac) -> Optional[dict]:
    """Expected localization ability from the interaural asymmetry alone."""
    r, l = _pta(right_ac), _pta(left_ac)
    if r is None or l is None:
        return None
    asymmetry = abs(r - l)
    worse = max(r, l)

    if asymmetry >= 30:
        band, expectation = "severely impaired", (
            "A 30 dB or greater difference between the ears removes the "
            "interaural cues localization depends on. Expect the patient to "
            "turn the wrong way to a car horn or a called name.")
    elif asymmetry >= 15:
        band, expectation = "impaired", (
            "A moderate interaural difference degrades localization, most "
            "noticeably in noise and for brief sounds.")
    elif worse >= 50:
        band, expectation = "reduced", (
            "Hearing is symmetric but reduced in both ears; localization is "
            "usually preserved in quiet and degrades in noise.")
    else:
        band, expectation = "normal", "Localization cues are intact."

    return {
        "right_pta": None if r is None else round(r, 1),
        "left_pta": None if l is None else round(l, 1),
        "asymmetry_db": round(asymmetry, 1),
        "band": band,
        "expectation": expectation,
        "predicted_rms_error_deg": round(
            NORMAL_RMS_DEGREES + min(asymmetry, 45) * 0.7, 1),
    }


def score_localization(trials: List[dict]) -> Optional[dict]:
    """Score a run of the localization test.

    ``trials``: [{"presented_deg": float, "responded_deg": float}] with
    angles in degrees, 0 straight ahead, positive to the right.
    """
    if not trials:
        return None

    errors, front_back = [], 0
    for t in trials:
        presented = float(t["presented_deg"])
        responded = float(t["responded_deg"])
        # Wrap into [-180, 180] so a response of 350 vs 10 is a 20 degree error.
        err = (responded - presented + 180) % 360 - 180
        errors.append(err)
        # A left/right reversal is qualitatively different from being imprecise.
        if presented * responded < 0 and abs(presented) > 15 and abs(responded) > 15:
            front_back += 1

    n = len(errors)
    rms = math.sqrt(sum(e * e for e in errors) / n)
    bias = sum(errors) / n

    if rms <= NORMAL_RMS_DEGREES:
        band = "normal"
    elif rms <= IMPAIRED_RMS_DEGREES:
        band = "reduced"
    else:
        band = "impaired"

    side = "right" if bias > 5 else "left" if bias < -5 else None
    return {
        "trials": n,
        "rms_error_deg": round(rms, 1),
        "mean_signed_error_deg": round(bias, 1),
        "reversals": front_back,
        "band": band,
        "pulled_toward": side,
        "interpretation": (
            f"Localization error {rms:.0f}° RMS over {n} trials — "
            + {"normal": "within the normal range (≤10°).",
               "reduced": "above the normal range; expect difficulty in noise.",
               "impaired": "markedly impaired; the interaural cues are not usable."}[band]
            + (f" Responses are pulled toward the {side} by {abs(bias):.0f}° on "
               "average, the direction of the better ear."
               if side else "")
            + (f" {front_back} left/right reversal(s)." if front_back else "")
        ),
        "normative": f"Normal ≤ {NORMAL_RMS_DEGREES:g}°, impaired above {IMPAIRED_RMS_DEGREES:g}°",
    }


# ---------------------------------------------------------------------------
# 2. Speech reception threshold in noise
# ---------------------------------------------------------------------------
#
# The digit-triplet test presents spoken digits against speech-shaped noise
# and adapts the signal-to-noise ratio to find the SNR at which half the
# triplets are repeated correctly. It is the instrument behind national
# telephone and online hearing screening programmes, because it measures the
# complaint people actually have and is robust to uncalibrated equipment:
# only the RATIO of speech to noise matters, not the absolute level.

SRTN_NORMAL_MAX = -7.0      # dB SNR; better (more negative) is normal
SRTN_INSUFFICIENT_MAX = -4.5

#: The digits-in-noise bands are PROVISIONAL. Published digits-in-noise
#: cut-offs belong to one recording, masker, language and delivery route —
#: e.g. good below -5.5 and poor above -2.8 dB SNR for the Dutch national
#: test (Smits, Merkus & Houtgast 2006), -5.7 dB SNR for the US telephone
#: test (Watson et al. 2012), -8.5 dB SNR for a computer-administered
#: version (Folmer et al. 2017) — and none was validated on this browser
#: test, whose digits come from the device's speech synthesiser. The
#: -7.0 / -4.5 dB pair is not traceable to a published validation; it lies
#: inside the published span (stricter than the telephone tests, more lenient
#: than the computer-administered one), so it cannot be shown to err in a
#: safe direction either. Every result therefore carries the provisional
#: flag, and the audiogram cross-check treats a band as a reason to
#: investigate, never as a diagnosis, until a calibration study on this test
#: supplies its own cut-offs.
DIN_BANDS_PROVISIONAL = True

#: The adaptive tracks stop at six reversals (frontend digitsInNoise.js, which
#: the babble screen extends), and the estimator then discards two and
#: averages four. A track with fewer
#: reversals was cut short by the trial cap or entered by hand; its SRT rests
#: on too few turning points to band with confidence, and is flagged so.
MIN_RELIABLE_REVERSALS = 6


def _srt_estimate(reversals: List[float]) -> Tuple[float, int]:
    """SRT (dB SNR, rounded to 0.1 dB) and the number of reversals averaged.

    The first two reversals come from the coarse opening steps and are
    discarded when at least three would remain; a shorter track averages
    every reversal it has (and is flagged low-reliability by the caller).
    The SRT is rounded BEFORE it is banded, so the value on screen and the
    band printed beside it are always the same number's.
    """
    used = reversals[2:] if len(reversals) > 4 else reversals
    return round(sum(used) / len(used), 1), len(used)


def _srt_band(srt: float) -> str:
    if srt <= SRTN_NORMAL_MAX:
        return "normal"
    if srt <= SRTN_INSUFFICIENT_MAX:
        return "insufficient"
    return "poor"


def _reliability(n_reversals: int) -> Tuple[bool, Optional[str]]:
    if n_reversals >= MIN_RELIABLE_REVERSALS:
        return True, None
    return False, (
        f"Only {n_reversals} reversal(s) recorded — fewer than the "
        f"{MIN_RELIABLE_REVERSALS} the adaptive protocol requires — so this "
        "SRT is low-reliability. Repeat the test before relying on the band.")


def score_digits_in_noise(reversals: List[float]) -> Optional[dict]:
    """SRT in noise from the adaptive track's reversal SNRs."""
    if not reversals:
        return None
    srt, n_used = _srt_estimate(reversals)
    band = _srt_band(srt)
    meaning = {
        "normal": "Speech reception in noise is within the normal range.",
        "insufficient": (
            "Speech reception in noise is below normal — the patient will "
            "struggle in restaurants, meetings and classrooms even though "
            "quiet conversation may seem fine."),
        "poor": (
            "Speech reception in noise is poor. This is the complaint that "
            "usually brings people to a clinic, and it is invisible on a "
            "pure-tone audiogram taken in a quiet booth."),
    }[band]
    reliable, reliability_note = _reliability(len(reversals))

    return {
        "srt_db_snr": srt,
        "reversals_used": n_used,
        "reversals_total": len(reversals),
        "reliable": reliable,
        "reliability_note": reliability_note,
        "band": band,
        "interpretation": meaning if reliable else f"{reliability_note} {meaning}",
        "normative": (f"Provisional: normal ≤ {SRTN_NORMAL_MAX:g} dB SNR, "
                      f"insufficient to {SRTN_INSUFFICIENT_MAX:g}, poor above that. "
                      "These cut-offs are not validated for this test; published "
                      "digits-in-noise cut-offs are specific to each test version"),
        "provisional_bands": DIN_BANDS_PROVISIONAL,
        "method": "Adaptive digit-triplet test, 1-up/1-down, SRT at 50% correct",
    }


#: Babble bands are PROVISIONAL: they reuse the steady-noise cutoffs — which
#: are themselves provisional (DIN_BANDS_PROVISIONAL) — until a clinical
#: calibration study supplies babble-specific ones. Multi-talker
#: babble adds informational masking on top of energetic masking, so real
#: babble SRTs run a few dB worse than steady-noise SRTs at the same hearing —
#: reusing the steady-noise bands therefore errs toward OVER-referral, which
#: is the safe direction for a screen.
BABBLE_BANDS_PROVISIONAL = True


def score_speech_babble(reversals: List[float]) -> Optional[dict]:
    """SRT against multi-talker babble, from the adaptive track's reversals.

    Same estimator as the digit-triplet test — discard the first two
    reversals when enough exist, average the rest — because the adaptive rule
    is identical; only the masker differs.
    """
    if not reversals:
        return None
    srt, n_used = _srt_estimate(reversals)
    band = _srt_band(srt)
    meaning = {
        "normal": ("Speech reception against competing talkers is within the "
                   "normal range."),
        "insufficient": (
            "Speech reception against competing talkers is below normal — "
            "exactly the situation of a family meal or a busy clinic, and "
            "harder than steady noise because the babble also competes for "
            "attention."),
        "poor": (
            "Speech reception against competing talkers is poor. Babble is "
            "the everyday worst case — several voices at once — and this "
            "result predicts real difficulty in any group conversation."),
    }[band]
    reliable, reliability_note = _reliability(len(reversals))

    return {
        "srt_db_snr": srt,
        "reversals_used": n_used,
        "reversals_total": len(reversals),
        "reliable": reliable,
        "reliability_note": reliability_note,
        "band": band,
        "interpretation": meaning if reliable else f"{reliability_note} {meaning}",
        "normative": (f"Provisional: steady-noise cutoffs reused (themselves not "
                      f"validated for this test) — normal ≤ {SRTN_NORMAL_MAX:g} dB "
                      f"SNR, insufficient to {SRTN_INSUFFICIENT_MAX:g}, poor above "
                      "that"),
        "provisional_bands": BABBLE_BANDS_PROVISIONAL,
        "method": ("Adaptive digit-triplet test against multi-talker babble, "
                   "1-up/1-down, SRT at 50% correct"),
    }


#: WHO (2021) World Report on Hearing: a four-frequency (0.5/1/2/4 kHz) PTA
#: below 20 dB HL is normal hearing; 20 dB HL is already a mild loss. The
#: same report grades a normal better ear with a worse ear of 35 dB HL or more
#: as "unilateral" loss, not normal hearing — so a normal audiogram here means
#: both ears below 20 dB HL, not the better ear alone.
WHO_NORMAL_PTA_BELOW = 20.0

#: A four-frequency PTA averages a high-frequency notch away (5/5/10/55 dB HL
#: is a PTA of 18.8). "Hidden" hearing loss is defined against the whole
#: audiogram — every standard frequency 0.25-8 kHz below 20 dB HL in both
#: ears (Liberman et al. 2016, PLoS ONE 11:e0162726, inclusion criterion) —
#: so any tested threshold at or above this level makes the loss visible,
#: not hidden.
NORMAL_THRESHOLD_BELOW = 20.0


def _raised_thresholds(ac) -> Dict[int, float]:
    """Tested frequencies whose threshold is outside normal limits."""
    numeric = ear_to_numeric(ac or {})
    return {f: v for f, v in sorted(numeric.items())
            if v is not None and v >= NORMAL_THRESHOLD_BELOW}


def _describe_raised(side: str, raised: Dict[int, float]) -> str:
    return (f"the {side} ear at "
            + ", ".join(f"{f} Hz ({v:g} dB HL)" for f, v in raised.items()))


def compare_srtn_with_audiogram(srtn: Optional[dict], right_ac, left_ac) -> Optional[dict]:
    """Flag the mismatch that matters: normal tones, poor speech in noise.

    "Hidden hearing loss" means a normal audiogram — both ears, every tested
    frequency — with poor speech in noise. When only one ear is normal, or a
    normal PTA hides a raised threshold, the audiogram is not normal, and the
    note says where rather than calling the thresholds normal.
    """
    if not srtn:
        return None
    r, l = _pta(right_ac), _pta(left_ac)
    if r is None or l is None:
        return None
    # Rounded before classification, so the PTA shown and the normal/abnormal
    # call made on it cannot disagree.
    r, l = round(r, 1), round(l, 1)
    better_side, worse_side = ("right", "left") if r <= l else ("left", "right")
    better, worse = min(r, l), max(r, l)
    better_normal = better < WHO_NORMAL_PTA_BELOW
    both_normal = worse < WHO_NORMAL_PTA_BELOW
    raised = {"right": _raised_thresholds(right_ac), "left": _raised_thresholds(left_ac)}
    any_raised = bool(raised["right"] or raised["left"])
    abnormal_srt = srtn["band"] in ("insufficient", "poor")
    hidden = both_normal and not any_raised and abnormal_srt
    raised_text = " and ".join(_describe_raised(side, raised[side])
                               for side in ("right", "left") if raised[side])

    if both_normal and any_raised and abnormal_srt:
        note = (
            f"Both pure-tone averages are within normal limits (right {r:g}, left "
            f"{l:g} dB HL), but thresholds are raised in {raised_text}. The "
            "four-frequency average hides that loss; it is visible on the "
            "audiogram and can itself make speech in noise harder to follow, so "
            "this is not hidden hearing loss. Investigate the raised "
            "frequencies before attributing the result to anything else.")
    elif both_normal and any_raised:
        note = (
            "Speech reception in noise is in the normal band, but thresholds are "
            f"raised in {raised_text} although both pure-tone averages are within "
            "normal limits. A normal screen does not rule that loss out; the "
            "audiogram should guide management.")
    elif hidden:
        note = (
            "Pure-tone thresholds are normal in both ears — every tested threshold "
            f"below {NORMAL_THRESHOLD_BELOW:g} dB HL (PTA right {r:g}, left {l:g} "
            "dB HL) — but speech reception in noise is not. This "
            "dissociation — sometimes called hidden hearing loss — is why a "
            "patient with a clean audiogram can still be unable to follow "
            "conversation in a crowd. Counsel accordingly rather than "
            "reassuring on the audiogram alone.")
    elif abnormal_srt and better_normal:
        note = (
            f"The {better_side} ear's pure-tone average is normal ({better:g} dB HL) "
            f"but the {worse_side} ear's is not ({worse:g} dB HL), so the audiogram "
            "is not normal and this is not hidden hearing loss: a one-sided loss "
            "can itself make speech in noise harder to follow. Investigate the "
            f"{worse_side} ear.")
    elif not abnormal_srt and better_normal and not both_normal:
        note = (
            f"Speech reception in noise is in the normal band, consistent with the "
            f"normal {better_side} ear ({better:g} dB HL). A speech-in-noise screen "
            "heard with both ears is carried largely by the better ear and does "
            f"not assess the {worse_side} ear ({worse:g} dB HL).")
    elif not abnormal_srt and not better_normal:
        note = (
            "Speech reception in noise is in the normal band despite a pure-tone "
            f"loss (better-ear PTA {better:g} dB HL). A normal screen does not rule "
            "the loss out; the audiogram should guide management.")
    else:
        note = "Speech-in-noise performance is consistent with the pure-tone result."

    if srtn.get("provisional_bands"):
        note += (" The speech-in-noise bands are provisional — not yet validated "
                 "for this test — so treat this as a reason to investigate, not "
                 "as a diagnosis.")
    if srtn.get("reliable") is False:
        note += (f" The SRT rests on fewer than {MIN_RELIABLE_REVERSALS} reversals; "
                 "repeat it before acting on this comparison.")

    return {
        "better_ear_pta": better,
        "better_ear": better_side,
        "right_pta": r,
        "left_pta": l,
        "srt_band": srtn["band"],
        "hidden_hearing_loss": hidden,
        "raised_thresholds": raised,
        "provisional_bands": bool(srtn.get("provisional_bands")),
        "srt_reliable": srtn.get("reliable", True),
        "normal_criterion": ("WHO 2021: four-frequency PTA (0.5–4 kHz) below 20 dB HL; "
                             "hidden hearing loss additionally requires every tested "
                             "threshold (0.25–8 kHz) below 20 dB HL in both ears"),
        "note": note,
    }


# ---------------------------------------------------------------------------
# 3. Tinnitus
# ---------------------------------------------------------------------------
#
# Tinnitus is matched rather than measured: the patient adjusts a tone until
# it sounds like their tinnitus, giving a pitch and a loudness in sensation
# level above their own threshold at that pitch. The matched pitch usually
# falls inside the region of hearing loss, which is itself the strongest
# evidence for the prevailing model of tinnitus as a central response to
# lost input.
#
# Notched sound therapy removes a half-octave band centred on the matched
# pitch from a noise carrier, on the reasoning that stimulating the
# neighbouring regions while starving the tinnitus frequency encourages
# lateral inhibition.

NOTCH_WIDTH_OCTAVES = 0.5


def analyze_tinnitus(
    match: dict,
    right_ac: Optional[dict] = None,
    left_ac: Optional[dict] = None,
) -> Optional[dict]:
    """Interpret a tinnitus match and derive notched-therapy parameters.

    ``match``: {"pitch_hz", "loudness_db_sl", "ear", "minimum_masking_db",
                "residual_inhibition_s"}
    """
    pitch = match.get("pitch_hz")
    if not pitch:
        return None
    pitch = float(pitch)
    ear = match.get("ear", "both")
    loudness = match.get("loudness_db_sl")

    ac = right_ac if ear == "right" else left_ac if ear == "left" else (right_ac or left_ac)
    threshold_at_pitch = None
    in_loss_region = None
    if ac:
        from app.services.phonemes import interpolate_threshold
        threshold_at_pitch = interpolate_threshold(ac, pitch)
        if threshold_at_pitch is not None:
            in_loss_region = threshold_at_pitch > 25

    notch_low = round(pitch / (2 ** (NOTCH_WIDTH_OCTAVES / 2)))
    notch_high = round(pitch * (2 ** (NOTCH_WIDTH_OCTAVES / 2)))

    notes: List[str] = []
    if in_loss_region:
        notes.append(
            f"The matched pitch ({pitch:.0f} Hz) falls inside the region of "
            f"hearing loss (threshold {threshold_at_pitch:.0f} dB HL there). "
            "This is the expected relationship and supports amplification of "
            "that region as first-line management.")
    elif in_loss_region is False:
        notes.append(
            f"The matched pitch ({pitch:.0f} Hz) sits in a region of normal "
            "hearing, which is less typical — review the match and consider "
            "further investigation.")
    if loudness is not None and float(loudness) <= 10:
        notes.append(
            f"Matched loudness is only {float(loudness):.0f} dB above the "
            "patient's own threshold. Tinnitus loudness is characteristically "
            "low; distress correlates with intrusiveness, not with level, and "
            "this is worth telling the patient explicitly.")
    if match.get("residual_inhibition_s"):
        notes.append(
            f"Residual inhibition lasted {match['residual_inhibition_s']:.0f} s "
            "after masking — a positive sign for sound-therapy approaches.")

    return {
        "pitch_hz": pitch,
        "ear": ear,
        "loudness_db_sl": loudness,
        "threshold_at_pitch": (None if threshold_at_pitch is None
                               else round(threshold_at_pitch, 1)),
        "matches_loss_region": in_loss_region,
        "minimum_masking_db": match.get("minimum_masking_db"),
        "residual_inhibition_s": match.get("residual_inhibition_s"),
        "notch": {
            "centre_hz": round(pitch),
            "low_hz": notch_low,
            "high_hz": notch_high,
            "width_octaves": NOTCH_WIDTH_OCTAVES,
        },
        "notes": notes,
        "therapy": (
            "Notched sound therapy removes a half-octave band centred on the "
            f"matched pitch ({notch_low}–{notch_high} Hz) from a noise "
            "carrier. Evidence is mixed and it is not a cure; it is offered "
            "alongside counselling and, where there is hearing loss, "
            "amplification."),
        "disclaimer": ("Tinnitus matching is subjective and repeat matches vary. "
                       "Sudden, pulsatile or strictly one-sided tinnitus needs "
                       "ENT assessment regardless of this result."),
    }
