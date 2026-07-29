"""Progression endpoint: two dated tests -> deltas + OSHA/ASHA flags."""
from __future__ import annotations

from fastapi import APIRouter

from app.clinical import progression, rules
from app.clinical.forecast import forecast
from app.models.schemas import ProgressionRequest

router = APIRouter(prefix="/api")


@router.post("/progression")
def progression_endpoint(req: ProgressionRequest):
    result = progression.compare_tests(
        {"right": {"ac": req.baseline.right.ac}, "left": {"ac": req.baseline.left.ac}},
        {"right": {"ac": req.current.right.ac}, "left": {"ac": req.current.left.ac}},
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
