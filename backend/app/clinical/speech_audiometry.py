"""Speech audiometry cross-checks: SRT agreement, WRS, and rollover.

Pure-tone thresholds are a voluntary response and can be exaggerated;
speech audiometry is the standard internal consistency check.

- SRT (Speech Reception Threshold) should agree with the pure-tone average
  within about 10 dB. When the SRT is substantially BETTER than the PTA,
  the pure-tone thresholds are likely exaggerated — the classic sign of a
  non-organic (functional) hearing loss, which matters in compensation and
  disability-certification settings.

- Word recognition (WRS) that is disproportionately poor for the degree of
  loss, or that ROLLS OVER (falls as presentation level rises), suggests
  retrocochlear pathology rather than a cochlear lesion.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import PTA_FREQS, ThresholdValue, ear_to_numeric

#: Acceptable |PTA − SRT| agreement, dB.
SRT_AGREEMENT_DB = 10
#: Rollover index above this suggests a retrocochlear site of lesion.
ROLLOVER_THRESHOLD = 0.45

WRS_BANDS = [
    (90, 100, "Excellent — normal word recognition"),
    (76, 90, "Good — slight difficulty with speech"),
    (60, 76, "Fair — moderate difficulty following conversation"),
    (40, 60, "Poor — marked difficulty; limited benefit from amplification alone"),
    (0, 40, "Very poor — amplification alone unlikely to restore understanding"),
]


def pta_two_frequency(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[float]:
    """Two-frequency PTA (500/1000 Hz) — the classic SRT comparator.

    For steeply sloping losses the 500/1000 Hz average predicts the SRT
    better than the four-frequency PTA does.
    """
    numeric = ear_to_numeric(ac)
    vals = [numeric[f] for f in (500, 1000) if numeric.get(f) is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def srt_agreement(ac: Dict[int, Optional[ThresholdValue]], srt: Optional[int]) -> Optional[dict]:
    """Compare SRT with the pure-tone average and flag disagreement."""
    if srt is None:
        return None
    numeric = ear_to_numeric(ac)
    pta_vals = [numeric[f] for f in PTA_FREQS if numeric.get(f) is not None]
    if not pta_vals:
        return None
    pta = round(sum(pta_vals) / len(pta_vals), 1)
    pta2 = pta_two_frequency(ac)
    comparator = pta2 if pta2 is not None else pta
    diff = round(comparator - srt, 1)  # positive = SRT better than pure tones

    agrees = abs(diff) <= SRT_AGREEMENT_DB
    non_organic = diff > SRT_AGREEMENT_DB  # tones look worse than speech
    return {
        "srt": srt,
        "pta": pta,
        "pta_500_1000": pta2,
        "difference": diff,
        "agrees": agrees,
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


def wrs_analysis(wrs: List[dict], pta: Optional[float] = None) -> Optional[dict]:
    """Interpret word-recognition scores and compute the rollover index.

    Rollover index = (PB max − PB min above the max) / PB max. A value above
    0.45 is the classic retrocochlear indicator.
    """
    points = [{"level": p["level"] if isinstance(p, dict) else p.level,
               "score": p["score"] if isinstance(p, dict) else p.score}
              for p in wrs]
    if not points:
        return None
    points.sort(key=lambda p: p["level"])

    best = max(points, key=lambda p: p["score"])
    pb_max = best["score"]
    after = [p for p in points if p["level"] > best["level"]]
    pb_min = min((p["score"] for p in after), default=None)

    rollover_index = None
    rollover = False
    if pb_min is not None and pb_max > 0:
        rollover_index = round((pb_max - pb_min) / pb_max, 3)
        rollover = rollover_index > ROLLOVER_THRESHOLD

    band = next((d for lo, hi, d in WRS_BANDS if lo <= pb_max < hi), WRS_BANDS[0][2])

    # Disproportionately poor word recognition for the degree of loss.
    disproportionate = pta is not None and pta < 50 and pb_max < 60

    notes = []
    if rollover:
        notes.append(
            f"Rollover index {rollover_index} exceeds {ROLLOVER_THRESHOLD} — word "
            "recognition worsens at higher levels, which suggests a retrocochlear "
            "site of lesion. Refer for ENT/neuro-otology assessment."
        )
    if disproportionate:
        notes.append(
            f"Word recognition ({pb_max:g}%) is disproportionately poor for a "
            f"{pta:g} dB HL loss — consider retrocochlear pathology or a "
            "significant cochlear distortion component."
        )
    return {
        "points": points,
        "pb_max": pb_max,
        "pb_max_level": best["level"],
        "pb_min_after_max": pb_min,
        "rollover_index": rollover_index,
        "rollover": rollover,
        "interpretation": band,
        "disproportionate": disproportionate,
        "notes": notes,
    }


def analyze_speech(ear, pta: Optional[float] = None) -> Optional[dict]:
    """Full speech-audiometry review for one ear (EarData)."""
    srt = srt_agreement(ear.ac, ear.srt)
    wrs = wrs_analysis(ear.wrs, pta)
    if srt is None and wrs is None:
        return None
    flags = []
    if srt and srt["non_organic_suspected"]:
        flags.append("non_organic")
    if wrs and wrs["rollover"]:
        flags.append("rollover")
    if wrs and wrs["disproportionate"]:
        flags.append("disproportionate_wrs")
    return {"srt": srt, "wrs": wrs, "flags": flags,
            "retrocochlear_suspicion": bool(wrs and (wrs["rollover"] or wrs["disproportionate"]))}
