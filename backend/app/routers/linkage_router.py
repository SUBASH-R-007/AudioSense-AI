"""Cross-modal linkage: reconcile history, image, immittance and audiogram."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from app.clinical import linkage
from app.clinical.symptom_kb import (
    DISEASES, OTOSCOPY_LINKS, SYMPTOM_LABELS, TYMPANOGRAM_LINKS,
)

router = APIRouter(prefix="/api/linkage")


def _names(keys):
    """Disease keys expanded to their display names.

    Done here rather than in the client so there is one place that knows how a
    disease is spelled, and the frontend never has to carry a lookup table
    that could drift out of step with the knowledge base.
    """
    return [DISEASES[k]["name"] if k in DISEASES else k for k in keys]


@router.get("/reference")
def reference():
    """The linkage rules themselves, so the UI can explain its own reasoning."""
    return {
        "tympanogram_types": [
            {**v, "type": t,
             "supports": _names(v["supports"]),
             "argues_against": _names(v["argues_against"])}
            for t, v in TYMPANOGRAM_LINKS.items()
        ],
        "otoscopy_patterns": [
            {**v, "pattern": p,
             "expects": [SYMPTOM_LABELS.get(s, s) for s in v["expects"]],
             "unexplained": [SYMPTOM_LABELS.get(s, s) for s in v["unexplained"]],
             "conditions": _names(v["conditions"])}
            for p, v in OTOSCOPY_LINKS.items()
        ],
        "note": ("Every cross-check the app makes comes from these rules. They "
                 "state what each finding predicts about the others, so a "
                 "disagreement can be pointed at rather than asserted."),
    }


@router.post("")
def link(payload: dict = Body(...)):
    """Every available cross-check for one case.

    Accepts whatever exists so far — an analysis, a symptom assessment, an
    otoscopy result, or any subset — and reports which links it could make
    plus what is missing to make the rest.
    """
    return linkage.link_case(
        analysis=payload.get("analysis"),
        assessment=payload.get("assessment"),
        otoscopy=payload.get("otoscopy"),
        side=payload.get("side") or "right",
    )
