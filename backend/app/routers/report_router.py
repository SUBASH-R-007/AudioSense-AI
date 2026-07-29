"""MODULE 6 endpoint: structured analysis -> verified report + counseling."""
from __future__ import annotations

from fastapi import APIRouter, Body

from app.services.report import generate_report

router = APIRouter(prefix="/api")


@router.post("/report")
def report(analysis: dict = Body(...)):
    return generate_report(analysis)
