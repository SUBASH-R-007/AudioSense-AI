"""Speech audiometry as a standalone instrument: SDT, SRT and WRS.

Speech testing is routinely done on its own — a paediatric SDT, a word-score
check after a hearing-aid fitting, a validity re-test before certification —
so it does not require a full pure-tone record to run.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.clinical import rules
from app.clinical import speech_audiometry as S
from app.models.schemas import AC_FREQS, EarData, SpeechPoint, ThresholdValue

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

    # The same threshold rules as a full record (EarData), so this endpoint
    # cannot accept an audiogram the full analysis would reject.
    @field_validator("ac", "opposite_ac")
    @classmethod
    def _validate_thresholds(cls, v: Dict[int, Optional[ThresholdValue]]):
        for freq, val in v.items():
            if freq not in AC_FREQS:
                raise ValueError(f"unsupported frequency {freq} Hz")
            if isinstance(val, int) and not (-10 <= val <= 120):
                raise ValueError(f"threshold {val} dB at {freq} Hz outside -10..120")
        return v


class CompareRequest(BaseModel):
    right_score: float = Field(ge=0, le=100)
    left_score: float = Field(ge=0, le=100)
    n_words: int = Field(default=25, ge=1, le=200)


@router.get("/reference")
def reference():
    """The criteria, so the interface can show what it is measuring against."""
    return {
        "srt_agreement_db": S.SRT_AGREEMENT_DB,
        "srt_comparator_freqs": list(S.SRT_PTA_FREQS),
        "srt_rule": S.SRT_CRITERION,
        "steep_step_db": S.STEEP_STEP_DB,
        "sdt_srt_expected_db": list(S.SDT_SRT_EXPECTED_DB),
        "rollover_threshold": S.ROLLOVER_THRESHOLD,
        "rollover_rule": f"index > {S.ROLLOVER_THRESHOLD}",
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
             "expects": f"Agrees within {S.SRT_AGREEMENT_DB} dB with the "
                        "500/1000/2000 Hz average or with Fletcher's average "
                        "of the best two; better than both by more than "
                        f"{S.SRT_AGREEMENT_DB} dB suggests exaggerated tones."},
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
            "Fletcher (1929, 1950) — three-frequency and best-two averages",
            "Guthrie & Mackersie (2009); Schoepflin (2012) — steep configurations",
            "Thornton & Raffin (1978) — binomial variability of word scores",
            "Goetzinger (1978) — word-recognition categories",
            "Jerger & Jerger (1971); Dirks et al. (1977) — rollover and site of lesion",
            "Meyer & Mishler (1985) — rollover criterion for NU-6 lists",
        ],
        "note": ("A word score is a sample, not a measurement. Every score here "
                 "carries its exact binomial confidence interval, and comparisons "
                 "are tested rather than eyeballed."),
    }


@router.post("/analyze")
def analyze(req: SpeechRequest):
    """SDT, SRT and WRS for one ear, with the cross-checks between them.

    Runs the same bundle as the full analysis (``analyze_speech``) with the
    same PTA — the WHO four-frequency average from the rules engine, "NR" as
    120 dB HL — so one ear cannot be called disproportionate here and not
    there.
    """
    ac_pta = rules.pta(req.ac)
    pta = ac_pta["value"] if ac_pta else None

    ear = EarData(ac=req.ac, sdt=req.sdt, srt=req.srt,
                  speech_masked=req.speech_masked, wrs=req.wrs)
    opposite = EarData(ac=req.opposite_ac) if req.opposite_ac else None
    result = S.analyze_speech(ear, pta, opposite) or {
        "sdt": None, "srt": None, "wrs": None, "flags": [],
        "retrocochlear_suspicion": False,
    }
    sdt, srt, wrs = result["sdt"], result["srt"], result["wrs"]

    return {
        "ear": req.ear,
        "sdt": sdt,
        "srt": srt,
        "wrs": wrs,
        "flags": result["flags"],
        "retrocochlear_suspicion": result["retrocochlear_suspicion"],
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
