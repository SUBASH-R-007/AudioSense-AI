"""Clinic-workflow endpoints: records, noise dose, referral letters, atlas."""
from __future__ import annotations

import io
from typing import List, Optional

import numpy as np
from datetime import date

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.clinical.noise_dose import compute_dose
from app.ml.classifier import PATTERN_LABELS, _bundle, model_available
from app.services import records
from app.services.referral import build_referral_pdf

router = APIRouter(prefix="/api")


# ------------------------------------------------------------- records ----

@router.post("/records/visit")
def save_visit(analysis: dict = Body(...)):
    return records.save_visit(analysis)


#: Generous for a clinic-scale SQLite file; a pilot's year is a few MB.
MAX_RESTORE_BYTES = 50 * 1024 * 1024


@router.get("/records/backup")
def download_backup():
    """The whole records database as one file — the USB-stick workflow.

    This exists because free hosting tiers have ephemeral disks: a redeploy
    or restart wipes the filesystem, and with it every visit saved since the
    last one. Download before redeploying, restore after.
    """
    try:
        data = records.backup_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "no records have been saved yet")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition":
                 f'attachment; filename="audiosense-records-{date.today().isoformat()}.db"'},
    )


@router.post("/records/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Replace the records database with an uploaded backup.

    The upload is validated as a records database before anything is
    touched; a bad file changes nothing and says why.
    """
    data = await file.read()
    if len(data) > MAX_RESTORE_BYTES:
        raise HTTPException(413, "backup larger than 50 MB — not a records file")
    try:
        counts = records.restore_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"restored": True, **counts}


@router.get("/records/patients")
def list_patients(q: str = ""):
    return {"patients": records.list_patients(q)}


@router.get("/records/patients/{patient_id}")
def patient_history(patient_id: int):
    history = records.patient_history(patient_id)
    if not history:
        raise HTTPException(404, "patient not found")
    return history


@router.delete("/records/patients/{patient_id}")
def delete_patient(patient_id: int):
    return {"deleted": records.delete_patient(patient_id)}


# ---------------------------------------------------------- noise dose ----

class Exposure(BaseModel):
    label: str = "exposure"
    level_dba: float
    hours: float


class DoseRequest(BaseModel):
    exposures: List[Exposure]
    nrr: Optional[float] = None
    protection_worn: bool = False


@router.post("/noise-dose")
def noise_dose(req: DoseRequest):
    return compute_dose([e.model_dump() for e in req.exposures],
                        req.nrr, req.protection_worn)


# ------------------------------------------------------------ referral ----

@router.post("/referral")
def referral(payload: dict = Body(...)):
    """One-click ENT referral letter carrying the red flags and findings."""
    pdf_bytes = build_referral_pdf(payload)
    name = ((payload.get("patient") or {}).get("name") or "patient").replace(" ", "_")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Referral_{name}.pdf"'},
    )


# --------------------------------------------------------------- atlas ----

@router.get("/atlas")
def atlas(limit: int = 900):
    """2-D PCA projection of the training set — the population this model knows.

    Plotting a patient on it makes the out-of-distribution flag visual:
    an atypical audiogram lands in empty space, away from every cluster.
    """
    if not model_available():
        raise HTTPException(503, "model not trained")
    b = _bundle()
    if "X_ref" not in b:
        raise HTTPException(503, "reference set missing — retrain the model")

    X = np.asarray(b["X_ref"], dtype=float)
    y = np.asarray(b["y_ref"])
    z = (X - b["global_mean"]) / b["global_std"]

    # PCA by SVD — no extra dependency, and deterministic.
    centred = z - z.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    components = vt[:2]
    coords = centred @ components.T

    idx = np.arange(len(coords))
    if len(idx) > limit:
        rng = np.random.default_rng(7)
        idx = rng.choice(idx, size=limit, replace=False)

    return {
        "points": [
            {"x": round(float(coords[i, 0]), 3), "y": round(float(coords[i, 1]), 3),
             "pattern": str(y[i]), "label": PATTERN_LABELS.get(str(y[i]), str(y[i]))}
            for i in idx
        ],
        "components": components.tolist(),
        "mean": b["global_mean"].tolist(),
        "std": b["global_std"].tolist(),
        "note": "First two principal components of the standardized feature space.",
    }


@router.post("/atlas/project")
def project(ear: dict = Body(...)):
    """Project one ear's audiogram into the atlas coordinate space."""
    from app.ml.features import build_features
    from app.models.schemas import ear_to_numeric

    if not model_available():
        raise HTTPException(503, "model not trained")
    b = _bundle()
    X = np.asarray(b["X_ref"], dtype=float)
    z = (X - b["global_mean"]) / b["global_std"]
    centred = z - z.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    components = vt[:2]

    ac = {int(k): v for k, v in (ear.get("ac") or {}).items()}
    bc = {int(k): v for k, v in (ear.get("bc") or {}).items()}
    x = build_features(ear_to_numeric(ac), ear_to_numeric(bc))
    zq = (x - b["global_mean"]) / b["global_std"] - z.mean(axis=0)
    coords = zq @ components.T
    return {"x": round(float(coords[0]), 3), "y": round(float(coords[1]), 3)}
