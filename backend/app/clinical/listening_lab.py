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
from typing import Dict, List, Optional

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


def score_digits_in_noise(reversals: List[float]) -> Optional[dict]:
    """SRT in noise from the adaptive track's reversal SNRs."""
    if not reversals:
        return None
    # Convention: discard the first two reversals, average the rest.
    used = reversals[2:] if len(reversals) > 4 else reversals
    srt = sum(used) / len(used)

    if srt <= SRTN_NORMAL_MAX:
        band, meaning = "normal", (
            "Speech reception in noise is within the normal range.")
    elif srt <= SRTN_INSUFFICIENT_MAX:
        band, meaning = "insufficient", (
            "Speech reception in noise is below normal — the patient will "
            "struggle in restaurants, meetings and classrooms even though "
            "quiet conversation may seem fine.")
    else:
        band, meaning = "poor", (
            "Speech reception in noise is poor. This is the complaint that "
            "usually brings people to a clinic, and it is invisible on a "
            "pure-tone audiogram taken in a quiet booth.")

    return {
        "srt_db_snr": round(srt, 1),
        "reversals_used": len(used),
        "band": band,
        "interpretation": meaning,
        "normative": (f"Normal ≤ {SRTN_NORMAL_MAX:g} dB SNR, "
                      f"insufficient to {SRTN_INSUFFICIENT_MAX:g}, poor above that"),
        "method": "Adaptive digit-triplet test, 1-up/1-down, SRT at 50% correct",
    }


def compare_srtn_with_audiogram(srtn: Optional[dict], right_ac, left_ac) -> Optional[dict]:
    """Flag the mismatch that matters: normal tones, poor speech in noise."""
    if not srtn:
        return None
    r, l = _pta(right_ac), _pta(left_ac)
    if r is None or l is None:
        return None
    better = min(r, l)
    hidden = better <= 20 and srtn["band"] in ("insufficient", "poor")
    return {
        "better_ear_pta": round(better, 1),
        "srt_band": srtn["band"],
        "hidden_hearing_loss": hidden,
        "note": (
            "Pure-tone thresholds are normal but speech reception in noise is "
            "not. This dissociation — sometimes called hidden hearing loss — is "
            "why a patient with a clean audiogram can still be unable to follow "
            "conversation in a crowd. Counsel accordingly rather than "
            "reassuring on the audiogram alone."
            if hidden else
            "Speech-in-noise performance is consistent with the pure-tone result."
        ),
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
