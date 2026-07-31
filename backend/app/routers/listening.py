"""Listening Lab endpoints: localization, speech in noise, tinnitus, deep model."""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.clinical.listening_lab import (
    analyze_tinnitus,
    compare_srtn_with_audiogram,
    predict_localization,
    score_digits_in_noise,
    score_localization,
)

router = APIRouter(prefix="/api")


class LocalizationTrial(BaseModel):
    presented_deg: float
    responded_deg: float


class LocalizationRequest(BaseModel):
    trials: List[LocalizationTrial]
    right_ac: Dict[int, Optional[object]] = {}
    left_ac: Dict[int, Optional[object]] = {}


@router.post("/listening/localization")
def localization(req: LocalizationRequest):
    scored = score_localization([t.model_dump() for t in req.trials])
    if not scored:
        raise HTTPException(400, "no trials supplied")
    return {
        "result": scored,
        "predicted_from_audiogram": predict_localization(req.right_ac, req.left_ac),
    }


@router.post("/listening/predict-localization")
def predict_localization_endpoint(payload: dict = Body(...)):
    """Expected localization ability before the patient does the test."""
    right = {int(k): v for k, v in (payload.get("right_ac") or {}).items()}
    left = {int(k): v for k, v in (payload.get("left_ac") or {}).items()}
    result = predict_localization(right, left)
    if not result:
        raise HTTPException(400, "thresholds required for both ears")
    return result


class DigitsRequest(BaseModel):
    reversals: List[float]
    right_ac: Dict[int, Optional[object]] = {}
    left_ac: Dict[int, Optional[object]] = {}


@router.post("/listening/digits-in-noise")
def digits_in_noise(req: DigitsRequest):
    scored = score_digits_in_noise(req.reversals)
    if not scored:
        raise HTTPException(400, "no reversals supplied")
    return {
        "result": scored,
        "versus_audiogram": compare_srtn_with_audiogram(
            scored, req.right_ac, req.left_ac),
    }


class TinnitusRequest(BaseModel):
    pitch_hz: float
    loudness_db_sl: Optional[float] = None
    ear: str = "both"
    minimum_masking_db: Optional[float] = None
    residual_inhibition_s: Optional[float] = None
    right_ac: Dict[int, Optional[object]] = {}
    left_ac: Dict[int, Optional[object]] = {}


@router.post("/listening/tinnitus")
def tinnitus(req: TinnitusRequest):
    result = analyze_tinnitus(
        {
            "pitch_hz": req.pitch_hz,
            "loudness_db_sl": req.loudness_db_sl,
            "ear": req.ear,
            "minimum_masking_db": req.minimum_masking_db,
            "residual_inhibition_s": req.residual_inhibition_s,
        },
        {int(k): v for k, v in req.right_ac.items()},
        {int(k): v for k, v in req.left_ac.items()},
    )
    if not result:
        raise HTTPException(400, "a matched pitch is required")
    return result


# ------------------------------------------------------------ deep model ---

@router.get("/model/comparison")
def model_comparison():
    """Head-to-head between the forest and the neural ensemble."""
    from app.ml.deep import compare_models, deep_available
    if not deep_available():
        raise HTTPException(503, "deep ensemble not trained — run python -m app.ml.deep")
    return compare_models()


@router.post("/model/deep-predict")
def deep_predict(ear: dict = Body(...)):
    """Ensemble prediction with epistemic uncertainty separated out."""
    from app.ml.deep import deep_available, predict_deep
    from app.ml.features import build_features
    from app.models.schemas import ear_to_numeric

    if not deep_available():
        raise HTTPException(503, "deep ensemble not trained")
    ac = {int(k): v for k, v in (ear.get("ac") or {}).items()}
    bc = {int(k): v for k, v in (ear.get("bc") or {}).items()}
    features = build_features(ear_to_numeric(ac), ear_to_numeric(bc))
    return predict_deep(features)
