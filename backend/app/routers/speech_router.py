"""Speech audiometry as a standalone instrument: SDT, SRT and WRS.

Speech testing is routinely done on its own — a paediatric SDT, a word-score
check after a hearing-aid fitting, a validity re-test before certification —
so it does not require a full pure-tone record to run.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import speech_audiometry as S
from app.models.schemas import SpeechPoint, ThresholdValue

router = APIRouter(prefix="/api/speech")


class SpeechRequest(BaseModel):
    ear: str = "right"
    ac: Dict[int, Optional[ThresholdValue]] = Field(default_factory=dict)
    #: The opposite ear's thresholds, used only to decide whether an unmasked
    #: SRT could be a shadow response.
    opposite_ac: Dict[int, Optional[ThresholdValue]] = Field(default_factory=dict)
    sdt: Optional[int] = None
    srt: Optional[int] = None
    speech_masked: bool = False
    wrs: List[SpeechPoint] = Field(default_factory=list)


class CompareRequest(BaseModel):
    right_score: float = Field(ge=0, le=100)
    left_score: float = Field(ge=0, le=100)
    n_words: int = Field(default=25, ge=1, le=200)


@router.get("/reference")
def reference():
    """The criteria, so the interface can show what it is measuring against."""
    return {
        "srt_agreement_db": S.SRT_AGREEMENT_DB,
        "sdt_srt_expected_db": list(S.SDT_SRT_EXPECTED_DB),
        "rollover_threshold": S.ROLLOVER_THRESHOLD,
        "suprathreshold_sl_db": S.SUPRATHRESHOLD_SL_DB,
        "speech_interaural_attenuation_db": S.SPEECH_INTERAURAL_ATTENUATION_DB,
        "wrs_bands": [{"low": lo, "high": hi, "label": label}
                      for lo, hi, label in S.WRS_BANDS],
        "tests": [
            {"key": "sdt", "name": "Speech Detection Threshold",
             "measures": "The lowest level at which speech is detected, without "
                         "needing to be understood.",
             "use": "The fallback when an SRT cannot be obtained — infants, "
                    "profound loss, or no language in common.",
             "expects": "Tracks the best pure-tone threshold, and sits "
                        f"{S.SDT_SRT_EXPECTED_DB[0]}-{S.SDT_SRT_EXPECTED_DB[1]} dB "
                        "better than the SRT."},
            {"key": "srt", "name": "Speech Reception Threshold",
             "measures": "The lowest level at which half a spondee list is "
                         "repeated correctly.",
             "use": "The internal-consistency check on pure-tone thresholds.",
             "expects": f"Agrees with the pure-tone average within "
                        f"{S.SRT_AGREEMENT_DB} dB."},
            {"key": "wrs", "name": "Word Recognition Score",
             "measures": "Percentage of monosyllabic words repeated correctly "
                         "at a suprathreshold level.",
             "use": "How much use the patient can make of audible speech, and "
                    "the rollover check for retrocochlear pathology.",
             "expects": f"Measured {S.SUPRATHRESHOLD_SL_DB} dB or more above the "
                        "SRT, where PB max is reached."},
        ],
        "citations": [
            "Chaiklin (1959); ASHA (1988) — threshold level for speech",
            "Thornton & Raffin (1978) — binomial variability of word scores",
            "Jerger & Jerger (1971) — rollover and site of lesion",
        ],
        "note": ("A word score is a sample, not a measurement. Every score here "
                 "carries its exact binomial confidence interval, and comparisons "
                 "are tested rather than eyeballed."),
    }


@router.post("/analyze")
def analyze(req: SpeechRequest):
    """SDT, SRT and WRS for one ear, with the cross-checks between them."""
    numeric = [v for v in req.ac.values() if isinstance(v, int)]
    pta = round(sum(numeric) / len(numeric), 1) if numeric else None

    srt = S.srt_agreement(req.ac, req.srt, masked=req.speech_masked,
                          opposite_ac=req.opposite_ac or None)
    sdt = S.sdt_analysis(req.ac, req.sdt, req.srt)
    wrs = S.wrs_analysis([p.model_dump() for p in req.wrs], pta, req.srt)

    flags: List[str] = []
    if srt and srt["non_organic_suspected"]:
        flags.append("non_organic")
    if srt and srt["masking_note"]:
        flags.append("speech_masking_required")
    if sdt:
        flags.extend(sdt["flags"])
    if wrs and wrs["rollover"]:
        flags.append("rollover")
    if wrs and wrs["adequate_level"] is False:
        flags.append("wrs_level_too_low")

    return {
        "ear": req.ear,
        "sdt": sdt,
        "srt": srt,
        "wrs": wrs,
        "flags": flags,
        "retrocochlear_suspicion": bool(
            wrs and (wrs["rollover"] or wrs["disproportionate"])),
        "available": bool(sdt or srt or wrs),
    }


@router.post("/compare")
def compare(req: CompareRequest):
    """Is a word-score difference larger than the list can resolve?"""
    significant = S.scores_differ(req.right_score, req.left_score, req.n_words)
    correct = round(req.right_score * req.n_words / 100)
    return {
        "right_score": req.right_score,
        "left_score": req.left_score,
        "n_words": req.n_words,
        "difference": round(req.right_score - req.left_score, 1),
        "significant": significant,
        "right_ci": S.binomial_ci(correct, req.n_words),
        "left_ci": S.binomial_ci(round(req.left_score * req.n_words / 100),
                                 req.n_words),
        "message": (
            "The difference exceeds what this list length can attribute to "
            "chance." if significant else
            f"A {abs(req.right_score - req.left_score):g}-point difference is "
            f"within the range a {req.n_words}-word list cannot resolve."
        ),
    }
