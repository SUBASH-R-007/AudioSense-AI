"""Masking: when it is required, how much, and when it cannot be done."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import masking as M
from app.models.schemas import EarData, ThresholdValue

router = APIRouter(prefix="/api/masking")


class MaskingRequest(BaseModel):
    transducer: str = M.DEFAULT_TRANSDUCER
    right: EarData = Field(default_factory=EarData)
    left: EarData = Field(default_factory=EarData)


@router.get("/reference")
def reference():
    """The rules and the transducers, so the interface can state its criteria."""
    return {
        "transducers": [{"key": k, **v} for k, v in M.TRANSDUCERS.items()],
        "default_transducer": M.DEFAULT_TRANSDUCER,
        "interaural_attenuation_bc": M.INTERAURAL_ATTENUATION_BC,
        "bc_masking_gap_db": M.BC_MASKING_GAP_DB,
        "rules": {
            "air_conduction": [
                "AC(test ear) − AC(non-test ear) ≥ IA",
                "AC(test ear) − BC(non-test ear) ≥ IA",
            ],
            "bone_conduction": [
                "AC(test ear) − BC(unmasked) ≥ 15 dB",
                "Air-bone gap ≥ 15 dB",
            ],
        },
        "dilemma": (
            "Masking has a floor and a ceiling: enough noise to cover the "
            "crossed signal, but not so much that it crosses back and shifts "
            "the test ear. When the floor rises above the ceiling there is no "
            "usable level, and the threshold cannot be masked at all."),
        "citations": list(M.CITATIONS),
    }


@router.post("/analyze")
def analyze(req: MaskingRequest):
    """Per-frequency masking requirement for both ears."""
    return M.masking_review(req.right, req.left, req.transducer)
