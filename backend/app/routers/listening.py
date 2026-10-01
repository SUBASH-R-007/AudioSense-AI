"""Listening Lab endpoints: localization, speech in noise, tinnitus, deep model."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from app.clinical.listening_lab import (
    analyze_tinnitus,
    compare_srtn_with_audiogram,
    predict_localization,
    score_digits_in_noise,
    score_localization,
    score_speech_babble,
)
from app.ml.features import AC_FREQS as MODEL_FREQS
from app.ml.features import BC_FREQS as MODEL_BC_FREQS
from app.ml.features import DB_MAX, DB_MIN, coverage

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


@router.post("/listening/speech-babble")
def speech_babble(req: DigitsRequest):
    """Same request shape as digits-in-noise — only the masker differs."""
    scored = score_speech_babble(req.reversals)
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


def _thresholds_field(value, kind: str) -> Dict[int, object]:
    """Normalise one transducer's thresholds, rejecting anything the models
    cannot represent with a message naming the offending key or value."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{kind} must be an object mapping frequency in Hz to "
                         "a threshold in dB HL")
    out: Dict[int, object] = {}
    for key, v in value.items():
        try:
            f = int(str(key).strip())
        except ValueError:
            raise ValueError(f"{kind} frequency {key!r} is not a whole number of "
                             f"Hz; use one of {MODEL_FREQS}") from None
        if f not in MODEL_FREQS:
            raise ValueError(f"{kind} frequency {f} Hz is not one of the "
                             f"standard audiometric frequencies {MODEL_FREQS}")
        if v is None or (isinstance(v, str) and not v.strip()):
            out[f] = None          # untested
            continue
        if kind == "bc" and f not in MODEL_BC_FREQS:
            # Bone conduction is conventionally tested at 250-4000 Hz only
            # (vibrator output limits, schemas.BC_FREQS); the models have no
            # bone-conduction feature above that, so a value here would be
            # silently unused.
            raise ValueError(f"bc threshold at {f} Hz cannot be used: bone "
                             "conduction is measured, and used by the model, "
                             f"only at {MODEL_BC_FREQS}; send null or omit it")
        if isinstance(v, str) and v.strip().upper() == "NR":
            out[f] = "NR"
            continue
        if isinstance(v, bool):
            raise ValueError(f"{kind} threshold at {f} Hz must be a number, "
                             "'NR' or null")
        try:
            db = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{kind} threshold {v!r} at {f} Hz is not a number, "
                             "'NR' or null") from None
        if not (DB_MIN <= db <= DB_MAX):
            raise ValueError(f"{kind} threshold {db:g} dB HL at {f} Hz is outside "
                             f"{DB_MIN:g}..{DB_MAX:g} dB HL")
        out[f] = db
    return out


class DeepPredictRequest(BaseModel):
    """One ear for the deep ensemble.

    Keys are the standard audiometric frequencies: 250-8000 Hz for air
    conduction, 250-4000 Hz for bone conduction (an 8 kHz bone-conduction
    key is accepted only as null). Values are dB HL in -10..120, "NR", or
    null for untested. At least five of the six air-conduction
    frequencies, including 4 kHz, are needed to describe a configuration.
    """

    ac: Dict[int, object]
    bc: Dict[int, object] = Field(default_factory=dict)

    @field_validator("ac", mode="before")
    @classmethod
    def _check_ac(cls, v):
        return _thresholds_field(v, "ac")

    @field_validator("bc", mode="before")
    @classmethod
    def _check_bc(cls, v):
        return _thresholds_field(v, "bc")

    @model_validator(mode="after")
    def _check_coverage(self):
        from app.models.schemas import ear_to_numeric
        cov = coverage(ear_to_numeric(self.ac))
        if not cov["adequate"]:
            raise ValueError(cov["note"])
        return self


def _validation_message(exc: ValidationError) -> str:
    """One readable sentence per problem, naming the field.

    The frontend shows ``detail`` as text, so the 422 carries a string
    rather than pydantic's list of error objects.
    """
    parts = []
    for err in exc.errors():
        msg = re.sub(r"^Value error,\s*", "", str(err.get("msg", "")))
        loc = ".".join(str(p) for p in err.get("loc", ()))
        named = not loc or msg.startswith(f"{loc} ")
        parts.append(msg if named else f"{loc}: {msg}")
    return "; ".join(parts) or "invalid request"


@router.post(
    "/model/deep-predict",
    openapi_extra={"requestBody": {
        "required": True,
        "content": {"application/json": {
            "schema": DeepPredictRequest.model_json_schema()}},
    }},
)
async def deep_predict(request: Request):
    """Ensemble prediction with epistemic uncertainty separated out.

    The body is a ``DeepPredictRequest``; any problem with it — including
    a body that is not JSON at all — is a 422 whose ``detail`` is one
    readable string naming the field and the reason. The body is read here
    rather than declared as a parameter because FastAPI answers unparseable
    JSON itself, with a list of error objects the frontend cannot show.
    """
    shape = ("request body must be a JSON object with an 'ac' field (and "
             "optionally 'bc')")
    raw = await request.body()
    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not raw.strip():
        raise HTTPException(422, shape)
    if media and media != "application/json" and not media.endswith("+json"):
        raise HTTPException(422, f"request body must be JSON (Content-Type "
                                 f"application/json), not {media}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"request body is not valid JSON: {exc.msg} "
                                 f"(line {exc.lineno}, column {exc.colno})") from None
    except ValueError:
        raise HTTPException(422, "request body is not valid UTF-8 JSON") from None
    except RecursionError:
        # A body nested deeper than the parser's recursion limit (thousands
        # of "[") is not an audiogram; refuse it like any other bad body.
        raise HTTPException(422, "request body is nested too deeply to be an "
                                 "audiogram") from None
    if not isinstance(payload, dict):
        kind = ("null" if payload is None else "array" if isinstance(payload, list)
                else "string" if isinstance(payload, str)
                else "boolean" if isinstance(payload, bool) else "number")
        raise HTTPException(422, f"{shape}, not a JSON {kind}")
    # Model inference is CPU-bound; keep it off the event loop.
    return await run_in_threadpool(_deep_predict, payload)


def _deep_predict(payload: Any):
    from app.ml.deep import deep_available, predict_deep
    from app.ml.features import build_features
    from app.models.schemas import ear_to_numeric

    try:
        req = DeepPredictRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, _validation_message(exc)) from None

    if not deep_available():
        raise HTTPException(503, "deep ensemble not trained")
    ac, bc = ear_to_numeric(req.ac), ear_to_numeric(req.bc)
    features = build_features(ac, bc)
    return predict_deep(features, ac=ac, bc=bc)
