"""The complete diagnostic picture: coverage, convergence and the next test."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import diagnosis as D

router = APIRouter(prefix="/api/diagnosis")


class PictureRequest(BaseModel):
    """Everything the clinic has gathered so far, in whatever state it is in.

    Every field is optional by design — the point of the endpoint is to report
    honestly on a half-finished workup, so a request carrying only an audiogram
    is a legitimate one and gets a legitimate answer.
    """

    #: The response from POST /api/analyze.
    analysis: Optional[dict] = None
    #: The response from POST /api/symptoms/analyze.
    assessment: Optional[dict] = None
    #: The response from POST /api/otoscopy/analyze.
    otoscopy: Optional[dict] = None
    #: The response from POST /api/aep/battery.
    aep: Optional[dict] = None
    #: The response from POST /api/tuning-fork/analyze.
    tuning_fork: Optional[dict] = None
    #: The response from POST /api/boa/analyze.
    boa: Optional[dict] = None
    #: Age in months — only needed to catch the under-six-month case, where
    #: behavioural audiometry is not obtainable and the battery reorders.
    age_months: Optional[float] = Field(default=None, ge=0)
    #: Modality key -> the reason it was deliberately not performed. Silences
    #: the prompt; never substitutes for a result.
    skipped: Optional[Dict[str, str]] = None


@router.get("/reference")
def reference():
    """The battery this module expects, so the interface can state its criteria."""
    return {
        "modalities": D.MODALITIES,
        "significant_abg_db": D.SIGNIFICANT_ABG,
        "infant_months": D.INFANT_MONTHS,
        "confidence_levels": [
            {"key": "insufficient", "meaning": "No thresholds — nothing to interpret yet."},
            {"key": "incomplete", "meaning": "A critical test is outstanding."},
            {"key": "conflicted", "meaning": "Tests performed disagree; resolve before diagnosing."},
            {"key": "provisional", "meaning": "Interpretable, but resting on few modalities."},
            {"key": "adequate", "meaning": "Essential battery complete, limited corroboration."},
            {"key": "corroborated", "meaning": "Independent findings agree, nothing critical outstanding."},
        ],
        "citations": list(D.CITATIONS),
    }


@router.post("/picture")
def picture(req: PictureRequest):
    """Coverage, convergence and the single most useful next test."""
    return D.diagnostic_picture(
        analysis=req.analysis, assessment=req.assessment, otoscopy=req.otoscopy,
        aep=req.aep, tuning_fork=req.tuning_fork, boa=req.boa,
        age_months=req.age_months, skipped=req.skipped)
