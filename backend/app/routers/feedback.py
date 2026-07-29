"""Clinician correction loop — human-in-the-loop model improvement.

When an audiologist disagrees with the classifier, that disagreement is
the most valuable training signal available. Corrections are appended to
a JSONL file with the full feature-bearing thresholds so the model can be
retrained on real, expert-labelled data rather than only synthetic cases.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.ml.classifier import PATTERN_LABELS

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"


class Correction(BaseModel):
    ear: str
    predicted: Optional[str] = None
    confidence: Optional[float] = None
    corrected: str
    thresholds: Dict[str, Dict[str, object]] = {}
    note: str = ""
    clinician: str = ""


@router.post("/feedback")
def submit_correction(c: Correction):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        **c.model_dump(),
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "stored": True, **feedback_stats()}


@router.get("/feedback")
def feedback_stats():
    """Correction counts — surfaced in the UI as a model-improvement signal."""
    entries: List[dict] = []
    if FEEDBACK_PATH.exists():
        for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_pattern: Dict[str, int] = {}
    for e in entries:
        key = e.get("corrected", "unknown")
        by_pattern[key] = by_pattern.get(key, 0) + 1
    disagreements = sum(
        1 for e in entries if e.get("predicted") and e["predicted"] != e.get("corrected")
    )
    return {
        "total": len(entries),
        "disagreements": disagreements,
        "agreement_pct": (
            round(100 * (len(entries) - disagreements) / len(entries), 1)
            if entries else None
        ),
        "by_corrected_pattern": {
            PATTERN_LABELS.get(k, k): v for k, v in sorted(by_pattern.items())
        },
        "retrain_ready": len(entries) >= 25,
        "note": "Corrections are appended to data/feedback.jsonl and folded into "
                "the next training run.",
    }
