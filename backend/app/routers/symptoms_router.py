"""Signs and symptoms: complaint in, differential and test battery out."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.clinical import symptoms as S

router = APIRouter(prefix="/api/symptoms")


class SymptomRequest(BaseModel):
    age: int = Field(ge=0, le=120, default=40)
    sex: str = "unspecified"
    #: Presenting complaint keys ("otorrhea", "otalgia", "vertigo", "headache").
    complaints: List[str] = Field(default_factory=list)
    #: Canonical symptom keys from the checklist, free text, or both.
    symptoms: List[str] = Field(default_factory=list)
    #: Anything the patient said that does not fit a checkbox.
    notes: str = ""
    side: str = "unspecified"
    duration: str = "unspecified"
    onset: str = "unknown"


@router.get("/catalog")
def catalog():
    """Complaints, grouped symptom checklist and the disease reference."""
    return S.catalog()


@router.post("/analyze")
def analyze(req: SymptomRequest):
    """Ranked differential, red flags and the test battery that separates them."""
    reported = list(req.symptoms)
    if req.notes.strip():
        # Free text is split on connectives so "discharge and pain, no fever"
        # yields separate fragments to match, and unmatched fragments are
        # reported back rather than dropped.
        parts = [p.strip() for p in
                 req.notes.replace(";", ",").replace(" and ", ",").split(",")]
        reported.extend(p for p in parts if p)

    result = S.assess(
        age=req.age, complaints=req.complaints, symptoms=reported,
        side=req.side, duration=req.duration, onset=req.onset,
    )
    result["sex"] = req.sex
    return result


@router.post("/correlate")
def correlate(payload: dict = Body(...)):
    """Check a symptom-based differential against measured thresholds."""
    return S.correlate(payload.get("assessment") or {}, payload.get("analysis"))
