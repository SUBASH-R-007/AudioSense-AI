"""Progression endpoint: two dated tests -> deltas + OSHA/ASHA flags."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.clinical import progression, rules
from app.clinical.forecast import forecast
from app.models.schemas import ProgressionRequest, ThresholdValue

router = APIRouter(prefix="/api")


class EarPair3k(BaseModel):
    """One test's 3000 Hz air-conduction thresholds, dB HL (or "NR")."""

    right: Optional[ThresholdValue] = None
    left: Optional[ThresholdValue] = None

    @field_validator("right", "left")
    @classmethod
    def _in_range(cls, v):
        if isinstance(v, int) and not (-10 <= v <= 120):
            raise ValueError(f"threshold {v} dB at 3000 Hz outside -10..120")
        return v


class Thresholds3k(BaseModel):
    baseline: EarPair3k = Field(default_factory=EarPair3k)
    current: EarPair3k = Field(default_factory=EarPair3k)


class ProgressionWith3kRequest(ProgressionRequest):
    #: OSHA's STS and recording rules average 2000, 3000 and 4000 Hz, but the
    #: shared audiogram model stops at the octave frequencies. A caller that
    #: tested 3000 Hz supplies it here: both tests' values give the regulatory
    #: STS, and the current value alone completes the 29 CFR 1904.10 hearing
    #: level (taken from the current audiogram only). Without it the STS is
    #: computed on the labelled 2000/4000 Hz proxy and recordability is left
    #: undetermined unless the known values settle it.
    thresholds_3000: Optional[Thresholds3k] = None


@router.post("/progression")
def progression_endpoint(req: ProgressionWith3kRequest):
    t3k = req.thresholds_3000 or Thresholds3k()
    result = progression.compare_tests(
        {"right": {"ac": req.baseline.right.ac, "ac_3000": t3k.baseline.right},
         "left": {"ac": req.baseline.left.ac, "ac_3000": t3k.baseline.left}},
        {"right": {"ac": req.current.right.ac, "ac_3000": t3k.current.right},
         "left": {"ac": req.current.left.ac, "ac_3000": t3k.current.left}},
    )
    return {
        "baseline_date": str(req.baseline.patient.test_date or ""),
        "current_date": str(req.current.patient.test_date or ""),
        "patient": req.current.patient.model_dump(),
        "progression": result,
        "baseline_rules": rules.analyze_test(
            req.baseline.right.ac, req.baseline.right.bc,
            req.baseline.left.ac, req.baseline.left.bc,
        ),
        "current_rules": rules.analyze_test(
            req.current.right.ac, req.current.right.bc,
            req.current.left.ac, req.current.left.bc,
        ),
        "thresholds": {
            "baseline": {"right": req.baseline.right.ac, "left": req.baseline.left.ac},
            "current": {"right": req.current.right.ac, "left": req.current.left.ac},
        },
        "forecast": forecast(
            {"right": req.baseline.right.ac, "left": req.baseline.left.ac},
            {"right": req.current.right.ac, "left": req.current.left.ac},
            str(req.baseline.patient.test_date or ""),
            str(req.current.patient.test_date or ""),
            age=req.current.patient.age,
        ),
    }
